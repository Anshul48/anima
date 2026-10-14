"""Runtime configuration: explicit storage root, store, policy, and sources.

One configuration object supplies CLI, HTTP, journal, policy, and user
controls. When a runtime root is configured there is NO in-memory default:
the SQLite store, consent grants, corrections, and audit log are all
persisted under the root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass(frozen=True)
class SourceSpec:
    """One configured source adapter to run under the source lifecycle."""

    name: str
    adapter: str  # registry key, e.g. "dev-task-inbox"
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeConfig:
    """Explicit runtime configuration shared by serve and CLI."""

    storage_root: Path
    source_id: str = "entorhinal.dev-task.01"
    db_filename: str = "evidence.db"
    journal_filename: str = "evidence_journal.jsonl"
    auth_filename: str = "auth_principals.json"
    write_queue_size: int = 1000
    default_allow: bool = False
    sources: List[SourceSpec] = field(default_factory=list)

    @staticmethod
    def from_root(
        storage_root: Union[str, Path],
        source_id: str = "entorhinal.dev-task.01",
        sources: Optional[List[SourceSpec]] = None,
        **kwargs: Any,
    ) -> "RuntimeConfig":
        return RuntimeConfig(
            storage_root=Path(storage_root),
            source_id=source_id,
            sources=list(sources or []),
            **kwargs,
        )

    @property
    def db_path(self) -> Path:
        return self.storage_root / self.db_filename

    @property
    def journal_path(self) -> Path:
        return self.storage_root / self.journal_filename

    @property
    def auth_path(self) -> Path:
        return self.storage_root / self.auth_filename

    def ensure_root(self) -> Path:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        return self.storage_root
