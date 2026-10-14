"""E2E tests for `stc run --target stc` (P05).

Dry-run tests run under ANY interpreter: the --dry-run path builds
spec→TOC→bundle→packet, prints packets+budgets, and asserts the default
auditor is with_codex=False — with tripwires proving zero model calls
(ModelGateway.invoke + BaseHarness.execute wraps, RT-08). The manual test
drives the REAL DialecticRunner with clipboard-fixture payloads and real
substrate gates, so it needs gate tools (requires_gate_tools, 3.11) per the
P04 precedent. No test in this file is marked live (D13).

Fixture tree + module contents mirror tests/integration/test_dialectic_fixture.py
(BASE_MOD/TEST_MOD/GOOD_MOD are gate-proven there); the unified-diff helper
follows the same custody exact-patch shape.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from sst.core.models import DeterministicGateResult

from stc.cli import main
from stc.integration import dialectic_runner as runner_mod

BASE_MOD = 'def add(a: int, b: int) -> int:\n    """Add two integers."""\n    return a + b\n'

TEST_MOD = "from mod import add\n\n\ndef test_add() -> None:\n    assert add(1, 2) == 3\n"

GOOD_MOD = (
    'def add(a: int, b: int) -> int:\n    """Good branch implementation."""\n    return a + b\n'
)

# Five-dimension spec scoring below TAU (every dimension non-empty, no error
# keywords, no opposing-pattern pairs). The quoted `mod.py` becomes the packet
# target; must/never lines feed invariants/inhibitors extraction.
LOW_TAU_SPEC = """# Keep the adder correct

## Domain rules

- The `mod.py` adder must return a + b for all integer inputs.
- The change must touch only `mod.py` and keep its public signature.

## Storage tables

- No stored state is involved; the adder is a pure function of its inputs.

## Protocol interfaces

- Callers use the `add(a, b)` interface with two integer arguments.

## Security tokens

- Never log secrets; the adder handles plain integers only.

## Recovery plan

- If a candidate breaks the suite, the loop prunes it and keeps prior code.
"""

HIGH_TAU_SPEC = """# Vague adder wish

## Domain rules

- Make `mod.py` nicer somehow.
"""

BUDGET_TIGHT = "time=600,tokens=500000,usd=10,iters=1,branching=1,depth=4"


def _probe(executable: str, *args: str) -> bool:
    try:
        proc = subprocess.run([executable, *args], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _gate_tools_available() -> bool:
    return (
        _probe(sys.executable, "-m", "ruff", "--version")
        and _probe(sys.executable, "-m", "mypy", "--version")
        and shutil.which("git") is not None
    )


GATE_TOOLS = _gate_tools_available()

requires_gate_tools = pytest.mark.skipif(
    not GATE_TOOLS, reason="manual e2e needs ruff+mypy modules and git"
)


def _git_source(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text(BASE_MOD, encoding="utf-8")
    (src / "test_mod.py").write_text(TEST_MOD, encoding="utf-8")
    # Mutmut config (P04 once-test precedent): without it the native mutmut
    # gate cannot guess source paths (F-C-2) and fails the champion receipt.
    (src / "pyproject.toml").write_text(
        '[tool.mutmut]\npaths_to_mutate = ["mod.py"]\ntests_dir = ["."]\nrunner = "pytest"\n',
        encoding="utf-8",
    )
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


def _full_diff(new_text: str) -> str:
    old_lines = BASE_MOD.splitlines()
    new_lines = new_text.splitlines()
    out = [
        "--- a/mod.py",
        "+++ b/mod.py",
        f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@",
    ]
    out.extend(f"-{line}" for line in old_lines)
    out.extend(f"+{line}" for line in new_lines)
    return "\n".join(out) + "\n"


def _write_spec(tmp_path: Path, name: str, body: str) -> Path:
    spec = tmp_path / name
    spec.write_text(body, encoding="utf-8")
    return spec


def _arm_zero_call_tripwires(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """Counts ModelGateway.invoke + BaseHarness.execute + gate calls (must stay 0)."""
    from prompt_kit.harnesses.base import BaseHarness
    from sst.gateway.gateway import ModelGateway

    from stc.substrate.runner import SubstrateRunner

    calls: dict[str, list[str]] = {"invoke": [], "execute": [], "gates": []}

    def _no_invoke(self: Any, request: Any) -> Any:
        calls["invoke"].append(str(getattr(request, "role", "?")))
        raise AssertionError("ModelGateway.invoke called during dry-run")

    def _no_execute(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["execute"].append(str(kwargs.get("role", "?")))
        raise AssertionError("BaseHarness.execute called during dry-run")

    def _no_gates(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["gates"].append("execute_gates")
        raise AssertionError("SubstrateRunner.execute_gates called during dry-run")

    monkeypatch.setattr(ModelGateway, "invoke", _no_invoke)
    monkeypatch.setattr(BaseHarness, "execute", _no_execute)
    monkeypatch.setattr(SubstrateRunner, "execute_gates", _no_gates)
    return calls


def test_dry_run_zero_model_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--dry-run prints packets+budgets with a composite zero-model-call proof."""
    src = _git_source(tmp_path)
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    dossier_dir = tmp_path / "dossier"
    monkeypatch.setenv("STC_SOURCE_ROOT", str(src))
    monkeypatch.setenv("STC_DOSSIER_DIR", str(dossier_dir))
    calls = _arm_zero_call_tripwires(monkeypatch)

    res = CliRunner().invoke(
        main,
        ["run", str(spec), "--target", "stc", "--dry-run", "--budget", BUDGET_TIGHT],
    )
    assert res.exit_code == 0, res.output
    assert calls == {"invoke": [], "execute": [], "gates": []}
    assert "0 model calls" in res.output
    assert "with_codex=False" in res.output
    assert "mod.py" in res.output
    qa = json.loads((dossier_dir / "qa_log.json").read_text(encoding="utf-8"))
    assert qa["triggered"] is False
    assert qa["ambiguity_score"] < 0.30
    assert qa["status"] == "below-tau"


