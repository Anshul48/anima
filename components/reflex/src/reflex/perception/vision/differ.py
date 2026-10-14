"""Reflex Visual Differ: Algorithmic frame differencing, Otsu thresholding, and SSIM noise filtering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import io
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

try:
    from PIL import Image, ImageFilter
    _HAS_PIL = True
except ImportError:
    Image = None  # type: ignore[assignment]
    ImageFilter = None  # type: ignore[assignment]
    _HAS_PIL = False

try:
    from scipy.ndimage import binary_closing, find_objects, label, uniform_filter
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

from reflex.schemas.state import BoundingBox


@dataclass(frozen=True)
class VisualDifferenceResult:
    """Outcome of local visual diffing between two frames."""

    changed_boxes: List[BoundingBox]
    pixel_change_ratio: float
    is_static: bool
    duration_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "changed_boxes": [b.to_dict() for b in self.changed_boxes],
            "pixel_change_ratio": self.pixel_change_ratio,
            "is_static": self.is_static,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VisualDifferenceResult:
        return cls(
            changed_boxes=[BoundingBox.from_dict(b) for b in data.get("changed_boxes", [])],
            pixel_change_ratio=float(data.get("pixel_change_ratio", 0.0)),
            is_static=bool(data.get("is_static", True)),
            duration_ms=float(data.get("duration_ms", 0.0)),
        )


class VisualDifferPort(ABC):
    """Abstract port for high-speed local visual frame differencing."""

    @abstractmethod
    def diff_frames(
        self,
        prev_frame_bytes: bytes,
        curr_frame_bytes: bytes,
    ) -> VisualDifferenceResult:
        """Executes sub-millisecond frame differencing pipeline."""
        ...


class OpenCVVisualDiffer(VisualDifferPort):
    """Algorithmic visual frame differencer using OpenCV with pure-Python/PIL fallback.

    Pipeline:
    1. Lossless frame decoding to grayscale (I_gray = 0.299 R + 0.587 G + 0.114 B).
    2. Gaussian smoothing to reduce sensor and sub-pixel high frequency noise.
    3. Absolute difference computation D(x, y) = |I_t - I_{t-1}|.
    4. Otsu automatic global binarization to obtain change mask.
    5. Morphological closing to bridge fragmented text and nearby altered pixel clusters.
    6. External contour extraction to obtain candidate bounding boxes.
    7. Localized Structural Similarity Index (SSIM) evaluation:
       Candidate regions with SSIM > ssim_noise_threshold (default 0.85) are discarded as
       rendering jitter (e.g. blinking text cursors, subtle sub-pixel anti-aliasing shifts).
    """

    def __init__(
        self,
        ssim_noise_threshold: float = 0.85,
        blur_kernel_size: Tuple[int, int] = (5, 5),
        morph_kernel_size: Tuple[int, int] = (7, 7),
        min_box_area: int = 4,
        max_candidate_boxes: int = 50,
        context_padding: int = 24,
        force_fallback: bool = False,
    ) -> None:
        self.ssim_noise_threshold = ssim_noise_threshold
        self.blur_kernel_size = blur_kernel_size
        self.morph_kernel_size = morph_kernel_size
        self.min_box_area = min_box_area
        self.max_candidate_boxes = max_candidate_boxes
        self.context_padding = context_padding
        self.force_fallback = force_fallback

    def _decode_grayscale(self, frame_bytes: bytes) -> np.ndarray:
        """Decodes image bytes to 2D grayscale numpy array (H, W) uint8."""
        if _HAS_CV2 and not self.force_fallback:
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                return img

        if _HAS_PIL:
            pil_img = Image.open(io.BytesIO(frame_bytes)).convert("L")
            return np.array(pil_img, dtype=np.uint8)

        raise RuntimeError(
            "Neither OpenCV (cv2) nor Pillow (PIL) is available for image decoding."
        )

    @staticmethod
    def compute_ssim_numpy(
        roi_prev: np.ndarray,
        roi_curr: np.ndarray,
        k1: float = 0.01,
        k2: float = 0.03,
        L: float = 255.0,
    ) -> float:
        """Computes windowed SSIM on ROI numpy arrays using pure numpy / scipy."""
        if roi_prev.shape != roi_curr.shape or roi_prev.size == 0:
            return 1.0

        p = roi_prev.astype(np.float64)
        c = roi_curr.astype(np.float64)

        c1 = (k1 * L) ** 2
        c2 = (k2 * L) ** 2

        if _HAS_CV2:
            h, w = p.shape[:2]
            kw = min(11, w if w % 2 == 1 else w - 1)
            kh = min(11, h if h % 2 == 1 else h - 1)
            kw = max(3, kw)
            kh = max(3, kh)
            ksize = (kw, kh)

            mu1 = cv2.GaussianBlur(p, ksize, 1.5)
            mu2 = cv2.GaussianBlur(c, ksize, 1.5)
            mu1_sq = mu1 * mu1
            mu2_sq = mu2 * mu2
            mu1_mu2 = mu1 * mu2

            sigma1_sq = cv2.GaussianBlur(p * p, ksize, 1.5) - mu1_sq
            sigma2_sq = cv2.GaussianBlur(c * c, ksize, 1.5) - mu2_sq
            sigma12 = cv2.GaussianBlur(p * c, ksize, 1.5) - mu1_mu2

            ssim_map = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / (
                (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2) + 1e-12
            )
            return float(np.mean(ssim_map))

        if _HAS_SCIPY:
            h, w = p.shape[:2]
            win_size = min(11, min(h, w))
            if win_size >= 3:
                mu1 = uniform_filter(p, win_size)
                mu2 = uniform_filter(c, win_size)
                mu1_sq = mu1 * mu1
                mu2_sq = mu2 * mu2
                mu1_mu2 = mu1 * mu2

                sigma1_sq = uniform_filter(p * p, win_size) - mu1_sq
                sigma2_sq = uniform_filter(c * c, win_size) - mu2_sq
                sigma12 = uniform_filter(p * c, win_size) - mu1_mu2

                ssim_map = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / (
                    (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2) + 1e-12
                )
                return float(np.mean(ssim_map))

        # Fallback global window statistics calculation
        mu1 = float(np.mean(p))
        mu2 = float(np.mean(c))
        sigma1_sq = float(np.var(p))
        sigma2_sq = float(np.var(c))
        sigma12 = float(np.mean((p - mu1) * (c - mu2)))

        numerator = (2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)
        denominator = (mu1**2 + mu2**2 + c1) * (sigma1_sq + sigma2_sq + c2) + 1e-12
        return float(numerator / denominator)

    def _otsu_threshold_numpy(self, diff: np.ndarray) -> np.ndarray:
        """Computes Otsu binarization in pure numpy."""
        hist, _ = np.histogram(diff.ravel(), bins=256, range=(0, 256))
        total = diff.size
        if total == 0:
            return np.zeros_like(diff, dtype=np.uint8)

        current_max = 0.0
        threshold = 0
        sum_total = float(np.dot(np.arange(256), hist))
        sum_b = 0.0
        w_b = 0

        for i in range(256):
            w_b += int(hist[i])
            if w_b == 0:
                continue
            w_f = total - w_b
            if w_f == 0:
                break
            sum_b += float(i * hist[i])
            m_b = sum_b / w_b
            m_f = (sum_total - sum_b) / w_f
            between_var = float(w_b) * float(w_f) * ((m_b - m_f) ** 2)
            if between_var > current_max:
                current_max = between_var
                threshold = i

        return np.where(diff > threshold, 255, 0).astype(np.uint8)

    def _morphological_close_numpy(self, thresh: np.ndarray) -> np.ndarray:
        """Computes morphological closing using scipy or numpy convolution."""
        if _HAS_SCIPY:
            struct = np.ones(self.morph_kernel_size, dtype=bool)
            return binary_closing(thresh > 0, structure=struct).astype(np.uint8) * 255

        # Fallback simple 2D dilation then erosion
        h, w = thresh.shape
        kh, kw = self.morph_kernel_size
        pad_h, pad_w = kh // 2, kw // 2
        padded = np.pad(thresh, ((pad_h, pad_h), (pad_w, pad_w)), mode="constant", constant_values=0)
        dilated = np.zeros_like(thresh)
        for dy in range(kh):
            for dx in range(kw):
                dilated = np.maximum(dilated, padded[dy : dy + h, dx : dx + w])
        
        padded_d = np.pad(dilated, ((pad_h, pad_h), (pad_w, pad_w)), mode="constant", constant_values=255)
        eroded = np.ones_like(thresh) * 255
        for dy in range(kh):
            for dx in range(kw):
                eroded = np.minimum(eroded, padded_d[dy : dy + h, dx : dx + w])
        return eroded

    def _extract_boxes_numpy(self, closed: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Extracts bounding boxes (x, y, w, h) from binary mask using scipy or connected components."""
        if _HAS_SCIPY:
            lbl, _ = label(closed > 0)
            slices = find_objects(lbl)
            boxes = []
            for slc in slices:
                if slc is None:
                    continue
                ys, xs = slc
                w = xs.stop - xs.start
                h = ys.stop - ys.start
                boxes.append((xs.start, ys.start, w, h))
            return boxes

        # Fast row/col scan fallback
        nonzero_y, nonzero_x = np.nonzero(closed)
        if len(nonzero_x) == 0:
            return []
        x_min, x_max = int(np.min(nonzero_x)), int(np.max(nonzero_x))
        y_min, y_max = int(np.min(nonzero_y)), int(np.max(nonzero_y))
        return [(x_min, y_min, x_max - x_min + 1, y_max - y_min + 1)]

    def diff_frames(
        self,
        prev_frame_bytes: bytes,
        curr_frame_bytes: bytes,
    ) -> VisualDifferenceResult:
        """Executes sub-millisecond visual differencing pipeline."""
        start_time = time.perf_counter()

        # Fast byte equality short-circuit
        if prev_frame_bytes == curr_frame_bytes:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return VisualDifferenceResult(
                changed_boxes=[],
                pixel_change_ratio=0.0,
                is_static=True,
                duration_ms=round(elapsed, 3),
            )

        prev_gray = self._decode_grayscale(prev_frame_bytes)
        curr_gray = self._decode_grayscale(curr_frame_bytes)

        if prev_gray.shape != curr_gray.shape:
            # Resolution mismatch between frames
            elapsed = (time.perf_counter() - start_time) * 1000.0
            h, w = curr_gray.shape[:2]
            return VisualDifferenceResult(
                changed_boxes=[BoundingBox(x1=0, y1=0, x2=w, y2=h)],
                pixel_change_ratio=1.0,
                is_static=False,
                duration_ms=round(elapsed, 3),
            )

        h, w = prev_gray.shape[:2]
        total_pixels = h * w

        # Differencing pipeline
        use_cv2 = _HAS_CV2 and not self.force_fallback

        if use_cv2:
            prev_blur = cv2.GaussianBlur(prev_gray, self.blur_kernel_size, 0)
            curr_blur = cv2.GaussianBlur(curr_gray, self.blur_kernel_size, 0)
            diff = cv2.absdiff(curr_blur, prev_blur)

            if int(np.max(diff)) == 0:
                elapsed = (time.perf_counter() - start_time) * 1000.0
                return VisualDifferenceResult(
                    changed_boxes=[],
                    pixel_change_ratio=0.0,
                    is_static=True,
                    duration_ms=round(elapsed, 3),
                )

            _, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            if int(np.count_nonzero(thresh)) == 0:
                elapsed = (time.perf_counter() - start_time) * 1000.0
                return VisualDifferenceResult(
                    changed_boxes=[],
                    pixel_change_ratio=0.0,
                    is_static=True,
                    duration_ms=round(elapsed, 3),
                )

            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, self.morph_kernel_size)
            closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            raw_boxes = [cv2.boundingRect(c) for c in contours]
        else:
            # Pure numpy/PIL fallback
            if _HAS_PIL:
                p_img = Image.fromarray(prev_gray).filter(ImageFilter.GaussianBlur(radius=1.0))
                c_img = Image.fromarray(curr_gray).filter(ImageFilter.GaussianBlur(radius=1.0))
                prev_blur = np.array(p_img, dtype=np.uint8)
                curr_blur = np.array(c_img, dtype=np.uint8)
            else:
                prev_blur = prev_gray
                curr_blur = curr_gray

            diff = np.abs(curr_blur.astype(np.int16) - prev_blur.astype(np.int16)).astype(np.uint8)

            if int(np.max(diff)) == 0:
                elapsed = (time.perf_counter() - start_time) * 1000.0
                return VisualDifferenceResult(
                    changed_boxes=[],
                    pixel_change_ratio=0.0,
                    is_static=True,
                    duration_ms=round(elapsed, 3),
                )

            thresh = self._otsu_threshold_numpy(diff)

            if int(np.count_nonzero(thresh)) == 0:
                elapsed = (time.perf_counter() - start_time) * 1000.0
                return VisualDifferenceResult(
                    changed_boxes=[],
                    pixel_change_ratio=0.0,
                    is_static=True,
                    duration_ms=round(elapsed, 3),
                )

            closed = self._morphological_close_numpy(thresh)
            raw_boxes = self._extract_boxes_numpy(closed)

        # Filter candidate boxes by minimum area
        candidate_boxes = [
            (x, y, bw, bh) for (x, y, bw, bh) in raw_boxes
            if (bw * bh) >= self.min_box_area
        ]

        # Bound maximum candidate boxes to prevent unbounded diffing overhead
        if len(candidate_boxes) > self.max_candidate_boxes:
            candidate_boxes = sorted(
                candidate_boxes, key=lambda b: b[2] * b[3], reverse=True
            )[: self.max_candidate_boxes]

        # Noise Filtering: Calibrated dual-criteria filter
        # 1. Reject sub-pixel rendering jitter / anti-aliasing shifts:
        #    Padded SSIM >= 0.98 and unpadded ROI SSIM >= 0.75 (or max pixel diff < 15).
        # 2. Reject text caret / cursor noise:
        #    Thin vertical or horizontal bar (aspect ratio >= 2.8 with width or height <= 4)
        #    or isolated tiny noise dot (<= 2x2) when surrounding context is static (padded SSIM >= 0.90).
        # 3. Preserve meaningful small changes (single-character edits, checkboxes, warning icons):
        #    Balanced aspect ratio, distinct pixel intensity shifts, low unpadded SSIM.
        retained_boxes: List[BoundingBox] = []
        pad = self.context_padding

        for (bx, by, bw, bh) in candidate_boxes:
            # Direct unpadded ROI
            roi_prev_direct = prev_gray[by : by + bh, bx : bx + bw]
            roi_curr_direct = curr_gray[by : by + bh, bx : bx + bw]
            ssim_nopad = self.compute_ssim_numpy(roi_prev_direct, roi_curr_direct)
            max_pixel_diff = int(np.max(np.abs(roi_curr_direct.astype(np.int16) - roi_prev_direct.astype(np.int16))))

            # Padded context ROI
            x1 = max(0, bx - pad)
            y1 = max(0, by - pad)
            x2 = min(w, bx + bw + pad)
            y2 = min(h, by + bh + pad)

            roi_prev_pad = prev_gray[y1:y2, x1:x2]
            roi_curr_pad = curr_gray[y1:y2, x1:x2]
            ssim_pad = self.compute_ssim_numpy(roi_prev_pad, roi_curr_pad)

            # Evaluate noise criteria
            is_vertical_cursor = (bw <= 4 and bh >= 6 and (bh / max(bw, 1)) >= 2.8 and ssim_pad >= 0.90)
            is_horizontal_cursor = (bh <= 4 and bw >= 6 and (bw / max(bh, 1)) >= 2.8 and ssim_pad >= 0.90)
            is_tiny_dot_noise = (bw <= 2 and bh <= 2 and ssim_pad >= 0.95)

            if is_vertical_cursor or is_horizontal_cursor or is_tiny_dot_noise:
                continue

            # If the candidate bounding box itself underwent genuine structural change, preserve it
            if ssim_nopad < 0.70:
                retained_boxes.append(
                    BoundingBox(x1=bx, y1=by, x2=bx + bw, y2=by + bh)
                )
                continue

            # For regions without significant unpadded structural change (ssim_nopad >= 0.70),
            # reject if context SSIM exceeds noise threshold or pixel difference is negligible jitter
            if ssim_pad >= self.ssim_noise_threshold or max_pixel_diff < 15:
                continue

            retained_boxes.append(
                BoundingBox(x1=bx, y1=by, x2=bx + bw, y2=by + bh)
            )

        # Sort retained boxes top-to-bottom, left-to-right for deterministic ordering
        retained_boxes.sort(key=lambda b: (b.y1, b.x1))

        if not retained_boxes:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return VisualDifferenceResult(
                changed_boxes=[],
                pixel_change_ratio=0.0,
                is_static=True,
                duration_ms=round(elapsed, 3),
            )

        # Calculate pixel change ratio inside retained regions
        retained_mask = np.zeros_like(thresh, dtype=np.uint8)
        for b in retained_boxes:
            retained_mask[b.y1:b.y2, b.x1:b.x2] = thresh[b.y1:b.y2, b.x1:b.x2]

        changed_pixel_count = int(np.count_nonzero(retained_mask))
        change_ratio = float(changed_pixel_count / max(total_pixels, 1))

        elapsed = (time.perf_counter() - start_time) * 1000.0
        return VisualDifferenceResult(
            changed_boxes=retained_boxes,
            pixel_change_ratio=round(change_ratio, 6),
            is_static=False,
            duration_ms=round(elapsed, 3),
        )
