# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""MiniHost: a NEW minimal host implementing RECOVERY-REUSE.md section 2.

Purpose: prove the reference recovery capability is consumable by a
separate host. This module is stdlib-only and deliberately imports
NOTHING from the reference prototype package (not its HOST.py, nor its
contract.py, nor its world_explore.py) -- verifiable by searching this
file for import statements. The reuse direction is one-way: the demo
runner loads the reference recovery_lib.resume_to_verdict (see
w1h_bridge.py) and drives it through THIS host's interface.

Section-2 interface implemented:
  ledger_entries / append / invoke (success vs error distinct) / deny /
  suspend+reattach (checkpoint.json schema + identity rule) /
  transition with settle-then-move / grant_settle + host_reopen markers /
  unsettled-terminal replay check (verify_conservation) / reopen-by-replay
  with descriptor re-supply + fail-closed withholding.

Successor-003 (R1) extends the host WITHOUT changing clean-path bytes:
  check_settleable (read-only settle rehearsal) + settle_grants
  pre-validation, so a settle refusal appends only a `deny` entry and
  leaves zero partial grant_returns; plus test-only crash hooks
  (SUBSTRATE_CRASH_AFTER_APPENDS / SUBSTRATE_CRASH_AT, both unset by
  default = zero behavior change) used by the R1 fault-injection
  suite to kill a CLI child at exact ledger boundaries.

Successor-004 (R3) adds atomic_write_text (same-dir temp +
os.replace) and routes EVERY whole-file side write through it, so a
kill inside a side-file write leaves old-or-new bytes, never a
tear (F2 fix; clean-path bytes unchanged — the helper writes
exactly the bytes it is given); plus test-only write-interior
crash hooks (SUBSTRATE_CRASH_MID_APPEND /
SUBSTRATE_CRASH_MID_SIDE_WRITE, unset by default = zero behavior
change) and a classified (deny + ContractViolation) refusal when a
checkpoint is unreadable.

Successor-005 (S5) adds atomic_write_bytes (the bytes twin of
atomic_write_text, routed THROUGH it via latin-1 so the one-helper
construction proof still covers every whole-file write); a creation-fixed `procedures`
table on MiniWorldRecord (default [], never mutated; the `create`
payload and reopen verification carry it ADDITIVE-ABSENT-WHEN-
EMPTY, so sched worlds emit byte-identical ledgers to
successor-004); and two append-map-neutral invoke options
(extra payload merge + explicit invoke_id, both defaulting to the
historical behavior) used only by the procedure executor
(procedure.py). Sched clean-path bytes are unchanged.

MiniWorld is the tiny pipeline-side world handle (deterministic,
timestamp-free artifacts) that recovery_lib's phase functions drive
through duck typing (write_formulation / search_propose / search_score /
state_dir).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

CONTRACT_VERSION = "0"

VALID_LIFECYCLE = ("proposed", "active", "suspended", "dissolved", "retired")

LIFECYCLE_EDGES = {
    ("proposed", "active"),
    ("active", "suspended"),
    ("suspended", "active"),
    ("active", "dissolved"),
    ("suspended", "dissolved"),
    ("active", "retired"),
    ("dissolved", "retired"),
    ("suspended", "retired"),
}

RESOURCE_KEYS = ("max_cost_usd", "max_time_s", "max_invocations")
TERMINAL_STATES = ("dissolved", "retired")

# Same fail-closed stamp convention as the reference host: no world holds
# this authority, so invokes against descriptor-withheld capabilities are
# denied.
WITHHELD_AUTHORITY = "recovery.withheld"

# R1 fault-injection hooks (TEST-ONLY). All are unset by default, in
# which case they cost one getenv and change nothing.
#   SUBSTRATE_CRASH_AFTER_APPENDS=N ... os._exit(42) right after the Nth
#       ledger append() of this process (N >= 1). Killed state is an
#       entry-granular prefix of the op's appends -- the same state a
#       SIGKILL between two appends leaves.
#   SUBSTRATE_CRASH_AT=p1,p2 ... os._exit(42) when maybe_crash_at(point)
#       fires for a listed point (api/recover phase boundaries that sit
#       between ledger-complete and side-file writes).
#   SUBSTRATE_SYNC_AT=p1,p2 + SUBSTRATE_SYNC_FILE=path ... when
#       maybe_sync_at(point) fires for a listed point, write "ready"
#       to the file and block until the file is REMOVED (test parent
#       deletes it to release, or kills this process for a
#       guaranteed live kill). Bounded by SUBSTRATE_SYNC_TIMEOUT_S
#       (default 120); on timeout prints to stderr and proceeds, so
#       a forgotten env can never hang production forever. Unset by
#       default = zero behavior change. No other release path exists:
#       the wait ignores file CONTENT changes; only removal releases.
# R3 write-interior hooks (TEST-ONLY, same convention). A kill can
# land INSIDE a write, not just between writes: a short/partial
# write MAY leave a torn tail (close() does not make a multi-byte
# append atomic). The hooks below crash deterministically inside
# each write kind so the landing is specified + tested:
#   SUBSTRATE_CRASH_MID_APPEND=N ... on the Nth append() of this
#       process, write only the first half of the line, flush, and
#       os._exit(42): the ledger ends with a torn (unparseable) tail
#       line. Readers detect it and refuse loudly as disk-loss
#       (LIMITS-2); see TestWriteInterior.
#   SUBSTRATE_CRASH_MID_SIDE_WRITE=<basename> ... in
#       atomic_write_text, when the target's basename matches, write
#       only the first half of the bytes to the temp file, flush, and
#       os._exit(42) BEFORE the replace: the target keeps its OLD
#       bytes (or stays absent when new). Recovery converges; the
#       partial temp is a benign orphan, never read.
CRASH_EXIT_CODE = 42
_APPEND_COUNT = 0


class ContractViolation(Exception):
    """Local contract refusal (independent copy of the reference type)."""


def crash_after_appends_target() -> int | None:
    raw = os.environ.get("SUBSTRATE_CRASH_AFTER_APPENDS", "")
    if not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def maybe_crash_at(point: str) -> None:
    """Fire a named test-only crash point (no-op unless armed)."""
    wanted = os.environ.get("SUBSTRATE_CRASH_AT", "")
    if not wanted.strip():
        return
    armed = {p.strip() for p in wanted.split(",") if p.strip()}
    if point in armed:
        os._exit(CRASH_EXIT_CODE)


