"""Guard the r5 feasibility fix: frozen run_tests.sh must use --capture=sys.

pytest's default fd-capture allocates TemporaryFiles; under the A3 profile
the tempdir falls back to the DrvFs case workdir, where unlink-while-open
destroys the handle (ENOENT at teardown, zero tests run). --capture=sys
keeps capture in-memory. See PREREGISTRATION amendment A4.
"""
from pathlib import Path

CASES = Path(__file__).resolve().parents[1] / "evidence/muse-20261011/cases"

CASE_IDS = ["C-A1", "C-B1", "C-C1", "E-D1", "E-E1", "E-E2", "F-A1", "F-B1",
            "F-C1", "I-A1", "I-B1", "I-C1", "M2-LIVE", "W-A1", "W-B1", "W-C1"]


def test_run_tests_uses_sys_capture():
    for case_id in CASE_IDS:
        script = CASES / case_id / "workdir/run_tests.sh"
        text = script.read_text(encoding="utf-8")
        invocations = [ln for ln in text.splitlines() if "-m pytest" in ln]
        assert len(invocations) == 1, f"{case_id}: expected 1 pytest line"
        line = invocations[0]
        assert "--capture=sys" in line, f"{case_id}: missing --capture=sys"
        assert "--capture=fd" not in line, f"{case_id}: fd-capture regressed"
