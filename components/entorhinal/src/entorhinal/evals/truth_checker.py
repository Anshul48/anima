"""Independent mechanical truth checker for Entorhinal evaluation (gate E0).

Plan EAP-20261004-v0.2, EVIDENCE-PLAN.md section E0. This module replaces the
defective historical comparative scorer for new experiments; it does not
rewrite history and it never imports the old experiment code.

The old scorer matched claims to ground truth by token overlap
(``overlap >= min(2, len(gt_tokens))``) and counted a statement as grounded
whenever a known entity substring appeared in it. It therefore scores
``engine.py tests failed`` against ``engine.py tests passed`` as
precision=1/recall=1/hallucination=0, and the old script additionally
overwrote one condition's hallucination metric with zero after evaluation.

This checker instead compares, dimension by dimension:

- subject, predicate/attribute, value, polarity
- role direction (actor vs target)
- conditions (claim conditions must be covered by the evidence)
- artifact/configuration identity (path AND hash/revision; a bare name match
  at a different revision is not support)
- time/validity (valid-time window, knowledge cutoff, currentness)
- outcome status

and reports six separated dimensions: relevance, attribution, semantic
support, contradiction, currentness, and predictive correctness. Relevance or
a bare entity mention never implies support; a cited evidence ID, a hash
link, or a numeric confidence is not entailment.

Method is mechanical-only: normalized string/numeric equality, explicit
validity windows, and explicit verification flags. There is no LLM judge in
this module. Any future supplemental judge must itself be calibrated on the
E0 negative controls before use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set


CHECKER_VERSION = "0.1.0"
CHECKER_METHOD = "mechanical-only (no LLM judge)"


class Verdict(str, Enum):
    """Possible outcomes of checking one claim against evidence."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    ABSTAIN = "abstain"


# Assertion strengths a claim may carry.
ASSERT_OBSERVED = "observed"
ASSERT_REPORTED = "reported"
ASSERT_VERIFIED = "verified"  # requires independently verified evidence
ASSERT_CAUSED = "caused"  # requires checked-cause evidence
ASSERT_PREDICTED = "predicted"  # outcome forecast; scored via score_prediction

# Evidence verification levels.
VERIF_OBSERVED = "observed"
VERIF_REPORTED = "reported"
VERIF_INDEPENDENT = "independently_verified"


@dataclass
class Claim:
    """A single checkable claim about task state, an artifact, or an outcome."""

    claim_id: str
    subject: str
    attribute: str
    value: str
    polarity: bool = True  # True asserts, False negates
    actor: Optional[str] = None
    target: Optional[str] = None
    conditions: Dict[str, str] = field(default_factory=dict)
    artifact_path: Optional[str] = None
    artifact_hash: Optional[str] = None
    artifact_revision: Optional[str] = None
    outcome_status: Optional[str] = None
    valid_at: Optional[datetime] = None  # valid time the claim is about
    as_of_current: bool = False  # claim is about current state
    asserts: str = ASSERT_OBSERVED
    cited_ids: List[str] = field(default_factory=list)
    text: str = ""


@dataclass
class Evidence:
    """One evidence record the checker may cite for support or contradiction."""

    evidence_id: str
    subject: str = ""
    attribute: str = ""
    value: str = ""
    polarity: bool = True
    actor: Optional[str] = None
    target: Optional[str] = None
    conditions: Dict[str, str] = field(default_factory=dict)
    artifact_path: Optional[str] = None
    artifact_hash: Optional[str] = None
    artifact_revision: Optional[str] = None
    outcome_status: Optional[str] = None
    observed_at: Optional[datetime] = None
    committed_at: Optional[datetime] = None  # knowledge time
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    superseded_by: Optional[str] = None
    revoked: bool = False
    verification: str = VERIF_OBSERVED
    verifier_id: Optional[str] = None
    cause_checked: bool = False
    is_gap: bool = False  # outage-unknown marker over [valid_from, valid_to]


@dataclass
class ClaimVerdict:
    """Result of checking one claim, with separated dimensions."""

    claim_id: str
    verdict: Verdict
    reasons: List[str]
    supporting_ids: List[str]
    contradicting_ids: List[str]
    relevant_ids: List[str]
    dimensions: Dict[str, Any]


