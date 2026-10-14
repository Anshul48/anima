# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained-package port of successor-006 J1 persistent-worlds journey tests.

The journey from RUNBOOK.md, asserted stage by stage through the
CONSUMER interfaces on FRESH state: project world -> nested
experiment + delegation -> work -> real kill + byte-identical resume
-> responsibilities/evidence inspection -> fused composite -> reuse
UNMODIFIED in a second task -> verified export -> settle.

Run from the repo root:
    PYTHONDONTWRITEBYTECODE=1 python3 prototype/successor-006/test_j1.py

All run dirs live under successor-006/.test-tmp/.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

import anima_substrate  # noqa: E402

PKG = Path(anima_substrate.__file__).resolve().parent
TOP = PKG.parent.parent
TMPROOT = Path(tempfile.mkdtemp(prefix="anima-substrate-tests-"))

from anima_substrate.host import api  # noqa: E402
from anima_substrate.host.minihost import ContractViolation  # noqa: E402
from anima_substrate.participants.sched import sched_inputs as FI  # noqa: E402

DELEGATE = {"max_cost_usd": 0.5, "max_time_s": 30.0, "max_invocations": 50}


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if os.environ.get("SUBSTRATE_KEEP_TMP"):
            return
        shutil.rmtree(self.root, ignore_errors=True)

    def journey_root(self) -> Path:
        root = self.root / "j1"
        api.j1_init(root, "PROJ", "test journey")
        api.nest_op(
            root, "PROJ", "EXP1", dict(DELEGATE), ["j1.budget"], "test delegation"
        )
        return root


class TestJourney(Base):
    def test_full_journey(self):
        root = self.root / "j1"
        # 1. persistent project world on fresh state
        r = api.j1_init(root, "PROJ", "test journey")
        self.assertEqual(r["custody"], ["j1.budget", "j1.plan"])
        host, _ = api.open_run(root)
        self.assertEqual(host.worlds["PROJ"].lifecycle, "active")
        self.assertIn("grant.delegate", host.worlds["PROJ"].authorities)
        # 2. nested experiment + delegation (grant + custody move)
        n = api.nest_op(
            root, "PROJ", "EXP1", dict(DELEGATE), ["j1.budget"], "test delegation"
        )
        self.assertEqual(n["custody"], ["j1.budget"])
        host, _ = api.open_run(root)
        self.assertEqual(
            [e for e in host.worlds["EXP1"].lineage if e.get("rel") == "derived_from"],
            [{"rel": "derived_from", "world": "PROJ"}],
        )
        self.assertEqual(host.worlds["EXP1"].custodians, {"j1.budget": "EXP1"})
        self.assertEqual(host.worlds["PROJ"].custodians, {"j1.plan": "PROJ"})
        held_p = dict(host.holdings["PROJ"])
        held_e = dict(host.holdings["EXP1"])
        self.assertEqual(held_e["max_cost_usd"], 0.5)
        self.assertEqual(held_p["max_cost_usd"], 0.5)
        # 3. first work task through the experiment world
        w = api.j1_work_op(root, "EXP1", "J1-T1", verifier="PROJ")
        self.assertTrue(w["valid"])
        self.assertEqual(w["re_executed_invokes"], 0)
        # 4. interrupt (real kill) + reopen byte-identical
        k = api.j1_kill_resume_op(root, "EXP1", "J1-T2", verifier="PROJ")
        self.assertNotEqual(k["child_rc"], 0)
        self.assertTrue(k["valid"])
        self.assertEqual(k["re_executed_invokes"], 0)
        self.assertIn("sched.formulate@formulate@v1", k["skipped"])
        # 5. inspect responsibilities + evidence
        s = api.j1_status_op(root)
        self.assertTrue(s["conservation"]["ok"])
        self.assertEqual(s["worlds"]["EXP1"]["custody"], ["j1.budget"])
        self.assertEqual(len(s["delegations"]), 2)
        self.assertEqual(len(s["nests"]), 1)
        self.assertEqual(len(s["solutions"]), 2)
        self.assertIn("verdict-J1-T1.json", s["worlds"]["PROJ"]["verdicts"])
        # 6. fuse into one composite (real ownership change)
        f = api.fuse_op(root, "PROJ", "EXP1", "PROJ-FUSED", "test composite")
        self.assertEqual(f["fused_id"], "PROJ-FUSED")
        host, _ = api.open_run(root)
        self.assertEqual(
            host.worlds["PROJ-FUSED"].custodians,
            {"j1.plan": "PROJ-FUSED", "j1.budget": "PROJ-FUSED"},
        )
        # 7a. reuse in the first follow-up task ...
        m1 = api.reuse_op(root, "PROJ-FUSED", dict(FI.S4_FOLLOWUP))
        self.assertTrue(m1["valid"])
        self.assertTrue(m1["lineage_ok"])
        snap = self._composite_snapshot(root, "PROJ-FUSED")
        # 7b. ... and UNMODIFIED in a second task: nothing about the
        # composite changes between the two reuses except the reuse
        # invokes themselves (no new grant, no custody move, no
        # lifecycle edge, identical lineage).
        m2 = api.reuse_op(root, "PROJ-FUSED", dict(FI.S6_FISSION_FOLLOWUP))
        self.assertTrue(m2["valid"])
        self.assertEqual(m2["derived_from"], m1["derived_from"])
        snap2 = self._composite_snapshot(root, "PROJ-FUSED")
        self.assertEqual(snap2, snap)
        # 8. verified export bundle
        x = api.j1_export_op(root, "PROJ-FUSED")
        self.assertEqual(x["derived_from"], ["PROJ", "EXP1"])
        self.assertEqual(x["solutions"], ["S4-followup", "S6-followup"])
        manifest = json.loads(Path(x["export_ref"]).read_text(encoding="utf-8"))
        for sol in manifest["solutions"]:
            digest = hashlib.sha256((root / sol["artifact"]).read_bytes()).hexdigest()
            self.assertEqual(digest, sol["sha256"])
        # 9. settle: 0 stranded, conservation ok
        done = api.settle_op(root, ["PROJ-FUSED"], "journey complete")
        self.assertTrue(done["conservation_ok"])

    @staticmethod
    def _composite_snapshot(root: Path, composite: str) -> dict:
        host, _ = api.open_run(root)
        rec = host.worlds[composite]
        grants = [
            e["payload"]
            for e in host.ledger_entries()
            if e.get("kind") == "grant" and e["payload"].get("to") == composite
        ]
        return {
            "lifecycle": rec.lifecycle,
            "custodians": dict(rec.custodians),
            "lineage": copy.deepcopy(rec.lineage),
            "grants": [(g["grant_id"], g["from"], g["limits"]) for g in grants],
        }

    def test_runbook_cli_smoke(self):
        # Every RUNBOOK command runs through release.py (except the
        # kill drill, covered above + in the demo).
        root = self.root / "cli"
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        def cli(*argv: str) -> str:
            p = subprocess.run(
                [sys.executable, "-m", "anima_substrate", *argv],
                cwd=str(HERE),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            return p.stdout

        cli(
            "j1-init",
            "--state-dir",
            str(root),
            "--project",
            "PROJ",
            "--reason",
            "cli smoke",
        )
        cli(
            "ops",
            "nest",
            "--state-dir",
            str(root),
            "--project",
            "PROJ",
            "--child",
            "EXP1",
            "--delegate",
            "0.5,30,50",
            "--custody",
            "j1.budget",
            "--reason",
            "cli smoke",
        )
        out = cli(
            "ops",
            "j1-work",
            "--state-dir",
            str(root),
            "--world",
            "EXP1",
            "--task",
            "CLI-T1",
            "--verifier",
            "PROJ",
        )
        self.assertIn("valid=True", out)
        out = cli("ops", "j1-status", "--state-dir", str(root))
        self.assertIn("EXP1: active", out)
        cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "PROJ",
            "--b",
            "EXP1",
            "--fused",
            "F",
            "--reason",
            "cli smoke",
        )
        out = cli(
            "ops",
            "reuse",
            "--state-dir",
            str(root),
            "--composite",
            "F",
            "--followup",
            "S4",
        )
        self.assertIn("valid=True", out)
        out = cli(
            "ops",
            "reuse",
            "--state-dir",
            str(root),
            "--composite",
            "F",
            "--followup",
            "S6",
        )
        self.assertIn("valid=True", out)
        out = cli("ops", "j1-export", "--state-dir", str(root), "--composite", "F")
        self.assertIn("S4-followup", out)


