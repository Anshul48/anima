# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained-package port of successor-006 quarantine-transfer repair tests (R11 owed item).

The supported repair path for kill-during-quarantine-transfer: the
complete-vs-rollback DECISION stays with the operator, and both
directions are supported ops (`quarantine_complete_op` /
`quarantine_rollback_op`, CLI `ops quarantine-complete` /
`ops quarantine-rollback`).

Coverage: kill at EVERY quarantine append boundary x both directions,
kill-during-repair convergence, wrong-standby / custody-moved /
double-resolve refusals, completed-quarantine silence (no false
positive), plain-suspend silence, re-quarantine after rollback.

Run from the repo root:
    PYTHONDONTWRITEBYTECODE=1 python3 prototype/successor-006/test_quarantine_repair.py

All run dirs live under successor-006/.test-tmp/.
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
from anima_substrate.host.minihost import ContractViolation  # noqa: E402

WORLD = "SC-L"  # 2 commitment classes -> k-of-N transfer coverage
STANDBY = "SC-S"
COMMITMENTS = ["sched.composite", "sched.requirements"]

# Quarantine append map (fresh `ops quarantine` process):
#   #1 host_reopen, #2 suspend/lifecycle, #3 checkpoint entry,
#   #4 transfer[0], #5 transfer[1], #6 quarantine entry.
CRASH_POINTS = [1, 2, 3, 4, 5, 6]


def _crash_quarantine(root: Path, n: int) -> int:
    env = dict(os.environ)
    env["SUBSTRATE_CRASH_AFTER_APPENDS"] = str(n)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "anima_substrate",
            "ops",
            "quarantine",
            "--state-dir",
            str(root),
            "--world",
            WORLD,
            "--standby",
            STANDBY,
            "--reason",
            "repair-matrix",
        ],
        cwd=str(HERE),
        env=env,
        capture_output=True,
        text=True,
    )
    return p.returncode


def _crash_cli(root: Path, op: str, n: int) -> int:
    env = dict(os.environ)
    env["SUBSTRATE_CRASH_AFTER_APPENDS"] = str(n)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "anima_substrate",
            "ops",
            op,
            "--state-dir",
            str(root),
            "--world",
            WORLD,
            "--standby",
            STANDBY,
            "--reason",
            "repair-matrix",
        ],
        cwd=str(HERE),
        env=env,
        capture_output=True,
        text=True,
    )
    return p.returncode


