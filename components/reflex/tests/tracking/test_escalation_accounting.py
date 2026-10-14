"""Escalation + accounting tests. Synthetic parses only."""

import dataclasses
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reflex.perception.tracking.accounting import ResourceLedger
from reflex.perception.tracking.adapters import ModelRunAdapter
from reflex.perception.tracking.escalation import (
    Decision, EscalationBudget, EscalationLevel, EscalationPolicy, EscalationTrigger,
)
from reflex.perception.tracking.frame import FrameQuality
from reflex.perception.tracking.tracking import TrackStore
from synth_fixtures import failed_component_frec, make_frec

AD = ModelRunAdapter(source_id="esc-test", surface_epoch="s1", document_epoch="d1")


def _parse(frec=None, **kw):
    frec = frec or make_frec()
    parse = AD.parse_frame_record(frec)
    if kw:
        frame = dataclasses.replace(parse.frame, **kw)
        parse = dataclasses.replace(parse, frame=frame)
    return parse


def test_no_trigger_proceeds():
    policy = EscalationPolicy()
    store = TrackStore()
    parse = _parse()
    store.update(parse)
    decisions = policy.evaluate(parse, store)
    assert len(decisions) == 1
    assert decisions[0].decision == Decision.PROCEED
    assert decisions[0].level == EscalationLevel.NONE


def test_missing_coverage_escalates():
    policy = EscalationPolicy()
    store = TrackStore()
    frec = make_frec()
    frec["regions"] = []
    parse = _parse(frec)
    store.update(parse)
    decisions = policy.evaluate(parse, store)
    trig = [d for d in decisions if d.trigger == EscalationTrigger.MISSING_COVERAGE]
    assert len(trig) == 1 and trig[0].granted
    assert trig[0].level == EscalationLevel.GLOBAL_REINSPECT


def test_component_failure_requests_fresh_parse():
    policy = EscalationPolicy()
    store = TrackStore()
    parse = _parse(failed_component_frec("regions"))
    decisions = policy.evaluate(parse, store)
    assert decisions[0].trigger == EscalationTrigger.ACQUISITION_FAULT
    assert decisions[0].granted


def test_corrupt_frame_requests_reacquisition():
    policy = EscalationPolicy()
    store = TrackStore()
    parse = _parse(quality=FrameQuality.CORRUPTED)
    store.update(parse)
    decisions = policy.evaluate(parse, store)
    assert decisions[0].trigger == EscalationTrigger.ACQUISITION_FAULT


def test_ambiguity_escalates_crop():
    policy = EscalationPolicy()
    store = TrackStore()
    frec = make_frec()
    frec["regions"] = [{"box_xyxy": [100, 100, 200, 150], "score": 0.8,
                        "merge_source": "m", "ocr_labels": "X", "region_id": 0}]
    frec["captions"] = []
    store.update(_parse(frec))
    frec2 = make_frec(fname="b.png")
    frec2["regions"] = [
        {"box_xyxy": [102, 102, 202, 152], "score": 0.8, "merge_source": "m",
         "ocr_labels": "X", "region_id": 0},
        {"box_xyxy": [104, 104, 204, 154], "score": 0.79, "merge_source": "m",
         "ocr_labels": "X", "region_id": 1},
    ]
    frec2["captions"] = []
    parse2 = _parse(frec2)
    store.update(parse2)
    decisions = policy.evaluate(parse2, store)
    amb = [d for d in decisions if d.trigger == EscalationTrigger.AMBIGUITY]
    assert len(amb) == 1 and amb[0].level == EscalationLevel.EXPAND_CROP
    assert amb[0].granted and amb[0].decision == Decision.ESCALATE


def test_tiny_evidence_escalates():
    policy = EscalationPolicy()
    store = TrackStore()
    frec = make_frec()
    frec["regions"] = [{"box_xyxy": [10, 10, 18, 18], "score": 0.8,
                        "merge_source": "m", "ocr_labels": "i", "region_id": 0}]
    frec["captions"] = []
    parse = _parse(frec)
    store.update(parse)
    decisions = policy.evaluate(parse, store)
    tiny = [d for d in decisions if d.trigger == EscalationTrigger.TINY_EVIDENCE]
    assert len(tiny) == 1 and tiny[0].granted


def test_budget_exhaustion_denies_with_reason():
    budget = EscalationBudget(max_expanded_crops=1, periodic_refresh_every_n_frames=0)
    policy = EscalationPolicy(budget=budget)
    store = TrackStore()
    frec = make_frec()
    frec["regions"] = [{"box_xyxy": [10, 10, 18, 18], "score": 0.8,
                        "merge_source": "m", "ocr_labels": "i", "region_id": 0}]
    frec["captions"] = []
    parse = _parse(frec)
    store.update(parse)
    first = [d for d in policy.evaluate(parse, store)
             if d.trigger == EscalationTrigger.TINY_EVIDENCE][0]
    assert first.granted
    second = [d for d in policy.evaluate(parse, store)
              if d.trigger == EscalationTrigger.TINY_EVIDENCE][0]
    assert not second.granted and second.decision == Decision.ABSTAIN
    assert "exhausted" in second.reason


def test_periodic_refresh_fires():
    budget = EscalationBudget(periodic_refresh_every_n_frames=2)
    policy = EscalationPolicy(budget=budget)
    store = TrackStore()
    parse = _parse()
    store.update(parse)
    policy.evaluate(parse, store)
    decisions = policy.evaluate(parse, store)
    per = [d for d in decisions if d.trigger == EscalationTrigger.PERIODIC_REFRESH
           and d.level == EscalationLevel.GLOBAL_REINSPECT]
    assert len(per) == 1


def test_failed_expectation_requests_vlm():
    policy = EscalationPolicy()
    store = TrackStore()
    parse = _parse()
    u = store.update(parse)
    tid = u.created[0][0]
    frec2 = make_frec(fname="b.png")
    frec2["regions"] = []
    frec2["captions"] = []
    parse2 = _parse(frec2)
    store.update(parse2)
    store.update(parse2)  # second miss
    decisions = policy.evaluate(parse2, store, expected_track_ids=[tid])
    fe = [d for d in decisions if d.trigger == EscalationTrigger.FAILED_EXPECTATION]
    assert len(fe) == 1 and fe[0].level == EscalationLevel.STRONG_VLM


def test_ledger_records_raw_usage_only():
    ledger = ResourceLedger()
    ledger.frames_seen = 3
    ledger.add_stage_ms("match", 1.5)
    ledger.add_stage_ms("match", 2.5)
    ledger.add_component_failure("regions")
    d = ledger.to_dict()
    assert d["frames_seen"] == 3
    assert d["stage_ms_summary"]["match"]["n"] == 2.0
    assert d["component_failures"] == {"regions": 1}
    assert "price" not in str(d).lower() and "cost_usd" not in d


def test_policy_budget_state_serializes():
    policy = EscalationPolicy()
    state = policy.budget_state()
    assert state["used"]["expanded_crops"] == 0
    assert state["budget"]["trial_envelope_ref"] == ""
