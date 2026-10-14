"""Test suite for Closed-Loop Browser Automation Engine: Multi-Step Form Wizard & Budgeting."""

import asyncio
import time
import unittest
from typing import Any, Dict, List, Optional

from reflex.episodes.journal import LocalEpisodeJournal
from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.grounding.browser_grounder import BrowserGroundingEngine
from reflex.host.identity.lease_manager import ActionLeaseManager
from reflex.host.kernel.host_kernel import HostControlKernel
from reflex.host.policy.capability_engine import CapabilityPolicyEngine
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.orchestration.browser_loop import (
    BrowserClosedLoopV1,
    TaskExecutionReport,
    TaskGoal,
    TaskStatus,
)
from reflex.orchestration.session_manager import (
    BrowserSession,
    BrowserSessionConfig,
    BrowserSessionManager,
)
from reflex.ports.clock import DeterministicClock, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityPolicy, CapabilityScope
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.verifier import AssertionRule, IndependentVerifier


class MockFormObservationAdapter(ObservationPort):
    """Observation adapter simulating state transitions of a multi-step form wizard."""

    def __init__(self, step_graphs: List[CanonicalUIGraph]):
        self.step_graphs = list(step_graphs)
        self.current_index = 0

    def set_index(self, index: int) -> None:
        self.current_index = min(index, len(self.step_graphs) - 1)

    def advance(self) -> None:
        if self.current_index < len(self.step_graphs) - 1:
            self.current_index += 1

    def update_node_value(self, node_id: str, new_value: str) -> None:
        curr = self.step_graphs[self.current_index]
        if node_id in curr.nodes:
            old_n = curr.nodes[node_id]
            updated_n = UIStateNode(
                node_id=old_n.node_id,
                role=old_n.role,
                bounds=old_n.bounds,
                label=old_n.label,
                value=new_value,
                is_clickable=old_n.is_clickable,
                is_editable=old_n.is_editable,
                is_focused=old_n.is_focused,
                is_enabled=old_n.is_enabled,
                parent_id=old_n.parent_id,
                children_ids=old_n.children_ids,
                source=old_n.source,
                confidence=old_n.confidence,
                attributes=old_n.attributes,
            )
            new_nodes = dict(curr.nodes)
            new_nodes[node_id] = updated_n
            self.step_graphs[self.current_index] = CanonicalUIGraph(
                timestamp_ms=curr.timestamp_ms + 10.0,
                nodes=new_nodes,
                focused_node_id=curr.focused_node_id,
                active_window_title=curr.active_window_title,
                url=curr.url,
                viewport_size=curr.viewport_size,
            )

    async def capture_state(self) -> CanonicalUIGraph:
        if self.current_index < len(self.step_graphs):
            return self.step_graphs[self.current_index]
        return self.step_graphs[-1]

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_screenshot_wizard"


class MockWizardActionAdapter(CDPActionAdapter):
    """Action adapter that advances mock observer upon specific button clicks."""

    def __init__(
        self,
        obs_adapter: MockFormObservationAdapter,
        page: Optional[Any] = None,
        lease_manager: Optional[ActionLeaseManager] = None,
    ):
        super().__init__(page=page or FakeBrowserPage(), lease_manager=lease_manager)
        self.obs_adapter = obs_adapter
        self.dispatched_actions: List[TypedAction] = []

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatched_actions.append(action)

        # Update input value on type
        if action.action_type == ActionType.TYPE and action.target_node_id:
            self.obs_adapter.update_node_value(action.target_node_id, action.text_payload or "")

        # Advance wizard step on "Next" or "Submit"
        elif action.action_type == ActionType.CLICK:
            if action.target_node_id in ("btn_step1_next", "btn_step2_next", "btn_step3_submit"):
                self.obs_adapter.advance()

        return await super().dispatch_action(action, identity)


