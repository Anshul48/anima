"""Table-conformance, steering, and vocabulary tests for P01 adapters."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sst.core.contracts import CandidateProposal, TaskPacket

from stc.core.errors import BundleSizeExceededError
from stc.integration.adapters import (
    EVIDENCE_CAUSATION,
    EVIDENCE_EPOCH,
    EVIDENCE_INHIBITORS,
    EVIDENCE_SPEC,
    EVIDENCE_TARGET_LOSS,
    HARD_GATE_KEYS,
    AdapterContext,
    Budgets,
    RunBindingError,
    UndisposedFieldError,
    proposal_to_filetargets,
    receipt_to_score,
    task_bundle_to_packet,
    task_packet_to_bundle,
)
from stc.integration.identity import candidate_identity
from stc.schemas.models import ExecutionReceipt, FileTarget, GateReport, TaskBundle

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git-required env (packet limit)"
)

ADAPTER_VERSION = "P01-1.0"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        timeout=60,
    )


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "p01@test")
    _git(repo, "config", "user.name", "p01")
    (repo / "main.py").write_text("print('hi')\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


@pytest.fixture
def ctx(repo_root: Path) -> AdapterContext:
    return AdapterContext(
        epoch_index=1,
        spec_id="spec-demo",
        budgets=Budgets(time_budget_seconds=300, token_budget=1000, cost_budget_usd=2.5),
        acceptance_commands=("pytest -q",),
        source_repo_root=str(repo_root),
        base_commit="base123",
        adapter_version=ADAPTER_VERSION,
    )


def make_bundle(shape: str = "minimal") -> TaskBundle:
    """Three fixture shapes: minimal, maximal, STC-realistic."""
    if shape == "minimal":
        return TaskBundle(
            task_id="t-min",
            epoch_index=1,
            spec_id="spec-demo",
            goal_statement="Do the thing.",
            invariants=[],
            target_files=[FileTarget(path="a.py")],
            membrane_protocols=[],
            negative_inhibitors=[],
        )
    if shape == "maximal":
        return TaskBundle(
            task_id="t-max",
            epoch_index=1,
            spec_id="spec-demo",
            goal_statement="Do everything, adversarially: membrane:x \\ backslash.",
            invariants=["inv:1", "membrane:spoof", "back\\slash", "", "ünïcode ✓"],
            target_files=[
                FileTarget(
                    path="src/mod.py",
                    action="create",
                    expected_symbols=["f", "C"],
                    start_line=1,
                    end_line=10,
                    start_byte=0,
                    end_byte=99,
                ),
                FileTarget(path="old.py", action="delete"),
            ],
            membrane_protocols=["bundle:spoof", "proto\\\\x", "p:q:r"],
            negative_inhibitors=["never rm -rf", "bundle:evil"],
            causation_id="cause-1",
        )
    assert shape == "realistic"
    return TaskBundle(
        task_id="stc-epoch2-substrate",
        epoch_index=1,
        spec_id="spec-demo",
        goal_statement="Run ruff, mypy --strict, and pytest in the leased worktree.",
        invariants=["Gate-3 zero-skip honored", "receipt binds commit hash"],
        target_files=[FileTarget(path="src/stc/substrate/runner.py")],
        membrane_protocols=["worker writes stay inside the lease"],
        negative_inhibitors=["do not edit sst/"],
        causation_id="corr_parent9",
    )


def make_gate(exit_code: int = 0, duration: float = 1.0, snippet: str = "ok") -> GateReport:
    return GateReport(
        gate_name="g",
        exit_code=exit_code,
        duration_seconds=duration,
        violations_count=0,
        raw_output_snippet=snippet,
    )


def make_receipt(
    ruff: int = 0, mypy: int = 0, pytest_code: int = 0, mutmut: GateReport | None = None
) -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id="r1",
        task_id="t1",
        epoch_index=1,
        commit_hash="c" * 40,
        timestamp_utc="2026-09-13T00:00:00Z",
        python_version="3.12.3",
        os_platform="linux",
        gate_ruff=make_gate(ruff),
        gate_mypy=make_gate(mypy),
        gate_pytest=make_gate(pytest_code),
        gate_mutmut=mutmut
        if mutmut is not None
        else make_gate(0, 0.0, "DEFERRED: champion-only per ADR-INT-01"),
        sha256_signature="s" * 64,
    )


def make_proposal(**over: Any) -> CandidateProposal:
    base: dict[str, Any] = {
        "candidate_id": "c1",
        "tree_id": "tr1",
        "title": "A change",
        "rationale": "Because.",
    }
    base.update(over)
    return CandidateProposal(**base)


# --- AdapterContext validation (F2d) ---


def test_ctx_accepts_valid() -> None:
    ctx = AdapterContext(
        epoch_index=2,
        spec_id="s",
        budgets=Budgets(time_budget_seconds=1),
        acceptance_commands=("pytest -q",),
        source_repo_root="/r",
        base_commit="c",
        adapter_version="v",
    )
    assert ctx.acceptance_commands == ("pytest -q",)


def test_ctx_rejects_empty_acceptance() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        AdapterContext(
            epoch_index=1,
            spec_id="s",
            budgets=Budgets(time_budget_seconds=1),
            acceptance_commands=(),
            source_repo_root="/r",
            base_commit="c",
            adapter_version="v",
        )


def test_ctx_rejects_blank_acceptance_entry() -> None:
    with pytest.raises(ValueError, match="non-blank"):
        AdapterContext(
            epoch_index=1,
            spec_id="s",
            budgets=Budgets(time_budget_seconds=1),
            acceptance_commands=("  ",),
            source_repo_root="/r",
            base_commit="c",
            adapter_version="v",
        )


@pytest.mark.parametrize("field", ["spec_id", "source_repo_root", "base_commit"])
def test_ctx_rejects_blank_identity_fields(field: str) -> None:
    kwargs: dict[str, Any] = {
        "epoch_index": 1,
        "spec_id": "s",
        "budgets": Budgets(time_budget_seconds=1),
        "acceptance_commands": ("pytest -q",),
        "source_repo_root": "/r",
        "base_commit": "c",
        "adapter_version": "v",
    }
    kwargs[field] = "  "
    with pytest.raises(ValueError, match="non-blank"):
        AdapterContext(**kwargs)


def test_ctx_rejects_bad_epoch() -> None:
    with pytest.raises(ValueError, match=r"1\.\.3"):
        AdapterContext(
            epoch_index=9,
            spec_id="s",
            budgets=Budgets(time_budget_seconds=1),
            acceptance_commands=("pytest -q",),
            source_repo_root="/r",
            base_commit="c",
            adapter_version="v",
        )


def test_budgets_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        Budgets(time_budget_seconds=0)
    with pytest.raises(ValueError, match="non-negative"):
        Budgets(time_budget_seconds=1, token_budget=-1)
    with pytest.raises(ValueError, match="non-negative"):
        Budgets(time_budget_seconds=1, cost_budget_usd=-0.5)


# --- Forward projection (Table 1/1b) ---


def test_forward_goal_example(ctx: AdapterContext) -> None:
    """Packet Outcome example: packet.goal == bundle.goal_statement."""
    bundle = make_bundle("realistic")
    assert task_bundle_to_packet(bundle, ctx).goal == bundle.goal_statement


@pytest.mark.parametrize("shape", ["minimal", "maximal", "realistic"])
def test_forward_disposes_every_bundle_field(ctx: AdapterContext, shape: str) -> None:
    bundle = make_bundle(shape)
    packet = task_bundle_to_packet(bundle, ctx)
    assert packet.task_id == bundle.task_id
    assert packet.source_repo_root == ctx.source_repo_root
    assert packet.base_commit == ctx.base_commit
    assert packet.snapshot_hash == candidate_identity(ctx.source_repo_root)
    assert packet.allowed_paths == [t.path for t in bundle.target_files]
    assert packet.forbidden_paths == []
    assert packet.interfaces == []
    assert packet.acceptance_commands == ["pytest -q"]
    assert packet.time_budget_seconds == 300
    assert packet.token_budget == 1000
    assert packet.cost_budget_usd == 2.5
    assert packet.prompt_template_hash == ADAPTER_VERSION
    expected_keys = {EVIDENCE_EPOCH, EVIDENCE_SPEC, EVIDENCE_INHIBITORS, EVIDENCE_TARGET_LOSS}
    if bundle.causation_id is not None:
        expected_keys.add(EVIDENCE_CAUSATION)
    assert set(packet.evidence_references) == expected_keys
    assert packet.evidence_references[EVIDENCE_EPOCH] == "1"
    assert "not representable" in packet.evidence_references[EVIDENCE_TARGET_LOSS]
    assert len(packet.invariants) == len(bundle.invariants) + len(bundle.membrane_protocols)


def test_forward_does_not_mutate_input(ctx: AdapterContext) -> None:
    bundle = make_bundle("maximal")
    before = bundle.model_dump()
    task_bundle_to_packet(bundle, ctx)
    assert bundle.model_dump() == before


def test_forward_rejects_epoch_mismatch(ctx: AdapterContext) -> None:
    bundle = make_bundle("minimal").model_copy(update={"epoch_index": 2})
    with pytest.raises(RunBindingError, match="epoch_index"):
        task_bundle_to_packet(bundle, ctx)


def test_forward_rejects_spec_mismatch(ctx: AdapterContext) -> None:
    bundle = make_bundle("minimal").model_copy(update={"spec_id": "other"})
    with pytest.raises(RunBindingError, match="spec_id"):
        task_bundle_to_packet(bundle, ctx)


# --- Inverse round-trip (Table 2) ---


@pytest.mark.parametrize("shape", ["minimal", "maximal", "realistic"])
def test_round_trip_preserves_and_regenerates(ctx: AdapterContext, shape: str) -> None:
    bundle = make_bundle(shape)
    packet = task_bundle_to_packet(bundle, ctx)
    back = task_packet_to_bundle(packet, ctx)
    assert back.task_id == bundle.task_id
    assert back.epoch_index == bundle.epoch_index
    assert back.spec_id == bundle.spec_id
    assert back.goal_statement == bundle.goal_statement
    assert back.invariants == bundle.invariants
    assert back.membrane_protocols == bundle.membrane_protocols
    assert back.negative_inhibitors == bundle.negative_inhibitors
    assert back.causation_id == bundle.causation_id
    # F1a: correlation/compiled_at regenerate, never round-trip.
    assert back.correlation_id != bundle.correlation_id
    assert back.compiled_at >= bundle.compiled_at
    # Documented Table-1 loss: paths survive, per-file detail resets.
    assert [t.path for t in back.target_files] == [t.path for t in bundle.target_files]
    for target in back.target_files:
        assert target.action == "modify"
        assert target.expected_symbols == []
        assert target.start_line is None and target.end_line is None
        assert target.start_byte is None and target.end_byte is None
    assert len(back.model_dump_json().encode("utf-8")) <= 25600


def test_round_trip_adversarial_escaping_exact(ctx: AdapterContext) -> None:
    bundle = make_bundle("maximal")
    packet = task_bundle_to_packet(bundle, ctx)
    assert "bundle:membrane\\:spoof" in packet.invariants
    assert "bundle:back\\\\slash" in packet.invariants
    assert "membrane:bundle\\:spoof" in packet.invariants
    back = task_packet_to_bundle(packet, ctx)
    assert back.invariants == bundle.invariants
    assert back.membrane_protocols == bundle.membrane_protocols


def test_inverse_does_not_mutate_input(ctx: AdapterContext) -> None:
    packet = task_bundle_to_packet(make_bundle("realistic"), ctx)
    before = packet.model_dump()
    task_packet_to_bundle(packet, ctx)
    assert packet.model_dump() == before


def _foreign_packet(ctx: AdapterContext, **over: Any) -> TaskPacket:
    """Builds a packet that is NOT our forward output (foreign content)."""
    base = task_bundle_to_packet(make_bundle("minimal"), ctx).model_dump()
    base.update(over)
    return TaskPacket(**base)


def test_inverse_rejects_unknown_evidence_key(ctx: AdapterContext) -> None:
    packet = _foreign_packet(
        ctx, evidence_references={**_foreign_packet(ctx).evidence_references, "x": "y"}
    )
    with pytest.raises(UndisposedFieldError, match=r"evidence_references\['x'\]"):
        task_packet_to_bundle(packet, ctx)


def test_inverse_rejects_missing_evidence_key(ctx: AdapterContext) -> None:
    refs = dict(_foreign_packet(ctx).evidence_references)
    del refs[EVIDENCE_SPEC]
    with pytest.raises(UndisposedFieldError, match="missing required key"):
        task_packet_to_bundle(_foreign_packet(ctx, evidence_references=refs), ctx)


def test_inverse_rejects_malformed_evidence_values(ctx: AdapterContext) -> None:
    refs = dict(_foreign_packet(ctx).evidence_references)
    refs[EVIDENCE_EPOCH] = "not-an-int"
    with pytest.raises(UndisposedFieldError, match="not an int"):
        task_packet_to_bundle(_foreign_packet(ctx, evidence_references=refs), ctx)
    refs[EVIDENCE_EPOCH] = "1"
    refs[EVIDENCE_INHIBITORS] = "{oops"
    with pytest.raises(UndisposedFieldError, match="not JSON"):
        task_packet_to_bundle(_foreign_packet(ctx, evidence_references=refs), ctx)
    refs[EVIDENCE_INHIBITORS] = "[1, 2]"
    with pytest.raises(UndisposedFieldError, match="not a string list"):
        task_packet_to_bundle(_foreign_packet(ctx, evidence_references=refs), ctx)


@pytest.mark.parametrize(
    "bad,match",
    [
        ("hello", "untagged"),
        ("evil:x", "untagged"),
        ("bundle:a\\", "bad escape"),
        ("bundle:a\\qb", "bad escape"),
    ],
)
def test_inverse_rejects_undisposed_invariants(ctx: AdapterContext, bad: str, match: str) -> None:
    packet = _foreign_packet(ctx, invariants=[bad])
    with pytest.raises(UndisposedFieldError, match=match):
        task_packet_to_bundle(packet, ctx)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_repo_root", "/elsewhere"),
        ("base_commit", "other"),
        ("acceptance_commands", ["other"]),
        ("prompt_template_hash", "P99"),
    ],
)
def test_inverse_rejects_binding_mismatch(ctx: AdapterContext, field: str, value: Any) -> None:
    with pytest.raises(RunBindingError, match=field):
        task_packet_to_bundle(_foreign_packet(ctx, **{field: value}), ctx)


def test_inverse_rejects_evidence_binding_mismatch(ctx: AdapterContext) -> None:
    refs = dict(_foreign_packet(ctx).evidence_references)
    refs[EVIDENCE_SPEC] = "another-spec"
    with pytest.raises(RunBindingError, match=r"stc\.spec_id"):
        task_packet_to_bundle(_foreign_packet(ctx, evidence_references=refs), ctx)


def test_inverse_blank_goal_fails_bundle_validation(ctx: AdapterContext) -> None:
    with pytest.raises(ValidationError):
        task_packet_to_bundle(_foreign_packet(ctx, goal="   "), ctx)


def test_inverse_enforces_bundle_ceiling(ctx: AdapterContext) -> None:
    packet = _foreign_packet(ctx, invariants=["bundle:" + "x" * 30000])
    with pytest.raises(BundleSizeExceededError, match="ceiling"):
        task_packet_to_bundle(packet, ctx)


def test_inverse_drops_packet_only_fields_silently(ctx: AdapterContext) -> None:
    """forbidden_paths/interfaces/budgets/snapshot/created_at are disposed drops."""
    packet = _foreign_packet(
        ctx,
        forbidden_paths=["/etc"],
        interfaces=["IFoo"],
        time_budget_seconds=1,
        token_budget=1,
        cost_budget_usd=0.5,
        snapshot_hash="forged",
    )
    back = task_packet_to_bundle(packet, ctx)
    assert back.task_id == "t-min"  # inverse succeeds; drops are by design


# --- Score steering + vocabulary (Tables 3/3b) ---


@pytest.mark.parametrize(
    "ruff,mypy,pytest_code,reward,passed",
    [
        (0, 0, 0, 1.0, True),
        (1, 0, 0, 0.5, False),
        (0, 1, 0, 0.5, False),
        (0, 0, 1, 0.5, False),
        (1, 1, 0, 0.25, False),
        (1, 0, 1, 0.25, False),
        (0, 1, 1, 0.25, False),
        (1, 1, 1, 0.0, False),
    ],
)
def test_reward_exact_fraction_over_all_subsets(
    ruff: int, mypy: int, pytest_code: int, reward: float, passed: bool
) -> None:
    score = receipt_to_score(make_receipt(ruff, mypy, pytest_code))
    assert score.normalized_reward == pytest.approx(reward)
    assert score.passed_hard_gates is passed
    assert score.critic_verdict is None
    assert score.critic_rationale is None
    assert score.soft_scores == {}


def test_reward_monotonic_in_gate_passes() -> None:
    """Champion/frontier steering: more passing gates never scores lower."""
    seen: dict[int, float] = {}
    for mask in range(8):
        exits = [(mask >> bit) & 1 for bit in range(3)]
        score = receipt_to_score(make_receipt(*exits))  # type: ignore[arg-type]
        passes = 3 - sum(exits)
        seen.setdefault(passes, score.normalized_reward)
        assert score.normalized_reward == seen[passes]
    assert [seen[k] for k in range(4)] == sorted(seen[k] for k in range(4))
    assert set(seen.values()) == {0.0, 0.25, 0.5, 1.0}


def test_hard_gate_vocabulary_exact_and_ordered() -> None:
    score = receipt_to_score(make_receipt())
    assert tuple(score.hard_gates) == HARD_GATE_KEYS
    assert score.hard_gates == {
        "verifier_passed": True,
        "stc_ruff": True,
        "stc_mypy": True,
        "stc_pytest": True,
    }


@pytest.mark.parametrize(
    "mutmut,status",
    [
        (make_gate(0, 0.0, "DEFERRED: champion-only per ADR-INT-01"), "deferred"),
        (make_gate(0, 1.5, "2.9% coverage"), "passed"),
        (make_gate(1, 3.0, "mutations survived"), "failed"),
        (make_gate(0, 0.0, "suspicious zero run"), "passed"),
    ],
)
def test_mutmut_never_counted(mutmut: GateReport, status: str) -> None:
    """Deferred (or even real) mutmut never enters the fraction (F2a)."""
    score = receipt_to_score(make_receipt(mutmut=mutmut))
    assert "mutmut" not in "".join(score.hard_gates)
    assert len(score.hard_gates) == 4
    assert score.normalized_reward == 1.0
    assert score.raw_metrics["mutmut_status"] == status


def test_mutmut_failure_does_not_tank_per_node_reward() -> None:
    score = receipt_to_score(make_receipt(0, 0, 0, make_gate(1, 9.9, "mutants survived")))
    assert score.normalized_reward == 1.0
    assert score.passed_hard_gates is True


# --- Proposal to file targets (Tables 4/4b) ---

DIFF_MODIFY = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1,1 +1,1 @@
-x
+y
"""

