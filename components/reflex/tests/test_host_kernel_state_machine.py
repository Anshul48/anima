from __future__ import annotations
import asyncio
import time
import unittest
from typing import Any, Dict, Optional

from reflex.host import (
    ActionLease,
    ActionLeaseManager,
    CapabilityPolicyEngine,
    ConfirmationDeniedError,
    ConfirmationTimeoutError,
    DispatchState,
    EmergencyHaltError,
    HostControlKernel,
    InvalidStateTransitionError,
    KernelDispatchResult,
    LeaseRevokedError,
    VALID_TRANSITIONS,
)
from reflex.ports.action import ActionPort, ActionReceipt, ActionStatus
from reflex.ports.clock import DeterministicClock, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.ports.verification import VerificationPort
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityGrant, CapabilityPolicy, CapabilityScope
from reflex.schemas.state import CanonicalUIGraph, UIStateNode, BoundingBox, NodeRole


class MockActionAdapter(ActionPort):
    def __init__(self, delay_s: float = 0.0, response_data: Optional[Dict[str, Any]] = None):
        self.delay_s = delay_s
        self.response_data = response_data or {"ok": True}
        self.dispatch_count = 0
        self.last_action: Optional[TypedAction] = None
        self.last_identity: Optional[ActionIdentity] = None
        self.adapter_name = "mock_browser_adapter"

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatch_count += 1
        self.last_action = action
        self.last_identity = identity
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        return self.response_data


class MockObservationAdapter(ObservationPort):
    def __init__(self):
        self.states: list[CanonicalUIGraph] = []

    async def capture_state(self) -> CanonicalUIGraph:
        graph = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes={
                "btn_1": UIStateNode(
                    node_id="btn_1",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(10, 10, 50, 50),
                    label="Submit",
                )
            },
            url="https://example.com/app",
        )
        self.states.append(graph)
        return graph

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_screenshot_bytes"


class MockVerificationAdapter(VerificationPort):
    def __init__(self, outcome: OutcomeClass = OutcomeClass.SUCCESS):
        self.outcome = outcome
        self.call_count = 0

    async def verify_transition(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
        after_state: CanonicalUIGraph,
        expected_delta: Optional[StateDelta] = None,
    ) -> StateDelta:
        self.call_count += 1
        return StateDelta(
            added_nodes=["success_banner"],
            removed_nodes=[],
            modified_nodes=[],
            pixel_change_ratio=0.05,
            outcome_class=self.outcome,
        )


