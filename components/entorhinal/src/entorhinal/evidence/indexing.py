"""Secondary Index Manager for the Evidence Journal.

Provides high-speed in-memory indexing over:
- UUIDv7 record identifiers
- Monotonic UTC timestamps with bisection range scanning
- Application identifiers
- Categorical SourceTypes
- Target URIs and domain scopes
"""

from __future__ import annotations

import bisect
from datetime import datetime, timezone
import fnmatch
from typing import Dict, List, Optional, Set, Tuple

from entorhinal.schemas.models import ClassificationLevel, EvidenceRecord, SourceType


class SecondaryIndexManager:
    """In-memory secondary indexer providing sub-millisecond range lookups over evidence logs."""

    def __init__(self) -> None:
        self._by_id: Dict[str, EvidenceRecord] = {}
        # List of (timestamp_ms, record_id) maintained in sorted order
        self._time_index: List[Tuple[float, str]] = []
        self._by_app: Dict[str, Set[str]] = {}
        self._by_source: Dict[SourceType, Set[str]] = {}
        self._by_uri: Dict[str, Set[str]] = {}
        self._by_classification: Dict[ClassificationLevel, Set[str]] = {}

    def index_record(self, record: EvidenceRecord) -> None:
        """Add or update an evidence record in all secondary indices."""
        rid = record.record_id

        # If already exists, remove first
        if rid in self._by_id:
            self.remove_record(rid)

        self._by_id[rid] = record

        # Timestamp index
        ts_ms = record.persisted_at.timestamp() * 1000.0
        # Insert into sorted list using bisect
        bisect.insort(self._time_index, (ts_ms, rid))

        # App index (lowercase normalized)
        app_norm = record.app_identifier.lower().strip()
        if app_norm not in self._by_app:
            self._by_app[app_norm] = set()
        self._by_app[app_norm].add(rid)

        # Source index
        if record.source_type not in self._by_source:
            self._by_source[record.source_type] = set()
        self._by_source[record.source_type].add(rid)

        # URI index
        if record.target_uri:
            uri_norm = record.target_uri.lower().strip()
            if uri_norm not in self._by_uri:
                self._by_uri[uri_norm] = set()
            self._by_uri[uri_norm].add(rid)

        # Classification index
        if record.classification not in self._by_classification:
            self._by_classification[record.classification] = set()
        self._by_classification[record.classification].add(rid)

    def remove_record(self, record_id: str) -> bool:
        """Remove a record by ID from all indices."""
        record = self._by_id.pop(record_id, None)
        if not record:
            return False

        # Remove from time index
        ts_ms = record.persisted_at.timestamp() * 1000.0
        item = (ts_ms, record_id)
        idx = bisect.bisect_left(self._time_index, item)
        while idx < len(self._time_index) and self._time_index[idx] == item:
            self._time_index.pop(idx)
            break

        # Remove from app index
        app_norm = record.app_identifier.lower().strip()
        if app_norm in self._by_app:
            self._by_app[app_norm].discard(record_id)
            if not self._by_app[app_norm]:
                del self._by_app[app_norm]

        # Remove from source index
        if record.source_type in self._by_source:
            self._by_source[record.source_type].discard(record_id)
            if not self._by_source[record.source_type]:
                del self._by_source[record.source_type]

        # Remove from URI index
        if record.target_uri:
            uri_norm = record.target_uri.lower().strip()
            if uri_norm in self._by_uri:
                self._by_uri[uri_norm].discard(record_id)
                if not self._by_uri[uri_norm]:
                    del self._by_uri[uri_norm]

        # Remove from classification index
        if record.classification in self._by_classification:
            self._by_classification[record.classification].discard(record_id)
            if not self._by_classification[record.classification]:
                del self._by_classification[record.classification]

        return True

    def update_record(self, record: EvidenceRecord) -> None:
        """Update an existing record (e.g. after tombstoning)."""
        self.index_record(record)

    def lookup_by_id(self, record_id: str) -> Optional[EvidenceRecord]:
        """Fast point lookup by UUIDv7 ID in O(1) time."""
        return self._by_id.get(record_id)

    def lookup_time_range(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        source_filter: Optional[List[SourceType]] = None,
        app_filter: Optional[str] = None,
        limit: Optional[int] = 1000,
    ) -> List[EvidenceRecord]:
        """Perform binary search range lookup over time index with optional source/app filtering."""
        if not self._time_index:
            return []

        start_ms = start_time.timestamp() * 1000.0 if start_time else 0.0
        end_ms = end_time.timestamp() * 1000.0 if end_time else float("inf")

        # Find bounds in sorted time list
        left_idx = bisect.bisect_left(self._time_index, (start_ms, ""))
        right_idx = bisect.bisect_right(self._time_index, (end_ms, "\xff" * 36))

        results: List[EvidenceRecord] = []
        source_set = set(source_filter) if source_filter else None
        app_norm = app_filter.lower().strip() if app_filter else None

        for i in range(left_idx, min(right_idx, len(self._time_index))):
            _, rid = self._time_index[i]
            record = self._by_id.get(rid)
            if not record:
                continue

            # Source filter check
            if source_set and record.source_type not in source_set:
                continue

            # App filter check
            if app_norm and not fnmatch.fnmatch(record.app_identifier.lower(), app_norm):
                continue

            results.append(record)
            if limit is not None and len(results) >= limit:
                break

        return results

    def lookup_by_app(self, app_identifier: str) -> List[EvidenceRecord]:
        """Lookup all records matching an application identifier."""
        app_norm = app_identifier.lower().strip()
        record_ids = self._by_app.get(app_norm, set())
        return [self._by_id[rid] for rid in record_ids if rid in self._by_id]

    def lookup_by_source(self, source_type: SourceType) -> List[EvidenceRecord]:
        """Lookup all records matching a SourceType category."""
        record_ids = self._by_source.get(source_type, set())
        return [self._by_id[rid] for rid in record_ids if rid in self._by_id]

    def count(self) -> int:
        """Total number of indexed evidence records."""
        return len(self._by_id)

    def clear(self) -> None:
        """Purge all index structures."""
        self._by_id.clear()
        self._time_index.clear()
        self._by_app.clear()
        self._by_source.clear()
        self._by_uri.clear()
        self._by_classification.clear()
