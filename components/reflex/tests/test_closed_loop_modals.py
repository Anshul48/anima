"""Test suite for Closed-Loop Browser Automation Engine: Modal Interception & Trajectory Resumption."""

import asyncio
import time
import unittest
from typing import Any, Dict, List, Optional

from reflex.episodes.journal import LocalEpisodeJournal
from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.grounding.browser_grounder import BrowserGroundingEngine
from reflex.host.identity.lease_manager import ActionLeaseManager
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


class ModalTestObservationAdapter(ObservationPort):
    """Dynamic observation adapter that injects a cookie modal overlay at step 2."""

    def __init__(self):
        self.state_sequence_id = "initial"
        self.modal_dismissed = False

        # 1. Base Initial Graph
        self.initial_graph = CanonicalUIGraph(
            timestamp_ms=1000000.0,
            nodes={
                "inp_username": UIStateNode(
                    node_id="inp_username",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(100, 100, 300, 130),
                    label="Username",
                    value="",
                    is_editable=True,
                ),
                "btn_continue": UIStateNode(
                    node_id="btn_continue",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 200, 250, 240),
                    label="Continue to Dashboard",
                ),
            },
            url="https://portal.example.com/login",
            active_window_title="Portal Login",
        )

        # 2. Graph at Step 2: Unexpected Cookie Modal Overlay Appeared!
        self.cookie_modal_graph = CanonicalUIGraph(
            timestamp_ms=1001000.0,
            nodes={
                "inp_username": UIStateNode(
                    node_id="inp_username",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(100, 100, 300, 130),
                    label="Username",
                    value="bob_smith",
                    is_editable=True,
                ),
                "btn_continue": UIStateNode(
                    node_id="btn_continue",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 200, 250, 240),
                    label="Continue to Dashboard",
                ),
                # Modal Overlay & Dialog
                "modal_cookie_banner": UIStateNode(
                    node_id="modal_cookie_banner",
                    role=NodeRole.MODAL,
                    bounds=BoundingBox(0, 0, 1920, 1080),
                    label="Cookie Consent Dialog",
                    children_ids=["btn_accept_cookies"],
                    attributes={"role": "dialog", "class": "cookie-banner modal"},
                ),
                "btn_accept_cookies": UIStateNode(
                    node_id="btn_accept_cookies",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(800, 500, 950, 540),
                    label="Accept All Cookies",
                    parent_id="modal_cookie_banner",
                ),
            },
            url="https://portal.example.com/login",
            active_window_title="Portal Login - Cookies",
        )

        # 3. Post-Dismissal Resumed Graph
        self.resumed_graph = CanonicalUIGraph(
            timestamp_ms=1002000.0,
            nodes={
                "inp_username": UIStateNode(
                    node_id="inp_username",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(100, 100, 300, 130),
                    label="Username",
                    value="bob_smith",
                    is_editable=True,
                ),
                "btn_continue": UIStateNode(
                    node_id="btn_continue",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 200, 250, 240),
                    label="Continue to Dashboard",
                ),
            },
            url="https://portal.example.com/login",
            active_window_title="Portal Login",
        )

        # 4. Final Dashboard Graph
        self.dashboard_graph = CanonicalUIGraph(
            timestamp_ms=1003000.0,
            nodes={
                "h1_welcome": UIStateNode(
                    node_id="h1_welcome",
                    role=NodeRole.TEXT,
                    bounds=BoundingBox(50, 50, 400, 90),
                    label="Welcome back, Bob!",
                )
            },
            url="https://portal.example.com/dashboard",
            active_window_title="Dashboard",
        )

    def transition_to_modal(self) -> None:
        self.state_sequence_id = "modal"

    def transition_to_dismissed(self) -> None:
        self.modal_dismissed = True
        self.state_sequence_id = "resumed"

    def transition_to_dashboard(self) -> None:
        self.state_sequence_id = "dashboard"

    async def capture_state(self) -> CanonicalUIGraph:
        if self.state_sequence_id == "initial":
            return self.initial_graph
        elif self.state_sequence_id == "modal":
            return self.cookie_modal_graph
        elif self.state_sequence_id == "resumed":
            return self.resumed_graph
        elif self.state_sequence_id == "dashboard":
            return self.dashboard_graph
        return self.initial_graph

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_modal_bytes"


class ModalTestActionAdapter(CDPActionAdapter):
    """Action adapter triggering state changes in observation adapter."""

    def __init__(
        self,
        obs_adapter: ModalTestObservationAdapter,
        page: Optional[Any] = None,
        lease_manager: Optional[ActionLeaseManager] = None,
    ):
        super().__init__(page=page or FakeBrowserPage(), lease_manager=lease_manager)
        self.obs_adapter = obs_adapter
        self.dispatched_actions: List[TypedAction] = []

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatched_actions.append(action)

        # Step 1: Type username -> triggers unexpected cookie modal appearance
        if action.action_type == ActionType.TYPE and action.target_node_id == "inp_username":
            self.obs_adapter.transition_to_modal()

        # Modal Dismissal: Click accept cookies -> dismisses modal
        elif action.action_type == ActionType.CLICK and action.target_node_id == "btn_accept_cookies":
            self.obs_adapter.transition_to_dismissed()

        # Step 2: Click Continue -> navigates to Dashboard
        elif action.action_type == ActionType.CLICK and action.target_node_id == "btn_continue":
            self.obs_adapter.transition_to_dashboard()

        return await super().dispatch_action(action, identity)


