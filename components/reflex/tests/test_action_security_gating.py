from __future__ import annotations
import asyncio
import time
import unittest

from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.execution.input.synthetic_input_adapter import SyntheticInputAdapter
from reflex.execution.router import ExecutionRouter
from reflex.host.identity.lease_manager import ActionLease, ActionLeaseManager, InvalidLeaseError
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.ports.action import ActionReceipt, ActionStatus
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.identity import ActionIdentity


class TestActionSecurityGating(unittest.IsolatedAsyncioTestCase):
    """Test suite for host-local action authority, cryptographic lease validation, and fail-closed execution gating."""

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

    def _create_action(self, action_type: ActionType = ActionType.CLICK, target: str = "#btn") -> TypedAction:
        return TypedAction(
            action_type=action_type,
            target_node_id=target,
            coords=NormalizedCoords(0.5, 0.5),
            safety_class=SafetyClass.REVERSIBLE,
        )

    def _create_lease(self, action: TypedAction, ttl_ms: float = 5000.0, offset_ms: float = 0.0) -> ActionLease:
        identity = ActionIdentity.create(session_id="sess_sec_test", step_index=1)
        now_ms = time.time() * 1000.0 + offset_ms
        return self.lease_manager.issue_lease(identity=identity, action=action, ttl_ms=ttl_ms, current_time_ms=now_ms)

    async def test_execution_without_lease_fails_closed(self):
        """Adapter and router must fail closed immediately when lease is None."""
        action = self._create_action()

        with self.assertRaises(InvalidLeaseError):
            await self.cdp_adapter.execute_action(action=action, lease=None)  # type: ignore

        with self.assertRaises(InvalidLeaseError):
            await self.synth_adapter.execute_action(action=action, lease=None)  # type: ignore

        with self.assertRaises(InvalidLeaseError):
            await self.router.execute_action(action=action, lease=None)  # type: ignore

        # Ensure zero events were dispatched
        self.assertEqual(len(self.page.event_log), 0)

    async def test_expired_lease_rejected(self):
        """Attempting dispatch with an expired ActionLease raises InvalidLeaseError."""
        action = self._create_action()
        # Create a lease that expired 10 seconds ago
        expired_lease = self._create_lease(action, ttl_ms=1000.0, offset_ms=-20000.0)

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.cdp_adapter.execute_action(action=action, lease=expired_lease)
        self.assertIn("expired", str(ctx.exception).lower())

        with self.assertRaises(InvalidLeaseError):
            await self.synth_adapter.execute_action(action=action, lease=expired_lease)

        # Ensure zero events dispatched
        self.assertEqual(len(self.page.event_log), 0)

    async def test_single_use_lease_reentry_rejected(self):
        """A lease cannot be dispatched twice (single-use enforcement)."""
        action = self._create_action()
        lease = self._create_lease(action)

        # First dispatch should succeed
        receipt = await self.cdp_adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.lease_id, lease.lease_id)

        # Second dispatch with identical lease must fail closed
        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.cdp_adapter.execute_action(action=action, lease=lease)
        self.assertIn("already been consumed", str(ctx.exception).lower())

    async def test_tampered_lease_signature_rejected(self):
        """Tampered cryptographic token in ActionLease raises InvalidLeaseError."""
        action = self._create_action()
        valid_lease = self._create_lease(action)

        tampered_lease = ActionLease(
            lease_id=valid_lease.lease_id,
            identity=valid_lease.identity,
            action=valid_lease.action,
            expires_at_ms=valid_lease.expires_at_ms,
            token="tampered_forged_cryptographic_token",
            created_at_ms=valid_lease.created_at_ms,
        )

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.cdp_adapter.execute_action(action=action, lease=tampered_lease)
        self.assertTrue(str(ctx.exception).strip())

    async def test_mismatched_action_type_rejected(self):
        """Action type mismatch between lease and executed action raises InvalidLeaseError."""
        action_click = self._create_action(action_type=ActionType.CLICK)
        lease_click = self._create_lease(action_click)

        action_type = TypedAction(action_type=ActionType.TYPE, text_payload="Malicious Injection")

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.cdp_adapter.execute_action(action=action_type, lease=lease_click)
        self.assertTrue(str(ctx.exception).strip())

    async def test_revoked_lease_rejected(self):
        """Revoked lease cannot be executed."""
        action = self._create_action()
        lease = self._create_lease(action)
        self.lease_manager.revoke_lease(lease.lease_id)

        with self.assertRaises(InvalidLeaseError) as ctx:
            await self.cdp_adapter.execute_action(action=action, lease=lease)
        self.assertIn("revoked", str(ctx.exception).lower())

    def test_execution_router_modality_selection(self):
        """ExecutionRouter accurately selects between CDP direct DOM and synthetic physical adapters."""
        # 1. Action with DOM target_node_id -> CDP
        act_dom = TypedAction(action_type=ActionType.CLICK, target_node_id="#btn")
        self.assertIs(self.router.select_adapter(act_dom), self.cdp_adapter)

        # 2. Action with coords and is_canvas -> Synthetic
        act_canvas = TypedAction(
            action_type=ActionType.CLICK,
            coords=NormalizedCoords(0.5, 0.5),
            metadata={"is_canvas": True},
        )
        self.assertIs(self.router.select_adapter(act_canvas), self.synth_adapter)

        # 3. Action with coords and no target_node_id -> Synthetic
        act_coords = TypedAction(
            action_type=ActionType.CLICK,
            coords=NormalizedCoords(0.2, 0.3),
        )
        self.assertIs(self.router.select_adapter(act_coords), self.synth_adapter)

        # 4. Explicit force_synthetic override -> Synthetic
        act_force_synth = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="#btn",
            metadata={"force_synthetic": True},
        )
        self.assertIs(self.router.select_adapter(act_force_synth), self.synth_adapter)

        # 5. Explicit force_direct override -> CDP
        act_force_direct = TypedAction(
            action_type=ActionType.CLICK,
            coords=NormalizedCoords(0.5, 0.5),
            metadata={"force_direct": True},
        )
        self.assertIs(self.router.select_adapter(act_force_direct), self.cdp_adapter)

        # 6. Global page actions (NAVIGATE) -> CDP
        act_nav = TypedAction(action_type=ActionType.NAVIGATE, text_payload="https://example.com")
        self.assertIs(self.router.select_adapter(act_nav), self.cdp_adapter)

    async def test_router_execution_end_to_end(self):
        """Router executes action via selected adapter under valid lease."""
        action = TypedAction(
            action_type=ActionType.CLICK,
            coords=NormalizedCoords(0.5, 0.5),
            metadata={"is_canvas": True},
        )
        lease = self._create_lease(action)

        receipt = await self.router.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.adapter_name, "SyntheticInputAdapter")
    async def test_concurrent_lease_dispatch_single_execution_guarantee(self):
        """Under concurrent execution attempts with the same lease, exactly 1 succeeds and all others fail closed."""
        action = self._create_action()
        lease = self._create_lease(action)

        success_count = 0
        failure_count = 0

        async def attempt_dispatch():
            nonlocal success_count, failure_count
            try:
                receipt = await self.cdp_adapter.execute_action(action=action, lease=lease)
                if receipt.status == ActionStatus.DISPATCHED:
                    success_count += 1
            except InvalidLeaseError:
                failure_count += 1

        # Spawn 50 simultaneous dispatch attempts for the same lease
        await asyncio.gather(*[attempt_dispatch() for _ in range(50)])

        self.assertEqual(success_count, 1)
        self.assertEqual(failure_count, 49)


if __name__ == "__main__":
    unittest.main()

