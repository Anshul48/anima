"""Frame identity, freshness, geometry, transforms. All synthetic."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reflex.perception.tracking.frame import (
    FrameIdentity, FrameQuality, Unsupported, ViewportGeometry,
    frame_from_observation_dict,
)
from reflex.perception.tracking.transforms import (
    box_iou, clamp_box, containment, css_to_frame, expand_box, frame_to_css,
    make_crop, scroll_compensate,
)
from synth_fixtures import make_obs_dict


def _geom(**kw):
    base = dict(width_px=800, height_px=600)
    base.update(kw)
    return ViewportGeometry(**base)


def _frame(**kw):
    base = dict(source_id="s/linux", frame_id="f1", pixel_sha256="ab" * 32,
                geometry=_geom(), received_ms=1000.0)
    base.update(kw)
    return FrameIdentity(**base)


def test_freshness_window():
    f = _frame(received_ms=1000.0, freshness_duration_ms=500.0)
    assert f.is_fresh(now_ms=1200.0)
    assert not f.is_fresh(now_ms=1600.0)


def test_negative_age_never_fresh():
    f = _frame(received_ms=2000.0)  # dated ahead of caller clock
    assert not f.is_fresh(now_ms=1000.0)


def test_roundtrip():
    f = _frame()
    g = FrameIdentity.from_dict(f.to_dict())
    assert g.uid == f.uid and g.geometry.width_px == 800


def test_css_unknown_dpr_is_unsupported_not_default():
    g = _geom(dpr=None)
    val, unsup = g.css_size()
    assert val is None and isinstance(unsup, Unsupported)
    box, unsup2 = frame_to_css((0, 0, 10, 10), g, "u")
    assert box is None and "1.0" in unsup2.reason
    box, unsup3 = css_to_frame((0, 0, 10, 10), g, "u")
    assert box is None


def test_css_known_dpr():
    g = _geom(dpr=2.0)
    (w, h), unsup = g.css_size()
    assert (w, h) == (400, 300) and unsup is None


def test_crop_roundtrip_mapping():
    view, unsup = make_crop((100, 100, 200, 150), _geom(), "u", pad_px=8)
    assert unsup is None
    assert view.crop_box_frame_px == (92, 92, 208, 158)
    assert view.to_frame((0, 0, 10, 10)) == (92, 92, 102, 102)
    assert view.to_crop((92, 92, 102, 102)) == (0, 0, 10, 10)
    assert view.records[0].kind == "crop"


def test_crop_clamps_at_edge_and_records():
    view, unsup = make_crop((0, 0, 50, 50), _geom(), "u", pad_px=20)
    assert unsup is None
    assert view.crop_box_frame_px == (0, 0, 70, 70)
    assert view.records[0].params["was_clamped"] is True


def test_crop_rejects_invalid_box():
    view, unsup = make_crop((50, 50, 10, 10), _geom(), "u")
    assert view is None and isinstance(unsup, Unsupported)
    view, unsup = make_crop((0, 0, 10, float("nan")), _geom(), "u")
    assert view is None


def test_scroll_compensate_requires_both_known():
    moved, unsup, rec = scroll_compensate((100, 100, 200, 200), (0, 0), True, (0, 50), True, "u")
    assert moved == (100, 50, 200, 150) and rec is not None
    moved, unsup, rec = scroll_compensate((100, 100, 200, 200), (0, 0), False, (0, 50), True, "u")
    assert moved is None and rec is None and "unknown" in unsup.reason


def test_clamp_and_expand():
    box, was = clamp_box((-5, -5, 900, 700), 800, 600)
    assert box == (0, 0, 800, 600) and was is True
    grown = expand_box((100, 100, 200, 200), 2.0, _geom())
    assert grown == (50, 50, 250, 250)
    try:
        expand_box((0, 0, 10, 10), 0.5, _geom())
    except ValueError:
        pass
    else:
        raise AssertionError("shrink factor must raise")


def test_iou_containment_basics():
    assert box_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert box_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert containment((2, 2, 4, 4), (0, 0, 10, 10)) == 1.0


def test_obs_bridge_preserves_identity():
    obs = make_obs_dict("obs-9")
    frame, unsupported = frame_from_observation_dict(
        obs, pixel_sha256="cd" * 32, width_px=800, height_px=600)
    assert frame.frame_id == "obs-9"
    assert frame.source_id == "BrowserSource/linux"
    assert frame.modality_status["screenshot"] == "ok: 800x600"
    assert any(u.feature == "dpr" for u in unsupported)  # DPR honestly unknown


def test_obs_bridge_missing_dims_unsupported():
    obs = make_obs_dict()
    obs["graph"]["viewport_size"] = [0, 0]
    frame, unsupported = frame_from_observation_dict(obs)
    assert any(u.feature == "frame_dimensions" for u in unsupported)
