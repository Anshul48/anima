from __future__ import annotations
import asyncio
import time
import unittest
from typing import Any, Dict, List, Optional

from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.execution.input.synthetic_input_adapter import SyntheticInputAdapter
from reflex.execution.router import ExecutionRouter
from reflex.host.identity import (
    ActionExecutionLockedError,
    ActionLease,
    ActionLeaseManager,
    ActionRecord,
    IdempotencyCollisionError,
    IdempotencyError,
    IdempotencyRegistry,
    InvalidLeaseError,
    LeaseAlreadyAcquiredError,
    LeaseExpiredError,
    LeaseNotFoundError,
    LeaseRevokedError,
    LeaseStatus,
    NonMonotonicStepError,
)
from reflex.host.kernel import (
    DispatchState,
    EmergencyHaltError,
    HostControlKernel,
    InvalidStateTransitionError,
    KernelDispatchResult,
    VALID_TRANSITIONS,
)
from reflex.host.policy import CapabilityPolicyEngine, PolicyEvaluationResult
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.ports.action import ActionPort, ActionReceipt, ActionStatus
from reflex.ports.clock import DeterministicClock, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.ports.verification import VerificationPort
from reflex.schemas.actions import (
    ActionType,
    NormalizedCoords,
    SafetyClass,
    TypedAction,
)
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import (
    CapabilityGrant,
    CapabilityPolicy,
    CapabilityScope,
)
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


# ============================================================================
# Test Doubles & Mock Ports
# ============================================================================

class MockActionAdapter(ActionPort):
    """Observable action adapter recording all physical dispatch calls."""

    def __init__(self, delay_ms: float = 0.0, fail_with: Optional[Exception] = None):
        self.delay_ms = delay_ms
        self.fail_with = fail_with
        self.dispatch_count = 0
        self.dispatched_actions: List[TypedAction] = []
        self.dispatched_identities: List[ActionIdentity] = []
        self.adapter_name = "mock_security_adapter"
        self._lock = asyncio.Lock()

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        async with self._lock:
            self.dispatch_count += 1
            self.dispatched_actions.append(action)
            self.dispatched_identities.append(identity)

        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)

        if self.fail_with is not None:
            raise self.fail_with

        return {"dispatched": True, "action_id": identity.action_id}


class MockObservationPort(ObservationPort):
    """Observation port providing mock UI graphs."""

    def __init__(self):
        self.capture_count = 0

    async def capture_state(self) -> CanonicalUIGraph:
        self.capture_count += 1
        return CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes={
                "target_node": UIStateNode(
                    node_id="target_node",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 100, 200, 50),
                    label="Execute Action",
                )
            },
            url="https://app.example.com",
        )

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_screenshot"


class MockVerificationPort(VerificationPort):
    """Deterministic verification port with configurable outcome class."""

    def __init__(self, outcome: OutcomeClass = OutcomeClass.SUCCESS):
        self.outcome = outcome
        self.verification_count = 0

    async def verify_transition(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
        after_state: CanonicalUIGraph,
        expected_delta: Optional[StateDelta] = None,
    ) -> StateDelta:
        self.verification_count += 1
        return StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=[],
            pixel_change_ratio=0.01,
            outcome_class=self.outcome,
        )


# ============================================================================
# Security Invariant Test Suite
# ============================================================================

