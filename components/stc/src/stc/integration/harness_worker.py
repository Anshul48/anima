"""CLI-harness worker: a WorkerProtocol over B1-verified native CLI shapes (P03).

A ``HarnessWorker`` renders a TaskBundle to a prompt (preserving
``[source:...]`` citations, F9), executes it inside the leased worktree via a
CLI harness, enforces a dispatch timeout, requires ``is_success`` (F8), and
returns the chaperone's notary custody report. Every subprocess attempt is
spend-logged (try/finally, retry = 2 rows) with a pre-dispatch cap check
(F11); breaches move to quarantine with a violation record (F5) and the
quarantine-owning wrapper transitions the lease (F6).

Live execution uses the B1-established NATIVE argv shapes (subprocess, no
shell, prompt via stdin/``-p``/``--prompt-file`` per shape) because the pinned
prompt-kit command builder routes codex through dead WSL interop and emits a
muse flag order muse 1.2.1 rejects (readiness R1). The prompt-kit import still
resolves to the P00-pinned tree (F3c): the ``mock`` path runs pinned
``get_harness("mock").execute(...)`` and native results use the pinned
``HarnessResult`` type, loaded via importlib so this module stays clean under
``mypy --strict`` (the kit ships no ``py.typed``).

Gateway calls (role="gateway") run under a stricter fix-tranche profile
(INT-2026-09-14.1, D15): fresh OS-temp scratch cwd (never a repo), codex
read-only sandbox + --ephemeral, -o last-message capture (B1 pick), and a
post-call tracked-status assertion that fails closed. Worker/dispatch argv and
behavior are unchanged by that delta.

F1 (follow-up): every failed attempt appends a record with FULL stdout +
stderr, exit status, effective model/profile, duration, and candidate
identity to the failure-evidence sidecar next to the spend ledger; the ledger
note keeps a short pointer, never the only copy.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

from stc.core.errors import WorktreeError
from stc.integration.lease_git import resolve_stc_root
from stc.orchestrator.dispatch import ChaperoneWorker, ConfinementViolationError
from stc.protocols.interfaces import WorkerProtocol
from stc.schemas.models import TaskBundle, WorktreeLease
from stc.worktree.manager import WorktreeManager

logger = logging.getLogger(__name__)

__all__ = [
    "API_HARNESS_NAMES",
    "CLI_HARNESS_NAMES",
    "FAILURE_EVIDENCE_VERSION",
    "GATEWAY_CONFINEMENT_REPO",
    "GATEWAY_ROLE",
    "NOTE_BUDGET",
    "CritiqueProvenance",
    "GatewayConfinementError",
    "HandshakeReport",
    "HarnessConfigError",
    "HarnessWorker",
    "SpendCapExceededError",
    "SpendLedger",
    "assert_tracked_status_unchanged",
    "build_gateway_command",
    "build_native_command",
    "default_runner",
    "default_spend_path",
    "dispatch_with_quarantine",
    "failure_evidence_path",
    "failure_note_pointer",
    "harness_worker_fn",
    "render_bundle_prompt",
    "run_harness_attempt",
    "snapshot_tracked_status",
    "sweep_prompt_kit_tmp",
    "write_failure_evidence",
]

#: CLI harnesses allowed for live execution (F11 closed world).
CLI_HARNESS_NAMES = frozenset({"codex", "agy", "agy2", "agy3", "agy4", "muse"})

#: Registry names that imply API-key spend or non-executing harnesses (F11/R5).
API_HARNESS_NAMES = frozenset(
    {
        "openai",
        "openai_compatible",
        "deepseek",
        "ollama",
        "anthropic",
        "claude",
        "dsh",
        "command",
        "interactive",
        "manual",
        "copy_paste",
        "clipboard",
    }
)

#: Characters that can only appear in template/injection payloads, never in a
#: legitimate harness name (F11 defense in depth).
_NAME_POISON_CHARS = frozenset("{};|&$`\"' \t\r\n")

#: R10 defaults (Q1 open): per-packet worker + gateway call budgets.
DEFAULT_MAX_WORKER_CALLS = 40
DEFAULT_MAX_GATEWAY_CALLS = 40


class HarnessConfigError(ValueError):
    """Bad harness configuration: unknown/API/template harness name or shape."""


class SpendCapExceededError(WorktreeError):
    """Pre-dispatch cap check failed (R10/Q1); no subprocess was spawned."""


class GatewayConfinementError(WorktreeError):
    """Gateway post-call tracked-status assertion failed (fix tranche, fail-closed)."""


#: Role value selecting the confined gateway profile in run_harness_attempt.
GATEWAY_ROLE = "gateway"

#: Last-message capture filename inside the per-call gateway scratch dir (B1 -o pick).
_GATEWAY_LAST_MESSAGE_FILENAME = "last-message.md"

#: Confinement root override for tests; None selects the stc repo automatically.
GATEWAY_CONFINEMENT_REPO: Path | None = None


def _gateway_confinement_repo() -> Path:
    if GATEWAY_CONFINEMENT_REPO is not None:
        return GATEWAY_CONFINEMENT_REPO
    # R2c: confinement needs the STC repo (a git checkout), not the raw
    # workspace root (which merely contains it on harness layouts).
    return resolve_stc_root()


def snapshot_tracked_status(repo: Path) -> str:
    """Capture tracked-only git status porcelain for a repo (fix tranche).

    Untracked files are excluded: leases, ledgers, and evidence churn normally
    under them. Raises GatewayConfinementError when the snapshot cannot be
    taken (fail-closed: an unverifiable repo is unsafe for gateway agency).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GatewayConfinementError(
            f"Tracked-status snapshot failed, failing closed: {exc}"
        ) from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise GatewayConfinementError(
            f"Tracked-status snapshot failed, failing closed: {detail[:200]}"
        )
    return proc.stdout


