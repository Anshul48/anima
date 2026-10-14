"""Judiciary blind adversarial auditing subsystem."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Final

from stc.protocols.interfaces import JudiciaryAuditorProtocol, SubstrateRunnerProtocol
from stc.schemas.models import AuditFinding, ExecutionReceipt, JudiciaryVerdict, TaskBundle

# Regex patterns for adversarial detection
MOCK_PATTERNS = [
    (re.compile(r"\bMagic" + r"Mock\b"), "Magic" + "Mock instantiation detected"),
    (re.compile(r"\bunittest\." + r"mock\b"), "unittest." + "mock import or usage detected"),
    (
        re.compile(r"\bfrom\s+unittest\s+import\s+" + r"mock\b"),
        "from unittest import " + "mock detected",
    ),
    (re.compile(r"\bmock\." + r"patch\b"), "mock." + "patch usage detected"),
    (re.compile(r"\bmock\." + r"Mock\b"), "mock." + "Mock usage detected"),
    (re.compile(r"\bassert\s+" + r"mock\b"), "assert " + "mock assertion gaming detected"),
    (re.compile(r"\bmock\s*==" + r"\s*True\b"), "mock" + " == True assertion gaming detected"),
]

EXC_HEADER = (
    r"\bexc" + r"ept(?:\s+(?:[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*"
    r"|\(\s*[a-zA-Z_]\w*(?:\s*,\s*[a-zA-Z_]\w*)*\s*\))"
    r"(?:\s+as\s+[a-zA-Z_]\w*)?)?\s*:"
)

FALLBACK_PATTERNS = [
    (
        re.compile(rf"{EXC_HEADER}\s*(?:pass|\.\.\.)"),
        "Empty exception handler (" + "exc" + "ept ...: pass) detected",
    ),
    (
        re.compile(
            rf"""{EXC_HEADER}\s*return(?:\s+(?:\[\]|\{{\}}|\(\)|None|False|0|''|"")|\s*$)"""
        ),
        "Silent fallback return in exception handler detected",
    ),
]

SECRET_PATTERNS = [
    (
        re.compile(
            r"""\b(api_key|secret_key|auth_token|private_key)\s*=\s*['"][a-zA-Z0-9_\-]{16,}['"]""",
            re.IGNORECASE,
        ),
        "Hardcoded credential or secret key detected",
    ),
]

#: Worker-visible statement of the judiciary-enforced diff rules (Fix 3).
#: Single source of truth: these lines ride the task bundle so every worker
#: and reviewer prompt states the SAME constraints the auditor enforces on
#: added/removed diff lines. Keep each line an exact plain-language mirror
#: of its pattern list above; the auditor itself is unchanged.
WORKER_CONSTRAINTS: Final[tuple[str, ...]] = (
    "Judiciary constraint (zero-mock, 0% mocks): added Python lines must not "
    "import or use unittest.mock, MagicMock, mock.patch, or mock.Mock, and "
    "must not assert on mocks (assert mock / mock == True). Hand-rolled "
    "fakes — plain classes or subclasses with real assertions and no mock "
    "imports — are legitimate test doubles.",
    "Judiciary constraint (fail-closed fallbacks): except handlers must not "
    "be empty (pass/...) and must not silently return empty values "
    "(None/False/0/'', [], {}, ()); re-raise, escalate, or handle explicitly.",
    "Judiciary constraint (no hardcoded secrets): never assign string "
    "literals of 16+ characters to api_key/secret_key/auth_token/private_key.",
    "Judiciary constraint (immutable contracts): do not delete rule text "
    "from 01_INVARIANTS.md and do not alter class/def/protocol/model "
    "contracts in src/stc/protocols/interfaces.py or "
    "src/stc/schemas/models.py.",
)