DIFF_CREATE = """--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+print(1)
"""

DIFF_DELETE = """--- a/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-gone
"""


def test_hunks_primary_create_modify_delete() -> None:
    targets = proposal_to_filetargets(make_proposal(patch_diff=DIFF_MODIFY))
    assert [(t.path, t.action) for t in targets] == [("src/a.py", "modify")]
    targets = proposal_to_filetargets(make_proposal(patch_diff=DIFF_CREATE))
    assert [(t.path, t.action) for t in targets] == [("new.py", "create")]
    targets = proposal_to_filetargets(make_proposal(patch_diff=DIFF_DELETE))
    assert [(t.path, t.action) for t in targets] == [("gone.py", "delete")]


def test_hunks_preserve_order_and_defaults() -> None:
    targets = proposal_to_filetargets(make_proposal(patch_diff=DIFF_MODIFY + DIFF_CREATE))
    assert [t.path for t in targets] == ["src/a.py", "new.py"]
    for target in targets:
        assert target.expected_symbols == []
        assert target.start_line is None and target.start_byte is None


def test_ops_only_source_when_no_hunks() -> None:
    proposal = make_proposal(
        file_operations=[
            {"op": "create", "path": "n.py"},
            {"op": "delete", "path": "o.py", "note": "extra keys ignored"},
        ]
    )
    targets = proposal_to_filetargets(proposal)
    assert [(t.path, t.action) for t in targets] == [("n.py", "create"), ("o.py", "delete")]


