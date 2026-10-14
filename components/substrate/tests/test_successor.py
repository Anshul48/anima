# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained-package port of successor-004 test suite (unittest, stdlib-only).

Run from the package root:
    .venv/bin/python -m pytest tests/test_successor.py -q

Run dirs live under a private tmp prefix. The SST legs
(TestSSTSnapshot) run against the caller-staged SST root
(SUBSTRATE_SST_ROOT, compat probe) and skip with an explicit reason
otherwise; every other test is pure stdlib in-process.
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
import time
import unittest

HERE = Path(__file__).resolve().parent

import anima_substrate  # noqa: E402

PKG = Path(anima_substrate.__file__).resolve().parent
TOP = PKG.parent.parent
TMPROOT = Path(tempfile.mkdtemp(prefix="anima-substrate-tests-"))

from anima_substrate.demos import successor_demo as DEMO  # noqa: E402
from anima_substrate.host.fusion import (  # noqa: E402
    fuse_worlds,
    quarantine_world,
    reuse_composite,
)
from anima_substrate.host.minihost import ContractViolation, MiniHost  # noqa: E402
from anima_substrate.host.pipeline import (  # noqa: E402
    FUSED_CAPS,
    Q_CAPS,
    LaneCtx,
    build_formulate,
    build_propose,
    build_verify,
    run_sched_task,
    s3_partial_plan,
    s3_resume_flow,
)
from anima_substrate.host.resume import (  # noqa: E402
    execute_plan,
    latest_formulation,
    read_verdict,
    reapply_revocations,
    scan_succeeded,
    successful_invokes,
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
from anima_substrate.participants.sched import sched_checker as checker  # noqa: E402
from anima_substrate.participants.sched import sched_domain as domain  # noqa: E402
from anima_substrate.participants.sched import sched_inputs as FI  # noqa: E402
from anima_substrate.participants.sst.manifest import (  # noqa: E402
    PINNED_MANIFEST as SNAPSHOT_MANIFEST,
)
from anima_substrate.participants.sst.staged import (  # noqa: E402
    SSTBoundary,
    probe,
    run_sst_test_search,
    verify_snapshot,
)

sys.path.insert(0, str(HERE))
import provcheck  # noqa: E402

# Port delta (test_14): the frozen minihost byte pin
# (successor-005 4cb3c1dd...095a4) cannot hold in a maintained tree
# whose imports are package-relative. It becomes PROVENANCE
# discipline instead: every shipped file's sha256 MUST be recorded
# in PROVENANCE.md's file-record section and MUST match live bytes
# (checked BOTH directions — no unrecorded files, no stale records).
# The frozen-import scan and the stdlib-only import check are kept
# at full strength over the package tree.


def _sst_staging():
    """(snapshot_src, venv_py, skip_reason); reason None when runnable."""
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
    return Path(rep["snapshot_src"]), Path(rep["venv_py"]), None


SST_SRC, SST_VENV_PY, SST_SKIP = _sst_staging()


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


class TestContractV1(Base):
    def test_01_c1_invoke_success_shape(self):
        host, _ = self.main_host()
        before = dict(host.holdings["SC-L"])
        args = host.store_args(
            "SC-L", "t1", {"formulation_ref": "", "candidate_refs": []}
        )
        entry = host.invoke(
            "SC-L",
            "SC-L",
            "sched.clarify",
            "1.0",
            args,
            lambda: "/tmp/r",
            cost_usd=0.0,
            time_s=1.0,
        )
        p = entry["payload"]
        self.assertEqual(p["capability"], "sched.clarify")
        self.assertEqual(p["args_ref"], args)
        self.assertEqual(p["result_ref"], "/tmp/r")
        self.assertNotIn("error", p)  # C1: success carries no error
        kinds = [e["kind"] for e in host.ledger_entries()]
        self.assertIn("consume", kinds)  # consumed ON SUCCESS ONLY
        self.assertEqual(
            host.holdings["SC-L"]["max_invocations"], before["max_invocations"] - 1
        )

    def test_02_c1_failed_invoke_no_consume(self):
        host, _ = self.main_host()
        before = dict(host.holdings["SC-L"])
        args = host.store_args(
            "SC-L", "t2", {"formulation_ref": "", "candidate_refs": []}
        )

        def boom():
            raise ValueError("planned failure")

        with self.assertRaises(ValueError):
            host.invoke(
                "SC-L",
                "SC-L",
                "sched.clarify",
                "1.0",
                args,
                boom,
                cost_usd=0.0,
                time_s=1.0,
            )
        kinds = [e["kind"] for e in host.ledger_entries()]
        self.assertNotIn("consume", kinds)  # failed call burns nothing
        self.assertEqual(host.holdings["SC-L"], before)
        err = [e for e in host.ledger_entries() if e.get("kind") == "invoke"][-1][
            "payload"
        ]
        self.assertIn("error", err)
        self.assertNotIn("result_ref", err)
        # ... and the resume matcher excludes it (never skips on failure)
        self.assertEqual(successful_invokes(host.ledger_entries(), "sched.clarify"), [])

    def test_03_c2_c3_args_result_schemas(self):
        host, _ = self.main_host()
        ctx = LaneCtx("central", Coordinator(), ChannelRegistry())
        task = copy.deepcopy(FI.S1)
        step = build_propose(
            host, task, "SC-L", "merged reqs + clarified prefs (O2)", ctx
        )
        self.assertIn("formulation_ref", step["args"])  # C2 keys ...
        self.assertIn("candidate_refs", step["args"])  # ... on every args
        rep = execute_plan(host, [step])
        self.assertEqual(rep["re_executed_invokes"], 0)
        args_body = json.loads(
            Path(host.store_args("SC-L", "probe", step["args"])).read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("formulation_ref", args_body)
        self.assertIn("candidate_refs", args_body)
        res_ref = [e for e in host.ledger_entries() if e.get("kind") == "invoke"][-1][
            "payload"
        ]["result_ref"]
        body = json.loads(Path(res_ref).read_text(encoding="utf-8"))
        self.assertIn("candidate_refs", body)  # C3 propose schema
        self.assertIn("champion_id", body)
        self.assertTrue(Path(body["candidate_refs"][0]).exists())

    def test_04_c4_c5_lifecycle_deny_shapes(self):
        host, _ = self.main_host()
        # C4: lifecycle read shape host.worlds[ID].lifecycle == "active"
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        # C5: deny(actor, action, reason) positional
        host.deny("SC-L", "probe.action", "probe reason")
        last = host.ledger_entries()[-1]
        self.assertEqual(last["kind"], "deny")
        self.assertEqual(last["actor"], "SC-L")
        self.assertEqual(last["payload"]["action"], "probe.action")
        # C5: suspend(world_id, actor, reason, pending_effects) positional
        host.suspend("SC-L", "host", "c5 probe", pending_effects=[])
        self.assertEqual(host.worlds["SC-L"].lifecycle, "suspended")
        host.reattach("SC-L", "host", "c5 probe over")
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        # reattach refusal: raises + recorded deny
        with self.assertRaises(ContractViolation):
            host.reattach("SC-L", "host", "not suspended")
        denies = [
            e
            for e in host.ledger_entries()
            if e.get("kind") == "deny" and e["payload"].get("action") == "reattach"
        ]
        self.assertTrue(denies)
        # unknown-capability refusal: raises + recorded deny
        with self.assertRaises(ContractViolation):
            host.invoke(
                "SC-L",
                "SC-L",
                "nope.missing",
                "9.9",
                host.store_args("SC-L", "t4", {}),
                lambda: "x",
            )
        denies = [e for e in host.ledger_entries() if e.get("kind") == "deny"]
        self.assertTrue(denies)

    def test_05_c6_c7_conventions_settle_reopen(self):
        host, pristine = self.main_host()
        ctx = LaneCtx("central", Coordinator(), ChannelRegistry())
        m = run_sched_task(self.root, host, FI.S1, ctx)
        self.assertTrue(m["valid"])
        ldir = Path(host.worlds["SC-L"].instance_state_dir)
        sdir = Path(host.worlds["SC-S"].instance_state_dir)
        # C6: formulations/*.json glob + verdicts/verdict.json
        self.assertTrue(latest_formulation(ldir).endswith(".json"))
        verdict = read_verdict(sdir)
        self.assertIn("phase_verdict", verdict)
        self.assertTrue(verdict["phase_verdict"])
        # C7: settle markers + conservation + reopen roundtrip
        fin = finish_worlds(host, ["SC-L", "SC-S"], reason="t5")
        self.assertTrue(fin["conservation_ok"])
        kinds = [e["kind"] for e in host.ledger_entries()]
        self.assertGreaterEqual(kinds.count("grant_settle"), 2)
        host2 = MiniHost.reopen(
            self.root / "state",
            self.root / "ledger.jsonl",
            rebuild_records(self.root, pristine),
            actor="host",
            reason="t5 reopen",
        )
        self.assertEqual(host2.worlds["SC-L"].lifecycle, "dissolved")
        # C7 fail-closed withholding: no descriptors -> WITHHELD invokes.
        # (Separate host: the world stays ACTIVE so the ONLY refusal
        # cause is the withheld authority stamp.)
        wroot = self.root / "withheld"
        w = world_record(
            wroot / "state", "W-ACT", [("sched.clarify", "1.0")], [("sched-list", "v1")]
        )
        _wh = setup_host(wroot, [w])
        wh2 = MiniHost.reopen(
            wroot / "state",
            wroot / "ledger.jsonl",
            records=None,
            actor="host",
            reason="t5 withheld",
        )
        self.assertEqual(wh2.worlds["W-ACT"].lifecycle, "active")
        with self.assertRaises(ContractViolation):
            wh2.invoke(
                "W-ACT",
                "W-ACT",
                "sched.clarify",
                "1.0",
                wh2.store_args("W-ACT", "t5w", {}),
                lambda: "x",
            )
        denies = [e for e in wh2.ledger_entries() if e.get("kind") == "deny"]
        self.assertTrue(
            any("recovery.withheld" in d["payload"]["reason"] for d in denies), denies
        )


class TestRouting(Base):
    def test_06_routing_central_default(self):
        host, _ = self.main_host()
        d = route(FI.S1)
        self.assertEqual(d["lane"], "central")
        record_routing(host, d, self.root / "ROUTING-LOG.jsonl")
        m = run_sched_task(
            self.root, host, FI.S1, LaneCtx("central", Coordinator(), ChannelRegistry())
        )
        self.assertTrue(m["valid"])
        self.assertEqual(m["quality"], m["prefs_total"])
        self.assertEqual(m["direct_bytes"], 0)
        self.assertGreater(m["central_bytes"], 0)
        # routing recorded per task: ledger entry + log line
        payloads = [
            e["payload"] for e in host.ledger_entries() if e.get("kind") == "routing"
        ]
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["task_id"], "S1")
        log = (
            (self.root / "ROUTING-LOG.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        self.assertEqual(len(log), 1)
        self.assertEqual(json.loads(log[0])["lane"], "central")
        # live counters agree with durable recomputation (no kill here)
        self.assertEqual(m["central_bytes"], m["live_central_bytes"])

    def test_07_routing_local_dialogue(self):
        host, _ = self.main_host()
        d = route(FI.S2)
        self.assertEqual(d["lane"], "local")
        record_routing(host, d, self.root / "ROUTING-LOG.jsonl")
        chans = ChannelRegistry()
        coord = HCoordinator()
        # local-lane guard: non-export payload refused, exports pass
        with self.assertRaises(ValueError):
            coord.handle(domain.req_fragment("S2", "SC-L", {}, []))
        coord.handle(domain.commitment("S2", "SC-L", {}, receipt="probe"))
        m = run_sched_task(self.root, host, FI.S2, LaneCtx("local", coord, chans))
        self.assertTrue(m["valid"])
        self.assertEqual(m["quality"], m["prefs_total"])
        self.assertGreater(m["direct_bytes"], 0)
        # local lane: coordinator handled commitments only
        kinds = {h["kind"] for h in coord.handled}
        self.assertTrue(kinds <= {"commitment", "escalation", "resolution"}, kinds)


class TestKillResume(Base):
    def test_08_kill_resume_zero_reinvoke(self):
        host, pristine = self.main_host()
        chans = ChannelRegistry()
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "anima_substrate.demos.successor_demo",
                "--child-partial",
                str(self.root),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        t0 = time.time()
        while not (self.root / "child.READY").exists():
            self.assertLess(time.time() - t0, 120, "child never READY")
            if child.poll() is not None:
                self.fail(
                    f"child died early rc={child.returncode}: "
                    f"{child.stderr.read().decode()[-2000:]}"
                )
            time.sleep(0.2)
        prekill = {
            str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((self.root / "state").rglob("*"))
            if p.is_file()
        }
        child.kill()  # Popen.kill(): SIGKILL/TerminateProcess
        _, err = child.communicate(timeout=60)
        self.assertNotEqual(child.returncode, 0)
        host = MiniHost.reopen(
            self.root / "state",
            self.root / "ledger.jsonl",
            rebuild_records(self.root, pristine),
            actor="host",
            reason="t8 resume",
        )
        self.assertEqual(reapply_revocations(host), [])
        pk = scan_succeeded(host)
        self.assertIn(("sched.formulate", "S3", "formulate@v1"), pk)
        m3 = s3_resume_flow(
            self.root, host, FI.S3, LaneCtx("local", HCoordinator(), chans), pk
        )
        self.assertTrue(m3["valid"])
        self.assertEqual(m3["re_executed_invokes"], 0)
        self.assertIn("sched.formulate@formulate@v1", m3["skipped"])
        self.assertIn("sched.clarify@clarify@r1", m3["skipped"])
        self.assertIn("sched.clarify@clarify@r2", m3["skipped"])
        postkill = {
            str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((self.root / "state").rglob("*"))
            if p.is_file()
        }
        for k, v in prekill.items():
            self.assertEqual(postkill.get(k), v, f"changed: {k}")
        n_reopen = sum(
            1 for e in host.ledger_entries() if e.get("kind") == "host_reopen"
        )
        self.assertGreaterEqual(n_reopen, 2)  # child attach + parent resume

    def test_09_revision_revocation_ruling(self):
        # Same S3 flow on a fresh host (no kill): revision, revocation,
        # denied retry, escalation, ruling, void, v2 re-propose.
        host, pristine = self.main_host()
        chans = ChannelRegistry()
        ctx = LaneCtx("local", HCoordinator(), chans)
        pre = execute_plan(host, s3_partial_plan(host, FI.S3, ctx))
        self.assertEqual(pre["re_executed_invokes"], 0)
        m3 = s3_resume_flow(self.root, host, FI.S3, ctx, scan_succeeded(host))
        self.assertTrue(m3["valid"])
        self.assertEqual(m3["re_executed_invokes"], 0)
        kinds = {}
        for e in host.ledger_entries():
            kinds.setdefault(e["kind"], []).append(e.get("payload", {}))
        self.assertIn("revision", kinds)
        self.assertEqual(kinds["revision"][0]["to"], "list2slot/v2")
        self.assertIn("revoke", kinds)
        self.assertEqual(m3["revoked"], "SC-L:sched.propose@1.0->SC-S")
        self.assertIsNotNone(m3["denied_retry"])
        self.assertIn("escalation", kinds)
        self.assertIn("resolution", kinds)
        self.assertIn("void", kinds)
        self.assertTrue(Path(m3["void_ref"]).exists())  # E3: kept on disk
        # revocation survives reopen (re-applied from the ledger)
        host2 = MiniHost.reopen(
            self.root / "state",
            self.root / "ledger.jsonl",
            rebuild_records(self.root, pristine),
            actor="host",
            reason="t9 reopen",
        )
        redone = reapply_revocations(host2)
        self.assertEqual(redone, ["SC-L:sched.propose@1.0"])
        with self.assertRaises(ContractViolation):
            host2.invoke(
                "SC-L",
                "SC-L",
                "sched.propose",
                "1.0",
                host2.store_args("SC-L", "t9", {}),
                lambda: "x",
            )


class TestFusionQuarantine(Base):
    def test_10_fusion_inventory_reuse(self):
        host, _ = self.main_host()
        chans = ChannelRegistry()
        m2 = run_sched_task(
            self.root, host, FI.S2, LaneCtx("local", HCoordinator(), chans)
        )
        self.assertTrue(m2["valid"])
        fused_rec = world_record(
            self.root / "state",
            "SC-FUSED",
            FUSED_CAPS,
            [("sched-list", "v2"), ("sched-slot", "v2")],
        )
        fus = fuse_worlds(
            host, chans, "SC-L", "SC-S", "SC-FUSED", fused_rec, "host", "t10 fusion"
        )
        # lineage: derived_from both parents
        derived = [
            e["world"]
            for e in fus["lineage"]
            if isinstance(e, dict) and e.get("rel") == "derived_from"
        ]
        self.assertEqual(sorted(derived), ["SC-L", "SC-S"])
        # ownership transfer: all three state classes moved
        self.assertEqual(len(fus["transfers"]), 3)
        self.assertEqual(
            host.worlds["SC-FUSED"].custodians,
            {
                "sched.composite": "SC-FUSED",
                "sched.requirements": "SC-FUSED",
                "sched.slots": "SC-FUSED",
            },
        )
        # lifecycle moves: parents dissolved, composite active
        self.assertEqual(host.worlds["SC-L"].lifecycle, "dissolved")
        self.assertEqual(host.worlds["SC-S"].lifecycle, "dissolved")
        self.assertEqual(host.worlds["SC-FUSED"].lifecycle, "active")
        # redundant mechanism removed: the direct channel is gone
        self.assertEqual(fus["removed_mechanism"], "direct-channel:SC-L<->SC-S")
        self.assertIn("direct-channel:SC-L<->SC-S", fus["before"]["mechanisms"])
        self.assertNotIn("direct-channel:SC-L<->SC-S", fus["after"]["mechanisms"])
        with self.assertRaises(KeyError):
            chans.channels[ChannelRegistry.key("SC-L", "SC-S")]
        # reuse the fused composite on a follow-up task elsewhere
        m4 = reuse_composite(self.root, host, "SC-FUSED", FI.S4_FOLLOWUP)
        self.assertTrue(m4["valid"])
        self.assertTrue(m4["lineage_ok"])
        self.assertEqual(sorted(m4["derived_from"]), ["SC-L", "SC-S"])

    def test_11_quarantine_separation(self):
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
        ctx = LaneCtx("central", Coordinator(), None)
        rep = execute_plan(host, [build_formulate(host, task, "SC-Q", "v1", ctx)])
        self.assertEqual(len(rep["executed"]), 1)
        quar = quarantine_world(host, "SC-Q", "SC-B", "host", "t11 drill")
        self.assertEqual(quar["commitments"], ["sched.commitment-q"])
        self.assertEqual(host.worlds["SC-Q"].lifecycle, "suspended")
        self.assertEqual(host.worlds["SC-B"].custodians, {"sched.commitment-q": "SC-B"})
        # quarantined world refuses invokes, with recorded deny
        with self.assertRaises(ContractViolation):
            host.invoke(
                "SC-Q",
                "SC-Q",
                "sched.propose",
                "1.0",
                host.store_args(
                    "SC-Q", "t11-probe", {"formulation_ref": "", "candidate_refs": []}
                ),
                lambda: "never",
            )
        self.assertTrue([e for e in host.ledger_entries() if e.get("kind") == "deny"])
        # standby completes the transferred commitment
        bprop = build_propose(
            host,
            task,
            "SC-B",
            "merged reqs + clarified prefs (O2; standby)",
            ctx,
            tag="propose",
        )
        bver = build_verify(host, task, "SC-B", ctx, "SC-B", "propose")
        brep = execute_plan(host, [bprop, bver])
        self.assertEqual(brep["re_executed_invokes"], 0)
        fin = finish_worlds(host, ["SC-Q", "SC-B"], reason="t11 over")
        self.assertTrue(fin["conservation_ok"])


class TestCheckerIsolation(Base):
    def test_12_checker_independent(self):
        self.assertEqual(checker.self_check()["known_good"]["quality"], 4)
        # mutated solutions fail on constraints, not on identity
        bad = dict(checker.KNOWN_GOOD)
        bad["A"], bad["B"] = bad["B"], bad["A"]  # swap -> window violation
        rep = checker.check(bad, checker.KNOWN_TASK)
        self.assertFalse(rep["valid"])
        self.assertTrue(rep["violations"])
        # quality counts satisfied prefs (partial credit, still valid)
        partial = {"A": "S0", "B": "S3", "C": "S0", "D": "S2"}
        rep = checker.check(partial, checker.KNOWN_TASK)
        self.assertFalse(rep["valid"])  # double S0
        ok_partial = {"A": "S2", "B": "S3", "C": "S1", "D": "S2"}
        rep = checker.check(ok_partial, checker.KNOWN_TASK)
        self.assertFalse(rep["valid"])  # double S2
        # quality counts satisfied prefs: suboptimal-but-valid exists here
        tiny = {
            "task_id": "tiny",
            "slots": {
                "S0": {"machine": "M0", "time": "t0"},
                "S1": {"machine": "M1", "time": "t0"},
            },
            "tasks": {"X": {"window": ["S0", "S1"]}, "Y": {"window": ["S0", "S1"]}},
            "precedence": [],
            "prefs": {"X": "M0", "Y": "M1"},
        }
        rep = checker.check({"X": "S0", "Y": "S1"}, tiny)
        self.assertTrue(rep["valid"])
        self.assertEqual(rep["quality"], 2)
        rep = checker.check({"X": "S1", "Y": "S0"}, tiny)
        self.assertTrue(rep["valid"])
        self.assertEqual(rep["quality"], 0)

    def test_14_no_frozen_imports_vendor_pinned(self):
        # PROVENANCE discipline (port delta, see header): every
        # shipped file recorded, every record matching live bytes.
        recorded = provcheck.recorded_files()
        shipped = provcheck.shipped_files()
        self.assertTrue(recorded, "PROVENANCE.md file record is empty")
        self.assertEqual(sorted(recorded), shipped)
        for rel in shipped:
            self.assertEqual(provcheck.live_sha(rel), recorded[rel], rel)
        # No SST bytes ship: the package carries pins, never sources.
        for rel in shipped:
            self.assertFalse(
                rel.startswith("src/anima_substrate/participants/sst/sst/"), rel
            )
        forbidden = [
            "w1-harden",
            "reuse-demo",
            "x3-20261004",
            "x3_run",
            "frozen_inputs",
            "w1h_bridge",
            "recovery_lib",
            "arm_c",
            "arm_h",
            "xcommon",
            "vendor/sst-snapshot",
        ]
        # Prose may cite source trees (provenance comments); imports
        # and paths must not touch them — hence the wider token set
        # for the import scan.
        forbidden_imports = forbidden + ["prototype/", "successor-00"]
        # This test file names the tokens in its own scan list:
        # exclude it from the text scan (import scan below still
        # covers every file including this one). minihost.py keeps
        # its historical docstring (bridge reference, no runtime
        # dependency — proven by the stdlib-import check below), so
        # it is excluded from the text scan exactly as upstream.
        for py in sorted(PKG.rglob("*.py")):
            if py.name == "minihost.py":
                continue
            text = py.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{py.relative_to(TOP)}: {token}")
        # ... but NO file (shipped or test) may IMPORT from frozen dirs
        for py in sorted(PKG.rglob("*.py")) + sorted(HERE.glob("*.py")):
            for line in py.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s.startswith(("import ", "from ")):
                    for token in forbidden_imports:
                        self.assertNotIn(token, s, f"{py.name}: {s}")
        # host imports are stdlib-only (+ intra-package)
        allowed = set(sys.stdlib_module_names) | {"anima_substrate"}
        for py in sorted((PKG / "host").glob("*.py")):
            for line in py.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s.startswith("import "):
                    mods = s[len("import ") :].split(",")
                    for m in mods:
                        self.assertIn(
                            m.strip().split(".")[0].split(" ")[0],
                            allowed,
                            f"{py.name}: {s}",
                        )
                elif s.startswith("from "):
                    if s.startswith("from ."):
                        continue  # explicit relative: intra-package
                    self.assertIn(
                        s.split()[1].split(".")[0], allowed, f"{py.name}: {s}"
                    )


class TestSettle(Base):
    def test_15_settle_zero_stranded(self):
        host, _ = self.main_host()
        run_sched_task(
            self.root, host, FI.S1, LaneCtx("central", Coordinator(), ChannelRegistry())
        )
        run_sched_task(
            self.root, host, FI.S2, LaneCtx("local", HCoordinator(), ChannelRegistry())
        )
        fin = finish_worlds(host, ["SC-L", "SC-S"], reason="t15")
        for wid, hold in fin["stranded"].items():
            self.assertEqual(
                hold,
                {"max_cost_usd": 0.0, "max_time_s": 0.0, "max_invocations": 0},
                wid,
            )
        self.assertTrue(fin["conservation_ok"])
        # negative: handwritten unsettled terminal is rejected
        host.append(
            "lifecycle",
            {
                "world_id": "SC-GHOST",
                "from": "active",
                "to": "dissolved",
                "reason": "handwritten",
            },
            actor="host",
        )
        with self.assertRaises(ContractViolation):
            host.verify_conservation()


@unittest.skipIf(SST_SKIP is not None, SST_SKIP or "SST unstaged")
class TestSSTSnapshot(unittest.TestCase):
    """SST legs over the caller-staged root (M2 optional extra).

    Port delta: the vendored snapshot is gone (no SST bytes ship);
    these legs run against SUBSTRATE_SST_ROOT when the compat probe
    passes and SKIP with an explicit reason otherwise. A skip here
    is reported separately — it is never counted as green.
    """

    def test_13_sst_snapshot_consumption(self):
        case = TMPROOT / "test_13_sst_snapshot_consumption"
        root = case / "sst"
        if case.exists():
            shutil.rmtree(case)
        root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, case, True)
        pre = verify_snapshot(SST_SRC)
        self.assertEqual(pre["verdict"], "MATCH")
        self.assertEqual(pre["file_count"], 54)
        ev = run_sst_test_search(root.resolve(), SST_SRC, SST_VENV_PY)
        self.assertEqual(ev["snapshot_check"], "MATCH")
        self.assertEqual(ev["snapshot_hash"], pre["snapshot_hash"])
        self.assertEqual(ev["cost_usd"], 0.0)
        self.assertTrue(ev["snapshot_unchanged"])
        self.assertIn(str(SST_SRC), ev["sst_file"])
        for key in (
            "tree_id",
            "termination_reason",
            "champion",
            "alternatives",
            "budget_consumed",
            "provider_errors",
            "gateway_bindings",
            "event_log_ref",
        ):
            self.assertIn(key, ev["envelope_keys"])
        self.assertEqual(ev["termination_reason"], "champion_found")
        self.assertIsNotNone(ev["champion"])

    def _snapshot_copy(self, case: str) -> Path:
        assert SST_SRC is not None
        dst = TMPROOT / case / "snapcopy"
        if dst.parent.exists():
            shutil.rmtree(dst.parent)
        shutil.copytree(SST_SRC, dst, ignore=shutil.ignore_patterns("__pycache__"))
        self.addCleanup(shutil.rmtree, dst.parent, True)
        return dst

    def test_16_snapshot_changed_bytes_refused(self):
        dst = self._snapshot_copy("test_16_changed")
        target = dst / "sst" / "search" / "policy.py"
        os.chmod(target, 0o644)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("# tamper\n")
        with self.assertRaises(SSTBoundary) as ctx:
            verify_snapshot(dst, SNAPSHOT_MANIFEST)
        self.assertIn("sst/search/policy.py", str(ctx.exception))

    def test_17_snapshot_missing_extra_refused(self):
        dst = self._snapshot_copy("test_17_missing")
        target = dst / "sst" / "gateway" / "gateway.py"
        os.chmod(target, 0o644)
        target.unlink()
        with self.assertRaises(SSTBoundary) as ctx:
            verify_snapshot(dst, SNAPSHOT_MANIFEST)
        self.assertIn("sst/gateway/gateway.py", str(ctx.exception))
        dst2 = self._snapshot_copy("test_17_extra")
        (dst2 / "sst" / "rogue.py").write_text("x = 1\n", encoding="utf-8")
        with self.assertRaises(SSTBoundary) as ctx2:
            verify_snapshot(dst2, SNAPSHOT_MANIFEST)
        self.assertIn("sst/rogue.py", str(ctx2.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
