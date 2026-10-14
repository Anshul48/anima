# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained-package port of successor-004 fission tests (unittest, stdlib-only, in-process).

Run from the repo root:
    PYTHONDONTWRITEBYTECODE=1 python3 prototype/successor-006/test_fission.py

All run dirs live under successor-006/.test-tmp/ (nothing is written
outside successor-006/).
"""

from __future__ import annotations

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
from anima_substrate.host.fusion import fission_worlds, fuse_worlds  # noqa: E402
from anima_substrate.host.pipeline import (  # noqa: E402
    FUSED_CAPS,
    L_CAPS,
    L_REPS,
    S_CAPS,
    S_REPS,
    LaneCtx,
    run_sched_task,
    run_split_pair_task,
)
from anima_substrate.host.routing import (  # noqa: E402
    ChannelRegistry,
    HCoordinator,
    finish_worlds,
    setup_host,
    world_record,
)
from anima_substrate.participants.sched import sched_inputs as FI  # noqa: E402

PARTITION = {
    "sched.composite": "SC-L2",
    "sched.requirements": "SC-L2",
    "sched.slots": "SC-S2",
}


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)

    def fused_host(self):
        worlds = DEMO.main_worlds(self.root / "state")
        host = setup_host(self.root, worlds)
        chans = ChannelRegistry()
        m2 = run_sched_task(
            self.root, host, FI.S2, LaneCtx("local", HCoordinator(), chans)
        )
        assert m2["valid"]
        fused_rec = world_record(
            self.root / "state",
            "SC-FUSED",
            FUSED_CAPS,
            [("sched-list", "v2"), ("sched-slot", "v2")],
        )
        fusion = fuse_worlds(
            host,
            chans,
            "SC-L",
            "SC-S",
            "SC-FUSED",
            fused_rec,
            "host",
            "fission-test fusion",
        )
        return host, chans, fusion

    def split(self, host, chans):
        l2 = world_record(self.root / "state", "SC-L2", L_CAPS, L_REPS)
        s2 = world_record(self.root / "state", "SC-S2", S_CAPS, S_REPS)
        return fission_worlds(
            host,
            chans,
            "SC-FUSED",
            "SC-L2",
            "SC-S2",
            l2,
            s2,
            dict(PARTITION),
            "host",
            "fission-test split",
        )


class TestFission(Base):
    def test_fission_partition_custody_lifecycle(self):
        host, chans, _ = self.fused_host()
        fis = self.split(host, chans)
        # partition record: exact coverage, both sides non-empty
        self.assertEqual(fis["partition"], PARTITION)
        self.assertEqual(
            set(fis["partition"]),
            {"sched.composite", "sched.requirements", "sched.slots"},
        )
        # custody back-transfer per the partition (giver = composite)
        self.assertEqual(
            host.worlds["SC-L2"].custodians,
            {"sched.composite": "SC-L2", "sched.requirements": "SC-L2"},
        )
        self.assertEqual(host.worlds["SC-S2"].custodians, {"sched.slots": "SC-S2"})
        self.assertEqual(len(fis["transfers"]), 3)
        for t in fis["transfers"]:
            self.assertEqual(t["from"], "SC-FUSED")
            self.assertEqual(fis["partition"][t["state_class"]], t["to"])
        xfers = [e for e in host.ledger_entries() if e.get("kind") == "transfer"]
        givers = {e["actor"] for e in xfers[-3:]}
        self.assertEqual(givers, {"SC-FUSED"})
        # lifecycle moves: composite dissolved, children active
        self.assertEqual(host.worlds["SC-FUSED"].lifecycle, "dissolved")
        self.assertEqual(host.worlds["SC-L2"].lifecycle, "active")
        self.assertEqual(host.worlds["SC-S2"].lifecycle, "active")

    def test_fission_lineage_names_fusion(self):
        host, chans, _ = self.fused_host()
        fis = self.split(host, chans)
        for side, key in (("left", "lineage_left"), ("right", "lineage_right")):
            lin = fis[key]
            derived = [e["world"] for e in lin if e.get("rel") == "derived_from"]
            self.assertEqual(derived, ["SC-FUSED"])
            named = [e for e in lin if e.get("rel") == "fission-of"]
            self.assertEqual(len(named), 1)
            # the fusion being split is named: composite + its parents
            self.assertEqual(named[0]["fusion"], "SC-FUSED")
            self.assertEqual(sorted(named[0]["fusion_parents"]), ["SC-L", "SC-S"])
            self.assertEqual(named[0]["side"], side)
        self.assertEqual(
            fis["fusion"], {"fused_id": "SC-FUSED", "parents": ["SC-L", "SC-S"]}
        )
        # ... and the named parents resolve to ledger creates
        created = {
            e["payload"]["world_id"]
            for e in host.ledger_entries()
            if e.get("kind") == "create"
        }
        self.assertTrue({"SC-L", "SC-S"} <= created)
        # ledger fission entry carries the partition + named fusion
        entries = [e for e in host.ledger_entries() if e.get("kind") == "fission"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["payload"]["partition"], PARTITION)
        self.assertEqual(entries[0]["payload"]["fusion"]["fused_id"], "SC-FUSED")

    def test_fission_restores_channel(self):
        host, chans, _ = self.fused_host()
        self.assertNotIn("direct-channel:SC-L<->SC-S", chans.inventory())
        fis = self.split(host, chans)
        self.assertEqual(fis["restored_mechanism"], "direct-channel:SC-L2<->SC-S2")
        self.assertIn("direct-channel:SC-L2<->SC-S2", fis["after"]["mechanisms"])
        self.assertNotIn("direct-channel:SC-L2<->SC-S2", fis["before"]["mechanisms"])
        # the restored channel is live: cross-boundary sends flow again
        chan = chans.get("SC-L2", "SC-S2")
        chan.send({"kind": "probe", "n": 1})
        self.assertEqual(chan.n, 1)

    def test_fission_children_cooperate(self):
        host, chans, _ = self.fused_host()
        self.split(host, chans)
        m6 = run_split_pair_task(
            self.root, host, FI.S6_FISSION_FOLLOWUP, "SC-L2", "SC-S2"
        )
        self.assertTrue(m6["valid"])
        self.assertEqual(m6["quality"], m6["prefs_total"])
        self.assertEqual(m6["via"], ["SC-L2", "SC-S2"])
        # settle the children with 0 stranded (composite already settled)
        fin = finish_worlds(host, ["SC-L2", "SC-S2"], reason="fission t")
        self.assertTrue(fin["conservation_ok"])

    def test_fission_rejects_non_composite(self):
        worlds = DEMO.main_worlds(self.root / "state")
        host = setup_host(self.root, worlds)
        chans = ChannelRegistry()
        l2 = world_record(self.root / "state", "SC-L2", L_CAPS, L_REPS)
        s2 = world_record(self.root / "state", "SC-S2", S_CAPS, S_REPS)
        with self.assertRaises(ValueError) as ctx:
            fission_worlds(
                host,
                chans,
                "SC-L",
                "SC-L2",
                "SC-S2",
                l2,
                s2,
                {"sched.requirements": "SC-L2"},
                "host",
                "not a fusion",
            )
        self.assertIn("not a recorded fusion", str(ctx.exception))
        # no partial effects
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        self.assertNotIn("SC-L2", host.worlds)
        self.assertFalse(
            [e for e in host.ledger_entries() if e.get("kind") == "fission"]
        )

    def test_fission_rejects_bad_partition(self):
        host, chans, _ = self.fused_host()
        n_before = len(host.ledger_entries())
        cases = [
            (
                {"sched.requirements": "SC-L2", "sched.slots": "SC-S2"},
                "missing",
            ),  # incomplete coverage
            ({**PARTITION, "sched.ghost": "SC-L2"}, "unknown"),  # unknown class
            ({**PARTITION, "sched.slots": "SC-OUTSIDER"}, "outside"),  # outsider owner
            (
                {
                    "sched.composite": "SC-L2",
                    "sched.requirements": "SC-L2",
                    "sched.slots": "SC-L2",
                },
                "one-sided",
            ),  # all to one side
        ]
        for part, why in cases:
            l2 = world_record(self.root / "state", "SC-L2", L_CAPS, L_REPS)
            s2 = world_record(self.root / "state", "SC-S2", S_CAPS, S_REPS)
            with self.assertRaises(ValueError, msg=why):
                fission_worlds(
                    host,
                    chans,
                    "SC-FUSED",
                    "SC-L2",
                    "SC-S2",
                    l2,
                    s2,
                    part,
                    "host",
                    f"bad: {why}",
                )
        # no partial effects from any rejected attempt
        self.assertEqual(host.worlds["SC-FUSED"].lifecycle, "active")
        self.assertNotIn("SC-L2", host.worlds)
        self.assertEqual(len(host.ledger_entries()), n_before)

    def test_fission_rejects_dissolved(self):
        host, chans, _ = self.fused_host()
        self.split(host, chans)
        l2 = world_record(self.root / "state", "SC-L3", L_CAPS, L_REPS)
        s2 = world_record(self.root / "state", "SC-S3", S_CAPS, S_REPS)
        with self.assertRaises(RuntimeError):
            fission_worlds(
                host,
                chans,
                "SC-FUSED",
                "SC-L3",
                "SC-S3",
                l2,
                s2,
                dict(PARTITION),
                "host",
                "re-split",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
