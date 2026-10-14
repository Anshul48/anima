# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Routing calibration (stdlib-only, in-process).

Runs the SAME task (S2) through BOTH lanes on fresh hosts and reports
central-handled canonical-JSON bytes per lane plus the ratio. This is
the entire content of the calibrated "2-6x" claim: a serialized-bytes
ratio inside the task envelope — NO token/attention/cost equivalence
is claimed (see docs/ARCHITECTURE.md).

Run installed:
    PYTHONDONTWRITEBYTECODE=1 python3 -m anima_substrate.host.calibrate

Scratch state lives in a temporary directory and is removed
afterwards unless --out is given (evidence JSON only).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile

from ..demos import successor_demo as DEMO
from ..participants.sched import sched_inputs as FI
from .minihost import atomic_write_text
from .pipeline import LaneCtx, run_sched_task
from .routing import ChannelRegistry, Coordinator, HCoordinator, setup_host


def run_lane(lane: str, root: Path) -> dict:
    host = setup_host(root, DEMO.main_worlds(root / "state"))
    if lane == "central":
        ctx = LaneCtx("central", Coordinator(), ChannelRegistry())
    else:
        ctx = LaneCtx("local", HCoordinator(), ChannelRegistry())
    return run_sched_task(root, host, copy.deepcopy(FI.S2), ctx)


def calibrate(scratch: Path) -> dict:
    if scratch.exists():
        shutil.rmtree(scratch)
    c = run_lane("central", scratch / "central")
    loc = run_lane("local", scratch / "local")
    assert c["valid"] and loc["valid"]
    assert c["quality"] == c["prefs_total"] == 4
    assert loc["quality"] == loc["prefs_total"] == 4
    ratio = c["central_bytes"] / loc["central_bytes"]
    return {
        "task": "S2 (identical inputs both lanes)",
        "unit": (
            "central-handled canonical-JSON bytes inside the task "
            "envelope (coordinator.handle inputs; fragments central, "
            "commitments local)"
        ),
        "central_lane": {
            "central_bytes": c["central_bytes"],
            "direct_bytes": c["direct_bytes"],
        },
        "local_lane": {
            "central_bytes": loc["central_bytes"],
            "direct_bytes": loc["direct_bytes"],
        },
        "ratio_central_over_local": round(ratio, 2),
        "not_claimed": (
            "token/attention/cost equivalence, cross-task generality, learned routing"
        ),
    }


def main(argv: list[str]) -> int:
    out = None
    for a in argv[1:]:
        if a.startswith("--out="):
            out = Path(a.split("=", 1)[1])
    with tempfile.TemporaryDirectory(prefix="anima-calibrate-") as tmp:
        rep = calibrate(Path(tmp) / "calibrate")
    print(
        f"S2-central: central={rep['central_lane']['central_bytes']} "
        f"direct={rep['central_lane']['direct_bytes']}"
    )
    print(
        f"S2-local:   central={rep['local_lane']['central_bytes']} "
        f"direct={rep['local_lane']['direct_bytes']}"
    )
    print(
        f"ratio central/local = "
        f"{rep['ratio_central_over_local']}x "
        f"(canonical-JSON bytes, task envelope only)"
    )
    if out is not None:
        atomic_write_text(out, json.dumps(rep, indent=2, sort_keys=True) + "\n")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
