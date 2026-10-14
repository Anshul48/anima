from __future__ import annotations
import asyncio
import time
import unittest
from typing import Any, Dict, List, Optional

from reflex.host.identity import (
    ActionExecutionLockedError,
    ActionLease,
    ActionLeaseManager,
    IdempotencyCollisionError,
    IdempotencyRegistry,
    LeaseAlreadyAcquiredError,
    NonMonotonicStepError,
)
from reflex.host.kernel import (
    DispatchState,
    HostControlKernel,
    KernelDispatchResult,
)
from reflex.ports.action import ActionPort
from reflex.ports.clock import DeterministicClock, SystemClock
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityPolicy, CapabilityScope


class CountingMockAdapter(ActionPort):
    """Mock action adapter recording physical dispatch invocations."""

    def __init__(self, delay_ms: float = 5.0):
        self.delay_ms = delay_ms
        self.dispatch_count = 0
        self.dispatched_action_ids: List[str] = []
        self._lock = asyncio.Lock()
        self.adapter_name = "counting_mock_adapter"

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        async with self._lock:
            self.dispatch_count += 1
            self.dispatched_action_ids.append(identity.action_id)

        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)

        return {"dispatched": True, "action_id": identity.action_id}


class TestIdempotencyConcurrency(unittest.IsolatedAsyncioTestCase):
    """Stress testing suite verifying atomic CAS locks, single-dispatch guarantees, and monotonic ordering."""

    def setUp(self):
        self.clock = SystemClock()
        self.policy = CapabilityPolicy.permissive_policy()
        self.adapter = CountingMockAdapter(delay_ms=2.0)
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
        session_id: str = "stress_session_001",
        step_index: int = 1,
    ) -> ActionProposal:
        identity = ActionIdentity.create(session_id=session_id, step_index=step_index)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_concurrent")
        return ActionProposal(
            identity=identity,
            action=action,
            required_scopes={CapabilityScope.BROWSER_INTERACT},
        )

    async def test_100_concurrent_dispatch_attempts_same_proposal(self):
        """Stress test: 100 concurrent async tasks attempting to dispatch the exact same proposal.
        
        Invariant: Exactly 1 attempt succeeds and physically executes against adapter; 99 are rejected.
        """
        proposal = self._create_proposal(step_index=1)
        num_tasks = 100

        async def worker():
            return await self.kernel.submit_proposal(proposal)

        # Launch 100 simultaneous tasks
        tasks = [asyncio.create_task(worker()) for _ in range(num_tasks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes: List[KernelDispatchResult] = []
        collisions: List[Exception] = []
        other_exceptions: List[Exception] = []

        for r in results:
            if isinstance(r, KernelDispatchResult):
                if r.outcome == OutcomeClass.SUCCESS:
                    successes.append(r)
            elif isinstance(r, (IdempotencyCollisionError, LeaseAlreadyAcquiredError, ActionExecutionLockedError)):
                collisions.append(r)
            else:
                other_exceptions.append(r)

        # Invariant Assertions
        self.assertEqual(len(other_exceptions), 0, f"Unexpected exceptions encountered: {other_exceptions}")
        self.assertEqual(len(successes), 1, f"Expected exactly 1 successful dispatch, got {len(successes)}")
        self.assertEqual(len(collisions), 99, f"Expected exactly 99 rejected collisions, got {len(collisions)}")
        self.assertEqual(self.adapter.dispatch_count, 1, "Adapter must have received at-most-one physical dispatch")
        self.assertEqual(self.adapter.dispatched_action_ids, [proposal.identity.action_id])

    async def test_concurrent_lease_acquisition_single_use(self):
        """Stress test: 100 concurrent tasks attempting to acquire the same ActionLease."""
        identity = ActionIdentity.create(session_id="sess_lease", step_index=1)
        action = TypedAction(action_type=ActionType.CLICK)
        lease = self.lease_manager.issue_lease(identity, action, ttl_ms=10000.0)

        async def acquire_worker():
            # Run in executor or async task to test concurrent acquisition
            return self.lease_manager.acquire_lease(lease.lease_id)

        tasks = [asyncio.create_task(acquire_worker()) for _ in range(100)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        acquired = [r for r in results if isinstance(r, ActionLease)]
        rejected = [r for r in results if isinstance(r, LeaseAlreadyAcquiredError)]

        self.assertEqual(len(acquired), 1, "Lease must only be acquired once (single-use authority)")
        self.assertEqual(len(rejected), 99, "99 lease acquisition attempts must be rejected")

    async def test_concurrent_atomic_begin_dispatch_registry(self):
        """Stress test: 100 concurrent tasks calling atomic_begin_dispatch on the registry."""
        identity = ActionIdentity.create(session_id="sess_reg", step_index=1)
        self.registry.register_proposal(identity)

        async def begin_worker():
            return self.registry.atomic_begin_dispatch(identity.action_id)

        tasks = [asyncio.create_task(begin_worker()) for _ in range(100)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = [r for r in results if r is True]
        locked_errors = [r for r in results if isinstance(r, ActionExecutionLockedError)]

        self.assertEqual(len(successes), 1, "Registry must only allow at-most-one begin_dispatch")
        self.assertEqual(len(locked_errors), 99, "99 begin_dispatch attempts must raise ActionExecutionLockedError")
        self.assertEqual(self.registry.get_dispatch_count(identity.action_id), 1)

    async def test_monotonic_step_index_enforcement(self):
        """Verify strict monotonic step index ordering per session."""
        session_id = "monotonic_sess_001"

        # Step 1: Valid
        p1 = self._create_proposal(session_id=session_id, step_index=1)
        res1 = await self.kernel.submit_proposal(p1)
        self.assertEqual(res1.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.registry.get_last_step_index(session_id), 1)

        # Step 1 again: Fails with IdempotencyCollisionError or NonMonotonicStepError
        p1_dup = self._create_proposal(session_id=session_id, step_index=1)
        with self.assertRaises(NonMonotonicStepError):
            await self.kernel.submit_proposal(p1_dup)

        # Step 0 (regressive step index): Fails with NonMonotonicStepError
        p0 = self._create_proposal(session_id=session_id, step_index=0)
        with self.assertRaises(NonMonotonicStepError):
            await self.kernel.submit_proposal(p0)

        # Step 2: Valid progression
        p2 = self._create_proposal(session_id=session_id, step_index=2)
        res2 = await self.kernel.submit_proposal(p2)
        self.assertEqual(res2.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.registry.get_last_step_index(session_id), 2)

        # Step 5: Valid forward progression
        p5 = self._create_proposal(session_id=session_id, step_index=5)
        res5 = await self.kernel.submit_proposal(p5)
        self.assertEqual(res5.outcome, OutcomeClass.SUCCESS)
        self.assertEqual(self.registry.get_last_step_index(session_id), 5)

        # Step 4 (backward progression): Fails
        p4 = self._create_proposal(session_id=session_id, step_index=4)
        with self.assertRaises(NonMonotonicStepError):
            await self.kernel.submit_proposal(p4)

    async def test_idempotency_key_collision_different_action_id(self):
        """Verify that reusing the same idempotency token raises IdempotencyCollisionError even if action_id differs."""
        fixed_idempotency_key = "abc123fixedtoken456"

        id1 = ActionIdentity(
            action_id="act_unique_1",
            session_id="sess_dup_key",
            step_index=1,
            idempotency_key=fixed_idempotency_key,
            created_at_ms=1000.0,
        )
        prop1 = ActionProposal(identity=id1, action=TypedAction(action_type=ActionType.CLICK))
        res1 = await self.kernel.submit_proposal(prop1)
        self.assertEqual(res1.outcome, OutcomeClass.SUCCESS)

        id2 = ActionIdentity(
            action_id="act_unique_2",
            session_id="sess_dup_key",
            step_index=2,
            idempotency_key=fixed_idempotency_key,  # Duplicate key!
            created_at_ms=2000.0,
        )
        prop2 = ActionProposal(identity=id2, action=TypedAction(action_type=ActionType.CLICK))

        with self.assertRaises(IdempotencyCollisionError):
            await self.kernel.submit_proposal(prop2)

    async def test_sessions_are_isolated(self):
        """Verify independent monotonic step tracking per session."""
        sess_a = "session_A"
        sess_b = "session_B"

        # Session A step 10
        pa10 = self._create_proposal(session_id=sess_a, step_index=10)
        res_a = await self.kernel.submit_proposal(pa10)
        self.assertEqual(res_a.outcome, OutcomeClass.SUCCESS)

        # Session B step 1 (independent from Session A)
        pb1 = self._create_proposal(session_id=sess_b, step_index=1)
        res_b = await self.kernel.submit_proposal(pb1)
        self.assertEqual(res_b.outcome, OutcomeClass.SUCCESS)

        self.assertEqual(self.registry.get_last_step_index(sess_a), 10)
        self.assertEqual(self.registry.get_last_step_index(sess_b), 1)


if __name__ == "__main__":
    unittest.main()
