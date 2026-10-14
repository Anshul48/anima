"""Public serialization round-trip tests for the observation contract.

Regression cover for a real builder defect: an edit nested
ObservationRecord.to_dict/from_dict inside a module-level validator, leaving
the class without public serialization while the suite stayed green. These
tests exercise the actual public methods against a nontrivial graph and
metadata, with the full PNG payload carried separately and with screenshots
absent. They are the offline half of the export/replay/service serialization
checks; the coordinator-executed runner (COORD-EXEC-01) exercises the same
methods through a real source, installed wheel, and separate service process.
"""

from __future__ import annotations

import io
import json
import unittest

from reflex.schemas.delta import OutcomeClass
from reflex.schemas.observation import (
    ObservationQuality,
    ObservationRecord,
    PerceptionDelta,
    SemanticChangeEvent,
    SemanticEventType,
)
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)


def make_png_bytes(width: int = 32, height: int = 24) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="green").save(buf, format="PNG")
    return buf.getvalue()


def make_rich_graph() -> CanonicalUIGraph:
    nodes = {
        "btn_submit": UIStateNode(
            "btn_submit",
            NodeRole.BUTTON,
            BoundingBox(10, 20, 110, 50),
            label="Submit Report",
            value="",
            is_clickable=True,
            is_enabled=True,
            parent_id="form_main",
            source=ModalitySource.DOM,
            confidence=0.99,
            attributes={"aria-label": "Submit Report", "tabindex": "3"},
        ),
        "fld_title": UIStateNode(
            "fld_title",
            NodeRole.INPUT,
            BoundingBox(10, 60, 310, 90),
            label="Title",
            value="Quarterly summary",
            is_clickable=True,
            is_editable=True,
            is_focused=True,
            parent_id="form_main",
            source=ModalitySource.DOM,
            attributes={"maxlength": "120"},
        ),
        "chk_urgent": UIStateNode(
            "chk_urgent",
            NodeRole.CHECKBOX,
            BoundingBox(10, 100, 30, 120),
            label="Mark urgent",
            value="false",
            is_enabled=False,
            source=ModalitySource.DOM,
        ),
        "form_main": UIStateNode(
            "form_main",
            NodeRole.FORM,
            BoundingBox(0, 0, 400, 300),
            label="Report form",
            children_ids=["btn_submit", "fld_title", "chk_urgent"],
            source=ModalitySource.DOM,
        ),
    }
    return CanonicalUIGraph(
        timestamp_ms=1720000000000.0,
        nodes=nodes,
        focused_node_id="fld_title",
        active_window_title="M1 Diagnostic Fixture",
        url="file:///tmp/reflex-linux-20261011-codex/fixtures/m1_diagnostic.html",
        viewport_size=(1280, 800),
    )


def make_rich_observation(screenshot: bytes | None = None) -> ObservationRecord:
    return ObservationRecord(
        observation_id="obs-roundtrip-001",
        timestamp_ms=1720000000000.0,
        source_adapter="cdp_provider",
        platform="linux",
        graph=make_rich_graph(),
        screenshot_bytes=screenshot,
        quality=ObservationQuality.HEALTHY,
        freshness_duration_ms=500.0,
        error_message=None,
        platform_metadata={
            "adapter_class": "CDPObservationProvider",
            "modality_status": {"tree": "ok", "screenshot": "ok: 32x24"},
            "target_id": "ABCDEF123456",
            "device_pixel_ratio": 1.0,
        },
    )


