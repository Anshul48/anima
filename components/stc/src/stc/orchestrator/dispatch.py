"""Orchestrator Worker Dispatch & Chaperone Execution Engine (Subsystem 5 / Stage 4).

Adheres strictly to ADR-007:
- The Orchestrator NEVER shells CLIs directly.
- Orchestrator dispatches exclusively across the WorkerProtocol interface.
- Chaperone acts as the confined execution engine and blind cryptographic notary.
- Fail-closed confinement: any file access or write outside the leased worktree
  raises ConfinementViolationError.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, NamedTuple

from stc.core.errors import WorktreeError
from stc.protocols.interfaces import WorkerProtocol
from stc.schemas.models import TaskBundle, WorktreeLease

logger = logging.getLogger(__name__)


class ConfinementViolationError(WorktreeError):
    """Raised when a worker attempts to access or modify paths outside its leased worktree."""

    violation_record: dict[str, Any] | None = None


#: One monitored-path signature: (mtime_ns, size, sha256-or-None). The digest
#: is recorded only for files under the .git tamper subset (F2); the
#: (mtime_ns, size) pair covers everything else (F3).
class OuterSig(NamedTuple):
    mtime_ns: int
    size: int
    sha256: str | None


#: .git entries under tamper watch (F2). The rest of .git stays skipped.
_GIT_WATCH_SUBSET = ("refs", "hooks", "config", "worktrees")

#: Directory names pruned (never descended into) by the outer-snapshot
#: walk. Name parity with lease_git.MANIFEST_EXCLUDE_DIRS is enforced by
#: test (a direct import would cycle: integration imports this module),
#: but the application depth differs per walker: the manifest skips at
#: every level (hash cost), while the outer snapshot prunes TOP LEVEL
#: ONLY (direct children of each monitored root). The gigabytes that
#: wedged the N12 snapshot are top-level (.durable/, dossier/,
#: artifacts/, worktrees/, .venv/); nested dirs with these names
#: (docs/.../dossier evidence) stay watched because they are evaluated
#: content — the R4B mirror regression proved every-level application
#: empties them. Pruning applies to directories only: a worker-created
#: FILE carrying one of these names is still enumerated and caught.
#: .git is pruned identically to its long-standing post-hoc skip (only
#: the F2 watch subset above is snapshotted, via a separate unpruned
#: descent, so ref names can never collide with the prune set).
_OUTER_SKIP_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        "mutants",
        ".mutmut-cache",
        ".coverage",
        "htmlcov",
        ".auto",
        ".sst",
        ".venv",
        "_quarantine",
        "node_modules",
        ".durable",
        "dossier",
        "worktrees",
        "artifacts",
    }
)


class ChaperoneWorker(WorkerProtocol):
    """Chaperone execution engine and blind notary adhering to WorkerProtocol.

    Confinement: Workers run strictly inside the leased worktree directory.
    Notary: Emits tamper-evident file custody facts (modified files + SHA256 hashes + lease id).
    Zero builder semantics: No prompt management, no test repair, no DAG orchestration.
    """

    #: Default STC membrane: (relative path, required content marker or None).
    #: None markers mean presence + non-empty + non-symlink only; this keeps the
    #: established STC-layout fixtures passing while custom membranes (P03/P04)
    #: enforce strict content markers. Symlinks are rejected unconditionally.
    DEFAULT_MEMBRANE_FILES: tuple[tuple[str, str | None], ...] = (
        ("src/stc/protocols/interfaces.py", None),
        ("src/stc/schemas/models.py", None),
    )

    def __init__(
        self,
        worker_cmd: list[str] | None = None,
        worker_fn: Callable[[TaskBundle, Path], Any] | None = None,
        enforce_membrane: bool = True,
        allowed_tools: tuple[str, ...] = ("agy", "aider", "dsh", "python", "pytest", "git"),
        membrane_files: tuple[tuple[str, str | None], ...] | None = None,
        outer_exclude: tuple[str | Path, ...] = (),
    ) -> None:
        if membrane_files is not None and len(membrane_files) == 0:
            raise ValueError("membrane_files must be non-empty; an empty list passes vacuously.")
        if membrane_files is not None:
            for entry in membrane_files:
                if (
                    not isinstance(entry, tuple)
                    or len(entry) != 2
                    or not entry[0]
                    or (entry[1] is not None and not entry[1])
                ):
                    raise ValueError(
                        "membrane_files entries must be (relpath, marker-or-None) "
                        "with a non-empty relpath."
                    )
        self.worker_cmd = worker_cmd
        self.worker_fn = worker_fn
        self.enforce_membrane = enforce_membrane
        self.allowed_tools = allowed_tools
        self.membrane_files = (
            tuple(membrane_files) if membrane_files is not None else self.DEFAULT_MEMBRANE_FILES
        )
        # Exact outer paths skipped by the strict audit (e.g. the caller's own
        # append-only spend log + its parent dir, whose mtime legitimately flips
        # on append). Children of excluded dirs are still audited individually.
        self.outer_exclude = tuple(outer_exclude)

    def confinement_root(self, lease: WorktreeLease) -> Path:
        """Return the physical root path to which the worker is strictly confined."""
        return Path(lease.worktree_path).resolve()

    def prove_membrane(self, lease: WorktreeLease) -> bool:
        """N11 membrane check: prove each membrane file exists with its marker (F10)."""
        root = self.confinement_root(lease)
        for relpath, marker in self.membrane_files:
            candidate = root / relpath
            if candidate.is_symlink():
                return False
            if not candidate.is_file():
                return False
            try:
                content = candidate.read_bytes()
            except OSError:
                return False
            if not content:
                return False
            if marker is not None and marker.encode("utf-8") not in content:
                return False
        return True

    def _monitor_dirs(self, root: Path) -> list[Path]:
        """Outer dirs under tripwire watch: enclosing repo root + lease parent."""
        dirs: list[Path] = []
        repo_root = self._find_repo_root(root)
        if repo_root is not None and repo_root.is_dir():
            dirs.append(repo_root)
        if root.parent.is_dir() and root.parent not in dirs:
            dirs.append(root.parent)
        return dirs

    def _walk_dir(self, mon_dir: Path, errors: list[str], prune: bool = True) -> list[Path]:
        """List one dir tree, pruning top-level _OUTER_SKIP_DIRS (fail-closed).

        Yield-set matches the former rglob walk minus pruned subtrees:
        every entry (files, dirs, and symlinks-as-themselves; symlinked
        dirs are yielded, never descended into). Pruning applies to
        direct children of mon_dir only; pass prune=False for the .git
        watch-subset descent, which is small and fully watched. A walk
        error is recorded (fail-closed), not raised here; entries
        collected before the error are still returned.
        """
        items: list[Path] = []
        stack: list[tuple[Path, int]] = [(mon_dir, 0)]
        while stack:
            cur, depth = stack.pop()
            try:
                with os.scandir(cur) as it:
                    entries = list(it)
            except OSError as exc:
                errors.append(f"{cur}: walk error: {exc}")
                return items
            for entry in entries:
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError as exc:
                    errors.append(f"{cur}: walk error: {exc}")
                    return items
                if prune and depth == 0 and is_dir and entry.name in _OUTER_SKIP_DIRS:
                    continue
                path = Path(entry.path)
                items.append(path)
                if is_dir:
                    stack.append((path, depth + 1))
        return items

    def _find_repo_root(self, root: Path) -> Path | None:
        """Find the enclosing git repository root for the given worktree."""
        git_item = root / ".git"
        if git_item.is_file():
            with contextlib.suppress(OSError):
                content = git_item.read_text(encoding="utf-8").strip()
                if content.startswith("gitdir:"):
                    git_dir = Path(content.split(":", 1)[1].strip())
                    if not git_dir.is_absolute():
                        git_dir = (root / git_dir).resolve()
                    for p in [git_dir, *git_dir.parents]:
                        if p.name == ".git":
                            return p.parent
        for p in [root, *root.parents]:
            if (p / ".git").is_dir():
                return p
        return None

    # Legacy outer audit (mtime-float, .git skipped, suppressing). Superseded in
    # the dispatch flow by _snapshot_outer_strict/_check_outer_tampering_strict
    # (P03, F2-F5); kept byte-compatible because CLIChaperoneWorker overrides it.
    def _snapshot_outer_files(self, root: Path) -> dict[Path, float]:
        """Record modification timestamps of all files outside the confinement root."""
        outer: dict[Path, float] = {}
        dirs_to_monitor: list[Path] = []

        repo_root = self._find_repo_root(root)
        if repo_root is not None and repo_root.is_dir():
            dirs_to_monitor.append(repo_root)

        if root.parent.is_dir() and root.parent not in dirs_to_monitor:
            dirs_to_monitor.append(root.parent)

        for mon_dir in dirs_to_monitor:
            with contextlib.suppress(OSError, PermissionError):
                for item in mon_dir.rglob("*"):
                    if item.is_relative_to(root):
                        continue

                    if ".git" in item.parts:
                        continue

                    with contextlib.suppress(OSError, PermissionError):
                        outer[item] = item.stat().st_mtime
        return outer

    def _check_outer_tampering(self, root: Path, before: dict[Path, float]) -> None:
        """Verify that zero files or directories outside confinement root were created/modified."""
        dirs_to_monitor: list[Path] = []
        repo_root = self._find_repo_root(root)
        if repo_root is not None and repo_root.is_dir():
            dirs_to_monitor.append(repo_root)
        if root.parent.is_dir() and root.parent not in dirs_to_monitor:
            dirs_to_monitor.append(root.parent)

        created_items: list[Path] = []
        modified_files: list[Path] = []

        for mon_dir in dirs_to_monitor:
            with contextlib.suppress(OSError, PermissionError):
                for item in mon_dir.rglob("*"):
                    if item.is_relative_to(root):
                        continue

                    if ".git" in item.parts:
                        continue

                    with contextlib.suppress(OSError, PermissionError):
                        if item not in before:
                            created_items.append(item)
                        elif item.is_file() and item.stat().st_mtime > before[item]:
                            modified_files.append(item)

        # Fail closed: clean any created rogue files and directories to preserve repository hygiene
        for c in sorted(created_items, key=lambda p: len(p.parts), reverse=True):
            with contextlib.suppress(OSError):
                if c.is_file() or c.is_symlink():
                    c.unlink()
                elif c.is_dir():
                    c.rmdir()

        if created_items:
            raise ConfinementViolationError(
                f"Worker breached confinement: created path outside lease root: {created_items[0]}"
            )
        if modified_files:
            raise ConfinementViolationError(
                "Worker breached confinement: modified file outside lease root: "
                f"{modified_files[0]}"
            )

    def _enumerate_outer(self, root: Path) -> tuple[list[Path], set[Path], list[str]]:
        """Walk monitored outer paths once (fail-closed enumeration, F4).

        Returns (stat_paths, hash_paths, errors): every path needing an
        (mtime_ns, size) signature, the subset of files additionally needing a
        SHA-256 digest (.git tamper subset, F2), and collected errors. .git
        content outside the watched subset stays skipped.
        """
        stat_paths: list[Path] = []
        hash_paths: set[Path] = set()
        errors: list[str] = []
        seen: set[Path] = set()
        excluded: set[Path] = set()
        for raw in self.outer_exclude:
            with contextlib.suppress(OSError):
                excluded.add(Path(raw).resolve())

        def _add(path: Path, hashed: bool = False) -> None:
            if path in excluded:
                return
            if path not in seen:
                seen.add(path)
                stat_paths.append(path)
            if hashed:
                hash_paths.add(path)

        for mon_dir in self._monitor_dirs(root):
            for item in self._walk_dir(mon_dir, errors):
                if item.is_relative_to(root):
                    continue
                if ".git" in item.parts:
                    continue
                _add(item)
        # .git tamper subset (F2): the enclosing repo's .git AND the lease's
        # own .git (a lease at the repo root would otherwise hide its .git
        # under the root skip above).
        subset_bases: list[Path] = [root]
        repo_root = self._find_repo_root(root)
        if repo_root is not None and repo_root != root:
            subset_bases.append(repo_root)
        for base in subset_bases:
            git = base / ".git"
            try:
                if git.is_symlink():
                    errors.append(f"{git}: symlinked .git fails closed")
                    continue
                if git.is_file():
                    _add(git, hashed=True)  # linked-worktree pointer bytes
                    continue
                if not git.is_dir():
                    continue
            except OSError as exc:
                errors.append(f"{git}: cannot inspect: {exc}")
                continue
            for name in _GIT_WATCH_SUBSET:
                sub = git / name
                try:
                    if sub.is_symlink():
                        errors.append(f"{sub}: symlinked .git entry fails closed")
                    elif sub.is_file():
                        _add(sub, hashed=True)
                    elif sub.is_dir():
                        for entry in self._walk_dir(sub, errors, prune=False):
                            if entry.is_symlink():
                                errors.append(f"{entry}: symlinked .git entry fails closed")
                            elif entry.is_file():
                                _add(entry, hashed=True)
                            else:
                                _add(entry)
                except OSError as exc:
                    errors.append(f"{sub}: cannot inspect: {exc}")
        return stat_paths, hash_paths, errors

    def _sign_paths(
        self, stat_paths: list[Path], hash_paths: set[Path]
    ) -> tuple[dict[Path, OuterSig], list[str]]:
        """Sign enumerated paths; unreadable paths are errors (fail-closed)."""
        sigs: dict[Path, OuterSig] = {}
        errors: list[str] = []
        for path in stat_paths:
            try:
                st = path.stat()
            except OSError as exc:
                errors.append(f"{path}: cannot stat: {exc}")
                continue
            digest: str | None = None
            if path in hash_paths:
                try:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError as exc:
                    errors.append(f"{path}: cannot hash: {exc}")
                    continue
            sigs[path] = OuterSig(st.st_mtime_ns, st.st_size, digest)
        return sigs, errors

    def _snapshot_outer_strict(self, root: Path) -> dict[Path, OuterSig]:
        """Fail-closed outer snapshot: (mtime_ns, size) + .git-subset hashes."""
        stat_paths, hash_paths, errors = self._enumerate_outer(root)
        sigs, sign_errors = self._sign_paths(stat_paths, hash_paths)
        errors.extend(sign_errors)
        if errors:
            raise WorktreeError(
                "Outer snapshot enumeration failed fail-closed: " + self._brief_errors(errors)
            )
        return sigs

    def _check_outer_tampering_strict(self, root: Path, before: dict[Path, OuterSig]) -> None:
        """Fail-closed outer audit: created/modified/vanished/error all raise."""
        stat_paths, hash_paths, errors = self._enumerate_outer(root)
        current, sign_errors = self._sign_paths(stat_paths, hash_paths)
        errors.extend(sign_errors)
        if errors:
            raise ConfinementViolationError(
                "Outer audit enumeration failed fail-closed: " + self._brief_errors(errors)
            )
        created = [p for p in current if p not in before]
        modified = sorted(p for p in current if p in before and current[p] != before[p])
        vanished = sorted((p for p in before if p not in current), key=str)
        if not created and not modified and not vanished:
            return
        record = self._quarantine_breach(root, created, modified, vanished, current)
        if created:
            kind, first = "created path", sorted(created, key=str)[0]
        elif modified:
            kind, first = "modified file", modified[0]
        else:
            kind, first = "vanished path", vanished[0]
        err = ConfinementViolationError(
            f"Worker breached confinement: {kind} outside lease root: {first}"
        )
        err.violation_record = record
        raise err

    @staticmethod
    def _brief_errors(errors: list[str]) -> str:
        shown = "; ".join(errors[:3])
        if len(errors) > 3:
            shown += f" (+{len(errors) - 3} more)"
        return shown

    def _quarantine_breach(
        self,
        root: Path,
        created: list[Path],
        modified: list[Path],
        vanished: list[Path],
        current: dict[Path, OuterSig],
    ) -> dict[str, Any]:
        """Move created paths to OS-temp quarantine; record bytes+hashes (F5).

        OS temp (not repo-adjacent) keeps quarantined files out of candidate
        identity. Top-level created paths move whole; nested ones are recorded
        as moved-with-parent. Pre-existing modified paths are recorded in
        place, never moved.
        """
        qdir = Path(tempfile.mkdtemp(prefix="stc-quarantine-"))
        top = [p for p in created if not any(p != q and p.is_relative_to(q) for q in created)]
        top_set = set(top)
        items: list[dict[str, Any]] = []
        for index, path in enumerate(sorted(top, key=str)):
            entry: dict[str, Any] = {
                "path": str(path),
                "kind": "created",
                "size": None,
                "sha256": None,
                "quarantined_as": None,
                "status": "moved",
            }
            try:
                if not path.exists() and not path.is_symlink():
                    entry["status"] = "vanished-before-quarantine (F15 transient suspected)"
                else:
                    was_dir = path.is_dir() and not path.is_symlink()
                    if path.is_symlink() or path.is_file():
                        with contextlib.suppress(OSError):
                            entry["size"] = path.stat().st_size
                        with contextlib.suppress(OSError):
                            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    dest = qdir / f"{index:04d}_{path.name}"
                    shutil.move(str(path), str(dest))
                    entry["quarantined_as"] = str(dest)
                    if was_dir:
                        entry["status"] = "moved-dir"
            except OSError as exc:
                entry["status"] = f"move-failed fail-closed: {exc}"
            items.append(entry)
        for path in sorted((p for p in created if p not in top_set), key=str):
            items.append(
                {
                    "path": str(path),
                    "kind": "created",
                    "size": None,
                    "sha256": None,
                    "quarantined_as": None,
                    "status": "moved-with-parent",
                }
            )
        for path in modified:
            sig = current.get(path)
            entry = {
                "path": str(path),
                "kind": "modified",
                "size": sig.size if sig is not None else None,
                "sha256": sig.sha256 if sig is not None else None,
                "quarantined_as": None,
                "status": "recorded in place (pre-existing path, not moved)",
            }
            if sig is not None and sig.sha256 is None:
                with contextlib.suppress(OSError):
                    if path.is_file():
                        data = path.read_bytes()
                        entry["size"] = len(data)
                        entry["sha256"] = hashlib.sha256(data).hexdigest()
            items.append(entry)
        for path in vanished:
            items.append(
                {
                    "path": str(path),
                    "kind": "vanished",
                    "size": None,
                    "sha256": None,
                    "quarantined_as": None,
                    "status": "deleted during execution",
                }
            )
        record: dict[str, Any] = {
            "lease_root": str(root),
            "quarantine_dir": str(qdir),
            "attested_at": datetime.now(UTC).isoformat(),
            "items": items,
        }
        with contextlib.suppress(OSError):
            (qdir / "violation.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record

    def _snapshot_inner_files(self, root: Path) -> dict[Path, str]:
        """Snapshot SHA-256 hashes of all files inside worktree."""
        inner: dict[Path, str] = {}
        if not root.is_dir():
            return inner

        ignored_names = {
            ".stc_lease.json",
            ".leases.json",
            ".quarantined.json",
            ".notary_custody.json",
        }

        for fpath in root.rglob("*"):
            if (
                fpath.is_file()
                and ".git" not in fpath.parts
                and "__pycache__" not in fpath.parts
                and ".pytest_cache" not in fpath.parts
                and not fpath.name.endswith(".pyc")
                and fpath.name not in ignored_names
            ):
                with contextlib.suppress(OSError, PermissionError):
                    inner[fpath] = hashlib.sha256(fpath.read_bytes()).hexdigest()
        return inner

    def generate_custody_report(
        self,
        lease: WorktreeLease,
        modified_files: list[tuple[str, str]],
    ) -> dict[str, Any]:
        """Notary custody report: file list + SHA-256 hashes + lease id."""
        return {
            "lease_id": lease.lease_id,
            "task_id": lease.task_id,
            "confinement_root": str(self.confinement_root(lease)),
            "modified_files": [
                {"path": rel_path, "sha256": sha} for rel_path, sha in modified_files
            ],
            "attested_at": datetime.now(UTC).isoformat(),
            "notary_verified": True,
        }

    def dispatch(self, bundle: TaskBundle, lease: WorktreeLease) -> str:
        """N12 worker dispatch node: execute worker strictly confined within worktree."""
        root = self.confinement_root(lease)
        if not root.is_dir():
            raise WorktreeError(f"Confinement root does not exist: {root}")

        # N11 membrane check
        if self.enforce_membrane and not self.prove_membrane(lease):
            raise WorktreeError(
                f"Membrane verification failed: upstream protocols or schemas missing in {root}"
            )

        # Enforce static confinement on target files
        for target in bundle.target_files:
            target_resolved = (root / target.path).resolve()
            if not target_resolved.is_relative_to(root):
                raise ConfinementViolationError(
                    f"Target file path '{target.path}' escapes confinement root {root}"
                )

        # Validate worker_cmd against allowed_tools
        if self.worker_cmd is not None:
            if not self.worker_cmd:
                raise WorktreeError("Worker command cannot be empty.")
            tool_name = Path(self.worker_cmd[0]).name
            clean_tool = tool_name.removesuffix(".exe").lower()
            allowed = [t.lower() for t in self.allowed_tools]
            if clean_tool not in allowed:
                raise WorktreeError(
                    f"Worker command '{tool_name}' is not in allowed tools: {self.allowed_tools}"
                )

        # Record pre-execution snapshots
        outer_before = self._snapshot_outer_strict(root)
        inner_before = self._snapshot_inner_files(root)

        # Execute worker
        if self.worker_fn is not None:
            self.worker_fn(bundle, root)

        if self.worker_cmd is not None:
            tool_name = Path(self.worker_cmd[0]).name
            try:
                res = subprocess.run(
                    self.worker_cmd,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=120.0,
                )
            except FileNotFoundError:
                raise WorktreeError(
                    f"Worker executable '{tool_name}' not found on system PATH."
                ) from None
            except subprocess.TimeoutExpired:
                raise WorktreeError(
                    f"Worker command timed out: {' '.join(self.worker_cmd)}"
                ) from None

            if res.returncode != 0:
                err = res.stderr.strip() or res.stdout.strip()
                raise WorktreeError(
                    f"Worker command '{tool_name}' failed with exit code {res.returncode}: {err}"
                )

        # Enforce dynamic confinement: fail closed if any write occurred outside root
        self._check_outer_tampering_strict(root, outer_before)

        # Compute modified files inside root
        inner_after = self._snapshot_inner_files(root)
        modified_files: list[tuple[str, str]] = []
        for fpath, sha in inner_after.items():
            if inner_before.get(fpath) != sha:
                rel_path = str(fpath.relative_to(root)).replace("\\", "/")
                modified_files.append((rel_path, sha))

        report = self.generate_custody_report(lease, modified_files)
        return json.dumps(report, indent=2)


def dispatch_worker(
    bundle: TaskBundle,
    lease: WorktreeLease,
    worker: WorkerProtocol,
) -> str:
    """N12 Orchestrator dispatch node.

    The Orchestrator NEVER shells CLIs directly (ADR-007).
    Dispatches exclusively across the WorkerProtocol interface.
    """
    if not isinstance(worker, WorkerProtocol):
        raise TypeError(f"Expected WorkerProtocol implementation, got {type(worker).__name__}")

    now = datetime.now(UTC)
    exp = lease.expires_at if lease.expires_at.tzinfo else lease.expires_at.replace(tzinfo=UTC)
    if not lease.is_active or now >= exp:
        raise WorktreeError(
            f"Cannot dispatch worker to inactive or expired lease: {lease.lease_id}"
        )

    root = worker.confinement_root(lease)
    if not root.is_dir():
        raise WorktreeError(f"Worker confinement root does not exist: {root}")

    # Delegation across WorkerProtocol membrane
    return worker.dispatch(bundle, lease)


class OrchestratorDispatcher:
    """Orchestrator dispatch coordinator adhering to ADR-007."""

    def __init__(self, worker: WorkerProtocol | None = None) -> None:
        self.worker = worker

    def dispatch(
        self,
        bundle: TaskBundle,
        lease: WorktreeLease,
        worker: WorkerProtocol | None = None,
    ) -> str:
        """Dispatch task bundle to worker within leased worktree."""
        active_worker = worker or self.worker
        if active_worker is None:
            raise WorktreeError("No WorkerProtocol implementation provided to orchestrator")
        return dispatch_worker(bundle, lease, active_worker)
