# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-004 hybrid coordination (X3 arm-C/arm-H lineage).

Central default + explicit logged routing rule: multi-round dialogue
over split state goes to the local-negotiation lane; everything else
stays central. Routing decisions are recorded per task (ledger
`routing` entries + a run-local routing log).

X3 evidence incorporated: central wins small (S1-shape), local wins
dialogue-heavy (S2-shape). The rule below encodes exactly that cut.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from ..participants.sched import sched_domain as domain
from .minihost import (
    ContractViolation,
    MiniCapability,
    MiniHost,
    MiniRepresentation,
    MiniWorldRecord,
    atomic_write_text,
)

GRANT_LIMITS = {"max_cost_usd": 1.0, "max_time_s": 60.0, "max_invocations": 100}

CODE_REF = "anima-substrate/host/routing.py"

# ---------------------------------------------------------------- rule

LOCAL_MIN_ROUNDS = 2


def route(task: dict) -> dict:
    """Apply the hybrid routing rule. Central default; local iff the task
    needs multi-round dialogue (>=2 clarification rounds) over state
    split across worlds."""
    rounds = int(task.get("expected_rounds", 1))
    split = bool(task.get("split_state", False))
    if rounds >= LOCAL_MIN_ROUNDS and split:
        lane = "local"
        reason = (
            f"multi-round dialogue ({rounds}>=2 rounds) over split "
            f"state -> local-negotiation lane (X3 H3a cut)"
        )
    else:
        lane = "central"
        reason = (
            f"default central (rounds={rounds}, split={split}; "
            f"local requires >=2 rounds AND split state)"
        )
    return {
        "task_id": task.get("task_id", "?"),
        "lane": lane,
        "rule": "local iff expected_rounds>=2 AND split_state else central",
        "inputs": {"expected_rounds": rounds, "split_state": split},
        "reason": reason,
    }


def record_routing(host: MiniHost, decision: dict, log_path: Path) -> dict:
    """Ledger the routing decision AND append to the run routing log."""
    entry = host.append("routing", dict(decision), actor="host")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(decision, sort_keys=True) + "\n")
    return entry


# ------------------------------------------------------- coordinators


class Coordinator:
    """Central context meter: every message the coordinator handles counts."""

    def __init__(self) -> None:
        self.central_bytes = 0
        self.handled: list[dict] = []

    def handle(self, msg: dict) -> dict:
        n = domain.canonical_bytes(msg)
        self.central_bytes += n
        self.handled.append({"kind": msg.get("kind"), "bytes": n})
        return msg


class HCoordinator(Coordinator):
    """Local-lane coordinator: sees ONLY commitments, escalations and
    resolutions. Any other payload is refused (mechanism guard: local
    state stays local; direct world traffic bypasses this object)."""

    ALLOWED = ("commitment", "escalation", "resolution")

    def handle(self, msg: dict) -> dict:
        if msg.get("kind") not in self.ALLOWED:
            raise ValueError(
                f"coordinator refused non-export payload "
                f"{msg.get('kind')!r}: local state stays local"
            )
        return super().handle(msg)


class DirectChannel:
    """World-to-world traffic: counted, never shown to the coordinator."""

    def __init__(self, name: str, _save=None) -> None:
        self.name = name
        self.direct_bytes = 0
        self.n = 0
        self.removed = False
        self._save = _save

    def send(self, msg: dict) -> dict:
        if self.removed:
            raise RuntimeError(
                f"direct channel {self.name} was removed "
                f"(fused pair communicates internally now)"
            )
        self.direct_bytes += domain.canonical_bytes(msg)
        self.n += 1
        if self._save is not None:
            self._save()
        return msg


