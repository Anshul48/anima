# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-004 resume engine (pilot recovery lineage, rewritten).

Resume-by-skip keyed on the WORLD-CONTRACT-v1 coupling points:
- C1: success matcher = capability + args_ref + result_ref present AND
  NO payload.error; failed invokes consume nothing and never skip.
- C2: args files MUST carry formulation_ref + candidate_refs keys.
- C3: propose result_ref JSON MUST carry candidate_refs + champion_id.
  (No sched.score capability exists in this pipeline; the verify verdict
  takes its place -- see PROVENANCE.md.)
- C4: lifecycle read via host.worlds[ID].lifecycle == "active".
- C6: world.state_dir handle + formulations/*.json glob (latest by name)
  + verdicts/verdict.json (phase_verdict).

Also: capability revocation with ledger durability (LIMITS-2 scope;
revoke entries are re-applied after reopen, same replay pattern
as the host), and the
pipeline-side SchedWorld handle (MiniWorld lineage: deterministic,
timestamp-free artifacts).

Successor-005 (S5) extends the C1 matcher for procedure steps
(`proc_succeeded` / `proc_prior_bundles` / `proc_begins`, keyed on
the ledger `proc` block); the sched matcher is byte-unchanged.
Durability here (LIMITS-2 process-crash scope) means ledger-recorded
on local disk across a process crash only — no fsync is issued, so
power/media loss stays the disk-loss class (out of scope).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .minihost import MiniCapability, MiniHost, atomic_write_text

CAP_FORMULATE = "sched.formulate"
CAP_CLARIFY = "sched.clarify"
CAP_PROPOSE = "sched.propose"
CAP_VERIFY = "sched.verify"
CAP_REUSE = "sched.reuse"

REVOKED_AUTHORITY = "revocation.quarantined"


# ------------------------------------------------------- C1 matcher


def successful_invokes(entries: list[dict], capability: str) -> list[dict]:
    """C1 resume matcher: capability match + result_ref present + no error."""
    out = []
    for e in entries:
        if e.get("kind") != "invoke":
            continue
        p = e.get("payload", {})
        if p.get("capability") != capability:
            continue
        if "error" in p:
            continue
        if "args_ref" not in p or "result_ref" not in p:
            continue
        out.append(e)
    return out


def args_of(args_ref: str) -> dict:
    return json.loads(Path(args_ref).read_text(encoding="utf-8"))


# ------------------------------------------- S5 proc matcher (C1 extent)
#
# Procedure steps skip-match on (capability, bundle_sha256, idem_key,
# step) from the ledger `proc` block — the C1 success/error
# distinction (result_ref present, no error) unchanged, the sched
# (capability, task_id, step) matcher byte-unchanged (S5-A1).


def proc_succeeded(host) -> set[tuple[str, str, str]]:
    """(bundle_sha256, idem_key, step) triples with a SUCCESS proc invoke."""
    found: set[tuple[str, str, str]] = set()
    for e in host.ledger_entries():
        if e.get("kind") != "invoke":
            continue
        p = e.get("payload", {})
        if p.get("capability") != "proc.exec":
            continue
        if "error" in p or "result_ref" not in p:
            continue
        proc = p.get("proc", {})
        if proc.get("bundle_sha256") and proc.get("idem_key") and proc.get("step"):
            found.add((proc["bundle_sha256"], proc["idem_key"], proc["step"]))
    return found


def proc_prior_bundles(host, idem_key: str) -> set[str]:
    """Bundle pins already recorded under an idempotence key.

    Scans `proc_begin` entries AND proc.exec invokes (success and
    error): same key + different bundle + any prior entry is the
    loud idempotence-key collision (§1.5).
    """
    out: set[str] = set()
    for e in host.ledger_entries():
        kind = e.get("kind")
        p = e.get("payload", {})
        if (
            kind == "proc_begin"
            and p.get("idem_key") == idem_key
            and p.get("bundle_sha256")
        ):
            out.add(p["bundle_sha256"])
        elif kind == "invoke" and p.get("capability") == "proc.exec":
            proc = p.get("proc", {})
            if proc.get("idem_key") == idem_key and proc.get("bundle_sha256"):
                out.add(proc["bundle_sha256"])
    return out


def proc_begins(host, idem_key: str, step: str) -> list[dict]:
    """`proc_begin` payloads for one (key, step), ledger order."""
    return [
        e.get("payload", {})
        for e in host.ledger_entries()
        if e.get("kind") == "proc_begin"
        and e.get("payload", {}).get("idem_key") == idem_key
        and e.get("payload", {}).get("step") == step
    ]


def scan_succeeded(host: MiniHost) -> set[tuple[str, str, str]]:
    """All (capability, task_id, step) triples with a successful invoke."""
    found: set[tuple[str, str, str]] = set()
    for e in host.ledger_entries():
        if e.get("kind") != "invoke":
            continue
        p = e.get("payload", {})
        if "error" in p or "result_ref" not in p or "args_ref" not in p:
            continue
        try:
            args = args_of(p["args_ref"])
        except (OSError, ValueError):
            continue
        if "task_id" in args and "step" in args:
            found.add((p["capability"], args["task_id"], args["step"]))
    return found


# ------------------------------------------------- C6 file conventions


def latest_formulation(world_dir: str | Path) -> str:
    cands = sorted((Path(world_dir) / "formulations").glob("*.json"))
    if not cands:
        raise FileNotFoundError(f"no formulations in {world_dir}")
    return str(cands[-1])


def read_verdict(world_dir: str | Path) -> dict:
    p = Path(world_dir) / "verdicts" / "verdict.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------- C4 lifecycle helper


def require_active(host: MiniHost, world_id: str) -> None:
    """C4 read shape: host.worlds[ID].lifecycle compared to "active"."""
    if host.worlds[world_id].lifecycle != "active":
        raise RuntimeError(
            f"{world_id} not active (state={host.worlds[world_id].lifecycle})"
        )


# ------------------------------------------------- plan execution


def check_args_keys(args: dict) -> None:
    """C2: every args file carries formulation_ref + candidate_refs."""
    missing = [k for k in ("formulation_ref", "candidate_refs") if k not in args]
    if missing:
        raise ValueError(f"args missing C2 keys: {missing}")


def check_propose_result(result_ref: str) -> dict:
    """C3: propose result_ref JSON carries candidate_refs + champion_id."""
    body = json.loads(Path(result_ref).read_text(encoding="utf-8"))
    missing = [k for k in ("candidate_refs", "champion_id") if k not in body]
    if missing:
        raise ValueError(f"propose result missing C3 keys: {missing}")
    return body


def execute_plan(
    host: MiniHost, plan: list[dict], prekill: set[tuple[str, str, str]] | None = None
) -> dict:
    """Run each plan step unless a successful invoke already covers it.

    Step shape: {cap, owner, step, name, args, fn}. Returns
    {skipped, executed, re_executed_invokes} where re_executed counts
    executed steps that had already succeeded pre-kill (0 on a correct
    resume: every pre-kill success is skipped, every execute is new).
    """
    succeeded = scan_succeeded(host)
    prekill = prekill or set()
    skipped: list[str] = []
    executed: list[str] = []
    re_executed = 0
    for st in plan:
        key = (st["cap"], st["args"]["task_id"], st["step"])
        label = f"{st['cap']}@{st['step']}"
        if key in succeeded:
            skipped.append(label)
            continue
        check_args_keys(st["args"])
        require_active(host, st["owner"])
        args_ref = host.store_args(st["owner"], st["name"], st["args"])
        entry = host.invoke(
            st["owner"],
            st["owner"],
            st["cap"],
            "1.0",
            args_ref,
            st["fn"],
            cost_usd=0.0,
            time_s=1.0,
        )
        if st["cap"] == CAP_PROPOSE:
            check_propose_result(entry["payload"]["result_ref"])
        executed.append(label)
        if key in prekill:
            re_executed += 1
    return {
        "skipped": skipped,
        "executed": executed,
        "re_executed_invokes": re_executed,
    }


# ------------------------------------- revocation (ledger-durable; LIMITS-2 scope)


def revoke_capability(
    host: MiniHost,
    world_id: str,
    name: str,
    version: str,
    actor: str,
    reason: str,
    new_owner: str = "",
) -> dict:
    """Revoke a capability: the invoke path denies it from here on (the
    cap's required_authority is set to a stamp nobody holds), and a
    ledger `revoke` entry makes the revocation durable (LIMITS-2)
    across reopen; durable = no-fsync ledger-recorded on local disk
    across a process crash (see reapply_revocations; power/media loss
    stays the disk-loss class). Capability name@version sets are
    unchanged, so reopen descriptor verification still passes."""
    world = host.worlds[world_id]
    caps = list(world.capabilities)
    hit = False
    for i, c in enumerate(caps):
        if c.name == name and c.version == version:
            caps[i] = MiniCapability(
                c.name, c.version, required_authority=REVOKED_AUTHORITY
            )
            hit = True
    if not hit:
        raise ValueError(f"{world_id} does not advertise {name}@{version}")
    if new_owner:
        if new_owner not in host.worlds:
            raise ValueError(f"new_owner {new_owner!r} is not a known world")
        if not any(
            c.name == name and c.version == version
            for c in host.worlds[new_owner].capabilities
        ):
            raise ValueError(
                f"new_owner {new_owner!r} does not advertise {name}@{version}"
            )
    world.capabilities = caps
    return host.append(
        "revoke",
        {
            "world_id": world_id,
            "capability": name,
            "version": version,
            "new_owner": new_owner,
            "reason": reason,
        },
        actor=actor,
    )


def reapply_revocations(host: MiniHost) -> list[str]:
    """Re-apply every ledger `revoke` entry to the live registry.

    Called after reopen: reopen rebuilds capabilities from supplied
    descriptors (pre-revocation authorities), so revocations must be
    replayed or they would silently lapse. No new ledger entries."""
    redone: list[str] = []
    for e in host.ledger_entries():
        if e.get("kind") != "revoke":
            continue
        p = e.get("payload", {})
        world = host.worlds[p["world_id"]]
        caps = [
            MiniCapability(
                c.name,
                c.version,
                required_authority=REVOKED_AUTHORITY
                if (c.name == p["capability"] and c.version == p["version"])
                else c.required_authority,
            )
            for c in world.capabilities
        ]
        world.capabilities = caps
        redone.append(f"{p['world_id']}:{p['capability']}@{p['version']}")
    return redone


# ------------------------------------------------- pipeline-side world handle


class SchedWorld:
    """Deterministic artifact writer (MiniWorld lineage).

    Provides the C6 world-handle shape: .state_dir (path-like) plus the
    formulations/*.json + verdicts/verdict.json conventions. All bytes
    timestamp-free so pre/post-kill artifacts are byte-comparable.
    """

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write(path: Path, obj: dict) -> str:
        return atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")

    def write_formulation(
        self,
        name: str,
        task_id: str,
        rep_version: str,
        list_doc: dict,
        slot_doc: dict,
        loss: dict,
    ) -> str:
        return self._write(
            self.state_dir / "formulations" / f"{name}.json",
            {
                "task_id": task_id,
                "representation": rep_version,
                "list": list_doc,
                "slot": slot_doc,
                "declared_loss": loss,
            },
        )

    def write_clarify_receipt(
        self, name: str, task_id: str, rnd: int, frag: dict, lane: str
    ) -> str:
        digest = hashlib.sha256(json.dumps(frag, sort_keys=True).encode()).hexdigest()[
            :16
        ]
        return self._write(
            self.state_dir / "clarify" / f"{name}.json",
            {
                "task_id": task_id,
                "round": rnd,
                "lane": lane,
                "fragment": frag,
                "fragment_digest": digest,
            },
        )

    def write_proposal(
        self,
        name: str,
        task_id: str,
        assignment: dict,
        basis: str,
        cand_name: str | None = None,
    ) -> str:
        # Candidate files are per (task, step): a fixed name would let
        # later tasks clobber earlier tasks' candidates.
        cand_name = cand_name or f"{name}-cand"
        cand_ref = self._write(
            self.state_dir / "candidates" / f"{cand_name}.json",
            {
                "task_id": task_id,
                "candidate_id": cand_name,
                "assignment": assignment,
                "basis": basis,
            },
        )
        return self._write(
            self.state_dir / "results" / f"{name}.json",
            {
                "candidate_refs": [cand_ref],
                "champion_id": cand_name,
                "task_id": task_id,
                "basis": basis,
            },
        )

    def write_verdict(self, task_id: str, assignment: dict, report: dict) -> str:
        return self._write(
            self.state_dir / "verdicts" / "verdict.json",
            {
                "task_id": task_id,
                "phase_verdict": report["valid"],
                "assignment": assignment,
                "quality": report["quality"],
                "prefs_total": report["prefs_total"],
                "violations": report["violations"],
            },
        )
