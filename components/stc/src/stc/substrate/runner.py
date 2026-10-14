"""Substrate deterministic quality gate execution engine and receipt signer."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from stc.core.config import get_settings
from stc.protocols.interfaces import SubstrateRunnerProtocol
from stc.schemas.models import ExecutionReceipt, GateReport
from stc.substrate.receipt import (
    ReceiptSigner,
    compute_receipt_signature,
    compute_receipt_signature_for_model,
    create_receipt,
    load_receipt,
    save_receipt,
    serialize_canonical_payload,
    verify_receipt,
)

logger = logging.getLogger(__name__)

_thread_local = threading.local()


def _argv_store() -> dict[str, list[list[str]]]:
    """Thread-local store of the ACTUAL gate argv executed (D-zeta)."""
    store: dict[str, list[list[str]]] | None = getattr(_thread_local, "gate_argv", None)
    if store is None:
        store = {}
        _thread_local.gate_argv = store
    return store


class SubstrateRunnerConfig(BaseModel):
    """Configuration for Substrate deterministic quality gates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_per_gate: float = Field(default=120.0, gt=0.0)
    run_mutmut: bool = True
    defer_windows_mutmut_to_wsl: bool = True
    mutmut_kill_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    wsl_distribution: str | None = None
    hmac_key: str | bytes | None = None


def _format_snippet(output: str, max_chars: int = 1000) -> str:
    """Extract snippet keeping the TAIL without cutting mid-line."""
    if not output:
        return ""
    if len(output) <= max_chars:
        return output
    tail = output[-max_chars:]
    nl = tail.find("\n")
    if nl != -1:
        tail = tail[nl + 1 :]
    return tail


def _translate_to_wsl_path(path: Path) -> str:
    """Translate a Windows filesystem path to POSIX WSL /mnt/<drive>/ path."""
    resolved = path.resolve()
    drive = resolved.drive
    if drive and len(drive) >= 2 and drive[1] == ":":
        drive_letter = drive[0].lower()
        parts = resolved.parts[1:]
        posix_sub = "/".join(parts)
        return f"/mnt/{drive_letter}/{posix_sub}" if posix_sub else f"/mnt/{drive_letter}"
    return resolved.as_posix()


def _parse_mutmut_output(output: str) -> tuple[int, int, int, float | None]:
    """Extract (killed, survived, timeout, kill_rate) from mutmut output."""
    counts = _parse_mutmut_counts(output)
    return counts.killed, counts.survived, counts.timeout, counts.kill_rate


@dataclass(frozen=True)
class MutmutCounts:
    """Parsed mutmut outcome counts (R3: errors never count as kills)."""

    killed: int
    survived: int
    timeout: int
    errors: int
    excluded: int
    kill_rate: float | None
    notests: int = 0
    reasons: str = ""


# Installed-mutmut progress line (see mutmut/__main__.py stats format):
#   {tried}/{total}  🎉 {killed} 🫥 {no_tests}  ⏰ {timeout}  🤔 {suspicious}
#   🙁 {survived}  🔇 {skipped}  🧙 {caught_by_type_check}
# The run emits one line per update; the LAST match carries final counts.
_MUTMUT_PROGRESS_RE = re.compile(
    r"\U0001f389\s+(\d+)\s+\U0001fae5\s+(\d+)\s+"
    r"\u23f0\s+(\d+)\s+\U0001f914\s+(\d+)\s+"
    r"\U0001f641\s+(\d+)\s+\U0001f507\s+(\d+)\s+"
    r"\U0001f9d9\s+(\d+)"
)


def _parse_mutmut_counts(output: str) -> MutmutCounts:
    """Extract killed/survived/timeout/error/excluded counts + kill rate.

    Installed-mutmut progress line wins when present (authoritative for
    this version); legacy "Killed X of Y" text is the fallback. Mapping:
    test kills + type-check catches are dead, so killed counts test kills
    only (no rate inflation) while typecheck rides excluded-with-reasons;
    no-tests (uncovered) mutants count as survived — the suite passes
    vacuously with them applied, so they are alive by definition.
    Error and timeout outcomes never count as kills (numerator); timeouts
    stay in the denominator (conservative: hung suites hurt the rate);
    infrastructure errors and excluded mutants are receipted but stay out
    of the rate (unjudgeable).
    """
    errors = _parse_error_count(output)
    progress = list(_MUTMUT_PROGRESS_RE.finditer(output))
    if progress:
        killed, no_tests, timeout, suspicious, survived, skipped, typecheck = (
            int(g) for g in progress[-1].groups()
        )
        alive = survived + no_tests
        total = killed + alive + timeout
        kill_rate = round(killed / total, 4) if total > 0 else None
        return MutmutCounts(
            killed=killed,
            survived=alive,
            timeout=timeout,
            errors=errors,
            excluded=skipped + suspicious + typecheck,
            kill_rate=kill_rate,
            notests=no_tests,
            reasons=f"notests={no_tests};skipped={skipped};"
            f"suspicious={suspicious};typecheck={typecheck}",
        )
    killed_match = re.search(r"(?:killed|Killed|\U0001f389)[\":\s]+(\d+)", output)
    survived_match = re.search(r"(?:survived|Survived|\U0001f641)[\":\s]+(\d+)", output)
    timeout_match = re.search(r"(?:timeout|Timeout|\u23f0)[\":\s]+(\d+)", output)
    excluded_match = re.search(
        r"(?:excluded|Excluded|skipped|Skipped|incompetent|Incompetent|\u23ed)[\":\s]+(\d+)",
        output,
    )

    killed = int(killed_match.group(1)) if killed_match else 0
    survived = int(survived_match.group(1)) if survived_match else 0
    timeout = int(timeout_match.group(1)) if timeout_match else 0
    excluded = int(excluded_match.group(1)) if excluded_match else 0

    total = killed + survived + timeout
    kill_rate = round(killed / total, 4) if total > 0 else None
    return MutmutCounts(
        killed=killed,
        survived=survived,
        timeout=timeout,
        errors=errors,
        excluded=excluded,
        kill_rate=kill_rate,
    )


