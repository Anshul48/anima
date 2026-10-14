#!/usr/bin/env python3
"""SST caller-compatibility probe (STC side, read-only on SST).

Given an SST root, verifies what STC's dialectic runner needs:
  1. Required import surface (contracts/controller/policy/store/
     custody/capsule/gateway/events/models symbols).
  2. Byte identity of the pinned spot files against the declared pin
     (lease_git._SST_SPOT), via `git show <pin>:<rel>` from the SST
     git repo (read-only).
  3. execute_search signature presence on SSTSearchController.

Verdicts: COMPATIBLE (surface + bytes match), DIRTY (bytes differ),
MISSING-SURFACE, NO-GIT (cannot resolve pin blobs).

Usage:
  python3 scripts/sst_compat_probe.py --sst-root /path/to/sst \
      [--pin 079f4de...] [--git-repo /path/to/sst-git]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

STC_ROOT = Path(__file__).resolve().parents[2]

# Inline copy of lease_git._SST_SPOT (importing lease_git would require
# `sst` itself; this probe must run without any SST on its own path).
# Source: src/stc/integration/lease_git.py; keep in sync on pin moves.
_SST_SPOT = (
    ("src/sst/__init__.py", "__init__.py"),
    ("src/sst/core/contracts.py", "core/contracts.py"),
    ("src/sst/sandbox/custody.py", "sandbox/custody.py"),
)

SST_PIN_DEFAULT = "df78f42894a65c48f524337a498032617689a013"

# STC's caller uses execute_search + these contracts (adapters.py,
# dialectic_runner.py). run_search/SearchResult are newer SST-side
# surface: reported when present, never required.
REQUIRED_SURFACE = [
    ("sst.core.contracts", ["CandidateProposal", "ScoreBreakdown", "TaskPacket"]),
    ("sst.search.controller", ["SSTSearchController"]),
    ("sst.search.policy", ["SearchPolicy"]),
    ("sst.storage.store", ["SQLiteSSTStore"]),
    ("sst.sandbox.custody", ["CandidateCustodyManager"]),
    ("sst.context.capsule", ["ContextCapsuleCompiler"]),
    ("sst.gateway.gateway", ["ModelGateway"]),
    ("sst.core.events", ["EventKind", "SSTEvent"]),
    ("sst.core.models", ["DeterministicGateResult"]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sst-root", required=True)
    ap.add_argument("--pin", default=SST_PIN_DEFAULT)
    ap.add_argument("--git-repo", default=None)
    args = ap.parse_args()
    root = Path(args.sst_root)
    git_repo = Path(args.git_repo) if args.git_repo else root

    probe = (
        "import importlib, json, sys\n"
        f"sys.path.insert(0, {(str(root / 'src'))!r})\n"
        f"req = {REQUIRED_SURFACE!r}\n"
        "import sst.search.controller as _c\n"
        "out = {\n"
        "    'execute_search': hasattr(_c.SSTSearchController, 'execute_search'),\n"
        "    'run_search': hasattr(_c.SSTSearchController, 'run_search'),\n"
        "    'missing': {},\n"
        "}\n"
        "for mod, names in req:\n"
        "    m = importlib.import_module(mod)\n"
        "    out['missing'][mod] = [n for n in names if not hasattr(m, n)]\n"
        "print(json.dumps(out))\n"
    )
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"VERDICT: MISSING-SURFACE\n{(r.stderr or r.stdout)[-800:]}")
        return 2
    import json as _json

    surface = _json.loads(r.stdout)
    missing = {m: n for m, n in surface["missing"].items() if n}
    print(f"surface: execute_search={surface['execute_search']} run_search={surface['run_search']}")
    if missing or not surface["execute_search"]:
        print(f"VERDICT: MISSING-SURFACE {missing}")
        return 2

    drift = []
    nogit = False
    for pin_rel, pkg_rel in _SST_SPOT:
        exp = subprocess.run(
            ["git", "-C", str(git_repo), "show", f"{args.pin}:{pin_rel}"],
            capture_output=True,
            timeout=60,
        )
        if exp.returncode != 0:
            nogit = True
            break
        observed = (root / "src" / "sst" / pkg_rel).read_bytes()
        if observed != exp.stdout:
            drift.append(f"sst/{pkg_rel}: differs from pin blob")
    if nogit:
        print("VERDICT: NO-GIT (pin blobs unresolvable)")
        return 3
    if drift:
        print("VERDICT: DIRTY")
        for d in drift:
            print(f"  - {d}")
        return 1
    print(f"VERDICT: COMPATIBLE pin={args.pin[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
