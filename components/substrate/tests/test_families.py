# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained family-contract tests (M1/M2, package-new).

Registry behavior, per-family create/run/recover/change through the
consumer surface, the relcheck v1→v2 upgrade with old pins
reproducible, and the zero-host-edit structural check (family
modules bind the public host surface only).
"""

from __future__ import annotations

import ast
import hashlib
import json
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
from anima_substrate.participants import (  # noqa: E402
    ParticipantFamily,
    get_family,
    list_families,
    register_family,
)
from anima_substrate.participants.relcheck.checker import (  # noqa: E402
    RelcheckError,
)

SEED = "m1-seed-001"


def seed_tree(root: Path, tag: str, n_files: int = 4) -> dict[str, str]:
    """Deterministic fixture tree (seeded contents, no randomness)."""
    files = {}
    for i in range(n_files):
        rel = f"{tag}/file-{i}.txt" if i % 2 else f"{tag}-top-{i}.txt"
        body = f"{SEED}:{tag}:{rel}:v1\n"
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        files[rel] = hashlib.sha256(body.encode()).hexdigest()
    return files


def write_manifest(
    path: Path, release: str, files: dict, version: int = 1, compat: dict | None = None
) -> Path:
    manifest: dict = {
        "manifest_version": version,
        "release": release,
        "files": files,
    }
    if compat is not None:
        manifest["compat"] = compat
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = self.root / "state"
        api.init_run(self.state)


class TestRegistry(Base):
    def test_list_families_covers_base(self):
        names = {(f["name"], f["version"]) for f in list_families()}
        for want in (
            ("sched", "v1"),
            ("relcheck", "v1"),
            ("relcheck", "v2"),
            ("sst", "v1"),
        ):
            self.assertIn(want, names)
        for entry in list_families():
            self.assertEqual(entry["contract"], "v1")

    def test_duplicate_registration_refused(self):
        fam = get_family("sched", "v1")
        with self.assertRaises(ValueError):
            register_family(fam)

    def test_unknown_family_refusal_names_registered(self):
        with self.assertRaises(ValueError) as ctx:
            get_family("nope", "v9")
        self.assertIn("nope@v9", str(ctx.exception))
        self.assertIn("sched@v1", str(ctx.exception))

    def test_empty_name_or_version_refused(self):
        class Bad(ParticipantFamily):
            name = ""
            version = "v1"

            @property
            def caps(self):
                return []

            @property
            def reps(self):
                return []

            @property
            def grant_limits(self):
                return {}

            def create(self, *a, **k):
                raise AssertionError

            def run(self, *a, **k):
                raise AssertionError

            def recover(self, *a, **k):
                raise AssertionError

            def change(self, *a, **k):
                raise AssertionError

        with self.assertRaises(ValueError):
            register_family(Bad())


class TestZeroHostEdit(Base):
    """M2 structural check: family modules bind the public surface only.

    A family may import stdlib, intra-package participant modules,
    and the PUBLIC host surface (`anima_substrate.host.api`,
    `anima_substrate.host.minihost`, public cap/grant constants).
    No private host names (`api._*`), no host internals.
    """

    # Every participant module with logic (the two re-export
    # __init__ files carry no imports of their own... except sst's,
    # which IS the sst family — hence listed).
    FAMILY_MODULES = (
        "src/anima_substrate/participants/__init__.py",
        "src/anima_substrate/participants/sched/family.py",
        "src/anima_substrate/participants/sched/sched_checker.py",
        "src/anima_substrate/participants/sched/sched_domain.py",
        "src/anima_substrate/participants/sched/sched_inputs.py",
        "src/anima_substrate/participants/relcheck/v1.py",
        "src/anima_substrate/participants/relcheck/v2.py",
        "src/anima_substrate/participants/relcheck/runner.py",
        "src/anima_substrate/participants/relcheck/checker.py",
        "src/anima_substrate/participants/sst/__init__.py",
        "src/anima_substrate/participants/sst/staged.py",
        "src/anima_substrate/participants/sst/manifest.py",
    )

    REEXPORT_ONLY = (
        "src/anima_substrate/participants/sched/__init__.py",
        "src/anima_substrate/participants/relcheck/__init__.py",
    )

    PUBLIC_HOST = {
        "anima_substrate.host.api",
        "anima_substrate.host.minihost",
        "anima_substrate.host.pipeline",
        "anima_substrate.host.routing",
    }

    def test_family_modules_use_public_surface_only(self):
        stdlib = set(sys.stdlib_module_names)
        for rel in self.FAMILY_MODULES:
            tree = ast.parse((TOP / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        top = (a.name or "").split(".")[0]
                        self.assertIn(
                            top, stdlib | {"anima_substrate"}, f"{rel}: {a.name}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue  # relative: intra-participant
                    mod = node.module or ""
                    if mod.startswith("anima_substrate.host."):
                        self.assertIn(mod, self.PUBLIC_HOST, f"{rel}: {mod}")
                    elif mod.startswith("anima_substrate.host"):
                        self.assertIn(mod, {"anima_substrate.host"}, f"{rel}: {mod}")
                    else:
                        top = mod.split(".")[0]
                        self.assertIn(
                            top, stdlib | {"anima_substrate"}, f"{rel}: {mod}"
                        )
                    for a in node.names:
                        self.assertFalse(
                            a.name.startswith("_"), f"{rel}: private name {a.name}"
                        )
            # no private-attribute use of the host api at runtime
            text = (TOP / rel).read_text(encoding="utf-8")
            self.assertNotIn("api._", text, rel)

    def test_all_family_files_listed(self):
        # The check above must not silently miss a family module.
        actual = sorted(
            p.relative_to(TOP).as_posix() for p in (PKG / "participants").rglob("*.py")
        )
        self.assertEqual(sorted(self.FAMILY_MODULES + self.REEXPORT_ONLY), actual)
        # Re-export files carry no host imports at all.
        for rel in self.REEXPORT_ONLY:
            text = (TOP / rel).read_text(encoding="utf-8")
            self.assertNotIn("anima_substrate.host", text, rel)


class TestSchedFamily(Base):
    def test_create_run_recover(self):
        fam = get_family("sched", "v1")
        rep = fam.create(self.state, "SCH1", {"preset": "L"}, "t")
        self.assertEqual(rep["world_id"], "SCH1")
        self.assertEqual(rep["family"], "sched")
        out = fam.run(self.state, "SCH1", {"task_id": "SCH-T1"})
        self.assertTrue(out["valid"])
        self.assertIn("measured_cost", out)
        self.assertEqual(out["measured_cost"]["max_invocations"], 3)
        rec = fam.recover(self.state, "SCH1")
        self.assertEqual(rec["lifecycle"], "active")
        self.assertTrue(rec["conservation"]["ok"])

    def test_unknown_preset_actionable(self):
        fam = get_family("sched", "v1")
        with self.assertRaises(ValueError) as ctx:
            fam.create(self.state, "SCH9", {"preset": "ZZ"}, "t")
        self.assertIn("preset", str(ctx.exception))
        self.assertIn("fix", str(ctx.exception))

    def test_change_refuses_single_version(self):
        fam = get_family("sched", "v1")
        fam.create(self.state, "SCH1", {}, "t")
        with self.assertRaises(ValueError) as ctx:
            fam.change(self.state, "SCH1", "v2", "t")
        self.assertIn("only", str(ctx.exception))

    def test_run_unknown_world_refuses(self):
        fam = get_family("sched", "v1")
        with self.assertRaises(ValueError) as ctx:
            fam.run(self.state, "GHOST", {})
        self.assertIn("GHOST", str(ctx.exception))


class TestRelcheckV1(Base):
    def setUp(self):
        super().setUp()
        self.tree = self.root / "tree-a"
        self.files = seed_tree(self.tree, "pkg")
        self.manifest = write_manifest(self.root / "pins-a.json", "pkg-1.0", self.files)

    def test_create_run_valid(self):
        fam = get_family("relcheck", "v1")
        fam.create(self.state, "RC1", {}, "t")
        rep = fam.run(
            self.state,
            "RC1",
            {
                "task_id": "T1",
                "manifest_path": str(self.manifest),
                "tree_root": str(self.tree),
            },
        )
        self.assertTrue(rep["valid"])
        self.assertEqual(rep["identity"]["checked"], 4)
        self.assertEqual(rep["identity"]["missing"], [])
        self.assertIn("measured_cost", rep)
        self.assertTrue(Path(rep["report_ref"]).is_file())
        # staged pin reproduces the verdict inputs
        staged = json.loads(Path(rep["manifest_ref"]).read_text())
        self.assertEqual(staged["files"], self.files)

    def test_negative_verdicts_are_verdicts_not_errors(self):
        (self.tree / "pkg-top-0.txt").write_text("tampered\n", encoding="utf-8")
        (self.tree / "pkg" / "file-1.txt").unlink()
        (self.tree / "rogue.txt").write_text("x\n", encoding="utf-8")
        fam = get_family("relcheck", "v1")
        fam.create(self.state, "RC1", {}, "t")
        rep = fam.run(
            self.state,
            "RC1",
            {
                "task_id": "T1",
                "manifest_path": str(self.manifest),
                "tree_root": str(self.tree),
            },
        )
        self.assertFalse(rep["valid"])
        self.assertEqual(rep["identity"]["missing"], ["pkg/file-1.txt"])
        self.assertEqual(rep["identity"]["extra"], ["rogue.txt"])
        self.assertEqual(rep["identity"]["mismatched"], ["pkg-top-0.txt"])

    def test_close_reopen_byte_verified(self):
        fam = get_family("relcheck", "v1")
        fam.create(self.state, "RC1", {}, "t")
        rep = fam.run(
            self.state,
            "RC1",
            {
                "task_id": "T1",
                "manifest_path": str(self.manifest),
                "tree_root": str(self.tree),
            },
        )
        before = {
            p.relative_to(self.state).as_posix(): p.read_bytes()
            for p in sorted((self.state / "state" / "RC1").rglob("*"))
            if p.is_file()
        }
        host, _ = api.open_run(self.state)  # close (drop) + reopen
        del host
        host, _ = api.open_run(self.state)
        after = {
            p.relative_to(self.state).as_posix(): p.read_bytes()
            for p in sorted((self.state / "state" / "RC1").rglob("*"))
            if p.is_file()
        }
        self.assertEqual(before, after)
        # and the world still runs: same report bytes on re-run
        rep2 = fam.run(
            self.state,
            "RC1",
            {
                "task_id": "T1",
                "manifest_path": str(self.manifest),
                "tree_root": str(self.tree),
            },
        )
        self.assertEqual(
            Path(rep["report_ref"]).read_bytes(), Path(rep2["report_ref"]).read_bytes()
        )

    def test_v1_refuses_v2_manifest(self):
        man2 = write_manifest(
            self.root / "pins2.json",
            "pkg-2.0",
            self.files,
            version=2,
            compat={"min_release": "1.0", "requires_files": []},
        )
        fam = get_family("relcheck", "v1")
        fam.create(self.state, "RC1", {}, "t")
        with self.assertRaises(RelcheckError) as ctx:
            fam.run(
                self.state,
                "RC1",
                {
                    "task_id": "T1",
                    "manifest_path": str(man2),
                    "tree_root": str(self.tree),
                },
            )
        self.assertIn("relcheck@v2", str(ctx.exception))

    def test_seeded_actionable_errors(self):
        fam = get_family("relcheck", "v1")
        fam.create(self.state, "RC1", {}, "t")
        task = {
            "task_id": "E",
            "manifest_path": str(self.manifest),
            "tree_root": str(self.tree),
        }
        # E1: missing manifest
        bad = dict(task, manifest_path=str(self.root / "nope.json"))
        with self.assertRaises(RelcheckError) as ctx:
            fam.run(self.state, "RC1", bad)
        self.assertTrue(ctx.exception.cause)
        self.assertTrue(ctx.exception.fix)
        self.assertIn("manifest_path", str(ctx.exception))
        # E2: malformed manifest (unknown version)
        evil = self.root / "evil.json"
        evil.write_text('{"manifest_version": 99}', encoding="utf-8")
        bad = dict(task, manifest_path=str(evil))
        with self.assertRaises(RelcheckError) as ctx:
            fam.run(self.state, "RC1", bad)
        self.assertIn("manifest_version", ctx.exception.cause)
        self.assertTrue(ctx.exception.fix)
        # E3: missing tree root
        bad = dict(task, tree_root=str(self.root / "no-tree"))
        with self.assertRaises(RelcheckError) as ctx:
            fam.run(self.state, "RC1", bad)
        self.assertIn("tree_root", ctx.exception.cause)
        self.assertTrue(ctx.exception.fix)
        # error legs are ledger-recorded but burn nothing
        host, _ = api.open_run(self.state)
        errors = [
            e
            for e in host.ledger_entries()
            if e.get("kind") == "invoke" and "error" in e.get("payload", {})
        ]
        self.assertGreaterEqual(len(errors), 3)
        for err in errors:
            self.assertIn("RelcheckError", err["payload"]["error"])
        self.assertEqual(host.consumed["RC1"]["max_invocations"], 0)
        self.assertEqual(host.consumed["RC1"]["max_time_s"], 0.0)


class TestRelcheckV2(Base):
    def setUp(self):
        super().setUp()
        self.tree = self.root / "tree-b"
        self.files = seed_tree(self.tree, "lib", n_files=3)
        self.manifest = write_manifest(
            self.root / "pins-b.json",
            "2.1",
            self.files,
            version=2,
            compat={"min_release": "2.0", "requires_files": ["lib-top-0.txt"]},
        )

    def test_v2_compat_valid(self):
        fam = get_family("relcheck", "v2")
        fam.create(self.state, "RC2", {}, "t")
        rep = fam.run(
            self.state,
            "RC2",
            {
                "task_id": "T1",
                "manifest_path": str(self.manifest),
                "tree_root": str(self.tree),
            },
        )
        self.assertTrue(rep["valid"])
        self.assertTrue(rep["compat"]["declared"])
        self.assertTrue(rep["compat"]["valid"])

    def test_v2_compat_negative(self):
        man = write_manifest(
            self.root / "pins-c.json",
            "1.5",
            self.files,
            version=2,
            compat={"min_release": "2.0", "requires_files": ["missing.txt"]},
        )
        fam = get_family("relcheck", "v2")
        fam.create(self.state, "RC2", {}, "t")
        rep = fam.run(
            self.state,
            "RC2",
            {"task_id": "T1", "manifest_path": str(man), "tree_root": str(self.tree)},
        )
        self.assertFalse(rep["valid"])
        self.assertFalse(rep["compat"]["release_ok"])
        self.assertEqual(rep["compat"]["requires_missing"], ["missing.txt"])

    def test_v2_accepts_v1_manifest_with_explicit_skip(self):
        man1 = write_manifest(self.root / "pins1.json", "9.9", self.files)
        fam = get_family("relcheck", "v2")
        fam.create(self.state, "RC2", {}, "t")
        rep = fam.run(
            self.state,
            "RC2",
            {"task_id": "T1", "manifest_path": str(man1), "tree_root": str(self.tree)},
        )
        self.assertTrue(rep["valid"])
        self.assertFalse(rep["compat"]["declared"])
        self.assertIsNone(rep["compat"]["valid"])

    def test_v1_to_v2_upgrade_old_pins_reproducible(self):
        man1 = write_manifest(self.root / "pins-old.json", "2.1", self.files)
        v1 = get_family("relcheck", "v1")
        v1.create(self.state, "RC1", {}, "t")
        rep1 = v1.run(
            self.state,
            "RC1",
            {"task_id": "T1", "manifest_path": str(man1), "tree_root": str(self.tree)},
        )
        self.assertTrue(rep1["valid"])
        up = v1.change(self.state, "RC1", "v2", "upgrade test")
        self.assertEqual(up["world_id"], "RC1-v2")
        self.assertEqual(up["derived_from"], "RC1")
        host, _ = api.open_run(self.state)
        lineage = host.worlds["RC1-v2"].lineage
        derived = [
            e["world"]
            for e in lineage
            if isinstance(e, dict) and e.get("rel") == "derived_from"
        ]
        self.assertEqual(derived, ["RC1"])
        # old world untouched: old pins reproduce byte-identically
        rep_old = v1.run(
            self.state,
            "RC1",
            {"task_id": "T1", "manifest_path": str(man1), "tree_root": str(self.tree)},
        )
        self.assertEqual(
            Path(rep1["report_ref"]).read_bytes(),
            Path(rep_old["report_ref"]).read_bytes(),
        )
        # both versions stay registered and runnable side by side;
        # the v2 world runs both the old and the new task shape
        v2 = get_family("relcheck", "v2")
        rep_compat = v2.run(
            self.state,
            "RC1-v2",
            {"task_id": "T1", "manifest_path": str(man1), "tree_root": str(self.tree)},
        )
        self.assertTrue(rep_compat["valid"])
        self.assertFalse(rep_compat["compat"]["declared"])
        rep_new = v2.run(
            self.state,
            "RC1-v2",
            {
                "task_id": "T2",
                "manifest_path": str(self.manifest),
                "tree_root": str(self.tree),
            },
        )
        self.assertTrue(rep_new["valid"])
        self.assertTrue(rep_new["compat"]["declared"])
        # v1 world cannot run the v2-manifest task
        with self.assertRaises(RelcheckError):
            v1.run(
                self.state,
                "RC1",
                {
                    "task_id": "T3",
                    "manifest_path": str(self.manifest),
                    "tree_root": str(self.tree),
                },
            )

    def test_change_refuses_unknown_target(self):
        v1 = get_family("relcheck", "v1")
        v1.create(self.state, "RC1", {}, "t")
        with self.assertRaises(ValueError) as ctx:
            v1.change(self.state, "RC1", "v9", "t")
        self.assertIn("v2", str(ctx.exception))

    def test_change_refuses_existing_successor(self):
        v1 = get_family("relcheck", "v1")
        v1.create(self.state, "RC1", {}, "t")
        v1.change(self.state, "RC1", "v2", "t")
        with self.assertRaises(ValueError) as ctx:
            v1.change(self.state, "RC1", "v2", "t")
        self.assertIn("already exists", str(ctx.exception))

    def test_v2_change_refuses_newest(self):
        v2 = get_family("relcheck", "v2")
        v2.create(self.state, "RC2", {}, "t")
        with self.assertRaises(ValueError) as ctx:
            v2.change(self.state, "RC2", "v3", "t")
        self.assertIn("newest", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
