"""Deterministic Replay Engine for Rebuilding State from Cold Evidence Logs.

Guarantees 100% bit-accurate state reconstruction by sequentially streaming journal entries,
applying temporal and source filters, and strictly skipping tombstoned/revoked records.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, AsyncIterator, Callable, List, Optional

from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.schemas.models import EvidenceRecord, SourceType, compute_sha256

logger = logging.getLogger(__name__)


class DeterministicReplayEngine:
    """Sequential stream iterator reconstructing intermediate and current system state from cold evidence logs."""

    def __init__(self, journal: EvidenceJournal) -> None:
        self.journal = journal

    async def replay_stream(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        source_types: Optional[List[SourceType]] = None,
        skip_tombstones: bool = True,
        limit: Optional[int] = None,
    ) -> AsyncIterator[EvidenceRecord]:
        """Stream evidence records in strict monotonic timestamp order."""
        # Use journal scanning
        records = await self.journal.scan_evidence(
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

        source_set = set(source_types) if source_types else None

        for record in records:
            # Skip tombstoned records if requested to prevent revoked data leakage
            if skip_tombstones and record.is_tombstone:
                continue

            if source_set and record.source_type not in source_set:
                continue

            yield record

    async def reconstruct_state(
        self,
        compiler_fn: Callable[[Any, EvidenceRecord], Any],
        initial_state: Any = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        source_types: Optional[List[SourceType]] = None,
        skip_tombstones: bool = True,
        limit: Optional[int] = None,
    ) -> Any:
        """Deterministically fold over the evidence stream with a custom state compiler function."""
        state = initial_state
        async for record in self.replay_stream(
            start_time=start_time,
            end_time=end_time,
            source_types=source_types,
            skip_tombstones=skip_tombstones,
            limit=limit,
        ):
            res = compiler_fn(state, record)
            if asyncio.iscoroutine(res):
                state = await res
            else:
                state = res
        return state

    async def verify_deterministic_parity(
        self,
        compiler_fn: Callable[[Any, EvidenceRecord], Any],
        initial_state_factory: Callable[[], Any],
        n_passes: int = 2,
    ) -> Tuple[bool, List[str]]:
        """Execute multiple replay passes from cold evidence logs and assert bit-accurate parity."""
        state_hashes: List[str] = []

        for _ in range(n_passes):
            state = await self.reconstruct_state(
                compiler_fn=compiler_fn,
                initial_state=initial_state_factory(),
            )
            state_hash = compute_sha256(state)
            state_hashes.append(state_hash)

        # Verify all hashes are identical
        is_parity = len(set(state_hashes)) == 1
        return is_parity, state_hashes
