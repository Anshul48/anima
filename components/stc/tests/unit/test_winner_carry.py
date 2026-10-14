"""Winner-carry tests: the seeded CODEX_HOME carries reasoning-medium (P2-H3a).

Scripted proof (0 CLI calls) that `stc.cli._seed_codex_home` writes
`model_reasoning_effort = "medium"` into the seeded `config.toml` for the
gateway role, whatever the operator config holds. HOME is faked per test via
a monkeypatched `Path.home`; seeded homes are removed afterwards.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from stc.cli import _seed_codex_home

MEDIUM_LINE = 'model_reasoning_effort = "medium"'
OPERATOR_MAX_CFG = (
    'model = "gpt-5.6-luna"\n'
    'model_reasoning_effort = "max"\n'
    '[projects."/home/anshul"]\n'
    'trust_level = "trusted"\n'
)


def _make_fake_codex_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, config_text: str | None
) -> Path:
    """Point `Path.home()` at a fake HOME holding an operator codex login."""
    fake_home = tmp_path / "fake-home"
    dot_codex = fake_home / ".codex"
    dot_codex.mkdir(parents=True)
    (dot_codex / "auth.json").write_text('{"tokens": "fake"}\n', encoding="utf-8")
    if config_text is not None:
        (dot_codex / "config.toml").write_text(config_text, encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    return dot_codex


def test_seeded_config_replaces_max_with_medium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Max→medium replacement; every other operator line preserved verbatim."""
    dot_codex = _make_fake_codex_home(tmp_path, monkeypatch, config_text=OPERATOR_MAX_CFG)
    home = _seed_codex_home()
    assert home is not None
    try:
        seeded = (home / "config.toml").read_text(encoding="utf-8")
        assert seeded == OPERATOR_MAX_CFG.replace('model_reasoning_effort = "max"', MEDIUM_LINE)
        assert (home / "auth.json").read_bytes() == (dot_codex / "auth.json").read_bytes()
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_seeded_config_inserts_medium_when_key_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Medium line inserted at top; original bytes preserved after it."""
    operator_cfg = 'model = "gpt-5.6-luna"\n'
    _make_fake_codex_home(tmp_path, monkeypatch, config_text=operator_cfg)
    home = _seed_codex_home()
    assert home is not None
    try:
        seeded = (home / "config.toml").read_text(encoding="utf-8")
        assert seeded == MEDIUM_LINE + "\n" + operator_cfg
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_seeded_config_created_when_operator_config_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No operator config.toml → minimal seeded config carrying medium."""
    _make_fake_codex_home(tmp_path, monkeypatch, config_text=None)
    home = _seed_codex_home()
    assert home is not None
    try:
        seeded = (home / "config.toml").read_text(encoding="utf-8")
        assert seeded == MEDIUM_LINE + "\n"
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_seed_returns_none_without_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing auth.json still fails closed (None), unchanged semantics."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    assert _seed_codex_home() is None


def test_seeding_is_idempotent_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two seeds → distinct homes, both carry medium, both remove cleanly."""
    _make_fake_codex_home(tmp_path, monkeypatch, config_text='model_reasoning_effort = "max"\n')
    first = _seed_codex_home()
    second = _seed_codex_home()
    assert first is not None and second is not None
    assert first != second
    try:
        for home in (first, second):
            seeded = (home / "config.toml").read_text(encoding="utf-8")
            assert seeded == MEDIUM_LINE + "\n"
    finally:
        shutil.rmtree(first, ignore_errors=True)
        shutil.rmtree(second, ignore_errors=True)
    assert not first.exists()
    assert not second.exists()


def test_operator_login_bytes_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Seeding never writes back to the operator's ~/.codex files."""
    dot_codex = _make_fake_codex_home(tmp_path, monkeypatch, config_text=OPERATOR_MAX_CFG)
    auth_before = (dot_codex / "auth.json").read_bytes()
    home = _seed_codex_home()
    assert home is not None
    try:
        pass
    finally:
        shutil.rmtree(home, ignore_errors=True)
    assert (dot_codex / "config.toml").read_bytes() == OPERATOR_MAX_CFG.encode("utf-8")
    assert (dot_codex / "auth.json").read_bytes() == auth_before
