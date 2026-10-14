"""P05 dossier assembly: full 5-artifact + partial NEEDS_REPAIR (RT-10).

Owns the ``stc run --target stc`` dossier layout. An accepted run (champion
+ judiciary APPROVED) yields the full dossier (STATUS=COMPLETE plus diff,
receipt, verdict, review, spend, branch refs, veto log, Q&A log, run ref).
A no-champion run yields the honest partial (STATUS=NEEDS_REPAIR with branch
refs, veto log, scores, reason, and budget — and ZERO success artifacts:
no diff, no receipt, no verdict file). A judiciary-rejected search champion
yields STATUS=NEEDS_REPAIR with reason ``judiciary-<status>:<rules>`` while
KEEPING the records as failure evidence (Fix 1: never presented as
success). Rendering never pads: absent outcomes stay absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stc.integration.dialectic_runner import ChampionResult, NoChampionResult

__all__ = [
    "STATUS_COMPLETE",
    "STATUS_NEEDS_REPAIR",
    "assemble_dossier",
    "final_outcome",
    "new_qa_log",
    "write_qa_log",
]

#: Dossier status markers (mirrored into STATUS + review.md + run_ref.json).
STATUS_COMPLETE: str = "COMPLETE"
STATUS_NEEDS_REPAIR: str = "NEEDS_REPAIR"


def final_outcome(result: ChampionResult | NoChampionResult) -> tuple[bool, str]:
    """Authoritative acceptance: (accepted, reason) — single source (Fix 1).

    A selected search candidate is NOT an accepted result: ChampionResult
    counts only with judiciary status APPROVED. CLI text, JSON, exit
    status, STATUS, branches.json, and run_ref.json all key off this.
    """
    if not isinstance(result, ChampionResult):
        return False, result.reason
    status = result.judiciary_verdict.status
    if status == "APPROVED":
        return True, "champion-accepted"
    rules = sorted({finding.rule_name for finding in result.judiciary_verdict.findings})
    suffix = ",".join(rules) if rules else "no-findings"
    return False, f"judiciary-{status.lower()}:{suffix}"


def new_qa_log(
    *,
    spec_id: str,
    ambiguity_score: float,
    tau: float,
    status: str,
    diffs: list[dict[str, Any]] | None = None,
    selected_choices: list[int] | None = None,
    locked_invariants_path: str | None = None,
    locked_invariants: list[str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Builds the Q&A log payload the CLI records for every stc-target run."""
    return {
        "spec_id": spec_id,
        "ambiguity_score": ambiguity_score,
        "tau": tau,
        "triggered": bool(ambiguity_score >= tau),
        "status": status,
        "diffs": list(diffs) if diffs else [],
        "selected_choices": list(selected_choices) if selected_choices else [],
        "locked_invariants_path": locked_invariants_path,
        "locked_invariants": list(locked_invariants) if locked_invariants else [],
        "note": note,
    }


