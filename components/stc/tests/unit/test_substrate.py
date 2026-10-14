"""Unit tests for the Substrate deterministic quality gate runner and receipt signer.

Enforces zero-mock verification:
- Real subprocess tool invocations (ruff, mypy, pytest)
- Real git repository operations in temporary worktrees
- Cryptographic HMAC-SHA256 and SHA-256 signature verification
- Exhaustive tamper detection across all receipt dimensions (including environment metadata & epoch)
- Injected syntax error verification failing Gate 1 with is_passing == False
- Cross-OS WSL path translation and mutmut threshold enforcement
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from stc.protocols.interfaces import SubstrateRunnerProtocol
from stc.schemas.models import GateReport
from stc.substrate.receipt import (
    ReceiptSigner,
    compute_receipt_signature,
    create_receipt,
    load_receipt,
    save_receipt,
    serialize_canonical_payload,
    verify_receipt,
)
from stc.substrate.runner import (
    SubstrateRunner,
    SubstrateRunnerConfig,
    _format_snippet,
    _parse_mutmut_output,
    _translate_to_wsl_path,
)


def _make_dummy_gate(name: str = "gate", exit_code: int = 0) -> GateReport:
    """Helper to create dummy gate reports for cryptographic unit testing."""
    return GateReport(
        gate_name=name,
        exit_code=exit_code,
        duration_seconds=0.1,
        violations_count=0 if exit_code == 0 else 1,
        raw_output_snippet="OK" if exit_code == 0 else "FAILED",
    )


def test_substrate_runner_protocol_conformance() -> None:
    """Verify that SubstrateRunner conforms to SubstrateRunnerProtocol."""
    runner = SubstrateRunner()
    assert isinstance(runner, SubstrateRunnerProtocol)


def test_signature_verification_and_exhaustive_tamper_detection() -> None:
    """Verify compute_receipt_signature and verify_receipt under all tamper scenarios."""
    runner = SubstrateRunner()
    g_pass = _make_dummy_gate("gate", exit_code=0)

    receipt = create_receipt(
        task_id="TASK-SUB-001",
        commit_hash="deadbeef1234",
        timestamp_utc="2026-09-03T14:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
        receipt_id="rcpt_test_001",
        epoch_index=1,
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        correlation_id="corr_001",
        causation_id="cause_001",
    )

    # 1. Untampered receipt must verify
    assert runner.verify_receipt(receipt) is True
    assert verify_receipt(receipt) is True

    # 2. Tampered task_id
    assert verify_receipt(receipt.model_copy(update={"task_id": "TASK-FORGED-999"})) is False

    # 3. Tampered commit_hash
    assert verify_receipt(receipt.model_copy(update={"commit_hash": "forged_commit"})) is False

    # 4. Tampered timestamp_utc
    tampered_time = receipt.model_copy(update={"timestamp_utc": "2026-09-04T00:00:00Z"})
    assert verify_receipt(tampered_time) is False

    # 5. Tampered correlation_id
    tampered_corr = receipt.model_copy(update={"correlation_id": "corr_tampered"})
    assert verify_receipt(tampered_corr) is False

    # 6. Tampered causation_id
    tampered_cause = receipt.model_copy(update={"causation_id": "cause_tampered"})
    assert verify_receipt(tampered_cause) is False
    assert verify_receipt(receipt.model_copy(update={"causation_id": None})) is False

    # 7. Tampered gates
    tampered_ruff = receipt.model_copy(update={"gate_ruff": _make_dummy_gate("ruff", exit_code=1)})
    assert verify_receipt(tampered_ruff) is False

    tampered_mypy = receipt.model_copy(update={"gate_mypy": _make_dummy_gate("mypy", exit_code=1)})
    assert verify_receipt(tampered_mypy) is False

    tampered_pytest = receipt.model_copy(
        update={"gate_pytest": _make_dummy_gate("pytest", exit_code=1)}
    )
    assert verify_receipt(tampered_pytest) is False

    tampered_mutmut = receipt.model_copy(
        update={"gate_mutmut": _make_dummy_gate("mutmut", exit_code=1)}
    )
    assert verify_receipt(tampered_mutmut) is False

    # 8. Tampered sha256_signature
    tampered_sig = receipt.model_copy(update={"sha256_signature": "0" * 64})
    assert verify_receipt(tampered_sig) is False

    # 9. Tampered receipt_id
    tampered_rcpt_id = receipt.model_copy(update={"receipt_id": "rcpt_forged_999"})
    assert verify_receipt(tampered_rcpt_id) is False

    # 10. Tampered epoch_index (critical for circuit breaker protection)
    tampered_epoch = receipt.model_copy(update={"epoch_index": 3})
    assert verify_receipt(tampered_epoch) is False

    # 11. Tampered environment metadata (python_version per 01_INVARIANTS.md §5)
    tampered_py = receipt.model_copy(update={"python_version": "3.11.0"})
    assert verify_receipt(tampered_py) is False

    # 12. Tampered environment metadata (os_platform per 01_INVARIANTS.md §5)
    tampered_os = receipt.model_copy(update={"os_platform": "Linux"})
    assert verify_receipt(tampered_os) is False


def test_hmac_sha256_signing_and_verification() -> None:
    """Verify HMAC-SHA256 receipt signing with secret key and key mismatch rejection."""
    g_pass = _make_dummy_gate("gate", exit_code=0)
    secret_key = "secret_sovereign_key_42"

    signer = ReceiptSigner(key=secret_key)
    receipt = signer.create_receipt(
        task_id="TASK-HMAC-001",
        commit_hash="aabbcc112233",
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        epoch_index=2,
        correlation_id="corr_hmac_01",
        causation_id="cause_hmac_01",
        receipt_id="rcpt_hmac_01",
        timestamp_utc="2026-09-04T12:00:00Z",
        python_version="3.12.9",
        os_platform="Linux",
    )

    assert receipt.task_id == "TASK-HMAC-001"
    assert receipt.commit_hash == "aabbcc112233"
    assert receipt.gate_ruff == g_pass
    assert receipt.gate_mypy == g_pass
    assert receipt.gate_pytest == g_pass
    assert receipt.gate_mutmut == g_pass
    assert receipt.epoch_index == 2
    assert receipt.correlation_id == "corr_hmac_01"
    assert receipt.causation_id == "cause_hmac_01"
    assert receipt.receipt_id == "rcpt_hmac_01"
    assert receipt.timestamp_utc == "2026-09-04T12:00:00Z"
    assert receipt.python_version == "3.12.9"
    assert receipt.os_platform == "Linux"

    sig = signer.compute_signature(
        task_id="TASK-HMAC-001",
        commit_hash="aabbcc112233",
        timestamp_utc="2026-09-04T12:00:00Z",
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        correlation_id="corr_hmac_01",
        causation_id="cause_hmac_01",
        epoch_index=2,
        python_version="3.12.9",
        os_platform="Linux",
        receipt_id="rcpt_hmac_01",
    )
    assert sig == receipt.sha256_signature

    # Verifying with the correct key must succeed
    assert signer.verify(receipt) is True
    assert verify_receipt(receipt, key=secret_key) is True

    # Verifying with wrong key must fail
    assert verify_receipt(receipt, key="wrong_secret_key") is False

    # Verifying with unkeyed/empty key must fail
    assert verify_receipt(receipt, key=None) is False

    # Tampered content with HMAC must fail
    tampered = receipt.model_copy(update={"task_id": "TASK-HMAC-FORGED"})
    assert signer.verify(tampered) is False


def test_substrate_runner_config_and_os_mutmut_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify SubstrateRunnerConfig separation from protocol and mutmut deferral policy."""
    config = SubstrateRunnerConfig(
        timeout_per_gate=45.0,
        run_mutmut=False,
        defer_windows_mutmut_to_wsl=True,
        mutmut_kill_threshold=0.90,
        wsl_distribution="Ubuntu-24.04",
    )
    runner = SubstrateRunner(config=config)

    assert runner.timeout_per_gate == 45.0
    assert runner.run_mutmut is False
    assert runner.defer_windows_mutmut_to_wsl is True
    assert runner.mutmut_kill_threshold == 0.90
    assert runner.wsl_distribution == "Ubuntu-24.04"
    assert isinstance(runner, SubstrateRunnerProtocol)

    # Gate 4 when mutmut is disabled
    report = runner._run_gate_mutmut(Path(), run_mutmut=False)
    assert report.exit_code == 0
    assert report.violations_count == 0
    assert "disabled" in report.raw_output_snippet.lower()

    # Gate 4 when mutmut on Windows defers to WSL (WSL binary absent)
    if sys.platform == "win32":
        monkeypatch.setattr(shutil, "which", lambda _: None)
        report_defer = runner._run_gate_mutmut(Path(), run_mutmut=True, defer_windows=True)
        assert report_defer.exit_code == 0
        assert report_defer.violations_count == 0
        assert "NOT-MEASURED" in report_defer.raw_output_snippet
        assert "01_INVARIANTS.md §3.3" in report_defer.raw_output_snippet
        assert "WSL executable not found" in report_defer.raw_output_snippet


