"""Configuration schemas and persistence for Entorhinal and AI / LLM tiers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import yaml
from dotenv import dotenv_values, set_key
from pydantic import BaseModel, Field


class AIConfig(BaseModel):
    """Configuration for AI & LLM integration tier (LiteLLM + Local Ollama)."""

    enabled: bool = Field(default=True, description="Enable or disable AI / LLM integration")
    mode: str = Field(default="hybrid", description="Operating mode: 'hybrid', 'local', or 'cloud'")
    allow_cloud: bool = Field(
        default=True,
        description="Strict air-gap flag. If False, cloud model requests are strictly rejected.",
    )

    # Primary Model (Local or Cloud)
    primary_model: str = Field(
        default="ollama/qwen3.8:27b",
        description="LiteLLM model identifier for primary inference (e.g. 'ollama/qwen3.8:27b')",
    )
    api_base: Optional[str] = Field(
        default="http://localhost:11434",
        description="API Base URL for local model server (Ollama, vLLM, LM Studio)",
    )
    api_key_env: Optional[str] = Field(
        default=None,
        description="Environment variable name containing the primary API key",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Direct API key (optional, preferred to use environment variables)",
    )

    # Fallback Model (Cloud or secondary local)
    fallback_model: Optional[str] = Field(
        default="gemini/gemini-2.5-flash",
        description="LiteLLM model identifier for fallback if primary times out or fails",
    )
    fallback_api_base: Optional[str] = Field(
        default=None,
        description="API Base URL for fallback model if using custom endpoint",
    )
    fallback_api_key_env: Optional[str] = Field(
        default="GEMINI_API_KEY",
        description="Environment variable name containing the fallback API key",
    )
    fallback_api_key: Optional[str] = Field(
        default=None,
        description="Direct fallback API key",
    )

    # Embedding Model for semantic clustering
    embedding_model: str = Field(
        default="ollama/nomic-embed-text",
        description="Model identifier for generating text embeddings",
    )
    embedding_api_base: Optional[str] = Field(
        default="http://localhost:11434",
        description="API Base URL for embedding server",
    )

    # Inference hyperparameters
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    timeout_seconds: float = Field(default=15.0, gt=0.0)
    max_retries: int = Field(default=2, ge=0)


class SourcesConfig(BaseModel):
    """Source adapter enablement flags."""

    enable_os_window: bool = Field(default=True, description="Capture active OS window titles and focus switches")
    enable_terminal_pty: bool = Field(default=True, description="Capture terminal CLI commands and exit codes")
    enable_browser: bool = Field(default=True, description="Capture browser DOM/CDP page context (opt-in)")


class PolicyConfig(BaseModel):
    """Privacy and pre-egress redaction policies."""

    redact_pii_before_cloud_egress: bool = Field(
        default=True,
        description="Deterministic redaction of API keys, tokens, emails, and credentials before cloud dispatch",
    )
    drop_unpermitted_domains: bool = Field(
        default=True,
        description="Drop capture events from non-whitelisted or blacklisted domains",
    )
    excluded_applications: List[str] = Field(
        default_factory=lambda: [
            "1Password",
            "Bitwarden",
            "KeePass",
            "KeePassXC",
            "Windows Security",
            "Credential Manager",
            "Enpass",
            "Dashlane",
        ],
        description="Application window titles/names excluded from capture",
    )
    excluded_domains: List[str] = Field(
        default_factory=lambda: [
            "*bank*",
            "*paypal*",
            "*stripe*",
            "*login*",
            "*signin*",
            "*auth*",
            "*chase*",
            "*fidelity*",
            "*wellsfargo*",
            "*schwab*",
        ],
        description="Domain wildcards excluded from capture",
    )


class DaemonConfig(BaseModel):
    """Daemon and IPC transport configurations."""

    host: str = Field(default="127.0.0.1", description="Loopback host address")
    port: int = Field(default=8000, description="REST API server port")
    named_pipe_path: str = Field(
        default=r"\\.\pipe\entorhinal_vnext",
        description="Windows Named Pipe path for vNext provider",
    )


class EntorhinalConfig(BaseModel):
    """Root configuration object for Entorhinal Contextual Intelligence System."""

    version: str = Field(default="1.0")
    storage_dir: str = Field(default="~/.entorhinal")
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)

    def get_resolved_storage_dir(self) -> Path:
        """Resolve storage directory expanding home user path."""
        path = Path(os.path.expanduser(self.storage_dir)).resolve()
        return path

    @classmethod
    def load_from_dir(cls, directory: Optional[Path | str] = None) -> "EntorhinalConfig":
        """Load configuration from config.yaml in the specified or default directory."""
        base_dir = (
            Path(directory).resolve()
            if directory
            else Path.home() / ".entorhinal"
        )
        config_path = base_dir / "config.yaml"
        env_path = base_dir / ".env"

        # Load environment variables if .env exists
        if env_path.exists():
            env_vars = dotenv_values(env_path)
            for k, v in env_vars.items():
                if v is not None and k not in os.environ:
                    os.environ[k] = v

        if not config_path.exists():
            return cls(storage_dir=str(base_dir))

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls.model_validate(data)

    def save_to_dir(self, directory: Optional[Path | str] = None) -> Path:
        """Save configuration to config.yaml in the target directory."""
        base_dir = (
            Path(directory).resolve()
            if directory
            else self.get_resolved_storage_dir()
        )
        base_dir.mkdir(parents=True, exist_ok=True)
        config_path = base_dir / "config.yaml"

        data = self.model_dump(mode="json")
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return config_path


def save_env_secret(storage_dir: Path, key: str, value: str) -> None:
    """Save an API key or secret to the .env file in storage directory."""
    storage_dir.mkdir(parents=True, exist_ok=True)
    env_file = storage_dir / ".env"
    if not env_file.exists():
        env_file.touch(mode=0o600)
    set_key(str(env_file), key, value)
    os.environ[key] = value
