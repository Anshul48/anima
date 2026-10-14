"""Test suite for Closed-Loop Browser Automation Engine: DOM Mutation & Pre-Dispatch Re-Grounding."""

import asyncio
import time
import unittest
from typing import Any, Dict, List, Optional

from reflex.episodes.journal import LocalEpisodeJournal
from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.grounding.browser_grounder import BrowserGroundingEngine, GroundingQuery
from reflex.host.kernel.host_kernel import HostControlKernel
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.orchestration.browser_loop import (
    BrowserClosedLoopV1,
    TaskExecutionReport,
    TaskGoal,
    TaskStatus,
)
from reflex.orchestration.session_manager import BrowserSessionManager
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityPolicy
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.verifier import AssertionRule, IndependentVerifier


class DynamicDOMObservationAdapter(ObservationPort):
    """Observation adapter that can dynamically mutate DOM states to simulate layout shifts and re-renders."""

    def __init__(self, initial_graph: CanonicalUIGraph):
        self.active_graph = initial_graph
        self.capture_count = 0

    def mutate_graph(self, new_graph: CanonicalUIGraph) -> None:
        self.active_graph = new_graph

    async def capture_state(self) -> CanonicalUIGraph:
        self.capture_count += 1
        return self.active_graph

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_staleness_bytes"


class TrackingActionAdapter(CDPActionAdapter):
    """Action adapter recording dispatched coordinates and target node IDs."""

    def __init__(self, page: Optional[Any] = None):
        super().__init__(page=page or FakeBrowserPage())
        self.dispatched_proposals: List[TypedAction] = []
        self.dispatched_coords: List[Optional[NormalizedCoords]] = []

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatched_proposals.append(action)
        self.dispatched_coords.append(action.coords)
        return await super().dispatch_action(action, identity)


