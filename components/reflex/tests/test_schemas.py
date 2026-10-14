import unittest
from reflex.schemas import (
    ActionType,
    BoundingBox,
    CanonicalUIGraph,
    FallbackLevel,
    ModalitySource,
    NormalizedCoords,
    NodeRole,
    OutcomeClass,
    SafetyClass,
    StateDelta,
    TypedAction,
    UIStateNode,
)


class TestReflexSchemas(unittest.TestCase):
    def test_normalized_coords(self):
        coords = NormalizedCoords(x=0.5, y=0.25)
        px, py = coords.to_pixel(1920, 1080)
        self.assertEqual(px, 960)
        self.assertEqual(py, 270)

    def test_canonical_ui_graph_hashing(self):
        node1 = UIStateNode(
            node_id="btn_1",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(10, 10, 100, 50),
            label="Submit",
        )
        node2 = UIStateNode(
            node_id="inp_1",
            role=NodeRole.INPUT,
            bounds=BoundingBox(10, 60, 200, 90),
            label="Search",
        )

        graph1 = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={"btn_1": node1, "inp_1": node2},
            url="https://example.com",
        )

        graph2 = CanonicalUIGraph(
            timestamp_ms=2000.0,
            nodes={"inp_1": node2, "btn_1": node1},  # reversed insertion order
            url="https://example.com",
        )

        # Hashes must match regardless of insertion order
        self.assertEqual(graph1.compute_state_hash(), graph2.compute_state_hash())

    def test_action_and_fallback_enum(self):
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn_1",
            safety_class=SafetyClass.REVERSIBLE,
        )
        self.assertEqual(action.action_type, "click")
        self.assertLess(FallbackLevel.L0_MOTOR_CACHE, FallbackLevel.L5_CLOUD_VLM)


if __name__ == "__main__":
    unittest.main()