def assert_tracked_status_unchanged(repo: Path, before: str) -> None:
    """Re-snapshot tracked status; fail closed if any tracked file changed."""
    after = snapshot_tracked_status(repo)
    if after != before:
        raise GatewayConfinementError(
            "Gateway call changed tracked files in stc/, failing closed. "
            f"before={before[:500]!r} after={after[:500]!r}"
        )


class HarnessResultT(Protocol):
    """Structural result type (pinned HarnessResult satisfies this)."""

    content: str
    exit_code: int
    error: str | None

    @property
    def is_success(self) -> bool: ...


class HarnessT(Protocol):
    """Structural harness type (pinned MockHarness satisfies this)."""

    def execute(
        self,
        prompt: str,
        role: str = ...,
        model: str | None = ...,
        context: dict[str, Any] | None = ...,
    ) -> HarnessResultT: ...


class RunnerFn(Protocol):
    """Subprocess seam: argv with cwd/env/timeout/stdin (scripted in tests)."""

    def __call__(
        self,
        argv: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        timeout: float,
        stdin_text: str | None,
    ) -> subprocess.CompletedProcess[str]: ...


@dataclass(frozen=True)
class HandshakeReport:
    """Outcome of HarnessWorker.handshake: binary + --version probe (B1 semantics)."""

    harness: str
    success: bool
    resolved_path: str | None = None
    version: str | None = None
    latency_ms: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class CritiqueProvenance:
    """Per-critique-call validity witness (Fix 2: fail-closed review).

    Recorded by the gateway backend for every controller critique call, in
    call order. ``valid`` is True only when the harness call succeeded AND
    the response parsed as an explicit critique object (numeric value_score,
    verdict in {APPROVE, PRUNE, ESCALATE_HUMAN}, non-empty rationale).
    ``ledger_row`` is the 0-based spend-ledger row index of the call (the
    backend logs exactly one row per call, so the counter is the index).
    The RT-03 veto pairs the k-th SCORE_RECORDED event with the k-th entry.
    """

    seq: int
    valid: bool
    detail: str
    ledger_row: int


def default_spend_path() -> Path:
    """Append-only spend log location (outside leases, F11)."""
    repo = resolve_stc_root()
    return repo / "docs" / "builds" / "stc-integration" / "evidence" / "P03" / "spend.jsonl"


#: Version tag for failure-evidence sidecar records (F1).
FAILURE_EVIDENCE_VERSION = 1

#: Suffix mapping a spend ledger path to its failure-evidence sidecar (F1):
#: ``<stem>.failures.jsonl`` next to the ledger (run/evidence dir).
_FAILURE_EVIDENCE_SUFFIX = ".failures.jsonl"

#: Ledger note budget: the pre-existing 300-char backstop, kept once notes
#: are short pointers (F1). Raised errors use the TAIL of this budget.
NOTE_BUDGET = 300


def failure_evidence_path(ledger_path: str | Path) -> Path:
    """Return the failure-evidence sidecar path for a spend ledger (F1)."""
    ledger = Path(ledger_path)
    return ledger.parent / f"{ledger.stem}{_FAILURE_EVIDENCE_SUFFIX}"


