"""Reflex Vision Grounder: Abstract port and local reference implementation for canvas visual grounding."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
import hashlib
import io
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    Image = None  # type: ignore[assignment]
    _HAS_PIL = False

from reflex.schemas.state import BoundingBox


class CorruptedFrameError(ValueError):
    """Raised when an input image buffer cannot be decoded, is corrupt, or is unsupported."""
    pass


@dataclass(frozen=True)
class VisualDetection:
    """Visual object detection bounding box, class, and confidence score."""

    bounds: BoundingBox
    label: str
    confidence: float
    element_type: str  # "button", "input", "icon", "checkbox", "text", "canvas_element"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bounds": self.bounds.to_dict(),
            "label": self.label,
            "confidence": self.confidence,
            "element_type": self.element_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VisualDetection:
        return cls(
            bounds=BoundingBox.from_dict(data["bounds"]),
            label=str(data.get("label", "")),
            confidence=float(data.get("confidence", 1.0)),
            element_type=str(data.get("element_type", "button")),
        )


class VisionGrounderPort(ABC):
    """Abstract port for visual object detection and referring expression grounding."""

    @abstractmethod
    async def ground_visual_target(
        self,
        frame_bytes: bytes,
        target_description: str,
    ) -> Optional[VisualDetection]:
        """Resolves target description to a visual bounding box on screen/canvas."""
        ...

    @abstractmethod
    async def parse_ui_elements(
        self,
        frame_bytes: bytes,
    ) -> List[VisualDetection]:
        """Detects all interactable visual elements on canvas/screen."""
        ...


class BaseVisionGrounder(VisionGrounderPort):
    """Base class offering spatial geometric metrics and semantic referring expression matching."""

    @staticmethod
    def compute_iou(box1: BoundingBox, box2: BoundingBox) -> float:
        """Computes Intersection-over-Union (IoU) between two BoundingBoxes."""
        x_left = max(box1.x1, box2.x1)
        y_top = max(box1.y1, box2.y1)
        x_right = min(box1.x2, box2.x2)
        y_bottom = min(box1.y2, box2.y2)

        if x_right <= x_left or y_bottom <= y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        box1_area = max(0, (box1.x2 - box1.x1) * (box1.y2 - box1.y1))
        box2_area = max(0, (box2.x2 - box2.x1) * (box2.y2 - box2.y1))
        union_area = box1_area + box2_area - intersection_area

        if union_area <= 0:
            return 0.0
        return round(intersection_area / float(union_area), 4)

    @staticmethod
    def _normalize_text(text: Optional[str]) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", str(text).strip().lower())

    @staticmethod
    def _levenshtein_similarity(s1: str, s2: str) -> float:
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        if len(s1) < len(s2):
            s1, s2 = s2, s1
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        dist = previous_row[-1]
        max_len = max(len(s1), len(s2))
        return 1.0 - (dist / max_len)

    def match_referring_expression(
        self,
        description: str,
        detections: Sequence[VisualDetection],
        min_score: float = 0.40,
    ) -> Optional[VisualDetection]:
        """Matches a referring expression query against candidate visual detections."""
        norm_desc = self._normalize_text(description)
        if not norm_desc or not detections:
            return None

        desc_tokens = set(re.findall(r"\w+", norm_desc))
        scored_candidates: List[Tuple[VisualDetection, float]] = []

        # Known UI roles keywords
        role_keywords = {"button", "input", "box", "icon", "checkbox", "radio", "link", "text", "tab"}
        desc_roles = desc_tokens.intersection(role_keywords)

        for det in detections:
            label_norm = self._normalize_text(det.label)
            elem_type = self._normalize_text(det.element_type)

            score = 0.0

            # Exact or substring label match
            if label_norm and label_norm == norm_desc:
                score = 1.0
            elif label_norm and (label_norm in norm_desc or norm_desc in label_norm):
                ratio = min(len(label_norm), len(norm_desc)) / max(len(label_norm), len(norm_desc))
                score = 0.85 + 0.10 * ratio
            elif label_norm:
                # Token overlap
                det_tokens = set(re.findall(r"\w+", label_norm))
                overlap = desc_tokens & det_tokens
                if overlap:
                    score = 0.65 + 0.25 * (len(overlap) / max(len(det_tokens), 1))
                else:
                    lev = self._levenshtein_similarity(norm_desc, label_norm)
                    if lev >= 0.60:
                        score = 0.50 + 0.30 * lev

            # Role bonus
            if desc_roles:
                if elem_type in desc_roles or any(r in elem_type for r in desc_roles):
                    score = max(score, 0.40) + 0.15

            # Weight by detector confidence
            total_score = min(1.0, score * (0.8 + 0.2 * det.confidence))

            if total_score >= min_score:
                scored_candidates.append((det, total_score))

        if not scored_candidates:
            return None

        scored_candidates.sort(key=lambda item: item[1], reverse=True)
        return scored_candidates[0][0]

    def detect_canvas_elements(self, frame_bytes: bytes) -> List[VisualDetection]:
        """Extracts candidate UI visual components from canvas/screen image buffer.
        
        Raises:
            CorruptedFrameError: If frame_bytes is empty, corrupted, truncated, or un-decodable.
        """
        if not frame_bytes:
            raise CorruptedFrameError("Empty frame buffer received.")

        img = None
        if _HAS_CV2:
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if img is None and _HAS_PIL:
            try:
                pil_img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                w, h = pil_img.size
                if not _HAS_CV2:
                    return [
                        VisualDetection(
                            bounds=BoundingBox(x1=0, y1=0, x2=w, y2=h),
                            label="canvas_root",
                            confidence=0.50,
                            element_type="canvas_element",
                        )
                    ]
                img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception as exc:
                raise CorruptedFrameError(f"Failed to decode image buffer: {exc}") from exc

        if img is None:
            raise CorruptedFrameError("Failed to decode image buffer: corrupt, truncated, or unsupported format.")

        detections: List[VisualDetection] = []
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            bx, by, bw, bh = cv2.boundingRect(c)
            area = bw * bh
            # Filter out outer image frame or tiny noise
            if area < 100 or area > (0.95 * w * h):
                continue

            aspect = float(bw) / max(bh, 1)
            if 1.5 <= aspect <= 6.0:
                elem_type = "button"
            elif aspect > 6.0:
                elem_type = "input"
            elif 0.7 <= aspect <= 1.3:
                elem_type = "icon"
            else:
                elem_type = "canvas_element"

            detections.append(
                VisualDetection(
                    bounds=BoundingBox(x1=bx, y1=by, x2=bx + bw, y2=by + bh),
                    label=f"canvas_{elem_type}_{bx}_{by}",
                    confidence=0.90,
                    element_type=elem_type,
                )
            )

        return detections


class MockVisionGrounder(BaseVisionGrounder):
    """Local mock & reference implementation of VisionGrounderPort for testing and qualification."""

    def __init__(
        self,
        simulated_latency_ms: float = 0.0,
        min_confidence: float = 0.40,
    ) -> None:
        self.simulated_latency_ms = simulated_latency_ms
        self.min_confidence = min_confidence
        self._mock_registry: Dict[str, List[VisualDetection]] = {}
        self._default_detections: List[VisualDetection] = []

    def register_detection(
        self,
        detection: VisualDetection,
        frame_key: Optional[str] = None,
    ) -> None:
        """Registers a mock detection for a specific frame hash or globally."""
        if frame_key:
            if frame_key not in self._mock_registry:
                self._mock_registry[frame_key] = []
            self._mock_registry[frame_key].append(detection)
        else:
            self._default_detections.append(detection)

    def register_detections(
        self,
        detections: Sequence[VisualDetection],
        frame_key: Optional[str] = None,
    ) -> None:
        """Registers multiple mock detections."""
        for d in detections:
            self.register_detection(d, frame_key=frame_key)

    def clear_mock_detections(self) -> None:
        """Clears all registered mock detections."""
        self._mock_registry.clear()
        self._default_detections.clear()

    @staticmethod
    def _compute_frame_hash(frame_bytes: bytes) -> str:
        return hashlib.sha256(frame_bytes).hexdigest()

    async def parse_ui_elements(
        self,
        frame_bytes: bytes,
    ) -> List[VisualDetection]:
        """Detects interactable elements on canvas/screen."""
        if self.simulated_latency_ms > 0:
            await asyncio.sleep(self.simulated_latency_ms / 1000.0)

        frame_key = self._compute_frame_hash(frame_bytes)

        # 1. Registered mock elements for frame hash
        if frame_key in self._mock_registry:
            return list(self._mock_registry[frame_key])

        # 2. Registered default mock elements
        if self._default_detections:
            return list(self._default_detections)

        # 3. Dynamic algorithmic contour detection from canvas image
        return self.detect_canvas_elements(frame_bytes)

    async def ground_visual_target(
        self,
        frame_bytes: bytes,
        target_description: str,
    ) -> Optional[VisualDetection]:
        """Resolves target description to a visual detection."""
        detections = await self.parse_ui_elements(frame_bytes)
        return self.match_referring_expression(
            description=target_description,
            detections=detections,
            min_score=self.min_confidence,
        )
