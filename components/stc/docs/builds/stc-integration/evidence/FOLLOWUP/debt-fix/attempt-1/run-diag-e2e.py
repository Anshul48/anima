"""Debt-fix B2 diagnostic: hand-written pins diff through custody-gates-judiciary-champion-dossier.

DIAGNOSTIC COVERAGE, NOT live acceptance: the diff is hand-written (not
model-emitted), there is no live search/critique/competition, Gate 3 runs
targeted at the new pin file (full Gate 3 is env/commit-blocked per the
debt-fix Gate-3 triage), and mutmut kill-rate is staged-unrun (box math).
What IS real: mirror_source_tree, pristine SST apply_proposal, the exact
substrate gate commands (whole-tree Gates 1+2), a real execute_gates receipt
(real HMAC signature), real receipt_to_score, real render_merged_diff, real
JudiciaryAuditor over the HMAC path, a real merge re-apply, and typed
ChampionResult assembly. 0 live calls; /tmp scratch only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

WS = Path("<workspace-root>")
STC = WS / "stc"
REPLAY = Path("/tmp/debtfix-diag")
PINS = "tests/unit/test_debtfix_diag_pin.py"

# Hand-written pin body (10 content lines + trailing newline; own bytes).
PIN_BODY = "\n".join(
    [
        '"""Diagnostic pins (debt-fix B2 diagnostic; lease-only, hand-written)."""',
        "",
        "from __future__ import annotations",
        "",
        "from stc.integration.dialectic_runner import DialecticRunner, NoChampionResult",
        "",
        "",
        "def test_no_champion_reason_wiring() -> None:",
        '    assert NoChampionResult.model_fields["reason"].annotation is str',
        "    assert callable(DialecticRunner.run_async)",
        "",
    ]
)

PIN_DIFF = (
    "--- /dev/null\n"
    f"+++ b/{PINS}\n"
    "@@ -0,0 +1,10 @@\n"
    + "".join(f"+{line}\n" if line else "+\n" for line in PIN_BODY.split("\n")[:-1])
)


def run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, float, str]:
    start = time.perf_counter()
    res = subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, timeout=timeout,
    )
    dur = round(time.perf_counter() - start, 4)
    return res.returncode, dur, ((res.stdout or "") + "\n" + (res.stderr or "")).strip()


def main() -> None:
    from sst.core.contracts import CandidateProposal, TaskPacket
    from sst.sandbox.custody import CandidateCustodyManager
    from stc.integration.adapters import receipt_to_score
    from stc.integration.dialectic_runner import (
        ChampionResult,
        LossLedger,
        _mutmut_disposition,
        count_mutmut_runs,
        mirror_source_tree,
        render_merged_diff,
    )
    from stc.judiciary.auditor import JudiciaryAuditor
    from stc.schemas.models import FileTarget, TaskBundle
    from stc.substrate.runner import SubstrateRunner

    print(f"pin diff: len={len(PIN_DIFF)} sha={hashlib.sha256(PIN_DIFF.encode()).hexdigest()}")
    print(f"pin body: len={len(PIN_BODY)} sha={hashlib.sha256(PIN_BODY.encode()).hexdigest()}")

    # 1. Lease mirror (real mirror_source_tree, post-fix tree).
    lease = REPLAY / "lease"
    if REPLAY.exists():
        shutil.rmtree(REPLAY)
    mirror_source_tree(STC, lease)
    assert (lease / "pyproject.toml").is_file()
    print("mirror: ok (pyproject present, .git mirrored)")

    # 2. Custody (pristine SST apply_proposal).
    packet = TaskPacket(
        task_id="TASK-DEBTFIX-DIAG",
        goal="debt-fix diagnostic",
        source_repo_root=str(STC),
        base_commit="edf5389873e4d4a2a4752ee0aa2159289398495e",
        snapshot_hash="debtfix-diag",
        allowed_paths=[PINS],
    )
    proposal = CandidateProposal(
        candidate_id="diag-0",
        tree_id="DEBTFIX-DIAG",
        parent_ids=["root_DEBTFIX-DIAG"],
        role="DIVERGE",
        title="debt-fix diagnostic pins",
        rationale="hand-written diagnostic",
        target_paths=[PINS],
        patch_diff=PIN_DIFF,
        model_id="hand",
    )
    # Strict check FIRST on the pristine lease (creation shape vs absent file);
    # after custody creates the file, --check would fail with "already exists".
    pf = lease / ".diag-strict.patch"
    pf.write_text(PIN_DIFF, encoding="utf-8")
    strict = subprocess.run(
        ["git", "apply", "--check", "--whitespace=nowarn", str(pf)],
        cwd=str(lease), capture_output=True, text=True, timeout=30,
    )
    print(f"strict git-apply: rc={strict.returncode} stderr={strict.stderr.strip()[:120]!r}")
    assert strict.returncode == 0, "pins diff must be strict-clean (exact hunk counts)"
    pf.unlink(missing_ok=True)
    mgr = CandidateCustodyManager(base_worktree_dir=REPLAY / "custody")
    res = mgr.apply_proposal(proposal, lease, task=packet)
    target = lease / PINS
    assert res.success, f"custody failed: {res.error_message}"
    assert target.read_bytes() == PIN_BODY.encode(), "applied bytes != pin body"
    print(f"custody: success=True file={len(PIN_BODY)}B sha={hashlib.sha256(PIN_BODY.encode()).hexdigest()[:12]}")

    # 3. Gates: exact substrate commands. Whole-tree 1+2; targeted 3; collect-all.
    py = sys.executable
    gates: dict[str, tuple[int, float]] = {}
    rc, dur, _ = run([py, "-m", "ruff", "check", "."], lease, 120)
    gates["ruff-check"] = (rc, dur)
    rc, dur, _ = run([py, "-m", "ruff", "format", "--check", "."], lease, 120)
    gates["ruff-format"] = (rc, dur)
    rc, dur, _ = run([py, "-m", "mypy", "--strict", "src", "tests"], lease, 600)
    gates["mypy"] = (rc, dur)
    rc, dur, _ = run(
        [py, "-m", "pytest", "-v", "--tb=short", "-m", "not live", PINS], lease, 300,
    )
    gates["pytest-targeted"] = (rc, dur)
    rc, dur, out = run(
        [py, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], lease, 300,
    )
    gates["pytest-collect"] = (rc, dur)
    for name, (rc, dur) in gates.items():
        print(f"gate {name}: rc={rc} dur={dur}s")
        assert rc == 0, f"diagnostic gate {name} failed"
    print("collect tail:", out.strip().splitlines()[-1] if out.strip() else "(empty)")

    # 4. Real receipt via the product path (targeted Gate 3, mutmut off per-node).
    runner = SubstrateRunner()
    receipt = runner.execute_gates(
        worktree_path=lease, task_id="TASK-DEBTFIX-DIAG", epoch_index=1,
        pytest_target=PINS, run_mutmut=False,
    )
    print(
        f"receipt: id={receipt.receipt_id} is_passing={receipt.is_passing} "
        f"ruff={receipt.gate_ruff.exit_code} mypy={receipt.gate_mypy.exit_code} "
        f"pytest={receipt.gate_pytest.exit_code} mutmut={receipt.gate_mutmut.exit_code} "
        f"sig={receipt.sha256_signature[:12]}..."
    )
    assert receipt.is_passing is True
    assert runner.verify_receipt(receipt) is True
    print("receipt HMAC self-verify: True")

    # 5. Score (real mapping).
    score = receipt_to_score(receipt)
    print(f"score: passed={score.passed_hard_gates} reward={score.normalized_reward:.2f} hard={score.hard_gates}")
    assert score.passed_hard_gates is True

    # 6. Judiciary over the REAL HMAC path (runner set) + RT-08 parity assert.
    bundle = TaskBundle(
        task_id="TASK-DEBTFIX-DIAG",
        epoch_index=1,
        spec_id="debtfix-diag",
        goal_statement="debt-fix diagnostic: judiciary path exercise",
        invariants=[],
        target_files=[FileTarget(path=PINS, action="create")],
        membrane_protocols=[],
        negative_inhibitors=[],
    )
    auditor = JudiciaryAuditor(runner=SubstrateRunner(), with_codex=False)
    assert auditor.with_codex is False  # _audit (:946-955) RT-08 parity
    merged = render_merged_diff(proposal)
    verdict = auditor.audit_diff(merged, bundle, receipt)
    print(f"judiciary: status={verdict.status} findings={len(verdict.findings)}")
    for f in verdict.findings:
        print(f"  finding {f.rule_name} {f.severity} {f.filepath}:{f.line_number or '-'}")
    assert verdict.status == "APPROVED", f"diagnostic verdict: {verdict.status}"

    # 7. Champion: single verified candidate, no critique events -> no taint
    # (veto/reselect mechanics stay with the 61/61 unit suite; no competition
    # exists in a single-candidate diagnostic). Merge = fresh mirror + re-apply.
    merge_ws = REPLAY / "merge"
    mirror_source_tree(STC, merge_ws)
    mgr2 = CandidateCustodyManager(base_worktree_dir=REPLAY / "custody-merge")
    mres = mgr2.apply_proposal(proposal, merge_ws, task=packet)
    assert mres.success, f"merge apply failed: {mres.error_message}"
    assert (merge_ws / PINS).read_bytes() == PIN_BODY.encode()
    mrc, _, _ = run(
        ["git", "diff", "--no-index", "--no-color", "/dev/null", PINS],
        merge_ws, 60,
    )
    assert mrc in (0, 1), "git diff --no-index signals differences with rc 1"
    post = runner.execute_gates(
        worktree_path=merge_ws, task_id="TASK-DEBTFIX-DIAG", epoch_index=1,
        pytest_target=PINS, run_mutmut=False,
    )
    assert post.is_passing is True
    re_verdict = auditor.audit_diff(render_merged_diff(proposal), bundle, post)
    assert re_verdict.status == "APPROVED"
    print(f"merge: applied ok; post-merge receipt passing; re-audit {re_verdict.status}")

    # 8. Dossier assembly (diagnostic assembly of real objects, /tmp only).
    dos = REPLAY / "dossier"
    dos.mkdir(parents=True, exist_ok=True)
    (dos / "merged.diff").write_text(PIN_DIFF, encoding="utf-8")
    (dos / "execution_receipt.json").write_text(
        post.model_dump_json(indent=2), encoding="utf-8"
    )
    (dos / "judiciary_verdict.json").write_text(
        re_verdict.model_dump_json(indent=2), encoding="utf-8"
    )
    mutmut_count = count_mutmut_runs(post)
    disposition = (
        "counted-once"
        if mutmut_count == 1
        else _mutmut_disposition(False, post)
    )
    print(f"champion mutmut: count={mutmut_count} disposition={disposition!r}")
    champion = ChampionResult(
        tree_id="DEBTFIX-DIAG",
        run_id=post.receipt_id,
        champion_id="diag-0",
        reselected=False,
        merged_diff=PIN_DIFF,
        post_merge_receipt=post,
        mutmut_count=mutmut_count,
        mutmut_disposition=disposition,
        loss_ledger=LossLedger(tree_id="DEBTFIX-DIAG"),
        judiciary_verdict=re_verdict,
        scores_summary={"diag-0": score.normalized_reward},
        evidence_dir=str(dos),
    )
    (dos / "champion.json").write_text(champion.model_dump_json(indent=2), encoding="utf-8")
    for f in ("merged.diff", "execution_receipt.json", "judiciary_verdict.json", "champion.json"):
        data = (dos / f).read_bytes()
        print(f"dossier {f}: {len(data)}B sha={hashlib.sha256(data).hexdigest()}")
    print("DIAGNOSTIC COMPLETE: custody->gates->judiciary->champion->dossier green")


if __name__ == "__main__":
    main()
