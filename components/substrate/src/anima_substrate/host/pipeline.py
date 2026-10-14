# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Successor-004 scheduling pipeline (X3 central/local-arm lineage, unified).

One pipeline, two lanes. The routing decision (routing.route) selects the
lane per task; the phase plan (formulate -> clarify* -> propose ->
verify) is identical, but message flow differs:
- central: the coordinator handles every fragment (central_bytes).
- local:   fragments travel the direct channel (direct_bytes); the
  coordinator sees ONLY commitments + escalations/resolutions
  (HCoordinator refuses anything else -- O5/E1 mechanism guard).

Obligations enforced structurally (see OBLIGATIONS.md):
O1 one fragment per clarify step; O2 proposals cite their basis;
O3 conflicts escalate, stale voided only by ruling; O4 custody moves
direct giver->taker; O5 terminal commitments exported per world.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from ..participants.sched import sched_checker as checker
from ..participants.sched import sched_domain as domain
from .minihost import MiniHost, atomic_write_text
from .resume import (
    CAP_CLARIFY,
    CAP_FORMULATE,
    CAP_PROPOSE,
    CAP_VERIFY,
    SchedWorld,
    check_propose_result,
    execute_plan,
    latest_formulation,
    revoke_capability,
)
from .routing import ChannelRegistry, Coordinator, write_json

L_CAPS = [
    ("list.provide", "1.0"),
    ("sched.formulate", "1.0"),
    ("sched.clarify", "1.0"),
    ("sched.propose", "1.0"),
    ("sched.verify", "1.0"),
]
S_CAPS = [
    ("slot.provide", "1.0"),
    ("sched.clarify", "1.0"),
    ("sched.propose", "1.0"),
    ("sched.verify", "1.0"),
]
# SC-S advertises sched.propose from birth as the standby owner: the S3
# revocation flips usability (authority stamp), never the advertised set,
# so reopen descriptor verification (name@version compare) still passes.
T_CAPS = [("sched.verify", "1.0"), ("sched.reuse", "1.0")]
FUSED_CAPS = [
    ("list.provide", "1.0"),
    ("slot.provide", "1.0"),
    ("sched.formulate", "1.0"),
    ("sched.clarify", "1.0"),
    ("sched.propose", "1.0"),
    ("sched.verify", "1.0"),
    ("sched.reuse", "1.0"),
]
Q_CAPS = [
    ("sched.formulate", "1.0"),
    ("sched.clarify", "1.0"),
    ("sched.propose", "1.0"),
    ("sched.verify", "1.0"),
]

L_REPS = [("sched-list", "v1"), ("sched-list", "v2")]
S_REPS = [("sched-slot", "v1"), ("sched-slot", "v2")]
# Both representation versions are advertised from birth; a mid-task
# revision switches the ACTIVE one via a ledger `revision` entry (never
# by mutating the world record, which would break reopen identity).


def fragment_rounds(task: dict) -> list[tuple[str, dict]]:
    """Ordered (owner, fragment) clarify steps. Exactly one fragment per
    step (O1); rounds with empty holdings on a side are skipped."""
    tid = task["task_id"]
    hold = task["holdings"]
    ltasks = {t: task["tasks"][t] for t in hold["SC-L"]["req_tasks"]}
    stasks = {t: task["tasks"][t] for t in hold["SC-S"]["req_tasks"]}
    lprefs = {p: task["prefs"][p] for p in hold["SC-L"]["prefs"]}
    sprefs = {p: task["prefs"][p] for p in hold["SC-S"]["prefs"]}
    rounds: list[tuple[str, dict]] = []
    if ltasks:
        rounds.append(
            ("SC-L", domain.req_fragment(tid, "SC-L", ltasks, task["precedence"]))
        )
    if stasks:
        rounds.append(("SC-S", domain.req_fragment(tid, "SC-S", stasks, [])))
    if lprefs:
        rounds.append(("SC-L", domain.pref_fragment(tid, "SC-L", lprefs)))
    if sprefs:
        rounds.append(("SC-S", domain.pref_fragment(tid, "SC-S", sprefs)))
    return rounds


def check_basis(basis: str) -> None:
    """O2: every proposal cites its basis (merged requirements +
    clarified preferences, or revision + current owner)."""
    if not basis or not ("clarif" in basis or "revision" in basis):
        raise ValueError(
            f"O2 violated: proposal basis {basis!r} cites "
            f"neither clarified prefs nor revision"
        )


