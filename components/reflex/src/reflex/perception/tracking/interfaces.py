"""Interchangeable frame-bound interpretation interfaces.

Three swappable roles (region proposal, OCR, function hypothesis) plus the
StaticParse envelope that binds their outputs to one FrameIdentity.

Deliberate asymmetry: detector scores and OCR recognition scores are
CALIBRATED-OR-NOT model confidences carried as Optional floats with their
producer named; function hypotheses NEVER carry a confidence — only an
uncertainty record plus a support status. A hypothesis becomes SUPPORTED only
through observation or an independently checked interaction, never by caption
self-score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple

from .frame import FrameIdentity, Unsupported

Box = Tuple[float, float, float, float]


class ComponentState(str, Enum):
    OK = "ok"
    FAILED = "failed"  # ran and failed; reason preserved
    UNSUPPORTED = "unsupported"  # cannot run on this frame/config
    NOT_RUN = "not_run"  # skipped by policy/budget, explicitly recorded


class HypothesisStatus(str, Enum):
    HYPOTHESIS = "hypothesis"  # default: unverified proposal
    SUPPORTED_BY_OBSERVATION = "supported_by_observation"
    SUPPORTED_BY_INTERACTION = "supported_by_interaction"
    REFUTED = "refuted"


@dataclass(frozen=True)
class RegionProposal:
    region_id: str  # frame-scoped, e.g. "r3"
    box_xyxy: Box  # ORIGINAL PIXEL coords
    frame_uid: str
    score: Optional[float] = None  # detector confidence; None = not reported
    producer: str = ""
    merge_source: str = ""
    ocr_labels: str = ""
    out_of_frame_clamped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "box_xyxy": list(self.box_xyxy),
            "frame_uid": self.frame_uid,
            "score": self.score,
            "producer": self.producer,
            "merge_source": self.merge_source,
            "ocr_labels": self.ocr_labels,
            "out_of_frame_clamped": self.out_of_frame_clamped,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegionProposal":
        b = data["box_xyxy"]
        return cls(
            region_id=str(data["region_id"]),
            box_xyxy=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
            frame_uid=str(data["frame_uid"]),
            score=data.get("score"),
            producer=str(data.get("producer", "")),
            merge_source=str(data.get("merge_source", "")),
            ocr_labels=str(data.get("ocr_labels", "")),
            out_of_frame_clamped=bool(data.get("out_of_frame_clamped", False)),
        )


@dataclass(frozen=True)
class OCRSpan:
    ocr_id: str  # frame-scoped, e.g. "o7"
    polygon_xy: List[Tuple[float, float]]  # ORIGINAL PIXEL coords
    box_xyxy: Box
    text: str
    frame_uid: str
    confidence: Optional[float] = None  # recognizer score; None = not reported
    producer: str = ""
    consumed_by_region: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ocr_id": self.ocr_id,
            "polygon_xy": [list(p) for p in self.polygon_xy],
            "box_xyxy": list(self.box_xyxy),
            "text": self.text,
            "frame_uid": self.frame_uid,
            "confidence": self.confidence,
            "producer": self.producer,
            "consumed_by_region": self.consumed_by_region,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OCRSpan":
        b = data["box_xyxy"]
        return cls(
            ocr_id=str(data["ocr_id"]),
            polygon_xy=[(float(p[0]), float(p[1])) for p in data.get("polygon_xy", [])],
            box_xyxy=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
            text=str(data.get("text", "")),
            frame_uid=str(data["frame_uid"]),
            confidence=data.get("confidence"),
            producer=str(data.get("producer", "")),
            consumed_by_region=data.get("consumed_by_region"),
        )


@dataclass(frozen=True)
class FunctionHypothesis:
    """What a region might do. No confidence attribute by design: captions are
    uncalibrated. Uncertainty is descriptive (token logprobs), not a
    probability of functional correctness."""

    hypothesis_id: str  # frame-scoped, e.g. "h2"
    region_id: str
    text: str
    frame_uid: str
    uncertainty: Dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    crop_box_xyxy: Optional[Box] = None
    resized_to: Optional[Tuple[int, int]] = None
    nearby_texts: List[Dict[str, Any]] = field(default_factory=list)
    producer: str = ""
    status: HypothesisStatus = HypothesisStatus.HYPOTHESIS
    support_evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "region_id": self.region_id,
            "text": self.text,
            "frame_uid": self.frame_uid,
            "uncertainty": dict(self.uncertainty),
            "prompt": self.prompt,
            "crop_box_xyxy": list(self.crop_box_xyxy) if self.crop_box_xyxy else None,
            "resized_to": list(self.resized_to) if self.resized_to else None,
            "nearby_texts": [dict(t) for t in self.nearby_texts],
            "producer": self.producer,
            "status": self.status.value,
            "support_evidence": self.support_evidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FunctionHypothesis":
        crop = data.get("crop_box_xyxy")
        resized = data.get("resized_to")
        raw_s = data.get("status", HypothesisStatus.HYPOTHESIS.value)
        status = (
            HypothesisStatus(raw_s)
            if raw_s in HypothesisStatus._value2member_map_
            else HypothesisStatus.HYPOTHESIS
        )
        return cls(
            hypothesis_id=str(data["hypothesis_id"]),
            region_id=str(data["region_id"]),
            text=str(data.get("text", "")),
            frame_uid=str(data["frame_uid"]),
            uncertainty=dict(data.get("uncertainty", {})),
            prompt=str(data.get("prompt", "")),
            crop_box_xyxy=(float(crop[0]), float(crop[1]), float(crop[2]), float(crop[3]))
            if crop
            else None,
            resized_to=(int(resized[0]), int(resized[1])) if resized else None,
            nearby_texts=[dict(t) for t in data.get("nearby_texts", [])],
            producer=str(data.get("producer", "")),
            status=status,
            support_evidence=str(data.get("support_evidence", "")),
        )


@dataclass(frozen=True)
class OverlapHypothesis:
    """Occlusion/overlap proposal between two frame-bound boxes."""

    region_a: str
    region_b: str
    relation: str  # "overlaps" | "a_covers_b" | "b_covers_a" | "adjacent"
    iou: float
    containment_a_in_b: float
    containment_b_in_a: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_a": self.region_a,
            "region_b": self.region_b,
            "relation": self.relation,
            "iou": self.iou,
            "containment_a_in_b": self.containment_a_in_b,
            "containment_b_in_a": self.containment_b_in_a,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OverlapHypothesis":
        return cls(
            region_a=str(data["region_a"]),
            region_b=str(data["region_b"]),
            relation=str(data["relation"]),
            iou=float(data["iou"]),
            containment_a_in_b=float(data["containment_a_in_b"]),
            containment_b_in_a=float(data["containment_b_in_a"]),
        )


@dataclass(frozen=True)
class LayoutContext:
    """Compact global layout: frame extent, counts, and overlap hypotheses."""

    frame_xyxy: Box
    num_regions: int
    num_ocr: int
    num_hypotheses: int
    overlaps: List[OverlapHypothesis] = field(default_factory=list)
    container_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_xyxy": list(self.frame_xyxy),
            "num_regions": self.num_regions,
            "num_ocr": self.num_ocr,
            "num_hypotheses": self.num_hypotheses,
            "overlaps": [o.to_dict() for o in self.overlaps],
            "container_notes": list(self.container_notes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayoutContext":
        fb = data.get("frame_xyxy", [0, 0, 0, 0])
        return cls(
            frame_xyxy=(float(fb[0]), float(fb[1]), float(fb[2]), float(fb[3])),
            num_regions=int(data.get("num_regions", 0)),
            num_ocr=int(data.get("num_ocr", 0)),
            num_hypotheses=int(data.get("num_hypotheses", 0)),
            overlaps=[OverlapHypothesis.from_dict(o) for o in data.get("overlaps", [])],
            container_notes=list(data.get("container_notes", [])),
        )


@dataclass(frozen=True)
class StaticParse:
    """One frame's full static interpretation with component states."""

    frame: FrameIdentity
    regions: List[RegionProposal] = field(default_factory=list)
    ocr: List[OCRSpan] = field(default_factory=list)
    hypotheses: List[FunctionHypothesis] = field(default_factory=list)
    layout: Optional[LayoutContext] = None
    component_states: Dict[str, ComponentState] = field(default_factory=dict)
    component_errors: Dict[str, str] = field(default_factory=dict)
    unsupported: List[Unsupported] = field(default_factory=list)
    producer_config: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)

    def ok(self) -> bool:
        return all(s == ComponentState.OK for s in self.component_states.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame": self.frame.to_dict(),
            "regions": [r.to_dict() for r in self.regions],
            "ocr": [o.to_dict() for o in self.ocr],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "layout": self.layout.to_dict() if self.layout else None,
            "component_states": {k: v.value for k, v in self.component_states.items()},
            "component_errors": dict(self.component_errors),
            "unsupported": [u.to_dict() for u in self.unsupported],
            "producer_config": dict(self.producer_config),
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StaticParse":
        states = {}
        for k, v in data.get("component_states", {}).items():
            states[str(k)] = (
                ComponentState(v)
                if v in ComponentState._value2member_map_
                else ComponentState.FAILED
            )
        layout = data.get("layout")
        return cls(
            frame=FrameIdentity.from_dict(data["frame"]),
            regions=[RegionProposal.from_dict(r) for r in data.get("regions", [])],
            ocr=[OCRSpan.from_dict(o) for o in data.get("ocr", [])],
            hypotheses=[FunctionHypothesis.from_dict(h) for h in data.get("hypotheses", [])],
            layout=LayoutContext.from_dict(layout) if layout else None,
            component_states=states,
            component_errors={str(k): str(v) for k, v in data.get("component_errors", {}).items()},
            unsupported=[Unsupported.from_dict(u) for u in data.get("unsupported", [])],
            producer_config=dict(data.get("producer_config", {})),
            params=dict(data.get("params", {})),
        )


class RegionProposer(Protocol):
    """Interchangeable region-proposal role."""

    component_id: str

    def supports(self, frame: FrameIdentity) -> Optional[Unsupported]:
        """None when runnable on this frame, else truthful Unsupported."""
        ...

    def propose(self, frame: FrameIdentity, pixels_path: Optional[str] = None) -> List[RegionProposal]:
        ...


class OCRReader(Protocol):
    """Interchangeable OCR role."""

    component_id: str

    def supports(self, frame: FrameIdentity) -> Optional[Unsupported]:
        ...

    def read(self, frame: FrameIdentity, pixels_path: Optional[str] = None) -> List[OCRSpan]:
        ...


class FunctionHypothesizer(Protocol):
    """Interchangeable function-hypothesis role (captions are hypotheses)."""

    component_id: str

    def supports(self, frame: FrameIdentity) -> Optional[Unsupported]:
        ...

    def hypothesize(
        self,
        frame: FrameIdentity,
        regions: List[RegionProposal],
        ocr: List[OCRSpan],
        pixels_path: Optional[str] = None,
    ) -> List[FunctionHypothesis]:
        ...