def _quarantine_entries(root: Path, kind: str = "quarantine") -> list[dict]:
    host, _ = api.open_run(root)
    return [e for e in host.ledger_entries() if e.get("kind") == kind]


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)

    def tearDown(self):
        if os.environ.get("SUBSTRATE_KEEP_TMP"):
            return
        shutil.rmtree(self.root, ignore_errors=True)

    def fresh(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        api.init_run(self.root)
        return self.root


class TestCompleteMatrix(Base):
    def test_kill_at_every_boundary_then_complete(self):
        for n in CRASH_POINTS:
            with self.subTest(crash_after_appends=n):
                root = self.root / f"n{n}"
                root.mkdir(parents=True, exist_ok=True)
                api.init_run(root)
                if n <= 6:
                    rc = _crash_quarantine(root, n)
                    # N=6 crashes AFTER the quarantine entry: the op is
                    # already ledger-complete (still exit 42, by hook).
                    self.assertEqual(rc, 42, f"N={n}")
                rep = api.recover_op(root)
                partials = [
                    p for p in rep["partial_quarantines"] if p["world"] == WORLD
                ]
                if n == 1:
                    self.assertEqual(partials, [], f"N={n}")
                    with self.assertRaises(RuntimeError):
                        api.quarantine_complete_op(root, WORLD, STANDBY)
                    # No trace: the op simply runs.
                    api.quarantine_op(root, WORLD, STANDBY, "retry")
                    continue
                if n == 6:
                    self.assertEqual(partials, [], f"N={n}")
                    with self.assertRaises(RuntimeError):
                        api.quarantine_complete_op(root, WORLD, STANDBY)
                    continue
                self.assertEqual(len(partials), 1, f"N={n}")
                self.assertEqual(
                    len(partials[0]["transfers_done"]), max(0, n - 3), f"N={n}"
                )
                if n == 2:
                    self.assertEqual(
                        partials[0]["pending_source"], "side-file-checkpoint", f"N={n}"
                    )
                rec = api.quarantine_complete_op(
                    root, WORLD, STANDBY, "matrix-complete"
                )
                self.assertEqual(rec["commitments"], COMMITMENTS)
                self.assertEqual(len(rec["transfers"]), 2)
                self.assertTrue(rec["recovered"])
                host, _ = api.open_run(root)
                self.assertEqual(host.worlds[WORLD].lifecycle, "suspended")
                self.assertEqual(dict(host.worlds[WORLD].custodians), {})
                for sc in COMMITMENTS:
                    self.assertEqual(host.worlds[STANDBY].custodians.get(sc), STANDBY)
                q = _quarantine_entries(root)
                self.assertEqual(len(q), 1)
                self.assertTrue(q[0]["payload"].get("recovered"))
                self.assertTrue(host.verify_conservation()["ok"])
                # Resolved: detection silent, settle proceeds, 0 stranded.
                rep2 = api.recover_op(root)
                self.assertEqual(rep2["partial_quarantines"], [])
                done = api.settle_op(root, [WORLD, STANDBY], "matrix done")
                self.assertTrue(done["conservation_ok"])

    def test_complete_is_exactly_the_quarantine_end_state(self):
        # A repaired quarantine is indistinguishable (modulo the
        # recovered flag + reason strings) from a clean one: same
        # lifecycles, same custody, same entry shape.
        clean = self.root / "clean"
        clean.mkdir(parents=True, exist_ok=True)
        api.init_run(clean)
        api.quarantine_op(clean, WORLD, STANDBY, "clean")
        partial = self.root / "partial"
        partial.mkdir(parents=True, exist_ok=True)
        api.init_run(partial)
        self.assertEqual(_crash_quarantine(partial, 4), 42)
        api.quarantine_complete_op(partial, WORLD, STANDBY, "repair")
        hc, _ = api.open_run(clean)
        hp, _ = api.open_run(partial)
        for wid in (WORLD, STANDBY):
            self.assertEqual(hp.worlds[wid].lifecycle, hc.worlds[wid].lifecycle)
            self.assertEqual(
                dict(hp.worlds[wid].custodians), dict(hc.worlds[wid].custodians)
            )
        qc = _quarantine_entries(clean)[0]["payload"]
        qp = _quarantine_entries(partial)[0]["payload"]
        self.assertEqual(qp["world_id"], qc["world_id"])
        self.assertEqual(qp["standby"], qc["standby"])
        self.assertEqual(qp["commitments"], qc["commitments"])
        self.assertEqual(qp["transfers"], qc["transfers"])


class TestRollbackMatrix(Base):
    def test_kill_at_every_boundary_then_rollback(self):
        for n in (2, 3, 4, 5):
            with self.subTest(crash_after_appends=n):
                root = self.root / f"n{n}"
                root.mkdir(parents=True, exist_ok=True)
                api.init_run(root)
                self.assertEqual(_crash_quarantine(root, n), 42)
                rec = api.quarantine_rollback_op(
                    root, WORLD, STANDBY, "matrix-rollback"
                )
                self.assertEqual(len(rec["transfers_reversed"]), max(0, n - 3))
                host, _ = api.open_run(root)
                self.assertEqual(host.worlds[WORLD].lifecycle, "active")
                for sc in COMMITMENTS:
                    self.assertEqual(host.worlds[WORLD].custodians.get(sc), WORLD)
                rb = _quarantine_entries(root, "quarantine_rollback")
                self.assertEqual(len(rb), 1)
                self.assertTrue(host.verify_conservation()["ok"])
                rep = api.recover_op(root)
                self.assertEqual(rep["partial_quarantines"], [])
                # The rolled-back world quarantines cleanly afterwards.
                api.quarantine_op(root, WORLD, STANDBY, "re-quarantine")
                host2, _ = api.open_run(root)
                self.assertEqual(host2.worlds[WORLD].lifecycle, "suspended")

    def test_rollback_then_complete_refused_and_vice_versa(self):
        root = self.fresh()
        self.assertEqual(_crash_quarantine(root, 4), 42)
        api.quarantine_rollback_op(root, WORLD, STANDBY, "rb")
        with self.assertRaises(RuntimeError):
            api.quarantine_complete_op(root, WORLD, STANDBY, "late")
        with self.assertRaises(RuntimeError):
            api.quarantine_rollback_op(root, WORLD, STANDBY, "again")
        root2 = self.root / "other"
        root2.mkdir(parents=True, exist_ok=True)
        api.init_run(root2)
        self.assertEqual(_crash_quarantine(root2, 4), 42)
        api.quarantine_complete_op(root2, WORLD, STANDBY, "cp")
        with self.assertRaises(RuntimeError):
            api.quarantine_rollback_op(root2, WORLD, STANDBY, "late")
        with self.assertRaises(RuntimeError):
            api.quarantine_complete_op(root2, WORLD, STANDBY, "again")


class TestRefusals(Base):
    def _partial(self, n: int = 4) -> Path:
        root = self.fresh()
        self.assertEqual(_crash_quarantine(root, n), 42)
        return root

    def test_wrong_standby_refused(self):
        root = self._partial()
        # A third, ACTIVE world as the wrong standby: the refusal must
        # name the RECORDED standby, proving the caller's standby is
        # checked against the ledger (never silently adopted).
        from anima_substrate.host.pipeline import Q_CAPS
        from anima_substrate.host.routing import GRANT_LIMITS, world_record

        host, _ = api.open_run(root)
        host.create_world(
            world_record(root / "state", "SC-X", Q_CAPS, [("sched-list", "v1")]),
            "host",
            grant_limits=dict(GRANT_LIMITS),
        )
        host.transition("SC-X", "active", "host", reason="test standby")
        api._remember_creation(root, "SC-X", Q_CAPS, [("sched-list", "v1")])
        with self.assertRaises(RuntimeError) as cm:
            api.quarantine_complete_op(root, WORLD, "SC-X", "wrong")
        self.assertIn(STANDBY, str(cm.exception))
        with self.assertRaises(RuntimeError) as cm2:
            api.quarantine_rollback_op(root, WORLD, "SC-X", "wrong")
        self.assertIn(STANDBY, str(cm2.exception))

    def test_unknown_standby_refused(self):
        root = self._partial()
        with self.assertRaises(RuntimeError):
            api.quarantine_complete_op(root, WORLD, "NOBODY", "x")
        with self.assertRaises(RuntimeError):
            api.quarantine_rollback_op(root, WORLD, "NOBODY", "x")

    def test_custody_moved_refused(self):
        root = self._partial(4)  # sched.composite already with SC-S
        host, _ = api.open_run(root)
        host.transfer_custody(
            "sched.composite",
            STANDBY,
            WORLD,
            actor=STANDBY,
            reason="test move",
            continuity="test",
        )
        with self.assertRaises(ContractViolation):
            api.quarantine_complete_op(root, WORLD, STANDBY, "moved")
        with self.assertRaises(ContractViolation):
            api.quarantine_rollback_op(root, WORLD, STANDBY, "moved")

    def test_complete_after_rollback_started_refused(self):
        root = self._partial(5)  # both transfers recorded
        # Interrupt a rollback after its first reversal (subprocess:
        # #1 host_reopen, #2 first reversal).
        self.assertEqual(_crash_cli(root, "quarantine-rollback", 2), 42)
        with self.assertRaises(RuntimeError) as cm:
            api.quarantine_complete_op(root, WORLD, STANDBY, "mixed")
        self.assertIn("rollback", str(cm.exception))
        # ... while the rollback itself converges.
        rec = api.quarantine_rollback_op(root, WORLD, STANDBY, "finish")
        self.assertEqual(rec["adopted_reversals"], ["sched.requirements"])

    def test_clean_quarantine_is_silent(self):
        root = self.fresh()
        api.quarantine_op(root, WORLD, STANDBY, "clean")
        rep = api.recover_op(root)
        self.assertEqual(rep["partial_quarantines"], [])
        with self.assertRaises(RuntimeError):
            api.quarantine_complete_op(root, WORLD, STANDBY, "x")
        with self.assertRaises(RuntimeError):
            api.quarantine_rollback_op(root, WORLD, STANDBY, "x")

    def test_plain_suspend_is_silent(self):
        root = self.fresh()
        host, _ = api.open_run(root)
        host.suspend(WORLD, "host", "plain probe", pending_effects=[])
        rep = api.recover_op(root)
        self.assertEqual(rep["partial_quarantines"], [])


class TestKillDuringRepair(Base):
    def test_kill_during_complete_converges(self):
        root = self.fresh()
        self.assertEqual(_crash_quarantine(root, 4), 42)
        # Completion appends: #1 host_reopen, #2 remaining transfer,
        # #3 quarantine entry. Crash after #2: still partial.
        self.assertEqual(_crash_cli(root, "quarantine-complete", 2), 42)
        rep = api.recover_op(root)
        self.assertEqual(len(rep["partial_quarantines"]), 1)
        rec = api.quarantine_complete_op(root, WORLD, STANDBY, "converge")
        self.assertEqual(len(rec["transfers"]), 2)
        host, _ = api.open_run(root)
        self.assertEqual(
            [
                e for e in host.ledger_entries() if e.get("kind") == "quarantine"
            ].__len__(),
            1,
        )
        self.assertTrue(host.verify_conservation()["ok"])

    def test_kill_during_rollback_converges(self):
        for crash_n in (2, 3, 4):
            with self.subTest(crash_after_appends=crash_n):
                root = self.root / f"rb{crash_n}"
                root.mkdir(parents=True, exist_ok=True)
                api.init_run(root)
                self.assertEqual(_crash_quarantine(root, 5), 42)
                # Rollback appends: #1 host_reopen, #2/#3 reversals,
                # #4 lifecycle, #5 reattach, #6 rollback entry.
                self.assertEqual(_crash_cli(root, "quarantine-rollback", crash_n), 42)
                rec = api.quarantine_rollback_op(root, WORLD, STANDBY, "converge")
                self.assertEqual(len(rec["transfers_reversed"]), 2)
                host, _ = api.open_run(root)
                self.assertEqual(host.worlds[WORLD].lifecycle, "active")
                for sc in COMMITMENTS:
                    self.assertEqual(host.worlds[WORLD].custodians.get(sc), WORLD)
                rb = [
                    e
                    for e in host.ledger_entries()
                    if e.get("kind") == "quarantine_rollback"
                ]
                self.assertEqual(len(rb), 1)
                self.assertTrue(host.verify_conservation()["ok"])

    def test_detection_points_at_supported_ops(self):
        root = self.fresh()
        self.assertEqual(_crash_quarantine(root, 4), 42)
        rep = api.recover_op(root)
        self.assertEqual(len(rep["quarantine_operator_steps"]), 1)
        step = rep["quarantine_operator_steps"][0]
        self.assertIn("quarantine-complete", step)
        self.assertIn("quarantine-rollback", step)
        # And the involved world is still blocked from settle.
        with self.assertRaises(RuntimeError):
            api.recover_op(root, worlds=[WORLD])


if __name__ == "__main__":
    unittest.main(verbosity=2)