class LaneCtx:
    """Message-flow context for one task run."""

    def __init__(
        self,
        lane: str,
        coord: Coordinator,
        chan_registry: ChannelRegistry | None = None,
    ) -> None:
        self.lane = lane
        self.coord = coord
        self.chans = chan_registry

    def carry_fragment(self, frm: str, to: str, frag: dict) -> dict:
        if self.lane == "central":
            return self.coord.handle(frag)
        assert self.chans is not None, "local lane needs channels"
        return self.chans.get(frm, to).send(frag)


# ------------------------------------------------------- step builders


def _form_path(host: MiniHost, owner: str, task_id: str, rep: str) -> str:
    return str(
        Path(host.worlds[owner].instance_state_dir)
        / "formulations"
        / f"{task_id}-formulation-{rep}.json"
    )


def build_formulate(
    host: MiniHost, task: dict, owner: str, rep: str, ctx: LaneCtx
) -> dict:
    tid = task["task_id"]
    step = f"formulate@{rep}"
    ldoc = domain.list_doc(task)
    sdoc, loss = domain.translate_list2slot(ldoc, f"list2slot/{rep}")
    world = SchedWorld(host.worlds[owner].instance_state_dir)
    fname = f"{tid}-formulation-{rep}"

    def fn() -> str:
        return world.write_formulation(fname, tid, f"sched/{rep}", ldoc, sdoc, loss)

    return {
        "cap": CAP_FORMULATE,
        "owner": owner,
        "step": step,
        "name": f"{tid}-{step}",
        "args": {
            "formulation_ref": "",
            "candidate_refs": [],
            "task_id": tid,
            "step": step,
            "representation": rep,
            "lane": ctx.lane,
        },
        "fn": fn,
    }


def build_clarify(
    host: MiniHost,
    task: dict,
    owner: str,
    frag: dict,
    rnd: int,
    n_rounds: int,
    rep: str,
    ctx: LaneCtx,
    peer: str,
) -> dict:
    tid = task["task_id"]
    step = f"clarify@r{rnd}"
    world = SchedWorld(host.worlds[owner].instance_state_dir)
    fname = f"{tid}-{step}"

    def fn() -> str:
        ctx.carry_fragment(owner, peer, frag)  # O1: this step's one fragment
        return world.write_clarify_receipt(fname, tid, rnd, frag, ctx.lane)

    return {
        "cap": CAP_CLARIFY,
        "owner": owner,
        "step": step,
        "name": f"{tid}-{step}",
        "args": {
            "formulation_ref": _form_path(host, "SC-L", tid, rep)
            if owner in ("SC-L", "SC-S")
            else _form_path(host, owner, tid, rep),
            "candidate_refs": [],
            "task_id": tid,
            "step": step,
            "round": rnd,
            "of_rounds": n_rounds,
            "lane": ctx.lane,
            "fragment_kind": frag["kind"],
        },
        "fn": fn,
    }


def build_propose(
    host: MiniHost,
    task: dict,
    owner: str,
    basis: str,
    ctx: LaneCtx,
    tag: str = "propose",
    cap: str = CAP_PROPOSE,
) -> dict:
    tid = task["task_id"]
    check_basis(basis)  # O2 enforced at build time
    step = f"{tag}"
    world = SchedWorld(host.worlds[owner].instance_state_dir)

    def fn() -> str:
        assignment = domain.solve(task)
        return world.write_proposal(f"{tid}-{step}", tid, assignment, basis)

    return {
        "cap": cap,
        "owner": owner,
        "step": step,
        "name": f"{tid}-{step}",
        "args": {
            "formulation_ref": _latest_or_empty(world),
            "candidate_refs": [],
            "task_id": tid,
            "step": step,
            "basis": basis,
            "lane": ctx.lane,
        },
        "fn": fn,
    }


def _latest_or_empty(world: SchedWorld) -> str:
    try:
        return latest_formulation(world.state_dir)
    except FileNotFoundError:
        return ""