def _norm(text: Optional[str]) -> str:
    if not isinstance(text, str):
        return ""
    return text.strip().casefold()


def _values_equal(left: str, right: str) -> bool:
    """Mechanical value equality: normalized strings, with numeric awareness."""
    if _norm(left) == _norm(right):
        return True
    try:
        return float(str(left).strip()) == float(str(right).strip())
    except (TypeError, ValueError):
        return False


def _covers(evidence: Evidence, moment: Optional[datetime]) -> bool:
    """Whether the evidence validity window covers the claim's valid time."""
    if moment is None:
        return True
    if evidence.valid_from is not None and moment < evidence.valid_from:
        return False
    if evidence.valid_to is not None and moment > evidence.valid_to:
        return False
    return True


def _within_cutoff(evidence: Evidence, cutoff: Optional[datetime]) -> bool:
    """Knowledge-cutoff gate: unknown commit time cannot satisfy a cutoff."""
    if cutoff is None:
        return True
    return evidence.committed_at is not None and evidence.committed_at <= cutoff


def _is_current(evidence: Evidence, now: datetime) -> bool:
    if evidence.valid_to is not None and evidence.valid_to < now:
        return False
    if evidence.superseded_by is not None:
        return False
    return True


def _epistemic_ok(claim: Claim, evidence: Evidence) -> bool:
    """Whether the evidence meets the strength the claim asserts.

    A report of completion never verifies completion, and a self-explanation
    never checks a cause. Predictions are never supported as known facts by
    this function; use score_prediction against a later outcome instead.
    """
    if claim.asserts == ASSERT_VERIFIED:
        return evidence.verification == VERIF_INDEPENDENT
    if claim.asserts == ASSERT_CAUSED:
        return evidence.cause_checked
    if claim.asserts == ASSERT_PREDICTED:
        return False
    return True


