"""Durable Evidence Journal, Indexing, Deterministic Replay & Projection Staging.

Provides:
- EvidenceJournal: Append-only SHA-256 hash-chained local ledger
- SecondaryIndexManager: High-speed multi-attribute secondary indexer
- DeterministicReplayEngine: Bit-accurate sequential state reconstruction
- ProjectionStager: Double-buffered candidate staging, invariant validation, and atomic swap
- StagedProjectionContext: Container for candidate projection state
"""

from entorhinal.evidence.indexing import SecondaryIndexManager
from entorhinal.evidence.journal import GENESIS_HASH, EvidenceJournal
from entorhinal.evidence.replay import DeterministicReplayEngine
from entorhinal.evidence.stager import ProjectionStager, StagedProjectionContext

__all__ = [
    "DeterministicReplayEngine",
    "EvidenceJournal",
    "GENESIS_HASH",
    "ProjectionStager",
    "SecondaryIndexManager",
    "StagedProjectionContext",
]
