"""Selective escalation: auditable triggers, explicit budgets, full ledger.

Evaluates each frame-bound parse + track update and emits EscalationDecisions
(requests, never executed model calls). Every decision records trigger,
requested level, granted/denied + reason, and estimated cost. Budgets are
hard: exhausted budgets deny with an explicit reason — the policy degrades
to PROCEED-WITH-CAVEAT or ABSTAIN, never silently exceeds.

This module never calls a model, never captures pixels, and never authorizes
an action target; it only decides what richer perception is worth requesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .accounting import ResourceLedger
from .frame import FrameIdentity
from .interfaces import ComponentState, StaticParse
from .tracking import InvalidationReason, Track, TrackStatus, TrackStore
from .transforms import box_area


class EscalationTrigger(str, Enum):
    MISSING_COVERAGE = "missing_coverage"
    AMBIGUITY = "ambiguity"
    TINY_EVIDENCE = "tiny_evidence"
    DYNAMIC_EVIDENCE = "dynamic_evidence"
    ACQUISITION_FAULT = "acquisition_fault"
    FAILED_EXPECTATION = "failed_expectation"
    PERIODIC_REFRESH = "periodic_refresh"
    OVERLAY_OCCLUSION = "overlay_occlusion"
    EPOCH_RESYNC = "epoch_resync"


class EscalationLevel(str, Enum):
    NONE = "none"  # proceed on current evidence
    EXPAND_CROP = "expand_crop"  # request a larger-context crop re-read
    GLOBAL_REINSPECT = "global_reinspect"  # request full-frame fresh parse
    STRONG_VLM = "strong_vlm"  # request stronger-model inspection (not executed here)


class Decision(str, Enum):
    PROCEED = "proceed"
    ESCALATE = "escalate"
    ABSTAIN = "abstain"  # evidence insufficient and budget exhausted/blocked


@dataclass(frozen=True)
class EscalationBudget:
    max_expanded_crops: int = 8
    max_global_reinspects: int = 3
    max_vlm_requests: int = 2
    max_crop_pixels: int = 4_000_000
    periodic_refresh_every_n_frames: int = 30
    trial_envelope_ref: str = ""  # preregistered per-trial envelope id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_expanded_crops": self.max_expanded_crops,
            "max_global_reinspects": self.max_global_reinspects,
            "max_vlm_requests": self.max_vlm_requests,
            "max_crop_pixels": self.max_crop_pixels,
            "periodic_refresh_every_n_frames": self.periodic_refresh_every_n_frames,
            "trial_envelope_ref": self.trial_envelope_ref,
        }


@dataclass(frozen=True)
class EscalationDecision:
    frame_uid: str
    trigger: EscalationTrigger
    level: EscalationLevel
    decision: Decision
    reason: str
    granted: bool
    cost_crop_pixels: int = 0
    track_ids: List[str] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_uid": self.frame_uid,
            "trigger": self.trigger.value,
            "level": self.level.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "granted": self.granted,
            "cost_crop_pixels": self.cost_crop_pixels,
            "track_ids": list(self.track_ids),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class EscalationConfig:
    min_regions_for_coverage: int = 1
    tiny_area_px: float = 144.0
    failed_expectation_misses: int = 2  # consecutive MISSING => failed expectation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_regions_for_coverage": self.min_regions_for_coverage,
            "tiny_area_px": self.tiny_area_px,
            "failed_expectation_misses": self.failed_expectation_misses,
        }


class EscalationPolicy:
    """Stateful auditable escalation with hard budgets."""

    def __init__(
        self,
        budget: Optional[EscalationBudget] = None,
        config: Optional[EscalationConfig] = None,
        ledger: Optional[ResourceLedger] = None,
    ) -> None:
        self.budget = budget or EscalationBudget()
        self.config = config or EscalationConfig()
        self.ledger = ledger or ResourceLedger()
        self.used_crops = 0
        self.used_reinspects = 0
        self.used_vlm = 0
        self.used_crop_pixels = 0
        self.frames_evaluated = 0
        self.decisions: List[EscalationDecision] = []

    def _request(
        self,
        frame_uid: str,
        trigger: EscalationTrigger,
        level: EscalationLevel,
        reason: str,
        track_ids: Optional[List[str]] = None,
        cost_crop_pixels: int = 0,
        detail: str = "",
    ) -> EscalationDecision:
        granted = True
        deny_reason = ""
        if level == EscalationLevel.EXPAND_CROP:
            if self.used_crops >= self.budget.max_expanded_crops:
                granted, deny_reason = False, "expanded-crop budget exhausted"
            elif self.used_crop_pixels + cost_crop_pixels > self.budget.max_crop_pixels:
                granted, deny_reason = False, "crop-pixel budget exhausted"
        elif level == EscalationLevel.GLOBAL_REINSPECT:
            if self.used_reinspects >= self.budget.max_global_reinspects:
                granted, deny_reason = False, "global-reinspect budget exhausted"
        elif level == EscalationLevel.STRONG_VLM:
            if self.used_vlm >= self.budget.max_vlm_requests:
                granted, deny_reason = False, "strong-VLM budget exhausted"
        if granted:
            if level == EscalationLevel.EXPAND_CROP:
                self.used_crops += 1
                self.used_crop_pixels += cost_crop_pixels
                self.ledger.expanded_crops += 1
                self.ledger.crop_pixels_total += cost_crop_pixels
            elif level == EscalationLevel.GLOBAL_REINSPECT:
                self.used_reinspects += 1
                self.ledger.global_reinspects += 1
            elif level == EscalationLevel.STRONG_VLM:
                self.used_vlm += 1
                self.ledger.vlm_requests += 1
            decision = Decision.ESCALATE if level != EscalationLevel.NONE else Decision.PROCEED
            full_reason = reason
        else:
            decision = Decision.ABSTAIN
            full_reason = f"{reason} -- DENIED: {deny_reason}"
        record = EscalationDecision(
            frame_uid=frame_uid,
            trigger=trigger,
            level=level,
            decision=decision,
            reason=full_reason,
            granted=granted,
            cost_crop_pixels=cost_crop_pixels,
            track_ids=list(track_ids or []),
            detail=detail,
        )
        self.decisions.append(record)
        return record

    def evaluate(
        self,
        parse: StaticParse,
        store: TrackStore,
        *,
        expected_track_ids: Optional[List[str]] = None,
    ) -> List[EscalationDecision]:
        """Evaluate one frame. Returns decisions in trigger-priority order."""
        frame = parse.frame
        out: List[EscalationDecision] = []
        self.frames_evaluated += 1

        # 1. acquisition faults dominate: never escalate INTO bad pixels
        if frame.quality.value in ("corrupted", "unavailable", "disconnected", "permission_denied"):
            out.append(
                self._request(
                    frame.uid, EscalationTrigger.ACQUISITION_FAULT,
                    EscalationLevel.GLOBAL_REINSPECT,
                    f"frame quality {frame.quality.value}; requesting fresh acquisition",
                    detail=f"error={parse.frame.error_message}",
                )
            )
            return out
        failed_components = [k for k, v in parse.component_states.items() if v == ComponentState.FAILED]
        if failed_components:
            out.append(
                self._request(
                    frame.uid, EscalationTrigger.ACQUISITION_FAULT,
                    EscalationLevel.GLOBAL_REINSPECT,
                    f"component failures {failed_components}; requesting fresh parse",
                    detail=str(parse.component_errors),
                )
            )
            return out

        # 2. missing coverage
        if len(parse.regions) < self.config.min_regions_for_coverage:
            out.append(
                self._request(
                    frame.uid, EscalationTrigger.MISSING_COVERAGE,
                    EscalationLevel.GLOBAL_REINSPECT,
                    f"only {len(parse.regions)} regions (< {self.config.min_regions_for_coverage})",
                )
            )

        # 3. track-state triggers
        ambiguous = [t for t in store.tracks.values()
                     if t.status == TrackStatus.UNCERTAIN
                     and t.invalidation_reason == InvalidationReason.AMBIGUOUS
                     and t.last_frame_uid in ("", store.latest_frame_uid) or
                     (t.status == TrackStatus.UNCERTAIN
                      and t.invalidation_reason == InvalidationReason.AMBIGUOUS)]
        ambiguous = [t for t in store.tracks.values()
                     if t.status == TrackStatus.UNCERTAIN
                     and t.invalidation_reason == InvalidationReason.AMBIGUOUS]
        if ambiguous:
            out.append(
                self._request(
                    frame.uid, EscalationTrigger.AMBIGUITY,
                    EscalationLevel.EXPAND_CROP,
                    f"{len(ambiguous)} ambiguous track(s) need wider context",
                    track_ids=[t.track_id for t in ambiguous],
                    cost_crop_pixels=sum(_predicted_pixels(t) for t in ambiguous),
                )
            )
        tiny_active = [t for t in store.tracks.values()
                       if t.tiny and t.status == TrackStatus.ACTIVE
                       and t.last_frame_uid == store.latest_frame_uid]
        if tiny_active:
            out.append(
                self._request(
                    frame.uid, EscalationTrigger.TINY_EVIDENCE,
                    EscalationLevel.EXPAND_CROP,
                    f"{len(tiny_active)} tiny track(s) below {self.config.tiny_area_px}px^2",
                    track_ids=[t.track_id for t in tiny_active],
                    cost_crop_pixels=sum(_predicted_pixels(t) for t in tiny_active),
                )
            )
        dynamic = [t for t in store.tracks.values()
                   if t.status == TrackStatus.UNCERTAIN
                   and t.invalidation_reason == InvalidationReason.DYNAMIC_PIXELS]
        if dynamic:
            out.append(
                self._request(
                    frame.uid, EscalationTrigger.DYNAMIC_EVIDENCE,
                    EscalationLevel.EXPAND_CROP,
                    f"{len(dynamic)} dynamic track(s) need settled re-read",
                    track_ids=[t.track_id for t in dynamic],
                    cost_crop_pixels=sum(_predicted_pixels(t) for t in dynamic),
                )
            )
        occluded = [t for t in store.tracks.values()
                    if t.invalidation_reason == InvalidationReason.OVERLAY_OCCLUSION
                    and t.status == TrackStatus.INVALIDATED]
        if occluded:
            out.append(
                self._request(
                    frame.uid, EscalationTrigger.OVERLAY_OCCLUSION,
                    EscalationLevel.GLOBAL_REINSPECT,
                    f"{len(occluded)} track(s) occluded by overlay; need fresh global parse",
                    track_ids=[t.track_id for t in occluded],
                )
            )

        # 4. failed expectations: expected tracks repeatedly missing
        if expected_track_ids:
            missing_expected = [
                tid for tid in expected_track_ids
                if tid in store.tracks
                and store.tracks[tid].invalidation_reason == InvalidationReason.MISSING
                and store.tracks[tid].missing_frames >= self.config.failed_expectation_misses
            ]
            if missing_expected:
                out.append(
                    self._request(
                        frame.uid, EscalationTrigger.FAILED_EXPECTATION,
                        EscalationLevel.STRONG_VLM,
                        f"{len(missing_expected)} expected track(s) missing "
                        f">={self.config.failed_expectation_misses} frames",
                        track_ids=missing_expected,
                    )
                )

        # 5. periodic global refresh
        n = self.budget.periodic_refresh_every_n_frames
        if n > 0 and self.frames_evaluated % n == 0:
            out.append(
                self._request(
                    frame.uid, EscalationTrigger.PERIODIC_REFRESH,
                    EscalationLevel.GLOBAL_REINSPECT,
                    f"periodic refresh every {n} frames (#{self.frames_evaluated})",
                )
            )

        if not out:
            record = EscalationDecision(
                frame_uid=frame.uid,
                trigger=EscalationTrigger.PERIODIC_REFRESH,
                level=EscalationLevel.NONE,
                decision=Decision.PROCEED,
                reason="no trigger fired; proceeding on current evidence",
                granted=True,
            )
            self.decisions.append(record)
            out.append(record)
        return out

    def budget_state(self) -> Dict[str, Any]:
        return {
            "budget": self.budget.to_dict(),
            "used": {
                "expanded_crops": self.used_crops,
                "global_reinspects": self.used_reinspects,
                "vlm_requests": self.used_vlm,
                "crop_pixels": self.used_crop_pixels,
            },
            "frames_evaluated": self.frames_evaluated,
            "decisions": len(self.decisions),
        }


def _predicted_pixels(track: Track) -> int:
    box = track.predicted_box_xyxy or track.current_box
    if box is None:
        return 0
    return int(box_area(box) * 4)  # 2x-expand estimate
