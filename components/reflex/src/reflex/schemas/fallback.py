from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, Tuple


class FallbackLevel(IntEnum):
    L0_MOTOR_CACHE = 0    # Sub-5ms exact/ANN skill match (System 1)
    L1_DIFF_ENGINE = 1     # Pixel/DOM diff check against static regions (System 1)
    L2_YOLO_OCR = 2        # Fine-tuned YOLOv11-UI + RapidOCR crop detection (System 1)
    L3_DINO_GROUNDING = 3  # DINOv2 / Florence-2 crop-based grounding (System 1/2 boundary)
    L4_LOCAL_VLM = 4       # Holo 3.1 9B on bounding box crops only (System 2 local)
    L5_CLOUD_VLM = 5       # Gemini Computer Use on bounding box crops only (System 2 cloud)


@dataclass
class CropPacket:
    """Crop-and-Route payload passed to high-level VLMs (L4/L5) to keep O(N) compute."""
    bounding_box: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    crop_base64: str                         # High-resolution native crop
    parent_label: str
    element_role: str
    screen_position_quadrant: str            # e.g., "Top-Right", "Center"
    task_context: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bounding_box": list(self.bounding_box),
            "crop_base64": self.crop_base64,
            "parent_label": self.parent_label,
            "element_role": self.element_role,
            "screen_position_quadrant": self.screen_position_quadrant,
            "task_context": self.task_context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CropPacket:
        box = data["bounding_box"]
        return cls(
            bounding_box=(int(box[0]), int(box[1]), int(box[2]), int(box[3])),
            crop_base64=data["crop_base64"],
            parent_label=data.get("parent_label", ""),
            element_role=data.get("element_role", ""),
            screen_position_quadrant=data.get("screen_position_quadrant", ""),
            task_context=data.get("task_context", ""),
        )
