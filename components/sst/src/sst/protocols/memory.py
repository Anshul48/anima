"""Versioned memory-provider interface with explicit availability reporting.

Memory (prior insights, inhibitors, retrieved evidence) is an *optional*
accelerator for context compilation. Providers implement
:class:`MemoryProviderProtocol`; every query returns its insights together
with a :class:`ProviderAvailability` snapshot so callers can record status,
evidence refs, and the last error instead of silently swallowing failures.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

MEMORY_PROVIDER_PROTOCOL_VERSION: str = "memory-provider/v1"


class ProviderStatus(StrEnum):
    """Availability state of a memory provider."""

    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class MemoryInsight(BaseModel):
    """One retrieved memory item with machine-readable provenance."""

    kind: str = "insight"  # "interface" | "insight"
    text: str
    layer: str = ""
    path: str = ""
    evidence_ref: str = ""


class ProviderAvailability(BaseModel):
    """Point-in-time availability snapshot for a memory provider.

    ``last_error`` carries the most recent provider failure message (if any)
    so it is surfaced to callers and event payloads rather than swallowed.
    """

    provider_name: str
    status: ProviderStatus
    adapter_version: str = MEMORY_PROVIDER_PROTOCOL_VERSION
    evidence_refs: list[str] = Field(default_factory=list)
    last_error: str | None = None
    insight_count: int = 0


class MemoryQueryResult(BaseModel):
    """Insights plus the availability snapshot observed while fetching them."""

    insights: list[MemoryInsight] = Field(default_factory=list)
    availability: ProviderAvailability


@runtime_checkable
class MemoryProviderProtocol(Protocol):
    """Protocol defining versioned memory providers for capsule compilation."""

    @property
    def provider_name(self) -> str:
        """Stable provider identifier (e.g. ``"trace-lite-db"``, ``"none"``)."""
        ...

    @property
    def adapter_version(self) -> str:
        """Adapter interface version (``memory-provider/v1``)."""
        ...

    def check_availability(self) -> ProviderAvailability:
        """Reports provider availability without running a full query."""
        ...

    def query_insights(self, goal: str, limit: int = 5) -> MemoryQueryResult:
        """Retrieves prior insights relevant to ``goal`` with availability."""
        ...