def _parse_error_count(output: str) -> int:
    """Infrastructure-error signals in mutmut's own output (never kills)."""
    count_match = re.search(r"(?:errors|Errors|error|Error|ERROR|\u274c)[\":\s]+(\d+)", output)
    if count_match:
        return int(count_match.group(1))
    if "Traceback (most recent call last)" in output:
        return 1
    return 0


MUTMUT_TARGETS_PREFIX = "[mutmut-targets]"


def _mutmut_targets_line(paths: list[str], counts: MutmutCounts, threshold: float) -> str:
    """Anchored receipt line: mutated paths + outcome counts + rate (R3)."""
    rate = f"{counts.kill_rate:.2%}" if counts.kill_rate is not None else "n/a"
    reasons = f" reasons={counts.reasons}" if counts.reasons else ""
    return (
        f"{MUTMUT_TARGETS_PREFIX} paths={','.join(paths)} "
        f"killed={counts.killed} survived={counts.survived} notests={counts.notests} "
        f"timeout={counts.timeout} error={counts.errors} excluded={counts.excluded} "
        f"rate={rate} threshold={threshold:.2%}{reasons}"
    )


def parse_mutmut_targets(snippet: str) -> dict[str, str] | None:
    """Extracts the receipted targets line fields from a snippet (R3).

    Returns the key→value mapping (paths, killed, survived, timeout,
    error, excluded, rate, threshold) or None when the snippet carries
    no targets line (legacy/unscoped shape).
    """
    for line in snippet.splitlines():
        if not line.startswith(MUTMUT_TARGETS_PREFIX):
            continue
        fields: dict[str, str] = {}
        for token in line[len(MUTMUT_TARGETS_PREFIX) :].strip().split():
            if "=" in token:
                key, _, value = token.partition("=")
                fields[key] = value
        if {"paths", "killed", "survived", "rate", "threshold"} <= set(fields):
            return fields
        return None
    return None


_MUTMUT_COPY_SKIP: Final[frozenset[str]] = frozenset(
    {
        ".auto",
        ".git",
        ".mutmut-cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".sst",
        ".venv",
        "__pycache__",
        "mutants",
        "node_modules",
    }
)


def _mutmut_copy_ignore(directory: str, names: list[str]) -> set[str]:
    """copytree ignore: version control, envs, caches, prior mutants/."""
    _ = directory
    return set(names) & _MUTMUT_COPY_SKIP


def _patch_mutmut_config(pyproject_text: str | None, paths: list[str]) -> str:
    """Rewrites the [tool.mutmut] table to scoped source_paths (R3).

    Preserves the runner and other keys; drops legacy path keys (the
    deprecated tests_dir value is preserved under the modern
    pytest_add_cli_args_test_selection key); forces pytest_add_cli_args
    live-deselect (D13: live tests never run in the exercising suite);
    injects runner="pytest" when absent. A missing table/file yields a
    minimal block. Installed mutmut exposes no --paths-to-mutate flag,
    so scoped runs ride config — never bare-runner defaults.
    """
    block = (
        "[tool.mutmut]\n"
        f"source_paths = {json.dumps(paths)}\n"
        'runner = "pytest"\n'
        'pytest_add_cli_args_test_selection = ["tests/"]\n'
        'pytest_add_cli_args = ["-m", "not live"]\n'
    )
    if pyproject_text is None:
        return (
            "[tool.mutmut]\n"
            f"source_paths = {json.dumps(paths)}\n"
            'runner = "pytest"\n'
            'pytest_add_cli_args_test_selection = ["tests/"]\n'
            'pytest_add_cli_args = ["-m", "not live"]\n'
        )
    lines = pyproject_text.splitlines(keepends=True)
    start: int | None = None
    end = len(lines)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[tool.mutmut]":
            start = idx
            continue
        if start is not None and stripped.startswith("[") and stripped.endswith("]"):
            end = idx
            break
    if start is None:
        text = pyproject_text if pyproject_text.endswith("\n") else pyproject_text + "\n"
        return text + block
    kept: list[str] = []
    tests_dir_value: str | None = None
    has_runner = False
    for line in lines[start + 1 : end]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key == "tests_dir":
                tests_dir_value = _toml_string_array(stripped.split("=", 1)[1].strip())
                continue
            if key in {
                "paths_to_mutate",
                "source_paths",
                "pytest_add_cli_args",
                "pytest_add_cli_args_test_selection",
            }:
                continue
            if key == "runner":
                has_runner = True
        kept.append(line)
    selection = tests_dir_value or json.dumps(["tests/"])
    section = (
        "[tool.mutmut]\n"
        + "".join(kept)
        + f"source_paths = {json.dumps(paths)}\n"
        + f"pytest_add_cli_args_test_selection = {selection}\n"
        + 'pytest_add_cli_args = ["-m", "not live"]\n'
    )
    if not has_runner:
        section += 'runner = "pytest"\n'
    return "".join(lines[:start]) + section + "".join(lines[end:])


