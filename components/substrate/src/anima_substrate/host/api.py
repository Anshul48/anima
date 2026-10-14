# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained programmatic API (stdlib-only; SST search is an optional extra).

The operable surface over the demo-proven path. Every function takes
an explicit state dir chosen by the caller; nothing is written outside
that dir (tests use temporary directories).

State layout under STATE_DIR (created by init_run):
    ledger.jsonl        the integrated ledger
    state/              per-world state dirs
    ROUTING-LOG.jsonl   routing decisions (mirrors ledger `routing`)
    artifacts/          solutions + fusion/fission records
    worlds.json         world descriptor specs (for reopen)
    CONFIG.json         release + run metadata
    sst-leg/            SST evidence (only when the SST leg runs)

Successor-005 procedure runs add (only in proc runs; sched layout
byte-identical): state/<W>/procedures/<name>/ (staged bundles),
state/proc-scratch/<key>/<step>-attempt<N>/ (per-step scratch),
artifacts/proc-<key>/<step>/ (collected outputs + RESULT.json).

Channels persist to `channels.json` (M3: crash-atomic on every
mutation, restored by open_run). Ops that need a channel (fuse)
ensure it exists first and say so in their record.

Typical flow:
    from anima_substrate.host import api
    api.init_run("runs/cli-01")
    api.run_tasks("runs/cli-01", ["S1", "S2"])
    api.fuse_op("runs/cli-01", "SC-L", "SC-S", "SC-FUSED", reason="...")
    api.fission_op("runs/cli-01", "SC-FUSED", "SC-L2", "SC-S2",
                   {"sched.requirements": "SC-L2", ...}, reason="...")
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from ..demos import successor_demo as DEMO
from ..participants.sched import sched_inputs as FI
from . import procedure as PROC
from . import recipes as RECIPES
from . import recover as RC
from .fusion import fission_worlds, fuse_worlds, quarantine_world, reuse_composite
from .minihost import (
    ContractViolation,
    MiniHost,
    atomic_write_text,
    maybe_crash_at,
    maybe_sync_at,
)
from .pipeline import (
    FUSED_CAPS,
    L_CAPS,
    L_REPS,
    Q_CAPS,
    S_CAPS,
    S_REPS,
    LaneCtx,
    apply_revision,
    build_formulate,
    build_propose,
    build_verify,
    export_commitments,
    run_sched_task,
    run_split_pair_task,
    s3_resume_flow,
)
from .resume import reapply_revocations, revoke_capability, scan_succeeded
from .routing import (
    ChannelRegistry,
    Coordinator,
    HCoordinator,
    finish_worlds,
    record_routing,
    route,
    setup_host,
    world_record,
    write_json,
)


def run_sst_test_search(rundir: str | Path, **k) -> dict:
    """SST leg: run over the caller-staged root, or refuse loudly.

    Staged when SUBSTRATE_SST_ROOT points at a checkout passing the
    compat probe (see `docs/SST-STAGING.md`); otherwise a loud
    RuntimeError naming the staging variable — never a silent skip.
    """
    from ..participants.sst.staged import SSTBoundary
    from ..participants.sst.staged import run_sst_test_search as _run

    if not os.environ.get("SUBSTRATE_SST_ROOT", "").strip():
        raise RuntimeError(
            "run_tasks(..., with_sst=True) refused: no staged SST "
            "checkout (SUBSTRATE_SST_ROOT is unset); stage one per "
            "docs/SST-STAGING.md or re-run without with_sst"
        )
    try:
        return _run(rundir, **k)
    except SSTBoundary as exc:
        raise RuntimeError(f"run_tasks(..., with_sst=True) refused: {exc}") from exc


RELEASE = "anima-substrate-0.1.0"

CAP_PRESETS: dict[str, tuple[list, list]] = {
    "L": (L_CAPS, L_REPS),
    "S": (S_CAPS, S_REPS),
    "FUSED": (FUSED_CAPS, [("sched-list", "v2"), ("sched-slot", "v2")]),
    "Q": (Q_CAPS, [("sched-list", "v1")]),
}

LANE_TASKS = {"S1": FI.S1, "S2": FI.S2}


# ------------------------------------------------------------- specs


def _spec(
    world_id: str,
    caps: list[tuple[str, str]],
    reps: list[tuple[str, str]],
    custodians: dict | None = None,
    procedures: list | None = None,
) -> dict:
    spec = {
        "world_id": world_id,
        "caps": [[n, v] for n, v in caps],
        "reps": [[n, v] for n, v in reps],
        "custodians": dict(custodians or {}),
    }
    if procedures:
        # S5 R-A: additive-absent-when-empty — sched specs emit no
        # `procedures` key at all; proc worlds pin their table.
        spec["procedures"] = [dict(t) for t in procedures]
    return spec


def _read_specs(state_dir: Path) -> list[dict]:
    return json.loads((state_dir / "worlds.json").read_text(encoding="utf-8"))


def _write_specs(state_dir: Path, specs: list[dict]) -> None:
    # R3 (F2 fix): crash-atomic — a SIGKILL here leaves old-or-new
    # specs, never a torn worlds.json.
    atomic_write_text(
        state_dir / "worlds.json", json.dumps(specs, indent=2, sort_keys=True) + "\n"
    )


def _record_for(state_dir: Path, spec: dict):
    return world_record(
        state_dir / "state",
        spec["world_id"],
        [(n, v) for n, v in spec["caps"]],
        [(n, v) for n, v in spec["reps"]],
        custodians=dict(spec.get("custodians", {})),
        procedures=[dict(t) for t in spec.get("procedures", [])],
    )


# ------------------------------------------------------------- open


def init_run(state_dir: str | Path) -> dict:
    """Create a fresh run root with SC-L + SC-S on one ledger."""
    root = Path(state_dir)
    if (root / "ledger.jsonl").exists():
        raise FileExistsError(f"run root already initialized: {root}")
    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)
    worlds = DEMO.main_worlds(root / "state")
    setup_host(root, worlds)
    specs = [
        _spec(
            "SC-L",
            L_CAPS,
            L_REPS,
            {"sched.requirements": "SC-L", "sched.composite": "SC-L"},
        ),
        _spec("SC-S", S_CAPS, S_REPS, {"sched.slots": "SC-S"}),
    ]
    _write_specs(root, specs)
    config = {
        "release": RELEASE,
        "created_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "worlds": ["SC-L", "SC-S"],
        "tasks_run": [],
    }
    atomic_write_text(
        root / "CONFIG.json", json.dumps(config, indent=2, sort_keys=True) + "\n"
    )
    return {"state_dir": str(root), "worlds": ["SC-L", "SC-S"], "config": config}


def open_run(state_dir: str | Path) -> tuple[MiniHost, ChannelRegistry]:
    """Reopen a run root: replay the ledger, restore creation lineage,
    re-apply revocations.

    Lineage note: raw MiniHost.reopen keeps the lineage of the SUPPLIED
    descriptors (which only verify code_ref/caps/reps), so fusion /
    fission lineage would be lost on reopen. The ledger `create`
    payloads carry the authoritative creation lineage, so open_run
    restores it from there (the documented recovery procedure).
    """
    root = Path(state_dir)
    if not (root / "ledger.jsonl").exists():
        raise FileNotFoundError(f"not a run root (no ledger.jsonl): {root}")
    records = [_record_for(root, spec) for spec in _read_specs(root)]
    host = MiniHost.reopen(
        root / "state",
        root / "ledger.jsonl",
        records,
        actor="host",
        reason="api open_run",
    )
    for e in host.ledger_entries():
        if e.get("kind") == "create":
            wid = e["payload"].get("world_id")
            if wid in host.worlds:
                host.worlds[wid].lineage = copy.deepcopy(
                    e["payload"].get("lineage", [])
                )
                # S5: the ledger `create` payloads are likewise
                # authoritative for the creation-fixed procedure
                # table (absent ≡ empty).
                host.worlds[wid].procedures = copy.deepcopy(
                    e["payload"].get("procedures", [])
                )
                # Carried J1 nest: `create` payloads are likewise
                # authoritative for creation-fixed authorities (worlds
                # born without authorities restore [] — byte-identical
                # behavior for sched worlds).
                host.worlds[wid].authorities = copy.deepcopy(
                    e["payload"].get("authorities", [])
                )
    reapply_revocations(host)
    # M3: channels restore from the persisted registry (missing file
    # ≡ no channels yet; a torn file refuses loudly as disk-loss).
    return host, ChannelRegistry(root / "channels.json")


