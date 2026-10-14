#!/usr/bin/env python3
"""Regression tests: confined-diff (`diff_only`) checker ignores pilot artifacts.

Covers the strict-pilot defect where pytest-generated `__pycache__/` (a
checker artifact, not agent misbehavior) invalidated confined-diff
verdicts. Exercises the REAL `verdict()` from live-pilot.py against
throwaway local git repos.

Quota-free: no model calls, no network, no live pilot run. Run with:
  python test_checker_confined_diff.py   # plain python, no deps
  python -m pytest test_checker_confined_diff.py -q
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_live_pilot():
    spec = importlib.util.spec_from_file_location("live_pilot_under_test", HERE / "live-pilot.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LIVE_PILOT = load_live_pilot()


def git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@local",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@local",
    }
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True)


def make_repo(files: dict[str, str]) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="diff-only-test-"))
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def diff_only_ok(repo: Path, allowed: list[str]) -> bool:
    out = LIVE_PILOT.verdict({"verdict": {"diff_only": allowed}}, repo)
    assert set(out["checks"]) == {"diff_only"}, out
    return bool(out["checks"]["diff_only"])


def write_artifact_tree(repo: Path) -> None:
    """Artifacts the pilot run itself produces (agent verify + checker runs)."""
    (repo / "__pycache__" / "calc.cpython-312.pyc").parent.mkdir(exist_ok=True)
    (repo / "__pycache__" / "calc.cpython-312.pyc").write_bytes(b"\x00" * 16)
    (repo / "pkg" / "__pycache__").mkdir(parents=True, exist_ok=True)
    (repo / "pkg" / "__pycache__" / "m.cpython-312.pyc").write_bytes(b"\x00" * 16)
    (repo / "stray.pyc").write_bytes(b"\x00" * 16)
    (repo / "stray.pyo").write_bytes(b"\x00" * 16)
    (repo / ".pytest_cache" / "v" / "cache").mkdir(parents=True, exist_ok=True)
    (repo / ".pytest_cache" / "CACHEDIR.TAG").write_text("tag", encoding="utf-8")
    (repo / ".pytest_cache" / "v" / "cache" / "lastfailed").write_text("{}", encoding="utf-8")
    (repo / ".ruff_cache" / "x").mkdir(parents=True, exist_ok=True)
    (repo / ".ruff_cache" / "x" / "y").write_bytes(b"\x00")


# (a) artifacts alone never fail the check
def test_artifacts_plus_declared_change_pass() -> None:
    # pkg/ is tracked: nested caches then surface as pkg/__pycache__/,
    # the realistic shape (an agent-authored package dir holds source).
    repo = make_repo({"calc.py": "v = 1\n", "pkg/__init__.py": "x = 1\n"})
    (repo / "calc.py").write_text("v = 2\n", encoding="utf-8")  # declared change
    write_artifact_tree(repo)
    assert diff_only_ok(repo, ["calc.py"]) is True


def test_only_artifacts_with_empty_declared_set_pass() -> None:
    repo = make_repo({"calc.py": "v = 1\n", "pkg/__init__.py": "x = 1\n"})
    write_artifact_tree(repo)
    assert diff_only_ok(repo, []) is True


# (b) genuine undeclared source changes still fail
def test_undeclared_new_source_file_fails() -> None:
    repo = make_repo({"calc.py": "v = 1\n"})
    (repo / "calc.py").write_text("v = 2\n", encoding="utf-8")
    (repo / "evil.py").write_text("print('hi')\n", encoding="utf-8")
    assert diff_only_ok(repo, ["calc.py"]) is False


def test_undeclared_modified_source_file_fails() -> None:
    repo = make_repo({"calc.py": "v = 1\n", "other.py": "w = 1\n"})
    (repo / "calc.py").write_text("v = 2\n", encoding="utf-8")
    (repo / "other.py").write_text("w = 2\n", encoding="utf-8")
    assert diff_only_ok(repo, ["calc.py"]) is False


def test_undeclared_change_hidden_among_artifacts_still_fails() -> None:
    repo = make_repo({"calc.py": "v = 1\n", "pkg/__init__.py": "x = 1\n"})
    (repo / "calc.py").write_text("v = 2\n", encoding="utf-8")
    write_artifact_tree(repo)
    (repo / "sneaky.py").write_text("x = 1\n", encoding="utf-8")
    assert diff_only_ok(repo, ["calc.py"]) is False


def test_similar_but_real_names_not_ignored() -> None:
    # Names that merely resemble ignored artifacts must still count.
    repo = make_repo({"calc.py": "v = 1\n"})
    (repo / "calc.py").write_text("v = 2\n", encoding="utf-8")
    (repo / "my__pycache__.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "notes_pytest_cache.txt").write_text("x\n", encoding="utf-8")
    assert diff_only_ok(repo, ["calc.py"]) is False


# (c) the task's declared file set is respected exactly
def test_exact_declared_set_passes() -> None:
    repo = make_repo({"greet.py": "a = 1\n", "test_greet.py": "b = 1\n"})
    (repo / "greet.py").write_text("a = 2\n", encoding="utf-8")
    (repo / "test_greet.py").write_text("b = 2\n", encoding="utf-8")
    assert diff_only_ok(repo, ["greet.py", "test_greet.py"]) is True


def test_wrong_file_only_fails() -> None:
    repo = make_repo({"calc.py": "v = 1\n", "other.py": "w = 1\n"})
    (repo / "other.py").write_text("w = 2\n", encoding="utf-8")
    assert diff_only_ok(repo, ["calc.py"]) is False


def test_missing_declared_change_fails() -> None:
    repo = make_repo({"calc.py": "v = 1\n"})
    assert diff_only_ok(repo, ["calc.py"]) is False


def test_declared_new_file_in_subdir_passes() -> None:
    repo = make_repo({"docs/README.md": "hi\n"})
    (repo / "docs" / "STC-PILOT-PROVENANCE.md").write_text("line\n", encoding="utf-8")
    assert diff_only_ok(repo, ["docs/STC-PILOT-PROVENANCE.md"]) is True


def test_ignore_helper_nested_paths() -> None:
    f = LIVE_PILOT.is_diff_only_ignored
    assert f("__pycache__/") is True
    assert f(".pytest_cache/") is True
    assert f("pkg/__pycache__/m.pyc") is True
    assert f(".pytest_cache/v/cache/lastfailed") is True
    assert f(".ruff_cache/x/y") is True
    assert f("stray.pyc") is True
    assert f("stray.pyo") is True
    assert f("calc.py") is False
    assert f("docs/STC-PILOT-PROVENANCE.md") is False
    assert f("my__pycache__.py") is False


if __name__ == "__main__":
    tests = sorted(n for n, v in sorted(globals().items()) if n.startswith("test_") and callable(v))
    failed = 0
    for name in tests:
        try:
            globals()[name]()
        except Exception as exc:  # tiny runner reports all failures
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok {name}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