def test_empty_proposal_yields_no_targets() -> None:
    assert proposal_to_filetargets(make_proposal()) == []


@pytest.mark.parametrize(
    "ops,match",
    [
        ([{"op": "rename", "path": "a"}], "unknown op 'rename'"),
        ([{"op": "move", "path": "a"}], "unknown op 'move'"),
        ([{"op": "CREATE", "path": "a"}], "unknown op 'CREATE'"),
        ([{"path": "a"}], "unknown op None"),
        ([{"op": "modify"}], "path.*missing or blank"),
        ([{"op": "modify", "path": "  "}], "path.*missing or blank"),
    ],
)
def test_unknown_or_malformed_ops_raise(ops: list[dict[str, Any]], match: str) -> None:
    with pytest.raises(UndisposedFieldError, match=match):
        proposal_to_filetargets(make_proposal(file_operations=ops))


def test_op_outside_hunks_raises() -> None:
    proposal = make_proposal(
        patch_diff=DIFF_MODIFY, file_operations=[{"op": "modify", "path": "rogue.py"}]
    )
    with pytest.raises(UndisposedFieldError, match="not in patch_diff hunks"):
        proposal_to_filetargets(proposal)


def test_op_conflicting_with_hunk_raises() -> None:
    proposal = make_proposal(
        patch_diff=DIFF_MODIFY, file_operations=[{"op": "delete", "path": "src/a.py"}]
    )
    with pytest.raises(UndisposedFieldError, match="conflicts with hunk action"):
        proposal_to_filetargets(proposal)


