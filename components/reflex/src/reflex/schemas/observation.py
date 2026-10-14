"""Reflex Perception Domain Schemas.

Defines the normalized perception contract:
platform observation -> normalized, timestamped, provenance-bearing observations
-> meaningful state/change representation -> queryable or streamed output for consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import io
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

from reflex.schemas.delta import OutcomeClass
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
    freeze_evidence,
    thaw_evidence,
)


class PerceptionLifecycleState(str, Enum):
    """Lifecycle state of an observation adapter."""
    UNINITIALIZED = "uninitialized"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CLOSED = "closed"


class ObservationQuality(str, Enum):
    """Data quality and integrity state of a captured observation."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    CORRUPTED = "corrupted"
    PERMISSION_DENIED = "permission_denied"
    DISCONNECTED = "disconnected"


class PerceptionError(Exception):
    """Base exception for perception domain errors."""
    pass


class CorruptedObservationError(PerceptionError):
    """Raised when an observation frame or structure payload is corrupt or undecodable."""
    pass


class PermissionDeniedPerceptionError(PerceptionError):
    """Raised when platform permissions (e.g. screen recording, accessibility API access) are missing."""
    pass


class DisplayDisconnectedPerceptionError(PerceptionError):
    """Raised when the target display, session bus, or remote debugging port is disconnected."""
    pass


class PerceptionTimeoutError(PerceptionError):
    """Raised when acquiring an observation exceeds the allocated deadline."""
    pass


