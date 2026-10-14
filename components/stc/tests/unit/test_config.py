"""Unit tests for STC Settings and configuration management."""

import pytest
from pydantic import ValidationError

from stc.core.config import Settings, get_settings


def test_default_settings() -> None:
    """Verify default settings instantiation."""
    settings = Settings()
    assert settings.app_name == "stc"
    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.max_concurrency == 4
    assert settings.default_timeout_seconds == 30.0


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify settings override via STC_ prefixed environment variables."""
    monkeypatch.setenv("STC_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("STC_MAX_CONCURRENCY", "8")
    monkeypatch.setenv("STC_DEFAULT_TIMEOUT_SECONDS", "15.5")
    monkeypatch.setenv("STC_ENVIRONMENT", "production")

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.log_level == "DEBUG"
    assert settings.max_concurrency == 8
    assert settings.default_timeout_seconds == 15.5
    assert settings.environment == "production"
    get_settings.cache_clear()


def test_invalid_concurrency_validation() -> None:
    """Verify validation boundaries on numeric settings."""
    with pytest.raises(ValidationError):
        Settings(max_concurrency=0)

    with pytest.raises(ValidationError):
        Settings(default_timeout_seconds=-1.0)
