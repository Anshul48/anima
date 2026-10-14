"""Adapters: model-packaging outputs -> frame-bound StaticParse.

Consumes the per-frame JSON records written by the model worker's
10_run_static_perception.py (schema documented there; no import from the
model root). Never invents evidence:

- regions None -> ComponentState.FAILED (detector_failed), not empty.
- ocr None -> FAILED; captions None -> FAILED; each with preserved reason.
- Caption text becomes a HYPOTHESIS; its token-logprob record is carried as
  descriptive uncertainty, never converted into a confidence.
- Boxes are validated (finite, positive area) and clamped to frame bounds
  with an explicit flag; malformed boxes are dropped with a recorded reason.
- Expected sha256/dimensions, when supplied, are verified; mismatch fails
  the frame loudly instead of binding to wrong pixels.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
from typing import Any, Dict, List, Optional, Tuple

from .frame import FrameIdentity, FrameQuality, Unsupported, ViewportGeometry
from .interfaces import (
    Box,
    ComponentState,
    FunctionHypothesis,
    HypothesisStatus,
    LayoutContext,
    OCRSpan,
    OverlapHypothesis,
    RegionProposal,
    StaticParse,
)
from .transforms import clamp_box, is_valid_box, pairwise_overlaps

MODEL_RUN_SCHEMA = "model-static-perception/1"  # 10_run_static_perception.py frec


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def png_dimensions(path: str) -> Tuple[int, int]:
    """Stdlib PNG dimension check (magic + IHDR). Raises ValueError."""
    with open(path, "rb") as f:
        head = f.read(33)
    if len(head) < 33 or head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file (bad magic)")
    length, ctype = struct.unpack(">I4s", head[8:16])
    if ctype != b"IHDR" or length != 13:
        raise ValueError("not a PNG file (missing IHDR)")
    width, height = struct.unpack(">II", head[16:24])
    if width <= 0 or height <= 0 or width > 16384 or height > 16384:
        raise ValueError("implausible PNG dimensions %dx%d" % (width, height))
    return width, height


def _as_box(raw: Any) -> Optional[Box]:
    try:
        x0, y0, x1, y1 = (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    box = (x0, y0, x1, y1)
    return box if is_valid_box(box) else None


class FrameBindingError(ValueError):
    """Raised when a model record cannot be truthfully bound to a frame."""


class ModelRunAdapter:
    """Parse model-packaging per-frame records into StaticParse envelopes."""

    def __init__(
        self,
        *,
        source_id: str = "model-static-perception",
        surface_epoch: str = "",
        document_epoch: str = "",
        dpr: Optional[float] = None,
    ) -> None:
        self.source_id = source_id
        self.surface_epoch = surface_epoch
        self.document_epoch = document_epoch
        self.dpr = dpr

    def parse_frame_record(
        self,
        frec: Dict[str, Any],
        *,
        expected_sha256: Optional[str] = None,
        expected_dims: Optional[Tuple[int, int]] = None,
        received_ms: Optional[float] = None,
    ) -> StaticParse:
        """Adapt one per-frame record. Raises FrameBindingError on identity
        mismatch or malformed records; component failures become FAILED
        states (not exceptions) with reasons preserved."""
        if not isinstance(frec, dict):
            raise FrameBindingError("frame record must be a dict")
        try:
            width = int(frec["width"])
            height = int(frec["height"])
            sha = str(frec["sha256"])
            fname = str(frec["file"])
        except KeyError as exc:
            raise FrameBindingError(f"frame record missing identity key: {exc}") from exc

        if expected_sha256 is not None and sha != expected_sha256:
            raise FrameBindingError(
                f"sha256 mismatch for {fname}: record {sha[:16]}... != expected "
                f"{expected_sha256[:16]}...; refusing to bind to wrong pixels"
            )
        if expected_dims is not None and (width, height) != (expected_dims[0], expected_dims[1]):
            raise FrameBindingError(
                f"dimension mismatch for {fname}: record {width}x{height} != "
                f"expected {expected_dims[0]}x{expected_dims[1]}"
            )

        frame = FrameIdentity(
            source_id=self.source_id,
            frame_id=fname,
            pixel_sha256=sha,
            geometry=ViewportGeometry(width_px=width, height_px=height, dpr=self.dpr),
            quality=FrameQuality.HEALTHY,
            received_ms=received_ms if received_ms is not None else 0.0,
            modality_status={"model_run": "ok"},
            surface_epoch=self.surface_epoch,
            document_epoch=self.document_epoch,
        )
        unsupported: List[Unsupported] = []
        if self.dpr is None:
            unsupported.append(
                Unsupported(
                    feature="dpr",
                    reason="DPR not supplied for model-run frames",
                    needed_by="ModelRunAdapter",
                    frame_uid=frame.uid,
                )
            )

        failures = frec.get("failures", []) or []
        fail_by_component = {str(f.get("component", "")): str(f.get("error", "")) for f in failures}

        states: Dict[str, ComponentState] = {}
        errors: Dict[str, str] = {}
        dropped: List[str] = []

        # ---- regions ----
        raw_regions = frec.get("regions")
        regions: List[RegionProposal] = []
        if raw_regions is None:
            states["regions"] = ComponentState.FAILED
            errors["regions"] = fail_by_component.get("regions", "regions missing (detector_failed)")
        elif not isinstance(raw_regions, list):
            states["regions"] = ComponentState.FAILED
            errors["regions"] = "regions payload not a list (detector_failed)"
        else:
            states["regions"] = ComponentState.OK
            for ri, r in enumerate(raw_regions):
                box = _as_box(r.get("box_xyxy"))
                if box is None:
                    dropped.append(f"regions[{ri}]: malformed box dropped")
                    continue
                clamped, was_clamped = clamp_box(box, width, height)
                if not is_valid_box(clamped):
                    dropped.append(f"regions[{ri}]: box outside frame entirely, dropped")
                    continue
                regions.append(
                    RegionProposal(
                        region_id=f"r{r.get('region_id', ri)}",
                        box_xyxy=clamped,
                        frame_uid=frame.uid,
                        score=r.get("score"),
                        producer=str(frec.get("components", {}).get("regions", {}).get("backend", "")),
                        merge_source=str(r.get("merge_source", "")),
                        ocr_labels=str(r.get("ocr_labels", "")),
                        out_of_frame_clamped=was_clamped,
                    )
                )

        # ---- OCR ----
        raw_ocr = frec.get("ocr")
        ocr: List[OCRSpan] = []
        if raw_ocr is None:
            states["ocr"] = ComponentState.FAILED
            errors["ocr"] = fail_by_component.get("ocr", "ocr missing (ocr_failed)")
        elif not isinstance(raw_ocr, list):
            states["ocr"] = ComponentState.FAILED
            errors["ocr"] = "ocr payload not a list (ocr_failed)"
        else:
            states["ocr"] = ComponentState.OK
            for oi, o in enumerate(raw_ocr):
                box = _as_box(o.get("box_xyxy"))
                if box is None:
                    dropped.append(f"ocr[{oi}]: malformed box dropped")
                    continue
                clamped, _ = clamp_box(box, width, height)
                if not is_valid_box(clamped):
                    dropped.append(f"ocr[{oi}]: box outside frame entirely, dropped")
                    continue
                poly_raw = o.get("polygon_xy", []) or []
                poly: List[Tuple[float, float]] = []
                try:
                    poly = [(float(p[0]), float(p[1])) for p in poly_raw]
                except (TypeError, ValueError, IndexError):
                    dropped.append(f"ocr[{oi}]: malformed polygon, kept box only")
                consumed = o.get("consumed_by_region")
                ocr.append(
                    OCRSpan(
                        ocr_id=f"o{o.get('ocr_id', oi)}",
                        polygon_xy=poly,
                        box_xyxy=clamped,
                        text=str(o.get("text", "")),
                        frame_uid=frame.uid,
                        confidence=o.get("confidence"),
                        producer=str(frec.get("components", {}).get("ocr", {}).get("backend", "")),
                        consumed_by_region=f"r{consumed}" if consumed is not None else None,
                    )
                )

        # ---- captions -> hypotheses (never confidences) ----
        raw_caps = frec.get("captions")
        hypotheses: List[FunctionHypothesis] = []
        if raw_caps is None:
            states["caption"] = ComponentState.FAILED
            errors["caption"] = fail_by_component.get("caption", "captions missing (caption_failed)")
        elif not isinstance(raw_caps, list):
            states["caption"] = ComponentState.FAILED
            errors["caption"] = "captions payload not a list (caption_failed)"
        else:
            states["caption"] = ComponentState.OK
            for hi, c in enumerate(raw_caps):
                crop = c.get("crop", {}) or {}
                crop_box = _as_box(crop.get("box_xyxy")) if crop.get("box_xyxy") else None
                resized = crop.get("resized_to")
                hypotheses.append(
                    FunctionHypothesis(
                        hypothesis_id=f"h{hi}",
                        region_id=f"r{c.get('region_id', '?')}",
                        text=str(c.get("hypothesis_text", "")),
                        frame_uid=frame.uid,
                        uncertainty=dict(c.get("uncertainty", {}) or {}),
                        prompt=str(c.get("prompt", "")),
                        crop_box_xyxy=crop_box,
                        resized_to=(int(resized[0]), int(resized[1])) if resized else None,
                        nearby_texts=[dict(t) for t in c.get("nearby_texts", []) or []],
                        producer=str(frec.get("components", {}).get("caption", {}).get("backend", "")),
                        status=HypothesisStatus.HYPOTHESIS,
                    )
                )

        if dropped:
            errors["dropped_entries"] = "; ".join(dropped)

        # ---- layout context ----
        overlaps = pairwise_overlaps([(r.region_id, r.box_xyxy) for r in regions])
        layout = LayoutContext(
            frame_xyxy=(0.0, 0.0, float(width), float(height)),
            num_regions=len(regions),
            num_ocr=len(ocr),
            num_hypotheses=len(hypotheses),
            overlaps=[OverlapHypothesis.from_dict(o) for o in overlaps],
        )

        components = frec.get("components", {}) or {}
        return StaticParse(
            frame=frame,
            regions=regions,
            ocr=ocr,
            hypotheses=hypotheses,
            layout=layout,
            component_states=states,
            component_errors=errors,
            unsupported=unsupported,
            producer_config={
                "model_run_schema": MODEL_RUN_SCHEMA,
                "components": {k: v.get("backend", "") for k, v in components.items() if isinstance(v, dict)},
                "condition": frec.get("condition", ""),
            },
            params={},
        )

    def parse_run_dir(
        self,
        run_dir: str,
        frames_manifest_path: str,
    ) -> Tuple[List[StaticParse], List[Dict[str, Any]]]:
        """Adapt a full model run directory.

        Verifies each frame record against the frozen frames manifest
        (presence, sha256, dims) before binding. Returns (parses, failures);
        failures are explicit records, never silent drops.
        """
        with open(frames_manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        want: Dict[str, Dict[str, Any]] = {}
        for entry in manifest.get("frames", []):
            want[str(entry.get("file", ""))] = entry
        frames_out = os.path.join(run_dir, "frames")
        parses: List[StaticParse] = []
        failures: List[Dict[str, Any]] = []
        try:
            names = sorted(os.listdir(frames_out))
        except OSError as exc:
            return [], [{"file": "", "error": f"frames dir unreadable: {exc}"}]
        for name in names:
            if not name.endswith(".json"):
                continue
            base = name[: -len(".json")]
            path = os.path.join(frames_out, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    frec = json.load(f)
            except (OSError, ValueError) as exc:
                failures.append({"file": base, "error": f"unreadable record: {exc}"})
                continue
            entry = want.get(frec.get("file", base))
            if entry is None:
                failures.append({"file": base, "error": "no frozen manifest entry; refusing unidentified frame"})
                continue
            try:
                parses.append(
                    self.parse_frame_record(
                        frec,
                        expected_sha256=str(entry["sha256"]),
                        expected_dims=(int(entry["width"]), int(entry["height"])),
                    )
                )
            except FrameBindingError as exc:
                failures.append({"file": base, "error": str(exc)})
        return parses, failures


def static_parse_to_node_dicts(parse: StaticParse) -> Tuple[List[Dict[str, Any]], List[Unsupported]]:
    """Map a StaticParse onto builder-UIStateNode-shaped plain dicts.

    No builder import: emits plain dicts matching UIStateNode.to_dict() keys so
    the builder can convert with UIStateNode.from_dict. Vision-derived nodes
    carry source "vision" plus full frame/pixel provenance in attributes.
    Detector scores map to confidence ONLY where reported; hypotheses never
    contribute confidence (0.0 + uncalibrated flag would overclaim, so the
    attribute records the absence explicitly).
    """
    nodes: List[Dict[str, Any]] = []
    unsupported: List[Unsupported] = []
    hyp_by_region = {h.region_id: h for h in parse.hypotheses}
    for r in parse.regions:
        hyp = hyp_by_region.get(r.region_id)
        label = r.ocr_labels or (hyp.text if hyp else "")
        attrs: Dict[str, Any] = {
            "frame_uid": parse.frame.uid,
            "frame_id": parse.frame.frame_id,
            "pixel_sha256": parse.frame.pixel_sha256,
            "region_id": r.region_id,
            "merge_source": r.merge_source,
            "producer": r.producer,
            "out_of_frame_clamped": r.out_of_frame_clamped,
        }
        if hyp is not None:
            attrs["hypothesis_id"] = hyp.hypothesis_id
            attrs["hypothesis_status"] = hyp.status.value
            attrs["hypothesis_uncertainty"] = dict(hyp.uncertainty)
            attrs["hypothesis_support"] = hyp.support_evidence
        else:
            attrs["hypothesis_status"] = "none"
        if r.score is None:
            attrs["confidence_uncalibrated"] = True
            unsupported.append(
                Unsupported(
                    feature="region_confidence",
                    reason=f"detector score absent for {r.region_id}; node confidence unset",
                    needed_by="static_parse_to_node_dicts",
                    frame_uid=parse.frame.uid,
                )
            )
            confidence = 0.0
        else:
            confidence = float(r.score)
        x0, y0, x1, y1 = (int(round(v)) for v in r.box_xyxy)
        nodes.append(
            {
                "node_id": f"vis:{parse.frame.frame_id}:{r.region_id}",
                "role": "generic",
                "bounds": {"x1": x0, "y1": y0, "x2": x1, "y2": y1},
                "label": label,
                "value": "",
                "is_clickable": True,
                "is_editable": False,
                "is_focused": False,
                "is_enabled": True,
                "parent_id": None,
                "children_ids": [],
                "source": "vision",
                "confidence": confidence,
                "attributes": attrs,
            }
        )
    return nodes, unsupported
