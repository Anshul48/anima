# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-004 scheduling domain (X3 domain lineage, rewritten).

Constrained scheduling: place tasks into slots subject to
machine-exclusive (one task per slot) + precedence + window constraints.

Two representations (same split-state idea as X3):
- LIST-form: task -> requirements (windows) + precedence + preferences.
- SLOT-form: slot -> occupancy (machine, time, occupant).

Translation LIST->SLOT drops preferences (DECLARED loss); recovering them
needs clarification rounds. Protocol rule: one fragment per round; each
world's preference half arrives in its own round, so >= 2 clarification
rounds are required whenever preferences are split across worlds.

No imports from frozen directories; stdlib only.
"""

from __future__ import annotations

import json

ADAPTER_V1 = "list2slot/v1"
ADAPTER_V2 = "list2slot/v2"


def canonical_bytes(obj: dict) -> int:
    return len(json.dumps(obj, sort_keys=True).encode("utf-8"))


def list_doc(task: dict) -> dict:
    return {
        "form": "LIST",
        "task_id": task["task_id"],
        "tasks": task["tasks"],
        "precedence": task["precedence"],
        "prefs": task["prefs"],
    }


def slot_doc(task: dict, occupant: dict | None = None) -> dict:
    slots = {}
    for sid, spec in task["slots"].items():
        slots[sid] = {
            "machine": spec["machine"],
            "time": spec["time"],
            "occupant": (occupant or {}).get(sid),
        }
    return {"form": "SLOT", "task_id": task["task_id"], "slots": slots}


def translate_list2slot(ldoc: dict, version: str) -> tuple[dict, dict]:
    """Translate LIST -> SLOT. Preferences are DROPPED (declared loss)."""
    if version not in (ADAPTER_V1, ADAPTER_V2):
        raise ValueError(f"unknown adapter {version!r}")
    slots = {}
    for tid, req in sorted(ldoc["tasks"].items()):
        for sid in req["window"]:
            slots.setdefault(sid, {"candidate_tasks": []})["candidate_tasks"].append(
                tid
            )
    sdoc = {
        "form": "SLOT",
        "adapter": version,
        "task_id": ldoc["task_id"],
        "slots": slots,
    }
    loss = {
        "adapter": version,
        "dropped": ["preferences"],
        "reason": "SLOT-form carries occupancy only; preferences must be "
        "re-supplied via clarification rounds",
    }
    return sdoc, loss


def solve(task: dict) -> dict:
    """Deterministic backtracking solver: max prefs, ties -> lexicographic."""
    tids = sorted(task["tasks"])
    slots = task["slots"]
    order = {t: i for i, t in enumerate(sorted({s["time"] for s in slots.values()}))}
    prec = [(a, b) for a, b in task["precedence"]]
    prefs = task["prefs"]
    best: dict | None = None
    best_key = None

    def pref_sat(assign: dict) -> int:
        return sum(1 for t, s in assign.items() if slots[s]["machine"] == prefs.get(t))

    def ok_partial(assign: dict) -> bool:
        used = list(assign.values())
        if len(set(used)) != len(used):
            return False
        for a, b in prec:
            if a in assign and b in assign:
                if order[slots[assign[a]]["time"]] >= order[slots[assign[b]]["time"]]:
                    return False
        return True

    def rec(i: int, assign: dict) -> None:
        nonlocal best, best_key
        if i == len(tids):
            if not ok_partial(assign):
                return
            key = (-pref_sat(assign), tuple((t, assign[t]) for t in tids))
            if best_key is None or key < best_key:
                best_key = key
                best = dict(assign)
            return
        tid = tids[i]
        for sid in sorted(task["tasks"][tid]["window"]):
            if sid in assign.values():
                continue
            assign[tid] = sid
            if ok_partial(assign):
                rec(i + 1, assign)
            del assign[tid]

    rec(0, {})
    if best is None:
        raise ValueError(f"no valid schedule for {task['task_id']}")
    return best


# -- protocol fragments (one fragment per round) ----------------------


def req_fragment(task_id: str, frm: str, tasks: dict, precedence: list) -> dict:
    return {
        "kind": "req-fragment",
        "task_id": task_id,
        "from": frm,
        "tasks": tasks,
        "precedence": precedence,
    }


def pref_fragment(task_id: str, frm: str, prefs: dict) -> dict:
    return {"kind": "pref-fragment", "task_id": task_id, "from": frm, "prefs": prefs}


def proposal(task_id: str, frm: str, assignment: dict, basis: str) -> dict:
    return {
        "kind": "proposal",
        "task_id": task_id,
        "from": frm,
        "assignment": assignment,
        "basis": basis,
    }


def commitment(task_id: str, frm: str, assignment: dict, receipt: str) -> dict:
    return {
        "kind": "commitment",
        "task_id": task_id,
        "from": frm,
        "assignment": assignment,
        "obligation_receipt": receipt,
    }


def escalation(task_id: str, frm: str, issue: str, options: list) -> dict:
    return {
        "kind": "escalation",
        "task_id": task_id,
        "from": frm,
        "issue": issue,
        "options": options,
    }


def resolution(task_id: str, ruling: str, reason: str) -> dict:
    return {
        "kind": "resolution",
        "task_id": task_id,
        "from": "coordinator",
        "ruling": ruling,
        "reason": reason,
    }
