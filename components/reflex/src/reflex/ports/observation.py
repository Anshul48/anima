"""Reflex Perception Domain Port.

Abstract port defining the platform-independent perception contract:
platform observation -> normalized, timestamped, provenance-bearing observations
-> meaningful state/change representation -> queryable or streamed output for consumers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Sequence, Tuple
import uuid

from reflex.schemas.delta import OutcomeClass
from reflex.schemas.observation import (
    CorruptedObservationError,
    ObservationQuality,
    ObservationRecord,
    PerceptionCapabilities,
    PerceptionDelta,
    PerceptionError,
    PerceptionLifecycleState,
    SemanticChangeEvent,
    SemanticEventType,
    validate_screenshot_bytes,
)
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, ModalitySource, NodeRole, UIStateNode


class PixelModalityAssessment:
    """Outcome of one screenshot acquisition attempt plus decode validation."""

    def __init__(
        self,
        screenshot_bytes: Optional[bytes],
        status: str,
        error: Optional[str],
        decoded_size: Optional[Tuple[int, int]],
    ) -> None:
        self.screenshot_bytes = screenshot_bytes
        self.status = status
        self.error = error
        self.decoded_size = decoded_size


async def assess_pixel_modality(port: ObservationPort) -> PixelModalityAssessment:
    """Acquires and decode-validates one screenshot from any port.

    Shared by every capture_observation implementation so absent/empty/
    undecodable pixels are labeled identically everywhere.
    """
    try:
        screenshot_bytes = await port.capture_screenshot()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        return PixelModalityAssessment(None, f"unavailable: {error}", error, None)
    if screenshot_bytes is None:
        error = "Adapter returned no screenshot payload; tree-only observation."
        return PixelModalityAssessment(None, f"absent: {error}", error, None)
    if len(screenshot_bytes) == 0:
        error = "Adapter returned an empty screenshot payload; tree-only observation."
        return PixelModalityAssessment(screenshot_bytes, f"absent: {error}", error, None)
    try:
        width, height = validate_screenshot_bytes(screenshot_bytes)
        return PixelModalityAssessment(
            screenshot_bytes, f"ok: {width}x{height}", None, (width, height)
        )
    except CorruptedObservationError as exc:
        return PixelModalityAssessment(
            screenshot_bytes, f"corrupt: {exc}", str(exc), None
        )


def bind_pixel_geometry(
    decoded_size: Optional[Tuple[int, int]],
    declared_viewport: Tuple[int, int],
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Binds decoded pixel dimensions to the declared coordinate frame.

    Returns (ok, coordinate_transform, error). A mismatch degrades the
    observation: declared dimensions/DPR/transforms must explain the full
    decoded frame, never silently disagree with it. The transform records
    the observed scale either way; verified=True only on exact agreement.
    """
    declared = [int(declared_viewport[0]), int(declared_viewport[1])]
    if decoded_size is None:
        return True, {}, None
    width, height = decoded_size
    if [width, height] == declared:
        return True, {
            "declared_viewport": declared,
            "decoded_pixels": [width, height],
            "scale": [1.0, 1.0],
            "offset": [0, 0],
            "verified": True,
        }, None
    scale = [
        (width / declared[0]) if declared[0] else 0.0,
        (height / declared[1]) if declared[1] else 0.0,
    ]
    error = (
        f"Decoded pixels {width}x{height} do not match declared viewport "
        f"{declared[0]}x{declared[1]}; observed scale [{scale[0]:.4f}, {scale[1]:.4f}] "
        "is recorded but unverified."
    )
    return False, {
        "declared_viewport": declared,
        "decoded_pixels": [width, height],
        "scale": scale,
        "offset": [0, 0],
        "verified": False,
    }, error