def maybe_sync_at(point: str) -> None:
    """Block at a named test-only sync point (no-op unless armed).

    When SUBSTRATE_SYNC_AT lists `point` and SUBSTRATE_SYNC_FILE names
    a path: write "ready" to the file, then block until the file is
    removed (parent release/kill) or SUBSTRATE_SYNC_TIMEOUT_S elapses
    (default 120; stderr note, then proceed). Lets a test kill a child
    at an exact phase boundary instead of sleeping and hoping.
    """
    wanted = os.environ.get("SUBSTRATE_SYNC_AT", "")
    sync_file = os.environ.get("SUBSTRATE_SYNC_FILE", "")
    if not wanted.strip() or not sync_file.strip():
        return
    armed = {p.strip() for p in wanted.split(",") if p.strip()}
    if point not in armed:
        return
    try:
        timeout = float(os.environ.get("SUBSTRATE_SYNC_TIMEOUT_S", "120"))
    except ValueError:
        timeout = 120.0
    target = Path(sync_file)
    atomic_write_text(target, "ready\n")
    deadline = time.monotonic() + max(timeout, 1.0)
    while target.exists():
        if time.monotonic() >= deadline:
            print(
                f"sync point {point}: release timeout; proceeding",
                file=sys.stderr,
            )
            return
        time.sleep(0.005)


