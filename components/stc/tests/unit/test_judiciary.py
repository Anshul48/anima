"""Unit tests for the Judiciary blind adversarial auditor."""

from pathlib import Path

import pytest

from stc.judiciary.auditor import (
    FALLBACK_PATTERNS,
    MOCK_PATTERNS,
    SECRET_PATTERNS,
    WORKER_CONSTRAINTS,
    JudiciaryAuditor,
)
from stc.protocols.interfaces import JudiciaryAuditorProtocol
from stc.schemas.models import ExecutionReceipt, GateReport, TaskBundle
from stc.substrate.runner import create_receipt


def _make_valid_receipt(task_id: str = "TASK-001") -> ExecutionReceipt:
    g_pass = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    return create_receipt(
        task_id=task_id,
        commit_hash="c0ffee1234",
        gate_ruff=g_pass,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        receipt_id="rcpt_001",
        epoch_index=1,
        timestamp_utc="2026-09-03T12:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
        correlation_id="corr_001",
        causation_id=None,
    )


def _make_task_bundle(task_id: str = "TASK-001") -> TaskBundle:
    return TaskBundle(
        task_id=task_id,
        epoch_index=1,
        spec_id="spec_test",
        goal_statement="Implement domain logic without fake mocks",
        invariants=["Zero mock policy", "Fail-closed gates"],
        target_files=[],
        membrane_protocols=["SubstrateRunnerProtocol"],
        negative_inhibitors=[],
    )


def test_judiciary_auditor_protocol_conformance() -> None:
    """Verify that JudiciaryAuditor conforms to JudiciaryAuditorProtocol."""
    auditor = JudiciaryAuditor()
    assert isinstance(auditor, JudiciaryAuditorProtocol)


def test_judiciary_approves_clean_diff() -> None:
    """Verify clean diff and valid receipt yields APPROVED verdict."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-CLEAN")
    bundle = _make_task_bundle("TASK-CLEAN")

    diff_text = (
        "diff --git a/src/service.py b/src/service.py\n"
        "--- a/src/service.py\n"
        "+++ b/src/service.py\n"
        "@@ -10,2 +10,4 @@\n"
        "+def calculate_total(items: list[int]) -> int:\n"
        "+    return sum(items)\n"
    )

    verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)
    assert verdict.status == "APPROVED"
    assert len(verdict.findings) == 0
    assert "APPROVED" in verdict.summary_rationale


def test_judiciary_detects_and_rejects_mock_gaming() -> None:
    """Verify adversary using MagicMock or mock assertions is REJECTED with CRITICAL findings."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-MOCK")
    bundle = _make_task_bundle("TASK-MOCK")

    diff_mock = (
        "diff --git a/src/domain.py b/src/domain.py\n"
        "--- a/src/domain.py\n"
        "+++ b/src/domain.py\n"
        "@@ -1,3 +1,5 @@\n"
        "+from unittest.mock import MagicMock\n"
        "+fake_db = MagicMock()\n"
        "+assert mock == True\n"
    )

    verdict = auditor.audit_diff(diff_text=diff_mock, bundle=bundle, receipt=receipt)
    assert verdict.status == "REJECTED"
    rule_names = [f.rule_name for f in verdict.findings]
    assert "ZERO_MOCK_VIOLATION" in rule_names
    for f in verdict.findings:
        if f.rule_name == "ZERO_MOCK_VIOLATION":
            assert f.severity == "CRITICAL"


