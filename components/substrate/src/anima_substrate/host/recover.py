# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-004 interruption recovery (R1 atomic settle + boundaries).

Read-only forensics over the ledger (ledger_index + detect_*) plus
idempotent completion of interrupted settle/fusion/fission through the
SAME host primitives the ops use (transfer/settle/append). Every
completion step is conditional on ledger state, so recovery is itself
crash-safe: a kill during recovery just leaves a smaller partial state,
and re-running recovery converges (proven by the repeated-kill tests).

Scope (see docs/CONSUMER.md §6 + docs/ARCHITECTURE.md §Limits):
  automated .... birth completion (proposed worlds), fusion completion,
                 fission completion (operator supplies the partition +
                 child names + presets), settle completion.
  supported .... partial quarantine-transfer: the complete-vs-rollback
                 DECISION stays with the operator, and both directions
                 are supported ops (complete_quarantine /
                 rollback_quarantine — the R11 owed repair is closed).
  detected only  torn ledger lines (disk-loss class), ledgers that fail
                 conservation (fail-closed refusal with operator steps).

Every completion validates EVERYTHING before mutating (the fission
pattern): a refusal leaves zero new partial effects.
"""

from __future__ import annotations

import json
from pathlib import Path

from .minihost import ContractViolation, MiniHost, atomic_write_text, maybe_crash_at
from .procedure import PROC_GRANT_LIMITS
from .routing import GRANT_LIMITS, ChannelRegistry, world_record

# ------------------------------------------------------------ forensics


def ledger_index(host: MiniHost) -> dict:
    """Single-pass read-only index of the ledger (no appends)."""
    idx = {
        "creates": {},
        "create_order": [],
        "grants_to": {},
        "transfers": [],
        "last_lifecycle": {},
        "markers": {},
        "fusions": {},
        "fission": {},
        "quarantines": {},
        "rollbacks": {},
        "checkpoints": {},
        "n_entries": 0,
    }
    for e in host.ledger_entries():
        idx["n_entries"] += 1
        kind, p = e.get("kind"), e.get("payload", {})
        if kind == "create":
            wid = p.get("world_id", "")
            if wid not in idx["creates"]:
                idx["creates"][wid] = dict(p)
                idx["create_order"].append(wid)
        elif kind == "grant":
            idx["grants_to"].setdefault(p.get("to", ""), []).append(dict(p))
        elif kind == "transfer":
            idx["transfers"].append(e)
        elif kind == "lifecycle":
            idx["last_lifecycle"][p.get("world_id", "")] = p.get("to", "")
        elif kind == "grant_settle":
            wid = p.get("world_id", "")
            idx["markers"][wid] = idx["markers"].get(wid, 0) + 1
        elif kind == "fusion":
            idx["fusions"][p.get("fused_id", "")] = {
                "seq": e.get("seq"),
                "payload": dict(p),
            }
        elif kind == "fission":
            idx["fission"][p.get("composite", "")] = {
                "seq": e.get("seq"),
                "payload": dict(p),
            }
        elif kind == "quarantine":
            idx["quarantines"][p.get("world_id", "")] = {
                "seq": e.get("seq"),
                "payload": dict(p),
            }
        elif kind == "quarantine_rollback":
            # successor-006 (R11 repair): rollback resolutions recorded
            # by rollback_quarantine; detection treats them as
            # resolutions exactly like `quarantine` entries.
            idx["rollbacks"][p.get("world_id", "")] = {
                "seq": e.get("seq"),
                "payload": dict(p),
            }
        elif kind == "checkpoint":
            idx["checkpoints"].setdefault(p.get("world_id", ""), []).append(
                {"seq": e.get("seq"), "payload": dict(p)}
            )
    return idx


def _fusion_parents_of(create_payload: dict) -> list[str]:
    return [
        entry["world"]
        for entry in create_payload.get("lineage", [])
        if isinstance(entry, dict) and entry.get("rel") == "derived_from"
    ]


def _has_rel(create_payload: dict, rel: str) -> bool:
    return any(
        isinstance(entry, dict) and entry.get("rel") == rel
        for entry in create_payload.get("lineage", [])
    )


def detect_partial_fusions(host: MiniHost, idx: dict) -> list[dict]:
    """Composites born by fusion with no ledger `fusion` entry."""
    out = []
    for wid in idx["create_order"]:
        payload = idx["creates"][wid]
        if not _has_rel(payload, "fusion"):
            continue
        if wid in idx["fusions"]:
            continue
        done = [
            e
            for e in idx["transfers"]
            if e.get("payload", {}).get("reason") == f"fusion into {wid}"
            and e.get("payload", {}).get("to") == wid
        ]
        out.append(
            {
                "composite": wid,
                "parents": _fusion_parents_of(payload),
                "transfers_done": len(done),
                "lifecycle": host.worlds[wid].lifecycle if wid in host.worlds else "?",
                "create_seq": None,
            }
        )
    return out


def detect_partial_fissions(host: MiniHost, idx: dict) -> list[dict]:
    """Composites with fission progress but no ledger `fission` entry."""
    out = []
    candidates: dict[str, dict] = {}
    for e in idx["transfers"]:
        reason = e.get("payload", {}).get("reason", "")
        if reason.startswith("fission of ") and ":" in reason:
            comp = reason[len("fission of ") : reason.index(":")]
            candidates.setdefault(comp, {"done": []})["done"].append(e)
    for wid in idx["create_order"]:
        payload = idx["creates"][wid]
        for entry in payload.get("lineage", []):
            if isinstance(entry, dict) and entry.get("rel") == "fission-of":
                comp = entry.get("fusion", "")
                if comp:
                    candidates.setdefault(comp, {"done": []})
    for comp, info in candidates.items():
        if comp in idx["fission"]:
            continue
        children = sorted(
            {
                c
                for c in idx["create_order"]
                if any(
                    isinstance(entry, dict)
                    and entry.get("rel") == "fission-of"
                    and entry.get("fusion") == comp
                    for entry in idx["creates"][c].get("lineage", [])
                )
            }
        )
        out.append(
            {
                "composite": comp,
                "children_created": children,
                "transfers_done": len(info["done"]),
                "lifecycle": host.worlds[comp].lifecycle
                if comp in host.worlds
                else "?",
            }
        )
    return out


def _quarantine_moved(idx: dict) -> dict[str, list]:
    """Quarantine-reason transfers grouped by source world (ledger order)."""
    moved: dict[str, list] = {}
    for e in idx["transfers"]:
        p = e.get("payload", {})
        if str(p.get("reason", "")).startswith("quarantine transfer"):
            moved.setdefault(p.get("from", ""), []).append(e)
    return moved


def _pending_from_ledger(idx: dict, wid: str) -> tuple[list, int]:
    """Latest ledger checkpoint pending_effects + its seq (0 when none)."""
    ckpts = idx["checkpoints"].get(wid, [])
    if not ckpts:
        return [], 0
    last = ckpts[-1]
    return list(last["payload"].get("pending_effects", [])), last["seq"] or 0


def pending_effects_for(host: MiniHost, idx: dict, wid: str) -> tuple[list, str]:
    """Pending handoffs for a suspended world + their source.

    The ledger `checkpoint` entry is authoritative; when the kill
    landed between the suspend `lifecycle` and `checkpoint` appends
    the ledger has no checkpoint entry, and the host-written side
    file `checkpoint.json` (written atomically BEFORE the lifecycle
    append, never hand-edited under the consumer contract) is the
    fallback. Returns ([], "none") when neither names pending work.
    """
    pend, _ = _pending_from_ledger(idx, wid)
    if pend:
        return pend, "ledger-checkpoint"
    if wid in host.worlds:
        ckpt_path = Path(host.worlds[wid].instance_state_dir) / "checkpoint.json"
        if ckpt_path.exists():
            try:
                body = json.loads(ckpt_path.read_text(encoding="utf-8"))
            except ValueError:
                body = {}
            if body.get("world_id") == wid and body.get("pending_effects"):
                return list(body["pending_effects"]), "side-file-checkpoint"
    return [], "none"


def _quarantine_resolution_seq(idx: dict, wid: str) -> int:
    """Newest `quarantine`/`quarantine_rollback` seq for wid (0 = none)."""
    seqs = [0]
    if wid in idx["quarantines"]:
        seqs.append(idx["quarantines"][wid]["seq"] or 0)
    if wid in idx.get("rollbacks", {}):
        seqs.append(idx["rollbacks"][wid]["seq"] or 0)
    return max(seqs)


def detect_partial_quarantines(host: MiniHost, idx: dict) -> list[dict]:
    """Suspended/transferred worlds with no covering resolution entry.

    Detection keys on quarantine-shaped evidence ONLY (quarantine-reason
    transfers, or suspended + non-empty pending_effects from the ledger
    checkpoint entry or the host-written side-file checkpoint): a plain
    suspend/reattach probe is NOT a partial quarantine. A world counts
    as partial only when its newest quarantine-shaped progress is NEWER
    than any `quarantine`/`quarantine_rollback` entry for it, so a
    completed quarantine (suspended end state + entry) and a rolled-back
    one are never flagged, while a LATER re-quarantine still is.

    successor-006 (R11 repair): same detection shape as successor-005,
    extended with (a) rollback resolutions, (b) seq comparison instead
    of entry-presence, (c) the side-file fallback for the kill between
    the suspend lifecycle + checkpoint appends.
    """
    out = []
    moved = _quarantine_moved(idx)
    suspects = set(moved)
    for wid, rec in host.worlds.items():
        if rec.lifecycle != "suspended":
            continue
        pend, _ = _pending_from_ledger(idx, wid)
        if pend:
            suspects.add(wid)
            continue
        side, _ = pending_effects_for(host, idx, wid)
        if side:
            suspects.add(wid)
    for wid in sorted(suspects):
        resolution = _quarantine_resolution_seq(idx, wid)
        progress = 0
        for e in moved.get(wid, []):
            progress = max(progress, e.get("seq") or 0)
        _, ckpt_seq = _pending_from_ledger(idx, wid)
        progress = max(progress, ckpt_seq)
        if progress == 0:
            # Side-file-only evidence (kill between the suspend
            # lifecycle + checkpoint appends): any resolution entry
            # covers it, since the side file is rewritten by every
            # later suspend.
            if resolution > 0:
                continue
        elif resolution >= progress:
            continue
        pend, source = pending_effects_for(host, idx, wid)
        out.append(
            {
                "world": wid,
                "lifecycle": host.worlds[wid].lifecycle if wid in host.worlds else "?",
                "pending_effects": pend,
                "pending_source": source,
                "transfers_done": [
                    {
                        "state_class": e["payload"].get("state_class"),
                        "to": e["payload"].get("to"),
                        "seq": e.get("seq"),
                    }
                    for e in moved.get(wid, [])
                ],
            }
        )
    return out


def quarantine_operator_steps(partial: dict) -> str:
    w = partial["world"]
    pend = partial["pending_effects"] or []
    standby = pend[0].get("to", "<standby>") if pend else "<standby>"
    done = {t["state_class"] for t in partial["transfers_done"]}
    missing = [c.get("commitment") for c in pend if c.get("commitment") not in done]
    return (
        f"partial quarantine of {w}: {len(done)} transfer(s) recorded, "
        f"{len(missing)} pending {missing}, no covering quarantine "
        f"entry. SUPPORTED REPAIR (successor-006 closes the R11 owed "
        f"item; the complete-vs-rollback DECISION stays with the "
        f"operator): inspect via `anima-substrate inspect`, then either "
        f"`anima-substrate ops quarantine-complete --state-dir DIR "
        f"--world {w} --standby {standby} --reason R` (transfers "
        f"remaining {missing} {w}->{standby} with actor host, then "
        f"appends the quarantine entry) or `anima-substrate ops "
        f"quarantine-rollback --state-dir DIR --world {w} "
        f"--standby {standby} --reason R` (reverses {sorted(done)} "
        f"{standby}->{w} with actor {standby}, then reattaches {w}). "
        f"Recovery will not settle {w} until the partial quarantine "
        f"is resolved."
    )


# -------------------------------------------- quarantine completion (R11)


def _quarantine_recorded(host: MiniHost, idx: dict, world: str) -> list[dict]:
    """Recorded quarantine-reason transfers from `world` (ledger order)."""
    return [
        {
            "state_class": e["payload"].get("state_class"),
            "to": e["payload"].get("to"),
            "seq": e.get("seq"),
        }
        for e in _quarantine_moved(idx).get(world, [])
    ]


def _require_partial_quarantine(host: MiniHost, idx: dict, world: str) -> dict:
    """Return the detected partial for `world` or raise (nothing to do)."""
    for partial in detect_partial_quarantines(host, idx):
        if partial["world"] == world:
            return partial
    raise RuntimeError(
        f"no partial quarantine of {world!r} to resolve "
        f"(no quarantine-shaped progress newer than its resolution, "
        f"or the world is not suspended with pending handoffs); "
        f"nothing to complete"
    )


def complete_quarantine(
    host: MiniHost,
    world: str,
    standby: str,
    actor: str = "host",
    reason: str = "recover",
) -> dict:
    """Complete an interrupted quarantine (validates all, then mutates).

    The operator's COMPLETE decision, as a supported op (successor-006
    closes the R11 owed quarantine-transfer repair item): remaining
    commitment handoffs world->standby (actor=host, the documented O4
    exception — the giver is suspended) plus the ledger `quarantine`
    entry. The pending set comes from the ledger checkpoint entry, or
    the host-written side-file checkpoint when the kill landed between
    the suspend lifecycle + checkpoint appends; the caller's `standby`
    MUST agree with every recorded handoff or recovery refuses loudly
    — never silently diverging from what the kill interrupted.

    Ledger-conditional: remaining work is derived from ledger state, so
    a kill during completion just leaves a smaller partial and
    re-running converges (proven by the repeated-kill tests).
    """
    idx = ledger_index(host)
    partial = _require_partial_quarantine(host, idx, world)
    try:
        host.verify_conservation()
    except ContractViolation as exc:
        raise ContractViolation(
            f"recovery refused: ledger fails conservation ({exc}); "
            f"resolve the violation first, then re-run"
        ) from exc
    if standby not in host.worlds:
        raise RuntimeError(
            f"recovery refused: standby {standby!r} unknown; pass the original standby"
        )
    if host.worlds[standby].lifecycle != "active":
        raise RuntimeError(
            f"recovery refused: standby {standby!r} is "
            f"{host.worlds[standby].lifecycle}, not active"
        )
    pend = partial["pending_effects"] or []
    if not pend:
        raise RuntimeError(
            f"recovery refused: {world} has no pending handoffs in its "
            f"checkpoint (nothing to complete); reattach it instead"
        )
    bad_target = [c for c in pend if c.get("to") != standby]
    if bad_target:
        raise RuntimeError(
            f"recovery refused: recorded handoffs name "
            f"{sorted({c.get('to') for c in bad_target})}, not the "
            f"supplied standby {standby!r}; pass the original standby"
        )
    want = [c.get("commitment") for c in pend]
    if any(not c for c in want):
        raise RuntimeError(
            f"recovery refused: pending handoffs {pend} are not "
            f"commitment-shaped; operator repair required"
        )
    recorded = _quarantine_recorded(host, idx, world)
    done = {t["state_class"]: t["to"] for t in recorded}
    # A started rollback explains any custody position below: check it
    # FIRST so the operator gets the precise direction (finish the
    # rollback) instead of a generic custody-moved refusal.
    rollbacks = [
        e
        for e in idx["transfers"]
        if e.get("payload", {}).get("reason") == "quarantine rollback"
        and e.get("payload", {}).get("from") == standby
        and e.get("payload", {}).get("to") == world
    ]
    if rollbacks:
        raise RuntimeError(
            f"recovery refused: a rollback of {world} is already in "
            f"progress ({len(rollbacks)} reversal(s) recorded); finish "
            f"it with quarantine-rollback — complete is refused to "
            f"avoid mixing handoff directions"
        )
    for sc, to in done.items():
        if to != standby:
            raise ContractViolation(
                f"recovery refused: recorded transfer {sc}->{to} "
                f"contradicts standby {standby!r} (custody moved since "
                f"the kill); operator repair required"
            )
        if sc not in want:
            raise ContractViolation(
                f"recovery refused: recorded transfer {sc} is outside "
                f"the pending handoff set {want} (ledger inconsistent); "
                f"operator repair required"
            )
        if host.worlds[standby].custodians.get(sc) != standby:
            raise ContractViolation(
                f"recovery refused: recorded handoff {sc} no longer "
                f"held by {standby} (custody moved since the kill); "
                f"operator repair required"
            )
    missing = sorted(set(want) - set(done))
    for sc in missing:
        if host.worlds[world].custodians.get(sc) != world:
            raise ContractViolation(
                f"recovery refused: {sc} not held by {world} (custody "
                f"moved since the kill); operator repair required"
            )
    # ---- execute (all validation passed)
    fresh: list[dict] = []
    for sc in missing:
        host.transfer_custody(
            sc,
            world,
            standby,
            actor="host",
            reason=f"quarantine transfer: {reason}",
            continuity="commitment-handoff",
        )
        fresh.append({"state_class": sc, "from": world, "to": standby})
    transfers = [
        {"state_class": t["state_class"], "from": world, "to": t["to"]}
        for t in recorded
    ] + fresh
    host.append(
        "quarantine",
        {
            "world_id": world,
            "standby": standby,
            "commitments": want,
            "transfers": transfers,
            "reason": reason,
            "recovered": True,
        },
        actor=actor,
    )
    return {
        "world_id": world,
        "standby": standby,
        "commitments": want,
        "transfers": transfers,
        "pending_source": partial["pending_source"],
        "reason": reason,
        "recovered": True,
    }


def rollback_quarantine(
    host: MiniHost,
    world: str,
    standby: str,
    actor: str = "host",
    reason: str = "recover",
) -> dict:
    """Roll back an interrupted quarantine (validates all, then mutates).

    The operator's ROLLBACK decision, as a supported op: reverse every
    recorded handoff standby->world (actor=standby, the current giver),
    reattach the world, and append a `quarantine_rollback` resolution
    entry so detection never flags the resolved partial again. Refuses
    loudly when custody moved since the kill or the world is not
    reattachable — never silently diverging. Ledger-conditional:
    reversals recorded by an interrupted rollback run are adopted (not
    repeated) and an already-active world skips reattach, so a kill
    during rollback converges on re-run.
    """
    idx = ledger_index(host)
    # Validation effect only (raises when no partial is recorded).
    _require_partial_quarantine(host, idx, world)
    try:
        host.verify_conservation()
    except ContractViolation as exc:
        raise ContractViolation(
            f"recovery refused: ledger fails conservation ({exc}); "
            f"resolve the violation first, then re-run"
        ) from exc
    if standby not in host.worlds:
        raise RuntimeError(
            f"recovery refused: standby {standby!r} unknown; pass the original standby"
        )
    recorded = _quarantine_recorded(host, idx, world)
    for t in recorded:
        if t["to"] != standby:
            raise RuntimeError(
                f"recovery refused: recorded transfer "
                f"{t['state_class']}->{t['to']} contradicts the supplied "
                f"standby {standby!r}; pass the original standby"
            )
    # Ledger-conditional progress: reversals already recorded by an
    # interrupted rollback run are adopted, not repeated (kill-during-
    # rollback converges on re-run).
    already = {
        e["payload"].get("state_class")
        for e in idx["transfers"]
        if e.get("payload", {}).get("reason") == "quarantine rollback"
        and e.get("payload", {}).get("from") == standby
        and e.get("payload", {}).get("to") == world
    }
    for sc in sorted(already):
        if host.worlds[world].custodians.get(sc) != world:
            raise ContractViolation(
                f"recovery refused: already-reversed {sc} not held by "
                f"{world} (custody moved since the kill); operator "
                f"repair required"
            )
    todo = [t for t in reversed(recorded) if t["state_class"] not in already]
    for t in todo:
        if host.worlds[standby].custodians.get(t["state_class"]) != standby:
            raise ContractViolation(
                f"recovery refused: {t['state_class']} not held by "
                f"{standby} (custody moved since the kill); operator "
                f"repair required"
            )
    rec = host.worlds[world]
    needs_reattach = rec.lifecycle == "suspended"
    if needs_reattach:
        ckpt_path = Path(rec.instance_state_dir) / "checkpoint.json"
        if not ckpt_path.exists():
            raise ContractViolation(
                f"recovery refused: {world} is suspended with a "
                f"missing checkpoint (reattach would fail); operator "
                f"repair required"
            )
        try:
            checkpoint = json.loads(ckpt_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ContractViolation(
                f"recovery refused: {world} checkpoint unreadable "
                f"({exc}); reattach would fail; operator repair "
                f"required"
            ) from exc
        if (
            checkpoint.get("world_id") != world
            or checkpoint.get("code_ref") != rec.code_ref
        ):
            raise ContractViolation(
                f"recovery refused: {world} checkpoint identity "
                f"mismatch (reattach would fail); operator repair "
                f"required"
            )
    elif rec.lifecycle != "active":
        raise ContractViolation(
            f"recovery refused: {world} is {rec.lifecycle} (expected "
            f"suspended, or active after an interrupted rollback); "
            f"operator repair required"
        )
    # ---- execute (all validation passed)
    reversed_transfers: list[dict] = []
    for t in todo:
        host.transfer_custody(
            t["state_class"],
            standby,
            world,
            actor=standby,
            reason="quarantine rollback",
            continuity="rollback",
        )
        reversed_transfers.append(
            {"state_class": t["state_class"], "from": standby, "to": world}
        )
    if needs_reattach:
        host.reattach(world, actor, reason=f"quarantine rollback: {reason}")
    host.append(
        "quarantine_rollback",
        {
            "world_id": world,
            "standby": standby,
            "transfers_reversed": [
                {"state_class": t["state_class"], "from": standby, "to": world}
                for t in recorded
            ],
            "reason": reason,
            "recovered": True,
        },
        actor=actor,
    )
    return {
        "world_id": world,
        "standby": standby,
        "transfers_reversed": [
            {"state_class": t["state_class"], "from": standby, "to": world}
            for t in recorded
        ],
        "adopted_reversals": sorted(already),
        "reason": reason,
        "recovered": True,
    }


# ------------------------------------------------------ birth completion


def _birth_grant_for(idx: dict, wid: str) -> dict:
    # S5: worlds born with a procedure table complete with the
    # minutes-adequate proc grant; sched worlds keep GRANT_LIMITS
    # (byte-identical behavior).
    if idx["creates"][wid].get("procedures"):
        return dict(PROC_GRANT_LIMITS)
    return dict(GRANT_LIMITS)


def plan_births(host: MiniHost, idx: dict, skip: set[str]) -> list[dict]:
    """Plan grant+activate for proposed worlds outside partial ops.

    Pure validation (no mutation): raises ContractViolation when a
    birth cannot be completed (host cannot fund the initial grant).
    """
    plans = []
    for wid in idx["create_order"]:
        if wid in skip or wid not in host.worlds:
            continue
        if host.worlds[wid].lifecycle != "proposed":
            continue
        need_grant = not idx["grants_to"].get(wid)
        if need_grant:
            want = _birth_grant_for(idx, wid)
            avail = host.holdings.get("host", {})
            short = [k for k in want if want[k] > avail.get(k, 0) + 1e-9]
            if short:
                raise ContractViolation(
                    f"recovery refused: cannot fund initial grant "
                    f"for proposed world {wid!r} (host short on "
                    f"{short}); operator repair required"
                )
        plans.append({"world": wid, "need_grant": need_grant})
    return plans


def run_births(host: MiniHost, idx: dict, plans: list[dict]) -> list[str]:
    """Execute birth plans (grant-if-missing, then activate)."""
    done = []
    for plan in plans:
        wid = plan["world"]
        if plan["need_grant"]:
            authorities = list(idx["creates"][wid].get("authorities", []))
            host.grant(
                "host",
                wid,
                _birth_grant_for(idx, wid),
                authority=authorities,
                grant_id=f"g-init-{wid}",
            )
        host.transition(
            wid, "active", "host", reason="recovery: complete interrupted birth"
        )
        done.append(wid)
    return done


# ---------------------------------------------------- fusion completion


def _fusion_done(host: MiniHost, idx: dict, composite: str) -> list[dict]:
    return [
        {
            "state_class": e["payload"].get("state_class"),
            "from": e["payload"].get("from"),
            "to": e["payload"].get("to"),
        }
        for e in idx["transfers"]
        if e.get("payload", {}).get("reason") == f"fusion into {composite}"
        and e.get("payload", {}).get("to") == composite
    ]


def complete_fusion(
    host: MiniHost, composite: str, actor: str = "host", reason: str = "recover"
) -> dict:
    """Complete an interrupted fusion (validates all, then mutates).

    Parents come from the composite's recorded derived_from lineage;
    remaining transfers/dissolves are derived from ledger state, so the
    completion is deterministic and idempotent (re-running after a kill
    during recovery just finishes a smaller remainder).
    """
    idx = ledger_index(host)
    if composite in idx["fusions"]:
        raise RuntimeError(
            f"fusion of {composite} already recorded: nothing to complete"
        )
    if composite not in idx["creates"]:
        raise RuntimeError(
            f"no interrupted fusion of {composite}: never created (nothing to complete)"
        )
    parents = _fusion_parents_of(idx["creates"][composite])
    if len(parents) != 2 or parents[0] == parents[1]:
        raise ContractViolation(
            f"recovery refused: {composite} has no clean 2-parent "
            f"fusion lineage {parents}; operator repair required"
        )
    a, b = parents
    for p in (a, b):
        if p not in host.worlds:
            raise ContractViolation(
                f"recovery refused: fusion parent {p!r} unknown in "
                f"ledger; operator repair required"
            )
    state = host.worlds[composite].lifecycle
    if state not in ("active", "proposed"):
        raise ContractViolation(
            f"recovery refused: composite {composite} is {state}; "
            f"operator repair required"
        )
    done = _fusion_done(host, idx, composite)
    done_sc = {t["state_class"] for t in done}
    if state == "proposed" and done:
        raise ContractViolation(
            f"recovery refused: proposed {composite} already has "
            f"fusion transfers (ledger inconsistent); operator repair"
        )
    need_grant = not idx["grants_to"].get(composite)
    if need_grant:
        avail = host.holdings.get("host", {})
        short = [k for k in GRANT_LIMITS if GRANT_LIMITS[k] > avail.get(k, 0) + 1e-9]
        if short:
            raise ContractViolation(
                f"recovery refused: host cannot fund the initial "
                f"grant for {composite} (short on {short}); "
                f"operator repair required"
            )
    remaining: dict[str, list[str]] = {}
    for giver in (a, b):
        gstate = host.worlds[giver].lifecycle
        if gstate not in ("active", "dissolved"):
            raise ContractViolation(
                f"recovery refused: parent {giver} is {gstate}; "
                f"operator repair required"
            )
        if gstate == "dissolved" and not idx["markers"].get(giver):
            raise ContractViolation(
                f"recovery refused: parent {giver} dissolved with no "
                f"grant_settle marker (fail-closed); operator repair"
            )
        pre = set(host.worlds[giver].custodians) | {
            t["state_class"] for t in done if t["from"] == giver
        }
        rest = sorted(pre - done_sc)
        if gstate == "dissolved" and rest:
            raise ContractViolation(
                f"recovery refused: dissolved parent {giver} still "
                f"owes transfers {rest} (ledger inconsistent)"
            )
        for sc in rest:
            if host.worlds[giver].custodians.get(sc) != giver:
                raise ContractViolation(
                    f"recovery refused: {sc} not held by {giver} "
                    f"(custody moved since the kill); operator repair"
                )
        remaining[giver] = rest
        if gstate == "active":
            host.check_settleable(giver)  # raises before ANY mutation
    # ---- execute (all validation passed)
    if need_grant:
        authorities = list(idx["creates"][composite].get("authorities", []))
        host.grant(
            "host",
            composite,
            dict(GRANT_LIMITS),
            authority=authorities,
            grant_id=f"g-init-{composite}",
        )
    if state == "proposed":
        host.transition(
            composite,
            "active",
            actor,
            reason="recovery: activate interrupted composite",
        )
    fresh: list[dict] = []
    for giver in (a, b):
        for sc in remaining[giver]:
            host.transfer_custody(
                sc,
                giver,
                composite,
                actor=giver,
                reason=f"fusion into {composite}",
                continuity="sha256-of-composite",
            )
            fresh.append({"state_class": sc, "from": giver, "to": composite})
    for giver in (a, b):
        if host.worlds[giver].lifecycle == "active":
            host.transition(
                giver,
                "dissolved",
                actor,
                reason=f"fused into {composite} (recovery completion)",
            )
    transfers = done + fresh
    host.append(
        "fusion",
        {
            "fused_id": composite,
            "parents": [a, b],
            "transfers": transfers,
            "removed_mechanism": "direct-channel:" + ChannelRegistry.key(a, b),
            "reason": reason,
        },
        actor=actor,
    )
    return {
        "fused_id": composite,
        "parents": [a, b],
        "transfers": transfers,
        "removed_mechanism": "direct-channel:" + ChannelRegistry.key(a, b),
        "reason": reason,
        "recovered": True,
    }


# --------------------------------------------------- fission completion


def _fission_done(host: MiniHost, idx: dict, composite: str) -> dict:
    done: dict[str, str] = {}
    for e in idx["transfers"]:
        p = e.get("payload", {})
        if (
            str(p.get("reason", "")).startswith(f"fission of {composite}:")
            and p.get("from") == composite
        ):
            done[p.get("state_class", "")] = p.get("to", "")
    return done


def _split_nv(items: list[str]) -> list[tuple[str, str]]:
    out = []
    for item in items:
        name, _, version = item.partition("@")
        out.append((name, version))
    return out


def complete_fission(
    host: MiniHost,
    state_dir: Path | str,
    composite: str,
    left: str,
    right: str,
    partition: dict[str, str],
    left_caps,
    left_reps,
    right_caps,
    right_reps,
    actor: str = "host",
    reason: str = "recover",
) -> dict:
    """Complete an interrupted fission (validates all, then mutates).

    The operator supplies the partition (+ child names + cap/rep specs,
    normally via api presets): they are the partition of record and
    MUST agree with pre-crash progress (recorded transfers, created
    children's lineage) or recovery refuses loudly -- never silently
    diverging from what the kill interrupted.
    """
    idx = ledger_index(host)
    if left == right:
        raise ValueError(f"fission needs two distinct children, got {left!r} twice")
    if composite in idx["fission"]:
        raise RuntimeError(
            f"fission of {composite} already recorded: nothing to complete"
        )
    if composite not in idx["creates"]:
        raise RuntimeError(
            f"no interrupted fission of {composite}: "
            f"never created (nothing to complete)"
        )
    if composite not in idx["fusions"]:
        raise ContractViolation(
            f"recovery refused: {composite} is not a recorded fusion "
            f"composite; operator repair required"
        )
    fusion_parents = list(idx["fusions"][composite]["payload"].get("parents", []))
    if composite not in host.worlds:
        raise ContractViolation(
            f"recovery refused: {composite} unknown; operator repair"
        )
    cstate = host.worlds[composite].lifecycle
    done = _fission_done(host, idx, composite)
    expected = set(host.worlds[composite].custodians) | set(done)
    # ---- partition validation (mirrors fission_worlds + progress match)
    pkeys = set(partition)
    if pkeys != expected:
        raise ValueError(
            f"recovery partition must cover exactly the composite's "
            f"remaining + transferred classes {sorted(expected)}: "
            f"missing {sorted(expected - pkeys)}, "
            f"unknown {sorted(pkeys - expected)}"
        )
    sides = {left, right}
    bad = {sc: owner for sc, owner in partition.items() if owner not in sides}
    if bad:
        raise ValueError(f"recovery partition assigns outside {left}, {right}: {bad}")
    if set(partition.values()) != sides:
        raise ValueError(
            f"recovery partition must split across BOTH "
            f"children, got one-sided {partition}"
        )
    for sc, owner in done.items():
        if partition.get(sc) != owner:
            raise RuntimeError(
                f"recovery refused: recorded transfer {sc}->"
                f"{owner} contradicts the supplied partition "
                f"({sc}->{partition.get(sc)}); re-run with the "
                f"partition matching recorded progress"
            )
    # ---- children validation (created children must match the args)
    specs = {
        left: (left_caps, left_reps, "left"),
        right: (right_caps, right_reps, "right"),
    }
    for child, (caps, reps, side) in specs.items():
        want_side_classes = sorted(sc for sc, o in partition.items() if o == child)
        if child in idx["creates"]:
            payload = idx["creates"][child]
            named = [
                entry
                for entry in payload.get("lineage", [])
                if isinstance(entry, dict)
                and entry.get("rel") == "fission-of"
                and entry.get("fusion") == composite
            ]
            if not named:
                raise RuntimeError(
                    f"recovery refused: existing world {child} is not "
                    f"a recorded child of {composite}; pass the "
                    f"original child names"
                )
            if named[0].get("side") != side:
                raise RuntimeError(
                    f"recovery refused: {child} was created as side "
                    f"{named[0].get('side')!r}, now passed as {side!r}; "
                    f"pass the original --left/--right assignment"
                )
            if sorted(named[0].get("partition", [])) != want_side_classes:
                raise RuntimeError(
                    f"recovery refused: {child} was created for side "
                    f"{named[0].get('partition')} but the supplied "
                    f"partition gives {want_side_classes}; pass the "
                    f"original partition"
                )
            have_caps = set(payload.get("capabilities", []))
            want_caps = {n + "@" + v for n, v in caps}
            if have_caps != want_caps:
                raise RuntimeError(
                    f"recovery refused: {child} was created with "
                    f"capabilities {sorted(have_caps)}, not the "
                    f"supplied preset {sorted(want_caps)}; pass the "
                    f"original presets"
                )
            if child not in host.worlds:
                raise ContractViolation(
                    f"recovery refused: {child} created but unknown "
                    f"after reopen; operator repair required"
                )
            if host.worlds[child].lifecycle not in ("active", "proposed"):
                raise ContractViolation(
                    f"recovery refused: child {child} is "
                    f"{host.worlds[child].lifecycle}; operator repair"
                )
        else:
            if child in host.worlds:
                raise ContractViolation(
                    f"recovery refused: {child} live but never "
                    f"created in-ledger; operator repair required"
                )
            sdir = (Path(state_dir) / "state" / child).resolve()
            for other in host.worlds.values():
                if Path(other.instance_state_dir).resolve() == sdir:
                    raise ContractViolation(
                        f"recovery refused: state dir for {child} "
                        f"already owned by {other.world_id}"
                    )
    # ---- composite end-state validation
    if cstate == "active":
        host.check_settleable(composite)  # raises before ANY mutation
        for sc in sorted(expected - set(done)):
            if host.worlds[composite].custodians.get(sc) != composite:
                raise ContractViolation(
                    f"recovery refused: {sc} not held by "
                    f"{composite} (custody moved since the kill)"
                )
    elif cstate == "dissolved":
        if not idx["markers"].get(composite):
            raise ContractViolation(
                f"recovery refused: {composite} dissolved with no "
                f"grant_settle marker (fail-closed); operator repair"
            )
        if expected - set(done) or host.worlds[composite].custodians:
            raise ContractViolation(
                f"recovery refused: dissolved {composite} still "
                f"holds custody (ledger inconsistent)"
            )
    else:
        raise ContractViolation(
            f"recovery refused: composite {composite} is {cstate}; "
            f"operator repair required"
        )
    missing = [c for c in (left, right) if c not in idx["creates"]]
    if missing:
        avail = host.holdings.get("host", {})
        short = [
            k
            for k in GRANT_LIMITS
            if len(missing) * GRANT_LIMITS[k] > avail.get(k, 0) + 1e-9
        ]
        if short:
            raise ContractViolation(
                f"recovery refused: host cannot fund {len(missing)} "
                f"child grant(s) (short on {short}); operator repair"
            )
    # ---- execute (all validation passed)
    for child, (caps, reps, side) in specs.items():
        if child in idx["creates"]:
            if not idx["grants_to"].get(child):
                authorities = list(idx["creates"][child].get("authorities", []))
                host.grant(
                    "host",
                    child,
                    dict(GRANT_LIMITS),
                    authority=authorities,
                    grant_id=f"g-init-{child}",
                )
            if host.worlds[child].lifecycle == "proposed":
                host.transition(
                    child, "active", actor, reason="recovery: activate child"
                )
        else:
            side_classes = sorted(sc for sc, o in partition.items() if o == child)
            rec = world_record(Path(state_dir) / "state", child, list(caps), list(reps))
            rec.lineage = [
                {"rel": "derived_from", "world": composite},
                {
                    "rel": "fission-of",
                    "fusion": composite,
                    "fusion_parents": fusion_parents,
                    "side": side,
                    "partition": side_classes,
                },
                {"rel": "fission", "actor": actor, "reason": reason},
            ]
            host.create_world(rec, "host", grant_limits=dict(GRANT_LIMITS))
            host.transition(
                child, "active", actor, reason="recovery: fission birth completion"
            )
    fresh: list[dict] = []
    for sc in sorted(expected - set(done)):
        host.transfer_custody(
            sc,
            composite,
            partition[sc],
            actor=composite,
            reason=f"fission of {composite}: {reason}",
            continuity="fission-partition",
        )
        fresh.append({"state_class": sc, "from": composite, "to": partition[sc]})
    if host.worlds[composite].lifecycle == "active":
        host.transition(
            composite,
            "dissolved",
            actor,
            reason=f"fissioned into {left}+{right} (recovery completion)",
        )
    done_list = [
        {"state_class": sc, "from": composite, "to": owner}
        for sc, owner in sorted(done.items(), key=lambda kv: kv[0])
    ]
    transfers = done_list + fresh
    host.append(
        "fission",
        {
            "composite": composite,
            "children": [left, right],
            "partition": dict(partition),
            "fusion": {"fused_id": composite, "parents": fusion_parents},
            "transfers": transfers,
            "restored_mechanism": "direct-channel:" + ChannelRegistry.key(left, right),
            "reason": reason,
        },
        actor=actor,
    )
    return {
        "composite": composite,
        "children": [left, right],
        "partition": dict(partition),
        "fusion": {"fused_id": composite, "parents": fusion_parents},
        "transfers": transfers,
        "restored_mechanism": "direct-channel:" + ChannelRegistry.key(left, right),
        "reason": reason,
        "recovered": True,
    }


# ---------------------------------------------------------- spec repair


def spec_for_create(payload: dict, custodians: dict) -> dict:
    """Rebuild a worlds.json spec from a ledger `create` payload."""
    spec = {
        "world_id": payload["world_id"],
        "caps": [[n, v] for n, v in _split_nv(payload.get("capabilities", []))],
        "reps": [[n, v] for n, v in _split_nv(payload.get("representations", []))],
        "custodians": dict(custodians),
    }
    if payload.get("procedures"):
        # S5 R-A: additive-absent-when-empty — sched specs keep
        # byte-identical shapes; proc worlds carry their table.
        spec["procedures"] = [dict(t) for t in payload["procedures"]]
    return spec


def missing_specs(host: MiniHost, idx: dict, specs: list[dict]) -> list[str]:
    known = {s["world_id"] for s in specs}
    return [wid for wid in idx["create_order"] if wid not in known]


def repair_specs(root: Path, host: MiniHost, idx: dict, specs: list[dict]) -> list[str]:
    """Append specs for ledger-known worlds missing from worlds.json.

    The ledger `create` payloads are authoritative (code_ref/caps/reps
    match by construction, so the next open_run verifies). Crash point
    `recover:pre-spec` fires before the write (kill-during-recovery
    boundary: re-running repair is idempotent).
    """
    miss = missing_specs(host, idx, specs)
    if not miss:
        return []
    maybe_crash_at("recover:pre-spec")
    for wid in miss:
        specs.append(
            spec_for_create(
                idx["creates"][wid],
                host.worlds[wid].custodians if wid in host.worlds else {},
            )
        )
    atomic_write_text(
        root / "worlds.json", json.dumps(specs, indent=2, sort_keys=True) + "\n"
    )
    return miss
