# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-004 structural integration: REAL fusion + fission + quarantine.

Successor-003 (R1): fuse/fission pre-validate settleability of every
world they will dissolve BEFORE any host mutation (no partial effects
on rejection, extending the fission docstring promise to both ops);
kill-during-fusion/fission is a defined interruption boundary with
idempotent completion via recover.complete_fusion/complete_fission
(see docs/RECOVERY.md). Clean-path ledger bytes unchanged.

Fusion merges two cooperating worlds into one composite:
- recorded lineage (derived_from both parents, resolvable in-ledger),
- ownership transfer (every state class moves giver -> composite),
- lifecycle moves (parents settle-then-dissolve; composite activates),
- AND removal of a now-redundant mechanism: the direct channel between
  the fused pair (intra-composite coordination is internal afterwards).
A before/after mechanism inventory makes the removal checkable.

Fission splits a fused composite back into two worlds (reverse of
fusion with a partition record): custody back-transfer per the
partition, composite settle-then-dissolve, children activate, lineage
entries naming the fusion being split, and the direct channel between
the children restored (cross-boundary coordination is explicit again).

Quarantine stays the failure-driven separation path: a failed
participant is suspended with commitment transfer to a standby.
See SEPARATION-PATHS.md for when each path applies.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..participants.sched import sched_checker as checker
from ..participants.sched import sched_domain as domain
from .minihost import MiniHost, atomic_write_text
from .resume import SchedWorld
from .routing import GRANT_LIMITS, ChannelRegistry, write_json


def mechanism_inventory(host: MiniHost, chans: ChannelRegistry) -> dict:
    worlds = {
        wid: {
            "lifecycle": rec.lifecycle,
            "custodians": dict(rec.custodians),
            "capabilities": sorted(c.name + "@" + c.version for c in rec.capabilities),
        }
        for wid, rec in sorted(host.worlds.items())
    }
    mechanisms = [
        "ledger",
        "grants+settle",
        "invoke+deny",
        "checkpoint+suspend/reattach",
        "reopen-by-replay",
    ]
    mechanisms += [f"direct-channel:{k}" for k in sorted(chans.channels)]
    mechanisms += ["coordinator:central", "coordinator:local-exports-only"]
    return {
        "worlds": worlds,
        "channels": chans.inventory(),
        "mechanisms": sorted(mechanisms),
    }


def fuse_worlds(
    host: MiniHost,
    chans: ChannelRegistry,
    a: str,
    b: str,
    fused_id: str,
    fused_record,
    actor: str,
    reason: str,
) -> dict:
    """Fuse worlds a+b into one composite. Returns the fusion record."""
    from .resume import require_active

    require_active(host, a)
    require_active(host, b)
    # R1: settleability is a precondition, checked before ANY mutation
    # (refusal = ContractViolation, zero partial effects).
    host.check_settleable(a)
    host.check_settleable(b)
    before = mechanism_inventory(host, chans)
    # 1. composite birth with recorded lineage
    fused_record.lineage = [
        {"rel": "derived_from", "world": a},
        {"rel": "derived_from", "world": b},
        {"rel": "fusion", "actor": actor, "reason": reason},
    ]
    host.create_world(fused_record, "host", grant_limits=dict(GRANT_LIMITS))
    host.transition(fused_id, "active", "host", reason="fusion birth")
    # 2. ownership transfer, every state class, giver -> composite (O4:
    # transfer actor = giver)
    transfers = []
    for giver in (a, b):
        for sc in sorted(host.worlds[giver].custodians):
            host.transfer_custody(
                sc,
                giver,
                fused_id,
                actor=giver,
                reason=f"fusion into {fused_id}",
                continuity="sha256-of-composite",
            )
            transfers.append({"state_class": sc, "from": giver, "to": fused_id})
    # 3. lifecycle moves: parents settle-then-dissolve
    host.transition(a, "dissolved", actor, reason=f"fused into {fused_id}")
    host.transition(b, "dissolved", actor, reason=f"fused into {fused_id}")
    # 4. remove the now-redundant mechanism: the direct channel between
    # the fused pair (nothing left on either end to talk through it)
    removed_chan = chans.remove(a, b)
    after = mechanism_inventory(host, chans)
    assert ChannelRegistry.key(a, b) not in after["channels"]
    assert f"direct-channel:{ChannelRegistry.key(a, b)}" not in after["mechanisms"]
    record = {
        "fused_id": fused_id,
        "parents": [a, b],
        "lineage": list(fused_record.lineage),
        "transfers": transfers,
        "removed_mechanism": f"direct-channel:{removed_chan.name}",
        "removed_channel_bytes": removed_chan.direct_bytes,
        "removed_channel_messages": removed_chan.n,
        "before": before,
        "after": after,
    }
    host.append(
        "fusion",
        {
            "fused_id": fused_id,
            "parents": [a, b],
            "transfers": transfers,
            "removed_mechanism": record["removed_mechanism"],
            "reason": reason,
        },
        actor=actor,
    )
    return record