def test_judiciary_detects_and_rejects_silent_fallback() -> None:
    """Verify adversary inserting silent exception swallowing is REJECTED."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-FALLBACK")
    bundle = _make_task_bundle("TASK-FALLBACK")

    diff_fallback = (
        "diff --git a/src/client.py b/src/client.py\n"
        "--- a/src/client.py\n"
        "+++ b/src/client.py\n"
        "@@ -5,3 +5,5 @@\n"
        "+try:\n"
        "+    call_network()\n"
        "+except Exception:\n"
        "+    return []\n"
    )

    verdict = auditor.audit_diff(diff_text=diff_fallback, bundle=bundle, receipt=receipt)
    assert verdict.status == "REJECTED"
    rule_names = [f.rule_name for f in verdict.findings]
    assert "SILENT_FALLBACK_VIOLATION" in rule_names


def test_judiciary_rejects_tampered_receipt() -> None:
    """Verify receipt with altered fields fails cryptographic signature audit."""
    auditor = JudiciaryAuditor()
    valid_receipt = _make_valid_receipt("TASK-TAMPER")
    tampered_receipt = valid_receipt.model_copy(update={"task_id": "TASK-FORGED-ID"})
    bundle = _make_task_bundle("TASK-TAMPER")

    verdict = auditor.audit_diff(diff_text="", bundle=bundle, receipt=tampered_receipt)
    assert verdict.status == "REJECTED"
    assert len(verdict.findings) == 1
    finding = verdict.findings[0]
    assert finding.rule_name == "RECEIPT_SIGNATURE_TAMPERED"
    assert finding.severity == "CRITICAL"
    assert finding.filepath == "artifacts/receipts/receipt.json"
    assert finding.snippet == tampered_receipt.sha256_signature
    assert "Cryptographic SHA-256 signature verification failed" in finding.rationale


def test_judiciary_rejects_failing_gates_in_receipt() -> None:
    """Verify receipt with failing gate exit codes is rejected."""
    auditor = JudiciaryAuditor()
    g_fail = GateReport(
        gate_name="ruff",
        exit_code=1,
        duration_seconds=0.1,
        violations_count=3,
        raw_output_snippet="Syntax error",
    )
    g_pass = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    receipt = create_receipt(
        task_id="TASK-FAIL-GATES",
        commit_hash="c0ffee1234",
        gate_ruff=g_fail,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        receipt_id="rcpt_fail_001",
        epoch_index=1,
        timestamp_utc="2026-09-03T12:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
        correlation_id="corr_001",
        causation_id=None,
    )
    bundle = _make_task_bundle("TASK-FAIL-GATES")

    verdict = auditor.audit_diff(diff_text="", bundle=bundle, receipt=receipt)
    assert verdict.status == "REJECTED"
    assert len(verdict.findings) == 1
    finding = verdict.findings[0]
    assert finding.rule_name == "SUBSTRATE_GATE_FAILURE"
    assert finding.severity == "CRITICAL"
    assert finding.filepath == "artifacts/receipts/receipt.json"
    assert "ruff (exit 1)" in finding.snippet


def test_judiciary_detects_invariant_tampering() -> None:
    """Verify adversary attempting deletion of immutable invariants is REJECTED."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-TAMPER-INV")
    bundle = _make_task_bundle("TASK-TAMPER-INV")

    diff_tamper = (
        "diff --git a/01_INVARIANTS.md b/01_INVARIANTS.md\n"
        "--- a/01_INVARIANTS.md\n"
        "+++ b/01_INVARIANTS.md\n"
        "@@ -10,3 +10,1 @@\n"
        "-The worker must never violate the zero mock invariant rule.\n"
    )

    verdict = auditor.audit_diff(diff_text=diff_tamper, bundle=bundle, receipt=receipt)
    assert verdict.status == "REJECTED"
    rule_names = [f.rule_name for f in verdict.findings]
    assert "INVARIANT_TAMPERING" in rule_names
    finding = verdict.findings[0]
    assert finding.severity == "CRITICAL"
    assert finding.filepath == "01_INVARIANTS.md"
    assert "Attempted deletion of immutable Neocortex invariant rules" in finding.rationale


