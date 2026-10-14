"""Test suite for OpenCVVisualDiffer and frame differencing pipeline."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from reflex.perception.vision.differ import (
    OpenCVVisualDiffer,
    VisualDifferenceResult,
    VisualDifferPort,
)
from reflex.schemas.state import BoundingBox


class TestVisualDiffer(unittest.TestCase):
    """Unit and integration tests for OpenCV frame differencing and SSIM noise rejection."""

    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = Path(__file__).parent / "fixtures" / "visual_diff"
        with open(cls.fixture_dir / "base_frame.png", "rb") as f:
            cls.base_frame_bytes = f.read()
        with open(cls.fixture_dir / "static_frame.png", "rb") as f:
            cls.static_frame_bytes = f.read()
        with open(cls.fixture_dir / "button_added.png", "rb") as f:
            cls.button_added_bytes = f.read()
        with open(cls.fixture_dir / "cursor_blink.png", "rb") as f:
            cls.cursor_blink_bytes = f.read()

    def setUp(self):
        self.differ_cv2 = OpenCVVisualDiffer(
            ssim_noise_threshold=0.85,
            context_padding=24,
            force_fallback=False,
        )
        self.differ_fallback = OpenCVVisualDiffer(
            ssim_noise_threshold=0.85,
            context_padding=24,
            force_fallback=True,
        )

    def test_identical_frames_is_static(self):
        """Asserts identical frames return is_static=True with empty changed_boxes."""
        for differ in [self.differ_cv2, self.differ_fallback]:
            with self.subTest(differ_mode="fallback" if differ.force_fallback else "cv2"):
                result = differ.diff_frames(self.base_frame_bytes, self.static_frame_bytes)
                self.assertIsInstance(result, VisualDifferenceResult)
                self.assertTrue(result.is_static)
                self.assertEqual(result.changed_boxes, [])
                self.assertEqual(result.pixel_change_ratio, 0.0)
                self.assertGreaterEqual(result.duration_ms, 0.0)

    def test_same_buffer_short_circuit(self):
        """Asserts same buffer instance returns instantaneously."""
        result = self.differ_cv2.diff_frames(self.base_frame_bytes, self.base_frame_bytes)
        self.assertTrue(result.is_static)
        self.assertEqual(result.changed_boxes, [])
        self.assertEqual(result.pixel_change_ratio, 0.0)

    def test_modified_button_region_detected(self):
        """Asserts that adding a button triggers non-static result with correct bounding box."""
        for differ in [self.differ_cv2, self.differ_fallback]:
            with self.subTest(differ_mode="fallback" if differ.force_fallback else "cv2"):
                result = differ.diff_frames(self.base_frame_bytes, self.button_added_bytes)
                self.assertFalse(result.is_static)
                self.assertGreater(len(result.changed_boxes), 0)
                self.assertGreater(result.pixel_change_ratio, 0.0)

                # Expected button bounds: [250, 300, 400, 350] (w=150, h=50)
                detected = result.changed_boxes[0]
                self.assertAlmostEqual(detected.x1, 250, delta=10)
                self.assertAlmostEqual(detected.y1, 300, delta=10)
                self.assertAlmostEqual(detected.x2, 400, delta=10)
                self.assertAlmostEqual(detected.y2, 350, delta=10)

    def test_ssim_cursor_blink_noise_filtered(self):
        """Asserts that a 1px blinking cursor is rejected as noise due to SSIM > 0.85."""
        for differ in [self.differ_cv2, self.differ_fallback]:
            with self.subTest(differ_mode="fallback" if differ.force_fallback else "cv2"):
                result = differ.diff_frames(self.base_frame_bytes, self.cursor_blink_bytes)
                # Blinking cursor should be filtered out by SSIM check
                self.assertTrue(
                    result.is_static,
                    f"Blinking cursor was not discarded as noise: {result.changed_boxes}",
                )
                self.assertEqual(result.changed_boxes, [])
                self.assertEqual(result.pixel_change_ratio, 0.0)

    def test_result_serialization_roundtrip(self):
        """Tests serialization and deserialization of VisualDifferenceResult."""
        box = BoundingBox(x1=10, y1=20, x2=110, y2=70)
        res = VisualDifferenceResult(
            changed_boxes=[box],
            pixel_change_ratio=0.0125,
            is_static=False,
            duration_ms=2.45,
        )
        d = res.to_dict()
        res2 = VisualDifferenceResult.from_dict(d)
        self.assertEqual(res.changed_boxes, res2.changed_boxes)
        self.assertEqual(res.pixel_change_ratio, res2.pixel_change_ratio)
        self.assertEqual(res.is_static, res2.is_static)
        self.assertEqual(res.duration_ms, res2.duration_ms)

    def test_resolution_mismatch_fallback(self):
        """Tests handling when consecutive frames have differing dimensions."""
        # Create a smaller dummy frame
        from PIL import Image
        import io
        img_small = Image.new("RGB", (400, 300), color=(0, 0, 0))
        buf = io.BytesIO()
        img_small.save(buf, format="PNG")
        small_bytes = buf.getvalue()

        result = self.differ_cv2.diff_frames(self.base_frame_bytes, small_bytes)
        self.assertFalse(result.is_static)
        self.assertEqual(len(result.changed_boxes), 1)
        self.assertEqual(result.changed_boxes[0], BoundingBox(x1=0, y1=0, x2=400, y2=300))

    def test_cursor_noise_vs_meaningful_small_changes(self):
        """Asserts that cursor noise variants are filtered out while small signals (checkbox, warning, char) are detected."""
        from PIL import Image, ImageDraw
        import io

        base = Image.new("RGB", (400, 200), color=(255, 255, 255))
        d = ImageDraw.Draw(base)
        d.text((20, 20), "User Login Form", fill=(0, 0, 0))
        d.text((20, 60), "Username:", fill=(50, 50, 50))
        d.rectangle([(100, 55), (250, 80)], outline=(180, 180, 180), fill=(245, 245, 245))
        d.text((105, 62), "john_doe", fill=(0, 0, 0))

        # Checkbox base
        d.rectangle([(20, 100), (34, 114)], outline=(100, 100, 100), fill=(255, 255, 255))
        d.text((40, 100), "Remember me", fill=(50, 50, 50))

        def to_bytes(img):
            b = io.BytesIO()
            img.save(b, format="PNG")
            return b.getvalue()

        base_bytes = to_bytes(base)

        # 1. Cursor noise (1px vertical bar)
        f_cur1 = base.copy()
        ImageDraw.Draw(f_cur1).line([(160, 60), (160, 76)], fill=(0, 0, 0), width=1)
        res_cur1 = self.differ_cv2.diff_frames(base_bytes, to_bytes(f_cur1))
        self.assertTrue(res_cur1.is_static, f"1px Cursor should be filtered: {res_cur1.changed_boxes}")

        # 2. Cursor noise (2px vertical bar)
        f_cur2 = base.copy()
        ImageDraw.Draw(f_cur2).line([(160, 60), (160, 76)], fill=(0, 0, 0), width=2)
        res_cur2 = self.differ_cv2.diff_frames(base_bytes, to_bytes(f_cur2))
        self.assertTrue(res_cur2.is_static, f"2px Cursor should be filtered: {res_cur2.changed_boxes}")

        # 3. Cursor noise (horizontal underscore)
        f_cur3 = base.copy()
        ImageDraw.Draw(f_cur3).line([(160, 75), (168, 75)], fill=(0, 0, 0), width=1)
        res_cur3 = self.differ_cv2.diff_frames(base_bytes, to_bytes(f_cur3))
        self.assertTrue(res_cur3.is_static, f"Underscore Cursor should be filtered: {res_cur3.changed_boxes}")

        # 4. Single-character edit ('s' appended) -> MUST BE DETECTED
        f_char = base.copy()
        ImageDraw.Draw(f_char).text((160, 62), "s", fill=(0, 0, 0))
        res_char = self.differ_cv2.diff_frames(base_bytes, to_bytes(f_char))
        self.assertFalse(res_char.is_static, "Single character edit must NOT be filtered out")
        self.assertGreaterEqual(len(res_char.changed_boxes), 1)

        # 5. Checkbox toggle (checkmark drawn) -> MUST BE DETECTED
        f_cb = base.copy()
        d_cb = ImageDraw.Draw(f_cb)
        d_cb.line([(22, 107), (26, 112)], fill=(0, 120, 215), width=2)
        d_cb.line([(26, 112), (32, 103)], fill=(0, 120, 215), width=2)
        res_cb = self.differ_cv2.diff_frames(base_bytes, to_bytes(f_cb))
        self.assertFalse(res_cb.is_static, "Checkbox toggle must NOT be filtered out")
        self.assertGreaterEqual(len(res_cb.changed_boxes), 1)

        # 6. Warning indicator (16x16 icon) -> MUST BE DETECTED
        f_warn = base.copy()
        d_warn = ImageDraw.Draw(f_warn)
        d_warn.polygon([(260, 57), (276, 57), (268, 77)], fill=(220, 50, 50))
        d_warn.line([(268, 62), (268, 70)], fill=(255, 255, 255), width=2)
        d_warn.point([(268, 73)], fill=(255, 255, 255))
        res_warn = self.differ_cv2.diff_frames(base_bytes, to_bytes(f_warn))
        self.assertFalse(res_warn.is_static, "Warning indicator must NOT be filtered out")
        self.assertGreaterEqual(len(res_warn.changed_boxes), 1)


if __name__ == "__main__":
    unittest.main()