class TestClosedLoopModals(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying modal detection, automatic dismissal, and seamless trajectory resumption."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)
        self.obs_adapter = ModalTestObservationAdapter()
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.action_adapter = ModalTestActionAdapter(
            self.obs_adapter, lease_manager=self.lease_manager
        )

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
            lease_manager=self.lease_manager,
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
            auto_dismiss_modals=True,
        )

    async def test_unexpected_modal_interception_and_trajectory_resumption(self):
        """Unexpected cookie banner appearing at step 2 is detected, dismissed, and trajectory resumed."""
        goal = TaskGoal(
            task_id="task_login_with_modal",
            instruction="Log in as bob_smith and navigate to dashboard",
            target_url="https://portal.example.com/login",
            max_steps=10,
        )

        # Primary user proposal plan (does not know about cookie banner in advance)
        primary_proposals = [
            # Step 1: Type username -> triggers cookie modal in backend
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_username",
                text_payload="bob_smith",
                target_label="Username",
            ),
            # Step 2: Click Continue -> should succeed after modal is auto-dismissed!
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_continue",
                target_label="Continue to Dashboard",
            ),
        ]

        # Generator yields next proposal
        step_cursor = 0

        def proposal_generator(g: TaskGoal, state: CanonicalUIGraph, step_idx: int) -> Optional[TypedAction]:
            nonlocal step_cursor
            if step_cursor < len(primary_proposals):
                prop = primary_proposals[step_cursor]
                step_cursor += 1
                return prop
            return None

        report = await self.loop.run_task(
            goal=goal,
            proposal_generator=proposal_generator,
        )

        # 1. Assert Task Completion Status
        self.assertEqual(report.status, TaskStatus.COMPLETED)
        self.assertEqual(report.final_url, "https://portal.example.com/dashboard")
        self.assertIsNone(report.error_summary)

        # 2. Assert that modal dismissal was executed
        self.assertTrue(self.obs_adapter.modal_dismissed)

        # 3. Assert Journal Recorded the Transitions (including modal dismissal transition)
        transitions = await self.journal.get_episode_transitions(report.episode_id)
        # Should have: Step 0 (Type), Step 1 (Dismiss Modal), Step 2 (Click Continue)
        self.assertGreaterEqual(len(transitions), 3)

        action_types = [tx.action.action_type for tx in transitions]
        self.assertIn(ActionType.TYPE, action_types)
        self.assertIn(ActionType.CLICK, action_types)

        # Check provenance or action details of modal dismissal
        dismissal_txs = [
            tx for tx in transitions
            if tx.provenance.get("interception") == "modal_dismissal" or tx.action.target_node_id == "btn_accept_cookies"
        ]
        self.assertEqual(len(dismissal_txs), 1)
        self.assertEqual(dismissal_txs[0].action.target_node_id, "btn_accept_cookies")

    async def test_modal_dismissal_fallback_to_escape_key(self):
        """When modal has no recognizable button, closed loop falls back to Escape key press."""
        # Setup graph with modal lacking explicit accept button
        modal_no_btn_graph = CanonicalUIGraph(
            timestamp_ms=1001000.0,
            nodes={
                "modal_overlay": UIStateNode(
                    node_id="modal_overlay",
                    role=NodeRole.MODAL,
                    bounds=BoundingBox(0, 0, 1920, 1080),
                    label="Promo Announcement",
                    attributes={"role": "dialog"},
                ),
            },
            url="https://portal.example.com/login",
        )

        obs = ModalTestObservationAdapter()
        obs.cookie_modal_graph = modal_no_btn_graph  # replace modal graph
        esc_manager = ActionLeaseManager(clock=self.clock)
        action_adapter = ModalTestActionAdapter(obs, lease_manager=esc_manager)

        kernel = HostControlKernel(
            policy=self.policy,
            action_port=action_adapter,
            observation_port=obs,
            lease_manager=esc_manager,
            clock=self.clock,
            settle_interval_s=0.0,
        )

        loop = BrowserClosedLoopV1(
            kernel=kernel,
            observation_port=obs,
            journal=self.journal,
            clock=self.clock,
            auto_dismiss_modals=True,
        )

        # Trigger modal dismissal directly
        dismissed, post_state = await loop._dismiss_active_modal(
            state=modal_no_btn_graph,
            session_id="sess_esc",
            step_index=1,
            episode_id="ep_esc",
            goal=TaskGoal(task_id="t_esc", instruction="Test Escape", target_url="https://portal.example.com"),
        )

        self.assertTrue(dismissed)
        # Verify Escape key action was dispatched
        self.assertTrue(any(a.action_type == ActionType.KEY_PRESS and a.key_code == "Escape" for a in action_adapter.dispatched_actions))


if __name__ == "__main__":
    unittest.main()
