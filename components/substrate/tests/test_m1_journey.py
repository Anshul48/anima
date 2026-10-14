# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained M1 usable-journey tests (package-new).

Fresh-state CLI journey on real files: project world, file-backed
task work, close/reopen byte-verified, settle clean; 3 seeded
failure cases with actionable errors; install+run from a built
wheel outside the checkout (gated by ANIMA_WHEEL_CHECK=1 — slow,
runs the real build).
"""

from __future__ import annotations

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

SEED = "m1-seed-001"
WHEEL_CHECK = os.environ.get("ANIMA_WHEEL_CHECK", "") == "1"
WHEEL_SKIP = (
    "ANIMA_WHEEL_CHECK!=1 (wheel build+install runs gated; "
    "see BUILDER-LOG.md for the witnessed instance)"
)


def seed_tree(root: Path, tag: str, n_files: int = 4) -> dict[str, str]:
    files = {}
    for i in range(n_files):
        rel = f"{tag}/file-{i}.txt" if i % 2 else f"{tag}-top-{i}.txt"
        body = f"{SEED}:{tag}:{rel}:v1\n"
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        files[rel] = hashlib.sha256(body.encode()).hexdigest()
    return files


def cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    merged = dict(os.environ)
    merged["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "anima_substrate", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=merged,
    )


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.tree = self.root / "release-tree"
        self.files = seed_tree(self.tree, "pkg")
        self.manifest = self.root / "pins.json"
        self.manifest.write_text(
            json.dumps(
                {"manifest_version": 1, "release": "pkg-1.0", "files": self.files},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.state = self.root / "state"


class TestM1Journey(Base):
    def test_cli_journey(self):
        state = str(self.state)
        proc = cli("init", "--state-dir", state)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = cli("families")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("relcheck@v1", proc.stdout)
        self.assertIn("sched@v1", proc.stdout)
        proc = cli(
            "ops",
            "family-create",
            "--state-dir",
            state,
            "--family",
            "relcheck",
            "--version",
            "v1",
            "--world",
            "RC1",
            "--params",
            "{}",
            "--reason",
            "m1 journey",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("RC1", proc.stdout)
        task = json.dumps(
            {
                "task_id": "M1-T1",
                "manifest_path": str(self.manifest),
                "tree_root": str(self.tree),
            }
        )
        proc = cli(
            "ops",
            "family-run",
            "--state-dir",
            state,
            "--family",
            "relcheck",
            "--version",
            "v1",
            "--world",
            "RC1",
            "--task",
            task,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("valid=True", proc.stdout)
        proc = cli(
            "ops",
            "relate",
            "--state-dir",
            state,
            "--rel",
            "release-check",
            "--version",
            "v1",
            "--participants",
            "RC1,SC-L",
            "--purpose",
            "release RC1 checked against SC-L pins",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # close/reopen byte-verified (org snapshot + world files)
        before = cli("ops", "org-snapshot", "--state-dir", state, "--json")
        self.assertEqual(before.returncode, 0, before.stderr)
        world_before = {
            p.relative_to(self.state).as_posix(): p.read_bytes()
            for p in sorted((self.state / "state").rglob("*"))
            if p.is_file()
        }
        after = cli("ops", "org-snapshot", "--state-dir", state, "--json")
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual(
            json.loads(before.stdout)["channels"], json.loads(after.stdout)["channels"]
        )
        self.assertEqual(
            json.loads(before.stdout)["relationships"],
            json.loads(after.stdout)["relationships"],
        )
        world_after = {
            p.relative_to(self.state).as_posix(): p.read_bytes()
            for p in sorted((self.state / "state").rglob("*"))
            if p.is_file()
        }
        self.assertEqual(world_before, world_after)
        proc = cli(
            "ops",
            "family-recover",
            "--state-dir",
            state,
            "--family",
            "relcheck",
            "--version",
            "v1",
            "--world",
            "RC1",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("active", proc.stdout)
        proc = cli(
            "ops",
            "settle",
            "--state-dir",
            state,
            "--worlds",
            "RC1,SC-L,SC-S",
            "--reason",
            "m1 done",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("stranded=0", proc.stdout)

    def test_seeded_errors_actionable_via_cli(self):
        state = str(self.state)
        self.assertEqual(cli("init", "--state-dir", state).returncode, 0)
        proc = cli(
            "ops",
            "family-create",
            "--state-dir",
            state,
            "--family",
            "relcheck",
            "--version",
            "v1",
            "--world",
            "RC1",
            "--params",
            "{}",
            "--reason",
            "t",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        base = {
            "task_id": "E",
            "manifest_path": str(self.manifest),
            "tree_root": str(self.tree),
        }
        cases = [
            (
                "missing manifest",
                dict(base, manifest_path=str(self.root / "nope.json")),
                "manifest_path",
            ),
            (
                "malformed manifest",
                dict(base, manifest_path=self._evil()),
                "manifest_version",
            ),
            (
                "missing tree",
                dict(base, tree_root=str(self.root / "no-tree")),
                "tree_root",
            ),
        ]
        for name, task, marker in cases:
            proc = cli(
                "ops",
                "family-run",
                "--state-dir",
                state,
                "--family",
                "relcheck",
                "--version",
                "v1",
                "--world",
                "RC1",
                "--task",
                json.dumps(task),
            )
            self.assertEqual(proc.returncode, 1, name)
            self.assertIn("anima-substrate: error:", proc.stderr, name)
            self.assertIn(marker, proc.stderr, name)
            self.assertIn("fix:", proc.stderr, name)

    def _evil(self) -> str:
        evil = self.root / "evil.json"
        evil.write_text('{"manifest_version": 99}', encoding="utf-8")
        return str(evil)


@unittest.skipIf(not WHEEL_CHECK, WHEEL_SKIP)
class TestWheelInstall(unittest.TestCase):
    """Install + run from a built wheel outside the checkout (M1)."""

    def test_wheel_install_and_run_outside_checkout(self):
        work = TMPROOT / "wheel"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, work, True)
        dist = work / "dist"
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(dist)],
            cwd=str(TOP),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
        wheels = sorted(dist.glob("anima_substrate-*.whl"))
        self.assertEqual(len(wheels), 1)
        target = work / "target"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                str(wheels[0]),
                "--target",
                str(target),
                "--no-deps",
                "--quiet",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
        # run OUTSIDE the checkout: cwd=work, checkout not on sys.path
        tree = work / "tree"
        files = seed_tree(tree, "w")
        manifest = work / "pins.json"
        manifest.write_text(
            json.dumps({"manifest_version": 1, "release": "w-1.0", "files": files}),
            encoding="utf-8",
        )
        state = work / "state"
        env = {
            "PYTHONPATH": str(target),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": os.environ.get("PATH", ""),
        }

        def wcli(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, "-m", "anima_substrate", *args],
                cwd=str(work),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        proc = wcli("init", "--state-dir", str(state))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = wcli("families")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("relcheck@v1", proc.stdout)
        proc = wcli(
            "ops",
            "family-create",
            "--state-dir",
            str(state),
            "--family",
            "relcheck",
            "--version",
            "v1",
            "--world",
            "RC1",
            "--params",
            "{}",
            "--reason",
            "wheel check",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        task = json.dumps(
            {"task_id": "W-T1", "manifest_path": str(manifest), "tree_root": str(tree)}
        )
        proc = wcli(
            "ops",
            "family-run",
            "--state-dir",
            str(state),
            "--family",
            "relcheck",
            "--version",
            "v1",
            "--world",
            "RC1",
            "--task",
            task,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("valid=True", proc.stdout)
        before = wcli("ops", "org-snapshot", "--state-dir", str(state), "--json")
        after = wcli("ops", "org-snapshot", "--state-dir", str(state), "--json")
        self.assertEqual(before.stdout, after.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
