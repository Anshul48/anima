# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained-package port of successor-006 resume-coupling contract tests (Q3 owed item -> R9).

Each test pins one item of COUPLING-CONTRACT.md (CC1-CC8, the 8-item
resume-coupling list owed from the Q3 DEMONSTRATED-WITH-COUPLING-LIST
finding) through the CONSUMER surface, plus CC9: the resume engine is
carried byte-identical and drives unmodified resume on a fresh host.

Run from the repo root:
    PYTHONDONTWRITEBYTECODE=1 python3 prototype/successor-006/test_coupling.py

All run dirs live under successor-006/.test-tmp/.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

import anima_substrate  # noqa: E402

PKG = Path(anima_substrate.__file__).resolve().parent
TOP = PKG.parent.parent
TMPROOT = Path(tempfile.mkdtemp(prefix="anima-substrate-tests-"))

from anima_substrate.host import api  # noqa: E402
from anima_substrate.host.minihost import ContractViolation, MiniHost  # noqa: E402
from anima_substrate.host.resume import (  # noqa: E402
    SchedWorld,
    check_args_keys,
    check_propose_result,
    execute_plan,
    latest_formulation,
    read_verdict,
    require_active,
    scan_succeeded,
    successful_invokes,
)

sys.path.insert(0, str(HERE))
import provcheck  # noqa: E402


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