class TestClosedLoopForms(unittest.IsolatedAsyncioTestCase):
    """Test suite covering multi-step form wizard automation, budgeting, and journal persistence."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)

        # Build multi-step wizard UI State Graphs
        # Step 1: Personal Info
        self.step1_graph = CanonicalUIGraph(
            timestamp_ms=1000000.0,
            nodes={
                "inp_name": UIStateNode(
                    node_id="inp_name",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(100, 100, 300, 130),
                    label="Full Name",
                    value="",
                    is_editable=True,
                ),
                "inp_email": UIStateNode(
                    node_id="inp_email",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(100, 150, 300, 180),
                    label="Email Address",
                    value="",
                    is_editable=True,
                ),
                "btn_step1_next": UIStateNode(
                    node_id="btn_step1_next",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 200, 200, 240),
                    label="Next Step",
                ),
            },
            url="https://app.example.com/wizard/step1",
            active_window_title="Wizard - Step 1",
        )

        # Step 2: Preferences
        self.step2_graph = CanonicalUIGraph(
            timestamp_ms=1001000.0,
            nodes={
                "chk_newsletter": UIStateNode(
                    node_id="chk_newsletter",
                    role=NodeRole.CHECKBOX,
                    bounds=BoundingBox(100, 100, 120, 120),
                    label="Subscribe to newsletter",
                    value="false",
                ),
                "btn_step2_next": UIStateNode(
                    node_id="btn_step2_next",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 150, 200, 190),
                    label="Continue to Confirmation",
                ),
            },
            url="https://app.example.com/wizard/step2",
            active_window_title="Wizard - Step 2",
        )

        # Step 3: Review & Submit
        self.step3_graph = CanonicalUIGraph(
            timestamp_ms=1002000.0,
            nodes={
                "txt_summary": UIStateNode(
                    node_id="txt_summary",
                    role=NodeRole.TEXT,
                    bounds=BoundingBox(100, 50, 400, 80),
                    label="Review Your Details",
                ),
                "btn_step3_submit": UIStateNode(
                    node_id="btn_step3_submit",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 120, 250, 160),
                    label="Submit Registration",
                ),
            },
            url="https://app.example.com/wizard/step3",
            active_window_title="Wizard - Review",
        )

        # Final Success State
        self.success_graph = CanonicalUIGraph(
            timestamp_ms=1003000.0,
            nodes={
                "banner_success": UIStateNode(
                    node_id="banner_success",
                    role=NodeRole.TEXT,
                    bounds=BoundingBox(50, 50, 500, 100),
                    label="Registration Completed Successfully! Welcome Alice.",
                )
            },
            url="https://app.example.com/wizard/complete",
            active_window_title="Wizard - Success",
        )

        self.all_graphs = [self.step1_graph, self.step2_graph, self.step3_graph, self.success_graph]
        self.obs_adapter = MockFormObservationAdapter(self.all_graphs)
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.action_adapter = MockWizardActionAdapter(
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
        )

    async def test_full_wizard_closed_loop_execution_success(self):
        """End-to-end multi-step wizard execution completes successfully with all steps verified."""
        goal = TaskGoal(
            task_id="task_wizard_001",
            instruction="Complete multi-step registration wizard for Alice",
            target_url="https://app.example.com/wizard/step1",
            max_steps=10,
        )

        # Define 5-step proposal sequence for wizard
        proposals = [
            # 1. Type Name
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_name",
                text_payload="Alice Doe",
                target_label="Full Name",
            ),
            # 2. Type Email
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_email",
                text_payload="alice@example.com",
                target_label="Email Address",
            ),
            # 3. Click Next Step 1 -> advances to Step 2
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_step1_next",
                target_label="Next Step",
            ),
            # 4. Click Next Step 2 -> advances to Step 3
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_step2_next",
                target_label="Continue to Confirmation",
            ),
            # 5. Click Submit Step 3 -> advances to Success
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_step3_submit",
                target_label="Submit Registration",
            ),
            # 6. Generator finishes (returns None)
        ]

        report = await self.loop.run_task(
            goal=goal,
            proposal_generator=proposals,
        )

        # Assert Task Report
        self.assertEqual(report.status, TaskStatus.COMPLETED)
        self.assertEqual(report.total_steps, 5)
        self.assertEqual(report.task_id, "task_wizard_001")
        self.assertEqual(report.final_url, "https://app.example.com/wizard/complete")
        self.assertGreaterEqual(report.verification_passed_count, 5)
        self.assertIsNone(report.error_summary)

        # Assert Journal Persistence
        transitions = await self.journal.get_episode_transitions(report.episode_id)
        self.assertEqual(len(transitions), 5)
        for i, tx in enumerate(transitions):
            self.assertEqual(tx.step_index, i)
            self.assertEqual(tx.episode_id, report.episode_id)
            self.assertIsNotNone(tx.ui_state_hash)

        # Assert Episode Summary from Journal
        summary = await self.journal.get_episode_summary(report.episode_id)
        self.assertIsNotNone(summary)
        self.assertTrue(summary.success)
        self.assertEqual(summary.total_steps, 5)

        # Assert cryptographic state linkage across transitions
        valid_linkage, reason = await self.journal.verify_cryptographic_linkage(report.episode_id)
        self.assertTrue(valid_linkage, f"Linkage failed: {reason}")

    async def test_step_budget_exhaustion_terminates_gracefully(self):
        """When max_steps is smaller than required actions, loop strictly terminates with MAX_STEPS_EXCEEDED."""
        goal = TaskGoal(
            task_id="task_wizard_budget_exceeded",
            instruction="Complete registration with 2-step budget limit",
            target_url="https://app.example.com/wizard/step1",
            max_steps=2,  # Wizard requires 5 steps
        )

        proposals = [
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_name", text_payload="Alice"),
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_email", text_payload="alice@example.com"),
            TypedAction(action_type=ActionType.CLICK, target_node_id="btn_step1_next"),
            TypedAction(action_type=ActionType.CLICK, target_node_id="btn_step2_next"),
        ]

        report = await self.loop.run_task(
            goal=goal,
            proposal_generator=proposals,
        )

        self.assertEqual(report.status, TaskStatus.MAX_STEPS_EXCEEDED)
        self.assertEqual(report.total_steps, 2)
        self.assertIn("Max step budget exceeded", report.error_summary or "")

        # Verify journal recorded exactly 2 steps
        transitions = await self.journal.get_episode_transitions(report.episode_id)
        self.assertEqual(len(transitions), 2)

    async def test_task_timeout_budget_exhaustion(self):
        """When task duration exceeds task_timeout_ms, loop terminates with MAX_STEPS_EXCEEDED."""
        # Use Clock to simulate timeout
        class AdvancingClock(SystemClock):
            def __init__(self):
                self._current = 1000.0

            def monotonic_ms(self) -> float:
                self._current += 20000.0  # Advance 20s each read
                return self._current

            def now_ms(self) -> float:
                return self._current

        adv_clock = AdvancingClock()
        loop = BrowserClosedLoopV1(
            kernel=self.kernel,
            observation_port=self.obs_adapter,
            clock=adv_clock,
            journal=self.journal,
        )

        goal = TaskGoal(
            task_id="task_timeout_test",
            instruction="Test task timeout",
            target_url="https://app.example.com/wizard/step1",
            task_timeout_ms=10000.0,  # 10 seconds timeout
            max_steps=50,
        )

        proposals = [
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_name", text_payload="Alice"),
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_email", text_payload="alice@example.com"),
        ]

        report = await loop.run_task(goal=goal, proposal_generator=proposals)

        self.assertEqual(report.status, TaskStatus.MAX_STEPS_EXCEEDED)
        self.assertIn("Task timeout reached", report.error_summary or "")

    async def test_policy_rejection_halts_loop(self):
        """When an action proposal requests an unauthorized capability, the loop halts with HALTED_POLICY."""
        goal = TaskGoal(
            task_id="task_policy_reject",
            instruction="Execute forbidden action",
            target_url="https://app.example.com/wizard/step1",
            max_steps=10,
        )

        # Propose action requesting unauthorized scope (e.g. FS_WRITE)
        forbidden_proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_pol", step_index=1),
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_step1_next",
                metadata={"required_scope": CapabilityScope.FS_WRITE},
            ),
            required_scopes={CapabilityScope.FS_WRITE},  # Not allowed in default browser policy
        )

        report = await self.loop.run_task(
            goal=goal,
            proposal_generator=[forbidden_proposal],
        )

        self.assertEqual(report.status, TaskStatus.HALTED_POLICY)
        self.assertIn("Missing required capability", report.error_summary or "")

    def test_task_goal_and_report_serialization(self):
        """TaskGoal and TaskExecutionReport serialize and deserialize accurately."""
        goal = TaskGoal(
            task_id="t_001",
            instruction="Submit Form",
            target_url="https://example.com/form",
            max_steps=25,
            step_timeout_ms=5000.0,
            task_timeout_ms=60000.0,
            parameters={"env": "staging"},
        )
        g_dict = goal.to_dict()
        g_reconstructed = TaskGoal.from_dict(g_dict)
        self.assertEqual(goal, g_reconstructed)

        report = TaskExecutionReport(
            task_id="t_001",
            status=TaskStatus.COMPLETED,
            total_steps=12,
            duration_ms=4520.5,
            final_url="https://example.com/success",
            episode_id="ep_123",
            error_summary=None,
            verification_passed_count=12,
            metadata={"source": "unit_test"},
        )
        r_dict = report.to_dict()
        r_reconstructed = TaskExecutionReport.from_dict(r_dict)
        self.assertEqual(report, r_reconstructed)


if __name__ == "__main__":
    unittest.main()
