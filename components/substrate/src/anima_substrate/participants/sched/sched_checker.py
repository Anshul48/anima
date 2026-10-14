# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-004 independent checker (X3 checker lineage, rewritten).

VALID = all hard constraints hold. Quality = preferences satisfied
(count, higher better). Validates solutions against the constraints,
not a hash self-gate. No imports from frozen directories; stdlib only.
"""

from __future__ import annotations

import json
import sys


def check(assignment: dict, task: dict) -> dict:
    violations: list[str] = []
    tids = sorted(task["tasks"])
    if sorted(assignment) != tids:
        violations.append(f"task set {sorted(assignment)} != {tids}")
    for tid, sid in sorted(assignment.items()):
        if tid not in task["tasks"]:
            violations.append(f"unknown task {tid}")
            continue
        if sid not in task["slots"]:
            violations.append(f"{tid}: unknown slot {sid}")
        elif sid not in task["tasks"][tid]["window"]:
            violations.append(f"{tid}: slot {sid} outside window")
    used = sorted(assignment.values())
    if len(set(used)) != len(used):
        violations.append("machine-exclusive violated (double occupancy)")
    order = {
        t: i for i, t in enumerate(sorted({s["time"] for s in task["slots"].values()}))
    }
    for a, b in task["precedence"]:
        if (
            a in assignment
            and b in assignment
            and assignment[a] in task["slots"]
            and assignment[b] in task["slots"]
        ):
            if (
                order[task["slots"][assignment[a]]["time"]]
                >= order[task["slots"][assignment[b]]["time"]]
            ):
                violations.append(f"precedence {a}<{b} violated")
    prefs = task.get("prefs", {})
    quality = sum(
        1
        for t, s in assignment.items()
        if t in prefs and s in task["slots"] and task["slots"][s]["machine"] == prefs[t]
    )
    return {
        "valid": not violations,
        "violations": violations,
        "quality": quality,
        "prefs_total": len(prefs),
    }


KNOWN_TASK = {
    "task_id": "S-CAL",
    "slots": {
        "S0": {"machine": "M0", "time": "t0"},
        "S1": {"machine": "M1", "time": "t0"},
        "S2": {"machine": "M0", "time": "t1"},
        "S3": {"machine": "M1", "time": "t1"},
    },
    "tasks": {
        "A": {"window": ["S0", "S2"]},
        "B": {"window": ["S1", "S3"]},
        "C": {"window": ["S0", "S1"]},
        "D": {"window": ["S2", "S3"]},
    },
    "precedence": [["A", "B"], ["C", "D"]],
    "prefs": {"A": "M0", "B": "M1", "C": "M1", "D": "M0"},
}
KNOWN_GOOD = {"A": "S0", "B": "S3", "C": "S1", "D": "S2"}
KNOWN_BAD = {"A": "S2", "B": "S1", "C": "S1", "D": "S3"}  # double S1 + prec


def self_check() -> dict:
    good = check(KNOWN_GOOD, KNOWN_TASK)
    bad = check(KNOWN_BAD, KNOWN_TASK)
    assert good["valid"] and good["quality"] == 4, good
    assert not bad["valid"] and bad["violations"], bad
    return {"known_good": good, "known_bad": bad}


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-check":
        print(json.dumps(self_check(), indent=2, sort_keys=True))
    else:
        print("usage: sched_checker.py --self-check")
        sys.exit(2)
