"""External-target test selection (section 5.2, non-STC construction targets).

STC's mandatory IDs (``tests/unit/...``) name files that do not exist in a
foreign lease tree (e.g. csvledger): emitting them as the lease pytest gate
fails every candidate red regardless of quality (run-1i evidence: two
candidates green on honest reproduction -- ruff + format + mypy-strict +
44/44 pytest -- scored ``FAIL stc_pytest`` because the gate ran STC's test
IDs inside the csvledger lease). In external mode selection still VERIFIES
the mandatory set against the STC tree (provenance + tripwire) but scopes
the lease gate to the TARGET tree's full suite. Behavioral: real
``run_selection`` against fixture trees plus one full
``verify_candidate_proposal`` drive asserting the substrate-observed target.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from sst.core.contracts import CandidateProposal, TaskPacket
from sst.sandbox.custody import CandidateCustodyManager

from stc.integration.dialectic_runner import STCCustodyWrapper
from stc.integration.selection import (
    _default_selection_root,
    load_selection_config,
    run_selection,
)
from stc.schemas.models import ExecutionReceipt, GateReport

MOD_CODE = 'def add(a: int, b: int) -> int:\n    """Target module."""\n    return a + b\n'
TEST_CODE = "from mod import add\n\n\ndef test_add() -> None:\n    assert add(1, 2) == 3\n"


def _target_tree(tmp_path: Path, name: str = "target", *, with_tests: bool = True) -> Path:
    root = tmp_path / name
    (root / "tests").mkdir(parents=True)
    (root / "mod.py").write_text(MOD_CODE, encoding="utf-8")
    (root / "tests" / "test_mod.py").write_text(TEST_CODE, encoding="utf-8")
    if not with_tests:
        (root / "tests" / "test_mod.py").unlink()
        (root / "tests").rmdir()
    return root


def _mandatory_ids() -> list[str]:
    cfg = load_selection_config()
    return (
        list(cfg["m1_env_identity_pin"])
        + list(cfg["m2_lease_import_integrity"])
        + [str(entry["path"]) for entry in cfg["m3_custody_shape_pins"]]
    )


def test_external_target_with_tests_dir_scopes_to_target_suite(tmp_path: Path) -> None:
    target = _target_tree(tmp_path)
    result, verification = run_selection(["mod.py"], [], [], target_root=target)
    assert result.pytest_target == "tests"
    assert "tests/unit" not in result.pytest_target
    # Provenance still bound: mandatory verified against the STC tree.
    assert verification["mandatory_digest"]
    assert verification["config_revision"] == "sel-1"
    # Naming rule: every skipped mandatory ID recorded with a reason.
    skipped = {item["test"] for item in result.unrun_with_reasons}
    assert set(_mandatory_ids()) <= skipped
    assert all("external target" in item["reason"] for item in result.unrun_with_reasons)


def test_external_target_without_tests_dir_floors_whole_tree(tmp_path: Path) -> None:
    target = _target_tree(tmp_path, with_tests=False)
    result, _ = run_selection(["mod.py"], [], [], target_root=target)
    assert result.pytest_target == "."


def test_external_target_convention_maps_target_tests(tmp_path: Path) -> None:
    target = _target_tree(tmp_path)
    result, _ = run_selection(["tests/test_mod.py"], [], [], target_root=target)
    assert result.affected == ["tests/test_mod.py"]
    # Already covered by the floor: recorded, not duplicated as a target.
    assert result.pytest_target == "tests"


def test_external_target_keeps_suggested_tests_additive(tmp_path: Path) -> None:
    target = _target_tree(tmp_path)
    result, _ = run_selection(["mod.py"], [], ["tests/test_mod.py"], target_root=target)
    assert result.pytest_target.split() == ["tests", "tests/test_mod.py"]
    assert result.suggested == ["tests/test_mod.py"]


def test_stc_target_keeps_mandatory_set() -> None:
    stc_root = _default_selection_root()
    result, _ = run_selection(["src/stc/cli.py"], [], [], target_root=stc_root)
    for mid in _mandatory_ids():
        assert mid in result.pytest_target.split()


def test_unset_target_root_preserves_legacy_behavior() -> None:
    result, _ = run_selection(["src/stc/cli.py"], [], [])
    for mid in _mandatory_ids():
        assert mid in result.pytest_target.split()


def test_empty_target_root_treated_as_unset() -> None:
    result, _ = run_selection(["src/stc/cli.py"], [], [], target_root="")
    for mid in _mandatory_ids():
        assert mid in result.pytest_target.split()


def _gate(name: str) -> GateReport:
    return GateReport(
        gate_name=name,
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="ok",
    )


def _passing_receipt(task_id: str) -> ExecutionReceipt:
    return ExecutionReceipt(
        receipt_id="rc-test",
        task_id=task_id,
        epoch_index=1,
        commit_hash="abc",
        timestamp_utc="2026-10-06T00:00:00Z",
        python_version="3.12",
        os_platform="linux",
        gate_ruff=_gate("ruff"),
        gate_mypy=_gate("mypy"),
        gate_pytest=_gate("pytest"),
        gate_mutmut=_gate("mutmut"),
        sha256_signature="test-signature",
    )


class _RecordingSubstrate:
    """Minimal substrate: records gate calls, always passes."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_gates(
        self,
        worktree_path: Path,
        task_id: str,
        epoch_index: int = 1,
        pytest_target: str | None = None,
        **kwargs: Any,
    ) -> ExecutionReceipt:
        self.calls.append({"pytest_target": pytest_target, **kwargs})
        return _passing_receipt(task_id)

    def verify_receipt(self, receipt: ExecutionReceipt) -> bool:
        _ = receipt
        return True


def _git_commit(tree: Path) -> None:
    subprocess.run(["git", "-C", str(tree), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tree), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tree),
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


def test_external_drive_scopes_substrate_pytest_to_target_suite(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git required for lease setup")
    target = _target_tree(tmp_path)
    _git_commit(target)
    substrate: Any = _RecordingSubstrate()
    wrapper = STCCustodyWrapper(
        CandidateCustodyManager(base_worktree_dir=tmp_path / "custody"),
        substrate,
        leases_root=tmp_path / "leases",
    )
    packet = TaskPacket(
        task_id="TEXT-1",
        goal="test goal",
        source_repo_root=str(target),
        base_commit="abc",
        snapshot_hash="snap",
        allowed_paths=["mod.py"],
        forbidden_paths=[],
        acceptance_commands=["true"],
        evidence_references={"stc.epoch_index": "1"},
    )
    proposal = CandidateProposal(
        candidate_id="cand-ext-1",
        tree_id="tree-1",
        role="DIVERGE",
        title="external proposal",
        rationale="test",
        target_paths=["mod.py"],
        patch_diff=MOD_CODE,
        file_operations=[],
    )
    result = wrapper.verify_candidate_proposal(packet, proposal, target)
    assert result.passed
    assert len(substrate.calls) == 1
    assert substrate.calls[0]["pytest_target"] == "tests"
