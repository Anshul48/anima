"""Unit tests for the STC command-line interface."""

import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import click
import pytest
import yaml
from click.testing import CliRunner

from stc import __version__
from stc.cli import (
    _dossier_base_identity,
    _gate_timeout_from_env,
    _parse_stc_budget,
    _sync_seeded_home_back,
    main,
)
from stc.core.config import get_settings
from stc.schemas.models import GateReport
from stc.substrate.runner import create_receipt


@pytest.fixture(autouse=True)
def _disposable_runtime_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Redirect gate-generated state to per-test disposable locations (R1).

    CLI-invoking tests in this file drive pipeline writers (locked
    invariants, signed receipts, trace DB rows, leased worktrees); all
    land under tmp_path so the gated repository stays byte-neutral.
    """
    roots = tmp_path / "stc-runtime"
    monkeypatch.setenv("STC_INVARIANTS_DIR", str(roots / "invariants"))
    monkeypatch.setenv("STC_RECEIPTS_DIR", str(roots / "receipts"))
    monkeypatch.setenv("STC_TRACE_DB_PATH", str(roots / "trace.db"))
    monkeypatch.setenv("STC_WORKTREE_ROOT", str(roots / "worktrees"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cli_version() -> None:
    """Verify version command output."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_info() -> None:
    """Verify info command outputs configuration table."""
    runner = CliRunner()
    result = runner.invoke(main, ["info"])
    assert result.exit_code == 0
    assert "STC: Spec-To-Code" in result.output
    assert "Architecture" in result.output


def test_cli_health() -> None:
    """Verify health command."""
    runner = CliRunner()
    result = runner.invoke(main, ["health"])
    assert result.exit_code == 0
    assert "OK" in result.output

    result_json = runner.invoke(main, ["health", "--json-output"])
    assert result_json.exit_code == 0
    assert '"status": "ok"' in result_json.output


def test_cli_run_task() -> None:
    """Verify running an adhoc task from the CLI."""
    runner = CliRunner()
    result = runner.invoke(main, ["run-task", "--action", "ping", "--name", "cli-test"])
    assert result.exit_code == 0
    assert "COMPLETED" in result.output
    assert "Receipt ID" in result.output
    assert "Receipt ID" in result.output


def test_cli_spec_ingest_and_toc(tmp_path: Path) -> None:
    """Verify real spec ingestion and TOC decomposition in CLI."""
    spec_file = tmp_path / "sample_auth.md"
    spec_file.write_text(
        "# Authentication Gateway\n\n"
        "## Invariants\nMust enforce token expiration.\n"
        "## Storage\nSQLite session tables.\n"
        "## Protocols\nPEP 544 AuthGatewayProtocol.\n"
        "## Security\nPII redaction enabled.\n"
        "## Resilience\nRetry with backoff.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(main, ["spec", str(spec_file)], input="1\n")
    assert res.exit_code == 0
    assert "Tree of Concerns (TOC) Decomposition" in res.output
    assert "Domain Invariants" in res.output

    # JSON mode test
    res_json = runner.invoke(main, ["-j", "spec", str(spec_file)])
    assert res_json.exit_code == 0
    parsed = json.loads(res_json.output)
    assert "spec_atom" in parsed
    assert "tree_of_concerns" in parsed


def test_cli_compile_task_bundle(tmp_path: Path) -> None:
    """Verify real TaskBundle compilation and byte ceiling enforcement."""
    spec_file = tmp_path / "sample_service.md"
    spec_file.write_text(
        "# Service Engine Specification\n"
        "This is a valid specification for testing task bundle assembly.\n",
        encoding="utf-8",
    )
    bundle_out = tmp_path / "task_bundle.yaml"
    runner = CliRunner()
    res = runner.invoke(
        main,
        ["compile", "TASK-BUNDLE-TEST", "--spec", str(spec_file), "--out", str(bundle_out)],
    )
    assert res.exit_code == 0
    assert "Bundle successfully compiled" in res.output
    assert bundle_out.is_file()


def test_cli_worktree_list() -> None:
    """Verify worktree list command runs without failure."""
    runner = CliRunner()
    res = runner.invoke(main, ["worktree", "list"])
    assert res.exit_code == 0


def test_cli_judge_signature_verification(tmp_path: Path) -> None:
    """Verify judge command verifies cryptographic signature and catches tampering."""
    runner = CliRunner()
    g_pass = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = create_receipt(
        task_id="TASK-JUDGE-001",
        commit_hash="c0ffee1234",
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        receipt_id="rcpt_judge_001",
        epoch_index=1,
        timestamp_utc="2026-09-03T15:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
        correlation_id="corr_001",
        causation_id=None,
    )

    receipt_file = tmp_path / "valid_receipt.json"
    receipt_file.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

    # If valid receipt is presented, judge either finds codex or reports staged error
    res_valid = runner.invoke(main, ["judge", "TASK-JUDGE-001", "--receipt", str(receipt_file)])
    assert "Cryptographic signature check FAILED" not in res_valid.output

    # Tamper with receipt file
    tampered_dict = json.loads(receipt_file.read_text(encoding="utf-8"))
    tampered_dict["task_id"] = "TASK-FORGED-002"
    tampered_file = tmp_path / "tampered_receipt.json"
    tampered_file.write_text(json.dumps(tampered_dict), encoding="utf-8")

    res_tampered = runner.invoke(main, ["judge", "TASK-JUDGE-001", "--receipt", str(tampered_file)])
    assert res_tampered.exit_code != 0
    assert "Cryptographic signature check FAILED" in res_tampered.output


def test_cli_compile_with_custom_targets_and_protocols(tmp_path: Path) -> None:
    """Verify compile command respects custom target files and protocols."""
    spec_file = tmp_path / "custom_spec.md"
    spec_file.write_text(
        "# Custom Service\nMust implement custom service gateway without mocks.\n",
        encoding="utf-8",
    )
    bundle_out = tmp_path / "custom_bundle.yaml"
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "compile",
            "TASK-CUSTOM-001",
            "--spec",
            str(spec_file),
            "--out",
            str(bundle_out),
            "--target-file",
            "src/stc/custom/service.py",
            "--protocol",
            "CustomServiceProtocol",
        ],
    )
    assert res.exit_code == 0
    assert bundle_out.is_file()
    data = json.loads(
        bundle_out.read_text(encoding="utf-8").replace("\n", " ")
        if bundle_out.name.endswith(".json")
        else json.dumps(yaml.safe_load(bundle_out.read_text(encoding="utf-8")))
    )
    assert any(tf["path"] == "src/stc/custom/service.py" for tf in data["target_files"])
    assert "CustomServiceProtocol" in data["membrane_protocols"]


