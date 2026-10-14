"""Sensitivity and composition tests for P01 candidate identity."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from stc.integration.identity import (
    FORMULA_VERSION,
    IdentityError,
    IntegrationError,
    candidate_identity,
    compose_identity_map,
    digest_record,
    repo_identity_record,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git-required env (packet limit)"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        timeout=60,
    )


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "p01@test")
    _git(repo, "config", "user.name", "p01")
    (repo / "main.py").write_text("print('hi')\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def test_identity_stable_across_calls(repo_root: Path) -> None:
    assert candidate_identity(repo_root) == candidate_identity(repo_root)
    assert candidate_identity(str(repo_root)) == candidate_identity(repo_root)


def test_tracked_content_mutation_flips_and_reverts(repo_root: Path) -> None:
    before = candidate_identity(repo_root)
    (repo_root / "main.py").write_text("print('changed')\n")
    assert candidate_identity(repo_root) != before
    (repo_root / "main.py").write_text("print('hi')\n")
    assert candidate_identity(repo_root) == before


def test_staged_change_flips(repo_root: Path) -> None:
    """`git diff HEAD` covers the index too, not just the worktree."""
    before = candidate_identity(repo_root)
    (repo_root / "main.py").write_text("print('staged')\n")
    _git(repo_root, "add", "-A")
    assert candidate_identity(repo_root) != before


def test_untracked_py_flips_and_reverts(repo_root: Path) -> None:
    before = candidate_identity(repo_root)
    extra = repo_root / "extra.py"
    extra.write_text("X = 1\n")
    assert candidate_identity(repo_root) != before
    extra.unlink()
    assert candidate_identity(repo_root) == before


def test_untracked_nested_dir_expanded(repo_root: Path) -> None:
    before = candidate_identity(repo_root)
    nested = repo_root / "docs" / "new"
    nested.mkdir(parents=True)
    (nested / "note.md").write_text("# hello\n")
    assert candidate_identity(repo_root) != before


@pytest.mark.parametrize("name", ["notes.txt", "app.log", "data.yml", "mod.pyc", "run.sh"])
def test_fixed_glob_list_ignores_other_suffixes(repo_root: Path, name: str) -> None:
    """P00 fixed globs only (.py/.md/.yaml/.json/.toml/.cfg/.ini)."""
    before = candidate_identity(repo_root)
    (repo_root / name).write_text("untracked noise\n")
    assert candidate_identity(repo_root) == before


@pytest.mark.parametrize("name", ["u.py", "u.md", "u.yaml", "u.json", "u.toml", "u.cfg", "u.ini"])
def test_fixed_glob_list_hashes_each_suffix(repo_root: Path, name: str) -> None:
    before = candidate_identity(repo_root)
    (repo_root / name).write_text("tracked-by-identity\n")
    assert candidate_identity(repo_root) != before


def test_record_shape_and_env_keys(repo_root: Path) -> None:
    record = repo_identity_record(repo_root)
    assert record["formula_version"] == FORMULA_VERSION
    assert len(record["head"]) == 40
    assert len(record["diff_sha256"]) == 64
    assert record["diff_bytes"] == 0
    assert record["untracked"] == {}
    assert set(record["env"]) == {"python_version", "os", "pip_digest"}
    assert tuple(int(part) for part in record["env"]["python_version"].split(".")[:2]) >= (3, 12)
    pip_digest = record["env"]["pip_digest"]
    assert len(pip_digest) == 64 or pip_digest.startswith("UNAVAILABLE:")
    assert digest_record(record) == candidate_identity(repo_root)


def test_digest_excludes_checkout_location(repo_root: Path) -> None:
    """Identity is content-based: the root path does not feed the digest."""
    record = repo_identity_record(repo_root)
    tampered = dict(record)
    tampered["root"] = "/somewhere/else"
    assert digest_record(tampered) == digest_record(record)


def test_digest_sensitive_to_env_change(repo_root: Path) -> None:
    """Pure composition check: an env difference flips the digest."""
    record = repo_identity_record(repo_root)
    other = json.loads(json.dumps(record))
    other["env"]["python_version"] = "9.9.9"
    assert digest_record(other) != digest_record(record)


def test_digest_rejects_incomplete_record() -> None:
    with pytest.raises(IdentityError, match="missing digest key"):
        digest_record({"head": "x"})


def test_non_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(IdentityError):
        candidate_identity(tmp_path / "proj")


def test_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(IdentityError, match="not a directory"):
        candidate_identity(tmp_path / "nope")


def test_identity_error_is_integration_error() -> None:
    assert issubclass(IdentityError, IntegrationError)


def test_compose_map_shape_and_composite(repo_root: Path, tmp_path: Path) -> None:
    second = tmp_path / "other"
    shutil.copytree(repo_root, second)
    (second / "extra.md").write_text("# fork\n")
    text = compose_identity_map({"a": repo_root, "b": second})
    doc: dict[str, Any] = json.loads(text)
    assert doc["formula_version"] == FORMULA_VERSION
    assert set(doc["roots"]) == {"a", "b"}
    assert doc["roots"]["a"]["identity"] == candidate_identity(repo_root)
    assert doc["roots"]["b"]["identity"] == candidate_identity(second)
    assert doc["roots"]["a"]["identity"] != doc["roots"]["b"]["identity"]
    assert len(doc["composite_identity"]) == 64
    # Deterministic: insertion order must not matter.
    assert compose_identity_map({"b": second, "a": repo_root}) == text


def test_compose_map_rejects_empty() -> None:
    with pytest.raises(IdentityError, match="zero roots"):
        compose_identity_map({})