def _remember_creation(
    root: Path, world_id: str, caps, reps, procedures: list | None = None
) -> None:
    specs = _read_specs(root)
    if world_id not in {s["world_id"] for s in specs}:
        specs.append(_spec(world_id, caps, reps, procedures=procedures))
        _write_specs(root, specs)


def birth_world(
    state_dir: str | Path,
    world_id: str,
    caps: list[tuple[str, str]],
    reps: list[tuple[str, str]],
    grant_limits: dict | None,
    reason: str,
    custodians: dict | None = None,
    authorities: list | None = None,
    lineage: list | None = None,
    procedures: list | None = None,
) -> dict:
    """Birth + fund + activate a world (participant-family surface).

    The ONLY host mutation families need: births the world with the
    given creation-fixed capabilities/representations, funds it from
    host holdings (refusing when the grant exceeds them — delegation
    never manufactures resources), activates it, and records the
    creation spec so reopen restores the full record. All validation
    runs BEFORE any mutation. The run root must already exist (see
    `init_run`); families birth into it without any host edit.
    """
    root = Path(state_dir)
    if not (root / "ledger.jsonl").exists():
        raise ValueError(
            f"birth refused: {root} is not a run root (no ledger.jsonl); "
            f"create one first with `anima-substrate init --state-dir {root}`"
        )
    host, _ = open_run(root)
    if world_id in host.worlds:
        raise ContractViolation(
            f"birth refused: world_id {world_id!r} already used (ids never reused)"
        )
    rec = world_record(
        root / "state",
        world_id,
        list(caps),
        list(reps),
        custodians=dict(custodians or {}),
        authorities=list(authorities or []),
        lineage=list(lineage) if lineage is not None else None,
        procedures=[dict(t) for t in procedures] if procedures else None,
    )
    host.create_world(rec, "host", grant_limits=dict(grant_limits or {}))
    host.transition(world_id, "active", "host", reason=f"birth: {reason}")
    _remember_creation(root, world_id, list(caps), list(reps), procedures=procedures)
    return {
        "state_dir": str(root),
        "world_id": world_id,
        "caps": [[n, v] for n, v in caps],
        "reps": [[n, v] for n, v in reps],
        "grant": dict(grant_limits or {}),
    }


# ------------------------------------------------------------- run


def run_tasks(
    state_dir: str | Path, tasks: list[str] | None = None, with_sst: bool = False
) -> dict:
    """Route + run lane tasks (S1/S2) on the run root. Optionally the SST leg."""
    root = Path(state_dir)
    tasks = tasks or ["S1", "S2"]
    unknown = [t for t in tasks if t not in LANE_TASKS]
    if unknown:
        raise ValueError(
            f"run_tasks supports {sorted(LANE_TASKS)}; "
            f"got {unknown} (S3 runs via kill_resume_op, "
            f"S4/S6 via fuse/fission + reuse ops)"
        )
    host, chans = open_run(root)
    routing_log = root / "ROUTING-LOG.jsonl"
    out: dict = {"state_dir": str(root), "tasks": {}}
    for name in tasks:
        task = copy.deepcopy(LANE_TASKS[name])
        decision = route(task)
        record_routing(host, decision, routing_log)
        if decision["lane"] == "central":
            ctx = LaneCtx("central", Coordinator(), chans)
        else:
            ctx = LaneCtx("local", HCoordinator(), chans)
        m = run_sched_task(root, host, task, ctx)
        out["tasks"][name] = {
            "lane": m["lane"],
            "valid": m["valid"],
            "quality": m["quality"],
            "prefs_total": m["prefs_total"],
            "central_bytes": m["central_bytes"],
            "direct_bytes": m["direct_bytes"],
            "solution_ref": m["solution_ref"],
        }
    if with_sst:
        out["SST"] = run_sst_test_search((root / "sst-leg").resolve())
    config = json.loads((root / "CONFIG.json").read_text(encoding="utf-8"))
    config["tasks_run"].extend(tasks)
    atomic_write_text(
        root / "CONFIG.json", json.dumps(config, indent=2, sort_keys=True) + "\n"
    )
    return out


# ------------------------------------------------------------- ops


def fuse_op(
    state_dir: str | Path,
    a: str,
    b: str,
    fused_id: str,
    reason: str,
    preset: str = "FUSED",
) -> dict:
    """Fuse worlds a+b into `fused_id` (ORG-OPS OP-1)."""
    root = Path(state_dir)
    host, chans = open_run(root)
    caps, reps = CAP_PRESETS[preset]
    chans.get(a, b)  # channels are in-memory: ensure-then-remove
    record = fuse_worlds(
        host,
        chans,
        a,
        b,
        fused_id,
        _record_for(root, _spec(fused_id, caps, reps)),
        "host",
        reason,
    )
    maybe_crash_at("api:fuse:pre-spec")  # R1 kill boundary (test-only)
    _remember_creation(root, fused_id, caps, reps)
    atomic_write_text(
        root / "artifacts" / f"fusion-{fused_id}.json",
        json.dumps(record, indent=2, sort_keys=True, default=str),
    )
    return record


def fission_op(
    state_dir: str | Path,
    composite: str,
    left: str,
    right: str,
    partition: dict[str, str],
    reason: str,
    left_preset: str = "L",
    right_preset: str = "S",
) -> dict:
    """Fission `composite` into left+right per partition (ORG-OPS OP-6)."""
    root = Path(state_dir)
    host, chans = open_run(root)
    lcaps, lreps = CAP_PRESETS[left_preset]
    rcaps, rreps = CAP_PRESETS[right_preset]
    record = fission_worlds(
        host,
        chans,
        composite,
        left,
        right,
        _record_for(root, _spec(left, lcaps, lreps)),
        _record_for(root, _spec(right, rcaps, rreps)),
        partition,
        "host",
        reason,
    )
    maybe_crash_at("api:fission:pre-spec")  # R1 kill boundary (test-only)
    _remember_creation(root, left, lcaps, lreps)
    _remember_creation(root, right, rcaps, rreps)
    atomic_write_text(
        root / "artifacts" / f"fission-{composite}.json",
        json.dumps(record, indent=2, sort_keys=True, default=str),
    )
    return record


def quarantine_op(
    state_dir: str | Path,
    world: str,
    standby: str,
    reason: str,
    create_standby: bool = False,
) -> dict:
    """Quarantine `world` with transfer to `standby` (ORG-OPS OP-5)."""
    root = Path(state_dir)
    host, _ = open_run(root)
    if create_standby and standby not in host.worlds:
        caps, reps = CAP_PRESETS["Q"]
        from .routing import GRANT_LIMITS

        host.create_world(
            _record_for(root, _spec(standby, caps, reps)),
            "host",
            grant_limits=dict(GRANT_LIMITS),
        )
        host.transition(
            standby, "active", "host", reason="standby birth for quarantine"
        )
        _remember_creation(root, standby, caps, reps)
    return quarantine_world(host, world, standby, "host", reason)


def quarantine_complete_op(
    state_dir: str | Path, world: str, standby: str, reason: str = "recover"
) -> dict:
    """COMPLETE a partial quarantine-transfer (supported R11 repair).

    Transfers the remaining recorded handoffs world->standby
    (actor=host, the documented O4 exception) and appends the ledger
    `quarantine` entry. The caller names the ORIGINAL standby: any
    disagreement with the recorded handoffs refuses loudly, never
    silently diverging. Kill-during-completion converges on re-run.
    """
    root = Path(state_dir)
    host, _ = open_run(root)
    return RC.complete_quarantine(host, world, standby, "host", reason)


def quarantine_rollback_op(
    state_dir: str | Path, world: str, standby: str, reason: str = "recover"
) -> dict:
    """ROLL BACK a partial quarantine-transfer (supported R11 repair).

    Reverses the recorded handoffs standby->world (actor=standby),
    reattaches the world, and appends a `quarantine_rollback`
    resolution entry. Refuses loudly when custody moved since the
    kill or the world is not reattachable. Kill-during-rollback
    converges on re-run.
    """
    root = Path(state_dir)
    host, _ = open_run(root)
    return RC.rollback_quarantine(host, world, standby, "host", reason)


def revise_op(
    state_dir: str | Path, task_id: str, frm: str, to: str, reason: str
) -> dict:
    """Record a representation revision (ORG-OPS OP-3, ledger entry)."""
    root = Path(state_dir)
    host, _ = open_run(root)
    return apply_revision(host, task_id, {"from": frm, "to": to, "reason": reason})


