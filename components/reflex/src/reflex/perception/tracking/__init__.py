"""reflex_tracking: frame-bound perception interfaces, adapters, tracking, escalation.

Isolated specialist package (stdlib only). Drop-in target in the builder
candidate: src/reflex/perception/tracking/ (see patch/INTEGRATION.md).
"""

from .accounting import ResourceLedger
from .adapters import (
    MODEL_RUN_SCHEMA,
    FrameBindingError,
    ModelRunAdapter,
    png_dimensions,
    sha256_file,
    static_parse_to_node_dicts,
)
from .escalation import (
    Decision,
    EscalationBudget,
    EscalationConfig,
    EscalationDecision,
    EscalationLevel,
    EscalationPolicy,
    EscalationTrigger,
)
from .frame import (
    SCHEMA_VERSION,
    FrameIdentity,
    FrameQuality,
    Unsupported,
    ViewportGeometry,
    frame_from_observation_dict,
)
from .interfaces import (
    ComponentState,
    FunctionHypothesis,
    HypothesisStatus,
    LayoutContext,
    OCRSpan,
    OverlapHypothesis,
    RegionProposal,
    StaticParse,
)
from .tracking import (
    InvalidationReason,
    StaleTarget,
    Track,
    TrackingThresholds,
    TrackStatus,
    TrackStore,
    TrackUpdate,
)
from .transforms import (
    CropView,
    TransformRecord,
    box_area,
    box_iou,
    clamp_box,
    containment,
    css_to_frame,
    expand_box,
    frame_to_css,
    is_valid_box,
    make_crop,
    pairwise_overlaps,
    scroll_compensate,
)

__version__ = "0.1.0"
__all__ = [
    "SCHEMA_VERSION", "MODEL_RUN_SCHEMA",
    "ResourceLedger",
    "FrameBindingError", "ModelRunAdapter", "png_dimensions", "sha256_file",
    "static_parse_to_node_dicts",
    "Decision", "EscalationBudget", "EscalationConfig", "EscalationDecision",
    "EscalationLevel", "EscalationPolicy", "EscalationTrigger",
    "FrameIdentity", "FrameQuality", "Unsupported", "ViewportGeometry",
    "frame_from_observation_dict",
    "ComponentState", "FunctionHypothesis", "HypothesisStatus", "LayoutContext",
    "OCRSpan", "OverlapHypothesis", "RegionProposal", "StaticParse",
    "InvalidationReason", "StaleTarget", "Track", "TrackingThresholds",
    "TrackStatus", "TrackStore", "TrackUpdate",
    "CropView", "TransformRecord",
    "box_area", "box_iou", "clamp_box", "containment", "css_to_frame",
    "expand_box", "frame_to_css", "is_valid_box", "make_crop",
    "pairwise_overlaps", "scroll_compensate",
]
