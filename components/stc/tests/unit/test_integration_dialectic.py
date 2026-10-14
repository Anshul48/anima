"""Unit tests for the P04 dialectic runner (wrapper + veto + merge + audit).

Deterministic everywhere: substrate and gateway are scripted fakes (no
ruff/mypy/pytest binaries, no git, no network). Real-gate and live coverage
lives in tests/integration/test_dialectic_fixture.py.
"""

from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sst.core.contracts import CandidateProposal, TaskPacket
from sst.core.events import EventKind, SSTEvent
from sst.gateway.contracts import GatewayRequest, GatewayResponse, ProviderGatewayError
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager
from sst.search.policy import SearchPolicy

from stc.integration.adapters import AdapterContext, Budgets
from stc.integration.dialectic_runner import (
    DEFAULT_LIVE_CRITIQUE_RATIONALE,
    DEFAULT_LIVE_CRITIQUE_SCORE,
    FALLBACK_CRITIQUE_RATIONALE,
    ChampionResult,
    DialecticError,
    DialecticRunner,
    LossLedgerEntry,
    NoChampionResult,
    STCCustodyWrapper,
    SynthesisReceipt,
    count_mutmut_runs,
    lease_id_for,
    mirror_source_tree,
    render_merged_diff,
    sanitize_lease_segment,
    scrape_tainted_scores,
)
from stc.integration.harness_worker import CritiqueProvenance
from stc.judiciary.auditor import JudiciaryAuditor
from stc.schemas.models import (
    ExecutionReceipt,
    FileTarget,
    GateReport,
    JudiciaryVerdict,
    TaskBundle,
)

GOOD_CODE = 'def add(a: int, b: int) -> int:\n    """Good branch."""\n    return a + b\n'
LOW_CODE = 'def add(a: int, b: int) -> int:\n    """Low branch."""\n    return a + b\n'
GARBAGE_CODE = 'def add(a: int, b: int) -> int:\n    """Garbage branch."""\n    return a + b\n'
SYNTH_CODE = 'def add(a: int, b: int) -> int:\n    """Synth blend."""\n    return a + b\n'
FAIL_CODE = "def broken(:\n    this is not python\n"


def _gate(name: str, exit_code: int = 0, snippet: str = "ok") -> GateReport:
    return GateReport(
        gate_name=name,
        exit_code=exit_code,
        duration_seconds=0.5,
        violations_count=0 if exit_code == 0 else 1,
        raw_output_snippet=snippet,
    )


def _disabled_mutmut() -> GateReport:
    return GateReport(
        gate_name="mutmut",
        exit_code=0,
        duration_seconds=0.0,
        violations_count=0,
        raw_output_snippet="Mutmut Gate disabled by runner configuration.",
    )


def _receipt(
    task_id: str = "T",
    *,
    passing: bool = True,
    mutmut: GateReport | None = None,
) -> ExecutionReceipt:
    fail = _gate("pytest", exit_code=1, snippet="1 failed") if not passing else None
    return ExecutionReceipt(
        receipt_id="rc-test",
        task_id=task_id,
        epoch_index=1,
        commit_hash="abc",
        timestamp_utc="2026-09-13T00:00:00Z",
        python_version="3.11",
        os_platform="linux",
        gate_ruff=_gate("ruff"),
        gate_mypy=_gate("mypy"),
        gate_pytest=fail if fail is not None else _gate("pytest"),
        gate_mutmut=mutmut if mutmut is not None else _disabled_mutmut(),
        sha256_signature="test-signature",
    )


class FakeSubstrate:
    """Scripted substrate: pass/fail by lease content marker, calls recorded."""

    def __init__(
        self,
        *,
        fail_marker: str = "FAIL-ME",
        post_receipt: ExecutionReceipt | None = None,
        crash: Exception | None = None,
        verify_ok: bool = True,
        delay: float = 0.0,
    ) -> None:
        self.fail_marker = fail_marker
        self.post_receipt = post_receipt
        self.crash = crash
        self.verify_ok = verify_ok
        self.delay = delay
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def execute_gates(
        self,
        worktree_path: Path,
        task_id: str,
        epoch_index: int = 1,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        pytest_target: str | None = None,
        **kwargs: Any,
    ) -> ExecutionReceipt:
        with self._lock:
            self.calls.append(
                {
                    "worktree": str(worktree_path),
                    "task_id": task_id,
                    "epoch_index": epoch_index,
                    "pytest_target": pytest_target,
                    **kwargs,
                }
            )
        if self.crash is not None:
            raise self.crash
        if self.delay > 0:
            import time

            time.sleep(self.delay)
        if worktree_path.name == "merged" and self.post_receipt is not None:
            return self.post_receipt
        if self.fail_marker:
            try:
                text = "".join(
                    p.read_text(encoding="utf-8", errors="replace")
                    for p in worktree_path.rglob("*.py")
                )
            except OSError:
                text = ""
            if self.fail_marker in text:
                return _receipt(task_id, passing=False)
        return _receipt(task_id, passing=True)

    def verify_receipt(self, receipt: ExecutionReceipt) -> bool:
        _ = receipt
        return self.verify_ok


class ScriptGateway(ModelGateway):
    """Gateway serving scripted role responses (deterministic search)."""

    def __init__(self, handler: Any) -> None:
        super().__init__(profiles={}, routes={})
        self.profiles["test"] = "test"  # type: ignore[assignment]
        self._handler = handler
        self.calls: list[GatewayRequest] = []

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        self.calls.append(request)
        content = self._handler(request)
        return GatewayResponse(content=content, model="script", profile="test")


def _packet(
    task_id: str = "T1",
    source_root: str = "/tmp/src",
    *,
    forbidden: list[str] | None = None,
    allowed: list[str] | None = None,
) -> TaskPacket:
    return TaskPacket(
        task_id=task_id,
        goal="test goal",
        source_repo_root=source_root,
        base_commit="abc",
        snapshot_hash="snap",
        allowed_paths=allowed if allowed is not None else ["mod.py"],
        forbidden_paths=forbidden if forbidden is not None else [],
        acceptance_commands=["true"],
        evidence_references={"stc.epoch_index": "1"},
    )


def _proposal(
    candidate_id: str = "cand-1",
    code: str = GOOD_CODE,
    *,
    targets: list[str] | None = None,
    file_ops: list[dict[str, Any]] | None = None,
) -> CandidateProposal:
    return CandidateProposal(
        candidate_id=candidate_id,
        tree_id="tree-1",
        role="DIVERGE",
        title=f"Proposal {candidate_id}",
        rationale="test",
        target_paths=targets if targets is not None else ["mod.py"],
        patch_diff=code,
        file_operations=file_ops if file_ops is not None else [],
    )


