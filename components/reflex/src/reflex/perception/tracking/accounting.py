"""Raw resource accounting. Records observed usage only — no prices, no
fabricated per-call costs. Costs are raw counts/timings/bytes plus cold/warm
split, aligned to the evidence plan's accounting fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ResourceLedger:
    frames_seen: int = 0
    frames_ok: int = 0
    frames_failed: int = 0
    proposal_scans: int = 0
    regions_total: int = 0
    ocr_entries_total: int = 0
    captions_total: int = 0
    crops_total: int = 0
    expanded_crops: int = 0
    global_reinspects: int = 0
    vlm_requests: int = 0  # requested, never executed by this package
    track_matches: int = 0
    track_invalidations: int = 0
    track_uncertain: int = 0
    full_resyncs: int = 0
    crop_pixels_total: int = 0
    component_failures: Dict[str, int] = field(default_factory=dict)
    stage_ms: Dict[str, List[float]] = field(default_factory=dict)
    cold_frames: int = 0
    warm_frames: int = 0
    notes: List[str] = field(default_factory=list)

    def add_stage_ms(self, stage: str, ms: float) -> None:
        self.stage_ms.setdefault(stage, []).append(float(ms))

    def add_component_failure(self, component: str) -> None:
        self.component_failures[component] = self.component_failures.get(component, 0) + 1

    def stage_summary(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for stage, samples in self.stage_ms.items():
            if not samples:
                continue
            ordered = sorted(samples)
            out[stage] = {
                "n": float(len(ordered)),
                "p50": ordered[len(ordered) // 2],
                "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
                "total": sum(ordered),
            }
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frames_seen": self.frames_seen,
            "frames_ok": self.frames_ok,
            "frames_failed": self.frames_failed,
            "proposal_scans": self.proposal_scans,
            "regions_total": self.regions_total,
            "ocr_entries_total": self.ocr_entries_total,
            "captions_total": self.captions_total,
            "crops_total": self.crops_total,
            "expanded_crops": self.expanded_crops,
            "global_reinspects": self.global_reinspects,
            "vlm_requests": self.vlm_requests,
            "track_matches": self.track_matches,
            "track_invalidations": self.track_invalidations,
            "track_uncertain": self.track_uncertain,
            "full_resyncs": self.full_resyncs,
            "crop_pixels_total": self.crop_pixels_total,
            "component_failures": dict(self.component_failures),
            "stage_ms_summary": self.stage_summary(),
            "cold_frames": self.cold_frames,
            "warm_frames": self.warm_frames,
            "notes": list(self.notes),
        }