def test_dry_run_packet_carries_gate_discipline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run packet states the enforcing lint/type/test contract (A4-D1b)."""
    src = _git_source(tmp_path)
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    dossier_dir = tmp_path / "dossier"
    monkeypatch.setenv("STC_SOURCE_ROOT", str(src))
    monkeypatch.setenv("STC_DOSSIER_DIR", str(dossier_dir))
    calls = _arm_zero_call_tripwires(monkeypatch)

    res = CliRunner().invoke(main, ["--json", "run", str(spec), "--target", "stc", "--dry-run"])
    assert res.exit_code == 0, res.output
    assert calls == {"invoke": [], "execute": [], "gates": []}
    payload = json.loads(res.output)
    assert payload["status"] == "dry-run"
    assert payload["model_calls"] == 0
    joined = "\n".join(payload["packet"]["invariants"])
    assert "Gate discipline (ruff)" in joined
    assert "Gate discipline (mypy)" in joined
    assert "Gate discipline (pytest)" in joined


def test_dry_run_packet_carries_judiciary_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run packet states the judiciary-enforced diff rules (Fix 3)."""
    src = _git_source(tmp_path)
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    dossier_dir = tmp_path / "dossier"
    monkeypatch.setenv("STC_SOURCE_ROOT", str(src))
    monkeypatch.setenv("STC_DOSSIER_DIR", str(dossier_dir))
    calls = _arm_zero_call_tripwires(monkeypatch)

    res = CliRunner().invoke(main, ["--json", "run", str(spec), "--target", "stc", "--dry-run"])
    assert res.exit_code == 0, res.output
    assert calls == {"invoke": [], "execute": [], "gates": []}
    payload = json.loads(res.output)
    joined = "\n".join(payload["packet"]["invariants"])
    assert "Judiciary constraint (zero-mock" in joined
    assert "Hand-rolled fakes" in joined
    assert "Judiciary constraint (fail-closed fallbacks)" in joined
    assert "Judiciary constraint (no hardcoded secrets)" in joined
    assert "Judiciary constraint (immutable contracts)" in joined


