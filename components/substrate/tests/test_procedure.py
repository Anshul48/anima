# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained-package port of successor-005 procedure-participant tests (unittest, stdlib-only).

Proves S5-A2–S5-A8 + the in-tree A10/A11 legs from S5-DESIGN §6:
declaration honesty + tamper legs (A2), service honesty incl.
zero-spawn + hybrid worlds (A3), the P1–P15 permission matrix +
escape refusals + negative-wording legs (A4), accountability
completeness + hash recomputation (A5), the L1–L6 interruption
matrix incl. deterministic hooks + real-SIGKILL in-window legs +
repeated kills (A6), conservation + grant exactness + recover
output classes + never-spawns proof (A7), the new-world change
flow (A8), vehicle-readiness static legs (A10), and the tree-wide
wording audit (A11). S5-A1 (carried suites green) and S5-A9
(frozen intact) are proven by running the carried suites +
IDENTITY re-checks (see EVIDENCE.md); S5-A10 runs + S5-A12 follow.

Run from the repo root:
    PYTHONDONTWRITEBYTECODE=1 python3 prototype/successor-005/test_procedure.py

All run dirs live under successor-005/.test-tmp/ (nothing is written
outside successor-005/). No exact wall-clock assertions anywhere:
time appears only in bounds/inequalities and as a guard.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
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

from anima_substrate.host import api  # noqa: E402
from anima_substrate.host import procedure as PROC  # noqa: E402
from anima_substrate.host.minihost import ContractViolation  # noqa: E402
from anima_substrate.host.pipeline import LaneCtx, build_formulate  # noqa: E402
from anima_substrate.host.resume import (  # noqa: E402
    execute_plan,
    scan_succeeded,
)
from anima_substrate.host.routing import ChannelRegistry, Coordinator  # noqa: E402
from anima_substrate.participants.sched import sched_inputs as FI  # noqa: E402

CRASH_RC = 42


def child_env(**extra) -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for var in (
        "SUBSTRATE_CRASH_AFTER_APPENDS",
        "SUBSTRATE_CRASH_AT",
        "SUBSTRATE_CRASH_MID_APPEND",
        "SUBSTRATE_CRASH_MID_SIDE_WRITE",
        "PROC_PY",
    ):
        env.pop(var, None)
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


def spawn_cli(*args: str, env: dict | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "anima_substrate", *args],
        cwd=str(HERE),
        env=env or child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )


def kill_group(proc: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def ledger_lines(root: Path) -> list[dict]:
    out = []
    with open(root / "ledger.jsonl", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def proc_invokes(
    root: Path,
    key: str | None = None,
    step: str | None = None,
    errors: bool | None = None,
) -> list[dict]:
    """proc.exec invoke PAYLOADS, optionally filtered."""
    out = []
    for e in ledger_lines(root):
        if e.get("kind") != "invoke":
            continue
        p = e["payload"]
        if p.get("capability") != "proc.exec":
            continue
        proc = p.get("proc", {})
        if key is not None and proc.get("idem_key") != key:
            continue
        if step is not None and proc.get("step") != step:
            continue
        if errors is True and "error" not in p:
            continue
        if errors is False and "error" in p:
            continue
        out.append(p)
    return out


def proc_begins_of(
    root: Path, key: str | None = None, step: str | None = None
) -> list[dict]:
    out = []
    for e in ledger_lines(root):
        if e.get("kind") != "proc_begin":
            continue
        p = e["payload"]
        if key is not None and p.get("idem_key") != key:
            continue
        if step is not None and p.get("step") != step:
            continue
        out.append(p)
    return out


def c_step(
    step: str,
    outputs=("out.txt",),
    timeout: int = 60,
    extra_code: str = "",
    env_extra: dict | None = None,
) -> dict:
    """A manifest step running `python3 -c` (no bundle files needed)."""
    code = "".join(f"open({o!r},'w').write('v:{step}:{o}\\n');" for o in outputs)
    code += extra_code + f"print('done-{step}')"
    d: dict = {
        "step": step,
        "argv": ["python3", "-c", code],
        "declared_outputs": list(outputs),
        "timeout_s": timeout,
    }
    if env_extra:
        d["env_extra"] = dict(env_extra)
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)

    def bundle(
        self,
        name: str,
        steps: list[dict],
        files: dict | None = None,
        raw_manifest: dict | None = None,
        tag: str = "bundles",
    ) -> Path:
        """Write a caller bundle dir; return its path."""
        bdir = self.root / tag / name
        if bdir.exists():
            shutil.rmtree(bdir)
        bdir.mkdir(parents=True)
        fmap: dict[str, str] = {}
        for rel, body in (files or {}).items():
            data = body.encode() if isinstance(body, str) else body
            dest = bdir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            fmap[rel] = hashlib.sha256(data).hexdigest()
        manifest = {"files": fmap, "steps": steps}
        if raw_manifest is not None:
            manifest = raw_manifest
        (bdir / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True)
        )
        return bdir

    def create(
        self, run: str, world: str, bundle: Path, sched_preset: str | None = None
    ) -> tuple[Path, dict]:
        root = self.root / run
        rep = api.create_proc_world(
            root, world, bundle, reason="t", sched_preset=sched_preset
        )
        return root, rep

    def staged(self, root: Path, world: str, proc: str) -> Path:
        return root / "state" / world / "procedures" / proc

    def guarded_round(self, root: Path, key: str, fn):
        """Run fn(); on a torn-ledger-tail landing (L4, disk-loss),
        restore the pre-round ledger backup and run fn() once more
        (the documented disk-loss procedure). Returns (result, note)
        where note is None or "L4-restored"."""
        backup = self.root / f"ledger-backup-{key}.jsonl"
        shutil.copy(root / "ledger.jsonl", backup)
        try:
            return fn(), None
        except (RuntimeError, json.JSONDecodeError) as exc:
            if isinstance(exc, RuntimeError) and "disk-loss" not in str(exc):
                raise
            # Restore the pre-round state: ledger bytes + removal of
            # the wiped attempt's scratch (redo reuses the attempt
            # path; collected artifacts/RESULT overwrite idempotently).
            shutil.copy(backup, root / "ledger.jsonl")
            shutil.rmtree(root / "state" / "proc-scratch" / key, ignore_errors=True)
            return fn(), "L4-restored"


