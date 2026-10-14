from __future__ import annotations
import asyncio
import time
import unittest
from typing import Any, Dict, Optional

from reflex.host.identity import (
    ActionLeaseManager,
    IdempotencyCollisionError,
    IdempotencyRegistry,
    LeaseExpiredError,
    LeaseRevokedError,
    LeaseStatus,
)
from reflex.host.kernel import (
    DispatchState,
    HostControlKernel,
    KernelDispatchResult,
)
from reflex.ports.action import ActionPort
from reflex.ports.clock import DeterministicClock, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.ports.verification import VerificationPort
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityPolicy, CapabilityScope
from reflex.schemas.state import CanonicalUIGraph


class HangingAdapter(ActionPort):
    """Adapter that simulates network drop or CDP socket hang."""

    def __init__(self, hang_seconds: float = 2.0):
        self.hang_seconds = hang_seconds
        self.dispatch_count = 0
        self.adapter_name = "hanging_browser_adapter"

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatch_count += 1
        await asyncio.sleep(self.hang_seconds)
        return {"hung": False}


class CrashingAdapter(ActionPort):
    """Adapter that throws transport/crash exceptions during physical dispatch."""

    def __init__(self, exception_to_throw: Exception):
        self.exception_to_throw = exception_to_throw
        self.dispatch_count = 0
        self.adapter_name = "crashing_browser_adapter"

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatch_count += 1
        raise self.exception_to_throw


class StubVerificationAdapter(VerificationPort):
    """Verifier that returns a specific outcome class."""

    def __init__(self, outcome: OutcomeClass):
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
        return StateDelta(outcome_class=self.outcome)


