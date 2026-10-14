"""Unit and integration tests for native OS execution adapters (Windows, macOS, Linux)."""

from __future__ import annotations

import asyncio
import time
import unittest

from reflex.execution.native.base import (
    NativeActionConfig,
    NativeActionPort,
)
from reflex.execution.native.linux_input import (
    LinuxNativeInputAdapter,
    MockLinuxInputSubstrate,
)
from reflex.execution.native.macos_input import (
    MacOSNativeInputAdapter,
    MockMacOSInputSubstrate,
)
from reflex.execution.native.windows_input import (
    MockWindowsInputSubstrate,
    WindowsNativeInputAdapter,
)
from reflex.host.identity.lease_manager import (
    ActionLease,
    ActionLeaseManager,
    InvalidLeaseError,
)
from reflex.ports.action import ActionReceipt, ActionStatus
from reflex.ports.clock import DeterministicClock
from reflex.schemas.actions import ActionType, NormalizedCoords, TypedAction
from reflex.schemas.identity import ActionIdentity


class TestWindowsNativeExecution(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=10000.0)
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.config = NativeActionConfig(screen_width=1920, screen_height=1080)
        self.substrate = MockWindowsInputSubstrate()
        self.adapter = WindowsNativeInputAdapter(
            config=self.config,
            clock=self.clock,
            lease_manager=self.lease_manager,
            substrate=self.substrate,
        )

    def _create_lease(self, action: TypedAction, ttl_ms: float = 5000.0) -> ActionLease:
        ident = ActionIdentity.create("sess_win", step_index=1, created_at_ms=self.clock.now_ms())
        return self.lease_manager.issue_lease(ident, action, ttl_ms=ttl_ms)

    def test_mouse_clicks_and_coords(self):
        async def run():
            action = TypedAction(
                action_type=ActionType.CLICK,
                coords=NormalizedCoords(0.5, 0.25),
            )
            lease = self._create_lease(action)
            receipt = await self.adapter.execute_action(action, lease)
            self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
            self.assertEqual(self.substrate.mouse_position, (960, 270))
            self.assertEqual(len(self.substrate.events), 2)  # move + click

            # Double click
            action_dbl = TypedAction(
                action_type=ActionType.DOUBLE_CLICK,
                coords=NormalizedCoords(0.1, 0.1),
            )
            lease_dbl = self._create_lease(action_dbl)
            receipt_dbl = await self.adapter.execute_action(action_dbl, lease_dbl)
            self.assertEqual(receipt_dbl.status, ActionStatus.DISPATCHED)
            self.assertEqual(self.substrate.mouse_position, (192, 108))

            # Right click
            action_rc = TypedAction(
                action_type=ActionType.RIGHT_CLICK,
                coords=NormalizedCoords(0.2, 0.3),
            )
            lease_rc = self._create_lease(action_rc)
            receipt_rc = await self.adapter.execute_action(action_rc, lease_rc)
            self.assertEqual(receipt_rc.status, ActionStatus.DISPATCHED)

        asyncio.run(run())

    def test_direct_uia_pattern_invocation(self):
        async def run():
            # InvokePattern via target_node_id without coords
            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_calculator_equals",
            )
            lease = self._create_lease(action)
            receipt = await self.adapter.execute_action(action, lease)
            self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
            self.assertEqual(len(self.substrate.pattern_invocations), 1)
            self.assertEqual(self.substrate.pattern_invocations[0]["node_id"], "btn_calculator_equals")
            self.assertEqual(self.substrate.pattern_invocations[0]["pattern"], "InvokePattern.Invoke")

            # ValuePattern via target_node_id
            action_val = TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="txt_search_box",
                text_payload="Reflex Native Engine",
            )
            lease_val = self._create_lease(action_val)
            receipt_val = await self.adapter.execute_action(action_val, lease_val)
            self.assertEqual(receipt_val.status, ActionStatus.DISPATCHED)
            self.assertEqual(len(self.substrate.pattern_invocations), 2)
            self.assertEqual(self.substrate.pattern_invocations[1]["pattern"], "ValuePattern.SetValue")
            self.assertEqual(self.substrate.pattern_invocations[1]["value"], "Reflex Native Engine")

        asyncio.run(run())

    def test_typing_and_hotkeys(self):
        async def run():
            action_type = TypedAction(
                action_type=ActionType.TYPE,
                text_payload="Hello Windows!",
                coords=NormalizedCoords(0.1, 0.1),
            )
            lease_type = self._create_lease(action_type)
            receipt_type = await self.adapter.execute_action(action_type, lease_type)
            self.assertEqual(receipt_type.status, ActionStatus.DISPATCHED)
            self.assertIn({"type": "type_text", "text": "Hello Windows!"}, self.substrate.events)

            # Key combo
            action_combo = TypedAction(
                action_type=ActionType.KEY_COMBINATION,
                key_code="Control+Alt+Delete",
            )
            lease_combo = self._create_lease(action_combo)
            receipt_combo = await self.adapter.execute_action(action_combo, lease_combo)
            self.assertEqual(receipt_combo.status, ActionStatus.DISPATCHED)
            self.assertIn("Control+Alt+Delete", self.substrate.pressed_keys)

        asyncio.run(run())

    def test_drag_and_drop_interpolation(self):
        async def run():
            action_drag = TypedAction(
                action_type=ActionType.DRAG_AND_DROP,
                coords=NormalizedCoords(0.1, 0.1),
                metadata={"target_coords": {"x": 0.5, "y": 0.5}},
            )
            lease_drag = self._create_lease(action_drag)
            receipt = await self.adapter.execute_action(action_drag, lease_drag)
            self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
            self.assertEqual(receipt.raw_adapter_response["steps"], 10)
            self.assertEqual(self.substrate.mouse_position, (960, 540))

        asyncio.run(run())