class TestDirectAdapterBypassProtection(unittest.IsolatedAsyncioTestCase):
    """Invariant 1: Host kernel is the sole action authority.
    
    Direct invocation of physical execution adapters (CDPActionAdapter,
    SyntheticInputAdapter, ExecutionRouter) without a valid host-issued
    ActionLease must strictly fail closed with InvalidLeaseError.
    """

    def setUp(self):
        self.page = FakeBrowserPage(viewport_width=1280, viewport_height=800)
        self.lease_manager = ActionLeaseManager(default_ttl_ms=5000.0)
        self.cdp_adapter = CDPActionAdapter(page=self.page, lease_manager=self.lease_manager)
        self.synth_adapter = SyntheticInputAdapter(page=self.page, lease_manager=self.lease_manager)
        self.router = ExecutionRouter(
            cdp_adapter=self.cdp_adapter,
            synthetic_adapter=self.synth_adapter,
            lease_manager=self.lease_manager,
            page=self.page,
        )

    def _create_action(
        self,
        action_type: ActionType = ActionType.CLICK,
        target: str = "#target_node",
    ) -> TypedAction:
        return TypedAction(
            action_type=action_type,
            target_node_id=target,
            coords=NormalizedCoords(0.5, 0.5),
            safety_class=SafetyClass.REVERSIBLE,
        )

    async def test_cdp_adapter_direct_call_without_lease_fails_closed(self):
        """Direct call to CDPActionAdapter with lease=None must raise InvalidLeaseError and emit 0 page events."""
        action = self._create_action(ActionType.CLICK)

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.cdp_adapter.execute_action(action=action, lease=None)  # type: ignore

        self.assertIn("ActionLease is required", str(ctx.exception))
        self.assertEqual(len(self.page.event_log), 0, "No browser events must be emitted without a lease")

    async def test_synthetic_adapter_direct_call_without_lease_fails_closed(self):
        """Direct call to SyntheticInputAdapter with lease=None must raise InvalidLeaseError and emit 0 page events."""
        action = self._create_action(ActionType.CLICK)

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.synth_adapter.execute_action(action=action, lease=None)  # type: ignore

        self.assertIn("ActionLease is required", str(ctx.exception))
        self.assertEqual(len(self.page.event_log), 0, "No browser events must be emitted without a lease")

    async def test_router_direct_call_without_lease_fails_closed(self):
        """Direct call to ExecutionRouter with lease=None must raise InvalidLeaseError."""
        action = self._create_action(ActionType.CLICK)

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.router.execute_action(action=action, lease=None)  # type: ignore

        self.assertIn("ActionLease is required", str(ctx.exception))
        self.assertEqual(len(self.page.event_log), 0)

    async def test_adapter_direct_call_with_forged_cryptographic_token_rejected(self):
        """Tampering with cryptographic token in ActionLease must be rejected with InvalidLeaseError."""
        action = self._create_action(ActionType.CLICK)
        identity = ActionIdentity.create(session_id="sess_sec", step_index=1)
        valid_lease = self.lease_manager.issue_lease(identity, action)

        tampered_lease = ActionLease(
            lease_id=valid_lease.lease_id,
            identity=valid_lease.identity,
            action=valid_lease.action,
            expires_at_ms=valid_lease.expires_at_ms,
            token="forged_cryptographic_signature_token_000",
            created_at_ms=valid_lease.created_at_ms,
        )

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.cdp_adapter.execute_action(action=action, lease=tampered_lease)

        self.assertTrue(str(ctx.exception).strip())
        self.assertEqual(len(self.page.event_log), 0)

    async def test_adapter_direct_call_with_action_type_mismatch_rejected(self):
        """Action type mismatch between lease and dispatched action must fail closed."""
        action_click = self._create_action(ActionType.CLICK)
        identity = ActionIdentity.create(session_id="sess_sec", step_index=1)
        lease_click = self.lease_manager.issue_lease(identity, action_click)

        action_type = TypedAction(action_type=ActionType.TYPE, text_payload="Malicious Payload")

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.cdp_adapter.execute_action(action=action_type, lease=lease_click)

        self.assertTrue(str(ctx.exception).strip())
        self.assertEqual(len(self.page.event_log), 0)

    async def test_adapter_standalone_validation_without_manager_fails_closed(self):
        """Adapter instantiated without LeaseManager refuses every execution immediately.

        Manager-free local validation was removed: even a properly issued lease
        must fail closed when the executing adapter is not bound to its issuing
        authority, and zero input events may fire.
        """
        standalone_adapter = CDPActionAdapter(page=self.page, lease_manager=None)
        action = self._create_action(ActionType.CLICK)
        identity = ActionIdentity.create(session_id="sess_sec", step_index=1)
        lease = self.lease_manager.issue_lease(identity, action)

        # First execution attempt already fails closed (no manager, no execution).
        with self.assertRaises(InvalidLeaseError) as ctx:
            await standalone_adapter.execute_action(action=action, lease=lease)
        self.assertTrue(str(ctx.exception).strip())
        self.assertEqual(len(self.page.event_log), 0)

        # Port dispatch without a manager fails closed as well.
        with self.assertRaises(InvalidLeaseError):
            await standalone_adapter.dispatch_action(action=action, identity=identity)
        self.assertEqual(len(self.page.event_log), 0)

        # The un-consumed lease remains valid at its issuing authority.
        self.lease_manager.validate_lease(lease, action=action)


