"""Transactional SQLite evidence store with truthful commit receipts.

Durability contract (plan EAP-20261004-v0.2, M1):

- Single owning writer: every mutation goes through one bounded queue served
  by one writer thread. ``journal_mode=DELETE`` (rollback journal) with
  ``synchronous=EXTRA``. WAL is FORBIDDEN on this runtime (SQLite 3.45.1).
- One transaction atomically persists the sanitized event + source/event
  identity + idempotency key + sealed receipt + pending projection work.
- Failed commit exposes NO new state and returns failure, never success.
- Exact retry (same source/event ID + identical admitted content) returns the
  ORIGINAL receipt, including after restart/response loss. Same ID with
  changed content is a conflict.
- Projector failure after commit reports pending/degraded and retains
  recoverable work - never projected success.
- Observed/received/committed times plus source order/clock domain are
  preserved on every committed record.
- Source cursors advance only after durable admission.

The legacy JSONL journal (``evidence/journal.py``) stays intact as the
explicit legacy import/export path; this store is the durable backend for
new runs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import queue
import sqlite3
import threading
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Union

from entorhinal.evidence.receipts import (
    CommitReceipt,
    CommitState,
    ProjectionState,
    original_receipt_for_retry,
    utcnow,
)
from entorhinal.ports.interfaces import MemoryPort
from entorhinal.schemas.models import (
    ClassificationLevel,
    EvidenceRecord,
    SourceType,
    TombstoneRecord,
    compute_record_hash,
    generate_uuidv7,
)

logger = logging.getLogger(__name__)

STORE_VERSION = "sqlite-store/1"
SCHEMA_VERSION = "1.0.0"
STORE_SCHEMA_VERSION = 1
GENESIS_HASH = "0" * 64

DEFAULT_QUEUE_SIZE = 1000
DEFAULT_COMMIT_TIMEOUT_S = 30.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    commit_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT UNIQUE NOT NULL,
    source_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    content_hash TEXT NOT NULL,
    record_json TEXT NOT NULL,
    observed_at TEXT,
    received_at TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    source_seq INTEGER,
    clock_domain TEXT,
    prev_hash TEXT NOT NULL,
    prov_hash TEXT NOT NULL,
    projection_state TEXT NOT NULL,
    UNIQUE (source_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_source_event ON evidence (source_id, event_id);
CREATE TABLE IF NOT EXISTS pending_work (
    work_id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_state ON pending_work (state);
CREATE TABLE IF NOT EXISTS source_cursors (
    source_id TEXT PRIMARY KEY,
    cursor TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


ProjectorFn = Callable[[EvidenceRecord], Any]


class _CommitOp:
    __slots__ = ("payload", "future")

    def __init__(self, payload: Dict[str, Any], future: "Future[CommitReceipt]") -> None:
        self.payload = payload
        self.future = future


class SQLiteEvidenceStore(MemoryPort):
    """Transactional SQLite backend behind the evidence interface."""

    def __init__(
        self,
        db_path: Union[str, Path],
        queue_size: int = DEFAULT_QUEUE_SIZE,
        commit_timeout_s: float = DEFAULT_COMMIT_TIMEOUT_S,
        projector: Optional[ProjectorFn] = None,
    ) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be >= 1")
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._queue_size = queue_size
        self._commit_timeout_s = commit_timeout_s
        self._projector = projector

        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._apply_pragmas()
        with self._conn:
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
                ("store_version", STORE_VERSION),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
                ("schema_version", str(STORE_SCHEMA_VERSION)),
            )

        self._lock = threading.RLock()
        self._write_queue: "queue.Queue[Optional[_CommitOp]]" = queue.Queue(maxsize=queue_size)
        self._closed = False
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name="sqlite-evidence-writer", daemon=True
        )
        self._writer_thread.start()

        # Test/fault hooks. ``fail_next_commits`` counts down forced failures;
        # ``fault_injector`` may raise to simulate a storage fault.
        self.fail_next_commits: int = 0
        self.fault_injector: Optional[Callable[[], None]] = None

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    def _apply_pragmas(self) -> None:
        cur = self._conn.execute("PRAGMA journal_mode=DELETE;")
        mode = (cur.fetchone()[0] or "").upper()
        if mode == "WAL":
            raise RuntimeError("WAL journal mode is forbidden on this runtime")
        self._conn.execute("PRAGMA synchronous=EXTRA;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._conn.execute("PRAGMA foreign_keys=ON;")

    def set_projector(self, projector: Optional[ProjectorFn]) -> None:
        """Set (or clear) the required projector run inside the commit path."""
        with self._lock:
            self._projector = projector

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def queue_size(self) -> int:
        return self._queue_size

    @property
    def queue_depth(self) -> int:
        return self._write_queue.qsize()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        try:
            self._write_queue.put_nowait(None)
        except queue.Full:
            pass
        self._writer_thread.join(timeout=10.0)
        with self._lock:
            try:
                self._conn.commit()
            except Exception:
                pass
            self._conn.close()

    def __enter__(self) -> "SQLiteEvidenceStore":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def get_meta(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Read a control-plane value from the meta table (e.g. deletion generation)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return default
            return str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        """Durably write a control-plane value to the meta table."""
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    def commit_index(self) -> Dict[str, Tuple[int, datetime]]:
        """Map evidence_id -> (commit_seq, committed_at) for projection rebuilds."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT evidence_id, commit_seq, committed_at FROM evidence ORDER BY commit_seq ASC"
            ).fetchall()
            return {
                str(row["evidence_id"]): (
                    int(row["commit_seq"]),
                    _parse_time(row["committed_at"]) or utcnow(),
                )
                for row in rows
            }

    def event_keys_for(self, record_ids: List[str]) -> Dict[str, Dict[str, str]]:
        """Map evidence_id -> {source_id, event_id} for adapter purge (N4)."""
        if not record_ids:
            return {}
        with self._lock:
            placeholders = ",".join("?" for _ in record_ids)
            rows = self._conn.execute(
                f"SELECT evidence_id, source_id, event_id FROM evidence "
                f"WHERE evidence_id IN ({placeholders})",
                tuple(record_ids),
            ).fetchall()
            return {
                str(row["evidence_id"]): {
                    "source_id": str(row["source_id"]),
                    "event_id": str(row["event_id"]),
                }
                for row in rows
            }

    # ------------------------------------------------------------------
    # Single owning writer
    # ------------------------------------------------------------------

    def _writer_loop(self) -> None:
        while True:
            try:
                op = self._write_queue.get()
            except Exception:
                continue
            if op is None:
                self._write_queue.task_done()
                return
            try:
                receipt = self._execute_commit(op.payload)
            except Exception as e:  # never let the writer die on a bad op
                logger.error("Writer failed commit op: %s", e)
                receipt = CommitReceipt(
                    state=CommitState.RETRYABLE_STORAGE_FAILURE,
                    source_id=str(op.payload.get("source_id", "")),
                    event_id=str(op.payload.get("event_id", "")),
                    reason=f"writer error: {e}",
                )
            if not op.future.done():
                op.future.set_result(receipt)
            self._write_queue.task_done()

    # ------------------------------------------------------------------
    # Admission API
    # ------------------------------------------------------------------

    async def commit_event(
        self,
        source_id: str,
        event_id: str,
        record: Union[EvidenceRecord, Dict[str, Any]],
        observed_at: Optional[datetime] = None,
        received_at: Optional[datetime] = None,
        source_seq: Optional[int] = None,
        clock_domain: Optional[str] = None,
        evidence_id: Optional[str] = None,
    ) -> CommitReceipt:
        """Commit one sanitized event transactionally and return its receipt."""
        if self._closed:
            return CommitReceipt(
                state=CommitState.RETRYABLE_STORAGE_FAILURE,
                source_id=source_id or "",
                event_id=event_id or "",
                reason="store is closed",
            )
        if isinstance(record, EvidenceRecord):
            record = {
                "source_type": record.source_type.value,
                "app_identifier": record.app_identifier,
                "window_title": record.window_title,
                "target_uri": record.target_uri,
                "sanitized_payload": record.sanitized_payload,
                "classification": record.classification.value,
                "schema_version": record.schema_version,
                "is_tombstone": record.is_tombstone,
                "tombstone_reason": record.tombstone_reason,
            }
        validation_error = self._validate_envelope(source_id, event_id, record)
        if validation_error is not None:
            return CommitReceipt(
                state=CommitState.REJECTED,
                source_id=source_id or "",
                event_id=event_id or "",
                reason=validation_error,
            )
        assert isinstance(record, dict)
        payload = {
            "source_id": source_id,
            "event_id": event_id,
            "record": record,
            "observed_at": _iso(observed_at),
            "received_at": _iso(received_at or utcnow()),
            "source_seq": source_seq,
            "clock_domain": clock_domain,
            "evidence_id": evidence_id,
        }
        fut: "Future[CommitReceipt]" = Future()
        try:
            self._write_queue.put_nowait(_CommitOp(payload, fut))
        except queue.Full:
            return CommitReceipt(
                state=CommitState.RETRYABLE_STORAGE_FAILURE,
                source_id=source_id,
                event_id=event_id,
                reason="bounded write queue saturated; retry later",
            )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop: block the calling thread (sync test helper path).
            try:
                return fut.result(timeout=self._commit_timeout_s)
            except Exception as e:
                return CommitReceipt(
                    state=CommitState.RETRYABLE_STORAGE_FAILURE,
                    source_id=source_id,
                    event_id=event_id,
                    reason=f"commit wait failed: {e}",
                )
        try:
            return await asyncio.wait_for(
                asyncio.wrap_future(fut), timeout=self._commit_timeout_s
            )
        except asyncio.TimeoutError:
            return CommitReceipt(
                state=CommitState.RETRYABLE_STORAGE_FAILURE,
                source_id=source_id,
                event_id=event_id,
                reason="commit timed out waiting for owning writer",
            )

    def commit_event_sync(self, *args: Any, **kwargs: Any) -> CommitReceipt:
        """Synchronous wrapper for non-async callers (scripts, adapters)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.commit_event(*args, **kwargs))
        raise RuntimeError("commit_event_sync cannot be called from a running event loop")

    def _validate_envelope(
        self,
        source_id: Any,
        event_id: Any,
        record: Union[EvidenceRecord, Dict[str, Any], Any],
    ) -> Optional[str]:
        if not isinstance(source_id, str) or not source_id.strip():
            return "malformed: source_id must be a non-empty string"
        if not isinstance(event_id, str) or not event_id.strip():
            return "malformed: event_id must be a non-empty string"
        if isinstance(record, EvidenceRecord):
            return None
        if not isinstance(record, dict):
            return "malformed: record must be an EvidenceRecord or mapping"
        try:
            json.dumps(record, sort_keys=True, default=str)
        except Exception:
            return "malformed: record is not JSON-serializable (possibly truncated)"
        required = ("source_type", "app_identifier", "sanitized_payload")
        missing = [k for k in required if k not in record]
        if missing:
            return f"malformed: record missing required fields: {','.join(missing)}"
        if not isinstance(record.get("app_identifier"), str) or not record["app_identifier"].strip():
            return "malformed: app_identifier must be a non-empty string"
        if not isinstance(record.get("sanitized_payload"), dict):
            return "malformed: sanitized_payload must be an object"
        try:
            SourceType(str(record["source_type"]))
        except Exception:
            return f"malformed: unknown source_type {record.get('source_type')!r}"
        return None

    # ------------------------------------------------------------------
    # Transaction body (runs ONLY on the writer thread)
    # ------------------------------------------------------------------

    def _execute_commit(self, payload: Dict[str, Any]) -> CommitReceipt:
        if self.fault_injector is not None:
            self.fault_injector()
        if self.fail_next_commits > 0:
            self.fail_next_commits -= 1
            raise sqlite3.OperationalError("injected storage failure")

        source_id: str = payload["source_id"]
        event_id: str = payload["event_id"]
        raw = payload["record"]
        if isinstance(raw, EvidenceRecord):
            record_dict: Dict[str, Any] = {
                "source_type": raw.source_type.value,
                "app_identifier": raw.app_identifier,
                "window_title": raw.window_title,
                "target_uri": raw.target_uri,
                "sanitized_payload": raw.sanitized_payload,
                "classification": raw.classification.value,
                "schema_version": raw.schema_version,
                "is_tombstone": raw.is_tombstone,
                "tombstone_reason": raw.tombstone_reason,
            }
        else:
            record_dict = dict(raw)

        content_hash = self._content_hash(source_id, event_id, record_dict)
        idempotency_key = f"{source_id}\u0000{event_id}"
        received_at = payload["received_at"] or _iso(utcnow())
        committed_at = _iso(utcnow())
        assert committed_at is not None and received_at is not None

        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE;")
                try:
                    existing = self._conn.execute(
                        "SELECT * FROM evidence WHERE source_id = ? AND event_id = ?",
                        (source_id, event_id),
                    ).fetchone()
                    if existing is not None:
                        stored_hash = existing["content_hash"]
                        stored_receipt = self._receipt_from_row(existing)
                        self._conn.execute("ROLLBACK;")
                        if stored_hash != content_hash:
                            return CommitReceipt(
                                state=CommitState.CONFLICT,
                                source_id=source_id,
                                event_id=event_id,
                                evidence_id=existing["evidence_id"],
                                content_hash=stored_hash,
                                commit_seq=existing["commit_seq"],
                                committed_at=_parse_time(existing["committed_at"]),
                                projection_state=ProjectionState(existing["projection_state"]),
                                projection_watermark=self._watermark_locked(),
                                reason="event identity reused with changed content",
                            )
                        return original_receipt_for_retry(stored_receipt)

                    last = self._conn.execute(
                        "SELECT prov_hash FROM evidence ORDER BY commit_seq DESC LIMIT 1"
                    ).fetchone()
                    prev_hash = last["prov_hash"] if last else GENESIS_HASH
                    evidence_id = payload.get("evidence_id") or generate_uuidv7()
                    persisted_at = committed_at
                    data_for_hash = {
                        "record_id": evidence_id,
                        "schema_version": record_dict.get("schema_version", SCHEMA_VERSION),
                        "persisted_at": persisted_at,
                        "source_type": record_dict["source_type"],
                        "app_identifier": record_dict["app_identifier"],
                        "window_title": record_dict.get("window_title"),
                        "target_uri": record_dict.get("target_uri"),
                        "sanitized_payload": record_dict["sanitized_payload"],
                        "classification": record_dict.get("classification", ClassificationLevel.INTERNAL.value),
                        "previous_record_hash": prev_hash,
                        "is_tombstone": bool(record_dict.get("is_tombstone", False)),
                        "tombstone_reason": record_dict.get("tombstone_reason"),
                    }
                    prov_hash = compute_record_hash(prev_hash, data_for_hash)
                    record_json = json.dumps(
                        {
                            **data_for_hash,
                            "provenance_hash": prov_hash,
                            "source_id": source_id,
                            "event_id": event_id,
                            "observed_at": payload.get("observed_at"),
                            "received_at": received_at,
                            "committed_at": committed_at,
                            "source_seq": payload.get("source_seq"),
                            "clock_domain": payload.get("clock_domain"),
                        },
                        sort_keys=True,
                        default=str,
                    )
                    cur = self._conn.execute(
                        """INSERT INTO evidence (
                            evidence_id, source_id, event_id, idempotency_key,
                            content_hash, record_json, observed_at, received_at,
                            committed_at, source_seq, clock_domain, prev_hash,
                            prov_hash, projection_state
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            evidence_id,
                            source_id,
                            event_id,
                            idempotency_key,
                            content_hash,
                            record_json,
                            payload.get("observed_at"),
                            received_at,
                            committed_at,
                            payload.get("source_seq"),
                            payload.get("clock_domain"),
                            prev_hash,
                            prov_hash,
                            ProjectionState.PENDING.value,
                        ),
                    )
                    commit_seq = int(cur.lastrowid)
                    self._conn.execute(
                        """INSERT INTO pending_work
                           (evidence_id, kind, state, attempts, created_at, updated_at)
                           VALUES (?, 'project', 'pending', 0, ?, ?)""",
                        (evidence_id, committed_at, committed_at),
                    )
                    self._conn.execute("COMMIT;")
                except Exception:
                    try:
                        self._conn.execute("ROLLBACK;")
                    except Exception:
                        pass
                    raise

                # Commit boundary crossed: run the required projector OUTSIDE the
                # insert transaction. Projector failure must not roll back or
                # lose the event; it yields pending/degraded + retained work.
                sealed = self._evidence_record_from_parts(evidence_id, data_for_hash, prov_hash)
                projector_error: Optional[str] = None
                if self._projector is not None:
                    try:
                        res = self._projector(sealed)
                        if asyncio.iscoroutine(res):
                            # Writer thread has no running loop; drive it here.
                            asyncio.run(res)  # type: ignore[arg-type]
                    except Exception as e:
                        projector_error = str(e)
                        logger.error("Required projector failed for %s: %s", evidence_id, e)

                now = _iso(utcnow())
                with self._conn:
                    if projector_error is None:
                        self._conn.execute(
                            "UPDATE evidence SET projection_state = ? WHERE evidence_id = ?",
                            (ProjectionState.PROJECTED.value, evidence_id),
                        )
                        self._conn.execute(
                            "UPDATE pending_work SET state = 'done', updated_at = ? "
                            "WHERE evidence_id = ? AND kind = 'project'",
                            (now, evidence_id),
                        )
                        state = CommitState.COMMITTED_PROJECTED
                        proj_state = (
                            ProjectionState.NONE_REQUIRED
                            if self._projector is None
                            else ProjectionState.PROJECTED
                        )
                    else:
                        self._conn.execute(
                            "UPDATE evidence SET projection_state = ? WHERE evidence_id = ?",
                            (ProjectionState.PENDING.value, evidence_id),
                        )
                        self._conn.execute(
                            "UPDATE pending_work SET state = 'pending', attempts = attempts + 1, "
                            "last_error = ?, updated_at = ? "
                            "WHERE evidence_id = ? AND kind = 'project'",
                            (projector_error, now, evidence_id),
                        )
                        state = CommitState.COMMITTED_PENDING_DEGRADED
                        proj_state = ProjectionState.PENDING

                return CommitReceipt(
                    state=state,
                    source_id=source_id,
                    event_id=event_id,
                    evidence_id=evidence_id,
                    content_hash=content_hash,
                    commit_seq=commit_seq,
                    committed_at=_parse_time(committed_at),
                    projection_state=proj_state,
                    projection_watermark=self._watermark_locked(),
                    reason=projector_error,
                )
            except sqlite3.IntegrityError as e:
                # Concurrent/duplicate idempotency key: re-read for truthful retry/conflict.
                try:
                    row = self._conn.execute(
                        "SELECT * FROM evidence WHERE source_id = ? AND event_id = ?",
                        (source_id, event_id),
                    ).fetchone()
                except Exception:
                    row = None
                if row is not None:
                    stored_receipt = self._receipt_from_row(row)
                    if row["content_hash"] != content_hash:
                        return CommitReceipt(
                            state=CommitState.CONFLICT,
                            source_id=source_id,
                            event_id=event_id,
                            evidence_id=row["evidence_id"],
                            content_hash=row["content_hash"],
                            commit_seq=row["commit_seq"],
                            committed_at=_parse_time(row["committed_at"]),
                            projection_state=ProjectionState(row["projection_state"]),
                            projection_watermark=self._watermark_locked(),
                            reason="event identity reused with changed content",
                        )
                    return original_receipt_for_retry(stored_receipt)
                logger.error("Commit integrity failure: %s", e)
                return CommitReceipt(
                    state=CommitState.RETRYABLE_STORAGE_FAILURE,
                    source_id=source_id,
                    event_id=event_id,
                    reason=f"storage integrity failure: {e}",
                )
            except Exception as e:
                logger.error("Commit failed with no new visible state: %s", e)
                return CommitReceipt(
                    state=CommitState.RETRYABLE_STORAGE_FAILURE,
                    source_id=source_id,
                    event_id=event_id,
                    reason=f"storage failure: {e}",
                )

    # ------------------------------------------------------------------
    # Receipts, catch-up, cursors
    # ------------------------------------------------------------------

    @staticmethod
    def _content_hash(source_id: str, event_id: str, record: Dict[str, Any]) -> str:
        canonical = json.dumps(
            {
                "source_id": source_id,
                "event_id": event_id,
                "source_type": record.get("source_type"),
                "app_identifier": record.get("app_identifier"),
                "window_title": record.get("window_title"),
                "target_uri": record.get("target_uri"),
                "sanitized_payload": record.get("sanitized_payload"),
                "classification": record.get("classification"),
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _watermark_locked(self) -> int:
        row = self._conn.execute(
            "SELECT MAX(commit_seq) AS w FROM evidence WHERE projection_state = 'projected'"
        ).fetchone()
        return int(row["w"] or 0)

    def projection_watermark(self) -> int:
        with self._lock:
            return self._watermark_locked()

    def _receipt_from_row(self, row: sqlite3.Row) -> CommitReceipt:
        proj = ProjectionState(row["projection_state"])
        if proj == ProjectionState.PROJECTED:
            state = CommitState.COMMITTED_PROJECTED
        else:
            state = CommitState.COMMITTED_PENDING_DEGRADED
        return CommitReceipt(
            state=state,
            source_id=row["source_id"],
            event_id=row["event_id"],
            evidence_id=row["evidence_id"],
            content_hash=row["content_hash"],
            commit_seq=row["commit_seq"],
            committed_at=_parse_time(row["committed_at"]),
            projection_state=proj,
            projection_watermark=self._watermark_locked(),
        )

    @staticmethod
    def _evidence_record_from_parts(
        evidence_id: str, data_for_hash: Dict[str, Any], prov_hash: str
    ) -> EvidenceRecord:
        return EvidenceRecord(
            record_id=evidence_id,
            schema_version=str(data_for_hash.get("schema_version", SCHEMA_VERSION)),
            persisted_at=_parse_time(str(data_for_hash.get("persisted_at"))) or utcnow(),
            source_type=SourceType(str(data_for_hash.get("source_type"))),
            app_identifier=str(data_for_hash.get("app_identifier")),
            window_title=data_for_hash.get("window_title"),
            target_uri=data_for_hash.get("target_uri"),
            sanitized_payload=dict(data_for_hash.get("sanitized_payload") or {}),
            classification=ClassificationLevel(str(data_for_hash.get("classification", "internal"))),
            provenance_hash=prov_hash,
            previous_record_hash=str(data_for_hash.get("previous_record_hash")),
            is_tombstone=bool(data_for_hash.get("is_tombstone", False)),
            tombstone_reason=data_for_hash.get("tombstone_reason"),
        )

    def _row_to_record(self, row: sqlite3.Row) -> EvidenceRecord:
        stored = json.loads(row["record_json"])
        return EvidenceRecord(
            record_id=row["evidence_id"],
            schema_version=str(stored.get("schema_version", SCHEMA_VERSION)),
            persisted_at=_parse_time(row["committed_at"]) or utcnow(),
            source_type=SourceType(str(stored.get("source_type"))),
            app_identifier=str(stored.get("app_identifier")),
            window_title=stored.get("window_title"),
            target_uri=stored.get("target_uri"),
            sanitized_payload=dict(stored.get("sanitized_payload") or {}),
            classification=ClassificationLevel(str(stored.get("classification", "internal"))),
            provenance_hash=row["prov_hash"],
            previous_record_hash=row["prev_hash"],
            is_tombstone=bool(stored.get("is_tombstone", False)),
            tombstone_reason=stored.get("tombstone_reason"),
        )

    async def get_receipt(self, source_id: str, event_id: str) -> Optional[CommitReceipt]:
        """Return the ORIGINAL committed receipt for an identity, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM evidence WHERE source_id = ? AND event_id = ?",
                (source_id, event_id),
            ).fetchone()
            if row is None:
                return None
            return self._receipt_from_row(row)

    async def drain_pending(
        self, projector: Optional[ProjectorFn] = None, limit: int = 500
    ) -> Dict[str, Any]:
        """Retry durable pending projection work idempotently (catch-up)."""
        projector = projector if projector is not None else self._projector
        if projector is None:
            return {"processed": 0, "projected": 0, "still_pending": 0, "reason": "no projector"}
        with self._lock:
            rows = self._conn.execute(
                """SELECT p.work_id, p.attempts, e.* FROM pending_work p
                   JOIN evidence e ON e.evidence_id = p.evidence_id
                   WHERE p.state = 'pending' ORDER BY e.commit_seq ASC LIMIT ?""",
                (limit,),
            ).fetchall()
        processed = 0
        projected = 0
        for r in rows:
            processed += 1
            record = self._row_to_record(r)
            try:
                res = projector(record)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                now = _iso(utcnow())
                with self._lock:
                    with self._conn:
                        self._conn.execute(
                            "UPDATE pending_work SET attempts = attempts + 1, last_error = ?, "
                            "updated_at = ? WHERE work_id = ?",
                            (str(e), now, r["work_id"]),
                        )
                continue
            now = _iso(utcnow())
            with self._lock:
                with self._conn:
                    self._conn.execute(
                        "UPDATE pending_work SET state = 'done', attempts = attempts + 1, "
                        "updated_at = ? WHERE work_id = ?",
                        (now, r["work_id"]),
                    )
                    self._conn.execute(
                        "UPDATE evidence SET projection_state = 'projected' WHERE evidence_id = ?",
                        (r["evidence_id"],),
                    )
            projected += 1
        with self._lock:
            still = self._conn.execute(
                "SELECT COUNT(*) AS c FROM pending_work WHERE state = 'pending'"
            ).fetchone()["c"]
        return {
            "processed": processed,
            "projected": projected,
            "still_pending": int(still),
            "watermark": self.projection_watermark(),
        }

    async def pending_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM pending_work WHERE state = 'pending'"
            ).fetchone()
            return int(row["c"])

    # -- source cursors: advance only after durable admission -------------

    async def advance_cursor(self, source_id: str, cursor: str) -> None:
        """Persist a source cursor. Callers must invoke only after durable admission."""
        if not source_id or not cursor:
            raise ValueError("source_id and cursor must be non-empty")
        now = _iso(utcnow())
        with self._lock:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO source_cursors (source_id, cursor, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT (source_id) DO UPDATE SET cursor = excluded.cursor, "
                    "updated_at = excluded.updated_at",
                    (source_id, cursor, now),
                )

    async def get_cursor(self, source_id: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT cursor FROM source_cursors WHERE source_id = ?", (source_id,)
            ).fetchone()
            return row["cursor"] if row else None

    # -- store health ------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        with self._lock:
            mode = (self._conn.execute("PRAGMA journal_mode;").fetchone()[0] or "").upper()
            sync = self._conn.execute("PRAGMA synchronous;").fetchone()[0]
            count = self._conn.execute("SELECT COUNT(*) AS c FROM evidence").fetchone()["c"]
            pending = self._conn.execute(
                "SELECT COUNT(*) AS c FROM pending_work WHERE state = 'pending'"
            ).fetchone()["c"]
            watermark = self._watermark_locked()
        return {
            "backend": "sqlite",
            "store_version": STORE_VERSION,
            "db_path": str(self._db_path),
            "journal_mode": mode,
            "synchronous": sync,
            "evidence_count": int(count),
            "pending_work": int(pending),
            "projection_watermark": watermark,
            "write_queue_depth": self.queue_depth,
            "write_queue_size": self._queue_size,
            "writer_alive": self._writer_thread.is_alive(),
        }

    def retention_status(
        self,
        max_age_days: int = 30,
        max_db_bytes: int = 1 << 30,
    ) -> Dict[str, Any]:
        """Measured retention state against the P11 ceilings (G23).

        Age keys on durable ``committed_at`` (always present), not on
        producer-supplied timestamps. All committed_at values share the
        ``_iso(utcnow())`` format so ISO string comparison orders correctly.
        Enforcement is explicit (see ``UserControlService.enforce_retention``);
        this method only measures.
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_age_days)
        cutoff_iso = _iso(cutoff)
        assert cutoff_iso is not None
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) AS c FROM evidence").fetchone()["c"]
            expired = self._conn.execute(
                "SELECT COUNT(*) AS c FROM evidence WHERE committed_at < ?",
                (cutoff_iso,),
            ).fetchone()["c"]
            bounds = self._conn.execute(
                "SELECT MIN(committed_at) AS lo, MAX(committed_at) AS hi FROM evidence"
            ).fetchone()
        try:
            db_bytes: Optional[int] = self._db_path.stat().st_size
        except OSError:
            db_bytes = None
        return {
            "max_age_days": max_age_days,
            "cutoff_iso": cutoff_iso,
            "evidence_count": int(count),
            "expired_count": int(expired),
            "oldest_committed_at": bounds["lo"],
            "newest_committed_at": bounds["hi"],
            "db_bytes": db_bytes,
            "max_db_bytes": max_db_bytes,
            "over_age_ceiling": int(expired) > 0,
            "over_size_ceiling": db_bytes is not None and db_bytes >= max_db_bytes,
        }

    # ------------------------------------------------------------------
    # MemoryPort compatibility (legacy-shaped access over durable rows)
    # ------------------------------------------------------------------

    async def append_evidence(self, record: EvidenceRecord) -> str:
        receipt = await self.commit_event(
            source_id=f"legacy:{record.source_type.value}",
            event_id=record.record_id,
            record=record,
        )
        if receipt.state == CommitState.CONFLICT:
            raise ValueError(f"conflicting reuse of evidence identity {record.record_id}")
        if not receipt.committed or receipt.evidence_id is None:
            raise IOError(f"storage commit failed: {receipt.reason}")
        return receipt.evidence_id

    async def get_evidence(self, record_id: str) -> Optional[EvidenceRecord]:
        return await self.get_by_id(record_id)

    async def get_by_id(self, record_id: str) -> Optional[EvidenceRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM evidence WHERE evidence_id = ?", (record_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    async def scan_evidence(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        source_type: Optional[SourceType] = None,
        limit: Optional[int] = 1000,
    ) -> List[EvidenceRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM evidence ORDER BY commit_seq DESC LIMIT ?",
                (limit or 1000,),
            ).fetchall()
            out: List[EvidenceRecord] = []
            for row in rows:
                rec = self._row_to_record(row)
                if source_type is not None and rec.source_type != source_type:
                    continue
                if start_time is not None and rec.persisted_at < start_time:
                    continue
                if end_time is not None and rec.persisted_at > end_time:
                    continue
                out.append(rec)
            return out

    async def query_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        source_filter: Optional[List[str]] = None,
    ) -> AsyncIterator[EvidenceRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM evidence ORDER BY commit_seq ASC"
            ).fetchall()
        for row in rows:
            rec = self._row_to_record(row)
            if not (start_time <= rec.persisted_at <= end_time):
                continue
            if source_filter and rec.source_type.value not in source_filter:
                continue
            yield rec

    async def get_last_hash(self) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT prov_hash FROM evidence ORDER BY commit_seq DESC LIMIT 1"
            ).fetchone()
            return row["prov_hash"] if row else GENESIS_HASH

    async def count_records(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM evidence").fetchone()
            return int(row["c"])

    async def tombstone_record(
        self,
        record_id: str,
        reason: str = "User deletion request",
        user_signature: str = "",
    ) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM evidence WHERE evidence_id = ?", (record_id,)
            ).fetchone()
            if row is None:
                return False
            stored = json.loads(row["record_json"])
            stored["sanitized_payload"] = {}
            stored["window_title"] = None
            stored["target_uri"] = None
            stored["classification"] = ClassificationLevel.PROHIBITED.value
            stored["is_tombstone"] = True
            stored["tombstone_reason"] = reason
            with self._conn:
                self._conn.execute(
                    "UPDATE evidence SET record_json = ? WHERE evidence_id = ?",
                    (json.dumps(stored, sort_keys=True, default=str), record_id),
                )
            return True

    async def apply_tombstone(self, tombstone: TombstoneRecord) -> bool:
        return await self.tombstone_record(
            record_id=tombstone.original_record_id,
            reason=tombstone.revocation_reason,
        )

    def verify_journal_integrity(self) -> Tuple[bool, Optional[str], Optional[int]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM evidence ORDER BY commit_seq ASC"
            ).fetchall()
            expected_prev = GENESIS_HASH
            for i, row in enumerate(rows):
                if row["prev_hash"] != expected_prev:
                    return False, row["evidence_id"], i
                stored = json.loads(row["record_json"])
                data_for_hash = {
                    "record_id": row["evidence_id"],
                    "schema_version": stored.get("schema_version", SCHEMA_VERSION),
                    "persisted_at": stored.get("persisted_at"),
                    "source_type": stored.get("source_type"),
                    "app_identifier": stored.get("app_identifier"),
                    "window_title": stored.get("window_title"),
                    "target_uri": stored.get("target_uri"),
                    "sanitized_payload": stored.get("sanitized_payload"),
                    "classification": stored.get("classification"),
                    "previous_record_hash": row["prev_hash"],
                    "is_tombstone": stored.get("is_tombstone", False),
                    "tombstone_reason": stored.get("tombstone_reason"),
                }
                # Tombstoned rows keep chain continuity by their stored hashes.
                if not stored.get("is_tombstone"):
                    if compute_record_hash(row["prev_hash"], data_for_hash) != row["prov_hash"]:
                        return False, row["evidence_id"], i
                expected_prev = row["prov_hash"]
            return True, None, None