class TestClosedLoopStaleness(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying pre-dispatch re-grounding and staleness interception on DOM mutations."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)

        # Base UI Graph: Submit button at (100, 100, 200, 140) -> center (150, 120)
        self.initial_button = UIStateNode(
            node_id="btn_submit_order",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(100, 100, 200, 140),
            label="Place Order",
        )
        self.initial_graph = CanonicalUIGraph(
            timestamp_ms=1000000.0,
            nodes={"btn_submit_order": self.initial_button},
            url="https://shop.example.com/checkout",
            viewport_size=(1000, 1000),
        )

        self.obs_adapter = DynamicDOMObservationAdapter(self.initial_graph)
        self.action_adapter = TrackingActionAdapter()
        self.verifier = IndependentVerifier(
            observation_port=self.obs_adapter,
            clock=self.clock,
        )
        self.policy = CapabilityPolicy.default_browser_policy()
        self.kernel = HostControlKernel(
            policy=self.policy,
            action_port=self.action_adapter,
            observation_port=self.obs_adapter,
            verification_port=self.verifier,
            clock=self.clock,
            settle_interval_s=0.0,
        )
        self.journal = LocalEpisodeJournal(db_path=":memory:")
        self.grounder = BrowserGroundingEngine()
        self.session_manager = BrowserSessionManager()

        self.loop = BrowserClosedLoopV1(
            kernel=self.kernel,
            observation_port=self.obs_adapter,
            grounder=self.grounder,
            verifier=self.verifier,
            journal=self.journal,
            session_manager=self.session_manager,
            clock=self.clock,
            enable_pre_dispatch_regrounding=True,
            regrounding_tolerance_px=5,
        )

    async def test_pre_dispatch_regrounding_updates_shifted_coordinates(self):
        """When an element shifts position (layout shift), re-grounding updates coordinates to fresh center."""
        # Initial proposal planned at stale coords (0.15, 0.12) -> (150, 120)
        stale_proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_shift", step_index=1),
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_submit_order",
                coords=NormalizedCoords(0.15, 0.12),  # (150, 120) in (1000, 1000)
                target_label="Place Order",
            ),
        )

        # Mutate DOM before dispatch: Layout shift moves button down to (100, 400, 200, 440) -> center (150, 420)
        shifted_button = UIStateNode(
            node_id="btn_submit_order",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(100, 400, 200, 440),
            label="Place Order",
        )
        shifted_graph = CanonicalUIGraph(
            timestamp_ms=1000500.0,
            nodes={"btn_submit_order": shifted_button},
            url="https://shop.example.com/checkout",
            viewport_size=(1000, 1000),
        )
        self.obs_adapter.mutate_graph(shifted_graph)

        # Run re-grounding check
        updated_proposal, is_stale = await self.loop._reground_proposal_if_needed(
            proposal=stale_proposal,
            current_state=shifted_graph,
        )

        # 1. Assert proposal was updated with fresh coordinates (not stale)
        self.assertFalse(is_stale)
        self.assertIsNotNone(updated_proposal.action.coords)
        px_x, px_y = updated_proposal.action.coords.to_pixel(1000, 1000)
        self.assertEqual(px_x, 150)
        self.assertEqual(px_y, 420)  # Successfully updated from 120 to 420!

    async def test_pre_dispatch_regrounding_resolves_replaced_dom_node(self):
        """When React re-renders and changes node_id from 'btn_submit_1' to 'btn_submit_2', re-grounder resolves new node."""
        # Proposal planned targeting 'btn_old_id'
        stale_proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_rerender", step_index=1),
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_old_id",  # No longer exists in new DOM
                target_label="Place Order",
                metadata={"label": "Place Order"},
            ),
        )

        # Mutate DOM: React re-renders with new node ID 'btn_new_react_id' at (100, 200, 200, 240) -> center (150, 220)
        re_rendered_button = UIStateNode(
            node_id="btn_new_react_id",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(100, 200, 200, 240),
            label="Place Order",
        )
        rerendered_graph = CanonicalUIGraph(
            timestamp_ms=1000600.0,
            nodes={"btn_new_react_id": re_rendered_button},
            url="https://shop.example.com/checkout",
            viewport_size=(1000, 1000),
        )
        self.obs_adapter.mutate_graph(rerendered_graph)

        updated_proposal, is_stale = await self.loop._reground_proposal_if_needed(
            proposal=stale_proposal,
            current_state=rerendered_graph,
        )

        self.assertFalse(is_stale)
        self.assertEqual(updated_proposal.action.target_node_id, "btn_new_react_id")
        self.assertIsNotNone(updated_proposal.action.coords)
        px_x, px_y = updated_proposal.action.coords.to_pixel(1000, 1000)
        self.assertEqual(px_x, 150)
        self.assertEqual(px_y, 220)

    async def test_vanished_target_intercepts_stale_dispatch_safely(self):
        """When target element completely vanishes, pre-dispatch re-grounding intercepts and aborts physical dispatch."""
        # Proposal targeting vanished button
        stale_proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_vanish", step_index=1),
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_completely_gone",
                target_label="Nonexistent Button",
            ),
        )

        # Empty graph (button was removed)
        empty_graph = CanonicalUIGraph(
            timestamp_ms=1000700.0,
            nodes={},
            url="https://shop.example.com/checkout",
            viewport_size=(1000, 1000),
        )
        self.obs_adapter.mutate_graph(empty_graph)

        updated_proposal, is_stale = await self.loop._reground_proposal_if_needed(
            proposal=stale_proposal,
            current_state=empty_graph,
        )

        # Assert staleness detected (aborted before dispatch!)
        self.assertTrue(is_stale)

    async def test_closed_loop_recovers_when_target_temporarily_vanishes(self):
        """Closed loop handles stale target interception, reconciles, and recovers on subsequent step."""
        goal = TaskGoal(
            task_id="task_staleness_recovery",
            instruction="Submit order after temporary staleness",
            target_url="https://shop.example.com/checkout",
            max_steps=5,
        )

        # Step 0 proposal targets nonexistent element; Step 1 targets valid element
        proposals = [
            # Proposal 0: Stale target (will be intercepted)
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_ghost",
                target_label="Ghost Button",
            ),
            # Proposal 1: Valid target
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_submit_order",
                target_label="Place Order",
            ),
        ]

        report = await self.loop.run_task(
            goal=goal,
            proposal_generator=proposals,
        )

        # Verify loop executed step 0 (intercepted stale) and step 1 (completed)
        self.assertEqual(report.status, TaskStatus.COMPLETED)
        self.assertEqual(report.total_steps, 2)

        # Verify Journal recorded the stale target interception transition
        transitions = await self.journal.get_episode_transitions(report.episode_id)
        self.assertEqual(len(transitions), 2)
        self.assertEqual(transitions[0].provenance.get("interception"), "stale_target")
        self.assertEqual(transitions[0].delta.outcome_class, OutcomeClass.ERROR)


if __name__ == "__main__":
    unittest.main()