def reuse_composite(root: Path, host: MiniHost, fused_id: str, followup: dict) -> dict:
    """Reuse the fused composite on a follow-up task elsewhere, with a
    lineage check (derived_from present + resolvable in-ledger)."""
    from .resume import require_active

    require_active(host, fused_id)
    tid = followup["task_id"]
    rec = host.worlds[fused_id]
    # lineage check: derived_from entries resolve to ledger creates
    derived = [
        entry["world"]
        for entry in rec.lineage
        if isinstance(entry, dict) and entry.get("rel") == "derived_from"
    ]
    assert len(derived) >= 2, f"composite lineage incomplete: {rec.lineage}"
    created = {
        e["payload"]["world_id"]
        for e in host.ledger_entries()
        if e.get("kind") == "create"
    }
    assert all(d in created for d in derived), (
        f"lineage unresolvable: {derived} vs {sorted(created)}"
    )
    fused = [
        e
        for e in host.ledger_entries()
        if e.get("kind") == "fusion"
        and e.get("payload", {}).get("fused_id") == fused_id
    ]
    assert fused, "no ledger fusion entry for composite"
    # follow-up work through the composite's own capabilities
    world = SchedWorld(rec.instance_state_dir)
    ldoc = domain.list_doc(followup)
    sdoc, loss = domain.translate_list2slot(
        ldoc, followup.get("adapter", "list2slot/v1")
    )
    form_ref = world.write_formulation(
        f"{tid}-formulation-v1", tid, "sched/v1", ldoc, sdoc, loss
    )
    args = host.store_args(
        fused_id,
        f"{tid}-reuse",
        {
            "formulation_ref": form_ref,
            "candidate_refs": [],
            "task_id": tid,
            "step": "reuse",
            "lane": "fused",
        },
    )
    assign = domain.solve(followup)

    def _reuse() -> str:
        return world.write_proposal(
            f"{tid}-reuse",
            tid,
            assign,
            "revision none; fused composite re-solve (O2: clarified prefs inherited)",
        )

    entry = host.invoke(
        fused_id, fused_id, "sched.reuse", "1.0", args, _reuse, cost_usd=0.0, time_s=1.0
    )
    body = json.loads(Path(entry["payload"]["result_ref"]).read_text(encoding="utf-8"))
    assert "candidate_refs" in body and "champion_id" in body  # C3
    cand = json.loads(Path(body["candidate_refs"][0]).read_text(encoding="utf-8"))
    report = checker.check(cand["assignment"], followup)
    world.write_verdict(tid, cand["assignment"], report)
    task_ref = world.state_dir / "verdicts" / f"verdict-{tid}.json"
    atomic_write_text(
        task_ref,
        (world.state_dir / "verdicts" / "verdict.json").read_text(encoding="utf-8"),
    )
    sol_ref = write_json(
        root / "artifacts" / f"solution-{tid}.json",
        {
            "task_id": tid,
            "assignment": cand["assignment"],
            "quality": report["quality"],
            "prefs_total": report["prefs_total"],
            "valid": report["valid"],
            "via": fused_id,
        },
    )
    return {
        "task_id": tid,
        "via": fused_id,
        "valid": report["valid"],
        "quality": report["quality"],
        "prefs_total": report["prefs_total"],
        "lineage_ok": True,
        "derived_from": derived,
        "solution_ref": sol_ref,
    }