def _candidate_identity() -> dict[str, Any]:
    """Best-effort candidate identity for failure records (F1); never raises."""
    repo = resolve_stc_root()
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        head = proc.stdout.strip() if proc.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        head = "unknown"
    owned: dict[str, dict[str, str]] = {}
    here = Path(__file__).resolve()
    for name in ("harness_worker.py", "cli_gateway.py"):
        try:
            digest = hashlib.sha256((here.parent / name).read_bytes()).hexdigest()
        except OSError:
            digest = "unknown"
        owned[name] = {
            "sha256": digest,
            "short": digest[:12] if digest != "unknown" else "unknown",
        }
    return {"stc_head": head or "unknown", "owned_files": owned}


def write_failure_evidence(
    *,
    ledger_path: str | Path,
    channel: str,
    harness: str,
    model: str,
    profile: str | None,
    task_id: str,
    lease_id: str,
    attempt: int,
    exit_code: int | None,
    timed_out: bool,
    duration_s: float,
    out_bytes: int,
    stdout_full: str,
    stderr_full: str,
) -> tuple[Path, str] | None:
    """Append one failure record with FULL stdout/stderr to the sidecar (F1).

    Best-effort: returns (sidecar_path, record_id), or None when the write
    fails (a logging failure warns, never masks the harness failure).
    """
    sidecar = failure_evidence_path(ledger_path)
    record_id = uuid.uuid4().hex[:12]
    record: dict[str, Any] = {
        "v": FAILURE_EVIDENCE_VERSION,
        "id": record_id,
        "ts": datetime.now(UTC).isoformat(),
        "channel": channel,
        "harness": harness,
        "model": model,
        "profile": profile,
        "task_id": task_id,
        "lease_id": lease_id,
        "attempt": attempt,
        "ok": False,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": round(duration_s, 3),
        "out_bytes": out_bytes,
        "stdout_full": stdout_full,
        "stderr_full": stderr_full,
        **_candidate_identity(),
        "ledger": str(ledger_path),
    }
    try:
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        with sidecar.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.warning("Failure-evidence record dropped (logging failed): %s", exc)
        return None
    return sidecar, record_id


def failure_note_pointer(reason: str, sidecar: Path | None, record_id: str | None) -> str:
    """Build the short ledger note for a failure (F1): reason + sidecar pointer."""
    if sidecar is None or record_id is None:
        return f"{reason} [failure-evidence write failed]".strip()
    pointer = f"[full stderr: {sidecar.name}#{record_id}]"
    budget = NOTE_BUDGET - len(pointer) - 1
    head = reason if len(reason) <= budget else reason[:budget]
    return f"{head} {pointer}".strip()


def _pinned_attr(module_name: str, attr: str) -> Any:
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise HarnessConfigError(
            f"{module_name} is not importable; P03 requires the P00-pinned "
            f"prompt-kit tree on PYTHONPATH (F3c): {exc}"
        ) from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise HarnessConfigError(f"{module_name} has no {attr!r}: {exc}") from exc


def _mock_harness() -> HarnessT:
    factory = cast(Callable[..., Any], _pinned_attr("prompt_kit.harnesses", "get_harness"))
    return cast(HarnessT, factory("mock"))


def _result_cls() -> Callable[..., HarnessResultT]:
    return cast(
        Callable[..., HarnessResultT],
        _pinned_attr("prompt_kit.harnesses.base", "HarnessResult"),
    )


def validate_harness_name(name: str) -> str:
    """Normalize a harness name; reject API/template/unknown names (F11)."""
    norm = (name or "").strip().lower()
    if not norm or any(c in _NAME_POISON_CHARS for c in norm):
        raise HarnessConfigError(
            f"Rejected harness name {name!r}: template/injection shapes forbidden."
        )
    if norm == "mock" or norm in CLI_HARNESS_NAMES:
        return norm
    if norm in API_HARNESS_NAMES:
        raise HarnessConfigError(
            f"Rejected harness {name!r}: API/non-executing harnesses are forbidden (F11/R5)."
        )
    raise HarnessConfigError(
        f"Unknown harness {name!r}: allowed CLI names are {sorted(CLI_HARNESS_NAMES)} + 'mock'."
    )


