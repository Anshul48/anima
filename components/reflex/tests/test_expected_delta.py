"""Unit and Conformance Tests for ExpectedDeltaEngine (Deterministic Delta Generator)."""

from __future__ import annotations

import unittest

from reflex.cognition.prediction.delta_engine import ExpectedDeltaEngine
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, ModalitySource, NodeRole, UIStateNode


class TestExpectedDeltaEngine(unittest.TestCase):
    """Test suite for deterministic expected state delta prediction across DOM primitives."""

    def setUp(self) -> None:
        self.engine = ExpectedDeltaEngine()
        self.viewport = (1920, 1080)

    def _create_sample_graph(self) -> CanonicalUIGraph:
        """Helper to create a standard UI graph fixture."""
        nodes = {
            "btn_submit": UIStateNode(
                node_id="btn_submit",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(x1=100, y1=100, x2=200, y2=140),
                label="Submit Form",
                attributes={"type": "submit"},
            ),
            "link_pricing": UIStateNode(
                node_id="link_pricing",
                role=NodeRole.LINK,
                bounds=BoundingBox(x1=300, y1=50, x2=400, y2=80),
                label="Pricing",
                attributes={"href": "/pricing"},
            ),
            "chk_terms": UIStateNode(
                node_id="chk_terms",
                role=NodeRole.CHECKBOX,
                bounds=BoundingBox(x1=100, y1=200, x2=120, y2=220),
                label="Agree to Terms",
                value="false",
                attributes={"type": "checkbox"},
            ),
            "input_email": UIStateNode(
                node_id="input_email",
                role=NodeRole.INPUT,
                bounds=BoundingBox(x1=100, y1=300, x2=400, y2=340),
                label="Email Address",
                value="",
                is_editable=True,
            ),
            "btn_open_modal": UIStateNode(
                node_id="btn_open_modal",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(x1=500, y1=100, x2=650, y2=140),
                label="Open Settings Modal",
                attributes={"aria-haspopup": "dialog", "data-toggle": "modal"},
            ),
            "generic_btn": UIStateNode(
                node_id="generic_btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(x1=100, y1=400, x2=200, y2=440),
                label="Click Me",
            ),
        }
        return CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes=nodes,
            focused_node_id="input_email",
            active_window_title="Sample App",
            url="https://app.local/form",
            viewport_size=self.viewport,
        )

    def test_navigate_action(self) -> None:
        """Asserts NAVIGATE primitive yields navigation outcome with 0.50 pixel change ratio."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.NAVIGATE,
            text_payload="https://app.local/dashboard",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.NAVIGATION)
        self.assertEqual(delta.pixel_change_ratio, 0.50)
        self.assertEqual(delta.changed_bounding_boxes, [(0, 0, 1920, 1080)])
        self.assertEqual(delta.added_nodes, [])
        self.assertEqual(delta.removed_nodes, [])

    def test_click_navigation_link(self) -> None:
        """Asserts clicking an anchor link yields navigation outcome."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="link_pricing",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.NAVIGATION)
        self.assertEqual(delta.pixel_change_ratio, 0.50)
        self.assertEqual(delta.changed_bounding_boxes, [(0, 0, 1920, 1080)])

    def test_click_checkbox_toggle(self) -> None:
        """Asserts clicking a checkbox modifies the target node with minimal visual footprint."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="chk_terms",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(delta.modified_nodes, ["chk_terms"])
        self.assertEqual(delta.pixel_change_ratio, 0.005)
        self.assertEqual(delta.changed_bounding_boxes, [(100, 200, 120, 220)])

    def test_type_editable_input(self) -> None:
        """Asserts typing into an editable input yields modified target node."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="input_email",
            text_payload="alice@example.com",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(delta.modified_nodes, ["input_email"])
        self.assertEqual(delta.pixel_change_ratio, 0.005)
        self.assertEqual(delta.changed_bounding_boxes, [(100, 300, 400, 340)])

    def test_type_without_target_uses_focused_node(self) -> None:
        """Asserts typing without explicit target_node_id defaults to current focused_node_id."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.TYPE,
            text_payload="test",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(delta.modified_nodes, ["input_email"])

    def test_click_modal_trigger(self) -> None:
        """Asserts clicking a modal trigger button expects modal node addition and MODAL_APPEARED."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn_open_modal",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.MODAL_APPEARED)
        self.assertIn("modal_root", delta.added_nodes)
        self.assertEqual(delta.pixel_change_ratio, 0.20)

    def test_click_modal_close_button(self) -> None:
        """Asserts clicking close button inside an active modal predicts modal removal."""
        nodes = {
            "active_modal": UIStateNode(
                node_id="active_modal",
                role=NodeRole.MODAL,
                bounds=BoundingBox(x1=400, y1=200, x2=1000, y2=800),
                label="Confirm Action",
            ),
            "btn_close": UIStateNode(
                node_id="btn_close",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(x1=950, y1=210, x2=980, y2=240),
                label="Close",
                parent_id="active_modal",
            ),
        }
        graph = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes=nodes,
            viewport_size=self.viewport,
        )
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn_close",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertIn("active_modal", delta.removed_nodes)
        self.assertEqual(delta.pixel_change_ratio, 0.20)

    def test_escape_key_closes_modal(self) -> None:
        """Asserts Escape key press predicts active modal dismissal."""
        nodes = {
            "dialog_1": UIStateNode(
                node_id="dialog_1",
                role=NodeRole.MODAL,
                bounds=BoundingBox(x1=300, y1=200, x2=800, y2=600),
                label="Alert Dialog",
            ),
        }
        graph = CanonicalUIGraph(timestamp_ms=1000.0, nodes=nodes, viewport_size=self.viewport)
        action = TypedAction(action_type=ActionType.KEY_PRESS, key_code="Escape")

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertIn("dialog_1", delta.removed_nodes)

    def test_scroll_primitive(self) -> None:
        """Asserts SCROLL action predicts viewport bounding box shift with 0.15 pixel change."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.SCROLL,
            scroll_delta=(0.0, 300.0),
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(delta.pixel_change_ratio, 0.15)
        self.assertEqual(delta.changed_bounding_boxes, [(0, 0, 1920, 1080)])

    def test_wait_and_noop_primitives(self) -> None:
        """Asserts WAIT and NOOP predict zero visual/structural changes."""
        graph = self._create_sample_graph()
        for atype in (ActionType.WAIT, ActionType.NOOP):
            action = TypedAction(action_type=atype)
            delta = self.engine.predict_expected_delta(graph, action)

            self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
            self.assertEqual(delta.pixel_change_ratio, 0.0)
            self.assertEqual(delta.added_nodes, [])
            self.assertEqual(delta.removed_nodes, [])
            self.assertEqual(delta.modified_nodes, [])

    def test_hover_primitive(self) -> None:
        """Asserts HOVER action predicts subtle target node modification."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.HOVER,
            target_node_id="generic_btn",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(delta.modified_nodes, ["generic_btn"])
        self.assertEqual(delta.pixel_change_ratio, 0.002)

    def test_target_resolution_by_coordinates(self) -> None:
        """Asserts engine resolves target node by normalized coordinates when ID is omitted."""
        graph = self._create_sample_graph()
        # Point inside chk_terms (bounds: 100, 200, 120, 220 in 1920x1080 -> x=110/1920, y=210/1080)
        coords = NormalizedCoords(x=110.0 / 1920.0, y=210.0 / 1080.0)
        action = TypedAction(
            action_type=ActionType.CLICK,
            coords=coords,
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(delta.modified_nodes, ["chk_terms"])

    def test_target_resolution_by_label(self) -> None:
        """Asserts engine resolves target node by matching label substring."""
        graph = self._create_sample_graph()
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_label="Pricing",
        )

        delta = self.engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.NAVIGATION)

    def test_custom_rule_interception(self) -> None:
        """Asserts custom domain prediction rules can override default heuristics."""
        graph = self._create_sample_graph()
        engine = ExpectedDeltaEngine()

        def custom_rule(st: CanonicalUIGraph, act: TypedAction) -> StateDelta | None:
            if act.target_node_id == "generic_btn":
                return StateDelta(
                    added_nodes=["custom_toast"],
                    removed_nodes=[],
                    modified_nodes=[],
                    pixel_change_ratio=0.08,
                    outcome_class=OutcomeClass.SUCCESS,
                )
            return None

        engine.register_rule(custom_rule)
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="generic_btn")
        delta = engine.predict_expected_delta(graph, action)

        self.assertEqual(delta.added_nodes, ["custom_toast"])
        self.assertEqual(delta.pixel_change_ratio, 0.08)

    def test_graceful_handling_empty_graph(self) -> None:
        """Asserts empty graph does not crash predictor."""
        empty_graph = CanonicalUIGraph(timestamp_ms=0.0, nodes={})
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="unknown")

        delta = self.engine.predict_expected_delta(empty_graph, action)

        self.assertEqual(delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertIn("unknown", delta.modified_nodes)


if __name__ == "__main__":
    unittest.main()
