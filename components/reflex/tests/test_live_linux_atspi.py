"""Live Linux AT-SPI2 D-Bus Perception Integration Suite.

Verifies live Linux desktop accessibility observation over active D-Bus session
and AT-SPI bus (/run/user/<uid>/at-spi/bus) without mock substrates.
"""

from __future__ import annotations

import os
import sys
import unittest

from reflex.perception.native.linux_atspi import LinuxATSPIObservationAdapter
from reflex.schemas.observation import (
    ObservationQuality,
    ObservationRecord,
    PerceptionLifecycleState,
)


class TestLiveLinuxATSPIPerception(unittest.IsolatedAsyncioTestCase):
    """Integration test suite executing against real Linux AT-SPI D-Bus daemon."""

    @classmethod
    def setUpClass(cls) -> None:
        if not sys.platform.startswith("linux"):
            raise unittest.SkipTest("Live AT-SPI tests require a Linux environment")

        bus_addr = os.environ.get("AT_SPI_BUS_ADDRESS")
        runtime_dir = os.environ.get(
            "XDG_RUNTIME_DIR",
            f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "",
        )
        socket_path = (
            os.path.join(runtime_dir, "at-spi", "bus") if runtime_dir else None
        )

        has_atspi_socket = bool(socket_path and os.path.exists(socket_path))
        has_session_bus = bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))

        if not (bus_addr or has_atspi_socket or has_session_bus):
            raise unittest.SkipTest(
                "Neither AT_SPI_BUS_ADDRESS, at-spi socket, nor DBUS_SESSION_BUS_ADDRESS found"
            )

    async def asyncSetUp(self) -> None:
        self.adapter = LinuxATSPIObservationAdapter(substrate=None)

    async def asyncTearDown(self) -> None:
        await self.adapter.teardown()

    async def test_01_live_initialization(self) -> None:
        """Verifies that Linux adapter connects to live AT-SPI bus without mock substrate."""
        self.assertEqual(
            self.adapter.lifecycle_state, PerceptionLifecycleState.UNINITIALIZED
        )
        await self.adapter.initialize()
        self.assertEqual(
            self.adapter.lifecycle_state, PerceptionLifecycleState.CONNECTED
        )
        self.assertTrue(self.adapter.is_healthy())
        self.assertIsNotNone(self.adapter._a11y_bus)
        self.assertIsNotNone(self.adapter._a11y_bus_address)
        self.assertTrue(self.adapter._a11y_bus_address.startswith("unix:path="))

    async def test_02_live_observation_capture_and_provenance(self) -> None:
        """Captures real observation record from live Linux desktop environment."""
        await self.adapter.initialize()
        obs = await self.adapter.capture_observation()

        self.assertIsInstance(obs, ObservationRecord)
        self.assertEqual(obs.source_adapter, "linux_atspi")
        self.assertEqual(obs.platform, "linux")
        self.assertEqual(obs.quality, ObservationQuality.HEALTHY)
        self.assertIsNone(obs.error_message)

        # Validate live D-Bus provenance
        metadata = obs.platform_metadata
        self.assertEqual(metadata["bus"], "at-spi2")
        self.assertTrue(metadata["is_live"])
        self.assertIsNotNone(metadata["bus_address"])
        self.assertTrue(metadata["bus_address"].startswith("unix:path="))

    async def test_03_live_root_registry_properties(self) -> None:
        """Verifies that the live AT-SPI root registry object is queryable over D-Bus."""
        await self.adapter.initialize()
        import dbus

        conn = self.adapter._a11y_bus
        self.assertIsNotNone(conn)

        root = conn.get_object(
            "org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root"
        )
        props = dbus.Interface(root, "org.freedesktop.DBus.Properties")
        root_name = str(props.Get("org.a11y.atspi.Accessible", "Name"))
        self.assertEqual(root_name, "main")

        child_count = int(props.Get("org.a11y.atspi.Accessible", "ChildCount"))
        self.assertGreaterEqual(child_count, 0)

        acc_iface = dbus.Interface(root, "org.a11y.atspi.Accessible")
        children = acc_iface.GetChildren()
        self.assertIsInstance(children, list)
        self.assertEqual(len(children), child_count)

    async def test_04_live_fault_injection_and_recovery(self) -> None:
        """Verifies disconnect and permission fault handling on live Linux adapter."""
        await self.adapter.initialize()
        self.assertEqual(
            self.adapter.lifecycle_state, PerceptionLifecycleState.CONNECTED
        )

        # 1. Simulate disconnect
        self.adapter.simulate_disconnect()
        obs_disc = await self.adapter.capture_observation()
        self.assertEqual(obs_disc.quality, ObservationQuality.DISCONNECTED)
        self.assertIn("disconnected", (obs_disc.error_message or "").lower())

        # 2. Reconnect
        self.adapter.reconnect()
        obs_rec1 = await self.adapter.capture_observation()
        self.assertEqual(obs_rec1.quality, ObservationQuality.HEALTHY)

        # 3. Simulate permission denied
        self.adapter.simulate_permission_denied()
        obs_perm = await self.adapter.capture_observation()
        self.assertEqual(obs_perm.quality, ObservationQuality.PERMISSION_DENIED)
        self.assertIn("permission", (obs_perm.error_message or "").lower())

        # 4. Reconnect
        self.adapter.reconnect()
        obs_rec2 = await self.adapter.capture_observation()
        self.assertEqual(obs_rec2.quality, ObservationQuality.HEALTHY)

    async def test_05_teardown_cleans_resources(self) -> None:
        """Verifies teardown cleanly closes live D-Bus connection."""
        await self.adapter.initialize()
        self.assertIsNotNone(self.adapter._a11y_bus)

        await self.adapter.teardown()
        self.assertEqual(
            self.adapter.lifecycle_state, PerceptionLifecycleState.CLOSED
        )
        self.assertIsNone(self.adapter._a11y_bus)
        self.assertFalse(self.adapter.is_healthy())


if __name__ == "__main__":
    unittest.main()
