# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained-package port of successor-004 ORG-OPS conformance tests (unittest, stdlib-only).

Each class asserts the consumer clauses of one op in ORG-OPS.md
(commitments, state custody, resource ownership, lifecycle
transitions, lineage records, recovery behavior).

Run from the repo root:
    PYTHONDONTWRITEBYTECODE=1 python3 prototype/successor-006/test_conformance.py

All run dirs live under successor-006/.test-tmp/.
"""

from __future__ import annotations

import copy
from pathlib import Path
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

import anima_substrate  # noqa: E402

PKG = Path(anima_substrate.__file__).resolve().parent
TOP = PKG.parent.parent
TMPROOT = Path(tempfile.mkdtemp(prefix="anima-substrate-tests-"))

from anima_substrate.demos import successor_demo as DEMO  # noqa: E402
from anima_substrate.host import api  # noqa: E402
from anima_substrate.host.fusion import (  # noqa: E402
    fission_worlds,
    fuse_worlds,
    quarantine_world,
    reuse_composite,
)
from anima_substrate.host.minihost import ContractViolation, MiniHost  # noqa: E402
from anima_substrate.host.pipeline import (  # noqa: E402
    FUSED_CAPS,
    L_CAPS,
    L_REPS,
    Q_CAPS,
    S_CAPS,
    S_REPS,
    LaneCtx,
    build_formulate,
    run_sched_task,
    run_split_pair_task,
    s3_partial_plan,
    s3_resume_flow,
)
from anima_substrate.host.resume import (  # noqa: E402
    REVOKED_AUTHORITY,
    execute_plan,
    reapply_revocations,
    revoke_capability,
    scan_succeeded,
)
from anima_substrate.host.routing import (  # noqa: E402
    ChannelRegistry,
    Coordinator,
    HCoordinator,
    finish_worlds,
    rebuild_records,
    record_routing,
    route,
    setup_host,
    world_record,
)
from anima_substrate.participants.sched import sched_inputs as FI  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)

    def main_host(self):
        worlds = DEMO.main_worlds(self.root / "state")
        pristine = copy.deepcopy(worlds)
        host = setup_host(self.root, worlds)
        return host, pristine


class TestFuseConformance(Base):
    """OP-1 FUSE clauses."""

    def test_fuse_clause(self):
        host, pristine = self.main_host()
        chans = ChannelRegistry()
        run_sched_task(self.root, host, FI.S2, LaneCtx("local", HCoordinator(), chans))
        fused_rec = world_record(
            self.root / "state",
            "SC-FUSED",
            FUSED_CAPS,
            [("sched-list", "v2"), ("sched-slot", "v2")],
        )
        # commitments: inactive parents are refused before any mutation
        host.suspend("SC-S", "host", "conformance probe", pending_effects=[])
        with self.assertRaises(RuntimeError):
            fuse_worlds(
                host,
                chans,
                "SC-L",
                "SC-S",
                "SC-FUSED",
                fused_rec,
                "host",
                "must not happen",
            )
        self.assertNotIn("SC-FUSED", host.worlds)
        host.reattach("SC-S", "host", "probe over")
        # the op
        fus = fuse_worlds(
            host,
            chans,
            "SC-L",
            "SC-S",
            "SC-FUSED",
            fused_rec,
            "host",
            "conformance fusion",
        )
        # custody: union moved, giver-actor on every transfer
        self.assertEqual(
            host.worlds["SC-FUSED"].custodians,
            {
                "sched.composite": "SC-FUSED",
                "sched.requirements": "SC-FUSED",
                "sched.slots": "SC-FUSED",
            },
        )
        # lifecycle: parents dissolved, composite active
        self.assertEqual(host.worlds["SC-L"].lifecycle, "dissolved")
        self.assertEqual(host.worlds["SC-FUSED"].lifecycle, "active")
        # commitments: channel removed and refusing; inventory delta = 1
        self.assertEqual(fus["removed_mechanism"], "direct-channel:SC-L<->SC-S")
        removed = set(fus["before"]["mechanisms"]) - set(fus["after"]["mechanisms"])
        self.assertEqual(removed, {"direct-channel:SC-L<->SC-S"})
        # lineage: derived_from x2 + fusion entry, resolvable
        derived = [e["world"] for e in fus["lineage"] if e.get("rel") == "derived_from"]
        self.assertEqual(sorted(derived), ["SC-L", "SC-S"])
        created = {
            e["payload"]["world_id"]
            for e in host.ledger_entries()
            if e.get("kind") == "create"
        }
        self.assertTrue(set(derived) <= created)
        entries = [e for e in host.ledger_entries() if e.get("kind") == "fusion"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["payload"]["fused_id"], "SC-FUSED")
        # recovery: reopen replays the fused state (composite live)
        records = rebuild_records(self.root, pristine) + [
            world_record(
                self.root / "state",
                "SC-FUSED",
                FUSED_CAPS,
                [("sched-list", "v2"), ("sched-slot", "v2")],
            )
        ]
        host2 = MiniHost.reopen(
            self.root / "state",
            self.root / "ledger.jsonl",
            records,
            actor="host",
            reason="fuse replay",
        )
        self.assertEqual(host2.worlds["SC-FUSED"].lifecycle, "active")
        self.assertEqual(
            host2.worlds["SC-FUSED"].custodians, host.worlds["SC-FUSED"].custodians
        )
        self.assertEqual(host2.worlds["SC-L"].lifecycle, "dissolved")
        # resources: settle leaves 0 stranded, conservation holds
        fin = finish_worlds(host, ["SC-FUSED"], reason="fuse clause over")
        self.assertTrue(fin["conservation_ok"])


class TestReuseConformance(Base):
    """OP-2 REUSE clauses."""

    def test_reuse_clause(self):
        host, _ = self.main_host()
        chans = ChannelRegistry()
        run_sched_task(self.root, host, FI.S2, LaneCtx("local", HCoordinator(), chans))
        # commitments: an unfused world is REFUSED before any work
        n_before = len(host.ledger_entries())
        with self.assertRaises(AssertionError):
            reuse_composite(self.root, host, "SC-L", {"task_id": "X-followup"})
        self.assertEqual(len(host.ledger_entries()), n_before)
        # ... while the fused composite serves with C3 evidence
        fused_rec = world_record(
            self.root / "state",
            "SC-FUSED",
            FUSED_CAPS,
            [("sched-list", "v2"), ("sched-slot", "v2")],
        )
        fuse_worlds(
            host,
            chans,
            "SC-L",
            "SC-S",
            "SC-FUSED",
            fused_rec,
            "host",
            "reuse clause fusion",
        )
        held_before = dict(host.worlds["SC-FUSED"].custodians)
        m4 = reuse_composite(self.root, host, "SC-FUSED", FI.S4_FOLLOWUP)
        self.assertTrue(m4["valid"])
        self.assertTrue(m4["lineage_ok"])
        self.assertEqual(m4["via"], "SC-FUSED")
        # custody untouched; lifecycle untouched (still active)
        self.assertEqual(host.worlds["SC-FUSED"].custodians, held_before)
        self.assertEqual(host.worlds["SC-FUSED"].lifecycle, "active")
        # resources: the composite's grant paid for the reuse invokes
        kinds = [e["kind"] for e in host.ledger_entries()]
        self.assertIn("consume", kinds)


class TestRevisionConformance(Base):
    """OP-3 REVISE clauses."""

    def test_revision_clause(self):
        host, _ = self.main_host()
        ctx = LaneCtx("local", HCoordinator(), ChannelRegistry())
        pre = execute_plan(host, s3_partial_plan(host, FI.S3, ctx))
        self.assertEqual(pre["re_executed_invokes"], 0)
        caps_before = [
            (c.name, c.version, c.required_authority)
            for c in host.worlds["SC-L"].capabilities
        ]
        reps_before = [(r.name, r.version) for r in host.worlds["SC-L"].representations]
        m3 = s3_resume_flow(self.root, host, FI.S3, ctx, scan_succeeded(host))
        self.assertTrue(m3["valid"])
        # world records NEVER mutated by revision
        caps_after = [
            (c.name, c.version, c.required_authority)
            for c in host.worlds["SC-L"].capabilities
            if not (c.name == "sched.propose")
        ]
        caps_before_kept = [c for c in caps_before if c[0] != "sched.propose"]
        self.assertEqual(caps_after, caps_before_kept)
        self.assertEqual(
            [(r.name, r.version) for r in host.worlds["SC-L"].representations],
            reps_before,
        )
        # lineage: revision + void entries; void keeps the artifact (E3)
        kinds = {}
        for e in host.ledger_entries():
            kinds.setdefault(e["kind"], []).append(e.get("payload", {}))
        self.assertEqual(kinds["revision"][0]["to"], "list2slot/v2")
        self.assertTrue(Path(m3["void_ref"]).exists())
        self.assertEqual(kinds["void"][0]["artifact_ref"], m3["void_ref"])
        # O3: the stale proposal was voided by ruling, not unilaterally
        self.assertIn("resolution", kinds)
        self.assertIn("escalation", kinds)


class TestRevocationConformance(Base):
    """OP-4 REVOKE clauses."""

    def test_revocation_clause(self):
        host, pristine = self.main_host()
        # name@version sets unchanged by revocation (only the stamp flips)
        names_before = {(c.name, c.version) for c in host.worlds["SC-L"].capabilities}
        revoke_capability(
            host,
            "SC-L",
            "sched.propose",
            "1.0",
            actor="host",
            reason="conformance",
            new_owner="SC-S",
        )
        names_after = {(c.name, c.version) for c in host.worlds["SC-L"].capabilities}
        self.assertEqual(names_before, names_after)
        entry = [e for e in host.ledger_entries() if e.get("kind") == "revoke"][-1][
            "payload"
        ]
        self.assertEqual(entry["new_owner"], "SC-S")
        # invokes denied with recorded deny
        with self.assertRaises(ContractViolation):
            host.invoke(
                "SC-L",
                "SC-L",
                "sched.propose",
                "1.0",
                host.store_args("SC-L", "rv", {}),
                lambda: "x",
            )
        denies = [
            e
            for e in host.ledger_entries()
            if e.get("kind") == "deny" and e["payload"].get("action") == "invoke"
        ]
        self.assertTrue(denies)
        # recovery: WITHOUT reapply the revocation LAPSES after reopen
        host2 = MiniHost.reopen(
            self.root / "state",
            self.root / "ledger.jsonl",
            rebuild_records(self.root, pristine),
            actor="host",
            reason="rev lapse demo",
        )
        host2.invoke(
            "SC-L",
            "SC-L",
            "sched.propose",
            "1.0",
            host2.store_args("SC-L", "rv2", {}),
            lambda: "lapsed",
        )
        # ... and WITH reapply it holds (no new ledger entries)
        n_before = len(host2.ledger_entries())
        redone = reapply_revocations(host2)
        self.assertEqual(redone, ["SC-L:sched.propose@1.0"])
        self.assertEqual(len(host2.ledger_entries()), n_before)
        with self.assertRaises(ContractViolation):
            host2.invoke(
                "SC-L",
                "SC-L",
                "sched.propose",
                "1.0",
                host2.store_args("SC-L", "rv3", {}),
                lambda: "x",
            )

    def test_new_owner_must_advertise(self):
        # OP-4 §1: new_owner MUST already advertise the capability.
        # Unknown world -> ValueError, zero partial effects.
        host, _ = self.main_host()
        n_before = len(host.ledger_entries())
        with self.assertRaises(ValueError):
            revoke_capability(
                host,
                "SC-L",
                "sched.propose",
                "1.0",
                actor="host",
                reason="bogus owner",
                new_owner="SC-DOES-NOT-EXIST",
            )
        self.assertEqual(len(host.ledger_entries()), n_before)
        # Known world that does NOT advertise the cap -> ValueError,
        # stamp unflipped, no revoke entry (SC-S lacks list.provide).
        with self.assertRaises(ValueError):
            revoke_capability(
                host,
                "SC-L",
                "list.provide",
                "1.0",
                actor="host",
                reason="non-advertising",
                new_owner="SC-S",
            )
        self.assertEqual(len(host.ledger_entries()), n_before)
        self.assertFalse(
            [e for e in host.ledger_entries() if e.get("kind") == "revoke"]
        )
        stamp = [
            c.required_authority
            for c in host.worlds["SC-L"].capabilities
            if c.name == "list.provide"
        ]
        self.assertTrue(stamp and stamp[0] != REVOKED_AUTHORITY)


class TestQuarantineConformance(Base):
    """OP-5 QUARANTINE clauses."""

    def test_quarantine_clause(self):
        s5w = [
            world_record(
                self.root / "state",
                "SC-Q",
                Q_CAPS,
                [("sched-list", "v1")],
                custodians={"sched.commitment-q": "SC-Q"},
            ),
            world_record(self.root / "state", "SC-B", Q_CAPS, [("sched-list", "v1")]),
        ]
        host = setup_host(self.root, s5w)
        task = dict(FI.S5)
        quar = quarantine_world(host, "SC-Q", "SC-B", "host", "conformance quarantine")
        # lifecycle: failed world suspended, standby still active
        self.assertEqual(host.worlds["SC-Q"].lifecycle, "suspended")
        self.assertEqual(host.worlds["SC-B"].lifecycle, "active")
        # suspend evidence: checkpoint carries pending_effects naming
        # the standby handoff; lifecycle records active -> suspended
        ckpt = [e for e in host.ledger_entries() if e.get("kind") == "checkpoint"][-1][
            "payload"
        ]
        self.assertEqual(
            ckpt["pending_effects"],
            [{"commitment": "sched.commitment-q", "to": "SC-B"}],
        )
        life = [
            e
            for e in host.ledger_entries()
            if e.get("kind") == "lifecycle" and e["payload"].get("world_id") == "SC-Q"
        ][-1]["payload"]
        self.assertEqual((life["from"], life["to"]), ("active", "suspended"))
        # custody: every commitment on the standby (actor=host: the
        # documented O4 exception — the giver is suspended)
        self.assertEqual(host.worlds["SC-B"].custodians, {"sched.commitment-q": "SC-B"})
        xfer = [e for e in host.ledger_entries() if e.get("kind") == "transfer"][-1]
        self.assertEqual(xfer["actor"], "host")
        self.assertEqual(quar["standby"], "SC-B")
        # invokes on the quarantined world denied with recorded deny
        with self.assertRaises(ContractViolation):
            host.invoke(
                "SC-Q",
                "SC-Q",
                "sched.propose",
                "1.0",
                host.store_args(
                    "SC-Q", "qz", {"formulation_ref": "", "candidate_refs": []}
                ),
                lambda: "never",
            )
        self.assertTrue([e for e in host.ledger_entries() if e.get("kind") == "deny"])
        # standby completes transferred work with its own capabilities
        ctx = LaneCtx("central", Coordinator(), None)
        rep = execute_plan(host, [build_formulate(host, task, "SC-B", "v1", ctx)])
        self.assertEqual(len(rep["executed"]), 1)
        # resources: finish settles both with 0 stranded
        fin = finish_worlds(host, ["SC-Q", "SC-B"], reason="quarantine clause over")
        self.assertTrue(fin["conservation_ok"])


class TestFissionConformance(Base):
    """OP-6 FISSION clauses (full cycle: fuse -> fission -> settle)."""

    def test_fission_clause(self):
        host, _ = self.main_host()
        chans = ChannelRegistry()
        run_sched_task(self.root, host, FI.S2, LaneCtx("local", HCoordinator(), chans))
        fused_rec = world_record(
            self.root / "state",
            "SC-FUSED",
            FUSED_CAPS,
            [("sched-list", "v2"), ("sched-slot", "v2")],
        )
        fuse_worlds(
            host,
            chans,
            "SC-L",
            "SC-S",
            "SC-FUSED",
            fused_rec,
            "host",
            "fission clause fusion",
        )
        l2 = world_record(self.root / "state", "SC-L2", L_CAPS, L_REPS)
        s2 = world_record(self.root / "state", "SC-S2", S_CAPS, S_REPS)
        part = {
            "sched.composite": "SC-L2",
            "sched.requirements": "SC-L2",
            "sched.slots": "SC-S2",
        }
        fis = fission_worlds(
            host,
            chans,
            "SC-FUSED",
            "SC-L2",
            "SC-S2",
            l2,
            s2,
            part,
            "host",
            "fission clause",
        )
        # custody: each child holds exactly its partition side
        self.assertEqual(
            host.worlds["SC-L2"].custodians,
            {"sched.composite": "SC-L2", "sched.requirements": "SC-L2"},
        )
        self.assertEqual(host.worlds["SC-S2"].custodians, {"sched.slots": "SC-S2"})
        # lifecycle: children active, composite dissolved
        self.assertEqual(host.worlds["SC-L2"].lifecycle, "active")
        self.assertEqual(host.worlds["SC-S2"].lifecycle, "active")
        self.assertEqual(host.worlds["SC-FUSED"].lifecycle, "dissolved")
        # lineage: fission-of names the split fusion on BOTH children
        for key in ("lineage_left", "lineage_right"):
            named = [e for e in fis[key] if e.get("rel") == "fission-of"]
            self.assertEqual(len(named), 1)
            self.assertEqual(named[0]["fusion"], "SC-FUSED")
            self.assertEqual(sorted(named[0]["fusion_parents"]), ["SC-L", "SC-S"])
        # commitments: channel restored; ledger entry complete
        self.assertEqual(fis["restored_mechanism"], "direct-channel:SC-L2<->SC-S2")
        entries = [e for e in host.ledger_entries() if e.get("kind") == "fission"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["payload"]["partition"], part)
        # resources + recovery: children work, then settle clean
        m6 = run_split_pair_task(
            self.root, host, FI.S6_FISSION_FOLLOWUP, "SC-L2", "SC-S2"
        )
        self.assertTrue(m6["valid"])
        self.assertEqual(m6["quality"], m6["prefs_total"])
        fin = finish_worlds(host, ["SC-L2", "SC-S2"], reason="fission clause over")
        self.assertTrue(fin["conservation_ok"])


class TestApiRecovery(Base):
    """Recovery procedure: api.open_run restores lineage + revocations."""

    def test_open_run_restores_lineage(self):
        root = self.root / "apirec"
        api.init_run(root)
        api.run_tasks(root, ["S2"])
        api.fuse_op(root, "SC-L", "SC-S", "SC-FUSED", reason="recovery test fusion")
        host, _ = api.open_run(root)
        lineage = host.worlds["SC-FUSED"].lineage
        derived = [
            e["world"]
            for e in lineage
            if isinstance(e, dict) and e.get("rel") == "derived_from"
        ]
        self.assertEqual(sorted(derived), ["SC-L", "SC-S"])
        # ... so reuse (which checks lineage) works AFTER a reopen
        m4 = api.reuse_op(root, "SC-FUSED", copy.deepcopy(FI.S4_FOLLOWUP))
        self.assertTrue(m4["valid"])
        self.assertTrue(m4["lineage_ok"])
        # fission lineage survives a reopen too
        api.fission_op(
            root,
            "SC-FUSED",
            "SC-L2",
            "SC-S2",
            {
                "sched.composite": "SC-L2",
                "sched.requirements": "SC-L2",
                "sched.slots": "SC-S2",
            },
            reason="recovery test fission",
        )
        host2, _ = api.open_run(root)
        named = [
            e
            for e in host2.worlds["SC-L2"].lineage
            if isinstance(e, dict) and e.get("rel") == "fission-of"
        ]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0]["fusion"], "SC-FUSED")
        m6 = api.split_pair_op(
            root, copy.deepcopy(FI.S6_FISSION_FOLLOWUP), "SC-L2", "SC-S2"
        )
        self.assertTrue(m6["valid"])


class TestRoutingConformance(Base):
    """Routing rule clause (central default; local iff >=2 rounds + split)."""

    def test_routing_clause(self):
        d1 = route(FI.S1)
        self.assertEqual(d1["lane"], "central")
        d2 = route(FI.S2)
        self.assertEqual(d2["lane"], "local")
        host, _ = self.main_host()
        log = self.root / "ROUTING-LOG.jsonl"
        record_routing(host, d1, log)
        record_routing(host, d2, log)
        payloads = [
            e["payload"] for e in host.ledger_entries() if e.get("kind") == "routing"
        ]
        self.assertEqual({p["task_id"] for p in payloads}, {"S1", "S2"})
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
