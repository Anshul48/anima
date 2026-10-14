"""E1 behavioral check: safeguard selection survives the production call path.

Drives ``SubstrateRunner.execute_gates`` through the production call
shapes (per-node ``run_mutmut=False`` + merge ``run_mutmut=<bool>``) and
asserts the OBSERVED mutmut behavior matches the declaration. Behavioral
assertions on gate execution only — never AST assertions.

Precedence invariant under test (section 5.2): the ``runner.py`` trap
takes effect ONLY without an explicit ``run_mutmut`` kwarg; both
evaluation-path production call sites pass explicit bools, so coverage
is decided by the call sites, never by the trap.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from stc.schemas.models import GateReport
from stc.substrate.runner import SubstrateRunner


def _passing_gate(name: str) -> GateReport:
    return GateReport(
        gate_name=name,
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="ok",
    )


@pytest.fixture
def observed_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[SubstrateRunner, dict[str, Any]]:
    """Real runner with gate execution observed (subprocesses stubbed)."""
    runner = SubstrateRunner()
    seen: dict[str, Any] = {}

    def fake_ruff(worktree_path: Path) -> GateReport:
        seen["ruff_cwd"] = str(worktree_path)
        return _passing_gate("ruff")

    def fake_mypy(worktree_path: Path) -> GateReport:
        seen["mypy_cwd"] = str(worktree_path)
        return _passing_gate("mypy")

    def fake_pytest(worktree_path: Path, pytest_target: str | None = None) -> GateReport:
        seen["pytest_target"] = pytest_target
        return _passing_gate("pytest")

    def fake_mutmut(
        worktree_path: Path,
        run_mutmut: bool = True,
        defer_windows: bool = True,
        paths_to_mutate: list[str] | None = None,
    ) -> GateReport:
        seen["mutmut_run"] = run_mutmut
        seen["mutmut_defer"] = defer_windows
        seen["mutmut_paths"] = paths_to_mutate
        if not run_mutmut:
            return GateReport(
                gate_name="mutmut",
                exit_code=0,
                duration_seconds=0.0,
                violations_count=0,
                raw_output_snippet="Mutmut Gate disabled by runner configuration.",
            )
        return _passing_gate("mutmut")

    monkeypatch.setattr(runner, "_run_gate_ruff", fake_ruff)
    monkeypatch.setattr(runner, "_run_gate_mypy", fake_mypy)
    monkeypatch.setattr(runner, "_run_gate_pytest", fake_pytest)
    monkeypatch.setattr(runner, "_run_gate_mutmut", fake_mutmut)
    monkeypatch.setattr(runner, "_resolve_commit_hash", lambda path: "abc123")
    return runner, seen


def test_per_node_shape_disables_mutmut(
    observed_runner: tuple[SubstrateRunner, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-node production shape: explicit False wins, declaration matches."""
    runner, seen = observed_runner
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_per_node_shape (call)")
    receipt = runner.execute_gates(tmp_path, task_id="T", epoch_index=1, run_mutmut=False)
    assert seen["mutmut_run"] is False
    assert "disabled by runner configuration" in receipt.gate_mutmut.raw_output_snippet
    assert seen["pytest_target"] is None or isinstance(seen["pytest_target"], str)


def test_per_node_scoped_shape_disables_mutmut(
    observed_runner: tuple[SubstrateRunner, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scoped per-node shape: target + PYTEST_CURRENT_TEST still explicit-False."""
    runner, seen = observed_runner
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_scoped (call)")
    receipt = runner.execute_gates(
        tmp_path,
        task_id="T",
        epoch_index=1,
        pytest_target="tests/unit/test_config.py",
        run_mutmut=False,
    )
    assert seen["mutmut_run"] is False
    assert seen["pytest_target"] == "tests/unit/test_config.py"
    assert receipt.gate_pytest.exit_code == 0


def test_explicit_true_beats_trap(
    observed_runner: tuple[SubstrateRunner, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Precedence: explicit True wins over trap conditions (target + env)."""
    runner, seen = observed_runner
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_precedence (call)")
    receipt = runner.execute_gates(
        tmp_path,
        task_id="T",
        epoch_index=1,
        pytest_target="tests/unit/test_config.py",
        run_mutmut=True,
    )
    assert seen["mutmut_run"] is True
    assert "disabled by runner configuration" not in receipt.gate_mutmut.raw_output_snippet


def test_trap_arms_without_explicit_kwarg(
    observed_runner: tuple[SubstrateRunner, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trap behavior pinned: no kwarg + target + env => mutmut off."""
    runner, seen = observed_runner
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_trap (call)")
    runner.execute_gates(
        tmp_path, task_id="T", epoch_index=1, pytest_target="tests/unit/test_config.py"
    )
    assert seen["mutmut_run"] is False


def test_merge_shape_enables_mutmut(
    observed_runner: tuple[SubstrateRunner, dict[str, Any]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merge production shape: explicit True, no target => mutmut runs."""
    runner, seen = observed_runner
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    receipt = runner.execute_gates(
        tmp_path, task_id="T", epoch_index=1, causation_id="tree", run_mutmut=True
    )
    assert seen["mutmut_run"] is True
    assert seen["pytest_target"] is None
    assert receipt.is_passing is True


def test_pytest_current_test_present_in_gate_env() -> None:
    """Sanity: gate runs execute under PYTEST_CURRENT_TEST (trap can arm)."""
    assert os.environ.get("PYTEST_CURRENT_TEST"), "expected to run under pytest"