class TestNestRefusals(Base):
    def test_over_delegation_refused_with_zero_mutation(self):
        root = self.root / "j1"
        api.j1_init(root, "PROJ", "test")
        host, _ = api.open_run(root)
        n_entries = len(host.ledger_entries())
        held = dict(host.holdings["PROJ"])
        with self.assertRaises(ContractViolation):
            api.nest_op(
                root,
                "PROJ",
                "EXP9",
                {"max_cost_usd": 999.0, "max_time_s": 1.0, "max_invocations": 1},
                [],
                "over-delegation",
            )
        host2, _ = api.open_run(root)
        self.assertNotIn("EXP9", host2.worlds)
        # Only reopen markers were appended (one per open_run): zero
        # op mutation — no create/grant for the refused child.
        self.assertEqual(len(host2.ledger_entries()), n_entries + 2)
        kinds = [e.get("kind") for e in host2.ledger_entries()]
        self.assertNotIn("create", kinds[n_entries:])
        self.assertEqual(dict(host2.holdings["PROJ"]), held)

    def test_exact_holdings_delegation_allowed(self):
        root = self.root / "j1"
        api.j1_init(root, "PROJ", "test")
        host, _ = api.open_run(root)
        held = dict(host.holdings["PROJ"])
        api.nest_op(root, "PROJ", "EXP1", dict(held), ["j1.budget"], "exact delegation")
        host2, _ = api.open_run(root)
        self.assertEqual(host2.holdings["PROJ"]["max_cost_usd"], 0.0)

    def test_bad_nest_inputs_refused(self):
        root = self.root / "j1"
        api.j1_init(root, "PROJ", "test")
        with self.assertRaises(ContractViolation):
            api.nest_op(
                root, "PROJ", "EXP1", dict(DELEGATE), ["j1.nope"], "unknown custody"
            )
        with self.assertRaises(RuntimeError):
            api.nest_op(root, "NOBODY", "EXP1", dict(DELEGATE), [], "unknown project")
        with self.assertRaises(ValueError):
            api.nest_op(
                root,
                "PROJ",
                "EXP1",
                dict(DELEGATE),
                [],
                "bad preset",
                child_preset="NOBODY",
            )
        api.nest_op(root, "PROJ", "EXP1", dict(DELEGATE), ["j1.budget"], "ok")
        with self.assertRaises(ContractViolation):
            api.nest_op(root, "PROJ", "EXP1", dict(DELEGATE), [], "duplicate id")

    def test_export_refusals(self):
        root = self.journey_root()
        with self.assertRaises(RuntimeError):
            api.j1_export_op(root, "PROJ")  # not a composite
        with self.assertRaises(RuntimeError):
            api.j1_export_op(root, "NOBODY")


if __name__ == "__main__":
    unittest.main(verbosity=2)