class TestKernelTimeoutHandling(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying timeout handling, lease revocation, transition to RECONCILING, and no blind retry."""

    def setUp(self):
        self.clock = SystemClock()
        self.policy = CapabilityPolicy.permissive_policy()
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.idempotency_registry = IdempotencyRegistry(clock=self.clock)

    def _create_proposal(
        self,
        session_id: str = "timeout_session_001",
        step_index: int = 1,
    ) -> ActionProposal:
        identity = ActionIdentity.create(session_id=session_id, step_index=step_index)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_hang")
        return ActionProposal(
            identity=identity,
            action=action,
            required_scopes={CapabilityScope.BROWSER_INTERACT},
        )

    async def test_dispatch_timeout_revokes_lease_and_requires_reconciliation(self):
        """Verify that physical action dispatch hang triggers timeout, revokes lease, and transitions to RECONCILING."""
        hanging_adapter = HangingAdapter(hang_seconds=1.0)

        kernel = HostControlKernel(
            policy=self.policy,
            action_port=hanging_adapter,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.idempotency_registry,
            dispatch_timeout_s=0.05,  # 50ms fast timeout
            settle_interval_s=0.0,
        )

        proposal = self._create_proposal(step_index=1)
        result = await kernel.submit_proposal(proposal)

        # 1. Assert result classifies as UNKNOWN_EFFECT and requires reconciliation
        self.assertEqual(result.outcome, OutcomeClass.UNKNOWN_EFFECT)
        self.assertFalse(result.verification_passed)
        self.assertTrue(result.requires_reconciliation)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)
        self.assertIn("timed out", result.error_message or "")

        # 2. Invariant: Exactly 1 dispatch attempt occurred (no blind retries)
        self.assertEqual(hanging_adapter.dispatch_count, 1)

        # 3. Assert lease was revoked
        lease = self.lease_manager.get_lease_by_action_id(proposal.identity.action_id)
        self.assertIsNotNone(lease)
        self.assertEqual(
            self.lease_manager.get_lease_status(lease.lease_id),
            LeaseStatus.REVOKED,
        )

        # 4. Assert recorded state transitions include RECONCILING
        history_states = [t[1] for t in kernel.state_history]
        self.assertIn(DispatchState.IN_FLIGHT, history_states)
        self.assertIn(DispatchState.RECONCILING, history_states)
        self.assertIn(DispatchState.RETIRED_FAILED, history_states)
        self.assertEqual(kernel.current_state, DispatchState.IDLE)

        # 5. Resubmitting the same ActionIdentity must be rejected (duplicate suppression)
        with self.assertRaises(IdempotencyCollisionError):
            await kernel.submit_proposal(proposal)

    async def test_adapter_crash_transitions_to_reconciling_and_revokes_lease(self):
        """Verify unhandled transport crash triggers lease revocation and RECONCILING state transition."""
        crashing_adapter = CrashingAdapter(ConnectionResetError("CDP WebSocket disconnected"))

        kernel = HostControlKernel(
            policy=self.policy,
            action_port=crashing_adapter,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.idempotency_registry,
            settle_interval_s=0.0,
        )

        proposal = self._create_proposal(step_index=1)
        result = await kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.UNKNOWN_EFFECT)
        self.assertFalse(result.verification_passed)
        self.assertTrue(result.requires_reconciliation)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)
        self.assertIn("CDP WebSocket disconnected", result.error_message or "")
        self.assertEqual(crashing_adapter.dispatch_count, 1)

        # Lease was revoked
        lease = self.lease_manager.get_lease_by_action_id(proposal.identity.action_id)
        self.assertIsNotNone(lease)
        self.assertEqual(self.lease_manager.get_lease_status(lease.lease_id), LeaseStatus.REVOKED)

    async def test_verification_failure_triggers_reconciling(self):
        """Verify post-action verification failure (e.g. MODAL_APPEARED) transitions through RECONCILING."""
        modal_verifier = StubVerificationAdapter(OutcomeClass.MODAL_APPEARED)

        kernel = HostControlKernel(
            policy=self.policy,
            verification_port=modal_verifier,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.idempotency_registry,
            settle_interval_s=0.0,
        )

        proposal = self._create_proposal(step_index=1)
        result = await kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.MODAL_APPEARED)
        self.assertFalse(result.verification_passed)
        self.assertTrue(result.requires_reconciliation)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)

        # Verify state history contains VERIFYING -> RECONCILING -> RETIRED_FAILED
        history_states = [t[1] for t in kernel.state_history]
        self.assertIn(DispatchState.VERIFYING, history_states)
        self.assertIn(DispatchState.RECONCILING, history_states)
        self.assertIn(DispatchState.RETIRED_FAILED, history_states)

    def test_lease_expiration_guards(self):
        """Verify lease manager raises LeaseExpiredError when attempting to acquire expired lease."""
        clock = DeterministicClock(start_time_ms=1000000.0)
        manager = ActionLeaseManager(clock=clock, default_ttl_ms=1000.0)

        identity = ActionIdentity.create(session_id="sess_exp", step_index=1)
        action = TypedAction(action_type=ActionType.CLICK)
        lease = manager.issue_lease(identity, action, ttl_ms=1000.0)

        # Before expiry: status is ISSUED
        self.assertEqual(manager.get_lease_status(lease.lease_id), LeaseStatus.ISSUED)
        self.assertTrue(manager.is_lease_valid(lease.lease_id))

        # Advance clock past TTL (1000ms)
        clock.advance(1500.0)

        # Status is now EXPIRED
        self.assertEqual(manager.get_lease_status(lease.lease_id), LeaseStatus.EXPIRED)
        self.assertFalse(manager.is_lease_valid(lease.lease_id))

        # Acquisition raises LeaseExpiredError
        with self.assertRaises(LeaseExpiredError):
            manager.acquire_lease(lease.lease_id)

    def test_revoked_lease_acquisition_raises_error(self):
        """Verify lease manager raises LeaseRevokedError when attempting to acquire revoked lease."""
        manager = ActionLeaseManager()
        identity = ActionIdentity.create(session_id="sess_rev", step_index=1)
        action = TypedAction(action_type=ActionType.CLICK)
        lease = manager.issue_lease(identity, action)

        manager.revoke_lease(lease.lease_id, reason="Policy anomaly")
        self.assertEqual(manager.get_lease_status(lease.lease_id), LeaseStatus.REVOKED)

        with self.assertRaises(LeaseRevokedError):
            manager.acquire_lease(lease.lease_id)


if __name__ == "__main__":
    unittest.main()