def render_bundle_prompt(bundle: TaskBundle) -> str:
    """Render a bundle to worker prompt text; citations preserved verbatim (F9)."""
    lines = [
        f"STC task {bundle.task_id} (spec {bundle.spec_id}, epoch {bundle.epoch_index})",
        "",
        "GOAL:",
        bundle.goal_statement,
        "",
        "INVARIANTS (do not violate):",
    ]
    lines.extend(f"- {inv}" for inv in bundle.invariants)
    lines.extend(("", "TARGET FILES:"))
    for target in bundle.target_files:
        detail = f"- {target.path} [{target.action}]"
        if target.expected_symbols:
            detail += f" symbols={','.join(target.expected_symbols)}"
        lines.append(detail)
    lines.extend(("", "MEMBRANE PROTOCOLS:"))
    lines.extend(f"- {proto}" for proto in bundle.membrane_protocols)
    lines.extend(("", "NEGATIVE INHIBITORS (never do):"))
    lines.extend(f"- {inh}" for inh in bundle.negative_inhibitors)
    lines.extend(
        (
            "",
            "Implement the targets inside the current working directory (the leased",
            "worktree). Do not read or write anything outside it.",
        )
    )
    return "\n".join(lines)


def _model_flag(model: str | None) -> list[str]:
    if model and model != "default":
        return ["--model", model]
    return []


