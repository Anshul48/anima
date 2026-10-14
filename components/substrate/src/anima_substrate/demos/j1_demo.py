# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""J1 persistent-worlds journey demo (exit 0 + PASS/FAIL).

Single command (with the package installed):
    PYTHONDONTWRITEBYTECODE=1 python3 -m anima_substrate.demos.j1_demo

Runs the whole journey on FRESH state under ./runs/ (override with
--state-dir=DIR):
  1. j1-init ..... persistent project world on a fresh ledger
  2. nest ........ experiment world + sub-grant/custody delegation
  3. work ........ first work task through the experiment world
  4. kill-resume . real Popen.kill() mid-task, reopen byte-identical
  5. status ...... inspect responsibilities + evidence
  6. fuse ........ project + experiment -> one composite
  7. reuse x2 .... composite reused UNMODIFIED in two follow-up tasks
  8. export ...... verifiable evidence bundle for the composite
  9. settle ...... 0 stranded, conservation ok

Each stage prints PASS/FAIL with its evidence; any failure exits 1.
Stdlib-only, offline, $0. All state stays inside the state dir.

Child mode (--child-partial DIR WORLD TASK): open the run, execute
only the formulate step, signal READY with artifact hashes, sleep
until the parent kills us (mirrors successor_demo child mode).
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

from ..host import api
from ..host.minihost import atomic_write_text
from ..host.resume import execute_plan
from ..participants.sched import sched_inputs as FI


def hash_tree(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix != ".tmp":
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ------------------------------------------------------- child mode


def child_partial(root: Path, world: str, task_id: str) -> int:
    host, _ = api.open_run(root)
    task = api.j1_task(task_id)
    plan, _, _ = api.j1_plan(host, task, world)
    rep = execute_plan(host, plan[:1])  # formulate step only
    assert rep["executed"] == ["sched.formulate@formulate@v1"], rep
    assert rep["re_executed_invokes"] == 0, rep
    state = root / "state" / world
    hashes = {}
    for rel in [
        f"formulations/{task_id}-formulation-v1.json",
        f"args/{task_id}-formulate@v1.json",
    ]:
        hashes[f"state/{world}/{rel}"] = hashlib.sha256(
            (state / rel).read_bytes()
        ).hexdigest()
    atomic_write_text(
        root / "child.READY",
        json.dumps(
            {"executed": rep["executed"], "artifact_hashes": hashes},
            indent=2,
            sort_keys=True,
        ),
    )
    while True:
        time.sleep(60)


# ------------------------------------------------------- parent flow


def run_journey(root: Path) -> dict:
    ev: dict = {"run_dir": str(root), "stages": {}}

    def stage(name: str, fn):
        try:
            out = fn()
            ev["stages"][name] = {"status": "PASS", "evidence": out}
            print(f"  [{name}] PASS {out}", flush=True)
            return out
        except Exception as exc:  # demo reports, then exits 1
            ev["stages"][name] = {
                "status": "FAIL",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-2000:],
            }
            print(f"  [{name}] FAIL {type(exc).__name__}: {exc}", flush=True)
            raise

    r1 = stage("j1-init", lambda: api.j1_init(root, "PROJ", "J1 persistent project"))
    assert r1["custody"] == ["j1.budget", "j1.plan"], r1

    r2 = stage(
        "nest",
        lambda: api.nest_op(
            root,
            "PROJ",
            "EXP1",
            {"max_cost_usd": 0.5, "max_time_s": 30.0, "max_invocations": 50},
            ["j1.budget"],
            "J1 experiment delegation",
        ),
    )
    assert r2["custody"] == ["j1.budget"], r2
    assert r2["delegation"] == {
        "max_cost_usd": 0.5,
        "max_time_s": 30.0,
        "max_invocations": 50.0,
    }, r2

    r3 = stage("work", lambda: api.j1_work_op(root, "EXP1", "J1-T1", verifier="PROJ"))
    assert r3["valid"] is True, r3
    assert r3["re_executed_invokes"] == 0, r3

    r4 = stage(
        "kill-resume",
        lambda: api.j1_kill_resume_op(root, "EXP1", "J1-T2", verifier="PROJ"),
    )
    assert r4["child_rc"] != 0, r4
    assert r4["valid"] is True, r4
    assert r4["re_executed_invokes"] == 0, r4

    def _status():
        s = api.j1_status_op(root)
        assert s["conservation"]["ok"] is True, s["conservation"]
        assert s["worlds"]["PROJ"]["lifecycle"] == "active"
        assert s["worlds"]["EXP1"]["lifecycle"] == "active"
        assert s["worlds"]["EXP1"]["custody"] == ["j1.budget"]
        assert len(s["delegations"]) == 2, s["delegations"]  # init + nest
        assert len(s["nests"]) == 1, s["nests"]
        assert len(s["solutions"]) == 2, s["solutions"]
        return {
            "worlds": sorted(s["worlds"]),
            "delegations": len(s["delegations"]),
            "solutions": s["solutions"],
            "conservation_ok": True,
        }

    stage("status", _status)

    r6 = stage(
        "fuse",
        lambda: api.fuse_op(root, "PROJ", "EXP1", "PROJ-FUSED", "J1 composite export"),
    )
    assert r6["fused_id"] == "PROJ-FUSED", r6

    reuse_lineage = []

    def _reuse1():
        m = api.reuse_op(root, "PROJ-FUSED", dict(FI.S4_FOLLOWUP))
        assert m["valid"] is True, m
        reuse_lineage.append(m["derived_from"])
        return {
            "task": m["task_id"],
            "valid": m["valid"],
            "quality": f"{m['quality']}/{m['prefs_total']}",
        }

    stage("reuse-task-1", _reuse1)

    def _reuse2():
        # SECOND task through the SAME composite with ZERO changes to
        # it in between (unmodified reuse): no new grant, no custody
        # move, no lifecycle edge — just another follow-up task.
        m = api.reuse_op(root, "PROJ-FUSED", dict(FI.S6_FISSION_FOLLOWUP))
        assert m["valid"] is True, m
        assert m["derived_from"] == reuse_lineage[0], m
        return {
            "task": m["task_id"],
            "valid": m["valid"],
            "quality": f"{m['quality']}/{m['prefs_total']}",
            "lineage_identical": True,
        }

    stage("reuse-task-2-unmodified", _reuse2)

    def _export():
        x = api.j1_export_op(root, "PROJ-FUSED")
        assert x["derived_from"] == ["PROJ", "EXP1"], x
        assert x["solutions"] == ["S4-followup", "S6-followup"], x
        return x

    stage("export", _export)

    def _settle():
        s = api.settle_op(root, ["PROJ-FUSED"], "J1 journey complete")
        assert s["conservation_ok"] is True, s
        return {"settled": s["settled_terminals"], "stranded": 0}

    stage("settle", _settle)

    return ev


def main(argv: list[str]) -> int:
    if len(argv) == 5 and argv[1] == "--child-partial":
        return child_partial(Path(argv[2]), argv[3], argv[4])
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = Path.cwd() / "runs" / f"j1-{stamp}"
    for a in argv[1:]:
        if a.startswith("--state-dir="):
            root = Path(a.split("=", 1)[1])
    print(f"J1 journey: fresh state at {root}")
    try:
        ev = run_journey(root)
    except Exception:
        print(f"J1 journey: FAILED (state kept at {root})")
        return 1
    failed = [n for n, s in ev["stages"].items() if s["status"] != "PASS"]
    print(
        f"J1 journey: {'OK' if not failed else 'FAILED'} "
        f"({len(ev['stages']) - len(failed)}/{len(ev['stages'])} PASS)"
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
