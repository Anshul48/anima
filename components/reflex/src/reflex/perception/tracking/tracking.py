"""Short-horizon tracking with dependency-aware invalidation.

Epoch-scoped tracks over frame-bound StaticParse outputs. Matching is greedy
on IoU + text agreement; anything uncertain becomes UNCERTAIN (never
silently carried). Invalidation triggers:

- source-epoch change -> full resync (all tracks invalidated)
- document-epoch change (navigation) -> full resync
- scroll-origin shift -> compensate when BOTH origins known, else UNCERTAIN
- overlay/modal covering a track -> INVALIDATED (occlusion)
- attribute hints (enabled/clickable/value per node) -> UNCERTAIN refresh
- pixel-change ratio in track box above threshold -> UNCERTAIN dynamic
- movement beyond match threshold -> UNCERTAIN moved (predicted box kept
  separate from any authorized target)

Stale-target rule: TrackStore.authorize_target returns a box ONLY for a
track ACTIVE on the LATEST frame. Reuse never turns an old box into an
authorized current target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .frame import FrameIdentity
from .interfaces import Box, RegionProposal, StaticParse
from .transforms import box_area, box_iou, containment, scroll_compensate


class TrackStatus(str, Enum):
    ACTIVE = "active"  # matched on the latest frame
    UNCERTAIN = "uncertain"  # needs refresh; box is a prediction, not a target
    INVALIDATED = "invalidated"  # terminally dropped with reason
    LOST = "lost"  # no match for too many frames


class InvalidationReason(str, Enum):
    EPOCH_CHANGE = "epoch_change"
    DOCUMENT_NAVIGATION = "document_navigation"
    SCROLL_UNKNOWN = "scroll_unknown"
    OVERLAY_OCCLUSION = "overlay_occlusion"
    ATTRIBUTE_CHANGE = "attribute_change"
    DYNAMIC_PIXELS = "dynamic_pixels"
    MOVED = "moved"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    TINY = "tiny"  # informational flag, not itself invalidating
    QUALITY_FAULT = "quality_fault"


@dataclass(frozen=True)
class TrackingThresholds:
    match_iou: float = 0.5  # >= this IoU => candidate match
    ambiguity_margin: float = 0.1  # 2nd-best within margin => ambiguous
    move_iou: float = 0.2  # best IoU in [move_iou, match_iou) => MOVED
    containment_match: float = 0.7  # containment fallback for resize cases
    overlay_containment: float = 0.6  # modal covers this fraction => occluded
    dynamic_pixel_ratio: float = 0.25  # per-track pixel change => dynamic
    tiny_area_px: float = 144.0  # 12x12: below => tiny flag
    max_missing_frames: int = 3  # then LOST
    text_bonus: float = 0.15  # IoU bonus for exact OCR-label agreement

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_iou": self.match_iou,
            "ambiguity_margin": self.ambiguity_margin,
            "move_iou": self.move_iou,
            "containment_match": self.containment_match,
            "overlay_containment": self.overlay_containment,
            "dynamic_pixel_ratio": self.dynamic_pixel_ratio,
            "tiny_area_px": self.tiny_area_px,
            "max_missing_frames": self.max_missing_frames,
            "text_bonus": self.text_bonus,
        }


@dataclass
class TrackObservation:
    frame_uid: str
    box_xyxy: Box
    text: str = ""
    score: Optional[float] = None
    pixel_sha256: Optional[str] = None


@dataclass
class Track:
    track_id: str
    surface_epoch: str
    document_epoch: str
    status: TrackStatus = TrackStatus.ACTIVE
    observations: List[TrackObservation] = field(default_factory=list)
    missing_frames: int = 0
    invalidation_reason: Optional[InvalidationReason] = None
    invalidation_detail: str = ""
    predicted_box_xyxy: Optional[Box] = None  # UNCERTAIN prediction, never a target
    tiny: bool = False
    created_frame_uid: str = ""
    last_frame_uid: str = ""

    @property
    def current_box(self) -> Optional[Box]:
        if self.observations:
            return self.observations[-1].box_xyxy
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "surface_epoch": self.surface_epoch,
            "document_epoch": self.document_epoch,
            "status": self.status.value,
            "observations": [
                {
                    "frame_uid": o.frame_uid,
                    "box_xyxy": list(o.box_xyxy),
                    "text": o.text,
                    "score": o.score,
                    "pixel_sha256": o.pixel_sha256,
                }
                for o in self.observations
            ],
            "missing_frames": self.missing_frames,
            "invalidation_reason": self.invalidation_reason.value if self.invalidation_reason else None,
            "invalidation_detail": self.invalidation_detail,
            "predicted_box_xyxy": list(self.predicted_box_xyxy) if self.predicted_box_xyxy else None,
            "tiny": self.tiny,
            "created_frame_uid": self.created_frame_uid,
            "last_frame_uid": self.last_frame_uid,
        }


@dataclass(frozen=True)
class StaleTarget:
    """Returned when no current target can be authorized. Never a box."""

    track_id: str
    reason: str
    last_frame_uid: str
    latest_frame_uid: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "reason": self.reason,
            "last_frame_uid": self.last_frame_uid,
            "latest_frame_uid": self.latest_frame_uid,
        }


@dataclass(frozen=True)
class TrackUpdate:
    frame_uid: str
    matched: List[Tuple[str, str]]  # (track_id, region_id)
    created: List[Tuple[str, str]]
    uncertain: List[Tuple[str, str]]  # (track_id, reason)
    invalidated: List[Tuple[str, str]]
    lost: List[str]
    full_resync: bool
    resync_reason: str
    thresholds: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_uid": self.frame_uid,
            "matched": [list(p) for p in self.matched],
            "created": [list(p) for p in self.created],
            "uncertain": [list(p) for p in self.uncertain],
            "invalidated": [list(p) for p in self.invalidated],
            "lost": list(self.lost),
            "full_resync": self.full_resync,
            "resync_reason": self.resync_reason,
            "thresholds": dict(self.thresholds),
        }


def _text_agreement(a: str, b: str) -> bool:
    na, nb = a.strip().lower(), b.strip().lower()
    return bool(na) and na == nb


class TrackStore:
    """Epoch-scoped short-horizon track state."""

    def __init__(self, thresholds: Optional[TrackingThresholds] = None) -> None:
        self.thresholds = thresholds or TrackingThresholds()
        self.tracks: Dict[str, Track] = {}
        self.latest_frame_uid: str = ""
        self.surface_epoch: str = ""
        self.document_epoch: str = ""
        self._next_id = 0
        self.history: List[TrackUpdate] = []

    def _new_track_id(self) -> str:
        self._next_id += 1
        return f"trk:{self.surface_epoch or 'e0'}:{self._next_id}"

    def authorize_target(self, track_id: str) -> Tuple[Optional[Box], Optional[StaleTarget]]:
        """Return the target box ONLY if the track is ACTIVE on the latest frame."""
        track = self.tracks.get(track_id)
        if track is None:
            return None, StaleTarget(
                track_id=track_id,
                reason="unknown track",
                last_frame_uid="",
                latest_frame_uid=self.latest_frame_uid,
            )
        if track.status != TrackStatus.ACTIVE or track.last_frame_uid != self.latest_frame_uid:
            return None, StaleTarget(
                track_id=track_id,
                reason=f"status={track.status.value} (need ACTIVE on latest frame)",
                last_frame_uid=track.last_frame_uid,
                latest_frame_uid=self.latest_frame_uid,
            )
        box = track.current_box
        if box is None:
            return None, StaleTarget(
                track_id=track_id,
                reason="no observation",
                last_frame_uid=track.last_frame_uid,
                latest_frame_uid=self.latest_frame_uid,
            )
        return box, None

    def update(
        self,
        parse: StaticParse,
        *,
        overlay_boxes: Optional[List[Box]] = None,
        attribute_hints: Optional[Dict[str, Dict[str, Any]]] = None,
        pixel_change_by_region: Optional[Dict[str, float]] = None,
        track_text_by_id: Optional[Dict[str, str]] = None,
    ) -> TrackUpdate:
        """Advance tracks to a new frame-bound parse.

        Hints (all optional, keyed by region_id unless noted):
        - overlay_boxes: modal/overlay boxes in frame pixels.
        - attribute_hints: region_id -> changed attribute names (from tree delta).
        - pixel_change_by_region: region_id -> pixel change ratio in that box.
        - track_text_by_id: override text memory per track (testing hook).
        """
        frame = parse.frame
        thr = self.thresholds
        overlay_boxes = overlay_boxes or []
        attribute_hints = attribute_hints or {}
        pixel_change_by_region = pixel_change_by_region or {}

        # ---- epoch gates: full resync, never carry-over ----
        if self.latest_frame_uid and frame.surface_epoch != self.surface_epoch:
            return self._full_resync(parse, InvalidationReason.EPOCH_CHANGE,
                                     f"surface epoch {self.surface_epoch!r} -> {frame.surface_epoch!r}")
        if self.latest_frame_uid and frame.document_epoch != self.document_epoch:
            return self._full_resync(parse, InvalidationReason.DOCUMENT_NAVIGATION,
                                     f"document epoch {self.document_epoch!r} -> {frame.document_epoch!r}")
        if frame.quality.value in ("corrupted", "unavailable", "disconnected", "permission_denied"):
            update = self._mark_all_uncertain(
                parse, InvalidationReason.QUALITY_FAULT,
                f"frame quality {frame.quality.value}: no matching on faulty pixels",
            )
            self.latest_frame_uid = frame.uid
            self.history.append(update)
            return update

        # ---- scroll compensation of carried boxes ----
        carried: Dict[str, Box] = {}
        scroll_uncertain: Dict[str, str] = {}
        for tid, track in self.tracks.items():
            if track.status == TrackStatus.INVALIDATED or track.current_box is None:
                continue
            prev_geom = getattr(track, "_last_geometry", None)
            if prev_geom is None or prev_geom == frame.geometry:
                carried[tid] = track.current_box
                continue
            moved, unsup, _record = scroll_compensate(
                track.current_box,
                prev_geom.scroll_origin_px, prev_geom.scroll_origin_known,
                frame.geometry.scroll_origin_px, frame.geometry.scroll_origin_known,
                frame.uid,
            )
            if moved is None or unsup is not None:
                scroll_uncertain[tid] = (unsup.reason if unsup else "scroll compensation failed")
            else:
                carried[tid] = moved

        # ---- greedy matching with ambiguity detection ----
        candidates = [t for t in self.tracks.values() if t.track_id in carried]
        regions = list(parse.regions)
        used_regions: set = set()
        matched: List[Tuple[str, str]] = []
        uncertain: List[Tuple[str, str]] = []
        invalidated: List[Tuple[str, str]] = []
        created: List[Tuple[str, str]] = []
        lost: List[str] = []

        for tid, reason in scroll_uncertain.items():
            track = self.tracks[tid]
            track.status = TrackStatus.UNCERTAIN
            track.invalidation_reason = InvalidationReason.SCROLL_UNKNOWN
            track.invalidation_detail = reason
            uncertain.append((tid, f"scroll_unknown: {reason}"))

        for track in candidates:
            if track.track_id in scroll_uncertain:
                continue
            base = carried[track.track_id]
            scored: List[Tuple[float, RegionProposal]] = []
            track_text = (track_text_by_id or {}).get(track.track_id)
            if track_text is None and track.observations:
                track_text = track.observations[-1].text
            for r in regions:
                if r.region_id in used_regions:
                    continue
                iou = box_iou(base, r.box_xyxy)
                bonus = thr.text_bonus if _text_agreement(track_text or "", r.ocr_labels) else 0.0
                cont = max(containment(base, r.box_xyxy), containment(r.box_xyxy, base))
                score = max(iou + bonus, cont if cont >= thr.containment_match else 0.0)
                scored.append((score, r))
            scored.sort(key=lambda p: p[0], reverse=True)
            best = scored[0] if scored else (0.0, None)
            second = scored[1][0] if len(scored) > 1 else 0.0

            if best[1] is not None and best[0] >= thr.match_iou and (best[0] - second) > thr.ambiguity_margin:
                region = best[1]
                used_regions.add(region.region_id)
                # per-match invalidation checks
                occluded = any(
                    containment(region.box_xyxy, ob) >= thr.overlay_containment for ob in overlay_boxes
                )
                if occluded:
                    track.status = TrackStatus.INVALIDATED
                    track.invalidation_reason = InvalidationReason.OVERLAY_OCCLUSION
                    track.invalidation_detail = f"region {region.region_id} covered by overlay"
                    invalidated.append((track.track_id, "overlay_occlusion"))
                    continue
                if region.region_id in attribute_hints:
                    track.status = TrackStatus.UNCERTAIN
                    track.invalidation_reason = InvalidationReason.ATTRIBUTE_CHANGE
                    track.invalidation_detail = f"attributes changed: {sorted(attribute_hints[region.region_id])}"
                    track.predicted_box_xyxy = region.box_xyxy
                    uncertain.append((track.track_id, "attribute_change"))
                    continue
                pratio = pixel_change_by_region.get(region.region_id, 0.0)
                if pratio >= thr.dynamic_pixel_ratio:
                    track.status = TrackStatus.UNCERTAIN
                    track.invalidation_reason = InvalidationReason.DYNAMIC_PIXELS
                    track.invalidation_detail = f"pixel_change_ratio={pratio:.3f}"
                    track.predicted_box_xyxy = region.box_xyxy
                    uncertain.append((track.track_id, "dynamic_pixels"))
                    continue
                track.status = TrackStatus.ACTIVE
                track.missing_frames = 0
                track.invalidation_reason = None
                track.invalidation_detail = ""
                track.predicted_box_xyxy = None
                track.observations.append(
                    TrackObservation(
                        frame_uid=frame.uid,
                        box_xyxy=region.box_xyxy,
                        text=region.ocr_labels,
                        score=region.score,
                        pixel_sha256=frame.pixel_sha256,
                    )
                )
                track.last_frame_uid = frame.uid
                track.tiny = box_area(region.box_xyxy) < thr.tiny_area_px
                matched.append((track.track_id, region.region_id))
            elif best[1] is not None and best[0] >= thr.match_iou:
                track.status = TrackStatus.UNCERTAIN
                track.invalidation_reason = InvalidationReason.AMBIGUOUS
                track.invalidation_detail = (
                    f"best={best[0]:.3f} second={second:.3f} within margin {thr.ambiguity_margin}"
                )
                track.predicted_box_xyxy = best[1].box_xyxy
                uncertain.append((track.track_id, "ambiguous"))
            elif best[1] is not None and best[0] >= thr.move_iou:
                track.status = TrackStatus.UNCERTAIN
                track.invalidation_reason = InvalidationReason.MOVED
                track.invalidation_detail = f"best IoU {best[0]:.3f} below match {thr.match_iou}"
                track.predicted_box_xyxy = best[1].box_xyxy
                uncertain.append((track.track_id, "moved"))
            else:
                track.missing_frames += 1
                if track.missing_frames > thr.max_missing_frames:
                    track.status = TrackStatus.LOST
                    lost.append(track.track_id)
                else:
                    track.status = TrackStatus.UNCERTAIN
                    track.invalidation_reason = InvalidationReason.MISSING
                    track.invalidation_detail = f"no candidate (missing {track.missing_frames})"
                    uncertain.append((track.track_id, "missing"))

        # unmatched regions seed new tracks (except overlay-covered ones)
        matched_region_ids = {r for _, r in matched}
        for r in regions:
            if r.region_id in matched_region_ids or r.region_id in used_regions:
                continue
            if any(containment(r.box_xyxy, ob) >= thr.overlay_containment for ob in overlay_boxes):
                continue  # overlay-covered: do not seed a track under a modal
            self.surface_epoch = frame.surface_epoch
            tid = self._new_track_id()
            track = Track(
                track_id=tid,
                surface_epoch=frame.surface_epoch,
                document_epoch=frame.document_epoch,
                status=TrackStatus.ACTIVE,
                observations=[
                    TrackObservation(
                        frame_uid=frame.uid, box_xyxy=r.box_xyxy,
                        text=r.ocr_labels, score=r.score,
                        pixel_sha256=frame.pixel_sha256,
                    )
                ],
                tiny=box_area(r.box_xyxy) < thr.tiny_area_px,
                created_frame_uid=frame.uid,
                last_frame_uid=frame.uid,
            )
            setattr(track, "_last_geometry", frame.geometry)  # noqa: B010
            self.tracks[tid] = track
            created.append((tid, r.region_id))

        for track in self.tracks.values():
            if track.status != TrackStatus.INVALIDATED:
                setattr(track, "_last_geometry", frame.geometry)  # noqa: B010

        self.latest_frame_uid = frame.uid
        self.surface_epoch = frame.surface_epoch
        self.document_epoch = frame.document_epoch
        update = TrackUpdate(
            frame_uid=frame.uid,
            matched=matched,
            created=created,
            uncertain=uncertain,
            invalidated=invalidated,
            lost=lost,
            full_resync=False,
            resync_reason="",
            thresholds=thr.to_dict(),
        )
        self.history.append(update)
        return update

    def _full_resync(self, parse: StaticParse, reason: InvalidationReason, detail: str) -> TrackUpdate:
        frame = parse.frame
        invalidated = []
        for track in self.tracks.values():
            if track.status != TrackStatus.INVALIDATED:
                track.status = TrackStatus.INVALIDATED
                track.invalidation_reason = reason
                track.invalidation_detail = detail
                invalidated.append((track.track_id, reason.value))
        created: List[Tuple[str, str]] = []
        self.surface_epoch = frame.surface_epoch
        self.document_epoch = frame.document_epoch
        for r in parse.regions:
            tid = self._new_track_id()
            track = Track(
                track_id=tid,
                surface_epoch=frame.surface_epoch,
                document_epoch=frame.document_epoch,
                status=TrackStatus.ACTIVE,
                observations=[
                    TrackObservation(
                        frame_uid=frame.uid, box_xyxy=r.box_xyxy,
                        text=r.ocr_labels, score=r.score,
                        pixel_sha256=frame.pixel_sha256,
                    )
                ],
                created_frame_uid=frame.uid,
                last_frame_uid=frame.uid,
            )
            setattr(track, "_last_geometry", frame.geometry)  # noqa: B010
            self.tracks[tid] = track
            created.append((tid, r.region_id))
        self.latest_frame_uid = frame.uid
        update = TrackUpdate(
            frame_uid=frame.uid,
            matched=[],
            created=created,
            uncertain=[],
            invalidated=invalidated,
            lost=[],
            full_resync=True,
            resync_reason=detail,
            thresholds=self.thresholds.to_dict(),
        )
        self.history.append(update)
        return update

    def _mark_all_uncertain(self, parse: StaticParse, reason: InvalidationReason, detail: str) -> TrackUpdate:
        uncertain = []
        for track in self.tracks.values():
            if track.status == TrackStatus.INVALIDATED:
                continue
            track.status = TrackStatus.UNCERTAIN
            track.invalidation_reason = reason
            track.invalidation_detail = detail
            uncertain.append((track.track_id, reason.value))
        return TrackUpdate(
            frame_uid=parse.frame.uid,
            matched=[],
            created=[],
            uncertain=uncertain,
            invalidated=[],
            lost=[],
            full_resync=False,
            resync_reason="",
            thresholds=self.thresholds.to_dict(),
        )
