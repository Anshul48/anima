"""Tracking/invalidation tests. Synthetic parses only; no live source."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reflex.perception.tracking.adapters import ModelRunAdapter
from reflex.perception.tracking.frame import FrameQuality
from reflex.perception.tracking.interfaces import StaticParse
from reflex.perception.tracking.tracking import (
    InvalidationReason, TrackStatus, TrackStore, TrackingThresholds,
)
from synth_fixtures import make_frec

AD = ModelRunAdapter(source_id="trk-test", surface_epoch="s1", document_epoch="d1")


def _parse(fname, regions=None, surface="s1", doc="d1", quality=None, scroll=None, known=False):
    frec = make_frec(fname=fname)
    if regions is not None:
        frec["regions"] = regions
        frec["captions"] = []
    parse = AD.parse_frame_record(frec)
    if quality is not None or scroll is not None or surface != "s1" or doc != "d1":
        import dataclasses
        geom = dataclasses.replace(parse.frame.geometry,
                                   scroll_origin_px=scroll or (0, 0),
                                   scroll_origin_known=known)
        frame = dataclasses.replace(parse.frame, geometry=geom, surface_epoch=surface,
                                    document_epoch=doc,
                                    quality=quality or parse.frame.quality)
        parse = dataclasses.replace(parse, frame=frame)
        for r in parse.regions:
            object.__setattr__(r, "frame_uid", frame.uid)
    return parse


def _region(rid, box, score=0.8, labels="Apply"):
    return {"box_xyxy": list(box), "score": score, "merge_source": "m",
            "ocr_labels": labels, "region_id": rid}


def test_stable_match_and_authorize():
    store = TrackStore()
    p1 = _parse("a.png")
    u1 = store.update(p1)
    assert len(u1.created) == 2 and not u1.full_resync
    p2 = _parse("b.png")
    u2 = store.update(p2)
    assert len(u2.matched) == 2
    tid = u1.created[0][0]
    box, stale = store.authorize_target(tid)
    assert stale is None and box == (5, 5, 100, 40)


def test_stale_target_rejected_after_new_frame_without_match():
    store = TrackStore()
    p1 = _parse("a.png")
    u1 = store.update(p1)
    tid = u1.created[0][0]
    p2 = _parse("b.png", regions=[_region(5, (500, 500, 560, 560), labels="Other")])
    store.update(p2)
    box, stale = store.authorize_target(tid)
    assert box is None and stale is not None
    assert stale.latest_frame_uid == "trk-test@b.png"


def test_uncertain_track_never_authorized():
    store = TrackStore()
    p1 = _parse("a.png")
    u1 = store.update(p1)
    tid = u1.created[0][0]
    # partial overlap: IoU ~0.27 in [move_iou, match_iou) even with text bonus
    moved = [_region(0, (60, 5, 155, 40)), _region(1, (300, 300, 360, 360), labels="")]
    store.update(_parse("b.png", regions=moved))
    track = store.tracks[tid]
    assert track.status == TrackStatus.UNCERTAIN
    assert track.invalidation_reason == InvalidationReason.MOVED
    box, stale = store.authorize_target(tid)
    assert box is None


def test_epoch_change_full_resync():
    store = TrackStore()
    u1 = store.update(_parse("a.png"))
    u2 = store.update(_parse("b.png", surface="s2"))
    assert u2.full_resync and u2.resync_reason.startswith("surface epoch")
    assert len(u2.invalidated) == 2
    for tid, _ in u1.created:
        assert store.tracks[tid].status.name == "INVALIDATED"


def test_document_navigation_full_resync():
    store = TrackStore()
    store.update(_parse("a.png"))
    u2 = store.update(_parse("b.png", doc="d2"))
    assert u2.full_resync and "document epoch" in u2.resync_reason


def test_known_scroll_compensates():
    store = TrackStore()
    store.update(_parse("a.png", scroll=(0, 50), known=True))
    # scrolled back to origin: content shifts down 50px in frame coords
    shifted = [_region(0, (5, 55, 100, 90)), _region(1, (300, 350, 360, 410), labels="")]
    u2 = store.update(_parse("b.png", regions=shifted, scroll=(0, 0), known=True))
    assert len(u2.matched) == 2, u2.to_dict()


def test_unknown_scroll_is_uncertain_not_silent():
    store = TrackStore()
    store.update(_parse("a.png", scroll=(0, 0), known=True))
    u2 = store.update(_parse("b.png"))  # scroll unknown now
    assert any("scroll_unknown" in r for _, r in u2.uncertain)


def test_overlay_invalidates_covered_track():
    store = TrackStore()
    p1 = _parse("a.png")
    u1 = store.update(p1)
    overlay = [(0, 0, 200, 100)]  # covers region r0 fully
    u2 = store.update(_parse("b.png"), overlay_boxes=overlay)
    assert (u1.created[0][0], "overlay_occlusion") in u2.invalidated
    box, stale = store.authorize_target(u1.created[0][0])
    assert box is None


def test_attribute_change_requires_refresh():
    store = TrackStore()
    u1 = store.update(_parse("a.png"))
    u2 = store.update(_parse("b.png"), attribute_hints={"r0": {"is_enabled": [True, False]}})
    assert (u1.created[0][0], "attribute_change") in u2.uncertain
    t = store.tracks[u1.created[0][0]]
    assert t.invalidation_reason == InvalidationReason.ATTRIBUTE_CHANGE
    assert t.predicted_box_xyxy is not None  # prediction kept, not authorized


def test_dynamic_pixels_uncertain():
    store = TrackStore()
    u1 = store.update(_parse("a.png"))
    u2 = store.update(_parse("b.png"), pixel_change_by_region={"r0": 0.6})
    assert (u1.created[0][0], "dynamic_pixels") in u2.uncertain


def test_ambiguity_between_near_duplicates():
    store = TrackStore()
    p1 = _parse("a.png", regions=[_region(0, (100, 100, 200, 150))])
    u1 = store.update(p1)
    dupes = [_region(0, (102, 102, 202, 152)), _region(1, (104, 104, 204, 154))]
    u2 = store.update(_parse("b.png", regions=dupes))
    assert (u1.created[0][0], "ambiguous") in u2.uncertain


def test_missing_then_lost():
    store = TrackStore(thresholds=TrackingThresholds(max_missing_frames=1))
    u1 = store.update(_parse("a.png", regions=[_region(0, (100, 100, 200, 150))]))
    u2 = store.update(_parse("b.png", regions=[]))
    assert (u1.created[0][0], "missing") in u2.uncertain
    u3 = store.update(_parse("c.png", regions=[]))
    assert u1.created[0][0] in u3.lost


def test_tiny_flagged():
    store = TrackStore()
    u1 = store.update(_parse("a.png", regions=[_region(0, (10, 10, 18, 18))]))
    assert store.tracks[u1.created[0][0]].tiny is True


def test_quality_fault_no_matching():
    store = TrackStore()
    store.update(_parse("a.png"))
    u2 = store.update(_parse("b.png", quality=FrameQuality.CORRUPTED))
    assert u2.matched == [] and len(u2.uncertain) == 2
    assert all("quality_fault" in r for _, r in u2.uncertain)


def test_unknown_track_authorize():
    store = TrackStore()
    box, stale = store.authorize_target("trk:nope:1")
    assert box is None and stale.reason == "unknown track"


def test_update_serializes_with_thresholds():
    store = TrackStore()
    u = store.update(_parse("a.png"))
    d = u.to_dict()
    assert d["thresholds"]["match_iou"] == 0.5
    assert "frame_uid" in d