def test_cli_judge_json_mode(tmp_path: Path) -> None:
    """Verify judge command outputs valid JSON conforming to JudiciaryVerdict."""
    runner = CliRunner()
    g_pass = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = create_receipt(
        task_id="TASK-JUDGE-JSON-001",
        commit_hash="c0ffee1234",
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        receipt_id="rcpt_judge_json_001",
        epoch_index=1,
        timestamp_utc="2026-09-03T15:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
        correlation_id="corr_001",
        causation_id=None,
    )

    receipt_file = tmp_path / "valid_receipt.json"
    receipt_file.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")

    res = runner.invoke(
        main, ["-j", "judge", "TASK-JUDGE-JSON-001", "--receipt", str(receipt_file)]
    )
    assert res.exit_code == 0
    parsed = json.loads(res.output)
    assert parsed["task_id"] == "TASK-JUDGE-JSON-001"
    assert parsed["status"] in ["APPROVED", "QUARANTINED", "REJECTED"]


def test_cli_worktree_json_and_release() -> None:
    """Verify worktree list in JSON mode and worktree release command."""
    runner = CliRunner()
    res_list = runner.invoke(main, ["-j", "worktree", "list"])
    assert res_list.exit_code == 0
    parsed_list = json.loads(res_list.output)
    assert isinstance(parsed_list, list)

    res_rel = runner.invoke(main, ["-j", "worktree", "release", "TASK-TEST-TEMP", "--purge"])
    assert res_rel.exit_code == 0
    parsed_rel = json.loads(res_rel.output)
    assert parsed_rel["status"] == "RELEASED"