class ObservationPort(ABC):
    """Abstract port for platform observation acquisition, delta computation, and state querying."""

    @property
    def capabilities(self) -> PerceptionCapabilities:
        """Returns declared capabilities of this platform observation adapter."""
        return PerceptionCapabilities(
            supports_accessibility_tree=True,
            supports_window_hierarchy=True,
            supports_dom_snapshot=True,
            supports_pixel_buffer=True,
            supports_bounding_box_extraction=True,
        )

    @property
    def lifecycle_state(self) -> PerceptionLifecycleState:
        """Returns the current lifecycle state of the adapter."""
        return getattr(self, "_lifecycle_state", PerceptionLifecycleState.CONNECTED)

    async def initialize(self) -> None:
        """Initializes adapter connection to underlying platform display/accessibility server."""
        self._lifecycle_state = PerceptionLifecycleState.CONNECTED

    async def teardown(self) -> None:
        """Gracefully disconnects and releases platform resources."""
        self._lifecycle_state = PerceptionLifecycleState.CLOSED

    def is_healthy(self) -> bool:
        """Returns True if the adapter is in a healthy, connected operational state."""
        return self.lifecycle_state in (
            PerceptionLifecycleState.CONNECTED,
            PerceptionLifecycleState.DEGRADED,
        )

    @abstractmethod
    async def capture_state(self) -> CanonicalUIGraph:
        """Captures the current canonical UI state graph from active surface."""
        ...

    @abstractmethod
    async def capture_screenshot(self) -> bytes:
        """Captures raw viewport screenshot bytes from active surface."""
        ...

    async def capture_observation(self) -> ObservationRecord:
        """Captures a normalized, timestamped, provenance-bearing observation record.

        Each modality reports truthful status: a failed or undecodable screenshot
        can never yield a healthy pixel observation. Tree-only results are labeled
        degraded with the pixel failure reason preserved. Decoded pixel
        dimensions must agree with the declared graph viewport or the
        observation degrades with an explicit recorded (unverified) transform.
        """
        capture_start_wall_ms = time.time() * 1000.0
        capture_start_mono = time.monotonic()
        graph = await self.capture_state()
        assessment = await assess_pixel_modality(self)
        modality_status: Dict[str, str] = {"tree": "ok", "screenshot": assessment.status}
        errors: List[str] = [assessment.error] if assessment.error else []
        _, transform, geometry_error = bind_pixel_geometry(
            assessment.decoded_size, graph.viewport_size
        )
        if geometry_error is not None:
            errors.append(geometry_error)

        now_ms = graph.timestamp_ms if graph else (time.time() * 1000.0)
        if assessment.status.startswith("corrupt"):
            quality = ObservationQuality.CORRUPTED
        elif errors or not self.is_healthy():
            quality = ObservationQuality.DEGRADED
        else:
            quality = ObservationQuality.HEALTHY

        metadata: Dict[str, Any] = {
            "adapter_class": self.__class__.__name__,
            "modality_status": modality_status,
            "coordinate_transform": transform,
            "capture_clocks": {
                "wall_start_ms": capture_start_wall_ms,
                "wall_end_ms": time.time() * 1000.0,
                "mono_elapsed_ms": (time.monotonic() - capture_start_mono) * 1000.0,
            },
        }
        return ObservationRecord(
            observation_id=str(uuid.uuid4()),
            timestamp_ms=now_ms,
            source_adapter=self.__class__.__name__,
            platform="generic",
            graph=graph,
            screenshot_bytes=assessment.screenshot_bytes,
            quality=quality,
            freshness_duration_ms=500.0,
            error_message="; ".join(errors) if errors else None,
            platform_metadata=metadata,
        )

    # --- Query Interface for Consumers (Jarvis, Entorhinal, System-2) ---

    @staticmethod
    def find_node_by_id(graph: CanonicalUIGraph, node_id: str) -> Optional[UIStateNode]:
        """Queries graph for node by stable ID."""
        return graph.nodes.get(node_id)

    @staticmethod
    def find_nodes_by_role(graph: CanonicalUIGraph, role: NodeRole) -> List[UIStateNode]:
        """Queries graph for all nodes matching given NodeRole."""
        return [n for n in graph.nodes.values() if n.role == role]

    @staticmethod
    def find_nodes_by_label(
        graph: CanonicalUIGraph, query: str, exact: bool = False
    ) -> List[UIStateNode]:
        """Queries graph for nodes with label matching string."""
        q = query.strip() if exact else query.strip().lower()
        results: List[UIStateNode] = []
        for n in graph.nodes.values():
            lbl = n.label if exact else n.label.lower()
            if exact and lbl == q:
                results.append(n)
            elif not exact and q in lbl:
                results.append(n)
        return results

    # --- Structural and Semantic Delta Computation ---

    @staticmethod
    def _source_binding(obs: ObservationRecord) -> Dict[str, Any]:
        """Authoritative source-identity keys bound to one observation."""
        meta = obs.platform_metadata or {}
        return {
            "source_adapter": obs.source_adapter,
            "platform": obs.platform,
            "target_id": meta.get("target_id"),
            "session_epoch": meta.get("session_epoch"),
        }

    @staticmethod
    def compute_delta(
        prev_obs: ObservationRecord,
        curr_obs: ObservationRecord,
        pixel_change_ratio: float = 0.0,
        changed_boxes: Optional[List[BoundingBox]] = None,
        pixel_status: Optional[str] = None,
    ) -> PerceptionDelta:
        """Computes structural and semantic difference between two observation snapshots.

        pixel_status describes whether a decoded pixel comparison was actually
        performed ("ok", "missing", "undecodable"); callers that supply no
        pixel comparison get "unknown". A source-identity change (adapter,
        target, or epoch) always emits SOURCE_CHANGED and can never be NOOP.
        """
        prev_nodes = prev_obs.graph.nodes
        curr_nodes = curr_obs.graph.nodes

        prev_ids = set(prev_nodes.keys())
        curr_ids = set(curr_nodes.keys())

        added_ids = curr_ids - prev_ids
        removed_ids = list(prev_ids - curr_ids)
        common_ids = prev_ids.intersection(curr_ids)

        added_nodes = [curr_nodes[nid] for nid in sorted(added_ids)]
        modified_nodes: List[Dict[str, Any]] = []
        semantic_events: List[SemanticChangeEvent] = []

        now_ms = curr_obs.timestamp_ms

        # Detect modifications and high-level semantic events
        for nid in sorted(common_ids):
            p_node = prev_nodes[nid]
            c_node = curr_nodes[nid]

            changes: Dict[str, Any] = {}
            if p_node.value != c_node.value:
                changes["value"] = {"old": p_node.value, "new": c_node.value}
                # Check for checkbox / toggle change
                if c_node.role in (NodeRole.CHECKBOX, NodeRole.TOGGLE):
                    semantic_events.append(
                        SemanticChangeEvent(
                            event_type=SemanticEventType.CHECKBOX_TOGGLED,
                            description=f"Checkbox '{c_node.label}' toggled from {p_node.value} to {c_node.value}",
                            target_node_id=nid,
                            previous_value=p_node.value,
                            current_value=c_node.value,
                            timestamp_ms=now_ms,
                        )
                    )
                else:
                    semantic_events.append(
                        SemanticChangeEvent(
                            event_type=SemanticEventType.VALUE_CHANGED,
                            description=f"Node '{c_node.label or nid}' value changed from '{p_node.value}' to '{c_node.value}'",
                            target_node_id=nid,
                            previous_value=p_node.value,
                            current_value=c_node.value,
                            timestamp_ms=now_ms,
                        )
                    )

            if p_node.label != c_node.label:
                changes["label"] = {"old": p_node.label, "new": c_node.label}

            if p_node.is_focused != c_node.is_focused:
                changes["is_focused"] = {"old": p_node.is_focused, "new": c_node.is_focused}
                direction = "gained" if c_node.is_focused else "lost"
                semantic_events.append(
                    SemanticChangeEvent(
                        event_type=SemanticEventType.FOCUS_CHANGED,
                        description=f"Node '{c_node.label or nid}' {direction} focus",
                        target_node_id=nid,
                        previous_value=p_node.is_focused,
                        current_value=c_node.is_focused,
                        timestamp_ms=now_ms,
                    )
                )

            if p_node.bounds != c_node.bounds:
                changes["bounds"] = {"old": p_node.bounds.to_dict(), "new": c_node.bounds.to_dict()}

            if p_node.parent_id != c_node.parent_id:
                changes["parent_id"] = {"old": p_node.parent_id, "new": c_node.parent_id}
            if tuple(p_node.children_ids) != tuple(c_node.children_ids):
                changes["children_ids"] = {
                    "old": list(p_node.children_ids),
                    "new": list(c_node.children_ids),
                }
            if p_node.source != c_node.source:
                old_source = p_node.source.value if isinstance(p_node.source, ModalitySource) else str(p_node.source)
                new_source = c_node.source.value if isinstance(c_node.source, ModalitySource) else str(c_node.source)
                changes["source"] = {"old": old_source, "new": new_source}

            state_field_changes: Dict[str, Any] = {}
            if p_node.is_enabled != c_node.is_enabled:
                changes["is_enabled"] = {"old": p_node.is_enabled, "new": c_node.is_enabled}
                state_field_changes["is_enabled"] = changes["is_enabled"]
            if p_node.is_clickable != c_node.is_clickable:
                changes["is_clickable"] = {"old": p_node.is_clickable, "new": c_node.is_clickable}
                state_field_changes["is_clickable"] = changes["is_clickable"]
            if p_node.is_editable != c_node.is_editable:
                changes["is_editable"] = {"old": p_node.is_editable, "new": c_node.is_editable}
                state_field_changes["is_editable"] = changes["is_editable"]
            if p_node.role != c_node.role:
                old_role = p_node.role.value if isinstance(p_node.role, NodeRole) else str(p_node.role)
                new_role = c_node.role.value if isinstance(c_node.role, NodeRole) else str(c_node.role)
                changes["role"] = {"old": old_role, "new": new_role}
                state_field_changes["role"] = changes["role"]
            if p_node.attributes != c_node.attributes:
                changes["attributes"] = {"old": dict(p_node.attributes), "new": dict(c_node.attributes)}
                state_field_changes["attributes"] = changes["attributes"]
            if state_field_changes:
                semantic_events.append(
                    SemanticChangeEvent(
                        event_type=SemanticEventType.STATE_CHANGED,
                        description=(
                            f"Node '{c_node.label or nid}' interaction state changed: "
                            + ", ".join(sorted(state_field_changes.keys()))
                        ),
                        target_node_id=nid,
                        timestamp_ms=now_ms,
                    )
                )

            if changes:
                modified_nodes.append({
                    "node_id": nid,
                    "role": c_node.role.value if isinstance(c_node.role, NodeRole) else str(c_node.role),
                    "changes": changes,
                })

        # Detect newly added warning banners, errors, or modals
        for node in added_nodes:
            lbl_lower = node.label.lower()
            if (
                "warning" in lbl_lower
                or "error" in lbl_lower
                or "alert" in lbl_lower
                or (node.role in (NodeRole.IMAGE, NodeRole.TEXT) and ("warn" in lbl_lower or "err" in lbl_lower))
            ):
                semantic_events.append(
                    SemanticChangeEvent(
                        event_type=SemanticEventType.WARNING_BANNER_SHOWN,
                        description=f"Warning/Error banner displayed: '{node.label}'",
                        target_node_id=node.node_id,
                        timestamp_ms=now_ms,
                    )
                )
            elif node.role == NodeRole.MODAL or "modal" in lbl_lower or "dialog" in lbl_lower:
                semantic_events.append(
                    SemanticChangeEvent(
                        event_type=SemanticEventType.MODAL_OPENED,
                        description=f"Modal window opened: '{node.label}'",
                        target_node_id=node.node_id,
                        timestamp_ms=now_ms,
                    )
                )

        # Detect URL / window title navigation
        if prev_obs.graph.active_window_title != curr_obs.graph.active_window_title:
            semantic_events.append(
                SemanticChangeEvent(
                    event_type=SemanticEventType.WINDOW_FOCUSED,
                    description=f"Window changed: '{prev_obs.graph.active_window_title}' -> '{curr_obs.graph.active_window_title}'",
                    previous_value=prev_obs.graph.active_window_title,
                    current_value=curr_obs.graph.active_window_title,
                    timestamp_ms=now_ms,
                )
            )

        if prev_obs.graph.url and curr_obs.graph.url and prev_obs.graph.url != curr_obs.graph.url:
            semantic_events.append(
                SemanticChangeEvent(
                    event_type=SemanticEventType.NAVIGATION,
                    description=f"Navigated: '{prev_obs.graph.url}' -> '{curr_obs.graph.url}'",
                    previous_value=prev_obs.graph.url,
                    current_value=curr_obs.graph.url,
                    timestamp_ms=now_ms,
                )
            )

        # Source-identity binding: restart/reset/target replacement must be
        # detected even when pixels and trees are identical.
        prev_binding = ObservationPort._source_binding(prev_obs)
        curr_binding = ObservationPort._source_binding(curr_obs)
        source_changed = prev_binding != curr_binding
        source_binding: Optional[Dict[str, Any]] = None
        if source_changed:
            source_binding = {
                "previous": prev_binding,
                "current": curr_binding,
                "changed": True,
            }
            semantic_events.append(
                SemanticChangeEvent(
                    event_type=SemanticEventType.SOURCE_CHANGED,
                    description=(
                        f"Source identity changed from {prev_binding} to {curr_binding}; "
                        "cached interpretations require revalidation"
                    ),
                    timestamp_ms=now_ms,
                )
            )

        # Outcome classification
        outcome = OutcomeClass.SUCCESS
        if any(e.event_type == SemanticEventType.MODAL_OPENED for e in semantic_events):
            outcome = OutcomeClass.MODAL_APPEARED
        elif any(e.event_type == SemanticEventType.NAVIGATION for e in semantic_events):
            outcome = OutcomeClass.NAVIGATION
        elif (
            not added_nodes
            and not removed_ids
            and not modified_nodes
            and pixel_change_ratio == 0.0
            and not source_changed
        ):
            outcome = OutcomeClass.NOOP

        return PerceptionDelta(
            source_snapshot_id=prev_obs.observation_id,
            target_snapshot_id=curr_obs.observation_id,
            timestamp_ms=now_ms,
            added_nodes=added_nodes,
            removed_node_ids=removed_ids,
            modified_nodes=modified_nodes,
            changed_bounding_boxes=list(changed_boxes or []),
            pixel_change_ratio=pixel_change_ratio,
            pixel_status=pixel_status if pixel_status is not None else "unknown",
            semantic_events=semantic_events,
            outcome_class=outcome,
            source_binding=source_binding,
        )

    # --- Streaming and Subscription ---

    @staticmethod
    def compare_pixel_evidence(
        prev_bytes: Optional[bytes], curr_bytes: Optional[bytes]
    ) -> Tuple[float, List[BoundingBox], str]:
        """Compares two decoded pixel payloads.

        Returns (ratio, changed_boxes, status) where status is "ok" when a
        decoded comparison ran, "missing" when either side has no pixels, and
        "undecodable" when present bytes cannot be decoded. Byte-identical
        frames short-circuit to ratio 0.0 without decoding.
        """
        if prev_bytes is None or curr_bytes is None:
            return 0.0, [], "missing"
        if prev_bytes == curr_bytes:
            return 0.0, [], "ok"
        try:
            from reflex.perception.vision.differ import OpenCVVisualDiffer

            result = OpenCVVisualDiffer().diff_frames(prev_bytes, curr_bytes)
            return result.pixel_change_ratio, list(result.changed_boxes), "ok"
        except Exception:
            return 0.0, [], "undecodable"

    async def observe_stream(
        self, interval_ms: float = 100.0, max_iterations: Optional[int] = None
    ) -> AsyncIterator[PerceptionDelta]:
        """Continuous polling generator streaming deltas to consumer.

        Each emitted delta carries a real decoded pixel comparison between
        the consecutive observations (or an explicit missing/undecodable
        pixel status); pixel-only changes are never reported as ratio 0.
        """
        prev_obs = await self.capture_observation()
        iterations = 0

        while True:
            if max_iterations is not None and iterations >= max_iterations:
                break
            await asyncio.sleep(interval_ms / 1000.0)
            curr_obs = await self.capture_observation()
            ratio, boxes, pixel_status = self.compare_pixel_evidence(
                prev_obs.screenshot_bytes, curr_obs.screenshot_bytes
            )
            delta = self.compute_delta(
                prev_obs, curr_obs,
                pixel_change_ratio=ratio,
                changed_boxes=boxes,
                pixel_status=pixel_status,
            )
            prev_obs = curr_obs
            iterations += 1
            yield delta