class TestLeaseReplayAndExpirationInvariants(unittest.IsolatedAsyncioTestCase):
    """Invariant 2: Leases are strictly single-use, bounded by TTL, and subject to immediate revocation.
    
    Replay of expired, already-consumed, or revoked leases must be rejected.
    """

    def setUp(self):
        self.clock = SystemClock()
        self.lease_manager = ActionLeaseManager(clock=self.clock, default_ttl_ms=5000.0)
        self.page = FakeBrowserPage()
        self.adapter = CDPActionAdapter(page=self.page, lease_manager=self.lease_manager)

    def _create_action(self) -> TypedAction:
        return TypedAction(action_type=ActionType.CLICK, target_node_id="#btn")

    async def test_replay_consumed_lease_against_adapter_rejected(self):
        """A lease that was consumed once cannot be reused for a second physical dispatch."""
        action = self._create_action()
        identity = ActionIdentity.create(session_id="sess_replay", step_index=1)
        lease = self.lease_manager.issue_lease(identity, action)

        # 1. First execution consumes lease
        receipt1 = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt1.status, ActionStatus.DISPATCHED)

        # 2. Replay attempt must raise InvalidLeaseError
        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.adapter.execute_action(action=action, lease=lease)
        self.assertIn("already been consumed", str(ctx.exception).lower())

    async def test_replay_consumed_lease_concurrent_race_strictly_single_execution(self):
        """Under high concurrency (50 tasks), an ActionLease is consumed exactly once and 49 tasks fail closed."""
        action = self._create_action()
        identity = ActionIdentity.create(session_id="sess_race", step_index=1)
        lease = self.lease_manager.issue_lease(identity, action)

        success_count = 0
        rejection_count = 0

        async def worker():
            nonlocal success_count, rejection_count
            try:
                receipt = await self.adapter.execute_action(action=action, lease=lease)
                if receipt.status == ActionStatus.DISPATCHED:
                    success_count += 1
            except InvalidLeaseError:
                rejection_count += 1

        tasks = [asyncio.create_task(worker()) for _ in range(50)]
        await asyncio.gather(*tasks)

        self.assertEqual(success_count, 1, "Exactly one task must successfully execute under the lease")
        self.assertEqual(rejection_count, 49, "49 tasks must be rejected with InvalidLeaseError")

    def test_replay_expired_lease_rejected(self):
        """Attempting to validate or acquire an expired lease raises LeaseExpiredError / InvalidLeaseError."""
        clock = DeterministicClock(start_time_ms=1000000.0)
        manager = ActionLeaseManager(clock=clock, default_ttl_ms=2000.0)
        action = self._create_action()
        identity = ActionIdentity.create(session_id="sess_exp", step_index=1)
        lease = manager.issue_lease(identity, action, ttl_ms=2000.0)

        # Advance clock by 3000ms (past 2000ms TTL)
        clock.advance(3000.0)

        self.assertEqual(manager.get_lease_status(lease.lease_id), LeaseStatus.EXPIRED)
        self.assertFalse(manager.is_lease_valid(lease.lease_id))

        with self.assertRaises(LeaseExpiredError):
            manager.acquire_lease(lease.lease_id)

        with self.assertRaises(InvalidLeaseError) as ctx:
            manager.validate_lease(lease)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_replay_revoked_lease_rejected(self):
        """Attempting to validate or acquire a revoked lease raises LeaseRevokedError / InvalidLeaseError."""
        action = self._create_action()
        identity = ActionIdentity.create(session_id="sess_rev", step_index=1)
        lease = self.lease_manager.issue_lease(identity, action)

        self.lease_manager.revoke_lease(lease.lease_id, reason="Security anomaly detected")
        self.assertEqual(self.lease_manager.get_lease_status(lease.lease_id), LeaseStatus.REVOKED)

        with self.assertRaises(LeaseRevokedError):
            self.lease_manager.acquire_lease(lease.lease_id)

        with self.assertRaises(InvalidLeaseError) as ctx:
            self.lease_manager.validate_lease(lease)
        self.assertIn("revoked", str(ctx.exception).lower())

    def test_retired_lease_cannot_be_reused(self):
        """Retired lease transitions to RETIRED status and is no longer valid for execution."""
        action = self._create_action()
        identity = ActionIdentity.create(session_id="sess_ret", step_index=1)
        lease = self.lease_manager.issue_lease(identity, action)

        self.lease_manager.acquire_lease(lease.lease_id)
        self.lease_manager.retire_lease(lease.lease_id)

        self.assertEqual(self.lease_manager.get_lease_status(lease.lease_id), LeaseStatus.RETIRED)
        self.assertFalse(self.lease_manager.is_lease_valid(lease.lease_id))


class TestDoubleDispatchAndIdempotencyInvariants(unittest.IsolatedAsyncioTestCase):
    """Invariant 3: At-most-one physical dispatch per ActionIdentity (A_id) is mathematically guaranteed.
    
    Attempted double dispatch of the same ActionIdentity or idempotency key
    must be rejected with IdempotencyCollisionError / ActionExecutionLockedError.
    """

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)
        self.policy = CapabilityPolicy.permissive_policy()
        self.adapter = MockActionAdapter(delay_ms=2.0)
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.registry = IdempotencyRegistry(clock=self.clock)

        self.kernel = HostControlKernel(
            policy=self.policy,
            action_port=self.adapter,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.registry,
            settle_interval_s=0.0,
        )

    def _create_proposal(
        self,
        session_id: str = "sess_idem",
        step_index: int = 1,
    ) -> ActionProposal:
        identity = ActionIdentity.create(session_id=session_id, step_index=step_index)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="#btn")
        return ActionProposal(
            identity=identity,
            action=action,
            required_scopes={CapabilityScope.BROWSER_INTERACT},
        )

    async def test_double_dispatch_same_action_identity_rejected(self):
        """Sequential re-submission of the same ActionIdentity must raise IdempotencyCollisionError on second attempt."""
        proposal = self._create_proposal(step_index=1)

        # 1. First submission succeeds
        result1 = await self.kernel.submit_proposal(proposal)
        self.assertEqual(result1.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.adapter.dispatch_count, 1)

        # 2. Second submission with identical ActionIdentity must raise IdempotencyCollisionError
        with self.assertRaises(IdempotencyCollisionError) as ctx:
            await self.kernel.submit_proposal(proposal)

        self.assertIn("already been registered", str(ctx.exception))
        # Dispatch count must remain exactly 1
        self.assertEqual(self.adapter.dispatch_count, 1, "Physical adapter dispatch count must remain exactly 1")

    async def test_duplicate_idempotency_key_with_different_action_id_rejected(self):
        """Submitting a proposal with a reused idempotency_key (even with a different action_id) raises IdempotencyCollisionError."""
        shared_key = "fixed_sha256_idempotency_key_12345"

        id1 = ActionIdentity(
            action_id="act_first_001",
            session_id="sess_key_dup",
            step_index=1,
            idempotency_key=shared_key,
            created_at_ms=1000.0,
        )
        prop1 = ActionProposal(identity=id1, action=TypedAction(action_type=ActionType.CLICK))
        res1 = await self.kernel.submit_proposal(prop1)
        self.assertEqual(res1.outcome, OutcomeClass.SUCCESS)

        id2 = ActionIdentity(
            action_id="act_second_002",
            session_id="sess_key_dup",
            step_index=2,
            idempotency_key=shared_key,  # Duplicate idempotency token!
            created_at_ms=2000.0,
        )
        prop2 = ActionProposal(identity=id2, action=TypedAction(action_type=ActionType.CLICK))

        with self.assertRaises(IdempotencyCollisionError) as ctx:
            await self.kernel.submit_proposal(prop2)

        self.assertIn("Idempotency token collision", str(ctx.exception))
        self.assertEqual(self.adapter.dispatch_count, 1)

    def test_registry_atomic_begin_dispatch_locks_after_one_attempt(self):
        """Direct call to atomic_begin_dispatch raises ActionExecutionLockedError on 2nd invocation."""
        identity = ActionIdentity.create(session_id="sess_lock", step_index=1)
        self.registry.register_proposal(identity)

        # First begin_dispatch succeeds
        self.assertTrue(self.registry.atomic_begin_dispatch(identity.action_id))
        self.assertEqual(self.registry.get_dispatch_count(identity.action_id), 1)

        # Second begin_dispatch must raise ActionExecutionLockedError
        with self.assertRaises(ActionExecutionLockedError) as ctx:
            self.registry.atomic_begin_dispatch(identity.action_id)

        self.assertIn("At-most-one dispatch invariant violated", str(ctx.exception))
        self.assertEqual(self.registry.get_dispatch_count(identity.action_id), 1)

    async def test_concurrent_double_dispatch_race_strictly_single_dispatch(self):
        """Under concurrent dispatch race (50 tasks), exactly 1 physical execution occurs and 49 are rejected."""
        proposal = self._create_proposal(step_index=1)

        successes: List[KernelDispatchResult] = []
        rejected: List[Exception] = []

        async def worker():
            try:
                res = await self.kernel.submit_proposal(proposal)
                if res.outcome == OutcomeClass.SUCCESS:
                    successes.append(res)
            except (IdempotencyCollisionError, ActionExecutionLockedError, LeaseAlreadyAcquiredError) as e:
                rejected.append(e)

        tasks = [asyncio.create_task(worker()) for _ in range(50)]
        await asyncio.gather(*tasks)

        self.assertEqual(len(successes), 1, "Exactly 1 concurrent submission must succeed")
        self.assertEqual(len(rejected), 49, "49 concurrent submissions must be rejected")
        self.assertEqual(self.adapter.dispatch_count, 1, "Adapter must be invoked exactly once")