def test_judiciary_ignores_non_python_diff() -> None:
    """Verify non-python file diff additions do not trigger python mock/fallback checks."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-NON-PY")
    bundle = _make_task_bundle("TASK-NON-PY")

    diff_txt = (
        "diff --git a/notes.txt b/notes.txt\n"
        "--- a/notes.txt\n"
        "+++ b/notes.txt\n"
        "@@ -1,2 +1,3 @@\n"
        "+MagicMock is mentioned in this text note\n"
        "+except: pass\n"
    )

    verdict = auditor.audit_diff(diff_text=diff_txt, bundle=bundle, receipt=receipt)
    assert verdict.status == "APPROVED"
    assert len(verdict.findings) == 0


def test_extract_worktree_diff_safe(tmp_path: Path) -> None:
    """Verify extract_worktree_diff runs safely on clean directory."""
    auditor = JudiciaryAuditor()
    diff = auditor.extract_worktree_diff(tmp_path)
    assert isinstance(diff, str)


def test_extract_worktree_diff_real_git_and_mutants(tmp_path: Path) -> None:
    """Verify extract_worktree_diff handles git repositories and mutants path traversal."""
    import subprocess

    repo_dir = tmp_path / "git_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=repo_dir,
        capture_output=True,
        check=True,
    )

    file_a = repo_dir / "file.txt"
    file_a.write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, capture_output=True, check=True)

    # Modify file
    file_a.write_text("modified\n", encoding="utf-8")

    auditor = JudiciaryAuditor()
    diff = auditor.extract_worktree_diff(repo_dir)
    assert "modified" in diff

    # Nested mutants directory resolves to toplevel repo
    mutants_sub = repo_dir / "mutants" / "sub"
    mutants_sub.mkdir(parents=True)
    diff_nested = auditor.extract_worktree_diff(mutants_sub)
    assert "modified" in diff_nested


def test_audit_diff_all_substrate_gate_failures_exact() -> None:
    """Verify exact snippet and rationale when ruff, mypy, pytest, mutmut all fail."""
    auditor = JudiciaryAuditor()
    receipt = create_receipt(
        task_id="TASK-FAIL-ALL",
        commit_hash="c0ffee1234",
        gate_ruff=GateReport(
            gate_name="ruff",
            exit_code=1,
            duration_seconds=0.1,
            violations_count=1,
            raw_output_snippet="err",
        ),
        gate_mypy=GateReport(
            gate_name="mypy",
            exit_code=2,
            duration_seconds=0.1,
            violations_count=2,
            raw_output_snippet="err",
        ),
        gate_pytest=GateReport(
            gate_name="pytest",
            exit_code=3,
            duration_seconds=0.1,
            violations_count=3,
            raw_output_snippet="err",
        ),
        gate_mutmut=GateReport(
            gate_name="mutmut",
            exit_code=4,
            duration_seconds=0.1,
            violations_count=4,
            raw_output_snippet="err",
        ),
        receipt_id="rcpt_all_fail",
        epoch_index=1,
        timestamp_utc="2026-09-03T12:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
    )
    bundle = _make_task_bundle("TASK-FAIL-ALL")
    verdict = auditor.audit_diff(diff_text="", bundle=bundle, receipt=receipt)
    assert verdict.status == "REJECTED"
    assert len(verdict.findings) == 1
    f = verdict.findings[0]
    assert f.rule_name == "SUBSTRATE_GATE_FAILURE"
    assert f.severity == "CRITICAL"
    assert f.filepath == "artifacts/receipts/receipt.json"
    assert f.snippet == "ruff (exit 1), mypy (exit 2), pytest (exit 3), mutmut (exit 4)"
    assert f.rationale == "Candidate failed deterministic substrate mechanical gates."


def test_audit_diff_all_mock_patterns_exact() -> None:
    """Verify each individual mock pattern generates exact description and rationale."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-MOCKS")
    bundle = _make_task_bundle("TASK-MOCKS")

    cases = [
        ("MagicMock", "MagicMock instantiation detected"),
        ("unittest.mock", "unittest.mock import or usage detected"),
        ("mock.patch", "mock.patch usage detected"),
        ("assert mock", "assert mock assertion gaming detected"),
        ("mock == True", "mock == True assertion gaming detected"),
    ]

    for pattern_str, expected_desc in cases:
        diff_text = (
            "diff --git a/src/test.py b/src/test.py\n"
            "--- a/src/test.py\n"
            "+++ b/src/test.py\n"
            "@@ -1,1 +1,2 @@\n"
            f"+# test {pattern_str}\n"
        )
        verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)
        assert verdict.status == "REJECTED"
        assert len(verdict.findings) == 1
        f = verdict.findings[0]
        assert f.rule_name == "ZERO_MOCK_VIOLATION"
        assert f.severity == "CRITICAL"
        assert f.filepath == "src/test.py"
        assert f.rationale == f"{expected_desc}. Violates Invariant Article I & Article III."