def test_op_agreeing_with_hunk_ok() -> None:
    proposal = make_proposal(
        patch_diff=DIFF_MODIFY, file_operations=[{"op": "modify", "path": "src/a.py"}]
    )
    assert [t.path for t in proposal_to_filetargets(proposal)] == ["src/a.py"]


def test_target_paths_breach_raises() -> None:
    proposal = make_proposal(patch_diff=DIFF_MODIFY, target_paths=["other.py"])
    with pytest.raises(UndisposedFieldError, match="undeclared path"):
        proposal_to_filetargets(proposal)


def test_target_paths_declared_untouched_allowed() -> None:
    proposal = make_proposal(patch_diff=DIFF_MODIFY, target_paths=["src/a.py", "planned.py"])
    assert [t.path for t in proposal_to_filetargets(proposal)] == ["src/a.py"]


@pytest.mark.parametrize(
    "diff,match",
    [
        ("+++ b/lone.py\n", "without '---' pair"),
        ("--- a/x.py\nno follower\n", r"without '\+\+\+' pair"),
        ("--- a/x.py", r"without '\+\+\+' pair"),
        ('--- "a/sp ace.py"\n+++ "b/sp ace.py"\n', "quoted paths"),
        ("--- \n+++ b/x.py\n", "empty path"),
        ("--- /dev/null\n+++ /dev/null\n", "null header pair"),
    ],
)
def test_malformed_diffs_raise(diff: str, match: str) -> None:
    with pytest.raises(UndisposedFieldError, match=match):
        proposal_to_filetargets(make_proposal(patch_diff=diff))