@dataclass(frozen=True)
class PerceptionCapabilities:
    """Declared capabilities supported by a platform observation adapter."""
    supports_accessibility_tree: bool = False
    supports_window_hierarchy: bool = False
    supports_dom_snapshot: bool = False
    supports_pixel_buffer: bool = False
    supports_change_stream: bool = False
    supports_continuous_polling: bool = False
    supports_bounding_box_extraction: bool = True
    supported_modalities: List[ModalitySource] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supports_accessibility_tree": self.supports_accessibility_tree,
            "supports_window_hierarchy": self.supports_window_hierarchy,
            "supports_dom_snapshot": self.supports_dom_snapshot,
            "supports_pixel_buffer": self.supports_pixel_buffer,
            "supports_change_stream": self.supports_change_stream,
            "supports_continuous_polling": self.supports_continuous_polling,
            "supports_bounding_box_extraction": self.supports_bounding_box_extraction,
            "supported_modalities": [
                m.value if isinstance(m, ModalitySource) else str(m)
                for m in self.supported_modalities
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PerceptionCapabilities:
        raw_modalities = data.get("supported_modalities", [])
        modalities = [
            ModalitySource(m) if m in ModalitySource._value2member_map_ else ModalitySource(str(m).lower())
            for m in raw_modalities
        ]
        return cls(
            supports_accessibility_tree=bool(data.get("supports_accessibility_tree", False)),
            supports_window_hierarchy=bool(data.get("supports_window_hierarchy", False)),
            supports_dom_snapshot=bool(data.get("supports_dom_snapshot", False)),
            supports_pixel_buffer=bool(data.get("supports_pixel_buffer", False)),
            supports_change_stream=bool(data.get("supports_change_stream", False)),
            supports_continuous_polling=bool(data.get("supports_continuous_polling", False)),
            supports_bounding_box_extraction=bool(data.get("supports_bounding_box_extraction", True)),
            supported_modalities=modalities,
        )


class SemanticEventType(str, Enum):
    """Semantic UI event classifications derived from structural and visual deltas."""
    CLICK = "click"
    VALUE_CHANGED = "value_changed"
    CHECKBOX_TOGGLED = "checkbox_toggled"
    RADIO_SELECTED = "radio_selected"
    MODAL_OPENED = "modal_opened"
    MODAL_DISMISSED = "modal_dismissed"
    WARNING_BANNER_SHOWN = "warning_banner_shown"
    ERROR_MESSAGE_DISPLAYED = "error_message_displayed"
    NAVIGATION = "navigation"
    WINDOW_FOCUSED = "window_focused"
    FOCUS_CHANGED = "focus_changed"
    STATE_CHANGED = "state_changed"
    SOURCE_CHANGED = "source_changed"
    NOOP = "noop"


@dataclass(frozen=True)
class SemanticChangeEvent:
    """High-level semantic event inferred between observation frames."""
    event_type: SemanticEventType
    description: str
    target_node_id: Optional[str] = None
    previous_value: Optional[Any] = None
    current_value: Optional[Any] = None
    timestamp_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value if isinstance(self.event_type, SemanticEventType) else str(self.event_type),
            "description": self.description,
            "target_node_id": self.target_node_id,
            "previous_value": self.previous_value,
            "current_value": self.current_value,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SemanticChangeEvent:
        raw_type = data.get("event_type", SemanticEventType.NOOP.value)
        event_type = (
            SemanticEventType(raw_type)
            if raw_type in SemanticEventType._value2member_map_
            else SemanticEventType(str(raw_type).lower())
        )
        return cls(
            event_type=event_type,
            description=str(data.get("description", "")),
            target_node_id=data.get("target_node_id"),
            previous_value=data.get("previous_value"),
            current_value=data.get("current_value"),
            timestamp_ms=float(data.get("timestamp_ms", 0.0)),
        )


@dataclass(frozen=True)
class ObservationRecord:
    """Normalized, timestamped, provenance-bearing observation snapshot of the platform surface."""
    observation_id: str
    timestamp_ms: float
    source_adapter: str
    platform: str
    graph: CanonicalUIGraph
    screenshot_bytes: Optional[bytes] = None
    quality: ObservationQuality = ObservationQuality.HEALTHY
    freshness_duration_ms: float = 500.0
    error_message: Optional[str] = None
    platform_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "platform_metadata", freeze_evidence(dict(self.platform_metadata)))

    def is_fresh(self, current_time_ms: Optional[float] = None) -> bool:
        """Determines if the observation record is still fresh given its freshness window.

        A frame dated ahead of the caller's clock (negative age) is never fresh:
        it indicates clock skew or a replay-domain timestamp, not a live frame.
        """
        now = current_time_ms if current_time_ms is not None else (time.time() * 1000.0)
        age_ms = now - self.timestamp_ms
        return 0.0 <= age_ms <= self.freshness_duration_ms

    def to_dict(self, include_screenshot_bytes: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "observation_id": self.observation_id,
            "timestamp_ms": self.timestamp_ms,
            "source_adapter": self.source_adapter,
            "platform": self.platform,
            "graph": self.graph.to_dict(),
            "quality": self.quality.value if isinstance(self.quality, ObservationQuality) else str(self.quality),
            "freshness_duration_ms": self.freshness_duration_ms,
            "error_message": self.error_message,
            "platform_metadata": thaw_evidence(self.platform_metadata),
        }
        if include_screenshot_bytes and self.screenshot_bytes is not None:
            payload["screenshot_bytes_length"] = len(self.screenshot_bytes)
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any], screenshot_bytes: Optional[bytes] = None) -> ObservationRecord:
        raw_quality = data.get("quality", ObservationQuality.HEALTHY.value)
        quality = (
            ObservationQuality(raw_quality)
            if raw_quality in ObservationQuality._value2member_map_
            else ObservationQuality(str(raw_quality).lower())
        )
        return cls(
            observation_id=str(data.get("observation_id", str(uuid.uuid4()))),
            timestamp_ms=float(data.get("timestamp_ms", 0.0)),
            source_adapter=str(data.get("source_adapter", "unknown")),
            platform=str(data.get("platform", "unknown")),
            graph=CanonicalUIGraph.from_dict(data.get("graph", {})),
            screenshot_bytes=screenshot_bytes,
            quality=quality,
            freshness_duration_ms=float(data.get("freshness_duration_ms", 500.0)),
            error_message=data.get("error_message"),
            platform_metadata=dict(data.get("platform_metadata", {})),
        )