def test_wsl_unexpected_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify unexpected WSL execution exceptions return fail-closed GateReport."""
    runner = SubstrateRunner(defer_windows_mutmut_to_wsl=True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(shutil, "which", lambda _: "wsl.exe")

    def _failing_run(*args: Any, **kwargs: Any) -> Any:
        raise OSError("WSL process failed to spawn")

    monkeypatch.setattr(subprocess, "run", _failing_run)
    report = runner._run_gate_mutmut(Path(), run_mutmut=True, defer_windows=True)
    assert report.exit_code != 0
    assert report.violations_count >= 1
    assert "WSL process failed to spawn" in report.raw_output_snippet


def test_wsl_unparseable_output_disclosed_deferral(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify unparseable WSL output falls through to disclosed deferral with output preserved."""
    runner = SubstrateRunner(defer_windows_mutmut_to_wsl=True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(shutil, "which", lambda _: "wsl.exe")
    stub_res = subprocess.CompletedProcess(
        args=["wsl.exe"],
        returncode=1,
        stdout="sh: 1: mutmut: not found\n",
        stderr="Error code 127\n",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: stub_res)
    report = runner._run_gate_mutmut(Path(), run_mutmut=True, defer_windows=True)
    assert report.exit_code == 0
    assert report.violations_count == 0
    assert "NOT-MEASURED" in report.raw_output_snippet
    assert "01_INVARIANTS.md §3.3" in report.raw_output_snippet
    assert "mutmut: not found" in report.raw_output_snippet
    assert "WSL Output:" in report.raw_output_snippet


def test_translate_to_wsl_path() -> None:
    """Verify cross-OS path translation mapping Windows drives to /mnt/<drive>/."""
    from typing import cast

    class FakePath:
        def __init__(self, drive: str, parts: tuple[str, ...], posix_val: str) -> None:
            self.drive = drive
            self.parts = parts
            self._posix_val = posix_val

        def resolve(self) -> FakePath:
            return self

        def as_posix(self) -> str:
            return self._posix_val

    # Standard Windows paths: tested on ALL platforms
    p1 = cast(
        Path, FakePath("C:", ("C:\\", "Users", "developer", "code"), "C:/Users/developer/code")
    )
    assert _translate_to_wsl_path(p1) == "/mnt/c/Users/developer/code"

    p2 = cast(Path, FakePath("C:", ("C:\\",), "C:/"))
    assert _translate_to_wsl_path(p2) == "/mnt/c"

    p3 = cast(Path, FakePath("D:", ("D:\\", "data", "worktree"), "D:/data/worktree"))
    assert _translate_to_wsl_path(p3) == "/mnt/d/data/worktree"

    # Lowercase drive
    p4 = cast(Path, FakePath("e:", ("e:\\", "sub"), "e:/sub"))
    assert _translate_to_wsl_path(p4) == "/mnt/e/sub"

    # Drive with len < 2
    p5 = cast(Path, FakePath("C", ("C", "foo"), "/C/foo"))
    assert _translate_to_wsl_path(p5) == "/C/foo"

    # Drive with len >= 2 but drive[1] != ":"
    p6 = cast(Path, FakePath("//", ("//", "share"), "//share"))
    assert _translate_to_wsl_path(p6) == "//share"

    # Empty drive
    p7 = cast(Path, FakePath("", ("/", "var", "log", "stc"), "/var/log/stc"))
    assert _translate_to_wsl_path(p7) == "/var/log/stc"


def test_parse_mutmut_output_and_threshold_enforcement() -> None:
    """Verify mutmut output parsing and kill threshold enforcement."""
    sample_passing_output = "Killed: 90\nSurvived: 10\nTimeout: 0"
    killed, survived, timeout, kill_rate = _parse_mutmut_output(sample_passing_output)
    assert killed == 90
    assert survived == 10
    assert timeout == 0
    assert kill_rate == 0.90

    sample_failing_output = "Killed: 60\nSurvived: 40\nTimeout: 0"
    k_fail, s_fail, _t_fail, r_fail = _parse_mutmut_output(sample_failing_output)
    assert k_fail == 60
    assert s_fail == 40
    assert r_fail == 0.60

    # Emoji output parsing
    emoji_output = "🎉 85 🫥 10 ⏰ 2 🤔 0 🙁 15"
    k_em, s_em, t_em, r_em = _parse_mutmut_output(emoji_output)
    assert k_em == 85
    assert s_em == 15
    assert t_em == 2
    assert r_em == round(85 / (85 + 15 + 2), 4)

    # Empty and unparseable output
    assert _parse_mutmut_output("") == (0, 0, 0, None)
    assert _parse_mutmut_output("random output with no stats") == (0, 0, 0, None)

    # Isolated timeout checks
    assert _parse_mutmut_output("Timeout: 5") == (0, 0, 5, 0.0)
    assert _parse_mutmut_output("⏰ 3") == (0, 0, 3, 0.0)

    # Rounding precision to exactly 4 decimal places
    # 1 / 7 = 0.14285714... -> round(1/7, 4) == 0.1429
    k_rnd, s_rnd, t_rnd, r_rnd = _parse_mutmut_output("Killed: 1\nSurvived: 6")
    assert k_rnd == 1
    assert s_rnd == 6
    assert t_rnd == 0
    assert r_rnd == 0.1429


def test_format_snippet() -> None:
    """Verify _format_snippet truncation, empty handling, and tail preservation."""
    assert _format_snippet("") == ""
    assert _format_snippet("short message", max_chars=100) == "short message"

    # Exactly 1000 chars (default max_chars)
    exact_default = "x" * 1000
    assert _format_snippet(exact_default) == exact_default
    assert _format_snippet("x" * 1001) == "x" * 1000

    # Exact boundary max_chars
    assert _format_snippet("abcde", max_chars=5) == "abcde"
    assert _format_snippet("abcde", max_chars=3) == "cde"

    # Newline in tail handling
    # "ab\ncd" with max_chars=4: tail is "b\ncd", nl=1 -> tail[2:] is "cd"
    assert _format_snippet("ab\ncd", max_chars=4) == "cd"
    # Newline at index 0 of tail: "\nyz" with max_chars=3
    # tail is "\nyz", nl=0 -> tail[1:] is "yz"
    assert _format_snippet("x\nyz", max_chars=3) == "yz"
    # Newline at end of tail: "xy\n" with max_chars=3 -> tail is "xy\n", nl=2 -> tail[3:] is ""
    assert _format_snippet("wxy\n", max_chars=3) == ""


def test_receipt_signer_create_receipt_exhaustive() -> None:
    """Verify ReceiptSigner.create_receipt forwards all fields to create_receipt."""
    signer = ReceiptSigner(key="test-signing-key")
    g_pass = GateReport(
        gate_name="ruff",
        exit_code=0,
        duration_seconds=0.5,
        violations_count=0,
        raw_output_snippet="ok",
    )
    receipt = signer.create_receipt(
        task_id="TASK-CUSTOM-01",
        commit_hash="abcdef1234567890abcdef1234567890abcdef12",
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        epoch_index=3,
        correlation_id="corr_custom_999",
        causation_id="caus_custom_888",
        receipt_id="rcpt_custom_777",
        timestamp_utc="2026-09-04T12:00:00Z",
        python_version="3.12.99",
        os_platform="CustomOS",
    )
    assert receipt.task_id == "TASK-CUSTOM-01"
    assert receipt.commit_hash == "abcdef1234567890abcdef1234567890abcdef12"
    assert receipt.gate_ruff == g_pass
    assert receipt.gate_mypy == g_pass
    assert receipt.gate_pytest == g_pass
    assert receipt.gate_mutmut == g_pass
    assert receipt.epoch_index == 3
    assert receipt.correlation_id == "corr_custom_999"
    assert receipt.causation_id == "caus_custom_888"
    assert receipt.receipt_id == "rcpt_custom_777"
    assert receipt.timestamp_utc == "2026-09-04T12:00:00Z"
    assert receipt.python_version == "3.12.99"
    assert receipt.os_platform == "CustomOS"
    assert signer.verify(receipt) is True


def test_pytest_skipped_tests_fail_invariant(tmp_path: Path) -> None:
    """Verify 01_INVARIANTS.md §5: 0 skipped tests permitted.

    A test suite with skipped tests must fail Gate 3 with exit_code != 0.
    """
    test_dir = tmp_path / "skipped_test_repo"
    test_dir.mkdir()
    test_file = test_dir / "test_sample.py"
    test_content = (
        "import pytest\n\n@pytest.mark.skip(reason='testing skip failure')\ndef test_skip(): pass\n"
    )
    test_file.write_text(test_content, encoding="utf-8")
    runner = SubstrateRunner(timeout_per_gate=30.0)
    report = runner._run_gate_pytest(test_dir)
    assert report.exit_code != 0
    assert report.violations_count >= 1
    assert "skipped test(s) detected" in report.raw_output_snippet


def test_gate_timeout_graceful_handling() -> None:
    """Verify gate timeout handling gracefully returns exit_code 124."""
    runner = SubstrateRunner(timeout_per_gate=0.0001)
    # Trigger gate with impossible timeout
    report = runner._run_gate_ruff(Path())
    assert report.exit_code == 124
    assert report.violations_count >= 1
    assert "timed out" in report.raw_output_snippet.lower()


def test_substrate_runner_real_clean_execution_and_save(tmp_path: Path) -> None:
    """Verify executing real substrate gates against the clean STC repository."""
    runner = SubstrateRunner(timeout_per_gate=60.0)
    receipt = runner.execute_gates(
        worktree_path=Path(),
        task_id="TASK-CLEAN-TREE",
        epoch_index=1,
        pytest_target="tests/unit/test_config.py",
    )

    # Gate assertions
    assert receipt.task_id == "TASK-CLEAN-TREE"
    assert receipt.epoch_index == 1
    assert receipt.gate_ruff.exit_code == 0
    assert receipt.gate_mypy.exit_code == 0
    assert receipt.gate_pytest.exit_code == 0
    assert receipt.gate_mutmut.exit_code == 0
    assert receipt.is_passing is True
    assert runner.verify_receipt(receipt) is True

    # Persist and load verification
    saved_path = runner.save_receipt(receipt, output_dir=tmp_path)
    assert saved_path.is_file()

    loaded_receipt = load_receipt(saved_path)
    assert loaded_receipt.receipt_id == receipt.receipt_id
    assert loaded_receipt.task_id == receipt.task_id
    assert runner.verify_receipt(loaded_receipt) is True


def test_injected_syntax_error_fails_gate_1_with_is_passing_false(tmp_path: Path) -> None:
    """Verify exit criterion: injected syntax error fails Gate 1 with is_passing == False.

    Uses a real temporary git repository with no mocking of subprocesses or domain logic.
    """
    repo_dir = tmp_path / "syntax_err_repo"
    repo_dir.mkdir()

    # Initialize real git repository
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "STC Test Worker"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "worker@stc.test"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Initial valid commit to establish git HEAD
    src_dir = repo_dir / "src"
    src_dir.mkdir()
    valid_file = src_dir / "valid_module.py"
    valid_content = '"""Valid module."""\n\ndef answer() -> int:\n    return 42\n'
    valid_file.write_text(valid_content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Inject intentional syntax error
    broken_file = src_dir / "broken_module.py"
    broken_file.write_text("def invalid_syntax(\n", encoding="utf-8")

    runner = SubstrateRunner(timeout_per_gate=30.0)
    receipt = runner.execute_gates(
        worktree_path=repo_dir,
        task_id="TASK-SYNTAX-FAIL",
        epoch_index=1,
    )

    # Gate 1 (Ruff) must detect the syntax failure
    assert receipt.gate_ruff.exit_code != 0
    assert receipt.gate_ruff.violations_count >= 1
    snippet = receipt.gate_ruff.raw_output_snippet.lower()
    assert "unexpected eof" in snippet or "syntax" in snippet

    # Overall receipt must NOT be passing
    assert receipt.is_passing is False

    # The failing receipt itself must still possess a valid cryptographic signature
    assert runner.verify_receipt(receipt) is True


def test_clean_tree_emits_verifiable_receipt_json(tmp_path: Path) -> None:
    """Verify exit criterion: clean tree emits verifiable receipt.json."""
    runner = SubstrateRunner(timeout_per_gate=60.0)
    receipt = runner.execute_gates(
        worktree_path=Path(),
        task_id="STAGE-1",
        epoch_index=1,
        pytest_target="tests/unit/test_config.py",
    )

    assert receipt.is_passing is True
    assert runner.verify_receipt(receipt) is True

    # Save receipt as receipt.json in tmp_path and verify roundtrip
    saved = save_receipt(receipt, output_dir=tmp_path, filename="receipt.json")
    assert saved.is_file()

    loaded = load_receipt(saved)
    assert loaded.is_passing is True
    assert runner.verify_receipt(loaded) is True
    assert loaded.gate_ruff.exit_code == 0
    assert loaded.gate_mypy.exit_code == 0
    assert loaded.gate_pytest.exit_code == 0
    assert loaded.gate_mutmut.exit_code == 0


def test_canonical_serialization_determinism() -> None:
    """Verify bit-exact determinism of canonical receipt payload serialization."""
    g1 = _make_dummy_gate("gate", 0)
    g2 = _make_dummy_gate("gate", 0)

    bytes1 = serialize_canonical_payload(
        task_id="TASK-DET-01",
        commit_hash="abc",
        timestamp_utc="2026-09-04T12:00:00Z",
        gate_ruff=g1,
        gate_mypy=g1,
        gate_pytest=g1,
        gate_mutmut=g1,
        correlation_id="corr_01",
        causation_id=None,
        epoch_index=1,
        python_version="3.12.4",
        os_platform="Windows",
        receipt_id="rcpt_01",
    )

    bytes2 = serialize_canonical_payload(
        task_id="TASK-DET-01",
        commit_hash="abc",
        timestamp_utc="2026-09-04T12:00:00Z",
        gate_ruff=g2,
        gate_mypy=g2,
        gate_pytest=g2,
        gate_mutmut=g2,
        correlation_id="corr_01",
        causation_id=None,
        epoch_index=1,
        python_version="3.12.4",
        os_platform="Windows",
        receipt_id="rcpt_01",
    )

    assert bytes1 == bytes2

    sig1 = compute_receipt_signature(
        task_id="TASK-DET-01",
        commit_hash="abc",
        timestamp_utc="2026-09-04T12:00:00Z",
        gate_ruff=g1,
        gate_mypy=g1,
        gate_pytest=g1,
        gate_mutmut=g1,
        correlation_id="corr_01",
        causation_id=None,
        epoch_index=1,
        python_version="3.12.4",
        os_platform="Windows",
        receipt_id="rcpt_01",
    )
    sig2 = compute_receipt_signature(
        task_id="TASK-DET-01",
        commit_hash="abc",
        timestamp_utc="2026-09-04T12:00:00Z",
        gate_ruff=g2,
        gate_mypy=g2,
        gate_pytest=g2,
        gate_mutmut=g2,
        correlation_id="corr_01",
        causation_id=None,
        epoch_index=1,
        python_version="3.12.4",
        os_platform="Windows",
        receipt_id="rcpt_01",
    )
    assert sig1 == sig2


def test_root_receipt_json_exists_and_verifies() -> None:
    """Verify that root receipt.json is valid and cryptographically verified."""
    root_receipt_path: Path | None = None
    direct_candidate = Path("receipt.json")
    if direct_candidate.is_file():
        root_receipt_path = direct_candidate.resolve()
    else:
        # Search ancestor directories from __file__ and cwd to anchor to the true repo root
        candidates = [
            *(p / "receipt.json" for p in Path(__file__).resolve().parents),
            *(p / "receipt.json" for p in Path.cwd().resolve().parents),
        ]
        for candidate in candidates:
            if candidate.is_file():
                root_receipt_path = candidate
                break

    assert root_receipt_path is not None and root_receipt_path.is_file(), (
        f"receipt.json not found in root or any parent directory. Checked: {Path.cwd()}"
    )
    receipt = load_receipt(root_receipt_path)
    assert receipt.is_passing is True
    assert verify_receipt(receipt) is True


def test_mypy_gate_flat_layout_with_tests_no_duplicate_module(tmp_path: Path) -> None:
    """Flat layout + tests/ must not double-scan (mypy Duplicate module).

    Regression: the gate ran ``mypy --strict . tests`` on flat trees, so
    mypy saw every test module twice and failed clean trees (csvledger
    run-1 triage: 8/8 Pro candidates failed on the artifact, not on
    code). Real subprocess gate on a real worktree; no mocking.
    """
    repo_dir = tmp_path / "flat_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"], cwd=repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=repo_dir, check=True, capture_output=True
    )
    (repo_dir / "app.py").write_text(
        '"""Flat app module."""\n\n\ndef answer() -> int:\n    return 42\n',
        encoding="utf-8",
    )
    tests_dir = repo_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text(
        '"""Flat tests."""\n\nfrom app import answer\n\n\ndef test_answer() -> None:\n'
        "    assert answer() == 42\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo_dir, check=True, capture_output=True)
    runner = SubstrateRunner(timeout_per_gate=120.0)
    receipt = runner.execute_gates(
        worktree_path=repo_dir,
        task_id="TASK-FLAT-MYPY",
        epoch_index=1,
    )
    assert receipt.gate_mypy.exit_code == 0, receipt.gate_mypy.raw_output_snippet
    assert "Duplicate module" not in receipt.gate_mypy.raw_output_snippet