def test_audit_diff_all_single_line_fallback_patterns_exact() -> None:
    """Verify single-line fallback patterns generate exact descriptions and rationales."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-FALLBACKS")
    bundle = _make_task_bundle("TASK-FALLBACKS")

    empty_handlers = [
        "except: pass",
        "except Exception: pass",
        "except: ...",
        "except ValueError: ...",
    ]
    for line in empty_handlers:
        diff_text = (
            "diff --git a/src/mod.py b/src/mod.py\n"
            "--- a/src/mod.py\n"
            "+++ b/src/mod.py\n"
            f"@@ -1,1 +1,2 @@\n+{line}\n"
        )
        verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)
        assert verdict.status == "REJECTED"
        f = verdict.findings[0]
        assert f.rule_name == "SILENT_FALLBACK_VIOLATION"
        assert f.severity == "CRITICAL"
        assert f.rationale == (
            "Empty exception handler (except ...: pass) detected. "
            "Violates Invariant Article III (Fail-Closed Fallbacks)."
        )

    silent_returns = [
        "except: return []",
        "except: return {}",
        "except: return None",
        "except: return False",
        "except: return 0",
        "except: return ''",
        "except: return",
        "except KeyError: return []",
        "except Exception: return None",
    ]
    for line in silent_returns:
        diff_text = (
            "diff --git a/src/mod.py b/src/mod.py\n"
            "--- a/src/mod.py\n"
            "+++ b/src/mod.py\n"
            f"@@ -1,1 +1,2 @@\n+{line}\n"
        )
        verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)
        assert verdict.status == "REJECTED"
        f = verdict.findings[0]
        assert f.rule_name == "SILENT_FALLBACK_VIOLATION"
        assert f.severity == "CRITICAL"
        assert f.rationale == (
            "Silent fallback return in exception handler detected. "
            "Violates Invariant Article III (Fail-Closed Fallbacks)."
        )


def test_audit_diff_all_multiline_fallback_patterns_exact() -> None:
    """Verify multi-line exception fallback handling and line number tracking."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-MULTI-FB")
    bundle = _make_task_bundle("TASK-MULTI-FB")

    multiline_bodies = [
        "pass",
        "...",
        "return []",
        "return {}",
        "return None",
        "return False",
        "return 0",
        "return ''",
        "return",
    ]
    for body in multiline_bodies:
        diff_text = (
            "diff --git a/src/worker.py b/src/worker.py\n"
            "--- a/src/worker.py\n"
            "+++ b/src/worker.py\n"
            "@@ -10,1 +10,3 @@\n"
            "+except Exception:\n"
            f"+    {body}\n"
        )
        verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)
        assert verdict.status == "REJECTED"
        f = verdict.findings[0]
        assert f.rule_name == "SILENT_FALLBACK_VIOLATION"
        assert f.severity == "CRITICAL"
        assert f.filepath == "src/worker.py"
        assert f.line_number == 5  # line index of except line in diff
        assert f.rationale == (
            "Silent exception fallback detected across lines. "
            "Violates Invariant Article III (Fail-Closed Fallbacks)."
        )
        assert f.snippet == f"except ... -> {body}"

    # Multi-line except reset when a new file begins
    diff_reset = (
        "diff --git a/src/a.py b/src/a.py\n"
        "--- a/src/a.py\n"
        "+++ b/src/a.py\n"
        "@@ -1,1 +1,2 @@\n"
        "+except:\n"
        "diff --git a/src/b.py b/src/b.py\n"
        "--- a/src/b.py\n"
        "+++ b/src/b.py\n"
        "@@ -1,1 +1,2 @@\n"
        "+pass\n"
    )
    verdict_reset = auditor.audit_diff(diff_text=diff_reset, bundle=bundle, receipt=receipt)
    assert verdict_reset.status == "APPROVED"
    assert len(verdict_reset.findings) == 0