class TestObservationSerializationRoundTrip(unittest.TestCase):
    def test_methods_are_real_class_methods(self):
        self.assertEqual(ObservationRecord.to_dict.__qualname__, "ObservationRecord.to_dict")
        self.assertEqual(ObservationRecord.from_dict.__qualname__, "ObservationRecord.from_dict")

    def test_observation_round_trip_with_separate_png_payload(self):
        png = make_png_bytes()
        obs = make_rich_observation(screenshot=png)
        payload = obs.to_dict(include_screenshot_bytes=True)
        # Payload must be JSON-serializable without the raw bytes inline.
        text = json.dumps(payload)
        self.assertEqual(payload["screenshot_bytes_length"], len(png))
        restored = ObservationRecord.from_dict(json.loads(text), screenshot_bytes=png)
        self.assertEqual(restored.observation_id, obs.observation_id)
        self.assertEqual(restored.timestamp_ms, obs.timestamp_ms)
        self.assertEqual(restored.source_adapter, obs.source_adapter)
        self.assertEqual(restored.platform, obs.platform)
        self.assertEqual(restored.quality, obs.quality)
        self.assertEqual(restored.freshness_duration_ms, obs.freshness_duration_ms)
        self.assertEqual(restored.error_message, obs.error_message)
        self.assertEqual(restored.platform_metadata, obs.platform_metadata)
        self.assertEqual(restored.screenshot_bytes, png)
        self.assertEqual(restored.graph.to_dict(), obs.graph.to_dict())
        self.assertEqual(
            restored.graph.compute_evidence_hash(), obs.graph.compute_evidence_hash()
        )
        # Full node fidelity: values, flags, relations, attributes.
        node = restored.graph.nodes["fld_title"]
        self.assertEqual(node.value, "Quarterly summary")
        self.assertTrue(node.is_focused)
        self.assertTrue(node.is_editable)
        self.assertFalse(restored.graph.nodes["chk_urgent"].is_enabled)
        self.assertEqual(
            list(restored.graph.nodes["form_main"].children_ids),
            ["btn_submit", "fld_title", "chk_urgent"],
        )
        self.assertEqual(
            restored.graph.nodes["btn_submit"].attributes["aria-label"], "Submit Report"
        )
        self.assertEqual(restored.graph.viewport_size, (1280, 800))

    def test_observation_round_trip_absent_screenshot(self):
        obs = make_rich_observation(screenshot=None)
        payload = obs.to_dict()
        self.assertNotIn("screenshot_bytes_length", payload)
        restored = ObservationRecord.from_dict(json.loads(json.dumps(payload)))
        self.assertIsNone(restored.screenshot_bytes)
        self.assertEqual(restored.observation_id, obs.observation_id)
        self.assertEqual(restored.graph.to_dict(), obs.graph.to_dict())

    def test_delta_round_trip_with_events(self):
        delta = PerceptionDelta(
            source_snapshot_id="obs-a",
            target_snapshot_id="obs-b",
            timestamp_ms=1720000001000.0,
            added_nodes=[
                UIStateNode("m1", NodeRole.MODAL, BoundingBox(100, 100, 300, 250), label="Confirm")
            ],
            removed_node_ids=["toast_old"],
            modified_nodes=[{"node_id": "fld_title", "changes": {"value": {"old": "a", "new": "b"}}}],
            changed_bounding_boxes=[BoundingBox(10, 60, 310, 90)],
            pixel_change_ratio=0.02,
            semantic_events=[
                SemanticChangeEvent(
                    event_type=SemanticEventType.MODAL_OPENED,
                    description="Modal window opened: 'Confirm'",
                    target_node_id="m1",
                    timestamp_ms=1720000001000.0,
                )
            ],
            outcome_class=OutcomeClass.MODAL_APPEARED,
        )
        restored = PerceptionDelta.from_dict(json.loads(json.dumps(delta.to_dict())))
        self.assertEqual(restored.to_dict(), delta.to_dict())
        self.assertFalse(restored.is_static)
        self.assertEqual(restored.outcome_class, OutcomeClass.MODAL_APPEARED)
        self.assertEqual(restored.semantic_events[0].event_type, SemanticEventType.MODAL_OPENED)

    def test_from_dict_defaults_do_not_invent_evidence(self):
        restored = ObservationRecord.from_dict({})
        self.assertEqual(restored.platform, "unknown")
        self.assertIsNone(restored.screenshot_bytes)
        self.assertEqual(restored.graph.nodes, {})


if __name__ == "__main__":
    unittest.main()