def build_verify(
    host: MiniHost,
    task: dict,
    owner: str,
    ctx: LaneCtx,
    proposer: str,
    propose_step: str,
    cap: str = CAP_VERIFY,
    tag: str = "verify",
) -> dict:
    tid = task["task_id"]
    step = f"{tag}"
    world = SchedWorld(host.worlds[owner].instance_state_dir)
    prop_world = SchedWorld(host.worlds[proposer].instance_state_dir)

    def fn() -> str:
        res_path = prop_world.state_dir / "results" / f"{tid}-{propose_step}.json"
        body = check_propose_result(str(res_path))  # C3 re-read
        cand = json.loads(Path(body["candidate_refs"][0]).read_text(encoding="utf-8"))
        report = checker.check(cand["assignment"], task)
        ref = world.write_verdict(tid, cand["assignment"], report)
        task_ref = str(world.state_dir / "verdicts" / f"verdict-{tid}.json")
        atomic_write_text(task_ref, Path(ref).read_text(encoding="utf-8"))
        return ref

    return {
        "cap": cap,
        "owner": owner,
        "step": step,
        "name": f"{tid}-{step}",
        "args": {
            "formulation_ref": _latest_or_empty(world),
            "candidate_refs": [],
            "task_id": tid,
            "step": step,
            "propose_step": propose_step,
            "lane": ctx.lane,
        },
        "fn": fn,
    }


# ------------------------------------------------- escalation (O3/E1-E3)


def file_escalation(
    host: MiniHost, ctx: LaneCtx, task_id: str, frm: str, issue: str, options: list
) -> dict:
    msg = domain.escalation(task_id, frm, issue, options)
    ctx.coord.handle(msg)  # allowed in both lanes (export payload)
    return host.append("escalation", msg, actor=frm)


def issue_ruling(
    host: MiniHost, ctx: LaneCtx, task_id: str, ruling: str, reason: str
) -> dict:
    msg = domain.resolution(task_id, ruling, reason)
    ctx.coord.handle(msg)
    return host.append("resolution", msg, actor="host")


def void_proposal(host: MiniHost, task_id: str, artifact_ref: str, notice: str) -> dict:
    """E3: the voided artifact is KEPT on disk and referenced by the
    void-notice (auditability, no silent deletes)."""
    assert Path(artifact_ref).exists(), f"voided artifact missing: {artifact_ref}"
    return host.append(
        "void",
        {"task_id": task_id, "artifact_ref": artifact_ref, "notice": notice},
        actor="host",
    )


def apply_revision(host: MiniHost, task_id: str, revision: dict) -> dict:
    """Mid-task representation revision: a ledger `revision` entry
    switches the ACTIVE representation. World records are NOT mutated
    (both versions were advertised at birth), so reopen identity holds."""
    return host.append("revision", {"task_id": task_id, **revision}, actor="host")


def export_commitments(
    host: MiniHost, ctx: LaneCtx, task_id: str, worlds: list[str], assignment: dict
) -> list[dict]:
    """O5: each world exports a terminal commitment for what it agreed
    to; the coordinator sees commitments and nothing else (local lane)."""
    out = []
    for w in worlds:
        msg = domain.commitment(task_id, w, assignment, receipt=f"O5-{w}-accept")
        ctx.coord.handle(msg)
        out.append(host.append("commitment", msg, actor=w))
    return out


# ------------------------------------------------------- full task run


