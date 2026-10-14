"""Unit tests for the operator-authorized executable harness.

Deterministic: tiny shell executables under tmp_path; a stub HarnessResult
stands in for the prompt-kit pin (duck-typed: content/exit_code/error).
"""

from __future__ import annotations

import os
import stat
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
# Deliberate pin roots first (STC_*_ROOT), sibling checkouts as fallback.
# APPENDED, never prepended: collection-time insertion at sys.path[0] would
# shadow the authoritative pins for the whole suite process and poison
# pin-identity proofs (F3c, lease import-integrity) with sibling bytes.
_sst_root = os.environ.get("STC_SST_ROOT", "").strip()
_pk_root = os.environ.get("STC_PROMPT_KIT_ROOT", "").strip()
for _pins in (
    Path(_sst_root) / "src" if _sst_root else _REPO.parent / "sst" / "src",
    Path(_pk_root) if _pk_root else _REPO.parent / "prompt-kit",
):
    if str(_pins) not in sys.path:
        sys.path.append(str(_pins))
pytest.importorskip("sst", reason="sst/prompt-kit pin roots required")

from stc.integration.cli_gateway import CLIGatewayBackend  # noqa: E402
from stc.integration.exec_harness import TIMEOUT_EXIT_CODE, ExecHarness  # noqa: E402
from stc.integration.harness_worker import HarnessConfigError  # noqa: E402


@dataclass
class _StubResult:
    content: str = ""
    exit_code: int = 0
    error: str | None = None
    raw_response: Any = None

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0


@pytest.fixture
def stub_harness_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve a stub HarnessResult for exec_harness's lazy prompt-kit import."""
    base = types.ModuleType("prompt_kit.harnesses.base")
    base.HarnessResult = _StubResult  # type: ignore[attr-defined]
    harnesses = types.ModuleType("prompt_kit.harnesses")
    harnesses.base = base  # type: ignore[attr-defined]
    kit = types.ModuleType("prompt_kit")
    kit.harnesses = harnesses  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "prompt_kit", kit)
    monkeypatch.setitem(sys.modules, "prompt_kit.harnesses", harnesses)
    monkeypatch.setitem(sys.modules, "prompt_kit.harnesses.base", base)


def _mk_exe(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_relative_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(HarnessConfigError, match="absolute"):
        ExecHarness(Path("relative/exe"))


def test_missing_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(HarnessConfigError, match="not a file"):
        ExecHarness(tmp_path / "nope")


def test_non_executable_rejected(tmp_path: Path) -> None:
    target = tmp_path / "plain.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(HarnessConfigError, match="not executable"):
        ExecHarness(target)


def test_non_positive_timeout_rejected(tmp_path: Path) -> None:
    exe = _mk_exe(tmp_path / "h.sh", "cat\n")
    with pytest.raises(HarnessConfigError, match="timeout"):
        ExecHarness(exe, timeout=0)


def test_execute_pipes_prompt_and_role(tmp_path: Path, stub_harness_result: None) -> None:
    _ = stub_harness_result
    exe = _mk_exe(
        tmp_path / "h.sh",
        'echo "ROLE=$STC_HARNESS_ROLE CWD=$PWD"; cat\n',
    )
    harness = ExecHarness(exe, timeout=30.0)
    result = harness.execute(
        "hello-prompt", role="diverge", context={"project_root": str(tmp_path)}
    )
    assert result.exit_code == 0
    assert "ROLE=diverge" in result.content
    assert f"CWD={tmp_path}" in result.content
    assert "hello-prompt" in result.content


def test_execute_failure_preserves_content_and_error(
    tmp_path: Path, stub_harness_result: None
) -> None:
    _ = stub_harness_result
    exe = _mk_exe(tmp_path / "h.sh", 'echo "partial-out"; echo "boom-err" >&2; exit 3\n')
    harness = ExecHarness(exe, timeout=30.0)
    result = harness.execute("p", context={"project_root": str(tmp_path)})
    assert result.exit_code == 3
    assert "partial-out" in result.content
    assert result.error == "boom-err"


def test_execute_undecodable_output_is_failure_result(
    tmp_path: Path, stub_harness_result: None
) -> None:
    _ = stub_harness_result
    exe = _mk_exe(tmp_path / "h.sh", 'printf "\\377\\376"\n')
    harness = ExecHarness(exe, timeout=30.0)
    result = harness.execute("p", context={"project_root": str(tmp_path)})
    assert result.exit_code == 1
    assert "UTF-8" in (result.error or "")


def test_execute_timeout_maps_to_124(tmp_path: Path, stub_harness_result: None) -> None:
    _ = stub_harness_result
    exe = _mk_exe(tmp_path / "h.sh", "sleep 30\n")
    harness = ExecHarness(exe, timeout=0.2)
    result = harness.execute("p", context={"project_root": str(tmp_path)})
    assert result.exit_code == TIMEOUT_EXIT_CODE
    assert result.exit_code == 124
    assert "timed out" in (result.error or "")


def test_exec_harness_passes_f11_shape_gate(tmp_path: Path) -> None:
    """No template attributes; the gateway constructor accepts it (F11)."""
    exe = _mk_exe(tmp_path / "h.sh", "cat\n")
    harness = ExecHarness(exe)
    assert not hasattr(harness, "command_template")
    assert type(harness).__name__ != "CommandHarness"
    backend = CLIGatewayBackend(
        "mock",
        project_root=tmp_path,
        harness=harness,
        task_label="exec:h.sh",
    )
    assert backend.harness_name == "mock"


def test_cli_rejects_bad_exec_flag(tmp_path: Path) -> None:
    """The --exec-harness flag fails fast on bad paths (UsageError, exit 2)."""
    from click.testing import CliRunner

    from stc.cli import main

    runner = CliRunner()
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n\nA sufficiently long goal statement.\n", encoding="utf-8")
    env = {"STC_DOSSIER_DIR": str(tmp_path / "dossier")}
    res = runner.invoke(
        main,
        ["run", str(spec), "--target", "stc", "--choice", "1", "--exec-harness", "relative/exe"],
        env=env,
    )
    assert res.exit_code == 2
    assert "absolute" in res.output
    res = runner.invoke(
        main,
        [
            "run",
            str(spec),
            "--target",
            "stc",
            "--choice",
            "1",
            "--exec-harness",
            str(tmp_path / "nope"),
        ],
        env=env,
    )
    assert res.exit_code == 2
    assert "not a file" in res.output
    res = runner.invoke(
        main,
        ["run", str(spec), "--target", "stc", "--manual", "--exec-harness", str(spec)],
        env=env,
    )
    assert res.exit_code == 2
    assert "mutually exclusive" in res.output
    res = runner.invoke(
        main,
        ["run", str(spec), "--target", "stc", "--dry-run", "--exec-harness", str(spec)],
        env=env,
    )
    assert res.exit_code == 2
    assert "mutually exclusive" in res.output
    res = runner.invoke(
        main,
        ["run", str(spec), "--target", "stc", "--choice", "1", "--exec-harness", str(spec)],
        env=env,
    )
    assert res.exit_code == 2
    assert "not executable" in res.output
