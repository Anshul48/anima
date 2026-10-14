# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Integrated demo runner (exit 0 + evidence summary).

One ledger, full path: S1 central -> S2 local -> S3 kill+resume+revision+
revocation+ruling -> fusion (+channel removal) -> S4 reuse -> fission
(+channel restore) -> S6 split-pair reuse -> S5 quarantine drill ->
SST-TEST leg (staged snapshot) -> settle with 0 stranded.

Child mode (--child-partial ROOT): attach to the main ledger, run the S3
partial plan, signal READY, sleep until the parent kills us with
Popen.kill() (SIGKILL on POSIX, TerminateProcess on Windows:
cross-platform by construction, no signal module needed).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from ..host.fusion import fission_worlds, fuse_worlds, quarantine_world, reuse_composite
from ..host.minihost import ContractViolation, MiniHost, atomic_write_text
from ..host.pipeline import (
    FUSED_CAPS,
    L_CAPS,
    L_REPS,
    Q_CAPS,
    S_CAPS,
    S_REPS,
    LaneCtx,
    build_formulate,
    build_propose,
    build_verify,
    run_sched_task,
    run_split_pair_task,
    s3_partial_plan,
    s3_resume_flow,
)
from ..host.resume import execute_plan, reapply_revocations, scan_succeeded
from ..host.routing import (
    ChannelRegistry,
    Coordinator,
    HCoordinator,
    finish_worlds,
    rebuild_records,
    record_routing,
    route,
    setup_host,
    world_record,
    write_json,
)
from ..participants.sched import sched_inputs as FI


def run_sst_test_search(rundir, **k):  # staged-or-refuse (see host.api)
    from ..host.api import run_sst_test_search as _run

    return _run(rundir, **k)


def main_worlds(state_dir: Path):
    return [
        world_record(
            state_dir,
            "SC-L",
            L_CAPS,
            L_REPS,
            custodians={"sched.requirements": "SC-L", "sched.composite": "SC-L"},
        ),
        world_record(
            state_dir, "SC-S", S_CAPS, S_REPS, custodians={"sched.slots": "SC-S"}
        ),
    ]


def s5_worlds(state_dir: Path):
    return [
        world_record(
            state_dir,
            "SC-Q",
            Q_CAPS,
            [("sched-list", "v1")],
            custodians={"sched.commitment-q": "SC-Q"},
        ),
        world_record(state_dir, "SC-B", Q_CAPS, [("sched-list", "v1")]),
    ]


def hash_tree(root: Path) -> dict:
    import hashlib

    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ------------------------------------------------------- child mode


def child_partial(root: Path) -> int:
    records = main_worlds(root / "state")
    host = MiniHost.reopen(
        root / "state",
        root / "ledger.jsonl",
        records,
        actor="s3-child",
        reason="attach for S3 partial",
    )
    ctx = LaneCtx("local", HCoordinator(), ChannelRegistry())
    rep = execute_plan(host, s3_partial_plan(host, FI.S3, ctx))
    assert rep["executed"] == [
        "sched.formulate@formulate@v1",
        "sched.clarify@clarify@r1",
        "sched.clarify@clarify@r2",
    ], rep
    assert rep["re_executed_invokes"] == 0, rep
    atomic_write_text(root / "child.READY", json.dumps(rep, indent=2))
    while True:
        time.sleep(60)


# ------------------------------------------------------- parent flow


def wait_ready(root: Path, timeout_s: int = 180) -> None:
    t0 = time.time()
    while not (root / "child.READY").exists():
        if time.time() - t0 > timeout_s:
            raise RuntimeError("child never signaled READY")
        time.sleep(0.2)