def test_cli_run_json_mode(tmp_path: Path) -> None:
    """Verify run command end-to-end with -j output."""
    spec_file = tmp_path / "test_dag_spec.md"
    spec_file.write_text(
        "# Authentication Engine\n\n"
        "## Invariants\nMust enforce token expiration.\n"
        "## Persistence\nSQLite tables.\n"
        "## Protocols\nAuthProtocol.\n"
        "## Security\nPII redaction.\n"
        "## Resilience\nRetry on failure.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(main, ["-j", "run", str(spec_file)])
    assert res.exit_code == 0
    parsed = json.loads(res.output)
    assert "spec_atom" in parsed
    assert "tree_of_concerns" in parsed
    assert "task_bundle" in parsed
    assert "execution_receipt" in parsed
    assert "judiciary_verdict" in parsed
    assert parsed["judiciary_verdict"]["status"] == "APPROVED"


@pytest.mark.parametrize("spec", ["tokens=0", "usd=0", "usd=0.0", "tokens=-5"])
def test_parse_stc_budget_rejects_zero_and_negative_optionals(spec: str) -> None:
    """Explicit 0 would silently mean unlimited (falsy SST cap): reject it."""
    with pytest.raises(click.UsageError, match=r"must be positive \(or 'none'\)"):
        _parse_stc_budget(spec)


def test_parse_stc_budget_none_clears_optionals() -> None:
    """'none' stays the explicit unlimited spelling for tokens/usd."""
    budgets, policy = _parse_stc_budget("tokens=none,usd=none")
    assert budgets["token_budget"] is None
    assert budgets["cost_budget_usd"] is None
    assert policy["max_token_budget"] is None
    assert policy["max_cost_usd"] is None


def test_dossier_base_identity_clean_and_dirty(tmp_path: Path) -> None:
    """Base identity labels tracked state honestly (clean vs uncommitted)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
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
    assert _dossier_base_identity(repo, "abc123") == "abc123 (clean)"
    (repo / "a.txt").write_text("b\n", encoding="utf-8")
    assert _dossier_base_identity(repo, "abc123") == "abc123 + P05 owned (uncommitted)"


def test_dossier_base_identity_unknown_when_not_a_repo(tmp_path: Path) -> None:
    """Non-git source roots label state unknown, never clean or dirty."""
    assert _dossier_base_identity(tmp_path, "abc123") == "abc123 + P05 owned (state unknown)"


def _seed_pair(tmp_path: Path, main_bytes: bytes, scratch_bytes: bytes) -> tuple[Path, Path]:
    """Fake login + scratch homes; scratch written strictly after main."""
    main_auth = tmp_path / "main" / "auth.json"
    home = tmp_path / "scratch"
    main_auth.parent.mkdir(parents=True)
    home.mkdir(parents=True)
    main_auth.write_bytes(main_bytes)
    (home / "auth.json").write_bytes(scratch_bytes)
    base = 1_700_000_000.0
    os.utime(main_auth, (base, base))
    os.utime(home / "auth.json", (base + 60.0, base + 60.0))
    return home, main_auth


def test_sync_seeded_home_back_unchanged_is_noop(tmp_path: Path) -> None:
    """Identical bytes (no refresh, e.g. auth-failed runs) preserve main."""
    home, main_auth = _seed_pair(tmp_path, b"pair-A", b"pair-A")
    before = main_auth.stat().st_mtime
    record = _sync_seeded_home_back(home, main_auth)
    assert record["disposition"] == "unchanged"
    assert main_auth.read_bytes() == b"pair-A"
    assert main_auth.stat().st_mtime == before


def test_sync_seeded_home_back_synced_rotation(tmp_path: Path) -> None:
    """A newer rotated scratch pair is written back with mode 0o600."""
    home, main_auth = _seed_pair(tmp_path, b"pair-A", b"pair-B-rotated")
    record = _sync_seeded_home_back(home, main_auth)
    assert record["disposition"] == "synced"
    assert main_auth.read_bytes() == b"pair-B-rotated"
    assert main_auth.stat().st_mode & 0o777 == 0o600
    assert "pair-B" not in json.dumps(record)


def test_sync_seeded_home_back_keeps_newer_main(tmp_path: Path) -> None:
    """A main rotated elsewhere after seeding is never regressed."""
    home, main_auth = _seed_pair(tmp_path, b"pair-C-elsewhere", b"pair-A-stale")
    base = 1_700_000_000.0
    os.utime(home / "auth.json", (base, base))
    os.utime(main_auth, (base + 60.0, base + 60.0))
    record = _sync_seeded_home_back(home, main_auth)
    assert record["disposition"] == "main-newer-keep"
    assert main_auth.read_bytes() == b"pair-C-elsewhere"


def test_sync_seeded_home_back_missing_sides_fail_closed(tmp_path: Path) -> None:
    """Missing scratch or login yields a disposition, never a write."""
    home = tmp_path / "empty-scratch"
    home.mkdir(parents=True)
    main_auth = tmp_path / "main" / "auth.json"
    assert _sync_seeded_home_back(home, main_auth)["disposition"] == "scratch-missing"
    (home / "auth.json").write_bytes(b"pair-X")
    assert _sync_seeded_home_back(home, main_auth)["disposition"] == "main-missing"
    assert not main_auth.exists()


def test_gate_timeout_from_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset/blank keeps the 120s default (behavior unchanged)."""
    monkeypatch.delenv("STC_GATE_TIMEOUT_S", raising=False)
    assert _gate_timeout_from_env() == 120.0
    monkeypatch.setenv("STC_GATE_TIMEOUT_S", "   ")
    assert _gate_timeout_from_env() == 120.0


def test_gate_timeout_from_env_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit positive seconds pass through (leg5c precedent: 3600)."""
    monkeypatch.setenv("STC_GATE_TIMEOUT_S", "3600")
    assert _gate_timeout_from_env() == 3600.0


@pytest.mark.parametrize("raw", ["nope", "0", "-5", "inf", "nan", "1e999"])
def test_gate_timeout_from_env_rejects_bad(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """Non-numeric, non-positive, and non-finite values fail fast."""
    monkeypatch.setenv("STC_GATE_TIMEOUT_S", raw)
    with pytest.raises(click.UsageError):
        _gate_timeout_from_env()


@pytest.mark.parametrize(
    ("role", "marker"),
    [
        ("diverge", "proposed_changes"),
        ("refine", "executable_content"),
        ("synthesize", "executable_content"),
        ("critique", "value_score"),
    ],
)
def test_manual_template_renders_role_shape(role: str, marker: str) -> None:
    """manual-template prints parseable JSON with the role's key field."""
    runner = CliRunner()
    result = runner.invoke(main, ["manual-template", role])
    assert result.exit_code == 0
    assert marker in result.output
    json.loads(result.output)


def test_manual_template_rejects_unknown_role() -> None:
    """manual-template fails fast on unknown roles."""
    runner = CliRunner()
    result = runner.invoke(main, ["manual-template", "nope"])
    assert result.exit_code != 0