def test_audit_diff_invariant_tampering_all_keywords() -> None:
    """Verify deletion of lines with invariant, must, rule, never, forbidden in 01_INVARIANTS.md."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-INV-KW")
    bundle = _make_task_bundle("TASK-INV-KW")

    keywords = ["invariant", "must", "rule", "never", "forbidden"]
    for kw in keywords:
        diff_text = (
            "diff --git a/01_INVARIANTS.md b/01_INVARIANTS.md\n"
            "--- a/01_INVARIANTS.md\n"
            "+++ b/01_INVARIANTS.md\n"
            "@@ -5,2 +5,1 @@\n"
            f"-Deleted line with {kw} constraint\n"
        )
        verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)
        assert verdict.status == "REJECTED"
        assert len(verdict.findings) == 1
        f = verdict.findings[0]
        assert f.rule_name == "INVARIANT_TAMPERING"
        assert f.severity == "CRITICAL"
        assert f.filepath == "01_INVARIANTS.md"
        assert f.rationale == "Attempted deletion of immutable Neocortex invariant rules."

    # Deletion in non-invariant file or without keywords
    diff_safe = (
        "diff --git a/01_INVARIANTS.md b/01_INVARIANTS.md\n"
        "--- a/01_INVARIANTS.md\n"
        "+++ b/01_INVARIANTS.md\n"
        "@@ -5,2 +5,1 @@\n"
        "-# Just a regular markdown section header\n"
    )
    verdict_safe = auditor.audit_diff(diff_text=diff_safe, bundle=bundle, receipt=receipt)
    assert verdict_safe.status == "APPROVED"


def test_audit_diff_verdict_synthesis_and_rationale_exact() -> None:
    """Verify exact synthesis of summary rationale for APPROVED, QUARANTINED, and REJECTED."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-SYNTHESIS")
    bundle = _make_task_bundle("TASK-SYNTHESIS")

    # 1. APPROVED
    v_app = auditor.audit_diff(diff_text="", bundle=bundle, receipt=receipt)
    assert v_app.status == "APPROVED"
    assert v_app.summary_rationale == (
        "Adversarial Judiciary APPROVED candidate: Zero mocks, zero silent fallbacks, "
        "bit-exact receipt signature verified."
    )
    assert v_app.task_id == bundle.task_id

    # 2. None diff_text defaults to empty string
    v_none = auditor.audit_diff(diff_text=None, bundle=bundle, receipt=receipt)  # type: ignore[arg-type]
    assert v_none.status == "APPROVED"

    # 3. REJECTED with critical findings count
    v_rej = auditor.audit_diff(
        diff_text="diff --git a/src/x.py b/src/x.py\n+++ b/src/x.py\n@@ -1 +1,2 @@\n+MagicMock()\n",
        bundle=bundle,
        receipt=receipt,
    )
    assert v_rej.status == "REJECTED"
    assert (
        v_rej.summary_rationale
        == "Adversarial Judiciary REJECTED candidate: 1 critical invariant violations found."
    )


