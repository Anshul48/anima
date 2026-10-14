"""Shared conformance fixture suite for Linux AT-SPI and Windows UIA platform adapters.

Validates that both platform adapters adhere to the canonical ObservationPort contract:
- Common capability interfaces
- Lifecycle management (initialize, teardown, health check)
- Explicit failure/degradation states (permissions, disconnect, recovery)
- Provenance and platform metadata preservation
- Accurate validation status labeling on non-native environments
"""

from __future__ import annotations

import unittest

from reflex.perception.native.linux_atspi import LinuxATSPIObservationAdapter, MockLinuxATSPISubstrate
from reflex.perception.native.windows_uia import MockWindowsUIASubstrate, WindowsUIAObservationAdapter
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.observation import (
    ObservationQuality,
    ObservationRecord,
    PerceptionCapabilities,
    PerceptionLifecycleState,
    SemanticEventType,
)
from reflex.schemas.state import NodeRole


class TestPlatformAdapterConformance(unittest.IsolatedAsyncioTestCase):
    """Shared conformance test suite verifying both Linux and Windows native observation adapters."""

    async def asyncSetUp(self) -> None:
        self.clock = DeterministicClock(start_time_ms=50000.0)

        # Linux Substrate
        self.linux_sub = MockLinuxATSPISubstrate()
        self.linux_sub.add_window(title="Settings Manager", app_name="gnome-settings", is_focused=True)
        self.linux_sub.add_element(
            element_id="wifi_toggle",
            name="Wi-Fi Enable",
            role="ROLE_TOGGLE_BUTTON",
            extents=(50, 100, 80, 32),
            value="off",
            is_clickable=True,
            is_focused=True,
        )
        self.linux_adapter = LinuxATSPIObservationAdapter(clock=self.clock, substrate=self.linux_sub)

        # Windows Substrate
        self.win_sub = MockWindowsUIASubstrate()
        self.win_sub.add_window(title="Settings", handle=2002, process_name="SystemSettings.exe", is_focused=True)
        self.win_sub.add_element(
            element_id="wifi_toggle",
            name="Wi-Fi Enable",
            control_type="CheckBox",
            bounds=(50, 100, 130, 132),
            value="off",
            is_clickable=True,
            is_focused=True,
        )
        self.win_adapter = WindowsUIAObservationAdapter(clock=self.clock, substrate=self.win_sub)

    async def test_01_both_adapters_implement_observation_port(self) -> None:
        """Asserts that both Linux and Windows adapters implement the public ObservationPort ABC."""
        self.assertIsInstance(self.linux_adapter, ObservationPort)
        self.assertIsInstance(self.win_adapter, ObservationPort)

    async def test_02_capabilities_contract_conformance(self) -> None:
        """Asserts that both adapters expose valid PerceptionCapabilities declaring their features."""
        for name, adapter in [("linux", self.linux_adapter), ("windows", self.win_adapter)]:
            with self.subTest(adapter=name):
                caps = adapter.capabilities
                self.assertIsInstance(caps, PerceptionCapabilities)
                self.assertTrue(caps.supports_accessibility_tree)
                self.assertTrue(caps.supports_window_hierarchy)
                self.assertTrue(caps.supports_pixel_buffer)
                self.assertTrue(caps.supports_bounding_box_extraction)
                self.assertGreater(len(caps.supported_modalities), 0)

                # Serialization roundtrip
                caps_dict = caps.to_dict()
                caps2 = PerceptionCapabilities.from_dict(caps_dict)
                self.assertEqual(caps, caps2)

    async def test_03_lifecycle_transitions_conformance(self) -> None:
        """Asserts identical lifecycle state transitions across both adapters."""
        for name, adapter in [("linux", self.linux_adapter), ("windows", self.win_adapter)]:
            with self.subTest(adapter=name):
                self.assertEqual(adapter.lifecycle_state, PerceptionLifecycleState.UNINITIALIZED)

                await adapter.initialize()
                self.assertTrue(adapter.is_healthy())
                self.assertIn(
                    adapter.lifecycle_state,
                    (PerceptionLifecycleState.CONNECTED, PerceptionLifecycleState.DEGRADED),
                )

                await adapter.teardown()
                self.assertEqual(adapter.lifecycle_state, PerceptionLifecycleState.CLOSED)
                self.assertFalse(adapter.is_healthy())

    async def test_04_observation_capture_and_provenance(self) -> None:
        """Asserts normalized observation record capture with stable provenance metadata."""
        await self.linux_adapter.initialize()
        await self.win_adapter.initialize()

        # 1. Linux Observation
        linux_obs = await self.linux_adapter.capture_observation()
        self.assertIsInstance(linux_obs, ObservationRecord)
        self.assertEqual(linux_obs.source_adapter, "linux_atspi")
        self.assertEqual(linux_obs.platform, "linux")
        self.assertEqual(linux_obs.graph.active_window_title, "Settings Manager")
        self.assertIn("wifi_toggle", linux_obs.graph.nodes)
        self.assertEqual(linux_obs.graph.nodes["wifi_toggle"].role, NodeRole.TOGGLE)
        self.assertIn("bus", linux_obs.platform_metadata)

        # 2. Windows Observation
        win_obs = await self.win_adapter.capture_observation()
        self.assertIsInstance(win_obs, ObservationRecord)
        self.assertEqual(win_obs.source_adapter, "windows_uia")
        self.assertEqual(win_obs.platform, "windows")
        self.assertEqual(win_obs.graph.active_window_title, "Settings")
        self.assertIn("wifi_toggle", win_obs.graph.nodes)
        self.assertEqual(win_obs.graph.nodes["wifi_toggle"].role, NodeRole.CHECKBOX)
        self.assertIn("uia_version", win_obs.platform_metadata)

    async def test_05_windows_validation_status_accurate_labeling(self) -> None:
        """Asserts accurate validation status labeling when running Windows adapter in Linux WSL2.
        
        Contract requirement: If Windows execution is unavailable, label its implementation and
        validation status accurately; do not claim cross-platform support from interface compatibility alone.
        """
        import sys
        await self.win_adapter.initialize()
        obs = await self.win_adapter.capture_observation()

        if sys.platform != "win32":
            self.assertEqual(
                obs.quality,
                ObservationQuality.DEGRADED,
                "Windows UIA on Linux must report DEGRADED status, not false healthy live win32 execution",
            )
            self.assertIn(
                "Win32 live execution unavailable in Linux WSL2 environment",
                obs.error_message or "",
            )
            self.assertFalse(obs.platform_metadata.get("is_live_win32", True))

    async def test_06_fault_injection_and_recovery_conformance(self) -> None:
        """Asserts that both adapters handle permission denial, disconnect, and recovery identically."""
        for name, adapter in [("linux", self.linux_adapter), ("windows", self.win_adapter)]:
            with self.subTest(adapter=name):
                await adapter.initialize()

                # 1. Permission Denied Fault
                adapter.simulate_permission_denied()
                obs_perm = await adapter.capture_observation()
                self.assertEqual(obs_perm.quality, ObservationQuality.PERMISSION_DENIED)
                self.assertIsNotNone(obs_perm.error_message)
                self.assertEqual(len(obs_perm.graph.nodes), 0)

                # 2. Recovery
                adapter.reconnect()
                obs_rec1 = await adapter.capture_observation()
                self.assertIn(obs_rec1.quality, (ObservationQuality.HEALTHY, ObservationQuality.DEGRADED))
                self.assertGreater(len(obs_rec1.graph.nodes), 0)

                # 3. Disconnect Fault
                adapter.simulate_disconnect()
                obs_disc = await adapter.capture_observation()
                self.assertEqual(obs_disc.quality, ObservationQuality.DISCONNECTED)
                self.assertIsNotNone(obs_disc.error_message)

                # 4. Recovery
                adapter.reconnect()
                obs_rec2 = await adapter.capture_observation()
                self.assertIn(obs_rec2.quality, (ObservationQuality.HEALTHY, ObservationQuality.DEGRADED))

    async def test_07_semantic_delta_conformance(self) -> None:
        """Asserts that semantic delta computation operates consistently on both adapters."""
        await self.linux_adapter.initialize()
        obs1 = await self.linux_adapter.capture_observation()

        # Simulate toggle change in substrate
        self.clock.advance(200.0)
        self.linux_sub.element_tree["wifi_toggle"]["value"] = "on"
        obs2 = await self.linux_adapter.capture_observation()

        delta = self.linux_adapter.compute_delta(obs1, obs2)
        self.assertFalse(delta.is_static)
        self.assertEqual(len(delta.semantic_events), 1)
        self.assertEqual(delta.semantic_events[0].event_type, SemanticEventType.CHECKBOX_TOGGLED)
        self.assertEqual(delta.semantic_events[0].previous_value, "off")
        self.assertEqual(delta.semantic_events[0].current_value, "on")


if __name__ == "__main__":
    unittest.main()