class TestMacOSNativeExecution(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=20000.0)
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.substrate = MockMacOSInputSubstrate()
        self.adapter = MacOSNativeInputAdapter(
            clock=self.clock,
            lease_manager=self.lease_manager,
            substrate=self.substrate,
        )

    def _create_lease(self, action: TypedAction) -> ActionLease:
        ident = ActionIdentity.create("sess_mac", step_index=1, created_at_ms=self.clock.now_ms())
        return self.lease_manager.issue_lease(ident, action)

    def test_ax_press_background_trigger(self):
        async def run():
            # AXPress background action does not teleport cursor
            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="ax_finder_sidebar_documents",
            )
            lease = self._create_lease(action)
            receipt = await self.adapter.execute_action(action, lease)
            self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
            self.assertEqual(len(self.substrate.ax_press_invocations), 1)
            self.assertEqual(self.substrate.ax_press_invocations[0]["node_id"], "ax_finder_sidebar_documents")
            self.assertEqual(self.substrate.mouse_position, (0, 0))  # Unmoved cursor!

        asyncio.run(run())

    def test_cgevent_synthetic_inputs(self):
        async def run():
            # Click
            action_click = TypedAction(
                action_type=ActionType.CLICK,
                coords=NormalizedCoords(0.3, 0.4),
            )
            lease_click = self._create_lease(action_click)
            receipt = await self.adapter.execute_action(action_click, lease_click)
            self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
            self.assertEqual(self.substrate.mouse_position, (576, 432))

            # Hotkey
            action_hotkey = TypedAction(
                action_type=ActionType.KEY_COMBINATION,
                key_code="Command+Shift+4",
            )
            lease_hotkey = self._create_lease(action_hotkey)
            receipt_hotkey = await self.adapter.execute_action(action_hotkey, lease_hotkey)
            self.assertEqual(receipt_hotkey.status, ActionStatus.DISPATCHED)
            self.assertIn("Command+Shift+4", self.substrate.pressed_keys)

        asyncio.run(run())


