"""R3 mutmut-scope plumbing: derivation, config, empty-set, disposition (no live calls)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from stc.integration.dialectic_runner import (
    _measured_disposition,
    _mutmut_disposition,
    count_mutmut_runs,
    derive_mutation_paths,
)
from stc.schemas.models import ExecutionReceipt, GateReport
from stc.substrate.runner import (
    MutmutCounts,
    SubstrateRunner,
    _mutmut_cmd,
    _mutmut_targets_line,
    _parse_mutmut_counts,
    _patch_mutmut_config,
    _scoped_mutmut_tree,
    parse_mutmut_targets,
)

_BINDING = """diff --git a/src/stc/foo.py b/src/stc/foo.py
index 1111111..2222222 100644
--- a/src/stc/foo.py
+++ b/src/stc/foo.py
@@ -1 +1 @@
-old
+new
diff --git a/tests/unit/test_foo.py b/tests/unit/test_foo.py
index 3333333..4444444 100644
--- a/tests/unit/test_foo.py
+++ b/tests/unit/test_foo.py
@@ -1 +1 @@
-old
+new
diff --git a/src/stc/gone.py b/src/stc/gone.py
deleted file mode 100644
index 5555555..0000000
--- a/src/stc/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-gone
diff --git a/docs/notes.md b/docs/notes.md
index 6666666..7777777 100644
--- a/docs/notes.md
+++ b/docs/notes.md
@@ -1 +1 @@
-old
+new
diff --git a/src/stc/data.json b/src/stc/data.json
index 8888888..9999999 100644
--- a/src/stc/data.json
+++ b/src/stc/data.json
@@ -1 +1 @@
-old
+new
"""


def _receipt(mutmut_snippet: str, duration: float = 1.25, exit_code: int = 0) -> ExecutionReceipt:
    def _gate(name: str) -> GateReport:
        return GateReport(
            gate_name=name,
            exit_code=0,
            duration_seconds=0.5,
            violations_count=0,
            raw_output_snippet="ok",
        )

    return ExecutionReceipt(
        receipt_id="rc-r3",
        task_id="R3",
        epoch_index=1,
        commit_hash="abc",
        timestamp_utc="2026-09-20T00:00:00Z",
        python_version="3.12",
        os_platform="linux",
        gate_ruff=_gate("ruff"),
        gate_mypy=_gate("mypy"),
        gate_pytest=_gate("pytest"),
        gate_mutmut=GateReport(
            gate_name="mutmut",
            exit_code=exit_code,
            duration_seconds=duration,
            violations_count=0,
            raw_output_snippet=mutmut_snippet,
        ),
        sha256_signature="test-signature",
    )


def test_derive_keeps_production_py_only() -> None:
    """Derivation keeps src/stc/*.py; tests/docs/data/deletions dropped."""
    assert derive_mutation_paths(_BINDING.encode("utf-8")) == ["src/stc/foo.py"]


def test_derive_sorts_and_dedupes() -> None:
    """Derivation sorts and dedupes (multi-hunk files, quoted paths)."""
    diff = (
        "+++ b/src/stc/zeta.py\n"
        "+++ b/src/stc/alpha.py\n"
        "+++ b/src/stc/zeta.py\n"
        '+++ "b/src/stc/sp ace.py"\n'
    )
    assert derive_mutation_paths(diff.encode("utf-8")) == [
        "src/stc/alpha.py",
        "src/stc/sp ace.py",
        "src/stc/zeta.py",
    ]


def test_derive_empty_diff_yields_empty_set() -> None:
    """No production files (incl. test-only champions) derives to []."""
    assert derive_mutation_paths(b"") == []
    assert derive_mutation_paths(b"+++ b/tests/x.py\n") == []


_EXT_BINDING = """diff --git a/ledger_model.py b/ledger_model.py
index 1111111..2222222 100644
--- a/ledger_model.py
+++ b/ledger_model.py
@@ -1 +1 @@
-old
+new
diff --git a/ledger_report.py b/ledger_report.py
index 3333333..4444444 100644
--- a/ledger_report.py
+++ b/ledger_report.py
@@ -1 +1 @@
-old
+new
diff --git a/tests/test_ledger.py b/tests/test_ledger.py
index 5555555..6666666 100644
--- a/tests/test_ledger.py
+++ b/tests/test_ledger.py
@@ -1 +1 @@
-old
+new
diff --git a/docs/notes.md b/docs/notes.md
index 7777777..8888888 100644
--- a/docs/notes.md
+++ b/docs/notes.md
@@ -1 +1 @@
-old
+new
diff --git a/old_mod.py b/old_mod.py
deleted file mode 100644
index 9999999..0000000
--- a/old_mod.py
+++ /dev/null
@@ -1 +0,0 @@
-gone
"""


def test_derive_external_keeps_target_py_minus_tests(tmp_path: Path) -> None:
    """External targets scope to their own *.py minus tests/docs/deletions."""
    assert derive_mutation_paths(_EXT_BINDING.encode("utf-8"), target_root=tmp_path) == [
        "ledger_model.py",
        "ledger_report.py",
    ]


def test_derive_external_drops_test_shaped_files(tmp_path: Path) -> None:
    """test_*/conftest basenames are never production, anywhere in the tree."""
    diff = "+++ b/test_helper.py\n+++ b/pkg/foo_test.py\n+++ b/conftest.py\n+++ b/pkg/impl.py\n"
    assert derive_mutation_paths(diff.encode("utf-8"), target_root=tmp_path) == ["pkg/impl.py"]


def test_derive_external_tests_only_yields_empty_set(tmp_path: Path) -> None:
    """Test-only external champions still derive to [] (never-pass kept)."""
    assert derive_mutation_paths(b"+++ b/tests/x.py\n", target_root=tmp_path) == []


def test_derive_explicit_stc_root_keeps_legacy_filter() -> None:
    """An explicit STC-tree target_root keeps the src/stc/ filter exactly."""
    stc_root = Path(__file__).resolve().parents[2]
    assert derive_mutation_paths(_BINDING.encode("utf-8"), target_root=stc_root) == [
        "src/stc/foo.py"
    ]
    assert derive_mutation_paths(_EXT_BINDING.encode("utf-8"), target_root=stc_root) == []


def test_patch_config_replaces_paths_preserves_keys() -> None:
    """Config patch swaps path keys, preserves runner/tests_dir, forces deselect."""
    original = (
        "[tool.pytest.ini_options]\n"
        'markers = ["live: x"]\n'
        "\n"
        "[tool.mutmut]\n"
        'paths_to_mutate = ["src/stc/"]\n'
        'runner = "pytest"\n'
        'tests_dir = ["tests/"]\n'
        'pytest_add_cli_args = ["-x"]\n'
        "\n"
        "[tool.ruff]\n"
        "line-length = 100\n"
    )
    patched = _patch_mutmut_config(original, ["src/stc/a.py", "src/stc/b.py"])
    assert 'source_paths = ["src/stc/a.py", "src/stc/b.py"]' in patched
    assert "paths_to_mutate" not in patched
    assert 'runner = "pytest"' in patched
    assert "tests_dir" not in patched
    assert 'pytest_add_cli_args_test_selection = ["tests/"]' in patched
    assert 'pytest_add_cli_args = ["-m", "not live"]' in patched
    assert "[tool.pytest.ini_options]" in patched
    assert "[tool.ruff]" in patched


def test_patch_config_appends_missing_table_or_file() -> None:
    """Missing table appends; missing file yields a minimal runnable block."""
    no_table = "[tool.ruff]\nline-length = 100\n"
    patched = _patch_mutmut_config(no_table, ["src/stc/a.py"])
    assert patched.startswith(no_table)
    assert "[tool.mutmut]" in patched
    assert 'source_paths = ["src/stc/a.py"]' in patched
    assert 'runner = "pytest"' in patched
    assert 'pytest_add_cli_args_test_selection = ["tests/"]' in patched
    minimal = _patch_mutmut_config(None, ["src/stc/a.py"])
    assert minimal.startswith("[tool.mutmut]\n")
    assert 'source_paths = ["src/stc/a.py"]' in minimal
    assert 'runner = "pytest"' in minimal


def test_mutmut_cmd_shape() -> None:
    """Argv construction: interpreter -m mutmut run (scoping rides config)."""
    assert _mutmut_cmd() == [sys.executable, "-m", "mutmut", "run"]


def test_empty_set_fails_closed_without_execution(tmp_path: Path) -> None:
    """Empty mutation set: red NOT-MEASURED gate, zero counted runs."""
    if shutil.which("git") is None:
        pytest.skip("git required")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "seed",
        ],
        check=True,
    )
    runner = SubstrateRunner(timeout_per_gate=60.0, run_mutmut=True)
    receipt = runner.execute_gates(repo, task_id="R3-EMPTY", run_mutmut=True, paths_to_mutate=[])
    gate = receipt.gate_mutmut
    assert gate.exit_code != 0
    assert gate.violations_count >= 1
    assert "NOT-MEASURED" in (gate.raw_output_snippet or "")
    assert "empty mutation set" in (gate.raw_output_snippet or "")
    assert count_mutmut_runs(receipt) == 0
    assert _mutmut_disposition(True, receipt).startswith("not-run: NOT-MEASURED")


def test_counts_never_count_error_or_timeout_as_kill() -> None:
    """Timeouts stay in the denominator; errors/excluded stay out of the rate."""
    counts = _parse_mutmut_counts("Killed 7\nSurvived 1\nTimeout 2\nErrors 3\nSkipped 4\n")
    assert (counts.killed, counts.survived, counts.timeout) == (7, 1, 2)
    assert (counts.errors, counts.excluded) == (3, 4)
    assert counts.kill_rate == round(7 / 10, 4)
    assert isinstance(counts, MutmutCounts)


def test_counts_empty_output_yields_no_rate() -> None:
    """Zero judged mutants yields kill_rate None (caller fails closed)."""
    counts = _parse_mutmut_counts("no mutants were found here\n")
    assert counts.kill_rate is None
    assert counts.killed + counts.survived + counts.timeout == 0


def test_targets_line_roundtrip() -> None:
    """Targets line emits anchored fields the disposition re-parses."""
    counts = MutmutCounts(
        killed=7,
        survived=4,
        timeout=0,
        errors=0,
        excluded=0,
        kill_rate=0.6364,
        notests=3,
        reasons="notests=3;skipped=0;suspicious=0;typecheck=0",
    )
    line = _mutmut_targets_line(["src/stc/a.py", "src/stc/b.py"], counts, 0.85)
    assert line.startswith("[mutmut-targets] paths=src/stc/a.py,src/stc/b.py")
    fields = parse_mutmut_targets(line + "\nraw output here")
    assert fields is not None
    assert fields["paths"] == "src/stc/a.py,src/stc/b.py"
    assert fields["killed"] == "7"
    assert fields["notests"] == "3"
    assert fields["reasons"] == "notests=3;skipped=0;suspicious=0;typecheck=0"
    assert fields["rate"] == "63.64%"
    assert fields["threshold"] == "85.00%"
    assert parse_mutmut_targets("no targets here") is None


def test_progress_line_parse_last_wins() -> None:
    """Installed-mutmut progress line parses; last update wins; no-tests alive."""
    early = (
        "\r\u280b 1/4  \U0001f389 0 \U0001fae5 1  \u23f0 0  \U0001f914 0  "
        "\U0001f641 0  \U0001f507 0  \U0001f9d9 0"
    )
    final = (
        "\r\u280f 4/4  \U0001f389 1 \U0001fae5 3  \u23f0 0  \U0001f914 0  "
        "\U0001f641 0  \U0001f507 0  \U0001f9d9 0\n2.15 mutations/second\n"
    )
    counts = _parse_mutmut_counts(early + final)
    assert counts.killed == 1
    assert counts.survived == 3
    assert counts.notests == 3
    assert counts.timeout == 0
    assert counts.kill_rate == 0.25
    assert "notests=3" in counts.reasons


def test_progress_line_beats_legacy_text() -> None:
    """Emoji progress is authoritative; legacy regexes must not dilute it."""
    mixed = (
        "Killed 99 of 100\n"
        "\r\u280f 4/4  \U0001f389 1 \U0001fae5 3  \u23f0 0  \U0001f914 0  "
        "\U0001f641 0  \U0001f507 0  \U0001f9d9 0\n"
    )
    counts = _parse_mutmut_counts(mixed)
    assert (counts.killed, counts.survived) == (1, 3)


def test_measured_disposition_carries_paths_and_counts() -> None:
    """Counted scoped receipts dispose to measured with list + counts."""
    snippet = (
        "[mutmut-targets] paths=src/stc/a.py killed=7 survived=1 "
        "timeout=0 error=0 excluded=0 rate=87.50% threshold=85.00%\n"
        "Killed 7 of 8\n"
    )
    disp = _measured_disposition(_receipt(snippet))
    assert disp is not None
    assert disp.startswith("counted-once:measured:[mutmut-targets] paths=src/stc/a.py")
    assert "killed=7" in disp and "survived=1" in disp


def test_measured_disposition_absent_for_legacy_shape() -> None:
    """Legacy/unscoped receipts keep bare counted-once (no churn)."""
    assert _measured_disposition(_receipt("Killed 18 of 20\n")) is None


def test_disposition_empty_and_timeout_branches() -> None:
    """Empty-set and timeout snippets dispose to honest not-run."""
    empty = _receipt("MUTMUT NOT-MEASURED: empty mutation set (none); failing closed.")
    assert _mutmut_disposition(True, empty) == (
        "not-run: NOT-MEASURED (empty mutation set; never-pass)"
    )
    assert count_mutmut_runs(empty) == 0
    timeout = _receipt("Gate timed out", duration=120.0, exit_code=124)
    assert "timeout" in _mutmut_disposition(True, timeout)
    assert count_mutmut_runs(timeout) == 0


def test_scope_preseeds_src_docs_specs_not_tests(tmp_path: Path) -> None:
    """mutants/ pre-seed: src + docs + specs present, mutmut-owned untouched."""
    tree = tmp_path / "tree"
    (tree / "src" / "pkg").mkdir(parents=True)
    (tree / "src" / "pkg" / "sib.py").write_text("X = 1\n", encoding="utf-8")
    (tree / "docs" / "ev").mkdir(parents=True)
    (tree / "docs" / "ev" / "f.txt").write_text("fix\n", encoding="utf-8")
    (tree / "specs").mkdir(parents=True)
    (tree / "specs" / "sample_spec.md").write_text("# sample\n", encoding="utf-8")
    (tree / "tests").mkdir()
    (tree / "tests" / "t_test.py").write_text("def test_x() -> None:\n", encoding="utf-8")
    with _scoped_mutmut_tree(tree, ["src/pkg/sib.py"]) as scope:
        assert (scope / "mutants" / "src" / "pkg" / "sib.py").is_file()
        assert (scope / "mutants" / "docs" / "ev" / "f.txt").is_file()
        assert (scope / "mutants" / "specs" / "sample_spec.md").is_file()
        assert not (scope / "mutants" / "tests").exists()
        assert not (scope / "mutants" / "pyproject.toml").exists()
    assert not (scope / "mutants").exists()


def test_scope_mirror_bears_disposable_git(tmp_path: Path) -> None:
    """The scoped mirror commits its bytes: cwd detection stays in-lease."""
    if shutil.which("git") is None:
        pytest.skip("git required")
    tree = tmp_path / "tree"
    (tree / "src").mkdir(parents=True)
    (tree / "src" / "a.py").write_text("X = 1\n", encoding="utf-8")
    with _scoped_mutmut_tree(tree, ["src/a.py"]) as scope:
        assert (scope / ".git").is_dir()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=scope,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert len(head) == 40
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=scope / "mutants",
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert Path(top).resolve() == scope.resolve()
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=scope,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert branch == "main"


def _external_tree(tmp_path: Path) -> Path:
    tree = tmp_path / "ext"
    (tree / "fixtures").mkdir(parents=True)
    (tree / "fixtures" / "sample.csv").write_text("a,b\n", encoding="utf-8")
    (tree / "data.txt").write_text("data\n", encoding="utf-8")
    (tree / "mod.py").write_text("X = 1\n", encoding="utf-8")
    (tree / "tests").mkdir()
    (tree / "tests" / "test_mod.py").write_text("def test_x() -> None:\n", encoding="utf-8")
    (tree / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return tree


def test_scope_preseeds_external_data_not_owned(tmp_path: Path) -> None:
    """External pre-seed: data subtrees + data files present, owned untouched."""
    tree = _external_tree(tmp_path)
    with _scoped_mutmut_tree(tree, ["mod.py"], external_target=True) as scope:
        assert (scope / "mutants" / "fixtures" / "sample.csv").is_file()
        assert (scope / "mutants" / "data.txt").is_file()
        assert not (scope / "mutants" / "tests").exists()
        assert not (scope / "mutants" / "pyproject.toml").exists()
        # Scoped .py is pre-seeded as the inert original; mutmut overwrites
        # what it owns (trampolines) when it seeds.
        assert (scope / "mutants" / "mod.py").is_file()


def test_scope_preseeds_external_unscoped_py_sibling(tmp_path: Path) -> None:
    """Partial scope keeps untouched-but-imported .py siblings visible."""
    tree = _external_tree(tmp_path)
    (tree / "sibling.py").write_text("Y = 2\n", encoding="utf-8")
    with _scoped_mutmut_tree(tree, ["mod.py"], external_target=True) as scope:
        assert (scope / "mutants" / "sibling.py").is_file()
        assert (scope / "mutants" / "sibling.py").read_text(encoding="utf-8") == "Y = 2\n"
        assert not (scope / "mutants" / "tests").exists()
        assert not (scope / "mutants" / "pyproject.toml").exists()


def test_scope_legacy_preseed_ignores_external_data(tmp_path: Path) -> None:
    """Default (STC) pre-seed keeps the pinned list: no fixtures seeding."""
    tree = _external_tree(tmp_path)
    with _scoped_mutmut_tree(tree, ["mod.py"]) as scope:
        assert not (scope / "mutants" / "fixtures").exists()
        assert not (scope / "mutants" / "data.txt").exists()
