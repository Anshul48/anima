"""Unit and live integration tests for Managed Chromium & Direct CDP Driver."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional
import unittest

import websockets

from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.host.identity.lease_manager import ActionLease
from reflex.perception.browser.cdp_provider import (
    CDPObservationProvider,
    FakeCDPClient,
)
from reflex.perception.browser.managed_chromium import (
    CDPChildSession,
    CDPConnectionClosedError,
    CDPError,
    CDPKeyboard,
    CDPLocator,
    CDPMouse,
    CDPPage,
    CDPWebSocketClient,
    ChromiumDiscovery,
    ManagedChromiumProcess,
    ManagedChromiumSession,
)
from reflex.ports.action import ActionStatus
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.identity import ActionIdentity
from reflex.schemas.state import CanonicalUIGraph, NodeRole


class TestChromiumDiscovery(unittest.TestCase):
    """Tests for browser executable discovery and environment overrides."""

    def test_find_browser_executable_system(self):
        """Discovers Chrome or Edge on the active machine."""
        exe = ChromiumDiscovery.find_browser_executable()
        if exe is None:
            self.skipTest("No system browser executable installed")
        self.assertIsNotNone(exe, "Should discover at least one system browser executable")
        self.assertTrue(os.path.isfile(exe), f"Discovered executable '{exe}' must be a file")

    def test_get_available_executables(self):
        """Retrieves list of all available browser executables."""
        executables = ChromiumDiscovery.get_available_executables()
        if not executables:
            self.skipTest("No system browser executable installed")
        self.assertIsInstance(executables, list)
        self.assertGreater(len(executables), 0)
        for exe in executables:
            self.assertTrue(os.path.isfile(exe))

    def test_env_var_override(self):
        """Verifies environment variable takes precedence during discovery."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_exe = Path(tmp_dir) / ("fake_chrome.exe" if os.name == "nt" else "fake_chrome")
            fake_exe.write_text("#!/bin/sh\nexit 0\n")
            if os.name != "nt":
                os.chmod(fake_exe, 0o755)

            old_env = os.environ.get("CHROMIUM_PATH")
            try:
                os.environ["CHROMIUM_PATH"] = str(fake_exe)
                found = ChromiumDiscovery.find_browser_executable()
                self.assertEqual(found, str(fake_exe.resolve()))
            finally:
                if old_env is not None:
                    os.environ["CHROMIUM_PATH"] = old_env
                else:
                    os.environ.pop("CHROMIUM_PATH", None)

    def test_custom_path_override(self):
        """Verifies custom_path argument takes precedence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_exe = Path(tmp_dir) / ("custom_chrome.exe" if os.name == "nt" else "custom_chrome")
            fake_exe.write_text("#!/bin/sh\nexit 0\n")
            if os.name != "nt":
                os.chmod(fake_exe, 0o755)

            found = ChromiumDiscovery.find_browser_executable(custom_path=str(fake_exe))
            self.assertEqual(found, str(fake_exe.resolve()))

    def test_missing_executable_raises_error(self):
        """Verifies FileNotFoundError when executable path does not exist."""
        with self.assertRaises(FileNotFoundError):
            ManagedChromiumProcess(executable_path="C:\\nonexistent_dir\\fake_browser.exe")


class TestManagedChromiumProcessConfiguration(unittest.TestCase):
    """Unit tests for ManagedChromiumProcess argument construction and configuration."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        system_exe = ChromiumDiscovery.find_browser_executable()
        if system_exe is None:
            fake_exe = Path(self.temp_dir.name) / ("fake_chrome.exe" if os.name == "nt" else "fake_chrome")
            fake_exe.write_text("#!/bin/sh\nexit 0\n")
            if os.name != "nt":
                os.chmod(fake_exe, 0o755)
            self.system_exe = str(fake_exe)
        else:
            self.system_exe = system_exe

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_command_args_construction(self):
        system_exe = self.system_exe
        assert system_exe is not None

        proc = ManagedChromiumProcess(
            executable_path=system_exe,
            port=9222,
            headless="new",
            window_size=(1600, 900),
            extra_args=["--custom-flag-1", "--custom-flag-2=true"],
            disable_gpu=True,
        )

        args = proc._build_command_args()
        self.assertEqual(args[0], system_exe)
        self.assertIn("--remote-debugging-port=9222", args)
        self.assertIn("--window-size=1600,900", args)
        self.assertIn("--headless=new", args)
        self.assertIn("--disable-gpu", args)
        self.assertIn("--custom-flag-1", args)
        self.assertIn("--custom-flag-2=true", args)

    def test_headless_variants(self):
        system_exe = self.system_exe
        assert system_exe is not None

        proc_old = ManagedChromiumProcess(executable_path=system_exe, headless="old")
        self.assertIn("--headless", proc_old._build_command_args())

        proc_none = ManagedChromiumProcess(executable_path=system_exe, headless=False)
        self.assertNotIn("--headless", proc_none._build_command_args())
        self.assertNotIn("--headless=new", proc_none._build_command_args())

    def test_auto_cleanup_behavior(self):
        system_exe = self.system_exe
        assert system_exe is not None

        proc = ManagedChromiumProcess(executable_path=system_exe, auto_cleanup=True)
        temp_path = proc.user_data_dir
        self.assertTrue(temp_path.exists())

        proc.stop()
        self.assertFalse(temp_path.exists())

    def test_custom_user_data_dir_not_deleted_if_not_auto_created(self):
        system_exe = self.system_exe
        assert system_exe is not None

        with tempfile.TemporaryDirectory() as custom_dir:
            custom_path = Path(custom_dir) / "profile"
            custom_path.mkdir()

            proc = ManagedChromiumProcess(
                executable_path=system_exe,
                user_data_dir=custom_path,
                auto_cleanup=True,
            )
            proc.stop()
            self.assertTrue(custom_path.exists())