def test_extract_worktree_diff_mutants_and_fallbacks_exhaustive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exhaustively verify extract_worktree_diff arguments, mutants path handling, and fallbacks."""
    import subprocess

    auditor = JudiciaryAuditor()
    calls: list[dict[str, object]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": cmd, **kwargs})
        if cmd == ["git", "rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="/repo/root\n", stderr="")
        if cmd == ["git", "diff", "HEAD"]:
            return subprocess.CompletedProcess(
                cmd, returncode=0, stdout="diff --git a/f b/f\n", stderr=""
            )
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # 1. Path with "mutants" in parts calls git rev-parse with exact kwargs
    target_path = tmp_path / "mutants" / "workdir"
    target_path.mkdir(parents=True)
    res = auditor.extract_worktree_diff(target_path)
    assert res == "diff --git a/f b/f\n"
    assert len(calls) == 2

    # Verify rev-parse call parameters bit-exact
    c0 = calls[0]
    assert c0["cmd"] == ["git", "rev-parse", "--show-toplevel"]
    assert c0["cwd"] == target_path.resolve()
    assert c0["capture_output"] is True
    assert c0["text"] is True
    assert c0["encoding"] == "utf-8"
    assert c0["errors"] == "replace"
    assert c0["check"] is False
    assert c0["timeout"] == 5.0

    # Verify git diff HEAD called with cwd == Path("/repo/root")
    c1 = calls[1]
    assert c1["cmd"] == ["git", "diff", "HEAD"]
    assert c1["cwd"] == Path("/repo/root")
    assert c1["capture_output"] is True
    assert c1["text"] is True
    assert c1["encoding"] == "utf-8"
    assert c1["errors"] == "replace"
    assert c1["check"] is False

    # 2. Path without "mutants" does not call rev-parse
    calls.clear()
    non_mutant_path = tmp_path / "clean_dir"
    non_mutant_path.mkdir()
    res_clean = auditor.extract_worktree_diff(non_mutant_path)
    assert res_clean == "diff --git a/f b/f\n"
    assert len(calls) == 1
    assert calls[0]["cmd"] == ["git", "diff", "HEAD"]
    assert calls[0]["cwd"] == non_mutant_path

    # 3. rev-parse returns returncode != 0 -> fallback to resolved_path
    calls.clear()

    def fake_run_fail_revparse(
        cmd: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": cmd, **kwargs})
        if cmd == ["git", "rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="err")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="diff output", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run_fail_revparse)
    res_revfail = auditor.extract_worktree_diff(target_path)
    assert res_revfail == "diff output"
    assert calls[1]["cwd"] == target_path.resolve()

    # 4. rev-parse raises OSError -> fallback to resolved_path
    calls.clear()

    def fake_run_oserror(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": cmd, **kwargs})
        if cmd == ["git", "rev-parse", "--show-toplevel"]:
            raise OSError("git not found")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="diff output", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run_oserror)
    assert auditor.extract_worktree_diff(target_path) == "diff output"
    assert calls[1]["cwd"] == target_path.resolve()

    # 5. rev-parse raises SubprocessError -> fallback to resolved_path
    calls.clear()

    def fake_run_suberror(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": cmd, **kwargs})
        if cmd == ["git", "rev-parse", "--show-toplevel"]:
            raise subprocess.SubprocessError("timed out")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="diff output", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run_suberror)
    assert auditor.extract_worktree_diff(target_path) == "diff output"

    # 6. git diff HEAD returncode != 0 -> returns ""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd, returncode=1, stdout="err", stderr="err"
        ),
    )
    assert auditor.extract_worktree_diff(non_mutant_path) == ""

    # 7. git diff HEAD stdout is None -> returns ""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd, returncode=0, stdout=None, stderr=""
        ),
    )
    assert auditor.extract_worktree_diff(non_mutant_path) == ""


def _bare_diff(path: str, *added_lines: str) -> str:
    """Build a bare-`+++ <path>` new-file diff (the J1 live shape, no `b/`)."""
    lines = ["--- /dev/null\n", f"+++ {path}\n", "@@ -0,0 +1 @@\n"]
    lines.extend(f"+{line}\n" for line in added_lines)
    return "".join(lines)


def _prefixed_diff(path: str, *added_lines: str) -> str:
    """Same body with `+++ b/` headers (the 2-byte contrast arm)."""
    lines = [
        f"diff --git a/{path} b/{path}\n",
        f"--- a/{path}\n",
        f"+++ b/{path}\n",
        "@@ -0,0 +1 @@\n",
    ]
    lines.extend(f"+{line}\n" for line in added_lines)
    return "".join(lines)


def test_audit_diff_attributes_bare_triple_plus_headers() -> None:
    """Verify bare-`+++ <path>` diffs attribute and scan (J1 fix)."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-J1-BARE")
    bundle = _make_task_bundle("TASK-J1-BARE")

    verdict = auditor.audit_diff(
        diff_text=_bare_diff(
            "tests/unit/test_integration_runner_pins.py",
            "from unittest.mock import AsyncMock",
        ),
        bundle=bundle,
        receipt=receipt,
    )
    assert verdict.status == "REJECTED"
    rule_names = [f.rule_name for f in verdict.findings]
    assert "ZERO_MOCK_VIOLATION" in rule_names
    mock_hits = [f for f in verdict.findings if f.rule_name == "ZERO_MOCK_VIOLATION"]
    assert mock_hits[0].filepath == "tests/unit/test_integration_runner_pins.py"
    assert mock_hits[0].severity == "CRITICAL"


def test_audit_diff_bare_and_b_prefixed_contrast_agrees() -> None:
    """Verify the J1 2-byte contrast collapses: bare and `b/` scan alike."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-J1-CONTRAST")
    bundle = _make_task_bundle("TASK-J1-CONTRAST")
    body = ("from unittest.mock import AsyncMock",)

    bare = auditor.audit_diff(
        diff_text=_bare_diff("src/svc.py", *body), bundle=bundle, receipt=receipt
    )
    prefixed = auditor.audit_diff(
        diff_text=_prefixed_diff("src/svc.py", *body), bundle=bundle, receipt=receipt
    )
    assert bare.status == "REJECTED"
    assert prefixed.status == "REJECTED"
    assert [f.rule_name for f in bare.findings] == [f.rule_name for f in prefixed.findings]
    assert [f.snippet for f in bare.findings] == [f.snippet for f in prefixed.findings]


def test_audit_diff_bare_clean_diff_approved() -> None:
    """Verify bare attribution does not over-attribute: clean bare diff APPROVED."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-J1-CLEAN")
    bundle = _make_task_bundle("TASK-J1-CLEAN")

    verdict = auditor.audit_diff(
        diff_text=_bare_diff(
            "src/service.py",
            "def calculate_total(items: list[int]) -> int:",
            "    return sum(items)",
        ),
        bundle=bundle,
        receipt=receipt,
    )
    assert verdict.status == "APPROVED"
    assert len(verdict.findings) == 0


