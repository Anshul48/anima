"""Reflex Perception Vision: Sub-millisecond frame differencing, crop-and-route packaging, and visual grounding."""

from reflex.perception.vision.crop_router import CropAndRouteEngine, CropPacket
from reflex.perception.vision.differ import (
    OpenCVVisualDiffer,
    VisualDifferenceResult,
    VisualDifferPort,
)
from reflex.perception.vision.vision_grounder import (
    BaseVisionGrounder,
    MockVisionGrounder,
    VisualDetection,
    VisionGrounderPort,
)

__all__ = [
    "VisualDifferenceResult",
    "VisualDifferPort",
    "OpenCVVisualDiffer",
    "CropPacket",
    "CropAndRouteEngine",
    "VisualDetection",
    "VisionGrounderPort",
    "BaseVisionGrounder",
    "MockVisionGrounder",
]
