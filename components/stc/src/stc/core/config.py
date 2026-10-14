"""STC settings and configuration management using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration settings for the STC engine."""

    model_config = SettingsConfigDict(
        env_prefix="STC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "stc"
    environment: str = "development"
    log_level: str = "INFO"
    log_format: str = "rich"
    root_dir: Path = Path()
    workspace_root: Path = Path()
    artifacts_dir: Path = Path("artifacts")
    trace_db_path: Path = Path("../trace/data/trace.db")
    worktree_root: Path = Path("./worktrees")
    receipts_dir: Path = Path("./artifacts/receipts")

    # Concurrency and timeout controls
    max_concurrency: int = Field(default=4, gt=0)
    default_timeout_seconds: float = Field(default=30.0, gt=0.0)

    # Budget ceilings
    max_bundle_bytes: int = Field(default=25600, gt=0)  # 25KB hard ceiling
    worktree_ttl_seconds: int = Field(default=3600, gt=0)  # 1 hour lease TTL
    max_epoch_retries: int = Field(default=3, ge=1)


@lru_cache
def get_settings() -> Settings:
    """Returns a cached singleton instance of runtime settings."""
    return Settings()
