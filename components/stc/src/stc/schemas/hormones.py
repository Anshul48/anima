"""Scoped Pub/Sub Hormone Protocol schemas for Biomimetic STC.

Hormones are strictly typed, scoped cellular alerts (e.g. CONTRACT_DRIFT,
TEST_FAILURE, CONCURRENCY_PRESSURE) preventing global broadcast storms.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HormoneSignalType(StrEnum):
    """Permitted biomimetic hormone signal categories."""

    CONTRACT_DRIFT = "contract_drift"
    TEST_FAILURE = "test_failure"
    CONCURRENCY_PRESSURE = "concurrency_pressure"
    SCHEMA_MUTATION = "schema_mutation"
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    DIRECTIVE_AMENDMENT = "directive_amendment"
    INVARIANT_VIOLATION = "invariant_violation"


class HormoneScope(BaseModel):
    """Receptor boundary scope restricting event delivery to matched cellular pairs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    producer_subsystem: str = Field(..., min_length=1, description="Originating subsystem cell")
    target_subsystems: list[str] = Field(
        ..., min_length=1, description="Authorized target consumer subsystem IDs"
    )
    topic: str = Field(..., min_length=1, description="Functional topic e.g. 'membrane.contracts'")
    channel: str = Field(
        ...,
        min_length=1,
        description="Scoped channel identifier (e.g. 'provider:consumer' or 'cell.isolated')",
    )


class HormoneEvent(BaseModel):
    """Cryptographically hashed, scoped cellular hormone signal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(
        default_factory=lambda: f"hormone_{uuid.uuid4().hex[:12]}",
        description="Unique event identifier",
    )
    signal_type: HormoneSignalType = Field(..., description="Categorical hormone type")
    scope: HormoneScope = Field(..., description="Receptor routing scope")
    payload: dict[str, Any] = Field(default_factory=dict, description="Structured event payload")
    payload_sha256: str = Field(
        default="",
        description="Bit-exact SHA-256 digest of canonical JSON payload",
    )
    correlation_id: str = Field(
        default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}",
        description="Distributed trace correlation identifier",
    )
    causation_id: str | None = Field(
        default=None,
        description="Identifier of causal event or trigger",
    )
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event emission timestamp in UTC",
    )
    ttl_seconds: float = Field(
        default=300.0,
        gt=0.0,
        le=86400.0,
        description="Time-to-live before signal decays",
    )

    @model_validator(mode="before")
    @classmethod
    def compute_payload_hash(cls, data: Any) -> Any:
        """Automatically compute payload_sha256 if omitted or empty."""
        if isinstance(data, dict):
            payload = data.get("payload", {})
            sha = data.get("payload_sha256")
            if not sha:
                serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                data["payload_sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return data
