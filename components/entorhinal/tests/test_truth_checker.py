"""E0 calibration tests: negative controls for the independent truth checker.

Plan EAP-20261004-v0.2, EVIDENCE-PLAN.md section E0. Each of the 11
predeclared negative controls must reject the wrong claim or abstain as
appropriate. This file also reproduces the historical evaluator defect
(read-only AST extraction; the old module is never imported) and writes the
calibration report to /tmp/entorhinal-coordinator/evidence/e0-calibration.json.
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest

from entorhinal.evals.truth_checker import (
    ASSERT_CAUSED,
    ASSERT_PREDICTED,
    ASSERT_VERIFIED,
    VERIF_INDEPENDENT,
    VERIF_REPORTED,
    Claim,
    ClaimVerdict,
    Evidence,
    ProbeItem,
    Verdict,
    build_calibration_report,
    check_claim,
    evaluate_probe_set,
    score_prediction,
)


def _t(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


T0 = _t(2026, 9, 1)
T1 = _t(2026, 9, 20, 12)
CUTOFF = _t(2026, 10, 1)
T2_START = _t(2026, 10, 2, 8)
T2_MID = _t(2026, 10, 2, 12)
T2_END = _t(2026, 10, 2, 16)
T3 = _t(2026, 10, 3, 12)
NOW = _t(2026, 10, 4, 12)

REPORT_PATH = Path("/tmp/entorhinal-coordinator/evidence/e0-calibration.json")
# Machine-local author path redacted for public release; the dependent tests skip
# when the old experiment is absent (by design), and the defect evidence stays
# self-contained via _minimal_token_overlap_scorer.
OLD_EXPERIMENT = Path(
    "<research-archives>/autonomous_runs/"
    "entorhinal/run_20260930_001/experiments/run_comparative_experiment.py"
)


Case = Tuple[Claim, List[Evidence], Optional[datetime], datetime, Verdict]


def case_nc01_passed_failed_inversion() -> Case:
    """Opposite outcome polarity must contradict, not match by token overlap."""
    claim = Claim(
        claim_id="NC-01",
        subject="engine.py tests",
        attribute="result",
        value="passed",
        outcome_status="passed",
        cited_ids=["ev-outcome"],
        text="engine.py tests passed",
    )
    evidence = Evidence(
        evidence_id="ev-outcome",
        subject="engine.py tests",
        attribute="result",
        value="failed",
        outcome_status="failed",
        observed_at=T1,
        committed_at=T1,
    )
    return claim, [evidence], None, NOW, Verdict.CONTRADICTED


def case_nc02_actor_target_swap() -> Case:
    claim = Claim(
        claim_id="NC-02",
        subject="artifact promotion",
        attribute="promoted",
        value="completed",
        actor="production",
        target="staging",
        text="production promoted the artifact to staging",
    )
    evidence = Evidence(
        evidence_id="ev-promo",
        subject="artifact promotion",
        attribute="promoted",
        value="completed",
        actor="staging",
        target="production",
    )
    return claim, [evidence], None, NOW, Verdict.CONTRADICTED


def case_nc03_changed_number() -> Case:
    claim = Claim(
        claim_id="NC-03",
        subject="worker pool",
        attribute="size",
        value="16",
        text="worker pool size is 16",
    )
    evidence = Evidence(
        evidence_id="ev-pool",
        subject="worker pool",
        attribute="size",
        value="8",
    )
    return claim, [evidence], None, NOW, Verdict.CONTRADICTED


def case_nc04_same_name_different_revision() -> Case:
    """Same path and value at a different revision is a different instance."""
    claim = Claim(
        claim_id="NC-04",
        subject="pipeline config",
        attribute="batch_size",
        value="64",
        artifact_path="configs/pipeline.yaml",
        artifact_revision="r42",
        text="pipeline.yaml at r42 sets batch_size 64",
    )
    evidence = Evidence(
        evidence_id="ev-config",
        subject="pipeline config",
        attribute="batch_size",
        value="64",
        artifact_path="configs/pipeline.yaml",
        artifact_revision="r41",
    )
    return claim, [evidence], None, NOW, Verdict.UNSUPPORTED


def case_nc05_future_outcome_before_cutoff() -> Case:
    """An outcome known only after the cutoff is not known at the cutoff."""
    claim = Claim(
        claim_id="NC-05",
        subject="nightly build",
        attribute="result",
        value="passed",
        outcome_status="passed",
        valid_at=T3,
        asserts=ASSERT_PREDICTED,
        text="the nightly build passed",
    )
    evidence = Evidence(
        evidence_id="ev-build",
        subject="nightly build",
        attribute="result",
        value="passed",
        outcome_status="passed",
        observed_at=T3,
        committed_at=T3,
        valid_from=T3,
    )
    return claim, [evidence], CUTOFF, NOW, Verdict.UNSUPPORTED


def case_nc06_expired_superseded_current_claim() -> Case:
    claim = Claim(
        claim_id="NC-06",
        subject="active branch",
        attribute="name",
        value="feat-x",
        as_of_current=True,
        text="the active branch is feat-x",
    )
    evidence = Evidence(
        evidence_id="ev-branch",
        subject="active branch",
        attribute="name",
        value="feat-x",
        committed_at=T0,
        valid_from=T0,
        valid_to=T1,
        superseded_by="ev-branch-new",
    )
    return claim, [evidence], None, NOW, Verdict.STALE


def case_nc07_irrelevant_known_entity() -> Case:
    """A cited source about engine.py must not support every claim about it."""
    claim = Claim(
        claim_id="NC-07",
        subject="engine.py",
        attribute="owner",
        value="team-a",
        cited_ids=["ev-engine"],
        text="engine.py is owned by team-a",
    )
    evidence = Evidence(
        evidence_id="ev-engine",
        subject="engine.py",
        attribute="test_result",
        value="passed",
    )
    return claim, [evidence], None, NOW, Verdict.UNSUPPORTED


def case_nc08_reported_vs_verified_completion() -> Case:
    claim = Claim(
        claim_id="NC-08",
        subject="migration task",
        attribute="completion",
        value="complete",
        asserts=ASSERT_VERIFIED,
        cited_ids=["ev-report"],
        text="the migration task is verified complete",
    )
    evidence = Evidence(
        evidence_id="ev-report",
        subject="migration task",
        attribute="completion",
        value="complete",
        verification=VERIF_REPORTED,
    )
    return claim, [evidence], None, NOW, Verdict.UNSUPPORTED


def case_nc09_self_explanation_vs_checked_cause() -> Case:
    claim = Claim(
        claim_id="NC-09",
        subject="checkout failure",
        attribute="cause",
        value="disk full",
        asserts=ASSERT_CAUSED,
        text="the checkout failed because the disk was full",
    )
    evidence = Evidence(
        evidence_id="ev-expl",
        subject="checkout failure",
        attribute="cause",
        value="disk full",
        verification=VERIF_REPORTED,
        cause_checked=False,
    )
    return claim, [evidence], None, NOW, Verdict.UNSUPPORTED


def case_nc10_outage_unknown_interval() -> Case:
    claim = Claim(
        claim_id="NC-10",
        subject="worker heartbeat",
        attribute="status",
        value="idle",
        valid_at=T2_MID,
        text="the worker was idle at midday",
    )
    gap = Evidence(
        evidence_id="ev-gap",
        valid_from=T2_START,
        valid_to=T2_END,
        is_gap=True,
    )
    return claim, [gap], None, NOW, Verdict.ABSTAIN


def case_nc11_revoked_content_historical_query() -> Case:
    claim = Claim(
        claim_id="NC-11",
        subject="api key rotation",
        attribute="status",
        value="rotated",
        valid_at=T1,
        cited_ids=["ev-secret"],
        text="the api key was rotated",
    )
    evidence = Evidence(
        evidence_id="ev-secret",
        subject="api key rotation",
        attribute="status",
        value="rotated",
        committed_at=T1,
        valid_from=T1,
        revoked=True,
    )
    return claim, [evidence], None, NOW, Verdict.ABSTAIN


CONTROL_CASES = [
    ("NC-01", "passed/failed inversion", case_nc01_passed_failed_inversion),
    ("NC-02", "actor/target swap", case_nc02_actor_target_swap),
    ("NC-03", "changed number/config", case_nc03_changed_number),
    ("NC-04", "same name different revision", case_nc04_same_name_different_revision),
    ("NC-05", "future outcome before cutoff", case_nc05_future_outcome_before_cutoff),
    ("NC-06", "expired/superseded current claim", case_nc06_expired_superseded_current_claim),
    ("NC-07", "irrelevant known entity", case_nc07_irrelevant_known_entity),
    ("NC-08", "reported vs verified completion", case_nc08_reported_vs_verified_completion),
    ("NC-09", "self-explanation vs checked cause", case_nc09_self_explanation_vs_checked_cause),
    ("NC-10", "outage-unknown interval", case_nc10_outage_unknown_interval),
    ("NC-11", "revoked content in historical query", case_nc11_revoked_content_historical_query),
]


def _run_case(builder) -> ClaimVerdict:
    claim, pool, cutoff, now, _ = builder()
    return check_claim(claim, pool, cutoff=cutoff, now=now)


def test_nc01_passed_failed_inversion() -> None:
    result = _run_case(case_nc01_passed_failed_inversion)
    assert result.verdict == Verdict.CONTRADICTED
    assert result.contradicting_ids == ["ev-outcome"]


def test_nc02_actor_target_swap() -> None:
    result = _run_case(case_nc02_actor_target_swap)
    assert result.verdict == Verdict.CONTRADICTED


def test_nc03_changed_number() -> None:
    result = _run_case(case_nc03_changed_number)
    assert result.verdict == Verdict.CONTRADICTED


def test_nc04_same_name_different_revision() -> None:
    result = _run_case(case_nc04_same_name_different_revision)
    assert result.verdict == Verdict.UNSUPPORTED
    assert any(reason.startswith("identity_mismatch") for reason in result.reasons)


def test_nc05_future_outcome_before_cutoff() -> None:
    result = _run_case(case_nc05_future_outcome_before_cutoff)
    assert result.verdict == Verdict.UNSUPPORTED
    assert "future_outcome_beyond_cutoff" in result.reasons
    assert result.dimensions["predictive"] == "pending"


def test_nc06_expired_superseded_current_claim() -> None:
    result = _run_case(case_nc06_expired_superseded_current_claim)
    assert result.verdict == Verdict.STALE
    assert result.dimensions["currentness"] == "stale"


def test_nc07_irrelevant_known_entity() -> None:
    result = _run_case(case_nc07_irrelevant_known_entity)
    assert result.verdict == Verdict.UNSUPPORTED
    # Relevance without semantic support: the exact cut the old scorer missed.
    assert result.dimensions["relevance"]["matched"] is True
    assert result.dimensions["semantic_support"]["supported"] is False
    assert result.dimensions["contradiction"]["contradicted"] is False


def test_nc08_reported_vs_verified_completion() -> None:
    result = _run_case(case_nc08_reported_vs_verified_completion)
    assert result.verdict == Verdict.UNSUPPORTED
    assert any("needs_independent_verification" in reason for reason in result.reasons)


def test_nc09_self_explanation_vs_checked_cause() -> None:
    result = _run_case(case_nc09_self_explanation_vs_checked_cause)
    assert result.verdict == Verdict.UNSUPPORTED
    assert any("cause_unchecked" in reason for reason in result.reasons)


def test_nc10_outage_unknown_interval() -> None:
    result = _run_case(case_nc10_outage_unknown_interval)
    assert result.verdict == Verdict.ABSTAIN
    assert "outage_unknown_interval" in result.reasons
    # Absence during an outage is unknown: neither idle nor down is decided.
    claim, pool, _, _, _ = case_nc10_outage_unknown_interval()
    negated = Claim(
        claim_id="NC-10b",
        subject=claim.subject,
        attribute=claim.attribute,
        value="down",
        valid_at=T2_MID,
    )
    assert check_claim(negated, pool, now=NOW).verdict == Verdict.ABSTAIN


def test_nc11_revoked_content_historical_query() -> None:
    result = _run_case(case_nc11_revoked_content_historical_query)
    assert result.verdict == Verdict.ABSTAIN
    assert "revoked_content_inaccessible" in result.reasons
    assert result.dimensions["attribution"]["ev-secret"] == "revoked"


# ---------------------------------------------------------------------------
# Historical defect reproduction (read-only; the old module is never imported)
# ---------------------------------------------------------------------------


def _extract_old_scorer():
    """AST-extract the old evaluator function source without importing it."""
    source = OLD_EXPERIMENT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate_fact_propositions"
    )
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    namespace: Dict[str, Any] = {
        "re": re,
        "List": List,
        "Dict": Dict,
        "Any": Any,
        "Set": Set,
        "Optional": Optional,
    }
    exec(compile(module, str(OLD_EXPERIMENT), "exec"), namespace)  # noqa: S102
    return namespace["evaluate_fact_propositions"]


def _minimal_token_overlap_scorer(retrieved: List[str], ground_truth: List[str], grounded: List[str]):
    """MINIMAL FAITHFUL RE-IMPLEMENTATION of the described scoring behavior.

    This is not the original code: it re-implements only the two documented
    mechanisms (token-overlap matching at >= min(2, len) and entity-substring
    grounding) so the defect evidence stays self-contained in this repo. The
    original logic is exercised read-only via AST extraction above.
    """
    def tokens(text: str) -> Set[str]:
        return set(re.findall(r"\w+", text.lower()))

    tp = sum(
        1
        for gt in ground_truth
        if any(len(tokens(gt) & tokens(rf)) >= min(2, len(tokens(gt))) for rf in retrieved)
    )
    fp = sum(
        1
        for rf in retrieved
        if not any(len(tokens(gt) & tokens(rf)) >= min(2, len(tokens(gt))) for gt in ground_truth)
    )
    hallucinations = sum(1 for rf in retrieved if not any(ent.lower() in rf.lower() for ent in grounded))
    return {
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else 0.0,
        "recall": round(tp / len(ground_truth), 4) if ground_truth else 0.0,
        "hallucination_rate": round(hallucinations / len(retrieved), 4) if retrieved else 0.0,
    }


def collect_defect_evidence() -> Dict[str, Any]:
    """Gather defect evidence for the calibration report (read-only)."""
    new_result = _run_case(case_nc01_passed_failed_inversion)
    evidence: Dict[str, Any] = {
        "method": "AST-extracted single function, read-only; old module never imported or executed",
        "source": str(OLD_EXPERIMENT),
        "opposite_outcome_call": {
            "retrieved": ["engine.py tests failed"],
            "ground_truth": ["engine.py tests passed"],
        },
        "new_checker_verdict_on_same_pair": new_result.verdict.value,
    }
    if OLD_EXPERIMENT.exists():
        scorer = _extract_old_scorer()
        evidence["old_result"] = scorer(
            ["engine.py tests failed"], ["engine.py tests passed"], ["engine.py"], [], ""
        )
        text = OLD_EXPERIMENT.read_text(encoding="utf-8")
        evidence["overwrite_line_present"] = 'c3_eval["hallucination_rate"] = 0.0' in text
    else:
        evidence["old_result"] = {"status": "source_absent_skipped"}
        evidence["overwrite_line_present"] = "unknown_source_absent"
    return evidence


@pytest.mark.skipif(not OLD_EXPERIMENT.exists(), reason="old Desktop experiment absent")
def test_old_scorer_scores_opposite_outcomes_identically() -> None:
    scorer = _extract_old_scorer()
    result = scorer(["engine.py tests failed"], ["engine.py tests passed"], ["engine.py"], [], "")
    assert result["precision"] == 1
    assert result["recall"] == 1
    assert result["hallucination_rate"] == 0.0


@pytest.mark.skipif(not OLD_EXPERIMENT.exists(), reason="old Desktop experiment absent")
def test_old_hallucination_overwrite_present() -> None:
    text = OLD_EXPERIMENT.read_text(encoding="utf-8")
    assert 'c3_eval["hallucination_rate"] = 0.0' in text


def test_minimal_reimplementation_demonstrates_flaw() -> None:
    result = _minimal_token_overlap_scorer(
        ["engine.py tests failed"], ["engine.py tests passed"], ["engine.py"]
    )
    assert result == {"precision": 1.0, "recall": 1.0, "hallucination_rate": 0.0}


def test_new_checker_rejects_what_old_scorer_accepted() -> None:
    new_result = _run_case(case_nc01_passed_failed_inversion)
    assert new_result.verdict == Verdict.CONTRADICTED
    old_like = _minimal_token_overlap_scorer(
        ["engine.py tests failed"], ["engine.py tests passed"], ["engine.py"]
    )
    assert old_like["precision"] == 1.0 and old_like["hallucination_rate"] == 0.0


# ---------------------------------------------------------------------------
# Positive and supplemental behavior
# ---------------------------------------------------------------------------


def test_supported_claim_with_matching_evidence() -> None:
    claim = Claim(
        claim_id="POS-01", subject="engine.py tests", attribute="result",
        value="failed", outcome_status="failed", cited_ids=["ev-ok"],
    )
    evidence = Evidence(
        evidence_id="ev-ok", subject="engine.py tests", attribute="result",
        value="failed", outcome_status="failed",
    )
    result = check_claim(claim, [evidence], now=NOW)
    assert result.verdict == Verdict.SUPPORTED
    assert result.dimensions["attribution"]["ev-ok"] == "accessible"


def test_verified_completion_with_independent_verifier() -> None:
    claim = Claim(
        claim_id="POS-02", subject="migration task", attribute="completion",
        value="complete", asserts=ASSERT_VERIFIED,
    )
    evidence = Evidence(
        evidence_id="ev-ver", subject="migration task", attribute="completion",
        value="complete", verification=VERIF_INDEPENDENT, verifier_id="runner-7",
    )
    assert check_claim(claim, [evidence], now=NOW).verdict == Verdict.SUPPORTED


def test_citation_without_entailment() -> None:
    claim = Claim(
        claim_id="CIT-01", subject="engine.py", attribute="owner",
        value="team-a", cited_ids=["missing-id", "ev-engine"],
    )
    evidence = Evidence(
        evidence_id="ev-engine", subject="engine.py", attribute="test_result", value="passed",
    )
    result = check_claim(claim, [evidence], now=NOW)
    assert result.verdict == Verdict.UNSUPPORTED
    assert result.dimensions["attribution"]["missing-id"] == "missing"
    assert "citation_without_entailment" in result.reasons


def test_score_prediction_pending_correct_incorrect() -> None:
    assert score_prediction("passed", None, False)["verdict"] == "pending"
    assert score_prediction("passed", "passed", True)["verdict"] == "correct"
    assert score_prediction("passed", "failed", True)["verdict"] == "incorrect"


# ---------------------------------------------------------------------------
# Fixed probe set and calibration report
# ---------------------------------------------------------------------------


def _probe(
    probe_id: str,
    claim: Claim,
    pool: List[Evidence],
    retrieved_ids: List[str],
    relevant_ids: Set[str],
    expected: Verdict,
    cutoff: Optional[datetime] = None,
) -> ProbeItem:
    return ProbeItem(
        probe_id=probe_id,
        claim=claim,
        pool=pool,
        retrieved_ids=retrieved_ids,
        relevant_ids=relevant_ids,
        expected=expected,
        cutoff=cutoff,
        now=NOW,
    )


def build_probe_set() -> List[ProbeItem]:
    c01, p01, _, _, _ = case_nc01_passed_failed_inversion()
    c02, p02, _, _, _ = case_nc02_actor_target_swap()
    c04, p04, _, _, _ = case_nc04_same_name_different_revision()
    c05, p05, cut05, _, _ = case_nc05_future_outcome_before_cutoff()
    c06, p06, _, _, _ = case_nc06_expired_superseded_current_claim()
    c07, p07, _, _, _ = case_nc07_irrelevant_known_entity()
    c08, p08, _, _, _ = case_nc08_reported_vs_verified_completion()
    c10, p10, _, _, _ = case_nc10_outage_unknown_interval()
    c11, p11, _, _, _ = case_nc11_revoked_content_historical_query()

    return [
        _probe(
            "P-01", Claim(claim_id="P-01", subject="engine.py tests", attribute="result",
                          value="failed", outcome_status="failed"),
            [Evidence(evidence_id="p01-rel", subject="engine.py tests", attribute="result",
                       value="failed", outcome_status="failed"),
             Evidence(evidence_id="p01-irr", subject="cafeteria menu", attribute="soup",
                       value="tomato")],
            ["p01-rel", "p01-irr"], {"p01-rel"}, Verdict.SUPPORTED,
        ),
        _probe(
            "P-02", Claim(claim_id="P-02", subject="migration task", attribute="completion",
                          value="complete", asserts=ASSERT_VERIFIED),
            [Evidence(evidence_id="p02-rel", subject="migration task", attribute="completion",
                       value="complete", verification=VERIF_INDEPENDENT, verifier_id="runner-7")],
            ["p02-rel"], {"p02-rel"}, Verdict.SUPPORTED,
        ),
        _probe(
            "P-03", Claim(claim_id="P-03", subject="nightly build", attribute="result",
                          value="passed", valid_at=T1),
            [Evidence(evidence_id="p03-a", subject="nightly build", attribute="result",
                       value="passed", committed_at=T1, valid_from=T0, valid_to=CUTOFF),
             Evidence(evidence_id="p03-b", subject="nightly build", attribute="result",
                       value="passed", committed_at=T1, valid_from=T0, valid_to=CUTOFF)],
            ["p03-a"], {"p03-a", "p03-b"}, Verdict.SUPPORTED,
        ),
        _probe(
            "P-04", Claim(claim_id="P-04", subject="engine.py tests", attribute="result",
                          value="passed", polarity=False),
            [Evidence(evidence_id="p04-rel", subject="engine.py tests", attribute="result",
                       value="passed", polarity=True)],
            ["p04-rel"], {"p04-rel"}, Verdict.CONTRADICTED,
        ),
        _probe("P-05", c01, p01, ["ev-outcome"], {"ev-outcome"}, Verdict.CONTRADICTED),
        _probe("P-06", c02, p02, ["ev-promo"], {"ev-promo"}, Verdict.CONTRADICTED),
        _probe("P-07", c04, p04, ["ev-config"], {"ev-config"}, Verdict.UNSUPPORTED),
        _probe("P-08", c05, p05, ["ev-build"], {"ev-build"}, Verdict.UNSUPPORTED, cut05),
        _probe("P-09", c07, p07, ["ev-engine"], {"ev-engine"}, Verdict.UNSUPPORTED),
        _probe("P-10", c08, p08, ["ev-report"], {"ev-report"}, Verdict.UNSUPPORTED),
        _probe("P-11", c06, p06, ["ev-branch"], {"ev-branch"}, Verdict.STALE),
        _probe(
            "P-12", Claim(claim_id="P-12", subject="feature flag", attribute="state",
                          value="enabled", as_of_current=True),
            [Evidence(evidence_id="p12-rel", subject="feature flag", attribute="state",
                       value="enabled", valid_from=T0, valid_to=T1)],
            ["p12-rel"], {"p12-rel"}, Verdict.STALE,
        ),
        _probe("P-13", c10, p10, ["ev-gap"], {"ev-gap"}, Verdict.ABSTAIN),
        _probe("P-14", c11, p11, ["ev-secret"], {"ev-secret"}, Verdict.ABSTAIN),
    ]


def test_probe_set_fully_correct() -> None:
    summary = evaluate_probe_set(build_probe_set())
    assert summary["total"] == 14
    assert summary["accuracy"] == {"correct": 14, "total": 14}
    assert summary["unsupported"] == {"count": 4, "total": 14}
    assert summary["contradicted"] == {"count": 3, "total": 14}
    assert summary["stale"] == {"count": 2, "total": 14}
    assert summary["stale_errors"] == {"count": 0, "total": 14}
    assert summary["retrieval_precision"] == {"relevant_retrieved": 14, "retrieved": 15}
    assert summary["retrieval_recall"] == {"relevant_retrieved": 14, "relevant": 15}
    assert summary["abstention"] == {"correct": 2, "expected_total": 2, "emitted_total": 2}
    assert summary["missed_relevant_context"] == {"count": 1, "total_relevant": 15}


def test_calibration_report_written() -> None:
    controls = []
    for control_id, name, builder in CONTROL_CASES:
        claim, pool, cutoff, now, expected = builder()
        result = check_claim(claim, pool, cutoff=cutoff, now=now)
        controls.append({
            "id": control_id,
            "name": name,
            "expected": expected.value,
            "actual": result.verdict.value,
            "pass": result.verdict == expected,
            "reasons": list(result.reasons),
        })
    summary = evaluate_probe_set(build_probe_set())
    report = build_calibration_report(controls, summary, collect_defect_evidence())
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert report["negative_control_summary"] == {"passed": 11, "total": 11}
    assert report["verdict"] == "CALIBRATED"