def test_duplicate_same_action_dedupes() -> None:
    targets = proposal_to_filetargets(make_proposal(patch_diff=DIFF_MODIFY + DIFF_MODIFY))
    assert [(t.path, t.action) for t in targets] == [("src/a.py", "modify")]


def test_duplicate_conflicting_action_raises() -> None:
    clash = DIFF_MODIFY + "--- a/src/a.py\n+++ /dev/null\n"
    with pytest.raises(UndisposedFieldError, match="conflicting actions"):
        proposal_to_filetargets(make_proposal(patch_diff=clash))


# --- A4-D1: first-error signals for the prune hint ---


def _receipt_with_snippets(ruff: str, mypy: str, pytest_snip: str) -> ExecutionReceipt:
    base = make_receipt(1, 1, 1)
    return base.model_copy(
        update={
            "gate_ruff": make_gate(1, 1.0, ruff),
            "gate_mypy": make_gate(1, 1.0, mypy),
            "gate_pytest": make_gate(1, 1.0, pytest_snip),
        }
    )


def test_first_signals_carry_file_line_evidence() -> None:
    """Each failed gate contributes its first file:line-shaped error."""
    receipt = _receipt_with_snippets(
        "tests/unit/test_x.py:64:101: E501 Line too long (126 > 100 characters)\nFound 1 error",
        "tests/unit/test_x.py:30: error: Function is missing a type annotation  [no-untyped-def]",
        "FAILED tests/unit/test_x.py::test_a - AttributeError: boom\n3 failed, 1 passed",
    )
    score = receipt_to_score(receipt)
    signals = score.raw_metrics["first_signals"]
    assert signals[0].startswith("ruff tests/unit/test_x.py:64:101: E501")
    assert signals[1].startswith("mypy tests/unit/test_x.py:30: error:")
    assert signals[2].startswith("pytest FAILED tests/unit/test_x.py::test_a")
    assert all(len(item) <= 5 + 64 for item in signals)


