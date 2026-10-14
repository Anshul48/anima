"""Event definitions and schemas for the event-sourced SST engine."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventKind(StrEnum):
    # Tree & Node Lifecycle
    TREE_CREATED = "TREE_CREATED"
    NODE_PROPOSED = "NODE_PROPOSED"
    NODE_EXPANDED = "NODE_EXPANDED"
    CANDIDATE_CREATED = "CANDIDATE_CREATED"
    CANDIDATE_PATCHED = "CANDIDATE_PATCHED"

    # Execution & Verification
    WORKER_INVOKED = "WORKER_INVOKED"
    VERIFIER_STARTED = "VERIFIER_STARTED"
    VERIFIER_FINISHED = "VERIFIER_FINISHED"
    SCORE_RECORDED = "SCORE_RECORDED"
    NODE_PRUNED = "NODE_PRUNED"
    SYNTHESIS_PROPOSED = "SYNTHESIS_PROPOSED"
    NODE_SELECTED = "NODE_SELECTED"

    # Human Decisions & Promotion
    HUMAN_DECISION_REQUESTED = "HUMAN_DECISION_REQUESTED"
    HUMAN_DECISION_RECORDED = "HUMAN_DECISION_RECORDED"
    PROMOTION_RECOMMENDED = "PROMOTION_RECOMMENDED"
    PROMOTION_RECORDED = "PROMOTION_RECORDED"

    # Domain Outcome Feedback (SST records the domain's verdict verbatim;
    # never authoritative, never a promotion-gate input)
    OUTCOME_REPORTED = "OUTCOME_REPORTED"

    # System & Faults
    PROVIDER_ERROR = "PROVIDER_ERROR"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    VERIFIER_UNAVAILABLE = "VERIFIER_UNAVAILABLE"

    # Search Lifecycle Terminals
    SEARCH_COMPLETED = "SEARCH_COMPLETED"
    SEARCH_CANCELLED = "SEARCH_CANCELLED"


class SSTEvent(BaseModel):
    """Immutable, append-only event record for the State Space Tree control plane."""

    event_id: str
    tree_id: str
    kind: EventKind
    node_id: str | None = None
    event_version: int = 1
    actor: str = "controller"
    policy_version: str = "v1"
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def timestamp_iso(self) -> str:
        return self.created_at.isoformat()
