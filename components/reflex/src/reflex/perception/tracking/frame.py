"""Frame-bound identity, geometry context, quality, and truthful unsupported states.

Every interpretation this package produces is bound to a FrameIdentity that
preserves the full source/frame/pixel identity chain:

  source adapter -> frame (observation) id -> pixel sha256 + dimensions
  -> DPR / scroll-origin / viewport geometry -> quality + freshness

Nothing here captures pixels or calls models; it only carries provenance so
downstream tracking, escalation, and accounting can never detach a box, label,
or hypothesis from the frame it was derived from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import time

SCHEMA_VERSION = "reflex-tracking/1"


class FrameQuality(str, Enum):
    """Pixel/frame integrity state. Mirrors the builder ObservationQuality
    vocabulary and adds UNAVAILABLE for frames never received."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    CORRUPTED = "corrupted"
    PERMISSION_DENIED = "permission_denied"
    DISCONNECTED = "disconnected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Unsupported:
    """Truthful unsupported state: names the missing capability and why.

    Used whenever a frame, component, or transform cannot supply something a
    consumer asked for. Callers must propagate these instead of substituting
    defaults (e.g. DPR 1.0) or heuristics.
    """

    feature: str
    reason: str
    needed_by: str = ""
    frame_uid: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature": self.feature,
            "reason": self.reason,
            "needed_by": self.needed_by,
            "frame_uid": self.frame_uid,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Unsupported":
        return cls(
            feature=str(data["feature"]),
            reason=str(data.get("reason", "")),
            needed_by=str(data.get("needed_by", "")),
            frame_uid=str(data.get("frame_uid", "")),
        )


