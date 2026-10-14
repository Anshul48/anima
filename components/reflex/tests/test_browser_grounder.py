"""Unit and integration tests for BrowserGroundingEngine and semantic target resolution."""

from __future__ import annotations

import unittest

from reflex.grounding.browser_grounder import (
    BrowserGroundingEngine,
    BrowserGroundingPort,
    GroundingQuery,
    GroundingResult,
)
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)


class TestBrowserGrounder(unittest.TestCase):
    def setUp(self):
        self.grounder = BrowserGroundingEngine()

    def _build_sample_form_graph(self) -> CanonicalUIGraph:
        nodes = {
            "btn_submit": UIStateNode(
                node_id="btn_submit",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(50, 200, 150, 240),
                label="Submit",
                is_clickable=True,
                is_enabled=True,
                attributes={"is_topmost": True},
            ),
            "btn_cancel": UIStateNode(
                node_id="btn_cancel",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(160, 200, 240, 240),
                label="Cancel",
                is_clickable=True,
                is_enabled=True,
                attributes={"is_topmost": True},
            ),
            "input_email": UIStateNode(
                node_id="input_email",
                role=NodeRole.INPUT,
                bounds=BoundingBox(50, 100, 300, 135),
                label="Email Address",
                value="",
                is_clickable=True,
                is_editable=True,
                is_enabled=True,
                attributes={"placeholder": "user@example.com", "is_topmost": True},
            ),
            "input_password": UIStateNode(
                node_id="input_password",
                role=NodeRole.INPUT,
                bounds=BoundingBox(50, 145, 300, 180),
                label="Password",
                value="",
                is_clickable=True,
                is_editable=True,
                is_enabled=True,
                attributes={"placeholder": "Enter password", "is_topmost": True},
            ),
            "text_heading": UIStateNode(
                node_id="text_heading",
                role=NodeRole.TEXT,
                bounds=BoundingBox(50, 20, 400, 60),
                label="User Registration",
                is_clickable=False,
                attributes={"is_topmost": True},
            ),
        }
        return CanonicalUIGraph(timestamp_ms=100.0, nodes=nodes, viewport_size=(1920, 1080))

    def _build_data_table_graph(self) -> CanonicalUIGraph:
        """Graph representing a table with 3 rows, each with Edit and Delete buttons."""
        nodes = {
            "table_users": UIStateNode(
                node_id="table_users",
                role=NodeRole.CONTAINER,
                bounds=BoundingBox(20, 20, 800, 400),
                label="Users Table",
                children_ids=["row_alice", "row_bob", "row_charlie"],
            ),
            # Row 1: Alice
            "row_alice": UIStateNode(
                node_id="row_alice",
                role=NodeRole.CONTAINER,
                bounds=BoundingBox(20, 50, 800, 100),
                label="Alice Smith USR-001 Admin",
                parent_id="table_users",
                children_ids=["btn_edit_alice", "btn_delete_alice"],
            ),
            "btn_edit_alice": UIStateNode(
                node_id="btn_edit_alice",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(500, 60, 560, 90),
                label="Edit",
                is_clickable=True,
                parent_id="row_alice",
                attributes={"is_topmost": True},
            ),
            "btn_delete_alice": UIStateNode(
                node_id="btn_delete_alice",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(570, 60, 640, 90),
                label="Delete",
                is_clickable=True,
                parent_id="row_alice",
                attributes={"is_topmost": True},
            ),
            # Row 2: Bob
            "row_bob": UIStateNode(
                node_id="row_bob",
                role=NodeRole.CONTAINER,
                bounds=BoundingBox(20, 110, 800, 160),
                label="Bob Jones USR-002 Viewer",
                parent_id="table_users",
                children_ids=["btn_edit_bob", "btn_delete_bob"],
            ),
            "btn_edit_bob": UIStateNode(
                node_id="btn_edit_bob",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(500, 120, 560, 150),
                label="Edit",
                is_clickable=True,
                parent_id="row_bob",
                attributes={"is_topmost": True},
            ),
            "btn_delete_bob": UIStateNode(
                node_id="btn_delete_bob",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(570, 120, 640, 150),
                label="Delete",
                is_clickable=True,
                parent_id="row_bob",
                attributes={"is_topmost": True},
            ),
            # Row 3: Charlie
            "row_charlie": UIStateNode(
                node_id="row_charlie",
                role=NodeRole.CONTAINER,
                bounds=BoundingBox(20, 170, 800, 220),
                label="Charlie Brown USR-003 Editor",
                parent_id="table_users",
                children_ids=["btn_edit_charlie", "btn_delete_charlie"],
            ),
            "btn_edit_charlie": UIStateNode(
                node_id="btn_edit_charlie",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(500, 180, 560, 210),
                label="Edit",
                is_clickable=True,
                parent_id="row_charlie",
                attributes={"is_topmost": True},
            ),
            "btn_delete_charlie": UIStateNode(
                node_id="btn_delete_charlie",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(570, 180, 640, 210),
                label="Delete",
                is_clickable=True,
                parent_id="row_charlie",
                attributes={"is_topmost": True},
            ),
        }
        return CanonicalUIGraph(timestamp_ms=100.0, nodes=nodes, viewport_size=(1920, 1080))

    def test_port_inheritance(self):
        self.assertIsInstance(self.grounder, BrowserGroundingPort)

    def test_exact_text_resolution(self):
        graph = self._build_sample_form_graph()

        # Resolve Submit button
        query = GroundingQuery(target_text="Submit", target_role="button")
        result = self.grounder.resolve_target(graph, query)

        self.assertIsNotNone(result)
        self.assertEqual(result.target_node.node_id, "btn_submit")
        self.assertGreaterEqual(result.confidence, 0.95)
        self.assertEqual(result.click_coords, (100, 220))
        self.assertFalse(result.is_ambiguous)
        self.assertEqual(result.candidate_count, 1)

    def test_input_target_resolution(self):
        graph = self._build_sample_form_graph()

        query = GroundingQuery(target_text="Email Address", target_role="input")
        result = self.grounder.resolve_target(graph, query)

        self.assertIsNotNone(result)
        self.assertEqual(result.target_node.node_id, "input_email")
        self.assertGreaterEqual(result.confidence, 0.90)
        self.assertEqual(result.click_coords, (175, 117))

    def test_partial_and_fuzzy_matching(self):
        node = UIStateNode(
            node_id="btn_save_all",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(10, 10, 150, 50),
            label="Save All Changes",
            is_clickable=True,
            attributes={"is_topmost": True},
        )
        graph = CanonicalUIGraph(timestamp_ms=100.0, nodes={"btn_save_all": node})

        query = GroundingQuery(target_text="Save", target_role="button", min_confidence=0.80)
        result = self.grounder.resolve_target(graph, query)

        self.assertIsNotNone(result)
        self.assertEqual(result.target_node.node_id, "btn_save_all")
        self.assertGreaterEqual(result.confidence, 0.80)

    def test_role_filtering_preference(self):
        """Checks that target_role disambiguates between a button and a text element with same label."""
        nodes = {
            "heading_submit": UIStateNode(
                node_id="heading_submit",
                role=NodeRole.TEXT,
                bounds=BoundingBox(10, 10, 200, 40),
                label="Submit",
                is_clickable=False,
                attributes={"is_topmost": True},
            ),
            "btn_submit": UIStateNode(
                node_id="btn_submit",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(10, 100, 100, 140),
                label="Submit",
                is_clickable=True,
                attributes={"is_topmost": True},
            ),
        }
        graph = CanonicalUIGraph(timestamp_ms=100.0, nodes=nodes)

        query = GroundingQuery(target_text="Submit", target_role="button")
        result = self.grounder.resolve_target(graph, query)

        self.assertIsNotNone(result)
        self.assertEqual(result.target_node.node_id, "btn_submit")

    def test_container_context_disambiguation(self):
        """Checks resolving Delete button specifically inside Bob's row in a multi-row table."""
        graph = self._build_data_table_graph()

        query_bob = GroundingQuery(
            target_text="Delete",
            target_role="button",
            container_hint="Bob",
        )
        result_bob = self.grounder.resolve_target(graph, query_bob)

        self.assertIsNotNone(result_bob)
        self.assertEqual(result_bob.target_node.node_id, "btn_delete_bob")
        self.assertFalse(result_bob.is_ambiguous)
        self.assertEqual(result_bob.click_coords, (605, 135))

        # Disambiguate Charlie's Edit button
        query_charlie = GroundingQuery(
            target_text="Edit",
            target_role="button",
            container_hint="Charlie",
        )
        result_charlie = self.grounder.resolve_target(graph, query_charlie)

        self.assertIsNotNone(result_charlie)
        self.assertEqual(result_charlie.target_node.node_id, "btn_edit_charlie")
        self.assertFalse(result_charlie.is_ambiguous)

    def test_ambiguous_target_detection(self):
        """Without container hint, 3 identical Delete buttons must be flagged as ambiguous."""
        graph = self._build_data_table_graph()

        query = GroundingQuery(target_text="Delete", target_role="button")
        result = self.grounder.resolve_target(graph, query)

        self.assertIsNotNone(result)
        self.assertTrue(result.is_ambiguous)
        self.assertEqual(result.candidate_count, 3)

    def test_occlusion_and_topmost_penalty(self):
        """Occluded elements have lower confidence and are rejected or ranked lower."""
        nodes = {
            "btn_covered": UIStateNode(
                node_id="btn_covered",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(10, 10, 100, 40),
                label="Confirm",
                is_clickable=False,
                attributes={"is_topmost": False},
            ),
            "btn_modal_confirm": UIStateNode(
                node_id="btn_modal_confirm",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(300, 300, 400, 340),
                label="Confirm",
                is_clickable=True,
                attributes={"is_topmost": True},
            ),
        }
        graph = CanonicalUIGraph(timestamp_ms=100.0, nodes=nodes)

        query = GroundingQuery(target_text="Confirm", target_role="button")
        result = self.grounder.resolve_target(graph, query)

        self.assertIsNotNone(result)
        self.assertEqual(result.target_node.node_id, "btn_modal_confirm")
        self.assertFalse(result.is_ambiguous)

    def test_confidence_threshold_gating(self):
        graph = self._build_sample_form_graph()

        # Query for non-existent element
        query = GroundingQuery(target_text="NonExistentButton", min_confidence=0.80)
        result = self.grounder.resolve_target(graph, query)
        self.assertIsNone(result)

    def test_target_validation_and_layout_shift(self):
        graph = self._build_sample_form_graph()
        initial_bounds = BoundingBox(50, 200, 150, 240)

        # 1. Valid target
        self.assertTrue(self.grounder.validate_target(graph, "btn_submit", initial_bounds))

        # 2. Missing target
        self.assertFalse(self.grounder.validate_target(graph, "btn_nonexistent", initial_bounds))

        # 3. Layout shifted target
        shifted_bounds = BoundingBox(300, 500, 400, 540)
        self.assertFalse(self.grounder.validate_target(graph, "btn_submit", shifted_bounds, tolerance_px=5))

        # 4. Disabled target
        disabled_node = UIStateNode(
            node_id="btn_disabled",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(0, 0, 50, 20),
            is_enabled=False,
        )
        graph_with_disabled = CanonicalUIGraph(timestamp_ms=100.0, nodes={"btn_disabled": disabled_node})
        self.assertFalse(self.grounder.validate_target(graph_with_disabled, "btn_disabled"))

    def test_placeholder_and_attribute_resolution(self):
        """Checks resolving input field via placeholder text when label is empty."""
        node = UIStateNode(
            node_id="input_search",
            role=NodeRole.INPUT,
            bounds=BoundingBox(20, 20, 200, 50),
            label="",
            attributes={"placeholder": "Search products, orders...", "is_topmost": True},
        )
        graph = CanonicalUIGraph(timestamp_ms=100.0, nodes={"input_search": node})

        query = GroundingQuery(target_text="Search products", target_role="input")
        result = self.grounder.resolve_target(graph, query)

        self.assertIsNotNone(result)
        self.assertEqual(result.target_node.node_id, "input_search")
        self.assertGreaterEqual(result.confidence, 0.85)

    def test_shadow_dom_target_resolution(self):
        """Resolves target located within a shadow DOM tree."""
        nodes = {
            "widget_host": UIStateNode(
                node_id="widget_host",
                role=NodeRole.CONTAINER,
                bounds=BoundingBox(10, 10, 400, 300),
                children_ids=["shadow_submit_btn", "shadow_search_input"],
            ),
            "shadow_submit_btn": UIStateNode(
                node_id="shadow_submit_btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(50, 100, 180, 140),
                label="Shadow Submit",
                parent_id="widget_host",
                is_clickable=True,
                attributes={"is_topmost": True},
            ),
            "shadow_search_input": UIStateNode(
                node_id="shadow_search_input",
                role=NodeRole.INPUT,
                bounds=BoundingBox(50, 50, 250, 85),
                label="Shadow Search Components",
                parent_id="widget_host",
                is_clickable=True,
                is_editable=True,
                attributes={"is_topmost": True},
            ),
        }
        graph = CanonicalUIGraph(timestamp_ms=100.0, nodes=nodes)

        query = GroundingQuery(target_text="Shadow Submit", target_role="button")
        result = self.grounder.resolve_target(graph, query)

        self.assertIsNotNone(result)
        self.assertEqual(result.target_node.node_id, "shadow_submit_btn")
        self.assertEqual(result.click_coords, (115, 120))

    def test_nested_iframe_target_resolution(self):
        """Resolves target located within an iframe."""
        nodes = {
            "outer_btn": UIStateNode(
                node_id="outer_btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(20, 20, 120, 60),
                label="Outer Button",
                is_clickable=True,
                attributes={"is_topmost": True},
            ),
            "child_frame": UIStateNode(
                node_id="child_frame",
                role=NodeRole.CONTAINER,
                bounds=BoundingBox(20, 100, 520, 400),
                children_ids=["inner_submit_btn"],
            ),
            "inner_submit_btn": UIStateNode(
                node_id="inner_submit_btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(50, 150, 180, 190),
                label="Inner Submit",
                parent_id="child_frame",
                is_clickable=True,
                attributes={"is_topmost": True},
            ),
        }
        graph = CanonicalUIGraph(timestamp_ms=100.0, nodes=nodes)

        query_inner = GroundingQuery(target_text="Inner Submit", target_role="button")
        result_inner = self.grounder.resolve_target(graph, query_inner)

        self.assertIsNotNone(result_inner)
        self.assertEqual(result_inner.target_node.node_id, "inner_submit_btn")
        self.assertEqual(result_inner.click_coords, (115, 170))

    def test_fixture_suite_grounding_accuracy_benchmark(self):
        """Verifies >= 95% target resolution accuracy across standard fixture queries."""
        graph_form = self._build_sample_form_graph()
        graph_table = self._build_data_table_graph()

        benchmark_queries = [
            (graph_form, GroundingQuery(target_text="Submit", target_role="button"), "btn_submit"),
            (graph_form, GroundingQuery(target_text="Cancel", target_role="button"), "btn_cancel"),
            (graph_form, GroundingQuery(target_text="Email Address", target_role="input"), "input_email"),
            (graph_form, GroundingQuery(target_text="Password", target_role="input"), "input_password"),
            (graph_table, GroundingQuery(target_text="Edit", target_role="button", container_hint="Alice"), "btn_edit_alice"),
            (graph_table, GroundingQuery(target_text="Delete", target_role="button", container_hint="Alice"), "btn_delete_alice"),
            (graph_table, GroundingQuery(target_text="Edit", target_role="button", container_hint="Bob"), "btn_edit_bob"),
            (graph_table, GroundingQuery(target_text="Delete", target_role="button", container_hint="Bob"), "btn_delete_bob"),
            (graph_table, GroundingQuery(target_text="Edit", target_role="button", container_hint="Charlie"), "btn_edit_charlie"),
            (graph_table, GroundingQuery(target_text="Delete", target_role="button", container_hint="Charlie"), "btn_delete_charlie"),
        ]

        correct = 0
        for graph, query, expected_node_id in benchmark_queries:
            res = self.grounder.resolve_target(graph, query)
            self.assertIsNotNone(res, f"Failed to resolve query: {query}")
            if res.target_node.node_id == expected_node_id:
                correct += 1

        accuracy = (correct / len(benchmark_queries)) * 100.0
        self.assertGreaterEqual(accuracy, 95.0, f"Benchmark accuracy {accuracy}% fell below 95%")


if __name__ == "__main__":
    unittest.main()