class TestMonotonicStepOrderingInvariants(unittest.IsolatedAsyncioTestCase):
    """Invariant 4: Monotonic step index violation is strictly rejected with NonMonotonicStepError.
    
    Session step indices must be strictly increasing.
    """

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)
        self.policy = CapabilityPolicy.permissive_policy()
        self.adapter = MockActionAdapter()
        self.registry = IdempotencyRegistry(clock=self.clock)

        self.kernel = HostControlKernel(
            policy=self.policy,
            action_port=self.adapter,
            clock=self.clock,
            idempotency_registry=self.registry,
            settle_interval_s=0.0,
        )

    def _create_proposal(self, session_id: str, step_index: int) -> ActionProposal:
        identity = ActionIdentity.create(session_id=session_id, step_index=step_index)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="#btn")
        return ActionProposal(identity=identity, action=action)

    async def test_monotonic_step_index_duplicate_step_rejected(self):
        """Submitting step N followed by step N within the same session raises NonMonotonicStepError."""
        session_id = "session_mono_dup"

        p1 = self._create_proposal(session_id=session_id, step_index=1)
        res1 = await self.kernel.submit_proposal(p1)
        self.assertEqual(res1.outcome, OutcomeClass.SUCCESS)

        p1_dup = self._create_proposal(session_id=session_id, step_index=1)
        with self.assertRaises(NonMonotonicStepError) as ctx:
            await self.kernel.submit_proposal(p1_dup)

        self.assertIn("Non-monotonic step index 1", str(ctx.exception))
        self.assertEqual(self.adapter.dispatch_count, 1)

    async def test_monotonic_step_index_regressive_step_rejected(self):
        """Submitting step 5 followed by regressive step 2 or step 0 raises NonMonotonicStepError."""
        session_id = "session_mono_reg"

        p5 = self._create_proposal(session_id=session_id, step_index=5)
        res5 = await self.kernel.submit_proposal(p5)
        self.assertEqual(res5.outcome, OutcomeClass.SUCCESS)

        p2 = self._create_proposal(session_id=session_id, step_index=2)
        with self.assertRaises(NonMonotonicStepError) as ctx:
            await self.kernel.submit_proposal(p2)
        self.assertIn("Non-monotonic step index 2", str(ctx.exception))

        p0 = self._create_proposal(session_id=session_id, step_index=0)
        with self.assertRaises(NonMonotonicStepError) as ctx:
            await self.kernel.submit_proposal(p0)
        self.assertIn("Non-monotonic step index 0", str(ctx.exception))

        self.assertEqual(self.adapter.dispatch_count, 1)

    async def test_monotonic_step_index_strictly_increasing_accepted(self):
        """Strictly increasing step sequence (1 -> 2 -> 5 -> 10) succeeds without errors."""
        session_id = "session_mono_seq"

        for step in [1, 2, 5, 10]:
            prop = self._create_proposal(session_id=session_id, step_index=step)
            res = await self.kernel.submit_proposal(prop)
            self.assertEqual(res.outcome, OutcomeClass.SUCCESS)

        self.assertEqual(self.adapter.dispatch_count, 4)
        self.assertEqual(self.registry.get_last_step_index(session_id), 10)

    async def test_session_isolation_independent_step_counters(self):
        """Sessions have independent monotonic step counters and do not interfere with each other."""
        sess_a = "session_Alpha"
        sess_b = "session_Beta"

        # Session Alpha at step 20
        prop_a = self._create_proposal(session_id=sess_a, step_index=20)
        res_a = await self.kernel.submit_proposal(prop_a)
        self.assertEqual(res_a.outcome, OutcomeClass.SUCCESS)

        # Session Beta can cleanly start at step 1
        prop_b = self._create_proposal(session_id=sess_b, step_index=1)
        res_b = await self.kernel.submit_proposal(prop_b)
        self.assertEqual(res_b.outcome, OutcomeClass.SUCCESS)

        self.assertEqual(self.registry.get_last_step_index(sess_a), 20)
        self.assertEqual(self.registry.get_last_step_index(sess_b), 1)


