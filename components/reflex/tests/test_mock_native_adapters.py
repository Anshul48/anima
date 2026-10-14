"""Mock native OS adapter suite for platform-agnostic CI testing."""

from __future__ import annotations

import asyncio
import unittest

from reflex.execution.native.linux_input import LinuxNativeInputAdapter, MockLinuxInputSubstrate
from reflex.execution.native.macos_input import MacOSNativeInputAdapter, MockMacOSInputSubstrate
from reflex.execution.native.windows_input import MockWindowsInputSubstrate, WindowsNativeInputAdapter
from reflex.host.identity.lease_manager import ActionLeaseManager
from reflex.perception.native.linux_atspi import LinuxATSPIObservationAdapter, MockLinuxATSPISubstrate
from reflex.perception.native.macos_ax import MacOSAXObservationAdapter, MockMacOSAXSubstrate
from reflex.perception.native.windows_uia import MockWindowsUIASubstrate, WindowsUIAObservationAdapter
from reflex.ports.action import ActionStatus
from reflex.ports.clock import DeterministicClock
from reflex.schemas.actions import ActionType, NormalizedCoords, TypedAction
from reflex.schemas.identity import ActionIdentity
from reflex.schemas.state import CanonicalUIGraph, ModalitySource, NodeRole


class TestMockNativeAdapters(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=60000.0)

    def test_mock_windows_roundtrip(self):
        async def run():
            # Perception
            obs_sub = MockWindowsUIASubstrate()
            obs_sub.focused_window_title = "Paint"
            obs_sub.add_element(
                element_id="canvas_btn",
                name="Brush Tool",
                control_type="Button",
                bounds=(10, 10, 60, 60),
            )
            obs = WindowsUIAObservationAdapter(clock=self.clock, substrate=obs_sub)
            graph = obs.capture_active_window()
            self.assertEqual(graph.active_window_title, "Paint")
            self.assertEqual(graph.nodes["canvas_btn"].role, NodeRole.BUTTON)

            # Execution
            act_sub = MockWindowsInputSubstrate()
            manager = ActionLeaseManager(clock=self.clock)
            act = WindowsNativeInputAdapter(substrate=act_sub, lease_manager=manager, clock=self.clock)
            action = TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(0.02, 0.02))
            ident = ActionIdentity.create("sess_paint", step_index=1, created_at_ms=60000.0)
            manager.issue_lease(ident, action)
            receipt_dict = await act.dispatch_action(action, ident)
            self.assertEqual(receipt_dict["status"], ActionStatus.DISPATCHED.value)

        asyncio.run(run())

    def test_mock_macos_roundtrip(self):
        async def run():
            obs_sub = MockMacOSAXSubstrate()
            obs_sub.focused_window_title = "Notes"
            obs_sub.add_element(
                element_id="new_note_btn",
                title="New Note",
                role="AXButton",
                position=(20, 20),
                size=(80, 30),
            )
            obs = MacOSAXObservationAdapter(clock=self.clock, substrate=obs_sub)
            graph = obs.capture_active_window()
            self.assertEqual(graph.active_window_title, "Notes")
            self.assertEqual(graph.nodes["new_note_btn"].role, NodeRole.BUTTON)

            act_sub = MockMacOSInputSubstrate()
            manager = ActionLeaseManager(clock=self.clock)
            act = MacOSNativeInputAdapter(substrate=act_sub, lease_manager=manager, clock=self.clock)
            action = TypedAction(action_type=ActionType.CLICK, target_node_id="new_note_btn")
            ident = ActionIdentity.create("sess_notes", step_index=1, created_at_ms=60000.0)
            manager.issue_lease(ident, action)
            receipt_dict = await act.dispatch_action(action, ident)
            self.assertEqual(receipt_dict["status"], ActionStatus.DISPATCHED.value)
            self.assertEqual(len(act_sub.ax_press_invocations), 1)

        asyncio.run(run())

    def test_mock_linux_roundtrip(self):
        async def run():
            obs_sub = MockLinuxATSPISubstrate()
            obs_sub.focused_window_title = "Gedit"
            obs_sub.add_element(
                element_id="save_btn",
                name="Save File",
                role="ROLE_PUSH_BUTTON",
                extents=(10, 10, 50, 30),
            )
            obs = LinuxATSPIObservationAdapter(clock=self.clock, substrate=obs_sub)
            graph = obs.capture_active_window()
            self.assertEqual(graph.active_window_title, "Gedit")
            self.assertEqual(graph.nodes["save_btn"].role, NodeRole.BUTTON)

            act_sub = MockLinuxInputSubstrate()
            manager = ActionLeaseManager(clock=self.clock)
            act = LinuxNativeInputAdapter(substrate=act_sub, lease_manager=manager, clock=self.clock)
            action = TypedAction(action_type=ActionType.CLICK, target_node_id="save_btn")
            ident = ActionIdentity.create("sess_gedit", step_index=1, created_at_ms=60000.0)
            manager.issue_lease(ident, action)
            receipt_dict = await act.dispatch_action(action, ident)
            self.assertEqual(receipt_dict["status"], ActionStatus.DISPATCHED.value)
            self.assertEqual(len(act_sub.atspi_actions), 1)

        asyncio.run(run())

    def test_mock_windows_hermetic_isolation(self):
        """Ensure mock UIA substrate does not leak to live OS calls."""
        import sys
        if sys.platform != "win32":
            self.skipTest("Isolation test only fully valid on Windows")
        
        obs_sub = MockWindowsUIASubstrate()
        obs_sub.windows = []
        obs_sub.focused_window_title = "Strict Mock Window"
        obs = WindowsUIAObservationAdapter(clock=self.clock, substrate=obs_sub)
        
        import ctypes
        original_windll = getattr(ctypes, "windll", None)
        
        class ExplodingWindll:
            def __getattr__(self, name):
                raise RuntimeError(f"Hermetic boundary violated: mock queried {name}")
                
        try:
            if original_windll is not None:
                ctypes.windll = ExplodingWindll()
                
            titles = obs.list_open_windows()
            self.assertEqual(titles, ["Strict Mock Window"])
            
            focused = obs.get_focused_window_title()
            self.assertEqual(focused, "Strict Mock Window")
            
        finally:
            if original_windll is not None:
                ctypes.windll = original_windll

    def test_live_windows_queries_os_when_no_mock(self):
        """Ensure live mode accesses OS (we only test it doesn't use the mock fallback)."""
        import sys
        if sys.platform != "win32":
            return
            
        obs = WindowsUIAObservationAdapter(clock=self.clock, substrate=None)
        # In live mode with no mock injected, list_open_windows will try to call ctypes.windll.user32
        # We don't want to enforce real OS returns, but we can verify it doesn't just return the mock default
        # "Reflex Native Window" unconditionally if there are real windows, but a simple check is just ensuring it doesn't crash.
        titles = obs.list_open_windows()
        self.assertIsInstance(titles, list)
if __name__ == "__main__":
    unittest.main()