def validate_screenshot_bytes(data: bytes) -> Tuple[int, int]:
    """Decodes claimed pixel evidence and returns its (width, height).

    Raises CorruptedObservationError when the payload is empty or undecodable,
    so undecodable bytes can never ship as healthy pixel evidence.
    """
    from PIL import Image

    if not data:
        raise CorruptedObservationError("Screenshot payload is empty; no pixel evidence present.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return (int(image.width), int(image.height))
    except CorruptedObservationError:
        raise
    except Exception as exc:
        raise CorruptedObservationError(
            f"Screenshot payload of {len(data)} bytes failed to decode as an image: {exc}"
        ) from exc


@dataclass(frozen=True)
class PerceptionDelta:
    """Semantic and structural difference between ObservationRecord t and t+1."""
    source_snapshot_id: str
    target_snapshot_id: str
    timestamp_ms: float
    added_nodes: List[UIStateNode] = field(default_factory=list)
    removed_node_ids: List[str] = field(default_factory=list)
    modified_nodes: List[Dict[str, Any]] = field(default_factory=list)
    changed_bounding_boxes: List[BoundingBox] = field(default_factory=list)
    pixel_change_ratio: float = 0.0
    pixel_status: str = "unknown"
    semantic_events: List[SemanticChangeEvent] = field(default_factory=list)
    outcome_class: OutcomeClass = OutcomeClass.SUCCESS
    source_binding: Optional[Dict[str, Any]] = None

    @property
    def is_static(self) -> bool:
        return (
            len(self.added_nodes) == 0
            and len(self.removed_node_ids) == 0
            and len(self.modified_nodes) == 0
            and len(self.changed_bounding_boxes) == 0
            and len(self.semantic_events) == 0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_snapshot_id": self.source_snapshot_id,
            "target_snapshot_id": self.target_snapshot_id,
            "timestamp_ms": self.timestamp_ms,
            "added_nodes": [n.to_dict() for n in self.added_nodes],
            "removed_node_ids": list(self.removed_node_ids),
            "modified_nodes": list(self.modified_nodes),
            "changed_bounding_boxes": [b.to_dict() for b in self.changed_bounding_boxes],
            "pixel_change_ratio": self.pixel_change_ratio,
            "pixel_status": self.pixel_status,
            "semantic_events": [e.to_dict() for e in self.semantic_events],
            "outcome_class": self.outcome_class.value if isinstance(self.outcome_class, OutcomeClass) else str(self.outcome_class),
            "is_static": self.is_static,
            "source_binding": self.source_binding,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PerceptionDelta:
        raw_outcome = data.get("outcome_class", OutcomeClass.SUCCESS.value)
        outcome_class = (
            OutcomeClass(raw_outcome)
            if raw_outcome in OutcomeClass._value2member_map_
            else OutcomeClass(str(raw_outcome).lower())
        )
        added_nodes = [UIStateNode.from_dict(n) for n in data.get("added_nodes", [])]
        boxes = [BoundingBox.from_dict(b) for b in data.get("changed_bounding_boxes", [])]
        events = [SemanticChangeEvent.from_dict(e) for e in data.get("semantic_events", [])]

        return cls(
            source_snapshot_id=str(data.get("source_snapshot_id", "")),
            target_snapshot_id=str(data.get("target_snapshot_id", "")),
            timestamp_ms=float(data.get("timestamp_ms", 0.0)),
            added_nodes=added_nodes,
            removed_node_ids=list(data.get("removed_node_ids", [])),
            modified_nodes=list(data.get("modified_nodes", [])),
            changed_bounding_boxes=boxes,
            pixel_change_ratio=float(data.get("pixel_change_ratio", 0.0)),
            pixel_status=str(data.get("pixel_status", "unknown")),
            semantic_events=events,
            outcome_class=outcome_class,
            source_binding=data.get("source_binding"),
        )

    def to_state_delta(self) -> StateDelta:
        """Converts perception delta into canonical StateDelta for episodic memory."""
        from reflex.schemas.delta import StateDelta
        return StateDelta(
            added_nodes=[n.node_id for n in self.added_nodes],
            removed_nodes=list(self.removed_node_ids),
            modified_nodes=[
                m.get("node_id", "")
                if isinstance(m, dict) else getattr(m, "node_id", str(m))
                for m in self.modified_nodes
            ],
            pixel_change_ratio=self.pixel_change_ratio,
            changed_bounding_boxes=[(b.x1, b.y1, b.x2, b.y2) for b in self.changed_bounding_boxes],
            outcome_class=self.outcome_class,
        )
