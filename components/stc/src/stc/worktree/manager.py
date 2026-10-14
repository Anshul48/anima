"""Morphogenetic Cellular Worktree Manager (Subsystem 3).

Provides total filesystem and Git branch isolation for executive coding workers.
Enforces the Leased -> Expired -> Quarantined TTL lifecycle and manages
feature/stc-{id}-e{epoch} branches.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from stc.core.config import Settings, get_settings
from stc.core.errors import WorktreeError, WorktreeLeaseActiveError
from stc.protocols.interfaces import WorktreeManagerProtocol
from stc.schemas.models import WorktreeLease

logger = logging.getLogger(__name__)

_thread_local = threading.local()


class WorktreeManager(WorktreeManagerProtocol):
    """Morphogenetic cellular worktree manager.

    Allocates, isolates, and purges Git worktrees for executive worker sessions.
    Guarantees that no worker can directly contaminate the main branch or repository root.
    """

    def __init__(
        self,
        repo_root: Path | None = None,
        worktree_root: Path | None = None,
        ttl_seconds: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved_settings = settings or get_settings()
        self.repo_root = (
            repo_root or self._detect_repo_root() or resolved_settings.workspace_root
        ).resolve()

        if worktree_root is not None:
            self.worktree_root = Path(worktree_root).resolve()
        elif "STC_WORKTREE_ROOT" in os.environ:
            self.worktree_root = Path(os.environ["STC_WORKTREE_ROOT"]).resolve()
        else:
            self.worktree_root = (self.repo_root / "worktrees").resolve()

        self.ttl_seconds = (
            ttl_seconds if ttl_seconds is not None else resolved_settings.worktree_ttl_seconds
        )
        self._leases_file = self.worktree_root / ".leases.json"
        self._lock_file = self.worktree_root / ".leases.lock"

    @contextlib.contextmanager
    def _lock_leases(self, timeout: float = 10.0) -> Generator[None, None, None]:
        """Cross-process and reentrant file lock for .leases.json synchronization."""
        depth = getattr(_thread_local, "lock_depth", 0)
        if depth > 0:
            _thread_local.lock_depth = depth + 1
            try:
                yield
            finally:
                _thread_local.lock_depth -= 1
            return

        self.worktree_root.mkdir(parents=True, exist_ok=True)
        _thread_local.lock_depth = 1
        try:
            with self._lock_file.open("a+b") as lock_fd:
                has_fcntl = False
                try:
                    import fcntl

                    has_fcntl = True
                except ImportError as exc:
                    logger.debug("fcntl unavailable: %s", exc)

                has_msvcrt = False
                try:
                    import msvcrt

                    has_msvcrt = True
                except ImportError as exc:
                    logger.debug("msvcrt unavailable: %s", exc)

                start_time = time.time()
                locked = False
                while not locked:
                    try:
                        if has_fcntl:
                            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            locked = True
                        elif has_msvcrt:
                            lock_fd.seek(0)
                            msvcrt_mod: Any = msvcrt
                            msvcrt_mod.locking(lock_fd.fileno(), msvcrt_mod.LK_NBLCK, 1)
                            locked = True
                        else:
                            locked = True
                    except (BlockingIOError, OSError):
                        if time.time() - start_time > timeout:
                            raise WorktreeError(
                                f"Timeout ({timeout}s) acquiring lease lock on {self._lock_file}; "
                                "failing closed to prevent lease metadata corruption."
                            ) from None
                        time.sleep(0.01)
                try:
                    yield
                finally:
                    if locked:
                        try:
                            if has_fcntl:
                                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                            elif has_msvcrt:
                                lock_fd.seek(0)
                                msvcrt_mod = msvcrt
                                msvcrt_mod.locking(lock_fd.fileno(), msvcrt_mod.LK_UNLCK, 1)
                        except OSError as exc:
                            logger.debug("Lock release suppressed exception: %s", exc)
        finally:
            _thread_local.lock_depth = 0

    def _detect_repo_root(self) -> Path | None:
        """Detect top-level git repository directory from current working directory.

        Prioritizes --git-common-dir so that invocation from within a git worktree
        resolves the true repository root rather than the ephemeral worktree itself.
        """
        try:
            res_common = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5.0,
            )
            if res_common.returncode == 0 and res_common.stdout and res_common.stdout.strip():
                raw_common = Path(res_common.stdout.strip())
                if not raw_common.is_absolute():
                    raw_common = (Path.cwd() / raw_common).resolve()
                else:
                    raw_common = raw_common.resolve()
                for p in [raw_common, *raw_common.parents]:
                    if p.name == ".git":
                        return p.parent
        except (subprocess.SubprocessError, OSError) as exc:
            logger.debug("Could not resolve git-common-dir: %s", exc)

        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=5.0,
            )
            if res.returncode == 0 and res.stdout and res.stdout.strip():
                return Path(res.stdout.strip()).resolve()
        except (subprocess.SubprocessError, OSError) as exc:
            logger.debug("Could not resolve git toplevel: %s", exc)
        return None

    def _run_git(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Execute git command safely with standardized error propagation."""
        target_cwd = cwd or self.repo_root
        try:
            res = subprocess.run(
                ["git", *cmd],
                cwd=target_cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=30.0,
            )
        except FileNotFoundError:
            raise WorktreeError("Git executable not found on system PATH.") from None
        except subprocess.TimeoutExpired:
            raise WorktreeError(f"Git command timed out: git {' '.join(cmd)}") from None

        if check and res.returncode != 0:
            err = res.stderr.strip() or res.stdout.strip()
            raise WorktreeError(f"Git command failed (exit {res.returncode}): {err}")
        return res

    def _normalize_task_id(self, task_id: str) -> str:
        """Normalize task ID for branch and directory naming without redundant stc- prefixes."""
        clean = task_id.strip().lower()
        while clean.startswith("stc-") or clean.startswith("stc_"):
            clean = clean[4:]
        if (
            not clean
            or clean in (".", "..")
            or clean.endswith(".lock")
            or not re.match(r"^[a-zA-Z0-9_\-\.]+$", clean)
        ):
            raise WorktreeError(
                f"Invalid task_id '{task_id}': cannot contain path separators, "
                "traversals, or invalid characters."
            )
        return clean

    def _load_leases(self) -> dict[str, dict[str, Any]]:
        """Load persisted lease records from worktree root."""
        if not self._leases_file.is_file():
            return {}
        try:
            data = self._leases_file.read_text(encoding="utf-8")
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return {str(k): dict(v) for k, v in parsed.items() if isinstance(v, dict)}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read leases file %s: %s", self._leases_file, exc)
        return {}

    def _save_leases(self, records: dict[str, dict[str, Any]]) -> None:
        """Safely write lease records to worktree root via atomic swap."""
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        temp_file = self._leases_file.with_suffix(f".tmp.{uuid.uuid4().hex[:6]}")
        data = json.dumps(records, indent=2, default=str)
        temp_file.write_text(data, encoding="utf-8")
        temp_file.replace(self._leases_file)

    def _get_git_worktrees(self) -> list[dict[str, str]]:
        """Parse git worktree list --porcelain output."""
        res = self._run_git(["worktree", "list", "--porcelain"])
        entries: list[dict[str, str]] = []
        if res.returncode == 0 and res.stdout and res.stdout.strip():
            current_entry: dict[str, str] = {}
            for line in res.stdout.splitlines():
                if line.startswith("worktree "):
                    if current_entry:
                        entries.append(current_entry)
                        current_entry = {}
                    current_entry["worktree"] = line.split(" ", 1)[1]
                elif line.startswith("HEAD "):
                    current_entry["HEAD"] = line.split(" ", 1)[1]
                elif line.startswith("branch "):
                    current_entry["branch"] = line.split(" ", 1)[1].replace("refs/heads/", "")
            if current_entry:
                entries.append(current_entry)
        return entries

    def check_ttl(self, task_id: str | None = None) -> list[dict[str, Any]]:
        """Evaluate active leases against TTL and execute Leased -> Expired -> Quarantined.

        Per 01_INVARIANTS.md §3.2 and 03_LOSSLESS_SUBSYSTEM_SPECS.md §3.2:
        Expiry follows an explicit transition: Leased -> Expired -> Quarantined.
        The worktree is frozen for inspection and its refutation recorded.
        Resuming requires a brand-new lease record, never silent reuse.
        Expired or abandoned worktrees are quarantined and pruned.
        """
        with self._lock_leases():
            records = self._load_leases()
            now = datetime.now(UTC)
            quarantined: list[dict[str, Any]] = []

            for tid, rec in list(records.items()):
                if task_id is not None and tid != self._normalize_task_id(task_id):
                    continue
                if not rec.get("is_active", False):
                    continue

                expires_at_str = rec.get("expires_at")
                if not expires_at_str:
                    continue
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=UTC)
                except ValueError:
                    continue

                if now >= expires_at:
                    # Explicit Transition Step 1: Leased -> Expired
                    rec["status"] = "EXPIRED"
                    rec["expired_at"] = now.isoformat()
                    logger.warning(
                        "Lease %s for task %s expired at %s",
                        rec.get("lease_id"),
                        rec.get("task_id"),
                        expires_at_str,
                    )

                    # Explicit Transition Step 2: Expired -> Quarantined
                    rec["status"] = "QUARANTINED"
                    rec["is_active"] = False
                    rec["quarantined_at"] = now.isoformat()
                    rec["transition_history"] = ["LEASED", "EXPIRED", "QUARANTINED"]

                    refutation: dict[str, Any] = {
                        "task_id": rec.get("task_id"),
                        "lease_id": rec.get("lease_id"),
                        "reason": f"TTL lapsed without renewal (expired at {expires_at_str})",
                        "quarantined_at": now.isoformat(),
                        "status": "QUARANTINED",
                        "transition_history": ["LEASED", "EXPIRED", "QUARANTINED"],
                    }
                    rec["refutation_record"] = refutation

                    # Freeze worktree for inspection
                    wt_path = Path(rec.get("worktree_path", ""))
                    if wt_path.is_dir():
                        quarantine_file = wt_path / ".quarantined.json"
                        try:
                            quarantine_file.write_text(
                                json.dumps(refutation, indent=2), encoding="utf-8"
                            )
                        except OSError as exc:
                            logger.warning("Could not write quarantine record: %s", exc)

                    quarantined.append(rec)

            if quarantined:
                self._save_leases(records)

            return quarantined

    def quarantine_lease(
        self,
        lease_or_task_id: WorktreeLease | str,
        reason: str = "Circuit breaker tripped or explicit quarantine",
    ) -> dict[str, Any]:
        """Manually transition an active lease: Leased -> Expired -> Quarantined."""
        with self._lock_leases():
            task_id = (
                lease_or_task_id.task_id
                if isinstance(lease_or_task_id, WorktreeLease)
                else lease_or_task_id
            )
            norm_id = self._normalize_task_id(task_id)
            records = self._load_leases()
            rec = records.get(norm_id)
            now = datetime.now(UTC)

            if rec is None:
                wt_path = self.worktree_root / f"stc-{norm_id}"
                branch_name = f"feature/stc-{norm_id}-e1"
                lease_id = f"lease_{norm_id}_{uuid.uuid4().hex[:8]}"
                rec = {
                    "lease_id": lease_id,
                    "task_id": task_id,
                    "branch_name": branch_name,
                    "worktree_path": str(wt_path),
                    # Branch point (re-specified per section 5.3): this
                    # "main" labels a synthesized off-evaluation-path
                    # quarantine record only. The candidate evaluation
                    # path never allocates via WorktreeManager and never
                    # reads this default: every evaluation ref is an
                    # explicit scratch SHA (lease_git), never a branch.
                    "base_branch": "main",
                    "leased_at": now.isoformat(),
                    "expires_at": now.isoformat(),
                    "epoch": 1,
                    "status": "LEASED",
                    "is_active": True,
                }
                records[norm_id] = rec

            # Step 1: Leased -> Expired
            rec["status"] = "EXPIRED"
            rec["expired_at"] = now.isoformat()

            # Step 2: Expired -> Quarantined
            rec["status"] = "QUARANTINED"
            rec["is_active"] = False
            rec["quarantined_at"] = now.isoformat()
            rec["transition_history"] = ["LEASED", "EXPIRED", "QUARANTINED"]

            refutation: dict[str, Any] = {
                "task_id": rec.get("task_id", task_id),
                "lease_id": rec.get("lease_id"),
                "reason": reason,
                "quarantined_at": now.isoformat(),
                "status": "QUARANTINED",
                "transition_history": ["LEASED", "EXPIRED", "QUARANTINED"],
            }
            rec["refutation_record"] = refutation

            wt_path = Path(rec.get("worktree_path", ""))
            if wt_path.is_dir():
                quarantine_file = wt_path / ".quarantined.json"
                try:
                    quarantine_file.write_text(json.dumps(refutation, indent=2), encoding="utf-8")
                except OSError as exc:
                    logger.warning(
                        "Could not write quarantine record to %s: %s", quarantine_file, exc
                    )

            self._save_leases(records)
            return rec

    def allocate_lease(
        self,
        task_id: str,
        base_branch: str = "main",
        branch: str | None = None,
        epoch: int = 1,
    ) -> WorktreeLease:
        """Allocate an isolated Git worktree lease.

        Conforms to WorktreeManagerProtocol.
        Creates branch feature/stc-{id}-e{epoch} and worktree at worktrees/stc-{id}.

        Branch point (re-specified per section 5.3): the `base_branch`
        default exists for explicit off-evaluation-path callers (CLI
        worktree ops) ONLY. The candidate evaluation path (creation →
        custody → gates → selection → merge → judiciary → champion)
        never calls this method: it builds sanitized-mirror/independent-
        clone leases with explicit scratch SHAs (lease_git), so this
        default MUST NOT trigger there — any evaluation-path reliance
        on it is a contract violation and fails closed.
        """
        if not task_id or not task_id.strip():
            raise WorktreeError("task_id must be a non-empty string.")

        with self._lock_leases():
            # 1. First run check_ttl to quarantine any expired leases
            self.check_ttl()

            norm_id = self._normalize_task_id(task_id)
            records = self._load_leases()
            existing = records.get(norm_id)

            # 2. Check collision: active and unexpired lease raises WorktreeLeaseActiveError
            if existing and existing.get("is_active", False):
                raise WorktreeLeaseActiveError(
                    f"Worktree lease already active for task {task_id} "
                    f"(lease_id: {existing.get('lease_id')}) at {existing.get('worktree_path')}"
                )

            branch_name = branch or f"feature/stc-{norm_id}-e{epoch}"
            target_path = (self.worktree_root / f"stc-{norm_id}").resolve()

            # Safety: worktree path must never be repository root
            if target_path == self.repo_root or target_path in self.repo_root.parents:
                raise WorktreeError(
                    f"Target worktree path cannot be the repository root: {target_path}"
                )

            # Collision check across all other active leases
            for other_id, rec in records.items():
                if rec.get("is_active", False) and other_id != norm_id:
                    if rec.get("branch_name") == branch_name:
                        raise WorktreeLeaseActiveError(
                            f"Branch {branch_name} already in use by active lease "
                            f"{rec.get('lease_id')} (task {rec.get('task_id')})"
                        )
                    if Path(rec.get("worktree_path", "")).resolve() == target_path:
                        raise WorktreeLeaseActiveError(
                            f"Worktree path {target_path} already in use by active lease "
                            f"{rec.get('lease_id')} (task {rec.get('task_id')})"
                        )

            # 3. Check git worktrees for stale/quarantined entries and clean them
            git_entries = self._get_git_worktrees()
            for entry in git_entries:
                entry_path = Path(entry.get("worktree", "")).resolve()
                if entry_path == target_path:
                    self._run_git(["worktree", "remove", "--force", str(target_path)])
                    self._run_git(["worktree", "prune"])
                    break

            if target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)

            self.worktree_root.mkdir(parents=True, exist_ok=True)

            # 4. Create git worktree
            res_branch = self._run_git(["rev-parse", "--verify", f"refs/heads/{branch_name}"])
            if res_branch.returncode == 0:
                res = self._run_git(["worktree", "add", "--force", str(target_path), branch_name])
            else:
                res = self._run_git(
                    ["worktree", "add", "-b", branch_name, str(target_path), base_branch]
                )

            if res.returncode != 0:
                self._run_git(["worktree", "prune"])
                if target_path.exists():
                    shutil.rmtree(target_path, ignore_errors=True)
                err = res.stderr.strip() or res.stdout.strip()
                raise WorktreeError(f"Failed to allocate worktree: {err}")

            # 5. Build WorktreeLease
            now = datetime.now(UTC)
            lease_id = f"lease_{norm_id}_{uuid.uuid4().hex[:8]}"
            lease = WorktreeLease(
                lease_id=lease_id,
                task_id=task_id,
                branch_name=branch_name,
                worktree_path=str(target_path),
                leased_at=now,
                expires_at=now + timedelta(seconds=self.ttl_seconds),
                is_active=True,
            )

            # 6. Save lease record
            records[norm_id] = {
                "lease_id": lease.lease_id,
                "task_id": lease.task_id,
                "branch_name": lease.branch_name,
                "worktree_path": lease.worktree_path,
                "base_branch": base_branch,
                "leased_at": lease.leased_at.isoformat(),
                "expires_at": lease.expires_at.isoformat(),
                "epoch": epoch,
                "status": "LEASED",
                "is_active": True,
                "quarantined_at": None,
                "refutation_record": None,
                "transition_history": ["LEASED"],
            }
            self._save_leases(records)
            return lease

    def release_lease(self, lease: WorktreeLease, purge: bool = True) -> None:
        """Release an active Git worktree lease and clean up.

        Conforms to WorktreeManagerProtocol.
        """
        self.release_by_task_id(lease.task_id, purge=purge, lease=lease)

    def release_by_task_id(
        self,
        task_id: str,
        purge: bool = True,
        lease: WorktreeLease | None = None,
    ) -> dict[str, Any]:
        """Release worktree by task ID or lease instance, updating lease store."""
        with self._lock_leases():
            norm_id = self._normalize_task_id(task_id)
            records = self._load_leases()
            rec = records.get(norm_id)

            if lease is not None:
                worktree_path = Path(lease.worktree_path)
                branch_name = lease.branch_name
            elif rec is not None:
                worktree_path = Path(rec["worktree_path"])
                branch_name = rec["branch_name"]
            else:
                worktree_path = self.worktree_root / f"stc-{norm_id}"
                branch_name = f"feature/stc-{norm_id}-e1"
                # If unrecorded in .leases.json, query git worktrees for attached branch
                resolved_target = worktree_path.resolve()
                for entry in self._get_git_worktrees():
                    if Path(entry.get("worktree", "")).resolve() == resolved_target:
                        if entry.get("branch"):
                            branch_name = entry["branch"]
                        break

            # Safety: worktree path must never be repository root
            resolved_wt = worktree_path.resolve()
            if resolved_wt == self.repo_root or resolved_wt in self.repo_root.parents:
                raise WorktreeError(
                    f"Refusing to remove or delete repository root: {worktree_path}"
                )

            cmd = ["worktree", "remove", str(worktree_path)]
            if purge:
                cmd.append("--force")

            cleaned_now = False
            res = self._run_git(cmd)
            if res.returncode == 0:
                cleaned_now = True
            elif not purge and worktree_path.exists():
                err = res.stderr.strip() or res.stdout.strip()
                raise WorktreeError(f"Failed to remove worktree {worktree_path}: {err}")

            if purge:
                self._run_git(["branch", "-D", branch_name])
                if worktree_path.exists():
                    shutil.rmtree(worktree_path, ignore_errors=True)
                    cleaned_now = True

            self._run_git(["worktree", "prune"])

            if rec is not None:
                rec["status"] = "RELEASED"
                rec["is_active"] = False
                rec["transition_history"] = [*rec.get("transition_history", []), "RELEASED"]
                self._save_leases(records)

            return {
                "task_id": task_id,
                "worktree_path": str(worktree_path),
                "branch_name": branch_name,
                "status": "RELEASED",
                "purged": purge,
                "cleaned_now": cleaned_now,
            }

    def get_diff(self, lease: WorktreeLease) -> str:
        """Extract git diff from leased worktree against base branch.

        Conforms to WorktreeManagerProtocol.
        Automatically marks untracked files with intent-to-add so newly created files
        are reliably captured in the diff without staging them permanently.
        Diffs against the merge-base between base_branch and HEAD to capture only
        changes introduced on the feature branch, avoiding contamination from commits
        added to base_branch.
        """
        wt_path = Path(lease.worktree_path).resolve()
        if not wt_path.is_dir():
            raise WorktreeError(f"Worktree path does not exist: {wt_path}")

        records = self._load_leases()
        rec = records.get(self._normalize_task_id(lease.task_id))
        # Branch point (re-specified per section 5.3): the "main" fallback
        # below serves recorded off-evaluation-path leases without a stored
        # base ONLY. The evaluation path never calls get_diff (merge binding
        # diffs explicit SHAs via diff_binding), so no silent "main" fallback
        # exists anywhere on the evaluation path.
        base_branch = rec.get("base_branch", "main") if rec else "main"

        # Record intent-to-add for untracked files so git diff sees newly created files
        self._run_git(["add", "-N", "."], cwd=wt_path)

        # Compute merge-base so commits added to base_branch do not appear as deletions
        res_mb = self._run_git(["merge-base", base_branch, "HEAD"], cwd=wt_path)
        diff_target = (
            res_mb.stdout.strip()
            if (res_mb.returncode == 0 and res_mb.stdout and res_mb.stdout.strip())
            else base_branch
        )

        res = self._run_git(["diff", diff_target], cwd=wt_path)
        if res.returncode == 0 and res.stdout is not None:
            return res.stdout

        res_head = self._run_git(["diff", "HEAD"], cwd=wt_path)
        if res_head.returncode == 0 and res_head.stdout is not None:
            return res_head.stdout

        return ""

    def list_leases(self) -> list[WorktreeLease]:
        """List active WorktreeLease instances, updating TTL state."""
        self.check_ttl()
        records = self._load_leases()
        active: list[WorktreeLease] = []
        for rec in records.values():
            if rec.get("is_active", False):
                try:
                    active.append(
                        WorktreeLease(
                            lease_id=rec["lease_id"],
                            task_id=rec["task_id"],
                            branch_name=rec["branch_name"],
                            worktree_path=rec["worktree_path"],
                            leased_at=datetime.fromisoformat(rec["leased_at"]),
                            expires_at=datetime.fromisoformat(rec["expires_at"]),
                            is_active=True,
                        )
                    )
                except (KeyError, ValueError):
                    continue
        return active

    def list_active_leases_for_cli(self) -> list[dict[str, str]]:
        """List active leases formatted for CLI porcelain output.

        Filters out the repository root and non-active/quarantined worktrees.
        """
        self.check_ttl()
        all_worktrees = self._get_git_worktrees()
        records = self._load_leases()

        active_entries: list[dict[str, str]] = []
        for entry in all_worktrees:
            wt_path = Path(entry.get("worktree", "")).resolve()
            # The repository root itself is never an ephemeral leased worktree
            if wt_path == self.repo_root:
                continue

            # Worktree must reside under worktree_root
            if not wt_path.is_relative_to(self.worktree_root):
                continue

            # Verify active status against recorded leases
            matching_rec = None
            for rec in records.values():
                if Path(rec.get("worktree_path", "")).resolve() == wt_path:
                    matching_rec = rec
                    break

            if matching_rec is not None and not matching_rec.get("is_active", False):
                continue

            active_entries.append(entry)

        return active_entries
