"""Bounded inbox tailer for source `entorhinal.dev-task.01` (EAP-20261004-v0.2).

Tails exactly one configured, resolved inbox file
(``capture-inbox/task-events.jsonl`` under the coordinator run dir) starting at
a recorded activation boundary. It never executes commands, never crawls
repositories, and never watches any other path: only ``stat``/``read`` on the
exact configured file, plus its own cursor/spool/error sidecars.

Durability contract:
- the cursor advances only after the sanitized record is durably spooled
  (or after an attributable denial/error disposition is recorded);
- producer-side redaction runs before any spool persistence;
- the sanitized spool is bounded (default 10 MiB); at the ceiling the tailer
  first compacts acknowledged-committed entries, then pauses admission and
  reports backpressure instead of discarding events;
- rotation/truncation/in-place rewrite is detected by file identity
  (device + inode + head fingerprint), recorded as a visible gap, and the
  tailer resyncs to the new file start in inbox order instead of reading
  from a stale byte offset;
- every spooled event is tracked in a durable pending ledger until the
  runtime acknowledges its commit via ``note_admitted``; drained-but-
  uncommitted events are re-emittable in order without a restart via
  ``requeue_pending`` (never silently lost, never hammered every poll);
- denied/error dispositions are structural and redacted: offense class,
  offsets, attributable event ID, a redacted prefix and a content hash.
  Raw secret-pattern text is never persisted;
- health distinguishes connected-but-idle from offline/unknown, and exposes
  heartbeat, cursor offset, lag, pending/backlog counts, gaps and errors.

Note: ``SourceType`` has no dedicated dev-task member (existing schema files
are out of scope for this milestone), so this adapter reports the nearest
existing category, ``TERMINAL_PTY``, on the volatile ``RawSignalEvent`` path
while the envelope itself always carries the configured source ID
``entorhinal.dev-task.01``. A dedicated ``SourceType.DEV_TASK`` is proposed
as follow-up.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Collection, Dict, List, Optional, Set, Tuple

from entorhinal.policy.engine import PolicyEngine
from entorhinal.schemas.models import RawSignalEvent, SourceType
from entorhinal.schemas.task_event import (
    DEV_TASK_SOURCE_ID,
    ProducerManifest,
    TaskEvent,
    TaskEventAdmissionError,
    admit_task_event,
)
from entorhinal.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)

DEFAULT_SPOOL_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_POLL_INTERVAL_SECONDS = 0.2
MAX_ERROR_PREFIX_CHARS = 512

# Bytes of the inbox head covered by the rotation fingerprint. Append-only
# growth never changes this prefix, so any mismatch (with unchanged device /
# inode) proves an in-place rewrite of already-observed bytes.
HEAD_FINGERPRINT_BYTES = 4096
CURSOR_FORMAT_V2 = "dev-task-cursor/2"
PENDING_LEDGER_VERSION = 1
PENDING_LEDGER_FILENAME = "pending.json"
# Bound on the pending-ID sample exposed in health (the ledger itself is
# bounded by the uncommitted backlog, not by this sample).
MAX_PENDING_SAMPLE = 20
# Bound on persisted deletion tombstones (FIFO; oldest evicted first).
MAX_PURGED_TOMBSTONES = 10000

_ROTATION_GAP_REASONS = frozenset(
    {
        "inbox-rotated",
        "inbox-truncated-or-rotated",
        "inbox-rewritten-in-place",
    }
)


class DevTaskSourceState(str, Enum):
    """Truthful tailer connectivity state."""

    UNKNOWN = "unknown"
    OFFLINE = "offline"
    STARTING = "starting"
    CONNECTED_IDLE = "connected-idle"
    CONNECTED_ACTIVE = "connected-active"
    BACKPRESSURE = "backpressure"
    GAP = "gap"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class DevTaskSourceConfig:
    """Runtime configuration for the dev-task inbox tailer."""

    inbox_path: Path
    cursor_path: Path
    spool_path: Path
    error_log_path: Path
    manifest: ProducerManifest
    source_id: str = DEV_TASK_SOURCE_ID
    activation_boundary_offset: int = 0
    spool_max_bytes: int = DEFAULT_SPOOL_MAX_BYTES
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    max_buffer_size: int = 5000
    # Durable pending ledger (spooled-but-uncommitted event IDs, in spool
    # order). Defaults to ``<spool-dir>/pending.json`` when None.
    pending_path: Optional[Path] = None


RedactionHook = Callable[[Dict[str, Any]], Tuple[Dict[str, Any], str]]


def default_producer_redaction_hook(policy: Optional[PolicyEngine] = None) -> RedactionHook:
    """Build the default producer-side redaction hook.

    Sanitizes excerpt text (and only excerpt text plus string values) with
    the shared deterministic policy redaction helpers, without weakening
    them. Structural fields (IDs, hashes, revisions, timestamps) pass
    through untouched so admission stays exact.
    """
    engine = policy or PolicyEngine()

    def _hook(event_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        redacted_paths: List[str] = []
        payload = event_dict.get("payload")
        if not isinstance(payload, dict):
            return event_dict, "clean"
        excerpts = payload.get("excerpts")
        if isinstance(excerpts, list):
            for index, excerpt in enumerate(excerpts):
                if not isinstance(excerpt, dict) or not isinstance(excerpt.get("text"), str):
                    continue
                clean_text, hits = engine.redact_text(excerpt["text"])
                if hits:
                    excerpt["text"] = clean_text
                    redacted_paths.append(f"payload.excerpts[{index}].text:{','.join(hits)}")
        value = payload.get("value")
        if isinstance(value, dict):
            clean_value, value_paths = engine.sanitize_payload(value, parent_path="payload.value")
            if value_paths:
                payload["value"] = clean_value
                redacted_paths.extend(value_paths)
        outcome = "clean" if not redacted_paths else f"redacted:{len(redacted_paths)}"
        if redacted_paths:
            admission = event_dict.get("admission")
            if isinstance(admission, dict):
                admission["redaction_outcome"] = outcome
        return event_dict, outcome

    return _hook


def _fsync_file(handle: Any) -> None:
    try:
        handle.flush()
        os.fsync(handle.fileno())
    except Exception:  # pragma: no cover - best effort on exotic filesystems
        logger.warning("fsync failed; cursor/spool durability degraded", exc_info=True)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:  # pragma: no cover - best effort on exotic filesystems
        return
    try:
        os.fsync(fd)
    except Exception:  # pragma: no cover - best effort on exotic filesystems
        logger.warning("directory fsync failed; rename durability degraded", exc_info=True)
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically: temp file + fsync + rename + dir fsync.

    Readers never observe a torn file: they see either the previous or the
    new content. Used for the cursor, cursor identity, pending ledger, and
    spool/denied-log rewrites (compaction, purge).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp-{os.getpid()}"
    with open(tmp, "wb") as handle:
        handle.write(data)
        _fsync_file(handle)
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _head_fingerprint(path: Path, size: int) -> Tuple[str, int]:
    """SHA-256 of the file head plus the byte length covered.

    The covered length is returned alongside the digest so growth by
    appends stays comparable: only the previously witnessed prefix is
    compared, and coverage is ratcheted up (never down) on clean scans.
    """
    want = min(max(0, size), HEAD_FINGERPRINT_BYTES)
    if want <= 0:
        return hashlib.sha256(b"").hexdigest(), 0
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read(want)).hexdigest(), want


def _head_fingerprint_n(path: Path, n: int) -> Optional[str]:
    """SHA-256 of exactly the first ``n`` bytes, or None on I/O failure."""
    if n <= 0:
        return hashlib.sha256(b"").hexdigest()
    try:
        with open(path, "rb") as handle:
            data = handle.read(n)
    except OSError:
        return None
    if len(data) < n:
        return None
    return hashlib.sha256(data).hexdigest()


class DevTaskSourceAdapter(BaseSourceAdapter):
    """Tail one exact inbox file from a recorded activation boundary."""

    def __init__(
        self,
        config: DevTaskSourceConfig,
        redaction_hook: Optional[RedactionHook] = None,
        policy: Optional[PolicyEngine] = None,
    ) -> None:
        super().__init__(max_buffer_size=config.max_buffer_size)
        resolved = Path(os.path.realpath(config.inbox_path))
        self._config = config
        self._inbox_path = resolved
        self._manifest = config.manifest
        self._policy = policy or PolicyEngine()
        self._redact = redaction_hook or default_producer_redaction_hook(self._policy)
        self._pending_path = config.pending_path or (
            config.spool_path.parent / PENDING_LEDGER_FILENAME
        )
        self._identity_path = config.cursor_path.parent / (
            config.cursor_path.name + ".identity.json"
        )
        self._state = DevTaskSourceState.UNKNOWN
        self._cursor_offset = max(0, int(config.activation_boundary_offset))
        self._activation_boundary = max(0, int(config.activation_boundary_offset))
        self._last_heartbeat: Optional[str] = None
        self._last_file_size: int = 0
        self._pending_estimate: int = 0
        self._spool_bytes: int = 0
        self._gap_count = 0
        self._rotation_count = 0
        self._denied_count = 0
        self._malformed_count = 0
        self._purged_filtered_count = 0
        self._last_gap: Optional[Dict[str, Any]] = None
        self._backpressure = False
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._cursor_lock = asyncio.Lock()
        # Observed inbox identity (device/inode/size/head fingerprint).
        # None until the first successful observation (including legacy
        # cursor upgrades, which carry no identity).
        self._inbox_dev: Optional[int] = None
        self._inbox_ino: Optional[int] = None
        self._inbox_head_sha: Optional[str] = None
        self._inbox_head_len: int = 0
        self._inbox_size: int = 0
        # Spooled-but-uncommitted events in spool order (durable pending
        # ledger). An entry exists from ledger-persist (before the spool
        # append) until ``note_admitted`` (after the durable store commit),
        # an explicit purge, or a self-heal drop. Bodies are rehydrated
        # from the spool at start (None placeholders in between).
        self._pending_events: Dict[str, Optional[TaskEvent]] = {}
        # Pending IDs never placed in the volatile queue (it was saturated).
        # Auto-retried in order at the head of every scan.
        self._needs_queue: deque[str] = deque()
        # Pending IDs currently sitting in the volatile queue (seen on
        # enqueue, cleared on drain). ``pending - needs_queue - queued``
        # is the drained-but-unacked set, re-emitted only on explicit
        # ``requeue_pending`` so the pump is never hammered with rejects.
        self._queued_unacked: Set[str] = set()
        # Deletion tombstones (event IDs purged via purge_managed). Guards
        # against resurrection through the volatile queue and producer
        # re-emission. Bounded FIFO; persisted with the ledger.
        self._purged_ids: deque[str] = deque()
        self._purged_set: Set[str] = set()
        self._last_compaction: Optional[Dict[str, Any]] = None

    @property
    def adapter_id(self) -> str:
        return self._config.source_id

    @property
    def source_type(self) -> SourceType:
        return SourceType.TERMINAL_PTY

    @property
    def dev_task_state(self) -> DevTaskSourceState:
        """Current truthful connectivity state."""
        return self._state

    # -- lifecycle ------------------------------------------------------

    async def start(self) -> None:
        if self._is_running:
            return
        self._state = DevTaskSourceState.STARTING
        self._touch_heartbeat()
        self._load_cursor()
        self._refresh_spool_size()
        self._load_pending_ledger()
        await super().start()
        # The volatile queue may still hold undrained signals across a
        # stop/start cycle: re-install them first (order-preserving) so the
        # pending backlog is not re-emitted twice.
        restored = await super().poll_signals()
        for signal in restored:
            signal_id = getattr(signal, "signal_id", None)
            if isinstance(signal_id, str):
                self._queued_unacked.add(signal_id)
            try:
                self._event_queue.put_nowait(signal)
            except Exception:  # pragma: no cover - defensive
                break
        self._reconcile_pending_with_spool()
        # NOTE: pending (unacked) events are deliberately NOT auto-queued
        # here. Restart recovery flows through the runtime spool reconcile
        # (idempotent full replay) or an explicit requeue_pending() call;
        # auto-queuing would duplicate events the previous process already
        # emitted but that were never acknowledged (e.g. adapter-only use
        # without a store). In-runtime queue saturation still auto-retries
        # via the scan-level backlog drain.
        self._poll_task = asyncio.create_task(self._poll_loop(), name="dev-task-tailer")
        # One synchronous scan so health is truthful immediately after start.
        await self.poll_once()
        logger.info(
            "DevTask source %s tailing %s from boundary %d (cursor %d)",
            self.adapter_id,
            self._inbox_path,
            self._activation_boundary,
            self._cursor_offset,
        )

    async def stop(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        async with self._cursor_lock:
            self._persist_cursor_locked()
        await super().stop()
        self._state = DevTaskSourceState.STOPPED
        logger.info("DevTask source %s stopped at cursor %d", self.adapter_id, self._cursor_offset)

    async def emit_signal(self, signal: RawSignalEvent) -> bool:
        """Enqueue without drop-oldest: semantic events are never discarded.

        Differs from the base-class helper, which drops the oldest queued
        event under saturation. Here a full queue returns False
        (backpressure) and the tailer retains its cursor so the event is
        retried; nothing is silently lost.
        """
        if not self._is_running:
            return False
        try:
            if self._event_queue.full():
                self._backpressure = True
                return False
            self._event_queue.put_nowait(signal)
            self._events_captured += 1
            return True
        except Exception as exc:
            self._error_count += 1
            self._last_error = str(exc)
            logger.error("Failed to emit signal in adapter %s: %s", self.adapter_id, exc)
            return False

    async def poll_signals(self) -> List[Any]:
        """Drain the volatile queue, tracking acknowledgements.

        Drained pending IDs leave the in-queue set (they become
        drained-but-unacked until ``note_admitted`` or an explicit
        ``requeue_pending``). Purged IDs are filtered here so a deleted event
        still sitting in volatile RAM can never reach the pump.
        """
        from entorhinal.schemas.models import RawSignalEvent

        drained: List[RawSignalEvent] = await super().poll_signals()
        kept: List[RawSignalEvent] = []
        for signal in drained:
            signal_id = getattr(signal, "signal_id", None)
            if isinstance(signal_id, str):
                self._queued_unacked.discard(signal_id)
                if signal_id in self._purged_set:
                    self._purged_filtered_count += 1
                    continue
            kept.append(signal)
        return kept

    def is_healthy(self) -> bool:
        return self._is_running and self._state in (
            DevTaskSourceState.CONNECTED_IDLE,
            DevTaskSourceState.CONNECTED_ACTIVE,
        )

    def health_check(self) -> Dict[str, Any]:
        report = super().health_check()
        lag = max(0, self._last_file_size - self._cursor_offset)
        try:
            denied_bytes = self._config.error_log_path.stat().st_size
        except OSError:
            denied_bytes = 0
        pending_ids = list(self._pending_events)
        drained_unacked = [
            event_id
            for event_id in pending_ids
            if event_id not in self._queued_unacked
            and event_id not in self._needs_queue
        ]
        report.update(
            {
                "dev_task_state": self._state.value,
                "inbox_path": str(self._inbox_path),
                "inbox_exists": self._inbox_exists(),
                "inbox_dev": self._inbox_dev,
                "inbox_ino": self._inbox_ino,
                "activation_boundary_offset": self._activation_boundary,
                "cursor_offset": self._cursor_offset,
                "cursor_format": CURSOR_FORMAT_V2,
                "file_size_bytes": self._last_file_size,
                "lag_bytes": lag,
                "pending_lines_estimate": self._pending_estimate,
                "spool_bytes": self._spool_bytes,
                "spool_max_bytes": self._config.spool_max_bytes,
                "backpressure": self._backpressure,
                "gap_count": self._gap_count,
                "rotation_count": self._rotation_count,
                "denied_count": self._denied_count,
                "malformed_count": self._malformed_count,
                "purged_filtered_count": self._purged_filtered_count,
                "last_gap": self._last_gap,
                "last_heartbeat": self._last_heartbeat,
                # Admission-lag contract (pump treats these as truth):
                "spool_pending_count": len(self._pending_events),
                "queue_backlog_count": len(self._needs_queue),
                "drained_unacked_count": len(drained_unacked),
                "pending_sample": pending_ids[:MAX_PENDING_SAMPLE],
                "last_compaction": self._last_compaction,
                "denied_log_bytes": denied_bytes,
            }
        )
        return report

    # -- scanning -------------------------------------------------------

    async def poll_once(self) -> int:
        """Run one bounded inbox scan.

        Returns the number of events newly placed in the volatile queue
        (backlog requeues plus fresh admissions). Spooled-but-queued-later
        events are durable and visible via ``queue_backlog_count``, but are
        NOT counted here: this return value is the truthful queued-admission
        bit. While stopped, returns 0 and never advances.
        """
        async with self._cursor_lock:
            return self._scan_locked()

    async def _poll_loop(self) -> None:
        try:
            while self._is_running:
                await asyncio.sleep(self._config.poll_interval_seconds)
                try:
                    async with self._cursor_lock:
                        self._scan_locked()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._error_count += 1
                    self._last_error = str(exc)
                    self._state = DevTaskSourceState.ERROR
                    logger.error("DevTask tailer scan failed: %s", exc)
        except asyncio.CancelledError:
            pass

    def _scan_locked(self) -> int:
        # Halt cooperation (N5): a stopped source never advances.
        if not self._is_running:
            return 0
        self._touch_heartbeat()
        # Backpressure is re-evaluated every scan so recovery is visible as
        # soon as the queue/spool drains; it is never latched forever.
        self._backpressure = False
        if not self._inbox_exists():
            self._state = DevTaskSourceState.OFFLINE
            self._last_file_size = 0
            self._pending_estimate = 0
            return 0

        try:
            st = self._inbox_path.stat()
        except OSError as exc:
            self._error_count += 1
            self._last_error = str(exc)
            self._state = DevTaskSourceState.ERROR
            return 0
        file_size = st.st_size
        self._last_file_size = file_size

        if self._detect_rotation_locked(st, file_size):
            # A gap was recorded and the cursor resynced to the new file
            # start; fall through and scan the new content in inbox order
            # within this same poll (never skip it, never misparse it from
            # a stale mid-file offset).
            file_size = self._last_file_size

        admitted = self._drain_queue_backlog_locked()
        advanced = False
        try:
            with open(self._inbox_path, "rb") as handle:
                handle.seek(self._cursor_offset)
                while True:
                    line_start = handle.tell()
                    raw_line = handle.readline()
                    if not raw_line:
                        break
                    if not raw_line.endswith(b"\n"):
                        # Partial trailing line: wait for the writer to finish.
                        break
                    line_end = handle.tell()
                    outcome = self._handle_line(raw_line, line_start, line_end)
                    if outcome == "admitted":
                        admitted += 1
                        self._cursor_offset = line_end
                        advanced = True
                    elif outcome in ("spooled", "disposition"):
                        # Durably recorded (spool or redacted disposition):
                        # the cursor may advance although nothing was queued.
                        self._cursor_offset = line_end
                        advanced = True
                    elif outcome == "backpressure":
                        break
                    else:  # pragma: no cover - defensive
                        break
                pending_bytes = file_size - handle.tell()
        except OSError as exc:
            self._error_count += 1
            self._last_error = str(exc)
            self._state = DevTaskSourceState.ERROR
            return admitted

        if advanced:
            self._persist_cursor_locked()

        self._pending_estimate = self._estimate_pending_lines(pending_bytes)
        if self._backpressure:
            self._state = DevTaskSourceState.BACKPRESSURE
        elif self._state not in (DevTaskSourceState.GAP, DevTaskSourceState.ERROR):
            self._state = (
                DevTaskSourceState.CONNECTED_ACTIVE
                if admitted
                else DevTaskSourceState.CONNECTED_IDLE
            )
        return admitted

    def _detect_rotation_locked(self, st: "os.stat_result", file_size: int) -> bool:
        """Detect rotation/truncation/rewrite; resync with a visible gap.

        Returns True when the inbox file was replaced or rewritten and the
        cursor was resynced to the new file start (the caller continues
        scanning in the same poll). Detection layers:

        1. device/inode change  -> ``inbox-rotated`` (rename-replace style);
        2. size below cursor, or below the previously observed size ->
           ``inbox-truncated-or-rotated`` (shrink, incl. unread-tail loss);
        3. witnessed-head-prefix change with same inode and no shrink ->
           ``inbox-rewritten-in-place`` (same-size/larger overwrite).

        On a clean scan the witnessed coverage is ratcheted up to the
        current head (appends never rewrite the prefix), so later
        rewrites of newly observed bytes are detectable too.
        """
        if self._inbox_dev is None or self._inbox_ino is None:
            # First observation (or legacy cursor upgrade): a cursor past
            # EOF is certainly a shrink-while-stopped (gap + resync);
            # otherwise adopt the current identity without manufacturing
            # a gap (a same-size-or-larger rotation across the upgrade
            # itself is indistinguishable and therefore not claimed).
            resynced = False
            if file_size < self._cursor_offset:
                self._record_gap(
                    {
                        "reason": "inbox-truncated-or-rotated",
                        "expected_offset": self._cursor_offset,
                        "observed_size": file_size,
                        "observed_dev": st.st_dev,
                        "observed_ino": st.st_ino,
                        "previous_dev": None,
                        "previous_ino": None,
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                self._rotation_count += 1
                self._cursor_offset = 0
                self._state = DevTaskSourceState.GAP
                self._pending_estimate = 0
                resynced = True
            try:
                head_sha, head_len = _head_fingerprint(self._inbox_path, file_size)
            except OSError:
                head_sha, head_len = None, 0
            self._adopt_inbox_identity_locked(st, file_size, head_sha, head_len)
            self._persist_cursor_locked()
            return resynced
        reason: Optional[str] = None
        if (st.st_dev, st.st_ino) != (self._inbox_dev, self._inbox_ino):
            reason = "inbox-rotated"
        elif file_size < self._cursor_offset or (
            self._inbox_size and file_size < self._inbox_size
        ):
            reason = "inbox-truncated-or-rotated"
        else:
            comparable = _head_fingerprint_n(self._inbox_path, self._inbox_head_len)
            if (
                self._inbox_head_sha is not None
                and comparable is not None
                and comparable != self._inbox_head_sha
            ):
                reason = "inbox-rewritten-in-place"
        if reason is None:
            # Clean scan: ratchet coverage up (at most once per growth).
            full_head, full_len = _head_fingerprint(self._inbox_path, file_size)
            if full_len > self._inbox_head_len:
                self._adopt_inbox_identity_locked(st, file_size, full_head, full_len)
                self._persist_cursor_locked()
            elif file_size != self._inbox_size:
                self._inbox_size = file_size
                self._persist_cursor_locked()
            return False
        gap = {
            "reason": reason,
            "expected_offset": self._cursor_offset,
            "observed_size": file_size,
            "observed_dev": st.st_dev,
            "observed_ino": st.st_ino,
            "observed_mtime_ns": getattr(st, "st_mtime_ns", None),
            "previous_dev": self._inbox_dev,
            "previous_ino": self._inbox_ino,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._record_gap(gap)
        if reason in _ROTATION_GAP_REASONS:
            self._rotation_count += 1
        # Resync to the new file start: its content is post-rotation and
        # must be admitted in order, not skipped (old EOF resume) nor read
        # from a stale mid-file offset (silent misparse).
        self._cursor_offset = 0
        try:
            new_head, new_len = _head_fingerprint(self._inbox_path, file_size)
        except OSError:
            new_head, new_len = None, 0
        self._adopt_inbox_identity_locked(st, file_size, new_head, new_len)
        self._persist_cursor_locked()
        self._state = DevTaskSourceState.GAP
        self._pending_estimate = 0
        return True

    def _adopt_inbox_identity_locked(
        self,
        st: "os.stat_result",
        size: int,
        head_sha: Optional[str],
        head_len: int,
    ) -> None:
        self._inbox_dev = st.st_dev
        self._inbox_ino = st.st_ino
        self._inbox_size = max(0, size)
        self._inbox_head_sha = head_sha
        self._inbox_head_len = max(0, head_len)

    def _drain_queue_backlog_locked(self) -> int:
        """Re-emit never-queued backlog in order while space allows."""
        queued = 0
        while self._needs_queue and not self._event_queue.full():
            event_id = self._needs_queue[0]
            event = self._pending_events.get(event_id)
            if event is None:
                # Ledger/body skew (e.g. purged): drop and continue in order.
                self._needs_queue.popleft()
                continue
            try:
                self._event_queue.put_nowait(event.to_raw_signal_event())
            except Exception as exc:  # pragma: no cover - defensive
                self._error_count += 1
                self._last_error = str(exc)
                break
            self._needs_queue.popleft()
            self._queued_unacked.add(event_id)
            self._events_captured += 1
            queued += 1
        if self._needs_queue:
            self._backpressure = True
            self._last_error = "volatile event queue saturated; spool retains record"
        return queued

    def _handle_line(self, raw_line: bytes, line_start: int, line_end: int) -> str:
        """Process one complete line.

        Returns ``admitted`` (queued), ``spooled`` (durable, queued later),
        ``disposition`` (redacted denial recorded) or ``backpressure``
        (cursor held, nothing recorded).
        """
        try:
            text = raw_line.decode("utf-8")
        except UnicodeDecodeError as exc:
            self._record_disposition(
                "malformed-encoding",
                line_start,
                line_end,
                f"line is not valid UTF-8: {exc}",
                raw_line,
            )
            return "disposition"

        stripped = text.strip()
        if not stripped:
            return "disposition"

        try:
            candidate = json.loads(stripped)
        except json.JSONDecodeError as exc:
            self._record_disposition(
                "malformed-json",
                line_start,
                line_end,
                f"line is not valid JSON: {exc}",
                stripped,
            )
            return "disposition"

        if not isinstance(candidate, dict):
            self._record_disposition(
                "malformed-envelope",
                line_start,
                line_end,
                "top-level JSON value must be an object",
                stripped,
            )
            return "disposition"

        try:
            event, _notes = admit_task_event(
                candidate, source_id=self._config.source_id, manifest=self._manifest
            )
        except TaskEventAdmissionError as exc:
            self._record_disposition(
                "denied",
                line_start,
                line_end,
                str(exc),
                stripped,
            )
            return "disposition"
        except Exception as exc:  # fail-closed on unexpected validator errors
            self._record_disposition(
                "denied",
                line_start,
                line_end,
                f"admission error: {exc}",
                stripped,
            )
            return "disposition"

        if event.event_id in self._purged_set:
            # Deleted data must not resurrect through producer re-emission.
            self._record_disposition(
                "purged",
                line_start,
                line_end,
                "event_id purged by deletion; producer re-emission ignored",
                stripped,
            )
            return "disposition"

        # Producer-side redaction precedes any spool persistence.
        try:
            event_dict = event.model_dump(mode="json")
            sanitized, _outcome = self._redact(event_dict)
            resanitized = TaskEvent.model_validate(sanitized)
        except Exception as exc:
            self._record_disposition(
                "denied",
                line_start,
                line_end,
                f"post-redaction validation failed: {exc}",
                stripped,
            )
            return "disposition"

        record = json.dumps(resanitized.model_dump(mode="json"), sort_keys=True) + "\n"
        encoded = record.encode("utf-8")
        if self._spool_bytes + len(encoded) > self._config.spool_max_bytes:
            # The spool only ever holds sanitized records; compacting
            # acknowledged-committed entries is safe and may free room.
            self._compact_spool_locked()
            if self._spool_bytes + len(encoded) > self._config.spool_max_bytes:
                self._backpressure = True
                self._last_error = (
                    f"sanitized spool at budget ({self._spool_bytes}/"
                    f"{self._config.spool_max_bytes} bytes); admission paused"
                )
                return "backpressure"

        # Ledger-first ordering: the pending entry is persisted BEFORE the
        # spool append, so a crash can only leave a ledger entry without a
        # spool line (self-healed on requeue) — never a spool line the
        # ledger, compaction and replay do not know about.
        self._track_pending_locked(resanitized)
        try:
            self._config.spool_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config.spool_path, "ab") as spool:
                spool.write(encoded)
                _fsync_file(spool)
        except OSError as exc:
            self._error_count += 1
            self._last_error = f"spool write failed: {exc}"
            self._state = DevTaskSourceState.ERROR
            return "backpressure"
        self._spool_bytes += len(encoded)

        if self._event_queue.full():
            # Durably spooled but volatile queue saturated: the cursor still
            # advances because the spool holds the record, and the backlog
            # is auto-requeued in order by later scans. Reported as
            # backpressure, and — unlike before — NOT as queued admission.
            self._needs_queue.append(resanitized.event_id)
            self._backpressure = True
            self._last_error = "volatile event queue saturated; spool retains record"
            return "spooled"
        try:
            self._event_queue.put_nowait(resanitized.to_raw_signal_event())
            self._queued_unacked.add(resanitized.event_id)
            self._events_captured += 1
        except Exception as exc:  # pragma: no cover - defensive
            self._error_count += 1
            self._last_error = str(exc)
            self._needs_queue.append(resanitized.event_id)
            return "spooled"
        return "admitted"

    # -- durability helpers ---------------------------------------------

    def _load_cursor(self) -> None:
        try:
            if self._config.cursor_path.exists():
                text = self._config.cursor_path.read_text(encoding="utf-8").strip()
                if text:
                    stored = int(text.split()[0])
                    self._cursor_offset = max(self._activation_boundary, stored)
                    self._load_cursor_identity()
                    return
        except (OSError, ValueError) as exc:
            logger.warning("Cursor load failed (%s); using activation boundary", exc)
            self._record_gap(
                {
                    "reason": "cursor-unreadable",
                    "expected_offset": self._cursor_offset,
                    "observed_size": None,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        self._cursor_offset = self._activation_boundary

    def _load_cursor_identity(self) -> None:
        """Load the persisted inbox identity, if any (legacy: none)."""
        try:
            if not self._identity_path.exists():
                return
            payload = json.loads(self._identity_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Cursor identity load failed (%s); relearning", exc)
            return
        if not isinstance(payload, dict):
            return
        try:
            dev = payload.get("dev")
            ino = payload.get("ino")
            if isinstance(dev, int) and isinstance(ino, int):
                self._inbox_dev = dev
                self._inbox_ino = ino
            head = payload.get("head_sha256")
            if isinstance(head, str) and head:
                self._inbox_head_sha = head
            head_len = payload.get("head_len")
            if isinstance(head_len, int) and head_len >= 0:
                self._inbox_head_len = head_len
            size = payload.get("size")
            if isinstance(size, int) and size >= 0:
                self._inbox_size = size
        except Exception:  # pragma: no cover - defensive
            logger.warning("Cursor identity malformed; relearning", exc_info=True)

    def _persist_cursor_locked(self) -> None:
        try:
            _atomic_write_bytes(
                self._config.cursor_path, f"{self._cursor_offset}\n".encode("utf-8")
            )
            identity = {
                "format": CURSOR_FORMAT_V2,
                "offset": self._cursor_offset,
                "dev": self._inbox_dev,
                "ino": self._inbox_ino,
                "size": self._inbox_size or self._last_file_size,
                "head_sha256": self._inbox_head_sha,
                "head_len": self._inbox_head_len,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_write_bytes(
                self._identity_path,
                (json.dumps(identity, sort_keys=True) + "\n").encode("utf-8"),
            )
        except OSError as exc:  # pragma: no cover - best effort with visible error
            self._error_count += 1
            self._last_error = f"cursor persist failed: {exc}"
            logger.error("Cursor persist failed: %s", exc)

    def _refresh_spool_size(self) -> None:
        try:
            if self._config.spool_path.exists():
                self._spool_bytes = self._config.spool_path.stat().st_size
            else:
                self._spool_bytes = 0
        except OSError:
            self._spool_bytes = 0

    def _record_disposition(
        self, kind: str, start: int, end: int, reason: str, raw: Any
    ) -> None:
        """Record an attributable denial/error disposition without raw secrets.

        The entry is structural (offense class, offsets, attributable event
        ID, top-level shape) plus a REDACTED prefix and a SHA-256 of the raw
        line for correlation. Raw line bytes — which may carry secret-pattern
        excerpts from a denied event — are never persisted.
        """
        if kind in ("denied", "purged"):
            self._denied_count += 1
        else:
            self._malformed_count += 1
        if isinstance(raw, (bytes, bytearray)):
            raw_bytes = bytes(raw)
            try:
                text = raw_bytes.decode("utf-8")
                decode_ok = True
            except UnicodeDecodeError:
                text = raw_bytes.decode("utf-8", errors="replace")
                decode_ok = False
        else:
            text = str(raw)
            raw_bytes = text.encode("utf-8", errors="replace")
            decode_ok = True
        event_id: Optional[str] = None
        top_keys: List[str] = []
        json_valid = False
        candidate: Any = None
        try:
            candidate = json.loads(text)
            json_valid = True
        except ValueError:
            json_valid = False
        if isinstance(candidate, dict):
            try:
                top_keys = sorted(str(k) for k in candidate.keys())[:32]
            except Exception:  # pragma: no cover - defensive
                top_keys = []
            raw_event_id = candidate.get("event_id")
            if isinstance(raw_event_id, str) and raw_event_id:
                event_id = raw_event_id[:256]
        try:
            redacted_prefix, prefix_hits = self._policy.redact_text(text)
        except Exception:  # fail-closed: no prefix rather than raw on error
            logger.error("Disposition redaction failed; omitting prefix", exc_info=True)
            redacted_prefix, prefix_hits = "", ["redaction-error"]
        try:
            redacted_reason, reason_hits = self._policy.redact_text(str(reason))
        except Exception:  # pragma: no cover - defensive
            redacted_reason, reason_hits = str(reason), []
        self._error_count += 1
        self._last_error = f"{kind} at bytes {start}-{end}: {redacted_reason}"
        entry = {
            "kind": kind,
            "event_id": event_id,
            "offset_start": start,
            "offset_end": end,
            "line_length": len(raw_bytes),
            "utf8_valid": decode_ok,
            "json_valid": json_valid,
            "top_keys": top_keys,
            "reason": redacted_reason,
            "prefix": redacted_prefix[:MAX_ERROR_PREFIX_CHARS],
            "prefix_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "redaction_hits": sorted(set(prefix_hits) | set(reason_hits)),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._config.error_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config.error_log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
                _fsync_file(handle)
        except OSError as exc:  # pragma: no cover - best effort with visible error
            logger.error("Error-log write failed: %s", exc)

    def _record_gap(self, gap: Dict[str, Any]) -> None:
        self._gap_count += 1
        self._last_gap = gap
        self._error_count += 1
        self._last_error = f"gap: {gap.get('reason')}"
        logger.warning("DevTask inbox gap: %s", gap)

    # -- small helpers --------------------------------------------------

    def _inbox_exists(self) -> bool:
        try:
            return self._inbox_path.is_file()
        except OSError:
            return False

    def _touch_heartbeat(self) -> None:
        self._last_heartbeat = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _estimate_pending_lines(pending_bytes: int) -> int:
        if pending_bytes <= 0:
            return 0
        # Coarse estimate: one pending line per 512 bytes, at least one.
        return max(1, pending_bytes // 512 + 1)

    # -- pending ledger + commit acknowledgement (F12 source side) --------

    def _persist_pending_locked(self) -> None:
        payload = {
            "version": PENDING_LEDGER_VERSION,
            "pending": list(self._pending_events),
            "purged": list(self._purged_ids)[-MAX_PURGED_TOMBSTONES:],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            _atomic_write_bytes(
                self._pending_path,
                (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"),
            )
        except OSError as exc:  # pragma: no cover - best effort, visible
            self._error_count += 1
            self._last_error = f"pending ledger persist failed: {exc}"
            logger.error("Pending ledger persist failed: %s", exc)

    def _load_pending_ledger(self) -> None:
        try:
            if not self._pending_path.exists():
                return
            payload = json.loads(self._pending_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Pending ledger load failed (%s); rebuilding", exc)
            self._record_gap(
                {
                    "reason": "pending-ledger-unreadable",
                    "expected_offset": self._cursor_offset,
                    "observed_size": None,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            return
        if not isinstance(payload, dict):
            return
        pending = payload.get("pending")
        if isinstance(pending, list):
            for event_id in pending:
                if isinstance(event_id, str) and event_id:
                    # Body placeholders: rehydrated from the spool in
                    # _reconcile_pending_with_spool; ghosts are pruned there
                    # or on first requeue (self-heal).
                    self._pending_events[event_id] = self._pending_events.get(event_id)
        purged = payload.get("purged")
        if isinstance(purged, list):
            for event_id in purged[-MAX_PURGED_TOMBSTONES:]:
                if isinstance(event_id, str) and event_id:
                    self._remember_purged_id(event_id, persist=False)

    def _reconcile_pending_with_spool(self) -> None:
        """Union spool IDs into pending; rehydrate bodies; prune ghosts.

        After this, every spooled-but-uncommitted event is pending: a crash
        between spool append and ledger persist can only under-report, and
        the spool scan closes that hole. Ledger IDs with no spool line are
        pruned (ledger-first crash artefacts), and bodies load from spool.
        """
        spooled: Dict[str, TaskEvent] = {}
        try:
            if self._config.spool_path.exists():
                with open(self._config.spool_path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = TaskEvent.model_validate(json.loads(line))
                        except Exception:
                            continue
                        spooled.setdefault(event.event_id, event)
        except OSError as exc:
            logger.error("Pending/spool reconcile scan failed: %s", exc)
            return
        merged: Dict[str, TaskEvent] = {}
        for event_id, body in self._pending_events.items():
            if event_id in spooled:
                merged[event_id] = spooled[event_id]
            elif body is not None:
                merged[event_id] = body
            # else: ledger ghost with no spool line and no body — pruned.
        for event_id, event in spooled.items():
            if event_id not in merged and event_id not in self._purged_set:
                merged[event_id] = event
        self._pending_events = merged
        self._persist_pending_locked()

    def _track_pending_locked(self, event: TaskEvent) -> None:
        if event.event_id not in self._pending_events:
            self._pending_events[event.event_id] = event
        else:
            self._pending_events[event.event_id] = event
        self._persist_pending_locked()

    def note_admitted(self, signal: Any) -> None:
        """Mark one spooled event committed (runtime hook, post-commit only).

        The factory calls this ONLY after a durable store commit, so the ID
        leaves the pending ledger and becomes eligible for spool compaction.
        Unknown IDs and malformed signals are ignored; this hook never
        raises into the pump.
        """
        try:
            event_id = self._signal_event_id(signal)
            if event_id is None:
                return
            if event_id in self._pending_events:
                del self._pending_events[event_id]
                try:
                    self._needs_queue.remove(event_id)
                except ValueError:
                    pass
                self._queued_unacked.discard(event_id)
                self._persist_pending_locked()
        except Exception as exc:  # never fail the pump on bookkeeping
            logger.error("note_admitted bookkeeping failed: %s", exc)

    @staticmethod
    def _signal_event_id(signal: Any) -> Optional[str]:
        if isinstance(signal, str) and signal:
            return signal
        signal_id = getattr(signal, "signal_id", None)
        if isinstance(signal_id, str) and signal_id:
            return signal_id
        metadata = getattr(signal, "metadata", None)
        if isinstance(metadata, dict):
            event_id = metadata.get("event_id")
            if isinstance(event_id, str) and event_id:
                return event_id
        raw_payload = getattr(signal, "raw_payload", None)
        if isinstance(raw_payload, dict):
            event_id = raw_payload.get("event_id")
            if isinstance(event_id, str) and event_id:
                return event_id
        return None

    def pending_spool_events(self, *, limit: int = 200) -> List[TaskEvent]:
        """Oldest-first view of spooled-but-uncommitted events (lag disclosure)."""
        events = [
            event
            for event in self._pending_events.values()
            if event is not None
        ]
        return events[: max(0, limit)]

    def requeue_pending(self, *, max_events: Optional[int] = None) -> int:
        """Re-emit drained-but-uncommitted events in spool order (F12 retry).

        The runtime calls this after a grant change (or on a slow tick) so
        policy-denied admissions recover WITHOUT a restart. Only IDs that
        are neither queued nor never-queued-backlog are re-emitted, bounded
        by free queue space and ``max_events``. Returns the count re-emitted.
        Ledger ghosts (no spool body) are pruned instead of emitted.
        """
        if not self._is_running:
            return 0
        budget = len(self._pending_events) if max_events is None else max(0, max_events)
        requeued = 0
        pruned = False
        for event_id in list(self._pending_events):
            if requeued >= budget or self._event_queue.full():
                break
            if event_id in self._queued_unacked:
                continue
            event = self._pending_events.get(event_id)
            if event is None:
                event = self._spool_body(event_id)
                if event is None:
                    del self._pending_events[event_id]
                    pruned = True
                    continue
                self._pending_events[event_id] = event
            try:
                self._event_queue.put_nowait(event.to_raw_signal_event())
            except Exception as exc:
                self._error_count += 1
                self._last_error = str(exc)
                break
            try:
                self._needs_queue.remove(event_id)
            except ValueError:
                pass
            self._queued_unacked.add(event_id)
            self._events_captured += 1
            requeued += 1
        if pruned:
            self._persist_pending_locked()
        return requeued

    def _spool_body(self, event_id: str) -> Optional[TaskEvent]:
        """Fetch one spooled event body by ID (tolerant scan)."""
        try:
            if not self._config.spool_path.exists():
                return None
            with open(self._config.spool_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or event_id not in line:
                        continue
                    try:
                        event = TaskEvent.model_validate(json.loads(line))
                    except Exception:
                        continue
                    if event.event_id == event_id:
                        return event
        except OSError as exc:
            logger.error("Spool body lookup failed: %s", exc)
        return None

    def spool_replay(self, *, limit: Optional[int] = None) -> List[TaskEvent]:
        """Read back durably spooled events (audit/recovery helper).

        With ``limit=None`` (default) returns ALL spooled events in spool
        (oldest-first) order, so reconcile-time exact retry covers events
        beyond any fixed window. ``limit=N`` keeps the legacy most-recent-N
        peek. The daemon owns idempotent admission by event ID; this helper
        never re-emits into the volatile queue on its own.
        """
        if not self._config.spool_path.exists():
            return []
        events: List[TaskEvent] = []
        try:
            with open(self._config.spool_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(TaskEvent.model_validate(json.loads(line)))
                    except Exception:
                        continue
        except OSError as exc:
            logger.error("Spool replay failed: %s", exc)
            return []
        if limit is None:
            return events
        if limit <= 0:
            return []
        return events[-limit:]

    # -- spool compaction (F14) -------------------------------------------

    def compact_spool(
        self, committed_ids: Optional[Collection[str]] = None
    ) -> Dict[str, Any]:
        """Atomically drop acknowledged-committed spool entries, in order.

        Default keeps every pending (uncommitted) entry plus every
        unparseable line (conservative); explicit ``committed_ids`` drops
        exactly those IDs. Order of kept lines is preserved. Returns
        measured ``{kept, removed, kept_unparseable, spool_bytes_before,
        spool_bytes_after}``. Never drops pending entries.
        """
        return self._compact_spool_locked(committed_ids)

    def _compact_spool_locked(
        self, committed_ids: Optional[Collection[str]] = None
    ) -> Dict[str, Any]:
        before = self._spool_bytes
        if not self._config.spool_path.exists():
            result = {
                "kept": 0,
                "removed": 0,
                "kept_unparseable": 0,
                "spool_bytes_before": before,
                "spool_bytes_after": 0,
            }
            self._last_compaction = {**result, "at": self._last_heartbeat}
            return result
        drop: Optional[Set[str]] = (
            set(committed_ids) if committed_ids is not None else None
        )
        kept_lines: List[bytes] = []
        kept = 0
        removed = 0
        kept_unparseable = 0
        try:
            with open(self._config.spool_path, "rb") as handle:
                raw_lines = handle.read().split(b"\n")
        except OSError as exc:
            logger.error("Spool compaction read failed: %s", exc)
            return {
                "kept": 0,
                "removed": 0,
                "kept_unparseable": 0,
                "spool_bytes_before": before,
                "spool_bytes_after": before,
                "error": str(exc),
            }
        for raw in raw_lines:
            if not raw.strip():
                continue
            event_id: Optional[str] = None
            try:
                event_id = TaskEvent.model_validate(json.loads(raw)).event_id
            except Exception:
                kept_lines.append(raw + b"\n")
                kept += 1
                kept_unparseable += 1
                continue
            if drop is not None:
                should_drop = event_id in drop
            else:
                should_drop = event_id not in self._pending_events
            if should_drop:
                removed += 1
            else:
                kept_lines.append(raw + b"\n")
                kept += 1
        try:
            _atomic_write_bytes(self._config.spool_path, b"".join(kept_lines))
        except OSError as exc:
            logger.error("Spool compaction write failed: %s", exc)
            return {
                "kept": kept,
                "removed": 0,
                "kept_unparseable": kept_unparseable,
                "spool_bytes_before": before,
                "spool_bytes_after": before,
                "error": str(exc),
            }
        self._refresh_spool_size()
        result = {
            "kept": kept,
            "removed": removed,
            "kept_unparseable": kept_unparseable,
            "spool_bytes_before": before,
            "spool_bytes_after": self._spool_bytes,
        }
        if removed:
            self._last_compaction = {
                **result,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        return result

    # -- managed-copy deletion hooks (N4; stop != forget) ------------------

    def managed_paths(self) -> Dict[str, str]:
        """Daemon-side file paths owned by this source.

        ``inbox`` is producer-owned (listed for inventory, never purged by
        this adapter); ``cursor``, ``cursor_identity``, ``spool``,
        ``denied_log`` and ``pending_ledger`` are daemon sidecars.
        """
        return {
            "inbox": str(self._inbox_path),
            "cursor": str(self._config.cursor_path),
            "cursor_identity": str(self._identity_path),
            "spool": str(self._config.spool_path),
            "denied_log": str(self._config.error_log_path),
            "pending_ledger": str(self._pending_path),
        }

    def _remember_purged_id(self, event_id: str, *, persist: bool = True) -> None:
        if event_id in self._purged_set:
            return
        self._purged_ids.append(event_id)
        self._purged_set.add(event_id)
        while len(self._purged_ids) > MAX_PURGED_TOMBSTONES:
            self._purged_set.discard(self._purged_ids.popleft())
        if persist:
            self._persist_pending_locked()

    def purge_managed(
        self,
        *,
        reason: str,
        event_ids: Optional[Collection[str]] = None,
        match_all: bool = False,
    ) -> Dict[str, Any]:
        """Purge this source's managed copies of deleted data (N4).

        Removes spool lines, pending-ledger entries and denied-log entries
        for ``event_ids`` (or everything when ``match_all=True`` — the full-
        forget path, whose caller must have stopped the source first).
        Tombstones guard the volatile queue (filtered on drain) and producer
        re-emission (recorded as ``purged`` dispositions). The cursor and
        inbox are untouched, so surviving offsets stay valid. Returns
        measured counts; never raises on missing files.
        """
        targets: Optional[Set[str]] = None
        if not match_all:
            if not event_ids:
                raise ValueError("purge_managed requires event_ids or match_all=True")
            targets = {e for e in event_ids if isinstance(e, str) and e}
            if not targets:
                raise ValueError("purge_managed requires event_ids or match_all=True")
        spool_removed, spool_kept = self._purge_spool_locked(targets)
        pending_removed = self._purge_pending_locked(targets)
        denied_removed, denied_kept = self._purge_denied_log_locked(targets)
        if targets is not None:
            for event_id in sorted(targets):
                self._remember_purged_id(event_id, persist=False)
            self._persist_pending_locked()
        else:
            # Full forget: tombstoning every ID is unbounded; the stopped
            # source + emptied spool/ledger/denied-log is the guarantee, and
            # the ledger persist below records the generation boundary.
            self._persist_pending_locked()
        self._refresh_spool_size()
        return {
            "reason": reason,
            "match_all": match_all,
            "targets": None if targets is None else len(targets),
            "spool_removed": spool_removed,
            "spool_kept": spool_kept,
            "pending_removed": pending_removed,
            "pending_remaining": len(self._pending_events),
            "denied_removed": denied_removed,
            "denied_kept": denied_kept,
        }

    def _purge_spool_locked(self, targets: Optional[Set[str]]) -> Tuple[int, int]:
        if not self._config.spool_path.exists():
            return 0, 0
        try:
            data = self._config.spool_path.read_bytes().split(b"\n")
        except OSError as exc:
            logger.error("Purge spool read failed: %s", exc)
            return 0, 0
        kept_lines: List[bytes] = []
        removed = 0
        for raw in data:
            if not raw.strip():
                continue
            if targets is None:
                removed += 1
                continue
            event_id: Optional[str] = None
            try:
                event_id = TaskEvent.model_validate(json.loads(raw)).event_id
            except Exception:
                kept_lines.append(raw + b"\n")  # unattributable: keep
                continue
            if event_id in targets:
                removed += 1
            else:
                kept_lines.append(raw + b"\n")
        try:
            _atomic_write_bytes(self._config.spool_path, b"".join(kept_lines))
        except OSError as exc:
            logger.error("Purge spool write failed: %s", exc)
            return 0, 0
        return removed, len(kept_lines)

    def _purge_pending_locked(self, targets: Optional[Set[str]]) -> int:
        if targets is None:
            removed = len(self._pending_events)
            self._pending_events.clear()
            self._needs_queue.clear()
            self._queued_unacked.clear()
            return removed
        removed = 0
        for event_id in list(targets):
            if event_id in self._pending_events:
                del self._pending_events[event_id]
                removed += 1
            try:
                self._needs_queue.remove(event_id)
            except ValueError:
                pass
            self._queued_unacked.discard(event_id)
        return removed

    def _purge_denied_log_locked(
        self, targets: Optional[Set[str]]
    ) -> Tuple[int, int]:
        if not self._config.error_log_path.exists():
            return 0, 0
        try:
            data = self._config.error_log_path.read_bytes().split(b"\n")
        except OSError as exc:
            logger.error("Purge denied-log read failed: %s", exc)
            return 0, 0
        kept_lines: List[bytes] = []
        removed = 0
        for raw in data:
            if not raw.strip():
                continue
            if targets is None:
                removed += 1
                continue
            entry_id: Optional[str] = None
            try:
                entry = json.loads(raw)
                if isinstance(entry, dict):
                    maybe = entry.get("event_id")
                    if isinstance(maybe, str):
                        entry_id = maybe
            except ValueError:
                kept_lines.append(raw + b"\n")  # unattributable: keep
                continue
            if entry_id is not None and entry_id in targets:
                removed += 1
            else:
                kept_lines.append(raw + b"\n")
        try:
            _atomic_write_bytes(self._config.error_log_path, b"".join(kept_lines))
        except OSError as exc:
            logger.error("Purge denied-log write failed: %s", exc)
            return 0, 0
        return removed, len(kept_lines)

    @property
    def cursor_offset(self) -> int:
        """Current durable inbox cursor (byte offset)."""
        return self._cursor_offset

    @property
    def spool_bytes(self) -> int:
        """Current sanitized spool size in bytes."""
        return self._spool_bytes

    def uptime_seconds(self) -> float:
        """Seconds since start (0 when never started)."""
        if self._started_at and self._is_running:
            return (datetime.now(timezone.utc) - self._started_at).total_seconds()
        return 0.0


DEV_TASK_REGISTRY_KEY = "dev-task-inbox"


def _coerce_int(value: Any, name: str) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"dev-task option {name!r} must be an integer") from exc


def _coerce_float(value: Any, name: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"dev-task option {name!r} must be a number") from exc


def dev_task_adapter_factory(spec: Any) -> DevTaskSourceAdapter:
    """Build a dev-task tailer from a runtime SourceSpec (fail-closed).

    Required options: ``inbox_path`` (exact inbox file), ``manifest_path``
    (producer manifest JSON). Optional: ``state_dir`` (cursor/spool/error
    sidecars; default ``<inbox-parent>/dev-task-state``), ``cursor_path``,
    ``spool_path``, ``error_log_path``, ``pending_path`` (durable pending
    ledger; default ``<spool-dir>/pending.json``),
    ``activation_boundary_offset`` (default: manifest value),
    ``spool_max_bytes``, ``poll_interval_seconds``, ``max_buffer_size``,
    ``source_id``.
    """
    from entorhinal.schemas.task_event import ProducerManifest

    options: Dict[str, Any] = dict(getattr(spec, "options", None) or {})
    raw_inbox = options.get("inbox_path")
    raw_manifest = options.get("manifest_path")
    if not raw_inbox:
        raise ValueError("dev-task-inbox requires option 'inbox_path'")
    if not raw_manifest:
        raise ValueError("dev-task-inbox requires option 'manifest_path'")
    inbox_path = Path(os.path.realpath(str(raw_inbox)))
    try:
        with open(raw_manifest, "r", encoding="utf-8") as handle:
            manifest = ProducerManifest.model_validate(json.load(handle))
    except (OSError, ValueError) as exc:
        raise ValueError(f"dev-task manifest unreadable/invalid: {exc}") from exc
    manifest_inbox = Path(os.path.realpath(manifest.inbox_path))
    if manifest_inbox != inbox_path:
        raise ValueError(
            f"manifest inbox {manifest_inbox} does not match configured {inbox_path}"
        )
    state_dir = Path(str(options.get("state_dir", inbox_path.parent / "dev-task-state")))
    boundary = options.get("activation_boundary_offset", manifest.activation_boundary_offset)
    config = DevTaskSourceConfig(
        inbox_path=inbox_path,
        cursor_path=Path(str(options.get("cursor_path", state_dir / "cursor.offset"))),
        spool_path=Path(str(options.get("spool_path", state_dir / "sanitized.spool.jsonl"))),
        error_log_path=Path(str(options.get("error_log_path", state_dir / "denied.jsonl"))),
        manifest=manifest,
        source_id=str(options.get("source_id", DEV_TASK_SOURCE_ID)),
        activation_boundary_offset=_coerce_int(boundary, "activation_boundary_offset"),
        spool_max_bytes=_coerce_int(
            options.get("spool_max_bytes", DEFAULT_SPOOL_MAX_BYTES), "spool_max_bytes"
        ),
        poll_interval_seconds=_coerce_float(
            options.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS),
            "poll_interval_seconds",
        ),
        max_buffer_size=_coerce_int(options.get("max_buffer_size", 5000), "max_buffer_size"),
        pending_path=(
            Path(str(options["pending_path"]))
            if options.get("pending_path")
            else None
        ),
    )
    return DevTaskSourceAdapter(config)


def register_dev_task_adapter() -> None:
    """Register the dev-task inbox tailer under ``dev-task-inbox``."""
    from entorhinal.runtime.sources import register_adapter

    register_adapter(DEV_TASK_REGISTRY_KEY, dev_task_adapter_factory)