def fission_worlds(
    host: MiniHost,
    chans: ChannelRegistry,
    composite_id: str,
    left_id: str,
    right_id: str,
    left_record,
    right_record,
    partition: dict[str, str],
    actor: str,
    reason: str,
) -> dict:
    """Split a fused composite back into two worlds (reverse of fusion).

    partition maps EVERY state class the composite holds to exactly one
    of the two children. Returns the fission record. Preconditions
    (all loud, no partial effects — validation precedes any host
    mutation; ValueError for bad partition/input incl. active-but-
    non-fused targets, RuntimeError for inactive targets):
    - the composite is ACTIVE and is a RECORDED fusion (a ledger
      `fusion` entry names it as fused_id);
    - partition covers exactly the composite's custodian set, each
      class assigned to left_id or right_id, both sides non-empty.
    """
    from .resume import require_active

    require_active(host, composite_id)
    if left_id == right_id:
        raise ValueError(f"fission needs two distinct children, got {left_id!r} twice")
    # 0. validate BEFORE mutating: the fusion being split must be real
    fusions = [
        e
        for e in host.ledger_entries()
        if e.get("kind") == "fusion"
        and e.get("payload", {}).get("fused_id") == composite_id
    ]
    if not fusions:
        raise ValueError(
            f"{composite_id} is not a recorded fusion "
            f"composite: no ledger fusion entry names it"
        )
    fusion_entry = fusions[-1]["payload"]
    fusion_parents = list(fusion_entry.get("parents", []))
    held = set(host.worlds[composite_id].custodians)
    pkeys = set(partition)
    if pkeys != held:
        raise ValueError(
            f"fission partition must cover exactly the composite's "
            f"state classes {sorted(held)}: missing "
            f"{sorted(held - pkeys)}, unknown {sorted(pkeys - held)}"
        )
    sides = {left_id, right_id}
    bad = {sc: owner for sc, owner in partition.items() if owner not in sides}
    if bad:
        raise ValueError(
            f"fission partition assigns outside the two children {sorted(sides)}: {bad}"
        )
    if set(partition.values()) != sides:
        raise ValueError(
            f"fission must split custody across BOTH "
            f"children, got one-sided {partition}"
        )
    # R1: the composite must be settleable too (it will dissolve);
    # checked before ANY mutation, like every other precondition.
    host.check_settleable(composite_id)
    before = mechanism_inventory(host, chans)
    # 1. children birth with lineage NAMING the fusion being split
    left_classes = sorted(sc for sc, o in partition.items() if o == left_id)
    right_classes = sorted(sc for sc, o in partition.items() if o == right_id)
    left_record.lineage = [
        {"rel": "derived_from", "world": composite_id},
        {
            "rel": "fission-of",
            "fusion": composite_id,
            "fusion_parents": fusion_parents,
            "side": "left",
            "partition": left_classes,
        },
        {"rel": "fission", "actor": actor, "reason": reason},
    ]
    right_record.lineage = [
        {"rel": "derived_from", "world": composite_id},
        {
            "rel": "fission-of",
            "fusion": composite_id,
            "fusion_parents": fusion_parents,
            "side": "right",
            "partition": right_classes,
        },
        {"rel": "fission", "actor": actor, "reason": reason},
    ]
    host.create_world(left_record, "host", grant_limits=dict(GRANT_LIMITS))
    host.transition(left_id, "active", "host", reason="fission birth")
    host.create_world(right_record, "host", grant_limits=dict(GRANT_LIMITS))
    host.transition(right_id, "active", "host", reason="fission birth")
    # 2. custody back-transfer per the partition (O4: actor = giver)
    transfers = []
    for sc in sorted(partition):
        owner = partition[sc]
        host.transfer_custody(
            sc,
            composite_id,
            owner,
            actor=composite_id,
            reason=f"fission of {composite_id}: {reason}",
            continuity="fission-partition",
        )
        transfers.append({"state_class": sc, "from": composite_id, "to": owner})
    # 3. lifecycle move: composite settle-then-dissolves
    host.transition(
        composite_id, "dissolved", actor, reason=f"fissioned into {left_id}+{right_id}"
    )
    # 4. restore the cross-boundary mechanism: the direct channel between
    # the children (coordination across the split is explicit again)
    chan = chans.get(left_id, right_id)
    after = mechanism_inventory(host, chans)
    assert ChannelRegistry.key(left_id, right_id) in after["channels"]
    record = {
        "composite": composite_id,
        "children": [left_id, right_id],
        "partition": dict(partition),
        "fusion": {"fused_id": composite_id, "parents": fusion_parents},
        "lineage_left": list(left_record.lineage),
        "lineage_right": list(right_record.lineage),
        "transfers": transfers,
        "restored_mechanism": f"direct-channel:{ChannelRegistry.key(left_id, right_id)}",
        "restored_channel_bytes": chan.direct_bytes,
        "before": before,
        "after": after,
    }
    host.append(
        "fission",
        {
            "composite": composite_id,
            "children": [left_id, right_id],
            "partition": dict(partition),
            "fusion": record["fusion"],
            "transfers": transfers,
            "restored_mechanism": record["restored_mechanism"],
            "reason": reason,
        },
        actor=actor,
    )
    return record


def quarantine_world(
    host: MiniHost, world_id: str, standby_id: str, actor: str, reason: str
) -> dict:
    """Declared separation path: quarantine a failed participant.

    Suspends the world (pending_effects = its commitments) and transfers
    every commitment to the standby. Invokes against the quarantined
    world are denied by the host (not-active rule); the standby can
    complete the transferred commitments. Returns the quarantine record.
    """
    world = host.worlds[world_id]
    assert world.lifecycle == "active", f"{world_id} not active"
    commitments = sorted(world.custodians)
    host.suspend(
        world_id,
        actor,
        reason,
        pending_effects=[{"commitment": c, "to": standby_id} for c in commitments],
    )
    transfers = []
    for sc in commitments:
        host.transfer_custody(
            sc,
            world_id,
            standby_id,
            actor="host",
            reason=f"quarantine transfer: {reason}",
            continuity="commitment-handoff",
        )
        transfers.append({"state_class": sc, "from": world_id, "to": standby_id})
    host.append(
        "quarantine",
        {
            "world_id": world_id,
            "standby": standby_id,
            "commitments": commitments,
            "transfers": transfers,
            "reason": reason,
        },
        actor=actor,
    )
    return {
        "world_id": world_id,
        "standby": standby_id,
        "commitments": commitments,
        "transfers": transfers,
    }
