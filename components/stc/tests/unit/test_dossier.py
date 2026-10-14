"""Unit tests for authoritative final outcome (Fix 1)."""

import json
from pathlib import Path
from typing import Any

from stc.integration.dialectic_runner import ChampionResult, LossLedger, NoChampionResult
from stc.integration.dossier import assemble_dossier, final_outcome
from stc.schemas.models import AuditFinding, GateReport, JudiciaryVerdict
from stc.substrate.receipt import create_receipt


def _gate(exit_code: int = 0) -> GateReport:
    return GateReport(
        gate_name="gate",
        exit_code=exit_code,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )


def _receipt() -> Any:
    return create_receipt(
        task_id="T",
        commit_hash="c0ffee1234",
        gate_ruff=_gate(),
        gate_mypy=_gate(),
        gate_pytest=_gate(),
        gate_mutmut=_gate(),
    )


def _verdict(status: str, rules: list[str] | None = None) -> JudiciaryVerdict:
    return JudiciaryVerdict(
        task_id="T",
        status=status,
        findings=[
            AuditFinding(
                rule_name=rule,
                severity="CRITICAL",
                filepath="a.py",
                snippet="x",
                rationale="r",
            )
            for rule in (rules or [])
        ],
        summary_rationale="s",
    )


def _champion(status: str, rules: list[str] | None = None) -> ChampionResult:
    return ChampionResult(
        tree_id="tree-1",
        run_id="run-1",
        champion_id="cand-1",
        reselected=False,
        merged_diff="diff --git a/a b/a\n",
        post_merge_receipt=_receipt(),
        mutmut_count=1,
        mutmut_disposition="measured",
        loss_ledger=LossLedger(tree_id="tree-1"),
        judiciary_verdict=_verdict(status, rules),
        evidence_dir="/tmp/ev",
    )


def _no_champion(reason: str = "no-verified-candidate") -> NoChampionResult:
    return NoChampionResult(
        tree_id="tree-1",
        run_id="run-1",
        branch_refs=["b1"],
        scores_summary={},
        reason=reason,
        evidence_dir="/tmp/ev",
    )


def _assemble(result: Any, tmp_path: Path) -> Path:
    out = tmp_path / "dossier"
    assemble_dossier(
        result,
        out,
        spec_id="spec-1",
        task_id="T",
        contract_revision="INT-test",
        base_identity="abc",
        qa={"status": "ok"},
        spend_rows=[],
        limitations=[],
    )
    return out


def test_final_outcome_matrix() -> None:
    assert final_outcome(_champion("APPROVED")) == (True, "champion-accepted")
    assert final_outcome(_champion("REJECTED", ["B", "A"])) == (
        False,
        "judiciary-rejected:A,B",
    )
    assert final_outcome(_champion("REJECTED")) == (False, "judiciary-rejected:no-findings")
    ok, reason = final_outcome(_champion("QUARANTINED", ["X"]))
    assert ok is False and reason == "judiciary-quarantined:X"
    assert final_outcome(_no_champion("r1")) == (False, "r1")


def test_approved_champion_dossier_unchanged(tmp_path: Path) -> None:
    out = _assemble(_champion("APPROVED"), tmp_path)
    assert (out / "STATUS").read_text(encoding="utf-8").strip() == "COMPLETE"
    branches = json.loads((out / "branches.json").read_text(encoding="utf-8"))
    assert branches["outcome"] == "champion"
    assert branches["champion_id"] == "cand-1"
    assert "reason" not in branches
    assert (out / "merged.diff").is_file()
    assert "UNSUCCESSFUL" not in (out / "review.md").read_text(encoding="utf-8")


def test_rejected_champion_is_unsuccessful_with_evidence(tmp_path: Path) -> None:
    """Fix 1: REJECTED search champion is explicit UNSUCCESSFUL, records kept."""
    out = _assemble(_champion("REJECTED", ["ZERO_MOCK_VIOLATION"]), tmp_path)
    assert (out / "STATUS").read_text(encoding="utf-8").strip() == "NEEDS_REPAIR"
    branches = json.loads((out / "branches.json").read_text(encoding="utf-8"))
    assert branches["outcome"] == "no-champion"
    assert branches["reason"] == "judiciary-rejected:ZERO_MOCK_VIOLATION"
    assert branches["champion_id"] == "cand-1"
    run_ref = json.loads((out / "run_ref.json").read_text(encoding="utf-8"))
    assert run_ref["status"] == "NEEDS_REPAIR"
    # Evidence preserved, never presented as success.
    assert (out / "merged.diff").is_file()
    assert (out / "execution_receipt.json").is_file()
    assert (out / "judiciary_verdict.json").is_file()
    review = (out / "review.md").read_text(encoding="utf-8")
    assert "UNSUCCESSFUL: do not merge" in review
    assert "judiciary-rejected:ZERO_MOCK_VIOLATION" in review


def test_no_champion_shape_preserved(tmp_path: Path) -> None:
    """The honest-partial contract is untouched (zero success artifacts)."""
    out = _assemble(_no_champion(), tmp_path)
    assert (out / "STATUS").read_text(encoding="utf-8").strip() == "NEEDS_REPAIR"
    branches = json.loads((out / "branches.json").read_text(encoding="utf-8"))
    assert branches["outcome"] == "no-champion"
    assert branches["reason"] == "no-verified-candidate"
    assert "champion_id" not in branches
    assert not (out / "merged.diff").exists()
    assert not (out / "execution_receipt.json").exists()
    assert not (out / "judiciary_verdict.json").exists()