class TestLinuxNativeExecution(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=30000.0)
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.substrate = MockLinuxInputSubstrate()
        self.adapter = LinuxNativeInputAdapter(
            clock=self.clock,
            lease_manager=self.lease_manager,
            substrate=self.substrate,
        )

    def _create_lease(self, action: TypedAction) -> ActionLease:
        ident = ActionIdentity.create("sess_linux", step_index=1, created_at_ms=self.clock.now_ms())
        return self.lease_manager.issue_lease(ident, action)

    def test_atspi_direct_action(self):
        async def run():
            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="atspi_btn_apply",
            )
            lease = self._create_lease(action)
            receipt = await self.adapter.execute_action(action, lease)
            self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
            self.assertEqual(len(self.substrate.atspi_actions), 1)
            self.assertEqual(self.substrate.atspi_actions[0]["node_id"], "atspi_btn_apply")

        asyncio.run(run())

    def test_xtest_synthetic_inputs(self):
        async def run():
            action_click = TypedAction(
                action_type=ActionType.CLICK,
                coords=NormalizedCoords(0.25, 0.5),
            )
            lease_click = self._create_lease(action_click)
            receipt = await self.adapter.execute_action(action_click, lease_click)
            self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
            self.assertEqual(self.substrate.mouse_position, (480, 540))

            # Drag and drop
            action_drag = TypedAction(
                action_type=ActionType.DRAG_AND_DROP,
                coords=NormalizedCoords(0.1, 0.1),
                metadata={"target_coords": {"x": 0.8, "y": 0.8}},
            )
            lease_drag = self._create_lease(action_drag)
            receipt_drag = await self.adapter.execute_action(action_drag, lease_drag)
            self.assertEqual(receipt_drag.status, ActionStatus.DISPATCHED)
            self.assertEqual(self.substrate.mouse_position, (1536, 864))

        asyncio.run(run())


class TestStrictLeaseValidation(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=40000.0)
        self.lease_manager = ActionLeaseManager(clock=self.clock)
        self.substrate = MockWindowsInputSubstrate()
        self.adapter = WindowsNativeInputAdapter(
            clock=self.clock,
            lease_manager=self.lease_manager,
            substrate=self.substrate,
        )

    def test_missing_lease_raises(self):
        async def run():
            action = TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(0.1, 0.1))
            with self.assertRaises(InvalidLeaseError):
                await self.adapter.execute_action(action, None)  # type: ignore

        asyncio.run(run())

    def test_expired_lease_raises(self):
        async def run():
            action = TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(0.1, 0.1))
            ident = ActionIdentity.create("sess_exp", step_index=1, created_at_ms=self.clock.now_ms())
            lease = self.lease_manager.issue_lease(ident, action, ttl_ms=100.0)

            # Advance clock past TTL
            self.clock.advance(200.0)
            with self.assertRaises(InvalidLeaseError):
                await self.adapter.execute_action(action, lease)

        asyncio.run(run())

    def test_single_use_consumption_enforced(self):
        async def run():
            action = TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(0.1, 0.1))
            ident = ActionIdentity.create("sess_single", step_index=1, created_at_ms=self.clock.now_ms())
            lease = self.lease_manager.issue_lease(ident, action)

            # First execution succeeds
            receipt1 = await self.adapter.execute_action(action, lease)
            self.assertEqual(receipt1.status, ActionStatus.DISPATCHED)

            # Second execution with same lease MUST raise InvalidLeaseError
            with self.assertRaises(InvalidLeaseError):
                await self.adapter.execute_action(action, lease)

        asyncio.run(run())

    def test_action_type_mismatch_raises(self):
        async def run():
            action_lease = TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(0.1, 0.1))
            action_exec = TypedAction(action_type=ActionType.TYPE, text_payload="Malicious Type Switch")
            ident = ActionIdentity.create("sess_mismatch", step_index=1, created_at_ms=self.clock.now_ms())
            lease = self.lease_manager.issue_lease(ident, action_lease)

            with self.assertRaises(InvalidLeaseError):
                await self.adapter.execute_action(action_exec, lease)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
