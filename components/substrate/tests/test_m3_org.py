# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained M3 persistent-organization tests (package-new).

Channels + relationship evidence + custody persist across
close/reopen (byte-verified inventories); an exported composite
executes UNMODIFIED in a fresh separate state dir (VALID +
lineage_ok, explicit new grants, bundle untouched); kill-during-
persist converges via reopen + recover.
"""

from __future__ import annotations

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


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


class Base(unittest.TestCase):
    def setUp(self):
        self.root = TMPROOT / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.state = self.root / "state"
        api.init_run(self.state)


class TestOrgPersist(Base):
    def test_channels_persist_across_reopen(self):
        api.run_tasks(self.state, ["S1", "S2"])  # local lane = traffic
        before = api.org_snapshot_bytes(self.state)
        snap = api.org_snapshot_op(self.state)
        self.assertTrue(snap["channels"], "expected live channels")
        chan_file = (self.state / "channels.json").read_bytes()
        host, _ = api.open_run(self.state)  # close + reopen
        del host
        after = api.org_snapshot_bytes(self.state)
        self.assertEqual(before, after)
        self.assertEqual((self.state / "channels.json").read_bytes(), chan_file)

    def test_empty_registry_persists_too(self):
        # fuse removes the pair channel; the emptied registry persists
        api.run_tasks(self.state, ["S1", "S2"])
        api.fuse_op(self.state, "SC-L", "SC-S", "SC-F", reason="t")
        before = api.org_snapshot_bytes(self.state)
        self.assertEqual(api.org_snapshot_op(self.state)["channels"], {})
        host, _ = api.open_run(self.state)
        del host
        self.assertEqual(api.org_snapshot_bytes(self.state), before)

    def test_relationships_persist_across_reopen(self):
        api.relate_op(
            self.state, "req-slots", "v1", ["SC-L", "SC-S"], "requirements to slots"
        )
        api.relate_op(
            self.state,
            "req-slots",
            "v2",
            ["SC-L", "SC-S"],
            "requirements to slots, revised mapping",
        )
        before = api.org_snapshot_bytes(self.state)
        snap = api.org_snapshot_op(self.state)
        self.assertEqual(sorted(snap["relationships"]["req-slots"]), ["v1", "v2"])
        self.assertEqual(
            snap["relationships"]["req-slots"]["v1"]["purpose"], "requirements to slots"
        )
        host, _ = api.open_run(self.state)
        del host
        self.assertEqual(api.org_snapshot_bytes(self.state), before)

    def test_relate_refusals(self):
        api.relate_op(self.state, "r1", "v1", ["SC-L"], "p")
        with self.assertRaises(Exception):
            api.relate_op(self.state, "r1", "v1", ["SC-L"], "p again")
        with self.assertRaises(Exception):
            api.relate_op(self.state, "r2", "v1", ["GHOST"], "p")

    def test_custody_persists_across_reopen(self):
        jstate = self.root / "jstate"
        api.j1_init(jstate, "PROJ", "t")
        api.nest_op(
            jstate,
            "PROJ",
            "EXP1",
            {"max_cost_usd": 0.5, "max_time_s": 30.0, "max_invocations": 50},
            ["j1.budget"],
            "t",
        )
        before = api.org_snapshot_bytes(jstate)
        snap = api.org_snapshot_op(jstate)
        self.assertIn("j1.budget", snap["custody"]["EXP1"])
        host, _ = api.open_run(jstate)
        del host
        self.assertEqual(api.org_snapshot_bytes(jstate), before)

    def test_snapshot_deterministic(self):
        api.run_tasks(self.state, ["S1"])
        self.assertEqual(
            api.org_snapshot_bytes(self.state), api.org_snapshot_bytes(self.state)
        )

    def test_kill_during_channel_persist_converges(self):
        api.run_tasks(self.state, ["S1", "S2"])
        old = api.org_snapshot_op(self.state)["channels"]
        self.assertTrue(old)
        script = (
            "from anima_substrate.host import api; "
            f"host, chans = api.open_run({str(self.state)!r}); "
            "chans.get('SC-L', 'SC-S').send({'probe': 'kill-me'})"
        )
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["SUBSTRATE_CRASH_MID_SIDE_WRITE"] = "channels.json"
        proc = subprocess.run(
            [sys.executable, "-c", script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(proc.returncode, 42)
        # old-or-new: the kill landed before the replace, so old
        host, _ = api.open_run(self.state)
        self.assertEqual(api.org_snapshot_op(self.state)["channels"], old)
        rep = api.recover_op(self.state)
        self.assertEqual(rep["specs_repaired"], [])
        self.assertTrue(host.verify_conservation()["ok"])
        # the path keeps working after convergence
        host, chans = api.open_run(self.state)
        chans.get("SC-L", "SC-S").send({"probe": "after"})
        self.assertEqual(
            api.org_snapshot_op(self.state)["channels"]["SC-L<->SC-S"]["messages"],
            old["SC-L<->SC-S"]["messages"] + 1,
        )


class TestPortableComposite(Base):
    def _fused(self) -> Path:
        api.run_tasks(self.state, ["S1", "S2"])
        api.relate_op(self.state, "req-slots", "v1", ["SC-L", "SC-S"], "t")
        api.fuse_op(self.state, "SC-L", "SC-S", "SC-F", reason="t")
        from anima_substrate.participants.sched import sched_inputs as FI

        rep = api.reuse_op(self.state, "SC-F", dict(FI.S4_FOLLOWUP))
        self.assertTrue(rep["valid"])
        return self.state

    def test_export_import_fresh_dir_executes(self):
        self._fused()
        bundle = self.root / "bundle"
        exp = api.export_composite_op(self.state, "SC-F", bundle)
        self.assertGreater(exp["files"], 0)
        self.assertGreater(exp["excerpt_entries"], 0)
        before = tree_bytes(bundle)
        fresh = self.root / "fresh"
        grants = {"max_cost_usd": 1.0, "max_time_s": 60.0, "max_invocations": 100.0}
        imp = api.import_composite_op(fresh, bundle, "SC-F2", grants, "m3 test import")
        self.assertTrue(imp["lineage_ok"])
        self.assertEqual(imp["derived_from"], ["SC-L", "SC-S"])
        self.assertEqual(imp["grants"], grants)
        # consumed UNMODIFIED: every bundle byte identical
        self.assertEqual(tree_bytes(bundle), before)
        # executes on the fresh state dir
        host, _ = api.open_run(fresh)
        self.assertEqual(host.worlds["SC-F2"].lifecycle, "active")
        m = api.j1_work_op(fresh, "SC-F2", "M3-T1")
        self.assertTrue(m["valid"])
        self.assertEqual(m["quality"], m["prefs_total"])

    def test_export_refuses_existing_out(self):
        self._fused()
        bundle = self.root / "bundle"
        bundle.mkdir()
        with self.assertRaises(RuntimeError) as ctx:
            api.export_composite_op(self.state, "SC-F", bundle)
        self.assertIn("already exists", str(ctx.exception))

    def test_export_refuses_unknown_world(self):
        with self.assertRaises(RuntimeError) as ctx:
            api.export_composite_op(self.state, "GHOST", self.root / "b")
        self.assertIn("unknown world", str(ctx.exception))

    def test_import_refuses_non_fresh_dir(self):
        self._fused()
        bundle = self.root / "bundle"
        api.export_composite_op(self.state, "SC-F", bundle)
        with self.assertRaises(RuntimeError) as ctx:
            api.import_composite_op(
                self.state,
                bundle,
                "X",
                {"max_cost_usd": 1.0, "max_time_s": 60.0, "max_invocations": 100.0},
                "t",
            )
        self.assertIn("not fresh", str(ctx.exception))

    def test_import_refuses_tampered_bundle(self):
        self._fused()
        bundle = self.root / "bundle"
        api.export_composite_op(self.state, "SC-F", bundle)
        victim = next((bundle / "files").rglob("*.json"))
        victim.write_text('{"tampered": true}', encoding="utf-8")
        with self.assertRaises(RuntimeError) as ctx:
            api.import_composite_op(
                self.root / "fresh",
                bundle,
                "X",
                {"max_cost_usd": 1.0, "max_time_s": 60.0, "max_invocations": 100.0},
                "t",
            )
        self.assertIn("changed since export", str(ctx.exception))

    def test_import_refuses_incomplete_bundle(self):
        with self.assertRaises(RuntimeError) as ctx:
            api.import_composite_op(
                self.root / "fresh",
                self.root / "nope",
                "X",
                {"max_cost_usd": 1.0, "max_time_s": 60.0, "max_invocations": 100.0},
                "t",
            )
        self.assertIn("no EXPORT.json", str(ctx.exception))

    def test_import_refuses_vague_grants(self):
        self._fused()
        bundle = self.root / "bundle"
        api.export_composite_op(self.state, "SC-F", bundle)
        with self.assertRaises(ValueError) as ctx:
            api.import_composite_op(
                self.root / "fresh", bundle, "X", {"max_cost_usd": 1.0}, "t"
            )
        self.assertIn("missing", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            api.import_composite_op(
                self.root / "fresh",
                bundle,
                "X",
                {"max_cost_usd": 1.0, "max_time_s": -5.0, "max_invocations": 100.0},
                "t",
            )
        self.assertIn("negative", str(ctx.exception))

    def test_proc_world_roundtrip_pins_reproduce(self):

        bdir = self.root / "bundles" / "thing"
        bdir.mkdir(parents=True)
        code = "open('out.txt','w').write('v\\n');print('done')"
        manifest = {
            "files": {},
            "steps": [
                {
                    "step": "one",
                    "argv": ["python3", "-c", code],
                    "declared_outputs": ["out.txt"],
                    "timeout_s": 60,
                }
            ],
        }
        (bdir / "MANIFEST.json").write_text(json.dumps(manifest))
        proot = self.root / "proot"
        created = api.create_proc_world(proot, "PW", bdir, reason="t")
        ran = api.run_procedure(proot, "PW", "thing", "K1")
        self.assertEqual(ran["executed"], ["one"])
        bundle = self.root / "pbundle"
        api.export_composite_op(proot, "PW", bundle)
        imp = api.import_composite_op(
            self.root / "pfresh",
            bundle,
            "PW2",
            {"max_cost_usd": 1.0, "max_time_s": 600.0, "max_invocations": 100.0},
            "t",
        )
        self.assertEqual(imp["procedures_verified"], ["thing"])
        # re-verified pins: staged bytes reproduce the advertised sha
        host, _ = api.open_run(self.root / "pfresh")
        table = host.worlds["PW2"].procedures
        self.assertEqual(table[0]["bundle_sha256"], created["bundle_sha256"])
        self.assertIn(str(self.root / "pfresh"), table[0]["manifest_ref"])
        # executes unmodified on the fresh dir
        ran2 = api.run_procedure(self.root / "pfresh", "PW2", "thing", "K2")
        self.assertEqual(ran2["executed"], ["one"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
