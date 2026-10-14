"""Cross-platform factory, registry, and mock substrate integration tests."""

from __future__ import annotations

import asyncio
import sys
import unittest

from reflex.execution.native import (
    LinuxNativeInputAdapter,
    MacOSNativeInputAdapter,
    MockLinuxInputSubstrate,
    MockMacOSInputSubstrate,
    MockWindowsInputSubstrate,
    NativeActionConfig,
    NativeActionFactory,
    NativeActionPort,
    WindowsNativeInputAdapter,
)
from reflex.host.identity.lease_manager import ActionLeaseManager, InvalidLeaseError
from reflex.perception.native import (
    LinuxATSPIObservationAdapter,
    MacOSAXObservationAdapter,
    MockLinuxATSPISubstrate,
    MockMacOSAXSubstrate,
    MockWindowsUIASubstrate,
    NativeObservationConfig,
    NativeObservationFactory,
    NativeObservationPort,
    PlatformAdapterRegistry,
    WindowsUIAObservationAdapter,
)
from reflex.ports.action import ActionStatus
from reflex.ports.clock import DeterministicClock
from reflex.schemas.actions import ActionType, NormalizedCoords, TypedAction
from reflex.schemas.identity import ActionIdentity


class TestCrossPlatformFactories(unittest.TestCase):
    def test_observation_factory_autodetection(self):
        adapter = NativeObservationFactory.create()
        self.assertIsInstance(adapter, NativeObservationPort)
        if sys.platform == "win32":
            self.assertIsInstance(adapter, WindowsUIAObservationAdapter)
        elif sys.platform == "darwin":
            self.assertIsInstance(adapter, MacOSAXObservationAdapter)
        elif sys.platform.startswith("linux"):
            self.assertIsInstance(adapter, LinuxATSPIObservationAdapter)

    def test_observation_factory_explicit_overrides(self):
        win_adapter = NativeObservationFactory.create(os_name="windows")
        self.assertIsInstance(win_adapter, WindowsUIAObservationAdapter)

        mac_adapter = NativeObservationFactory.create(os_name="darwin")
        self.assertIsInstance(mac_adapter, MacOSAXObservationAdapter)

        linux_adapter = NativeObservationFactory.create(os_name="linux")
        self.assertIsInstance(linux_adapter, LinuxATSPIObservationAdapter)

        # PlatformAdapterRegistry alias test
        reg_adapter = PlatformAdapterRegistry.create(os_name="macos")
        self.assertIsInstance(reg_adapter, MacOSAXObservationAdapter)

    def test_action_factory_autodetection(self):
        adapter = NativeActionFactory.create()
        self.assertIsInstance(adapter, NativeActionPort)
        if sys.platform == "win32":
            self.assertIsInstance(adapter, WindowsNativeInputAdapter)
        elif sys.platform == "darwin":
            self.assertIsInstance(adapter, MacOSNativeInputAdapter)
        elif sys.platform.startswith("linux"):
            self.assertIsInstance(adapter, LinuxNativeInputAdapter)

    def test_action_factory_explicit_overrides(self):
        win_exec = NativeActionFactory.create(os_name="windows")
        self.assertIsInstance(win_exec, WindowsNativeInputAdapter)

        mac_exec = NativeActionFactory.create(os_name="darwin")
        self.assertIsInstance(mac_exec, MacOSNativeInputAdapter)

        linux_exec = NativeActionFactory.create(os_name="linux")
        self.assertIsInstance(linux_exec, LinuxNativeInputAdapter)

    def test_custom_substrate_injection_via_factory(self):
        custom_sub = MockWindowsUIASubstrate()
        custom_sub.add_window("Custom Tool", handle=8888, is_focused=True)
        adapter = NativeObservationFactory.create(os_name="win32", substrate=custom_sub)
        self.assertTrue(any("Custom Tool" in w for w in adapter.list_open_windows()))

        custom_act_sub = MockWindowsInputSubstrate()
        act_adapter = NativeActionFactory.create(os_name="win32", substrate=custom_act_sub)
        self.assertIs(act_adapter.substrate, custom_act_sub)  # type: ignore

    def test_custom_adapter_registration(self):
        class CustomTestObservationAdapter(NativeObservationPort):
            def capture_active_window(self):
                return None  # type: ignore

            def list_open_windows(self):
                return ["CustomOS Window"]

            def get_focused_window_title(self):
                return "CustomOS Window"

            def get_focused_element(self):
                return None

            async def capture_screenshot(self):
                return b"custom_os_bytes"

        NativeObservationFactory.register_adapter("custom_os", CustomTestObservationAdapter)
        adapter = NativeObservationFactory.create(os_name="custom_os")
        self.assertIsInstance(adapter, CustomTestObservationAdapter)
        self.assertEqual(adapter.list_open_windows(), ["CustomOS Window"])

    def test_dispatch_action_lifecycle_and_error_handling(self):
        async def run():
            clock = DeterministicClock(start_time_ms=50000.0)
            lease_mgr = ActionLeaseManager(clock=clock)
            substrate = MockLinuxInputSubstrate()
            adapter = LinuxNativeInputAdapter(clock=clock, lease_manager=lease_mgr, substrate=substrate)

            # Valid execution under an issued lease (adapter shares the issuing manager)
            action = TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(0.5, 0.5))
            ident = ActionIdentity.create("sess_dispatch", step_index=1, created_at_ms=50000.0)
            lease = lease_mgr.issue_lease(ident, action)
            res = await adapter.execute_action(action, lease)
            self.assertEqual(res.status, ActionStatus.DISPATCHED)
            self.assertEqual(substrate.mouse_position, (960, 540))

            # Leaseless port dispatch fails closed: the native port mints only an
            # unregistered synthetic lease, which the shared manager rejects.
            action_nl = TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(0.1, 0.1))
            ident_nl = ActionIdentity.create("sess_nolease", step_index=3, created_at_ms=50000.0)
            with self.assertRaises(InvalidLeaseError):
                await adapter.dispatch_action(action_nl, ident_nl)

            # Invalid coordinates error capture in receipt
            action_bad = TypedAction(action_type=ActionType.DOUBLE_CLICK, coords=None)
            ident_bad = ActionIdentity.create("sess_bad", step_index=2, created_at_ms=50000.0)
            lease_bad = lease_mgr.issue_lease(ident_bad, action_bad)
            res_bad = await adapter.execute_action(action_bad, lease_bad)
            self.assertEqual(res_bad.status, ActionStatus.FAILED)
            self.assertIsNotNone(res_bad.error)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
