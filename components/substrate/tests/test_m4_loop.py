# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained M4 experience-loop tests (package-new).

Propose → assess → retain → reuse on real task work, with the
prereg entry filed BEFORE any comparison run (programme PREREG-LOG
format, package-local), invalid proposals assessed too, reuse on a
meaningfully different second task, a competent from-scratch
baseline with costs/interventions, and no comparative-claim or
learning verbiage anywhere.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

import anima_substrate  # noqa: E402

PKG = Path(anima_substrate.__file__).resolve().parent
TOP = PKG.parent.parent
TMPROOT = Path(tempfile.mkdtemp(prefix="anima-substrate-tests-"))

from anima_substrate.host import (  # noqa: E402
    api,
    recipes,
)

SEED = "m4-seed-001"
BUDGET_S = 60.0

# Byte-pinned fixture contents (filed in the prereg, built verbatim).
TREE_A = {
    "rel/app.py": "print('app-a')\n",
    "rel/util.py": "X = 1\n",
}
TREE_B = {
    "pkg/main.py": "print('main-b')\n",
    "pkg/extra/deep.py": "Y = [1, 2, 3]\n",
    "pkg/extra/shallow.py": "Z = 's'\n",
    "notes.txt": "release notes b\n",
}

PREREG_BODY = """# M4-LOOP PREREG (filed before any comparison run)

seed: m4-seed-001
task-a: release rel-a-1.0, files {rel/app.py, rel/util.py} with the
  exact bytes quoted in fixtures.json (built verbatim, never edited)
task-b: release rel-b-2.0, files {pkg/main.py, pkg/extra/deep.py,
  pkg/extra/shallow.py, notes.txt} with the exact bytes quoted in
  fixtures.json (relpaths disjoint from task-a by construction)
predicates (coded in anima_substrate.host.recipes):
  P0 evaluator self-test passes (signal: evaluator defect)
  P1 staged pins reproduce on the task tree (signal: independent-check failure)
  P2 staged manifest requirements met (signal: explicit requirement/preference correction)
  P3 measured elapsed within budget_s=60.0 (signal: prediction discrepancy)
  P4 reuse-vs-baseline record (signal: comparative workflow advantage)
verdict rule: VOID iff P0 fails; POSITIVE iff P1+P2+P3 pass; else NEGATIVE
rule: verdict agreement REPORTED; reuse cost (elapsed_s + ledger
  measured_cost) and baseline cost (elapsed_s) REPORTED;
  interventions REPORTED (reuse 1, baseline 3); no ranking under any
  outcome (superiority_claimed=false is fixed)
"""

SIGNAL_CLASSES = {
    "prediction discrepancy",
    "explicit requirement/preference correction",
    "independent-check failure",
    "evaluator defect",
    "comparative workflow advantage",
}


def build_tree(root: Path, files: dict[str, str]) -> dict[str, str]:
    pins = {}
    for rel, body in sorted(files.items()):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        pins[rel] = hashlib.sha256(body.encode()).hexdigest()
    return pins