class ChannelRegistry:
    """Named direct channels between world pairs. Fusion removes the
    channel between the fused pair (the now-redundant mechanism).

    M3 persistence: with a `backing` file, every mutation (get /
    send / remove) is crash-atomically persisted (temp +
    os.replace, old-or-new), and an existing backing file is loaded
    at construction. Without `backing` the registry is in-memory
    only (historical behavior, unchanged).
    """

    def __init__(self, backing: str | Path | None = None) -> None:
        self.channels: dict[str, DirectChannel] = {}
        self.backing = Path(backing) if backing else None
        if self.backing is not None and self.backing.exists():
            self._load()

    @staticmethod
    def key(a: str, b: str) -> str:
        return "<->".join(sorted([a, b]))

    def _persist(self) -> None:
        if self.backing is None:
            return
        atomic_write_text(
            self.backing,
            json.dumps({"channels": self.inventory()}, indent=2, sort_keys=True) + "\n",
        )

    def _load(self) -> None:
        assert self.backing is not None
        try:
            doc = json.loads(self.backing.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"channels file {self.backing} unreadable ({exc}); torn "
                f"files are the disk-loss class (out of scope): restore "
                f"from backup, never hand-edit"
            ) from exc
        channels = doc.get("channels")
        if not isinstance(channels, dict):
            raise ValueError(
                f"channels file {self.backing} has no channels object; "
                f"torn files are the disk-loss class (out of scope)"
            )
        for name, data in channels.items():
            if not isinstance(data, dict):
                raise ValueError(
                    f"channels file {self.backing}: channel {name!r} is not an object"
                )
            chan = DirectChannel(name, self._persist)
            try:
                chan.direct_bytes = int(data["direct_bytes"])
                chan.n = int(data["messages"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"channels file {self.backing}: channel {name!r} "
                    f"has bad counters ({exc})"
                ) from exc
            self.channels[name] = chan

    def get(self, a: str, b: str) -> DirectChannel:
        k = self.key(a, b)
        if k not in self.channels:
            self.channels[k] = DirectChannel(k, self._persist)
            self._persist()
        return self.channels[k]

    def remove(self, a: str, b: str) -> DirectChannel:
        k = self.key(a, b)
        chan = self.channels.pop(k)
        chan.removed = True
        self._persist()
        return chan

    def inventory(self) -> dict:
        return {
            k: {"direct_bytes": c.direct_bytes, "messages": c.n}
            for k, c in sorted(self.channels.items())
        }


# ------------------------------------------------------------- setup


def world_record(
    state_dir: Path,
    world_id: str,
    caps: list[tuple[str, str]],
    reps: list[tuple[str, str]],
    custodians: dict | None = None,
    authorities: list | None = None,
    lineage: list | None = None,
    procedures: list | None = None,
) -> MiniWorldRecord:
    return MiniWorldRecord(
        world_id=world_id,
        lineage=list(lineage or [("host", "created", "anima-substrate-0.1.0")]),
        code_ref=f"{CODE_REF}:{world_id}",
        instance_state_dir=str(Path(state_dir) / world_id),
        custodians=dict(custodians or {}),
        capabilities=[MiniCapability(n, v) for n, v in caps],
        representations=[MiniRepresentation(n, v) for n, v in reps],
        authorities=list(authorities or []),
        procedures=[dict(t) for t in (procedures or [])],
    )


def setup_host(root: Path, worlds: list[MiniWorldRecord]) -> MiniHost:
    host = MiniHost(root / "state", root / "ledger.jsonl")
    for rec in worlds:
        host.create_world(rec, "host", grant_limits=dict(GRANT_LIMITS))
        host.transition(rec.world_id, "active", "host", reason="setup")
    return host


def rebuild_records(root: Path, worlds: list[MiniWorldRecord]) -> list[MiniWorldRecord]:
    """Fresh descriptors for reopen (same bytes as setup: verifiable)."""
    return [
        world_record(
            root / "state",
            r.world_id,
            [(c.name, c.version) for c in r.capabilities],
            [(x.name, x.version) for x in r.representations],
            dict(r.custodians),
            list(r.authorities),
            copy.deepcopy(r.lineage),
            copy.deepcopy(r.procedures or []),
        )
        for r in worlds
    ]


def write_json(path: Path, obj: dict) -> str:
    """Crash-atomic JSON write (R3: via temp + os.replace)."""
    return atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def finish_worlds(host: MiniHost, world_ids: list[str], reason: str) -> dict:
    """Settle-then-dissolve every world; verify conservation + 0 stranded.

    Successor-003 (R1): ATOMIC on refusal. Phase 1 validates the whole
    batch before ANY dissolve: the ledger must already conserve (a
    pre-existing unsettled terminal refuses here instead of stranding
    fresh dissolves), and every world must pass check_settleable
    (known, active/suspended, reattachable, zero residual). A refusal
    raises ContractViolation with ZERO partial dissolves -- only a
    `deny` entry is recorded. Phase 2 executes. Single-machine /
    no-multi-writer (LIMITS-2) means no TOCTOU between the phases;
    kill-during-execution is the defined interruption boundary (see
    docs/RECOVERY.md; recovery via api.recover_op).
    """
    try:
        host.verify_conservation()
    except ContractViolation as exc:
        host.deny("host", "settle", f"settle refused batch {list(world_ids)}: {exc}")
        raise ContractViolation(
            f"settle refused: ledger not conserving before settle "
            f"({exc}); zero worlds dissolved"
        ) from exc
    for wid in world_ids:
        try:
            host.check_settleable(wid)
        except ContractViolation as exc:
            host.deny(
                "host", "settle", f"settle refused batch {list(world_ids)}: {exc}"
            )
            raise ContractViolation(
                f"settle refused: {exc}; zero worlds dissolved"
            ) from exc
    for wid in world_ids:
        if host.worlds[wid].lifecycle == "suspended":
            host.reattach(wid, "host", reason="finish reattach")
        host.transition(wid, "dissolved", "host", reason=reason)
    stranded = {w: dict(host.holdings[w]) for w in world_ids}
    assert all(v == 0 for h in stranded.values() for v in h.values()), (
        f"stranded holdings: {stranded}"
    )
    rep = host.verify_conservation()
    assert rep["ok"]
    n_settle = sum(1 for e in host.ledger_entries() if e.get("kind") == "grant_settle")
    return {
        "stranded": stranded,
        "settled_terminals": rep["settled_terminals"],
        "grant_settle_markers": n_settle,
        "conservation_ok": True,
    }