class TestMockCDPWebSocketClient(unittest.TestCase):
    """Unit tests for CDPWebSocketClient protocol mechanics using a mock WebSocket server."""

    def test_client_request_response_and_events(self):
        async def run():
            # Spin up a lightweight in-process mock CDP server
            async def echo_cdp_server(websocket: websockets.WebSocketServerProtocol):
                async for raw_msg in websocket:
                    data = json.loads(raw_msg)
                    req_id = data.get("id")
                    method = data.get("method")
                    params = data.get("params", {})

                    if method == "Page.enable":
                        # Send load event before reply
                        await websocket.send(json.dumps({
                            "method": "Page.loadEventFired",
                            "params": {"timestamp": 12345.67},
                        }))
                        await websocket.send(json.dumps({
                            "id": req_id,
                            "result": {},
                        }))
                    elif method == "Runtime.evaluate":
                        expr = params.get("expression", "")
                        await websocket.send(json.dumps({
                            "id": req_id,
                            "result": {
                                "result": {
                                    "type": "string",
                                    "value": f"eval:{expr}",
                                }
                            },
                        }))
                    elif method == "Error.trigger":
                        await websocket.send(json.dumps({
                            "id": req_id,
                            "error": {
                                "code": -32001,
                                "message": "Simulated CDP domain failure",
                            },
                        }))
                    elif method == "Child.command":
                        session_id = data.get("sessionId")
                        await websocket.send(json.dumps({
                            "id": req_id,
                            "sessionId": session_id,
                            "result": {"received_by_session": session_id},
                        }))
                        # Emit session event
                        await websocket.send(json.dumps({
                            "method": "Child.sessionEvent",
                            "sessionId": session_id,
                            "params": {"detail": "child_event_ok"},
                        }))

            server = await websockets.serve(echo_cdp_server, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://127.0.0.1:{port}"

            try:
                client = CDPWebSocketClient(ws_url, timeout=5.0)
                await client.connect()
                self.assertTrue(client.is_connected)

                # 1. Event listener registration
                received_events = []
                client.on("Page.loadEventFired", lambda p: received_events.append(p))

                # 2. Command execution
                resp1 = await client.send("Page.enable")
                self.assertEqual(resp1, {})

                # Allow event loop tick for event delivery
                await asyncio.sleep(0.05)
                self.assertEqual(len(received_events), 1)
                self.assertEqual(received_events[0]["timestamp"], 12345.67)

                # 3. Runtime.evaluate command
                resp2 = await client.send("Runtime.evaluate", {"expression": "2+2"})
                self.assertEqual(resp2["result"]["value"], "eval:2+2")

                # 4. Error response propagation
                with self.assertRaises(CDPError) as ctx:
                    await client.send("Error.trigger")
                self.assertIn("Simulated CDP domain failure", str(ctx.exception))
                self.assertEqual(ctx.exception.code, -32001)

                # 5. wait_for_event helper
                event_task = asyncio.create_task(
                    client.wait_for_event("Page.loadEventFired", timeout=2.0)
                )
                await client.send("Page.enable")
                ev = await event_task
                self.assertEqual(ev["timestamp"], 12345.67)

                # 6. Child session multiplexing
                child = client.create_session("sess_alpha")
                child_events = []
                child.on("Child.sessionEvent", lambda p: child_events.append(p))

                child_resp = await child.send("Child.command")
                self.assertEqual(child_resp["received_by_session"], "sess_alpha")

                await asyncio.sleep(0.05)
                self.assertEqual(len(child_events), 1)
                self.assertEqual(child_events[0]["detail"], "child_event_ok")

                await client.close()
                self.assertFalse(client.is_connected)

            finally:
                server.close()
                await server.wait_closed()

        asyncio.run(run())

    def test_client_timeout_and_disconnect(self):
        async def run():
            async def silent_server(websocket: websockets.WebSocketServerProtocol):
                # Don't reply, just hang or close
                async for msg in websocket:
                    data = json.loads(msg)
                    if data.get("method") == "Close.now":
                        await websocket.close()

            server = await websockets.serve(silent_server, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            ws_url = f"ws://127.0.0.1:{port}"

            try:
                client = CDPWebSocketClient(ws_url, timeout=0.1)
                await client.connect()

                # Test timeout
                with self.assertRaises(TimeoutError):
                    await client.send("Hanging.command")

                # Test disconnect during request
                disconnect_client = CDPWebSocketClient(ws_url, timeout=5.0)
                await disconnect_client.connect()

                req_task = asyncio.create_task(disconnect_client.send("Hanging.command"))
                await asyncio.sleep(0.05)
                await disconnect_client.close()

                with self.assertRaises(CDPConnectionClosedError):
                    await req_task

                await client.close()


            finally:
                server.close()
                await server.wait_closed()

        asyncio.run(run())


class TestCDPPageAndInputPrimitives(unittest.TestCase):
    """Unit tests for CDPPage, CDPMouse, CDPKeyboard, and CDPLocator."""

    def test_mouse_and_keyboard_primitives(self):
        async def run():
            fake_cdp = FakeCDPClient()
            page = CDPPage(fake_cdp, viewport_size=(1920, 1080))

            # Test Mouse click
            await page.mouse.click(100, 200, button="left")
            commands = [cmd[0] for cmd in fake_cdp.sent_commands]
            self.assertIn("Input.dispatchMouseEvent", commands)

            # Test Keyboard type
            fake_cdp.sent_commands.clear()
            await page.keyboard.type("Hello Reflex")
            self.assertEqual(fake_cdp.sent_commands[0], ("Input.insertText", {"text": "Hello Reflex"}))

            # Test Keyboard press
            fake_cdp.sent_commands.clear()
            await page.keyboard.press("Enter")
            press_cmds = [cmd[0] for cmd in fake_cdp.sent_commands]
            self.assertEqual(press_cmds.count("Input.dispatchKeyEvent"), 3)  # down, char, up

            # Test evaluate
            fake_cdp.eval_result = {"key": "value"}
            eval_val = await page.evaluate("return 42")
            self.assertEqual(eval_val, {"key": "value"})

        asyncio.run(run())


class TestLiveManagedChromiumIntegration(unittest.TestCase):
    """Integration tests running against the live installed Chromium/Edge browser."""

    @classmethod
    def setUpClass(cls):
        cls.browser_exe = ChromiumDiscovery.find_browser_executable()
        if not cls.browser_exe:
            raise unittest.SkipTest("No Chromium or Edge executable found for live testing")

    def test_live_process_lifecycle(self):
        """Tests live Chromium process startup, DevToolsActivePort discovery, health check, and termination."""
        proc = ManagedChromiumProcess(
            executable_path=self.browser_exe,
            port=0,
            headless="new",
            disable_gpu=True,
        )
        try:
            ws_url = proc.start()
            self.assertTrue(proc.is_running())
            self.assertIsNotNone(proc.actual_port)
            self.assertGreater(proc.actual_port, 0)
            self.assertTrue(ws_url.startswith("ws://127.0.0.1:"))
            self.assertTrue(proc.check_health())

            version_info = proc.get_version_info()
            self.assertIn("Browser", version_info)
            self.assertIn("Protocol-Version", version_info)

            targets = proc.get_targets()
            self.assertIsInstance(targets, list)
            self.assertGreater(len(targets), 0)

        finally:
            proc.stop()
            self.assertFalse(proc.is_running())

    def test_live_managed_chromium_session_navigation_and_dom_extraction(self):
        """Tests end-to-end navigation, DOM/AXTree distillation, and screenshot capture in live browser."""
        async def run():
            async with ManagedChromiumSession(
                executable_path=self.browser_exe,
                headless="new",
                window_size=(1920, 1080),
                disable_gpu=True,
            ) as session:
                self.assertIsNotNone(session.page)
                self.assertIsNotNone(session.observation_provider)
                self.assertIsNotNone(session.action_adapter)

                # Navigate to a structured data URI HTML fixture
                html_fixture = """data:text/html,<!DOCTYPE html>
                <html>
                <head>
                    <title>Managed Chromium Live Test</title>
                </head>
                <body>
                    <header>
                        <h1>Reflex Live Integration Suite</h1>
                    </header>
                    <main>
                        <form id="login_form">
                            <label for="username_inp">User:</label>
                            <input id="username_inp" type="text" placeholder="Enter username" />
                            <button id="submit_btn" type="button" onclick="window.__clicked=true">Submit Form</button>
                        </form>
                    </main>
                </body>
                </html>
                """
                await session.navigate(html_fixture)

                # Verify JavaScript evaluation in page context
                title = await session.evaluate("document.title")
                self.assertEqual(title, "Managed Chromium Live Test")

                # Verify page content
                content = await session.get_page_content()
                self.assertIn("Reflex Live Integration Suite", content)

                # Capture canonical state graph
                graph = await session.capture_state()
                self.assertIsInstance(graph, CanonicalUIGraph)
                self.assertEqual(graph.active_window_title, "Managed Chromium Live Test")

                # Verify interactive nodes were distilled
                btn_node = next((n for n in graph.nodes.values() if "submit_btn" in n.node_id or n.label == "Submit Form"), None)
                self.assertIsNotNone(btn_node, "Submit button should be present in canonical graph")
                self.assertEqual(btn_node.role, NodeRole.BUTTON)
                self.assertTrue(btn_node.is_clickable)

                input_node = next((n for n in graph.nodes.values() if "username_inp" in n.node_id), None)
                self.assertIsNotNone(input_node, "Username input should be present in canonical graph")
                self.assertEqual(input_node.role, NodeRole.INPUT)
                self.assertTrue(input_node.is_editable)

                # Capture viewport screenshot
                screenshot = await session.capture_screenshot()
                self.assertIsInstance(screenshot, bytes)
                self.assertTrue(screenshot.startswith(b"\x89PNG\r\n\x1a\n"), "Must be a valid PNG image")
                self.assertGreater(len(screenshot), 1000)

        asyncio.run(run())

    def test_live_action_adapter_typing_and_clicking(self):
        """Tests executing typed actions via CDPActionAdapter on live Chromium session."""
        async def run():
            async with ManagedChromiumSession(
                executable_path=self.browser_exe,
                headless="new",
                window_size=(1920, 1080),
                disable_gpu=True,
            ) as session:
                html_fixture = """data:text/html,<!DOCTYPE html>
                <html>
                <head><title>Action Test</title></head>
                <body>
                    <input id="test_input" type="text" value="" />
                    <button id="test_button" onclick="window.__buttonClicked = true">Execute</button>
                </body>
                </html>"""
                await session.navigate(html_fixture)

                now_ms = time.time() * 1000.0

                # 1. Type into input
                type_action = TypedAction(
                    action_type=ActionType.TYPE,
                    target_node_id="test_input",
                    text_payload="Reflex CDP Works!",
                )
                type_lease = ActionLease(
                    lease_id="lease_type_1",
                    identity=ActionIdentity.create(session_id="run_1", step_index=1),
                    action=type_action,
                    expires_at_ms=now_ms + 10000.0,
                    created_at_ms=now_ms,
                )

                receipt1 = await session.action_adapter.execute_action(type_action, type_lease)
                self.assertEqual(receipt1.status, ActionStatus.DISPATCHED)
                self.assertIsNone(receipt1.error)

                input_val = await session.evaluate("document.getElementById('test_input').value")
                self.assertEqual(input_val, "Reflex CDP Works!")

                # 2. Click button
                click_action = TypedAction(
                    action_type=ActionType.CLICK,
                    target_node_id="test_button",
                )
                click_lease = ActionLease(
                    lease_id="lease_click_1",
                    identity=ActionIdentity.create(session_id="run_1", step_index=2),
                    action=click_action,
                    expires_at_ms=now_ms + 10000.0,
                    created_at_ms=now_ms,
                )

                receipt2 = await session.action_adapter.execute_action(click_action, click_lease)
                self.assertEqual(receipt2.status, ActionStatus.DISPATCHED)
                self.assertIsNone(receipt2.error)

                clicked = await session.evaluate("window.__buttonClicked === true")
                self.assertTrue(clicked)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
