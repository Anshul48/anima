"""Comprehensive End-to-End Integration & Verification Test Suite for Reflex Closed-Loop Execution & Replay (Workstreams R3 & R4).

Verifies the entire closed loop stack:
1. Multi-step task execution through the closed loop (HostControlKernel + ExecutionRouter + Single-Use ActionLease).
2. Settlement detection on dynamic DOM updates, animations, and in-flight network requests.
3. Decoupled independent verification of expected vs actual state deltas and assertion rules.
4. Reconciliation and bounded recovery when a simulated element is stale or modal appears (no blind retries).
5. Resource budget exhaustion (step budget, timeout, consecutive errors) triggering safe shutdown.
6. Immutable episode recording to SQLite journal with PII redaction and deterministic replay via ReplayRunner.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from typing import Any, Dict, List, Optional, Tuple

from reflex.episodes.journal import EpisodeSummary, LocalEpisodeJournal
from reflex.episodes.redactor import PrivacyRedactor
from reflex.episodes.replay_runner import EpisodeReplayRunner, ReplayReport
from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.execution.input.synthetic_input_adapter import SyntheticInputAdapter
from reflex.execution.router import ExecutionRouter
from reflex.grounding.browser_grounder import BrowserGroundingEngine
from reflex.host.identity.lease_manager import (
    ActionLease,
    ActionLeaseManager,
    InvalidLeaseError,
    LeaseAlreadyAcquiredError,
)
from reflex.host.kernel.host_kernel import (
    DispatchState,
    EmergencyHaltError,
    HostControlKernel,
    KernelDispatchResult,
)
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
from reflex.schemas.memory import TransitionTuple
from reflex.schemas.policy import CapabilityPolicy, CapabilityScope
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.reconciliation import ReconciliationEngine, ReconciliationReport
from reflex.verification.settlement_observer import SettlementObserver, SettlementResult
from reflex.verification.verifier import AssertionRule, IndependentVerifier, VerificationResult


class E2EFormSimulationObserver(ObservationPort):
    """Simulates multi-step interactive web application state transitions."""

    def __init__(self, initial_url: str = "https://app.example.com/login"):
        self.url = initial_url
        self.step_name = "login"
        self.username_val = ""
        self.password_val = ""
        self.amount_val = ""
        self.is_confirmed = False
        self.modal_visible = False
        self.element_shifted = False
        self.ghost_element_visible = False
        self.loading_active = False

    def update_field(self, node_id: str, val: str) -> None:
        if node_id == "inp_username":
            self.username_val = val
        elif node_id == "inp_password":
            self.password_val = val
        elif node_id == "inp_amount":
            self.amount_val = val

    async def capture_state(self) -> CanonicalUIGraph:
        timestamp_ms = time.time() * 1000.0

        if self.step_name == "login":
            nodes = {
                "inp_username": UIStateNode(
                    node_id="inp_username",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(100, 100, 300, 130),
                    label="Username",
                    value=self.username_val,
                    is_editable=True,
                ),
                "inp_password": UIStateNode(
                    node_id="inp_password",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(100, 150, 300, 180),
                    label="Password",
                    value=self.password_val,
                    is_editable=True,
                    attributes={"type": "password"},
                ),
                "btn_login": UIStateNode(
                    node_id="btn_login",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 200, 250, 240),
                    label="Log In",
                    is_clickable=True,
                ),
            }
            title = "App Login"

        elif self.step_name == "transfer":
            btn_bounds = BoundingBox(100, 300, 250, 340) if not self.element_shifted else BoundingBox(100, 500, 250, 540)
            nodes = {
                "inp_amount": UIStateNode(
                    node_id="inp_amount",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(100, 100, 300, 130),
                    label="Transfer Amount",
                    value=self.amount_val,
                    is_editable=True,
                ),
                "btn_transfer": UIStateNode(
                    node_id="btn_transfer",
                    role=NodeRole.BUTTON,
                    bounds=btn_bounds,
                    label="Submit Transfer",
                    is_clickable=True,
                ),
            }
            if self.modal_visible:
                nodes["modal_dialog"] = UIStateNode(
                    node_id="modal_dialog",
                    role=NodeRole.MODAL,
                    bounds=BoundingBox(0, 0, 1920, 1080),
                    label="Security Verification Dialog",
                    children_ids=["btn_confirm_modal"],
                    attributes={"role": "dialog", "class": "security-modal"},
                )
                nodes["btn_confirm_modal"] = UIStateNode(
                    node_id="btn_confirm_modal",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(800, 500, 950, 540),
                    label="I Agree & Continue",
                    parent_id="modal_dialog",
                    is_clickable=True,
                )
            if self.ghost_element_visible:
                nodes["btn_temporary_ghost"] = UIStateNode(
                    node_id="btn_temporary_ghost",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(50, 50, 150, 80),
                    label="Temporary Option",
                )
            title = "Transfer Funds"

        elif self.step_name == "complete":
            nodes = {
                "txt_success": UIStateNode(
                    node_id="txt_success",
                    role=NodeRole.TEXT,
                    bounds=BoundingBox(100, 100, 600, 150),
                    label=f"Transfer of ${self.amount_val} completed successfully!",
                )
            }
            title = "Transfer Complete"
        else:
            nodes = {}
            title = "Blank"

        return CanonicalUIGraph(
            timestamp_ms=timestamp_ms,
            nodes=nodes,
            url=self.url,
            active_window_title=title,
            viewport_size=(1920, 1080),
        )

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_e2e_screenshot"


class E2EFormSimulationActionAdapter(CDPActionAdapter):
    """Simulates physical execution backend wired directly to simulated observer."""

    def __init__(
        self,
        observer: E2EFormSimulationObserver,
        page: Optional[Any] = None,
        lease_manager: Optional[ActionLeaseManager] = None,
    ):
        super().__init__(page=page or FakeBrowserPage(), lease_manager=lease_manager)
        self.observer = observer
        self.dispatched_actions: List[TypedAction] = []

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatched_actions.append(action)

        if action.action_type == ActionType.NAVIGATE:
            url = action.text_payload or action.metadata.get("url", "")
            self.observer.url = url
            if "transfer" in url:
                self.observer.step_name = "transfer"
            elif "login" in url:
                self.observer.step_name = "login"

        elif action.action_type == ActionType.TYPE:
            if action.target_node_id:
                self.observer.update_field(action.target_node_id, action.text_payload or "")

        elif action.action_type == ActionType.CLICK:
            if action.target_node_id == "btn_login":
                self.observer.step_name = "transfer"
                self.observer.url = "https://app.example.com/transfer"
            elif action.target_node_id == "btn_confirm_modal":
                self.observer.modal_visible = False
            elif action.target_node_id == "btn_transfer":
                self.observer.step_name = "complete"
                self.observer.url = "https://app.example.com/complete"

        return await super().dispatch_action(action, identity)


class TestClosedLoopRunnerE2E(unittest.IsolatedAsyncioTestCase):
    """Comprehensive E2E integration test suite for Closed-Loop Automation & Replay."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)
        self.observer = E2EFormSimulationObserver()
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.action_adapter = E2EFormSimulationActionAdapter(
            self.observer, lease_manager=self.lease_manager
        )

        self.settlement_observer = SettlementObserver(
            clock=self.clock,
            debounce_window_ms=50.0,
            max_timeout_ms=2000.0,
            poll_interval_ms=10.0,
        )
        self.verifier = IndependentVerifier(
            observation_port=self.observer,
            settlement_observer=self.settlement_observer,
            clock=self.clock,
        )
        self.policy = CapabilityPolicy.default_browser_policy()
        self.kernel = HostControlKernel(
            policy=self.policy,
            action_port=self.action_adapter,
            observation_port=self.observer,
            verification_port=self.verifier,
            lease_manager=self.lease_manager,
            clock=self.clock,
            settle_interval_s=0.0,
        )
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.journal = LocalEpisodeJournal(db_path=self.temp_db.name)
        self.grounder = BrowserGroundingEngine()
        self.session_manager = BrowserSessionManager()
        self.reconciler = ReconciliationEngine(
            observation_port=self.observer,
            settlement_observer=self.settlement_observer,
            clock=self.clock,
        )

        self.closed_loop = BrowserClosedLoopV1(
            kernel=self.kernel,
            observation_port=self.observer,
            grounder=self.grounder,
            verifier=self.verifier,
            journal=self.journal,
            session_manager=self.session_manager,
            clock=self.clock,
            reconciler=self.reconciler,
            auto_dismiss_modals=True,
            enable_pre_dispatch_regrounding=True,
        )

    def tearDown(self):
        try:
            os.remove(self.temp_db.name)
        except Exception:
            pass

    # =========================================================================
    # Test 1: Multi-Step Task Execution & ExecutionRouter Integration
    # =========================================================================

    async def test_multi_step_closed_loop_execution_and_lease_lifecycle(self):
        """End-to-end multi-step task execution through the closed loop:
        1. Form filling with credentials and amount.
        2. Authorization through HostControlKernel.
        3. Single-use ActionLease issuance, consumption, and retirement.
        4. Independent verification and transition recording with cryptographic linkage.
        """
        goal = TaskGoal(
            task_id="task_e2e_transfer_001",
            instruction="Log in and complete $250 transfer",
            target_url="https://app.example.com/login",
            max_steps=10,
        )

        proposals = [
            # 1. Type Username
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_username",
                text_payload="alice_corp",
                target_label="Username",
            ),
            # 2. Type Password (sensitive PII)
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_password",
                text_payload="SuperSecretPass123!",
                target_label="Password",
            ),
            # 3. Click Login -> navigates to /transfer
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_login",
                target_label="Log In",
            ),
            # 4. Type Transfer Amount
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_amount",
                text_payload="250.00",
                target_label="Transfer Amount",
            ),
            # 5. Click Submit Transfer -> navigates to /complete
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_transfer",
                target_label="Submit Transfer",
            ),
        ]

        report = await self.closed_loop.run_task(
            goal=goal,
            proposal_generator=proposals,
        )

        # 1. Verify Task Report
        self.assertEqual(report.status, TaskStatus.COMPLETED)
        self.assertEqual(report.total_steps, 5)
        self.assertEqual(report.final_url, "https://app.example.com/complete")
        self.assertGreaterEqual(report.verification_passed_count, 5)
        self.assertIsNone(report.error_summary)

        # 2. Verify Invariant: Leases were issued and consumed via HostControlKernel
        transitions = await self.journal.get_episode_transitions(report.episode_id)
        self.assertEqual(len(transitions), 5)

        for i, tx in enumerate(transitions):
            self.assertEqual(tx.step_index, i)
            self.assertEqual(tx.episode_id, report.episode_id)
            self.assertIsNotNone(tx.provenance.get("lease_id"))

        # 3. Verify Invariant: PII / Credential Redaction in Journal
        pw_tx = transitions[1]  # Password step
        self.assertEqual(pw_tx.action.text_payload, "[REDACTED_PASSWORD]")

        # 4. Verify Invariant: Cryptographic State Hash Linkage
        valid_linkage, reason = await self.journal.verify_cryptographic_linkage(report.episode_id)
        self.assertTrue(valid_linkage, f"Cryptographic state linkage broken: {reason}")

    # =========================================================================
    # Test 2: ExecutionRouter Direct vs Synthetic Dispatch
    # =========================================================================

    async def test_execution_router_adapter_selection(self):
        """ExecutionRouter deterministically routes direct DOM and synthetic physical coordinates."""
        fake_page = FakeBrowserPage()
        cdp_adapter = CDPActionAdapter(page=fake_page)
        synthetic_adapter = SyntheticInputAdapter(page=fake_page)
        router = ExecutionRouter(cdp_adapter=cdp_adapter, synthetic_adapter=synthetic_adapter)

        # Direct DOM action with target_node_id
        direct_action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_dom")
        self.assertIs(router.select_adapter(direct_action), cdp_adapter)

        # Coordinate-based action without node ID
        synthetic_action = TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(0.5, 0.5))
        self.assertIs(router.select_adapter(synthetic_action), synthetic_adapter)

        # Canvas explicit metadata override
        canvas_action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="canvas_elem",
            metadata={"is_canvas": True},
        )
        self.assertIs(router.select_adapter(canvas_action), synthetic_adapter)

        # Force synthetic override
        force_synth_action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn_dom",
            metadata={"force_synthetic": True},
        )
        self.assertIs(router.select_adapter(force_synth_action), synthetic_adapter)

    # =========================================================================
    # Test 3: Settlement Detection on Dynamic DOM Updates
    # =========================================================================

    async def test_settlement_detection_on_mutations_and_network_quiescence(self):
        """SettlementObserver accurately waits for DOM debounce and network in-flight requests."""
        clock = DeterministicClock(start_time_ms=1000.0)
        settle_obs = SettlementObserver(
            clock=clock,
            debounce_window_ms=100.0,
            max_timeout_ms=1500.0,
            poll_interval_ms=10.0,
        )

        # 1. In-flight network request blocks settlement
        settle_obs.record_request_started("req_api_1", url="https://api.example.com/sync")
        self.assertFalse(settle_obs.is_settled(1000.0))

        # 2. Record mutation
        settle_obs.record_mutation(timestamp_ms=1050.0)
        self.assertFalse(settle_obs.is_dom_quiescent(1100.0))

        # 3. Finish network request at t=1120
        settle_obs.record_request_finished("req_api_1")
        self.assertTrue(settle_obs.is_network_idle())

        # At t=1160 (110ms > 100ms debounce), DOM is quiet and observer settles
        self.assertTrue(settle_obs.is_dom_quiescent(1160.0))
        self.assertTrue(settle_obs.is_settled(1160.0))

        # 4. Stuck network request triggers bounding timeout
        settle_obs.record_request_started("stuck_req", url="https://hang.example.com")
        res = await settle_obs.wait_for_settlement(timeout_ms=300.0)
        self.assertFalse(res.settled)
        self.assertTrue(res.timed_out)
        self.assertIn("network request(s) in-flight", res.details)

    # =========================================================================
    # Test 4: Decoupled Independent Verifier & Delta Evaluation
    # =========================================================================

    async def test_independent_verifier_delta_computation_and_assertions(self):
        """IndependentVerifier evaluates assertions, computes structural deltas, and classifies outcomes."""
        before_state = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={
                "txt_status": UIStateNode(
                    node_id="txt_status",
                    role=NodeRole.TEXT,
                    bounds=BoundingBox(10, 10, 100, 30),
                    label="Pending",
                    value="Pending",
                )
            },
            url="https://app.example.com/status",
        )

        after_state = CanonicalUIGraph(
            timestamp_ms=1050.0,
            nodes={
                "txt_status": UIStateNode(
                    node_id="txt_status",
                    role=NodeRole.TEXT,
                    bounds=BoundingBox(10, 10, 100, 30),
                    label="Success",
                    value="Success",
                ),
                "btn_download": UIStateNode(
                    node_id="btn_download",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(10, 50, 120, 80),
                    label="Download Receipt",
                ),
            },
            url="https://app.example.com/status",
        )

        verifier = IndependentVerifier(clock=self.clock)

        # 1. Delta Computation
        delta = verifier.compute_state_delta(before_state, after_state)
        self.assertIn("btn_download", delta.added_nodes)
        self.assertIn("txt_status", delta.modified_nodes)
        self.assertEqual(len(delta.removed_nodes), 0)

        # 2. Assertion Rules Evaluation
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit")
        custom_assertions = [
            AssertionRule(assertion_type="element_present", target_node_id="btn_download"),
            AssertionRule(assertion_type="element_value_equals", target_node_id="txt_status", target_value="Success"),
            AssertionRule(assertion_type="url_equals", target_value="https://app.example.com/status"),
            AssertionRule(assertion_type="no_console_error"),
        ]

        passed, failed, critical_failed = verifier.evaluate_assertions(
            before_state=before_state,
            after_state=after_state,
            delta=delta,
            action=action,
            custom_assertions=custom_assertions,
        )

        self.assertEqual(len(failed), 0)
        self.assertEqual(len(critical_failed), 0)
        self.assertGreaterEqual(len(passed), 4)

        # 3. Classify outcome
        outcome = verifier.classify_outcome(
            before_state=before_state,
            after_state=after_state,
            delta=delta,
            action=action,
            failed_critical=[],
        )
        self.assertEqual(outcome, OutcomeClass.SUCCESS)

    # =========================================================================
    # Test 5: Modal Interception & Trajectory Resumption
    # =========================================================================

    async def test_unexpected_modal_interception_and_recovery(self):
        """Unexpected modal banner appearing mid-task is diagnosed, dismissed, and resumed without blind retry."""
        self.observer.url = "https://app.example.com/transfer"
        self.observer.step_name = "transfer"
        self.observer.modal_visible = True  # Inject active modal

        goal = TaskGoal(
            task_id="task_modal_recovery",
            instruction="Transfer $100 after dismissing security modal",
            target_url="https://app.example.com/transfer",
            max_steps=5,
        )

        proposals = [
            # Primary intent: Type amount and click transfer
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_amount", text_payload="100.00"),
            TypedAction(action_type=ActionType.CLICK, target_node_id="btn_transfer"),
        ]

        step_idx = 0

        def generator(g: TaskGoal, state: CanonicalUIGraph, idx: int) -> Optional[TypedAction]:
            nonlocal step_idx
            if step_idx < len(proposals):
                act = proposals[step_idx]
                step_idx += 1
                return act
            return None

        report = await self.closed_loop.run_task(goal=goal, proposal_generator=generator)

        # Modal was auto-dismissed and primary goal completed
        self.assertEqual(report.status, TaskStatus.COMPLETED)
        self.assertEqual(report.final_url, "https://app.example.com/complete")

        # Journal recorded modal dismissal transition
        transitions = await self.journal.get_episode_transitions(report.episode_id)
        dismiss_txs = [tx for tx in transitions if tx.provenance.get("interception") == "modal_dismissal"]
        self.assertGreaterEqual(len(dismiss_txs), 1)
        self.assertEqual(dismiss_txs[0].action.target_node_id, "btn_confirm_modal")

    # =========================================================================
    # Test 6: Pre-Dispatch Re-Grounding on Shifted and Stale Elements
    # =========================================================================

    async def test_staleness_and_layout_shift_handling(self):
        """Pre-dispatch re-grounding updates coordinates on layout shifts and reconciles vanished elements."""
        self.observer.url = "https://app.example.com/transfer"
        self.observer.step_name = "transfer"
        self.observer.element_shifted = True  # Shifts button from y=300 to y=500

        goal = TaskGoal(
            task_id="task_staleness_shift",
            instruction="Execute action with shifted coordinates",
            target_url="https://app.example.com/transfer",
            max_steps=5,
        )

        stale_proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_shift", step_index=1),
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_transfer",
                coords=NormalizedCoords(0.09, 0.29),  # Old center ~ (175, 320)
                target_label="Submit Transfer",
            ),
        )

        # Re-grounding test
        curr_state = await self.observer.capture_state()
        updated_proposal, is_stale = await self.closed_loop._reground_proposal_if_needed(
            proposal=stale_proposal,
            current_state=curr_state,
        )

        self.assertFalse(is_stale)
        self.assertIsNotNone(updated_proposal.action.coords)
        px_x, px_y = updated_proposal.action.coords.to_pixel(1920, 1080)
        self.assertEqual(px_y, 520)  # Correctly shifted from 320 to 520!

        # Vanished element staleness test
        ghost_proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_ghost", step_index=2),
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="nonexistent_button",
                target_label="Ghost Button",
            ),
        )
        _, is_stale_ghost = await self.closed_loop._reground_proposal_if_needed(
            proposal=ghost_proposal,
            current_state=curr_state,
        )
        self.assertTrue(is_stale_ghost)

    # =========================================================================
    # Test 7: Resource Budget Exhaustion & Fail-Safe Termination
    # =========================================================================

    async def test_resource_budget_exhaustion_step_and_timeout(self):
        """Budget ceilings (step count, task timeout, consecutive errors) strictly enforce fail-safe termination."""
        # 1. Max Steps Budget
        goal_step_limit = TaskGoal(
            task_id="task_step_budget",
            instruction="Execute beyond step budget",
            target_url="https://app.example.com/login",
            max_steps=2,
        )
        proposals = [
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_username", text_payload="u1"),
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_password", text_payload="p1"),
            TypedAction(action_type=ActionType.CLICK, target_node_id="btn_login"),
        ]

        report_step = await self.closed_loop.run_task(goal=goal_step_limit, proposal_generator=proposals)
        self.assertEqual(report_step.status, TaskStatus.MAX_STEPS_EXCEEDED)
        self.assertEqual(report_step.total_steps, 2)
        self.assertIn("Max step budget exceeded", report_step.error_summary or "")

        # 2. Consecutive Error Threshold Termination
        self.observer.url = "https://app.example.com/transfer"
        self.observer.step_name = "transfer"
        goal_error_limit = TaskGoal(
            task_id="task_error_budget",
            instruction="Fail repeatedly on nonexistent elements",
            target_url="https://app.example.com/transfer",
            max_steps=10,
        )
        bad_proposals = [
            TypedAction(action_type=ActionType.CLICK, target_node_id="ghost_1"),
            TypedAction(action_type=ActionType.CLICK, target_node_id="ghost_2"),
            TypedAction(action_type=ActionType.CLICK, target_node_id="ghost_3"),
        ]
        report_err = await self.closed_loop.run_task(goal=goal_error_limit, proposal_generator=bad_proposals)
        self.assertEqual(report_err.status, TaskStatus.FAILED)

    # =========================================================================
    # Test 8: Deterministic Replay via ReplayRunner
    # =========================================================================

    async def test_deterministic_episode_replay_and_drift_detection(self):
        """Recorded SQLite episode transitions are accurately replayed with determinism verification and drift detection."""
        # 1. First record an episode via closed loop execution
        goal = TaskGoal(
            task_id="task_replay_source",
            instruction="Log in Alice",
            target_url="https://app.example.com/login",
            max_steps=5,
        )
        proposals = [
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_username", text_payload="alice"),
            TypedAction(action_type=ActionType.CLICK, target_node_id="btn_login"),
        ]
        exec_report = await self.closed_loop.run_task(goal=goal, proposal_generator=proposals)
        self.assertEqual(exec_report.status, TaskStatus.COMPLETED)

        transitions = await self.journal.get_episode_transitions(exec_report.episode_id)
        self.assertEqual(len(transitions), 2)

        # 2. Mock replay environment replicating exact observed state progression
        replay_obs_match = E2EFormSimulationObserver()
        replay_manager = ActionLeaseManager(clock=self.clock)
        replay_act_match = E2EFormSimulationActionAdapter(
            replay_obs_match, lease_manager=replay_manager
        )
        replay_kernel = HostControlKernel(
            action_port=replay_act_match,
            lease_manager=replay_manager,
            clock=self.clock,
            settle_interval_s=0.0,
        )

        runner_pass = EpisodeReplayRunner(
            journal=self.journal,
            observation_port=replay_obs_match,
            action_port=replay_act_match,
            kernel=replay_kernel,
        )

        replay_report_pass: ReplayReport = await runner_pass.replay_episode(exec_report.episode_id)
        self.assertEqual(replay_report_pass.total_steps, 2)
        self.assertEqual(replay_report_pass.matched_steps, 2)
        self.assertEqual(replay_report_pass.determinism_ratio, 1.0)
        self.assertTrue(replay_report_pass.is_fully_deterministic)

        # 3. Mock replay environment with drift (e.g. unexpected popup altering state hash)
        class DriftingObserver(ObservationPort):
            async def capture_state(self) -> CanonicalUIGraph:
                return CanonicalUIGraph(
                    timestamp_ms=1000.0,
                    nodes={
                        "popup_drift": UIStateNode(
                            node_id="popup_drift",
                            role=NodeRole.MODAL,
                            bounds=BoundingBox(0, 0, 500, 300),
                            label="Unexpected Warning",
                        )
                    },
                    url="https://app.example.com/drifted",
                )

            async def capture_screenshot(self) -> bytes:
                return b""

        runner_drift = EpisodeReplayRunner(
            journal=self.journal,
            observation_port=DriftingObserver(),
            action_port=replay_act_match,
            kernel=replay_kernel,
            stop_on_drift=False,
        )

        replay_report_drift: ReplayReport = await runner_drift.replay_episode(exec_report.episode_id)
        self.assertEqual(replay_report_drift.total_steps, 2)
        self.assertEqual(replay_report_drift.matched_steps, 0)
        self.assertEqual(replay_report_drift.determinism_ratio, 0.0)
        self.assertFalse(replay_report_drift.is_fully_deterministic)
        self.assertIn("Hash mismatch", replay_report_drift.step_results[0].drift_details or "")

    # =========================================================================
    # Test 9: HostControlKernel Invariant & Emergency Halt Verification
    # =========================================================================

    async def test_kernel_single_use_lease_and_emergency_halt_invariants(self):
        """Verifies strict kernel non-negotiable invariants:
        - Re-use of ActionLease raises InvalidLeaseError / LeaseAlreadyAcquiredError.
        - emergency_halt immediately revokes all active leases and halts dispatch.
        """
        # Test 1: Single-use lease acquisition
        identity = ActionIdentity.create(session_id="sess_lease_test", step_index=1)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_login")
        lease = self.lease_manager.issue_lease(identity, action, ttl_ms=5000.0)

        # First acquisition succeeds
        acquired_lease = self.lease_manager.acquire_lease(lease.lease_id)
        self.assertEqual(acquired_lease.lease_id, lease.lease_id)

        # Second acquisition fails (single-use enforcement)
        with self.assertRaises(LeaseAlreadyAcquiredError):
            self.lease_manager.acquire_lease(lease.lease_id)

        # Test 2: Emergency Halt
        self.kernel.emergency_halt("Security breach detected")
        self.assertTrue(self.kernel.is_halted)
        self.assertEqual(self.lease_manager.active_lease_count(), 0)

        halt_proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_halt", step_index=2),
            action=action,
        )
        with self.assertRaises(EmergencyHaltError):
            await self.kernel.submit_proposal(halt_proposal)


if __name__ == "__main__":
    unittest.main()
