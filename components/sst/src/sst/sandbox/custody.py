"""Exact-patch candidate custody and isolated verifier management."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, ClassVar, Final

from pydantic import BaseModel, Field

from sst.core.contracts import CandidateProposal, TaskPacket
from sst.core.models import AcceptanceCommandResult, DeterministicGateResult
from sst.protocols.executor import EXECUTOR_PROTOCOL_VERSION


def compute_proposal_hash(patch_diff: str, file_operations: list[dict[str, Any]]) -> str:
    """Canonical content hash binding verified bytes to a proposal.

    Covers both the diff payload and any explicit file operations. The
    verifier records it; promote recomputes and compares, so logged bytes
    altered after verification are refused. The form is part of the
    persisted contract: do not change it without a migration.
    """
    canonical_ops = json.dumps(file_operations, sort_keys=True, default=str)
    return hashlib.sha256(f"{patch_diff}\n{canonical_ops}".encode()).hexdigest()


#: Directory names never covered by workspace digests (SST-owned state,
#: version control, environments, caches). Search-time snapshots and
#: promote-time comparisons use the same exclusion set, so SST's own
#: databases and worktrees can grow without invalidating the snapshot.
DIGEST_EXCLUDE_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".auto",
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hypothesis",
        ".sst",
        ".tox",
        ".venv",
        "__pycache__",
        "htmlcov",
        "node_modules",
    }
)


def compute_workspace_digest(root: Path | str) -> str:
    """Content digest of a workspace for search/promote staleness checks.

    Covers every regular file except dotfiles and DIGEST_EXCLUDE_DIRS
    (pruned at every level). Deterministic for identical trees.
    """
    hasher = hashlib.sha256()
    ws = Path(root)
    for dirpath, dirnames, filenames in os.walk(str(ws)):
        # Prune in place (top-down) so excluded trees are never traversed;
        # sorting keeps traversal order deterministic.
        dirnames[:] = sorted(d for d in dirnames if d not in DIGEST_EXCLUDE_DIRS)
        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            fpath = Path(dirpath) / fname
            try:
                hasher.update(fpath.relative_to(ws).as_posix().encode())
                hasher.update(fpath.read_bytes())
            except OSError:
                pass
    return hasher.hexdigest()


class PatchApplicationResult(BaseModel):
    """Result of attempting to apply a candidate patch proposal."""

    success: bool
    applied_files: list[str] = Field(default_factory=list)
    error_message: str | None = None
    patch_hash: str = ""
    post_patch_digest: str = ""


class CandidateCustodyManager:
    """Manages detached candidate worktrees and exact-patch verification sandboxes.

    This is the default :class:`ExecutorProtocol` implementation: patch
    failures are returned as results, acceptance timeouts return
    ``passed=False`` with ``exit_code=124``, and only programming errors raise.
    """

    executor_version: ClassVar[str] = EXECUTOR_PROTOCOL_VERSION

    SECRET_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
        re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
        re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----", re.IGNORECASE),
    ]

    def __init__(self, base_worktree_dir: Path | str | None = None) -> None:
        self.base_worktree_dir = Path(base_worktree_dir) if base_worktree_dir else Path(".sst/worktrees")

    def create_candidate_workspace(self, tree_id: str, candidate_id: str, source_dir: Path | str) -> Path:
        """Creates an isolated candidate workspace/worktree for branch execution."""
        candidate_ws = self.base_worktree_dir / tree_id / candidate_id
        candidate_ws.mkdir(parents=True, exist_ok=True)
        src = Path(source_dir)

        # Mirror base files if source directory exists
        if src.exists() and src.is_dir():
            for item in src.iterdir():
                # Skip recursive worktrees or heavy git locks
                if item.name in {".auto", ".sst", ".git", ".venv", "__pycache__", ".pytest_cache"}:
                    continue
                target = candidate_ws / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)

        return candidate_ws

    def cleanup_candidate(self, tree_id: str, candidate_id: str) -> None:
        """Removes an isolated candidate workspace directory."""
        candidate_ws = self.base_worktree_dir / tree_id / candidate_id
        if candidate_ws.exists():
            shutil.rmtree(candidate_ws, ignore_errors=True)

    def cleanup_tree(self, tree_id: str) -> None:
        """Removes the entire workspace tree directory for a search tree."""
        tree_ws = self.base_worktree_dir / tree_id
        if tree_ws.exists():
            shutil.rmtree(tree_ws, ignore_errors=True)

    def _validate_path_containment(
        self,
        workspace_dir: Path,
        path_str: str,
        task: TaskPacket | None = None,
    ) -> Path:
        """Validates that a path is strictly contained within workspace and obeys task scope rules."""
        clean_path = path_str.strip().lstrip("/\\")
        resolved = (workspace_dir / clean_path).resolve()
        ws_resolved = workspace_dir.resolve()

        if not resolved.is_relative_to(ws_resolved):
            raise ValueError(f"Path Traversal Violation: Target path '{path_str}' escapes workspace boundary.")

        if task:
            # Check forbidden paths
            for forbidden in task.forbidden_paths:
                clean_forbid = forbidden.strip().lstrip("/\\")
                if (
                    clean_path == clean_forbid
                    or clean_path.startswith(f"{clean_forbid}/")
                    or clean_path.startswith(f"{clean_forbid}\\")
                ):
                    raise ValueError(f"Scope Policy Violation: Modifying forbidden path '{path_str}'.")

            # Check allowed paths (if specified)
            if task.allowed_paths:
                is_allowed = False
                for allowed in task.allowed_paths:
                    clean_allowed = allowed.strip().lstrip("/\\")
                    if (
                        clean_path == clean_allowed
                        or clean_path.startswith(f"{clean_allowed}/")
                        or clean_path.startswith(f"{clean_allowed}\\")
                    ):
                        is_allowed = True
                        break
                if not is_allowed:
                    raise ValueError(f"Scope Policy Violation: Path '{path_str}' not in task allowed_paths.")

        return resolved

    def apply_proposal(
        self,
        proposal: CandidateProposal,
        workspace_dir: Path | str,
        task: TaskPacket | None = None,
    ) -> PatchApplicationResult:
        """Applies a candidate proposal to an isolated workspace with strict security & path validation."""
        workspace_dir = Path(workspace_dir).resolve()

        # 1. Security Check: Secret scan in patch diff
        diff_text = proposal.patch_diff
        for pattern in self.SECRET_PATTERNS:
            if pattern.search(diff_text):
                return PatchApplicationResult(
                    success=False,
                    error_message="Security Policy Violation: Candidate patch contains hardcoded secret or token.",
                )

        # 2. Path Containment & Scope Check on declared target_paths
        for path_str in proposal.target_paths:
            try:
                self._validate_path_containment(workspace_dir, path_str, task=task)
            except ValueError as e:
                return PatchApplicationResult(
                    success=False,
                    error_message=str(e),
                )

        applied_files: list[str] = []

        # 3. Apply Explicit File Operations (with containment validation on every operation)
        if proposal.file_operations:
            for op in proposal.file_operations:
                rel_path = op.get("path", "")
                content = op.get("content", "")
                action = op.get("action", "write")

                # Secret scan on file content
                for pattern in self.SECRET_PATTERNS:
                    if pattern.search(content):
                        return PatchApplicationResult(
                            success=False,
                            error_message="Security Policy Violation: File operation contains hardcoded secret.",
                        )

                try:
                    target_file = self._validate_path_containment(workspace_dir, rel_path, task=task)
                except ValueError as e:
                    return PatchApplicationResult(
                        success=False,
                        error_message=str(e),
                    )

                if action == "delete":
                    if target_file.exists():
                        target_file.unlink()
                else:
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text(content, encoding="utf-8")
                applied_files.append(rel_path)

        elif diff_text:
            # Check if it's a unified diff
            if diff_text.startswith("--- ") or "@@" in diff_text or diff_text.startswith("diff --git"):
                # Try applying via git apply in workspace or fallback parser
                patch_file = workspace_dir / ".candidate.patch"
                try:
                    patch_file.write_text(diff_text, encoding="utf-8")
                    cmd = ["git", "apply", "--whitespace=nowarn", str(patch_file)]
                    res = subprocess.run(cmd, cwd=str(workspace_dir), capture_output=True, text=True, timeout=30)
                    if res.returncode != 0:
                        # Fallback parsing with strict containment check
                        fallback_err = self._apply_unified_diff_manually(diff_text, workspace_dir, task=task)
                        if fallback_err:
                            return PatchApplicationResult(
                                success=False,
                                error_message=f"git apply failed: {res.stderr} | fallback: {fallback_err}",
                            )
                finally:
                    if patch_file.exists():
                        patch_file.unlink()
            else:
                # Direct file replacement using target_paths[0] if single file
                if proposal.target_paths:
                    try:
                        target = self._validate_path_containment(workspace_dir, proposal.target_paths[0], task=task)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(diff_text, encoding="utf-8")
                        applied_files.append(proposal.target_paths[0])
                    except ValueError as e:
                        return PatchApplicationResult(
                            success=False,
                            error_message=str(e),
                        )
                else:
                    return PatchApplicationResult(
                        success=False,
                        error_message="Target path required for raw code payload",
                    )

        patch_hash = compute_proposal_hash(diff_text, proposal.file_operations)
        post_digest = self._compute_workspace_digest(workspace_dir)

        return PatchApplicationResult(
            success=True,
            applied_files=applied_files or proposal.target_paths,
            patch_hash=patch_hash,
            post_patch_digest=post_digest,
        )

    def verify_candidate_proposal(
        self,
        task: TaskPacket,
        proposal: CandidateProposal,
        source_dir: Path | str,
        acceptance_command: str | None = None,
        timeout: int = 120,
    ) -> DeterministicGateResult:
        """Executes candidate application and runs acceptance tests in an isolated, credential-scrubbed sandbox."""
        start_time = time.perf_counter()
        source_dir = Path(source_dir)

        with tempfile.TemporaryDirectory() as tmp_dir:
            isolated_ws = Path(tmp_dir) / "verifier_ws"
            isolated_ws.mkdir(parents=True, exist_ok=True)

            # Copy source directory
            if source_dir.exists() and source_dir.is_dir():
                for item in source_dir.iterdir():
                    if item.name in {".auto", ".sst", ".git", ".venv", "__pycache__", ".pytest_cache"}:
                        continue
                    target = isolated_ws / item.name
                    if item.is_dir():
                        shutil.copytree(item, target, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, target)

            # Apply candidate proposal
            app_result = self.apply_proposal(proposal, isolated_ws, task=task)
            if not app_result.success:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=1,
                    stdout="",
                    stderr=app_result.error_message or "Patch application failed",
                    duration_seconds=time.perf_counter() - start_time,
                    failure_reason=app_result.error_message,
                )

            # Determine acceptance commands: an explicit override runs alone,
            # otherwise EVERY task acceptance command runs. No command means no
            # acceptance ran, which is an explicit failure, never a PASS.
            cmds = [acceptance_command] if acceptance_command else list(task.acceptance_commands)
            if not cmds:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=1,
                    stdout="",
                    stderr="No acceptance command configured: patch application validated only.",
                    duration_seconds=time.perf_counter() - start_time,
                    failure_reason=(
                        "No acceptance command: candidate applied and scope-checked, "
                        "but no acceptance ran, so verification is incomplete."
                    ),
                )

            # Scrub sensitive credentials from execution environment
            scrubbed_env = {
                k: v
                for k, v in os.environ.items()
                if not any(
                    pat in k.upper()
                    for pat in ["KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL", "AWS_", "SSH_", "GH_"]
                )
            }
            scrubbed_env["AUTO_SANDBOX"] = "1"
            scrubbed_env["SST_SANDBOX"] = "1"
            current_bin = str(Path(sys.executable).parent)
            existing_path = scrubbed_env.get("PATH", "")
            if current_bin not in existing_path.split(os.pathsep):
                scrubbed_env["PATH"] = f"{current_bin}{os.pathsep}{existing_path}" if existing_path else current_bin

            # Execute every acceptance command in the scrubbed environment.
            # timeout applies per command; the gate passes only if all pass.
            command_results: list[AcceptanceCommandResult] = []
            stdout_parts: list[str] = []
            stderr_parts: list[str] = []
            for cmd in cmds:
                cmd_start = time.perf_counter()
                try:
                    proc = subprocess.run(
                        cmd,
                        cwd=str(isolated_ws),
                        env=scrubbed_env,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    cmd_passed = proc.returncode == 0
                    command_results.append(
                        AcceptanceCommandResult(
                            command=cmd,
                            exit_code=proc.returncode,
                            passed=cmd_passed,
                            stdout=proc.stdout[-4000:],
                            stderr=proc.stderr[-4000:],
                            duration_seconds=time.perf_counter() - cmd_start,
                        )
                    )
                    stdout_parts.append(f"$ {cmd}\n{proc.stdout[-4000:]}")
                    stderr_parts.append(f"$ {cmd}\n{proc.stderr[-4000:]}")
                except subprocess.TimeoutExpired:
                    command_results.append(
                        AcceptanceCommandResult(
                            command=cmd,
                            exit_code=124,
                            passed=False,
                            stdout="",
                            stderr=f"Verifier timed out after {timeout} seconds",
                            duration_seconds=float(timeout),
                        )
                    )
                    stderr_parts.append(f"$ {cmd}\nVerifier timed out after {timeout} seconds")

            duration = time.perf_counter() - start_time
            passed = all(r.passed for r in command_results)
            exit_code = 0 if passed else next(r.exit_code for r in command_results if not r.passed)

            def _summarize(result: AcceptanceCommandResult) -> str:
                if result.exit_code == 124 and "timed out" in result.stderr:
                    return f"{result.command} (timeout)"
                return f"{result.command} (exit {result.exit_code})"

            failed = [_summarize(r) for r in command_results if not r.passed]
            return DeterministicGateResult(
                passed=passed,
                exit_code=exit_code,
                stdout="\n".join(stdout_parts)[-8000:],
                stderr="\n".join(stderr_parts)[-8000:],
                duration_seconds=duration,
                failure_reason=None if passed else f"Acceptance failed: {failed}",
                command_results=command_results,
                patch_hash=app_result.patch_hash,
                post_patch_digest=app_result.post_patch_digest,
            )

    def _compute_workspace_digest(self, workspace_dir: Path | str) -> str:
        """Computes a recursive SHA256 digest of workspace files."""
        hasher = hashlib.sha256()
        ws = Path(workspace_dir)
        for root, _, files in sorted(os.walk(str(ws))):
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                fpath = Path(root) / fname
                try:
                    hasher.update(fname.encode("utf-8"))
                    hasher.update(fpath.read_bytes())
                except Exception:
                    pass
        return hasher.hexdigest()

    def _apply_unified_diff_manually(
        self,
        diff_text: str,
        workspace_dir: Path,
        task: TaskPacket | None = None,
    ) -> str | None:
        """Line-based unified diff fallback parser with hunk parsing and strict path containment checks."""
        try:
            lines = diff_text.splitlines()
            if not lines:
                return "Empty diff payload"

            file_blocks: list[dict[str, Any]] = []
            curr_old_path: str | None = None
            curr_new_path: str | None = None
            curr_hunks: list[tuple[int, int, int, int, list[str]]] = []
            curr_hunk_lines: list[str] = []
            curr_hunk_header: tuple[int, int, int, int] | None = None

            i = 0
            while i < len(lines):
                line = lines[i]
                if line.startswith("--- "):
                    if curr_hunk_header is not None:
                        curr_hunks.append((*curr_hunk_header, curr_hunk_lines))
                        curr_hunk_header = None
                        curr_hunk_lines = []
                    if curr_new_path is not None:
                        file_blocks.append(
                            {
                                "old_path": curr_old_path,
                                "new_path": curr_new_path,
                                "hunks": curr_hunks,
                            }
                        )
                        curr_hunks = []
                    raw_old = line[4:].strip()
                    curr_old_path = raw_old[2:] if raw_old.startswith("a/") else raw_old
                    i += 1
                    if i < len(lines) and lines[i].startswith("+++ "):
                        raw_new = lines[i][4:].strip()
                        curr_new_path = raw_new[2:] if raw_new.startswith("b/") else raw_new
                        i += 1
                    else:
                        curr_new_path = None
                    continue

                if line.startswith("@@"):
                    if curr_hunk_header is not None:
                        curr_hunks.append((*curr_hunk_header, curr_hunk_lines))
                        curr_hunk_lines = []
                    hunk_match = re.match(r"@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", line)
                    if hunk_match:
                        old_s = int(hunk_match.group(1))
                        old_c = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
                        new_s = int(hunk_match.group(3))
                        new_c = int(hunk_match.group(4)) if hunk_match.group(4) is not None else 1
                        curr_hunk_header = (old_s, old_c, new_s, new_c)
                    else:
                        return f"Invalid hunk header format: {line}"
                    i += 1
                    continue

                if curr_hunk_header is not None:
                    curr_hunk_lines.append(line)
                i += 1

            if curr_hunk_header is not None:
                curr_hunks.append((*curr_hunk_header, curr_hunk_lines))
            if curr_new_path is not None:
                file_blocks.append(
                    {
                        "old_path": curr_old_path,
                        "new_path": curr_new_path,
                        "hunks": curr_hunks,
                    }
                )

            if not file_blocks:
                return "Could not identify target file from diff header"

            for block in file_blocks:
                rel_path = block["new_path"]
                if rel_path == "/dev/null" or rel_path is None:
                    if block["old_path"] and block["old_path"] != "/dev/null":
                        target_file = self._validate_path_containment(workspace_dir, block["old_path"], task=task)
                        if target_file.exists():
                            target_file.unlink()
                    continue

                target_file = self._validate_path_containment(workspace_dir, rel_path, task=task)
                hunks = block["hunks"]
                if not hunks:
                    return f"No hunks found for target file {rel_path}"

                if target_file.exists():
                    orig_lines = target_file.read_text(encoding="utf-8").splitlines()
                else:
                    orig_lines = []

                new_file_lines: list[str] = []
                orig_idx = 0

                for old_s, _old_c, _new_s, _new_c, hunk_lines in hunks:
                    target_idx = max(0, old_s - 1) if old_s > 0 else 0
                    if target_idx < orig_idx:
                        return f"Overlapping or out-of-order hunks in diff for {rel_path}"

                    new_file_lines.extend(orig_lines[orig_idx:target_idx])
                    orig_idx = target_idx

                    for hline in hunk_lines:
                        if not hline:
                            if orig_idx < len(orig_lines) and orig_lines[orig_idx] == "":
                                new_file_lines.append("")
                                orig_idx += 1
                            else:
                                new_file_lines.append("")
                            continue
                        prefix = hline[0]
                        text = hline[1:]
                        if prefix == " ":
                            if orig_idx < len(orig_lines):
                                if orig_lines[orig_idx] != text:
                                    return f"Context mismatch in {rel_path} at line {orig_idx + 1}: expected '{text}', got '{orig_lines[orig_idx]}'"
                                new_file_lines.append(orig_lines[orig_idx])
                                orig_idx += 1
                            else:
                                return f"Context mismatch in {rel_path}: hunk extends beyond original file length"
                        elif prefix == "-":
                            if orig_idx < len(orig_lines):
                                if orig_lines[orig_idx] != text:
                                    return f"Deletion mismatch in {rel_path} at line {orig_idx + 1}: expected '{text}', got '{orig_lines[orig_idx]}'"
                                orig_idx += 1
                            else:
                                return f"Deletion mismatch in {rel_path}: deletion extends beyond original file length"
                        elif prefix == "+":
                            new_file_lines.append(text)
                        elif prefix == "\\":
                            pass
                        else:
                            return f"Unrecognized diff line format in {rel_path}: '{hline}'"

                new_file_lines.extend(orig_lines[orig_idx:])
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text("\n".join(new_file_lines) + ("\n" if new_file_lines else ""), encoding="utf-8")

            return None
        except ValueError as e:
            return str(e)
        except Exception as e:
            return str(e)
