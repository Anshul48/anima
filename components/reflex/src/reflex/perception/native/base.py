"""Base interfaces, data structures, and configuration for native OS observation providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Tuple

import uuid

from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import (
    ObservationPort,
    assess_pixel_modality,
    bind_pixel_geometry,
)
from reflex.schemas.observation import (
    ObservationQuality,
    ObservationRecord,
    PerceptionCapabilities,
    PerceptionLifecycleState,
)
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)


@dataclass(frozen=True)
class NativeObservationConfig:
    """Configuration options for native desktop OS observation adapters."""
    max_depth: int = 50
    include_invisible: bool = False
    cache_subtrees: bool = True
    timeout_ms: float = 1000.0
    prefetch_properties: List[str] = field(default_factory=list)
    target_window_title: Optional[str] = None
    target_process_id: Optional[int] = None
    enable_mock_fallback: bool = True
    screen_width: int = 1920
    screen_height: int = 1080

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_depth": self.max_depth,
            "include_invisible": self.include_invisible,
            "cache_subtrees": self.cache_subtrees,
            "timeout_ms": self.timeout_ms,
            "prefetch_properties": list(self.prefetch_properties),
            "target_window_title": self.target_window_title,
            "target_process_id": self.target_process_id,
            "enable_mock_fallback": self.enable_mock_fallback,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NativeObservationConfig:
        return cls(
            max_depth=int(data.get("max_depth", 50)),
            include_invisible=bool(data.get("include_invisible", False)),
            cache_subtrees=bool(data.get("cache_subtrees", True)),
            timeout_ms=float(data.get("timeout_ms", 1000.0)),
            prefetch_properties=list(data.get("prefetch_properties", [])),
            target_window_title=data.get("target_window_title"),
            target_process_id=data.get("target_process_id"),
            enable_mock_fallback=bool(data.get("enable_mock_fallback", True)),
            screen_width=int(data.get("screen_width", 1920)),
            screen_height=int(data.get("screen_height", 1080)),
        )


@dataclass(frozen=True)
class NativeUIElement:
    """Normalized intermediate representation of a native OS UI element."""
    element_id: str
    name: str = ""
    role: str = ""
    bounds: BoundingBox = field(default_factory=lambda: BoundingBox(0, 0, 0, 0))
    value: str = ""
    is_clickable: bool = True
    is_editable: bool = False
    is_focused: bool = False
    is_enabled: bool = True
    is_visible: bool = True
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    control_type: str = ""
    handle: Optional[int] = None
    process_id: Optional[int] = None
    window_title: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_ui_state_node(
        self,
        mapped_role: NodeRole = NodeRole.UNKNOWN,
        source: ModalitySource = ModalitySource.UIA,
    ) -> UIStateNode:
        """Converts native element into canonical UIStateNode."""
        node_attrs = dict(self.attributes)
        if self.control_type:
            node_attrs["control_type"] = self.control_type
        if self.handle is not None:
            node_attrs["handle"] = self.handle
        if self.process_id is not None:
            node_attrs["process_id"] = self.process_id
        if self.window_title is not None:
            node_attrs["window_title"] = self.window_title

        return UIStateNode(
            node_id=self.element_id,
            role=mapped_role,
            bounds=self.bounds,
            label=self.name,
            value=self.value,
            is_clickable=self.is_clickable,
            is_editable=self.is_editable,
            is_focused=self.is_focused,
            is_enabled=self.is_enabled,
            parent_id=self.parent_id,
            children_ids=list(self.children_ids),
            source=source,
            confidence=1.0,
            attributes=node_attrs,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_id": self.element_id,
            "name": self.name,
            "role": self.role,
            "bounds": self.bounds.to_dict(),
            "value": self.value,
            "is_clickable": self.is_clickable,
            "is_editable": self.is_editable,
            "is_focused": self.is_focused,
            "is_enabled": self.is_enabled,
            "is_visible": self.is_visible,
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "control_type": self.control_type,
            "handle": self.handle,
            "process_id": self.process_id,
            "window_title": self.window_title,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NativeUIElement:
        bounds_data = data.get("bounds", {"x1": 0, "y1": 0, "x2": 0, "y2": 0})
        return cls(
            element_id=data["element_id"],
            name=data.get("name", ""),
            role=data.get("role", ""),
            bounds=BoundingBox.from_dict(bounds_data),
            value=data.get("value", ""),
            is_clickable=bool(data.get("is_clickable", True)),
            is_editable=bool(data.get("is_editable", False)),
            is_focused=bool(data.get("is_focused", False)),
            is_enabled=bool(data.get("is_enabled", True)),
            is_visible=bool(data.get("is_visible", True)),
            parent_id=data.get("parent_id"),
            children_ids=list(data.get("children_ids", [])),
            control_type=data.get("control_type", ""),
            handle=data.get("handle"),
            process_id=data.get("process_id"),
            window_title=data.get("window_title"),
            attributes=data.get("attributes", {}),
        )


class NativeObservationPort(ObservationPort, ABC):
    """Abstract port for extracting native desktop OS accessibility graphs and viewport buffers."""

    def __init__(
        self,
        config: Optional[NativeObservationConfig] = None,
        clock: Optional[ClockPort] = None,
    ) -> None:
        self.config = config or NativeObservationConfig()
        self.clock = clock or SystemClock()
        self._lifecycle_state: PerceptionLifecycleState = PerceptionLifecycleState.UNINITIALIZED

    @property
    def capabilities(self) -> PerceptionCapabilities:
        return PerceptionCapabilities(
            supports_accessibility_tree=True,
            supports_window_hierarchy=True,
            supports_dom_snapshot=False,
            supports_pixel_buffer=True,
            supports_change_stream=True,
            supports_continuous_polling=True,
            supports_bounding_box_extraction=True,
            supported_modalities=[ModalitySource.UIA],
        )

    @property
    def lifecycle_state(self) -> PerceptionLifecycleState:
        return self._lifecycle_state

    async def initialize(self) -> None:
        self._lifecycle_state = PerceptionLifecycleState.CONNECTED

    async def teardown(self) -> None:
        self._lifecycle_state = PerceptionLifecycleState.CLOSED

    @abstractmethod
    def capture_active_window(self) -> CanonicalUIGraph:
        """Extracts accessibility graph from currently focused native window."""
        ...

    @abstractmethod
    def list_open_windows(self) -> List[str]:
        """Lists active top-level native window titles and process names."""
        ...

    @abstractmethod
    def get_focused_window_title(self) -> Optional[str]:
        """Returns the title of the currently focused native window."""
        ...

    @abstractmethod
    def get_focused_element(self) -> Optional[NativeUIElement]:
        """Returns the currently focused native UI element, if any."""
        ...

    async def capture_state(self) -> CanonicalUIGraph:
        """Captures the current canonical UI state graph from the active native window/desktop."""
        return self.capture_active_window()

    async def capture_observation(self) -> ObservationRecord:
        """Captures a normalized, timestamped, provenance-bearing observation record.

        Reports per-modality status: failed or undecodable pixels degrade the
        observation instead of silently yielding a healthy record.
        """
        capture_start_wall_ms = time.time() * 1000.0
        capture_start_mono = time.monotonic()
        timestamp_ms = self.clock.now_ms()
        graph = self.capture_active_window()
        assessment = await assess_pixel_modality(self)
        modality_status = {"tree": "ok", "screenshot": assessment.status}
        errors = [assessment.error] if assessment.error else []
        _, transform, geometry_error = bind_pixel_geometry(
            assessment.decoded_size, graph.viewport_size
        )
        if geometry_error is not None:
            errors.append(geometry_error)

        if assessment.status.startswith("corrupt"):
            quality = ObservationQuality.CORRUPTED
        elif errors or not self.is_healthy():
            quality = ObservationQuality.DEGRADED
        else:
            quality = ObservationQuality.HEALTHY

        return ObservationRecord(
            observation_id=str(uuid.uuid4()),
            timestamp_ms=timestamp_ms,
            source_adapter="native_os",
            platform="native",
            graph=graph,
            screenshot_bytes=assessment.screenshot_bytes,
            quality=quality,
            freshness_duration_ms=500.0,
            error_message="; ".join(errors) if errors else None,
            platform_metadata={
                "focused_window": self.get_focused_window_title(),
                "open_windows_count": len(self.list_open_windows()),
                "modality_status": modality_status,
                "coordinate_transform": transform,
                "capture_clocks": {
                    "wall_start_ms": capture_start_wall_ms,
                    "wall_end_ms": time.time() * 1000.0,
                    "mono_elapsed_ms": (time.monotonic() - capture_start_mono) * 1000.0,
                },
            },
        )

    @abstractmethod
    async def capture_screenshot(self) -> bytes:
        """Captures raw viewport screenshot bytes from the active display/window."""
        ...