def run_demo(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    evidence: dict = {"run_dir": str(root)}
    routing_log = root / "ROUTING-LOG.jsonl"

    # ---- main host: S1 + S2 share one ledger with the later S3/fusion
    worlds = main_worlds(root / "state")
    pristine = copy.deepcopy(worlds)
    host = setup_host(root, worlds)
    chans = ChannelRegistry()

    # ---- S1: small -> central default
    d1 = route(FI.S1)
    assert d1["lane"] == "central", d1
    record_routing(host, d1, routing_log)
    ctx1 = LaneCtx("central", Coordinator(), chans)
    m1 = run_sched_task(root, host, FI.S1, ctx1)
    assert m1["valid"] and m1["quality"] == m1["prefs_total"], m1
    assert m1["direct_bytes"] == 0, m1
    assert m1["central_bytes"] == m1["live_central_bytes"], m1
    evidence["S1"] = m1

    # ---- S2: dialogue-heavy over split state -> local lane
    d2 = route(FI.S2)
    assert d2["lane"] == "local", d2
    record_routing(host, d2, routing_log)
    ctx2 = LaneCtx("local", HCoordinator(), chans)
    m2 = run_sched_task(root, host, FI.S2, ctx2)
    assert m2["valid"] and m2["quality"] == m2["prefs_total"], m2
    assert m2["direct_bytes"] > 0 and m2["central_bytes"] < 2000, m2
    evidence["S2"] = m2

    # ---- S3: real forced-termination resume on the integrated path
    d3 = route({**FI.S3, "task_id": "S3"})
    assert d3["lane"] == "local", d3
    record_routing(host, d3, routing_log)
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "anima_substrate.demos.successor_demo",
            "--child-partial",
            str(root),
        ],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    wait_ready(root)
    # Child is past its last write (READY is ordered after it): snapshot
    # the full pre-kill state, then really kill it.
    prekill_files = hash_tree(root / "state")
    child.kill()  # real forced termination (cross-platform by construction)
    out, err = child.communicate(timeout=60)
    assert child.returncode != 0, "child should have been killed, not exited"
    # parent drops its stale handle and reopens (replay rebuilds seq,
    # holdings, lifecycle); revocations (none yet) re-applied.
    host = MiniHost.reopen(
        root / "state",
        root / "ledger.jsonl",
        rebuild_records(root, pristine),
        actor="host",
        reason="resume after SIGKILL",
    )
    redone = reapply_revocations(host)
    assert redone == [], redone
    prekill = scan_succeeded(host)
    assert ("sched.formulate", "S3", "formulate@v1") in prekill, prekill
    ctx3 = LaneCtx("local", HCoordinator(), chans)
    m3 = s3_resume_flow(root, host, FI.S3, ctx3, prekill)
    assert m3["valid"] and m3["quality"] == m3["prefs_total"], m3
    assert m3["re_executed_invokes"] == 0, m3
    assert any(s.startswith("sched.formulate@formulate@v1") for s in m3["skipped"]), m3[
        "skipped"
    ]
    postkill_files = hash_tree(root / "state")

    def is_history(path: str) -> bool:
        # Per-task history must be immutable; the canonical-latest
        # verdict.json pointer is SUPPOSED to advance to the newest task.
        return not path.endswith("verdicts/verdict.json")

    identical = all(
        postkill_files.get(k) == v for k, v in prekill_files.items() if is_history(k)
    )
    assert identical, "pre-kill artifacts changed across resume"
    latest = json.loads(
        Path(
            host.worlds["SC-L"].instance_state_dir, "verdicts", "verdict.json"
        ).read_text(encoding="utf-8")
    )
    assert latest["task_id"] == "S3", latest  # latest-pointer advanced
    n_reopen = sum(1 for e in host.ledger_entries() if e.get("kind") == "host_reopen")
    assert n_reopen >= 2, n_reopen  # child attach + parent resume
    evidence["S3"] = m3
    evidence["kill"] = {
        "child_rc": child.returncode,
        "reopen_markers": n_reopen,
        "prekill_artifacts_identical": identical,
        "child_stdout_tail": out.decode()[-300:],
        "child_stderr_tail": err.decode()[-300:],
    }

    # ---- fusion: SC-L + SC-S -> SC-FUSED (channel removed)
    fused_rec = world_record(
        root / "state",
        "SC-FUSED",
        FUSED_CAPS,
        [("sched-list", "v2"), ("sched-slot", "v2")],
    )
    fusion = fuse_worlds(
        host,
        chans,
        "SC-L",
        "SC-S",
        "SC-FUSED",
        fused_rec,
        "host",
        "S1+S2 cooperation complete; fuse sched pair into one composite",
    )
    assert fusion["removed_mechanism"] == "direct-channel:SC-L<->SC-S"
    write_json(root / "artifacts" / "fusion-record.json", fusion)
    evidence["fusion"] = {
        k: fusion[k]
        for k in (
            "fused_id",
            "parents",
            "transfers",
            "removed_mechanism",
            "removed_channel_bytes",
            "removed_channel_messages",
        )
    }
    evidence["fusion"]["before_mechanisms"] = fusion["before"]["mechanisms"]
    evidence["fusion"]["after_mechanisms"] = fusion["after"]["mechanisms"]

    # ---- S4: reuse the fused composite on a follow-up task elsewhere
    record_routing(
        host,
        {
            "task_id": "S4-followup",
            "lane": "fused-reuse",
            "rule": "post-fusion composite reuse",
            "inputs": {"via": "SC-FUSED"},
            "reason": "follow-up runs through the fused "
            "composite, not the dissolved pair",
        },
        routing_log,
    )
    m4 = reuse_composite(root, host, "SC-FUSED", FI.S4_FOLLOWUP)
    assert m4["valid"] and m4["lineage_ok"], m4
    evidence["S4"] = m4

    # ---- fission: SC-FUSED -> SC-L2 + SC-S2 (partition record)
    record_routing(
        host,
        {
            "task_id": "S6-followup",
            "lane": "fission-reuse",
            "rule": "post-fission split-pair reuse",
            "inputs": {"via": ["SC-L2", "SC-S2"]},
            "reason": "follow-up runs through the fission "
            "children, not the dissolved composite",
        },
        routing_log,
    )
    l2_rec = world_record(root / "state", "SC-L2", L_CAPS, L_REPS)
    s2_rec = world_record(root / "state", "SC-S2", S_CAPS, S_REPS)
    partition = {
        "sched.composite": "SC-L2",
        "sched.requirements": "SC-L2",
        "sched.slots": "SC-S2",
    }
    fission = fission_worlds(
        host,
        chans,
        "SC-FUSED",
        "SC-L2",
        "SC-S2",
        l2_rec,
        s2_rec,
        partition,
        "host",
        "S4 reuse complete; split the composite back into a sched pair",
    )
    assert fission["restored_mechanism"] == "direct-channel:SC-L2<->SC-S2"
    write_json(root / "artifacts" / "fission-record.json", fission)
    evidence["fission"] = {
        k: fission[k]
        for k in (
            "composite",
            "children",
            "partition",
            "transfers",
            "restored_mechanism",
        )
    }
    evidence["fission"]["fusion"] = fission["fusion"]
    evidence["fission"]["before_mechanisms"] = fission["before"]["mechanisms"]
    evidence["fission"]["after_mechanisms"] = fission["after"]["mechanisms"]

    # ---- S6: the split pair cooperates on a fresh task
    m6 = run_split_pair_task(root, host, FI.S6_FISSION_FOLLOWUP, "SC-L2", "SC-S2")
    assert m6["valid"] and m6["quality"] == m6["prefs_total"], m6
    evidence["S6"] = m6

    # ---- S5: quarantine drill (declared separation path) on a sub-host
    record_routing(
        host,
        {
            "task_id": "S5",
            "lane": "quarantine-drill",
            "rule": "declared separation path exercise",
            "inputs": {"world": "SC-Q", "standby": "SC-B"},
            "reason": "failed-participant quarantine with commitment transfer",
        },
        routing_log,
    )
    s5root = root / "s5"
    s5host = setup_host(s5root, s5_worlds(s5root / "state"))
    s5task = dict(FI.S5)
    qform = build_formulate(
        s5host, s5task, "SC-Q", "v1", LaneCtx("central", Coordinator(), None)
    )
    qform["args"]["task_id"] = "S5"
    qrep = execute_plan(s5host, [qform])
    assert qrep["executed"] == ["sched.formulate@formulate@v1"], qrep
    quar = quarantine_world(
        s5host, "SC-Q", "SC-B", "host", "S5 drill: SC-Q failed mid-task"
    )
    denied_probe: dict | None = None
    try:
        s5host.invoke(
            "SC-Q",
            "SC-Q",
            "sched.propose",
            "1.0",
            s5host.store_args(
                "SC-Q",
                "S5-probe",
                {
                    "formulation_ref": "",
                    "candidate_refs": [],
                    "task_id": "S5",
                    "step": "probe",
                },
            ),
            lambda: "never",
            cost_usd=0.0,
            time_s=1.0,
        )
        raise AssertionError("quarantined invoke unexpectedly succeeded")
    except ContractViolation as exc:
        denies = [e for e in s5host.ledger_entries() if e.get("kind") == "deny"]
        assert denies, "quarantine probe raised without recorded deny"
        denied_probe = {
            "error": f"{type(exc).__name__}: {exc}",
            "deny_seq": denies[-1]["seq"],
        }
    bctx = LaneCtx("central", Coordinator(), None)
    bprop = build_propose(
        s5host,
        s5task,
        "SC-B",
        "merged reqs + clarified prefs (O2; standby completion)",
        bctx,
        tag="propose",
    )
    bprop["args"]["task_id"] = "S5"
    bver = build_verify(s5host, s5task, "SC-B", bctx, "SC-B", "propose")
    bver["args"]["task_id"] = "S5"
    brep = execute_plan(s5host, [bprop, bver])
    assert brep["re_executed_invokes"] == 0, brep
    s5settle = finish_worlds(s5host, ["SC-Q", "SC-B"], reason="S5 drill over")
    evidence["S5"] = {
        "quarantine": quar,
        "denied_probe": denied_probe,
        "standby_completed": brep["executed"],
        "settle": s5settle,
    }

    # ---- SST-TEST leg (staged snapshot only)
    evidence["SST"] = run_sst_test_search(root / "sst-leg")
    assert evidence["SST"]["cost_usd"] == 0.0
    assert evidence["SST"]["snapshot_unchanged"] is True

    # ---- settle the integrated path with 0 stranded
    evidence["settle"] = finish_worlds(host, ["SC-L2", "SC-S2"], reason="demo complete")
    routing_entries = [
        e["payload"] for e in host.ledger_entries() if e.get("kind") == "routing"
    ]
    assert {p["task_id"] for p in routing_entries} >= {
        "S1",
        "S2",
        "S3",
        "S4-followup",
        "S5",
        "S6-followup",
    }, routing_entries
    evidence["routing"] = routing_entries
    atomic_write_text(
        root / "EVIDENCE.json",
        json.dumps(evidence, indent=2, sort_keys=True, default=str),
    )
    return evidence


