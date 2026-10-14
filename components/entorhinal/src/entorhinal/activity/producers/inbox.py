"""Opt-in activity inbox producer: one exact JSONL file, nothing else.

``ActivityInboxAdapter`` tails exactly one configured inbox file of
``ActivityEvent`` JSON objects starting at a recorded activation boundary.
It never executes commands, never crawls directories, and never watches any
other path: only ``stat``/``read`` on the exact configured file plus its own
cursor/spool/error sidecars.

Durability contract (mirrors the dev-task tailer, separate namespace):

- the cursor advances only after the sanitized record is durably spooled
  (or after an attributable denial/error disposition is recorded);
- producer-side redaction runs before any spool persistence;
- the sanitized spool is bounded; at the ceiling the tailer pauses admission
  and reports backpressure instead of discarding events;
- every event must satisfy a live ``SourceGrant`` (unknown/expired/revoked
  grant => attributable denial, counted, never silent);
- health distinguishes connected-but-idle from offline/unknown and exposes
  heartbeat, cursor offset, lag, pending count, gaps, denials, and errors;
- truncation/rotation records a visible gap and resumes at EOF (never
  silently re-reads or skips).

Registration: main calls ``register_activity_adapters()`` during factory
wiring; this module does not self-register on import and never starts
capture on its own.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from entorhinal.activity.events import ACTIVITY_SOURCE_PREFIX, ActivityEvent
from entorhinal.activity.grants import GrantStore
from entorhinal.policy.engine import PolicyEngine
from entorhinal.schemas.models import RawSignalEvent, SourceType
from entorhinal.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)

ACTIVITY_INBOX_REGISTRY_KEY = "activity-inbox"
ACTIVITY_BROWSER_BRIDGE_KEY = "activity-browser-bridge"

DEFAULT_SPOOL_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_POLL_INTERVAL_SECONDS = 0.2
MAX_ERROR_PREFIX_CHARS = 512


class ActivityInboxState(str, Enum):
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
class ActivityInboxConfig:
    inbox_path: Path
    cursor_path: Path
    spool_path: Path
    error_log_path: Path
    grants_path: Path
    source_id: str = ACTIVITY_SOURCE_PREFIX + "file.01"
    activation_boundary_offset: int = 0
    spool_max_bytes: int = DEFAULT_SPOOL_MAX_BYTES
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    max_buffer_size: int = 5000


RedactionHook = Callable[[Dict[str, Any]], Tuple[Dict[str, Any], str]]


def default_activity_redaction_hook(policy: Optional[PolicyEngine] = None) -> RedactionHook:
    """Producer-side redaction using the shared policy helpers (unmodified).

    Sanitizes free-text fields (window title, string payload values) while
    structural fields (ids, timestamps, sequences, media positions) pass
    through untouched so admission stays exact.
    """
    engine = policy or PolicyEngine()

    def _hook(event_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        redacted_paths: List[str] = []
        title = event_dict.get("window_title")
        if isinstance(title, str) and title:
            clean_title, hits = engine.redact_text(title)
            if hits:
                event_dict["window_title"] = clean_title
                redacted_paths.append(f"window_title:{','.join(hits)}")
        payload = event_dict.get("payload")
        if isinstance(payload, dict):
            clean_payload, payload_paths = engine.sanitize_payload(payload, parent_path="payload")
            if payload_paths:
                event_dict["payload"] = clean_payload
                redacted_paths.extend(payload_paths)
        outcome = "clean" if not redacted_paths else f"redacted:{len(redacted_paths)}"
        labels = event_dict.get("redaction_labels")
        if isinstance(labels, list) and redacted_paths:
            labels.append(outcome)
        return event_dict, outcome

    return _hook


def _fsync_file(handle: Any) -> None:
    try:
        handle.flush()
        os.fsync(handle.fileno())
    except Exception:  # pragma: no cover - best effort on exotic filesystems
        logger.warning("fsync failed; cursor/spool durability degraded", exc_info=True)


class ActivityInboxAdapter(BaseSourceAdapter):
    """Tail one exact activity inbox file from a recorded activation boundary."""

    def __init__(
        self,
        config: ActivityInboxConfig,
        grants: Optional[GrantStore] = None,
        redaction_hook: Optional[RedactionHook] = None,
        policy: Optional[PolicyEngine] = None,
    ) -> None:
        super().__init__(max_buffer_size=config.max_buffer_size)
        if not config.source_id.startswith(ACTIVITY_SOURCE_PREFIX):
            raise ValueError(
                f"source_id {config.source_id!r} outside {ACTIVITY_SOURCE_PREFIX!r}"
            )
        resolved = Path(os.path.realpath(config.inbox_path))
        self._config = config
        self._inbox_path = resolved
        self._grants = grants if grants is not None else GrantStore(config.grants_path)
        if grants is None and config.grants_path.exists():
            self._grants.load()
        self._redact = redaction_hook or default_activity_redaction_hook(policy)
        self._state = ActivityInboxState.UNKNOWN
        self._cursor_offset = max(0, int(config.activation_boundary_offset))
        self._activation_boundary = max(0, int(config.activation_boundary_offset))
        self._last_heartbeat: Optional[str] = None
        self._last_file_size: int = 0
        self._pending_estimate: int = 0
        self._spool_bytes: int = 0
        self._gap_count = 0
        self._denied_count = 0
        self._malformed_count = 0
        self._last_gap: Optional[Dict[str, Any]] = None
        self._backpressure = False
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._cursor_lock = asyncio.Lock()

    @property
    def adapter_id(self) -> str:
        return self._config.source_id

    @property
    def source_type(self) -> SourceType:
        # Volatile-path category only; the envelope always carries the exact
        # activity source_id. TERMINAL_PTY mirrors the dev-task precedent for
        # file-tail adapters until a dedicated member exists (main's call).
        return SourceType.TERMINAL_PTY

    @property
    def inbox_state(self) -> ActivityInboxState:
        return self._state

    # -- lifecycle ------------------------------------------------------

    async def start(self) -> None:
        if self._is_running:
            return
        self._state = ActivityInboxState.STARTING
        self._touch_heartbeat()
        self._load_cursor()
        self._refresh_spool_size()
        self._grants.load()
        await super().start()
        self._poll_task = asyncio.create_task(self._poll_loop(), name="activity-inbox-tailer")
        await self.poll_once()
        logger.info(
            "Activity inbox %s tailing %s from boundary %d (cursor %d)",
            self.adapter_id, self._inbox_path,
            self._activation_boundary, self._cursor_offset,
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
        self._state = ActivityInboxState.STOPPED

    async def emit_signal(self, signal: RawSignalEvent) -> bool:
        """Enqueue without drop-oldest: activity events are never discarded."""
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

    def is_healthy(self) -> bool:
        return self._is_running and self._state in (
            ActivityInboxState.CONNECTED_IDLE,
            ActivityInboxState.CONNECTED_ACTIVE,
        )

    def health_check(self) -> Dict[str, Any]:
        report = super().health_check()
        lag = max(0, self._last_file_size - self._cursor_offset)
        report.update({
            "activity_inbox_state": self._state.value,
            "inbox_path": str(self._inbox_path),
            "inbox_exists": self._inbox_exists(),
            "activation_boundary_offset": self._activation_boundary,
            "cursor_offset": self._cursor_offset,
            "file_size_bytes": self._last_file_size,
            "lag_bytes": lag,
            "pending_lines_estimate": self._pending_estimate,
            "spool_bytes": self._spool_bytes,
            "spool_max_bytes": self._config.spool_max_bytes,
            "backpressure": self._backpressure,
            "gap_count": self._gap_count,
            "denied_count": self._denied_count,
            "malformed_count": self._malformed_count,
            "last_gap": self._last_gap,
            "last_heartbeat": self._last_heartbeat,
        })
        return report

    def spool_replay(self) -> List[ActivityEvent]:
        """Re-read durably spooled events for post-crash reconciliation.

        Returns ActivityEvents in spool order; main feeds them through the
        idempotent commit path. Corrupt spool lines are skipped with a
        recorded error (never crash the replay).
        """
        events: List[ActivityEvent] = []
        if not self._config.spool_path.exists():
            return events
        try:
            lines = self._config.spool_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            self._error_count += 1
            self._last_error = f"spool replay read failed: {exc}"
            return events
        for line in lines:
            if not line.strip():
                continue
            try:
                events.append(ActivityEvent.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                self._error_count += 1
                self._last_error = f"spool line skipped: {exc}"
        return events

    # -- scanning -------------------------------------------------------

    async def poll_once(self) -> int:
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
                    self._state = ActivityInboxState.ERROR
                    logger.error("Activity inbox scan failed: %s", exc)
        except asyncio.CancelledError:
            pass

    def _scan_locked(self) -> int:
        self._touch_heartbeat()
        if not self._inbox_exists():
            self._state = ActivityInboxState.OFFLINE
            self._last_file_size = 0
            self._pending_estimate = 0
            return 0
        try:
            file_size = self._inbox_path.stat().st_size
        except OSError as exc:
            self._error_count += 1
            self._last_error = str(exc)
            self._state = ActivityInboxState.ERROR
            return 0
        self._last_file_size = file_size

        if file_size < self._cursor_offset:
            gap = {
                "reason": "inbox-truncated-or-rotated",
                "expected_offset": self._cursor_offset,
                "observed_size": file_size,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._record_gap(gap)
            self._cursor_offset = file_size
            self._persist_cursor_locked()
            self._state = ActivityInboxState.GAP
            self._pending_estimate = 0
            return 0

        admitted = 0
        advanced = False
        pending_bytes = 0
        try:
            with open(self._inbox_path, "rb") as handle:
                handle.seek(self._cursor_offset)
                while True:
                    line_start = handle.tell()
                    raw_line = handle.readline()
                    if not raw_line:
                        break
                    if not raw_line.endswith(b"\n"):
                        break  # partial trailing line: wait for the writer
                    line_end = handle.tell()
                    outcome = self._handle_line(raw_line, line_start, line_end)
                    if outcome in ("admitted", "disposition"):
                        self._cursor_offset = line_end
                        advanced = True
                        if outcome == "admitted":
                            admitted += 1
                    else:  # backpressure
                        break
                pending_bytes = file_size - handle.tell()
        except OSError as exc:
            self._error_count += 1
            self._last_error = str(exc)
            self._state = ActivityInboxState.ERROR
            return admitted

        if advanced:
            self._persist_cursor_locked()
        self._pending_estimate = max(0, pending_bytes // 80)
        if self._backpressure:
            self._state = ActivityInboxState.BACKPRESSURE
        elif self._state not in (ActivityInboxState.GAP, ActivityInboxState.ERROR):
            self._state = (
                ActivityInboxState.CONNECTED_ACTIVE if admitted
                else ActivityInboxState.CONNECTED_IDLE
            )
        return admitted

    def _handle_line(self, raw_line: bytes, line_start: int, line_end: int) -> str:
        try:
            text = raw_line.decode("utf-8")
        except UnicodeDecodeError as exc:
            self._record_disposition("malformed-encoding", line_start, line_end,
                                     f"line is not valid UTF-8: {exc}")
            return "disposition"
        stripped = text.strip()
        if not stripped:
            return "disposition"
        try:
            candidate = json.loads(stripped)
        except json.JSONDecodeError as exc:
            self._record_disposition("malformed-json", line_start, line_end,
                                     f"line is not valid JSON: {exc}")
            return "disposition"
        if not isinstance(candidate, dict):
            self._record_disposition("malformed-envelope", line_start, line_end,
                                     "top-level JSON value must be an object")
            return "disposition"
        try:
            event = ActivityEvent.model_validate(candidate)
        except ValidationError as exc:
            self._record_disposition("malformed-activity-event", line_start, line_end,
                                     f"schema validation failed: {exc}")
            return "disposition"
        if event.source_id != self._config.source_id:
            self._record_disposition("denied", line_start, line_end,
                                     f"source mismatch: inbox {self._config.source_id} "
                                     f"vs event {event.source_id}")
            return "disposition"
        allowed, reason = self._grants.check(event)
        if not allowed:
            self._record_disposition("denied", line_start, line_end, reason)
            return "disposition"
        try:
            event_dict = event.to_json_dict()
            sanitized, _outcome = self._redact(event_dict)
            resanitized = ActivityEvent.model_validate(sanitized)
        except (ValidationError, ValueError) as exc:
            self._record_disposition("denied", line_start, line_end,
                                     f"post-redaction validation failed: {exc}")
            return "disposition"

        record = json.dumps(resanitized.to_json_dict(), sort_keys=True) + "\n"
        encoded = record.encode("utf-8")
        if self._spool_bytes + len(encoded) > self._config.spool_max_bytes:
            self._backpressure = True
            self._last_error = (
                f"sanitized spool at budget ({self._spool_bytes}/"
                f"{self._config.spool_max_bytes} bytes); admission paused"
            )
            return "backpressure"
        try:
            self._config.spool_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config.spool_path, "ab") as spool:
                spool.write(encoded)
                _fsync_file(spool)
        except OSError as exc:
            self._error_count += 1
            self._last_error = f"spool write failed: {exc}"
            self._state = ActivityInboxState.ERROR
            return "backpressure"
        self._spool_bytes += len(encoded)

        signal = resanitized.to_raw_signal_event()
        if self._event_queue.full():
            self._backpressure = True
            self._last_error = "volatile event queue saturated; spool retains record"
        else:
            try:
                self._event_queue.put_nowait(signal)
                self._events_captured += 1
            except Exception as exc:  # pragma: no cover - defensive
                self._error_count += 1
                self._last_error = str(exc)
        return "admitted"

    # -- durability helpers ---------------------------------------------

    def _touch_heartbeat(self) -> None:
        self._last_heartbeat = datetime.now(timezone.utc).isoformat()

    def _inbox_exists(self) -> bool:
        try:
            return self._inbox_path.exists() and self._inbox_path.is_file()
        except OSError:
            return False

    def _load_cursor(self) -> None:
        try:
            if self._config.cursor_path.exists():
                text = self._config.cursor_path.read_text(encoding="utf-8").strip()
                if text:
                    stored = int(text.split()[0])
                    self._cursor_offset = max(self._activation_boundary, stored)
                    return
        except (OSError, ValueError) as exc:
            self._error_count += 1
            self._last_error = f"cursor load failed: {exc}"
        self._cursor_offset = self._activation_boundary

    def _persist_cursor_locked(self) -> None:
        try:
            self._config.cursor_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config.cursor_path, "w", encoding="utf-8") as handle:
                handle.write(str(self._cursor_offset))
                _fsync_file(handle)
        except OSError as exc:
            self._error_count += 1
            self._last_error = f"cursor persist failed: {exc}"

    def _refresh_spool_size(self) -> None:
        try:
            if self._config.spool_path.exists():
                self._spool_bytes = self._config.spool_path.stat().st_size
            else:
                self._spool_bytes = 0
        except OSError:
            self._spool_bytes = 0

    def _record_gap(self, gap: Dict[str, Any]) -> None:
        self._gap_count += 1
        self._last_gap = gap
        logger.warning("Activity inbox gap: %s", gap)

    def _record_disposition(self, kind: str, line_start: int, line_end: int, reason: str) -> None:
        if kind == "denied":
            self._denied_count += 1
        else:
            self._malformed_count += 1
        entry = {
            "kind": kind,
            "line_start": line_start,
            "line_end": line_end,
            "reason": reason[:MAX_ERROR_PREFIX_CHARS],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._config.error_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config.error_log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        except OSError as exc:
            self._error_count += 1
            self._last_error = f"error-log write failed: {exc}"


def register_activity_adapters() -> List[str]:
    """Register activity producers with the source lifecycle (main calls this).

    Registry keys: ``activity-inbox`` (file tailer). The browser bridge key
    is reserved for main's HTTP wiring; the reference receiver lives in
    ``browser_sender`` and main maps it onto the real API route.
    """
    from entorhinal.runtime.sources import register_adapter  # local import: main-owned module

    def _inbox_factory(spec: Any) -> ActivityInboxAdapter:
        options = dict(spec.options or {})
        config = ActivityInboxConfig(
            inbox_path=Path(options["inbox_path"]),
            cursor_path=Path(options["cursor_path"]),
            spool_path=Path(options["spool_path"]),
            error_log_path=Path(options["error_log_path"]),
            grants_path=Path(options["grants_path"]),
            source_id=str(options.get("source_id", ACTIVITY_SOURCE_PREFIX + "file.01")),
            activation_boundary_offset=int(options.get("activation_boundary_offset", 0)),
            spool_max_bytes=int(options.get("spool_max_bytes", DEFAULT_SPOOL_MAX_BYTES)),
            poll_interval_seconds=float(options.get("poll_interval_seconds", DEFAULT_POLL_INTERVAL_SECONDS)),
            max_buffer_size=int(options.get("max_buffer_size", 5000)),
        )
        return ActivityInboxAdapter(config)

    register_adapter(ACTIVITY_INBOX_REGISTRY_KEY, _inbox_factory)
    return [ACTIVITY_INBOX_REGISTRY_KEY]
