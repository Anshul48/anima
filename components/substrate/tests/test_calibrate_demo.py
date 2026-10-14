# Copyright 2026 Anshul48
# SPDX-License-Identifier: Apache-2.0
"""Maintained calibration + J1-demo regression tests (package-new).

calibrate.py's 2.61x is re-proven live (not carried on faith), and
the J1 journey demo holds 10/10 PASS through the installed entry
point.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
TMPROOT = Path(tempfile.mkdtemp(prefix="anima-substrate-tests-"))

from anima_substrate.host import calibrate  # noqa: E402


class TestCalibrate(unittest.TestCase):
    def test_ratio_reproven_live(self):
        scratch = TMPROOT / "calibrate"
        if scratch.exists():
            shutil.rmtree(scratch)
        rep = calibrate.calibrate(scratch)
        self.addCleanup(shutil.rmtree, scratch, True)
        self.assertEqual(rep["central_lane"]["central_bytes"], 810)
        self.assertEqual(rep["local_lane"]["central_bytes"], 310)
        self.assertEqual(rep["ratio_central_over_local"], 2.61)
        # the non-claim travels with the number
        self.assertIn("token", rep["not_claimed"])


class TestJ1Demo(unittest.TestCase):
    def test_j1_demo_10_of_10(self):
        root = TMPROOT / "j1demo"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "anima_substrate.demos.j1_demo",
                f"--state-dir={root}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
        self.assertIn("J1 journey: OK (10/10 PASS)", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