def build_native_command(
    harness_name: str, prompt: str, *, model: str | None, lease_root: Path
) -> tuple[list[str], str | None, Path | None]:
    """Build B1-verified native argv: (argv, stdin_text, prompt_file|None).

    Prompt placement is per-shape and fixed (stdin / -p value / --prompt-file);
    no shell and no templates are involved. The muse shape writes the prompt to
    an OS-temp file (outside the lease); the caller must delete it. Raises
    WorktreeError if the binary is missing.
    """
    norm = validate_harness_name(harness_name)
    if norm == "mock":
        raise HarnessConfigError("mock has no native command; use the pinned mock path.")
    binary = "agy" if norm.startswith("agy") else norm
    resolved = shutil.which(binary)
    if resolved is None:
        raise WorktreeError(f"Harness binary {binary!r} not found on PATH.")
    if norm == "codex":
        argv = [
            resolved,
            "exec",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "-C",
            str(lease_root),
            *_model_flag(model),
            "-",
        ]
        return argv, prompt, None
    if norm.startswith("agy"):
        argv = [resolved, "--dangerously-skip-permissions", *_model_flag(model), "-p", prompt]
        return argv, None, None
    fd, tmp = tempfile.mkstemp(prefix="stc-prompt-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(prompt)
    except OSError:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            Path(tmp).unlink()
        raise
    prompt_file = Path(tmp)
    argv = [resolved, "exec", *_model_flag(model), "--prompt-file", str(prompt_file)]
    return argv, None, prompt_file


def build_gateway_command(
    harness_name: str, prompt: str, *, model: str | None, scratch_dir: Path
) -> tuple[list[str], str | None, Path | None, Path]:
    """Build the fix-tranche gateway argv: (argv, stdin_text, prompt_file|None, last_message).

    Role=gateway profile (D15): caller runs with cwd=scratch_dir (fresh OS-temp
    dir, never a repo); codex additionally gets read-only sandbox,
    --skip-git-repo-check, --ephemeral, and -o last-message capture (B1 pick).
    Model/timeout are unchanged. agy/muse keep their existing flag shapes (no
    verified read-only profile exists for them) but inherit scratch cwd,
    shaping, and the tracked-status assertion. The caller must delete
    prompt_file (muse shape) and the scratch dir. Raises WorktreeError if the
    binary is missing.
    """
    norm = validate_harness_name(harness_name)
    if norm == "mock":
        raise HarnessConfigError("mock has no gateway command; use the pinned mock path.")
    binary = "agy" if norm.startswith("agy") else norm
    resolved = shutil.which(binary)
    if resolved is None:
        raise WorktreeError(f"Harness binary {binary!r} not found on PATH.")
    last_message = scratch_dir / _GATEWAY_LAST_MESSAGE_FILENAME
    if norm == "codex":
        argv = [
            resolved,
            "exec",
            "--skip-git-repo-check",
            "-s",
            "read-only",
            "-C",
            str(scratch_dir),
            "--ephemeral",
            "-o",
            str(last_message),
            *_model_flag(model),
            "-",
        ]
        return argv, prompt, None, last_message
    if norm.startswith("agy"):
        argv = [resolved, "--dangerously-skip-permissions", *_model_flag(model), "-p", prompt]
        return argv, None, None, last_message
    fd, tmp = tempfile.mkstemp(prefix="stc-prompt-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(prompt)
    except OSError:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            Path(tmp).unlink()
        raise
    prompt_file = Path(tmp)
    argv = [resolved, "exec", *_model_flag(model), "--prompt-file", str(prompt_file)]
    return argv, None, prompt_file, last_message


class SpendLedger:
    """Append-only JSONL spend log with pre-dispatch cap checks (F11/BT-04)."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_worker_calls: int = DEFAULT_MAX_WORKER_CALLS,
        max_gateway_calls: int = DEFAULT_MAX_GATEWAY_CALLS,
    ) -> None:
        self.path = Path(path) if path is not None else default_spend_path()
        self.max_worker_calls = max_worker_calls
        self.max_gateway_calls = max_gateway_calls

    def _cap_for(self, channel: str) -> int:
        if channel == "worker":
            return self.max_worker_calls
        if channel == "gateway":
            return self.max_gateway_calls
        raise HarnessConfigError(f"Unknown spend channel {channel!r}.")

    def count(self, channel: str) -> int:
        """Counted rows for a channel; torn tail lines (crash mid-write) skip."""
        self._cap_for(channel)
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return 0
        except OSError as exc:
            logger.warning("Spend ledger unreadable, failing closed: %s", exc)
            raise SpendCapExceededError(f"Spend ledger unreadable, failing closed: {exc}") from exc
        used = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("channel") == channel:
                used += 1
        return used

    def check_quota(self, channel: str) -> None:
        """Raise before spawning when the channel budget is exhausted (R10/Q1)."""
        cap = self._cap_for(channel)
        used = self.count(channel)
        if used >= cap:
            raise SpendCapExceededError(
                f"Spend cap reached: {used}/{cap} {channel} calls used; no subprocess spawned."
            )

    def log_row(
        self,
        channel: str,
        *,
        harness: str,
        model: str,
        task_id: str,
        lease_id: str,
        attempt: int,
        ok: bool,
        exit_code: int | None,
        timed_out: bool,
        duration_s: float,
        out_bytes: int,
        note: str = "",
        failure_evidence: str | None = None,
    ) -> None:
        """Append one attempt row; best-effort (a logging failure warns, never masks).

        The ``failure_evidence`` key (``<sidecar>#<record>``) is present ONLY on
        failure rows carrying a sidecar record (F1); success rows are unchanged.
        """
        self._cap_for(channel)
        row: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "channel": channel,
            "harness": harness,
            "model": model,
            "task_id": task_id,
            "lease_id": lease_id,
            "attempt": attempt,
            "ok": ok,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_s": round(duration_s, 3),
            "out_bytes": out_bytes,
            "note": note[:NOTE_BUDGET],
        }
        if failure_evidence is not None:
            row["failure_evidence"] = failure_evidence
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        except OSError as exc:
            logger.warning("Spend row dropped (logging failed): %s", exc)


def sweep_prompt_kit_tmp(root: Path) -> list[str]:
    """Move lease `.prompt-kit/tmp/*.md` leftovers to OS-temp quarantine (BT-05).

    The harness deletes its own prompt file on success; leftovers only survive
    crashes. Sweeping them out of the lease keeps candidate identity and the
    custody report clean. Never raises; returns swept filenames.
    """
    swept: list[str] = []
    tmpdir = root / ".prompt-kit" / "tmp"
    try:
        if not tmpdir.is_dir():
            return swept
        leftovers = sorted(tmpdir.glob("*.md"))
        if not leftovers:
            return swept
        qdir = Path(tempfile.mkdtemp(prefix="stc-promptkit-sweep-"))
        for leftover in leftovers:
            try:
                shutil.move(str(leftover), str(qdir / leftover.name))
            except OSError:
                continue
            swept.append(leftover.name)
    except OSError:
        return swept
    return swept


def default_runner(
    argv: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    timeout: float,
    stdin_text: str | None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _run_confined_gateway_attempt(
    *,
    norm: str,
    model: str,
    prompt: str,
    timeout: float,
    harness_env: dict[str, str],
    runner: RunnerFn,
) -> tuple[HarnessResultT, Path]:
    """Run one native gateway attempt under the fix-tranche profile (D15).

    Fresh OS-temp scratch cwd per call (never a repo), gateway argv, -o
    last-message readback (stdout fallback), and a tracked-status assertion
    that fails closed on every completed attempt (success, failure, and
    timeout alike). Returns (result, scratch_dir); the scratch dir is removed
    before return, so the path identifies where the call ran. A spawn failure
    (runner OSError) propagates without assertion: no agency occurred.
    """
    repo = _gateway_confinement_repo()
    before = snapshot_tracked_status(repo)
    scratch_dir = Path(tempfile.mkdtemp(prefix="stc-gateway-"))
    argv, stdin_text, prompt_file, last_message = build_gateway_command(
        norm, prompt, model=model, scratch_dir=scratch_dir
    )
    try:
        env = dict(os.environ)
        env.update(harness_env)
        try:
            proc = runner(
                argv, cwd=str(scratch_dir), env=env, timeout=timeout, stdin_text=stdin_text
            )
        except subprocess.TimeoutExpired as exc:
            assert_tracked_status_unchanged(repo, before)
            partial = exc.stdout if isinstance(exc.stdout, str) else ""
            return (
                _result_cls()(
                    content=partial or "",
                    exit_code=124,
                    error=f"Harness timed out after {timeout}s",
                ),
                scratch_dir,
            )
        cls = _result_cls()
        assert_tracked_status_unchanged(repo, before)
        if proc.returncode != 0:
            return (
                cls(
                    content=proc.stdout,
                    exit_code=proc.returncode,
                    error=proc.stderr.strip() or f"Process exited with code {proc.returncode}",
                    raw_response=proc,
                ),
                scratch_dir,
            )
        content = proc.stdout
        with contextlib.suppress(OSError):
            if last_message.is_file():
                file_text = last_message.read_text(encoding="utf-8")
                if file_text:
                    content = file_text
        return cls(content=content, exit_code=0, raw_response=proc), scratch_dir
    finally:
        if prompt_file is not None:
            with contextlib.suppress(OSError):
                prompt_file.unlink()
        shutil.rmtree(scratch_dir, ignore_errors=True)


def run_harness_attempt(
    *,
    name: str,
    model: str,
    prompt: str,
    role: str,
    project_root: Path,
    context_extra: dict[str, Any],
    timeout: float,
    harness_env: dict[str, str],
    harness: HarnessT | None,
    runner: RunnerFn,
    harness_role: str | None = None,
) -> tuple[HarnessResultT, Path]:
    """Run one harness attempt; shared core of worker + gateway (no ledger here).

    ``role`` drives routing (gateway role ⇒ confinement profile). ``harness_role``,
    when given, is the SST role label forwarded to harness.execute (role-aware
    prompts + payload validation); it never affects routing. Defaults to ``role``.
    Returns (result, invoked_cwd). Mock names run the pinned mock harness;
    CLI names run the B1 native shape. Native gateway-role calls run under the
    fix-tranche confinement profile (scratch cwd, read-only codex sandbox,
    -o capture, tracked-status assertion). A runner timeout becomes an
    exit-124 failure result (the caller decides retry/fail).
    """
    norm = validate_harness_name(name)
    context: dict[str, Any] = {"project_root": str(project_root), **context_extra}
    if harness is not None or norm == "mock":
        active = harness if harness is not None else _mock_harness()
        return (
            active.execute(prompt, role=harness_role or role, model=model, context=context),
            project_root,
        )
    if role == GATEWAY_ROLE:
        return _run_confined_gateway_attempt(
            norm=norm,
            model=model,
            prompt=prompt,
            timeout=timeout,
            harness_env=harness_env,
            runner=runner,
        )
    argv, stdin_text, prompt_file = build_native_command(
        norm, prompt, model=model, lease_root=project_root
    )
    try:
        env = dict(os.environ)
        env.update(harness_env)
        try:
            proc = runner(
                argv, cwd=str(project_root), env=env, timeout=timeout, stdin_text=stdin_text
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout if isinstance(exc.stdout, str) else ""
            return (
                _result_cls()(
                    content=partial or "",
                    exit_code=124,
                    error=f"Harness timed out after {timeout}s",
                ),
                project_root,
            )
        cls = _result_cls()
        if proc.returncode != 0:
            return (
                cls(
                    content=proc.stdout,
                    exit_code=proc.returncode,
                    error=proc.stderr.strip() or f"Process exited with code {proc.returncode}",
                    raw_response=proc,
                ),
                project_root,
            )
        return cls(content=proc.stdout, exit_code=0, raw_response=proc), project_root
    finally:
        if prompt_file is not None:
            with contextlib.suppress(OSError):
                prompt_file.unlink()


class HarnessWorker(WorkerProtocol):
    """WorkerProtocol driving CLI harnesses inside leased worktrees (P03)."""

    def __init__(
        self,
        harness_name: str,
        model: str | None = "default",
        *,
        ledger: SpendLedger | None = None,
        timeout: float = 600.0,
        harness_env: dict[str, str] | None = None,
        harness: HarnessT | None = None,
        runner: RunnerFn | None = None,
        chaperone_cls: type[ChaperoneWorker] = ChaperoneWorker,
        membrane_files: tuple[tuple[str, str | None], ...] | None = None,
        max_attempts: int = 2,
    ) -> None:
        self._name = validate_harness_name(harness_name)
        if harness is not None and (
            hasattr(harness, "command_template") or type(harness).__name__ == "CommandHarness"
        ):
            raise HarnessConfigError("Shell/command-template harnesses are forbidden (F11).")
        if timeout <= 0:
            raise HarnessConfigError("timeout must be positive seconds.")
        if max_attempts < 1:
            raise HarnessConfigError("max_attempts must be >= 1.")
        self._model = model or "default"
        self._ledger = ledger if ledger is not None else SpendLedger()
        self._timeout = timeout
        self._harness_env = dict(harness_env) if harness_env else {}
        self._harness = harness
        self._runner: RunnerFn = runner if runner is not None else default_runner
        self._chaperone_cls = chaperone_cls
        self._membrane_files = membrane_files
        self._max_attempts = max_attempts

    def confinement_root(self, lease: WorktreeLease) -> Path:
        """Return the physical root path to which the worker is strictly confined."""
        return Path(lease.worktree_path).resolve()

    def handshake(self, probe: bool = True) -> HandshakeReport:
        """Binary presence (+ --version execution when probe=True). No quota spent."""
        if self._name == "mock":
            return HandshakeReport(harness=self._name, success=True, version="mock")
        binary = "agy" if self._name.startswith("agy") else self._name
        resolved = shutil.which(binary)
        if resolved is None:
            return HandshakeReport(
                harness=self._name, success=False, error=f"binary {binary!r} not on PATH"
            )
        if not probe:
            return HandshakeReport(harness=self._name, success=True, resolved_path=resolved)
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                [resolved, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return HandshakeReport(
                harness=self._name,
                success=False,
                resolved_path=resolved,
                error=f"version probe failed: {exc}",
            )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if proc.returncode != 0:
            detail = proc.stderr.strip() or f"exit {proc.returncode}"
            return HandshakeReport(
                harness=self._name,
                success=False,
                resolved_path=resolved,
                latency_ms=latency_ms,
                error=f"version probe failed: {detail[:200]}",
            )
        first_line = (proc.stdout.strip().splitlines() or ["unknown"])[0]
        return HandshakeReport(
            harness=self._name,
            success=True,
            resolved_path=resolved,
            version=first_line[:120],
            latency_ms=latency_ms,
        )

    def worker_fn_for(self, lease: WorktreeLease) -> Callable[[TaskBundle, Path], str]:
        """Build the (bundle, root) closure composed with the chaperone."""

        def fn(bundle: TaskBundle, root: Path) -> str:
            prompt = render_bundle_prompt(bundle)
            try:
                last_error = "no attempts ran"
                for attempt in range(1, self._max_attempts + 1):
                    self._ledger.check_quota("worker")
                    started = time.perf_counter()
                    ok = False
                    exit_code: int | None = None
                    timed_out = False
                    out_bytes = 0
                    note = ""
                    stdout_full = ""
                    stderr_full = ""
                    try:
                        result = self._execute_once(prompt, bundle, root)
                        ok = bool(result.is_success)
                        exit_code = result.exit_code
                        timed_out = exit_code == 124
                        out_bytes = len(result.content or "")
                        stdout_full = result.content or ""
                        stderr_full = result.error or ""
                        if ok:
                            return result.content
                        last_error = result.error or f"exit {result.exit_code}"
                        note = last_error
                    except SpendCapExceededError:
                        raise
                    except Exception as exc:
                        last_error = f"{type(exc).__name__}: {exc}"
                        note = last_error
                        stderr_full = last_error
                        if attempt >= self._max_attempts:
                            raise WorktreeError(
                                f"Harness {self._name!r} crashed: {last_error}"
                            ) from exc
                    finally:
                        elapsed = time.perf_counter() - started
                        failure_ref: str | None = None
                        if not ok:
                            written = write_failure_evidence(
                                ledger_path=self._ledger.path,
                                channel="worker",
                                harness=self._name,
                                model=self._model,
                                profile=None,
                                task_id=bundle.task_id,
                                lease_id=lease.lease_id,
                                attempt=attempt,
                                exit_code=exit_code,
                                timed_out=timed_out,
                                duration_s=elapsed,
                                out_bytes=out_bytes,
                                stdout_full=stdout_full,
                                stderr_full=stderr_full,
                            )
                            if written is not None:
                                sidecar, record_id = written
                                failure_ref = f"{sidecar}#{record_id}"
                                note = failure_note_pointer(note, sidecar, record_id)
                            else:
                                note = failure_note_pointer(note, None, None)
                        self._ledger.log_row(
                            "worker",
                            harness=self._name,
                            model=self._model,
                            task_id=bundle.task_id,
                            lease_id=lease.lease_id,
                            attempt=attempt,
                            ok=ok,
                            exit_code=exit_code,
                            timed_out=timed_out,
                            duration_s=elapsed,
                            out_bytes=out_bytes,
                            note=note,
                            failure_evidence=failure_ref,
                        )
                raise WorktreeError(
                    f"Harness {self._name!r} failed after "
                    f"{self._max_attempts} attempts: {last_error}"
                )
            finally:
                sweep_prompt_kit_tmp(root)

        return fn

    def _execute_once(self, prompt: str, bundle: TaskBundle, root: Path) -> HarnessResultT:
        context_extra = {"task_id": bundle.task_id, "correlation_id": bundle.correlation_id}
        result, invoked = run_harness_attempt(
            name=self._name,
            model=self._model,
            prompt=prompt,
            role="builder",
            project_root=root,
            context_extra=context_extra,
            timeout=self._timeout,
            harness_env=self._harness_env,
            harness=self._harness,
            runner=self._runner,
        )
        self._assert_cwd(root, invoked)
        return result

    @staticmethod
    def _assert_cwd(root: Path, invoked: Path) -> None:
        if invoked.resolve() != root.resolve():
            raise WorktreeError(f"Harness cwd {invoked} != lease root {root} (F7).")

    def dispatch(self, bundle: TaskBundle, lease: WorktreeLease) -> str:
        """Execute the bundle in the lease; return the custody report JSON."""
        root = self.confinement_root(lease)
        if not root.is_dir():
            raise WorktreeError(f"Confinement root does not exist: {root}")
        if self._ledger.path.resolve().is_relative_to(root):
            raise HarnessConfigError("Spend ledger must live outside the lease (F11).")
        # Pre-create the ledger parent pre-snapshot so its creation never trips
        # the audit; the ledger file + parent dir are exact-excluded below.
        with contextlib.suppress(OSError):
            self._ledger.path.parent.mkdir(parents=True, exist_ok=True)
        # F1: pre-create the failure-evidence sidecar pre-snapshot and
        # exact-exclude it, so failure appends stay invisible to the outer
        # tripwire exactly like the ledger file itself (per-failure files
        # would trip it: exclusions are exact paths, and fail-then-retry
        # success runs DO reach the post-run audit).
        sidecar = failure_evidence_path(self._ledger.path)
        with contextlib.suppress(OSError):
            sidecar.touch(exist_ok=True)
        exclusions = (self._ledger.path, self._ledger.path.parent, sidecar)
        try:
            if self._membrane_files is None:
                chaperone = self._chaperone_cls(
                    worker_fn=self.worker_fn_for(lease), outer_exclude=exclusions
                )
            else:
                chaperone = self._chaperone_cls(
                    worker_fn=self.worker_fn_for(lease),
                    membrane_files=self._membrane_files,
                    outer_exclude=exclusions,
                )
        except TypeError as exc:
            raise HarnessConfigError(
                f"chaperone_cls {self._chaperone_cls.__name__} is incompatible: {exc}"
            ) from exc
        return chaperone.dispatch(bundle, lease)


def harness_worker_fn(
    worker: HarnessWorker, lease: WorktreeLease
) -> Callable[[TaskBundle, Path], str]:
    """Factory: (bundle, root) closure over a configured worker for a lease."""
    return worker.worker_fn_for(lease)


def dispatch_with_quarantine(
    worker: WorkerProtocol,
    bundle: TaskBundle,
    lease: WorktreeLease,
    manager: WorktreeManager,
    reason_prefix: str = "confinement breach",
) -> str:
    """Dispatch, owning the lease-quarantine call on breach (F6); breach re-raised."""
    try:
        return worker.dispatch(bundle, lease)
    except ConfinementViolationError as exc:
        try:
            manager.quarantine_lease(lease, reason=f"{reason_prefix}: {exc}")
        except Exception as quarantine_exc:
            logger.warning("Lease quarantine call failed (breach still raised): %s", quarantine_exc)
        raise