class TestCouplingContract(Base):
    def test_cc1_invoke_kwargs_and_consume_on_success_only(self):
        # Kwarg names pinned by signature ...
        params = list(inspect.signature(MiniHost.invoke).parameters)
        self.assertIn("cost_usd", params)
        self.assertIn("time_s", params)
        # ... and every success invoke on a real consumer run carries
        # the cost block while consuming exactly one invocation.
        root = self.root / "run"
        api.init_run(root)
        api.run_tasks(root, ["S1"])
        host, _ = api.open_run(root)
        ok = [
            e
            for e in host.ledger_entries()
            if e.get("kind") == "invoke" and "error" not in e["payload"]
        ]
        self.assertGreater(len(ok), 0)
        for e in ok:
            self.assertIn("cost_usd", e["payload"]["cost"])
            self.assertIn("time_s", e["payload"]["cost"])
        consumes = [e for e in host.ledger_entries() if e.get("kind") == "consume"]
        self.assertEqual(len(consumes), len(ok))
        # ... while a FAILED invoke records error and consumes NOTHING.
        before = dict(host.holdings["SC-L"])
        n_consume = len(consumes)
        args = host.store_args(
            "SC-L",
            "cc1-fail",
            {
                "formulation_ref": "f",
                "candidate_refs": [],
                "task_id": "CC1",
                "step": "probe",
            },
        )

        def _boom():
            raise ValueError("cc1 induced failure")

        with self.assertRaises(ValueError):
            host.invoke(
                "SC-L",
                "SC-L",
                "sched.propose",
                "1.0",
                args,
                _boom,
                cost_usd=0.0,
                time_s=1.0,
            )
        self.assertEqual(dict(host.holdings["SC-L"]), before)
        entries = host.ledger_entries()
        self.assertEqual(
            len([e for e in entries if e.get("kind") == "consume"]), n_consume
        )
        err = entries[-1]
        self.assertIn("error", err["payload"])
        self.assertNotIn("result_ref", err["payload"])
        self.assertNotIn("consume", err["payload"].get("cost", {}))

    def test_cc2_invoke_payload_keys(self):
        root = self.root / "run"
        api.init_run(root)
        api.run_tasks(root, ["S1"])
        host, _ = api.open_run(root)
        ok = successful_invokes(host.ledger_entries(), "sched.propose")
        self.assertGreater(len(ok), 0)
        for e in ok:
            p = e["payload"]
            self.assertIn("capability", p)
            self.assertIn("args_ref", p)
            self.assertIn("result_ref", p)
            self.assertNotIn("error", p)
        # The matcher keys on EXACTLY these four conditions: an error
        # entry for the same capability is excluded.
        args = host.store_args(
            "SC-L",
            "cc2-fail",
            {
                "formulation_ref": "f",
                "candidate_refs": [],
                "task_id": "CC2",
                "step": "probe",
            },
        )

        def _boom():
            raise ValueError("cc2 induced failure")

        with self.assertRaises(ValueError):
            host.invoke(
                "SC-L",
                "SC-L",
                "sched.propose",
                "1.0",
                args,
                _boom,
                cost_usd=0.0,
                time_s=1.0,
            )
        ok2 = successful_invokes(host.ledger_entries(), "sched.propose")
        self.assertEqual(len(ok2), len(ok))
        self.assertNotIn(("sched.propose", "CC2", "probe"), scan_succeeded(host))

    def test_cc3_args_keys_and_byte_compat_across_kill(self):
        with self.assertRaises(ValueError):
            check_args_keys({"formulation_ref": "only-one-key"})
        root = self.root / "run"
        api.j1_init(root, "PROJ", "cc3")
        api.nest_op(
            root,
            "PROJ",
            "EXP1",
            {"max_cost_usd": 0.5, "max_time_s": 30.0, "max_invocations": 50},
            ["j1.budget"],
            "cc3",
        )
        rep = api.j1_kill_resume_op(root, "EXP1", "CC3-T1", verifier="PROJ")
        self.assertEqual(rep["re_executed_invokes"], 0)
        # The formulate args file crossed the kill boundary byte-
        # identical AND still keys the resume matcher afterwards.
        args_rel = "state/EXP1/args/CC3-T1-formulate@v1.json"
        self.assertIn(args_rel, rep["prekill_artifacts"])
        body = json.loads((root / args_rel).read_text(encoding="utf-8"))
        check_args_keys(body)  # raises when the keys are absent
        host, _ = api.open_run(root)
        self.assertIn(
            ("sched.formulate", "CC3-T1", "formulate@v1"), scan_succeeded(host)
        )

    def test_cc4_result_schemas(self):
        root = self.root / "run"
        api.j1_init(root, "PROJ", "cc4")
        api.nest_op(
            root,
            "PROJ",
            "EXP1",
            {"max_cost_usd": 0.5, "max_time_s": 30.0, "max_invocations": 50},
            ["j1.budget"],
            "cc4",
        )
        api.j1_work_op(root, "EXP1", "CC4-T1", verifier="PROJ")
        host, _ = api.open_run(root)
        prop = [
            e
            for e in host.ledger_entries()
            if e.get("kind") == "invoke"
            and e["payload"].get("capability") == "sched.propose"
            and "error" not in e["payload"]
        ][0]
        body = check_propose_result(prop["payload"]["result_ref"])
        self.assertIn("candidate_refs", body)
        self.assertIn("champion_id", body)
        # The C3 check is enforced, not advisory.
        bad = root / "bad-result.json"
        bad.write_text(json.dumps({"nope": 1}), encoding="utf-8")
        with self.assertRaises(ValueError):
            check_propose_result(str(bad))

    def test_cc5_lifecycle_read_shape(self):
        root = self.root / "run"
        api.init_run(root)
        host, _ = api.open_run(root)
        # The read shape is a mapping view + string compare ...
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        require_active(host, "SC-L")
        # ... and a non-active world refuses work loudly.
        api.quarantine_op(root, "SC-L", "SC-S", "cc5")
        host2, _ = api.open_run(root)
        self.assertEqual(host2.worlds["SC-L"].lifecycle, "suspended")
        with self.assertRaises(RuntimeError):
            require_active(host2, "SC-L")
        args = host2.store_args(
            "SC-S", "cc5-x", {"formulation_ref": "f", "candidate_refs": []}
        )
        with self.assertRaises(ContractViolation):
            host2.invoke(
                "SC-S",
                "SC-L",
                "sched.propose",
                "1.0",
                args,
                lambda: "never",
                cost_usd=0.0,
                time_s=0.0,
            )
        denies = [
            e
            for e in host2.ledger_entries()
            if e.get("kind") == "deny" and e["payload"].get("action") == "invoke"
        ]
        self.assertGreater(len(denies), 0)

    def test_cc6_deny_positional_order(self):
        params = list(inspect.signature(MiniHost.deny).parameters)
        self.assertEqual(params[:4], ["self", "actor", "action", "reason"])
        root = self.root / "run"
        api.init_run(root)
        host, _ = api.open_run(root)
        host.deny("tester", "probe.action", "cc6 reason")
        entry = host.ledger_entries()[-1]
        self.assertEqual(entry["kind"], "deny")
        self.assertEqual(entry["actor"], "tester")
        self.assertEqual(entry["payload"]["action"], "probe.action")
        self.assertEqual(entry["payload"]["reason"], "cc6 reason")

    def test_cc7_world_handle_shape(self):
        root = self.root / "run"
        api.init_run(root)
        api.run_tasks(root, ["S1"])
        host, _ = api.open_run(root)
        w = SchedWorld(host.worlds["SC-L"].instance_state_dir)
        # state_dir is path-like ...
        self.assertTrue(Path(w.state_dir).is_dir())
        # ... the formulations glob finds the latest artifact ...
        latest = latest_formulation(w.state_dir)
        self.assertTrue(latest.endswith(".json"))
        # ... and verdicts/verdict.json carries the phase verdict.
        sw = SchedWorld(host.worlds["SC-S"].instance_state_dir)
        verdict = read_verdict(sw.state_dir)
        self.assertIn("phase_verdict", verdict)
        self.assertTrue((sw.state_dir / "verdicts" / "verdict-S1.json").exists())

    def test_cc8_suspend_reattach_shapes(self):
        self.assertEqual(
            list(inspect.signature(MiniHost.suspend).parameters),
            ["self", "world_id", "actor", "reason", "pending_effects"],
        )
        self.assertEqual(
            list(inspect.signature(MiniHost.reattach).parameters),
            ["self", "world_id", "actor", "reason"],
        )
        root = self.root / "run"
        api.init_run(root)
        host, _ = api.open_run(root)
        host.suspend(
            "SC-L", "host", "cc8 probe", pending_effects=[{"note": "shape probe"}]
        )
        self.assertEqual(host.worlds["SC-L"].lifecycle, "suspended")
        host.reattach("SC-L", "host", reason="cc8 probe done")
        self.assertEqual(host.worlds["SC-L"].lifecycle, "active")
        with self.assertRaises(ContractViolation):
            host.reattach("SC-L", "host", reason="not suspended")

    def test_cc9_engine_carried_unmodified_and_resumes(self):
        # Port delta: the frozen byte-identity pin becomes PROVENANCE
        # consistency (recorded sha == live bytes for resume.py; the
        # full both-directions check lives in test_14). The
        # behavioral proof — unmodified resume on a fresh host —
        # is unchanged and is the actual Q3 demonstration.
        recorded = provcheck.recorded_files()
        rel = "src/anima_substrate/host/resume.py"
        self.assertIn(rel, recorded)
        self.assertEqual(provcheck.live_sha(rel), recorded[rel])
        # And it resumes unmodified on a FRESH host: re-driving a
        # finished plan skips every step with zero re-execution.
        root = self.root / "run"
        api.j1_init(root, "PROJ", "cc9")
        api.nest_op(
            root,
            "PROJ",
            "EXP1",
            {"max_cost_usd": 0.5, "max_time_s": 30.0, "max_invocations": 50},
            ["j1.budget"],
            "cc9",
        )
        first = api.j1_work_op(root, "EXP1", "CC9-T1", verifier="PROJ")
        self.assertEqual(len(first["executed"]), 3)
        host, _ = api.open_run(root)
        task = api.j1_task("CC9-T1")
        plan, _, _ = api.j1_plan(host, task, "EXP1", "PROJ")
        rep = execute_plan(host, plan, prekill=scan_succeeded(host))
        self.assertEqual(rep["executed"], [])
        self.assertEqual(len(rep["skipped"]), 3)
        self.assertEqual(rep["re_executed_invokes"], 0)

    def test_contract_file_lists_all_items(self):
        doc = (TOP / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
        for item in ("CC1", "CC2", "CC3", "CC4", "CC5", "CC6", "CC7", "CC8", "CC9"):
            self.assertIn(item, doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
