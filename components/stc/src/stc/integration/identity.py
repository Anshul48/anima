"""Content-based candidate identity over git checkouts (P01, F3a-F3c).

Formula (ARCHITECTURE.md section 4; DESIGN_REVIEW.md F3a disposition)::

    identity(root) = sha256(canonical_json({
        "formula_version": FORMULA_VERSION,
        "head":            <git rev-parse HEAD>,
        "diff_sha256":     sha256(<raw `git diff HEAD` bytes>),
        "untracked":       {relpath: sha256(file bytes)} for the fixed glob set,
        "env":             {python_version, os, pip_digest},
    }))

Notes:

- ``git diff HEAD`` covers staged AND unstaged changes versus HEAD (F3a:
  diff bytes, never status text).
- Untracked files follow the P00 fixed glob list exactly:
  ``.py .md .yaml .json .toml .cfg .ini`` (F3b; note: no ``.yml``).
  Untracked directories are expanded; matching is on the lowercased suffix.
- The checkout path itself is recorded for audit but EXCLUDED from the
  digest: identity is content-based, so two checkouts with identical
  content share an identity regardless of where they live.
- ``pip_digest`` is ``sha256(pip freeze)`` of the CURRENT interpreter. When
  pip is unavailable (e.g. no pip module, cf. P00 V-OBS-2) the record
  carries an honest ``UNAVAILABLE:<reason>`` marker instead of guessing.
- :func:`compose_identity_map` composes per-root records into one
  deterministic JSON map plus a composite digest (F3c).
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

__all__ = [
    "FORMULA_VERSION",
    "UNTRACKED_SUFFIXES",
    "IdentityError",
    "IntegrationError",
    "candidate_identity",
    "compose_identity_map",
    "digest_record",
    "repo_identity_record",
]


class IntegrationError(Exception):
    """Base class for all ``stc.integration`` failures.

    P02-P04 catch this (or a subclass) around membrane crossings. Concrete
    reasons live in subclasses: undisposed content, run-binding mismatch,
    identity collection failure, bundle ceiling breach (STC native).
    """


class IdentityError(IntegrationError):
    """Candidate identity could not be collected or composed.

    Raised for non-git directories, missing paths, git failures, and empty
    composition requests. Never raised for content differences -- those
    simply change the digest.
    """


FORMULA_VERSION: Final[str] = "P01-1"

#: Fixed untracked-file glob list, exactly as fixed in P00 (F3b).
UNTRACKED_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".py", ".md", ".yaml", ".json", ".toml", ".cfg", ".ini"}
)

_GIT_TIMEOUT_S: Final[int] = 60
_PIP_TIMEOUT_S: Final[int] = 60

#: Record keys covered by the digest. ``root`` is deliberately absent:
#: identity is content-based, not location-based.
_DIGEST_KEYS: Final[tuple[str, ...]] = (
    "formula_version",
    "head",
    "diff_sha256",
    "untracked",
    "env",
)


def _git(repo: Path, args: list[str]) -> bytes:
    """Runs ``git -C <repo> <args>`` and returns raw stdout bytes."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise IdentityError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise IdentityError(f"git {' '.join(args)} timed out") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise IdentityError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _collect_untracked(repo: Path) -> dict[str, str]:
    """Hashes untracked files under the fixed glob list.

    ``git ls-files --others`` collapses untracked directories to ``dir/``
    entries; those are expanded so nested matches are still hashed.
    """
    raw = _git(repo, ["ls-files", "--others", "--exclude-standard", "-z"])
    candidates: list[str] = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        rel = entry.decode("utf-8", errors="surrogateescape")
        if rel.endswith("/"):
            for path in sorted((repo / rel).rglob("*")):
                if path.is_file():
                    candidates.append(path.relative_to(repo).as_posix())
        else:
            candidates.append(rel)
    hashed: dict[str, str] = {}
    for rel in sorted(set(candidates)):
        if Path(rel).suffix.lower() not in UNTRACKED_SUFFIXES:
            continue
        try:
            hashed[rel] = _sha256_bytes((repo / rel).read_bytes())
        except FileNotFoundError as exc:
            raise IdentityError(f"untracked file vanished mid-read: {rel}") from exc
        except IsADirectoryError as exc:
            raise IdentityError(f"untracked path is a directory: {rel}") from exc
    return hashed


def _pip_freeze_digest() -> str:
    """Digests ``pip freeze`` of the current interpreter, honestly degraded.

    Returns ``UNAVAILABLE:<reason>`` (deterministic per environment) when
    pip cannot run, instead of silently dropping the environment binding.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            check=False,
            timeout=_PIP_TIMEOUT_S,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        reason = "no-interpreter" if isinstance(exc, FileNotFoundError) else "timeout"
        return f"UNAVAILABLE:{reason}"
    if proc.returncode != 0:
        return f"UNAVAILABLE:exit={proc.returncode}"
    return _sha256_bytes(proc.stdout)


def _env_record() -> dict[str, str]:
    os_desc = f"{platform.system()} {platform.release()} {platform.machine()}".strip()
    return {
        "python_version": platform.python_version(),
        "os": os_desc,
        "pip_digest": _pip_freeze_digest(),
    }


def repo_identity_record(repo_root: str | Path) -> dict[str, Any]:
    """Collects the full identity record for one git checkout.

    The record carries ``root`` (audit), ``formula_version``, ``head``,
    ``diff_sha256``, ``diff_bytes``, ``untracked`` (path -> sha256), and
    ``env``. Only :data:`_DIGEST_KEYS` feed the digest; see module docs.
    """
    repo = Path(repo_root)
    if not repo.is_dir():
        raise IdentityError(f"not a directory: {repo}")
    head = _git(repo, ["rev-parse", "HEAD"]).decode("ascii").strip()
    diff_bytes = _git(repo, ["diff", "HEAD"])
    return {
        "root": str(repo.absolute()),
        "formula_version": FORMULA_VERSION,
        "head": head,
        "diff_sha256": _sha256_bytes(diff_bytes),
        "diff_bytes": len(diff_bytes),
        "untracked": _collect_untracked(repo),
        "env": _env_record(),
    }


def digest_record(record: Mapping[str, Any]) -> str:
    """Pure composition: identity digest for an already-collected record."""
    try:
        payload = {key: record[key] for key in _DIGEST_KEYS}
    except KeyError as exc:
        raise IdentityError(f"record missing digest key: {exc}") from exc
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(canonical.encode("utf-8"))


def candidate_identity(repo_root: str | Path) -> str:
    """Hex identity digest for one git checkout (collect + compose)."""
    return digest_record(repo_identity_record(repo_root))


def compose_identity_map(roots: Mapping[str, str | Path]) -> str:
    """Composes per-root records into one deterministic JSON map (F3c).

    Returns JSON text with ``roots`` (name -> full record plus its
    ``identity`` digest) and ``composite_identity`` (digest over the
    sorted name -> identity pairs). Key order is fixed, so the text is
    byte-stable for identical inputs.
    """
    if not roots:
        raise IdentityError("cannot compose an identity map over zero roots")
    built: dict[str, Any] = {}
    for name in sorted(roots):
        record = repo_identity_record(roots[name])
        record["identity"] = digest_record(record)
        built[name] = record
    composite = _sha256_bytes(
        json.dumps(
            {name: built[name]["identity"] for name in sorted(built)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return json.dumps(
        {
            "formula_version": FORMULA_VERSION,
            "roots": built,
            "composite_identity": composite,
        },
        sort_keys=True,
        indent=2,
    )
