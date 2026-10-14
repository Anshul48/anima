# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""SST snapshot manifest construction (stdlib-only, no SST bytes).

Carried construction `substrate-snapshot-v1` from the frozen
successor-005 `make_snapshot_manifest.py` (hash algorithm + file
enumeration only — zero SST source bytes live in this package). The
pinned manifest this verifies against is `SNAPSHOT-MANIFEST.json`
next to this module: relpaths + sha256 digests (pins, not bytes).

Staging (caller-provided root): see `docs/SST-STAGING.md`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ...host.minihost import atomic_write_text

CONSTRUCTION = "substrate-snapshot-v1"
EXPECTED_FILE_COUNT = 54
PINNED_SNAPSHOT_HASH = (
    "5f1f37893b0f5ab9ff7dcf0ce2c60b287b51647e2f18f627eabf5510537cad96"
)
PINNED_SST_COMMIT = "df78f42894a65c48f524337a498032617689a013"
PINNED_PYDANTIC = "2.13.5"
LABEL = "SUBSTRATE-QUALIFIED SNAPSHOT — NO SST-OWNER RELEASE ACCEPTANCE"

HERE = Path(__file__).resolve().parent
PINNED_MANIFEST = HERE / "SNAPSHOT-MANIFEST.json"


def collect_files(snapshot_dir: Path) -> list[str]:
    """Sorted snapshot-root-relative posix relpaths of every file under sst/.

    ALL regular files are pinned (importable or not); __pycache__ is
    excluded (never staged).
    """
    pkg = snapshot_dir / "sst"
    if not pkg.is_dir():
        raise ValueError(f"snapshot has no sst/ package dir: {pkg}")
    rels = []
    for p in pkg.rglob("*"):
        if "__pycache__" in p.parts:
            continue
        if p.is_dir():
            continue
        if p.is_symlink() or not p.is_file():
            raise ValueError(f"snapshot member is not a regular file: {p}")
        rels.append(p.relative_to(snapshot_dir).as_posix())
    return sorted(rels)


def file_manifest(snapshot_dir: Path) -> list[dict[str, str]]:
    out = []
    for rel in collect_files(snapshot_dir):
        digest = hashlib.sha256((snapshot_dir / rel).read_bytes()).hexdigest()
        out.append({"relpath": rel, "sha256": digest})
    return out


def payload_bytes(manifest: list[dict[str, str]]) -> bytes:
    """HASH-CONSTRUCTION payload: relpath LF hexdigest LF per file."""
    return b"".join(
        entry["relpath"].encode("utf-8")
        + b"\n"
        + entry["sha256"].encode("ascii")
        + b"\n"
        for entry in manifest
    )


def snapshot_hash(manifest: list[dict[str, str]]) -> str:
    return hashlib.sha256(payload_bytes(manifest)).hexdigest()


def build_manifest(snapshot_dir: Path) -> dict:
    manifest = file_manifest(snapshot_dir)
    return {
        "construction": CONSTRUCTION,
        "file_count": len(manifest),
        "files": manifest,
        "label": LABEL,
        "snapshot_hash": snapshot_hash(manifest),
    }


def write_manifest(snapshot_dir: Path, out_path: Path) -> dict:
    """Build + atomically write a manifest (staging/upgrade tooling)."""
    doc = build_manifest(snapshot_dir)
    atomic_write_text(out_path, json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return doc
