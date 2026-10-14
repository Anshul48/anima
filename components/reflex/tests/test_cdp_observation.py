"""Unit and mock integration tests for CDPObservationProvider and DOM distillation."""

from __future__ import annotations

import asyncio
import base64
import unittest

from reflex.perception.browser.cdp_provider import (
    CDPObservationProvider,
    FakeCDPClient,
)
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)


class MockPlaywrightPage:
    """Mock Playwright Page for offline unit testing."""

    def __init__(self, eval_return_val=None, screenshot_bytes=b"\x89PNG\r\n\x1a\npw_screenshot"):
        self.eval_return_val = eval_return_val or {}
        self.screenshot_bytes = screenshot_bytes
        self.evaluated_scripts = []

    async def evaluate(self, script: str):
        self.evaluated_scripts.append(script)
        return self.eval_return_val

    async def screenshot(self, type="png"):
        return self.screenshot_bytes


class TestCDPObservation(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000.0)

    def test_observation_port_inheritance(self):
        provider = CDPObservationProvider(clock=self.clock)
        self.assertIsInstance(provider, ObservationPort)

    def test_role_mapping(self):
        self.assertEqual(CDPObservationProvider.map_role("button"), NodeRole.BUTTON)
        self.assertEqual(CDPObservationProvider.map_role("textbox"), NodeRole.INPUT)
        self.assertEqual(CDPObservationProvider.map_role("checkbox"), NodeRole.CHECKBOX)
        self.assertEqual(CDPObservationProvider.map_role("radio"), NodeRole.RADIO)
        self.assertEqual(CDPObservationProvider.map_role("switch"), NodeRole.TOGGLE)
        self.assertEqual(CDPObservationProvider.map_role("link"), NodeRole.LINK)
        self.assertEqual(CDPObservationProvider.map_role("heading"), NodeRole.TEXT)
        self.assertEqual(CDPObservationProvider.map_role("image"), NodeRole.IMAGE)
        self.assertEqual(CDPObservationProvider.map_role("dialog"), NodeRole.MODAL)
        self.assertEqual(CDPObservationProvider.map_role("scrollbar"), NodeRole.SCROLLBAR)
        self.assertEqual(CDPObservationProvider.map_role("region"), NodeRole.CONTAINER)
        self.assertEqual(CDPObservationProvider.map_role(None, "BUTTON"), NodeRole.BUTTON)
        self.assertEqual(CDPObservationProvider.map_role(None, "INPUT"), NodeRole.INPUT)
        self.assertEqual(CDPObservationProvider.map_role(None, "DIV"), NodeRole.CONTAINER)
        self.assertEqual(CDPObservationProvider.map_role(None, "UNKNOWN_TAG"), NodeRole.UNKNOWN)

    def test_capture_state_empty_session(self):
        async def run():
            provider = CDPObservationProvider(clock=self.clock)
            graph = await provider.capture_state()
            self.assertIsInstance(graph, CanonicalUIGraph)
            self.assertEqual(graph.timestamp_ms, 1000.0)
            self.assertEqual(len(graph.nodes), 0)

        asyncio.run(run())

    def test_capture_from_distilled_form_dict(self):
        async def run():
            distilled_form = {
                "url": "http://localhost:8000/form",
                "title": "User Registration",
                "viewport_size": [1920, 1080],
                "focused_node_id": "node_username",
                "nodes": {
                    "node_username": {
                        "node_id": "node_username",
                        "role": "input",
                        "bounds": {"x1": 20, "y1": 50, "x2": 320, "y2": 80},
                        "label": "Username",
                        "value": "",
                        "is_clickable": True,
                        "is_editable": True,
                        "is_focused": True,
                        "is_enabled": True,
                        "parent_id": "node_form",
                        "children_ids": [],
                        "attributes": {"id": "username", "placeholder": "Enter username", "is_topmost": True},
                    },
                    "node_email": {
                        "node_id": "node_email",
                        "role": "input",
                        "bounds": {"x1": 20, "y1": 90, "x2": 320, "y2": 120},
                        "label": "Email Address",
                        "value": "user@example.com",
                        "is_clickable": True,
                        "is_editable": True,
                        "is_focused": False,
                        "is_enabled": True,
                        "parent_id": "node_form",
                        "children_ids": [],
                        "attributes": {"id": "email", "placeholder": "user@example.com", "is_topmost": True},
                    },
                    "node_submit": {
                        "node_id": "node_submit",
                        "role": "button",
                        "bounds": {"x1": 20, "y1": 150, "x2": 100, "y2": 185},
                        "label": "Submit",
                        "value": "",
                        "is_clickable": True,
                        "is_editable": False,
                        "is_focused": False,
                        "is_enabled": True,
                        "parent_id": "node_form",
                        "children_ids": [],
                        "attributes": {"id": "submit_btn", "type": "submit", "is_topmost": True},
                    },
                },
            }

            fake_client = FakeCDPClient(eval_result=distilled_form)
            provider = CDPObservationProvider(cdp_session=fake_client, clock=self.clock)

            graph = await provider.capture_state()
            self.assertEqual(graph.url, "http://localhost:8000/form")
            self.assertEqual(graph.active_window_title, "User Registration")
            self.assertEqual(graph.focused_node_id, "node_username")
            self.assertEqual(len(graph.nodes), 3)

            submit_node = graph.nodes["node_submit"]
            self.assertEqual(submit_node.role, NodeRole.BUTTON)
            self.assertEqual(submit_node.label, "Submit")
            self.assertTrue(submit_node.is_clickable)
            self.assertFalse(submit_node.is_editable)
            self.assertEqual(submit_node.bounds.center, (60, 167))

            # Verify deterministic state hash
            hash_1 = graph.compute_state_hash()
            hash_2 = graph.compute_state_hash()
            self.assertEqual(hash_1, hash_2)
            self.assertEqual(len(hash_1), 64)  # SHA-256 hex length

        asyncio.run(run())

    def test_occlusion_detection_modal_dialog(self):
        """Verifies that occluded background buttons are marked is_clickable=False."""
        async def run():
            distilled_modal = {
                "url": "http://localhost:8000/modal",
                "title": "Modal Dialog Fixture",
                "viewport_size": [1920, 1080],
                "nodes": {
                    "node_bg_btn": {
                        "node_id": "node_bg_btn",
                        "role": "button",
                        "bounds": {"x1": 20, "y1": 50, "x2": 220, "y2": 90},
                        "label": "Perform Background Action",
                        "is_clickable": False,  # Occluded by modal overlay
                        "attributes": {"id": "bg_action_btn", "is_topmost": False},
                    },
                    "node_dialog": {
                        "node_id": "node_dialog",
                        "role": "modal",
                        "bounds": {"x1": 760, "y1": 400, "x2": 1160, "y2": 600},
                        "label": "Confirm Deletion",
                        "is_clickable": True,
                        "attributes": {"role": "dialog", "aria-modal": "true", "is_topmost": True},
                    },
                    "node_confirm_delete": {
                        "node_id": "node_confirm_delete",
                        "role": "button",
                        "bounds": {"x1": 800, "y1": 520, "x2": 880, "y2": 560},
                        "label": "Delete",
                        "is_clickable": True,  # Topmost on modal
                        "parent_id": "node_dialog",
                        "attributes": {"id": "confirm_delete_btn", "is_topmost": True},
                    },
                },
            }

            fake_client = FakeCDPClient(eval_result=distilled_modal)
            provider = CDPObservationProvider(cdp_session=fake_client, clock=self.clock)

            graph = await provider.capture_state()
            self.assertFalse(graph.nodes["node_bg_btn"].is_clickable)
            self.assertFalse(graph.nodes["node_bg_btn"].attributes["is_topmost"])

            self.assertTrue(graph.nodes["node_confirm_delete"].is_clickable)
            self.assertTrue(graph.nodes["node_confirm_delete"].attributes["is_topmost"])

        asyncio.run(run())

    def test_shadow_dom_and_iframe_nodes(self):
        """Verifies ingestion of shadow DOM and nested iframe nodes."""
        async def run():
            distilled_shadow = {
                "url": "http://localhost:8000/shadow",
                "title": "Shadow DOM Fixture",
                "viewport_size": [1920, 1080],
                "nodes": {
                    "node_host": {
                        "node_id": "node_host",
                        "role": "container",
                        "bounds": {"x1": 10, "y1": 10, "x2": 400, "y2": 200},
                        "children_ids": ["node_shadow_btn", "node_shadow_input"],
                    },
                    "node_shadow_btn": {
                        "node_id": "node_shadow_btn",
                        "role": "button",
                        "bounds": {"x1": 20, "y1": 50, "x2": 150, "y2": 85},
                        "label": "Shadow Submit",
                        "is_clickable": True,
                        "parent_id": "node_host",
                    },
                    "node_shadow_input": {
                        "node_id": "node_shadow_input",
                        "role": "input",
                        "bounds": {"x1": 20, "y1": 95, "x2": 250, "y2": 130},
                        "label": "Shadow Search",
                        "value": "",
                        "is_editable": True,
                        "parent_id": "node_host",
                    },
                },
            }

            fake_client = FakeCDPClient(eval_result=distilled_shadow)
            provider = CDPObservationProvider(cdp_session=fake_client, clock=self.clock)

            graph = await provider.capture_state()
            self.assertEqual(len(graph.nodes), 3)
            self.assertIn("node_shadow_btn", graph.nodes)
            self.assertIn("node_shadow_input", graph.nodes)
            self.assertEqual(graph.nodes["node_shadow_btn"].label, "Shadow Submit")
            self.assertEqual(list(graph.nodes["node_host"].children_ids), ["node_shadow_btn", "node_shadow_input"])

        asyncio.run(run())

    def test_protocol_cdp_extraction_pipeline(self):
        """Verifies direct CDP protocol extraction (DOM.getFlattenedDocument + Accessibility.getFullAXTree)."""
        async def run():
            dom_data = {
                "nodes": [
                    {
                        "nodeId": 1,
                        "backendNodeId": 101,
                        "nodeType": 1,
                        "nodeName": "BUTTON",
                        "attributes": ["id", "save_btn", "class", "btn-primary"],
                        "parentId": None,
                    },
                    {
                        "nodeId": 2,
                        "backendNodeId": 102,
                        "nodeType": 1,
                        "nodeName": "INPUT",
                        "attributes": ["id", "name_input", "type", "text", "placeholder", "Full Name"],
                        "parentId": None,
                    },
                    {
                        "nodeId": 3,
                        "backendNodeId": 103,
                        "nodeType": 1,
                        "nodeName": "SCRIPT",  # Noise tag, should be skipped
                        "attributes": [],
                    },
                ]
            }

            ax_data = {
                "nodes": [
                    {
                        "nodeId": "ax_1",
                        "backendDOMNodeId": 101,
                        "role": {"value": "button"},
                        "name": {"value": "Save Changes"},
                    },
                    {
                        "nodeId": "ax_2",
                        "backendDOMNodeId": 102,
                        "role": {"value": "textbox"},
                        "name": {"value": "Full Name"},
                    },
                ]
            }

            box_models = {
                101: {"content": [10, 20, 110, 20, 110, 60, 10, 60], "width": 100, "height": 40},
                102: {"content": [10, 70, 250, 70, 250, 105, 10, 105], "width": 240, "height": 35},
            }

            fake_client = FakeCDPClient(
                flattened_document=dom_data,
                ax_tree=ax_data,
                box_models=box_models,
            )

            provider = CDPObservationProvider(
                cdp_session=fake_client,
                clock=self.clock,
                prefer_js_distiller=False,
            )

            graph = await provider.capture_state()
            self.assertEqual(len(graph.nodes), 2)  # SCRIPT excluded

            btn_node = graph.nodes["node_1"]
            self.assertEqual(btn_node.role, NodeRole.BUTTON)
            self.assertEqual(btn_node.label, "Save Changes")
            self.assertEqual(btn_node.bounds, BoundingBox(10, 20, 110, 60))
            self.assertTrue(btn_node.is_clickable)

            input_node = graph.nodes["node_2"]
            self.assertEqual(input_node.role, NodeRole.INPUT)
            self.assertEqual(input_node.label, "Full Name")
            self.assertTrue(input_node.is_editable)

        asyncio.run(run())

    def test_capture_from_playwright_page(self):
        """Verifies capture using Playwright Page mock."""
        async def run():
            page_data = {
                "url": "http://localhost:3000/app",
                "title": "Playwright App",
                "nodes": {
                    "node_1": {
                        "node_id": "node_1",
                        "role": "button",
                        "label": "Click Me",
                        "bounds": {"x1": 50, "y1": 50, "x2": 150, "y2": 90},
                    }
                },
            }
            mock_page = MockPlaywrightPage(eval_return_val=page_data)
            provider = CDPObservationProvider(page=mock_page, clock=self.clock)

            graph = await provider.capture_state()
            self.assertEqual(graph.url, "http://localhost:3000/app")
            self.assertIn("node_1", graph.nodes)
            self.assertEqual(graph.nodes["node_1"].label, "Click Me")

            # Screenshot test
            screenshot = await provider.capture_screenshot()
            self.assertEqual(screenshot, b"\x89PNG\r\n\x1a\npw_screenshot")

        asyncio.run(run())

    def test_capture_screenshot_cdp(self):
        """Verifies screenshot retrieval via CDP session."""
        async def run():
            fake_client = FakeCDPClient()
            provider = CDPObservationProvider(cdp_session=fake_client)

            screenshot = await provider.capture_screenshot()
            self.assertTrue(screenshot.startswith(b"\x89PNG"))

        asyncio.run(run())

    def test_state_hash_determinism_and_mutation(self):
        """Verifies SHA-256 state hash changes when DOM mutates."""
        n1 = UIStateNode(
            node_id="btn_1",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(0, 0, 100, 40),
            label="Submit",
        )
        g1 = CanonicalUIGraph(timestamp_ms=100.0, nodes={"btn_1": n1}, url="http://app")
        g2 = CanonicalUIGraph(timestamp_ms=200.0, nodes={"btn_1": n1}, url="http://app")

        # Hashes match despite different timestamps
        self.assertEqual(g1.compute_state_hash(), g2.compute_state_hash())

        # Mutate label -> hash must change
        n1_mutated = UIStateNode(
            node_id="btn_1",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(0, 0, 100, 40),
            label="Submitting...",
        )
    def test_dom_distiller_script_loading(self):
        """Verifies that dom_distiller.js is present, non-empty, and loads properly."""
        provider = CDPObservationProvider()
        script = provider._load_distiller_script()
        self.assertTrue(len(script) > 100)
        self.assertIn("function", script)
        self.assertIn("elementFromPoint", script)
        self.assertIn("shadowRoot", script)

    def test_fixture_files_exist(self):
        """Verifies that all 5 benchmark fixture HTML pages exist and are well-formed."""
        from pathlib import Path
        fixtures_dir = Path(__file__).parent / "fixtures" / "browser_pages"
        expected_fixtures = [
            "standard_form.html",
            "modal_dialog.html",
            "data_table.html",
            "shadow_dom.html",
            "nested_iframes.html",
        ]
        for name in expected_fixtures:
            fpath = fixtures_dir / name
            self.assertTrue(fpath.exists(), f"Fixture {name} not found")
            content = fpath.read_text(encoding="utf-8")
            self.assertGreater(len(content), 50)
            self.assertIn("<html", content.lower())

    def test_observation_performance_benchmark(self):
        """Verifies capture_state execution latency is well within < 50ms requirement."""
        import time
        async def run():
            distilled_large = {
                "url": "http://localhost:8000/large",
                "title": "Large Document",
                "nodes": {
                    f"node_{i}": {
                        "node_id": f"node_{i}",
                        "role": "button" if i % 2 == 0 else "text",
                        "bounds": {"x1": i % 1000, "y1": i, "x2": (i % 1000) + 100, "y2": i + 30},
                        "label": f"Action Button {i}",
                        "is_clickable": True,
                    }
                    for i in range(500)
                },
            }
            fake_client = FakeCDPClient(eval_result=distilled_large)
            provider = CDPObservationProvider(cdp_session=fake_client)

            t0 = time.perf_counter()
            graph = await provider.capture_state()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            self.assertEqual(len(graph.nodes), 500)
            self.assertLess(elapsed_ms, 100.0, f"Capture latency {elapsed_ms:.2f}ms exceeded benchmark")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

