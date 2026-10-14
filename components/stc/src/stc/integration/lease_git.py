"""Lease git mechanics + full-manifest tripwire + import proof (D-beta/D-delta).

D-beta (section 5.3): ref propagation AND head assert on EVERY lease.
Primary leases check out the scratch ref at intake and assert
``HEAD == SHA`` at gate time; nested leases receive the exact
``(lease_git_path, scratch_ref_SHA)`` pair, materialize that SHA, and
assert ``HEAD == SHA`` before running anything. Propagation (usability)
AND assertion (safety) are both required.

Branch-point rule (section 5.3): safety never depends on the ``main``
default. No function here takes or applies a branch default: every ref
is an explicit 40-hex SHA passed by the caller (no ``main`` fallback
exists anywhere on the evaluation path). ``git worktree add`` against
the ORIGINAL repository is FORBIDDEN on every evaluation path — leases
are sanitized mirror copies (remotes removed, copied ``worktrees/``
admin dropped) or independent clones; cleanup deletes the disposable
git whole, and quarantine preserves a COPY for inspection, never the
live lease.

D-delta (section 5.4): full-manifest tripwire. The guarantee is
labeled detection-with-fail-closed, never "read-only": "read-only"
describes the external mount mode only, never the tripwire guarantee.
chmod-based prevention is DROPPED (theater on Windows/OneDrive) and is
deliberately not built here. RESIDUAL RISK (accepted explicitly by the
authorization): a transient write-then-restore inside one hash interval
is invisible to hashing; the open/pre-gates/close checkpoints narrow
the window but do not eliminate it. Prevention awaits container
read-only mounts (future, not built).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from stc.integration.identity import IntegrationError

__all__ = [
    "EXTERNAL_PINS",
    "MANIFEST_EXCLUDE_DIRS",
    "LeaseGitError",
    "LeaseTripwire",
    "TripwireBreach",
    "assert_head_equals",
    "checkout_ref",
    "commit_tree",
    "create_scratch_ref",
    "ensure_disposable_git",
    "fallback_in_lease_finding",
    "hash_tree_manifest",
    "head_sha",
    "materialize_nested_lease",
    "prove_import_integrity",
    "resolve_stc_root",
    "resolve_workspace_root",
    "verify_baseline_manifest",
    "workspace_source",
]

_GIT_TIMEOUT_S: Final[int] = 120

#: Pinned external content (section Q3 enumerated set). Full SHAs from the
#: design-tranche identity probe (2026-09-19); additions are contract
#: amendments, never implementation discretion.
EXTERNAL_PINS: Final[dict[str, str]] = {
    "prompt-kit": "4f442a6c829bc06b60f9979fdc8d7585e30bac9a",
    "trace": "a24a937009fec41e6dcb6d2ca31d3c1783ac97f7",
    "sst": "df78f42894a65c48f524337a498032617689a013",
}

#: prompt_kit package files spot-hashed against the prompt-kit pin
#: (pin-relative path -> package-relative path; F3c precedent).
_PROMPT_KIT_SPOT: Final[tuple[tuple[str, str], ...]] = (
    ("prompt_kit/harnesses/__init__.py", "harnesses/__init__.py"),
    ("prompt_kit/harnesses/base.py", "harnesses/base.py"),
    ("prompt_kit/harnesses/mock_harness.py", "harnesses/mock_harness.py"),
    ("prompt_kit/harnesses/catalog.py", "harnesses/catalog.py"),
    ("prompt_kit/harnesses/account_harness.py", "harnesses/account_harness.py"),
)

#: sst package files spot-hashed against the sst pin
#: (pin-relative path -> package-relative path).
_SST_SPOT: Final[tuple[tuple[str, str], ...]] = (
    ("src/sst/__init__.py", "__init__.py"),
    ("src/sst/core/contracts.py", "core/contracts.py"),
    ("src/sst/sandbox/custody.py", "sandbox/custody.py"),
)

#: Directory/file names excluded from manifest enumeration. These are
#: lease-admin, version-control, gate-artifact, or backend-runtime-output
#: paths — never evaluated bytes. Gate caches (.pytest_cache,
#: __pycache__, .mypy_cache, .ruff_cache, mutants, .mutmut-cache,
#: coverage data) are excluded so legitimate gate artifacts cannot trip
#: the wire; dossier/ (backend dossier + run records), .durable/ (local
#: install fallback), worktrees/ (lease checkouts), and artifacts/
#: (evidence archives, mostly gitignored) are backend runtime outputs
#: whose presence otherwise wedges the T0 walk and lease mirrors
#: (gigabytes over slow mounts) and self-trips the close check.
#: EVERYTHING else — content deltas AND additions/deletions — fails
#: the run.
MANIFEST_EXCLUDE_DIRS: Final[frozenset[str]] = frozenset(
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

_MANIFEST_EXCLUDE_FILES: Final[frozenset[str]] = frozenset(
    {
        ".coverage",
        ".coverage.*",
        "coverage.xml",
        "quarantine_reason.txt",
    }
)

#: Local commit identity for disposable-lease commits (transport only;
#: binding comes from the tree hashes + scratch ref, never the author).
_COMMIT_ENV: Final[dict[str, str]] = {
    "GIT_AUTHOR_NAME": "stc-custody",
    "GIT_AUTHOR_EMAIL": "stc-custody@local",
    "GIT_COMMITTER_NAME": "stc-custody",
    "GIT_COMMITTER_EMAIL": "stc-custody@local",
}


class LeaseGitError(IntegrationError):
    """Lease git setup / ref protocol failure (fail-closed)."""


class TripwireBreach(IntegrationError):
    """Full-manifest tripwire detected persistent change (fail-closed)."""


def _git(
    repo: Path, args: list[str], *, timeout: int = _GIT_TIMEOUT_S
) -> subprocess.CompletedProcess[str]:
    """Runs git in ``repo`` (text mode); raises :class:`LeaseGitError` if git is missing."""
    if shutil.which("git") is None:
        raise LeaseGitError("git executable not found on PATH (lease git is mandatory)")
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise LeaseGitError(f"git {' '.join(args)} timed out") from exc
    except OSError as exc:
        raise LeaseGitError(f"git {' '.join(args)} failed: {exc}") from exc


# --- Workspace resolution (section Q3 override mechanics) ---


def workspace_source() -> tuple[Path, str]:
    """Resolves the STC workspace root + how it resolved.

    ``STC_WORKSPACE_ROOT`` wins when set (in-lease runs set it ALWAYS);
    otherwise the legacy ``parents[3]`` inference applies (real-tree runs
    only). Returns ``(root, "override" | "fallback")``.
    """
    override = os.environ.get("STC_WORKSPACE_ROOT", "").strip()
    if override:
        return Path(override).resolve(), "override"
    import stc

    assert stc.__file__ is not None
    return Path(stc.__file__).resolve().parents[3], "fallback"


def resolve_workspace_root() -> Path:
    """Resolves the STC workspace root (override-first, fallback second)."""
    root, _ = workspace_source()
    return root


def resolve_stc_root() -> Path:
    """Resolves the STC repository root under either workspace layout.

    Harness-shaped workspaces carry the repo at ``<workspace>/stc``;
    leases ARE stc trees, so the workspace root itself is returned when
    no ``stc/`` child carries an importable package (same src/flat probe
    as :func:`prove_import_integrity`). Consumers needing the STC root
    (corpus paths, confinement git repos, spend logs) use this, never
    the raw workspace root (R2c: S1 consumed the workspace root as the
    repo root, breaking corpus/confinement/spend resolution).
    """
    workspace = resolve_workspace_root()
    candidate = workspace / "stc"
    src_layout = (candidate / "src" / "stc" / "__init__.py").is_file()
    flat_layout = (candidate / "stc" / "__init__.py").is_file()
    return candidate if (src_layout or flat_layout) else workspace


def fallback_in_lease_finding(root: Path, source: str) -> str | None:
    """Findings text when the legacy fallback resolves inside a lease.

    The fallback resolving to a lease-style (``/tmp``-rooted) path is a
    finding, not a supported configuration. Returns ``None`` when clean.
    """
    if source != "fallback":
        return None
    text = root.as_posix().lower()
    if text.startswith(("/tmp/", "/temp/", "/private/tmp/", "/var/folders/")):
        return (
            f"workspace fallback resolved inside a lease-style root: {root} "
            "(in-lease runs must set STC_WORKSPACE_ROOT; unsupported configuration)"
        )
    return None


# --- Disposable lease git (T2 isolation) ---


def ensure_disposable_git(lease_ws: Path) -> str:
    """Makes the lease git disposable-by-construction. Returns the mode.

    - Mirror leases (copied ``.git`` present): sanitized at intake —
      ALL remotes removed, copied ``worktrees/`` admin dropped — before
      any ref is created. Refs created in the copy cannot propagate:
      no remote and no shared ref store exist.
    - Fresh leases (no ``.git``): a NEW independent repo is initialized
      in the lease (``git init``, no remotes ever added).

    ``git worktree add`` against the original repository is never used
    here or anywhere on the evaluation path. Asserts zero remotes after.
    """
    dot_git = lease_ws / ".git"
    if dot_git.exists():
        proc = _git(lease_ws, ["remote"])
        for name in (proc.stdout or "").split():
            rm = _git(lease_ws, ["remote", "remove", name])
            if rm.returncode != 0:
                raise LeaseGitError(f"failed to remove lease remote {name!r}")
        worktrees_admin = dot_git / "worktrees"
        if worktrees_admin.exists():
            shutil.rmtree(worktrees_admin, ignore_errors=False)
        mode = "sanitized-mirror"
    else:
        proc = _git(lease_ws, ["init", "-q"])
        if proc.returncode != 0:
            raise LeaseGitError(f"git init failed in lease: {proc.stderr.strip()[:300]}")
        mode = "fresh-init"
    check = _git(lease_ws, ["remote"])
    if (check.stdout or "").strip():
        raise LeaseGitError("lease git still has remotes after sanitize (fail-closed)")
    return mode


def commit_tree(lease_ws: Path, message: str) -> str:
    """Stages the whole lease tree and commits; returns the commit SHA."""
    add = _git(lease_ws, ["add", "-A"])
    if add.returncode != 0:
        raise LeaseGitError(f"lease git add failed: {add.stderr.strip()[:300]}")
    env = dict(os.environ)
    env.update(_COMMIT_ENV)
    if shutil.which("git") is None:  # pragma: no cover - guarded in _git too
        raise LeaseGitError("git executable not found on PATH (lease git is mandatory)")
    try:
        proc = subprocess.run(
            ["git", "commit", "-qm", message],
            cwd=str(lease_ws),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_GIT_TIMEOUT_S,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LeaseGitError(f"lease commit failed: {exc}") from exc
    if proc.returncode != 0:
        # Empty tree (nothing to commit) still needs a ref target: the
        # lease bytes are empty-but-real, so commit an explicit empty root.
        combined = (proc.stderr or "") + (proc.stdout or "")
        if "nothing to commit" in combined or "no changes added to commit" in combined:
            proc2 = subprocess.run(
                ["git", "commit", "-q", "--allow-empty", "-m", message],
                cwd=str(lease_ws),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=_GIT_TIMEOUT_S,
                env=env,
            )
            if proc2.returncode != 0:
                raise LeaseGitError(
                    f"lease empty commit failed: {proc2.stderr.strip()[:300]}"
                ) from None
        else:
            raise LeaseGitError(f"lease commit failed: {proc.stderr.strip()[:300]}")
    return head_sha(lease_ws)


def create_scratch_ref(lease_ws: Path, candidate_id: str, sha: str) -> str:
    """Creates ``refs/scratch/<candidate_id>`` at ``sha``; returns the ref."""
    safe = candidate_id.replace("/", "_").replace("\\", "_").replace(" ", "_") or "candidate"
    ref = f"refs/scratch/{safe}"
    proc = _git(lease_ws, ["update-ref", ref, sha])
    if proc.returncode != 0:
        raise LeaseGitError(f"scratch ref creation failed: {proc.stderr.strip()[:300]}")
    return ref


def checkout_ref(lease_ws: Path, ref: str) -> None:
    """Checks out the scratch ref at intake (detached HEAD at the ref)."""
    proc = _git(lease_ws, ["checkout", "-q", "--detach", ref])
    if proc.returncode != 0:
        raise LeaseGitError(f"scratch ref checkout failed: {proc.stderr.strip()[:300]}")


def head_sha(lease_ws: Path) -> str:
    """Resolves the lease ``HEAD`` SHA (one rev-parse comparison input)."""
    proc = _git(lease_ws, ["rev-parse", "HEAD"])
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        raise LeaseGitError(f"HEAD resolution failed: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def assert_head_equals(lease_ws: Path, expected_sha: str) -> None:
    """Asserts ``HEAD == expected_sha``; mismatch fails closed (no fallback)."""
    observed = head_sha(lease_ws)
    if observed != expected_sha:
        raise LeaseGitError(
            f"HEAD assert failed: lease HEAD {observed} != scratch {expected_sha} "
            "(fail-closed; never falls back to other bytes)"
        )


def materialize_nested_lease(
    lease_git_path: str | Path, scratch_ref_sha: str, dest: str | Path
) -> Path:
    """Materializes a NESTED lease from the exact propagated pair.

    The parent passes ``(lease_git_path, scratch_ref_SHA)``; the child
    takes an independent clone (``--no-hardlinks``, remote removed
    post-clone), checks out the SHA detached, and asserts
    ``HEAD == SHA`` before running anything. ``dest`` must not exist.
    Never ``worktree add`` (forbidden against the original repo).
    """
    src = Path(lease_git_path)
    target = Path(dest)
    if target.exists():
        raise LeaseGitError(f"nested lease dest already exists: {target}")
    if shutil.which("git") is None:
        raise LeaseGitError("git executable not found on PATH (lease git is mandatory)")
    try:
        proc = subprocess.run(
            ["git", "clone", "-q", "--no-hardlinks", str(src), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LeaseGitError(f"nested lease clone failed: {exc}") from exc
    if proc.returncode != 0:
        raise LeaseGitError(f"nested lease clone failed: {proc.stderr.strip()[:300]}")
    remotes = _git(target, ["remote"])
    for name in (remotes.stdout or "").split():
        _git(target, ["remote", "remove", name])
    checkout = _git(target, ["checkout", "-q", "--detach", scratch_ref_sha])
    if checkout.returncode != 0:
        raise LeaseGitError(
            f"nested lease checkout of {scratch_ref_sha} failed: {checkout.stderr.strip()[:300]}"
        )
    assert_head_equals(target, scratch_ref_sha)
    return target


# --- Full-manifest tripwire (D-delta; detection-with-fail-closed) ---


def _excluded(rel: str) -> bool:
    parts = rel.split("/")
    if any(part in MANIFEST_EXCLUDE_DIRS for part in parts):
        return True
    name = parts[-1]
    for pattern in _MANIFEST_EXCLUDE_FILES:
        if pattern.endswith("*"):
            if name.startswith(pattern[:-1]):
                return True
        elif name == pattern:
            return True
    return False


def hash_tree_manifest(root: str | Path) -> dict[str, str]:
    """Hashes EVERY enumerated file under ``root`` (rel-posix -> sha256).

    Deterministic (sorted); follows the exclusion set above. Symlinks to
    files are hashed by target bytes; broken symlinks are recorded as
    ``BROKEN-SYMLINK`` (a change there still trips the wire). Directory
    symlinks are NEVER descended (foreign bytes must never hash under
    local names; package-manager link cycles would ELOOP the walk) —
    each is recorded as ``DIR-SYMLINK:<target>`` so retargeting still
    trips the wire. Excluded dirs are pruned before descent.
    """
    base = Path(root)
    manifest: dict[str, str] = {}
    if not base.is_dir():
        raise TripwireBreach(f"tripwire root not a directory: {base}")

    def _on_walk_error(exc: OSError) -> None:
        raise TripwireBreach(f"tripwire walk failed for {exc.filename}: {exc}") from exc

    entries: list[tuple[str, Path | None, str | None]] = []
    for dirpath, dirnames, filenames in os.walk(
        base, topdown=True, followlinks=False, onerror=_on_walk_error
    ):
        here = Path(dirpath)
        if here != base:
            rel_here = here.relative_to(base).as_posix()
            if _excluded(rel_here):
                dirnames[:] = []
                continue
        else:
            rel_here = ""
        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            rel = f"{rel_here}/{name}" if rel_here else name
            full = here / name
            if _excluded(rel):
                continue
            if full.is_symlink():
                try:
                    target = str(full.readlink())
                except OSError as exc:
                    raise TripwireBreach(f"tripwire readlink failed for {rel}: {exc}") from exc
                entries.append((rel, None, f"DIR-SYMLINK:{target}"))
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            rel = f"{rel_here}/{name}" if rel_here else name
            if _excluded(rel):
                continue
            entries.append((rel, here / name, None))
    for rel, path, marker in sorted(entries, key=lambda item: item[0]):
        if marker is not None:
            manifest[rel] = hashlib.sha256(marker.encode("utf-8")).hexdigest()
            continue
        assert path is not None
        try:
            manifest[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            manifest[rel] = "BROKEN-SYMLINK"
        except OSError as exc:
            raise TripwireBreach(f"tripwire read failed for {rel}: {exc}") from exc
    return manifest


@dataclass
class LeaseTripwire:
    """Open/pre-gates/close full-manifest checkpoints for one lease.

    Detection-with-fail-closed, never read-only (see module docstring):
    a persistent change => the run fails; a transient write-then-restore
    inside one hash interval is invisible (RESIDUAL RISK, accepted).

    The proposal application between open and pre-gates is AUTHORIZED
    mutation: the caller re-baselines explicitly via
    :meth:`rebaseline_after_apply` (recorded, never silent). The
    pre-gates and close checkpoints then require byte-identity modulo
    the exclusion set.
    """

    lease_id: str
    manifest_open: dict[str, str] = field(default_factory=dict)
    manifest_gates: dict[str, str] = field(default_factory=dict)

    def check_against(
        self, baseline: dict[str, str], current: dict[str, str], checkpoint: str
    ) -> None:
        """Compares manifests; content deltas AND additions/deletions fail."""
        changed = sorted(
            rel for rel in baseline if rel in current and current[rel] != baseline[rel]
        )
        added = sorted(rel for rel in current if rel not in baseline)
        deleted = sorted(rel for rel in baseline if rel not in current)
        if changed or added or deleted:
            detail: list[str] = []
            if changed:
                detail.append(f"content-changed={changed[:10]}")
            if added:
                detail.append(f"added={added[:10]}")
            if deleted:
                detail.append(f"deleted={deleted[:10]}")
            raise TripwireBreach(
                f"tripwire {checkpoint} for lease {self.lease_id}: "
                + "; ".join(detail)
                + " (detection-with-fail-closed: persistent change fails the run)"
            )

    def rebaseline_after_apply(self, lease_ws: Path) -> dict[str, str]:
        """Records the authorized post-apply manifest (proposal application)."""
        self.manifest_gates = hash_tree_manifest(lease_ws)
        return self.manifest_gates

    def check_pre_gates(self, lease_ws: Path) -> None:
        """Pre-gates checkpoint: nothing changed since the apply baseline."""
        self.check_against(self.manifest_gates, hash_tree_manifest(lease_ws), "pre-gates")

    def check_close(self, lease_ws: Path) -> None:
        """Close checkpoint: nothing changed since pre-gates."""
        self.check_against(self.manifest_gates, hash_tree_manifest(lease_ws), "close")


def verify_baseline_manifest(source_root: str | Path, pinned: dict[str, str]) -> list[str]:
    """Re-hashes the T0 baseline manifest (E4 ``--locked`` semantics).

    Returns the finding lines (empty when the manifest is unchanged).
    Any drift (content delta, addition, deletion) is a finding the
    caller fails closed on (re-pin T0, never proceed).
    """
    current = hash_tree_manifest(source_root)
    findings: list[str] = []
    for rel in sorted(set(pinned) | set(current)):
        old, new = pinned.get(rel), current.get(rel)
        if old is None:
            findings.append(f"baseline-manifest drift: added {rel}")
        elif new is None:
            findings.append(f"baseline-manifest drift: deleted {rel}")
        elif old != new:
            findings.append(f"baseline-manifest drift: content changed {rel}")
    return findings


# --- Per-lease import-integrity proof (section Q3) ---


_PROBE_SCRIPT: Final[str] = (
    "import json, os, sys; "
    "import stc; "
    "print(json.dumps({"
    "'stc_file': stc.__file__, "
    "'path_head': sys.path[:4], "
    "'cwd': os.getcwd(), "
    "'pythonpath': os.environ.get('PYTHONPATH', '')}))"
)


def _ambient_pythonpath_findings(roots: dict[str, Path]) -> list[str]:
    """Findings for ambient PYTHONPATH entries beyond the enumerated set.

    The lease MUST NOT inherit ambient PYTHONPATH entries beyond the
    enumerated set (the three external repos). Each ambient entry must
    resolve under one of those roots; anything else is a finding.
    """
    allowed = [root.resolve() for root in roots.values()]
    findings: list[str] = []
    ambient = os.environ.get("PYTHONPATH", "")
    if not ambient.strip():
        return findings
    for entry in ambient.split(os.pathsep):
        if not entry.strip():
            continue
        resolved = Path(entry).resolve()
        if not any(resolved == root or root in resolved.parents for root in allowed):
            findings.append(f"ambient PYTHONPATH entry beyond the enumerated set: {entry}")
    return findings


def _externals_roots(real_tree: Path) -> dict[str, Path]:
    """Resolves the enumerated external repos (explicit env wins)."""
    return {
        "prompt-kit": Path(
            os.environ.get("STC_PROMPT_KIT_ROOT", str(real_tree.parent / "prompt-kit"))
        ),
        "trace": Path(os.environ.get("STC_TRACE_ROOT", str(real_tree.parent / "trace"))),
        "sst": Path(os.environ.get("STC_SST_ROOT", str(real_tree.parent / "sst"))),
    }


def _git_blob(repo: Path, pin: str, rel: str) -> str:
    proc = _git(repo, ["rev-parse", f"{pin}:{rel}"])
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        raise LeaseGitError(f"pin blob unresolvable: {repo.name} {pin[:12]}:{rel}")
    return proc.stdout.strip()


def _hash_object(path: Path) -> str:
    proc = _git(path.parent, ["hash-object", str(path)])
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        raise LeaseGitError(f"hash-object failed: {path}")
    return proc.stdout.strip()


def _spot_hash_package(
    package: str, repo: Path, pin: str, files: tuple[tuple[str, str], ...]
) -> list[str]:
    """Byte-compares imported ``package`` files against pin blobs."""
    spec = importlib.util.find_spec(package)
    if spec is None or spec.submodule_search_locations is None:
        raise LeaseGitError(f"import-integrity: {package} not importable")
    pkg_dir = Path(next(iter(spec.submodule_search_locations)))
    mismatches: list[str] = []
    for pin_rel, pkg_rel in files:
        expected = _git_blob(repo, pin, pin_rel)
        observed = _hash_object(pkg_dir / pkg_rel)
        if observed != expected:
            mismatches.append(f"{package}/{pkg_rel}: imported bytes differ from pin blob")
    return mismatches


def prove_import_integrity(lease_ws: str | Path) -> dict[str, Any]:
    """Proves per-lease import integrity before gates (section Q3).

    Asserts ``stc.__file__`` resolves UNDER the lease, ``sys.path`` order
    puts the lease first, and each enumerated external resolves to its
    pinned content (spot-hash). Failure fails the lease closed.

    Scope: the proof binds leases that carry STC bytes. A lease with no
    importable ``stc`` package (a non-STC target tree) records an
    explicit ``not-applicable`` verdict — there is no STC import to
    prove — instead of asserting about the harness's own install.
    """
    lease = Path(lease_ws).resolve()
    src_layout = (lease / "src" / "stc" / "__init__.py").is_file()
    flat_layout = (lease / "stc" / "__init__.py").is_file()
    if not src_layout and not flat_layout:
        return {
            "verdict": "not-applicable",
            "reason": "lease carries no importable stc package (non-STC target tree)",
        }
    # Gate-equivalent launch: the lease root (cwd) plus its own package
    # root on PYTHONPATH, exactly — no ambient entries inherited.
    probe_path = str(lease / "src") if src_layout else str(lease)
    probe_env = dict(os.environ)
    probe_env["PYTHONPATH"] = probe_path
    try:
        proc = subprocess.run(
            [sys.executable, "-B", "-c", _PROBE_SCRIPT],
            cwd=str(lease),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
            env=probe_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LeaseGitError(f"import-integrity probe failed: {exc}") from exc
    if proc.returncode != 0:
        raise LeaseGitError(f"import-integrity probe failed: {(proc.stderr or '').strip()[:300]}")
    try:
        probe = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise LeaseGitError(f"import-integrity probe unparseable: {exc}") from exc
    stc_file = Path(str(probe.get("stc_file", ""))).resolve()
    if lease not in stc_file.parents:
        raise LeaseGitError(
            f"import-integrity: stc.__file__={stc_file} is NOT under lease {lease} "
            "(evaluates the wrong bytes; verdict void)"
        )
    path_head = [str(p) for p in probe.get("path_head", [])]
    lease_first = any(
        Path(p).resolve() == lease or str(p) in (str(lease), "") for p in path_head[:2]
    )
    if not lease_first:
        raise LeaseGitError(
            f"import-integrity: lease {lease} not first in sys.path head {path_head}"
        )
    real_tree = Path(__file__).resolve().parents[3]
    roots = _externals_roots(real_tree)
    ambient_findings = _ambient_pythonpath_findings(roots)
    if ambient_findings:
        raise LeaseGitError("import-integrity: " + "; ".join(ambient_findings[:6]))
    mismatches: list[str] = []
    for name, repo in roots.items():
        pin = EXTERNAL_PINS[name]
        if not (repo / ".git").exists():
            raise LeaseGitError(
                f"import-integrity: external repo missing: {repo} ({name} pin {pin[:12]})"
            )
        head = _git(repo, ["rev-parse", "HEAD"])
        if (head.stdout or "").strip() != pin:
            mismatches.append(
                f"{name}: checkout HEAD {(head.stdout or '').strip()[:12]} != pin {pin[:12]}"
            )
    mismatches.extend(
        _spot_hash_package(
            "prompt_kit", roots["prompt-kit"], EXTERNAL_PINS["prompt-kit"], _PROMPT_KIT_SPOT
        )
    )
    mismatches.extend(_spot_hash_package("sst", roots["sst"], EXTERNAL_PINS["sst"], _SST_SPOT))
    # Trace: the contract names no file-level spot path, so the repo-level
    # HEAD==pin check above is the trace binding (recorded explicitly).
    if mismatches:
        raise LeaseGitError("import-integrity: " + "; ".join(mismatches[:6]))
    return {
        "verdict": "pass",
        "stc_file": str(stc_file),
        "sys_path_head": path_head,
        "probe_pythonpath": probe_path,
        "ambient_pythonpath": os.environ.get("PYTHONPATH", ""),
        "externals": {name: EXTERNAL_PINS[name][:12] for name in roots},
        "trace_binding": "repo-HEAD==pin (no contract-named file path)",
    }