def write_manifest(path: Path, release: str, pins: dict) -> Path:
    path.write_text(
        json.dumps(
            {"manifest_version": 1, "release": release, "files": pins},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def file_prereg(rundir: Path, stamp: str) -> tuple[Path, Path]:
    """File PREREG.md + PREREG-ENTRY.md; return (prereg, entry)."""
    prereg = rundir / "PREREG.md"
    prereg.write_text(PREREG_BODY, encoding="utf-8")
    fixtures = rundir / "fixtures.json"
    fixtures.write_text(
        json.dumps(
            {"seed": SEED, "tree-a": TREE_A, "tree-b": TREE_B}, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    prereg_sha = hashlib.sha256(prereg.read_bytes()).hexdigest()
    fixtures_sha = hashlib.sha256(fixtures.read_bytes()).hexdigest()
    recipes_sha = hashlib.sha256((PKG / "host" / "recipes.py").read_bytes()).hexdigest()
    body = (
        f"## M4-LOOP {stamp}\n"
        f"\n"
        f"- experiment: M4 recipe loop (relcheck profile reuse vs "
        f"from-scratch baseline)\n"
        f"- work_dir: {rundir}\n"
        f"- prev_hash: ba821dd039077c29820da9a6b3fb0cca44eeb7f89db4e46078786e58c2f45eea\n"
        f"- prev_basis: programme PREREG-LOG U-EXECUTE entry_hash "
        f"(read-only anchor; the programme log is coordinator-owned)\n"
        f"- prereg: PREREG.md sha256 {prereg_sha}\n"
        f"- fixtures: fixtures.json sha256 {fixtures_sha}\n"
        f"- predicates: recipes.py sha256 {recipes_sha} (P0-P3 + "
        f"verdict rule quoted verbatim in PREREG.md)\n"
        f"- tasks: tree-a/tree-b bytes inline in fixtures.json "
        f"(relpaths disjoint, releases rel-a-1.0/rel-b-2.0)\n"
        f"- generator: seeded builder (seed m4-seed-001), bytes inline\n"
        f"- rule: agreement + costs + interventions REPORTED; "
        f"superiority_claimed=false fixed (no ranking)\n"
        f"- entry_hash_basis: sha256 of this entry body EXCLUDING "
        f"this entry_hash line\n"
    )
    entry_hash = hashlib.sha256(body.encode()).hexdigest()
    entry = rundir / "PREREG-ENTRY.md"
    entry.write_text(body + f"- entry_hash: {entry_hash}\n", encoding="utf-8")
    return prereg, entry


class TestM4Loop(unittest.TestCase):
    def test_full_loop(self):
        rundir = TMPROOT / "test_full_loop"
        if rundir.exists():
            shutil.rmtree(rundir)
        rundir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, rundir, True)
        # 1. FILE THE PREREG BEFORE ANY COMPARISON RUN
        prereg, entry = file_prereg(rundir, "2026-10-07T00:00:00Z")
        filed_entry_hash = hashlib.sha256(entry.read_bytes()).hexdigest()
        filed_prereg_hash = hashlib.sha256(prereg.read_bytes()).hexdigest()
        # 2. build the pinned tasks verbatim
        tree_a = rundir / "tree-a"
        tree_b = rundir / "tree-b"
        pins_a = build_tree(tree_a, TREE_A)
        pins_b = build_tree(tree_b, TREE_B)
        man_a = write_manifest(rundir / "pins-a.json", "rel-a-1.0", pins_a)
        man_b = write_manifest(rundir / "pins-b.json", "rel-b-2.0", pins_b)
        # 3. task B is MEANINGFULLY DIFFERENT (mechanical precondition)
        self.assertEqual(set(pins_a) & set(pins_b), set())
        self.assertNotEqual("rel-a-1.0", "rel-b-2.0")
        self.assertNotEqual(len(pins_a), len(pins_b))
        # 4. propose → assess → retain on task A
        state = rundir / "state"
        api.init_run(state)
        prop = api.recipe_propose_op(
            state, "pins-v1", "relcheck", "v1", man_a, entry, "m4 test proposal"
        )
        self.assertEqual(prop["prereg_entry_sha256"], filed_entry_hash)
        assessed = api.recipe_assess_op(state, "pins-v1", tree_a, "A1", BUDGET_S)
        self.assertEqual(assessed["verdict"], "POSITIVE")
        for pid, pred in assessed["predicates"].items():
            self.assertIn(pred["signal_class"], SIGNAL_CLASSES, pid)
        classes = [p["signal_class"] for p in assessed["predicates"].values()]
        self.assertEqual(len(set(classes)), 4)  # never conflated
        retained = api.recipe_retain_op(
            state, "pins-v1", "A1", "retain", "m4 test retention"
        )
        self.assertEqual(retained["decision"], "retain")
        self.assertIn("manifest_sha256", retained["lineage"])
        self.assertIn("elapsed_s", retained["measured_cost"])
        # 5. reuse on task B + from-scratch baseline + compare
        reused = api.recipe_reuse_op(state, "pins-v1", "RC-R", tree_b, man_b, "B1")
        self.assertTrue(reused["valid"])
        baseline = api.recipe_baseline_op(tree_b, rundir / "baseline", "B1")
        self.assertTrue(baseline["valid"])
        self.assertEqual(baseline["interventions"], 3)
        compared = api.recipe_compare_op(state, "pins-v1", "B1", baseline, entry)
        self.assertTrue(compared["verdict_agreement"])
        self.assertEqual(compared["signal_class"], "comparative workflow advantage")
        self.assertFalse(compared["superiority_claimed"])
        self.assertEqual(compared["reuse"]["interventions"], 1)
        self.assertEqual(compared["baseline"]["interventions"], 3)
        self.assertEqual(compared["prereg_entry_sha256"], filed_entry_hash)
        # 6. the prereg is byte-identical after all runs
        self.assertEqual(
            hashlib.sha256(entry.read_bytes()).hexdigest(), filed_entry_hash
        )
        self.assertEqual(
            hashlib.sha256(prereg.read_bytes()).hexdigest(), filed_prereg_hash
        )

    def test_invalid_proposal_assessed_and_blocked(self):
        rundir = TMPROOT / "test_invalid_proposal"
        if rundir.exists():
            shutil.rmtree(rundir)
        rundir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, rundir, True)
        _, entry = file_prereg(rundir, "2026-10-07T00:00:01Z")
        tree_a = rundir / "tree-a"
        pins_a = build_tree(tree_a, TREE_A)
        # corrupt pins: every digest flipped
        bad_pins = {r: ("0" if d[0] != "0" else "1") + d[1:] for r, d in pins_a.items()}
        man_bad = write_manifest(rundir / "pins-bad.json", "rel-a-1.0", bad_pins)
        state = rundir / "state"
        api.init_run(state)
        # propose ACCEPTS the invalid recipe (assessment decides)
        api.recipe_propose_op(
            state, "bad-pins", "relcheck", "v1", man_bad, entry, "m4 invalid test"
        )
        assessed = api.recipe_assess_op(state, "bad-pins", tree_a, "A1", BUDGET_S)
        self.assertEqual(assessed["verdict"], "NEGATIVE")
        self.assertFalse(assessed["predicates"]["P1"]["passed"])
        retained = api.recipe_retain_op(
            state, "bad-pins", "A1", "retain-negative", "m4 test"
        )
        self.assertEqual(retained["decision"], "retain-negative")
        # negatives are evidence, not executables
        with self.assertRaises(ValueError) as ctx:
            api.recipe_reuse_op(state, "bad-pins", "RC-X", tree_a, man_bad, "B9")
        self.assertIn("retained-negative", str(ctx.exception))

    def test_retain_rules(self):
        rundir = TMPROOT / "test_retain_rules"
        if rundir.exists():
            shutil.rmtree(rundir)
        rundir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, rundir, True)
        _, entry = file_prereg(rundir, "2026-10-07T00:00:02Z")
        tree_a = rundir / "tree-a"
        pins_a = build_tree(tree_a, TREE_A)
        man_a = write_manifest(rundir / "pins-a.json", "rel-a-1.0", pins_a)
        state = rundir / "state"
        api.init_run(state)
        api.recipe_propose_op(state, "r1", "relcheck", "v1", man_a, entry, "t")
        api.recipe_assess_op(state, "r1", tree_a, "A1", BUDGET_S)
        with self.assertRaises(ValueError) as ctx:
            api.recipe_retain_op(state, "r1", "A1", "retain-negative", "t")
        self.assertIn("not NEGATIVE", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            api.recipe_retain_op(state, "r1", "A1", "drop", "t")
        self.assertIn("not in", str(ctx.exception))

    def test_compare_voids_on_changed_prereg(self):
        rundir = TMPROOT / "test_changed_prereg"
        if rundir.exists():
            shutil.rmtree(rundir)
        rundir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, rundir, True)
        _, entry = file_prereg(rundir, "2026-10-07T00:00:03Z")
        tree_a = rundir / "tree-a"
        tree_b = rundir / "tree-b"
        pins_a = build_tree(tree_a, TREE_A)
        pins_b = build_tree(tree_b, TREE_B)
        man_a = write_manifest(rundir / "pins-a.json", "rel-a-1.0", pins_a)
        man_b = write_manifest(rundir / "pins-b.json", "rel-b-2.0", pins_b)
        state = rundir / "state"
        api.init_run(state)
        api.recipe_propose_op(state, "r1", "relcheck", "v1", man_a, entry, "t")
        api.recipe_assess_op(state, "r1", tree_a, "A1", BUDGET_S)
        api.recipe_retain_op(state, "r1", "A1", "retain", "t")
        api.recipe_reuse_op(state, "r1", "RC-R", tree_b, man_b, "B1")
        baseline = api.recipe_baseline_op(tree_b, rundir / "baseline", "B1")
        with entry.open("a", encoding="utf-8") as fh:
            fh.write("- tampered: true\n")
        with self.assertRaises(ValueError) as ctx:
            api.recipe_compare_op(state, "r1", "B1", baseline, entry)
        self.assertIn("VOID", str(ctx.exception))

    def test_propose_refuses_missing_prereg(self):
        rundir = TMPROOT / "test_missing_prereg"
        if rundir.exists():
            shutil.rmtree(rundir)
        rundir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, rundir, True)
        state = rundir / "state"
        api.init_run(state)
        with self.assertRaises(ValueError) as ctx:
            api.recipe_propose_op(
                state,
                "r1",
                "relcheck",
                "v1",
                rundir / "pins.json",
                rundir / "NO-ENTRY.md",
                "t",
            )
        self.assertIn("prereg", str(ctx.exception))

    def test_verdict_rule_unit(self):
        def preds(p0, p1, p2, p3):
            return {
                k: {"passed": v}
                for k, v in (("P0", p0), ("P1", p1), ("P2", p2), ("P3", p3))
            }

        self.assertEqual(recipes._verdict(preds(True, True, True, True)), "POSITIVE")
        self.assertEqual(recipes._verdict(preds(True, False, True, True)), "NEGATIVE")
        self.assertEqual(recipes._verdict(preds(True, True, False, True)), "NEGATIVE")
        self.assertEqual(recipes._verdict(preds(False, True, True, True)), "VOID")
        self.assertEqual(recipes._verdict(preds(False, False, False, False)), "VOID")

    def test_no_claim_verbiage(self):
        rundir = TMPROOT / "test_no_claim_verbiage"
        if rundir.exists():
            shutil.rmtree(rundir)
        rundir.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, rundir, True)
        prereg, entry = file_prereg(rundir, "2026-10-07T00:00:04Z")
        tree_a = rundir / "tree-a"
        tree_b = rundir / "tree-b"
        pins_a = build_tree(tree_a, TREE_A)
        pins_b = build_tree(tree_b, TREE_B)
        man_a = write_manifest(rundir / "pins-a.json", "rel-a-1.0", pins_a)
        man_b = write_manifest(rundir / "pins-b.json", "rel-b-2.0", pins_b)
        state = rundir / "state"
        api.init_run(state)
        api.recipe_propose_op(state, "r1", "relcheck", "v1", man_a, entry, "t")
        api.recipe_assess_op(state, "r1", tree_a, "A1", BUDGET_S)
        api.recipe_retain_op(state, "r1", "A1", "retain", "t")
        api.recipe_reuse_op(state, "r1", "RC-R", tree_b, man_b, "B1")
        baseline = api.recipe_baseline_op(tree_b, rundir / "baseline", "B1")
        compared = api.recipe_compare_op(state, "r1", "B1", baseline, entry)
        report_text = json.dumps(compared, indent=2, sort_keys=True)
        self.assertIn('"superiority_claimed": false', report_text)
        self.assertNotIn('"superiority_claimed": true', report_text)
        # no learning/comparative-claim stems outside the allowlisted key
        bodies = [
            body.replace("superiority_claimed", "")
            for body in (
                report_text,
                prereg.read_text(encoding="utf-8"),
                entry.read_text(encoding="utf-8"),
                (PKG / "host" / "recipes.py").read_text(encoding="utf-8"),
            )
        ]
        banned = re.compile(
            r"\b(discov\w*|invent\w*|learn\w*|superior\w*|breakthrough|"
            r"novel\w*)\b",
            re.IGNORECASE,
        )
        for body in bodies:
            hits = banned.findall(body)
            self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