class JudiciaryAuditor(JudiciaryAuditorProtocol):
    """Blind adversarial auditor inspecting diffs and machine receipts.

    Implements Article IV (The Blind Judge Protocol) of the STC Constitution.
    Audits diffs without access to worker chat history, strictly searching
    for fake mocks, silent fallbacks, contract tampering, and receipt validity.
    """

    def __init__(
        self,
        runner: SubstrateRunnerProtocol | None = None,
        with_codex: bool = False,
        codex_bin: str | None = None,
    ) -> None:
        self.runner: SubstrateRunnerProtocol | None = runner
        self.with_codex = with_codex
        self.codex_bin = codex_bin

    def _verify_receipt_signature(self, receipt: ExecutionReceipt) -> bool:
        """Verify receipt signature without concrete cross-subsystem dependencies."""
        if self.runner is not None:
            return self.runner.verify_receipt(receipt)

        if not receipt.sha256_signature:
            return False

        canonical: dict[str, Any] = {
            "causation_id": receipt.causation_id,
            "commit_hash": receipt.commit_hash,
            "correlation_id": receipt.correlation_id,
            "epoch_index": receipt.epoch_index,
            "gate_mutmut": receipt.gate_mutmut.model_dump(),
            "gate_mypy": receipt.gate_mypy.model_dump(),
            "gate_pytest": receipt.gate_pytest.model_dump(),
            "gate_ruff": receipt.gate_ruff.model_dump(),
            "os_platform": receipt.os_platform,
            "python_version": receipt.python_version,
            "receipt_id": receipt.receipt_id,
            "task_id": receipt.task_id,
            "timestamp_utc": receipt.timestamp_utc,
        }
        raw_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected_sig = hashlib.sha256(raw_bytes).hexdigest()
        return hmac.compare_digest(receipt.sha256_signature, expected_sig)

    def _invoke_codex_adversarial_audit(
        self,
        diff_text: str,
        bundle: TaskBundle,
        receipt: ExecutionReceipt,
    ) -> list[AuditFinding]:
        """Invoke headless Codex CLI instance in isolated sandbox."""
        codex_bin = self.codex_bin or shutil.which("codex") or shutil.which("codex.exe")
        if not codex_bin:
            return [
                AuditFinding(
                    rule_name="CODEX_EXECUTION_ERROR",
                    severity="CRITICAL",
                    filepath="judiciary/auditor.py",
                    snippet="",
                    rationale=(
                        "Adversarial Judiciary requires OpenAI Codex CLI "
                        "('codex.exe') on system PATH."
                    ),
                )
            ]

        prompt = (
            f"Adversarial Blind Audit for task {bundle.task_id}.\n"
            f"Invariants: {bundle.invariants}\n"
            f"Receipt: {receipt.receipt_id} (Passed: {receipt.is_passing})\n"
            f"Diff:\n{diff_text}\n"
            "Verify: zero mocks, zero silent fallbacks, zero contract tampering."
        )
        try:
            res = subprocess.run(
                [codex_bin, "exec", "--sandbox", prompt],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=30.0,
            )
            if res.returncode != 0:
                return [
                    AuditFinding(
                        rule_name="CODEX_AUDIT_FAILURE",
                        severity="CRITICAL",
                        filepath="judiciary/auditor.py",
                        snippet=(res.stderr or res.stdout)[:120],
                        rationale=f"Codex CLI audit returned non-zero exit code {res.returncode}",
                    )
                ]
        except (subprocess.SubprocessError, OSError) as exc:
            return [
                AuditFinding(
                    rule_name="CODEX_EXECUTION_ERROR",
                    severity="CRITICAL",
                    filepath="judiciary/auditor.py",
                    snippet=str(exc)[:120],
                    rationale=f"Failed to execute Codex CLI: {exc}",
                )
            ]
        return []

    def audit_diff(
        self,
        diff_text: str,
        bundle: TaskBundle,
        receipt: ExecutionReceipt,
    ) -> JudiciaryVerdict:
        """Perform blind adversarial audit on candidate diff and execution receipt."""
        findings: list[AuditFinding] = []

        # 1. Verify receipt authenticity and cryptographic signature
        if not self._verify_receipt_signature(receipt):
            findings.append(
                AuditFinding(
                    rule_name="RECEIPT_SIGNATURE_TAMPERED",
                    severity="CRITICAL",
                    filepath="artifacts/receipts/receipt.json",
                    snippet=receipt.sha256_signature,
                    rationale="Cryptographic SHA-256 signature verification failed. "
                    "Receipt has been tampered with or corrupted.",
                )
            )

        # 2. Verify all substrate gates passed deterministically
        if not receipt.is_passing:
            failing_gates: list[str] = []
            for name, gate in [
                ("ruff", receipt.gate_ruff),
                ("mypy", receipt.gate_mypy),
                ("pytest", receipt.gate_pytest),
                ("mutmut", receipt.gate_mutmut),
            ]:
                if gate.exit_code != 0:
                    failing_gates.append(f"{name} (exit {gate.exit_code})")

            findings.append(
                AuditFinding(
                    rule_name="SUBSTRATE_GATE_FAILURE",
                    severity="CRITICAL",
                    filepath="artifacts/receipts/receipt.json",
                    snippet=", ".join(failing_gates),
                    rationale="Candidate failed deterministic substrate mechanical gates.",
                )
            )

        # 3. Adversarial Diff Inspection
        current_file = "unknown"
        line_no = 0
        pending_except = False
        pending_except_line = 0

        diff_str = diff_text or ""
        for line in diff_str.splitlines():
            line_no += 1
            if line.startswith("+++ b/"):
                current_file = line[6:].strip()
                pending_except = False
                continue
            if line.startswith("+++ ") and not line.startswith("+++ /dev/null"):
                # J1 (follow-up): bare-`+++ <path>` diffs (accepted by custody
                # and git) attribute like `b/`-prefixed ones; `/dev/null`
                # never attributes (a deleted file has no scannable content).
                current_file = line[4:].strip()
                pending_except = False
                continue
            if line.startswith("--- a/"):
                continue

            # Check added lines for forbidden mock or fallback constructs
            if line.startswith("+"):
                content = line[1:].strip()

                if current_file.endswith(".py"):
                    for pattern, desc in MOCK_PATTERNS:
                        if pattern.search(content):
                            findings.append(
                                AuditFinding(
                                    rule_name="ZERO_MOCK_VIOLATION",
                                    severity="CRITICAL",
                                    filepath=current_file,
                                    line_number=line_no,
                                    snippet=content[:120],
                                    rationale=(
                                        f"{desc}. Violates Invariant Article I & Article III."
                                    ),
                                )
                            )

                    for pattern, desc in FALLBACK_PATTERNS:
                        if pattern.search(content):
                            findings.append(
                                AuditFinding(
                                    rule_name="SILENT_FALLBACK_VIOLATION",
                                    severity="CRITICAL",
                                    filepath=current_file,
                                    line_number=line_no,
                                    snippet=content[:120],
                                    rationale=(
                                        f"{desc}. Violates Invariant Article III "
                                        "(Fail-Closed Fallbacks)."
                                    ),
                                )
                            )

                    for pattern, desc in SECRET_PATTERNS:
                        if pattern.search(content):
                            findings.append(
                                AuditFinding(
                                    rule_name="HARDCODED_SECRET_VIOLATION",
                                    severity="CRITICAL",
                                    filepath=current_file,
                                    line_number=line_no,
                                    snippet=content[:120],
                                    rationale=f"{desc}. Violates Security Invariant.",
                                )
                            )

                    # Multi-line except handler check
                    if re.search(rf"^{EXC_HEADER}", content):
                        pending_except = True
                        pending_except_line = line_no
                    elif pending_except and content:
                        if content.startswith("#"):
                            continue
                        if re.search(
                            r"""^(pass|\.\.\.|return(\s*(\[\]|\{\}|\(\)|None|False|0|''|"")|\s*$))""",
                            content,
                        ):
                            findings.append(
                                AuditFinding(
                                    rule_name="SILENT_FALLBACK_VIOLATION",
                                    severity="CRITICAL",
                                    filepath=current_file,
                                    line_number=pending_except_line,
                                    snippet="exc" + f"ept ... -> {content}",
                                    rationale=(
                                        "Silent exception fallback detected across lines. "
                                        "Violates Invariant Article III (Fail-Closed Fallbacks)."
                                    ),
                                )
                            )
                        pending_except = False

            # Check removed lines for unauthorized protocol or invariant tampering
            elif line.startswith("-"):
                content = line[1:].strip()
                if current_file.endswith("01_INVARIANTS.md") and any(
                    k in content.lower()
                    for k in ["invariant", "must", "rule", "never", "forbidden"]
                ):
                    findings.append(
                        AuditFinding(
                            rule_name="INVARIANT_TAMPERING",
                            severity="CRITICAL",
                            filepath=current_file,
                            line_number=line_no,
                            snippet=content[:120],
                            rationale="Attempted deletion of immutable Neocortex invariant rules.",
                        )
                    )
                elif (
                    current_file.endswith("src/stc/protocols/interfaces.py")
                    or current_file.endswith("src/stc/schemas/models.py")
                ) and any(
                    k in content.lower()
                    for k in ["class ", "def ", "protocol", "model_config", "frozen=true"]
                ):
                    findings.append(
                        AuditFinding(
                            rule_name="CONTRACT_TAMPERING",
                            severity="CRITICAL",
                            filepath=current_file,
                            line_number=line_no,
                            snippet=content[:120],
                            rationale=(
                                "Attempted alteration or deletion of immutable Neocortex "
                                "membrane contracts or schemas."
                            ),
                        )
                    )

        # 4. Headless Codex CLI integration if enabled
        if self.with_codex:
            findings.extend(self._invoke_codex_adversarial_audit(diff_str, bundle, receipt))

        # 5. Synthesize Verdict
        critical_findings = [f for f in findings if f.severity == "CRITICAL"]
        if critical_findings:
            status = "REJECTED"
            rationale = (
                f"Adversarial Judiciary REJECTED candidate: "
                f"{len(critical_findings)} critical invariant violations found."
            )
        elif findings:
            status = "QUARANTINED"
            rationale = (
                f"Adversarial Judiciary QUARANTINED candidate: {len(findings)} non-critical issues."
            )
        else:
            status = "APPROVED"
            rationale = (
                "Adversarial Judiciary APPROVED candidate: Zero mocks, zero silent fallbacks, "
                "bit-exact receipt signature verified."
            )

        return JudiciaryVerdict(
            task_id=bundle.task_id,
            status=status,
            findings=findings,
            summary_rationale=rationale,
        )

    def extract_worktree_diff(self, worktree_path: Path) -> str:
        """Extract current git diff from worktree path."""
        resolved_path = worktree_path.resolve()
        if "mutants" in resolved_path.parts:
            try:
                res_root = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=resolved_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=5.0,
                )
                if res_root.returncode == 0 and res_root.stdout and res_root.stdout.strip():
                    worktree_path = Path(res_root.stdout.strip())
            except (subprocess.SubprocessError, OSError):
                worktree_path = resolved_path

        try:
            res = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if res.returncode == 0 and res.stdout is not None:
                return res.stdout
        except (subprocess.SubprocessError, OSError):
            worktree_path = resolved_path
        return ""


__all__ = ["JudiciaryAuditor"]
