"""Pytest configuration and shared fixtures for STC tests."""

from pathlib import Path

import pytest

from stc.core.config import Settings
from stc.schemas.models import TaskPriority, TaskSpec
from stc.services.engine import STCEngine


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Fixture providing a temporary repository directory."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary workspace path."""
    return tmp_path


@pytest.fixture
def test_settings(temp_workspace: Path) -> Settings:
    """Fixture providing testing settings bounded to a temporary workspace."""
    return Settings(
        environment="test",
        log_level="DEBUG",
        max_concurrency=2,
        default_timeout_seconds=5.0,
        workspace_root=temp_workspace,
        artifacts_dir=Path("artifacts"),
    )


@pytest.fixture
def engine(test_settings: Settings) -> STCEngine:
    """Fixture providing an STCEngine instance backed by the test settings."""
    return STCEngine(test_settings)


@pytest.fixture
def sample_task_spec() -> TaskSpec:
    """Fixture providing a standard valid TaskSpec."""
    return TaskSpec(
        name="test-ping-task",
        action="ping",
        priority=TaskPriority.HIGH,
        payload={"echo": "hello world"},
    )
