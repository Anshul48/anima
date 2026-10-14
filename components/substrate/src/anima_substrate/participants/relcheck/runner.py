# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Shared relcheck run path (v1/v2 differ only in checks + caps)."""

from __future__ import annotations

import json
import math
from pathlib import Path
import time

from anima_substrate.host import api
from anima_substrate.host.minihost import atomic_write_bytes, atomic_write_text
from anima_substrate.participants.relcheck.checker import run_check

GRANT_LIMITS = {
    "max_cost_usd": 0.0,
    "max_time_s": 120.0,
    "max_invocations": 50.0,
}


def run_task(
    family: str,
    family_version: str,
    cap: str,
    cap_ver: str,
    state_dir: str | Path,
    world_id: str,
    task: dict,
) -> dict:
    """Run one relcheck task through the world; report measured cost."""
    root = Path(state_dir)
    host, _ = api.open_run(root)
    if world_id not in host.worlds:
        raise ValueError(
            f"{family} run refused: unknown world {world_id!r}; fix: "
            f"create it first via {family}@v{family_version} create"
        )
    task_id = task.get("task_id", f"{world_id}-T1")
    manifest_path = task.get("manifest_path", "")
    tree_root = task.get("tree_root", "")
    args_ref = host.store_args(
        world_id,
        f"{family}-{task_id}",
        {
            "formulation_ref": f"{family}:{task_id}",
            "candidate_refs": [],
            "manifest_path": str(manifest_path),
            "tree_root": str(tree_root),
        },
    )
    before = dict(host.consumed.get(world_id, {}))
    report_dir = root / "state" / world_id / "relcheck" / task_id
    elapsed = {"s": 0.0}

    def _check() -> str:
        t0 = time.time()
        report, raw = run_check(
            family, family_version, task_id, manifest_path, tree_root
        )
        elapsed["s"] = time.time() - t0
        atomic_write_bytes(report_dir / "manifest.json", raw)
        return atomic_write_text(
            report_dir / "report.json",
            json.dumps(report, indent=2, sort_keys=True) + "\n",
        )

    entry = host.invoke(
        world_id,
        world_id,
        cap,
        cap_ver,
        args_ref,
        _check,
        cost_usd=0.0,
        time_s=0.0,
    )
    # Ledger-record the measured wall time (rounded UP 0.1 s, P14
    # style); the invoke itself already consumed 1 invocation.
    host.consume(
        world_id,
        cost_usd=0.0,
        time_s=math.ceil(elapsed["s"] * 10.0) / 10.0,
        invocations=0,
        evidence_ref=entry["payload"]["invoke_id"],
    )
    host, _ = api.open_run(root)
    after = dict(host.consumed.get(world_id, {}))
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["report_ref"] = str(report_dir / "report.json")
    report["manifest_ref"] = str(report_dir / "manifest.json")
    report["invoke_seq"] = entry["seq"]
    report["measured_cost"] = {
        k: round(after.get(k, 0.0) - before.get(k, 0.0), 6)
        for k in ("max_cost_usd", "max_time_s", "max_invocations")
    }
    report["elapsed_s"] = round(elapsed["s"], 3)
    return report


def recover_world(family: str, state_dir: str | Path, world_id: str) -> dict:
    """Reopen-verify a relcheck world; adopt/report, invent nothing."""
    root = Path(state_dir)
    host, _ = api.open_run(root)
    if world_id not in host.worlds:
        raise ValueError(f"{family} recover refused: unknown world {world_id!r}")
    try:
        conservation = host.verify_conservation()
    except Exception as exc:  # read-only probe: report, don't raise
        conservation = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    rdir = root / "state" / world_id / "relcheck"
    reports = (
        sorted(p.parent.name for p in rdir.glob("*/report.json"))
        if rdir.exists()
        else []
    )
    return {
        "world_id": world_id,
        "lifecycle": host.worlds[world_id].lifecycle,
        "conservation": conservation,
        "reports": reports,
        "holdings": dict(host.holdings.get(world_id, {})),
        "consumed": dict(host.consumed.get(world_id, {})),
    }