class TestProcAdvertise(Base):
    """Creation-fixed tables + advertise-time validation (A2/A7/A8)."""

    def test_create_pins_table(self):
        steps = [c_step("one"), c_step("two")]
        files = {"prog.py": "print('p')\n"}
        bdir = self.bundle("thing", steps, files)
        root, rep = self.create("r1", "W1", bdir)
        staged = self.staged(root, "W1", "thing")
        self.assertTrue((staged / "MANIFEST.json").is_file())
        self.assertTrue((staged / "prog.py").is_file())
        # table pinned in the ledger create payload
        creates = [
            e["payload"] for e in ledger_lines(root) if e.get("kind") == "create"
        ]
        self.assertEqual(len(creates), 1)
        table = creates[0]["procedures"]
        self.assertEqual(len(table), 1)
        staged_manifest = json.loads(
            (staged / "MANIFEST.json").read_text(encoding="utf-8")
        )
        expect_sha = hashlib.sha256(
            PROC.canonical_manifest_bytes(staged_manifest)
        ).hexdigest()
        self.assertEqual(table[0]["bundle_sha256"], expect_sha)
        self.assertEqual(table[0]["name"], "thing")
        self.assertEqual(table[0]["steps"], ["one", "two"])
        self.assertEqual(rep["bundle_sha256"], expect_sha)
        # world live + funded + active; specs carry the table
        host, _ = api.open_run(root)
        self.assertEqual(host.worlds["W1"].lifecycle, "active")
        self.assertEqual(host.holdings["W1"], dict(PROC.PROC_GRANT_LIMITS))
        self.assertEqual(host.worlds["W1"].procedures, table)
        specs = json.loads((root / "worlds.json").read_text(encoding="utf-8"))
        self.assertEqual(specs[0]["procedures"], table)
        self.assertTrue(host.verify_conservation()["ok"])

    def test_reopen_table_mismatch_refuses(self):
        bdir = self.bundle("thing", [c_step("one")])
        root, rep = self.create("r1", "W1", bdir)
        specs = json.loads((root / "worlds.json").read_text(encoding="utf-8"))
        specs[0]["procedures"][0]["bundle_sha256"] = "0" * 64
        (root / "worlds.json").write_text(
            json.dumps(specs, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with self.assertRaises(ContractViolation):
            api.open_run(root)
        denies = [e for e in ledger_lines(root) if e.get("kind") == "deny"]
        self.assertTrue(
            any("procedures" in d["payload"].get("reason", "") for d in denies)
        )

    def test_advertise_validation_matrix(self):
        good_files = {"a.py": "print(1)\n"}
        good_steps = [c_step("s1")]

        def raw(manifest=None, files="good", name="m"):
            f = dict(good_files) if files == "good" else dict(files)
            if manifest == "good":
                m = {
                    "files": {
                        k: hashlib.sha256(v.encode()).hexdigest()
                        for k, v in good_files.items()
                    },
                    "steps": copy.deepcopy(good_steps),
                }
            else:
                m = manifest
            bdir = self.root / "bundles" / name
            if bdir.exists():
                shutil.rmtree(bdir)
            bdir.mkdir(parents=True)
            for rel, body in f.items():
                dest = bdir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(body.encode())
            if m == {}:
                pass  # missing MANIFEST case: write nothing
            elif isinstance(m, str):
                (bdir / "MANIFEST.json").write_text(m)
            elif m is not None:
                (bdir / "MANIFEST.json").write_text(json.dumps(m))
            return bdir

        h = hashlib.sha256(b"print(1)\n").hexdigest()
        gs = lambda: copy.deepcopy(good_steps)  # noqa: E731
        cases = [
            ("missing-manifest", {}, {}),
            ("unparseable", "{nope", {}),
            ("not-object", [], {}),
            ("files-not-object", {"files": [], "steps": gs()}, {}),
            ("bad-relpath", {"files": {"/abs": h}, "steps": []}, {}),
            ("dotdot-relpath", {"files": {"a/../../x": h}, "steps": []}, {}),
            ("bad-hex", {"files": {"a.py": "zzz"}, "steps": []}, {}),
            ("steps-not-list", {"files": {}, "steps": {}}, {}),
            ("step-not-object", {"files": {}, "steps": ["s"]}, {}),
            (
                "step-bad-name",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "a/b",
                            "argv": ["python3"],
                            "declared_outputs": [],
                            "timeout_s": 1,
                        }
                    ],
                },
                {},
            ),
            ("step-dup-name", {"files": {}, "steps": [c_step("d"), c_step("d")]}, {}),
            (
                "argv-not-list",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "s",
                            "argv": "python3 x",
                            "declared_outputs": [],
                            "timeout_s": 1,
                        }
                    ],
                },
                {},
            ),
            (
                "argv-empty",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "s",
                            "argv": [],
                            "declared_outputs": [],
                            "timeout_s": 1,
                        }
                    ],
                },
                {},
            ),
            (
                "argv-nonstr",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "s",
                            "argv": [1],
                            "declared_outputs": [],
                            "timeout_s": 1,
                        }
                    ],
                },
                {},
            ),
            (
                "outputs-not-list",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "s",
                            "argv": ["python3"],
                            "declared_outputs": "o",
                            "timeout_s": 1,
                        }
                    ],
                },
                {},
            ),
            (
                "output-abs",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "s",
                            "argv": ["python3"],
                            "declared_outputs": ["/x"],
                            "timeout_s": 1,
                        }
                    ],
                },
                {},
            ),
            (
                "timeout-zero",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "s",
                            "argv": ["python3"],
                            "declared_outputs": [],
                            "timeout_s": 0,
                        }
                    ],
                },
                {},
            ),
            (
                "timeout-over",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "s",
                            "argv": ["python3"],
                            "declared_outputs": [],
                            "timeout_s": 601,
                        }
                    ],
                },
                {},
            ),
            (
                "timeout-nonnumeric",
                {
                    "files": {},
                    "steps": [
                        {
                            "step": "s",
                            "argv": ["python3"],
                            "declared_outputs": [],
                            "timeout_s": "60",
                        }
                    ],
                },
                {},
            ),
            (
                "env-extra-pinned",
                {"files": {}, "steps": [c_step("s", env_extra={"PATH": "/x"})]},
                {},
            ),
            (
                "env-extra-proxy",
                {"files": {}, "steps": [c_step("s", env_extra={"http_proxy": "x"})]},
                {},
            ),
            ("python-pin", {"files": {}, "steps": [], "python": "elsewhere"}, {}),
            ("unpinned-extra", "good", {"a.py": "print(1)\n", "zzz.py": "x"}),
            (
                "missing-pinned",
                {"files": {"a.py": h, "gone.py": h}, "steps": []},
                {"a.py": "print(1)\n"},
            ),
            (
                "file-hash-mismatch",
                {"files": {"a.py": "0" * 64}, "steps": []},
                {"a.py": "print(1)\n"},
            ),
        ]
        n = 0
        for label, manifest, files in cases:
            with self.subTest(label):
                bdir = raw(manifest, files, f"m-{label}")
                root = self.root / f"adv-{label}"
                with self.assertRaises(ValueError, msg=label):
                    api.create_proc_world(root, "W", bdir, reason="t")
                if (root / "ledger.jsonl").exists():
                    kinds = [e.get("kind") for e in ledger_lines(root)]
                    self.assertNotIn("create", kinds, label)
                    self.assertNotIn("proc_begin", kinds, label)
                n += 1
        self.assertEqual(n, len(cases))
        # symlink in bundle refused
        bdir = self.root / "bundles" / "linky"
        bdir.mkdir(parents=True)
        (bdir / "real.py").write_bytes(b"x")
        try:
            os.symlink("real.py", bdir / "alias.py")
        except OSError:
            self.skipTest("symlinks unavailable")
        h2 = hashlib.sha256(b"x").hexdigest()
        (bdir / "MANIFEST.json").write_text(
            json.dumps({"files": {"real.py": h2, "alias.py": h2}, "steps": []})
        )
        with self.assertRaises(ValueError):
            api.create_proc_world(self.root / "adv-link", "W", bdir, reason="t")
        # bad procedure name (bundle dir) refused pre-stage
        bdir = self.bundle("ok", [c_step("s")])
        evil = self.root / "bundles" / "bad name"
        shutil.copytree(bdir, evil)
        with self.assertRaises(ValueError):
            api.create_proc_world(self.root / "adv-name", "W", evil, reason="t")
        # duplicate world refused with no staged side effects
        root = self.root / "adv-dup"
        api.create_proc_world(root, "W", bdir, reason="t")
        with self.assertRaises(ContractViolation):
            api.create_proc_world(root, "W", bdir, reason="t2")
        # unknown sched preset refused
        with self.assertRaises(ValueError):
            api.create_proc_world(
                self.root / "adv-preset", "W2", bdir, reason="t", sched_preset="Z"
            )

    def test_interrupted_proc_birth_completes_with_proc_grant(self):
        bdir = self.bundle("thing", [c_step("s")])
        root = self.root / "birth"
        api._init_proc_root(root)
        # kill after create (append 2: reopen=1, create=2) via CLI
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="2"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        host, _ = api.open_run(root)
        self.assertEqual(host.worlds["W1"].lifecycle, "proposed")
        rec = api.recover_op(root)
        self.assertEqual(rec["births_completed"], ["W1"])
        host, _ = api.open_run(root)
        self.assertEqual(host.worlds["W1"].lifecycle, "active")
        self.assertEqual(host.holdings["W1"], dict(PROC.PROC_GRANT_LIMITS))
        self.assertTrue(host.verify_conservation()["ok"])
        # the world runs procedures after birth completion
        out = api.run_procedure(root, "W1", "thing", "K1")
        self.assertEqual(out["executed"], ["s"])

    def test_create_prespec_kill_repairs_spec_with_table(self):
        bdir = self.bundle("thing", [c_step("s")])
        root = self.root / "prespec"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
            env=child_env(SUBSTRATE_CRASH_AT="api:create-proc-world:pre-spec"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        specs = json.loads((root / "worlds.json").read_text(encoding="utf-8"))
        self.assertEqual(specs, [])
        rec = api.recover_op(root)
        self.assertEqual(rec["specs_repaired"], ["W1"])
        specs = json.loads((root / "worlds.json").read_text(encoding="utf-8"))
        self.assertEqual(len(specs[0]["procedures"]), 1)
        host, _ = api.open_run(root)  # reopen verifies the table
        self.assertEqual(host.worlds["W1"].lifecycle, "active")

    def test_proc_birth_on_sched_root_refuses_for_grant(self):
        # sched roots hold too little for the minutes-adequate proc
        # grant: loud refusal, and recovery refuses funding too.
        bdir = self.bundle("thing", [c_step("s")])
        root = self.root / "schedroot"
        api.init_run(root)
        with self.assertRaises(ContractViolation):
            api.create_proc_world(root, "W1", bdir, reason="t")
        host, _ = api.open_run(root)
        self.assertEqual(host.worlds["W1"].lifecycle, "proposed")
        with self.assertRaises(ContractViolation):
            api.recover_op(root)


class TestProcGates(Base):
    """Service honesty: table/collision/exit gates + hybrid worlds (A3)."""

    def test_unknown_procedure_zero_spawn(self):
        bdir = self.bundle("thing", [c_step("s")])
        root, _ = self.create("r1", "W1", bdir)
        with self.assertRaises(ContractViolation):
            api.run_procedure(root, "W1", "nope", "K1")
        self.assertEqual(proc_begins_of(root), [])
        self.assertEqual(proc_invokes(root), [])
        self.assertFalse((root / "state" / "proc-scratch").exists())
        denies = [e for e in ledger_lines(root) if e.get("kind") == "deny"]
        self.assertTrue(denies)

    def test_forged_bundle_pair_gate(self):
        bdir = self.bundle("thing", [c_step("s")])
        root, rep = self.create("r1", "W1", bdir)
        host, _ = api.open_run(root)
        forged = "f" * 64
        assert forged != rep["bundle_sha256"]
        with self.assertRaises(ContractViolation):
            PROC.run_step(host, root, "W1", "thing", forged, "s", "K1")
        self.assertEqual(proc_begins_of(root), [])
        host, _ = api.open_run(root)
        with self.assertRaises(ValueError):
            PROC.run_step(
                host, root, "W1", "thing", rep["bundle_sha256"], "wrong-step", "K1"
            )

    def test_collision_across_bundles(self):
        b1 = self.bundle("aaa", [c_step("s")], {"tag.py": "W1"})
        b2 = self.bundle("bbb", [c_step("s")], {"tag.py": "W2"})
        root = self.root / "r1"
        r1 = api.create_proc_world(root, "W1", b1, reason="t")
        r2 = api.create_proc_world(root, "W2", b2, reason="t")
        self.assertNotEqual(r1["bundle_sha256"], r2["bundle_sha256"])
        out = api.run_procedure(root, "W1", "aaa", "K")
        self.assertEqual(out["executed"], ["s"])
        with self.assertRaises(ValueError) as ctx:
            api.run_procedure(root, "W2", "bbb", "K")
        self.assertIn("collision", str(ctx.exception))
        self.assertEqual(
            proc_begins_of(root, "K"),
            [
                b
                for b in proc_begins_of(root, "K")
                if b["bundle_sha256"] == r1["bundle_sha256"]
            ],
        )
        # same key + same bundle re-invokes skip; failure retries run
        out = api.run_procedure(root, "W1", "aaa", "K")
        self.assertEqual(out["skipped"], ["s"])
        self.assertEqual(out["executed"], [])

    def test_failure_never_skips(self):
        fail = {
            "step": "s",
            "argv": ["python3", "-c", "import sys; sys.exit(3)"],
            "declared_outputs": [],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [fail])
        root, _ = self.create("r1", "W1", bdir)
        with self.assertRaises(RuntimeError):
            api.run_procedure(root, "W1", "thing", "K")
        with self.assertRaises(RuntimeError):
            api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(len(proc_begins_of(root, "K")), 2)
        self.assertEqual(len(proc_invokes(root, "K", errors=True)), 2)
        self.assertEqual(proc_invokes(root, "K", errors=False), [])

    def test_nonzero_exit_never_result_ref(self):
        fail = {
            "step": "s",
            "argv": ["python3", "-c", "import sys; sys.exit(7)"],
            "declared_outputs": [],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [fail])
        root, _ = self.create("r1", "W1", bdir)
        with self.assertRaises(RuntimeError):
            api.run_procedure(root, "W1", "thing", "K")
        errs = proc_invokes(root, "K", errors=True)
        self.assertEqual(len(errs), 1)
        self.assertNotIn("result_ref", errs[0])
        self.assertIn("exited 7", errs[0]["error"])
        self.assertEqual(errs[0]["proc"]["exit_code"], 7)
        self.assertFalse((root / "artifacts" / "proc-K" / "s" / "RESULT.json").exists())

    def test_direct_invoke_without_envelope_denied(self):
        bdir = self.bundle("thing", [c_step("s")])
        root, _ = self.create("r1", "W1", bdir)
        host, _ = api.open_run(root)
        aref = host.store_args("W1", "direct", {"task_id": "t", "step": "s"})
        with self.assertRaises(ContractViolation) as ctx:
            host.invoke("W1", "W1", "proc.exec", "v1", aref, lambda: "x")
        self.assertIn("envelope", str(ctx.exception))

    def test_gates_before_spawn(self):
        bdir = self.bundle("thing", [c_step("s")])
        # sched world (no proc.exec): "does not advertise", zero spawn
        sroot = self.root / "sched"
        api.init_run(sroot)
        host, _ = api.open_run(sroot)
        with self.assertRaises(ContractViolation) as ctx:
            PROC.run_step(host, sroot, "SC-L", "thing", "0" * 64, "s", "K")
        self.assertIn("does not advertise", str(ctx.exception))
        self.assertEqual(proc_begins_of(sroot), [])
        # suspended proc world: not-active deny, zero spawn
        root, _ = self.create("r1", "W1", bdir)
        host, _ = api.open_run(root)
        host.suspend("W1", "host", reason="t", pending_effects=[])
        with self.assertRaises(ContractViolation) as ctx:
            PROC.run_procedure(host, root, "W1", "thing", "K")
        self.assertIn("not active", str(ctx.exception))
        self.assertEqual(proc_begins_of(root), [])
        host.reattach("W1", "host", reason="t")
        # revoked proc.exec: lacks-authority deny, zero spawn
        host, _ = api.open_run(root)
        api.revoke_op(root, "W1", "proc.exec", "v1", reason="t")
        host, _ = api.open_run(root)
        with self.assertRaises(ContractViolation) as ctx:
            PROC.run_procedure(host, root, "W1", "thing", "K")
        self.assertIn("lacks", str(ctx.exception))
        self.assertEqual(proc_begins_of(root), [])

    def test_hybrid_world_both_matchers(self):
        bdir = self.bundle("thing", [c_step("s")])
        root, rep = self.create("rhyb", "W1", bdir, sched_preset="L")
        host, _ = api.open_run(root)
        caps = {c.name + "@" + c.version for c in host.worlds["W1"].capabilities}
        self.assertIn("proc.exec@v1", caps)
        self.assertIn("sched.formulate@1.0", caps)
        # one sched plan step via the C1–C3 matcher
        task = copy.deepcopy(FI.S1)
        ctx = LaneCtx("central", Coordinator(), ChannelRegistry())
        plan = [build_formulate(host, task, "W1", "v1", ctx)]
        m = execute_plan(host, plan)
        self.assertEqual(m["re_executed_invokes"], 0)
        self.assertIn(("sched.formulate", "S1", "formulate@v1"), scan_succeeded(host))
        # one procedure run via the proc matcher
        out = PROC.run_procedure(host, root, "W1", "thing", "K")
        self.assertEqual(out["executed"], ["s"])
        # both re-run cleanly: every completed step skips
        m2 = execute_plan(host, plan)
        self.assertEqual(m2["executed"], [])
        out2 = PROC.run_procedure(host, root, "W1", "thing", "K")
        self.assertEqual(out2["skipped"], ["s"])
        self.assertEqual(out2["executed"], [])
        self.assertTrue(host.verify_conservation()["ok"])


class TestProcHonesty(Base):
    """Declaration honesty: ledger names match executed bytes (A2)."""

    def test_ledger_matches_bytes(self):
        prog = (
            "import sys, hashlib\n"
            "data = open(sys.argv[1], 'rb').read()\n"
            "open('digest.txt', 'w').write(hashlib.sha256(data)."
            "hexdigest())\n"
        )
        steps = [
            {
                "step": "hash",
                "argv": ["python3", "inputs/prog.py", "inputs/blob.bin"],
                "declared_outputs": ["digest.txt"],
                "timeout_s": 60,
            }
        ]
        files = {"prog.py": prog, "blob.bin": b"blob-bytes-v1"}
        bdir = self.bundle("hasher", steps, files)
        root, rep = self.create("r1", "W1", bdir)
        staged = self.staged(root, "W1", "hasher")
        inputs = {"prog.py": staged / "prog.py", "blob.bin": staged / "blob.bin"}
        out = api.run_procedure(root, "W1", "hasher", "K1", inputs)
        self.assertEqual(out["executed"], ["hash"])
        # create pin == recomputed staged hash
        creates = [
            e["payload"] for e in ledger_lines(root) if e.get("kind") == "create"
        ]
        staged_manifest = json.loads(
            (staged / "MANIFEST.json").read_text(encoding="utf-8")
        )
        expect = hashlib.sha256(
            PROC.canonical_manifest_bytes(staged_manifest)
        ).hexdigest()
        self.assertEqual(creates[0]["procedures"][0]["bundle_sha256"], expect)
        # begin pin ∈ table; executed argv == manifest argv
        begins = proc_begins_of(root, "K1")
        self.assertEqual(len(begins), 1)
        table_pins = {t["bundle_sha256"] for t in creates[0]["procedures"]}
        self.assertIn(begins[0]["bundle_sha256"], table_pins)
        manifest_argv = steps[0]["argv"]
        self.assertEqual(
            begins[0]["argv_sha256"],
            hashlib.sha256(
                json.dumps(manifest_argv, sort_keys=True).encode()
            ).hexdigest(),
        )
        # interpreter recorded == interpreter that ran
        recorded = begins[0]["interpreter"]
        self.assertTrue(recorded)
        self.assertEqual(begins[0]["interpreter_version"], PROC.probe_version(recorded))
        self.assertNotEqual(begins[0]["interpreter_version"], "")
        # executed input bytes == staged pinned bytes
        for name in ("prog.py", "blob.bin"):
            self.assertEqual(
                begins[0]["input_hashes"][name],
                hashlib.sha256((staged / name).read_bytes()).hexdigest(),
            )
        # and the digest output matches the pinned blob
        digest = (root / "artifacts" / "proc-K1" / "hash" / "digest.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(digest, hashlib.sha256(b"blob-bytes-v1").hexdigest())

    def test_staged_tamper_refuses_pre_run(self):
        variants = ["modify", "add", "delete", "manifest"]
        for variant in variants:
            with self.subTest(variant):
                bdir = self.bundle(
                    f"thing-{variant}", [c_step("s")], {"a.py": "print(1)\n"}
                )
                root, _ = self.create(f"r-{variant}", "W1", bdir)
                staged = self.staged(root, "W1", f"thing-{variant}")
                if variant == "modify":
                    (staged / "a.py").write_bytes(b"print(2)\n")
                elif variant == "add":
                    (staged / "evil.py").write_bytes(b"x")
                elif variant == "delete":
                    (staged / "a.py").unlink()
                else:
                    man = json.loads(
                        (staged / "MANIFEST.json").read_text(encoding="utf-8")
                    )
                    man["steps"][0]["timeout_s"] = 59
                    (staged / "MANIFEST.json").write_text(json.dumps(man))
                with self.assertRaises(ValueError):
                    api.run_procedure(root, "W1", f"thing-{variant}", "K")
                # error-invoke recorded, zero spawn (no proc_begin)
                self.assertEqual(proc_begins_of(root), [])
                errs = proc_invokes(root, "K", errors=True)
                self.assertEqual(len(errs), 1)
                self.assertIn("pre-verify", errs[0]["error"])


class TestProcPermissions(Base):
    """P1–P15 enforcement + escape refusals + non-claim legs (A4)."""

    def test_p1_no_shell(self):
        # AST sweep: zero `shell=True` anywhere; every Popen in the
        # executor passes shell=False explicitly; no string command.
        for py in sorted(HERE.glob("*.py")):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for kw in node.keywords:
                    if kw.arg == "shell":
                        self.assertIsInstance(
                            kw.value, ast.Constant, f"{py.name}:{node.lineno}"
                        )
                        self.assertIs(kw.value.value, False, f"{py.name}:{node.lineno}")
        tree = ast.parse((PKG / "host" / "procedure.py").read_text(encoding="utf-8"))

        def _is_popen(node):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "Popen":
                return True
            return isinstance(f, ast.Attribute) and f.attr == "Popen"

        popens = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _is_popen(n)]
        self.assertTrue(popens)
        for node in popens:
            kws = {kw.arg: kw.value for kw in node.keywords}
            self.assertIn("shell", kws)
            self.assertIs(kws["shell"].value, False)
            first = node.args[0]
            self.assertNotIsInstance(
                first, ast.Constant, "string command has no code path"
            )

    def test_p2_scratch_cwd(self):
        code = "import os; open('where.txt','w').write(os.getcwd())"
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": ["where.txt"],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        api.run_procedure(root, "W1", "thing", "K")
        begin = proc_begins_of(root, "K")[0]
        where = (root / "artifacts" / "proc-K" / "s" / "where.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(where, begin["scratch"])
        self.assertIn("proc-scratch", begin["scratch"])
        self.assertTrue(Path(begin["scratch"]).is_dir())

    def test_p3_allowlist_env(self):
        if os.name != "posix" or shutil.which("/usr/bin/env") is None:
            self.skipTest("Linux-authoritative env-exactness leg")
        # /usr/bin/env dumps EXACTLY what the host passed (a python
        # child would add LC_CTYPE=C.UTF-8 itself via PEP 538/540
        # locale coercion — see the companion leg below).
        step = {
            "step": "s",
            "argv": ["/usr/bin/env"],
            "declared_outputs": [],
            "timeout_s": 60,
            "env_extra": {"THING_MODE": "on"},
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        api.run_procedure(root, "W1", "thing", "K")
        begin = proc_begins_of(root, "K")[0]
        dumped = (root / "artifacts" / "proc-K" / "s" / "stdout.log").read_text(
            encoding="utf-8"
        )
        env = dict(line.split("=", 1) for line in dumped.splitlines() if "=" in line)
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(env["HOME"], begin["scratch"])
        self.assertEqual(env["TMPDIR"], begin["scratch"])
        self.assertEqual(env["THING_MODE"], "on")
        self.assertNotIn("PYTHONPATH", env)
        self.assertFalse([k for k in env if k.upper().endswith("_PROXY")])
        self.assertEqual(sorted(env), begin["env_keys"])
        self.assertIn("PATH", env)

    def test_p3_python_child_locale_delta(self):
        # A python child exports LC_CTYPE=C.UTF-8 into its OWN
        # environ at startup (PEP 538/540) when the locale is
        # unset — the host passes exactly env_keys; the delta, when
        # present, is exactly this runtime addition.
        code = (
            "import os, json; open('env.json','w').write("
            "json.dumps(dict(os.environ), sort_keys=True))"
        )
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": ["env.json"],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        api.run_procedure(root, "W1", "thing", "K")
        begin = proc_begins_of(root, "K")[0]
        env = json.loads(
            (root / "artifacts" / "proc-K" / "s" / "env.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            set(env) - set(begin["env_keys"]),
            set() if "LC_CTYPE" not in env else {"LC_CTYPE"},
        )
        for key in begin["env_keys"]:
            self.assertIn(key, env)

    def test_p4_stdin_devnull(self):
        code = (
            "import sys; data = sys.stdin.buffer.read(); "
            "open('stdin.txt','w').write(repr(data))"
        )
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": ["stdin.txt"],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        api.run_procedure(root, "W1", "thing", "K")
        got = (root / "artifacts" / "proc-K" / "s" / "stdin.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(got, "b''")

    def test_p5_capture_and_caps(self):
        big = 2 * 1024 * 1024
        code = (
            f"import sys; sys.stdout.buffer.write(b'A'*{big}); "
            f"sys.stdout.buffer.flush(); "
            f"sys.stderr.buffer.write(b'B'*{big}); print('tail')"
        )
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": [],
            "timeout_s": 120,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        api.run_procedure(root, "W1", "thing", "K")
        ok = proc_invokes(root, "K", errors=False)[0]
        proc = ok["proc"]
        self.assertTrue(proc["truncated_stdout"])
        self.assertTrue(proc["truncated_stderr"])
        self.assertEqual(proc["stdout_bytes"], PROC.STDOUT_CAP)
        self.assertEqual(proc["stderr_bytes"], PROC.STDERR_CAP)
        out = (root / "artifacts" / "proc-K" / "s" / "stdout.log").read_bytes()
        err = (root / "artifacts" / "proc-K" / "s" / "stderr.log").read_bytes()
        self.assertEqual(len(out), PROC.STDOUT_CAP)
        self.assertEqual(hashlib.sha256(out).hexdigest(), proc["stdout_sha256"])
        self.assertEqual(hashlib.sha256(err).hexdigest(), proc["stderr_sha256"])
        res = json.loads(Path(ok["result_ref"]).read_text(encoding="utf-8"))
        self.assertGreater(res["stdout_total_bytes"], PROC.STDOUT_CAP)
        self.assertEqual(res["caps"]["stdout"], PROC.STDOUT_CAP)

    def test_p6_timeout_kill(self):
        step = {
            "step": "s",
            "argv": ["python3", "-c", "import time; time.sleep(60)"],
            "declared_outputs": [],
            "timeout_s": 2,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        t0 = time.monotonic()
        with self.assertRaises(TimeoutError):
            api.run_procedure(root, "W1", "thing", "K")
        wall = time.monotonic() - t0
        errs = proc_invokes(root, "K", errors=True)
        self.assertEqual(len(errs), 1)
        self.assertIn("timeout", errs[0]["error"])
        self.assertNotIn("result_ref", errs[0])
        proc = errs[0]["proc"]
        self.assertTrue(proc["timed_out"])
        self.assertLess(proc["elapsed_s"], 2 + 60)  # guard-only bound
        self.assertGreater(proc["elapsed_s"], 0)
        self.assertLess(wall, 2 + 120)  # guard-only bound
        if os.name == "posix":
            self.assertEqual(proc["exit_code"], -9)
        # failures burn nothing: retry with the same key is attempted
        host, _ = api.open_run(root)
        self.assertEqual(host.consumed["W1"]["max_invocations"], 0)
        with self.assertRaises(TimeoutError):
            api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(len(proc_begins_of(root, "K")), 2)

    def test_p7_interpreter_pin(self):
        bdir = self.bundle("thing", [c_step("s")])
        root, _ = self.create("r1", "W1", bdir)
        out = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(out["executed"], ["s"])
        begin = proc_begins_of(root, "K")[0]
        expect = shutil.which("python3", path=os.environ.get("PATH", ""))
        self.assertEqual(begin["interpreter"], expect)
        # PROC_PY override must match: mismatch refuses pre-spawn
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "thing",
            "--key",
            "K2",
            env=child_env(PROC_PY="/bin/echo-nope"),
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("pin mismatch", proc.stderr)
        self.assertEqual(proc_begins_of(root, "K2"), [])
        # PROC_PY matching the resolution runs
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "thing",
            "--key",
            "K3",
            env=child_env(PROC_PY=expect),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(proc_begins_of(root, "K3")), 1)

    def test_p8_post_run_tamper(self):
        # the child tampers its own staged bundle mid-run
        code = (
            "import pathlib; "
            "p = pathlib.Path('../../../W1/procedures/thing/a.py'); "
            "p.write_text('tampered\\n')"
        )
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": [],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step], {"a.py": "print(1)\n"})
        root, _ = self.create("r1", "W1", bdir)
        with self.assertRaises(ValueError) as ctx:
            api.run_procedure(root, "W1", "thing", "K")
        self.assertIn("post-verify", str(ctx.exception))
        errs = proc_invokes(root, "K", errors=True)
        self.assertEqual(len(errs), 1)
        self.assertNotIn("result_ref", errs[0])
        self.assertFalse((root / "artifacts" / "proc-K" / "s" / "RESULT.json").exists())

    def test_p9_outside_scratch_write(self):
        code = "open('../../../sneak.txt','w').write('sneak')"
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": [],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        marker = root / "state" / "marker.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            api.run_procedure(root, "W1", "thing", "K")
        self.assertIn("sneak.txt", str(ctx.exception))
        errs = proc_invokes(root, "K", errors=True)
        self.assertEqual(len(errs), 1)
        self.assertTrue(
            any("sneak.txt" in d for d in errs[0]["proc"]["outside_writes"])
        )
        self.assertNotIn("result_ref", errs[0])

    def test_p9_deletion_detected(self):
        code = "import os; os.remove('../../../marker.txt')"
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": [],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        (root / "state" / "marker.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            api.run_procedure(root, "W1", "thing", "K")
        self.assertIn("marker.txt", str(ctx.exception))

    def test_p9_same_key_prior_attempt_tolerated(self):
        # Dead-attempt scratch of the SAME key is excluded from P9: a
        # SIGKILL mid-step can orphan the detached child, which may
        # complete its writes into the dead attempt after the re-run's
        # before-snapshot (loop-test red -> key-subtree exclusion).
        code = "open('../o-attempt1/planted.txt','w').write('late')"
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": [],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        dead = root / "state" / "proc-scratch" / "K" / "o-attempt1"
        dead.mkdir(parents=True)
        rep = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(rep["executed"], ["s"])
        self.assertTrue((dead / "planted.txt").is_file())
        ok = proc_invokes(root, "K", errors=False)
        self.assertEqual(len(ok), 1)

    def test_p9_cross_key_scratch_still_guarded(self):
        # Tightness pin for the key-subtree exclusion: a step writing
        # into ANOTHER key's scratch still trips P9 (audit gap note).
        code = "open('../../K2/s-attempt1/planted.txt','w').write('x')"
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": [],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        other = root / "state" / "proc-scratch" / "K2" / "s-attempt1"
        other.mkdir(parents=True)
        with self.assertRaises(ValueError) as ctx:
            api.run_procedure(root, "W1", "thing", "K")
        self.assertIn("planted.txt", str(ctx.exception))

    def test_symlink_discipline(self):
        try:
            os.symlink("t", self.root / "probe-link")
            (self.root / "probe-link").unlink()
        except OSError:
            self.skipTest("symlinks unavailable")
        # undeclared symlink: accounted (listed), never followed
        code = (
            "import os; os.symlink('/etc/hostname', 'evil-link'); "
            "open('ok.txt','w').write('ok')"
        )
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": ["ok.txt"],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        api.run_procedure(root, "W1", "thing", "K")
        ok = proc_invokes(root, "K", errors=False)[0]
        und = {d["relpath"] for d in ok["proc"]["undeclared_present"]}
        self.assertIn("evil-link", und)
        self.assertFalse((root / "artifacts" / "proc-K" / "s" / "evil-link").exists())
        # declared-output symlink: loud refusal
        code2 = "import os; os.symlink('/etc/hostname', 'out.txt')"
        step2 = {
            "step": "t",
            "argv": ["python3", "-c", code2],
            "declared_outputs": ["out.txt"],
            "timeout_s": 60,
        }
        bdir2 = self.bundle("thing2", [step2])
        root2, _ = self.create("r2", "W2", bdir2)
        with self.assertRaises(ValueError):
            api.run_procedure(root2, "W2", "thing2", "K")
        self.assertEqual(proc_invokes(root2, "K", errors=False), [])

    def test_p11_outside_state_contractual_not_prevented(self):
        # P11 is CONTRACTUAL: the host neither prevents nor claims to
        # prevent writes outside the state dir. This leg pins the
        # non-claim behaviorally (the step succeeds; the file lands).
        probe = self.root / "p11-probe.txt"
        code = f"open({str(probe)!r},'w').write('outside')"
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": [],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        out = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(out["executed"], ["s"])
        self.assertEqual(probe.read_text(encoding="utf-8"), "outside")
        ok = proc_invokes(root, "K", errors=False)[0]
        self.assertEqual(ok["proc"]["outside_writes"], [])

    def test_grant_exactness_and_exhaustion(self):
        bdir = self.bundle("thing", [c_step("a"), c_step("b")])
        root, _ = self.create("r1", "W1", bdir)
        out = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(out["executed"], ["a", "b"])
        host, _ = api.open_run(root)
        oks = proc_invokes(root, "K", errors=False)
        total = sum(p["proc"]["elapsed_s"] for p in oks)
        consumed = host.consumed["W1"]
        self.assertEqual(consumed["max_invocations"], 2)
        self.assertEqual(consumed["max_time_s"], total)
        self.assertEqual(consumed["max_cost_usd"], 0.0)
        # exhaustion: with zero invocations left, the step runs but
        # the standard grant-exceeded deny fires (nothing consumed,
        # no invoke, no DONE — a terminal honest refusal).
        host.consume("W1", invocations=98, evidence_ref="test-drain")
        self.assertEqual(host.holdings["W1"]["max_invocations"], 0)
        with self.assertRaises(ContractViolation) as ctx:
            PROC.run_procedure(host, root, "W1", "thing", "K2")
        self.assertIn("grant exceeded", str(ctx.exception))
        self.assertEqual(len(proc_begins_of(root, "K2")), 1)
        self.assertEqual(proc_invokes(root, "K2"), [])
        denies = [e["payload"] for e in ledger_lines(root) if e.get("kind") == "deny"]
        self.assertTrue(
            any("would exceed grant" in d.get("reason", "") for d in denies)
        )
        begin = proc_begins_of(root, "K2")[0]
        self.assertFalse((Path(begin["scratch"]) / "DONE.json").exists())


PROC_KEYS = {
    "procedure",
    "bundle_sha256",
    "idem_key",
    "step",
    "attempt",
    "exit_code",
    "stdout_sha256",
    "stdout_bytes",
    "stderr_sha256",
    "stderr_bytes",
    "truncated_stdout",
    "truncated_stderr",
    "artifacts",
    "undeclared_present",
    "outside_writes",
    "elapsed_s",
    "timed_out",
    "recovered",
}


class TestProcAccountability(Base):
    """Record completeness + hash recomputation (A5)."""

    def test_success_carries_all_fields_recomputable(self):
        code = (
            "open('a.txt','w').write('A'*100); "
            "open('sub.txt','w').write('S'); "
            "open('extra.txt','w').write('undec'); "
            "print('hello-out'); "
            "import sys; sys.stderr.write('hello-err')"
        )
        step = {
            "step": "s",
            "argv": ["python3", "-c", code],
            "declared_outputs": ["a.txt", "sub.txt"],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, rep = self.create("r1", "W1", bdir)
        out = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(out["executed"], ["s"])
        oks = proc_invokes(root, "K", errors=False)
        self.assertEqual(len(oks), 1)
        proc = oks[0]["proc"]
        self.assertEqual(set(proc), PROC_KEYS)
        self.assertEqual(proc["exit_code"], 0)
        self.assertFalse(proc["timed_out"])
        self.assertFalse(proc["recovered"])
        self.assertEqual(proc["outside_writes"], [])
        self.assertEqual(proc["attempt"], 1)
        dest = root / "artifacts" / "proc-K" / "s"
        for art in proc["artifacts"]:
            data = (dest / art["relpath"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), art["sha256"])
            self.assertEqual(len(data), art["bytes"])
        self.assertEqual(
            {a["relpath"] for a in proc["artifacts"]}, {"a.txt", "sub.txt"}
        )
        for stream, cname in (("stdout", "stdout.log"), ("stderr", "stderr.log")):
            data = (dest / cname).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), proc[f"{stream}_sha256"])
            self.assertEqual(len(data), proc[f"{stream}_bytes"])
        und = {d["relpath"]: d["bytes"] for d in proc["undeclared_present"]}
        self.assertEqual(und, {"extra.txt": 5})
        self.assertNotIn("extra.txt", {a["relpath"] for a in proc["artifacts"]})
        # RESULT.json agrees with the ledger entry field for field
        res = json.loads(Path(oks[0]["result_ref"]).read_text(encoding="utf-8"))
        for key in PROC_KEYS:
            self.assertEqual(res[key], proc[key], key)

    def test_inputs_recorded_and_staged(self):
        step = {
            "step": "s",
            "argv": [
                "python3",
                "-c",
                "open('echo.txt','w').write("
                "open('inputs/in.bin','rb').read().decode())",
            ],
            "declared_outputs": ["echo.txt"],
            "timeout_s": 60,
        }
        bdir = self.bundle("thing", [step])
        root, _ = self.create("r1", "W1", bdir)
        blob = self.root / "blob.bin"
        blob.write_bytes(b"payload-42")
        out = api.run_procedure(
            root, "W1", "thing", "K", {"in.bin": blob, "direct.txt": b"direct"}
        )
        self.assertEqual(out["executed"], ["s"])
        begin = proc_begins_of(root, "K")[0]
        self.assertEqual(
            begin["input_hashes"]["in.bin"], hashlib.sha256(b"payload-42").hexdigest()
        )
        self.assertEqual(
            begin["input_hashes"]["direct.txt"], hashlib.sha256(b"direct").hexdigest()
        )
        echo = (root / "artifacts" / "proc-K" / "s" / "echo.txt").read_text(
            encoding="utf-8"
        )
        self.assertEqual(echo, "payload-42")
        # bad inputs refuse without ledger effect
        with self.assertRaises(ValueError):
            api.run_procedure(root, "W1", "thing", "K2", {"../evil": b"x"})
        self.assertEqual(proc_begins_of(root, "K2"), [])
        with self.assertRaises(ValueError):
            api.run_procedure(
                root, "W1", "thing", "K3", {"in.bin": self.root / "missing.bin"}
            )
        self.assertEqual(proc_begins_of(root, "K3"), [])


class TestProcInterruption(Base):
    """L1–L6 matrix: deterministic hooks first (A6)."""

    def _two_step(self, tag="thing"):
        return self.bundle(tag, [c_step("one"), c_step("two")])

    def test_l1_before_begin_no_trace(self):
        bdir = self._two_step()
        root = self.root / "l1"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # kill after append 1 (reopen) of the run process: before
        # the first proc_begin — no trace of the run
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "thing",
            "--key",
            "K",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="1"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        self.assertEqual(proc_begins_of(root), [])
        rec = api.recover_op(root)
        self.assertTrue(rec["proc_nothing_to_do"])
        out = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(out["executed"], ["one", "two"])
        self.assertEqual(out["child_executions"], {"one": 1, "two": 1})

    def test_l1_before_second_begin_partial_skip(self):
        bdir = self._two_step()
        root = self.root / "l1b"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # appends: reopen=1, begin=2, consume=3, invoke=4: kill after
        # 4 lands before step two's begin (L1 for step two)
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "thing",
            "--key",
            "K",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="4"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        self.assertEqual(len(proc_begins_of(root, "K")), 1)
        out = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(out["skipped"], ["one"])
        self.assertEqual(out["executed"], ["two"])
        self.assertEqual(out["re_executed_steps"], [])
        self.assertEqual(out["child_executions"], {"one": 1, "two": 1})

    def test_l2_killed_mid_step_reruns_fresh(self):
        bdir = self._two_step()
        root = self.root / "l2"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # kill after append 2 (step one's begin): L2, no DONE
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "thing",
            "--key",
            "K",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="2"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        begins = proc_begins_of(root, "K")
        self.assertEqual(len(begins), 1)
        stale = Path(begins[0]["scratch"])
        rec = api.recover_op(root)
        self.assertEqual(rec["proc_adopted"], [])
        self.assertEqual(len(rec["proc_rerunnable"]), 1)
        self.assertEqual(rec["proc_rerunnable"][0]["step"], "one")
        out = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(out["executed"], ["one", "two"])
        self.assertEqual(out["re_executed_steps"], ["one"])
        self.assertEqual(out["child_executions"], {"one": 2, "two": 1})
        # fresh scratch; the stale one is kept as evidence, never read
        begins = proc_begins_of(root, "K", "one")
        self.assertEqual(len(begins), 2)
        self.assertNotEqual(begins[0]["scratch"], begins[1]["scratch"])
        self.assertTrue(stale.is_dir())
        host, _ = api.open_run(root)
        self.assertTrue(host.verify_conservation()["ok"])

    def test_l3_done_no_invoke_adopts(self):
        bdir = self._two_step()
        root = self.root / "l3"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "thing",
            "--key",
            "K",
            env=child_env(SUBSTRATE_CRASH_AT="proc:post-done-pre-invoke"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        begins = proc_begins_of(root, "K")
        self.assertEqual(len(begins), 1)
        self.assertTrue((Path(begins[0]["scratch"]) / "DONE.json").is_file())
        self.assertEqual(proc_invokes(root, "K"), [])
        # re-invoke without recover refuses, naming recover
        with self.assertRaises(RuntimeError) as ctx:
            api.run_procedure(root, "W1", "thing", "K")
        self.assertIn("recover", str(ctx.exception))
        rec = api.recover_op(root)
        self.assertEqual(len(rec["proc_adopted"]), 1)
        self.assertEqual(rec["proc_adopted"][0]["step"], "one")
        self.assertEqual(rec["proc_rerunnable"], [])
        oks = proc_invokes(root, "K", errors=False)
        self.assertEqual(len(oks), 1)
        self.assertTrue(oks[0]["proc"]["recovered"])
        self.assertEqual(oks[0]["proc"]["attempt"], 1)
        out = api.run_procedure(root, "W1", "thing", "K")
        self.assertEqual(out["skipped"], ["one"])
        self.assertEqual(out["executed"], ["two"])
        self.assertEqual(out["child_executions"], {"one": 1, "two": 1})
        # the adopted record is complete + recomputable
        res = json.loads(Path(oks[0]["result_ref"]).read_text(encoding="utf-8"))
        for key in PROC_KEYS:
            self.assertEqual(res[key], oks[0]["proc"][key], key)
        host, _ = api.open_run(root)
        self.assertTrue(host.verify_conservation()["ok"])

    def test_l3_adopt_refusal_reruns(self):
        for variant in ("output", "done", "stdio", "bundle"):
            with self.subTest(variant):
                bdir = self.bundle(
                    f"thing-{variant}", [c_step("one")], {"a.py": "print(1)\n"}
                )
                root = self.root / f"l3r-{variant}"
                proc = cli(
                    "ops",
                    "create-proc-world",
                    "--state-dir",
                    str(root),
                    "--world",
                    "W1",
                    "--bundle",
                    str(bdir),
                    "--reason",
                    "t",
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                proc = cli(
                    "ops",
                    "run-procedure",
                    "--state-dir",
                    str(root),
                    "--world",
                    "W1",
                    "--procedure",
                    f"thing-{variant}",
                    "--key",
                    "K",
                    env=child_env(SUBSTRATE_CRASH_AT="proc:post-done-pre-invoke"),
                )
                self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
                begin = proc_begins_of(root, "K")[0]
                scratch = Path(begin["scratch"])
                if variant == "output":
                    (scratch / "out.txt").write_bytes(b"tampered")
                elif variant == "done":
                    (scratch / "DONE.json").write_bytes(b"{broken")
                elif variant == "stdio":
                    (scratch / ".host-stdio" / "stdout.log").write_bytes(b"tampered")
                else:
                    staged = self.staged(root, "W1", f"thing-{variant}")
                    (staged / "a.py").write_bytes(b"tampered\n")
                rec = api.recover_op(root)
                self.assertEqual(rec["proc_adopted"], [], variant)
                self.assertEqual(len(rec["proc_rerunnable"]), 1, variant)
                self.assertIn(
                    "adopt-refused", rec["proc_rerunnable"][0]["reason"], variant
                )
                errs = proc_invokes(root, "K", errors=True)
                self.assertEqual(len(errs), 1, variant)
                if variant == "bundle":
                    # restore the staged bytes so the re-run verifies
                    (self.staged(root, "W1", f"thing-{variant}") / "a.py").write_bytes(
                        b"print(1)\n"
                    )
                out = api.run_procedure(root, "W1", f"thing-{variant}", "K")
                self.assertEqual(out["executed"], ["one"], variant)
                self.assertEqual(out["re_executed_steps"], ["one"], variant)
                oks = proc_invokes(root, "K", errors=False)
                self.assertEqual(len(oks), 1, variant)
                self.assertFalse(oks[0]["proc"]["recovered"], variant)

    def test_l4_torn_ledger_refuses(self):
        bdir = self._two_step()
        root = self.root / "l4"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "thing",
            "--key",
            "K",
            env=child_env(SUBSTRATE_CRASH_MID_APPEND="2"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        tail = (root / "ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        with self.assertRaises(ValueError):
            json.loads(tail)
        proc = cli("ops", "recover", "--state-dir", str(root))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("disk-loss", proc.stderr)

    def test_l5_kill_during_adopt_converges_exactly_once(self):
        bdir = self._two_step()
        root = self.root / "l5"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "thing",
            "--key",
            "K",
            env=child_env(SUBSTRATE_CRASH_AT="proc:post-done-pre-invoke"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        # recover appends: reopen=1, adopt consume=2, adopt invoke=3:
        # kill after 2 lands between consume and invoke (L5)
        proc = cli(
            "ops",
            "recover",
            "--state-dir",
            str(root),
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="2"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        # re-run converges with exactly-once accounting
        rec = api.recover_op(root)
        self.assertEqual(len(rec["proc_adopted"]), 1)
        oks = proc_invokes(root, "K", errors=False)
        self.assertEqual(len(oks), 1)
        self.assertTrue(oks[0]["proc"]["recovered"])
        consumes = [
            e["payload"] for e in ledger_lines(root) if e.get("kind") == "consume"
        ]
        mine = [c for c in consumes if c.get("evidence_ref") == oks[0]["invoke_id"]]
        self.assertEqual(len(mine), 1)
        host, _ = api.open_run(root)
        self.assertTrue(host.verify_conservation()["ok"])

    def test_real_sigkill_l2_l3_loop(self):
        if os.name != "posix":
            self.skipTest("POSIX group-kill leg")
        sleep_s = 5
        step = {
            "step": "long",
            "argv": [
                "python3",
                "-c",
                f"import time; time.sleep({sleep_s}); open('done.txt','w').write('d')",
            ],
            "declared_outputs": ["done.txt"],
            "timeout_s": 600,
        }
        big = b"x" * (10 * 1024 * 1024)
        bdir = self.bundle("longrun", [step], {"big.bin": big})
        root = self.root / "killloop"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # P9 ballast: 2000 small state files widen the honest
        # post-DONE window (post snapshot + P8 re-hash of big.bin).
        ballast = root / "state" / "ballast"
        ballast.mkdir(parents=True)
        for i in range(2000):
            (ballast / f"f{i:04d}.txt").write_text(f"ballast-{i}")
        # calibration run: measure the clean wall on this box
        t0 = time.monotonic()
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            "longrun",
            "--key",
            "K-cal",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        wall = time.monotonic() - t0
        self.assertGreater(wall, sleep_s)  # sanity: slept
        delays = [0.05 * wall + i * (0.90 * wall / 19) for i in range(20)] + [
            (wall - 0.45) + j * (0.60 / 19) for j in range(20)
        ]
        delays = [max(0.05, d) for d in delays]
        landings: dict[str, int] = {}

        def one_round(key, delay):
            child = spawn_cli(
                "ops",
                "run-procedure",
                "--state-dir",
                str(root),
                "--world",
                "W1",
                "--procedure",
                "longrun",
                "--key",
                key,
            )
            time.sleep(delay)
            if child.poll() is None:
                kill_group(child)
            child.communicate()
            begins = proc_begins_of(root, key)
            oks = proc_invokes(root, key, errors=False)
            errs = proc_invokes(root, key, errors=True)
            self.assertEqual(errs, [], f"{key}: no error leg here")
            if oks:
                landing = "complete"
            elif not begins:
                landing = "no-trace"
            elif (Path(begins[0]["scratch"]) / "DONE.json").is_file():
                landing = "L3"
            else:
                landing = "L2"
            rec = api.recover_op(root)
            if landing == "L3":
                self.assertTrue(
                    any(a["idem_key"] == key for a in rec["proc_adopted"]), key
                )
            out = api.run_procedure(root, "W1", "longrun", key)
            final = proc_invokes(root, key, errors=False)
            self.assertEqual(len(final), 1, f"{key}/{landing}")
            self.assertLessEqual(len(proc_begins_of(root, key)), 2, key)
            self.assertLessEqual(len(out["re_executed_steps"]), 1, key)
            host, _ = api.open_run(root)
            self.assertTrue(host.verify_conservation()["ok"], key)
            return landing

        for n, delay in enumerate(delays):
            key = f"K{n:02d}"
            landing, note = self.guarded_round(root, key, lambda: one_round(key, delay))
            landings[landing] = landings.get(landing, 0) + 1
            if note:
                landings[note] = landings.get(note, 0) + 1
        print(f"sigkill loop landings={landings} wall={wall:.2f}s")
        self.assertGreaterEqual(landings.get("L2", 0), 1)
        self.assertGreaterEqual(landings.get("L3", 0), 1)

    def test_repeated_kills_during_recover(self):
        # History: timing racer until 2026-10-08 (CI run 37768629306,
        # 3.11 leg: killed_live=0 when `recover` finished in <50ms on
        # all 12 rounds; re-run green). Fixed by child-side sync at
        # proc:recover-pre-adopt — the kill now lands on a blocked
        # child every round, deterministically. Do NOT weaken the
        # >=1 assert and do NOT reintroduce fixed sleeps.
        if os.name != "posix":
            self.skipTest("POSIX group-kill leg")
        bdir = self.bundle("thing", [c_step("one")])
        root = self.root / "repkill"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        rounds = 12
        killed_live = 0
        restored = 0

        def wait_ready(path: Path, timeout: float = 30.0) -> bool:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    if path.read_text(encoding="utf-8").strip() == "ready":
                        return True
                except OSError:
                    pass
                time.sleep(0.005)
            return False

        def one_round(key):
            syncfile = self.root / f"sync-{key}"
            syncfile.unlink(missing_ok=True)
            child = spawn_cli(
                "ops",
                "recover",
                "--state-dir",
                str(root),
                env=child_env(
                    SUBSTRATE_SYNC_AT="proc:recover-pre-adopt",
                    SUBSTRATE_SYNC_FILE=str(syncfile),
                ),
            )
            try:
                if not wait_ready(syncfile):
                    kill_group(child)
                    child.communicate()
                    self.fail(f"recover child never reached sync point: {key}")
                killed = child.poll() is None
                if killed:
                    kill_group(child)
                child.communicate()
            finally:
                syncfile.unlink(missing_ok=True)
            api.recover_op(root)
            oks = proc_invokes(root, key, errors=False)
            self.assertEqual(len(oks), 1, key)
            self.assertTrue(oks[0]["proc"]["recovered"], key)
            consumes = [
                e["payload"]
                for e in ledger_lines(root)
                if e.get("kind") == "consume"
                and e["payload"].get("evidence_ref") == oks[0]["invoke_id"]
            ]
            self.assertEqual(len(consumes), 1, key)
            host, _ = api.open_run(root)
            self.assertTrue(host.verify_conservation()["ok"], key)
            return killed

        for i in range(rounds):
            key = f"K{i:02d}"
            proc = cli(
                "ops",
                "run-procedure",
                "--state-dir",
                str(root),
                "--world",
                "W1",
                "--procedure",
                "thing",
                "--key",
                key,
                env=child_env(SUBSTRATE_CRASH_AT="proc:post-done-pre-invoke"),
            )
            self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
            killed, note = self.guarded_round(root, key, lambda: one_round(key))
            killed_live += 1 if killed else 0
            restored += 1 if note else 0
        print(
            f"repeated-kill loop: {rounds} rounds, "
            f"killed-live={killed_live} l4-restored={restored}"
        )
        self.assertGreaterEqual(killed_live, 1)


class TestProcRecovery(Base):
    """Conservation + recover classes + never-spawns + settle (A7)."""

    def _l3_root(self, tag, key="K"):
        bdir = self.bundle(f"thing-{tag}", [c_step("one")])
        root = self.root / f"rec-{tag}"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--bundle",
            str(bdir),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(root),
            "--world",
            "W1",
            "--procedure",
            f"thing-{tag}",
            "--key",
            key,
            env=child_env(SUBSTRATE_CRASH_AT="proc:post-done-pre-invoke"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        return root

    def test_recover_classes(self):
        # nothing-to-do on a clean root
        bdir = self.bundle("thing", [c_step("one")])
        root, _ = self.create("clean", "W1", bdir)
        api.run_procedure(root, "W1", "thing", "K")
        rec = api.recover_op(root)
        self.assertEqual(rec["proc_adopted"], [])
        self.assertEqual(rec["proc_rerunnable"], [])
        self.assertTrue(rec["proc_nothing_to_do"])
        # adopted on an L3 root
        l3 = self._l3_root("adopt")
        rec = api.recover_op(l3)
        self.assertEqual(len(rec["proc_adopted"]), 1)
        self.assertTrue(rec["proc_nothing_to_do"] is False)
        rec2 = api.recover_op(l3)
        self.assertTrue(rec2["proc_nothing_to_do"])
        # rerunnable on an L2 root
        bdir2 = self.bundle("thing2", [c_step("one")])
        l2 = self.root / "rec-l2"
        proc = cli(
            "ops",
            "create-proc-world",
            "--state-dir",
            str(l2),
            "--world",
            "W1",
            "--bundle",
            str(bdir2),
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli(
            "ops",
            "run-procedure",
            "--state-dir",
            str(l2),
            "--world",
            "W1",
            "--procedure",
            "thing2",
            "--key",
            "K",
            env=child_env(SUBSTRATE_CRASH_AFTER_APPENDS="2"),
        )
        self.assertEqual(proc.returncode, CRASH_RC, proc.stderr)
        rec = api.recover_op(l2)
        self.assertEqual(rec["proc_adopted"], [])
        self.assertEqual(len(rec["proc_rerunnable"]), 1)
        self.assertIn("re-invoke", rec["proc_rerunnable"][0]["reason"])

    def test_conservation_after_kills(self):
        l3 = self._l3_root("cons")
        host, _ = api.open_run(l3)
        self.assertTrue(host.verify_conservation()["ok"])
        api.recover_op(l3)
        host, _ = api.open_run(l3)
        self.assertTrue(host.verify_conservation()["ok"])
        out = api.run_procedure(l3, "W1", "thing-cons", "K")
        self.assertEqual(out["skipped"], ["one"])
        self.assertTrue(host.verify_conservation()["ok"])

    def test_recover_never_spawns_runtime(self):
        import subprocess as SP

        l3 = self._l3_root("nosspawn")
        real = SP.Popen
        calls: list = []

        def boom(*a, **k):
            calls.append((a, k))
            raise AssertionError("spawn under recover")

        SP.Popen = boom  # noqa: F841
        try:
            rec = api.recover_op(l3)
        finally:
            SP.Popen = real
        self.assertEqual(len(rec["proc_adopted"]), 1)
        self.assertEqual(calls, [])

    def test_adopt_then_settle_one_call(self):
        l3 = self._l3_root("settle")
        rec = api.recover_op(l3, ["W1"], reason="t")
        self.assertEqual(len(rec["proc_adopted"]), 1)
        self.assertIsNotNone(rec["settle"])
        self.assertIn("W1", rec["settle"]["settled_terminals"])
        host, _ = api.open_run(l3)
        self.assertTrue(host.verify_conservation()["ok"])

    def test_direct_settle_strands_l3_loudly(self):
        # Footgun (INT-BOUNDARIES §8, F1-style): a DIRECT settle
        # with L3 pending strands the adoption. Recovery reports it
        # (adopt-impossible, world dissolved) with no adopt appends.
        l3 = self._l3_root("strand")
        rep = api.settle_op(l3, ["W1"], reason="t")
        self.assertIn("W1", rep["settled_terminals"])
        before = len(ledger_lines(l3))
        rec = api.recover_op(l3)
        self.assertEqual(rec["proc_adopted"], [])
        self.assertEqual(len(rec["proc_rerunnable"]), 1)
        reason = rec["proc_rerunnable"][0]["reason"]
        self.assertIn("adopt-impossible", reason)
        self.assertIn("dissolved", reason)
        after = [
            e
            for e in ledger_lines(l3)[before:]
            if e.get("kind") in ("invoke", "consume", "deny")
        ]
        self.assertEqual(after, [])


class TestProcChange(Base):
    """New-world revision flow + cost-to-adapt counters (A8)."""

    def test_revised_bundle_new_world(self):
        v1 = self.bundle("relcheck", [c_step("one")], {"prog.py": "v1\n"})
        root = self.root / "change"
        r1 = api.create_proc_world(root, "W1", v1, reason="v1")
        out1 = api.run_procedure(root, "W1", "relcheck", "K1")
        self.assertEqual(out1["executed"], ["one"])
        # revised bytes ⇒ a NEW world (re-advertisement is creation)
        v2 = self.bundle(
            "relcheck",
            [c_step("one"), c_step("two")],
            {"prog.py": "v2\n"},
            tag="bundles-v2",
        )
        r2 = api.create_proc_world(root, "W2", v2, reason="rev")
        self.assertNotEqual(r1["bundle_sha256"], r2["bundle_sha256"])
        out2 = api.run_procedure(root, "W2", "relcheck", "K2")
        self.assertEqual(out2["executed"], ["one", "two"])
        # cost-to-adapt counters emitted on the revised run
        self.assertEqual(out2["re_executed_steps"], [])
        self.assertEqual(out2["child_executions"], {"one": 1, "two": 1})
        # W1 history intact and still resumable
        again = api.run_procedure(root, "W1", "relcheck", "K1")
        self.assertEqual(again["skipped"], ["one"])
        fresh = api.run_procedure(root, "W1", "relcheck", "K3")
        self.assertEqual(fresh["executed"], ["one"])
        # the ledger chain proves both tables
        creates = [
            e["payload"] for e in ledger_lines(root) if e.get("kind") == "create"
        ]
        pins = {
            c["world_id"]: [t["bundle_sha256"] for t in c["procedures"]]
            for c in creates
        }
        self.assertEqual(pins["W1"], [r1["bundle_sha256"]])
        self.assertEqual(pins["W2"], [r2["bundle_sha256"]])
        host, _ = api.open_run(root)
        self.assertTrue(host.verify_conservation()["ok"])


class TestProcConstruction(Base):
    """Executor construction: helper routing + no-spawn + stdlib (A7)."""

    def test_procedure_routes_writes_via_helpers(self):
        tree = ast.parse((PKG / "host" / "procedure.py").read_text(encoding="utf-8"))
        uses_text = uses_bytes = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "atomic_write_text":
                uses_text = True
            if isinstance(node, ast.Name) and node.id == "atomic_write_bytes":
                uses_bytes = True
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "write_text":
                    self.fail(
                        f"procedure.py:{node.lineno}: direct "
                        f".write_text (must route via helpers)"
                    )
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "replace"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                ):
                    self.fail(
                        f"procedure.py:{node.lineno}: direct "
                        f"os.replace (only inside the helper)"
                    )
                if isinstance(func, ast.Name) and func.id == "open":
                    mode = ""
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        mode = node.args[1].value or ""
                    for kw in node.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                            mode = kw.value.value or ""
                    self.assertNotIn(
                        "w", mode, f"procedure.py:{node.lineno}: raw open-w"
                    )
                    self.assertNotIn(
                        "a", mode, f"procedure.py:{node.lineno}: raw open-a"
                    )
        self.assertTrue(uses_text)
        self.assertTrue(uses_bytes)

    def test_atomic_write_bytes_semantics(self):
        from anima_substrate.host import minihost

        target = self.root / "sub" / "f.bin"
        blob = bytes(range(256)) * 100  # non-UTF8 bytes included
        out = minihost.atomic_write_bytes(target, blob)
        self.assertEqual(out, str(target))
        self.assertEqual(target.read_bytes(), blob)
        self.assertEqual(list(target.parent.glob("*.tmp-*")), [])
        src = minihost.atomic_write_bytes.__code__.co_names
        self.assertIn("atomic_write_text", src)  # one implementation
        # the mid-side-write hook covers byte writes (fresh process)
        script = (
            "from anima_substrate.host.minihost import "
            "atomic_write_bytes; "
            "atomic_write_bytes(%r, b'z' * 100)" % (str(self.root / "hooked.bin"))
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            env=child_env(SUBSTRATE_CRASH_MID_SIDE_WRITE="hooked.bin"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(proc.returncode, CRASH_RC)
        self.assertFalse((self.root / "hooked.bin").exists())

    def test_no_spawn_under_recover_paths(self):
        spawns = {
            "Popen",
            "run",
            "call",
            "check_output",
            "check_call",
            "system",
            "popen",
            "spawnl",
            "spawnlp",
            "spawnve",
            "create_subprocess",
        }
        targets = [
            (
                PKG / "host" / "procedure.py",
                {"proc_recover", "adopt_begin", "scan_proc_partials"},
            ),
            (PKG / "host" / "api.py", {"recover_op"}),
            (PKG / "host" / "recover.py", None),
        ]  # whole module
        for fpath, fns in targets:
            fname = fpath.name
            tree = ast.parse(fpath.read_text(encoding="utf-8"))

            def visit(node, scope=""):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scope = node.name
                if isinstance(node, ast.Call) and (fns is None or scope in fns):
                    func = node.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else getattr(func, "attr", "")
                    )
                    self.assertNotIn(
                        name,
                        spawns,
                        f"{fname}:{node.lineno}: spawn {name} under "
                        f"recovery scope {scope}",
                    )
                for child in ast.iter_child_nodes(node):
                    visit(child, scope)

            visit(tree)

    def test_envelope_branch_present_in_invoke(self):
        src = (PKG / "host" / "minihost.py").read_text(encoding="utf-8")
        self.assertIn("requires the procedure", src)
        self.assertIn('capability == "proc.exec"', src)

    def test_procedure_imports_stdlib_or_intree(self):
        tree = ast.parse((PKG / "host" / "procedure.py").read_text(encoding="utf-8"))
        intree = {p.stem for p in PKG.rglob("*.py")} | {"anima_substrate"}
        stdlib = set(sys.stdlib_module_names)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = (a.name or "").split(".")[0]
                    self.assertTrue(top in stdlib or top in intree, top)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # explicit relative import: intra-package
                top = (node.module or "").split(".")[0]
                self.assertTrue(top in stdlib or top in intree, top)


class TestProcWording(unittest.TestCase):
    """Tree-wide wording audit: non-claims hold everywhere (A11)."""

    NEGATIONS = (
        "not",
        "no",
        "never",
        "n't",
        "non-claim",
        "without",
        "forbidden",
        "unclaimed",
        "nor",
        "neither",
    )
    CLAIM_TERMS = (
        "sandbox",
        "isolat",
        "network-blocked",
        "contained",
        "containment",
        "air-gap",
        "network=none",
        "unbreakable",
        "tamper-proof",
    )

    # Package scope (port adaptation): every shipped module under
    # src/anima_substrate/ plus the consumer doc. Generated manifests
    # are data, not prose: pinned SST snapshot paths (incl.
    # sst/sandbox/*) appear as identifiers. Same principle as the
    # import carve-out below.
    GENERATED_MANIFESTS = (
        "pins.json",
        "MANIFEST.json",
        "relcheck-pins.json",
        "SNAPSHOT-MANIFEST.json",
    )

    def _scoped_files(self):
        out = sorted(PKG.rglob("*.py"))
        out.append(TOP / "docs" / "CONSUMER.md")
        out = [p for p in out if p.name not in self.GENERATED_MANIFESTS]
        return [p for p in out if p.is_file()]

    def _hits(self, terms):
        found = []
        for path in self._scoped_files():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = str(path.relative_to(TOP))
            for i, line in enumerate(text.splitlines(), 1):
                low = line.lower()
                for term in terms:
                    if term in low:
                        found.append((rel, i, line.strip()))
                        break
        return found

    def test_no_unnegated_isolation_claims(self):
        # Module paths in import statements are identifiers, not
        # claims (e.g. the vendored `sst.sandbox` package import).
        bad = [
            (rel, i, line)
            for rel, i, line in self._hits(self.CLAIM_TERMS)
            if not line.strip().startswith(("import ", "from "))
            and not any(neg in line.lower() for neg in self.NEGATIONS)
        ]
        self.assertEqual(bad, [])

    def test_impossibility_bounded(self):
        bounders = (
            "except",
            "carve-out",
            "adopt-impossible",
            "no ",
            "not ",
            "never",
            "apart from",
        )
        bad = [
            (rel, i, line)
            for rel, i, line in self._hits(("impossible",))
            if not any(b in line.lower() for b in bounders)
        ]
        self.assertEqual(bad, [])

    def test_required_terms_and_narrowings(self):
        consumer = (TOP / "docs" / "CONSUMER.md").read_text(encoding="utf-8")
        for term in (
            "accountable executor",
            "scoped invocation",
            "contractual",
            "CONTRACTUAL",
            "ENFORCED",
            "P11",
            "P15",
        ):
            self.assertIn(term, consumer, term)
        proc_src = (PKG / "host" / "procedure.py").read_text(encoding="utf-8")
        self.assertIn("accountable executor", proc_src.lower())
        # N1: the resume-skip carve-out is documented
        self.assertIn("scan_succeeded", consumer)
        # N2: every durability wording carries its disclaimer
        bad = [
            (rel, i, line)
            for rel, i, line in self._hits(("durab",))
            if not any(
                d in line.lower() for d in ("no fsync", "no-fsync", "limits-2", "power")
            )
        ]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
