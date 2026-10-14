# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-004 frozen task inputs.

Fixed at build time; the demo and tests never mutate TASKS (deep copies
are taken by runners). Small toy scale, same envelope as the X3 lineage.
"""

from __future__ import annotations

SLOTS = {
    "S0": {"machine": "M0", "time": "t0"},
    "S1": {"machine": "M1", "time": "t0"},
    "S2": {"machine": "M0", "time": "t1"},
    "S3": {"machine": "M1", "time": "t1"},
}

BASE_TASKS = {
    "A": {"window": ["S0", "S2"]},
    "B": {"window": ["S1", "S3"]},
    "C": {"window": ["S0", "S1"]},
    "D": {"window": ["S2", "S3"]},
}
BASE_PREC = [["A", "B"], ["C", "D"]]
BASE_PREFS = {"A": "M0", "B": "M1", "C": "M1", "D": "M0"}

# S1: small task, preferences co-located -> CENTRAL lane.
S1 = {
    "task_id": "S1",
    "slots": dict(SLOTS),
    "tasks": {k: dict(v) for k, v in BASE_TASKS.items()},
    "precedence": [list(p) for p in BASE_PREC],
    "prefs": dict(BASE_PREFS),
    "holdings": {
        "SC-L": {"req_tasks": ["A", "B", "C", "D"], "prefs": ["A", "B", "C", "D"]},
        "SC-S": {"req_tasks": [], "prefs": []},
    },
    "adapter": "list2slot/v1",
    "expected_rounds": 2,
    "split_state": False,
}

# S2: dialogue-heavy, preferences split across worlds -> LOCAL lane.
S2 = {
    "task_id": "S2",
    "slots": dict(SLOTS),
    "tasks": {k: dict(v) for k, v in BASE_TASKS.items()},
    "precedence": [list(p) for p in BASE_PREC],
    "prefs": dict(BASE_PREFS),
    "holdings": {
        "SC-L": {"req_tasks": ["A", "B"], "prefs": ["A", "B"]},
        "SC-S": {"req_tasks": ["C", "D"], "prefs": ["C", "D"]},
    },
    "adapter": "list2slot/v1",
    "expected_rounds": 4,
    "split_state": True,
}

# S3: revision v1->v2 + revocation + kill mid-adaptation.
S3_BASE = {
    "task_id": "S3-base",
    "slots": dict(SLOTS),
    "tasks": {k: dict(v) for k, v in BASE_TASKS.items()},
    "precedence": [list(p) for p in BASE_PREC],
    "prefs": dict(BASE_PREFS),
    "adapter": "list2slot/v1",
}
S3_REVISED = {
    "task_id": "S3-v2",
    "slots": dict(SLOTS),
    "tasks": {
        "A": {"window": ["S0", "S2"]},
        "B": {"window": ["S3"]},
        "C": {"window": ["S0", "S1"]},
        "D": {"window": ["S2", "S3"]},
    },
    "precedence": [list(p) for p in BASE_PREC],
    "prefs": dict(BASE_PREFS),
    "adapter": "list2slot/v2",
}
S3 = {
    "task_id": "S3",
    "base": S3_BASE,
    "revision": {
        "from": "list2slot/v1",
        "to": "list2slot/v2",
        "window_changes": {"B": ["S3"]},
        "declared_loss": ["preferences"],
    },
    "revised": S3_REVISED,
    "revocation": {
        "capability": "sched.propose",
        "version": "1.0",
        "from": "SC-L",
        "to": "SC-S",
        "reason": "ownership change at v1->v2",
    },
    "holdings": {
        "SC-L": {"req_tasks": ["A", "B"], "prefs": ["A", "B"]},
        "SC-S": {"req_tasks": ["C", "D"], "prefs": ["C", "D"]},
    },
    "expected_rounds": 4,
    "split_state": True,
}

# S4: fusion follow-up — composite reused on a 5-task extension.
S4_FOLLOWUP = {
    "task_id": "S4-followup",
    "slots": {**SLOTS, "S4": {"machine": "M1", "time": "t2"}},
    "tasks": {
        "A": {"window": ["S0", "S2"]},
        "B": {"window": ["S1", "S3"]},
        "C": {"window": ["S0", "S1"]},
        "D": {"window": ["S2", "S3"]},
        "E": {"window": ["S4"]},
    },
    "precedence": [["A", "B"], ["C", "D"]],
    "prefs": {"A": "M0", "B": "M1", "C": "M1", "D": "M0", "E": "M1"},
    "adapter": "list2slot/v1",
}
S4 = {
    "task_id": "S4",
    "composite_from": "S2",
    "followup": S4_FOLLOWUP,
    "transfer": {
        "state_class": "sched.composite",
        "from": "SC-L",
        "to": "SC-FUSED",
        "continuity": "sha256-of-composite",
    },
}

# S5: quarantine drill — spare world fails, standby takes commitments.
S5 = {
    "task_id": "S5",
    "slots": dict(SLOTS),
    "tasks": {k: dict(v) for k, v in BASE_TASKS.items()},
    "precedence": [list(p) for p in BASE_PREC],
    "prefs": dict(BASE_PREFS),
    "adapter": "list2slot/v1",
}

# S6: fission follow-up — the split pair cooperates on a fresh task.
S6_FISSION_FOLLOWUP = {
    "task_id": "S6-followup",
    "slots": dict(SLOTS),
    "tasks": {k: dict(v) for k, v in BASE_TASKS.items()},
    "precedence": [list(p) for p in BASE_PREC],
    "prefs": dict(BASE_PREFS),
    "adapter": "list2slot/v1",
}

TASKS = {"S1": S1, "S2": S2, "S3": S3, "S4": S4, "S5": S5, "S6": S6_FISSION_FOLLOWUP}