def run_sched_task(
    root: Path, host: MiniHost, task: dict, ctx: LaneCtx, prekill: set | None = None
) -> dict:
    """Run formulate -> clarify* -> propose -> verify + O5 commitments."""
    task = copy.deepcopy(task)
    tid = task["task_id"]
    rep = "v1" if task.get("adapter", "v1").endswith("v1") else "v2"
    rounds = fragment_rounds(task)
    plan = [build_formulate(host, task, "SC-L", rep, ctx)]
    for i, (owner, frag) in enumerate(rounds, start=1):
        peer = "SC-S" if owner == "SC-L" else "SC-L"
        plan.append(
            build_clarify(host, task, owner, frag, i, len(rounds), rep, ctx, peer)
        )
    plan.append(
        build_propose(host, task, "SC-L", "merged reqs + clarified prefs (O2)", ctx)
    )
    plan.append(build_verify(host, task, "SC-S", ctx, "SC-L", "propose"))
    resume_rep = execute_plan(host, plan, prekill=prekill)
    verdict = json.loads(
        Path(host.worlds["SC-S"].instance_state_dir)
        .joinpath("verdicts", f"verdict-{tid}.json")
        .read_text(encoding="utf-8")
    )
    export_commitments(host, ctx, tid, ["SC-L", "SC-S"], verdict["assignment"])
    sol_ref = write_json(
        root / "artifacts" / f"solution-{tid}.json",
        {
            "task_id": tid,
            "assignment": verdict["assignment"],
            "quality": verdict["quality"],
            "prefs_total": verdict["prefs_total"],
            "valid": verdict["phase_verdict"],
        },
    )
    metered = lane_bytes(host, tid)
    return {
        "task_id": tid,
        "lane": ctx.lane,
        "valid": verdict["phase_verdict"],
        "quality": verdict["quality"],
        "prefs_total": verdict["prefs_total"],
        "central_bytes": metered["central_bytes"],
        "direct_bytes": metered["direct_bytes"],
        "live_central_bytes": ctx.coord.central_bytes,
        "rounds": len(rounds),
        "solution_ref": sol_ref,
        "skipped": resume_rep["skipped"],
        "executed": resume_rep["executed"],
        "re_executed_invokes": resume_rep["re_executed_invokes"],
    }


def lane_bytes(host: MiniHost, task_id: str) -> dict:
    """Recompute lane bytes from DURABLE state (LIMITS-2 scope;
    kill-proof, unlike live in-memory counters): clarify receipts
    on disk (each records its
    lane) + ledger commitment/escalation/resolution payloads (exactly
    what the coordinator handled)."""
    central = 0
    direct = 0
    for wid, rec in host.worlds.items():
        cdir = Path(rec.instance_state_dir) / "clarify"
        if not cdir.exists():
            continue
        for rp in sorted(cdir.glob(f"{task_id}-*.json")):
            body = json.loads(rp.read_text(encoding="utf-8"))
            n = domain.canonical_bytes(body["fragment"])
            if body.get("lane") == "central":
                central += n
            else:
                direct += n
    for e in host.ledger_entries():
        if (
            e.get("kind") in ("commitment", "escalation", "resolution")
            and e.get("payload", {}).get("task_id") == task_id
        ):
            central += domain.canonical_bytes(e["payload"])
    return {"central_bytes": central, "direct_bytes": direct}


# ------------------------------------------------- fission follow-up


def run_split_pair_task(
    root: Path, host: MiniHost, task: dict, left: str, right: str
) -> dict:
    """Run a fresh task through a fission-split pair: formulate + propose
    on `left`, cross-verify on `right`. Proves both children are live
    and cooperating after the split. No clarification dialogue (the
    pair inherits the composite's clarified state), so no lane bytes
    are claimed here — validity + quality + cross-world invokes only.
    """
    from .resume import require_active

    require_active(host, left)
    require_active(host, right)
    task = copy.deepcopy(task)
    tid = task["task_id"]
    lane = "fission-reuse"
    left_world = SchedWorld(host.worlds[left].instance_state_dir)
    right_world = SchedWorld(host.worlds[right].instance_state_dir)
    ldoc = domain.list_doc(task)
    sdoc, loss = domain.translate_list2slot(ldoc, task.get("adapter", "list2slot/v1"))
    form_ref = left_world.write_formulation(
        f"{tid}-formulation-v1", tid, "sched/v1", ldoc, sdoc, loss
    )
    args_f = host.store_args(
        left,
        f"{tid}-formulate",
        {
            "formulation_ref": "",
            "candidate_refs": [],
            "task_id": tid,
            "step": "formulate@v1",
            "lane": lane,
        },
    )
    host.invoke(
        left,
        left,
        CAP_FORMULATE,
        "1.0",
        args_f,
        lambda: form_ref,
        cost_usd=0.0,
        time_s=1.0,
    )
    basis = "merged reqs + clarified prefs inherited from the fused composite (O2)"
    check_basis(basis)
    assignment = domain.solve(task)
    args_p = host.store_args(
        left,
        f"{tid}-propose",
        {
            "formulation_ref": form_ref,
            "candidate_refs": [],
            "task_id": tid,
            "step": "propose",
            "basis": basis,
            "lane": lane,
        },
    )
    pentry = host.invoke(
        left,
        left,
        CAP_PROPOSE,
        "1.0",
        args_p,
        lambda: left_world.write_proposal(f"{tid}-propose", tid, assignment, basis),
        cost_usd=0.0,
        time_s=1.0,
    )
    body = check_propose_result(pentry["payload"]["result_ref"])  # C3
    cand = json.loads(Path(body["candidate_refs"][0]).read_text(encoding="utf-8"))
    report = checker.check(cand["assignment"], task)
    args_v = host.store_args(
        right,
        f"{tid}-verify",
        {
            "formulation_ref": form_ref,
            "candidate_refs": [],
            "task_id": tid,
            "step": "verify",
            "propose_step": "propose",
            "lane": lane,
        },
    )
    ventry = host.invoke(
        right,
        right,
        CAP_VERIFY,
        "1.0",
        args_v,
        lambda: right_world.write_verdict(tid, cand["assignment"], report),
        cost_usd=0.0,
        time_s=1.0,
    )
    task_ref = right_world.state_dir / "verdicts" / f"verdict-{tid}.json"
    atomic_write_text(
        task_ref, Path(ventry["payload"]["result_ref"]).read_text(encoding="utf-8")
    )
    sol_ref = write_json(
        root / "artifacts" / f"solution-{tid}.json",
        {
            "task_id": tid,
            "assignment": cand["assignment"],
            "quality": report["quality"],
            "prefs_total": report["prefs_total"],
            "valid": report["valid"],
            "via": [left, right],
        },
    )
    return {
        "task_id": tid,
        "lane": lane,
        "via": [left, right],
        "valid": report["valid"],
        "quality": report["quality"],
        "prefs_total": report["prefs_total"],
        "formulation_ref": form_ref,
        "propose_ref": pentry["payload"]["result_ref"],
        "verdict_ref": str(task_ref),
        "solution_ref": sol_ref,
    }


