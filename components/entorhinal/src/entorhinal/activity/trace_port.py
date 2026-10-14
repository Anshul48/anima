"""Future optional Trace integration port (not a prerequisite).

Trace is unfinished. Activity tracking, classification, and discovery work
fully without it. When a real Trace contract exists, main can plug a
``TraceOrganizerPort`` implementation here to organize/enrich activity
snapshots — enrichment must preserve session/span/label/connection identity
and provenance, which ``validate_enrichment`` enforces. Until then,
``NullTraceOrganizer`` (the default) is an explicit, honest no-op.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol

from pydantic import BaseModel, ConfigDict, Field


class TraceEnrichment(BaseModel):
    """Optional Trace-supplied organization layered over activity state."""

    model_config = ConfigDict(extra="forbid")

    organizer_id: str = Field(..., min_length=1)
    notes: List[str] = Field(default_factory=list)
    extra_connections: List[Dict[str, Any]] = Field(default_factory=list)
    preserved_ids: List[str] = Field(default_factory=list)


class TraceOrganizerPort(Protocol):
    """Contract a future Trace adapter implements (main plugs it in)."""

    @property
    def organizer_id(self) -> str:
        """Stable organizer identity (e.g. 'trace/1')."""
        ...  # pragma: no cover

    def organize(self, snapshot: Dict[str, Any]) -> TraceEnrichment:
        """Organize/enrich an activity snapshot without rewriting identity."""
        ...  # pragma: no cover


def validate_enrichment(
    snapshot_ids: List[str], enrichment: TraceEnrichment
) -> List[str]:
    """Check an enrichment preserves identity; returns violation messages."""
    violations: List[str] = []
    preserved = set(enrichment.preserved_ids)
    for snapshot_id in snapshot_ids:
        if snapshot_id not in preserved:
            violations.append(f"trace dropped id {snapshot_id}")
    for index, connection in enumerate(enrichment.extra_connections):
        if not isinstance(connection, dict):
            violations.append(f"extra_connections[{index}] is not an object")
            continue
        if "kind" not in connection or "evidence" not in connection:
            violations.append(f"extra_connections[{index}] lacks kind/evidence")
    return violations


class NullTraceOrganizer:
    """Default organizer: explicit no-op preserving everything."""

    @property
    def organizer_id(self) -> str:
        return "trace-null/1"

    def organize(self, snapshot: Dict[str, Any]) -> TraceEnrichment:
        ids = [str(v) for v in snapshot.get("ids", [])]
        return TraceEnrichment(
            organizer_id=self.organizer_id,
            notes=["trace integration not configured; activity state unchanged"],
            preserved_ids=ids,
        )


class RecordingTraceOrganizer:
    """Test double recording the snapshots it was offered."""

    def __init__(self, organizer_id: str = "trace-test/1") -> None:
        self._organizer_id = organizer_id
        self.seen: List[Dict[str, Any]] = []

    @property
    def organizer_id(self) -> str:
        return self._organizer_id

    def organize(self, snapshot: Dict[str, Any]) -> TraceEnrichment:
        self.seen.append(dict(snapshot))
        ids = [str(v) for v in snapshot.get("ids", [])]
        return TraceEnrichment(
            organizer_id=self._organizer_id,
            notes=["recorded by test organizer"],
            preserved_ids=ids,
        )
