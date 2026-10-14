"""Unit tests for Entorhinal Interactive Setup Wizard and initialization routines."""

from pathlib import Path
import pytest
from typer.testing import CliRunner

from entorhinal.ai.config import EntorhinalConfig
from entorhinal.cli.init_wizard import InteractiveSetupWizard
from entorhinal.cli.main import app

runner = CliRunner()


def test_wizard_non_interactive_hybrid(tmp_path: Path):
    """Test non-interactive wizard run in hybrid mode."""
    wizard = InteractiveSetupWizard(target_dir=str(tmp_path))
    config = wizard.run_non_interactive(
        storage_dir=str(tmp_path),
        mode="hybrid",
        primary_model="ollama/qwen3.8:27b",
        fallback_model="gemini/gemini-2.5-flash",
    )

    assert config.storage_dir == str(tmp_path)
    assert config.ai.mode == "hybrid"
    assert config.ai.primary_model == "ollama/qwen3.8:27b"
    assert config.ai.fallback_model == "gemini/gemini-2.5-flash"
    assert config.ai.allow_cloud is True

    # Assert storage directories and files exist
    assert (tmp_path / "config.yaml").exists()
    assert (tmp_path / "evidence_journal.jsonl").exists()
    assert (tmp_path / "backups").is_dir()
    assert (tmp_path / "indices").is_dir()
    assert (tmp_path / "logs").is_dir()


def test_wizard_non_interactive_local_only(tmp_path: Path):
    """Test non-interactive wizard run in local-only air-gapped mode."""
    wizard = InteractiveSetupWizard(target_dir=str(tmp_path))
    config = wizard.run_non_interactive(
        storage_dir=str(tmp_path),
        mode="local",
        primary_model="ollama/llama3.2:3b",
        allow_cloud=False,
    )

    assert config.ai.mode == "local"
    assert config.ai.allow_cloud is False
    assert config.ai.fallback_model is None
    assert (tmp_path / "config.yaml").exists()


def test_cli_init_quick_command(tmp_path: Path):
    """Test 'entorhinal init --quick' Typer CLI command."""
    result = runner.invoke(
        app,
        ["init", "--quick", "--dir", str(tmp_path), "--hybrid"],
    )
    assert result.exit_code == 0
    assert "Quick initialization complete!" in result.stdout

    # Verify loaded config from disk
    loaded = EntorhinalConfig.load_from_dir(tmp_path)
    assert loaded.ai.mode == "hybrid"
    assert (tmp_path / "config.yaml").exists()


def test_cli_status_with_ai_config(tmp_path: Path):
    """Test 'entorhinal status' displays AI configuration when config.yaml is present."""
    wizard = InteractiveSetupWizard(target_dir=str(tmp_path))
    wizard.run_non_interactive(storage_dir=str(tmp_path), mode="hybrid")

    result = runner.invoke(app, ["status", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "AI Mode" in result.stdout
    assert "Primary Model" in result.stdout
    assert "HYBRID" in result.stdout
