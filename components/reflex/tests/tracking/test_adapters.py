"""Model-output adapter tests. All fixtures SYNTHETIC (see synth_fixtures).
Real-inference adapter validation is a separate gate with real run outputs."""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reflex.perception.tracking.adapters import (
    FrameBindingError, ModelRunAdapter, static_parse_to_node_dicts,
)
from reflex.perception.tracking.frame import FrameQuality
from reflex.perception.tracking.interfaces import ComponentState, HypothesisStatus
from synth_fixtures import SYNTHETIC_TAG, failed_component_frec, make_frec

AD = ModelRunAdapter(source_id="test-source", surface_epoch="s1", document_epoch="d1")


def test_valid_record_binds_full_identity():
    parse = AD.parse_frame_record(make_frec(), expected_sha256="aa" * 32,
                                  expected_dims=(800, 600))
    assert parse.ok()
    assert parse.frame.uid == "test-source@frame_0.png"
    assert parse.frame.pixel_sha256 == "aa" * 32
    assert len(parse.regions) == 2 and len(parse.ocr) == 2
    assert len(parse.hypotheses) == 1
    assert parse.ocr[0].consumed_by_region == "r0"
    assert parse.ocr[1].consumed_by_region is None
    assert parse.regions[0].ocr_labels == "Apply"
    assert parse.layout.num_regions == 2


def test_hypothesis_has_no_confidence():
    parse = AD.parse_frame_record(make_frec())
    hyp = parse.hypotheses[0]
    assert hyp.status == HypothesisStatus.HYPOTHESIS
    assert not hasattr(hyp, "confidence")
    assert hyp.uncertainty["mean_token_logprob"] == -0.62
    assert hyp.nearby_texts[0]["text"] == "Cancel"


def test_failed_detector_is_failed_not_empty():
    parse = AD.parse_frame_record(failed_component_frec("regions"))
    assert parse.component_states["regions"] == ComponentState.FAILED
    assert "detector" in parse.component_errors["regions"] or "broke" in parse.component_errors["regions"]
    assert parse.regions == [] and not parse.ok()


def test_failed_ocr_and_caption():
    parse = AD.parse_frame_record(failed_component_frec("ocr"))
    assert parse.component_states["ocr"] == ComponentState.FAILED
    parse = AD.parse_frame_record(failed_component_frec("captions"))
    assert parse.component_states["caption"] == ComponentState.FAILED


def test_empty_lists_are_ok_not_failed():
    frec = make_frec()
    frec["regions"] = []
    frec["ocr"] = []
    frec["captions"] = []
    parse = AD.parse_frame_record(frec)
    assert parse.component_states["regions"] == ComponentState.OK
    assert parse.layout.num_regions == 0


def test_sha_mismatch_fails_loudly():
    try:
        AD.parse_frame_record(make_frec(), expected_sha256="bb" * 32)
    except FrameBindingError as exc:
        assert "sha256 mismatch" in str(exc)
    else:
        raise AssertionError("must refuse wrong pixels")


def test_dim_mismatch_fails_loudly():
    try:
        AD.parse_frame_record(make_frec(), expected_dims=(640, 480))
    except FrameBindingError as exc:
        assert "dimension mismatch" in str(exc)
    else:
        raise AssertionError("must refuse wrong dims")


def test_malformed_box_dropped_with_reason():
    frec = make_frec()
    frec["regions"].append({"box_xyxy": [5, 5, 5, 5], "score": 0.9, "region_id": 9})
    frec["regions"].append({"box_xyxy": ["x", 0, 1, 1], "region_id": 10})
    parse = AD.parse_frame_record(frec)
    assert len(parse.regions) == 2
    assert "dropped_entries" in parse.component_errors


def test_out_of_frame_box_clamped_and_flagged():
    frec = make_frec()
    frec["regions"][0]["box_xyxy"] = [-50, -50, 900, 700]
    parse = AD.parse_frame_record(frec)
    assert parse.regions[0].box_xyxy == (0, 0, 800, 600)
    assert parse.regions[0].out_of_frame_clamped is True


def test_run_dir_intake(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    manifest = {"dataset_id": "synth", "source_id": "synth",
                "frames": [{"file": "a.png", "sha256": "aa" * 32,
                            "width": 800, "height": 600}]}
    man_path = tmp_path / "manifest.json"
    man_path.write_text(json.dumps(manifest))
    good = make_frec(fname="a.png")
    (frames / "a.png.json").write_text(json.dumps(good))
    bad = make_frec(fname="ghost.png")  # no manifest entry
    (frames / "ghost.png.json").write_text(json.dumps(bad))
    (frames / "junk.json").write_text("{not json")
    parses, failures = AD.parse_run_dir(str(tmp_path), str(man_path))
    assert len(parses) == 1 and len(failures) == 2
    assert any("manifest" in f["error"] for f in failures)
    assert any("unreadable" in f["error"] for f in failures)


def test_node_dict_mapping_preserves_provenance():
    parse = AD.parse_frame_record(make_frec())
    nodes, unsupported = static_parse_to_node_dicts(parse)
    assert len(nodes) == 2
    n0 = nodes[0]
    assert n0["source"] == "vision"
    assert n0["attributes"]["pixel_sha256"] == "aa" * 32
    assert n0["attributes"]["frame_uid"] == parse.frame.uid
    assert n0["confidence"] == 0.82
    assert n0["label"] == "Apply"


def test_node_dict_missing_score_is_explicit():
    frec = make_frec()
    del frec["regions"][1]["score"]
    parse = AD.parse_frame_record(frec)
    assert parse.regions[1].score is None
    nodes, unsupported = static_parse_to_node_dicts(parse)
    assert nodes[1]["attributes"]["confidence_uncalibrated"] is True
    assert any(u.feature == "region_confidence" for u in unsupported)


def test_static_parse_roundtrip():
    parse = AD.parse_frame_record(make_frec())
    from reflex.perception.tracking.interfaces import StaticParse
    back = StaticParse.from_dict(parse.to_dict())
    assert back.frame.uid == parse.frame.uid
    assert len(back.hypotheses) == 1
    assert SYNTHETIC_TAG  # fixtures labeled synthetic