def print_summary(ev: dict) -> None:
    print("anima-substrate integrated demo (run_demo needs the SST optional extra): OK")
    print(f"  run_dir: {ev['run_dir']}")
    for tid in ("S1", "S2", "S3", "S4", "S6"):
        m = ev[tid]
        print(
            f"  {tid}: lane={m.get('lane', m.get('via'))} "
            f"valid={m['valid']} quality={m['quality']}/{m['prefs_total']} "
            f"central={m.get('central_bytes', '-')} "
            f"direct={m.get('direct_bytes', '-')}"
        )
    print(
        f"  S3 resume: skipped={len(ev['S3']['skipped'])} "
        f"re_executed={ev['S3']['re_executed_invokes']} "
        f"child_rc={ev['kill']['child_rc']} "
        f"artifacts_identical={ev['kill']['prekill_artifacts_identical']}"
    )
    print(f"  S3 ruling: {ev['S3']['ruling']}; revoked={ev['S3']['revoked']}")
    print(
        f"  fusion: {ev['fusion']['fused_id']} from "
        f"{ev['fusion']['parents']}; "
        f"removed={ev['fusion']['removed_mechanism']}"
    )
    print(
        f"  fission: {ev['fission']['composite']} -> "
        f"{ev['fission']['children']}; "
        f"restored={ev['fission']['restored_mechanism']}"
    )
    print(
        f"  S5 quarantine: {ev['S5']['quarantine']['world_id']} -> "
        f"{ev['S5']['quarantine']['standby']}; "
        f"probe_denied_seq={ev['S5']['denied_probe']['deny_seq']}"
    )
    print(
        f"  SST: snapshot={ev['SST']['snapshot_check']} "
        f"hash={ev['SST']['snapshot_hash'][:12]} "
        f"termination={ev['SST']['termination_reason']} "
        f"champion={ev['SST']['champion']} cost=${ev['SST']['cost_usd']} "
        f"pydantic={ev['SST']['pydantic_version']}"
    )
    print(
        f"  settle: {ev['settle']['settled_terminals']} "
        f"markers={ev['settle']['grant_settle_markers']} stranded=0"
    )
    print(f"  routing decisions: {len(ev['routing'])} recorded")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child-partial":
        sys.exit(child_partial(Path(sys.argv[2])))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    rundir = Path.cwd() / "runs" / f"demo-{stamp}"
    for a in sys.argv[1:]:
        if a.startswith("--run-dir="):
            rundir = Path(a.split("=", 1)[1])
    ev = run_demo(rundir)
    print_summary(ev)
