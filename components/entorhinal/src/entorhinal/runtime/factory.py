"""One explicit runtime factory for serve and CLI.

``build_runtime`` constructs the storage root, SQLite store, policy engine
with persistent grants, compiler, pipeline, user controls, and the source
lifecycle from a single ``RuntimeConfig``. Both ``serve`` and the CLI share
this path; there is no in-memory default when a runtime root is configured.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from entorhinal.evidence.sqlite_store import SQLiteEvidenceStore
from entorhinal.ingest.pipeline import IngestionPipeline
from entorhinal.policy.engine import PolicyEngine
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.query.service import ContextSnapshotService
from entorhinal.runtime.config import RuntimeConfig, SourceSpec
from entorhinal.runtime.projection_holder import ProjectionHolder
from entorhinal.runtime.sources import STOPPED_RECORDS_FILENAME, SourceLifecycle
from entorhinal.schemas.models import EvidenceRecord
from entorhinal.user_control.service import UserControlService

logger = logging.getLogger(__name__)

# Admission-pump retry/backpressure policy (F5/F12). Retryable outcomes
# (retryable-storage-failure receipts, transient admission exceptions) are
# retried with exponential backoff; after the final attempt the signal is
# dead-lettered in stats (spool-backed adapters recover it via reconcile on
# restart). Failing adapters are polled with exponential backoff instead of
# being hammered every tick.
PUMP_MAX_ATTEMPTS = 3
PUMP_RETRY_BASE_DELAY_S = 0.1
POLL_BACKOFF_BASE_S = 0.2
POLL_BACKOFF_CAP_S = 5.0
# In-runtime spool reconcile (F5/F12): spooled-but-uncommitted events
# (retryable failures, policy-denied-then-granted) recover without restart.
RECONCILE_INTERVAL_S = 30.0
# Store size ceiling (G23/P11: 1 GiB retained ceiling). At the ceiling the
# pump pauses admission and exposes pending/gap status instead of discarding.
RETENTION_MAX_BYTES = 1 << 30


def _fresh_pump_source_stats() -> Dict[str, Any]:
    return {
        "polled": 0,
        "committed": 0,
        "committed_degraded": 0,
        "rejected": 0,
        "conflict": 0,
        "retried_attempts": 0,
        "retryable_exhausted": 0,
        "dead_lettered": 0,
        "errors": 0,
        "poll_failures": 0,
        "consecutive_poll_failures": 0,
        "polls_backed_off": 0,
        "activity_admitted": 0,
        "activity_not_admitted": 0,
        "last_receipt_state": None,
        "last_error": None,
    }


@dataclass
class Runtime:
    """Fully constructed service graph for one runtime root."""

    config: RuntimeConfig
    store: SQLiteEvidenceStore
    policy: PolicyEngine
    compiler: MultiTimescaleCompiler
    service: ContextSnapshotService
    user_control: UserControlService
    pipeline: IngestionPipeline
    sources: SourceLifecycle
    projection: ProjectionHolder
    # Local activity service (activity-build integration). None when the
    # activity component is unavailable; every use site tolerates None.
    activity: Optional[Any] = None
    _pump_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _pump_stop: Optional[asyncio.Event] = field(default=None, repr=False)
    _pump_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict, repr=False)
    _pump_poll_backoff: Dict[str, float] = field(default_factory=dict, repr=False)
    reconcile_interval_s: float = RECONCILE_INTERVAL_S
    retention_max_bytes: int = RETENTION_MAX_BYTES
    _last_reconcile: float = field(default=0.0, repr=False)
    _retention_paused: bool = field(default=False, repr=False)
    _pump_counters: Dict[str, int] = field(default_factory=dict, repr=False)

    def _bump_counter(self, key: str, amount: int = 1) -> None:
        self._pump_counters[key] = self._pump_counters.get(key, 0) + amount

    def _feed_activity(self, stats: Dict[str, Any], signal: Any) -> None:
        """Feed a committed activity signal into the local ActivityService.

        Only signals carrying the activity bridge schema are converted; all
        other sources are untouched. Outcomes are counted in the per-source
        pump stats; conversion/ingest failures are logged and counted, never
        raised (evidence is already durably committed at this point).
        """
        if self.activity is None:
            return
        metadata = getattr(signal, "metadata", None) or {}
        if metadata.get("activity_schema") != "activity-event/1":
            return
        try:
            from entorhinal.activity.events import ActivityEvent

            event = ActivityEvent.from_raw_signal_event(signal)
        except Exception as e:
            stats["activity_not_admitted"] += 1
            logger.error("Activity bridge conversion failed: %s", e)
            return
        try:
            outcome = self.activity.ingest(event)
        except Exception as e:
            stats["activity_not_admitted"] += 1
            logger.error("Activity ingest failed: %s", e)
            return
        status = getattr(outcome, "status", "")
        if status == "admitted":
            stats["activity_admitted"] += 1
            self._bump_counter("activity_admitted")
        else:
            stats["activity_not_admitted"] += 1
            self._bump_counter(f"activity_{status or 'unknown'}")

    async def start_sources(self) -> None:
        """Start configured sources and the admission pump."""
        await self.sources.start()
        await self.pipeline.start()
        await self._reconcile_spools()
        self._last_reconcile = time.monotonic()
        if self._pump_task is None or self._pump_task.done():
            self._pump_stop = asyncio.Event()
            self._pump_task = asyncio.create_task(self._pump_loop())

    async def _reconcile_spools(self) -> Dict[str, int]:
        """Re-admit durably spooled events that never reached the store.

        The inbox tailer advances its cursor once a sanitized record is
        durably spooled, which can precede the store commit. After a crash
        between spool and commit, the spooled event would otherwise never be
        admitted. Reconciliation replays each adapter spool through the
        idempotent commit path (stable event IDs): already-committed events
        return their original receipt, uncommitted ones are committed now.
        Returns measured counts; also runs periodically in-runtime (F5/F12).
        """
        outcome: Dict[str, int] = {"replayed": 0, "committed": 0, "errors": 0}
        for name, adapter in self.sources.adapters().items():
            replay = getattr(adapter, "spool_replay", None)
            if not callable(replay):
                continue
            try:
                spooled = replay()
            except Exception as e:
                logger.error("Spool replay failed for source %s: %s", name, e)
                outcome["errors"] += 1
                continue
            for event in spooled:
                outcome["replayed"] += 1
                try:
                    signal = event.to_raw_signal_event()
                except Exception as e:
                    logger.error("Spooled event conversion failed (%s): %s", name, e)
                    outcome["errors"] += 1
                    continue
                try:
                    receipt = await self.admit_signal(name, signal)
                except Exception as e:
                    logger.error("Spooled event admission failed (%s): %s", name, e)
                    outcome["errors"] += 1
                    continue
                if receipt is not None and receipt.committed:
                    outcome["committed"] += 1
        self._bump_counter("reconcile_runs")
        self._bump_counter("reconcile_replayed", outcome["replayed"])
        self._bump_counter("reconcile_committed", outcome["committed"])
        self._bump_counter("reconcile_errors", outcome["errors"])
        # F14: bound restart-replay cost by compacting acknowledged spool
        # entries after each reconcile (adapter-owned, measured).
        for name, adapter in self.sources.adapters().items():
            compact = getattr(adapter, "compact_spool", None)
            if not callable(compact):
                continue
            try:
                result = compact()
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, dict):
                    self._bump_counter("spool_compacted_removed",
                                       int(result.get("removed", 0) or 0))
            except Exception as e:
                logger.error("Spool compaction failed for %s: %s", name, e)
                self._bump_counter("spool_compaction_errors")
        return outcome

    async def stop_sources(self) -> None:
        """Stop the admission pump, pipeline worker, and sources cleanly."""
        if self._pump_stop is not None:
            self._pump_stop.set()
        if self._pump_task is not None:
            try:
                await asyncio.wait_for(self._pump_task, timeout=10.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._pump_task.cancel()
            self._pump_task = None
        await self.pipeline.stop()
        await self.sources.stop()

    async def _prepare_admission(self, source_name: str, signal: Any) -> Any:
        """Run pipeline ingest once; return ``(record, commit_kwargs)`` or ``(None, receipt)``.

        Split from :meth:`admit_signal` so retries re-attempt the durable
        commit without re-ingesting: a re-ingested signal would be
        debounce/dedup-suppressed as a duplicate of itself and wrongly
        recorded as policy-rejected.
        """
        from datetime import datetime, timezone

        from entorhinal.evidence.receipts import CommitReceipt, CommitState

        received_at = datetime.now(timezone.utc)
        record = await self.pipeline.ingest_event(signal)
        if record is None:
            return None, CommitReceipt(
                state=CommitState.REJECTED,
                source_id=source_name,
                event_id=getattr(signal, "signal_id", ""),
                reason="suppressed by policy, debounce, or dedup",
            )
        metadata = getattr(signal, "metadata", None) or {}
        observed_at = getattr(signal, "captured_at", None)
        if "observed_at" in metadata:
            # Task-event path: preserve a genuinely unknown observation time
            # instead of the conversion-time fallback in captured_at.
            raw_observed = metadata["observed_at"]
            if raw_observed is None:
                observed_at = None
            elif isinstance(raw_observed, str):
                try:
                    observed_at = datetime.fromisoformat(raw_observed)
                except ValueError:
                    observed_at = getattr(signal, "captured_at", None)
        source_seq = metadata.get("source_sequence")
        clock_domain = metadata.get("clock_domain")
        commit_kwargs = {
            "source_id": source_name,
            "event_id": getattr(signal, "signal_id", record.record_id),
            "record": record,
            "observed_at": observed_at,
            "received_at": received_at,
            "source_seq": source_seq if isinstance(source_seq, int) else None,
            "clock_domain": clock_domain if isinstance(clock_domain, str) else None,
        }
        return record, commit_kwargs

    async def _note_admitted(self, source_name: str, signal: Any) -> None:
        """Invoke the adapter's ``note_admitted`` hook (commit already durable)."""
        adapter = self.sources.get(source_name)
        hook = getattr(adapter, "note_admitted", None)
        if callable(hook):
            try:
                res = hook(signal)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error("note_admitted hook failed for %s: %s", source_name, e)

    async def admit_signal(self, source_name: str, signal: Any) -> Any:
        """Admit one polled signal: policy gate + pipeline + durable commit.

        Returns the store's truthful ``CommitReceipt`` (or a synthetic
        ``rejected`` receipt when policy/debounce suppresses the signal).
        The adapter's ``note_admitted`` hook - when present - is invoked
        ONLY after a durable commit, so source cursors advance only after
        durable admission.
        """
        record, outcome = await self._prepare_admission(source_name, signal)
        if record is None:
            return outcome
        receipt = await self.store.commit_event(**outcome)
        if receipt.committed:
            await self._note_admitted(source_name, signal)
            self._feed_activity(self._pump_source_stats(source_name), signal)
        return receipt

    def _pump_source_stats(self, name: str) -> Dict[str, Any]:
        """Get-or-create the mutable admission stats bucket for one source."""
        return self._pump_stats.setdefault(name, _fresh_pump_source_stats())

    def pump_stats(self) -> Dict[str, Dict[str, Any]]:
        """Return a copy of the per-source admission-pump statistics."""
        return {name: dict(stats) for name, stats in self._pump_stats.items()}

    async def _admit_with_retry(self, name: str, signal: Any) -> Any:
        """Admit one signal with bounded retries on retryable outcomes.

        Ingest runs once; only the durable commit is retried, so a retry
        is never debounce-suppressed as a duplicate of itself. Every
        outcome is recorded in the per-source pump stats; nothing is
        silently dropped. Returns the last receipt (or None when every
        attempt raised before producing one).
        """
        from entorhinal.evidence.receipts import CommitState

        stats = self._pump_source_stats(name)
        commit_kwargs = None
        for attempt in range(PUMP_MAX_ATTEMPTS):
            try:
                record, outcome = await self._prepare_admission(name, signal)
            except Exception as e:
                stats["errors"] += 1
                stats["last_error"] = f"ingest: {type(e).__name__}: {e}"
                logger.error(
                    "Admission ingest failed for source %s (attempt %d/%d): %s",
                    name, attempt + 1, PUMP_MAX_ATTEMPTS, e,
                )
            else:
                if record is None:
                    stats["last_receipt_state"] = outcome.state.value
                    stats["rejected"] += 1
                    return outcome
                commit_kwargs = outcome
                break
            if attempt + 1 < PUMP_MAX_ATTEMPTS:
                stats["retried_attempts"] += 1
                await asyncio.sleep(PUMP_RETRY_BASE_DELAY_S * (2 ** attempt))
        if commit_kwargs is None:
            stats["retryable_exhausted"] += 1
            stats["dead_lettered"] += 1
            logger.error(
                "Admission dead-lettered for source %s: ingest failed %d times (%s)",
                name, PUMP_MAX_ATTEMPTS, stats["last_error"],
            )
            return None
        last_receipt = None
        for attempt in range(PUMP_MAX_ATTEMPTS):
            try:
                receipt = await self.store.commit_event(**commit_kwargs)
            except Exception as e:
                stats["errors"] += 1
                stats["last_error"] = f"commit: {type(e).__name__}: {e}"
                logger.error(
                    "Admission commit failed for source %s (attempt %d/%d): %s",
                    name, attempt + 1, PUMP_MAX_ATTEMPTS, e,
                )
            else:
                last_receipt = receipt
                stats["last_receipt_state"] = receipt.state.value
                if receipt.committed:
                    stats["committed"] += 1
                    if receipt.state == CommitState.COMMITTED_PENDING_DEGRADED:
                        stats["committed_degraded"] += 1
                    await self._note_admitted(name, signal)
                    self._feed_activity(stats, signal)
                    return receipt
                if receipt.state == CommitState.REJECTED:
                    stats["rejected"] += 1
                    return receipt
                if receipt.state == CommitState.CONFLICT:
                    stats["conflict"] += 1
                    return receipt
                stats["last_error"] = receipt.reason or "retryable storage failure"
            if attempt + 1 < PUMP_MAX_ATTEMPTS:
                stats["retried_attempts"] += 1
                await asyncio.sleep(PUMP_RETRY_BASE_DELAY_S * (2 ** attempt))
        stats["retryable_exhausted"] += 1
        stats["dead_lettered"] += 1
        logger.error(
            "Admission dead-lettered for source %s after %d commit attempts: %s",
            name, PUMP_MAX_ATTEMPTS, stats["last_error"],
        )
        return last_receipt

    def _store_size_bytes(self) -> Optional[int]:
        """Current SQLite file size (None when unreadable)."""
        try:
            return os.path.getsize(self.store.db_path)
        except OSError:
            return None

    def _retention_ceiling_hit(self) -> bool:
        """Whether the retained store ceiling is reached (G23/P11)."""
        size = self._store_size_bytes()
        return size is not None and size >= self.retention_max_bytes

    def admission_lag(self) -> Dict[str, Dict[str, Any]]:
        """Per-source pending/gap snapshot from adapter health (F12).

        The pump treats documented tailer health fields as the contract;
        missing fields simply yield no entry for that source.
        """
        lag: Dict[str, Dict[str, Any]] = {}
        for name, adapter in self.sources.adapters().items():
            probe = getattr(adapter, "health_check", None)
            if not callable(probe):
                continue
            try:
                report = probe()
            except Exception as e:
                lag[name] = {"health_probe_error": str(e)}
                continue
            if not isinstance(report, dict):
                continue
            lag[name] = {
                key: report[key]
                for key in (
                    "spool_pending_count",
                    "queue_backlog_count",
                    "drained_unacked_count",
                    "spool_bytes",
                    "spool_max_bytes",
                    "backpressure",
                    "gap_count",
                    "lag_bytes",
                    "denied_count",
                )
                if key in report
            }
        return lag

    async def _pump_once(self) -> None:
        """Run one poll/admit pass over all adapters with poll backpressure."""
        now = time.monotonic()
        try:
            sync = await self.sources.sync_stopped_with_adapters()
        except Exception as e:
            logger.error("Stop-record sync failed: %s", e)
        else:
            if sync["stopped"] or sync["started"] or sync["errors"]:
                self._bump_counter("stop_sync_stopped", len(sync["stopped"]))
                self._bump_counter("stop_sync_started", len(sync["started"]))
                self._bump_counter("stop_sync_errors", len(sync["errors"]))
                for err in sync["errors"]:
                    logger.error("Stop-record sync: %s", err)
        if self._retention_ceiling_hit():
            # G23: pause admission at the ceiling; pending/gap status stays
            # visible via health() instead of silently discarding events.
            if not self._retention_paused:
                logger.error(
                    "Retention ceiling reached (%d bytes >= %d); "
                    "admission paused until the store shrinks",
                    self._store_size_bytes() or -1,
                    self.retention_max_bytes,
                )
            self._retention_paused = True
            self._bump_counter("retention_paused_ticks")
            return
        self._retention_paused = False
        for name, adapter in self.sources.adapters().items():
            stats = self._pump_source_stats(name)
            backed_off_until = self._pump_poll_backoff.get(name, 0.0)
            if now < backed_off_until:
                stats["polls_backed_off"] += 1
                continue
            try:
                signals = await adapter.poll_signals()
            except Exception as e:
                stats["poll_failures"] += 1
                stats["consecutive_poll_failures"] += 1
                stats["last_error"] = f"poll: {type(e).__name__}: {e}"
                shift = min(stats["consecutive_poll_failures"] - 1, 5)
                delay = min(POLL_BACKOFF_CAP_S, POLL_BACKOFF_BASE_S * (2 ** shift))
                self._pump_poll_backoff[name] = now + delay
                logger.error(
                    "Poll failed for source %s (backing off %.1fs): %s", name, delay, e
                )
                continue
            stats["consecutive_poll_failures"] = 0
            self._pump_poll_backoff.pop(name, None)
            for signal in signals:
                stats["polled"] += 1
                await self._admit_with_retry(name, signal)

    async def _pump_loop(self) -> None:
        """Poll adapters and admit signals through policy into the store."""
        assert self._pump_stop is not None
        while not self._pump_stop.is_set():
            await self._pump_once()
            now = time.monotonic()
            if now - self._last_reconcile >= self.reconcile_interval_s:
                self._last_reconcile = now
                try:
                    await self._reconcile_spools()
                except Exception as e:
                    logger.error("Periodic spool reconcile failed: %s", e)
            try:
                await asyncio.wait_for(self._pump_stop.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

    def activity_status(self) -> Dict[str, Any]:
        """Small activity-service status dict (counts best-effort)."""
        if self.activity is None:
            return {"available": False}
        status: Dict[str, Any] = {"available": True}
        try:
            status["sessions"] = len(self.activity.sessions())
            status["spans"] = len(self.activity.spans())
            status["events"] = len(self.activity.events())
            status["connections"] = len(self.activity.connections())
        except Exception as e:
            status["error"] = f"{type(e).__name__}: {e}"
        return status

    def health(self) -> Dict[str, Any]:
        return {
            "storage_root": str(self.config.storage_root),
            "store": self.store.health(),
            "sources": self.sources.health(),
            "pipeline": self.pipeline.get_metrics(),
            "projection": self.projection.status(),
            "activity": self.activity_status(),
            "pump": {
                "running": self._pump_task is not None and not self._pump_task.done(),
                "sources": self.pump_stats(),
                "counters": dict(self._pump_counters),
                "retention": {
                    "paused": self._retention_paused,
                    "db_bytes": self._store_size_bytes(),
                    "ceiling_bytes": self.retention_max_bytes,
                },
                "admission_lag": self.admission_lag(),
            },
        }

    def close(self) -> None:
        self._save_activity_snapshot()
        self.store.close()

    def _save_activity_snapshot(self) -> None:
        """Persist derived activity state at shutdown (I-3).

        The factory rebuilds the ActivityService from the snapshot directory
        when present; without a shutdown save, derived sessions, labels,
        connections, and user corrections/decisions are dropped by every
        restart. Best-effort: activity is additive, so a save failure must
        never break store shutdown.
        """
        activity = self.activity
        if activity is None:
            return
        save_snapshot = getattr(activity, "save_snapshot", None)
        if not callable(save_snapshot):
            return
        try:
            save_snapshot()
        except Exception as e:
            logger.warning("Activity shutdown snapshot save failed: %s", e)


def _build_activity_service(root: Path) -> Optional[Any]:
    """Build the local ActivityService for one runtime root.

    Grants persist at <root>/activity/grants.json; derived snapshots at
    <root>/activity/. Returns None when the activity component is
    unavailable (never raises: activity is additive to the core runtime).
    """
    try:
        from entorhinal.activity.grants import GrantStore
        from entorhinal.activity.service import ActivityService
    except Exception as e:
        logger.warning("Activity component unavailable: %s", e)
        return None
    activity_dir = root / "activity"
    try:
        grants = GrantStore(activity_dir / "grants.json")
        if (activity_dir / "events.jsonl").exists():
            return ActivityService.load_snapshot(activity_dir, grants=grants)
        return ActivityService(grants=grants, snapshot_dir=activity_dir)
    except Exception as e:
        logger.error("Activity service build failed: %s", e)
        return None


def build_runtime(
    config: Union[RuntimeConfig, str, Path],
    source_id: Optional[str] = None,
    sources: Optional[List[SourceSpec]] = None,
) -> Runtime:
    """Build the full service graph for one runtime root."""
    if not isinstance(config, RuntimeConfig):
        config = RuntimeConfig.from_root(config)
    if source_id is not None or sources is not None:
        # dataclasses.replace: sibling-owned defaulted fields (e.g. auth
        # settings) survive the override instead of resetting to defaults.
        import dataclasses

        config = dataclasses.replace(
            config,
            source_id=source_id or config.source_id,
            sources=list(sources) if sources is not None else list(config.sources),
        )
    root = config.ensure_root()

    policy = PolicyEngine(default_allow=config.default_allow)
    store = SQLiteEvidenceStore(
        config.db_path,
        queue_size=config.write_queue_size,
    )
    compiler = MultiTimescaleCompiler(journal=store)  # type: ignore[arg-type]
    service = ContextSnapshotService(
        compiler=compiler,
        policy_engine=policy,
        journal=store,  # type: ignore[arg-type]
    )
    projection = ProjectionHolder(store)
    lifecycle = SourceLifecycle(
        list(config.sources),
        storage_path=root / STOPPED_RECORDS_FILENAME,
    )
    activity = _build_activity_service(root)
    user_control = UserControlService(
        journal=store,  # type: ignore[arg-type]
        policy_engine=policy,
        compiler=compiler,
        snapshot_service=service,
        storage_dir=root,
        source_specs=[
            {"name": spec.name, "adapter": spec.adapter, "options": dict(spec.options)}
            for spec in config.sources
        ],
        on_forget=lambda proof: projection.invalidate(
            f"forget {proof.get('deletion_id', '?')} "
            f"generation={proof.get('deletion_generation', '?')}"
        ),
        adapter_accessor=lifecycle.adapters,
        activity_service=activity,
    )
    pipeline = IngestionPipeline(policy_engine=policy)

    # Required projector: the store runs it inside the commit path so a
    # projection failure yields a pending/degraded receipt with retained
    # work - never silent projected success.
    #
    # NOTE: no auto-commit pipeline subscriber is registered here. The
    # pipeline's subscriber fan-out swallows commit exceptions, which is
    # exactly the false-success defect; all runtime admission goes through
    # Runtime.admit_signal / explicit store.commit_event so the truthful
    # receipt (or failure) is always observed by the caller.
    def _required_projector(rec: EvidenceRecord) -> None:
        compiler.process_incremental_event(rec)

    store.set_projector(_required_projector)

    return Runtime(
        config=config,
        store=store,
        policy=policy,
        compiler=compiler,
        service=service,
        user_control=user_control,
        pipeline=pipeline,
        sources=lifecycle,
        projection=projection,
        activity=activity,
    )


async def close_runtime(runtime: Runtime) -> None:
    """Stop sources/pump and close the store."""
    try:
        await runtime.stop_sources()
    finally:
        runtime.close()
