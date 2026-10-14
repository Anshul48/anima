"""Tests for the transactional SQLite evidence store and receipt contract.

Covers: commit/reopen durability, exact-retry idempotency, conflict on ID
reuse with changed content, injected storage failure with no visible state,
projector failure with pending/degraded + catch-up, malformed input
rejection, bounded queue behavior, rollback-journal pragmas, chain
integrity, cursor semantics, and MemoryPort compatibility.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from entorhinal.evidence.receipts import CommitState, ProjectionState
from entorhinal.evidence.sqlite_store import SQLiteEvidenceStore
from entorhinal.schemas.models import EvidenceRecord


def _record_dict(app: str = "code", payload: dict | None = None) -> dict:
    return {
        "source_type": "browser",
        "app_identifier": app,
        "window_title": "engine.py - editor",
        "target_uri": "file:///workspace/engine.py",
        "sanitized_payload": payload or {"event_type": "observation", "n": 1},
        "classification": "internal",
    }


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "evidence.db"


@pytest.fixture
def store(store_path: Path):
    s = SQLiteEvidenceStore(store_path)
    yield s
    s.close()


@pytest.mark.asyncio
async def test_pragmas_rollback_journal_no_wal(store: SQLiteEvidenceStore):
    health = store.health()
    assert health["journal_mode"] == "DELETE"
    assert health["synchronous"] == 3  # EXTRA
    assert health["backend"] == "sqlite"


@pytest.mark.asyncio
async def test_commit_reopen_survives(store_path: Path):
    observed = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
    received = datetime(2026, 10, 4, 12, 0, 1, tzinfo=timezone.utc)
    s1 = SQLiteEvidenceStore(store_path)
    r1 = await s1.commit_event(
        "src-A", "evt-1", _record_dict(), observed_at=observed,
        received_at=received, source_seq=42, clock_domain="producer-monotonic",
    )
    assert r1.state == CommitState.COMMITTED_PROJECTED
    assert r1.commit_seq == 1
    assert r1.evidence_id is not None
    s1.close()

    s2 = SQLiteEvidenceStore(store_path)
    try:
        assert await s2.count_records() == 1
        rec = await s2.get_by_id(r1.evidence_id)
        assert rec is not None
        assert rec.app_identifier == "code"
        assert rec.sanitized_payload == {"event_type": "observation", "n": 1}
        # Times / ordering preserved on the stored row.
        conn = sqlite3.connect(str(store_path))
        try:
            row = conn.execute(
                "SELECT observed_at, received_at, committed_at, source_seq, clock_domain,"
                " content_hash, prov_hash FROM evidence WHERE evidence_id = ?",
                (r1.evidence_id,),
            ).fetchone()
        finally:
            conn.close()
        assert row[0] == observed.isoformat()
        assert row[1] == received.isoformat()
        assert row[2] is not None  # committed_at sealed by store
        assert row[3] == 42
        assert row[4] == "producer-monotonic"
        assert row[5] == r1.content_hash
        assert row[6] == rec.provenance_hash
        # Receipt retrievable after restart.
        again = await s2.get_receipt("src-A", "evt-1")
        assert again is not None
        assert again.evidence_id == r1.evidence_id
        assert again.commit_seq == r1.commit_seq
        assert again.content_hash == r1.content_hash
    finally:
        s2.close()


@pytest.mark.asyncio
async def test_exact_retry_returns_original_receipt_one_effect(store: SQLiteEvidenceStore):
    r1 = await store.commit_event("src-A", "evt-9", _record_dict())
    assert r1.committed
    r2 = await store.commit_event("src-A", "evt-9", _record_dict())
    assert r2.state == r1.state
    assert r2.evidence_id == r1.evidence_id
    assert r2.content_hash == r1.content_hash
    assert r2.commit_seq == r1.commit_seq
    assert r2.is_duplicate is True
    assert await store.count_records() == 1


@pytest.mark.asyncio
async def test_conflicting_id_reuse_is_conflict(store: SQLiteEvidenceStore):
    r1 = await store.commit_event("src-A", "evt-7", _record_dict(payload={"v": 1}))
    assert r1.committed
    r2 = await store.commit_event("src-A", "evt-7", _record_dict(payload={"v": 2}))
    assert r2.state == CommitState.CONFLICT
    assert r2.evidence_id == r1.evidence_id  # points at the stored original
    assert await store.count_records() == 1
    stored = await store.get_by_id(r1.evidence_id)
    assert stored is not None and stored.sanitized_payload == {"v": 1}


@pytest.mark.asyncio
async def test_injected_storage_failure_no_visible_state(store: SQLiteEvidenceStore):
    store.fail_next_commits = 1
    r = await store.commit_event("src-A", "evt-fail", _record_dict())
    assert r.state == CommitState.RETRYABLE_STORAGE_FAILURE
    assert r.committed is False
    assert await store.count_records() == 0
    assert await store.get_receipt("src-A", "evt-fail") is None
    # Retry after the fault clears commits normally.
    r2 = await store.commit_event("src-A", "evt-fail", _record_dict())
    assert r2.committed
    assert await store.count_records() == 1


@pytest.mark.asyncio
async def test_fault_injector_failure_no_visible_state(store: SQLiteEvidenceStore):
    def boom():
        raise sqlite3.OperationalError("simulated disk fault")

    store.fault_injector = boom
    r = await store.commit_event("src-A", "evt-boom", _record_dict())
    assert r.state == CommitState.RETRYABLE_STORAGE_FAILURE
    assert await store.count_records() == 0
    store.fault_injector = None
    r2 = await store.commit_event("src-A", "evt-boom", _record_dict())
    assert r2.committed


@pytest.mark.asyncio
async def test_projector_failure_pending_degraded_then_catch_up(store_path: Path):
    def failing_projector(record):
        raise RuntimeError("projection exploded")

    s = SQLiteEvidenceStore(store_path, projector=failing_projector)
    try:
        r = await s.commit_event("src-A", "evt-p", _record_dict())
        assert r.state == CommitState.COMMITTED_PENDING_DEGRADED
        assert r.projection_state == ProjectionState.PENDING
        assert r.evidence_id is not None
        assert await s.pending_count() == 1
        # Event is durable and recoverable despite projector failure.
        assert await s.count_records() == 1
        # Catch-up with a working projector drains durable work.
        projected_ids: list[str] = []
        out = await s.drain_pending(projector=lambda rec: projected_ids.append(rec.record_id))
        assert out["projected"] == 1
        assert out["still_pending"] == 0
        assert projected_ids == [r.evidence_id]
        assert s.projection_watermark() == r.commit_seq
        receipt = await s.get_receipt("src-A", "evt-p")
        assert receipt is not None and receipt.state == CommitState.COMMITTED_PROJECTED
    finally:
        s.close()


@pytest.mark.asyncio
async def test_malformed_inputs_rejected(store: SQLiteEvidenceStore):
    base = _record_dict()
    bad_records = [
        {"app_identifier": "x", "sanitized_payload": {}},  # missing source_type
        {**base, "app_identifier": "  "},  # blank app
        {**base, "sanitized_payload": [1, 2]},  # wrong shape
        {**base, "source_type": "nope"},  # unknown source type
        "not-a-record",  # wrong type entirely
        None,
    ]
    for bad in bad_records:
        r = await store.commit_event("src-A", "evt-bad", bad)  # type: ignore[arg-type]
        assert r.state == CommitState.REJECTED, bad
    r = await store.commit_event("", "evt-x", base)
    assert r.state == CommitState.REJECTED
    r = await store.commit_event("src-A", "  ", base)
    assert r.state == CommitState.REJECTED
    assert await store.count_records() == 0


@pytest.mark.asyncio
async def test_non_serializable_record_rejected(store: SQLiteEvidenceStore):
    class Unserializable:
        def __str__(self):  # pragma: no cover
            raise ValueError("cannot render")

    rec = _record_dict()
    rec["sanitized_payload"] = {"obj": Unserializable()}
    # default=str handles most objects; force failure via circular ref instead
    circ: dict = {}
    circ["self"] = circ
    rec["sanitized_payload"] = circ
    r = await store.commit_event("src-A", "evt-circ", rec)
    assert r.state == CommitState.REJECTED


@pytest.mark.asyncio
async def test_bounded_queue_saturation_is_retryable(tmp_path: Path):
    import time as _time

    def slow_projector(record):
        _time.sleep(0.3)

    s = SQLiteEvidenceStore(tmp_path / "q.db", queue_size=2, projector=slow_projector)
    try:
        results = await asyncio.gather(*[
            s.commit_event("src-Q", f"evt-{i}", _record_dict(app=f"app-{i}"))
            for i in range(8)
        ])
        states = [r.state for r in results]
        assert CommitState.RETRYABLE_STORAGE_FAILURE in states
        committed = [r for r in results if r.committed]
        assert len(committed) >= 1
        assert await s.count_records() == len(committed)
    finally:
        s.close()


@pytest.mark.asyncio
async def test_chain_integrity_across_commits(store: SQLiteEvidenceStore):
    for i in range(5):
        r = await store.commit_event("src-A", f"evt-{i}", _record_dict(app=f"app-{i}"))
        assert r.committed
    valid, bad_id, bad_idx = store.verify_journal_integrity()
    assert valid and bad_id is None and bad_idx is None
    last = await store.get_last_hash()
    assert len(last) == 64


@pytest.mark.asyncio
async def test_cursors_advance_and_persist(store_path: Path):
    s = SQLiteEvidenceStore(store_path)
    try:
        assert await s.get_cursor("src-A") is None
        r = await s.commit_event("src-A", "evt-1", _record_dict())
        assert r.committed
        await s.advance_cursor("src-A", "offset-100")
        assert await s.get_cursor("src-A") == "offset-100"
    finally:
        s.close()
    s2 = SQLiteEvidenceStore(store_path)
    try:
        assert await s2.get_cursor("src-A") == "offset-100"
    finally:
        s2.close()


@pytest.mark.asyncio
async def test_memoryport_compat_append_scan_tombstone(store: SQLiteEvidenceStore):
    rec = EvidenceRecord(
        source_type="browser",  # type: ignore[arg-type]
        app_identifier="code",
        sanitized_payload={"k": "v"},
        provenance_hash="0" * 64,
        previous_record_hash="0" * 64,
    )
    rid = await store.append_evidence(rec)
    assert rid
    got = await store.get_evidence(rid)
    assert got is not None and got.app_identifier == "code"
    scanned = await store.scan_evidence(limit=10)
    assert len(scanned) == 1
    assert await store.count_records() == 1
    assert await store.tombstone_record(rid, reason="test forget") is True
    tombed = await store.get_by_id(rid)
    assert tombed is not None and tombed.is_tombstone is True
    assert tombed.sanitized_payload == {}
    valid, _, _ = store.verify_journal_integrity()
    assert valid