def crash_mid_append_target() -> int | None:
    raw = os.environ.get("SUBSTRATE_CRASH_MID_APPEND", "")
    if not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def atomic_write_text(
    path: str | os.PathLike, text: str, encoding: str = "utf-8"
) -> str:
    """Write a whole file crash-atomically: same-dir temp + os.replace.

    Crash guarantee (R3, F2 fix): os.replace() renames atomically
    for a single file on POSIX and on NTFS, so a kill (SIGKILL or
    os._exit) at ANY point leaves the target holding either the OLD
    bytes or the NEW bytes -- never a torn (truncated/mixed) file.
    A kill between the temp write and the replace may orphan a
    `<name>.tmp-<pid>` file next to the target; orphans are never
    read by any code path and are safe to delete. No fsync is
    issued: the guarantee is atomicity across a PROCESS crash, not
    durability across OS/machine power loss (that stays the
    disk-loss class, LIMITS-2, out of scope). Uses only os/pathlib
    (no new imports; the stdlib-only pin still holds).
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f"{target.name}.tmp-{os.getpid()}"
    want = os.environ.get("SUBSTRATE_CRASH_MID_SIDE_WRITE", "")
    if want.strip() and target.name == want.strip():
        with open(tmp, "w", encoding=encoding) as fh:
            fh.write(text[: max(1, len(text) // 2)])
            fh.flush()
        os._exit(CRASH_EXIT_CODE)
    with open(tmp, "w", encoding=encoding) as fh:
        fh.write(text)
    os.replace(tmp, target)
    return str(target)


def atomic_write_bytes(path: str | os.PathLike, data: bytes) -> str:
    """Bytes twin of atomic_write_text (S5 §1.3/§1.8).

    Routes THROUGH atomic_write_text via latin-1 (which round-trips
    every byte value 1:1, so the disk bytes are exactly `data`):
    same-dir temp + os.replace, same old-or-new crash guarantee (no
    fsync; power loss stays the disk-loss class, LIMITS-2), same
    test-only SUBSTRATE_CRASH_MID_SIDE_WRITE hook. Routing through
    the one helper keeps the carried construction proof ("every
    whole-file write lands via atomic_write_text") covering byte
    writes too — there is still exactly one temp+replace
    implementation in this file.
    """
    return atomic_write_text(path, data.decode("latin-1"), encoding="latin-1")


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def require_contract_version(value: str, what: str) -> None:
    if value != CONTRACT_VERSION:
        raise ContractViolation(
            f"{what}: unknown contract_version {value!r} "
            f"(only '0' understood); refusing, not guessing"
        )


def check_lifecycle_edge(frm: str, to: str, what: str) -> None:
    if (frm, to) not in LIFECYCLE_EDGES:
        raise ContractViolation(f"{what}: lifecycle edge {frm} -> {to} not allowed")


def _zero_holdings() -> dict:
    return {"max_cost_usd": 0.0, "max_time_s": 0.0, "max_invocations": 0}


def _limits_normalized(limits: dict) -> dict:
    out = _zero_holdings()
    for key in RESOURCE_KEYS:
        if key in limits and limits[key] is not None:
            out[key] = limits[key]
    return out


@dataclass(frozen=True)
class MiniCapability:
    name: str
    version: str
    required_authority: str = ""


@dataclass(frozen=True)
class MiniRepresentation:
    name: str
    version: str


@dataclass
class MiniWorldRecord:
    world_id: str
    code_ref: str
    instance_state_dir: str
    custodians: dict = field(default_factory=dict)
    capabilities: list = field(default_factory=list)  # list[MiniCapability]
    representations: list = field(default_factory=list)  # list[MiniRepresentation]
    lifecycle: str = "proposed"
    authorities: list = field(default_factory=list)
    lineage: list = field(default_factory=list)
    contract_version: str = CONTRACT_VERSION
    # S5: creation-fixed procedure table (list of
    # {name, bundle_sha256, manifest_ref, steps}); default [] for all
    # sched worlds; never mutated after creation (same rule as
    # caps/reps — OP-3.1). ledger + specs carry it
    # additive-absent-when-empty (R-A).
    procedures: list = field(default_factory=list)  # list[dict]

    def validate(self) -> None:
        require_contract_version(self.contract_version, f"world {self.world_id}")
        if not self.world_id:
            raise ContractViolation("world needs world_id")
        if self.lifecycle not in VALID_LIFECYCLE:
            raise ContractViolation(f"world {self.world_id}: bad lifecycle state")
        if not self.instance_state_dir:
            raise ContractViolation(f"world {self.world_id}: needs instance_state_dir")
        if self.procedures is None:
            raise ContractViolation(
                f"world {self.world_id}: procedures must be present "
                f"(default [], never None)"
            )


class MiniHost:
    """Registry + ledger + accountable invocation. All state under state_dir."""

    def __init__(
        self,
        state_dir: str | os.PathLike,
        ledger_path: str | os.PathLike,
        root_holdings: dict | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = Path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ledger_path.exists():
            atomic_write_text(self.ledger_path, "")
        self.worlds: dict[str, MiniWorldRecord] = {}
        self.holdings: dict[str, dict] = {}
        self.holdings_initial: dict[str, dict] = {}
        self.grants_out: dict[str, list[dict]] = {}
        self.consumed: dict[str, dict] = {}
        self.relationships: dict[str, dict] = {}
        self._seq = 0
        self._retired_ids: set[str] = set()
        root = dict(_zero_holdings())
        root.update(
            root_holdings
            or {"max_cost_usd": 10.0, "max_time_s": 600.0, "max_invocations": 1000}
        )
        self.holdings["host"] = dict(root)
        self.holdings_initial["host"] = dict(root)
        self.consumed["host"] = _zero_holdings()
        self.append("host_init", {"root_holdings": root}, actor="host")

    # -- ledger ------------------------------------------------------
    def append(self, kind: str, payload: dict, actor: str) -> dict:
        """Monotonic-seq append (section-2 primitive)."""
        global _APPEND_COUNT
        self._seq += 1
        entry = {
            "seq": self._seq,
            "at": utcnow(),
            "kind": kind,
            "contract_version": CONTRACT_VERSION,
            "actor": actor,
            "payload": payload,
        }
        line = json.dumps(entry, sort_keys=True) + "\n"
        mid = crash_mid_append_target()
        if mid is not None and _APPEND_COUNT + 1 == mid:
            with open(self.ledger_path, "a", encoding="utf-8") as fh:
                fh.write(line[: max(1, len(line) // 2)])
                fh.flush()
            os._exit(CRASH_EXIT_CODE)
        with open(self.ledger_path, "a", encoding="utf-8") as fh:
            fh.write(line)
        _APPEND_COUNT += 1
        target = crash_after_appends_target()
        if target is not None and _APPEND_COUNT >= target:
            os._exit(CRASH_EXIT_CODE)
        return entry

    def ledger_entries(self) -> list[dict]:
        out = []
        with open(self.ledger_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def deny(
        self, actor: str, action: str, reason: str, detail: dict | None = None
    ) -> dict:
        payload = {"action": action, "reason": reason}
        if detail:
            payload.update(detail)
        return self.append("deny", payload, actor=actor)

    # -- worlds ------------------------------------------------------
    def create_world(
        self, record: MiniWorldRecord, creator: str, grant_limits: dict | None = None
    ) -> MiniWorldRecord:
        record.validate()
        if record.world_id in self.worlds or record.world_id in self._retired_ids:
            self.deny(
                creator,
                "world.create",
                f"world_id {record.world_id!r} already used (ids never reused)",
            )
            raise ContractViolation(f"world_id {record.world_id!r} already used")
        for other in self.worlds.values():
            if (
                Path(other.instance_state_dir).resolve()
                == Path(record.instance_state_dir).resolve()
            ):
                self.deny(
                    creator,
                    "world.create",
                    "state dir already owned by " + other.world_id,
                )
                raise ContractViolation("distinct worlds MUST NOT share a state dir")
        if creator != "host":
            parent = self.worlds.get(creator)
            if parent is None:
                self.deny(creator, "world.create", f"unknown creator {creator!r}")
                raise ContractViolation(f"unknown creator {creator!r}")
            if "world.create" not in parent.authorities:
                self.deny(
                    creator, "world.create", f"{creator!r} lacks world.create authority"
                )
                raise ContractViolation(f"{creator!r} lacks world.create authority")
        Path(record.instance_state_dir).mkdir(parents=True, exist_ok=True)
        self.worlds[record.world_id] = record
        self.holdings[record.world_id] = _zero_holdings()
        self.holdings_initial[record.world_id] = _zero_holdings()
        self.consumed[record.world_id] = _zero_holdings()
        create_payload = {
            "world_id": record.world_id,
            "creator": creator,
            "code_ref": record.code_ref,
            "instance_state_dir": record.instance_state_dir,
            "custodians": record.custodians,
            "authorities": record.authorities,
            "capabilities": [c.name + "@" + c.version for c in record.capabilities],
            "representations": [
                r.name + "@" + r.version for r in record.representations
            ],
            "lineage": record.lineage,
        }
        if record.procedures:
            # S5 R-A: additive-absent-when-empty — sched creates emit
            # byte-identical payloads to successor-004 (no
            # `procedures: []` key); proc worlds pin the table.
            create_payload["procedures"] = [
                {
                    "name": t.get("name", ""),
                    "bundle_sha256": t.get("bundle_sha256", ""),
                    "manifest_ref": t.get("manifest_ref", ""),
                    "steps": list(t.get("steps", [])),
                }
                for t in record.procedures
            ]
        self.append("create", create_payload, actor=creator)
        if grant_limits:
            self.grant(
                creator,
                record.world_id,
                grant_limits,
                authority=list(record.authorities),
                grant_id=f"g-init-{record.world_id}",
            )
        return record

    @classmethod
    def reopen(
        cls,
        state_dir: str | os.PathLike,
        ledger_path: str | os.PathLike,
        records: list[MiniWorldRecord] | None = None,
        actor: str = "host",
        reason: str = "reopen after interruption",
    ) -> "MiniHost":
        """Rebuild a live MiniHost over an existing state dir + ledger.

        Same R-REOPEN rules as the reference host: registry/holdings/grants/
        lifecycle rebuilt purely by replaying the ledger in seq order (no
        lifecycle edges traversed, no second host_init); supplied records are
        verified against the ledger (world known, code_ref equal,
        name@version sets equal); worlds without supplied records come back
        ledger-only with authority WITHHELD (fail closed); one balance-neutral
        host_reopen marker is appended.
        """
        obj = cls.__new__(cls)
        obj.state_dir = Path(state_dir)
        obj.ledger_path = Path(ledger_path)
        if not obj.ledger_path.exists():
            raise ContractViolation(f"reopen: missing ledger {obj.ledger_path}")
        obj.worlds = {}
        obj.holdings = {}
        obj.holdings_initial = {}
        obj.grants_out = {}
        obj.consumed = {}
        obj.relationships = {}
        obj._seq = 0
        obj._retired_ids = set()
        creates: dict[str, dict] = {}
        last_lifecycle: dict[str, str] = {}
        custodians: dict[str, dict] = {}
        n_replayed = 0
        for e in obj.ledger_entries():
            n_replayed += 1
            obj._seq = max(obj._seq, int(e.get("seq", 0)))
            kind, payload = e.get("kind"), e.get("payload", {})
            if kind == "host_init":
                root = _limits_normalized(payload.get("root_holdings", {}))
                obj.holdings["host"] = dict(root)
                obj.holdings_initial["host"] = dict(root)
                obj.consumed.setdefault("host", _zero_holdings())
            elif kind == "create":
                wid = payload.get("world_id", "")
                creates[wid] = dict(payload)
                custodians[wid] = dict(payload.get("custodians", {}))
                obj.holdings.setdefault(wid, _zero_holdings())
                obj.holdings_initial.setdefault(wid, _zero_holdings())
                obj.consumed.setdefault(wid, _zero_holdings())
            elif kind == "lifecycle":
                wid = payload.get("world_id", "")
                last_lifecycle[wid] = payload.get("to", "")
                if payload.get("to") == "retired":
                    obj._retired_ids.add(wid)
            elif kind == "grant":
                frm, to = payload.get("from", ""), payload.get("to", "")
                limits = _limits_normalized(payload.get("limits", {}))
                for key in RESOURCE_KEYS:
                    obj.holdings.setdefault(frm, _zero_holdings())[key] -= limits[key]
                    obj.holdings.setdefault(to, _zero_holdings())[key] += limits[key]
                obj.grants_out.setdefault(frm, []).append(
                    {
                        "grant_id": payload.get("grant_id", ""),
                        "from": frm,
                        "to": to,
                        "limits": limits,
                        "authority": payload.get("authority", []),
                        "at": payload.get("at", ""),
                        "expires": payload.get("expires"),
                    }
                )
            elif kind == "grant_return":
                frm, to = payload.get("from", ""), payload.get("to", "")
                amounts = _limits_normalized(payload.get("amounts", {}))
                for key in RESOURCE_KEYS:
                    obj.holdings.setdefault(frm, _zero_holdings())[key] -= amounts[key]
                    obj.holdings.setdefault(to, _zero_holdings())[key] += amounts[key]
            elif kind == "consume":
                wid = payload.get("world_id", "")
                for key in RESOURCE_KEYS:
                    use = payload.get(key, 0)
                    obj.holdings.setdefault(wid, _zero_holdings())[key] -= use
                    obj.consumed.setdefault(wid, _zero_holdings())[key] += use
            elif kind == "transfer":
                frm, to = payload.get("from", ""), payload.get("to", "")
                state_class = payload.get("state_class", "")
                if frm in custodians:
                    custodians[frm].pop(state_class, None)
                if to != "host" and to in custodians:
                    custodians[to][state_class] = to
            elif kind == "relationship":
                obj.relationships.setdefault(payload.get("rel_id", ""), {})[
                    payload.get("version", "")
                ] = dict(payload)
            # grant_settle / host_reopen / checkpoint / reattach / invoke /
            # deny: balance-neutral or registry-neutral; ignored by replay.
        obj.holdings.setdefault("host", _zero_holdings())
        obj.holdings_initial.setdefault("host", _zero_holdings())
        obj.consumed.setdefault("host", _zero_holdings())

        supplied = {r.world_id: r for r in (records or [])}
        for wid in supplied:
            if wid not in creates:
                obj.deny(
                    actor,
                    "reopen",
                    f"supplied record for unknown world {wid!r} "
                    f"(never created in this ledger)",
                )
                raise ContractViolation(
                    f"reopen: {wid!r} was never created in this ledger; "
                    f"refusing, not guessing"
                )
        for wid, payload in creates.items():
            if wid in supplied:
                rec = supplied[wid]
                rec.validate()
                problems = []
                if rec.code_ref != payload.get("code_ref"):
                    problems.append(
                        f"code_ref ledger={payload.get('code_ref')!r} "
                        f"supplied={rec.code_ref!r}"
                    )
                ledger_caps = set(payload.get("capabilities", []))
                supplied_caps = {c.name + "@" + c.version for c in rec.capabilities}
                if ledger_caps != supplied_caps:
                    problems.append(
                        f"capabilities ledger={sorted(ledger_caps)} "
                        f"supplied={sorted(supplied_caps)}"
                    )
                ledger_reps = set(payload.get("representations", []))
                supplied_reps = {r.name + "@" + r.version for r in rec.representations}
                if ledger_reps != supplied_reps:
                    problems.append(
                        f"representations ledger={sorted(ledger_reps)} "
                        f"supplied={sorted(supplied_reps)}"
                    )
                # S5: procedure-table equality (absent ≡ empty, R-A).
                ledger_procs = [
                    json.dumps(t, sort_keys=True) for t in payload.get("procedures", [])
                ]
                supplied_procs = [
                    json.dumps(
                        {
                            "name": t.get("name", ""),
                            "bundle_sha256": t.get("bundle_sha256", ""),
                            "manifest_ref": t.get("manifest_ref", ""),
                            "steps": list(t.get("steps", [])),
                        },
                        sort_keys=True,
                    )
                    for t in (rec.procedures or [])
                ]
                if ledger_procs != supplied_procs:
                    problems.append(
                        f"procedures ledger={ledger_procs} supplied={supplied_procs}"
                    )
                if problems:
                    obj.deny(
                        actor,
                        "reopen",
                        f"record mismatch for {wid!r}: " + "; ".join(problems),
                    )
                    raise ContractViolation(
                        f"reopen: supplied record for {wid!r} does not match "
                        f"ledger (" + "; ".join(problems) + "); refusing, not guessing"
                    )
                rec.lifecycle = last_lifecycle.get(wid, "proposed")
                rec.custodians = dict(custodians.get(wid, {}))
                obj.worlds[wid] = rec
            else:
                skel_caps = []
                for item in payload.get("capabilities", []):
                    name, _, version = item.partition("@")
                    skel_caps.append(
                        MiniCapability(
                            name=name,
                            version=version,
                            required_authority=WITHHELD_AUTHORITY,
                        )
                    )
                skel_reps = []
                for item in payload.get("representations", []):
                    name, _, version = item.partition("@")
                    skel_reps.append(MiniRepresentation(name=name, version=version))
                obj.worlds[wid] = MiniWorldRecord(
                    world_id=wid,
                    lineage=list(payload.get("lineage", [])),
                    code_ref=payload.get("code_ref", ""),
                    instance_state_dir=payload.get("instance_state_dir", ""),
                    custodians=dict(custodians.get(wid, {})),
                    capabilities=skel_caps,
                    representations=skel_reps,
                    lifecycle=last_lifecycle.get(wid, "proposed"),
                    authorities=list(payload.get("authorities", [])),
                    procedures=[dict(t) for t in payload.get("procedures", [])],
                )
        obj.append(
            "host_reopen",
            {
                "reason": reason,
                "ledger_entries_replayed": n_replayed,
                "worlds": sorted(obj.worlds),
                "descriptors_supplied": sorted(supplied),
                "descriptors_withheld": sorted(set(obj.worlds) - set(supplied)),
            },
            actor=actor,
        )
        return obj

    # -- grants / conservation ---------------------------------------
    def grant(
        self,
        frm: str,
        to: str,
        limits: dict,
        authority: list,
        grant_id: str,
        expires: str | None = None,
    ) -> dict:
        if frm != "host" and frm not in self.worlds:
            self.deny(frm, "grant", f"unknown grantor {frm!r}")
            raise ContractViolation(f"unknown grantor {frm!r}")
        if to not in self.worlds:
            self.deny(frm, "grant", f"unknown grantee {to!r}")
            raise ContractViolation(f"unknown grantee {to!r}")
        if frm != "host" and "grant.delegate" not in self.worlds[frm].authorities:
            self.deny(frm, "grant", f"{frm!r} lacks grant.delegate authority")
            raise ContractViolation(f"{frm!r} lacks grant.delegate authority")
        norm = _limits_normalized(limits)
        avail = self.holdings.get(frm, _zero_holdings())
        for key in RESOURCE_KEYS:
            if norm[key] > avail[key] + 1e-9:
                self.deny(
                    frm,
                    "grant",
                    f"grant {grant_id} exceeds holding: "
                    f"{key} {norm[key]} > {avail[key]}",
                    {"grant_id": grant_id, "to": to},
                )
                raise ContractViolation(
                    "delegation never manufactures resources: "
                    f"{key} {norm[key]} > available {avail[key]}"
                )
        for key in RESOURCE_KEYS:
            self.holdings[frm][key] -= norm[key]
            self.holdings[to][key] += norm[key]
        rec = {
            "grant_id": grant_id,
            "from": frm,
            "to": to,
            "limits": norm,
            "authority": authority,
            "at": utcnow(),
            "expires": expires,
        }
        self.grants_out.setdefault(frm, []).append(rec)
        self.append(
            "grant",
            dict(
                rec,
                parent_holding_after=dict(self.holdings[frm]),
                child_holding_after=dict(self.holdings[to]),
            ),
            actor=frm,
        )
        return rec

    def return_grant(self, grant_id: str, frm: str, amounts: dict, reason: str) -> dict:
        found = None
        for parent, grants in self.grants_out.items():
            for g in grants:
                if g["grant_id"] == grant_id and g["to"] == frm:
                    found = (parent, g)
        if found is None:
            self.deny(frm, "grant_return", f"unknown grant {grant_id!r}")
            raise ContractViolation(f"unknown grant {grant_id!r}")
        parent, _g = found
        norm = _limits_normalized(amounts)
        for key in RESOURCE_KEYS:
            if norm[key] > self.holdings[frm][key] + 1e-9:
                self.deny(frm, "grant_return", f"return exceeds holding for {key}")
                raise ContractViolation("cannot return more than held")
        for key in RESOURCE_KEYS:
            self.holdings[frm][key] -= norm[key]
            self.holdings[parent][key] += norm[key]
        return self.append(
            "grant_return",
            {
                "grant_id": grant_id,
                "from": frm,
                "to": parent,
                "amounts": norm,
                "reason": reason,
            },
            actor=frm,
        )

    def check_settleable(self, world_id: str) -> dict:
        """Read-only rehearsal of settling world_id: no mutation, no append.

        Returns {"world_id", "needs_reattach", "grants", "returns",
        "amounts_total"} mirroring exactly what settle_grants would do.
        Raises ContractViolation (LOUD, but itself side-effect-free) when
        the world is unknown, not in active/suspended, would need a
        reattach that cannot succeed (missing/unreadable/mismatched
        checkpoint), or would leave residual holdings. Successor-003
        (R1 atomic settle): every settle path rehearses the WHOLE batch
        through this check before the first grant_return is appended, so
        a refusal leaves zero partial dissolves and zero partial returns.
        """
        world = self.worlds.get(world_id)
        if world is None:
            raise ContractViolation(f"settle refused: unknown world {world_id!r}")
        needs_reattach = world.lifecycle == "suspended"
        if world.lifecycle not in ("active", "suspended"):
            raise ContractViolation(
                f"settle refused: {world_id!r} is {world.lifecycle}, "
                f"not active/suspended"
            )
        if needs_reattach:
            ckpt_path = Path(world.instance_state_dir) / "checkpoint.json"
            if not ckpt_path.exists():
                raise ContractViolation(
                    f"settle refused: {world_id!r} is suspended with a "
                    f"missing checkpoint (reattach would fail)"
                )
            try:
                checkpoint = json.loads(ckpt_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ContractViolation(
                    f"settle refused: {world_id!r} checkpoint unreadable "
                    f"({exc}); reattach would fail"
                )
            require_contract_version(
                checkpoint.get("contract_version", "?"), f"checkpoint {world_id}"
            )
            if (
                checkpoint.get("world_id") != world_id
                or checkpoint.get("code_ref") != world.code_ref
            ):
                raise ContractViolation(
                    f"settle refused: {world_id!r} checkpoint identity "
                    f"mismatch (reattach would fail)"
                )
        grants_to = [
            g
            for grants in self.grants_out.values()
            for g in grants
            if g["to"] == world_id
        ]
        held = dict(self.holdings.get(world_id, _zero_holdings()))
        plan: list[dict] = []
        for g in grants_to:
            if not any(held[key] > 1e-9 for key in RESOURCE_KEYS):
                break
            amounts = {
                key: min(held[key], g["limits"].get(key, 0)) for key in RESOURCE_KEYS
            }
            if any(amounts[key] > 1e-9 for key in RESOURCE_KEYS):
                plan.append({"grant_id": g["grant_id"], "amounts": amounts})
                for key in RESOURCE_KEYS:
                    held[key] -= amounts[key]
        if any(held[key] > 1e-6 for key in RESOURCE_KEYS):
            raise ContractViolation(
                f"settle refused: residual holdings on {world_id!r} "
                f"({held}); refusing, not stranding funds"
            )
        totals = _zero_holdings()
        for step in plan:
            for key in RESOURCE_KEYS:
                totals[key] += step["amounts"][key]
        return {
            "world_id": world_id,
            "needs_reattach": needs_reattach,
            "grants": [g["grant_id"] for g in grants_to],
            "returns": plan,
            "amounts_total": totals,
        }

    def settle_grants(self, world_id: str, actor: str, reason: str) -> list[str]:
        """Return ALL unused holdings of world_id to its grantors, then mark.

        One grant_return per grant with funds to move (amounts distributed as
        min(held, grant_limits)), then a balance-neutral grant_settle marker.
        Successor-003: pre-validated through check_settleable BEFORE the
        first grant_return is appended, so a refusal records only a `deny`
        entry and leaves zero partial returns (previously partial returns
        could precede the refusal). Clean-path ledger bytes are unchanged.
        """
        try:
            plan = self.check_settleable(world_id)
        except ContractViolation as exc:
            self.deny(actor, "grant_settle", str(exc), {"world_id": world_id})
            raise
        totals = _zero_holdings()
        for step in plan["returns"]:
            self.return_grant(
                step["grant_id"],
                world_id,
                step["amounts"],
                reason=f"settle-on-terminal: {reason}",
            )
            for key in RESOURCE_KEYS:
                totals[key] += step["amounts"][key]
        self.append(
            "grant_settle",
            {
                "world_id": world_id,
                "grants": plan["grants"],
                "reason": reason,
                "amounts_total": totals,
            },
            actor=actor,
        )
        return plan["grants"]

    def consume(
        self,
        world_id: str,
        cost_usd: float = 0.0,
        time_s: float = 0.0,
        invocations: int = 0,
        evidence_ref: str = "",
    ) -> dict:
        use = {
            "max_cost_usd": cost_usd,
            "max_time_s": time_s,
            "max_invocations": invocations,
        }
        avail = self.holdings.get(world_id)
        if avail is None:
            self.deny(world_id, "consume", f"unknown world {world_id!r}")
            raise ContractViolation(f"unknown world {world_id!r}")
        for key in RESOURCE_KEYS:
            if use[key] > avail[key] + 1e-9:
                self.deny(
                    world_id,
                    "consume",
                    f"would exceed grant: {key} {use[key]} > {avail[key]}",
                )
                raise ContractViolation(f"grant exceeded for {world_id}: {key}")
        for key in RESOURCE_KEYS:
            self.holdings[world_id][key] -= use[key]
            self.consumed[world_id][key] += use[key]
        return self.append(
            "consume",
            dict(use, world_id=world_id, evidence_ref=evidence_ref),
            actor=world_id,
        )

    def verify_conservation(self) -> dict:
        """Replay the ledger; balances must stay >= 0; terminals need markers.

        grant_settle/host_reopen markers are balance-neutral but envelope-
        checked; a world whose LAST lifecycle state is dissolved/retired
        without a grant_settle marker raises "unsettled terminal".
        """
        bal: dict[str, dict] = {}
        consumed: dict[str, dict] = {}
        last_lifecycle: dict[str, str] = {}
        settled: set[str] = set()

        def B(w: str) -> dict:
            return bal.setdefault(w, _zero_holdings())

        def C(w: str) -> dict:
            return consumed.setdefault(w, _zero_holdings())

        for e in self.ledger_entries():
            k, p = e["kind"], e["payload"]
            if k == "host_init":
                for key in RESOURCE_KEYS:
                    B("host")[key] = p["root_holdings"].get(key, 0)
            elif k == "grant":
                for key in RESOURCE_KEYS:
                    B(p["from"])[key] -= p["limits"][key]
                    B(p["to"])[key] += p["limits"][key]
            elif k == "grant_return":
                for key in RESOURCE_KEYS:
                    B(p["from"])[key] -= p["amounts"][key]
                    B(p["to"])[key] += p["amounts"][key]
            elif k == "consume":
                for key in RESOURCE_KEYS:
                    B(p["world_id"])[key] -= p[key]
                    C(p["world_id"])[key] += p[key]
            elif k == "grant_settle":
                if e.get("contract_version") != CONTRACT_VERSION:
                    raise ContractViolation(
                        f"grant_settle at seq {e['seq']}: bad envelope; "
                        f"refusing, not guessing"
                    )
                for f in ("world_id", "grants", "reason"):
                    if f not in p:
                        raise ContractViolation(
                            f"grant_settle at seq {e['seq']}: missing {f!r}"
                        )
                settled.add(p["world_id"])
            elif k == "host_reopen":
                if e.get("contract_version") != CONTRACT_VERSION:
                    raise ContractViolation(
                        f"host_reopen at seq {e['seq']}: bad envelope; "
                        f"refusing, not guessing"
                    )
            elif k == "lifecycle":
                last_lifecycle[p["world_id"]] = p["to"]
            for w, b in bal.items():
                for key in RESOURCE_KEYS:
                    if b[key] < -1e-9:
                        raise ContractViolation(
                            f"conservation violated at seq {e['seq']}: "
                            f"{w}.{key}={b[key]}"
                        )
        for wid, state in last_lifecycle.items():
            if state in TERMINAL_STATES and wid not in settled:
                raise ContractViolation(
                    f"unsettled terminal: world {wid!r} ended in {state!r} "
                    f"with no grant_settle marker; holdings may be stranded"
                )
        total_held = {key: sum(b[key] for b in bal.values()) for key in RESOURCE_KEYS}
        total_consumed = {
            key: sum(c[key] for c in consumed.values()) for key in RESOURCE_KEYS
        }
        total_initial = dict(self.holdings_initial.get("host", _zero_holdings()))
        for key in RESOURCE_KEYS:
            if abs(total_held[key] + total_consumed[key] - total_initial[key]) > 1e-6:
                raise ContractViolation(f"global conservation failed for {key}")
        return {
            "balances": bal,
            "consumed": consumed,
            "ok": True,
            "settled_terminals": sorted(settled),
        }

    # -- invoke ------------------------------------------------------
    def invoke(
        self,
        caller: str,
        callee: str,
        capability: str,
        version: str,
        args_ref: str,
        fn,
        cost_usd: float = 0.0,
        time_s: float = 0.0,
        extra: dict | None = None,
        invoke_id: str | None = None,
    ) -> dict:
        """Accountable call. Success records result_ref; failure records error.

        The success/error distinction is what lets resume tell "ran ok" from
        "ran and failed" from "never ran". Budget is consumed only on success
        (a failed call burns nothing but is still ledger-recorded).

        S5 options (procedure executor only; both default to the
        historical behavior, so sched invoke bytes are unchanged):
        `extra` is merged into the invoke payload on BOTH the success
        and error legs (the `proc` block); `invoke_id` overrides the
        generated id so a `proc_begin` entry and its later `invoke`
        (normal or adopt-path) share one stable id.
        """
        if caller != "host" and caller not in self.worlds:
            self.deny(caller, "invoke", f"unknown caller {caller!r}")
            raise ContractViolation(f"unknown caller {caller!r}")
        target = self.worlds.get(callee)
        if target is None:
            self.deny(caller, "invoke", f"unknown callee {callee!r}")
            raise ContractViolation(f"unknown callee {callee!r}")
        if target.lifecycle != "active":
            self.deny(
                caller,
                "invoke",
                f"callee {callee!r} not active (state={target.lifecycle})",
            )
            raise ContractViolation(f"callee {callee!r} not active")
        cap = next(
            (
                c
                for c in target.capabilities
                if c.name == capability and c.version == version
            ),
            None,
        )
        if cap is None:
            self.deny(
                caller,
                "invoke",
                f"{callee!r} does not advertise {capability}@{version}",
            )
            raise ContractViolation(
                f"{callee!r} does not advertise {capability}@{version}"
            )
        if cap.required_authority:
            if (
                caller != "host"
                and cap.required_authority not in self.worlds[caller].authorities
            ):
                self.deny(
                    caller,
                    "invoke",
                    f"{caller!r} lacks {cap.required_authority} for {capability}",
                )
                raise ContractViolation(f"{caller!r} lacks {cap.required_authority}")
        if capability == "proc.exec" and (not extra or "proc" not in extra):
            # S5: the procedure envelope is host-enforced — proc.exec
            # is invocable only via run_procedure / adopt-path
            # recovery (which always attach the `proc` block).
            # Sched invokes never name this capability: zero
            # clean-path effect.
            self.deny(
                caller,
                "invoke",
                f"{capability}@{version} requires the procedure "
                f"envelope (use run_procedure); direct invoke denied",
            )
            raise ContractViolation(
                f"{capability}@{version} requires the procedure "
                f"envelope (use run_procedure); direct invoke denied"
            )
        avail = self.holdings.get(caller, _zero_holdings())
        need = {"max_cost_usd": cost_usd, "max_time_s": time_s, "max_invocations": 1}
        for key in RESOURCE_KEYS:
            if need[key] > avail[key] + 1e-9:
                self.deny(
                    caller,
                    "invoke",
                    f"would exceed grant: {key} {need[key]} > {avail[key]}",
                )
                raise ContractViolation(f"grant exceeded for {caller}: {key}")
        if invoke_id is None:
            invoke_id = f"inv-{self._seq + 1:06d}"
        try:
            result_ref = fn()
        except Exception as exc:  # recorded, then re-raised
            payload = {
                "invoke_id": invoke_id,
                "caller": caller,
                "callee": callee,
                "capability": capability,
                "version": version,
                "args_ref": args_ref,
                "error": f"{type(exc).__name__}: {exc}",
                "cost": {"cost_usd": cost_usd, "time_s": time_s},
            }
            if extra:
                payload.update(extra)
            self.append("invoke", payload, actor=caller)
            raise
        self.consume(
            caller,
            cost_usd=cost_usd,
            time_s=time_s,
            invocations=1,
            evidence_ref=invoke_id,
        )
        payload = {
            "invoke_id": invoke_id,
            "caller": caller,
            "callee": callee,
            "capability": capability,
            "version": version,
            "args_ref": args_ref,
            "result_ref": result_ref,
            "cost": {"cost_usd": cost_usd, "time_s": time_s},
        }
        if extra:
            payload.update(extra)
        return self.append("invoke", payload, actor=caller)

    # -- lifecycle ---------------------------------------------------
    def transition(self, world_id: str, to_state: str, actor: str, reason: str) -> dict:
        world = self.worlds.get(world_id)
        if world is None:
            self.deny(actor, "lifecycle", f"unknown world {world_id!r}")
            raise ContractViolation(f"unknown world {world_id!r}")
        try:
            check_lifecycle_edge(world.lifecycle, to_state, world_id)
        except ContractViolation as exc:
            self.deny(actor, "lifecycle", str(exc))
            raise
        if to_state in TERMINAL_STATES:
            # Settle-then-move: funds move while the world is still in its
            # pre-terminal state (ledger order: grant_return(s), grant_settle,
            # then lifecycle). A settle failure refuses the transition.
            self.settle_grants(world_id, actor, reason)
        frm = world.lifecycle
        world.lifecycle = to_state
        if to_state == "retired":
            self._retired_ids.add(world_id)
        return self.append(
            "lifecycle",
            {"world_id": world_id, "from": frm, "to": to_state, "reason": reason},
            actor=actor,
        )

    def suspend(
        self,
        world_id: str,
        actor: str,
        reason: str,
        pending_effects: list | None = None,
    ) -> dict:
        world = self.worlds.get(world_id)
        if world is None:
            self.deny(actor, "suspend", f"unknown world {world_id!r}")
            raise ContractViolation(f"unknown world {world_id!r}")
        checkpoint = {
            "contract_version": CONTRACT_VERSION,
            "world_id": world_id,
            "code_ref": world.code_ref,
            "capability_versions": [
                c.name + "@" + c.version for c in world.capabilities
            ],
            "representation_versions": [
                r.name + "@" + r.version for r in world.representations
            ],
            "ledger_position": self._seq,
            "pending_effects": pending_effects or [],
            "at": utcnow(),
        }
        ckpt_path = Path(world.instance_state_dir) / "checkpoint.json"
        atomic_write_text(ckpt_path, json.dumps(checkpoint, indent=2, sort_keys=True))
        self.transition(world_id, "suspended", actor, reason)
        return self.append(
            "checkpoint",
            {
                "world_id": world_id,
                "checkpoint_ref": str(ckpt_path),
                "ledger_position": self._seq - 1,
                "pending_effects": pending_effects or [],
            },
            actor=actor,
        )

    def reattach(self, world_id: str, actor: str, reason: str) -> dict:
        world = self.worlds.get(world_id)
        if world is None:
            self.deny(actor, "reattach", f"unknown world {world_id!r}")
            raise ContractViolation(f"unknown world {world_id!r}")
        if world.lifecycle != "suspended":
            self.deny(actor, "reattach", f"{world_id!r} not suspended")
            raise ContractViolation(f"{world_id!r} not suspended")
        ckpt_path = Path(world.instance_state_dir) / "checkpoint.json"
        if not ckpt_path.exists():
            self.deny(actor, "reattach", "missing checkpoint")
            raise ContractViolation("missing checkpoint")
        try:
            checkpoint = json.loads(ckpt_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            self.deny(
                actor,
                "reattach",
                f"checkpoint unreadable ({exc}); torn files are "
                f"the disk-loss class (LIMITS-2): restore from "
                f"backup, never hand-edit",
            )
            raise ContractViolation(
                f"reattach refused: checkpoint {world_id} unreadable "
                f"({exc}); torn files are the disk-loss class "
                f"(LIMITS-2): restore from backup"
            ) from exc
        require_contract_version(
            checkpoint.get("contract_version", "?"), f"checkpoint {world_id}"
        )
        if (
            checkpoint["world_id"] != world_id
            or checkpoint["code_ref"] != world.code_ref
        ):
            self.deny(actor, "reattach", "checkpoint identity mismatch")
            raise ContractViolation("checkpoint identity mismatch")
        self.transition(world_id, "active", actor, reason)
        return self.append(
            "reattach",
            {
                "world_id": world_id,
                "checkpoint_ref": str(ckpt_path),
                "restored_ledger_position": checkpoint["ledger_position"],
                "pending_effects_replayed": checkpoint["pending_effects"],
            },
            actor=actor,
        )

    # -- custody / relationships (minimal, replay-compatible) ----------
    def transfer_custody(
        self,
        state_class: str,
        frm: str,
        to: str,
        actor: str,
        reason: str,
        continuity: str,
    ) -> dict:
        if frm not in self.worlds or (to != "host" and to not in self.worlds):
            self.deny(actor, "custody.transfer", "unknown world in transfer")
            raise ContractViolation("unknown world in transfer")
        if self.worlds[frm].custodians.get(state_class) != frm:
            self.deny(
                actor,
                "custody.transfer",
                f"{frm!r} is not custodian of {state_class!r}",
            )
            raise ContractViolation(f"{frm!r} is not custodian of {state_class!r}")
        if actor != "host" and actor != frm:
            held = self.worlds.get(actor)
            if held is None or "custody.transfer" not in held.authorities:
                self.deny(
                    actor,
                    "custody.transfer",
                    f"{actor!r} lacks custody.transfer authority",
                )
                raise ContractViolation(f"{actor!r} lacks custody.transfer authority")
        del self.worlds[frm].custodians[state_class]
        if to != "host":
            self.worlds[to].custodians[state_class] = to
        return self.append(
            "transfer",
            {
                "state_class": state_class,
                "from": frm,
                "to": to,
                "reason": reason,
                "continuity": continuity,
            },
            actor=actor,
        )

    def declare_relationship(
        self, rel_id: str, version: str, participants: list, purpose: str, actor: str
    ) -> dict:
        versions = self.relationships.setdefault(rel_id, {})
        if version in versions:
            self.deny(
                actor, "relationship.declare", f"{rel_id} v{version} already declared"
            )
            raise ContractViolation(f"{rel_id} v{version} already declared")
        for pid in participants:
            if pid != "host" and pid not in self.worlds:
                self.deny(actor, "relationship.declare", f"unknown participant {pid!r}")
                raise ContractViolation(f"unknown participant {pid!r}")
        versions[version] = {"purpose": purpose, "participants": participants}
        return self.append(
            "relationship",
            {
                "rel_id": rel_id,
                "version": version,
                "participants": participants,
                "purpose": purpose,
                "mapping": {"from": "", "to": "", "ref": "", "losses": []},
                "protocol": "",
                "authority_granted": [],
                "state": "proposed",
            },
            actor=actor,
        )

    # -- helpers -------------------------------------------------------
    def store_args(self, world_id: str, name: str, payload: dict) -> str:
        world = self.worlds.get(world_id)
        base = self.state_dir if world is None else Path(world.instance_state_dir)
        path = base / "args" / f"{name}.json"
        return atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))

    @staticmethod
    def sha256_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()


class MiniWorld:
    """Tiny pipeline-side world: deterministic, timestamp-free artifacts.

    Duck-compatible with what recovery_lib's phase functions need:
    state_dir, write_formulation, search_propose, search_score. Fixed file
    names + content-derived ids keep every byte reproducible across the
    kill boundary, so "byte-identical reused artifacts" is checkable.
    """

    def __init__(self, state_dir: str | os.PathLike) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write(path: Path, obj: dict) -> str:
        return atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")

    def write_formulation(
        self, goal: str, domain: str, constraints: list, budget: dict
    ) -> str:
        return self._write(
            self.state_dir / "formulations" / "formulation.json",
            {
                "contract_version": CONTRACT_VERSION,
                "representation": "minihost-formulation/v0",
                "goal": goal,
                "domain": domain,
                "constraints": constraints,
                "budget": budget,
            },
        )

    def search_propose(self, form_ref: str, policy: dict) -> dict:
        seed = hashlib.sha256(
            Path(form_ref).read_bytes() + json.dumps(policy, sort_keys=True).encode()
        ).hexdigest()[:16]
        refs = []
        for i in range(2):
            cid = f"cand-{i}"
            refs.append(
                self._write(
                    self.state_dir / "candidates" / f"cand-{i:03d}.json",
                    {
                        "contract_version": CONTRACT_VERSION,
                        "candidate_id": cid,
                        "variant_seed": seed,
                        "formulation_ref": form_ref,
                    },
                )
            )
        return {
            "candidate_refs": refs,
            "champion_id": "cand-0",
            "engine": "minihost-stub/v0",
        }

    def search_score(self, candidate_refs: list) -> dict:
        scores = []
        for ref in candidate_refs:
            body = json.loads(Path(ref).read_text(encoding="utf-8"))
            cid = body["candidate_id"]
            digest = hashlib.sha256(Path(ref).read_bytes()).hexdigest()
            score = (int(digest[:8], 16) % 1000) / 1000.0
            sref = self._write(
                self.state_dir / "scores" / f"score-{cid}.json",
                {
                    "contract_version": CONTRACT_VERSION,
                    "candidate_id": cid,
                    "score": score,
                    "candidate_sha256": digest,
                },
            )
            scores.append({"candidate_id": cid, "score": score, "score_ref": sref})
        return {"scores": scores, "evaluator": "minihost-eval/v0"}