def test_dry_run_escalation_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A >=tau dry-run stops pre-model with the escalation record (exit 2)."""
    src = _git_source(tmp_path)
    spec = _write_spec(tmp_path, "high_tau.md", HIGH_TAU_SPEC)
    dossier_dir = tmp_path / "dossier"
    monkeypatch.setenv("STC_SOURCE_ROOT", str(src))
    monkeypatch.setenv("STC_DOSSIER_DIR", str(dossier_dir))
    calls = _arm_zero_call_tripwires(monkeypatch)

    res = CliRunner().invoke(main, ["run", str(spec), "--target", "stc", "--dry-run"])
    assert res.exit_code == 2, res.output
    assert calls == {"invoke": [], "execute": [], "gates": []}
    assert "OPERATOR DECISION REQUIRED" in res.output
    qa = json.loads((dossier_dir / "qa_log.json").read_text(encoding="utf-8"))
    assert qa["triggered"] is True
    assert qa["status"] == "escalation-required"
    assert qa["ambiguity_score"] >= 0.30
    assert len(qa["diffs"]) == 1


def test_stc_flags_require_target(tmp_path: Path) -> None:
    """New flags without --target stc are a usage error (never silent)."""
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    res = CliRunner().invoke(main, ["run", str(spec), "--dry-run"])
    assert res.exit_code == 2
    assert "require --target stc" in res.output


def test_budget_validation(tmp_path: Path) -> None:
    """Malformed --budget is a usage error naming the expected shape."""
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    res = CliRunner().invoke(
        main, ["run", str(spec), "--target", "stc", "--dry-run", "--budget", "bogus"]
    )
    assert res.exit_code == 2
    assert "Invalid --budget" in res.output


@requires_gate_tools
def test_manual_mode_completes_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--manual completes the loop on clipboard-fixture payloads (no models)."""
    import stc.integration.harness_worker as worker_mod

    src = _git_source(tmp_path)
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    dossier_dir = tmp_path / "dossier"
    payloads = tmp_path / "payloads"
    payloads.mkdir()
    (payloads / "01-diverge.json").write_text(
        json.dumps(
            {
                "branches": [
                    {
                        "strategy_title": "Good branch",
                        "hypothesis_or_rationale": "Keep add correct.",
                        "proposed_changes": _full_diff(GOOD_MOD),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (payloads / "02-critique.json").write_text(
        json.dumps(
            {
                "value_score": 0.9,
                "verdict": "APPROVE",
                "rationale": "Fixture critique: the good branch keeps add correct.",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("STC_SOURCE_ROOT", str(src))
    monkeypatch.setenv("STC_DOSSIER_DIR", str(dossier_dir))
    monkeypatch.setenv("STC_MANUAL_FIXTURE_DIR", str(payloads))

    def _no_native(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("native CLI-model command built in manual mode")

    monkeypatch.setattr(worker_mod, "build_native_command", _no_native)

    res = CliRunner().invoke(
        main,
        ["run", str(spec), "--target", "stc", "--manual", "--budget", BUDGET_TIGHT],
    )
    # R2b contract conversion (packet decision 2; P1-ADDENDUM item 1): the
    # tiny clipboard fixture cannot host the ratified §5.2 mandatory set,
    # so the loop fails closed — exit 1 with a partial NEEDS_REPAIR
    # dossier and zero success artifacts — instead of a champion.
    assert res.exit_code == 1
    assert "no-verified-candidate" in res.output
    assert (dossier_dir / "STATUS").read_text(encoding="utf-8").strip() == "NEEDS_REPAIR"
    assert not (dossier_dir / "merged.diff").exists()
    assert not (dossier_dir / "execution_receipt.json").exists()
    assert not (dossier_dir / "judiciary_verdict.json").exists()
    spend = json.loads((dossier_dir / "spend.json").read_text(encoding="utf-8"))
    # Fail-closed spend shape: diverge runs (1 call), critique never runs
    # with zero verified candidates (the old ==2 was champion-path
    # aspirational and never observed — the old test failed before it).
    assert spend["totals"]["gateway_calls"] == 1
    assert spend["totals"]["gateway_ok"] == 1
    branches = json.loads((dossier_dir / "branches.json").read_text(encoding="utf-8"))
    assert branches["outcome"] == "no-champion"
    assert branches["reason"] == "no-verified-candidate"
    assert len(branches["branch_refs"]) >= 1
    run_ref = json.loads((dossier_dir / "run_ref.json").read_text(encoding="utf-8"))
    assert run_ref["status"] == "NEEDS_REPAIR"
    assert Path(run_ref["result_file"]).is_file()
    assert branches["scores_summary"] == {}
    assert "champion_id" not in branches


def test_manual_mode_rejects_invalid_fixtures_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--manual fails fast on invalid fixture payloads (no loop run)."""
    src = _git_source(tmp_path)
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    dossier_dir = tmp_path / "dossier"
    payloads = tmp_path / "payloads"
    payloads.mkdir()
    (payloads / "01-diverge.json").write_text("{not json", encoding="utf-8")
    (payloads / "02-critique.json").write_text(
        json.dumps({"value_score": "high", "verdict": "APPROVE"}), encoding="utf-8"
    )
    monkeypatch.setenv("STC_SOURCE_ROOT", str(src))
    monkeypatch.setenv("STC_DOSSIER_DIR", str(dossier_dir))
    monkeypatch.setenv("STC_MANUAL_FIXTURE_DIR", str(payloads))

    res = CliRunner().invoke(
        main,
        ["run", str(spec), "--target", "stc", "--manual", "--budget", BUDGET_TIGHT],
    )
    assert res.exit_code == 2
    assert "01-diverge.json" in res.output
    assert "02-critique.json" in res.output
    assert "manual-template" in res.output
    assert not (dossier_dir / "STATUS").exists()
    assert not (dossier_dir / "branches.json").exists()


def test_manual_mode_rejects_shape_mismatch_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diverge-shaped file named *-refine.json fails with a mismatch hint."""
    src = _git_source(tmp_path)
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    dossier_dir = tmp_path / "dossier"
    payloads = tmp_path / "payloads"
    payloads.mkdir()
    (payloads / "01-refine.json").write_text(
        json.dumps(
            {
                "branches": [
                    {
                        "strategy_title": "t",
                        "hypothesis_or_rationale": "r",
                        "proposed_changes": _full_diff(GOOD_MOD),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("STC_SOURCE_ROOT", str(src))
    monkeypatch.setenv("STC_DOSSIER_DIR", str(dossier_dir))
    monkeypatch.setenv("STC_MANUAL_FIXTURE_DIR", str(payloads))

    res = CliRunner().invoke(
        main,
        ["run", str(spec), "--target", "stc", "--manual", "--budget", BUDGET_TIGHT],
    )
    assert res.exit_code == 2
    assert "DIVERGE" in res.output and "REFINE" in res.output


def _pass_verify(
    self: Any,
    task: Any,
    proposal: Any,
    source_dir: Any,
    acceptance_command: Any = None,
    timeout: int = 120,
) -> DeterministicGateResult:
    """Deterministic custody pass (isolates the critique/veto path under test)."""
    _ = (self, task, proposal, source_dir, acceptance_command, timeout)
    return DeterministicGateResult(
        passed=True,
        exit_code=0,
        stdout="ruff=True mypy=True pytest=True",
        stderr="",
        duration_seconds=0.1,
    )


def test_manual_starved_critique_vetoes_to_unsuccessful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exhausted critique (fallback layer A) vetoes to an unsuccessful final.

    Custody is stubbed to pass so the critique call runs; with no critique
    fixture left, the harness errors, the controller falls back, and the
    RT-03 veto (string rules + provenance) must reject the champion. The
    final outcome is unsuccessful with typed veto evidence (Fixes 1+2).
    """
    import stc.integration.harness_worker as worker_mod

    src = _git_source(tmp_path)
    spec = _write_spec(tmp_path, "low_tau.md", LOW_TAU_SPEC)
    dossier_dir = tmp_path / "dossier"
    payloads = tmp_path / "payloads"
    payloads.mkdir()
    (payloads / "01-diverge.json").write_text(
        json.dumps(
            {
                "branches": [
                    {
                        "strategy_title": "Good branch",
                        "hypothesis_or_rationale": "Keep add correct.",
                        "proposed_changes": _full_diff(GOOD_MOD),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("STC_SOURCE_ROOT", str(src))
    monkeypatch.setenv("STC_DOSSIER_DIR", str(dossier_dir))
    monkeypatch.setenv("STC_MANUAL_FIXTURE_DIR", str(payloads))
    monkeypatch.setattr(runner_mod.STCCustodyWrapper, "verify_candidate_proposal", _pass_verify)

    def _no_native(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("native CLI-model command built in manual mode")

    monkeypatch.setattr(worker_mod, "build_native_command", _no_native)

    res = CliRunner().invoke(
        main,
        ["run", str(spec), "--target", "stc", "--manual", "--budget", BUDGET_TIGHT],
    )
    assert res.exit_code == 1
    assert "champion-vetoed-no-alternative" in res.output
    assert (dossier_dir / "STATUS").read_text(encoding="utf-8").strip() == "NEEDS_REPAIR"
    assert not (dossier_dir / "merged.diff").exists()
    veto_log = json.loads((dossier_dir / "veto_log.json").read_text(encoding="utf-8"))
    assert len(veto_log) >= 1
    assert veto_log[0]["rule"] in (
        "explicit-critique-failed",
        "exact-fallback-rationale",
        "default-score-0.85",
        "critique-unprovenanced",
    )
    branches = json.loads((dossier_dir / "branches.json").read_text(encoding="utf-8"))
    assert branches["outcome"] == "no-champion"
    assert branches["reason"] == "champion-vetoed-no-alternative"