@dataclass(frozen=True)
class ViewportGeometry:
    """Coordinate-system context for a frame.

    All boxes in this package are in ORIGINAL PIXEL coordinates of the frame
    PNG. DPR and scroll origin translate between those pixels and CSS/layout
    coordinates. Unknown values stay None (never guessed); transforms that
    need them must return Unsupported instead.
    """

    width_px: int
    height_px: int
    dpr: Optional[float] = None
    scroll_origin_px: Tuple[int, int] = (0, 0)
    scroll_origin_known: bool = False
    viewport_css: Optional[Tuple[int, int]] = None

    def css_size(self) -> Tuple[Optional[Tuple[int, int]], Optional[Unsupported]]:
        """Viewport size in CSS px, or Unsupported when DPR is unknown."""
        if self.dpr is None or self.dpr <= 0:
            return None, Unsupported(
                feature="css_coordinates",
                reason="DPR unknown for this frame; refusing to assume 1.0",
                needed_by="css_size",
            )
        return (
            (int(round(self.width_px / self.dpr)), int(round(self.height_px / self.dpr))),
            None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width_px": self.width_px,
            "height_px": self.height_px,
            "dpr": self.dpr,
            "scroll_origin_px": list(self.scroll_origin_px),
            "scroll_origin_known": self.scroll_origin_known,
            "viewport_css": list(self.viewport_css) if self.viewport_css else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ViewportGeometry":
        origin = data.get("scroll_origin_px", [0, 0])
        css = data.get("viewport_css")
        return cls(
            width_px=int(data["width_px"]),
            height_px=int(data["height_px"]),
            dpr=data.get("dpr"),
            scroll_origin_px=(int(origin[0]), int(origin[1])),
            scroll_origin_known=bool(data.get("scroll_origin_known", False)),
            viewport_css=(int(css[0]), int(css[1])) if css else None,
        )


@dataclass(frozen=True)
class FrameIdentity:
    """Full identity chain for one frame of pixel evidence."""

    source_id: str  # e.g. builder source_adapter class + platform
    frame_id: str  # builder observation_id / replay frame_id / manifest file
    pixel_sha256: Optional[str]  # None only when pixels genuinely absent
    geometry: ViewportGeometry
    quality: FrameQuality = FrameQuality.HEALTHY
    freshness_duration_ms: float = 500.0
    capture_ms: float = 0.0  # source clock at capture
    received_ms: float = 0.0  # local clock at receipt
    modality_status: Dict[str, str] = field(default_factory=dict)
    error_message: Optional[str] = None
    # Epoch scoping: surface = source session/run; document = url/window/nav.
    surface_epoch: str = ""
    document_epoch: str = ""

    @property
    def uid(self) -> str:
        return f"{self.source_id}@{self.frame_id}"

    def is_fresh(self, now_ms: Optional[float] = None) -> bool:
        """Freshness against the RECEIPT clock. Frames dated ahead of the
        caller clock (negative age) are never fresh: clock skew or replay."""
        now = now_ms if now_ms is not None else time.time() * 1000.0
        age_ms = now - self.received_ms
        return 0.0 <= age_ms <= self.freshness_duration_ms

    def has_pixels(self) -> bool:
        return self.pixel_sha256 is not None and self.quality not in (
            FrameQuality.CORRUPTED,
            FrameQuality.UNAVAILABLE,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "source_id": self.source_id,
            "frame_id": self.frame_id,
            "uid": self.uid,
            "pixel_sha256": self.pixel_sha256,
            "geometry": self.geometry.to_dict(),
            "quality": self.quality.value,
            "freshness_duration_ms": self.freshness_duration_ms,
            "capture_ms": self.capture_ms,
            "received_ms": self.received_ms,
            "modality_status": dict(self.modality_status),
            "error_message": self.error_message,
            "surface_epoch": self.surface_epoch,
            "document_epoch": self.document_epoch,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FrameIdentity":
        raw_q = data.get("quality", FrameQuality.HEALTHY.value)
        quality = (
            FrameQuality(raw_q)
            if raw_q in FrameQuality._value2member_map_
            else FrameQuality(str(raw_q).lower())
        )
        return cls(
            source_id=str(data["source_id"]),
            frame_id=str(data["frame_id"]),
            pixel_sha256=data.get("pixel_sha256"),
            geometry=ViewportGeometry.from_dict(data["geometry"]),
            quality=quality,
            freshness_duration_ms=float(data.get("freshness_duration_ms", 500.0)),
            capture_ms=float(data.get("capture_ms", 0.0)),
            received_ms=float(data.get("received_ms", 0.0)),
            modality_status=dict(data.get("modality_status", {})),
            error_message=data.get("error_message"),
            surface_epoch=str(data.get("surface_epoch", "")),
            document_epoch=str(data.get("document_epoch", "")),
        )


def frame_from_observation_dict(
    obs: Dict[str, Any],
    *,
    pixel_sha256: Optional[str] = None,
    width_px: Optional[int] = None,
    height_px: Optional[int] = None,
    dpr: Optional[float] = None,
    surface_epoch: str = "",
    document_epoch: str = "",
    received_ms: Optional[float] = None,
) -> Tuple[FrameIdentity, List[Unsupported]]:
    """Build a FrameIdentity from a builder ObservationRecord.to_dict() payload.

    Takes plain dicts only (no builder import). Geometry absent from the
    payload stays unknown and is reported via Unsupported entries.
    """
    unsupported: List[Unsupported] = []
    meta = obs.get("platform_metadata", {}) or {}
    modality = dict(meta.get("modality_status", {}) or {})
    adapter = str(obs.get("source_adapter", "unknown"))
    platform = str(obs.get("platform", "unknown"))
    graph = obs.get("graph", {}) or {}
    viewport = graph.get("viewport_size", [0, 0])

    w = int(width_px) if width_px else int(viewport[0] or 0)
    h = int(height_px) if height_px else int(viewport[1] or 0)
    if not w or not h:
        unsupported.append(
            Unsupported(
                feature="frame_dimensions",
                reason="no decoded pixel dimensions supplied and graph viewport empty",
                needed_by="frame_from_observation_dict",
                frame_uid=str(obs.get("observation_id", "")),
            )
        )
    if dpr is None:
        unsupported.append(
            Unsupported(
                feature="dpr",
                reason="DPR not present in observation payload",
                needed_by="frame_from_observation_dict",
                frame_uid=str(obs.get("observation_id", "")),
            )
        )
    raw_q = str(obs.get("quality", FrameQuality.HEALTHY.value))
    quality = (
        FrameQuality(raw_q)
        if raw_q in FrameQuality._value2member_map_
        else FrameQuality.UNAVAILABLE
        if raw_q == "unavailable"
        else FrameQuality.DEGRADED
    )
    frame = FrameIdentity(
        source_id=f"{adapter}/{platform}",
        frame_id=str(obs.get("observation_id", "")),
        pixel_sha256=pixel_sha256,
        geometry=ViewportGeometry(width_px=w, height_px=h, dpr=dpr),
        quality=quality,
        freshness_duration_ms=float(obs.get("freshness_duration_ms", 500.0)),
        capture_ms=float(obs.get("timestamp_ms", 0.0)),
        received_ms=received_ms if received_ms is not None else time.time() * 1000.0,
        modality_status={str(k): str(v) for k, v in modality.items()},
        error_message=obs.get("error_message"),
        surface_epoch=surface_epoch,
        document_epoch=document_epoch,
    )
    return frame, unsupported
