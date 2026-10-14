# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Release-identity / compat file checks over real caller files.

Pure stdlib file work with NO host imports: load a pins manifest,
hash every regular file under a tree root, compare. Used by the
relcheck v1/v2 participant families AND usable directly (it is also
the M4 from-scratch baseline). Every failure is a `RelcheckError`
carrying a named cause plus a fix — never a bare boolean, never
silent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST_VERSION_V1 = 1
MANIFEST_VERSION_V2 = 2


class RelcheckError(ValueError):
    """Actionable relcheck failure: named cause + fix."""

    def __init__(self, cause: str, fix: str) -> None:
        super().__init__(f"{cause}; fix: {fix}")
        self.cause = cause
        self.fix = fix


def _is_hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value.lower())
    )


def load_manifest(path: str | Path) -> tuple[dict, str, bytes]:
    """Load + validate a manifest; return (manifest, sha256, raw bytes)."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError:
        raise RelcheckError(
            f"manifest unreadable: {path}",
            f"pass task['manifest_path'] pointing at a readable "
            f"pins-manifest JSON file (got {path})",
        )
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise RelcheckError(
            f"manifest is not valid UTF-8 JSON: {path}",
            "repair the JSON (pins format: "
            '{"manifest_version": 1, "release": "...", '
            '"files": {"rel/path": "<sha256hex>"}})',
        )
    if not isinstance(manifest, dict):
        raise RelcheckError(
            f"manifest root is not an object: {path}",
            "use the pins format "
            '{"manifest_version": 1, "release": "...", "files": {...}}',
        )
    version = manifest.get("manifest_version")
    if version not in (MANIFEST_VERSION_V1, MANIFEST_VERSION_V2):
        raise RelcheckError(
            f"manifest_version {version!r} unknown (want 1 or 2): {path}",
            "set manifest_version to 1 (identity pins) or 2 "
            "(identity + compat rules), matching the family version",
        )
    if not isinstance(manifest.get("release"), str) or not manifest["release"]:
        raise RelcheckError(
            f"manifest has no release name: {path}",
            'add "release": "<release id>" to the manifest',
        )
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RelcheckError(
            f"manifest has no files pins: {path}",
            'add "files": {"rel/path": "<sha256hex>", ...} (at least one pinned file)',
        )
    for rel, digest in files.items():
        if not isinstance(rel, str) or not rel or rel.startswith("/"):
            raise RelcheckError(
                f"manifest pins a non-relative path {rel!r}: {path}",
                "pin tree-relative posix paths only (no absolute "
                "paths, no '..' segments)",
            )
        if ".." in Path(rel).parts or "\\" in rel:
            raise RelcheckError(
                f"manifest pins an escaping path {rel!r}: {path}",
                "pin tree-relative posix paths only (no absolute "
                "paths, no '..' segments)",
            )
        if not _is_hex64(digest):
            raise RelcheckError(
                f"manifest pin for {rel!r} is not a sha256 hex digest: {path}",
                "pin the lowercase sha256 hex of the exact released file bytes",
            )
    if version == MANIFEST_VERSION_V2:
        compat = manifest.get("compat")
        if not isinstance(compat, dict):
            raise RelcheckError(
                f"manifest_version 2 needs a compat object: {path}",
                'add "compat": {"min_release": "x.y", "requires_files": [...]}',
            )
        if not isinstance(compat.get("min_release"), str):
            raise RelcheckError(
                f"compat.min_release is not a string: {path}",
                'set "compat": {"min_release": "<dotted version>"}',
            )
        requires = compat.get("requires_files", [])
        if not isinstance(requires, list) or not all(
            isinstance(r, str) for r in requires
        ):
            raise RelcheckError(
                f"compat.requires_files is not a string list: {path}",
                'set "compat": {"requires_files": ["rel/path", ...]} (may be empty)',
            )
        for rel in requires:
            if not rel or rel.startswith("/") or ".." in Path(rel).parts:
                raise RelcheckError(
                    f"compat.requires_files pins an escaping path {rel!r}: {path}",
                    "list tree-relative posix paths only",
                )
    return manifest, hashlib.sha256(raw).hexdigest(), raw


def hash_tree(tree_root: str | Path) -> dict[str, str]:
    """sha256 of every regular file under tree_root, keyed by relpath."""
    root = Path(tree_root)
    if not root.is_dir():
        raise RelcheckError(
            f"tree_root is not a directory: {root}",
            "pass task['tree_root'] pointing at the released file "
            f"tree to verify (got {root})",
        )
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            raise RelcheckError(
                f"tree member is not a regular file: {rel}",
                "verify trees of regular files only (no symlinks, no special files)",
            )
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def verify_identity(manifest: dict, hashes: dict[str, str]) -> dict:
    """Compare tree hashes against manifest pins (pure verdict)."""
    pins = manifest["files"]
    missing = sorted(r for r in pins if r not in hashes)
    extra = sorted(r for r in hashes if r not in pins)
    mismatched = sorted(r for r in pins if r in hashes and pins[r] != hashes[r])
    return {
        "checked": len(hashes),
        "pinned": len(pins),
        "missing": missing,
        "extra": extra,
        "mismatched": mismatched,
        "valid": not (missing or extra or mismatched),
    }


def _norm_release(value: str) -> tuple:
    parts = []
    for chunk in value.strip().split("."):
        parts.append(int(chunk) if chunk.isdigit() else chunk)
    return tuple(parts)


def verify_compat(manifest: dict, release: str, hashes: dict[str, str]) -> dict:
    """Check v2 compat rules (pure verdict; declared=false when absent)."""
    compat = manifest.get("compat")
    if not isinstance(compat, dict):
        return {
            "declared": False,
            "min_release": None,
            "release_ok": None,
            "requires_files": [],
            "requires_missing": [],
            "valid": None,
        }
    try:
        release_ok = _norm_release(release) >= _norm_release(compat["min_release"])
    except Exception:
        release_ok = release == compat["min_release"]
    requires = list(compat.get("requires_files", []))
    requires_missing = sorted(r for r in requires if r not in hashes)
    valid = bool(release_ok) and not requires_missing
    return {
        "declared": True,
        "min_release": compat["min_release"],
        "release_ok": bool(release_ok),
        "requires_files": sorted(requires),
        "requires_missing": requires_missing,
        "valid": valid,
    }


def run_check(
    family: str,
    family_version: str,
    task_id: str,
    manifest_path: str | Path,
    tree_root: str | Path,
) -> tuple[dict, bytes]:
    """Full check over real files; return (report, manifest_raw).

    Raises RelcheckError (cause + fix) on malformed inputs; identity
    or compat mismatches are negative VERDICTS in the report, not
    exceptions. The report is deterministic (no timestamps).
    """
    manifest, manifest_sha, raw = load_manifest(manifest_path)
    want = MANIFEST_VERSION_V1 if family_version == "v1" else MANIFEST_VERSION_V2
    if manifest["manifest_version"] > want:
        raise RelcheckError(
            f"manifest_version {manifest['manifest_version']} needs "
            f"relcheck@v{manifest['manifest_version']} "
            f"(running v{family_version})",
            f"run this manifest through relcheck@v{manifest['manifest_version']} "
            f"instead of v{family_version}",
        )
    hashes = hash_tree(tree_root)
    identity = verify_identity(manifest, hashes)
    report: dict = {
        "family": family,
        "family_version": family_version,
        "task_id": task_id,
        "release": manifest["release"],
        "manifest_sha256": manifest_sha,
        "tree_root": str(tree_root),
        "identity": identity,
        "valid": identity["valid"],
    }
    if family_version != "v1":
        compat = verify_compat(manifest, manifest["release"], hashes)
        report["compat"] = compat
        if compat["valid"] is not None:
            report["valid"] = identity["valid"] and compat["valid"]
    return report, raw
