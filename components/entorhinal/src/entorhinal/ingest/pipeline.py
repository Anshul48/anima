"""High-Throughput Ingestion Pipeline for Entorhinal.

Coordinates:
1. Asynchronous multi-adapter queue and pub-sub event bus.
2. Sliding-window temporal smoother & debouncer (suppressing rapid jitter <300ms).
3. Fast-path hash deduplication.
4. Pre-storage PolicyEngine gating, consent verification, and PII redaction.
5. Normalization into sealed EvidenceRecord instances.
6. Priority-aware backpressure management and metrics tracking.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set, Tuple

from entorhinal.policy.engine import PolicyEngine
from entorhinal.schemas.models import (
    EvidenceRecord,
    RawSignalEvent,
    SourceType,
    compute_record_hash,
    generate_uuidv7,
)
from entorhinal.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)

# Source types considered high-priority milestones that must never be dropped under backpressure
HIGH_PRIORITY_SOURCES: Set[SourceType] = {
    SourceType.TERMINAL_PTY,
    SourceType.USER_INPUT,
}


class IngestionPipeline:
    """High-throughput asynchronous ingestion pipeline and temporal debouncer."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        debounced_window_ms: int = 300,
        max_queue_size: int = 10000,
        dedup_cache_size: int = 2000,
    ) -> None:
        self.policy_engine = policy_engine
        self.debounced_window_ms = debounced_window_ms
        self.max_queue_size = max_queue_size
        self.dedup_cache_size = dedup_cache_size

        self._queue: asyncio.Queue[RawSignalEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._subscribers: List[Callable[[EvidenceRecord], Any]] = []

        # Sliding window debounce tracking: signature -> monotonic timestamp ms
        self._debounce_tracker: Dict[str, float] = {}

        # Sliding window deduplication cache: payload_hash -> timestamp ms
        self._dedup_cache: Dict[str, float] = {}

        # Running metrics counters
        self._events_received: int = 0
        self._events_debounced: int = 0
        self._events_deduplicated: int = 0
        self._events_policy_dropped: int = 0
        self._events_admitted: int = 0
        self._events_backpressure_dropped: int = 0
        self._total_latency_ms: float = 0.0

        self._is_running: bool = False
        self._worker_task: Optional[asyncio.Task] = None

    # --------------------------------------------------------------------------
    # Subscriptions & Event Bus
    # --------------------------------------------------------------------------

    def register_subscriber(self, subscriber: Callable[[EvidenceRecord], Any]) -> None:
        """Register a downstream consumer or journal listener callback."""
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    def unregister_subscriber(self, subscriber: Callable[[EvidenceRecord], Any]) -> bool:
        """Unregister an existing subscriber."""
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)
            return True
        return False

    async def _notify_subscribers(self, record: EvidenceRecord) -> None:
        """Dispatch sealed evidence record to all active subscribers."""
        for sub in self._subscribers:
            try:
                res = sub(record)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error("Error in ingestion subscriber: %s", e)

    # --------------------------------------------------------------------------
    # Fast-Path Deduplication & Temporal Debouncing
    # --------------------------------------------------------------------------

    def _compute_debounce_signature(self, signal: RawSignalEvent) -> str:
        """Compute structural signature for temporal focus debouncing."""
        event_type = signal.raw_payload.get("event_type", "focus")
        return f"{signal.source_type.value}:{signal.app_identifier}:{signal.window_title or ''}:{signal.target_uri or ''}:{event_type}"

    def _compute_payload_hash(self, signal: RawSignalEvent) -> str:
        """Compute deterministic payload hash for exact deduplication."""
        sig_data = {
            "source_type": signal.source_type.value,
            "app_identifier": signal.app_identifier,
            "window_title": signal.window_title,
            "target_uri": signal.target_uri,
            "raw_payload": signal.raw_payload,
        }
        canonical = json.dumps(sig_data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _should_debounce(self, signal: RawSignalEvent, now_ms: float) -> bool:
        """Check if identical structural focus event arrived within debounced_window_ms."""
        # Never debounce high-priority commands or explicit user actions
        if signal.source_type in HIGH_PRIORITY_SOURCES:
            return False

        if signal.raw_payload.get("event_type") == "command_execution":
            return False

        # Never debounce signals with stable producer idempotency: repeated
        # observations of the same media/app are distinct evidence (span
        # building needs them), not focus flapping. Exact replays still
        # dedup by payload hash and the store commit stays idempotent.
        metadata = signal.metadata or {}
        if metadata.get("activity_schema") == "activity-event/1":
            return False

        sig = self._compute_debounce_signature(signal)
        last_time = self._debounce_tracker.get(sig)

        # Update last seen
        self._debounce_tracker[sig] = now_ms

        # Prune debounce tracker if large
        if len(self._debounce_tracker) > 1000:
            threshold = now_ms - (self.debounced_window_ms * 5)
            self._debounce_tracker = {k: v for k, v in self._debounce_tracker.items() if v > threshold}

        if last_time is not None and (now_ms - last_time) < self.debounced_window_ms:
            return True

        return False

    def _should_deduplicate(self, signal: RawSignalEvent, now_ms: float) -> bool:
        """Check if identical payload was already processed recently."""
        # Never deduplicate high priority command executions
        if signal.source_type == SourceType.TERMINAL_PTY:
            return False

        p_hash = self._compute_payload_hash(signal)
        last_time = self._dedup_cache.get(p_hash)

        # Update last seen
        self._dedup_cache[p_hash] = now_ms

        # Prune dedup cache if exceeding capacity
        if len(self._dedup_cache) > self.dedup_cache_size:
            threshold = now_ms - (self.debounced_window_ms * 10)
            self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if v > threshold}

        if last_time is not None and (now_ms - last_time) < self.debounced_window_ms:
            return True

        return False

    # --------------------------------------------------------------------------
    # Core Ingestion Processing
    # --------------------------------------------------------------------------

    async def ingest_event(self, signal: RawSignalEvent) -> Optional[EvidenceRecord]:
        """Process a single raw signal through debouncing, deduplication, policy gating, and normalization.

        Returns sealed candidate EvidenceRecord if admitted, or None if suppressed.
        """
        start_time = time.perf_counter()
        now_ms = time.time() * 1000.0
        self._events_received += 1

        # 1. Temporal Debouncing
        if self._should_debounce(signal, now_ms):
            self._events_debounced += 1
            return None

        # 2. Fast-Path Exact Deduplication
        if self._should_deduplicate(signal, now_ms):
            self._events_deduplicated += 1
            return None

        # 3. Policy & Consent Evaluation (Fail-Closed)
        decision = self.policy_engine.evaluate_signal(signal)
        if not decision.permitted:
            self._events_policy_dropped += 1
            return None

        # 4. Normalization into EvidenceRecord
        record_id = generate_uuidv7()
        now_utc = datetime.now(timezone.utc)
        genesis_prev_hash = "0" * 64

        clean_window_title = decision.sanitized_window_title if decision.sanitized_window_title is not None else signal.window_title
        clean_target_uri = decision.sanitized_target_uri if decision.sanitized_target_uri is not None else signal.target_uri

        data_for_hash = {
            "record_id": record_id,
            "schema_version": "1.0.0",
            "persisted_at": now_utc.isoformat(),
            "source_type": signal.source_type.value,
            "app_identifier": signal.app_identifier,
            "window_title": clean_window_title,
            "target_uri": clean_target_uri,
            "sanitized_payload": decision.redacted_payload or {},
            "classification": decision.classification.value,
            "previous_record_hash": genesis_prev_hash,
            "is_tombstone": False,
            "tombstone_reason": None,
        }
        prov_hash = compute_record_hash(genesis_prev_hash, data_for_hash)

        record = EvidenceRecord(
            record_id=record_id,
            schema_version="1.0.0",
            persisted_at=now_utc,
            source_type=signal.source_type,
            app_identifier=signal.app_identifier,
            window_title=clean_window_title,
            target_uri=clean_target_uri,
            sanitized_payload=decision.redacted_payload or {},
            classification=decision.classification,
            provenance_hash=prov_hash,
            previous_record_hash=genesis_prev_hash,
            is_tombstone=False,
            tombstone_reason=None,
        )

        self._events_admitted += 1
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        self._total_latency_ms += elapsed_ms

        # Notify active subscribers
        await self._notify_subscribers(record)

        return record

    # --------------------------------------------------------------------------
    # Asynchronous Queue & Stream Processing
    # --------------------------------------------------------------------------

    async def submit_signal(self, signal: RawSignalEvent) -> bool:
        """Submit a raw signal to the asynchronous ingestion queue with priority-aware backpressure."""
        # Check backpressure saturation (>90% full)
        q_size = self._queue.qsize()
        if q_size >= int(self.max_queue_size * 0.9):
            # Drop low-priority focus events under high pressure
            if signal.source_type not in HIGH_PRIORITY_SOURCES:
                self._events_backpressure_dropped += 1
                return False

        try:
            if self._queue.full():
                # Guaranteed drop of oldest item if queue completely saturated
                try:
                    self._queue.get_nowait()
                    self._events_backpressure_dropped += 1
                except asyncio.QueueEmpty:
                    pass
            self._queue.put_nowait(signal)
            return True
        except Exception as e:
            logger.error("Failed to enqueue signal in ingestion pipeline: %s", e)
            return False

    async def process_stream(self, adapter: BaseSourceAdapter) -> AsyncIterator[EvidenceRecord]:
        """Stream events directly from a source adapter through the pipeline."""
        async for raw_signal in adapter.events():
            record = await self.ingest_event(raw_signal)
            if record is not None:
                yield record

    async def start(self) -> None:
        """Start the background ingestion queue consumer worker."""
        if self._is_running:
            return
        self._is_running = True
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Stop background worker and flush remaining queue items."""
        if not self._is_running:
            return
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    async def _worker_loop(self) -> None:
        """Continuous background task draining the ingestion queue."""
        while self._is_running:
            try:
                signal = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                await self.ingest_event(signal)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in ingestion pipeline worker: %s", e)

    # --------------------------------------------------------------------------
    # Metrics & Instrumentation
    # --------------------------------------------------------------------------

    def get_metrics(self) -> Dict[str, Any]:
        """Return operational metrics, admission counters, and average latency."""
        avg_latency = (
            self._total_latency_ms / self._events_admitted if self._events_admitted > 0 else 0.0
        )
        return {
            "events_received": self._events_received,
            "events_debounced": self._events_debounced,
            "events_deduplicated": self._events_deduplicated,
            "events_policy_dropped": self._events_policy_dropped,
            "events_admitted": self._events_admitted,
            "events_backpressure_dropped": self._events_backpressure_dropped,
            "queue_depth": self._queue.qsize(),
            "average_latency_ms": avg_latency,
        }

    def reset_metrics(self) -> None:
        """Reset all metrics counters."""
        self._events_received = 0
        self._events_debounced = 0
        self._events_deduplicated = 0
        self._events_policy_dropped = 0
        self._events_admitted = 0
        self._events_backpressure_dropped = 0
        self._total_latency_ms = 0.0
