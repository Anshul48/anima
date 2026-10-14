# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Shared test helper: PROVENANCE.md file-record consistency.

The maintained package evolves, so frozen byte pins become
provenance discipline: every shipped file's sha256 MUST be recorded
in PROVENANCE.md's file-record section, and recorded shas MUST match
live bytes. Both directions are checked (no unrecorded files, no
stale records).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import anima_substrate

PKG = Path(anima_substrate.__file__).resolve().parent
TOP = PKG.parent.parent
PROVENANCE = TOP / "PROVENANCE.md"

SECTION = "## Maintained package file record"


def recorded_files() -> dict[str, str]:
    """{package-relative posix path: sha256} from PROVENANCE.md."""
    text = PROVENANCE.read_text(encoding="utf-8")
    start = text.index(SECTION)
    chunk = text[start:]
    out: dict[str, str] = {}
    for line in chunk.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        parts = line[2:].split()
        if len(parts) == 2 and len(parts[0]) == 64:
            out[parts[1]] = parts[0]
    return out


def live_sha(rel: str) -> str:
    return hashlib.sha256((TOP / rel).read_bytes()).hexdigest()


def shipped_files() -> list[str]:
    """Every shipped file (py + JSON fixtures/manifests + accept pack)."""
    out = []
    for p in sorted(PKG.rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts:
            continue
        if p.suffix in (".py", ".json"):
            out.append(p.relative_to(TOP).as_posix())
    return out
