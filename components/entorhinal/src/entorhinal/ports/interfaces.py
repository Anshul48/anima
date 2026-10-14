"""Abstract Port Interfaces for Entorhinal.

Ports decouple the core epistemic engine from concrete external systems:
- SourcePort: Interface for capturing passive, permitted OS/Browser/PTY signals.
- MemoryPort: Interface for append-only evidence persistence and replay.
- QueryPort: Interface for advisory snapshot issuance to downstream consumers.
- UserControlPort: Interface for user overrides, consent lifecycle, and tombstoning.

Invariant: Ports contain zero third-party transport or database dependencies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from entorhinal.schemas.models import (
    ContextRequest,
    ContextSnapshot,
    DerivedFact,
    EvidenceRecord,
    FactExplanation,
    RawSignalEvent,
    SourceType,
    TombstoneRecord,
    UserCorrection,
)


class SourcePort(ABC):
    """Abstract interface for permitted source capture adapters."""

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this source adapter."""
        pass

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """Source type category produced by this adapter."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start signal ingestion."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop signal ingestion."""
        pass

    @abstractmethod
    async def poll_signals(self) -> List[RawSignalEvent]:
        """Poll queued ephemeral signals from volatile memory buffer."""
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check operational health status of the adapter."""
        pass


class MemoryPort(ABC):
    """Abstract interface for local append-only evidence storage and replay."""

    @abstractmethod
    async def append_evidence(self, record: EvidenceRecord) -> str:
        """Persist an immutable EvidenceRecord to the journal.

        Returns the sealed record_id.
        """
        pass

    @abstractmethod
    async def get_evidence(self, record_id: str) -> Optional[EvidenceRecord]:
        """Retrieve a specific EvidenceRecord by UUIDv7 ID."""
        pass

    @abstractmethod
    async def scan_evidence(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        source_type: Optional[SourceType] = None,
        limit: int = 1000,
    ) -> List[EvidenceRecord]:
        """Scan evidence records within an optional time range or filter."""
        pass

    @abstractmethod
    async def apply_tombstone(self, tombstone: TombstoneRecord) -> bool:
        """Cryptographically overwrite an evidence record with a tombstone."""
        pass

    @abstractmethod
    async def get_last_hash(self) -> str:
        """Get the latest SHA-256 hash in the journal chain (or genesis hash)."""
        pass

    @abstractmethod
    async def count_records(self) -> int:
        """Return the total number of journal records stored."""
        pass


class QueryPort(ABC):
    """Abstract interface for purpose-bounded context queries."""

    @abstractmethod
    async def request_snapshot(self, request: ContextRequest) -> ContextSnapshot:
        """Evaluate policy and synthesize a bounded ContextSnapshot for an approved consumer."""
        pass

    @abstractmethod
    async def explain_fact(self, fact_id: str) -> Optional[FactExplanation]:
        """Provide audit provenance explanation for a derived fact."""
        pass

    @abstractmethod
    async def query_facts(
        self,
        entity_uri: Optional[str] = None,
        attribute: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[DerivedFact]:
        """Query active derived facts by entity or attribute filter."""
        pass


class UserControlPort(ABC):
    """Abstract interface for human user commands, overrides, and privacy control."""

    @abstractmethod
    async def submit_correction(self, correction: UserCorrection) -> bool:
        """Apply an explicit user correction override lock."""
        pass

    @abstractmethod
    async def grant_consent(
        self,
        source_type: SourceType,
        app_pattern: str,
        domain_pattern: str,
    ) -> str:
        """Add a permitted consent rule. Returns created rule ID."""
        pass

    @abstractmethod
    async def revoke_consent(self, rule_id: str) -> bool:
        """Revoke an active consent rule."""
        pass

    @abstractmethod
    async def request_deletion(
        self,
        time_range_start: Optional[datetime] = None,
        time_range_end: Optional[datetime] = None,
        domain: Optional[str] = None,
        app_identifier: Optional[str] = None,
    ) -> int:
        """Execute cascade cryptographic tombstoning across journal and projections.

        Returns the count of tombstoned records.
        """
        pass

    @abstractmethod
    async def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent policy and query audit events."""
        pass