class TestCapabilityPolicyAndSafetyGatingInvariants(unittest.IsolatedAsyncioTestCase):
    """Invariant 5: Capability scopes and safety classes enforce mandatory approval/policy gating.
    
    Ungranted capability scopes (OS_INPUT_INJECT, FS_WRITE, BROWSER_NAVIGATE) and
    elevated safety classes (DESTRUCTIVE, AMBIGUOUS) without confirmation must fail closed.
    """

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000000.0)
        self.policy = CapabilityPolicy.default_browser_policy()
        self.adapter = MockActionAdapter()
        self.kernel = HostControlKernel(
            policy=self.policy,
            action_port=self.adapter,
            clock=self.clock,
            settle_interval_s=0.0,
        )

    def _create_proposal(
        self,
        action_type: ActionType = ActionType.CLICK,
        safety_class: SafetyClass = SafetyClass.REVERSIBLE,
        required_scopes: Optional[set[CapabilityScope]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        text_payload: Optional[str] = None,
        step_index: int = 1,
    ) -> ActionProposal:
        identity = ActionIdentity.create(session_id="sess_policy", step_index=step_index)
        action = TypedAction(
            action_type=action_type,
            safety_class=safety_class,
            target_node_id="target_btn",
            metadata=metadata or {},
            text_payload=text_payload,
        )
        return ActionProposal(
            identity=identity,
            action=action,
            required_scopes=required_scopes or {CapabilityScope.BROWSER_INTERACT},
        )

    async def test_unauthorized_scope_os_input_inject_rejected(self):
        """Action requesting OS_INPUT_INJECT without grant is rejected by policy engine and never reaches adapter."""
        proposal = self._create_proposal(
            action_type=ActionType.CLICK,
            required_scopes={CapabilityScope.OS_INPUT_INJECT},
            metadata={"required_scope": CapabilityScope.OS_INPUT_INJECT},
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertFalse(result.verification_passed)
        self.assertIn("Missing required capability scopes", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0, "Adapter must never be dispatched for ungranted scope")
        self.assertEqual(self.kernel.current_state, DispatchState.IDLE)

    async def test_unauthorized_scope_fs_write_rejected(self):
        """Action requesting FS_WRITE without grant is rejected and never dispatched."""
        proposal = self._create_proposal(
            action_type=ActionType.CLICK,
            required_scopes={CapabilityScope.FS_WRITE},
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertIn("Missing required capability scopes", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_unauthorized_scope_browser_download_rejected(self):
        """Action requesting BROWSER_DOWNLOAD without grant is rejected."""
        proposal = self._create_proposal(
            action_type=ActionType.CLICK,
            required_scopes={CapabilityScope.BROWSER_DOWNLOAD},
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertIn("Missing required capability scopes", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_expired_capability_grant_rejected(self):
        """Temporary CapabilityGrant is valid before expiry and rejected immediately after expiry."""
        grant = CapabilityGrant(
            scope=CapabilityScope.FS_WRITE,
            granted_at_ms=1000000.0,
            expires_at_ms=1005000.0,  # 5s validity
        )
        custom_policy = CapabilityPolicy(
            granted_scopes={CapabilityScope.BROWSER_INTERACT},
            grants=[grant],
        )
        kernel = HostControlKernel(
            policy=custom_policy,
            action_port=self.adapter,
            clock=self.clock,
            settle_interval_s=0.0,
        )

        # 1. Before expiry (1002000ms): Valid
        self.clock.advance(2000.0)
        p1 = self._create_proposal(required_scopes={CapabilityScope.FS_WRITE}, step_index=1)
        res1 = await kernel.submit_proposal(p1)
        self.assertEqual(res1.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.adapter.dispatch_count, 1)

        # 2. Advance clock past expiry (1006000ms)
        self.clock.advance(4000.0)
        p2 = self._create_proposal(required_scopes={CapabilityScope.FS_WRITE}, step_index=2)
        res2 = await kernel.submit_proposal(p2)
        self.assertEqual(res2.outcome, OutcomeClass.ERROR)
        self.assertIn("Missing required capability scopes", res2.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 1, "Expired grant must not dispatch")

    async def test_blacklisted_domain_exact_match_rejected(self):
        """Navigating to blacklisted banking domain is blocked with DOMAIN_DISALLOWED."""
        proposal = self._create_proposal(
            action_type=ActionType.NAVIGATE,
            text_payload="https://banking.example.com/transfer",
            required_scopes={CapabilityScope.BROWSER_NAVIGATE},
            metadata={"domain": "banking.example.com"},
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertIn("blacklisted", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_blacklisted_domain_wildcard_rejected(self):
        """Navigating to domain matching *.internal wildcard is blocked."""
        proposal = self._create_proposal(
            action_type=ActionType.NAVIGATE,
            text_payload="https://corp.internal/admin",
            required_scopes={CapabilityScope.BROWSER_NAVIGATE},
            metadata={"url": "https://corp.internal/admin"},
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertIn("blacklisted", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_blacklisted_cloud_metadata_ip_rejected(self):
        """Navigating to cloud instance metadata service (169.254.169.254) is blocked."""
        proposal = self._create_proposal(
            action_type=ActionType.NAVIGATE,
            text_payload="http://169.254.169.254/latest/meta-data/",
            required_scopes={CapabilityScope.BROWSER_NAVIGATE},
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertIn("blacklisted", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_session_action_rate_limit_enforced(self):
        """Exceeding max_actions_per_session is rejected by policy engine."""
        policy_limited = CapabilityPolicy(
            granted_scopes={CapabilityScope.BROWSER_INTERACT},
            max_actions_per_session=2,
        )
        kernel = HostControlKernel(
            policy=policy_limited,
            action_port=self.adapter,
            clock=self.clock,
            settle_interval_s=0.0,
        )

        # Action 1: Allowed
        p1 = self._create_proposal(step_index=1)
        res1 = await kernel.submit_proposal(p1)
        self.assertEqual(res1.outcome, OutcomeClass.SUCCESS)

        # Action 2: Allowed
        p2 = self._create_proposal(step_index=2)
        res2 = await kernel.submit_proposal(p2)
        self.assertEqual(res2.outcome, OutcomeClass.SUCCESS)

        # Action 3: Rejected (Limit reached)
        p3 = self._create_proposal(step_index=3)
        res3 = await kernel.submit_proposal(p3)
        self.assertEqual(res3.outcome, OutcomeClass.ERROR)
        self.assertIn("Session action limit reached", res3.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 2)

    async def test_destructive_action_unconfirmed_rejected(self):
        """Unconfirmed DESTRUCTIVE action fails closed without dispatch."""
        proposal = self._create_proposal(
            safety_class=SafetyClass.DESTRUCTIVE,
            step_index=1,
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertIn("Human confirmation denied or timed out", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_ambiguous_action_unconfirmed_rejected(self):
        """Unconfirmed AMBIGUOUS action fails closed without dispatch."""
        proposal = self._create_proposal(
            safety_class=SafetyClass.AMBIGUOUS,
            step_index=1,
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertIn("Human confirmation denied or timed out", result.error_message or "")
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_destructive_action_interactive_confirmation_denied_fails_closed(self):
        """Interactive human callback returning False aborts DESTRUCTIVE action."""
        async def denial_callback(p: ActionProposal) -> bool:
            return False

        self.kernel._human_confirmation_callback = denial_callback
        proposal = self._create_proposal(safety_class=SafetyClass.DESTRUCTIVE, step_index=1)

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.ERROR)
        self.assertEqual(self.adapter.dispatch_count, 0)
        history_states = [t[1] for t in self.kernel.state_history]
        self.assertIn(DispatchState.AWAITING_CONFIRMATION, history_states)
        self.assertIn(DispatchState.RETIRED_FAILED, history_states)
        self.assertNotIn(DispatchState.IN_FLIGHT, history_states)

    async def test_destructive_action_interactive_confirmation_approved_dispatches(self):
        """Interactive human callback returning True authorizes DESTRUCTIVE action."""
        callback_called = False

        async def approval_callback(p: ActionProposal) -> bool:
            nonlocal callback_called
            callback_called = True
            return True

        self.kernel._human_confirmation_callback = approval_callback
        proposal = self._create_proposal(safety_class=SafetyClass.DESTRUCTIVE, step_index=1)

        result = await self.kernel.submit_proposal(proposal)

        self.assertTrue(callback_called)
        self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.adapter.dispatch_count, 1)

    async def test_destructive_action_pre_confirmed_token_dispatches(self):
        """DESTRUCTIVE action with pre-signed confirmation_token authorizes and dispatches without prompt."""
        proposal = self._create_proposal(
            safety_class=SafetyClass.DESTRUCTIVE,
            metadata={"confirmation_token": "signed_operator_token_abc_789"},
            step_index=1,
        )

        result = await self.kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.adapter.dispatch_count, 1)


class TestTimeoutAndReconciliationInvariants(unittest.IsolatedAsyncioTestCase):
    """Invariant 6: Unknown effects / timeouts transition to RECONCILING, strictly prohibiting blind retries.
    
    Execution timeouts, settlement timeouts, and transport crashes must:
    1. Revoke active leases.
    2. Transition through RECONCILING -> RETIRED_FAILED.
    3. Return outcome UNKNOWN_EFFECT with requires_reconciliation=True.
    4. Prohibit automatic physical retry.
    5. Block subsequent retries of the same ActionIdentity in the idempotency registry.
    """

    def setUp(self):
        self.clock = SystemClock()
        self.policy = CapabilityPolicy.permissive_policy()
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.registry = IdempotencyRegistry(clock=self.clock)

    def _create_proposal(
        self,
        session_id: str = "sess_timeout",
        step_index: int = 1,
    ) -> ActionProposal:
        identity = ActionIdentity.create(session_id=session_id, step_index=step_index)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="#btn_hang")
        return ActionProposal(
            identity=identity,
            action=action,
            required_scopes={CapabilityScope.BROWSER_INTERACT},
        )

    async def test_physical_dispatch_timeout_transitions_to_reconciling_unknown_effect(self):
        """Simulate CDP socket or browser dispatch hang exceeding dispatch_timeout_s.
        
        Must transition IN_FLIGHT -> RECONCILING -> RETIRED_FAILED, return UNKNOWN_EFFECT,
        revoke the lease, and perform exactly 1 physical attempt (no blind retries).
        """
        # Hanging adapter simulates 1s delay with 50ms kernel timeout
        hanging_adapter = MockActionAdapter(delay_ms=1000.0)

        kernel = HostControlKernel(
            policy=self.policy,
            action_port=hanging_adapter,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.registry,
            dispatch_timeout_s=0.05,  # 50ms fast timeout
            settle_interval_s=0.0,
        )

        proposal = self._create_proposal(step_index=1)
        result = await kernel.submit_proposal(proposal)

        # 1. Assert result properties
        self.assertEqual(result.outcome, OutcomeClass.UNKNOWN_EFFECT)
        self.assertFalse(result.verification_passed)
        self.assertTrue(result.requires_reconciliation)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)
        self.assertIn("timed out", result.error_message or "")

        # 2. Assert exactly 1 physical attempt occurred (NO blind retries)
        self.assertEqual(hanging_adapter.dispatch_count, 1)

        # 3. Assert active lease was revoked
        lease = self.lease_manager.get_lease_by_action_id(proposal.identity.action_id)
        self.assertIsNotNone(lease)
        self.assertEqual(
            self.lease_manager.get_lease_status(lease.lease_id),
            LeaseStatus.REVOKED,
        )

        # 4. Assert state transitions traversed RECONCILING
        history_states = [t[1] for t in kernel.state_history]
        self.assertIn(DispatchState.IN_FLIGHT, history_states)
        self.assertIn(DispatchState.RECONCILING, history_states)
        self.assertIn(DispatchState.RETIRED_FAILED, history_states)
        self.assertEqual(kernel.current_state, DispatchState.IDLE)

    async def test_post_timeout_retry_with_same_action_identity_blocked(self):
        """Resubmitting a timed-out proposal with the same ActionIdentity is strictly rejected by IdempotencyRegistry."""
        hanging_adapter = MockActionAdapter(delay_ms=1000.0)

        kernel = HostControlKernel(
            policy=self.policy,
            action_port=hanging_adapter,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.registry,
            dispatch_timeout_s=0.05,
            settle_interval_s=0.0,
        )

        proposal = self._create_proposal(step_index=1)
        await kernel.submit_proposal(proposal)

        # Subsequent submission with same ActionIdentity must be blocked by idempotency ledger
        with self.assertRaises(IdempotencyCollisionError):
            await kernel.submit_proposal(proposal)

        self.assertEqual(hanging_adapter.dispatch_count, 1, "No retry allowed with same action identity")

    async def test_settlement_timeout_transitions_to_reconciling_unknown_effect(self):
        """When settlement quiet period fails or times out, transitions to RECONCILING with UNKNOWN_EFFECT."""
        adapter = MockActionAdapter()
        kernel = HostControlKernel(
            policy=self.policy,
            action_port=adapter,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.registry,
            settle_interval_s=0.0,
        )

        # Force settlement to return False (timeout condition)
        async def mock_failed_settlement():
            return False

        kernel._await_settlement = mock_failed_settlement  # type: ignore

        proposal = self._create_proposal(step_index=1)
        result = await kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.UNKNOWN_EFFECT)
        self.assertTrue(result.requires_reconciliation)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)
        self.assertIn("Settlement timeout", result.error_message or "")

        history_states = [t[1] for t in kernel.state_history]
        self.assertIn(DispatchState.SETTLING, history_states)
        self.assertIn(DispatchState.RECONCILING, history_states)
        self.assertIn(DispatchState.RETIRED_FAILED, history_states)

    async def test_adapter_transport_crash_transitions_to_reconciling_unknown_effect(self):
        """Adapter raising unhandled transport exception transitions through RECONCILING, revokes lease, and marks UNKNOWN_EFFECT."""
        crashing_adapter = MockActionAdapter(
            fail_with=ConnectionResetError("CDP WebSocket disconnected unexpectedly")
        )

        kernel = HostControlKernel(
            policy=self.policy,
            action_port=crashing_adapter,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.registry,
            settle_interval_s=0.0,
        )

        proposal = self._create_proposal(step_index=1)
        result = await kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.UNKNOWN_EFFECT)
        self.assertTrue(result.requires_reconciliation)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)
        self.assertIn("CDP WebSocket disconnected", result.error_message or "")
        self.assertEqual(crashing_adapter.dispatch_count, 1)

        lease = self.lease_manager.get_lease_by_action_id(proposal.identity.action_id)
        self.assertIsNotNone(lease)
        self.assertEqual(self.lease_manager.get_lease_status(lease.lease_id), LeaseStatus.REVOKED)

    async def test_verification_failure_transitions_to_reconciling(self):
        """Verification failure (e.g. MODAL_APPEARED) transitions through RECONCILING and sets requires_reconciliation=True."""
        adapter = MockActionAdapter()
        verifier = MockVerificationPort(outcome=OutcomeClass.MODAL_APPEARED)

        kernel = HostControlKernel(
            policy=self.policy,
            action_port=adapter,
            verification_port=verifier,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.registry,
            settle_interval_s=0.0,
        )

        proposal = self._create_proposal(step_index=1)
        result = await kernel.submit_proposal(proposal)

        self.assertEqual(result.outcome, OutcomeClass.MODAL_APPEARED)
        self.assertFalse(result.verification_passed)
        self.assertTrue(result.requires_reconciliation)
        self.assertEqual(result.state, DispatchState.RETIRED_FAILED)

        history_states = [t[1] for t in kernel.state_history]
        self.assertIn(DispatchState.VERIFYING, history_states)
        self.assertIn(DispatchState.RECONCILING, history_states)
        self.assertIn(DispatchState.RETIRED_FAILED, history_states)


class TestEmergencyHaltAndRevocationInvariants(unittest.IsolatedAsyncioTestCase):
    """Invariant 7: Emergency halt immediately revokes all active leases and halts all host execution.
    
    Emergency halt must execute within < 5ms, revoke all active leases across the system,
    cancel any in-flight task, and reject all subsequent action proposals.
    """

    def setUp(self):
        self.clock = SystemClock()
        self.policy = CapabilityPolicy.permissive_policy()
        self.adapter = MockActionAdapter(delay_ms=50.0)
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.registry = IdempotencyRegistry(clock=self.clock)

        self.kernel = HostControlKernel(
            policy=self.policy,
            action_port=self.adapter,
            clock=self.clock,
            lease_manager=self.lease_manager,
            idempotency_registry=self.registry,
            settle_interval_s=0.0,
        )

    def _create_proposal(self, step_index: int = 1) -> ActionProposal:
        identity = ActionIdentity.create(session_id="sess_halt", step_index=step_index)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="#btn")
        return ActionProposal(identity=identity, action=action)

    def test_emergency_halt_immediate_latency_and_halt_state(self):
        """Calling emergency_halt takes < 5ms and sets is_halted to True."""
        start_perf = time.perf_counter()
        self.kernel.emergency_halt("Operator killswitch pressed")
        elapsed_ms = (time.perf_counter() - start_perf) * 1000.0

        self.assertLess(elapsed_ms, 5.0, f"Emergency halt latency {elapsed_ms:.2f}ms exceeds 5ms ceiling")
        self.assertTrue(self.kernel.is_halted)
        self.assertEqual(self.kernel.halt_reason, "Operator killswitch pressed")

    def test_emergency_halt_revokes_all_active_leases(self):
        """Calling emergency_halt revokes every single issued lease in the lease manager."""
        action = TypedAction(action_type=ActionType.CLICK)
        id1 = ActionIdentity.create("sess_halt_1", 1)
        id2 = ActionIdentity.create("sess_halt_2", 1)
        id3 = ActionIdentity.create("sess_halt_3", 1)

        l1 = self.lease_manager.issue_lease(id1, action)
        l2 = self.lease_manager.issue_lease(id2, action)
        l3 = self.lease_manager.issue_lease(id3, action)

        self.assertEqual(self.lease_manager.active_lease_count(), 3)

        self.kernel.emergency_halt("Mass revocation trigger")

        self.assertEqual(self.lease_manager.active_lease_count(), 0)
        self.assertEqual(self.lease_manager.get_lease_status(l1.lease_id), LeaseStatus.REVOKED)
        self.assertEqual(self.lease_manager.get_lease_status(l2.lease_id), LeaseStatus.REVOKED)
        self.assertEqual(self.lease_manager.get_lease_status(l3.lease_id), LeaseStatus.REVOKED)

    async def test_emergency_halt_rejects_subsequent_proposals_immediately(self):
        """Proposals submitted while kernel is halted immediately raise EmergencyHaltError."""
        self.kernel.emergency_halt("Security breach containment")

        proposal = self._create_proposal(step_index=1)
        with self.assertRaises(EmergencyHaltError) as ctx:
            await self.kernel.submit_proposal(proposal)

        self.assertIn("Security breach containment", str(ctx.exception))
        self.assertEqual(self.adapter.dispatch_count, 0)

    async def test_revoked_leases_cannot_be_executed_by_adapters_post_halt(self):
        """Adapters fail closed when attempting to execute any lease revoked during emergency halt."""
        page = FakeBrowserPage()
        cdp_adapter = CDPActionAdapter(page=page, lease_manager=self.lease_manager)

        action = TypedAction(action_type=ActionType.CLICK)
        identity = ActionIdentity.create("sess_halt", 1)
        lease = self.lease_manager.issue_lease(identity, action)

        # Emergency halt revokes the lease
        self.kernel.emergency_halt("Containment halt")

        with self.assertRaises(InvalidLeaseError) as ctx:
            await cdp_adapter.execute_action(action=action, lease=lease)

        self.assertIn("revoked", str(ctx.exception).lower())
        self.assertEqual(len(page.event_log), 0)

    async def test_resume_re_enables_execution_cleanly(self):
        """Calling resume() clears halt condition and restores operational readiness."""
        self.kernel.emergency_halt("Temporary pause")
        self.assertTrue(self.kernel.is_halted)

        # Proposal fails when halted
        p1 = self._create_proposal(step_index=1)
        with self.assertRaises(EmergencyHaltError):
            await self.kernel.submit_proposal(p1)

        # Resume execution
        self.kernel.resume()
        self.assertFalse(self.kernel.is_halted)
        self.assertEqual(self.kernel.current_state, DispatchState.IDLE)

        # Subsequent proposal now succeeds cleanly
        p2 = self._create_proposal(step_index=2)
        res = await self.kernel.submit_proposal(p2)
        self.assertEqual(res.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.adapter.dispatch_count, 1)


if __name__ == "__main__":
    unittest.main()
