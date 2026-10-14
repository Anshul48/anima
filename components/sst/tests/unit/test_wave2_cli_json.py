"""Wave-2 CLI tests: `sst run --json` machine path and documented exit codes.

SYNTHETIC PROVENANCE: API_KEY values set here are the "[REDACTED]"
placeholder via monkeypatch, never real credentials.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _pytest.monkeypatch import MonkeyPatch
from click.testing import CliRunner

from sst.cli.main import (
    EXIT_BUDGET_EXHAUSTED,
    EXIT_CANCELLED,
    EXIT_CHAMPION,
    EXIT_NO_CANDIDATE,
    EXIT_PROVIDER_ERROR,
    _get_default_gateway,
    cli,
    exit_code_for_result,
)
from sst.core.contracts import CandidateProposal, ProviderErrorRecord, SearchResult, TerminationReason
from sst.gateway.contracts import ProviderKind


def _result(
    termination: TerminationReason,
    *,
    champion: bool = False,
    provider_errors: int = 0,
) -> SearchResult:
    return SearchResult(
        tree_id="tree_x",
        termination_reason=termination,
        champion=(
            CandidateProposal(candidate_id="cand_1", tree_id="tree_x", title="T", rationale="R") if champion else None
        ),
        provider_errors=[
            ProviderErrorRecord(role="diverge", category="unreachable_endpoint", remediation="Fix", message="Down")
            for _ in range(provider_errors)
        ],
    )


def test_exit_code_mapping() -> None:
    assert exit_code_for_result(_result(TerminationReason.CHAMPION_FOUND, champion=True)) == EXIT_CHAMPION == 0
    assert exit_code_for_result(_result(TerminationReason.NO_CANDIDATE)) == EXIT_NO_CANDIDATE == 2
    assert exit_code_for_result(_result(TerminationReason.BUDGET_EXHAUSTED)) == EXIT_BUDGET_EXHAUSTED == 3
    assert exit_code_for_result(_result(TerminationReason.NO_CANDIDATE, provider_errors=2)) == EXIT_PROVIDER_ERROR == 4
    assert exit_code_for_result(_result(TerminationReason.CANCELLED)) == EXIT_CANCELLED == 130


def test_exit_code_champion_beats_budget() -> None:
    """Mid-run champions preserved on budget breaks still exit 0."""
    assert exit_code_for_result(_result(TerminationReason.BUDGET_EXHAUSTED, champion=True)) == EXIT_CHAMPION
    assert exit_code_for_result(_result(TerminationReason.CANCELLED, champion=True)) == EXIT_CHAMPION


def test_run_help_documents_exit_codes() -> None:
    runner = CliRunner()
    res = runner.invoke(cli, ["run", "--help"])
    assert res.exit_code == 0
    assert "--json" in res.output
    assert "Exit codes" in res.output


def _run_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "run",
        "--goal",
        "Trivial fixture task",
        "--project-path",
        str(tmp_path),
        "--max-iterations",
        "1",
        *extra,
    ]


def test_run_json_prints_envelope_and_exits_zero(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """TEST-provider fixture run with passing acceptance yields a champion; stdout must be pure JSON."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()
    passing = f'{sys.executable} -c "pass"'
    res = runner.invoke(cli, _run_args(tmp_path, "--json", "--test-command", passing))

    assert res.exit_code == 0, res.output
    assert "Memory provider" in res.stderr
    assert "Gateway profiles:" in res.stderr
    assert "TEST" in res.stderr
    envelope = json.loads(res.stdout)
    assert envelope["termination_reason"] == TerminationReason.CHAMPION_FOUND.value
    assert envelope["champion"] is not None
    assert envelope["champion"]["candidate_id"].startswith("cand_tree_")
    assert envelope["event_log_ref"].startswith("sqlite:")


def test_run_json_no_candidate_exits_two(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A failing acceptance command yields no champion: exit 2 with a JSON envelope."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()
    failing = f'{sys.executable} -c "import sys; sys.exit(1)"'
    res = runner.invoke(cli, _run_args(tmp_path, "--json", "--test-command", failing))

    assert res.exit_code == EXIT_NO_CANDIDATE, res.output
    envelope = json.loads(res.stdout)
    assert envelope["termination_reason"] == TerminationReason.NO_CANDIDATE.value
    assert envelope["champion"] is None
    assert envelope["provider_errors"] == []


def test_run_human_default_unchanged(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Without --json the human panels stay the default and exit 0 on champion."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = CliRunner()
    passing = f'{sys.executable} -c "pass"'
    res = runner.invoke(cli, _run_args(tmp_path, "--test-command", passing))

    assert res.exit_code == 0, res.output
    assert "Champion Candidate Discovered" in res.output
    assert "Semantic review:" in res.output


def test_default_gateway_provider_precedence(monkeypatch: MonkeyPatch) -> None:
    """Credential precedence: OpenAI > DeepSeek > TEST fixture."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("SST_MODEL", raising=False)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    prof = _get_default_gateway().get_profile("default")
    assert prof is not None
    assert prof.kind is ProviderKind.TEST

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    prof = _get_default_gateway().get_profile("default")
    assert prof is not None
    assert prof.kind is ProviderKind.OPENAI_COMPATIBLE
    assert prof.api_base == "https://api.deepseek.com"
    assert prof.selected_model == "deepseek-chat"

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    prof = _get_default_gateway().get_profile("default")
    assert prof is not None
    assert prof.kind is ProviderKind.OPENAI_COMPATIBLE
    assert prof.api_base == "https://api.openai.com/v1"
    assert prof.selected_model == "gpt-4o"


def test_run_response_max_tokens_flag_reaches_policy(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """--response-max-tokens must reach SearchPolicy (reasoning-model headroom)."""
    from sst.search.controller import SSTSearchController

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    seen: dict[str, Any] = {}
    real_init = SSTSearchController.__init__

    def spy_init(self: SSTSearchController, *args: Any, **kwargs: Any) -> None:
        seen["policy"] = kwargs.get("policy")
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(SSTSearchController, "__init__", spy_init)
    runner = CliRunner()
    passing = f'{sys.executable} -c "pass"'
    res = runner.invoke(cli, _run_args(tmp_path, "--json", "--test-command", passing, "--response-max-tokens", "8192"))
    assert res.exit_code == 0, res.output
    assert seen["policy"] is not None
    assert seen["policy"].response_max_tokens == 8192
