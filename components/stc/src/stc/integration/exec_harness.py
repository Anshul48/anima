"""Operator-authorized executable harness (custom user harness, F11 intact).

:class:`ExecHarness` satisfies the :class:`HarnessT` structural protocol so a
user-supplied Linux executable can serve one gateway call per ``execute()``.
It is NOT a shell/command-template harness: the argv is fixed at construction
(no ``{prompt}`` templating, no shell), the prompt travels on stdin, and the
class carries no ``command_template`` attribute. The CLI allowlist
(:data:`CLI_HARNESS_NAMES`) is untouched — this rides the same injection seam
as the ``--manual`` harness (``CLIGatewayBackend("mock", harness=...)``) with
an honest ledger identity (``task_label="exec:<exe name>"``), never a fake
``codex``.

Child contract (documented for harness authors):
  - argv: ``[exe]`` exactly; prompt bytes on stdin (UTF-8).
  - env: inherits the backend env plus fixed ``STC_HARNESS_ROLE`` (the SST
    role label: diverge/refine/critique/…, or ``gateway`` when the caller
    passes no role) — fixed keys only, no templating.
  - cwd: ``context["project_root"]`` (the source root).
  - stdout (UTF-8): the response content. stderr: error detail on failure.
  - exit 0: success; any other exit: failure result (content preserved).
  - kill on timeout maps to an exit-124 failure result (same convention as
    :func:`run_harness_attempt`).

Agency note: the executable runs in-process-spawned with the operator's local
agency (it can read the source root). Use is operator-authorized per launch
(an explicit CLI flag / console LAUNCH) and recorded in the dossier
limitations; it must never be triggered unattended.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from stc.integration.harness_worker import HarnessConfigError

#: Fixed env key carrying the SST role label to the child (no templating).
ROLE_ENV_KEY = "STC_HARNESS_ROLE"

#: Exit code marking a harness timeout (mirrors run_harness_attempt).
TIMEOUT_EXIT_CODE = 124


class ExecHarness:
    """Run a fixed operator-authorized executable per harness call."""

    def __init__(self, exe: Path | str, *, timeout: float = 600.0) -> None:
        resolved = Path(exe).expanduser()
        if not resolved.is_absolute():
            raise HarnessConfigError(f"Exec harness path must be absolute, got {str(exe)!r}.")
        if not resolved.is_file():
            raise HarnessConfigError(f"Exec harness is not a file: {resolved}.")
        if not os.access(resolved, os.X_OK):
            raise HarnessConfigError(f"Exec harness is not executable: {resolved}.")
        if timeout <= 0:
            raise HarnessConfigError("timeout must be positive seconds.")
        self._exe = resolved
        self._timeout = timeout

    @property
    def exe(self) -> Path:
        """Absolute path of the authorized executable."""
        return self._exe

    @property
    def timeout(self) -> float:
        """Per-call timeout in seconds."""
        return self._timeout

    def execute(
        self,
        prompt: str,
        role: str = "general",
        model: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Run the executable once: prompt on stdin, stdout is the content."""
        from prompt_kit.harnesses.base import HarnessResult

        _ = model
        project_root = (context or {}).get("project_root") or str(Path.cwd())
        env = dict(os.environ)
        env[ROLE_ENV_KEY] = role
        try:
            proc = subprocess.run(
                [str(self._exe)],
                cwd=str(project_root),
                env=env,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._timeout,
                check=False,
            )
        except UnicodeDecodeError as exc:
            return HarnessResult(
                content="",
                exit_code=1,
                error=f"Exec harness emitted undecodable output (want UTF-8): {exc}",
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout if isinstance(exc.stdout, str) else ""
            return HarnessResult(
                content=partial or "",
                exit_code=TIMEOUT_EXIT_CODE,
                error=f"Exec harness timed out after {self._timeout}s",
            )
        except OSError as exc:
            return HarnessResult(
                content="",
                exit_code=1,
                error=f"Exec harness spawn failed: {exc}",
            )
        if proc.returncode != 0:
            return HarnessResult(
                content=proc.stdout,
                exit_code=proc.returncode,
                error=proc.stderr.strip() or f"Process exited with code {proc.returncode}",
                raw_response=proc,
            )
        return HarnessResult(content=proc.stdout, exit_code=0, raw_response=proc)
