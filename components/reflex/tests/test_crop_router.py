"""Test suite for CropAndRouteEngine and CropPacket packaging."""

from __future__ import annotations

import io
from pathlib import Path
import unittest

from PIL import Image

from reflex.perception.vision.crop_router import CropAndRouteEngine, CropPacket
from reflex.schemas.state import BoundingBox


class TestCropRouter(unittest.TestCase):
    """Unit tests for native resolution cropping, quadrant computation, and metadata injection."""

    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = Path(__file__).parent / "fixtures" / "visual_diff"
        with open(cls.fixture_dir / "base_frame.png", "rb") as f:
            cls.base_frame_bytes = f.read()

    def setUp(self):
        self.router = CropAndRouteEngine(default_format="PNG")

    def test_crop_extraction_and_dimensions(self):
        """Asserts that extracted crop has exact native dimensions of requested bounding box."""
        box = BoundingBox(x1=200, y1=100, x2=500, y2=140)  # 300x40 text box
        packet = self.router.crop_region(
            frame_bytes=self.base_frame_bytes,
            bounds=box,
            parent_label="main_panel",
            element_role="input",
            task_context="fill_email",
        )

        self.assertIsInstance(packet, CropPacket)
        self.assertEqual(packet.bounding_box, (200, 100, 500, 140))
        self.assertEqual(packet.parent_label, "main_panel")
        self.assertEqual(packet.element_role, "input")
        self.assertEqual(packet.task_context, "fill_email")

        # Decode base64 and verify image dimensions
        crop_bytes = self.router.decode_crop(packet)
        with Image.open(io.BytesIO(crop_bytes)) as crop_img:
            self.assertEqual(crop_img.size, (300, 40))

    def test_quadrant_calculation(self):
        """Asserts correct quadrant assignment for various screen regions (800x600 viewport)."""
        w, h = 800, 600

        # Top-Left: (50, 50, 100, 100) -> center (75, 75) -> rx=0.09, ry=0.125
        self.assertEqual(
            self.router.compute_quadrant(BoundingBox(x1=50, y1=50, x2=100, y2=100), w, h),
            "Top-Left",
        )

        # Top-Right: (700, 50, 750, 100) -> center (725, 75) -> rx=0.90, ry=0.125
        self.assertEqual(
            self.router.compute_quadrant(BoundingBox(x1=700, y1=50, x2=750, y2=100), w, h),
            "Top-Right",
        )

        # Bottom-Left: (50, 500, 100, 550) -> center (75, 525) -> rx=0.09, ry=0.875
        self.assertEqual(
            self.router.compute_quadrant(BoundingBox(x1=50, y1=500, x2=100, y2=550), w, h),
            "Bottom-Left",
        )

        # Bottom-Right: (700, 500, 750, 550) -> center (725, 525) -> rx=0.90, ry=0.875
        self.assertEqual(
            self.router.compute_quadrant(BoundingBox(x1=700, y1=500, x2=750, y2=550), w, h),
            "Bottom-Right",
        )

        # Center: (350, 250, 450, 350) -> center (400, 300) -> rx=0.50, ry=0.50
        self.assertEqual(
            self.router.compute_quadrant(BoundingBox(x1=350, y1=250, x2=450, y2=350), w, h),
            "Center",
        )

    def test_batch_crop(self):
        """Asserts batch cropping extracts multiple regions efficiently."""
        targets = [
            (BoundingBox(x1=10, y1=10, x2=60, y2=40), "toolbar", "button"),
            (BoundingBox(x1=200, y1=100, x2=500, y2=140), "editor", "input"),
            {"bounding_box": (300, 300, 400, 400), "parent_label": "canvas", "element_role": "icon"},
        ]

        packets = self.router.batch_crop(
            frame_bytes=self.base_frame_bytes,
            targets=targets,
            task_context="canvas_edit",
        )

        self.assertEqual(len(packets), 3)
        self.assertEqual(packets[0].element_role, "button")
        self.assertEqual(packets[0].parent_label, "toolbar")
        self.assertEqual(packets[1].element_role, "input")
        self.assertEqual(packets[2].element_role, "icon")
        self.assertEqual(packets[2].screen_position_quadrant, "Center")

    def test_out_of_bounds_clamping(self):
        """Asserts that coordinates extending beyond image bounds are safely clamped."""
        # Request box (-50, -50, 1000, 1000) on 800x600 image
        packet = self.router.crop_region(
            frame_bytes=self.base_frame_bytes,
            bounds=(-50, -50, 1000, 1000),
        )
        self.assertEqual(packet.bounding_box, (0, 0, 800, 600))
        crop_bytes = self.router.decode_crop(packet)
        with Image.open(io.BytesIO(crop_bytes)) as crop_img:
            self.assertEqual(crop_img.size, (800, 600))

    def test_inverted_coordinates_handling(self):
        """Asserts that inverted coordinates (x1 > x2, y1 > y2) are normalized."""
        packet = self.router.crop_region(
            frame_bytes=self.base_frame_bytes,
            bounds=(300, 200, 100, 50),
        )
        self.assertEqual(packet.bounding_box, (100, 50, 300, 200))


if __name__ == "__main__":
    unittest.main()
