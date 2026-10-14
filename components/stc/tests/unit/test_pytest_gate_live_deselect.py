"""Gate-3 live deselection: `@pytest.mark.live` never collects in gate runs (D13/G2)."""

from pathlib import Path

from stc.substrate.runner import SubstrateRunner


def _write_gate_tree(root: Path) -> None:
    """Fixture lease tree: one live test that must never run + one passing test."""
    root.mkdir(exist_ok=True)
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'markers = ["live: live CLI-harness tests, deselected in gate runs (D13)"]\n',
        encoding="utf-8",
    )
    # Fail-safe live probe: if the gate ever collects it, the gate fails (exit != 0)
    # instead of firing a live call — a broken filter is loud, never silent spend.
    (root / "test_live_probe.py").write_text(
        "import pytest\n"
        "\n"
        "@pytest.mark.live\n"
        "def test_live_must_not_run_in_gate() -> None:\n"
        '    raise AssertionError("live test collected in gate run")\n',
        encoding="utf-8",
    )
    (root / "test_ok.py").write_text("def test_ok() -> None:\n    assert True\n", encoding="utf-8")


def test_gate_pytest_deselects_live_marked_tests(tmp_path: Path) -> None:
    """Verify Gate 3 deselects `@pytest.mark.live` (D13): gate green, live unrun."""
    tree = tmp_path / "live_deselect_repo"
    _write_gate_tree(tree)
    runner = SubstrateRunner(timeout_per_gate=120.0)
    report = runner._run_gate_pytest(tree)
    assert report.exit_code == 0
    assert report.violations_count == 0
    assert "1 passed" in report.raw_output_snippet
    assert "1 deselected" in report.raw_output_snippet


def test_gate_pytest_live_skip_cannot_trip_zero_skip_invariant(tmp_path: Path) -> None:
    """Verify a skipping live test cannot trip the 0-skipped invariant (D13/G2)."""
    tree = tmp_path / "live_skip_repo"
    _write_gate_tree(tree)
    (tree / "test_live_probe.py").write_text(
        "import pytest\n"
        "\n"
        "@pytest.mark.live\n"
        "def test_live_skip_if_run() -> None:\n"
        "    pytest.skip('operator login absent')\n",
        encoding="utf-8",
    )
    runner = SubstrateRunner(timeout_per_gate=120.0)
    report = runner._run_gate_pytest(tree)
    assert report.exit_code == 0
    assert report.violations_count == 0
    assert "0 skipped" in report.raw_output_snippet