def _toml_string_array(value: str) -> str | None:
    """Best-effort TOML string-array passthrough (JSON-compatible subset)."""
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
        return json.dumps(parsed)
    return None


def _preseed_external_mutants(scope: Path) -> None:
    """Pre-seed mutants/ with an external target's data subtrees + siblings.

    Generic counterpart of the pinned src/docs/specs pre-seed: every
    top-level directory except mutmut-owned (tests/), tool state
    (dotdirs, mutants/, envs, caches per _MUTMUT_COPY_SKIP) is copied,
    plus top-level files (never pyproject.toml, never dotfiles).
    Top-level ``*.py`` siblings ARE pre-seeded as importable originals:
    mutmut 3.x mirrors only configured ``source_paths`` (+ tests) into
    mutants/, so a partial-scope champion (run 2 touched 2 of 3 files)
    otherwise breaks collection with ModuleNotFoundError on the
    untouched sibling. Pre-seeded siblings are inert: mutmut discovers
    mutatable files from config only, and overwrites whatever it owns
    (scoped trampolines) when it seeds.
    """
    for child in sorted(scope.iterdir()):
        name = child.name
        if name.startswith(".") or name in _MUTMUT_COPY_SKIP or name == "tests":
            continue
        if child.is_dir():
            shutil.copytree(
                child,
                scope / "mutants" / name,
                symlinks=True,
                ignore=_mutmut_copy_ignore,
            )
        elif child.is_file() and name != "pyproject.toml":
            dest_dir = scope / "mutants"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, dest_dir / name)


@contextlib.contextmanager
def _scoped_mutmut_tree(
    worktree_path: Path, paths: list[str], *, external_target: bool = False
) -> Iterator[Path]:
    """Mirror worktree to tmp + scope [tool.mutmut] (R3); cleans up on exit.

    The mirror keeps the lease byte-stable for the merge-close tripwire:
    mutmut writes mutants/ + cache into its cwd, which here is disposable.
    """
    parent = Path(tempfile.mkdtemp(prefix="stc-mutmut-scope-"))
    scope = parent / "scope"
    try:
        shutil.copytree(worktree_path, scope, symlinks=True, ignore=_mutmut_copy_ignore)
        pyproject = scope / "pyproject.toml"
        original = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else None
        pyproject.write_text(_patch_mutmut_config(original, paths), encoding="utf-8")
        # Leases bear disposable git (T2); the exercising suite detects its
        # repo root from its cwd, so commit the mirror bytes — a git-less
        # mirror would fall back to the ambient checkout (stale HEAD).
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=scope, check=True, capture_output=True
        )
        subprocess.run(["git", "add", "-A"], cwd=scope, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "scoped-mirror"],
            cwd=scope,
            check=True,
            capture_output=True,
        )
        # mutmut 3.x seeds mutants/ sparsely (mutated files + tests + config
        # only), so an exercising suite cannot see unmutated siblings or
        # repo-relative data there. Pre-seed the non-owned subtrees mutmut
        # never writes; tests/ + pyproject.toml stay mutmut-owned and are
        # never pre-seeded. STC trees keep the pinned src/docs/specs list
        # (byte-identical behavior); external targets pre-seed every
        # top-level data subtree (fixtures/, data/, ...) plus top-level
        # data files, since their layout is not STC-shaped.
        if external_target:
            _preseed_external_mutants(scope)
        else:
            for rel in ("src", "docs", "specs"):
                src_dir = scope / rel
                if src_dir.is_dir():
                    shutil.copytree(
                        src_dir,
                        scope / "mutants" / rel,
                        symlinks=True,
                        ignore=_mutmut_copy_ignore,
                    )
        yield scope
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def _mutmut_cmd() -> list[str]:
    """Argv for a mutmut run (R3: scoping rides config — installed mutmut
    exposes no --paths-to-mutate flag)."""
    return [sys.executable, "-m", "mutmut", "run"]