def revoke_op(
    state_dir: str | Path,
    world: str,
    capability: str,
    version: str,
    reason: str,
    new_owner: str = "",
) -> dict:
    """Revoke a capability, durably (ORG-OPS OP-4; LIMITS-2 scope).

    Durable (LIMITS-2) = ledger-recorded on local disk across a process crash
    (re-applied after reopen); no fsync is issued, so power/media
    loss stays the disk-loss class (LIMITS-2, out of scope).
    """
    root = Path(state_dir)
    host, _ = open_run(root)
    return revoke_capability(
        host,
        world,
        capability,
        version,
        actor="host",
        reason=reason,
        new_owner=new_owner,
    )


def reuse_op(state_dir: str | Path, composite: str, followup: dict) -> dict:
    """Reuse a fused composite on a follow-up task (ORG-OPS OP-2)."""
    root = Path(state_dir)
    host, _ = open_run(root)
    return reuse_composite(root, host, composite, followup)


def split_pair_op(state_dir: str | Path, task: dict, left: str, right: str) -> dict:
    """Run a task through a fission-split pair (S6 pattern)."""
    root = Path(state_dir)
    host, _ = open_run(root)
    return run_split_pair_task(root, host, task, left, right)


def _init_proc_root(root: Path) -> None:
    """Initialize a procedure-run root (no sched worlds).

    Same file layout as init_run, but the host holds
    PROC_ROOT_HOLDINGS (minutes-adequate) instead of the sched
    envelope. Used only when create_proc_world targets an
    uninitialized dir; sched roots are byte-identical to before.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)
    MiniHost(
        root / "state",
        root / "ledger.jsonl",
        root_holdings=dict(PROC.PROC_ROOT_HOLDINGS),
    )
    _write_specs(root, [])
    config = {
        "release": RELEASE,
        "created_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "worlds": [],
        "tasks_run": [],
    }
    atomic_write_text(
        root / "CONFIG.json", json.dumps(config, indent=2, sort_keys=True) + "\n"
    )


def create_proc_world(
    state_dir: str | Path,
    world_id: str,
    bundle_dir: str | Path,
    reason: str,
    sched_preset: str | None = None,
) -> dict:
    """Advertise a procedure world (S5 §1.1/§1.8).

    Validates the caller bundle (ValueError naming the defect, zero
    ledger effect), stages a host-owned copy under
    state/<W>/procedures/<name>/, creates the world with
    caps=[proc.exec@v1] (+ the sched preset's caps for hybrid
    worlds) and the creation-fixed `procedures` table, funds it
    with PROC_GRANT_LIMITS, and activates it. On an uninitialized
    dir, initializes a procedure-run root first (minutes-adequate
    host holdings); on an existing root, opens it.
    """
    root = Path(state_dir)
    src = Path(bundle_dir)
    name = PROC.validate_procedure_name(src.name)
    if not (root / "ledger.jsonl").exists():
        _init_proc_root(root)
    host, _ = open_run(root)
    # Pre-stage duplicate check (create_world would refuse after
    # staging; refuse before any side effect instead). host.worlds
    # covers every lifecycle incl. retired (ids never reused).
    if world_id in host.worlds:
        raise ContractViolation(
            f"world_id {world_id!r} already used (ids never reused)"
        )
    if sched_preset is not None and sched_preset not in CAP_PRESETS:
        raise ValueError(
            f"unknown sched_preset {sched_preset!r} (want one of {sorted(CAP_PRESETS)})"
        )
    staged_dir = root / "state" / world_id / "procedures" / name
    manifest, bundle_sha = PROC.stage_bundle(src, staged_dir)
    table = [
        {
            "name": name,
            "bundle_sha256": bundle_sha,
            "manifest_ref": str(staged_dir / PROC.MANIFEST_NAME),
            "steps": [s["step"] for s in manifest["steps"]],
        }
    ]
    if sched_preset is None:
        caps: list = [(PROC.PROC_CAP, PROC.PROC_VER)]
        reps: list = []
    else:
        preset_caps, preset_reps = CAP_PRESETS[sched_preset]
        caps = list(preset_caps) + [(PROC.PROC_CAP, PROC.PROC_VER)]
        reps = list(preset_reps)
    rec = world_record(root / "state", world_id, caps, reps, procedures=table)
    host.create_world(rec, "host", grant_limits=dict(PROC.PROC_GRANT_LIMITS))
    host.transition(world_id, "active", "host", reason=f"proc birth: {reason}")
    maybe_crash_at("api:create-proc-world:pre-spec")
    _remember_creation(root, world_id, caps, reps, procedures=table)
    return {
        "state_dir": str(root),
        "world_id": world_id,
        "procedure": name,
        "bundle_sha256": bundle_sha,
        "manifest_ref": table[0]["manifest_ref"],
        "steps": table[0]["steps"],
        "grant": dict(PROC.PROC_GRANT_LIMITS),
        "sched_preset": sched_preset,
    }


def run_procedure(
    state_dir: str | Path,
    world_id: str,
    procedure: str,
    idem_key: str,
    inputs: dict | None = None,
) -> dict:
    """Execute a table procedure (S5 §1.8): all steps in order with
    skip-match. Returns {skipped, executed, re_executed_steps,
    child_executions, results}."""
    root = Path(state_dir)
    host, _ = open_run(root)
    rep = PROC.run_procedure(host, root, world_id, procedure, idem_key, inputs)
    rep["state_dir"] = str(root)
    rep["world_id"] = world_id
    rep["procedure"] = procedure
    rep["idem_key"] = idem_key
    return rep


def settle_op(state_dir: str | Path, worlds: list[str], reason: str) -> dict:
    """Settle-then-dissolve worlds with 0-stranded verification.

    Successor-003: atomic on refusal (zero partial dissolves; see
    routing.finish_worlds). Kill-during-settle recovery: recover_op.
    """
    root = Path(state_dir)
    host, _ = open_run(root)
    return finish_worlds(host, worlds, reason=reason)


def _recovery_note(
    root: Path, kind: str, wid: str, seq: int | None, entry: dict, completed: bool
) -> str | None:
    """Write artifacts/recovery-<kind>-<id>.json when the original record
    file is missing (kill between ledger-complete and artifact write).
    Timestamp-free (C6-style): deterministic bytes."""
    orig = root / "artifacts" / f"{kind}-{wid}.json"
    note_path = root / "artifacts" / f"recovery-{kind}-{wid}.json"
    if orig.exists() or note_path.exists():
        return None
    atomic_write_text(
        note_path,
        json.dumps(
            {
                "kind": kind,
                "id": wid,
                "ledger_seq": seq,
                "completed_by_recovery": completed,
                "ledger_entry": entry,
                "note": "ledger entry is authoritative; the original record "
                "file was lost to a kill (or never written)",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return str(note_path)


def recover_op(
    state_dir: str | Path,
    worlds: list[str] | None = None,
    reason: str = "recover",
    fission: str | None = None,
    left: str | None = None,
    right: str | None = None,
    partition: dict[str, str] | None = None,
    left_preset: str = "L",
    right_preset: str = "S",
) -> dict:
    """Recover a run after a kill: repair + complete, loudly (R1).

    Steps: reopen (replay); repair worlds.json specs missing for
    ledger-known worlds; refuse fail-closed when conservation fails;
    complete interrupted births + fusions automatically; complete ONE
    interrupted fission when --fission/--left/--right/--partition name
    it (refuses with exact operator steps otherwise); detect (never
    silently complete) partial quarantines; settle exactly `worlds`
    (default: settle NOTHING -- pass --worlds explicitly; mass
    dissolve is never a default).

    Raises RuntimeError (operator input needed, steps in message) or
    ContractViolation (fail-closed state violation). Re-running after
    a kill during recovery converges (every step is ledger-
    conditional). See docs/RECOVERY.md.

    Successor-005: also adopts side-complete procedure steps (L3:
    DONE present, no invoke — verified then adopted with ONE
    recovered invoke) and reports re-runnable ones (L2: killed
    mid-step — re-invoke the same key) as `proc_adopted` /
    `proc_rerunnable` / `proc_nothing_to_do`. Recovery never spawns.
    """
    root = Path(state_dir)
    try:
        host, _ = open_run(root)
    except ValueError as exc:
        raise RuntimeError(
            f"recovery refused: ledger or worlds.json unreadable "
            f"({exc}); torn files are the disk-loss class "
            f"(LIMITS-2, out of scope): restore from backup, never "
            f"hand-edit; see docs/RECOVERY.md"
        ) from exc
    try:
        specs = _read_specs(root)
    except FileNotFoundError:
        specs = []
    idx = RC.ledger_index(host)
    repaired = RC.repair_specs(root, host, idx, specs)
    if repaired:
        host, _ = open_run(root)
        idx = RC.ledger_index(host)
    try:
        conservation = host.verify_conservation()
    except ContractViolation as exc:
        raise ContractViolation(
            f"recovery refused: ledger fails conservation ({exc}); "
            f"resolve the violation first (inspect via "
            f"`anima-substrate inspect --state-dir {root} --json`; see "
            f"docs/RECOVERY.md), then re-run recover"
        ) from exc
    partials_f = RC.detect_partial_fusions(host, idx)
    partials_s = RC.detect_partial_fissions(host, idx)
    skip = set()
    for pf in partials_f:
        skip.add(pf["composite"])
        skip.update(pf["parents"])
    for ps in partials_s:
        skip.add(ps["composite"])
        skip.update(ps["children_created"])
    births = RC.run_births(host, idx, RC.plan_births(host, idx, skip))
    fusions_completed = []
    for pf in partials_f:
        rec = RC.complete_fusion(host, pf["composite"], "host", reason)
        fusions_completed.append(
            {
                "fused_id": rec["fused_id"],
                "parents": rec["parents"],
                "transfers": len(rec["transfers"]),
            }
        )
    idx = RC.ledger_index(host)
    partials_s = RC.detect_partial_fissions(host, idx)
    fissions_completed: list[dict] = []
    fission_args = (fission, left, right, partition)
    if partials_s:
        if not all(fission_args):
            names = ", ".join(p["composite"] for p in partials_s)
            detail = "; ".join(
                f"{p['composite']}: children={p['children_created']} "
                f"transfers={p['transfers_done']}"
                for p in partials_s
            )
            raise RuntimeError(
                f"partial fission(s) of {names} need operator input "
                f"({detail}): re-run recover with --fission C --left L "
                f"--right R --partition k=v,... (+ presets when "
                f"non-default); the supplied partition must agree "
                f"with recorded progress"
            )
        if fission not in {p["composite"] for p in partials_s}:
            raise RuntimeError(
                f"no partial fission of {fission} "
                f"(partial now: "
                f"{[p['composite'] for p in partials_s]}); "
                f"nothing to complete"
            )
        lcaps, lreps = CAP_PRESETS[left_preset]
        rcaps, rreps = CAP_PRESETS[right_preset]
        rec = RC.complete_fission(
            host,
            root,
            fission,
            left,
            right,
            partition,
            lcaps,
            lreps,
            rcaps,
            rreps,
            "host",
            reason,
        )
        fissions_completed.append(
            {
                "composite": rec["composite"],
                "children": rec["children"],
                "transfers": len(rec["transfers"]),
            }
        )
    elif any(fission_args):
        raise RuntimeError(
            "--fission/--left/--right/--partition given but no "
            "partial fission exists; nothing to complete"
        )
    idx = RC.ledger_index(host)
    # S5: adopt-if-complete (L3) + report re-runnable steps (L2).
    # Adopt runs BEFORE the settle phase so one call can adopt and
    # then settle; rerunnable (L2) needs no withholding (a killed
    # mid-step attempt is consistent-but-incomplete, like a
    # half-executed sched plan — settling abandons it cleanly, and
    # re-invoke after settle refuses loudly by the not-active rule).
    # Recovery never spawns (adopt + report only).
    maybe_sync_at("proc:recover-pre-adopt")  # test-only rendezvous
    proc_rec = PROC.proc_recover(host, root)
    idx = RC.ledger_index(host)
    partials_q = RC.detect_partial_quarantines(host, idx)
    q_steps = [RC.quarantine_operator_steps(p) for p in partials_q]
    blocked = {p["world"] for p in partials_q}
    # structural guard: never settle a world still inside an
    # uncompleted partial fusion/fission (complete it first).
    still_blocked = set(blocked)
    for pf in RC.detect_partial_fusions(host, idx):
        still_blocked.add(pf["composite"])
        still_blocked.update(pf["parents"])
    for ps in RC.detect_partial_fissions(host, idx):
        still_blocked.add(ps["composite"])
        still_blocked.update(ps["children_created"])
    notes = []
    for fid, info in idx["fusions"].items():
        note = _recovery_note(
            root,
            "fusion",
            fid,
            info["seq"],
            info["payload"],
            fid in {f["fused_id"] for f in fusions_completed},
        )
        if note:
            notes.append(note)
    for cid, info in idx["fission"].items():
        note = _recovery_note(
            root,
            "fission",
            cid,
            info["seq"],
            info["payload"],
            cid in {f["composite"] for f in fissions_completed},
        )
        if note:
            notes.append(note)
    settle_rep: dict | None = None
    already: list[str] = []
    if worlds is None:
        active = sorted(
            w for w, r in host.worlds.items() if r.lifecycle in ("active", "suspended")
        )
    else:
        for w in worlds:
            if w in still_blocked:
                raise RuntimeError(
                    f"recovery refused to settle {w}: inside an "
                    f"uncompleted partial op (complete it first)"
                )
        known = [w for w in worlds if w in host.worlds]
        unknown = [w for w in worlds if w not in host.worlds]
        already = sorted(
            w for w in known if host.worlds[w].lifecycle not in ("active", "suspended")
        )
        active = (
            sorted(
                w for w in known if host.worlds[w].lifecycle in ("active", "suspended")
            )
            + unknown
        )
        if active:
            settle_rep = finish_worlds(host, active, reason=reason)
    return {
        "state_dir": str(root),
        "specs_repaired": repaired,
        "births_completed": births,
        "conservation_before_completion": {
            "ok": True,
            "settled_terminals": conservation["settled_terminals"],
        },
        "fusions_completed": fusions_completed,
        "fissions_completed": fissions_completed,
        "fissions_still_partial": [
            p["composite"]
            for p in partials_s
            if p["composite"] not in {f["composite"] for f in fissions_completed}
        ],
        "partial_quarantines": partials_q,
        "quarantine_operator_steps": q_steps,
        "recovery_notes": notes,
        "proc_adopted": proc_rec["adopted"],
        "proc_rerunnable": proc_rec["rerunnable"],
        "proc_nothing_to_do": proc_rec["nothing_to_do"],
        "settle_targets": active if worlds is not None else [],
        "settle_already_terminal": already,
        "settle_skipped_no_worlds": worlds is None,
        "settle": settle_rep,
    }


def kill_resume_op(state_dir: str | Path, timeout_s: int = 180) -> dict:
    """Real kill-resume drill: spawn the S3 partial child, Popen.kill()
    it, reopen, and finish the S3 adaptation flow (revise + revoke +
    ruling + void + re-propose + verify). Requires ACTIVE SC-L/SC-S
    (fresh init, or pre-fusion state)."""
    root = Path(state_dir).resolve()
    host, _ = open_run(root)
    for wid in ("SC-L", "SC-S"):
        if host.worlds[wid].lifecycle != "active":
            raise RuntimeError(
                f"kill_resume_op needs active SC-L/SC-S "
                f"({wid} is {host.worlds[wid].lifecycle})"
            )
    del host
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
    t0 = time.time()
    while not (root / "child.READY").exists():
        if time.time() - t0 > timeout_s:
            child.kill()
            raise RuntimeError("kill_resume_op: child never READY")
        if child.poll() is not None:
            raise RuntimeError(
                f"kill_resume_op: child died early rc={child.returncode}"
            )
        time.sleep(0.2)
    child.kill()
    out, err = child.communicate(timeout=60)
    if child.returncode == 0:
        raise RuntimeError("kill_resume_op: child exited, not killed")
    host, chans = open_run(root)
    prekill = scan_succeeded(host)
    ctx = LaneCtx("local", HCoordinator(), chans)
    m3 = s3_resume_flow(root, host, FI.S3, ctx, prekill)
    (root / "child.READY").unlink(missing_ok=True)
    return {
        "child_rc": child.returncode,
        "S3": m3,
        "child_stderr_tail": err.decode()[-300:],
    }


# ------------------------------------------------------------- J1
#
# Persistent-worlds journey (carried J1): a PROJECT world owns
# durable (process-crash-only, no fsync — LIMITS-2) state on a fresh
# ledger; an EXPERIMENT world is nested in
# it with a recorded delegation (sub-grant + custody handoff); work
# runs through the carried resume engine; a real kill resumes
# byte-identical; responsibilities + evidence stay inspectable; the
# pair fuses into a composite that is reused UNMODIFIED in a second
# task. All stages run through this consumer surface (or the
# anima-substrate CLI over it) on FRESH state. See docs/CONSUMER.md.

J1_PROJECT_CUSTODY = ("j1.plan", "j1.budget")


def j1_init(
    state_dir: str | Path, project: str, reason: str = "J1 project world"
) -> dict:
    """Create a fresh J1 run root holding one PROJECT world.

    The project is born active with custody of its plan + budget
    classes, a fresh sched grant, and the `grant.delegate` authority
    (creation-fixed, restored from the ledger on every reopen) so it
    can delegate sub-budgets to nested experiment worlds.
    """
    from .routing import GRANT_LIMITS

    root = Path(state_dir)
    if (root / "ledger.jsonl").exists():
        raise FileExistsError(f"run root already initialized: {root}")
    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)
    rec = world_record(
        root / "state",
        project,
        L_CAPS,
        L_REPS,
        custodians={sc: project for sc in J1_PROJECT_CUSTODY},
        authorities=["grant.delegate"],
    )
    setup_host(root, [rec])
    specs = [_spec(project, L_CAPS, L_REPS, {sc: project for sc in J1_PROJECT_CUSTODY})]
    _write_specs(root, specs)
    host, _ = open_run(root)
    host.append(
        "j1_project",
        {"project": project, "reason": reason, "custody": sorted(J1_PROJECT_CUSTODY)},
        actor="host",
    )
    config = {
        "release": RELEASE,
        "journey": "J1",
        "created_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "worlds": [project],
        "tasks_run": [],
    }
    atomic_write_text(
        root / "CONFIG.json", json.dumps(config, indent=2, sort_keys=True) + "\n"
    )
    return {
        "state_dir": str(root),
        "project": project,
        "custody": sorted(J1_PROJECT_CUSTODY),
        "grant": dict(GRANT_LIMITS),
    }


def nest_op(
    state_dir: str | Path,
    project: str,
    child: str,
    delegate: dict,
    custody: list[str],
    reason: str,
    child_preset: str = "Q",
) -> dict:
    """Nest an EXPERIMENT world in a project with a recorded delegation.

    The child is born with lineage derived_from the project; the
    project delegates a sub-grant (`delegate`, NEVER manufactured:
    each key must fit the project's live holdings, else loud
    ContractViolation with ZERO mutation) and hands off the listed
    custody classes (actor=project, the giver, O4). A ledger `nest`
    entry records {project, child, delegation, custody, reason}.
    All preconditions validate BEFORE any mutation.
    """
    root = Path(state_dir)
    host, _ = open_run(root)
    if project not in host.worlds:
        raise RuntimeError(f"nest refused: unknown project {project!r}")
    if host.worlds[project].lifecycle != "active":
        raise RuntimeError(
            f"nest refused: project {project} is "
            f"{host.worlds[project].lifecycle}, not active"
        )
    if child in host.worlds:
        raise ContractViolation(
            f"nest refused: world_id {child!r} already used (ids never reused)"
        )
    if child_preset not in CAP_PRESETS:
        raise ValueError(
            f"unknown child_preset {child_preset!r} (want one of {sorted(CAP_PRESETS)})"
        )
    want = {
        k: float(delegate.get(k, 0.0))
        for k in ("max_cost_usd", "max_time_s", "max_invocations")
    }
    if any(v < 0 for v in want.values()):
        raise ValueError(f"nest refused: negative delegation {want}")
    held = host.holdings.get(project, {})
    short = [k for k in want if want[k] > held.get(k, 0) + 1e-9]
    if short:
        raise ContractViolation(
            f"nest refused: delegation {want} exceeds {project} "
            f"holdings {held} on {short} (delegation never "
            f"manufactures resources); zero mutation"
        )
    for sc in custody:
        if host.worlds[project].custodians.get(sc) != project:
            raise ContractViolation(
                f"nest refused: {project} is not custodian of {sc!r}; zero mutation"
            )
    if "grant.delegate" not in host.worlds[project].authorities:
        raise ContractViolation(
            f"nest refused: {project} lacks grant.delegate authority"
        )
    # ---- execute (all validation passed)
    caps, reps = CAP_PRESETS[child_preset]
    rec = world_record(root / "state", child, caps, reps)
    rec.lineage = [
        {"rel": "derived_from", "world": project},
        {"rel": "nest", "actor": "host", "reason": reason},
    ]
    host.create_world(rec, "host", grant_limits=None)
    host.grant(project, child, want, authority=[], grant_id=f"g-delegate-{child}")
    host.transition(
        child, "active", "host", reason=f"nest birth in {project}: {reason}"
    )
    moved = []
    for sc in sorted(custody):
        host.transfer_custody(
            sc,
            project,
            child,
            actor=project,
            reason=f"nest delegation: {reason}",
            continuity="delegation-handoff",
        )
        moved.append({"state_class": sc, "from": project, "to": child})
    host.append(
        "nest",
        {
            "project": project,
            "child": child,
            "delegation": want,
            "custody": sorted(custody),
            "transfers": moved,
            "reason": reason,
        },
        actor="host",
    )
    _remember_creation(root, child, caps, reps)
    return {
        "state_dir": str(root),
        "project": project,
        "child": child,
        "delegation": want,
        "custody": sorted(custody),
        "transfers": moved,
    }


def j1_task(task_id: str) -> dict:
    """Fresh J1 work task (toy sched shape, own task_id namespace)."""
    task = copy.deepcopy(FI.S1)
    task["task_id"] = task_id
    return task


def j1_plan(
    host, task: dict, world: str, verifier: str | None = None
) -> tuple[list[dict], LaneCtx, dict]:
    """Single-world work plan: formulate -> propose -> cross-verify.

    No clarification dialogue (the nested world inherits the project's
    clarified state), so no lane bytes are claimed — validity +
    byte-identity + custody/delegation evidence only. The verifier
    defaults to the working world; pass the project for a cross-world
    check.
    """
    from .resume import require_active

    verifier = verifier or world
    require_active(host, world)
    require_active(host, verifier)
    ctx = LaneCtx("central", Coordinator(), None)
    plan = [
        build_formulate(host, task, world, "v1", ctx),
        build_propose(
            host, task, world, "merged reqs + clarified prefs (O2; J1 plan)", ctx
        ),
        build_verify(host, task, verifier, ctx, world, "propose"),
    ]
    return plan, ctx, task


def j1_work_op(
    state_dir: str | Path,
    world: str,
    task_id: str = "J1-T1",
    verifier: str | None = None,
    prekill: set | None = None,
) -> dict:
    """Run one J1 work task through `world` (resume-by-skip included).

    Writes the per-task verdict + `artifacts/solution-<id>.json` and
    exports terminal commitments (O5). When `prekill` (a
    scan_succeeded set taken before a kill) is passed,
    `re_executed_invokes` MUST be 0 — asserted by the caller.
    """
    from .resume import execute_plan as _execute

    root = Path(state_dir)
    host, _ = open_run(root)
    task = j1_task(task_id)
    plan, ctx, _ = j1_plan(host, task, world, verifier)
    rep = _execute(host, plan, prekill=prekill)
    vpath = (
        Path(host.worlds[verifier or world].instance_state_dir)
        / "verdicts"
        / f"verdict-{task_id}.json"
    )
    verdict = json.loads(vpath.read_text(encoding="utf-8"))
    export_commitments(
        host, ctx, task_id, sorted({world, verifier or world}), verdict["assignment"]
    )
    sol_ref = write_json(
        root / "artifacts" / f"solution-{task_id}.json",
        {
            "task_id": task_id,
            "assignment": verdict["assignment"],
            "quality": verdict["quality"],
            "prefs_total": verdict["prefs_total"],
            "valid": verdict["phase_verdict"],
            "via": world,
        },
    )
    return {
        "task_id": task_id,
        "world": world,
        "verifier": verifier or world,
        "valid": verdict["phase_verdict"],
        "quality": verdict["quality"],
        "prefs_total": verdict["prefs_total"],
        "solution_ref": sol_ref,
        "skipped": rep["skipped"],
        "executed": rep["executed"],
        "re_executed_invokes": rep["re_executed_invokes"],
    }


def j1_kill_resume_op(
    state_dir: str | Path,
    world: str,
    task_id: str = "J1-T1",
    verifier: str | None = None,
    timeout_s: int = 180,
) -> dict:
    """Real kill-resume drill on a J1 work task.

    Spawns the j1_demo child (formulate step, then READY + sleep),
    snapshots the pre-kill artifact bytes + ledger prefix, kills it
    with Popen.kill(), reopens, and finishes the task. Asserts:
    child was really killed (rc != 0), re_executed_invokes == 0, every
    pre-kill artifact byte-identical, the ledger prefix intact.
    """
    from .resume import execute_plan as _execute
    from .resume import scan_succeeded as _scan

    root = Path(state_dir).resolve()
    host, _ = open_run(root)
    for wid in {world, verifier or world}:
        if host.worlds[wid].lifecycle != "active":
            raise RuntimeError(
                f"j1_kill_resume_op needs active {wid} "
                f"(is {host.worlds[wid].lifecycle})"
            )
    del host
    child = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "anima_substrate.demos.j1_demo",
            "--child-partial",
            str(root),
            world,
            task_id,
        ],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    t0 = time.time()
    while not (root / "child.READY").exists():
        if time.time() - t0 > timeout_s:
            child.kill()
            raise RuntimeError("j1_kill_resume_op: child never READY")
        if child.poll() is not None:
            raise RuntimeError(
                f"j1_kill_resume_op: child died early rc={child.returncode}"
            )
        time.sleep(0.2)
    ready = json.loads((root / "child.READY").read_text(encoding="utf-8"))
    prekill_hashes = dict(ready["artifact_hashes"])
    ledger_prefix = (root / "ledger.jsonl").read_bytes().splitlines()
    child.kill()
    out, err = child.communicate(timeout=60)
    if child.returncode == 0:
        raise RuntimeError("j1_kill_resume_op: child exited, not killed")
    host, _ = open_run(root)
    post_prefix = (root / "ledger.jsonl").read_bytes().splitlines()
    # The reopen appends exactly one host_reopen line; every pre-kill
    # line must be intact ahead of it.
    assert post_prefix[: len(ledger_prefix)] == ledger_prefix, (
        "ledger prefix changed across the kill boundary"
    )
    prekill = _scan(host)
    task = j1_task(task_id)
    plan, ctx, _ = j1_plan(host, task, world, verifier)
    rep = _execute(host, plan, prekill=prekill)
    assert rep["re_executed_invokes"] == 0, rep
    import hashlib

    post_hashes = {}
    for rel in prekill_hashes:
        post_hashes[rel] = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    assert post_hashes == prekill_hashes, (
        f"pre-kill artifacts changed: {post_hashes} vs {prekill_hashes}"
    )
    (root / "child.READY").unlink(missing_ok=True)
    vpath = (
        Path(host.worlds[verifier or world].instance_state_dir)
        / "verdicts"
        / f"verdict-{task_id}.json"
    )
    verdict = json.loads(vpath.read_text(encoding="utf-8"))
    export_commitments(
        host, ctx, task_id, sorted({world, verifier or world}), verdict["assignment"]
    )
    sol_ref = write_json(
        root / "artifacts" / f"solution-{task_id}.json",
        {
            "task_id": task_id,
            "assignment": verdict["assignment"],
            "quality": verdict["quality"],
            "prefs_total": verdict["prefs_total"],
            "valid": verdict["phase_verdict"],
            "via": world,
        },
    )
    return {
        "child_rc": child.returncode,
        "task_id": task_id,
        "world": world,
        "valid": verdict["phase_verdict"],
        "quality": verdict["quality"],
        "prefs_total": verdict["prefs_total"],
        "solution_ref": sol_ref,
        "skipped": rep["skipped"],
        "executed": rep["executed"],
        "re_executed_invokes": rep["re_executed_invokes"],
        "prekill_artifacts": sorted(prekill_hashes),
        "ledger_prefix_lines": len(ledger_prefix),
        "child_stderr_tail": err.decode()[-300:],
    }


def j1_status_op(state_dir: str | Path) -> dict:
    """Read-only J1 summary: responsibilities + evidence per world."""
    root = Path(state_dir)
    host, _ = open_run(root)
    pending: dict[str, list] = {}
    for e in host.ledger_entries():
        if e.get("kind") == "checkpoint":
            pending[e["payload"].get("world_id", "")] = list(
                e["payload"].get("pending_effects", [])
            )
    worlds = {}
    for wid, rec in sorted(host.worlds.items()):
        vdir = Path(rec.instance_state_dir) / "verdicts"
        worlds[wid] = {
            "lifecycle": rec.lifecycle,
            "custody": sorted(rec.custodians),
            "holdings": dict(host.holdings.get(wid, {})),
            "consumed": dict(host.consumed.get(wid, {})),
            "capabilities": sorted(c.name + "@" + c.version for c in rec.capabilities),
            "authorities": sorted(rec.authorities),
            "lineage": [
                dict(entry) if isinstance(entry, dict) else list(entry)
                for entry in rec.lineage
            ],
            "pending_effects": pending.get(wid, []),
            "verdicts": sorted(p.name for p in vdir.glob("verdict-*.json"))
            if vdir.exists()
            else [],
        }
    delegations = [
        {
            "seq": e.get("seq"),
            "from": e["payload"].get("from"),
            "to": e["payload"].get("to"),
            "limits": e["payload"].get("limits"),
            "grant_id": e["payload"].get("grant_id"),
        }
        for e in host.ledger_entries()
        if e.get("kind") == "grant"
    ]
    nests = [e["payload"] for e in host.ledger_entries() if e.get("kind") == "nest"]
    fusions = [e["payload"] for e in host.ledger_entries() if e.get("kind") == "fusion"]
    solutions = (
        sorted(
            str(p.relative_to(root))
            for p in (root / "artifacts").glob("solution-*.json")
        )
        if (root / "artifacts").exists()
        else []
    )
    try:
        conservation = host.verify_conservation()
    except Exception as exc:  # read-only probe: report, don't raise
        conservation = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "state_dir": str(root),
        "worlds": worlds,
        "delegations": delegations,
        "nests": nests,
        "fusions": fusions,
        "solutions": solutions,
        "conservation": conservation,
    }


def j1_export_op(state_dir: str | Path, composite: str) -> dict:
    """Export a fused composite as a verifiable evidence bundle.

    Writes `artifacts/j1-export-<composite>.json`: the ledger fusion
    entry + the composite's derived_from lineage + every solution the
    composite produced, each with a sha256 over the artifact bytes.
    Re-reads every referenced file (loud FileNotFoundError when the
    export would dangle) and re-resolves the lineage against the
    ledger — an export that does not verify is not written.
    """
    import hashlib

    root = Path(state_dir)
    host, _ = open_run(root)
    if composite not in host.worlds:
        raise RuntimeError(f"j1_export refused: unknown {composite!r}")
    fusions = [
        e
        for e in host.ledger_entries()
        if e.get("kind") == "fusion"
        and e.get("payload", {}).get("fused_id") == composite
    ]
    if not fusions:
        raise RuntimeError(f"j1_export refused: no ledger fusion entry for {composite}")
    rec = host.worlds[composite]
    derived = [
        entry["world"]
        for entry in rec.lineage
        if isinstance(entry, dict) and entry.get("rel") == "derived_from"
    ]
    created = {
        e["payload"]["world_id"]
        for e in host.ledger_entries()
        if e.get("kind") == "create"
    }
    if len(derived) < 2 or not all(d in created for d in derived):
        raise RuntimeError(f"j1_export refused: lineage unresolvable: {derived}")
    sols = []
    for p in sorted((root / "artifacts").glob("solution-*.json")):
        body = json.loads(p.read_text(encoding="utf-8"))
        if body.get("via") != composite:
            continue
        sols.append(
            {
                "artifact": str(p.relative_to(root)),
                "task_id": body.get("task_id"),
                "valid": body.get("valid"),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "composite": composite,
        "fusion": fusions[-1]["payload"],
        "derived_from": derived,
        "solutions": sols,
    }
    # Verify-before-write: every referenced file re-read + re-hashed.
    for s in sols:
        digest = hashlib.sha256((root / s["artifact"]).read_bytes()).hexdigest()
        assert digest == s["sha256"], s
    ref = write_json(root / "artifacts" / f"j1-export-{composite}.json", manifest)
    return {
        "composite": composite,
        "derived_from": derived,
        "solutions": [s["task_id"] for s in sols],
        "export_ref": ref,
    }


# ------------------------------------------------------------- read


def explain_route_op(
    task_name: str | None = None, task_json: str | Path | None = None
) -> dict:
    """Apply the routing rule to a named task (S1/S2/S3) or a JSON file."""
    if task_json is not None:
        task = json.loads(Path(task_json).read_text(encoding="utf-8"))
    elif task_name in ("S1", "S2"):
        task = copy.deepcopy(LANE_TASKS[task_name])
    elif task_name == "S3":
        task = {**copy.deepcopy(FI.S3), "task_id": "S3"}
    elif task_name in ("S4-followup", "S4"):
        return {
            "task_id": "S4-followup",
            "lane": "fused-reuse",
            "rule": "post-fusion composite reuse",
            "reason": "follow-ups run through the fused composite, "
            "not through the routing rule",
        }
    elif task_name in ("S6-followup", "S6"):
        return {
            "task_id": "S6-followup",
            "lane": "fission-reuse",
            "rule": "post-fission split-pair reuse",
            "reason": "follow-ups run through the fission children, "
            "not through the routing rule",
        }
    else:
        raise ValueError(
            "explain_route_op needs task_name in "
            "S1/S2/S3/S4-followup/S6-followup or task_json"
        )
    return route(task)


def relate_op(
    state_dir: str | Path,
    rel_id: str,
    version: str,
    participants: list[str],
    purpose: str,
    actor: str = "host",
) -> dict:
    """Declare a relationship version (M3 org-state surface).

    Ledger-recorded (full evidence payload) and restored on every
    reopen by ledger replay — byte-verified by `org_snapshot_op`
    before/after comparisons. Re-declaring a version refuses;
    unknown participants refuse; both name the defect.
    """
    root = Path(state_dir)
    host, _ = open_run(root)
    return host.declare_relationship(
        rel_id, version, list(participants), purpose, actor
    )


def org_snapshot_op(state_dir: str | Path) -> dict:
    """Read-only org-state inventory: channels + relationships + custody.

    Deterministic (no timestamps): the same org state produces
    byte-identical canonical JSON across close/reopen. Relationships
    and custody persist via ledger replay; channels via
    `channels.json` (M3).
    """
    root = Path(state_dir)
    host, chans = open_run(root)
    return {
        "state_dir": str(root),
        "channels": chans.inventory(),
        "relationships": {
            rel_id: {ver: dict(payload) for ver, payload in sorted(versions.items())}
            for rel_id, versions in sorted(host.relationships.items())
        },
        "custody": {
            wid: sorted(rec.custodians) for wid, rec in sorted(host.worlds.items())
        },
        "lifecycle": {wid: rec.lifecycle for wid, rec in sorted(host.worlds.items())},
    }


def org_snapshot_bytes(state_dir: str | Path) -> bytes:
    """Canonical bytes of `org_snapshot_op` (byte-verify comparisons)."""
    snap = org_snapshot_op(state_dir)
    snap = dict(snap)
    snap["state_dir"] = "<root>"  # root path is not org state
    return (json.dumps(snap, indent=2, sort_keys=True) + "\n").encode("utf-8")


# ------------------------------------------------- portable composites (M3)


EXPORT_FORMAT = "anima-substrate-export/v1"


def _excerpt_for(host, composite: str) -> list[dict]:
    """Ledger entries evidencing the composite (explicit kinds only).

    Execution history (`invoke`/`consume`) is deliberately EXCLUDED:
    args/result refs are host-local paths and do not survive the
    move. What travels is the executable content (caps, staged
    procedures, pins) plus lineage evidence — never replay history.
    """
    out = []
    for e in host.ledger_entries():
        kind, p = e.get("kind"), e.get("payload", {})
        keep = (
            (kind == "create" and p.get("world_id") == composite)
            or (kind == "grant" and p.get("to") == composite)
            or (kind == "lifecycle" and p.get("world_id") == composite)
            or (kind == "fusion" and p.get("fused_id") == composite)
            or (kind == "fission" and p.get("composite") == composite)
            or (kind == "nest" and composite in (p.get("child"), p.get("project")))
            or (kind == "transfer" and composite in (p.get("from"), p.get("to")))
            or (kind == "checkpoint" and p.get("world_id") == composite)
            or (
                kind in ("quarantine", "quarantine_rollback")
                and p.get("world_id") == composite
            )
            or (kind == "j1_project" and p.get("project") == composite)
            or (kind == "import" and p.get("world_id") == composite)
            or (kind == "relationship" and composite in (p.get("participants") or []))
        )
        if keep:
            out.append(e)
    return out


def export_composite_op(
    state_dir: str | Path, composite: str, out_dir: str | Path
) -> dict:
    """Export a world as a PORTABLE EXECUTABLE composite bundle (M3).

    Writes `<out_dir>/` fresh: `EXPORT.json` (identity + pins, LAST —
    its presence means the export completed), `files/` (the world's
    state subtree), `ledger-excerpt.jsonl` (lineage evidence, explicit
    kinds — execution history excluded, see `_excerpt_for`).
    Verify-before-write: every copied file is re-read + re-hashed
    against its pin before EXPORT.json lands. A killed export leaves
    an unverifiable dir that import refuses.
    """
    root = Path(state_dir)
    host, _ = open_run(root)
    if composite not in host.worlds:
        raise RuntimeError(f"export refused: unknown world {composite!r}")
    bundle = Path(out_dir)
    if bundle.exists():
        raise RuntimeError(
            f"export refused: {bundle} already exists (export writes "
            f"fresh bundles only; remove it or pick another dir)"
        )
    rec = host.worlds[composite]
    srcdir = Path(rec.instance_state_dir)
    files_dir = bundle / "files"
    files_dir.mkdir(parents=True)
    pins: dict[str, str] = {}
    for path in sorted(srcdir.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(srcdir).as_posix()
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(
                f"export refused: world file is not a regular file: {rel}"
            )
        dest = files_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        pins[rel] = hashlib.sha256(dest.read_bytes()).hexdigest()
    excerpt = _excerpt_for(host, composite)
    atomic_write_text(
        bundle / "ledger-excerpt.jsonl",
        "".join(json.dumps(e, sort_keys=True) + "\n" for e in excerpt),
    )
    manifest = {
        "format": EXPORT_FORMAT,
        "composite": composite,
        "release": RELEASE,
        "code_ref": rec.code_ref,
        "caps": [c.name + "@" + c.version for c in rec.capabilities],
        "reps": [r.name + "@" + r.version for r in rec.representations],
        "procedures": [dict(t) for t in (rec.procedures or [])],
        "custodians": sorted(rec.custodians),
        "authorities": sorted(rec.authorities),
        "lineage": copy.deepcopy(rec.lineage),
        "lifecycle": rec.lifecycle,
        "files": {k: pins[k] for k in sorted(pins)},
        "excerpt_entries": len(excerpt),
    }
    # Verify-before-write: re-read + re-hash every copied file.
    for rel, digest in manifest["files"].items():
        live = hashlib.sha256((files_dir / rel).read_bytes()).hexdigest()
        assert live == digest, rel
    atomic_write_text(
        bundle / "EXPORT.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    bundle_sha = hashlib.sha256((bundle / "EXPORT.json").read_bytes()).hexdigest()
    return {
        "bundle": str(bundle),
        "composite": composite,
        "files": len(pins),
        "excerpt_entries": len(excerpt),
        "bundle_sha256": bundle_sha,
    }


def import_composite_op(
    state_dir: str | Path,
    bundle_dir: str | Path,
    world_id: str,
    grants: dict,
    reason: str,
) -> dict:
    """Consume an exported composite UNMODIFIED in a FRESH state dir (M3).

    The bundle is read-only input (never written); the new root must
    be fresh (no ledger). Funding is explicit: `grants` (all three
    keys, non-negative) funds the host root exactly, and the world is
    granted exactly that. Procedure tables are re-verified against
    staged bytes (pins must reproduce) with manifest refs rewritten
    to the new root. A ledger `import` entry records provenance; the
    original derived_from lineage is preserved verbatim.
    """
    root = Path(state_dir)
    if (root / "ledger.jsonl").exists():
        raise RuntimeError(
            f"import refused: {root} is not fresh (ledger.jsonl "
            f"exists); import consumes into a FRESH separate state dir"
        )
    bundle = Path(bundle_dir)
    try:
        manifest = json.loads((bundle / "EXPORT.json").read_text(encoding="utf-8"))
    except OSError:
        raise RuntimeError(
            f"import refused: {bundle} has no EXPORT.json (not a "
            f"complete export — a killed export leaves an unverifiable "
            f"dir; re-export)"
        )
    except ValueError as exc:
        raise RuntimeError(f"import refused: {bundle}/EXPORT.json unparseable ({exc})")
    if manifest.get("format") != EXPORT_FORMAT:
        raise RuntimeError(
            f"import refused: export format {manifest.get('format')!r} "
            f"!= {EXPORT_FORMAT!r}"
        )
    for key in ("caps", "reps", "procedures", "files", "lineage"):
        if key not in manifest:
            raise RuntimeError(
                f"import refused: EXPORT.json misses {key!r} "
                f"(incomplete export; re-export)"
            )
    files_dir = bundle / "files"
    for rel, digest in manifest["files"].items():
        target = files_dir / rel
        if not target.is_file() or target.is_symlink():
            raise RuntimeError(
                f"import refused: bundle file missing/not-regular: {rel} (re-export)"
            )
        live = hashlib.sha256(target.read_bytes()).hexdigest()
        if live != digest:
            raise RuntimeError(
                f"import refused: bundle file changed since export: "
                f"{rel} (re-export; bundles are read-only inputs)"
            )
    excerpt_path = bundle / "ledger-excerpt.jsonl"
    if excerpt_path.exists():
        try:
            excerpt = [
                json.loads(line)
                for line in excerpt_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except ValueError as exc:
            raise RuntimeError(
                f"import refused: ledger-excerpt.jsonl unparseable ({exc})"
            )
        if len(excerpt) != manifest.get("excerpt_entries"):
            raise RuntimeError(
                f"import refused: excerpt has {len(excerpt)} entries, "
                f"EXPORT.json pins {manifest.get('excerpt_entries')}"
            )
    need = ("max_cost_usd", "max_time_s", "max_invocations")
    if not isinstance(grants, dict) or [k for k in need if k not in grants]:
        missing = [k for k in need if k not in (grants or {})]
        raise ValueError(
            f"import refused: grants must name all of {list(need)} "
            f"(missing {missing}); fund the import explicitly"
        )
    norm = {}
    for key in need:
        try:
            norm[key] = float(grants[key])
        except (TypeError, ValueError):
            raise ValueError(
                f"import refused: grant {key}={grants[key]!r} is not a number"
            )
        if norm[key] < 0:
            raise ValueError(f"import refused: grant {key} is negative ({norm[key]})")
    if not world_id or not isinstance(world_id, str):
        raise ValueError("import refused: world_id must be a non-empty string")
    # ---- execute (all validation passed)
    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)
    host = MiniHost(root / "state", root / "ledger.jsonl", root_holdings=dict(norm))
    _write_specs(root, [])
    config = {
        "release": RELEASE,
        "created_utc": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "worlds": [],
        "tasks_run": [],
        "imported_from": manifest["composite"],
    }
    atomic_write_text(
        root / "CONFIG.json", json.dumps(config, indent=2, sort_keys=True) + "\n"
    )
    caps = []
    for item in manifest["caps"]:
        name, _, version = item.partition("@")
        caps.append((name, version))
    reps = []
    for item in manifest["reps"]:
        name, _, version = item.partition("@")
        reps.append((name, version))
    procedures = [dict(t) for t in manifest["procedures"]]
    lineage = copy.deepcopy(manifest["lineage"])
    bundle_sha = hashlib.sha256((bundle / "EXPORT.json").read_bytes()).hexdigest()
    lineage.append(
        {
            "rel": "imported_from",
            "composite": manifest["composite"],
            "bundle_sha256": bundle_sha,
            "reason": reason,
        }
    )
    rec = world_record(
        root / "state",
        world_id,
        caps,
        reps,
        custodians={sc: world_id for sc in manifest.get("custodians", [])},
        authorities=list(manifest.get("authorities", [])),
        lineage=lineage,
        procedures=procedures,
    )
    # Manifest refs point at the OLD root: rewrite to the new stage.
    # (The bundle itself is untouched — only the new specs differ.)
    staged_procs = []
    for table in rec.procedures:
        staged_procs.append(dict(table))
    wdir = Path(rec.instance_state_dir)
    wdir.mkdir(parents=True, exist_ok=True)
    for rel in manifest["files"]:
        dest = wdir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(files_dir / rel, dest)
    for table in staged_procs:
        name = table.get("name", "")
        new_ref = str(wdir / "procedures" / name / PROC.MANIFEST_NAME)
        if not Path(new_ref).is_file():
            raise RuntimeError(
                f"import refused: staged bundle for procedure {name!r} "
                f"missing {new_ref} (incomplete export; re-export)"
            )
        staged = PROC.verify_bundle(str(Path(new_ref).parent))
        live_sha = PROC.sha256_bytes(PROC.canonical_manifest_bytes(staged))
        if live_sha != table.get("bundle_sha256"):
            raise RuntimeError(
                f"import refused: procedure {name!r} pins "
                f"{table.get('bundle_sha256')} but staged bytes hash "
                f"{live_sha} (re-export)"
            )
        table["manifest_ref"] = new_ref
    rec.procedures = staged_procs
    host.create_world(rec, "host", grant_limits=dict(norm))
    host.transition(world_id, "active", "host", reason=f"import: {reason}")
    host.append(
        "import",
        {
            "world_id": world_id,
            "composite": manifest["composite"],
            "bundle_sha256": bundle_sha,
            "grants": norm,
            "procedures_verified": [t.get("name") for t in staged_procs],
            "reason": reason,
        },
        actor="host",
    )
    _remember_creation(root, world_id, caps, reps, procedures=staged_procs)
    derived = [
        e["world"]
        for e in lineage
        if isinstance(e, dict) and e.get("rel") == "derived_from"
    ]
    orig_derived = [
        e["world"]
        for e in manifest["lineage"]
        if isinstance(e, dict) and e.get("rel") == "derived_from"
    ]
    return {
        "state_dir": str(root),
        "world_id": world_id,
        "bundle_sha256": bundle_sha,
        "grants": norm,
        "procedures_verified": [t.get("name") for t in staged_procs],
        "derived_from": derived,
        "lineage_ok": derived == orig_derived,
    }


def recipe_propose_op(
    state_dir: str | Path,
    name: str,
    family: str,
    family_version: str,
    manifest_path: str | Path,
    prereg_entry_path: str | Path,
    reason: str,
) -> dict:
    """Propose a recipe bound to a filed prereg entry (M4)."""
    return RECIPES.propose(
        state_dir,
        name,
        family,
        family_version,
        manifest_path,
        prereg_entry_path,
        reason,
    )


def recipe_assess_op(
    state_dir: str | Path,
    name: str,
    tree_root: str | Path,
    task_id: str,
    budget_s: float = 60.0,
) -> dict:
    """Assess a proposed recipe on real files (M4 predicates P0–P3)."""
    return RECIPES.assess(state_dir, name, tree_root, task_id, budget_s)


def recipe_retain_op(
    state_dir: str | Path,
    name: str,
    assessment_id: str,
    decision: str,
    reason: str,
) -> dict:
    """Retain an assessed recipe with lineage + measured cost (M4)."""
    return RECIPES.retain(state_dir, name, assessment_id, decision, reason)


def recipe_reuse_op(
    state_dir: str | Path,
    name: str,
    world_id: str,
    tree_root: str | Path,
    manifest_path: str | Path,
    task_id: str,
) -> dict:
    """Reuse a retained recipe on a new task (M4)."""
    return RECIPES.reuse(state_dir, name, world_id, tree_root, manifest_path, task_id)


def recipe_baseline_op(
    tree_root: str | Path, work_dir: str | Path, task_id: str
) -> dict:
    """From-scratch direct check with counted interventions (M4)."""
    return RECIPES.baseline(tree_root, work_dir, task_id)


def recipe_compare_op(
    state_dir: str | Path,
    name: str,
    reuse_id: str,
    baseline_report: dict,
    prereg_entry_path: str | Path,
) -> dict:
    """Report reuse-vs-baseline with no comparative claims (M4)."""
    return RECIPES.compare(
        state_dir, name, reuse_id, baseline_report, prereg_entry_path
    )


def inspect_state_op(state_dir: str | Path) -> dict:
    """Read-only summary: worlds, ledger kinds, routing, conservation."""
    root = Path(state_dir)
    host, _ = open_run(root)
    worlds = {
        wid: {
            "lifecycle": rec.lifecycle,
            "custodians": dict(rec.custodians),
            "capabilities": sorted(c.name + "@" + c.version for c in rec.capabilities),
        }
        for wid, rec in sorted(host.worlds.items())
    }
    kinds: dict[str, int] = {}
    for e in host.ledger_entries():
        kinds[e.get("kind", "?")] = kinds.get(e.get("kind", "?"), 0) + 1
    routing = [
        e["payload"] for e in host.ledger_entries() if e.get("kind") == "routing"
    ]
    try:
        conservation = host.verify_conservation()
    except Exception as exc:  # read-only probe: report, don't raise
        conservation = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "state_dir": str(root),
        "worlds": worlds,
        "ledger_entries": sum(kinds.values()),
        "kinds": kinds,
        "routing": routing,
        "conservation": conservation,
    }
