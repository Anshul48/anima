# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained-package port of successor-004 R1 atomic-settle + interruption-boundary tests.

In-process refusal-atomicity proofs (fast) plus fault-injection kills
at EVERY ledger boundary of settle/fuse/fission through the consumer
CLI (release.py), including repeated kills, kill-during-recovery, and
real SIGKILLs. Recovery always goes through `ops recover`.

Successor-004 (R3) adds TestAtomicConstruction (every side-file write
routes through atomic_write_text: same-dir temp + os.replace) and
TestSpecWindowKillLoop (50 real SIGKILLs staggered across the
fission op tail incl. the spec-write window: zero torn side files,
every landing converges or refuses only in a classified way), and
TestWriteInterior (deterministic crashes INSIDE ledger appends and
side-file writes + torn-file fixtures: interior kills converge for
side files and refuse loudly as disk-loss for a torn ledger tail).

Run from the repo root:
    PYTHONDONTWRITEBYTECODE=1 python3 prototype/successor-005/test_atomicity.py

All run dirs live under successor-005/.test-tmp/ (nothing is written
outside successor-005/).
"""

from __future__ import annotations

import ast
import copy
import importlib
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent

import anima_substrate  # noqa: E402

PKG = Path(anima_substrate.__file__).resolve().parent
TOP = PKG.parent.parent
TMPROOT = Path(tempfile.mkdtemp(prefix="anima-substrate-tests-"))

from anima_substrate.demos import successor_demo as DEMO  # noqa: E402
from anima_substrate.host import api  # noqa: E402
from anima_substrate.host.fusion import fission_worlds, fuse_worlds  # noqa: E402
from anima_substrate.host.minihost import ContractViolation  # noqa: E402
from anima_substrate.host.pipeline import (  # noqa: E402
    FUSED_CAPS,
    L_CAPS,
    L_REPS,
    S_CAPS,
    S_REPS,
    LaneCtx,
    run_sched_task,
)
from anima_substrate.host.routing import (  # noqa: E402
    ChannelRegistry,
    HCoordinator,
    finish_worlds,
    setup_host,
    world_record,
)
from anima_substrate.participants.sched import sched_inputs as FI  # noqa: E402

sys.path.insert(0, str(HERE))
import provcheck  # noqa: E402

PARTITION = {
    "sched.composite": "SC-L2",
    "sched.requirements": "SC-L2",
    "sched.slots": "SC-S2",
}
PARTITION_CLI = "sched.composite=SC-L2,sched.requirements=SC-L2,sched.slots=SC-S2"

CRASH_RC = 42


def child_env(**extra) -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("SUBSTRATE_CRASH_AFTER_APPENDS", None)
    env.pop("SUBSTRATE_CRASH_AT", None)
    env.pop("SUBSTRATE_CRASH_MID_APPEND", None)
    env.pop("SUBSTRATE_CRASH_MID_SIDE_WRITE", None)
    env.update(extra)
    return env


def cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "anima_substrate", *args],
        cwd=str(HERE),
        env=env or child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def inspect_json(root: Path) -> dict:
    proc = cli("inspect", "--state-dir", str(root), "--json")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def ledger_lines(root: Path) -> list[dict]:
    out = []
    with open(root / "ledger.jsonl", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def kinds_of(root: Path) -> dict[str, int]:
    kinds: dict[str, int] = {}
    for e in ledger_lines(root):
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    return kinds


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

    def cli_run(self, name: str, tasks=("S1", "S2")) -> Path:
        root = self.root / name
        proc = cli("init", "--state-dir", str(root))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli("run", "--state-dir", str(root), "--tasks", ",".join(tasks))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return root

    def fresh_copy(self, template: Path, name: str) -> Path:
        dest = self.root / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(template, dest)
        return dest


class TestAtomicRefusal(Base):
    """Refusal/failure leaves ZERO partial dissolves (in-process)."""

    def test_refuse_unknown_world_zero_partials(self):
        host, _ = self.main_host()
        run_sched_task(self.root, host, FI.S1, _central_ctx())
        n_before = len(host.ledger_entries())
        with self.assertRaises(ContractViolation) as ctx:
            finish_worlds(host, ["SC-L", "SC-NOPE"], reason="t")
        self.assertIn("zero worlds dissolved", str(ctx.exception))
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        self.assertEqual(host.worlds["SC-S"].lifecycle, "active")
        fresh = host.ledger_entries()[n_before:]
        self.assertEqual([e["kind"] for e in fresh], ["deny"])
        host.verify_conservation()

    def test_refuse_unsettled_terminal_probe_zero_partials(self):
        # LIMITS-11's example: a pre-existing unsettled terminal used to
        # strand fresh dissolves; now the batch refuses up front.
        host, _ = self.main_host()
        run_sched_task(self.root, host, FI.S1, _central_ctx())
        host.append(
            "lifecycle",
            {
                "world_id": "SC-GHOST",
                "from": "active",
                "to": "dissolved",
                "reason": "probe",
            },
            actor="host",
        )
        n_before = len(host.ledger_entries())
        with self.assertRaises(ContractViolation) as ctx:
            finish_worlds(host, ["SC-L", "SC-S"], reason="t")
        self.assertIn("zero worlds dissolved", str(ctx.exception))
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        self.assertEqual(host.worlds["SC-S"].lifecycle, "active")
        fresh = host.ledger_entries()[n_before:]
        self.assertEqual([e["kind"] for e in fresh], ["deny"])
        markers = [e for e in host.ledger_entries() if e.get("kind") == "grant_settle"]
        self.assertEqual(markers, [])
        with self.assertRaises(ContractViolation):
            host.verify_conservation()  # pre-existing violation intact

    def test_refuse_residual_holdings_single_world(self):
        host, _ = self.main_host()
        run_sched_task(self.root, host, FI.S1, _central_ctx())
        host.holdings["SC-L"]["max_cost_usd"] += 5.0  # white-box fault
        n_before = len(host.ledger_entries())
        with self.assertRaises(ContractViolation):
            host.settle_grants("SC-L", "host", "t")
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        fresh = host.ledger_entries()[n_before:]
        self.assertEqual([e["kind"] for e in fresh], ["deny"])
        with self.assertRaises(ContractViolation):
            finish_worlds(host, ["SC-L", "SC-S"], reason="t")
        self.assertEqual(host.worlds["SC-S"].lifecycle, "active")

    def test_refuse_suspended_missing_checkpoint_both_orders(self):
        for order in (["SC-L", "SC-S"], ["SC-S", "SC-L"]):
            with self.subTest(order=order):
                root = self.root / f"ord-{order[0]}"
                root.mkdir(parents=True)
                worlds = DEMO.main_worlds(root / "state")
                host = setup_host(root, worlds)
                run_sched_task(root, host, FI.S1, _central_ctx())
                host.suspend("SC-S", "host", "probe", pending_effects=[])
                (
                    Path(host.worlds["SC-S"].instance_state_dir) / "checkpoint.json"
                ).unlink()
                n_before = len(host.ledger_entries())
                with self.assertRaises(ContractViolation) as ctx:
                    finish_worlds(host, list(order), reason="t")
                self.assertIn("zero worlds dissolved", str(ctx.exception))
                self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
                self.assertEqual(host.worlds["SC-S"].lifecycle, "suspended")
                fresh = host.ledger_entries()[n_before:]
                self.assertEqual([e["kind"] for e in fresh], ["deny"])
                host.verify_conservation()

    def test_check_settleable_side_effect_free(self):
        host, _ = self.main_host()
        run_sched_task(self.root, host, FI.S1, _central_ctx())
        ledger_before = (self.root / "ledger.jsonl").read_bytes()
        hold_before = copy.deepcopy(host.holdings)
        life_before = {w: r.lifecycle for w, r in host.worlds.items()}
        plan = host.check_settleable("SC-L")
        self.assertEqual(plan["world_id"], "SC-L")
        self.assertFalse(plan["needs_reattach"])
        with self.assertRaises(ContractViolation):
            host.check_settleable("SC-NOPE")
        host.holdings["SC-S"]["max_time_s"] += 999.0
        with self.assertRaises(ContractViolation):
            host.check_settleable("SC-S")
        self.assertEqual((self.root / "ledger.jsonl").read_bytes(), ledger_before)
        self.assertEqual({w: r.lifecycle for w, r in host.worlds.items()}, life_before)
        hold_after = copy.deepcopy(host.holdings)
        hold_after["SC-S"]["max_time_s"] -= 999.0
        self.assertEqual(hold_after, hold_before)

    def test_fuse_rejects_unsettleable_before_mutation(self):
        host, _ = self.main_host()
        chans = ChannelRegistry()
        run_sched_task(self.root, host, FI.S2, LaneCtx("local", HCoordinator(), chans))
        host.holdings["SC-S"]["max_invocations"] += 50.0
        fused_rec = world_record(
            self.root / "state",
            "SC-FUSED",
            FUSED_CAPS,
            [("sched-list", "v2"), ("sched-slot", "v2")],
        )
        n_before = len(host.ledger_entries())
        with self.assertRaises(ContractViolation):
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
        self.assertEqual(len(host.ledger_entries()), n_before)

    def test_fission_rejects_unsettleable_before_mutation(self):
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
            host, chans, "SC-L", "SC-S", "SC-FUSED", fused_rec, "host", "setup fusion"
        )
        host.holdings["SC-FUSED"]["max_cost_usd"] += 2.0
        l2 = world_record(self.root / "state", "SC-L2", L_CAPS, L_REPS)
        s2 = world_record(self.root / "state", "SC-S2", S_CAPS, S_REPS)
        n_before = len(host.ledger_entries())
        with self.assertRaises(ContractViolation):
            fission_worlds(
                host,
                chans,
                "SC-FUSED",
                "SC-L2",
                "SC-S2",
                l2,
                s2,
                dict(PARTITION),
                "host",
                "must not",
            )
        self.assertNotIn("SC-L2", host.worlds)
        self.assertEqual(len(host.ledger_entries()), n_before)


def _central_ctx():
    from anima_substrate.host.routing import Coordinator

    return LaneCtx("central", Coordinator(), ChannelRegistry())


class TestCrashSettle(Base):
    """Kill at EVERY settle boundary (CLI), then recover (CLI)."""

    def test_settle_every_boundary(self):
        template = self.cli_run("settle-template")
        probe = self.fresh_copy(template, "growth-probe")
        before = len(ledger_lines(probe))
        proc = cli(
            "ops",
            "settle",
            "--state-dir",
            str(probe),
            "--worlds",
            "SC-L,SC-S",
            "--reason",
            "probe",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        growth = len(ledger_lines(probe)) - before
        self.assertEqual(growth, 7)  # reopen + 2 x (return+marker+life)
        for n in range(1, growth + 2):
            with self.subTest(boundary=n):
                root = self.fresh_copy(template, f"settle-n{n}")
                proc = cli(
                    "ops",
                    "settle",
                    "--state-dir",
                    str(root),
                    "--worlds",
                    "SC-L,SC-S",
                    "--reason",
                    "kill",
                    env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS=str(n)),
                )
                if n > growth:
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                else:
                    self.assertEqual(proc.returncode, CRASH_RC)
                # inspect stays readable after the kill (fail-closed read)
                state = inspect_json(root)
                self.assertIn("conservation", state)
                # recover converges: both dissolved, 0 stranded
                proc = cli(
                    "ops",
                    "recover",
                    "--state-dir",
                    str(root),
                    "--worlds",
                    "SC-L,SC-S",
                    "--reason",
                    "rec",
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                state = inspect_json(root)
                self.assertEqual(state["worlds"]["SC-L"]["lifecycle"], "dissolved")
                self.assertEqual(state["worlds"]["SC-S"]["lifecycle"], "dissolved")
                self.assertTrue(state["conservation"]["ok"])
                kinds = kinds_of(root)
                self.assertGreaterEqual(kinds.get("grant_settle", 0), 2)
                if n == 3:
                    # crashed between marker + lifecycle: the re-settle
                    # leaves a second (benign, set-semantic) marker
                    marks = [
                        e
                        for e in ledger_lines(root)
                        if e.get("kind") == "grant_settle"
                        and e["payload"].get("world_id") == "SC-L"
                    ]
                    self.assertEqual(len(marks), 2)
                print(
                    f"settle N={n}: rc={CRASH_RC if n <= growth else 0} "
                    f"-> recovered markers={kinds.get('grant_settle')}"
                )


class TestCrashFuse(Base):
    """Kill at EVERY fusion boundary (CLI), then recover (CLI)."""

    def test_fuse_every_boundary(self):
        template = self.cli_run("fuse-template")
        probe = self.fresh_copy(template, "growth-probe")
        before = len(ledger_lines(probe))
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(probe),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "probe",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        growth = len(ledger_lines(probe)) - before
        self.assertEqual(growth, 14)
        for n in range(1, growth + 2):
            with self.subTest(boundary=n):
                root = self.fresh_copy(template, f"fuse-n{n}")
                proc = cli(
                    "ops",
                    "fuse",
                    "--state-dir",
                    str(root),
                    "--a",
                    "SC-L",
                    "--b",
                    "SC-S",
                    "--fused",
                    "SC-FUSED",
                    "--reason",
                    "kill",
                    env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS=str(n)),
                )
                if n > growth:
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    crash_rc = 0
                else:
                    self.assertEqual(proc.returncode, CRASH_RC)
                    crash_rc = CRASH_RC
                proc = cli(
                    "ops", "recover", "--state-dir", str(root), "--reason", "rec"
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                state = inspect_json(root)
                if "SC-FUSED" not in state["worlds"]:
                    # kill before the first op append: no trace, so the
                    # op simply never happened -- re-run it cleanly.
                    self.assertEqual(n, 1)
                    proc = cli(
                        "ops",
                        "fuse",
                        "--state-dir",
                        str(root),
                        "--a",
                        "SC-L",
                        "--b",
                        "SC-S",
                        "--fused",
                        "SC-FUSED",
                        "--reason",
                        "re-run after pre-op kill",
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    state = inspect_json(root)
                self.assertEqual(state["worlds"]["SC-FUSED"]["lifecycle"], "active")
                self.assertEqual(state["worlds"]["SC-L"]["lifecycle"], "dissolved")
                self.assertEqual(state["worlds"]["SC-S"]["lifecycle"], "dissolved")
                self.assertEqual(
                    state["worlds"]["SC-FUSED"]["custodians"],
                    {
                        "sched.composite": "SC-FUSED",
                        "sched.requirements": "SC-FUSED",
                        "sched.slots": "SC-FUSED",
                    },
                )
                kinds = kinds_of(root)
                self.assertEqual(kinds.get("fusion", 0), 1)
                self.assertTrue(state["conservation"]["ok"])
                specs = {
                    s["world_id"]
                    for s in json.loads(
                        (root / "worlds.json").read_text(encoding="utf-8")
                    )
                }
                self.assertIn("SC-FUSED", specs)
                fused_art = root / "artifacts" / "fusion-SC-FUSED.json"
                note = root / "artifacts" / "recovery-fusion-SC-FUSED.json"
                self.assertTrue(fused_art.exists() or note.exists())
                # the recovered composite serves reuse (descriptors OK)
                proc = cli(
                    "ops",
                    "reuse",
                    "--state-dir",
                    str(root),
                    "--composite",
                    "SC-FUSED",
                    "--followup",
                    "S4",
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                print(f"fuse N={n}: crash_rc={crash_rc} recovered + reuse OK")


class TestCrashFission(Base):
    """Kill at EVERY fission boundary; partition refusal; recover."""

    def fission_template(self) -> Path:
        root = self.cli_run("fission-template")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "template fusion",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return root

    def test_fission_every_boundary(self):
        template = self.fission_template()
        probe = self.fresh_copy(template, "growth-probe")
        before = len(ledger_lines(probe))
        proc = cli(
            "ops",
            "fission",
            "--state-dir",
            str(probe),
            "--composite",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
            "--reason",
            "probe",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        growth = len(ledger_lines(probe)) - before
        self.assertEqual(growth, 14)
        for n in range(1, growth + 2):
            with self.subTest(boundary=n):
                root = self.fresh_copy(template, f"fission-n{n}")
                proc = cli(
                    "ops",
                    "fission",
                    "--state-dir",
                    str(root),
                    "--composite",
                    "SC-FUSED",
                    "--left",
                    "SC-L2",
                    "--right",
                    "SC-S2",
                    "--partition",
                    PARTITION_CLI,
                    "--reason",
                    "kill",
                    env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS=str(n)),
                )
                if n > growth:
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                else:
                    self.assertEqual(proc.returncode, CRASH_RC)
                # bare recover: refuses IFF a partial fission exists
                bare = cli(
                    "ops", "recover", "--state-dir", str(root), "--reason", "rec"
                )
                if bare.returncode != 0:
                    self.assertIn("need operator input", bare.stderr)
                    proc = cli(
                        "ops",
                        "recover",
                        "--state-dir",
                        str(root),
                        "--reason",
                        "rec",
                        "--fission",
                        "SC-FUSED",
                        "--left",
                        "SC-L2",
                        "--right",
                        "SC-S2",
                        "--partition",
                        PARTITION_CLI,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                state = inspect_json(root)
                if (
                    state["worlds"]["SC-FUSED"]["lifecycle"] == "active"
                    and kinds_of(root).get("fission", 0) == 0
                ):
                    # kill before the first op append: no trace, so the
                    # op simply never happened -- re-run it cleanly.
                    self.assertEqual(n, 1)
                    proc = cli(
                        "ops",
                        "fission",
                        "--state-dir",
                        str(root),
                        "--composite",
                        "SC-FUSED",
                        "--left",
                        "SC-L2",
                        "--right",
                        "SC-S2",
                        "--partition",
                        PARTITION_CLI,
                        "--reason",
                        "re-run after pre-op kill",
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    state = inspect_json(root)
                self.assertEqual(state["worlds"]["SC-FUSED"]["lifecycle"], "dissolved")
                self.assertEqual(state["worlds"]["SC-L2"]["lifecycle"], "active")
                self.assertEqual(state["worlds"]["SC-S2"]["lifecycle"], "active")
                self.assertEqual(
                    state["worlds"]["SC-L2"]["custodians"],
                    {"sched.composite": "SC-L2", "sched.requirements": "SC-L2"},
                )
                self.assertEqual(
                    state["worlds"]["SC-S2"]["custodians"], {"sched.slots": "SC-S2"}
                )
                kinds = kinds_of(root)
                self.assertEqual(kinds.get("fission", 0), 1)
                self.assertTrue(state["conservation"]["ok"])
                print(f"fission N={n}: bare_rc={bare.returncode} -> converged")

    def test_fission_wrong_partition_refused(self):
        template = self.fission_template()
        root = self.fresh_copy(template, "fission-wrongpart")
        proc = cli(
            "ops",
            "fission",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="9"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        bad = "sched.composite=SC-S2,sched.requirements=SC-L2,sched.slots=SC-L2"
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--reason",
            "rec",
            "--fission",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            bad,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("contradicts", proc.stderr)
        # ... and the correct partition still completes afterwards
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--reason",
            "rec",
            "--fission",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


class TestPreSpecCrash(Base):
    """Kill between ledger-complete and worlds.json write."""

    def test_fuse_pre_spec_withheld_then_repaired(self):
        root = self.cli_run("prespec-fuse")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AT="api:fuse:pre-spec"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        kinds = kinds_of(root)
        self.assertEqual(kinds.get("fusion", 0), 1)  # ledger complete
        specs = {
            s["world_id"]
            for s in json.loads((root / "worlds.json").read_text(encoding="utf-8"))
        }
        self.assertNotIn("SC-FUSED", specs)  # ... but specs stale
        # the composite reopens WITHHELD: its invokes deny (fail-closed)
        host, _ = api.open_run(root)
        with self.assertRaises(ContractViolation):
            host.invoke(
                "SC-FUSED",
                "SC-FUSED",
                "sched.reuse",
                "1.0",
                host.store_args("SC-FUSED", "pre", {}),
                lambda: "never",
            )
        # recover repairs the specs; reuse serves again
        rep = api.recover_op(root)
        self.assertEqual(rep["specs_repaired"], ["SC-FUSED"])
        self.assertEqual(rep["fusions_completed"], [])
        proc = cli(
            "ops",
            "reuse",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--followup",
            "S4",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        note = root / "artifacts" / "recovery-fusion-SC-FUSED.json"
        self.assertTrue(note.exists())

    def test_fission_pre_spec_repaired(self):
        root = self.cli_run("prespec-fission")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "setup",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "fission",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AT="api:fission:pre-spec"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        self.assertEqual(kinds_of(root).get("fission", 0), 1)
        rep = api.recover_op(root)
        self.assertEqual(sorted(rep["specs_repaired"]), ["SC-L2", "SC-S2"])
        self.assertEqual(rep["fissions_completed"], [])
        state = inspect_json(root)
        self.assertEqual(state["worlds"]["SC-L2"]["lifecycle"], "active")
        self.assertTrue(state["conservation"]["ok"])


class TestRepeatedKills(Base):
    """Kill during recovery converges on re-run (all ops)."""

    def test_settle_kill_during_recovery(self):
        root = self.cli_run("rep-settle")
        proc = cli(
            "ops",
            "settle",
            "--state-dir",
            str(root),
            "--worlds",
            "SC-L,SC-S",
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="4"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--worlds",
            "SC-L,SC-S",
            "--reason",
            "rec",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="3"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--worlds",
            "SC-L,SC-S",
            "--reason",
            "rec",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertTrue(state["conservation"]["ok"])
        self.assertEqual(state["worlds"]["SC-L"]["lifecycle"], "dissolved")
        # idempotent: re-recover is a clean no-op-ish report
        rep = api.recover_op(root, ["SC-L", "SC-S"])
        self.assertEqual(sorted(rep["settle_already_terminal"]), ["SC-L", "SC-S"])
        self.assertIsNone(rep["settle"])

    def test_fuse_kill_during_recovery(self):
        root = self.cli_run("rep-fuse")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="6"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--reason",
            "rec",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="5"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli("ops", "recover", "--state-dir", str(root), "--reason", "rec")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertEqual(state["worlds"]["SC-FUSED"]["lifecycle"], "active")
        self.assertEqual(kinds_of(root).get("fusion", 0), 1)
        self.assertTrue(state["conservation"]["ok"])

    def test_fission_kill_during_recovery(self):
        root = self.cli_run("rep-fission")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "setup",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "fission",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="8"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        rec = [
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--reason",
            "rec",
            "--fission",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
        ]
        proc = cli(*rec, env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="4"))
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli(*rec)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertEqual(state["worlds"]["SC-L2"]["lifecycle"], "active")
        self.assertEqual(kinds_of(root).get("fission", 0), 1)
        self.assertTrue(state["conservation"]["ok"])

    def test_kill_during_spec_repair(self):
        root = self.cli_run("rep-spec")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="6"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--reason",
            "rec",
            env=child_env(SUBSTRATE_CRASH_AT="recover:pre-spec"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli("ops", "recover", "--state-dir", str(root), "--reason", "rec")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertEqual(state["worlds"]["SC-FUSED"]["lifecycle"], "active")
        self.assertTrue(state["conservation"]["ok"])

    def test_full_flow_with_kills_at_every_op(self):
        # init -> run -> fuse(kill) -> recover -> reuse -> fission(kill)
        # -> recover -> split-pair -> settle(kill) -> recover: the whole
        # demo spine with a kill inside every mutating op.
        root = self.cli_run("flow")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="6"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli("ops", "recover", "--state-dir", str(root), "--reason", "rec")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "reuse",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--followup",
            "S4",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "fission",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="9"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--reason",
            "rec",
            "--fission",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "split-pair",
            "--state-dir",
            str(root),
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--followup",
            "S6",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "settle",
            "--state-dir",
            str(root),
            "--worlds",
            "SC-L2,SC-S2",
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="4"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            "--worlds",
            "SC-L2,SC-S2",
            "--reason",
            "rec",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertTrue(state["conservation"]["ok"])
        self.assertEqual(
            sorted(state["conservation"]["settled_terminals"]),
            ["SC-FUSED", "SC-L", "SC-L2", "SC-S", "SC-S2"],
        )


class TestRealKill(Base):
    """Real SIGKILL (not the hook) at staggered delays, then recover."""

    def kill_run(self, root: Path, op_args: list[str], delay: float) -> str:
        child = subprocess.Popen(
            [sys.executable, "-m", "anima_substrate", *op_args],
            cwd=str(HERE),
            env=child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(delay)
        try:
            child.kill()
            killed = True
        except ProcessLookupError:
            killed = False
        child.communicate(timeout=60)
        if child.returncode == 0:
            return "completed-before-kill"
        self.assertTrue(killed)
        self.assertLess(child.returncode, 0)
        return "killed"

    def test_sigkill_settle(self):
        template = self.cli_run("kill-settle-template")
        for i, delay in enumerate((0.05, 0.2, 0.5)):
            with self.subTest(delay=delay):
                root = self.fresh_copy(template, f"kill-settle-{i}")
                landing = self.kill_run(
                    root,
                    [
                        "ops",
                        "settle",
                        "--state-dir",
                        str(root),
                        "--worlds",
                        "SC-L,SC-S",
                        "--reason",
                        "kill",
                    ],
                    delay,
                )
                proc = cli(
                    "ops",
                    "recover",
                    "--state-dir",
                    str(root),
                    "--worlds",
                    "SC-L,SC-S",
                    "--reason",
                    "rec",
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                state = inspect_json(root)
                self.assertTrue(state["conservation"]["ok"])
                self.assertEqual(state["worlds"]["SC-L"]["lifecycle"], "dissolved")
                print(f"sigkill settle delay={delay}: {landing} -> converged")

    def test_sigkill_fuse(self):
        template = self.cli_run("kill-fuse-template")
        for i, delay in enumerate((0.05, 0.2, 0.5)):
            with self.subTest(delay=delay):
                root = self.fresh_copy(template, f"kill-fuse-{i}")
                landing = self.kill_run(
                    root,
                    [
                        "ops",
                        "fuse",
                        "--state-dir",
                        str(root),
                        "--a",
                        "SC-L",
                        "--b",
                        "SC-S",
                        "--fused",
                        "SC-FUSED",
                        "--reason",
                        "kill",
                    ],
                    delay,
                )
                proc = cli(
                    "ops", "recover", "--state-dir", str(root), "--reason", "rec"
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                state = inspect_json(root)
                if "SC-FUSED" not in state["worlds"]:
                    landing += "+no-trace-rerun"
                    proc = cli(
                        "ops",
                        "fuse",
                        "--state-dir",
                        str(root),
                        "--a",
                        "SC-L",
                        "--b",
                        "SC-S",
                        "--fused",
                        "SC-FUSED",
                        "--reason",
                        "re-run after pre-op kill",
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    state = inspect_json(root)
                self.assertEqual(state["worlds"]["SC-FUSED"]["lifecycle"], "active")
                self.assertEqual(kinds_of(root).get("fusion", 0), 1)
                self.assertTrue(state["conservation"]["ok"])
                print(f"sigkill fuse delay={delay}: {landing} -> converged")

    def test_sigkill_fission(self):
        template = self.cli_run("kill-fission-template")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(template),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "template fusion",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for i, delay in enumerate((0.05, 0.2, 0.5)):
            with self.subTest(delay=delay):
                root = self.fresh_copy(template, f"kill-fission-{i}")
                landing = self.kill_run(
                    root,
                    [
                        "ops",
                        "fission",
                        "--state-dir",
                        str(root),
                        "--composite",
                        "SC-FUSED",
                        "--left",
                        "SC-L2",
                        "--right",
                        "SC-S2",
                        "--partition",
                        PARTITION_CLI,
                        "--reason",
                        "kill",
                    ],
                    delay,
                )
                bare = cli(
                    "ops", "recover", "--state-dir", str(root), "--reason", "rec"
                )
                if bare.returncode != 0:
                    proc = cli(
                        "ops",
                        "recover",
                        "--state-dir",
                        str(root),
                        "--reason",
                        "rec",
                        "--fission",
                        "SC-FUSED",
                        "--left",
                        "SC-L2",
                        "--right",
                        "SC-S2",
                        "--partition",
                        PARTITION_CLI,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                state = inspect_json(root)
                if (
                    state["worlds"]["SC-FUSED"]["lifecycle"] == "active"
                    and kinds_of(root).get("fission", 0) == 0
                ):
                    landing += "+no-trace-rerun"
                    proc = cli(
                        "ops",
                        "fission",
                        "--state-dir",
                        str(root),
                        "--composite",
                        "SC-FUSED",
                        "--left",
                        "SC-L2",
                        "--right",
                        "SC-S2",
                        "--partition",
                        PARTITION_CLI,
                        "--reason",
                        "re-run after pre-op kill",
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    state = inspect_json(root)
                self.assertEqual(state["worlds"]["SC-FUSED"]["lifecycle"], "dissolved")
                self.assertEqual(kinds_of(root).get("fission", 0), 1)
                self.assertTrue(state["conservation"]["ok"])
                print(f"sigkill fission delay={delay}: {landing} -> converged")


class TestDetection(Base):
    """Forensics: quarantine/conservation/torn/input refusal paths."""

    def test_partial_quarantine_detected_with_steps(self):
        root = self.root / "qdetect"
        api.init_run(root)
        api.run_tasks(root, ["S1"])
        host, _ = api.open_run(root)
        host.suspend(
            "SC-L",
            "host",
            "drill",
            pending_effects=[
                {"commitment": "sched.composite", "to": "SC-S"},
                {"commitment": "sched.requirements", "to": "SC-S"},
            ],
        )
        host.transfer_custody(
            "sched.composite",
            "SC-L",
            "SC-S",
            actor="host",
            reason="quarantine transfer: drill",
            continuity="commitment-handoff",
        )
        rep = api.recover_op(root)
        self.assertEqual(len(rep["partial_quarantines"]), 1)
        self.assertEqual(rep["partial_quarantines"][0]["world"], "SC-L")
        self.assertIn("SC-L", rep["quarantine_operator_steps"][0])
        # Port delta: s005 said "OPERATOR REPAIR (LIMITS-3; automation
        # out of scope)"; the maintained tree closes R11, so the
        # steps name the SUPPORTED repair ops (audited s006 text).
        # Intent kept: the steps name the repair path explicitly.
        self.assertIn("SUPPORTED REPAIR", rep["quarantine_operator_steps"][0])
        self.assertIn("quarantine-complete", rep["quarantine_operator_steps"][0])
        self.assertIn("quarantine-rollback", rep["quarantine_operator_steps"][0])
        # involved world blocked; uninvolved worlds still settle
        with self.assertRaises(RuntimeError):
            api.recover_op(root, ["SC-L"])
        rep2 = api.recover_op(root, ["SC-S"])
        self.assertIsNotNone(rep2["settle"])

    def test_conservation_violation_refuses_recover(self):
        root = self.root / "violated"
        api.init_run(root)
        api.run_tasks(root, ["S1"])
        host, _ = api.open_run(root)
        host.append(
            "lifecycle",
            {
                "world_id": "SC-GHOST",
                "from": "active",
                "to": "dissolved",
                "reason": "probe",
            },
            actor="host",
        )
        with self.assertRaises(ContractViolation) as ctx:
            api.recover_op(root)
        self.assertIn("fails conservation", str(ctx.exception))

    def test_torn_ledger_refuses_recover(self):
        root = self.root / "torn"
        api.init_run(root)
        api.run_tasks(root, ["S1"])
        with open(root / "ledger.jsonl", "a", encoding="utf-8") as fh:
            fh.write('{"seq": 9999, "torn": "no-close-brace"\n')
        with self.assertRaises(RuntimeError) as ctx:
            api.recover_op(root)
        self.assertIn("disk-loss", str(ctx.exception))
        proc = cli("inspect", "--state-dir", str(root))
        self.assertNotEqual(proc.returncode, 0)

    def test_fission_args_without_partial_refused(self):
        root = self.cli_run("nopartial")
        with self.assertRaises(RuntimeError) as ctx:
            api.recover_op(
                root,
                fission="SC-FUSED",
                left="SC-L2",
                right="SC-S2",
                partition=dict(PARTITION),
            )
        self.assertIn("nothing to complete", str(ctx.exception))

    def test_bare_recover_settles_nothing_by_default(self):
        root = self.cli_run("safe-default")
        rep = api.recover_op(root)
        self.assertTrue(rep["settle_skipped_no_worlds"])
        self.assertIsNone(rep["settle"])
        host, _ = api.open_run(root)
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        self.assertEqual(host.worlds["SC-S"].lifecycle, "active")

    def test_partial_fission_blocks_settle_until_completed(self):
        root = self.cli_run("blocked")
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "setup",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "fission",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="8"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        with self.assertRaises(RuntimeError):
            api.recover_op(root, ["SC-FUSED"])
        # one call completes the fission AND settles the children
        rep = api.recover_op(
            root,
            ["SC-L2", "SC-S2"],
            fission="SC-FUSED",
            left="SC-L2",
            right="SC-S2",
            partition=dict(PARTITION),
        )
        self.assertEqual(len(rep["fissions_completed"]), 1)
        self.assertIsNotNone(rep["settle"])
        host, _ = api.open_run(root)
        self.assertTrue(host.verify_conservation()["ok"])


def _shipped_py() -> dict[str, str]:
    """{package-relative posix path: dotted module} for shipped .py."""
    out = {}
    for rel in provcheck.shipped_files():
        if not rel.endswith(".py"):
            continue
        mod = rel[len("src/") : -len(".py")].replace("/", ".")
        if mod.endswith(".__init__"):
            mod = mod[: -len(".__init__")]
        out[rel] = mod
    return out


class TestAtomicConstruction(Base):
    """R3 (F2 fix): every side-file write is temp + os.replace.

    Static (AST: no direct .write_text / open-w in shipped code) +
    runtime (a recorder proves the init/run/fuse/fission/reuse/
    split-pair/settle/checkpoint flows all land via the one helper,
    and Path.write_text is never touched) + helper semantics.

    Port delta: SHIPPED is every shipped .py (new modules are
    auto-covered — stronger than the frozen file list); the exact
    shipped SET is pinned by test_14's PROVENANCE check instead.
    WRITER_MODULES is every shipped module referencing the helper
    (auto-covered), with the ported frozen core asserted present.
    """

    # Port-mapped frozen core (upstream: minihost, api, routing,
    # resume, fusion, pipeline, recover, sst_leg, successor_demo,
    # calibrate, make_snapshot_manifest) + procedure/j1_demo/sst
    # package (covered by sibling suites upstream; pinned here too).
    CORE_WRITERS = (
        "anima_substrate.host.minihost",
        "anima_substrate.host.api",
        "anima_substrate.host.routing",
        "anima_substrate.host.resume",
        "anima_substrate.host.fusion",
        "anima_substrate.host.pipeline",
        "anima_substrate.host.recover",
        "anima_substrate.host.calibrate",
        "anima_substrate.host.procedure",
        "anima_substrate.demos.successor_demo",
        "anima_substrate.demos.j1_demo",
        "anima_substrate.participants.sst.staged",
        "anima_substrate.participants.sst.manifest",
        "anima_substrate.participants.sst",
    )

    def _writer_modules(self) -> dict[str, str]:
        """{dotted module: relpath} for shipped modules using the helper."""
        out = {}
        for rel, mod in _shipped_py().items():
            tree = ast.parse((TOP / rel).read_text(encoding="utf-8"))
            if any(
                isinstance(n, ast.Name) and n.id == "atomic_write_text"
                for n in ast.walk(tree)
            ):
                out[mod] = rel
        return out

    def test_helper_is_temp_plus_replace(self):
        from anima_substrate.host import minihost

        src = inspect.getsource(minihost.atomic_write_text)
        self.assertIn("os.replace(", src)
        self.assertIn(".tmp-", src)
        self.assertNotIn(".write_text(", src)
        # one implementation shared by every writer module
        writers = self._writer_modules()
        for core in self.CORE_WRITERS:
            self.assertIn(core, writers, core)
        for name, rel in sorted(writers.items()):
            mod = importlib.import_module(name)
            self.assertTrue(hasattr(mod, "atomic_write_text"), f"{rel}: no helper attr")
            self.assertIs(mod.atomic_write_text, minihost.atomic_write_text, rel)

    def test_no_direct_whole_file_writes_in_shipped_code(self):
        shipped = _shipped_py()
        self.assertGreaterEqual(len(shipped), len(self.CORE_WRITERS))
        for fname in sorted(shipped):
            tree = ast.parse((TOP / fname).read_text(encoding="utf-8"))
            uses_helper = False
            stack: list[str] = []

            def visit(node):
                nonlocal uses_helper
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    stack.append(node.name)
                    for child in ast.iter_child_nodes(node):
                        visit(child)
                    stack.pop()
                    return
                if isinstance(node, ast.Name) and node.id == "atomic_write_text":
                    uses_helper = True
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and func.attr == "write_text":
                        self.fail(
                            f"{fname}:{node.lineno}: direct "
                            f".write_text call (must route via "
                            f"atomic_write_text)"
                        )
                    if isinstance(func, ast.Name) and func.id == "open":
                        mode = ""
                        if len(node.args) >= 2 and isinstance(
                            node.args[1], ast.Constant
                        ):
                            mode = node.args[1].value or ""
                        for kw in node.keywords:
                            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                                mode = kw.value.value or ""
                        if "w" in mode:
                            scope = (fname, stack[-1] if stack else "")
                            self.assertEqual(
                                scope,
                                (
                                    "src/anima_substrate/host/minihost.py",
                                    "atomic_write_text",
                                ),
                                f"{fname}:{node.lineno}: raw "
                                f"open(..., 'w') outside the helper",
                            )
                        if "a" in mode:
                            scope = (fname, stack[-1] if stack else "")
                            self.assertIn(
                                scope,
                                [
                                    ("src/anima_substrate/host/minihost.py", "append"),
                                    (
                                        "src/anima_substrate/host/routing.py",
                                        "record_routing",
                                    ),
                                ],
                                f"{fname}:{node.lineno}: append-mode "
                                f"open outside ledger/ROUTING-LOG",
                            )
                for child in ast.iter_child_nodes(node):
                    visit(child)

            visit(tree)
            if shipped[fname] in self.CORE_WRITERS:
                self.assertTrue(
                    uses_helper,
                    f"{fname}: writer module never references atomic_write_text",
                )

    def test_flows_route_all_side_writes_through_helper(self):
        from anima_substrate.host import minihost
        from anima_substrate.host import recover as RC

        seen: list[str] = []
        real = minihost.atomic_write_text

        def recorder(path, text, encoding="utf-8"):
            seen.append(str(path))
            return real(path, text, encoding=encoding)

        def boom(self, *a, **k):
            raise AssertionError("direct Path.write_text touched during op flows")

        mods = [
            sys.modules[n]
            for n in (
                "anima_substrate.host.minihost",
                "anima_substrate.host.api",
                "anima_substrate.host.routing",
                "anima_substrate.host.resume",
                "anima_substrate.host.fusion",
                "anima_substrate.host.pipeline",
                "anima_substrate.host.recover",
            )
        ]
        saved = [m.atomic_write_text for m in mods]
        real_wt = Path.write_text
        try:
            for m in mods:
                m.atomic_write_text = recorder
            Path.write_text = boom
            root = self.root / "routed"
            api.init_run(root)
            api.run_tasks(root, ["S1", "S2"])
            api.fuse_op(root, "SC-L", "SC-S", "SC-FUSED", reason="t")
            api.reuse_op(root, "SC-FUSED", dict(FI.S4_FOLLOWUP))
            api.fission_op(
                root, "SC-FUSED", "SC-L2", "SC-S2", dict(PARTITION), reason="t"
            )
            api.split_pair_op(root, dict(FI.S6_FISSION_FOLLOWUP), "SC-L2", "SC-S2")
            # checkpoint write + read-back, then targeted settle
            host, _ = api.open_run(root)
            host.suspend("SC-L2", "host", reason="t", pending_effects=[])
            host.reattach("SC-L2", "host", reason="t")
            api.settle_op(root, ["SC-L2", "SC-S2"], reason="t")
            # spec-repair write + recovery-note write, directly
            host, _ = api.open_run(root)
            idx = RC.ledger_index(host)
            specs = [s for s in api._read_specs(root) if s["world_id"] != "SC-FUSED"]
            repaired = RC.repair_specs(root, host, idx, specs)
            self.assertEqual(repaired, ["SC-FUSED"])
            art = root / "artifacts" / "fusion-SC-FUSED.json"
            art.unlink()
            note = api._recovery_note(root, "fusion", "SC-FUSED", 1, {"k": "v"}, True)
            self.assertIsNotNone(note)
            # legacy MiniWorld handle routes through the helper too
            ref = minihost.MiniWorld(root / "state" / "SC-L").write_formulation(
                "g", "d", [], {"b": 1}
            )
            self.assertTrue(Path(ref).exists())
        finally:
            for m, fn in zip(mods, saved):
                m.atomic_write_text = fn
            Path.write_text = real_wt
        names = [Path(p).name for p in seen]
        for want in (
            "worlds.json",
            "CONFIG.json",
            "checkpoint.json",
            "fusion-SC-FUSED.json",
            "fission-SC-FUSED.json",
            "recovery-fusion-SC-FUSED.json",
        ):
            self.assertIn(want, names, want)
        self.assertTrue(any(n.startswith("solution-") for n in names))
        self.assertTrue(any(n.startswith("verdict-") for n in names))
        self.assertTrue(any(n == "verdict.json" for n in names))
        self.assertGreaterEqual(names.count("worlds.json"), 4)
        print(
            f"routed side writes: {len(seen)} via helper, "
            f"0 direct (Path.write_text never touched)"
        )

    def test_atomic_write_old_or_new_semantics(self):
        from anima_substrate.host import minihost

        target = self.root / "sub" / "f.json"
        out = minihost.atomic_write_text(target, '{"v": 1}')
        self.assertEqual(out, str(target))
        self.assertEqual(target.read_text(encoding="utf-8"), '{"v": 1}')
        self.assertEqual(list(target.parent.glob("*.tmp-*")), [])
        minihost.atomic_write_text(target, '{"v": 2}')
        self.assertEqual(target.read_text(encoding="utf-8"), '{"v": 2}')
        self.assertEqual(list(target.parent.glob("*.tmp-*")), [])
        # a stale orphan from a dead pid never disturbs the target
        (target.parent / "f.json.tmp-99999999").write_text("stale", encoding="utf-8")
        minihost.atomic_write_text(target, '{"v": 3}')
        self.assertEqual(target.read_text(encoding="utf-8"), '{"v": 3}')


class TestSpecWindowKillLoop(Base):
    """R3 (F2 proof): 50 real SIGKILLs across the fission op tail.

    Fission ends with TWO worlds.json spec writes + the artifact
    write (the lane's F2 window, 0.2s on their box). Delays span
    0.05..0.90s so kills land pre-op, mid-ledger, inside the spec
    window, and post-op. Every iteration asserts ZERO torn side
    files (worlds.json + every *.json parses; ledger stays
    entry-granular) and every landing converges via `ops recover`
    (bare, then with the partition when the classified
    need-operator-input refusal fires). A final idempotent bare
    re-recover repairs specs for recovery-born children (pre-existing
    R1 semantic: complete_fission births hit the ledger; their specs
    land on the next recover — verified byte-identical on
    successor-003), after which all five specs are present."""

    KILLS = 50

    def kill_run(self, root: Path, op_args: list[str], delay: float) -> str:
        child = subprocess.Popen(
            [sys.executable, "-m", "anima_substrate", *op_args],
            cwd=str(HERE),
            env=child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(delay)
        try:
            child.kill()
            killed = True
        except ProcessLookupError:
            killed = False
        child.communicate(timeout=60)
        if child.returncode == 0:
            return "completed-before-kill"
        self.assertTrue(killed)
        self.assertLess(child.returncode, 0)
        return "killed"

    def assert_side_files_intact(self, root: Path) -> list[dict]:
        specs = json.loads((root / "worlds.json").read_text(encoding="utf-8"))
        self.assertIsInstance(specs, list)
        self.assertTrue(all("world_id" in s for s in specs))
        for p in sorted(root.rglob("*.json")):
            if ".tmp-" in p.name:
                continue  # benign replace orphan: never read
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                self.fail(f"TORN side file {p.relative_to(root)}: {exc}")
        with open(root / "ledger.jsonl", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    json.loads(line)  # entry-granular prefix
        return specs

    def test_sigkill_spec_window_50(self):
        template = self.cli_run("specwin-template", tasks=("S1",))
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(template),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "template fusion",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        landings: dict[str, int] = {}
        orphans = 0
        for i in range(self.KILLS):
            delay = 0.05 + i * (0.85 / (self.KILLS - 1))
            with self.subTest(i=i, delay=round(delay, 3)):
                root = self.fresh_copy(template, f"specwin-{i}")
                landing = self.kill_run(
                    root,
                    [
                        "ops",
                        "fission",
                        "--state-dir",
                        str(root),
                        "--composite",
                        "SC-FUSED",
                        "--left",
                        "SC-L2",
                        "--right",
                        "SC-S2",
                        "--partition",
                        PARTITION_CLI,
                        "--reason",
                        "kill",
                    ],
                    delay,
                )
                self.assert_side_files_intact(root)
                orphans += len(list(root.rglob("*.tmp-*")))
                bare = cli(
                    "ops", "recover", "--state-dir", str(root), "--reason", "rec"
                )
                if bare.returncode != 0:
                    # the ONLY acceptable refusal: classified
                    # need-operator-input (partial fission); a
                    # disk-loss/torn refusal here fails the test
                    self.assertIn("need operator input", bare.stdout + bare.stderr)
                    landing += "+classified-refusal"
                    proc = cli(
                        "ops",
                        "recover",
                        "--state-dir",
                        str(root),
                        "--reason",
                        "rec",
                        "--fission",
                        "SC-FUSED",
                        "--left",
                        "SC-L2",
                        "--right",
                        "SC-S2",
                        "--partition",
                        PARTITION_CLI,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                state = inspect_json(root)
                if (
                    state["worlds"]["SC-FUSED"]["lifecycle"] == "active"
                    and kinds_of(root).get("fission", 0) == 0
                ):
                    landing += "+no-trace-rerun"
                    proc = cli(
                        "ops",
                        "fission",
                        "--state-dir",
                        str(root),
                        "--composite",
                        "SC-FUSED",
                        "--left",
                        "SC-L2",
                        "--right",
                        "SC-S2",
                        "--partition",
                        PARTITION_CLI,
                        "--reason",
                        "re-run after pre-op kill",
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    state = inspect_json(root)
                self.assertEqual(state["worlds"]["SC-FUSED"]["lifecycle"], "dissolved")
                self.assertEqual(kinds_of(root).get("fission", 0), 1)
                self.assertTrue(state["conservation"]["ok"])
                # idempotent re-run converges specs for recovery-born
                # children (pre-existing R1 semantic, s003-identical)
                again = cli(
                    "ops", "recover", "--state-dir", str(root), "--reason", "rec2"
                )
                self.assertEqual(again.returncode, 0, again.stderr)
                final = {
                    s["world_id"]
                    for s in json.loads(
                        (root / "worlds.json").read_text(encoding="utf-8")
                    )
                }
                self.assertEqual(final, {"SC-L", "SC-S", "SC-FUSED", "SC-L2", "SC-S2"})
                landings[landing] = landings.get(landing, 0) + 1
        print(
            f"spec-window kill loop: {self.KILLS} SIGKILLs, "
            f"0 torn side files, landings={landings}, "
            f"benign tmp orphans={orphans}"
        )


class TestWriteInterior(Base):
    """R3: kills INSIDE writes, not just between them.

    SUBSTRATE_CRASH_MID_APPEND=N writes only half of the Nth ledger
    line, flushes, and exits(42): the landing is a torn tail over an
    intact prefix, and readers MUST refuse it loudly as disk-loss.
    SUBSTRATE_CRASH_MID_SIDE_WRITE=<basename> writes only half of
    the temp file and exits(42) BEFORE the replace: the target keeps
    its OLD bytes (or stays absent when new), and recovery MUST
    converge. Torn-file fixtures pin the reader side for worlds.json
    (0-byte = the F2 landing; truncated mid-JSON) and checkpoint.json
    (classified deny + ContractViolation).
    """

    def test_mid_append_crash_torn_tail_refused_loudly(self):
        root = self.cli_run("midappend", tasks=("S1",))
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "setup",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "fission",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_MID_APPEND="8"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        body = [
            line
            for line in (root / "ledger.jsonl").read_text(encoding="utf-8").split("\n")
            if line.strip()
        ]
        for line in body[:-1]:
            json.loads(line)  # prefix intact
        with self.assertRaises(json.JSONDecodeError):
            json.loads(body[-1])  # tail genuinely torn (self-check)
        proc = cli("ops", "recover", "--state-dir", str(root), "--reason", "rec")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("disk-loss", proc.stderr)
        with self.assertRaises(RuntimeError) as ctx:
            api.recover_op(root)
        self.assertIn("disk-loss", str(ctx.exception))
        proc = cli("inspect", "--state-dir", str(root))
        self.assertNotEqual(proc.returncode, 0)

    def test_torn_worlds_json_fixtures_refuse_loudly(self):
        root = self.cli_run("tornspec", tasks=("S1",))
        good = (root / "worlds.json").read_bytes()
        for name, bad in (("zero-byte", b""), ("truncated", good[: len(good) // 2])):
            with self.subTest(fixture=name):
                (root / "worlds.json").write_bytes(bad)
                with self.assertRaises(ValueError):
                    json.loads(bad.decode())  # genuinely torn
                with self.assertRaises(RuntimeError) as ctx:
                    api.recover_op(root)
                self.assertIn("disk-loss", str(ctx.exception))
                proc = cli(
                    "ops", "recover", "--state-dir", str(root), "--reason", "rec"
                )
                self.assertEqual(proc.returncode, 1)
                self.assertIn("disk-loss", proc.stderr)
        (root / "worlds.json").write_bytes(good)

    def test_mid_side_write_worlds_json_keeps_old_bytes(self):
        root = self.cli_run("midside", tasks=("S1",))
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "setup",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        before = (root / "worlds.json").read_bytes()
        proc = cli(
            "ops",
            "fission",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--left",
            "SC-L2",
            "--right",
            "SC-S2",
            "--partition",
            PARTITION_CLI,
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_MID_SIDE_WRITE="worlds.json"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        # the F2 kill point: target keeps pre-op bytes, never torn
        self.assertEqual((root / "worlds.json").read_bytes(), before)
        json.loads(before.decode())
        orphans = list(root.glob("worlds.json.tmp-*"))
        self.assertEqual(len(orphans), 1)
        self.assertLess(orphans[0].stat().st_size, len(before))
        proc = cli("ops", "recover", "--state-dir", str(root), "--reason", "rec")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertEqual(state["worlds"]["SC-FUSED"]["lifecycle"], "dissolved")
        self.assertEqual(kinds_of(root).get("fission", 0), 1)
        self.assertTrue(state["conservation"]["ok"])
        final = {
            s["world_id"]
            for s in json.loads((root / "worlds.json").read_text(encoding="utf-8"))
        }
        self.assertEqual(final, {"SC-L", "SC-S", "SC-FUSED", "SC-L2", "SC-S2"})

    def test_mid_side_write_artifact_converges_via_recovery_note(self):
        root = self.cli_run("midart", tasks=("S1",))
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "kill",
            env=child_env(SUBSTRATE_CRASH_MID_SIDE_WRITE=("fusion-SC-FUSED.json")),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        self.assertFalse((root / "artifacts" / "fusion-SC-FUSED.json").exists())
        proc = cli("ops", "recover", "--state-dir", str(root), "--reason", "rec")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((root / "artifacts" / "recovery-fusion-SC-FUSED.json").exists())
        proc = cli(
            "ops",
            "reuse",
            "--state-dir",
            str(root),
            "--composite",
            "SC-FUSED",
            "--followup",
            "S4",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertTrue(state["conservation"]["ok"])

    def test_mid_side_write_config_keeps_old_and_converges(self):
        root = self.cli_run("midcfg", tasks=("S1",))
        before = (root / "CONFIG.json").read_bytes()
        proc = cli(
            "run",
            "--state-dir",
            str(root),
            "--tasks",
            "S2",
            env=child_env(SUBSTRATE_CRASH_MID_SIDE_WRITE="CONFIG.json"),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        self.assertEqual((root / "CONFIG.json").read_bytes(), before)
        # CONFIG is informational (the API re-reads only worlds.json
        # + ledger): the next op is unaffected by the stale bytes
        proc = cli(
            "ops",
            "fuse",
            "--state-dir",
            str(root),
            "--a",
            "SC-L",
            "--b",
            "SC-S",
            "--fused",
            "SC-FUSED",
            "--reason",
            "after",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertTrue(state["conservation"]["ok"])

    def test_mid_side_write_checkpoint_leaves_no_trace(self):
        root = self.cli_run("midckpt", tasks=("S1",))
        proc = cli(
            "ops",
            "quarantine",
            "--state-dir",
            str(root),
            "--world",
            "SC-S",
            "--standby",
            "SC-Q",
            "--reason",
            "kill",
            "--create-standby",
            env=child_env(SUBSTRATE_CRASH_MID_SIDE_WRITE=("checkpoint.json")),
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        self.assertFalse((root / "state" / "SC-S" / "checkpoint.json").exists())
        state = inspect_json(root)
        self.assertEqual(state["worlds"]["SC-S"]["lifecycle"], "active")
        proc = cli(
            "ops",
            "quarantine",
            "--state-dir",
            str(root),
            "--world",
            "SC-S",
            "--standby",
            "SC-Q",
            "--reason",
            "clean",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = inspect_json(root)
        self.assertEqual(state["worlds"]["SC-S"]["lifecycle"], "suspended")

    def test_torn_checkpoint_refuses_classified(self):
        root = self.root / "tornckpt"
        api.init_run(root)
        api.run_tasks(root, ["S1"])
        host, _ = api.open_run(root)
        host.suspend("SC-S", "host", reason="t")
        ckpt = Path(host.worlds["SC-S"].instance_state_dir) / "checkpoint.json"
        raw = ckpt.read_bytes()
        ckpt.write_bytes(raw[: len(raw) // 2])
        with self.assertRaises(ValueError):
            json.loads(raw[: len(raw) // 2].decode())  # genuinely torn
        with self.assertRaises(ContractViolation) as ctx:
            host.reattach("SC-S", "host", "t")
        self.assertIn("unreadable", str(ctx.exception))
        self.assertIn("disk-loss", str(ctx.exception))
        fresh = host.ledger_entries()[-1]
        self.assertEqual(fresh["kind"], "deny")
        self.assertEqual(host.worlds["SC-S"].lifecycle, "suspended")


if __name__ == "__main__":
    unittest.main(verbosity=2)