# ------------------------------------------------------- S3 kill flow


def s3_views(s3: dict) -> tuple[dict, dict]:
    """Base + revised task views, both keyed under task_id S3 (the
    matcher distinguishes steps, not views)."""
    s3 = copy.deepcopy(s3)
    base = dict(s3["base"])
    base["task_id"] = "S3"
    base["holdings"] = copy.deepcopy(s3["holdings"])
    revised = dict(s3["revised"])
    revised["task_id"] = "S3"
    revised["holdings"] = copy.deepcopy(s3["holdings"])
    return base, revised


def s3_partial_plan(host: MiniHost, s3: dict, ctx: LaneCtx) -> list[dict]:
    """Child-side partial work: formulate@v1 + clarify r1 + r2."""
    base, _ = s3_views(s3)
    rounds = fragment_rounds(base)
    plan = [build_formulate(host, base, "SC-L", "v1", ctx)]
    for i, (owner, frag) in enumerate(rounds[:2], start=1):
        peer = "SC-S" if owner == "SC-L" else "SC-L"
        plan.append(
            build_clarify(host, base, owner, frag, i, len(rounds), "v1", ctx, peer)
        )
    return plan


def s3_resume_flow(
    root: Path, host: MiniHost, s3: dict, ctx: LaneCtx, prekill: set
) -> dict:
    """Parent-side resume: finish dialogue, stale-propose, revise,
    revoke, denied retry, escalate, rule, void, re-propose, verify."""
    from .minihost import ContractViolation

    base, revised = s3_views(s3)
    rounds = fragment_rounds(base)
    skipped: list[str] = []
    executed: list[str] = []
    re_executed = 0

    def run(plan: list[dict]) -> dict:
        nonlocal re_executed
        rep = execute_plan(host, plan, prekill=prekill)
        skipped.extend(rep["skipped"])
        executed.extend(rep["executed"])
        re_executed += rep["re_executed_invokes"]
        return rep

    # 1. re-drive the full v1 prefix: pre-kill steps skip (resume
    # evidence), only r3/r4 execute (new steps, not rework).
    prefix = [build_formulate(host, base, "SC-L", "v1", ctx)]
    for i, (owner, frag) in enumerate(rounds, start=1):
        peer = "SC-S" if owner == "SC-L" else "SC-L"
        prefix.append(
            build_clarify(host, base, owner, frag, i, len(rounds), "v1", ctx, peer)
        )
    run(prefix)
    # 2. stale proposal under v1 (succeeds at the host; staleness is the
    # coordinator's call per O3, not the host's)
    run(
        [
            build_propose(
                host,
                base,
                "SC-L",
                "merged reqs + clarified prefs @v1 (O2; STALE after revision)",
                ctx,
                tag="propose@v1-stale",
            )
        ]
    )
    stale_ref = next(
        e["payload"]["result_ref"]
        for e in host.ledger_entries()
        if e.get("kind") == "invoke"
        and e.get("payload", {}).get("capability") == CAP_PROPOSE
        and "error" not in e.get("payload", {})
        and e["payload"]["args_ref"].endswith("S3-propose@v1-stale.json")
    )
    # 3. mid-task representation revision v1 -> v2
    apply_revision(host, "S3", s3["revision"])
    run([build_formulate(host, revised, "SC-L", "v2", ctx)])
    # 4. capability revocation with ownership transfer SC-L -> SC-S
    rev = s3["revocation"]
    revoke_capability(
        host,
        rev["from"],
        rev["capability"],
        rev["version"],
        actor="host",
        reason=rev["reason"],
        new_owner=rev["to"],
    )
    # 5. denied retry proves enforcement (raises + recorded deny)
    denied: dict | None = None
    retry = build_propose(
        host,
        base,
        "SC-L",
        "merged reqs + clarified prefs @v1 retry (O2)",
        ctx,
        tag="propose@v1-retry",
    )
    try:
        run([retry])
        raise AssertionError("revoked propose unexpectedly succeeded")
    except ContractViolation as exc:
        denies = [
            e
            for e in host.ledger_entries()
            if e.get("kind") == "deny"
            and e.get("payload", {}).get("action") == "invoke"
        ]
        assert denies, "revoked invoke raised without a recorded deny"
        denied = {
            "error": f"{type(exc).__name__}: {exc}",
            "deny_seq": denies[-1]["seq"],
        }
    # 6. escalation + ruling (O3/E1-E2), then void (E3, artifact kept)
    file_escalation(
        host,
        ctx,
        "S3",
        "SC-L",
        "stale v1 proposal + revoked sched.propose@SC-L",
        ["void v1, SC-S re-proposes under v2", "restore SC-L ownership"],
    )
    issue_ruling(
        host,
        ctx,
        "S3",
        "void v1 proposal; SC-S re-proposes under v2",
        "ownership changed at v1->v2; O3 void-by-ruling only",
    )
    void_proposal(
        host, "S3", stale_ref, "R1: v1 proposal void; artifact kept for audit"
    )
    # 7. re-propose under v2 by the new owner + cross-verify
    run(
        [
            build_propose(
                host,
                revised,
                "SC-S",
                "revision v1->v2 + owner SC-S per ruling R1 (O2/O3)",
                ctx,
                tag="propose@v2",
            )
        ]
    )
    run(
        [
            build_verify(
                host, revised, "SC-L", ctx, "SC-S", "propose@v2", tag="verify@v2"
            )
        ]
    )
    verdict = json.loads(
        Path(
            host.worlds["SC-L"].instance_state_dir, "verdicts", "verdict-S3.json"
        ).read_text(encoding="utf-8")
    )
    export_commitments(host, ctx, "S3", ["SC-L", "SC-S"], verdict["assignment"])
    sol_ref = write_json(
        root / "artifacts" / "solution-S3.json",
        {
            "task_id": "S3",
            "assignment": verdict["assignment"],
            "quality": verdict["quality"],
            "prefs_total": verdict["prefs_total"],
            "valid": verdict["phase_verdict"],
            "representation": "v2",
        },
    )
    metered = lane_bytes(host, "S3")
    return {
        "task_id": "S3",
        "lane": ctx.lane,
        "valid": verdict["phase_verdict"],
        "quality": verdict["quality"],
        "prefs_total": verdict["prefs_total"],
        "central_bytes": metered["central_bytes"],
        "direct_bytes": metered["direct_bytes"],
        "rounds": len(rounds),
        "solution_ref": sol_ref,
        "skipped": skipped,
        "executed": executed,
        "re_executed_invokes": re_executed,
        "revoked": f"{rev['from']}:{rev['capability']}@{rev['version']}->{rev['to']}",
        "denied_retry": denied,
        "void_ref": stale_ref,
        "ruling": "void v1 proposal; SC-S re-proposes under v2",
    }