def write_qa_log(dossier_dir: Path | str, qa: dict[str, Any]) -> Path:
    """Writes qa_log.json (usable pre-run for escalation stops, rewritten post-run)."""
    out_dir = Path(dossier_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "qa_log.json"
    path.write_text(json.dumps(qa, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def _spend_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    gateway_rows = [row for row in rows if row.get("channel") == "gateway"]
    worker_rows = [row for row in rows if row.get("channel") == "worker"]
    return {
        "rows": len(rows),
        "gateway_calls": len(gateway_rows),
        "gateway_ok": sum(1 for row in gateway_rows if row.get("ok") is True),
        "worker_calls": len(worker_rows),
        "worker_ok": sum(1 for row in worker_rows if row.get("ok") is True),
        "usd_metered": 0.0,
        "tokens": None,
        "tokens_note": (
            "unobservable from CLI harnesses (P03 precedent); spend tracked in ledger rows"
        ),
    }


def assemble_dossier(
    result: ChampionResult | NoChampionResult,
    dossier_dir: Path | str,
    *,
    spec_id: str,
    task_id: str,
    contract_revision: str,
    base_identity: str,
    qa: dict[str, Any],
    spend_rows: list[dict[str, Any]],
    limitations: list[str],
) -> dict[str, str]:
    """Assembles the dossier for a finished run; returns artifact name → filename.

    Accepted (champion + judiciary APPROVED) → STATUS_COMPLETE with all 5
    success artifacts. No-champion → STATUS_NEEDS_REPAIR with branch refs +
    veto log + scores + reason + budget and zero success artifacts. A
    judiciary-rejected search champion → STATUS_NEEDS_REPAIR with the
    rejection reason, but the records (diff, receipt, verdict) are KEPT as
    evidence of the failure — never presented as success. Raises on I/O
    failure (fail-closed: a run without its dossier is not reported).
    """
    out_dir = Path(dossier_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    champion = isinstance(result, ChampionResult)
    accepted, reason = final_outcome(result)
    status = STATUS_COMPLETE if accepted else STATUS_NEEDS_REPAIR

    (out_dir / "STATUS").write_text(status + "\n", encoding="utf-8")
    write_qa_log(out_dir, qa)

    veto_payload = [record.model_dump(mode="json") for record in result.veto_log]
    (out_dir / "veto_log.json").write_text(
        json.dumps(veto_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )

    totals = _spend_totals(spend_rows)
    (out_dir / "spend.json").write_text(
        json.dumps({"totals": totals, "rows": spend_rows}, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    artifacts: dict[str, str] = {
        "STATUS": "STATUS",
        "qa_log": "qa_log.json",
        "veto_log": "veto_log.json",
        "spend": "spend.json",
    }
    if champion:
        assert isinstance(result, ChampionResult)
        (out_dir / "merged.diff").write_text(result.merged_diff, encoding="utf-8")
        (out_dir / "execution_receipt.json").write_text(
            result.post_merge_receipt.model_dump_json(indent=2), encoding="utf-8"
        )
        verdict_payload = {
            "verdict": result.judiciary_verdict.model_dump(mode="json"),
            "first_verdict": (
                result.first_verdict.model_dump(mode="json")
                if result.first_verdict is not None
                else None
            ),
            "retried": result.first_verdict is not None,
            "retry_receipts": len(result.retry_receipts),
            "mutmut_count": result.mutmut_count,
            "retry_mutmut_counts": list(result.retry_mutmut_counts),
            "mutmut_disposition": result.mutmut_disposition,
        }
        (out_dir / "judiciary_verdict.json").write_text(
            json.dumps(verdict_payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        branches_payload: dict[str, Any] = {
            "tree_id": result.tree_id,
            "run_id": result.run_id,
            "outcome": "champion" if accepted else "no-champion",
            "champion_id": result.champion_id,
            "reselected": result.reselected,
            "scores_summary": dict(result.scores_summary),
            "synthesis_receipts": [
                receipt.model_dump(mode="json") for receipt in result.synthesis_receipts
            ],
            "loss_ledger": result.loss_ledger.model_dump(mode="json"),
        }
        if not accepted:
            branches_payload["reason"] = reason
        artifacts.update(
            {
                "merged_diff": "merged.diff",
                "execution_receipt": "execution_receipt.json",
                "judiciary_verdict": "judiciary_verdict.json",
            }
        )
    else:
        assert isinstance(result, NoChampionResult)
        branches_payload = {
            "tree_id": result.tree_id,
            "run_id": result.run_id,
            "outcome": "no-champion",
            "reason": result.reason,
            "branch_refs": list(result.branch_refs),
            "scores_summary": dict(result.scores_summary),
            "budget_state": dict(result.budget_state),
        }
    (out_dir / "branches.json").write_text(
        json.dumps(branches_payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    artifacts["branches"] = "branches.json"

    (out_dir / "run_ref.json").write_text(
        json.dumps(
            {
                "run_id": result.run_id,
                "tree_id": result.tree_id,
                "status": status,
                "evidence_dir": result.evidence_dir,
                "result_file": str(Path(result.evidence_dir) / "result.json"),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    artifacts["run_ref"] = "run_ref.json"

    review_lines = _review_lines(
        status=status,
        result=result,
        spec_id=spec_id,
        task_id=task_id,
        contract_revision=contract_revision,
        base_identity=base_identity,
        totals=totals,
        limitations=limitations,
    )
    (out_dir / "review.md").write_text("\n".join(review_lines) + "\n", encoding="utf-8")
    artifacts["review"] = "review.md"
    return artifacts


def _review_lines(
    *,
    status: str,
    result: ChampionResult | NoChampionResult,
    spec_id: str,
    task_id: str,
    contract_revision: str,
    base_identity: str,
    totals: dict[str, Any],
    limitations: list[str],
) -> list[str]:
    champion = isinstance(result, ChampionResult)
    accepted, reason = final_outcome(result)
    lines = [
        f"# Dossier review — {task_id} ({status})",
        "",
        f"Spec: {spec_id} | Contract: {contract_revision}",
        f"Base: {base_identity}",
        f"Run: {result.run_id} | Tree: {result.tree_id}",
        "",
        "## Outcome",
        "",
    ]
    if champion and accepted:
        assert isinstance(result, ChampionResult)
        lines.extend(
            [
                f"Champion `{result.champion_id}` (reselected={result.reselected}).",
                f"Judiciary: {result.judiciary_verdict.status}; "
                f"mutmut: count={result.mutmut_count} "
                f"disposition={result.mutmut_disposition}.",
                "",
                "## Artifacts",
                "",
                "- merged.diff (champion unified diff)",
                "- execution_receipt.json (post-merge substrate receipt)",
                "- judiciary_verdict.json (final verdict + retry record)",
                "- spend.json (ledger rows + totals)",
                "- branches.json (scores, synthesis receipts, loss ledger)",
                "- veto_log.json, qa_log.json, run_ref.json",
            ]
        )
    elif champion:
        assert isinstance(result, ChampionResult)
        lines.extend(
            [
                f"No champion ({reason}) — the search selected "
                f"`{result.champion_id}` but the judiciary did not approve it.",
                "UNSUCCESSFUL: do not merge. Records below are failure evidence.",
                "",
                "## Artifacts",
                "",
                "- merged.diff (REJECTED candidate diff — evidence only)",
                "- execution_receipt.json (post-merge substrate receipt)",
                "- judiciary_verdict.json (REJECTED verdict + findings)",
                "- spend.json (ledger rows + totals)",
                "- branches.json (outcome no-champion + reason)",
                "- veto_log.json, qa_log.json, run_ref.json",
            ]
        )
    else:
        assert isinstance(result, NoChampionResult)
        lines.extend(
            [
                "No champion (honest partial — zero success artifacts).",
                f"Reason: `{result.reason}`.",
                f"Branches observed: {len(result.branch_refs)}; "
                f"veto records: {len(result.veto_log)}.",
                "",
                "## Artifacts",
                "",
                "- branches.json (branch refs, scores, budget state, reason)",
                "- veto_log.json (veto records, possibly empty)",
                "- spend.json (ledger rows + totals)",
                "- qa_log.json, run_ref.json",
                "- ABSENT by design: merged.diff, execution_receipt.json,",
                "  judiciary_verdict.json (no champion => no success artifacts).",
            ]
        )
    lines.extend(
        [
            "",
            "## Spend",
            "",
            f"Gateway calls: {totals['gateway_calls']} "
            f"({totals['gateway_ok']} ok); "
            f"worker calls: {totals['worker_calls']} "
            f"({totals['worker_ok']} ok); "
            "USD metered: 0.0 (CLI session); tokens: unobservable.",
            "",
            "## Limitations",
            "",
        ]
    )
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    else:
        lines.append("- None recorded.")
    lines.extend(
        [
            "",
            "No claim is made that this run validates anything beyond the",
            "tool itself (packet §Scope: M1-validates-anything claims forbidden).",
        ]
    )
    return lines
