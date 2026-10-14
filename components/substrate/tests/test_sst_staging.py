# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained SST-staging tests (M2 optional extra, package-new).

Refusals run always (no staging needed); consumption legs run only
when SUBSTRATE_SST_ROOT passes the compat probe, else skip with an
explicit reason (reported separately, never green).
"""

from __future__ import annotations

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
from anima_substrate.participants import get_family  # noqa: E402
from anima_substrate.participants.sst.staged import (  # noqa: E402
    SSTBoundary,
    probe,
)


def _staging():
    root = os.environ.get("SUBSTRATE_SST_ROOT", "").strip()
    if not root:
        return (
            None,
            None,
            "SUBSTRATE_SST_ROOT unset (SST is a caller-staged "
            "optional extra; see docs/SST-STAGING.md)",
        )
    try:
        rep = probe(root)
    except SSTBoundary as exc:
        return None, None, f"SST compat probe failed: {exc}"
    return Path(rep["sst_root"]), Path(rep["venv_py"]), None


SST_ROOT, SST_VENV_PY, SST_SKIP = _staging()


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)


class TestSSTRefusals(Base):
    """Refusal legs: always run, never need staging."""

    def test_probe_refuses_unset_root(self):
        env = {k: v for k, v in os.environ.items() if k not in ("SUBSTRATE_SST_ROOT",)}
        script = "from anima_substrate.participants.sst.staged import probe; probe()"
        proc = subprocess.run(
            [sys.executable, "-c", script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("SUBSTRATE_SST_ROOT", proc.stderr)

    def test_probe_refuses_missing_tree(self):
        with self.assertRaises(SSTBoundary) as ctx:
            probe(self.root / "no-such-root")
        self.assertIn("no staged SST checkout", str(ctx.exception))

    def test_run_tasks_with_sst_refuses_unstaged(self):
        state = self.root / "state"
        api.init_run(state)
        script = (
            "import os; os.environ.pop('SUBSTRATE_SST_ROOT', None); "
            "from anima_substrate.host import api; "
            f"api.run_tasks({str(state)!r}, ['S1'], with_sst=True)"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("SUBSTRATE_SST_ROOT", proc.stderr)

    def test_sst_family_create_refuses_unstaged(self):
        state = self.root / "state"
        api.init_run(state)
        env = dict(os.environ)
        env.pop("SUBSTRATE_SST_ROOT", None)
        script = (
            "import os; os.environ.pop('SUBSTRATE_SST_ROOT', None); "
            "from anima_substrate.participants import get_family; "
            f"get_family('sst', 'v1').create({str(state)!r}, "
            "'SST1', {}, 't')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("sst create refused", proc.stderr)
        # zero ledger effect: the world was never born
        host, _ = api.open_run(state)
        self.assertNotIn("SST1", host.worlds)


@unittest.skipIf(SST_SKIP is not None, SST_SKIP or "SST unstaged")
class TestSSTStaged(Base):
    """Consumption legs over the caller-staged root."""

    def test_probe_reports_pin(self):
        assert SST_ROOT is not None
        rep = probe(SST_ROOT)
        self.assertEqual(rep["verdict"], "MATCH")
        self.assertEqual(rep["snapshot_check"]["file_count"], 54)
        self.assertEqual(rep["pydantic_version"], "2.13.5")
        self.assertTrue(rep["git"]["pinned"])

    def test_probe_refuses_drifted_tree(self):
        assert SST_ROOT is not None
        staged = self.root / "staged-copy"
        shutil.copytree(
            SST_ROOT / "src",
            staged / "src",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        target = staged / "src" / "sst" / "search" / "policy.py"
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("# tamper\n")
        with self.assertRaises(SSTBoundary) as ctx:
            probe(staged)
        self.assertIn("sst/search/policy.py", str(ctx.exception))

    def test_probe_refuses_wrong_interpreter(self):
        assert SST_ROOT is not None
        with self.assertRaises(SSTBoundary) as ctx:
            probe(SST_ROOT, sys.executable)
        self.assertIn("pydantic", str(ctx.exception))

    def test_run_tasks_with_sst_staged(self):
        state = self.root / "state"
        api.init_run(state)
        rep = api.run_tasks(state, ["S1"], with_sst=True)
        self.assertTrue(rep["tasks"]["S1"]["valid"])
        self.assertEqual(rep["SST"]["snapshot_check"], "MATCH")
        self.assertEqual(rep["SST"]["cost_usd"], 0.0)
        self.assertTrue(rep["SST"]["snapshot_unchanged"])
        self.assertTrue((state / "sst-leg" / "SNAPSHOT-CHECK.json").exists())

    def test_sst_family_create_run_recover(self):
        state = self.root / "state"
        api.init_run(state)
        fam = get_family("sst", "v1")
        created = fam.create(state, "SST1", {}, "t")
        self.assertEqual(
            created["staging"]["snapshot_hash"],
            "5f1f37893b0f5ab9ff7dcf0ce2c60b287b51647e2f18f627eabf5510537cad96",
        )
        rep = fam.run(state, "SST1", {"task_id": "T1"})
        self.assertEqual(rep["termination_reason"], "champion_found")
        self.assertEqual(rep["cost_usd"], 0.0)
        self.assertIn("measured_cost", rep)
        rec = fam.recover(state, "SST1")
        self.assertEqual(rec["snapshot"], "MATCH")

    def test_sst_family_change_refuses(self):
        state = self.root / "state"
        api.init_run(state)
        fam = get_family("sst", "v1")
        fam.create(state, "SST1", {}, "t")
        with self.assertRaises(ValueError) as ctx:
            fam.change(state, "SST1", "v2", "t")
        self.assertIn("re-qualification", str(ctx.exception))


@unittest.skipIf(SST_SKIP is not None, SST_SKIP or "SST unstaged")
class TestRunDemoStaged(Base):
    def test_run_demo_staged(self):
        from anima_substrate.demos import successor_demo as DEMO

        ev = DEMO.run_demo(self.root / "demo")
        for stage in ("S1", "S2", "S3", "S4", "S6"):
            self.assertTrue(ev[stage]["valid"], stage)
        self.assertEqual(ev["kill"]["child_rc"] != 0, True)
        self.assertEqual(ev["S3"]["re_executed_invokes"], 0)
        self.assertEqual(ev["SST"]["snapshot_check"], "MATCH")
        self.assertEqual(ev["SST"]["cost_usd"], 0.0)
        self.assertTrue(ev["SST"]["snapshot_unchanged"])
        for wid, hold in ev["settle"]["stranded"].items():
            self.assertEqual(
                hold,
                {"max_cost_usd": 0.0, "max_time_s": 0.0, "max_invocations": 0},
                wid,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
