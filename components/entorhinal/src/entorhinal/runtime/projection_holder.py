"""Runtime-owned holder for the single temporal task projection.

The holder rebuilds a :class:`TaskProjection` from the durable SQLite store
on first access and caches it until a control operation (forget) invalidates
it. Rebuilds skip tombstoned evidence and adopt the store's persisted
deletion generation, so deletion-time rewinding is a rebuild, not a patch.

Convergence contract (N2): this is the ONE holder. Sibling F9 cutoff serving
reads through :meth:`ProjectionHolder.get`; it must not build a second
projection from the store. If `api-repair/INTERFACES.md` defines a serving
facade, this holder moves behind it without changing rebuild semantics.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from entorhinal.temporal.projection import CommittedTaskEvent, TaskProjection

logger = logging.getLogger(__name__)

FULL_SCAN_LIMIT = 1_000_000
DELETION_GENERATION_META_KEY = "deletion_generation"
REVOCATION_GENERATION_META_KEY = "revocation_generation"


class ProjectionHolder:
    """Owns the runtime's single cached TaskProjection."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._projection: Optional[TaskProjection] = None
        self._build_count = 0
        self._last_invalidated_reason: Optional[str] = None

    @property
    def is_built(self) -> bool:
        """Whether a projection is currently cached (not invalidated)."""
        return self._projection is not None

    @property
    def build_count(self) -> int:
        """Number of rebuilds performed (monotonic; for tests/health)."""
        return self._build_count

    @property
    def last_invalidated_reason(self) -> Optional[str]:
        """Reason for the most recent invalidation (None if never)."""
        return self._last_invalidated_reason

    def invalidate(self, reason: str = "") -> None:
        """Drop the cached projection; the next get() rebuilds from the store."""
        self._projection = None
        self._last_invalidated_reason = reason or "unspecified"
        logger.info("TaskProjection invalidated: %s", self._last_invalidated_reason)

    async def get(self) -> TaskProjection:
        """Return the cached projection, rebuilding from the store if needed."""
        if self._projection is None:
            self._projection = await self.rebuild()
        return self._projection

    async def rebuild(self) -> TaskProjection:
        """Rebuild the projection from all committed store records."""
        index = self._store.commit_index()
        records = await self._store.scan_evidence(limit=FULL_SCAN_LIMIT)
        ordered = sorted(
            records, key=lambda r: (index.get(r.record_id, (0,))[0], r.record_id)
        )
        projection = TaskProjection()
        applied = 0
        skipped = 0
        for record in ordered:
            meta = index.get(record.record_id)
            if meta is None:
                skipped += 1
                continue
            commit_seq, committed_at = meta
            entry = CommittedTaskEvent.from_evidence_record(
                record,
                commit_seq=commit_seq,
                committed_at=committed_at,
                evidence_id=record.record_id,
            )
            if entry is None:
                skipped += 1
                continue
            projection.apply(entry)
            applied += 1
        get_meta = getattr(self._store, "get_meta", None)
        deletion_generation = 0
        revocation_generation = 0
        if callable(get_meta):
            try:
                deletion_generation = int(get_meta(DELETION_GENERATION_META_KEY, "0") or "0")
            except (TypeError, ValueError):
                deletion_generation = 0
            try:
                revocation_generation = int(
                    get_meta(REVOCATION_GENERATION_META_KEY, "0") or "0"
                )
            except (TypeError, ValueError):
                revocation_generation = 0
        projection.adopt_generations(
            deletion=deletion_generation, revocation=revocation_generation
        )
        self._build_count += 1
        logger.info(
            "TaskProjection rebuilt: %d applied, %d skipped, "
            "deletion_generation=%d revocation_generation=%d",
            applied,
            skipped,
            deletion_generation,
            revocation_generation,
        )
        self._projection = projection
        return projection

    def status(self) -> Dict[str, Any]:
        """Small health/status dict for runtime health and tests."""
        return {
            "built": self.is_built,
            "build_count": self._build_count,
            "last_invalidated_reason": self._last_invalidated_reason,
            "watermark": self._projection.watermark if self._projection else None,
            "deletion_generation": (
                self._projection.deletion_generation if self._projection else None
            ),
            "revocation_generation": (
                self._projection.revocation_generation if self._projection else None
            ),
        }
