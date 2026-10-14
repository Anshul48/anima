"""Unit and integration tests for Windows Host Bridge Client & WSL2 Adapter (WP-02).

Validates communication between WSL2 Reflex and a native Windows host daemon
running on localhost over HTTP/REST.
"""

from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import threading
from typing import Any, Dict
import unittest

from PIL import Image

from reflex.perception.native.windows_bridge_client import WindowsBridgeClient, WindowsBridgeConfig
from reflex.perception.native.windows_uia import WindowsUIAObservationAdapter
from reflex.ports.clock import DeterministicClock
from reflex.schemas.observation import ObservationQuality, ObservationRecord, PerceptionLifecycleState
from reflex.schemas.state import NodeRole


class MockWindowsBridgeHTTPHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler simulating a native Windows UI Automation host bridge daemon."""

    # Class-level state to simulate daemon health and responses
    is_healthy = True
    active_window = "Visual Studio Code"
    windows_list = ["Visual Studio Code", "Task Manager", "Calculator"]
    # Full-frame screenshot matching the adapter's declared 1920x1080 screen:
    # dimension-consistent by construction (generated once, lazily).
    screenshot_png: bytes | None = None

    @classmethod
    def frame_png(cls) -> bytes:
        if cls.screenshot_png is None:
            buf = io.BytesIO()
            Image.new("RGB", (1920, 1080), color="navy").save(buf, format="PNG")
            cls.screenshot_png = buf.getvalue()
        return cls.screenshot_png

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress standard logging to keep test output clean
        pass

    def do_GET(self) -> None:
        if not self.is_healthy:
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b"Service Unavailable")
            return

        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {"status": "ok", "platform": "windows", "uia_version": "3.0"}
            self.wfile.write(json.dumps(resp).encode("utf-8"))

        elif self.path == "/windows":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"windows": self.windows_list}).encode("utf-8"))

        elif self.path == "/active_window/title":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"title": self.active_window}).encode("utf-8"))

        elif self.path.startswith("/active_window/tree"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            tree_data = {
                "timestamp_ms": 123456.0,
                "active_window_title": self.active_window,
                "focused_node_id": "win_editor",
                "viewport_size": [1920, 1080],
                "nodes": {
                    "win_editor": {
                        "role": "input",
                        "bounds": [100, 100, 800, 600],
                        "label": "Code Editor",
                        "value": "def reflex(): pass",
                        "is_clickable": True,
                        "is_editable": True,
                        "is_focused": True,
                    },
                    "btn_save": {
                        "role": "button",
                        "bounds": [10, 10, 60, 30],
                        "label": "Save",
                        "is_clickable": True,
                        "is_editable": False,
                        "is_focused": False,
                    },
                },
            }
            self.wfile.write(json.dumps(tree_data).encode("utf-8"))

        elif self.path == "/active_window/screenshot":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            # Full-frame PNG matching the declared 1920x1080 screen geometry.
            self.wfile.write(MockWindowsBridgeHTTPHandler.frame_png())

        else:
            self.send_response(404)
            self.end_headers()


class TestWindowsHostBridge(unittest.IsolatedAsyncioTestCase):
    """Test suite for WindowsBridgeClient and bridge-connected WindowsUIAObservationAdapter."""

    @classmethod
    def setUpClass(cls) -> None:
        # Start mock HTTP daemon on ephemeral port
        cls.server = HTTPServer(("127.0.0.1", 0), MockWindowsBridgeHTTPHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

    def setUp(self) -> None:
        MockWindowsBridgeHTTPHandler.is_healthy = True
        self.config = WindowsBridgeConfig(bridge_url=f"http://127.0.0.1:{self.port}", timeout_s=1.0)
        self.client = WindowsBridgeClient(config=self.config)
        self.clock = DeterministicClock(start_time_ms=80000.0)

    async def asyncTearDown(self) -> None:
        await self.client.close()

    async def test_01_bridge_client_health_and_endpoints(self) -> None:
        """Verifies health check and basic introspection across bridge."""
        health = await self.client.check_health()
        self.assertEqual(health.get("status"), "ok")
        self.assertEqual(health.get("platform"), "windows")
        self.assertTrue(self.client.is_connected)

        windows = await self.client.list_open_windows()
        self.assertIn("Visual Studio Code", windows)
        self.assertIn("Task Manager", windows)

        title = await self.client.get_active_window_title()
        self.assertEqual(title, "Visual Studio Code")

    async def test_02_bridge_client_tree_and_screenshot(self) -> None:
        """Verifies extracting CanonicalUIGraph and screenshot over the bridge."""
        await self.client.check_health()

        graph = await self.client.capture_active_window(max_depth=10)
        self.assertIsNotNone(graph)
        assert graph is not None
        self.assertEqual(graph.active_window_title, "Visual Studio Code")
        self.assertEqual(len(graph.nodes), 2)
        self.assertIn("win_editor", graph.nodes)
        self.assertEqual(graph.nodes["win_editor"].role, NodeRole.INPUT)
        self.assertEqual(graph.nodes["btn_save"].role, NodeRole.BUTTON)

        sc = await self.client.capture_screenshot()
        self.assertIsNotNone(sc)
        assert sc is not None
        self.assertTrue(sc.startswith(b"\x89PNG\r\n\x1a\n"))

    async def test_03_windows_adapter_with_active_bridge(self) -> None:
        """Verifies WindowsUIAObservationAdapter transitions to CONNECTED when bridge is healthy."""
        adapter = WindowsUIAObservationAdapter(
            clock=self.clock,
            bridge_client=self.client,
        )

        self.assertEqual(adapter.lifecycle_state, PerceptionLifecycleState.UNINITIALIZED)
        await adapter.initialize()
        # When bridge is running, adapter transitions to CONNECTED instead of DEGRADED!
        self.assertEqual(adapter.lifecycle_state, PerceptionLifecycleState.CONNECTED)
        self.assertTrue(adapter.is_healthy())

        obs = await adapter.capture_observation()
        self.assertIsInstance(obs, ObservationRecord)
        self.assertEqual(obs.source_adapter, "windows_uia")
        self.assertEqual(obs.platform, "windows")
        self.assertEqual(obs.quality, ObservationQuality.HEALTHY)
        self.assertIsNone(obs.error_message)

        # Bridge provenance metadata
        self.assertTrue(obs.platform_metadata["is_bridge"])
        self.assertEqual(obs.platform_metadata["bridge_url"], f"http://127.0.0.1:{self.port}")
        self.assertEqual(obs.graph.active_window_title, "Visual Studio Code")
        self.assertIn("win_editor", obs.graph.nodes)

        await adapter.teardown()
        self.assertEqual(adapter.lifecycle_state, PerceptionLifecycleState.CLOSED)

    async def test_04_windows_adapter_with_unreachable_bridge_degrades_gracefully(self) -> None:
        """Verifies that if bridge is unreachable, adapter degrades with accurate WSL2 status."""
        dead_config = WindowsBridgeConfig(bridge_url="http://127.0.0.1:49999", timeout_s=0.1)
        dead_client = WindowsBridgeClient(config=dead_config)
        adapter = WindowsUIAObservationAdapter(
            clock=self.clock,
            bridge_client=dead_client,
        )

        await adapter.initialize()
        self.assertEqual(adapter.lifecycle_state, PerceptionLifecycleState.DEGRADED)

        obs = await adapter.capture_observation()
        self.assertEqual(obs.quality, ObservationQuality.DEGRADED)
        self.assertIn("Win32 live execution unavailable in Linux WSL2 environment", obs.error_message or "")
        self.assertFalse(obs.platform_metadata.get("is_bridge", False))

    async def test_05_bridge_fault_recovery(self) -> None:
        """Verifies adapter fault injection and recovery over bridge."""
        adapter = WindowsUIAObservationAdapter(
            clock=self.clock,
            bridge_client=self.client,
        )
        await adapter.initialize()
        self.assertEqual(adapter.lifecycle_state, PerceptionLifecycleState.CONNECTED)

        # 1. Simulate disconnect
        adapter.simulate_disconnect()
        obs_disc = await adapter.capture_observation()
        self.assertEqual(obs_disc.quality, ObservationQuality.DISCONNECTED)

        # 2. Reconnect
        adapter.reconnect()
        obs_rec = await adapter.capture_observation()
        self.assertEqual(obs_rec.quality, ObservationQuality.HEALTHY)
        self.assertEqual(adapter.lifecycle_state, PerceptionLifecycleState.CONNECTED)

        await adapter.teardown()


if __name__ == "__main__":
    unittest.main()
