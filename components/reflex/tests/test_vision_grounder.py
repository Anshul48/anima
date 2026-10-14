"""Test suite for VisionGrounderPort, BaseVisionGrounder, and MockVisionGrounder."""

from __future__ import annotations

import asyncio
from pathlib import Path
import unittest

from reflex.perception.vision.vision_grounder import (
    BaseVisionGrounder,
    CorruptedFrameError,
    MockVisionGrounder,
    VisualDetection,
    VisionGrounderPort,
)
from reflex.schemas.state import BoundingBox


class TestVisionGrounder(unittest.IsolatedAsyncioTestCase):
    """Unit and integration tests for visual object detection and referring expression grounding."""

    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = Path(__file__).parent / "fixtures" / "visual_diff"
        with open(cls.fixture_dir / "canvas_buttons.png", "rb") as f:
            cls.canvas_frame_bytes = f.read()

    def setUp(self):
        self.grounder = MockVisionGrounder(simulated_latency_ms=0.0, min_confidence=0.40)

    def test_visual_detection_serialization(self):
        """Tests serialization and deserialization of VisualDetection."""
        det = VisualDetection(
            bounds=BoundingBox(x1=100, y1=150, x2=220, y2=200),
            label="save_button",
            confidence=0.95,
            element_type="button",
        )
        d = det.to_dict()
        det2 = VisualDetection.from_dict(d)
        self.assertEqual(det.bounds, det2.bounds)
        self.assertEqual(det.label, det2.label)
        self.assertEqual(det.confidence, det2.confidence)
        self.assertEqual(det.element_type, det2.element_type)

    def test_compute_iou(self):
        """Tests Intersection-over-Union calculation across bounding boxes."""
        box1 = BoundingBox(x1=100, y1=100, x2=200, y2=200)  # Area 10000
        box2 = BoundingBox(x1=100, y1=100, x2=200, y2=200)  # Identical
        box3 = BoundingBox(x1=150, y1=100, x2=250, y2=200)  # 50% overlap
        box4 = BoundingBox(x1=300, y1=300, x2=400, y2=400)  # No overlap

        # Identical
        self.assertEqual(BaseVisionGrounder.compute_iou(box1, box2), 1.0)
        # Disjoint
        self.assertEqual(BaseVisionGrounder.compute_iou(box1, box4), 0.0)
        # Partial overlap: intersection 50x100 = 5000, union = 10000 + 10000 - 5000 = 15000 -> 0.3333
        self.assertAlmostEqual(BaseVisionGrounder.compute_iou(box1, box3), 0.3333, places=3)

    async def test_canvas_button_grounding_iou(self):
        """Asserts detection of canvas buttons with >= 90% IoU against ground truth."""
        # Expected ground truth for buttons in canvas_buttons.png:
        # Save button: [100, 150, 220, 200]
        # Cancel button: [260, 150, 380, 200]
        save_gt = BoundingBox(x1=100, y1=150, x2=220, y2=200)
        cancel_gt = BoundingBox(x1=260, y1=150, x2=380, y2=200)

        detections = await self.grounder.parse_ui_elements(self.canvas_frame_bytes)
        self.assertGreaterEqual(len(detections), 2)

        # Check that we have a detection matching Save button with IoU >= 0.90
        save_match = any(
            BaseVisionGrounder.compute_iou(d.bounds, save_gt) >= 0.90
            for d in detections
        )
        self.assertTrue(save_match, f"Failed to match Save button with >=90% IoU among {detections}")

        # Check that we have a detection matching Cancel button with IoU >= 0.90
        cancel_match = any(
            BaseVisionGrounder.compute_iou(d.bounds, cancel_gt) >= 0.90
            for d in detections
        )
        self.assertTrue(cancel_match, f"Failed to match Cancel button with >=90% IoU among {detections}")

    async def test_mock_registry_and_referring_expressions(self):
        """Asserts referring expression grounding with registered mock visual detections."""
        save_det = VisualDetection(
            bounds=BoundingBox(x1=100, y1=150, x2=220, y2=200),
            label="Save Changes",
            confidence=0.98,
            element_type="button",
        )
        cancel_det = VisualDetection(
            bounds=BoundingBox(x1=260, y1=150, x2=380, y2=200),
            label="Cancel",
            confidence=0.95,
            element_type="button",
        )
        search_det = VisualDetection(
            bounds=BoundingBox(x1=100, y1=250, x2=500, y2=290),
            label="Search repository",
            confidence=0.92,
            element_type="input",
        )

        self.grounder.register_detections([save_det, cancel_det, search_det])

        # 1. Ground Save button
        resolved_save = await self.grounder.ground_visual_target(
            self.canvas_frame_bytes, "save button"
        )
        self.assertIsNotNone(resolved_save)
        self.assertEqual(resolved_save.label, "Save Changes")
        self.assertEqual(resolved_save.bounds, save_det.bounds)

        # 2. Ground Cancel button
        resolved_cancel = await self.grounder.ground_visual_target(
            self.canvas_frame_bytes, "cancel"
        )
        self.assertIsNotNone(resolved_cancel)
        self.assertEqual(resolved_cancel.label, "Cancel")

        # 3. Ground Search input
        resolved_search = await self.grounder.ground_visual_target(
            self.canvas_frame_bytes, "search input box"
        )
        self.assertIsNotNone(resolved_search)
        self.assertEqual(resolved_search.label, "Search repository")

        # 4. Unknown target returns None
        resolved_unknown = await self.grounder.ground_visual_target(
            self.canvas_frame_bytes, "nonexistent payment checkout widget"
        )
        self.assertIsNone(resolved_unknown)

    async def test_frame_hash_specific_registration(self):
        """Asserts frame-specific mock detections isolate to that specific frame."""
        frame_hash = MockVisionGrounder._compute_frame_hash(self.canvas_frame_bytes)
        custom_det = VisualDetection(
            bounds=BoundingBox(x1=10, y1=10, x2=50, y2=50),
            label="custom_avatar",
            confidence=0.99,
            element_type="icon",
        )
        self.grounder.register_detection(custom_det, frame_key=frame_hash)

        detections = await self.grounder.parse_ui_elements(self.canvas_frame_bytes)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "custom_avatar")

        # Querying with different valid frame bytes returns default / dynamic
        from PIL import Image
        import io
        img_dummy = Image.new("RGB", (60, 60), color=(255, 255, 255))
        buf = io.BytesIO()
        img_dummy.save(buf, format="PNG")
        valid_other_bytes = buf.getvalue()

        self.grounder.clear_mock_detections()
        detections_other = await self.grounder.parse_ui_elements(valid_other_bytes)
        self.assertIsInstance(detections_other, list)

        # Querying with corrupt / invalid bytes MUST raise CorruptedFrameError
        corrupted_bytes = b"corrupted_non_image_bytes_here"
        with self.assertRaises(CorruptedFrameError):
            await self.grounder.parse_ui_elements(corrupted_bytes)


if __name__ == "__main__":
    unittest.main()