def test_first_signals_degrade_timeout_unknown_and_pass() -> None:
    """Timeouts, unknown shapes, and passing gates degrade without raising."""
    receipt = _receipt_with_snippets("Gate timed out", "weird blob", "ok")
    score = receipt_to_score(receipt)
    signals = score.raw_metrics["first_signals"]
    assert signals[0] == "ruff timeout"
    assert signals[1] == "mypy weird blob"
    assert signals[2] == "pytest ok"
    passing = receipt_to_score(make_receipt(0, 0, 0))
    assert passing.raw_metrics["first_signals"] == []


def test_first_signals_skip_passing_gates() -> None:
    """Signals cover exactly the failed gates, in ruff/mypy/pytest order."""
    receipt = make_receipt(0, 1, 0)
    receipt = receipt.model_copy(
        update={"gate_mypy": make_gate(1, 1.0, "src/a.py:3: error: boom  [x]")}
    )
    score = receipt_to_score(receipt)
    assert score.raw_metrics["first_signals"] == ["mypy src/a.py:3: error: boom [x]"]


# --- Runner-disclosed mutmut non-measurements read deferred ---


@pytest.mark.parametrize(
    "snippet",
    [
        "Mutmut Gate disabled by runner configuration.",
        ("Mutmut Gate deferred per 01_INVARIANTS.md §3.3 (Cross-OS Execution Neutrality)."),
        "Mutmut Gate skipped under active mutation test runner.",
    ],
)
def test_mutmut_runner_disclosures_are_deferred(snippet: str) -> None:
    """Exit-0 runner disclosures never masquerade as a measured pass."""
    score = receipt_to_score(make_receipt(mutmut=make_gate(0, 0.0, snippet)))
    assert score.raw_metrics["mutmut_status"] == "deferred"
    assert score.normalized_reward == 1.0