def check_claim(
    claim: Claim,
    evidence_pool: Sequence[Evidence],
    cutoff: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> ClaimVerdict:
    """Check one claim against an evidence pool.

    Args:
        claim: The claim to check.
        evidence_pool: Candidate evidence records.
        cutoff: Knowledge cutoff; evidence committed after it is invisible,
            and unknown commit times cannot satisfy it.
        now: Reference time for currentness; defaults to UTC now.

    Precedence: contradiction beats support (conflicting observations stay
    visible); outage-unknown and revoked-only inputs abstain rather than
    deciding; superseded/expired matches for a current-state claim are stale;
    anything without full semantic support is unsupported.
    """
    moment = now or datetime.now(timezone.utc)
    pool: Dict[str, Evidence] = {item.evidence_id: item for item in evidence_pool}

    # Attribution: cited IDs are resolved, never trusted blindly.
    attribution: Dict[str, str] = {}
    for cited in claim.cited_ids:
        cited_evidence = pool.get(cited)
        if cited_evidence is None:
            attribution[cited] = "missing"
        elif cited_evidence.revoked:
            attribution[cited] = "revoked"
        elif not _within_cutoff(cited_evidence, cutoff):
            attribution[cited] = "beyond_cutoff"
        else:
            attribution[cited] = "accessible"

    usable = [
        item
        for item in evidence_pool
        if not item.revoked and not item.is_gap and _within_cutoff(item, cutoff)
    ]
    gaps = [
        item
        for item in evidence_pool
        if item.is_gap and not item.revoked and _within_cutoff(item, cutoff)
    ]
    revoked_matches = [
        item.evidence_id
        for item in evidence_pool
        if item.revoked
        and _norm(item.subject) == _norm(claim.subject)
        and _norm(item.attribute) == _norm(claim.attribute)
    ]

    supporting: List[str] = []
    contradicting: List[str] = []
    relevant: List[str] = []
    direct: List[str] = []
    stale_candidates: List[str] = []
    reasons: List[str] = []

    claim_conditions = {str(k).strip().casefold(): str(v) for k, v in claim.conditions.items()}

    for item in usable:
        item_conditions = {str(k).strip().casefold(): str(v) for k, v in item.conditions.items()}
        subject_match = bool(_norm(claim.subject)) and _norm(item.subject) == _norm(claim.subject)
        attribute_match = bool(_norm(claim.attribute)) and _norm(item.attribute) == _norm(claim.attribute)
        value_match = _values_equal(claim.value, item.value) if claim.value or item.value else True
        polarity_match = claim.polarity == item.polarity

        if subject_match or attribute_match:
            relevant.append(item.evidence_id)
        if subject_match and attribute_match:
            direct.append(item.evidence_id)

        # Role direction.
        actor_ok = claim.actor is None or (
            item.actor is not None and _norm(claim.actor) == _norm(item.actor)
        )
        target_ok = claim.target is None or (
            item.target is not None and _norm(claim.target) == _norm(item.target)
        )
        role_mismatch = (
            claim.actor is not None
            and item.actor is not None
            and _norm(claim.actor) != _norm(item.actor)
        ) or (
            claim.target is not None
            and item.target is not None
            and _norm(claim.target) != _norm(item.target)
        )

        # Conditions: the evidence must cover every condition the claim states.
        condition_conflict = any(
            key in item_conditions and not _values_equal(val, item_conditions[key])
            for key, val in claim_conditions.items()
        )
        conditions_covered = all(
            key in item_conditions and _values_equal(val, item_conditions[key])
            for key, val in claim_conditions.items()
        )

        # Artifact identity: path plus revision/hash. A bare name at a
        # different revision is a different artifact instance.
        path_conflict = (
            claim.artifact_path is not None
            and item.artifact_path is not None
            and _norm(claim.artifact_path) != _norm(item.artifact_path)
        )
        path_ok = claim.artifact_path is None or (
            item.artifact_path is not None
            and _norm(claim.artifact_path) == _norm(item.artifact_path)
        )
        revision_conflict = (
            claim.artifact_revision is not None
            and item.artifact_revision is not None
            and _norm(claim.artifact_revision) != _norm(item.artifact_revision)
        )
        hash_conflict = (
            claim.artifact_hash is not None
            and item.artifact_hash is not None
            and _norm(claim.artifact_hash) != _norm(item.artifact_hash)
        )
        revision_ok = claim.artifact_revision is None or (
            item.artifact_revision is not None
            and _norm(claim.artifact_revision) == _norm(item.artifact_revision)
        )
        hash_ok = claim.artifact_hash is None or (
            item.artifact_hash is not None
            and _norm(claim.artifact_hash) == _norm(item.artifact_hash)
        )
        identity_blocked = path_conflict or revision_conflict or hash_conflict
        identity_ok = path_ok and revision_ok and hash_ok

        # Outcome status.
        if claim.outcome_status is None:
            outcome_ok = True
            outcome_mismatch = False
        elif item.outcome_status is None:
            outcome_ok = False
            outcome_mismatch = False
        else:
            outcome_ok = _norm(claim.outcome_status) == _norm(item.outcome_status)
            outcome_mismatch = not outcome_ok

        covers = _covers(item, claim.valid_at)
        value_mismatch = bool(claim.value or item.value) and not value_match

        base_match = (
            subject_match
            and attribute_match
            and value_match
            and polarity_match
            and actor_ok
            and target_ok
            and conditions_covered
            and identity_ok
            and outcome_ok
            and covers
        )

        if base_match and not identity_blocked:
            if not _epistemic_ok(claim, item):
                if claim.asserts == ASSERT_VERIFIED:
                    reasons.append(f"needs_independent_verification:{item.evidence_id}")
                elif claim.asserts == ASSERT_CAUSED:
                    reasons.append(f"cause_unchecked:{item.evidence_id}")
                elif claim.asserts == ASSERT_PREDICTED:
                    reasons.append(f"prediction_unresolved:{item.evidence_id}")
            elif claim.as_of_current and not _is_current(item, moment):
                stale_candidates.append(item.evidence_id)
            else:
                supporting.append(item.evidence_id)
        elif subject_match and attribute_match and identity_blocked:
            reasons.append(f"identity_mismatch:{item.evidence_id}")

        # Contradiction: same subject/predicate about the same artifact and
        # time, but a differing value, polarity, outcome, roles, or condition.
        if claim.as_of_current:
            time_compatible = _is_current(item, moment)
        else:
            time_compatible = covers
        artifact_compatible = not identity_blocked and (
            claim.artifact_path is None
            or (item.artifact_path is not None and path_ok)
        )
        if (
            subject_match
            and attribute_match
            and artifact_compatible
            and time_compatible
            and (
                value_mismatch
                or not polarity_match
                or outcome_mismatch
                or role_mismatch
                or condition_conflict
            )
        ):
            contradicting.append(item.evidence_id)

    # Outage-unknown: a gap covering the claim time with no direct evidence.
    gap_moment = claim.valid_at if claim.valid_at is not None else (moment if claim.as_of_current else None)
    gap_covers = gap_moment is not None and any(
        (gap.valid_from is None or gap_moment >= gap.valid_from)
        and (gap.valid_to is None or gap_moment <= gap.valid_to)
        for gap in gaps
    )

    future_beyond_cutoff = (
        cutoff is not None and claim.valid_at is not None and claim.valid_at > cutoff
    )

    if contradicting:
        verdict = Verdict.CONTRADICTED
        reasons.extend(f"contradicted_by:{item_id}" for item_id in contradicting)
        if supporting:
            reasons.append("conflicting_observations_visible")
    elif supporting:
        verdict = Verdict.SUPPORTED
        reasons.extend(f"supported_by:{item_id}" for item_id in supporting)
    elif gap_covers and not direct:
        verdict = Verdict.ABSTAIN
        reasons.append("outage_unknown_interval")
    elif revoked_matches and not direct:
        verdict = Verdict.ABSTAIN
        reasons.append("revoked_content_inaccessible")
    elif stale_candidates:
        verdict = Verdict.STALE
        reasons.extend(f"stale_candidate:{item_id}" for item_id in stale_candidates)
    else:
        verdict = Verdict.UNSUPPORTED
        if future_beyond_cutoff:
            reasons.append("future_outcome_beyond_cutoff")
        if relevant and not direct:
            reasons.append("relevant_but_no_semantic_support")
        if direct and not supporting and not contradicting:
            reasons.append("direct_match_without_full_support")
        if not relevant:
            reasons.append("no_relevant_evidence")
        if any(status != "accessible" for status in attribution.values()):
            reasons.append("citation_without_entailment")

    if claim.as_of_current:
        currentness = "stale" if verdict == Verdict.STALE else "current"
    elif claim.valid_at is not None:
        currentness = "not_applicable_historical"
    else:
        currentness = "not_applicable"

    dimensions: Dict[str, Any] = {
        "relevance": {"matched": bool(relevant), "evidence_ids": sorted(relevant)},
        "attribution": dict(attribution),
        "semantic_support": {"supported": bool(supporting), "evidence_ids": sorted(supporting)},
        "contradiction": {"contradicted": bool(contradicting), "evidence_ids": sorted(contradicting)},
        "currentness": currentness,
        "predictive": "pending" if claim.asserts == ASSERT_PREDICTED else "not_prediction",
    }
    return ClaimVerdict(
        claim_id=claim.claim_id,
        verdict=verdict,
        reasons=reasons,
        supporting_ids=sorted(supporting),
        contradicting_ids=sorted(contradicting),
        relevant_ids=sorted(relevant),
        dimensions=dimensions,
    )


def score_prediction(
    predicted_value: str, actual_value: Optional[str], outcome_known: bool
) -> Dict[str, str]:
    """Score predictive correctness only against a known later outcome.

    A forecast made before the outcome exists is ``pending``, never correct:
    post-outcome explanations must not be scored as predictions, and
    predictions must not be presented as known facts before the outcome.
    """
    if not outcome_known or actual_value is None:
        return {"verdict": "pending", "reason": "outcome_unknown"}
    if _values_equal(predicted_value, actual_value):
        return {"verdict": "correct", "reason": "prediction_matches_outcome"}
    return {"verdict": "incorrect", "reason": "prediction_differs_from_outcome"}


@dataclass
class ProbeItem:
    """One fixed calibration probe: a claim plus its retrieval context."""

    probe_id: str
    claim: Claim
    pool: List[Evidence]
    retrieved_ids: List[str]
    relevant_ids: Set[str]
    expected: Verdict
    cutoff: Optional[datetime] = None
    now: Optional[datetime] = None


def evaluate_probe(item: ProbeItem) -> Dict[str, Any]:
    """Run one probe through the checker on its retrieved evidence subset."""
    wanted = set(item.retrieved_ids)
    retrieved = [entry for entry in item.pool if entry.evidence_id in wanted]
    result = check_claim(item.claim, retrieved, cutoff=item.cutoff, now=item.now)
    retrieved_set = set(item.retrieved_ids)
    relevant_retrieved = sorted(set(item.relevant_ids) & retrieved_set)
    missed_relevant = sorted(set(item.relevant_ids) - retrieved_set)
    return {
        "probe_id": item.probe_id,
        "expected": item.expected.value,
        "actual": result.verdict.value,
        "correct": result.verdict == item.expected,
        "reasons": list(result.reasons),
        "retrieved": len(retrieved_set),
        "relevant": len(item.relevant_ids),
        "relevant_retrieved": len(relevant_retrieved),
        "missed_relevant": missed_relevant,
    }


def evaluate_probe_set(items: Sequence[ProbeItem]) -> Dict[str, Any]:
    """Score a fixed probe set. Every rate carries its raw denominator."""
    per_probe = [evaluate_probe(item) for item in items]
    total = len(per_probe)
    correct = sum(1 for row in per_probe if row["correct"])
    actual_counts = {verdict.value: 0 for verdict in Verdict}
    for row in per_probe:
        actual_counts[row["actual"]] += 1
    stale_errors = sum(
        1 for row in per_probe if (row["expected"] == Verdict.STALE.value) != (row["actual"] == Verdict.STALE.value)
    )
    retrieved_total = sum(row["retrieved"] for row in per_probe)
    relevant_total = sum(row["relevant"] for row in per_probe)
    relevant_retrieved_total = sum(row["relevant_retrieved"] for row in per_probe)
    missed_total = sum(len(row["missed_relevant"]) for row in per_probe)
    expected_abstain = sum(1 for row in per_probe if row["expected"] == Verdict.ABSTAIN.value)
    emitted_abstain = sum(1 for row in per_probe if row["actual"] == Verdict.ABSTAIN.value)
    correct_abstain = sum(
        1
        for row in per_probe
        if row["expected"] == Verdict.ABSTAIN.value and row["actual"] == Verdict.ABSTAIN.value
    )
    return {
        "total": total,
        "correct": correct,
        "accuracy": {"correct": correct, "total": total},
        "actual_counts": actual_counts,
        "unsupported": {"count": actual_counts[Verdict.UNSUPPORTED.value], "total": total},
        "contradicted": {"count": actual_counts[Verdict.CONTRADICTED.value], "total": total},
        "stale": {"count": actual_counts[Verdict.STALE.value], "total": total},
        "stale_errors": {"count": stale_errors, "total": total},
        "retrieval_precision": {
            "relevant_retrieved": relevant_retrieved_total,
            "retrieved": retrieved_total,
        },
        "retrieval_recall": {
            "relevant_retrieved": relevant_retrieved_total,
            "relevant": relevant_total,
        },
        "abstention": {
            "correct": correct_abstain,
            "expected_total": expected_abstain,
            "emitted_total": emitted_abstain,
        },
        "missed_relevant_context": {"count": missed_total, "total_relevant": relevant_total},
        "per_probe": per_probe,
    }


def build_calibration_report(
    controls: Sequence[Dict[str, Any]],
    probe_summary: Dict[str, Any],
    defect_evidence: Dict[str, Any],
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the E0 calibration report payload (JSON-serializable)."""
    controls_list = list(controls)
    passed = sum(1 for row in controls_list if row.get("pass"))
    calibrated = passed == len(controls_list) and probe_summary.get("correct") == probe_summary.get("total")
    return {
        "plan": "EAP-20261004-v0.2",
        "gate": "E0",
        "checker": {
            "module": "src/entorhinal/evals/truth_checker.py",
            "version": CHECKER_VERSION,
            "method": CHECKER_METHOD,
        },
        "defect_reproduction": defect_evidence,
        "negative_controls": controls_list,
        "negative_control_summary": {"passed": passed, "total": len(controls_list)},
        "probe_set": probe_summary,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": "CALIBRATED" if calibrated else "NOT CALIBRATED",
    }

