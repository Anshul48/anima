"""Ingestion and Normalization Pipeline for Entorhinal.

Provides:
- IngestionPipeline: Async queue, sliding-window smoother, hash deduplicator, and policy gating
- HIGH_PRIORITY_SOURCES: High priority signal categories immune to backpressure drops
"""

from entorhinal.ingest.pipeline import HIGH_PRIORITY_SOURCES, IngestionPipeline

__all__ = [
    "HIGH_PRIORITY_SOURCES",
    "IngestionPipeline",
]
