"""Durable commit receipt contract for Entorhinal evidence admission.

Implements the receipt/lifecycle contract from BOUNDARY-PROPOSALS.md
(architect packet EAP-20261004-v0.2):

- A ``committed`` acknowledgement returns the committed evidence ID/hash and
  commit sequence *after* the durable commit boundary.
- Storage errors yield no success.
- A repeated ID with identical admitted content returns the ORIGINAL receipt;
  changed content under the same ID is a conflict.
- A failed required projection is reported as failed/pending, never as
  projected success.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class CommitState(str, Enum):
    """Distinct terminal/non-terminal outcomes of an admission attempt."""

    REJECTED = "rejected"
    CONFLICT = "conflict"
    RETRYABLE_STORAGE_FAILURE = "retryable-storage-failure"
    COMMITTED_PENDING_DEGRADED = "committed-pending-degraded"
    COMMITTED_PROJECTED = "committed-projected"


class ProjectionState(str, Enum):
    """Required-projection state disclosed separately from commit state."""

    NONE_REQUIRED = "none-required"
    PENDING = "pending"
    PROJECTED = "projected"
    FAILED = "failed"


@dataclass(frozen=True)
class CommitReceipt:
    """Truthful receipt for one admission attempt.

    Invariants:
    - ``evidence_id``/``content_hash``/``commit_seq``/``committed_at`` always
      describe the STORED record, never a pre-chain candidate.
    - Exact retry (same source/event identity + identical admitted content)
      returns the original receipt values with ``is_duplicate=True``.
    """

    state: CommitState
    source_id: str
    event_id: str
    evidence_id: Optional[str] = None
    content_hash: Optional[str] = None
    commit_seq: Optional[int] = None
    committed_at: Optional[datetime] = None
    store_version: str = "sqlite-store/1"
    schema_version: str = "1.0.0"
    projection_state: ProjectionState = ProjectionState.NONE_REQUIRED
    projection_watermark: int = 0
    reason: Optional[str] = None
    is_duplicate: bool = False

    @property
    def committed(self) -> bool:
        return self.state in (
            CommitState.COMMITTED_PENDING_DEGRADED,
            CommitState.COMMITTED_PROJECTED,
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["projection_state"] = self.projection_state.value
        if self.committed_at is not None:
            data["committed_at"] = self.committed_at.isoformat()
        return data


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def original_receipt_for_retry(receipt: CommitReceipt) -> CommitReceipt:
    """Return the original receipt values for an exact retry."""
    return CommitReceipt(
        state=receipt.state,
        source_id=receipt.source_id,
        event_id=receipt.event_id,
        evidence_id=receipt.evidence_id,
        content_hash=receipt.content_hash,
        commit_seq=receipt.commit_seq,
        committed_at=receipt.committed_at,
        store_version=receipt.store_version,
        schema_version=receipt.schema_version,
        projection_state=receipt.projection_state,
        projection_watermark=receipt.projection_watermark,
        reason=receipt.reason,
        is_duplicate=True,
    )