def test_audit_diff_dev_null_never_attributes() -> None:
    """Verify `+++ /dev/null` leaves attribution unchanged (deleted = unscannable)."""
    auditor = JudiciaryAuditor()
    receipt = _make_valid_receipt("TASK-J1-DEVNULL")
    bundle = _make_task_bundle("TASK-J1-DEVNULL")

    diff_text = (
        "--- a/src/real.py\n"
        "+++ b/src/real.py\n"
        "@@ -1 +1 @@\n"
        "--- a/src/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "+from unittest.mock import AsyncMock\n"
    )
    verdict = auditor.audit_diff(diff_text=diff_text, bundle=bundle, receipt=receipt)
    assert verdict.status == "REJECTED"
    mock_hits = [f for f in verdict.findings if f.rule_name == "ZERO_MOCK_VIOLATION"]
    assert len(mock_hits) == 1
    assert mock_hits[0].filepath == "src/real.py"


def test_audit_diff_bare_multifile_and_gate_fail_closed() -> None:
    """Verify multi-file bare attribution + gate-failure fail-closed stays intact."""
    auditor = JudiciaryAuditor()
    bundle = _make_task_bundle("TASK-J1-MULTI")

    multi = _bare_diff("docs/notes.txt", "from unittest.mock import AsyncMock")
    multi += _bare_diff("src/other.py", "from unittest.mock import AsyncMock")
    verdict = auditor.audit_diff(
        diff_text=multi,
        bundle=bundle,
        receipt=_make_valid_receipt("TASK-J1-MULTI"),
    )
    assert verdict.status == "REJECTED"
    mock_hits = [f for f in verdict.findings if f.rule_name == "ZERO_MOCK_VIOLATION"]
    assert [f.filepath for f in mock_hits] == ["src/other.py"]

    g_fail = GateReport(
        gate_name="ruff",
        exit_code=1,
        duration_seconds=0.1,
        violations_count=3,
        raw_output_snippet="Syntax error",
    )
    g_pass = GateReport(
        gate_name="gate",
        exit_code=0,
        duration_seconds=0.1,
        violations_count=0,
        raw_output_snippet="OK",
    )
    failing_receipt = create_receipt(
        task_id="TASK-J1-GATES",
        commit_hash="c0ffee1234",
        gate_ruff=g_fail,
        gate_mypy=g_pass,
        gate_pytest=g_pass,
        gate_mutmut=g_pass,
        receipt_id="rcpt_j1_gates",
        epoch_index=1,
        timestamp_utc="2026-09-03T12:00:00Z",
        python_version="3.12.4",
        os_platform="Windows",
        correlation_id="corr_001",
        causation_id=None,
    )
    gated = auditor.audit_diff(
        diff_text=_bare_diff("src/svc.py", "from unittest.mock import AsyncMock"),
        bundle=bundle,
        receipt=failing_receipt,
    )
    assert gated.status == "REJECTED"
    gated_rules = [f.rule_name for f in gated.findings]
    assert "SUBSTRATE_GATE_FAILURE" in gated_rules
    assert "ZERO_MOCK_VIOLATION" in gated_rules


def test_worker_constraints_mirror_enforced_patterns() -> None:
    """Worker-visible lines track the enforced pattern lists (Fix 3)."""
    assert len(WORKER_CONSTRAINTS) == 4
    assert len(MOCK_PATTERNS) > 0
    assert len(FALLBACK_PATTERNS) > 0
    assert len(SECRET_PATTERNS) > 0
    joined = "\n".join(WORKER_CONSTRAINTS)
    assert "unittest.mock" in joined
    assert "Hand-rolled fakes" in joined
    assert "pass/..." in joined
    assert "api_key" in joined
    assert "01_INVARIANTS.md" in joined
    assert "interfaces.py" in joined
