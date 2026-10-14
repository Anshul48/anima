"""Pure box math plus recorded crop/DPR/scroll transforms.

All transforms operate in ORIGINAL PIXEL coordinates and return a
TransformRecord describing exactly what was applied, so a crop box can always
be mapped back to its source frame pixels. Transforms that need unknown
geometry (DPR, scroll origin) return Unsupported instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .frame import Unsupported, ViewportGeometry

Box = Tuple[float, float, float, float]


def box_area(box: Box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def box_iou(a: Box, b: Box) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = box_area(a) + box_area(b) - inter
    if union <= 0:
        return 0.0
    return inter / union


def containment(inner: Box, outer: Box) -> float:
    """Fraction of `inner` covered by `outer`."""
    ix0, iy0 = max(inner[0], outer[0]), max(inner[1], outer[1])
    ix1, iy1 = min(inner[2], outer[2]), min(inner[3], outer[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    area = box_area(inner)
    if area <= 0:
        return 0.0
    return inter / area


def is_valid_box(box: Box) -> bool:
    import math

    x0, y0, x1, y1 = box
    return (
        all(math.isfinite(v) for v in box)
        and x1 > x0
        and y1 > y0
    )


def clamp_box(box: Box, width_px: int, height_px: int) -> Tuple[Box, bool]:
    """Clamp to frame bounds. Returns (box, was_clamped)."""
    x0, y0, x1, y1 = box
    cx0, cy0 = max(0.0, x0), max(0.0, y0)
    cx1, cy1 = min(float(width_px), x1), min(float(height_px), y1)
    clamped = (cx0, cy0, cx1, cy1)
    return clamped, clamped != box


@dataclass(frozen=True)
class TransformRecord:
    """Provenance for one coordinate transform application."""

    kind: str  # "crop" | "dpr_scale" | "dpr_unscale" | "scroll_compensate" | "clamp"
    params: Dict[str, Any]
    frame_uid: str

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "params": dict(self.params), "frame_uid": self.frame_uid}


@dataclass(frozen=True)
class CropView:
    """A context-padded crop with exact crop<->frame mapping."""

    crop_box_frame_px: Box  # clamped crop extent in frame pixels
    requested_box_frame_px: Box  # pre-clamp requested extent
    pad_px: int
    frame_uid: str
    records: Tuple[TransformRecord, ...] = ()

    @property
    def width(self) -> float:
        return self.crop_box_frame_px[2] - self.crop_box_frame_px[0]

    @property
    def height(self) -> float:
        return self.crop_box_frame_px[3] - self.crop_box_frame_px[1]

    def to_frame(self, box_in_crop: Box) -> Box:
        """Map a box in crop-local coords back to frame pixels."""
        ox, oy = self.crop_box_frame_px[0], self.crop_box_frame_px[1]
        x0, y0, x1, y1 = box_in_crop
        return (x0 + ox, y0 + oy, x1 + ox, y1 + oy)

    def to_crop(self, box_in_frame: Box) -> Box:
        """Map a frame-pixel box into crop-local coords."""
        ox, oy = self.crop_box_frame_px[0], self.crop_box_frame_px[1]
        x0, y0, x1, y1 = box_in_frame
        return (x0 - ox, y0 - oy, x1 - ox, y1 - oy)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "crop_box_frame_px": list(self.crop_box_frame_px),
            "requested_box_frame_px": list(self.requested_box_frame_px),
            "pad_px": self.pad_px,
            "frame_uid": self.frame_uid,
            "records": [r.to_dict() for r in self.records],
        }


def make_crop(
    region_box: Box,
    geometry: ViewportGeometry,
    frame_uid: str,
    pad_px: int = 8,
    min_size_px: int = 1,
) -> Tuple[Optional[CropView], Optional[Unsupported]]:
    """Context-padded crop around a region box, clamped to the frame."""
    if not is_valid_box(region_box):
        return None, Unsupported(
            feature="crop",
            reason=f"invalid region box {region_box!r}: need finite x1>x0, y1>y0",
            needed_by="make_crop",
            frame_uid=frame_uid,
        )
    if pad_px < 0:
        return None, Unsupported(
            feature="crop",
            reason=f"negative pad_px {pad_px}",
            needed_by="make_crop",
            frame_uid=frame_uid,
        )
    requested = (
        region_box[0] - pad_px,
        region_box[1] - pad_px,
        region_box[2] + pad_px,
        region_box[3] + pad_px,
    )
    clamped, was_clamped = clamp_box(requested, geometry.width_px, geometry.height_px)
    if clamped[2] - clamped[0] < min_size_px or clamped[3] - clamped[1] < min_size_px:
        return None, Unsupported(
            feature="crop",
            reason="crop collapsed below minimum size after clamping",
            needed_by="make_crop",
            frame_uid=frame_uid,
        )
    records = (
        TransformRecord(
            kind="crop",
            params={
                "region_box": list(region_box),
                "pad_px": pad_px,
                "requested": list(requested),
                "clamped": list(clamped),
                "was_clamped": was_clamped,
            },
            frame_uid=frame_uid,
        ),
    )
    return (
        CropView(
            crop_box_frame_px=clamped,
            requested_box_frame_px=requested,
            pad_px=pad_px,
            frame_uid=frame_uid,
            records=records,
        ),
        None,
    )


def frame_to_css(
    box: Box, geometry: ViewportGeometry, frame_uid: str
) -> Tuple[Optional[Box], Optional[Unsupported]]:
    """Frame pixels -> CSS px. Unsupported when DPR unknown."""
    if geometry.dpr is None or geometry.dpr <= 0:
        return None, Unsupported(
            feature="css_coordinates",
            reason="DPR unknown; refusing to assume 1.0",
            needed_by="frame_to_css",
            frame_uid=frame_uid,
        )
    d = geometry.dpr
    return (box[0] / d, box[1] / d, box[2] / d, box[3] / d), None


def css_to_frame(
    box: Box, geometry: ViewportGeometry, frame_uid: str
) -> Tuple[Optional[Box], Optional[Unsupported]]:
    """CSS px -> frame pixels. Unsupported when DPR unknown."""
    if geometry.dpr is None or geometry.dpr <= 0:
        return None, Unsupported(
            feature="css_coordinates",
            reason="DPR unknown; refusing to assume 1.0",
            needed_by="css_to_frame",
            frame_uid=frame_uid,
        )
    d = geometry.dpr
    return (box[0] * d, box[1] * d, box[2] * d, box[3] * d), None


def scroll_compensate(
    box: Box,
    old_origin: Tuple[int, int],
    old_known: bool,
    new_origin: Tuple[int, int],
    new_known: bool,
    frame_uid: str,
) -> Tuple[Optional[Box], Optional[Unsupported], Optional[TransformRecord]]:
    """Shift a box from an old scroll origin into a new frame's coords.

    Returns Unsupported unless BOTH origins are known: silently carrying a
    box across an unknown scroll delta is exactly the stale-target failure
    this package exists to prevent.
    """
    if not (old_known and new_known):
        return None, Unsupported(
            feature="scroll_compensation",
            reason=f"scroll origin unknown (old_known={old_known}, new_known={new_known})",
            needed_by="scroll_compensate",
            frame_uid=frame_uid,
        ), None
    dx = new_origin[0] - old_origin[0]
    dy = new_origin[1] - old_origin[1]
    moved = (box[0] - dx, box[1] - dy, box[2] - dx, box[3] - dy)
    record = TransformRecord(
        kind="scroll_compensate",
        params={
            "old_origin": list(old_origin),
            "new_origin": list(new_origin),
            "delta": [dx, dy],
            "input": list(box),
            "output": list(moved),
        },
        frame_uid=frame_uid,
    )
    return moved, None, record


def expand_box(box: Box, factor: float, geometry: ViewportGeometry) -> Box:
    """Grow a box about its center by `factor`, clamped to the frame."""
    if factor < 1.0:
        raise ValueError(f"expand factor must be >= 1.0, got {factor}")
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0
    hw = (box[2] - box[0]) * factor / 2.0
    hh = (box[3] - box[1]) * factor / 2.0
    grown = (cx - hw, cy - hh, cx + hw, cy + hh)
    clamped, _ = clamp_box(grown, geometry.width_px, geometry.height_px)
    return clamped


def pairwise_overlaps(
    boxes: List[Tuple[str, Box]], iou_threshold: float = 0.0
) -> List[Dict[str, Any]]:
    """Overlap/occlusion hypotheses for layout context (descriptive only)."""
    out: List[Dict[str, Any]] = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ida, ba = boxes[i]
            idb, bb = boxes[j]
            iou = box_iou(ba, bb)
            cab = containment(ba, bb)
            cba = containment(bb, ba)
            if iou <= iou_threshold and cab <= 0.0 and cba <= 0.0:
                continue
            if cab > 0.8:
                relation = "b_covers_a"
            elif cba > 0.8:
                relation = "a_covers_b"
            elif iou > 0:
                relation = "overlaps"
            else:
                relation = "adjacent"
            out.append(
                {
                    "region_a": ida,
                    "region_b": idb,
                    "relation": relation,
                    "iou": iou,
                    "containment_a_in_b": cab,
                    "containment_b_in_a": cba,
                }
            )
    return out