def _source(tmp_path: Path, name: str = "src") -> Path:
    src = tmp_path / name
    src.mkdir()
    (src / "mod.py").write_text(GOOD_CODE, encoding="utf-8")
    (src / "test_mod.py").write_text(
        "from mod import add\n\n\ndef test_add() -> None:\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    return src


def _git_source(tmp_path: Path, name: str = "src") -> Path:
    """Git-backed source tree (P01 snapshot_hash needs rev-parse HEAD)."""
    if shutil.which("git") is None:
        pytest.skip("git required for P01 candidate identity")
    src = _source(tmp_path, name)
    subprocess.run(["git", "-C", str(src), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(src),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "init",
        ],
        check=True,
    )
    return src


def _wrapper(tmp_path: Path, substrate: Any, leases: str = "leases") -> STCCustodyWrapper:
    return STCCustodyWrapper(
        CandidateCustodyManager(base_worktree_dir=tmp_path / "custody"),
        substrate,
        leases_root=tmp_path / leases,
    )


def _ctx(source_root: str, time_budget_seconds: int = 60) -> AdapterContext:
    return AdapterContext(
        epoch_index=1,
        spec_id="spec-1",
        budgets=Budgets(time_budget_seconds=time_budget_seconds),
        acceptance_commands=("true",),
        source_repo_root=source_root,
        base_commit="abc",
        adapter_version="p04-test",
    )


def _bundle(task_id: str = "T1") -> TaskBundle:
    return TaskBundle(
        task_id=task_id,
        epoch_index=1,
        spec_id="spec-1",
        goal_statement="make add work",
        invariants=["keep add correct"],
        target_files=[FileTarget(path="mod.py", action="modify")],
        membrane_protocols=["proto-a"],
        negative_inhibitors=[],
    )


def _score_event(node_id: str, score: float, rationale: str, verdict: str = "APPROVE") -> SSTEvent:
    return SSTEvent(
        event_id=f"evt-{node_id}",
        tree_id="tree-1",
        node_id=node_id,
        kind=EventKind.SCORE_RECORDED,
        idempotency_key=f"score-{node_id}",
        payload={"value_score": score, "verdict": verdict, "critique": rationale},
    )


# --- Wrapper: composition, signature, leases ---


def test_wrapper_is_composition_not_subclass(tmp_path: Path) -> None:
    wrapper = _wrapper(tmp_path, FakeSubstrate())
    assert not isinstance(wrapper, CandidateCustodyManager)
    assert isinstance(wrapper.custody, CandidateCustodyManager)
    assert callable(wrapper.verify_candidate_proposal)


def test_wrapper_signature_matches_parent() -> None:
    parent = inspect.signature(CandidateCustodyManager.verify_candidate_proposal)
    child = inspect.signature(STCCustodyWrapper.verify_candidate_proposal)
    assert list(child.parameters) == list(parent.parameters)
    for name in ("acceptance_command", "timeout"):
        assert child.parameters[name].default == parent.parameters[name].default


def test_lease_id_format_and_sanitization() -> None:
    assert lease_id_for("T1", "cand-9") == "T1__cand-9"
    assert ".." not in lease_id_for("a/b", "..\\c")
    assert "/" not in lease_id_for("a/b", "c/d")
    assert sanitize_lease_segment("") == "_"


def test_wrapper_pass_maps_receipt_and_releases(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    result = wrapper.verify_candidate_proposal(_packet(source_root=str(src)), _proposal(), src)
    assert result.passed is True
    assert result.exit_code == 0
    assert "reward=1.00" in result.stdout
    assert wrapper.receipts["cand-1"].task_id == "T1"
    assert wrapper.scores["cand-1"].normalized_reward == 1.0
    assert list((tmp_path / "leases").iterdir()) == [tmp_path / "leases" / "_quarantine"]


def test_wrapper_gate_failure_prunes_with_detail(tmp_path: Path) -> None:
    substrate = FakeSubstrate(fail_marker="FAIL-ME")
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    bad = _proposal(code="FAIL-ME\n" + GOOD_CODE)
    result = wrapper.verify_candidate_proposal(_packet(source_root=str(src)), bad, src)
    assert result.passed is False
    assert result.exit_code == 1
    assert "stc_pytest" in (result.failure_reason or "")
    assert "reward=0.50" in result.stdout
    assert list((tmp_path / "leases").iterdir()) == [tmp_path / "leases" / "_quarantine"]


def test_wrapper_per_node_mutmut_forced_off(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    wrapper.verify_candidate_proposal(_packet(source_root=str(src)), _proposal(), src)
    assert substrate.calls[0]["run_mutmut"] is False


def test_test_command_declared_ignored(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    packet = _packet(source_root=str(src))
    first = wrapper.verify_candidate_proposal(
        packet, _proposal("c1"), src, acceptance_command="false"
    )
    second = wrapper.verify_candidate_proposal(packet, _proposal("c2"), src)
    assert (first.passed, first.exit_code) == (second.passed, second.exit_code)
    assert first.passed is True


def test_denylist_exact_and_nested_denied(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    packet = _packet(source_root=str(src), forbidden=["secrets"])
    for target in ("secrets", "secrets/token.txt", "secrets\\win.txt"):
        result = wrapper.verify_candidate_proposal(packet, _proposal(targets=[target]), src)
        assert result.passed is False
        assert "Scope Policy Violation" in result.stderr
        assert "no lease created" in result.stderr
    assert list((tmp_path / "leases").iterdir()) == [tmp_path / "leases" / "_quarantine"]
    assert substrate.calls == []


def test_denylist_file_operations_path_checked(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    packet = _packet(source_root=str(src), forbidden=["secrets"])
    proposal = _proposal(
        targets=["mod.py"],
        file_ops=[{"op": "create", "path": "secrets/x.txt", "content": "x"}],
    )
    result = wrapper.verify_candidate_proposal(packet, proposal, src)
    assert result.passed is False
    assert "Scope Policy Violation" in result.stderr
    assert substrate.calls == []


def test_denylist_sibling_prefix_allowed(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    (src / "secrets2").mkdir()
    packet = _packet(source_root=str(src), forbidden=["secrets"], allowed=["secrets2/y.py"])
    result = wrapper.verify_candidate_proposal(
        packet, _proposal(targets=["secrets2/y.py"], code=GOOD_CODE), src
    )
    assert result.passed is True


def test_wrapper_patch_apply_failure_releases(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    packet = _packet(source_root=str(src), allowed=["mod.py"])
    result = wrapper.verify_candidate_proposal(
        packet, _proposal(targets=["elsewhere.py"], code=GOOD_CODE), src
    )
    assert result.passed is False
    assert "Scope Policy Violation" in result.stderr
    assert substrate.calls == []
    assert list((tmp_path / "leases").iterdir()) == [tmp_path / "leases" / "_quarantine"]


def test_wrapper_quarantines_on_substrate_crash(tmp_path: Path) -> None:
    substrate = FakeSubstrate(crash=RuntimeError("boom-8842"))
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    result = wrapper.verify_candidate_proposal(_packet(source_root=str(src)), _proposal(), src)
    assert result.passed is False
    assert "boom-8842" in result.stderr
    quarantined = list((tmp_path / "leases" / "_quarantine").iterdir())
    assert len(quarantined) == 1
    reason = (quarantined[0] / "quarantine_reason.txt").read_text(encoding="utf-8")
    assert "RuntimeError: boom-8842" in reason
    assert (quarantined[0] / "mod.py").is_file()


def test_wrapper_missing_source_fails_closed(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    missing = tmp_path / "no-such-src"
    result = wrapper.verify_candidate_proposal(
        _packet(source_root=str(missing)), _proposal(), missing
    )
    assert result.passed is False
    assert "source tree not found" in result.stderr
    assert list((tmp_path / "leases").iterdir()) == [tmp_path / "leases" / "_quarantine"]


def test_concurrent_parallel_leases(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    packet = _packet(source_root=str(src))

    def verify(index: int) -> bool:
        result = wrapper.verify_candidate_proposal(packet, _proposal(f"cand-n{index}"), src)
        return result.passed

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(verify, range(8)))
    assert outcomes == [True] * 8
    assert len(wrapper.receipts) == 8
    assert len(substrate.calls) == 8
    assert list((tmp_path / "leases").iterdir()) == [tmp_path / "leases" / "_quarantine"]
    assert list((tmp_path / "leases" / "_quarantine").iterdir()) == []


# --- Mutmut counting rule (RT-05) ---


def _mutmut_receipt(duration: float, snippet: str, exit_code: int = 0) -> ExecutionReceipt:
    return _receipt(
        mutmut=GateReport(
            gate_name="mutmut",
            exit_code=exit_code,
            duration_seconds=duration,
            violations_count=0,
            raw_output_snippet=snippet,
        )
    )


def test_count_mutmut_real_report() -> None:
    receipt = _mutmut_receipt(
        1.25, "Killed 18 of 20 mutants\n[mutmut kill rate: 90.00% (threshold: 85.00%)]"
    )
    assert count_mutmut_runs(receipt) == 1


@pytest.mark.parametrize(
    ("duration", "snippet", "exit_code"),
    [
        (0.0, "Mutmut Gate deferred per 01_INVARIANTS.md §3.3\nKill rate status: NOT-MEASURED", 0),
        (0.0, "DEFERRED: per-node placeholder, champion-only policy", 0),
        (0.0, "Mutmut Gate disabled by runner configuration.", 0),
        (0.0, "Mutmut Gate skipped under active mutation test runner.", 0),
        (0.7, "No module named mutmut", 1),
        (0.4, "/usr/bin/python: No module named 'mutmut'", 1),
        (120.0, "Gate timed out", 124),
        (30.0, "Gate timed out in WSL", 124),
        (0.0, "Killed 18 of 20 mutants", 0),
        (1.1, "   ", 0),
        (2.0, "", 0),
    ],
)
def test_count_mutmut_non_reports(duration: float, snippet: str, exit_code: int) -> None:
    assert count_mutmut_runs(_mutmut_receipt(duration, snippet, exit_code)) == 0


# --- Veto scrape (RT-03) ---


def test_scrape_exact_fallback_tainted() -> None:
    events = [_score_event("n1", 0.95, FALLBACK_CRITIQUE_RATIONALE)]
    tainted = scrape_tainted_scores(events)
    assert set(tainted) == {"n1"}
    assert tainted["n1"].rule == "exact-fallback-rationale"
    assert tainted["n1"].value_score == 0.95


def test_scrape_explicit_critique_failed_tainted() -> None:
    """New-SST explicit CRITIQUE_FAILED verdict taints whatever the score."""
    events = [_score_event("n9", 0.5, "critique call failed: no route", verdict="CRITIQUE_FAILED")]
    tainted = scrape_tainted_scores(events)
    assert set(tainted) == {"n9"}
    assert tainted["n9"].rule == "explicit-critique-failed"
    assert tainted["n9"].value_score == 0.5


def test_scrape_default_085_tainted() -> None:
    events = [_score_event("n2", DEFAULT_LIVE_CRITIQUE_SCORE, DEFAULT_LIVE_CRITIQUE_RATIONALE)]
    tainted = scrape_tainted_scores(events)
    assert set(tainted) == {"n2"}
    assert tainted["n2"].rule == "default-score-0.85"


def test_scrape_genuine_scores_clean() -> None:
    events = [
        _score_event("g85", 0.85, "solid types, one naming nit"),
        _score_event("g95", 0.95, "excellent: full invariant coverage"),
        _score_event("g90", 0.9, DEFAULT_LIVE_CRITIQUE_RATIONALE),
        _score_event("g70", 0.7, "meets the goal, minimal margin"),
    ]
    assert scrape_tainted_scores(events) == {}


def _prov(seq: int, valid: bool, ledger_row: int, detail: str = "ok") -> CritiqueProvenance:
    return CritiqueProvenance(seq=seq, valid=valid, detail=detail, ledger_row=ledger_row)


def test_scrape_unprovenanced_critique_tainted() -> None:
    """Invalid provenance taints regardless of score value (Fix 2)."""
    events = [_score_event("n1", 0.97, "thorough genuine-looking rationale")]
    prov = [_prov(0, False, 1, detail="harness failure: exit 1")]
    tainted = scrape_tainted_scores(events, prov)
    assert set(tainted) == {"n1"}
    assert tainted["n1"].rule == "critique-unprovenanced"
    assert "ledger row 1" in tainted["n1"].rationale
    assert "harness failure" in tainted["n1"].rationale


def test_scrape_provenanced_critique_clean() -> None:
    """Valid provenance leaves genuine scores clean (Fix 2)."""
    events = [
        _score_event("g1", 0.95, "full requirement coverage"),
        _score_event("g2", 0.6, "partial: missing edge case"),
    ]
    prov = [_prov(0, True, 0), _prov(1, True, 2)]
    assert scrape_tainted_scores(events, prov) == {}


def test_scrape_pairs_in_order_and_skips_unpaired() -> None:
    """k-th score pairs with k-th witness; unpaired left to Rules 1-2."""
    events = [
        _score_event("a", 0.9, "fine"),
        _score_event("b", 0.9, "fine"),
        _score_event("c", 0.9, "fine"),
    ]
    prov = [_prov(0, True, 0), _prov(1, False, 2, detail="unparseable critique content")]
    tainted = scrape_tainted_scores(events, prov)
    assert set(tainted) == {"b"}
    assert tainted["b"].rule == "critique-unprovenanced"


def test_scrape_verifier_fail_consumes_no_pairing_slot() -> None:
    """Deterministic verifier-fail PRUNEs pair with no witness (Fix 2).

    The controller emits these scores without a gateway critique call, so
    they must not shift later events off their own witnesses: here "g"
    pairs with the valid witness and "b" with the invalid one.
    """
    events = [
        _score_event("v", 0.0, "Deterministic verifier failed: exit 2", verdict="PRUNE"),
        _score_event("g", 0.95, "full requirement coverage"),
        _score_event("b", 0.97, "thorough genuine-looking rationale"),
    ]
    prov = [_prov(0, True, 0), _prov(1, False, 2, detail="harness failure: exit 1")]
    tainted = scrape_tainted_scores(events, prov)
    assert set(tainted) == {"b"}
    assert tainted["b"].rule == "critique-unprovenanced"


def test_scrape_string_rules_keep_precedence() -> None:
    """First matching rule wins: exact-fallback beats provenance."""
    events = [_score_event("n1", 0.95, FALLBACK_CRITIQUE_RATIONALE)]
    prov = [_prov(0, False, 0, detail="harness failure: exit 1")]
    tainted = scrape_tainted_scores(events, prov)
    assert tainted["n1"].rule == "exact-fallback-rationale"


def test_scrape_ignores_non_score_events() -> None:
    other = SSTEvent(
        event_id="evt-x",
        tree_id="tree-1",
        node_id="n9",
        kind=EventKind.VERIFIER_FINISHED,
        idempotency_key="ver-x",
        payload={"passed": True},
    )
    assert scrape_tainted_scores([other]) == {}
    assert scrape_tainted_scores([_score_event("n1", 0.9, "fine")]) == {}


# --- Schemas ---


def test_synthesis_receipt_schema() -> None:
    receipt = SynthesisReceipt(
        synthesis_id="synth-c1",
        tree_id="tree-1",
        parent_ids=["a", "b"],
        parent_scores={"a": 0.9, "b": 0.95},
        synth_candidate_id="c1",
        synth_score=0.88,
        verification_passed=True,
        verification_exit_code=0,
        verification_duration_s=1.5,
    )
    assert receipt.parent_scores == {"a": 0.9, "b": 0.95}
    with pytest.raises(ValidationError):
        receipt.synth_score = 0.1


def test_loss_ledger_entry_schema() -> None:
    entry = LossLedgerEntry(
        candidate_id="low-1",
        tree_id="tree-1",
        normalized_reward=0.6,
        critic_verdict="APPROVE",
        reason="below-synthesis-threshold",
    )
    assert entry.reason == "below-synthesis-threshold"


def test_no_champion_schema() -> None:
    result = NoChampionResult(
        tree_id="t",
        run_id="r",
        branch_refs=["a"],
        scores_summary={"a": 0.5},
        veto_log=[],
        budget_state={"iterations_completed": 1.0},
        reason="no-verified-candidate",
        evidence_dir="/tmp/x",
    )
    assert result.reason == "no-verified-candidate"


# --- Merged-diff rendering ---


def test_render_passthrough_unified_diff() -> None:
    diff = "--- a/mod.py\n+++ b/mod.py\n@@ -1 +1 @@\n-old\n+new\n"
    proposal = _proposal(code=diff)
    assert render_merged_diff(proposal) == diff


def test_render_raw_code_synthetic() -> None:
    proposal = _proposal(code=GOOD_CODE)
    rendered = render_merged_diff(proposal)
    assert "+++ b/mod.py" in rendered
    assert "+def add(a: int, b: int) -> int:" in rendered


def test_render_file_operations() -> None:
    proposal = _proposal(
        code="",
        file_ops=[
            {"action": "write", "path": "mod.py", "content": GOOD_CODE},
            {"action": "delete", "path": "old.py", "content": "x = 1\n"},
        ],
    )
    rendered = render_merged_diff(proposal)
    assert "+++ b/mod.py" in rendered
    assert "+++ /dev/null" in rendered
    assert "-x = 1" in rendered


# --- Runner: search → veto → merge → audit (scripted gateway + substrate) ---


def _diverge_payload(codes: list[str]) -> str:
    branches = [
        {
            "strategy_title": f"strategy-{index}",
            "hypothesis_or_rationale": "test hypothesis",
            "proposed_changes": code,
        }
        for index, code in enumerate(codes)
    ]
    return json.dumps({"branches": branches})


def _critique_payload(
    score: float, verdict: str = "APPROVE", rationale: str = "thorough review"
) -> str:
    return json.dumps({"value_score": score, "verdict": verdict, "rationale": rationale})


def _make_handler(
    diverge_codes: list[str],
    *,
    synth_code: str = SYNTH_CODE,
    good_score: float = 0.9,
    escalate_marker: str | None = None,
    diverge_raw: str | None = None,
) -> Any:
    def handle(request: GatewayRequest) -> str:
        prompt = request.messages[0]["content"] if request.messages else ""
        text = str(prompt)
        if request.role == "diverge":
            if diverge_raw is not None:
                return diverge_raw
            return _diverge_payload(diverge_codes)
        if request.role == "synthesize":
            return json.dumps(
                {
                    "synthesized_title": "synth",
                    "synthesis_rationale": "blend",
                    "executable_content": synth_code,
                }
            )
        if request.role == "refine":
            return json.dumps(
                {
                    "refined_title": "refined",
                    "refactoring_notes": "notes",
                    "executable_content": GOOD_CODE,
                }
            )
        if request.role == "critique":
            if "GARBAGE-CRITIQUE" in text:
                raise ProviderGatewayError(
                    "garbage critique: unparseable model output",
                    category="model_error",
                    remediation="retry",
                )
            if escalate_marker is not None and escalate_marker in text:
                return _critique_payload(0.99, "ESCALATE_HUMAN", "uncertain architecture")
            if "Low branch" in text:
                return _critique_payload(0.6, rationale="meets the goal, minimal margin")
            if "Synth blend" in text:
                return _critique_payload(0.88, rationale="strong blend of both parents")
            return _critique_payload(good_score, rationale="thorough review, solid types")
        raise AssertionError(f"unexpected role {request.role!r}")

    return handle


class FakeAuditor:
    """Scripted judiciary: queued verdicts, calls recorded."""

    def __init__(self, verdicts: list[JudiciaryVerdict]) -> None:
        self.with_codex = False
        self._verdicts = list(verdicts)
        self.calls: list[tuple[str, TaskBundle, ExecutionReceipt]] = []

    def audit_diff(
        self, diff_text: str, bundle: TaskBundle, receipt: ExecutionReceipt
    ) -> JudiciaryVerdict:
        self.calls.append((diff_text, bundle, receipt))
        if len(self._verdicts) > 1:
            return self._verdicts.pop(0)
        return self._verdicts[0]


def _verdict(status: str = "APPROVED") -> JudiciaryVerdict:
    return JudiciaryVerdict(
        task_id="T1", status=status, findings=[], summary_rationale="test verdict"
    )


def _runner(
    tmp_path: Path,
    substrate: Any,
    handler: Any,
    auditor: Any,
    *,
    policy: SearchPolicy | None = None,
    post_receipt: ExecutionReceipt | None = None,
    time_budget_seconds: int = 60,
    **kwargs: Any,
) -> tuple[DialecticRunner, Path]:
    src = _git_source(tmp_path)
    if post_receipt is not None and isinstance(substrate, FakeSubstrate):
        substrate.post_receipt = post_receipt
    runner = DialecticRunner(
        ctx=_ctx(str(src), time_budget_seconds=time_budget_seconds),
        gateway=ScriptGateway(handler),
        substrate=substrate,
        evidence_root=tmp_path / "ev",
        policy=(
            policy
            if policy is not None
            else SearchPolicy(max_iterations=1, max_depth=2, branching_factor=4)
        ),
        auditor=auditor,
        **kwargs,
    )
    return runner, src


class _RoleHarness:
    """Harness-level stub serving gateway-handler payloads per SST role.

    Wraps a _make_handler-style ``handle(request)`` so the REAL STC CLI
    gateway (CLIModelGateway + CLIGatewayBackend) can drive a run in the
    caller exercise. ``name=None`` leaves the harness unnamed (exec-like,
    spend unknown); a name marks a provably-$0 harness (manual/mock).
    """

    def __init__(self, handle: Any, name: str | None) -> None:
        self._handle = handle
        if name is not None:
            self.name = name

    def execute(
        self,
        prompt: str,
        role: str = "general",
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        from types import SimpleNamespace  # local: keep module imports (H1 §1) stable

        _ = (model, context)
        request = GatewayRequest(role=role, messages=[{"role": "user", "content": prompt}])
        content = self._handle(request)
        return SimpleNamespace(is_success=True, exit_code=0, content=content, error=None)


def _runner_with_cli_gateway(
    tmp_path: Path,
    substrate: Any,
    harness: Any,
    auditor: Any,
    *,
    policy: SearchPolicy | None = None,
    time_budget_seconds: int = 60,
) -> tuple[DialecticRunner, Path]:
    """DialecticRunner on the REAL STC CLI gateway (caller exercise).

    Unlike _runner (ScriptGateway), this drives CLIModelGateway +
    CLIGatewayBackend with an explicit harness, proving the
    controller→gateway→harness seam against the pinned SST —
    including honest-budget cost accounting. Local imports keep the
    module import block (H1 §1 spans) stable.
    """
    from sst.gateway.contracts import ModelCatalog, ProviderKind, ProviderProfile

    from stc.integration.cli_gateway import CLIGatewayBackend, CLIModelGateway
    from stc.integration.harness_worker import SpendLedger

    src = _git_source(tmp_path)
    backend = CLIGatewayBackend(
        "mock",
        project_root=src,
        ledger=SpendLedger(path=tmp_path / "spend.jsonl"),
        harness=harness,
        task_label="caller-exercise",
    )
    gateway = CLIModelGateway(backend)
    gateway.register_profile(
        ProviderProfile(
            name="cli",
            kind=ProviderKind.TEST,
            api_base="cli://local",
            selected_model="default",
            catalog=ModelCatalog(),
        )
    )
    for role in ("diverge", "refine", "critique", "synthesize"):
        gateway.set_route(role, "cli", "default")
    runner = DialecticRunner(
        ctx=_ctx(str(src), time_budget_seconds=time_budget_seconds),
        gateway=gateway,
        substrate=substrate,
        evidence_root=tmp_path / "ev",
        policy=(
            policy
            if policy is not None
            else SearchPolicy(max_iterations=1, max_depth=2, branching_factor=4)
        ),
        auditor=auditor,
    )
    return runner, src


def _merged_calls(substrate: FakeSubstrate) -> list[dict[str, Any]]:
    return [call for call in substrate.calls if call["worktree"].endswith("merged")]


def test_no_champion_when_no_proposals(tmp_path: Path) -> None:
    runner, _ = _runner(
        tmp_path,
        FakeSubstrate(),
        _make_handler([], diverge_raw=""),
        FakeAuditor([_verdict()]),
    )
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert result.reason == "no-verified-candidate"
    assert result.branch_refs == []
    assert result.scores_summary == {}
    assert result.veto_log == []
    assert not (Path(result.evidence_dir) / "merged").exists()
    assert (Path(result.evidence_dir) / "result.json").is_file()
    assert (Path(result.evidence_dir) / "store.db").is_file()
    assert (Path(result.evidence_dir) / "inhibitors.json").is_file()


def test_no_champion_when_all_pruned(tmp_path: Path) -> None:
    substrate = FakeSubstrate(fail_marker="FAIL-ME")
    codes = ["# FAIL-ME\n" + FAIL_CODE, "# FAIL-ME\n" + FAIL_CODE]
    runner, _ = _runner(tmp_path, substrate, _make_handler(codes), FakeAuditor([_verdict()]))
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert result.reason == "no-verified-candidate"
    assert len(result.branch_refs) == 2
    assert result.scores_summary == {}
    assert len(substrate.calls) == 2
    assert _merged_calls(substrate) == []


def test_no_champion_budget_exhausted_reason(tmp_path: Path) -> None:
    substrate = FakeSubstrate(fail_marker="FAIL-ME", delay=1.1)
    codes = ["# FAIL-ME\n" + FAIL_CODE]
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler(codes),
        FakeAuditor([_verdict()]),
        policy=SearchPolicy(max_iterations=3, max_depth=2, max_time_seconds=1),
    )
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert result.reason == "budget-exhausted"


def test_clean_champion_merges_with_receipt(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    post = _receipt("T1", passing=True)
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=post,
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    assert result.reselected is False
    assert result.veto_log == []
    assert result.champion_id.startswith("cand_")
    assert result.synthesis_receipts == []
    assert result.loss_ledger.entries == []
    assert list(result.scores_summary.values()) == [0.9]
    merged_code = (Path(result.evidence_dir) / "merged" / "mod.py").read_text(encoding="utf-8")
    assert merged_code == GOOD_CODE.strip()
    assert result.post_merge_receipt.receipt_id == post.receipt_id
    assert "+def add(a: int, b: int) -> int:" in result.merged_diff
    assert (Path(result.evidence_dir) / "post_merge_receipt.json").is_file()
    assert (Path(result.evidence_dir) / "events.json").is_file()
    assert (Path(result.evidence_dir) / "store.db").is_file()


# NOTE (SST cand-02 handoff): test_veto_reselects_and_receipts_synthesis
# retired — veto-then-reselect-to-synthesis is unreachable under honest
# SST scores (tainted 0.5 can never be synthesis-paired). Veto-to-
# NoChampion stays covered by test_all_tainted_yields_no_champion.


def test_all_tainted_yields_no_champion(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    garbage = GARBAGE_CODE + "# GARBAGE-CRITIQUE\n"
    runner, _ = _runner(tmp_path, substrate, _make_handler([garbage]), FakeAuditor([_verdict()]))
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert result.reason == "champion-vetoed-no-alternative"
    assert len(result.veto_log) == 1
    assert result.veto_log[0].rule == "explicit-critique-failed"
    assert _merged_calls(substrate) == []


def test_escalated_excluded_from_reselection(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    garbage = GARBAGE_CODE + "# GARBAGE-CRITIQUE\n"
    escalated = GOOD_CODE + "# ESCALATE-ME\n"
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([garbage, escalated], escalate_marker="ESCALATE-ME"),
        FakeAuditor([_verdict()]),
    )
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert result.reason == "champion-vetoed-no-alternative"
    events = json.loads((Path(result.evidence_dir) / "events.json").read_text(encoding="utf-8"))
    kinds = [event["kind"] for event in events]
    assert "HUMAN_DECISION_REQUESTED" in kinds


def test_loss_ledger_records_sub_threshold(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE, LOW_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=_receipt("T1", passing=True),
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    assert result.synthesis_receipts == []
    assert len(result.loss_ledger.entries) == 1
    entry = result.loss_ledger.entries[0]
    assert entry.normalized_reward == 0.6
    assert entry.critic_verdict == "APPROVE"
    assert entry.reason == "below-synthesis-threshold"
    assert entry.candidate_id != result.champion_id


def test_post_merge_call_has_no_pytest_target(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=_receipt("T1", passing=True),
    )
    runner.run(_bundle())
    merged = _merged_calls(substrate)
    assert len(merged) == 1
    assert merged[0]["pytest_target"] is None
    assert merged[0]["run_mutmut"] is True


def test_mutmut_disposition_disabled_config(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=_receipt("T1", passing=True),
        champion_mutmut=False,
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    assert result.mutmut_count == 0
    assert result.mutmut_disposition.startswith("not-run: disabled-by-config")
    assert _merged_calls(substrate)[0]["run_mutmut"] is False


def test_mutmut_disposition_module_missing(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    post = _mutmut_receipt(0.5, "/usr/bin/python: No module named mutmut", 1)
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=post,
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    assert result.mutmut_count == 0
    assert "mutmut-unavailable" in result.mutmut_disposition


def test_mutmut_counted_once_shape(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    post = _mutmut_receipt(1.25, "Killed 18 of 20\n[mutmut kill rate: 90.00%]")
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=post,
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    assert result.mutmut_count == 1
    assert result.mutmut_disposition == "counted-once"


def test_judiciary_with_codex_true_rejected(tmp_path: Path) -> None:
    src = _git_source(tmp_path)
    with pytest.raises(DialecticError, match="with_codex"):
        DialecticRunner(
            ctx=_ctx(str(src)),
            gateway=ScriptGateway(_make_handler([GOOD_CODE])),
            substrate=FakeSubstrate(),  # type: ignore[arg-type]
            evidence_root=tmp_path / "ev",
            auditor=JudiciaryAuditor(with_codex=True),
        )


def test_judiciary_default_real_auditor_approves(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    src = _git_source(tmp_path)
    if isinstance(substrate, FakeSubstrate):
        substrate.post_receipt = _receipt("T1", passing=True)
    runner = DialecticRunner(
        ctx=_ctx(str(src)),
        gateway=ScriptGateway(_make_handler([GOOD_CODE])),
        substrate=substrate,  # type: ignore[arg-type]
        evidence_root=tmp_path / "ev",
        policy=SearchPolicy(max_iterations=1, max_depth=2, branching_factor=4),
    )
    assert runner._auditor.with_codex is False
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    assert result.judiciary_verdict.status == "APPROVED"


def test_judiciary_rejected_retries_once(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    auditor = FakeAuditor([_verdict("REJECTED"), _verdict("APPROVED")])
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        auditor,
        post_receipt=_receipt("T1", passing=True),
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    assert result.judiciary_verdict.status == "APPROVED"
    assert result.first_verdict is not None
    assert result.first_verdict.status == "REJECTED"
    assert len(auditor.calls) == 2
    assert len(result.retry_receipts) == 1
    assert len(result.retry_mutmut_counts) == 1
    assert len(_merged_calls(substrate)) == 2
    assert (Path(result.evidence_dir) / "retry_receipt.json").is_file()


def test_async_bridging_sync_and_async(tmp_path: Path) -> None:
    import asyncio

    substrate = FakeSubstrate()
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=_receipt("T1", passing=True),
    )
    via_async = asyncio.run(runner.run_async(_bundle()))
    via_sync = runner.run(_bundle())
    assert isinstance(via_async, ChampionResult)
    assert isinstance(via_sync, ChampionResult)
    assert via_async.merged_diff == via_sync.merged_diff
    assert via_async.tree_id != via_sync.tree_id


def test_inhibitor_injection_reaches_packet(tmp_path: Path) -> None:
    from stc.integration.memory import FileBackedMemory

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "inhibitors.md").write_text(
        "## Test mod inhibitor {#test-mod}\n"
        "\n"
        "- component: mod\n"
        "- source: unit-test\n"
        "- as-of: stc@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, 2026-09-13\n"
        "\n"
        "> Do not break the add function in test fixtures.\n",
        encoding="utf-8",
    )
    memory = FileBackedMemory(corpus_dir=corpus)
    substrate = FakeSubstrate()
    src = _git_source(tmp_path)
    runner = DialecticRunner(
        ctx=_ctx(str(src)),
        gateway=ScriptGateway(_make_handler([GOOD_CODE])),
        substrate=substrate,  # type: ignore[arg-type]
        evidence_root=tmp_path / "ev",
        memory=memory,
        policy=SearchPolicy(max_iterations=1, max_depth=2, branching_factor=4),
        auditor=FakeAuditor([_verdict()]),  # type: ignore[arg-type]
        champion_mutmut=False,
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    injected = json.loads(
        (Path(result.evidence_dir) / "inhibitors.json").read_text(encoding="utf-8")
    )
    assert len(injected["injected"]) == 1
    assert injected["injected"][0].startswith("memory-inhibitor: ")
    assert "Do not break the add function" in injected["injected"][0]
    events = json.loads((Path(result.evidence_dir) / "events.json").read_text(encoding="utf-8"))
    tree_created = next(event for event in events if event["kind"] == "TREE_CREATED")
    assert any(
        "memory-inhibitor" in invariant for invariant in tree_created["payload"]["invariants"]
    )


def test_inhibitor_none_memory(tmp_path: Path) -> None:
    substrate = FakeSubstrate()
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=_receipt("T1", passing=True),
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    injected = json.loads(
        (Path(result.evidence_dir) / "inhibitors.json").read_text(encoding="utf-8")
    )
    assert injected["injected"] == []
    assert injected["memory_corpus"] is None


def test_bundle_binding_error_propagates(tmp_path: Path) -> None:
    from stc.integration.adapters import RunBindingError

    runner, _ = _runner(
        tmp_path, FakeSubstrate(), _make_handler([GOOD_CODE]), FakeAuditor([_verdict()])
    )
    bad = _bundle()
    bad = bad.model_copy(update={"epoch_index": 2})
    with pytest.raises(RunBindingError):
        runner.run(bad)


def test_store_preserved_with_tree_created(tmp_path: Path) -> None:
    from sst.storage.store import SQLiteSSTStore

    substrate = FakeSubstrate()
    runner, _ = _runner(
        tmp_path,
        substrate,
        _make_handler([GOOD_CODE]),
        FakeAuditor([_verdict()]),
        post_receipt=_receipt("T1", passing=True),
    )
    result = runner.run(_bundle())
    assert isinstance(result, ChampionResult)
    store = SQLiteSSTStore(Path(result.evidence_dir) / "store.db")
    kinds = [str(event.kind) for event in store.get_events(result.tree_id)]
    assert "TREE_CREATED" in kinds
    assert "SCORE_RECORDED" in kinds
    assert result.tree_id == result.run_id


# --- Runner-wall elapsed accumulation (P04-fix, INFO-2) ---


def test_fix_elapsed_accumulates_two_280s_legs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two simulated 280s gateway legs report >= 560-eps (>= controller value).

    The controller stamps elapsed at the iteration TOP with no final stamp, so
    its raw value omits the last leg; the runner's own wall wins the max().
    Fake clock: deterministic, zero real waiting. No-champion shape mirrors
    the observed INFO-2 failure (elapsed 280.29 vs ~560s wall).
    """
    import time

    from sst.search.controller import SSTSearchController

    clock = [1000.0]
    monkeypatch.setattr(time, "perf_counter", lambda: clock[0])
    base = _make_handler(["# FAIL-ME\n" + FAIL_CODE])
    generation_legs: list[str] = []

    def handle(request: GatewayRequest) -> str:
        if request.role in ("diverge", "refine"):
            generation_legs.append(request.role)
            clock[0] += 280.0
        text: str = base(request)
        return text

    captured: dict[str, Any] = {}
    original_execute = SSTSearchController.execute_search

    async def spy(self: SSTSearchController, tree_id: str) -> Any:
        captured["controller"] = self
        return await original_execute(self, tree_id)

    monkeypatch.setattr(SSTSearchController, "execute_search", spy)
    runner, _ = _runner(
        tmp_path,
        FakeSubstrate(fail_marker="FAIL-ME"),
        handle,
        FakeAuditor([_verdict()]),
        policy=SearchPolicy(max_iterations=2, max_depth=2, branching_factor=1),
        # New SST binds the task budget: the 2x280s simulation needs a
        # budget covering 560s of fake wall (was ignored pre-cand-02).
        time_budget_seconds=600,
    )
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert result.reason == "no-verified-candidate"
    assert generation_legs == ["diverge", "diverge"]
    raw_controller = float(captured["controller"].budget_tracker.elapsed_seconds)
    assert raw_controller == pytest.approx(280.0)
    reported = result.budget_state["elapsed_seconds"]
    assert reported >= 560.0 - 1e-6
    assert reported >= raw_controller
    assert reported == pytest.approx(560.0)
    assert result.budget_state["iterations_completed"] == 1.0


def test_fix_elapsed_single_leg_equals_own_wall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One simulated 137.25s leg reports exactly the runner's own wall."""
    import time

    from sst.search.controller import SSTSearchController

    clock = [500.0]
    monkeypatch.setattr(time, "perf_counter", lambda: clock[0])
    base = _make_handler(["# FAIL-ME\n" + FAIL_CODE])
    generation_legs: list[str] = []

    def handle(request: GatewayRequest) -> str:
        if request.role in ("diverge", "refine"):
            generation_legs.append(request.role)
            clock[0] += 137.25
        text: str = base(request)
        return text

    captured: dict[str, Any] = {}
    original_execute = SSTSearchController.execute_search

    async def spy(self: SSTSearchController, tree_id: str) -> Any:
        captured["controller"] = self
        return await original_execute(self, tree_id)

    monkeypatch.setattr(SSTSearchController, "execute_search", spy)
    runner, _ = _runner(
        tmp_path,
        FakeSubstrate(fail_marker="FAIL-ME"),
        handle,
        FakeAuditor([_verdict()]),
        policy=SearchPolicy(max_iterations=1, max_depth=2, branching_factor=1),
    )
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert generation_legs == ["diverge"]
    raw_controller = float(captured["controller"].budget_tracker.elapsed_seconds)
    assert raw_controller == 0.0
    assert result.budget_state["elapsed_seconds"] == pytest.approx(137.25)


# --- A1: dst-inside-src mirror bound (FOLLOWUP a1-fix) ---


def test_mirror_dst_inside_src_excludes_destination(tmp_path: Path) -> None:
    """A1 regression: dst nested inside src (live dossier layout) terminates.

    Mirrors the accept attempt-1 shape: source root ``ws/stc`` with the lease
    at ``<src>/docs/.../dossier/runs/<run>/leases/<lease>``. Pre-fix this
    recursed without bound (lease copied into itself to ENAMETOOLONG /
    disk-full); post-fix the mirror terminates, the dst subtree is excluded,
    and all genuine source content is faithful byte-exact.
    """
    src = tmp_path / "stc"
    (src / "src" / "pkg").mkdir(parents=True)
    (src / "src" / "pkg" / "mod.py").write_text(GOOD_CODE, encoding="utf-8")
    (src / "tests").mkdir()
    (src / "tests" / "test_mod.py").write_text(
        "def test_add() -> None:\n    assert True\n", encoding="utf-8"
    )
    (src / ".git" / "objects").mkdir(parents=True)
    (src / ".git" / "objects" / "pack").write_text("pack-bytes", encoding="utf-8")
    dst = (
        src
        / "docs"
        / "builds"
        / "x"
        / "evidence"
        / "dossier"
        / "runs"
        / "run-1"
        / "leases"
        / "lease-1"
    )
    dst.mkdir(parents=True)
    (dst / "pre-existing.txt").write_text("lease-marker", encoding="utf-8")

    mirror_source_tree(src, dst)

    # Dst subtree excluded: the lease dir never reappears under itself, and the
    # pre-existing lease marker is not duplicated.
    nested_lease = (
        dst
        / "docs"
        / "builds"
        / "x"
        / "evidence"
        / "dossier"
        / "runs"
        / "run-1"
        / "leases"
        / "lease-1"
    )
    assert not nested_lease.exists()
    assert list(dst.rglob("pre-existing.txt")) == [dst / "pre-existing.txt"]
    # Exact bound: dst holds the mirror of genuine source content + the
    # untouched marker — nothing more (no runaway nesting).
    mirrored = sorted(str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file())
    assert mirrored == [
        ".git/objects/pack",
        "pre-existing.txt",
        "src/pkg/mod.py",
        "tests/test_mod.py",
    ]
    # Faithful byte-exact, and the pre-existing dst content is preserved.
    assert (dst / "src" / "pkg" / "mod.py").read_text(encoding="utf-8") == GOOD_CODE
    assert (dst / ".git" / "objects" / "pack").read_text(encoding="utf-8") == "pack-bytes"
    assert (dst / "pre-existing.txt").read_text(encoding="utf-8") == "lease-marker"


def test_mirror_disjoint_layout_faithful(tmp_path: Path) -> None:
    """Normal disjoint layout: faithful copy, skip-set excluded, .git kept."""
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text(GOOD_CODE, encoding="utf-8")
    (src / ".git" / "objects").mkdir(parents=True)
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (src / ".venv" / "lib").mkdir(parents=True)
    (src / ".venv" / "lib" / "huge.py").write_text("x = 1\n", encoding="utf-8")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "mod.pyc").write_bytes(b"\x00\x01")
    dst = tmp_path / "leases" / "lease-1"

    mirror_source_tree(src, dst)

    assert (dst / "pkg" / "mod.py").read_text(encoding="utf-8") == GOOD_CODE
    assert (dst / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert (dst / ".git" / "objects").is_dir()
    assert not (dst / ".venv").exists()
    assert not (dst / "__pycache__").exists()


def test_mirror_skips_backend_runtime_outputs(tmp_path: Path) -> None:
    """Mirror skips top-level runtime outputs (walkthrough wedge).

    Dossier/.durable/worktrees/artifacts/node_modules at the mirror
    root are backend runtime outputs, evidence archives, or install
    artifacts, never evaluated bytes; mirroring them wedged lease
    setup on real trees (gigabytes over slow mounts). Nested dirs
    with these names are preserved (next test).
    """
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text(GOOD_CODE, encoding="utf-8")
    (src / ".git" / "objects").mkdir(parents=True)
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (src / "dossier" / "runs").mkdir(parents=True)
    (src / "dossier" / "qa_log.json").write_text("{}\n", encoding="utf-8")
    (src / ".durable" / "dsh").mkdir(parents=True)
    (src / ".durable" / "dsh" / "big.bin").write_text("0" * 100, encoding="utf-8")
    (src / "worktrees" / "lease-1").mkdir(parents=True)
    (src / "worktrees" / "lease-1" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (src / "artifacts" / "notebooklm").mkdir(parents=True)
    (src / "artifacts" / "notebooklm" / "media.bin").write_text("0" * 100, encoding="utf-8")
    (src / "node_modules" / "pkg").mkdir(parents=True)
    (src / "node_modules" / "pkg" / "index.js").write_text("z = 3\n", encoding="utf-8")
    dst = tmp_path / "leases" / "lease-1"

    mirror_source_tree(src, dst)

    assert (dst / "pkg" / "mod.py").read_text(encoding="utf-8") == GOOD_CODE
    assert (dst / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert not (dst / "dossier").exists()
    assert not (dst / ".durable").exists()
    assert not (dst / "worktrees").exists()
    assert not (dst / "artifacts").exists()
    assert not (dst / "node_modules").exists()


def test_mirror_preserves_nested_runtime_named_evidence(tmp_path: Path) -> None:
    """Skip-set applies top-level only: nested dirs with runtime names
    (docs/.../dossier evidence) are evaluated content the lease needs.

    R4B regression: every-level skip emptied the attempt-1 dossier in
    the lease and red-lit the real-gates green path
    (test_embedded_bytes_match_dossier).
    """
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text(GOOD_CODE, encoding="utf-8")
    nested = src / "docs" / "builds" / "x" / "evidence" / "dossier" / "runs"
    nested.mkdir(parents=True)
    (nested / "events.json").write_text('{"k": "v"}\n', encoding="utf-8")
    (src / "dossier" / "runs").mkdir(parents=True)
    (src / "dossier" / "qa_log.json").write_text("{}\n", encoding="utf-8")
    dst = tmp_path / "leases" / "lease-1"

    mirror_source_tree(src, dst)

    assert (dst / "pkg" / "mod.py").read_text(encoding="utf-8") == GOOD_CODE
    assert (
        dst / "docs" / "builds" / "x" / "evidence" / "dossier" / "runs" / "events.json"
    ).read_text(encoding="utf-8") == '{"k": "v"}\n'
    assert not (dst / "dossier").exists()


def test_mirror_self_reference_refuses_loudly(tmp_path: Path) -> None:
    """Un-mirrorable self layouts raise DialecticError (bound, never silent)."""
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text(GOOD_CODE, encoding="utf-8")
    with pytest.raises(DialecticError, match="into itself"):
        mirror_source_tree(src, src)
    with pytest.raises(DialecticError, match="into itself"):
        mirror_source_tree(src / "pkg", src)


def test_mirror_dir_symlink_replicated_never_followed(tmp_path: Path) -> None:
    """Dir symlinks (incl. cycles) replicate as links; no ELOOP, no foreign bytes."""
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text(GOOD_CODE, encoding="utf-8")
    (tmp_path / "ext").mkdir()
    (tmp_path / "ext" / "foreign.py").write_text("x = 1\n", encoding="utf-8")
    (src / "out").symlink_to(tmp_path / "ext", target_is_directory=True)
    (src / "pkg" / "loop").symlink_to(src, target_is_directory=True)
    dst = tmp_path / "dst"

    mirror_source_tree(src, dst)

    assert (dst / "pkg" / "mod.py").read_text(encoding="utf-8") == GOOD_CODE
    assert (dst / "out").is_symlink()
    assert (dst / "out").readlink() == (tmp_path / "ext")
    assert (dst / "pkg" / "loop").is_symlink()
    assert (dst / "pkg" / "loop").readlink() == src
    # Link, not a copy: new foreign content is visible through it, and no
    # materialized descent exists.
    (tmp_path / "ext" / "later.py").write_text("z = 3\n", encoding="utf-8")
    assert (dst / "out" / "later.py").read_text(encoding="utf-8") == "z = 3\n"
    assert len(list((dst / "pkg").iterdir())) == 2  # mod.py + loop link, no descent


def test_mirror_file_symlink_materializes_target_bytes(tmp_path: Path) -> None:
    """File symlinks keep historical behavior: target bytes materialized."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "real.txt").write_text("hello\n", encoding="utf-8")
    (src / "alias.txt").symlink_to(src / "real.txt")
    dst = tmp_path / "dst"

    mirror_source_tree(src, dst)

    assert not (dst / "alias.txt").is_symlink()
    assert (dst / "alias.txt").read_text(encoding="utf-8") == "hello\n"


def test_mirror_dst_exclusion_survives_symlink_cycles(tmp_path: Path) -> None:
    """Dst-inside-src exclusion still holds with cyclic links present (lexical)."""
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text(GOOD_CODE, encoding="utf-8")
    (src / "pkg" / "loop").symlink_to(src, target_is_directory=True)
    dst = src / "leases" / "lease-1"
    dst.mkdir(parents=True)

    mirror_source_tree(src, dst)

    assert (dst / "pkg" / "mod.py").read_text(encoding="utf-8") == GOOD_CODE
    assert not (dst / "leases" / "lease-1").exists()


# --- A4-D1: head-first prune feedback (imports local: file top is H1-pinned) ---


def test_prune_detail_leads_with_gates_and_signals() -> None:
    """The failure head carries gates + locations inside SST's [:100] slice."""
    from stc.integration.adapters import receipt_to_score
    from stc.integration.dialectic_runner import _score_failure_detail

    receipt = ExecutionReceipt(
        receipt_id="rc",
        task_id="T",
        epoch_index=1,
        commit_hash="c",
        timestamp_utc="t",
        python_version="p",
        os_platform="o",
        gate_ruff=_gate(
            "ruff",
            exit_code=1,
            snippet="tests/unit/test_x.py:64:101: E501 Line too long (126 > 100)",
        ),
        gate_mypy=_gate(
            "mypy",
            exit_code=1,
            snippet="tests/unit/test_x.py:30: error: missing annotation  [no-untyped-def]",
        ),
        gate_pytest=_gate("pytest", exit_code=1, snippet="FAILED tests/unit/test_x.py::t"),
        gate_mutmut=_disabled_mutmut(),
        sha256_signature="s",
    )
    score = receipt_to_score(receipt)
    detail = _score_failure_detail(score, "L" * 60)
    assert detail.startswith("FAIL stc_mypy stc_pytest stc_ruff [ruff tests/unit/test_x.py:64:")
    assert "[mypy tests/unit/test_x.py:30:" in detail
    assert "[pytest FAILED tests/unit/test_x.py::t]" in detail
    assert detail.endswith(f"| lease {'L' * 60} (reward 0.00)")
    assert "verifier_passed" not in detail
    head = detail[:100]
    assert "stc_mypy" in head and "stc_pytest" in head and "stc_ruff" in head
    assert "test_x.py:64:" in head


def test_prune_detail_degrades_without_signals() -> None:
    """Foreign scores lacking first_signals still render gates + tail."""
    from sst.core.contracts import ScoreBreakdown

    from stc.integration.dialectic_runner import _score_failure_detail

    score = ScoreBreakdown(
        passed_hard_gates=False,
        hard_gates={
            "verifier_passed": False,
            "stc_ruff": True,
            "stc_mypy": True,
            "stc_pytest": False,
        },
        normalized_reward=0.5,
    )
    detail = _score_failure_detail(score, "lease-1")
    assert detail == "FAIL stc_pytest | lease lease-1 (reward 0.50)"


def test_wrapper_gate_failure_stderr_is_head_first(tmp_path: Path) -> None:
    """End to end: the prune stderr/failure_reason lead with the failed gate."""
    substrate = FakeSubstrate(fail_marker="FAIL-ME")
    wrapper = _wrapper(tmp_path, substrate)
    src = _source(tmp_path)
    bad = _proposal(code="FAIL-ME\n" + GOOD_CODE)
    result = wrapper.verify_candidate_proposal(_packet(source_root=str(src)), bad, src)
    assert result.passed is False
    assert result.stderr.startswith("FAIL stc_pytest [pytest 1 failed]")
    assert "| lease " in result.stderr and "(reward 0.50)" in result.stderr
    assert result.failure_reason == result.stderr


# --- Reporting agreement: spend-cap mapping + evidence preservation ---


def test_spend_cap_exhaustion_yields_typed_budget_exhausted(tmp_path: Path) -> None:
    """A ledger quota hit mid-search is a typed result, never a crash."""
    from stc.integration.harness_worker import SpendCapExceededError

    def _capped(request: Any) -> str:
        raise SpendCapExceededError("Spend cap reached: 40/40 gateway calls used")

    runner, _src = _runner(tmp_path, FakeSubstrate(), _capped, FakeAuditor([_verdict()]))
    result = runner.run(_bundle())
    assert isinstance(result, NoChampionResult)
    assert result.reason == "budget-exhausted"
    run_dir = Path(result.evidence_dir)
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "selection_outcome.json").is_file()
    assert (run_dir / "events.json").is_file()


def test_no_champion_preserves_prior_synthesis_evidence(tmp_path: Path) -> None:
    """Merge-path synthesis/loss writes survive the no-champion finish."""
    runner, _src = _runner(
        tmp_path, FakeSubstrate(), _make_handler([GOOD_CODE]), FakeAuditor([_verdict()])
    )
    run_dir = tmp_path / "ev" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "synthesis.json").write_text('[{"kept": true}]', encoding="utf-8")
    (run_dir / "loss_ledger.json").write_text('{"kept": true}', encoding="utf-8")
    result = runner._no_champion(
        run_dir,
        "tree-1",
        "run-1",
        ["cand-1"],
        {"cand-1": 0.9},
        [],
        {"elapsed_seconds": 1.0},
        "merge-apply-failed",
    )
    assert isinstance(result, NoChampionResult)
    assert (run_dir / "synthesis.json").read_text(encoding="utf-8") == '[{"kept": true}]'
    assert (run_dir / "loss_ledger.json").read_text(encoding="utf-8") == '{"kept": true}'
    assert (run_dir / "result.json").is_file()


def test_no_champion_writes_defaults_when_absent(tmp_path: Path) -> None:
    """Early-path runs still get empty synthesis/loss defaults."""
    runner, _src = _runner(
        tmp_path, FakeSubstrate(), _make_handler([GOOD_CODE]), FakeAuditor([_verdict()])
    )
    run_dir = tmp_path / "ev" / "run-1"
    run_dir.mkdir(parents=True)
    runner._no_champion(
        run_dir, "tree-1", "run-1", [], {}, [], {"elapsed_seconds": 1.0}, "no-verified-candidate"
    )
    assert json.loads((run_dir / "synthesis.json").read_text(encoding="utf-8")) == []
    assert "tree-1" in (run_dir / "loss_ledger.json").read_text(encoding="utf-8")


# --- Caller exercise: real CLI gateway against the pinned SST (contract §4) ---


def test_caller_exercise_named_harness_usd_cap_completes(tmp_path: Path) -> None:
    """Named (manual) harness + USD cap completes: $0 is KNOWN, cap holds."""
    handle = _make_handler([GOOD_CODE])
    runner, _ = _runner_with_cli_gateway(
        tmp_path,
        FakeSubstrate(),
        _RoleHarness(handle, name="manual"),
        FakeAuditor([_verdict()]),
        policy=SearchPolicy(max_iterations=1, max_depth=2, branching_factor=1, max_cost_usd=10.0),
    )
    result = runner.run(_bundle())  # must not raise UnpricedCostBudgetError
    assert isinstance(result, (ChampionResult, NoChampionResult))


def test_caller_exercise_unnamed_harness_usd_cap_fails_closed(tmp_path: Path) -> None:
    """Unnamed (exec-like) harness + USD cap fails closed, honestly."""
    from sst.core.errors import UnpricedCostBudgetError

    handle = _make_handler([GOOD_CODE])
    runner, _ = _runner_with_cli_gateway(
        tmp_path,
        FakeSubstrate(),
        _RoleHarness(handle, name=None),
        FakeAuditor([_verdict()]),
        policy=SearchPolicy(max_iterations=1, max_depth=2, branching_factor=1, max_cost_usd=10.0),
    )
    with pytest.raises(UnpricedCostBudgetError):
        runner.run(_bundle())


def test_caller_exercise_run_search_surface() -> None:
    """Newer optional surface: run_search present with the expected shape.

    execute_search (the wrapped path every run exercises) already drives
    run_search internally, so presence + signature is the assertion;
    absence would fail only if STC starts requiring it (contract §2).
    """
    from sst.search.controller import SSTSearchController

    assert hasattr(SSTSearchController, "run_search")
    assert inspect.iscoroutinefunction(SSTSearchController.run_search)
    params = inspect.signature(SSTSearchController.run_search).parameters
    assert "tree_id" in params and "acquire_lease" in params