class TestHostKernelStateMachine(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying HostControlKernel state machine transitions and safety invariants."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)
        self.policy = CapabilityPolicy.default_browser_policy()
        self.adapter = MockActionAdapter()
        self.obs = MockObservationAdapter()
        self.verifier = MockVerificationAdapter(OutcomeClass.SUCCESS)

        self.kernel = HostControlKernel(
            policy=self.policy,
            action_port=self.adapter,
            observation_port=self.obs,
            verification_port=self.verifier,
            clock=self.clock,
            settle_interval_s=0.0,  # Fast settlement in tests
        )

    def _create_proposal(
        self,
        session_id: str = "sess_001",
        step_index: int = 1,
        action_type: ActionType = ActionType.CLICK,
        safety_class: SafetyClass = SafetyClass.REVERSIBLE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ActionProposal:
        identity = ActionIdentity.create(session_id=session_id, step_index=step_index)
        action = TypedAction(
            action_type=action_type,
            target_node_id="btn_1",
            coords=NormalizedCoords(0.2, 0.3),
            safety_class=safety_class,
            metadata=metadata or {},
        )
        return ActionProposal(
            identity=identity,
            action=action,
            required_scopes={CapabilityScope.BROWSER_INTERACT},
        )

    async def test_full_happy_path_state_transitions(self):
        """Verify full path: IDLE -> PROPOSAL_RECEIVED -> AUTHORIZING -> LEASE_ISSUED -> IN_FLIGHT -> SETTLING -> VERIFYING -> RETIRED_SUCCESS -> IDLE."""
        self.assertEqual(self.kernel.current_state, DispatchState.IDLE)
        proposal = self._create_proposal(step_index=1)

        result = await self.kernel.submit_proposal(proposal)

        # 1. Assert result status
        self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
        self.assertTrue(result.verification_passed)
        self.assertFalse(result.requires_reconciliation)
        self.assertEqual(result.state, DispatchState.RETIRED_SUCCESS)
        self.assertIsNotNone(result.receipt)
        self.assertEqual(result.receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(self.adapter.dispatch_count, 1)
        self.assertEqual(self.verifier.call_count, 1)

        # 2. Assert kernel returned to IDLE
        self.assertEqual(self.kernel.current_state, DispatchState.IDLE)

        # 3. Assert full recorded state machine sequence
        history_states = [transition[1] for transition in self.kernel.state_history]
        expected_sequence = [
            DispatchState.PROPOSAL_RECEIVED,
            DispatchState.AUTHORIZING,
            DispatchState.LEASE_ISSUED,
            DispatchState.IN_FLIGHT,
            DispatchState.SETTLING,
            DispatchState.VERIFYING,
            DispatchState.RETIRED_SUCCESS,
            DispatchState.IDLE,
        ]
        self.assertEqual(history_states, expected_sequence)

    def test_invalid_state_transitions_raise_error(self):
        """Assert that invalid state transitions raise InvalidStateTransitionError."""
        self.assertEqual(self.kernel.current_state, DispatchState.IDLE)

        # Illegal jumps from IDLE
        with self.assertRaises(InvalidStateTransitionError):
            self.kernel.transition_to(DispatchState.IN_FLIGHT)

        with self.assertRaises(InvalidStateTransitionError):
            self.kernel.transition_to(DispatchState.VERIFYING)

        with self.assertRaises(InvalidStateTransitionError):
            self.kernel.transition_to(DispatchState.RETIRED_SUCCESS)

        # Valid transition to PROPOSAL_RECEIVED
        self.kernel.transition_to(DispatchState.PROPOSAL_RECEIVED)
        self.assertEqual(self.kernel.current_state, DispatchState.PROPOSAL_RECEIVED)

        # Illegal jump from PROPOSAL_RECEIVED
        with self.assertRaises(InvalidStateTransitionError):
            self.kernel.transition_to(DispatchState.IN_FLIGHT)

        with self.assertRaises(InvalidStateTransitionError):
            self.kernel.transition_to(DispatchState.RETIRED_SUCCESS)

    async def test_policy_rejection_missing_scope(self):
        """Assert policy rejection when requested capability scope is not granted."""
        proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_001", step_index=1),
            action=TypedAction(
                action_type=ActionType.CLICK,
                metadata={"required_scope": CapabilityScope.FS_WRITE},
            ),
            required_scopes={CapabilityScope.FS_WRITE},  # Not in default browser policy
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertFalse(result.verification_passed)
        self.assertIn("Missing required capability scopes", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)
        self.assertEqual(self.kernel.current_state, DispatchState.IDLE)

        history_states = [t[1] for t in self.kernel.state_history]
        self.assertIn(DispatchState.RETIRED_FAILED, history_states)
        self.assertNotIn(DispatchState.IN_FLIGHT, history_states)

    async def test_policy_rejection_blacklisted_domain(self):
        """Assert policy rejection when target domain is blacklisted."""
        proposal = ActionProposal(
            identity=ActionIdentity.create(session_id="sess_001", step_index=1),
            action=TypedAction(
                action_type=ActionType.NAVIGATE,
                text_payload="https://banking.example.com/transfer",
                metadata={"domain": "banking.example.com"},
            ),
            required_scopes={CapabilityScope.BROWSER_NAVIGATE},
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertIn("blacklisted", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_human_confirmation_interactive_approved(self):
        """Assert destructive action proceeds to LEASE_ISSUED when human confirmation callback returns True."""
        confirmed_proposals = []

        async def confirmation_cb(p: ActionProposal) -> bool:
            confirmed_proposals.append(p.identity.action_id)
            return True

        self.kernel._human_confirmation_callback = confirmation_cb

        proposal = self._create_proposal(
            step_index=1,
            safety_class=SafetyClass.DESTRUCTIVE,
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
        self.assertTrue(result.verification_passed)
        self.assertEqual(len(confirmed_proposals), 1)
        self.assertEqual(self.adapter.dispatch_count, 1)

        history_states = [t[1] for t in self.kernel.state_history]
        self.assertIn(DispatchState.AWAITING_CONFIRMATION, history_states)
        self.assertIn(DispatchState.LEASE_ISSUED, history_states)
        self.assertIn(DispatchState.RETIRED_SUCCESS, history_states)

    async def test_human_confirmation_interactive_denied(self):
        """Assert destructive action transitions to RETIRED_FAILED when human confirmation callback returns False."""
        async def denial_cb(p: ActionProposal) -> bool:
            return False

        self.kernel._human_confirmation_callback = denial_cb

        proposal = self._create_proposal(
            step_index=1,
            safety_class=SafetyClass.DESTRUCTIVE,
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertFalse(result.verification_passed)
        self.assertEqual(self.adapter.dispatch_count, 0)
        self.assertIn("denied", result.error_message or "")

        history_states = [t[1] for t in self.kernel.state_history]
        self.assertIn(DispatchState.AWAITING_CONFIRMATION, history_states)
        self.assertIn(DispatchState.RETIRED_FAILED, history_states)
        self.assertNotIn(DispatchState.IN_FLIGHT, history_states)

    async def test_human_confirmation_pre_confirmed_token(self):
        """Assert destructive action with valid pre-signed confirmation token bypasses interactive prompt."""
        proposal = self._create_proposal(
            step_index=1,
            safety_class=SafetyClass.DESTRUCTIVE,
            metadata={"confirmation_token": "token_signed_xyz_123"},
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.adapter.dispatch_count, 1)

    async def test_emergency_halt_blocks_execution(self):
        """Assert emergency_halt immediately puts kernel in halted mode, revokes leases, and rejects proposals within < 5ms."""
        start_time = time.perf_counter()
        self.kernel.emergency_halt("Manual killswitch activated")
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Halt operation must complete well under 5ms
        self.assertLess(elapsed_ms, 5.0)
        self.assertTrue(self.kernel.is_halted)
        self.assertEqual(self.kernel.halt_reason, "Manual killswitch activated")

        # Submitting proposals when halted raises EmergencyHaltError
        proposal = self._create_proposal(step_index=1)
        with self.assertRaises(EmergencyHaltError):
            await self.kernel.submit_proposal(proposal)

        # Dispatch adapter was never called
        self.assertEqual(self.adapter.dispatch_count, 0)

        # Resuming clears halt
        self.kernel.resume()
        self.assertFalse(self.kernel.is_halted)

        # Subsequent proposal now succeeds
        result = await self.kernel.submit_proposal(proposal)
        self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.adapter.dispatch_count, 1)

    def test_lease_and_result_serialization(self):
        """Assert round-trip dictionary serialization for ActionLease and KernelDispatchResult."""
        identity = ActionIdentity.create(session_id="sess_abc", step_index=3)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit")

        lease = ActionLease(
            lease_id="lease_12345",
            identity=identity,
            action=action,
            expires_at_ms=1005000.0,
            granted_at_ms=1000000.0,
        )

        d_lease = lease.to_dict()
        reconstructed_lease = ActionLease.from_dict(d_lease)
        self.assertEqual(reconstructed_lease.lease_id, lease.lease_id)
        self.assertEqual(reconstructed_lease.identity.action_id, identity.action_id)

        result = KernelDispatchResult(
            identity=identity,
            outcome=OutcomeClass.SUCCESS,
            execution_latency_ms=12.5,
            verification_passed=True,
            requires_reconciliation=False,
            state=DispatchState.RETIRED_SUCCESS,
        )

        d_result = result.to_dict()
        reconstructed_result = KernelDispatchResult.from_dict(d_result)
        self.assertEqual(reconstructed_result.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(reconstructed_result.identity.action_id, identity.action_id)


if __name__ == "__main__":
    unittest.main()