def _mutmut_not_measured(reason: str, detail: str = "") -> GateReport:
    """Fail-closed GateReport for unmeasurable mutmut scope (R3: never pass)."""
    snippet = f"MUTMUT NOT-MEASURED: {reason}; the gate fails closed — never a vacuous pass."
    if detail.strip():
        snippet += f"\n{_format_snippet(detail)}"
    return GateReport(
        gate_name="mutmut",
        exit_code=1,
        duration_seconds=0.0,
        violations_count=1,
        raw_output_snippet=snippet,
    )


class SubstrateRunner(SubstrateRunnerProtocol):
    """Deterministic substrate quality gate execution engine.

    Executes mechanical verification gates (Ruff, Mypy, Pytest, Mutmut)
    against a target worktree and produces cryptographically signed receipts.
    """

    def __init__(
        self,
        config: SubstrateRunnerConfig | None = None,
        *,
        timeout_per_gate: float | None = None,
        run_mutmut: bool | None = None,
        skip_mutmut_on_windows: bool | None = None,
        defer_windows_mutmut_to_wsl: bool | None = None,
        mutmut_kill_threshold: float | None = None,
        wsl_distribution: str | None = None,
        hmac_key: str | bytes | None = None,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            settings = get_settings()
            defer_win = (
                defer_windows_mutmut_to_wsl
                if defer_windows_mutmut_to_wsl is not None
                else (
                    skip_mutmut_on_windows
                    if skip_mutmut_on_windows is not None
                    else getattr(settings, "defer_windows_mutmut_to_wsl", True)
                )
            )
            self.config = SubstrateRunnerConfig(
                timeout_per_gate=(
                    timeout_per_gate
                    if timeout_per_gate is not None
                    else getattr(settings, "gate_timeout_seconds", 120.0)
                ),
                run_mutmut=(
                    run_mutmut if run_mutmut is not None else getattr(settings, "run_mutmut", True)
                ),
                defer_windows_mutmut_to_wsl=defer_win,
                mutmut_kill_threshold=(
                    mutmut_kill_threshold
                    if mutmut_kill_threshold is not None
                    else getattr(settings, "mutmut_kill_threshold", 0.85)
                ),
                wsl_distribution=(
                    wsl_distribution
                    if wsl_distribution is not None
                    else getattr(settings, "wsl_distribution", None)
                ),
                hmac_key=(
                    hmac_key
                    if hmac_key is not None
                    else getattr(settings, "receipt_hmac_key", None)
                ),
            )

    @property
    def timeout_per_gate(self) -> float:
        """Configured timeout per individual gate in seconds."""
        return self.config.timeout_per_gate

    @property
    def run_mutmut(self) -> bool:
        """Whether mutmut mutation gate is enabled."""
        return self.config.run_mutmut

    @property
    def skip_mutmut_on_windows(self) -> bool:
        """Whether mutmut execution on Windows defers to WSL/Linux."""
        return self.config.defer_windows_mutmut_to_wsl

    @property
    def defer_windows_mutmut_to_wsl(self) -> bool:
        """Whether mutmut execution on Windows defers to WSL/Linux."""
        return self.config.defer_windows_mutmut_to_wsl

    @property
    def mutmut_kill_threshold(self) -> float:
        """Configured kill threshold for mutmut."""
        return self.config.mutmut_kill_threshold

    @property
    def wsl_distribution(self) -> str | None:
        """Target WSL distribution name if configured."""
        return self.config.wsl_distribution

    @property
    def last_gate_argv(self) -> dict[str, list[list[str]]]:
        """ACTUAL gate argv executed by this thread's most recent run.

        Recorded per gate (``ruff``/``mypy``/``pytest``/``mutmut``) for the
        SelectionRecord's actual-argv binding (D-zeta: what ran beats what
        varies). Empty before the first run on this thread.
        """
        return {gate: [list(cmd) for cmd in cmds] for gate, cmds in _argv_store().items()}

    @staticmethod
    def _record_argv(gate: str, cmd: list[str]) -> None:
        _argv_store().setdefault(gate, []).append(list(cmd))

    def execute_gates(
        self,
        worktree_path: Path,
        task_id: str,
        epoch_index: int = 1,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        pytest_target: str | None = None,
        paths_to_mutate: list[str] | None = None,
        external_target: bool = False,
        **kwargs: Any,
    ) -> ExecutionReceipt:
        """Run all substrate gates against the target worktree and generate signed receipt.

        Conforms strictly to SubstrateRunnerProtocol. OS/mutmut policy is governed
        by runner configuration, with optional per-execution kwargs overrides.
        R3: paths_to_mutate scopes the mutmut gate to exactly those files
        (empty list fails closed as NOT-MEASURED; None keeps whole-tree).
        external_target marks a non-STC construction target: the mutmut
        mirror pre-seeds generic data subtrees (STC trees keep the pinned
        src/docs/specs pre-seed list).
        """
        _argv_store().clear()
        # Redirect to repository root if invoked from mutmut temporary mutants directory
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
            except (subprocess.SubprocessError, OSError) as exc:
                logger.debug("Failed to resolve git root from mutants dir: %s", exc)

        commit_hash = self._resolve_commit_hash(worktree_path)

        # E1 PRECEDENCE INVARIANT (section 5.2): the auto-disable trap below
        # takes effect ONLY when the caller passes no explicit `run_mutmut`
        # kwarg — an explicit kwarg takes precedence (checked first). BOTH
        # evaluation-path production call sites pass explicit bools (per-node
        # `run_mutmut=False`, merge `run_mutmut=self._champion_mutmut`), so
        # safeguard coverage there is decided by the call sites, never by the
        # trap. (CLI `gate` is off the evaluation path and may arm the trap.)
        # Proven behaviorally at the execution boundary, never by AST.
        active_run_mutmut = (
            kwargs["run_mutmut"]
            if "run_mutmut" in kwargs and kwargs["run_mutmut"] is not None
            else (
                False
                if os.environ.get("PYTEST_CURRENT_TEST") and pytest_target is not None
                else self.config.run_mutmut
            )
        )
        active_defer_windows = (
            kwargs["skip_mutmut_on_windows"]
            if "skip_mutmut_on_windows" in kwargs and kwargs["skip_mutmut_on_windows"] is not None
            else (
                kwargs["defer_windows_mutmut_to_wsl"]
                if "defer_windows_mutmut_to_wsl" in kwargs
                and kwargs["defer_windows_mutmut_to_wsl"] is not None
                else self.config.defer_windows_mutmut_to_wsl
            )
        )

        gate_ruff = self._run_gate_ruff(worktree_path)
        gate_mypy = self._run_gate_mypy(worktree_path)
        gate_pytest = self._run_gate_pytest(worktree_path, pytest_target=pytest_target)
        gate_mutmut = self._run_gate_mutmut(
            worktree_path,
            run_mutmut=active_run_mutmut,
            defer_windows=active_defer_windows,
            paths_to_mutate=paths_to_mutate,
            external_target=external_target,
        )

        return create_receipt(
            task_id=task_id,
            commit_hash=commit_hash,
            gate_ruff=gate_ruff,
            gate_mypy=gate_mypy,
            gate_pytest=gate_pytest,
            gate_mutmut=gate_mutmut,
            epoch_index=epoch_index,
            correlation_id=correlation_id,
            causation_id=causation_id,
            key=self.config.hmac_key,
        )

    def verify_receipt(self, receipt: ExecutionReceipt) -> bool:
        """Verify the cryptographic signature of an execution receipt."""
        return verify_receipt(receipt, key=self.config.hmac_key)

    def save_receipt(
        self,
        receipt: ExecutionReceipt,
        output_dir: Path | None = None,
    ) -> Path:
        """Serialize and persist the signed execution receipt to disk."""
        return save_receipt(receipt, output_dir=output_dir)

    def _resolve_commit_hash(self, worktree_path: Path) -> str:
        """Extract current git commit hash from worktree."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5.0,
            )
            if res.returncode == 0 and res.stdout and res.stdout.strip():
                return res.stdout.strip()
            raise RuntimeError(
                f"Failed to resolve git HEAD in worktree {worktree_path}: {res.stderr}"
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Git HEAD resolution timed out after 5.0s in worktree {worktree_path}"
            ) from exc

    def _run_gate_ruff(self, worktree_path: Path) -> GateReport:
        """Gate 1: Ruff code hygiene and style check (lint + format)."""
        cmd_check = [sys.executable, "-m", "ruff", "check", "."]
        cmd_fmt = [sys.executable, "-m", "ruff", "format", "--check", "."]
        self._record_argv("ruff", cmd_check)
        self._record_argv("ruff", cmd_fmt)
        start = time.perf_counter()
        try:
            res_check = subprocess.run(
                cmd_check,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.timeout_per_gate,
            )
            if res_check.returncode != 0:
                elapsed = time.perf_counter() - start
                output = ((res_check.stdout or "") + "\n" + (res_check.stderr or "")).strip()
                match = re.search(r"Found (\d+) error", output)
                violations = int(match.group(1)) if match else max(1, len(output.splitlines()))
                return GateReport(
                    gate_name="ruff",
                    exit_code=res_check.returncode,
                    duration_seconds=round(elapsed, 4),
                    violations_count=violations,
                    raw_output_snippet=_format_snippet(output),
                )

            remaining_timeout = max(0.01, self.timeout_per_gate - (time.perf_counter() - start))
            res_fmt = subprocess.run(
                cmd_fmt,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=remaining_timeout,
            )
            elapsed = time.perf_counter() - start
            output = ((res_fmt.stdout or "") + "\n" + (res_fmt.stderr or "")).strip()
            violations = 0
            if res_fmt.returncode != 0:
                match = re.search(r"(\d+) files? would be reformatted", output)
                violations = int(match.group(1)) if match else 1

            raw_snippet = _format_snippet(output) if output else "All checks and formatting passed!"
            return GateReport(
                gate_name="ruff",
                exit_code=res_fmt.returncode,
                duration_seconds=round(elapsed, 4),
                violations_count=violations,
                raw_output_snippet=raw_snippet,
            )
        except subprocess.TimeoutExpired:
            return GateReport(
                gate_name="ruff",
                exit_code=124,
                duration_seconds=self.timeout_per_gate,
                violations_count=1,
                raw_output_snippet="Gate timed out",
            )
        except Exception as exc:
            return GateReport(
                gate_name="ruff",
                exit_code=1,
                duration_seconds=0.0,
                violations_count=1,
                raw_output_snippet=_format_snippet(str(exc)),
            )

    def _run_gate_mypy(self, worktree_path: Path) -> GateReport:
        """Gate 2: Mypy strict type checking."""
        cmd = [sys.executable, "-m", "mypy", "--strict"]
        if (worktree_path / "src").is_dir():
            cmd.append("src")
            if (worktree_path / "tests").is_dir():
                cmd.append("tests")
        else:
            # Flat layout: "." already covers tests/, so appending
            # "tests" makes mypy report every test module twice
            # ("Duplicate module ...") and fail clean trees.
            cmd.append(".")
        self._record_argv("mypy", cmd)

        start = time.perf_counter()
        try:
            res = subprocess.run(
                cmd,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.timeout_per_gate,
            )
            elapsed = time.perf_counter() - start
            output = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()

            violations = 0
            if res.returncode != 0:
                match = re.search(r"Found (\d+) error", output)
                if match:
                    violations = int(match.group(1))
                else:
                    violations = max(
                        1, len([line for line in output.splitlines() if ": error:" in line])
                    )

            return GateReport(
                gate_name="mypy",
                exit_code=res.returncode,
                duration_seconds=round(elapsed, 4),
                violations_count=violations,
                raw_output_snippet=_format_snippet(output),
            )
        except subprocess.TimeoutExpired:
            return GateReport(
                gate_name="mypy",
                exit_code=124,
                duration_seconds=self.timeout_per_gate,
                violations_count=1,
                raw_output_snippet="Gate timed out",
            )
        except Exception as exc:
            return GateReport(
                gate_name="mypy",
                exit_code=1,
                duration_seconds=0.0,
                violations_count=1,
                raw_output_snippet=_format_snippet(str(exc)),
            )

    def _run_gate_pytest(
        self,
        worktree_path: Path,
        pytest_target: str | None = None,
    ) -> GateReport:
        """Gate 3: Deterministic Pytest execution.

        Enforces 01_INVARIANTS.md §5: Exit Code == 0 (100% pass, 0 failed, 0 skipped).
        Live-marked tests are deselected per D13 (deterministic zero-skip invariant).
        """
        cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", "-m", "not live"]
        if pytest_target:
            # Trusted-selection targets are space-joined (section 5.2);
            # single-target behavior is unchanged (one token == one arg).
            cmd.extend(shlex.split(pytest_target))
        self._record_argv("pytest", cmd)
        start = time.perf_counter()
        try:
            res = subprocess.run(
                cmd,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.timeout_per_gate,
            )
            elapsed = time.perf_counter() - start
            output = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()

            passed_match = re.search(r"(\d+) passed", output)
            failed_match = re.search(r"(\d+) failed", output)
            skipped_match = re.search(r"(\d+) skipped", output)
            error_match = re.search(r"(\d+) error", output)

            passed_count = int(passed_match.group(1)) if passed_match else 0
            failed_count = int(failed_match.group(1)) if failed_match else 0
            skipped_count = int(skipped_match.group(1)) if skipped_match else 0
            error_count = int(error_match.group(1)) if error_match else 0

            # 01_INVARIANTS.md §5 invariant: 0 skipped tests permitted
            exit_code = res.returncode
            if exit_code == 0 and skipped_count > 0:
                exit_code = 1

            violations = failed_count + error_count + skipped_count
            if exit_code != 0 and violations == 0:
                violations = 1

            tail = _format_snippet(output)
            tally_summary = (
                f"[pytest summary: {passed_count} passed, "
                f"{failed_count} failed, {skipped_count} skipped, {error_count} errors]"
            )
            if skipped_count > 0:
                tally_summary += (
                    f" [INVARIANT VIOLATION: {skipped_count} skipped test(s) detected; "
                    "0 skipped required per 01_INVARIANTS.md §5]"
                )
            snippet = f"{tail}\n{tally_summary}" if tally_summary not in tail else tail

            return GateReport(
                gate_name="pytest",
                exit_code=exit_code,
                duration_seconds=round(elapsed, 4),
                violations_count=violations,
                raw_output_snippet=snippet,
            )
        except subprocess.TimeoutExpired:
            return GateReport(
                gate_name="pytest",
                exit_code=124,
                duration_seconds=self.timeout_per_gate,
                violations_count=1,
                raw_output_snippet="Gate timed out",
            )
        except Exception as exc:
            return GateReport(
                gate_name="pytest",
                exit_code=1,
                duration_seconds=0.0,
                violations_count=1,
                raw_output_snippet=_format_snippet(str(exc)),
            )

    def _run_gate_mutmut(
        self,
        worktree_path: Path,
        run_mutmut: bool = True,
        defer_windows: bool = True,
        paths_to_mutate: list[str] | None = None,
        external_target: bool = False,
    ) -> GateReport:
        """Gate 4: Mutmut mutation testing.

        Enforces Cross-OS Execution Neutrality (01_INVARIANTS.md §3.3) and
        the normative >=85% kill rate threshold (01_INVARIANTS.md §5).
        R3: an explicit paths list scopes the run to exactly those
        production files (config-file scoping in a disposable mirror —
        installed mutmut exposes no --paths-to-mutate flag); an empty
        list fails closed as NOT-MEASURED-never-pass; None keeps the
        legacy whole-tree behavior.
        """
        if not run_mutmut:
            return GateReport(
                gate_name="mutmut",
                exit_code=0,
                duration_seconds=0.0,
                violations_count=0,
                raw_output_snippet="Mutmut Gate disabled by runner configuration.",
            )
        if paths_to_mutate is not None and len(paths_to_mutate) == 0:
            return _mutmut_not_measured(
                "empty mutation set (no production files under src/stc/ in scope)"
            )

        # Cross-OS Neutrality check: Mutmut requires Linux features
        if sys.platform == "win32" and defer_windows:
            if paths_to_mutate:
                return _mutmut_not_measured(
                    "scoped mutmut unsupported on win32/WSL executors "
                    "(no scoped run attempted; refusing silently-unscoped execution)"
                )
            wsl_path = _translate_to_wsl_path(worktree_path)
            wsl_exe = shutil.which("wsl.exe") or shutil.which("wsl")
            wsl_raw_output: str | None = None

            # If WSL is available, attempt execution with path translation
            if wsl_exe:
                wsl_cmd: list[str] = [wsl_exe]
                if self.config.wsl_distribution:
                    wsl_cmd.extend(["-d", self.config.wsl_distribution])

                shell_cmd = (
                    f"cd {wsl_path} && "
                    "(uv run mutmut run || "
                    "python3 -m mutmut run || "
                    "uv run mutmut run --paths-to-mutate src/stc/ || "
                    "python3 -m mutmut run --paths-to-mutate src/stc/) && "
                    "(uv run mutmut export-cicd-stats 2>/dev/null || true) && "
                    "(cat mutants/mutmut-cicd-stats.json 2>/dev/null || true)"
                )
                wsl_cmd.extend(["--", "sh", "-c", shell_cmd])
                self._record_argv("mutmut", wsl_cmd)

                start = time.perf_counter()
                try:
                    res_wsl = subprocess.run(
                        wsl_cmd,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        check=False,
                        timeout=self.timeout_per_gate,
                    )
                    elapsed = time.perf_counter() - start
                    output = ((res_wsl.stdout or "") + "\n" + (res_wsl.stderr or "")).strip()
                    wsl_raw_output = output
                    _killed, survived, _timeout, kill_rate = _parse_mutmut_output(output)

                    if kill_rate is not None:
                        exit_code = 0 if kill_rate >= self.config.mutmut_kill_threshold else 1
                        violations = survived if exit_code != 0 else 0
                        snippet = (
                            f"{_format_snippet(output)}\n"
                            f"[mutmut kill rate: {kill_rate:.2%} "
                            f"(threshold: {self.config.mutmut_kill_threshold:.2%})]"
                        )
                        return GateReport(
                            gate_name="mutmut",
                            exit_code=exit_code,
                            duration_seconds=round(elapsed, 4),
                            violations_count=violations,
                            raw_output_snippet=snippet,
                        )
                except subprocess.TimeoutExpired:
                    return GateReport(
                        gate_name="mutmut",
                        exit_code=124,
                        duration_seconds=self.timeout_per_gate,
                        violations_count=1,
                        raw_output_snippet="Gate timed out in WSL",
                    )
                except Exception as exc:
                    elapsed = time.perf_counter() - start
                    return GateReport(
                        gate_name="mutmut",
                        exit_code=1,
                        duration_seconds=round(elapsed, 4),
                        violations_count=1,
                        raw_output_snippet=_format_snippet(
                            f"WSL execution error at {wsl_path}: {exc}"
                        ),
                    )

            # Explicit deferral disclosure under §3.3 when WSL lacks mutmut
            distro_flag = (
                f"-d {self.config.wsl_distribution} " if self.config.wsl_distribution else ""
            )
            cmd_str = f"`wsl {distro_flag}uv run mutmut run --paths-to-mutate src/stc/`"
            deferral_lines = [
                "Mutmut Gate deferred per 01_INVARIANTS.md §3.3 (Cross-OS Execution Neutrality).",
                f"WSL Target Path: {wsl_path}",
                (
                    "Kill rate status: NOT-MEASURED "
                    "(deferral authority active; not a measured 0-violations pass)."
                ),
                (f"Stage-1 Linux/WSL verification command to achieve >=85% kill rate: {cmd_str}"),
            ]
            if wsl_raw_output:
                deferral_lines.append(f"WSL Output:\n{_format_snippet(wsl_raw_output)}")
            elif not wsl_exe:
                deferral_lines.append("WSL executable not found on host.")

            return GateReport(
                gate_name="mutmut",
                exit_code=0,
                duration_seconds=0.0,
                violations_count=0,
                raw_output_snippet="\n".join(deferral_lines),
            )

        # Native Linux/container execution
        # Prevent recursive execution when invoked inside an active mutmut test runner
        if os.environ.get("MUTANT_UNDER_TEST"):
            return GateReport(
                gate_name="mutmut",
                exit_code=0,
                duration_seconds=0.0,
                violations_count=0,
                raw_output_snippet="Mutmut Gate skipped under active mutation test runner.",
            )
        if paths_to_mutate:
            return self._run_gate_mutmut_scoped(
                worktree_path, paths_to_mutate, external_target=external_target
            )

        cmd = _mutmut_cmd()
        self._record_argv("mutmut", cmd)
        start = time.perf_counter()
        try:
            res = subprocess.run(
                cmd,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.timeout_per_gate,
            )
            elapsed = time.perf_counter() - start
            output = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
            _killed, survived, _timeout, kill_rate = _parse_mutmut_output(output)

            exit_code = res.returncode
            violations = 1 if exit_code != 0 else 0
            if kill_rate is not None:
                if kill_rate < self.config.mutmut_kill_threshold:
                    exit_code = 1
                    violations = max(1, survived)
                output += (
                    f"\n[mutmut kill rate: {kill_rate:.2%} "
                    f"(threshold: {self.config.mutmut_kill_threshold:.2%})]"
                )

            return GateReport(
                gate_name="mutmut",
                exit_code=exit_code,
                duration_seconds=round(elapsed, 4),
                violations_count=violations,
                raw_output_snippet=_format_snippet(output),
            )
        except subprocess.TimeoutExpired:
            return GateReport(
                gate_name="mutmut",
                exit_code=124,
                duration_seconds=self.timeout_per_gate,
                violations_count=1,
                raw_output_snippet="Gate timed out",
            )
        except Exception as exc:
            return GateReport(
                gate_name="mutmut",
                exit_code=1,
                duration_seconds=0.0,
                violations_count=1,
                raw_output_snippet=_format_snippet(str(exc)),
            )

    def _run_gate_mutmut_scoped(
        self, worktree_path: Path, paths: list[str], *, external_target: bool = False
    ) -> GateReport:
        """Gate 4 scoped: mutmut over exactly `paths` in a disposable mirror (R3).

        The mirror carries a generated [tool.mutmut] table pinning
        source_paths to the derived list plus forced live-deselect; the
        lease itself is never written. Zero judged mutants (empty mutant
        set, total infra collapse, or unparseable output) fails closed as
        NOT-MEASURED — never a vacuous pass.
        """
        cmd = _mutmut_cmd()
        self._record_argv("mutmut", cmd)
        start = time.perf_counter()
        try:
            with _scoped_mutmut_tree(
                worktree_path, paths, external_target=external_target
            ) as scope:
                res = subprocess.run(
                    cmd,
                    cwd=scope,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=self.timeout_per_gate,
                )
        except subprocess.TimeoutExpired:
            return GateReport(
                gate_name="mutmut",
                exit_code=124,
                duration_seconds=self.timeout_per_gate,
                violations_count=1,
                raw_output_snippet="Gate timed out",
            )
        except Exception as exc:
            return GateReport(
                gate_name="mutmut",
                exit_code=1,
                duration_seconds=round(time.perf_counter() - start, 4),
                violations_count=1,
                raw_output_snippet=_format_snippet(str(exc)),
            )
        elapsed = time.perf_counter() - start
        output = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        counts = _parse_mutmut_counts(output)
        if counts.killed + counts.survived + counts.timeout == 0:
            return _mutmut_not_measured(
                f"empty mutant set (no judged mutants over {len(paths)} scoped path(s))",
                detail=output,
            )
        targets = _mutmut_targets_line(paths, counts, self.config.mutmut_kill_threshold)
        exit_code = res.returncode
        violations = 1 if exit_code != 0 else 0
        if counts.kill_rate is not None:
            if counts.kill_rate < self.config.mutmut_kill_threshold:
                exit_code = 1
                violations = max(1, counts.survived)
            output += (
                f"\n[mutmut kill rate: {counts.kill_rate:.2%} "
                f"(threshold: {self.config.mutmut_kill_threshold:.2%})]"
            )
        return GateReport(
            gate_name="mutmut",
            exit_code=exit_code,
            duration_seconds=round(elapsed, 4),
            violations_count=violations,
            raw_output_snippet=f"{targets}\n{_format_snippet(output)}",
        )


__all__ = [
    "MUTMUT_TARGETS_PREFIX",
    "MutmutCounts",
    "ReceiptSigner",
    "SubstrateRunner",
    "SubstrateRunnerConfig",
    "compute_receipt_signature",
    "compute_receipt_signature_for_model",
    "create_receipt",
    "load_receipt",
    "parse_mutmut_targets",
    "save_receipt",
    "serialize_canonical_payload",
    "verify_receipt",
]
