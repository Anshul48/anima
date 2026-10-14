"""Regression tests for the dev-task source repair (F7/F8/F12-source/F14).

Each test asserts on exact event IDs, order, counts and file content — not
on bare exit codes — so a green run means actual recovery happened. All
fixtures are fresh synthetic dev-task events; the only secret-like string
is a synthetic pattern-shaped token (``ghp_`` + filler), never a credential.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from entorhinal.schemas.models import RawSignalEvent, SourceType
from entorhinal.schemas.task_event import (
    DEV_TASK_SOURCE_ID,
    ProducerManifest,
    TaskEvent,
)
from entorhinal.sources.dev_task import (
    DevTaskSourceAdapter,
    DevTaskSourceConfig,
    DevTaskSourceState,
)

GRANT = "test-grant-1"
ALLOWLISTED_ARTIFACT = "/tmp/dev-task-test/artifacts/report.xml"
ARTIFACT_SHA = hashlib.sha256(b"report-bytes").hexdigest()

# Synthetic pattern-shaped token for redaction tests (not a credential).
FAKE_SECRET = "ghp_" + "Q" * 32


def make_manifest(inbox: Path) -> ProducerManifest:
    return ProducerManifest(
        manifest_version="entorhinal.producer-manifest/v1-draft",
        source_id=DEV_TASK_SOURCE_ID,
        inbox_path=str(inbox),
        activation_boundary_offset=0,
        permitted_fields=["contract_version", "source_id"],
        artifact_allow_list=[
            {"path": ALLOWLISTED_ARTIFACT, "sha256": ARTIFACT_SHA, "revision": "r1"}
        ],  # type: ignore[list-item]
        grant_revision=GRANT,
        retention_class="payload-30d",
    )


def make_config(tmp_path: Path, manifest: ProducerManifest, **overrides) -> DevTaskSourceConfig:
    inbox = Path(manifest.inbox_path)
    kwargs = {
        "inbox_path": inbox,
        "cursor_path": tmp_path / "cursor" / "offset",
        "spool_path": tmp_path / "spool" / "task-events.spool.jsonl",
        "error_log_path": tmp_path / "errors" / "dispositions.jsonl",
        "manifest": manifest,
        "source_id": DEV_TASK_SOURCE_ID,
        "activation_boundary_offset": 0,
        "poll_interval_seconds": 3600.0,  # tests drive poll_once() deterministically
    }
    kwargs.update(overrides)
    return DevTaskSourceConfig(**kwargs)


def make_event_dict(event_id: str = "evt-001", sequence: int = 0, **overrides) -> dict:
    event = {
        "contract_version": "entorhinal.task-event/v1-draft",
        "source_id": DEV_TASK_SOURCE_ID,
        "event_id": event_id,
        "producer_run_id": "run-1",
        "producer_sequence": sequence,
        "producer_version": "test-emitter/v0",
        "work": {"session_id": "s1", "task_id": "t1"},
        "kind": "goal",
        "time": {
            "observed_at": "2026-10-04T00:00:00+00:00",
            "received_at": None,
            "committed_at": None,
            "clock_domain": "test-clock",
            "precision_ms": 1.0,
            "uncertainty_ms": None,
            "source_sequence": sequence,
        },
        "payload": {
            "condition": "Fix the login redirect",
            "excerpts": [
                {"label": "goal-statement", "text": "Fix the login redirect", "truncated": False}
            ],
        },
        "epistemic": "assertion",
        "revision": {},
        "admission": {
            "grant_revision": GRANT,
            "redaction_outcome": None,
            "retention_class": "payload-30d",
            "deletion_generation": 0,
            "revocation_generation": 0,
        },
        "assistance": {},
    }
    event.update(overrides)
    return event


def append_lines(inbox: Path, lines: list[str]) -> None:
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with open(inbox, "a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")


def make_filler(signal_id: str = "filler-1") -> RawSignalEvent:
    return RawSignalEvent(
        signal_id=signal_id,
        source_type=SourceType.TERMINAL_PTY,
        adapter_id="test-filler",
        app_identifier="filler.app",
    )


def signal_ids(signals) -> list[str]:
    return [s.signal_id for s in signals]


# -- F7: denied-log redaction -----------------------------------------------


@pytest.mark.asyncio
async def test_denied_line_with_secret_pattern_stores_no_raw_secret(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    denied = make_event_dict("evt-denied-secret", 0)
    denied["admission"]["grant_revision"] = "forged-grant"
    denied["payload"]["excerpts"] = [
        {"label": "leak", "text": f"deploy token {FAKE_SECRET} done", "truncated": False}
    ]
    append_lines(inbox, [json.dumps(denied)])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == []
        assert adapter.health_check()["denied_count"] == 1
        raw_log = config.error_log_path.read_text(encoding="utf-8")
        assert FAKE_SECRET not in raw_log
        # The secret sits past the 512-char stored prefix; redaction runs
        # on the full line first (proven by redaction_hits), then truncates.
        entry = json.loads(raw_log.strip().split("\n")[0])
        assert entry["kind"] == "denied"
        assert entry["event_id"] == "evt-denied-secret"
        assert entry["offset_start"] == 0
        assert "prefix_sha256" in entry and len(entry["prefix_sha256"]) == 64
        assert "github_token" in entry["redaction_hits"]
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_denied_prefix_window_is_redacted_not_truncated_away(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    denied = make_event_dict("evt-denied-early", 0)
    denied["admission"]["grant_revision"] = "forged-grant"
    # Early field: the secret lands inside the stored 512-char window.
    denied["producer_version"] = f"emitter {FAKE_SECRET}"
    append_lines(inbox, [json.dumps(denied)])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == []
        raw_log = config.error_log_path.read_text(encoding="utf-8")
        assert FAKE_SECRET not in raw_log
        assert "REDACTED" in raw_log
        entry = json.loads(raw_log.strip().split("\n")[0])
        assert entry["event_id"] == "evt-denied-early"
        assert "github_token" in entry["redaction_hits"]
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_malformed_line_with_secret_pattern_stores_no_raw_secret(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [f"NOT-JSON {{{FAKE_SECRET}}} trailing"])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == []
        assert adapter.health_check()["malformed_count"] == 1
        raw_log = config.error_log_path.read_text(encoding="utf-8")
        assert FAKE_SECRET not in raw_log
        assert "REDACTED" in raw_log  # secret inside the stored prefix window
        entry = json.loads(raw_log.strip().split("\n")[0])
        assert entry["kind"] == "malformed-json"
        assert entry["json_valid"] is False
        assert entry["event_id"] is None
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_bad_encoding_line_stores_no_raw_bytes(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_bytes(b"\xff\xfe bad bytes " + FAKE_SECRET.encode() + b"\n")
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == []
        raw_log = config.error_log_path.read_text(encoding="utf-8")
        assert FAKE_SECRET not in raw_log
        entry = json.loads(raw_log.strip().split("\n")[0])
        assert entry["kind"] == "malformed-encoding"
        assert entry["utf8_valid"] is False
    finally:
        await adapter.stop()


# -- F8: rotation / truncation / resync --------------------------------------


@pytest.mark.asyncio
async def test_rotation_same_inode_larger_size_gaps_and_admits(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-before", 0))])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == ["evt-before"]
        size_before = inbox.stat().st_size
        # Same-inode in-place replacement, strictly larger: the old byte
        # offset would misparse without identity detection.
        replacement = make_event_dict("evt-rotated", 1)
        replacement["payload"]["excerpts"] = [
            {"label": "pad", "text": "Y" * (size_before + 200), "truncated": False}
        ]
        inbox.write_text(json.dumps(replacement, sort_keys=True) + "\n", encoding="utf-8")
        assert inbox.stat().st_size > size_before
        await adapter.poll_once()
        health = adapter.health_check()
        assert health["gap_count"] == 1
        assert health["last_gap"]["reason"] == "inbox-rewritten-in-place"
        assert health["rotation_count"] == 1
        assert signal_ids(await adapter.poll_signals()) == ["evt-rotated"]
        assert "evt-rotated" in config.spool_path.read_text(encoding="utf-8")
        assert adapter.cursor_offset == inbox.stat().st_size
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_rotation_new_inode_gaps_and_admits_in_order(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-before", 0))])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == ["evt-before"]
        rotated = inbox.with_name("task-events.jsonl.new")
        rotated.write_text(
            json.dumps(make_event_dict("evt-n1", 1)) + "\n"
            + json.dumps(make_event_dict("evt-n2", 2)) + "\n",
            encoding="utf-8",
        )
        rotated.replace(inbox)  # new inode
        await adapter.poll_once()
        health = adapter.health_check()
        assert health["gap_count"] == 1
        assert health["last_gap"]["reason"] == "inbox-rotated"
        assert signal_ids(await adapter.poll_signals()) == ["evt-n1", "evt-n2"]
        assert adapter.cursor_offset == inbox.stat().st_size
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_truncation_shrink_resyncs_and_admits_replacement(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-before", 0))])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == ["evt-before"]
        # Shrink + replacement content: must gap AND admit (never skip).
        # ("evt-after" is one byte shorter than "evt-before": size < cursor.)
        inbox.write_text(json.dumps(make_event_dict("evt-after", 1)) + "\n", encoding="utf-8")
        await adapter.poll_once()
        health = adapter.health_check()
        assert health["gap_count"] == 1
        assert health["last_gap"]["reason"] == "inbox-truncated-or-rotated"
        assert signal_ids(await adapter.poll_signals()) == ["evt-after"]
        assert adapter.cursor_offset == inbox.stat().st_size
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_restart_after_rotation_resumes_without_loss_or_dupe(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.touch(exist_ok=True)
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    first = DevTaskSourceAdapter(config)
    await first.start()
    try:
        append_lines(inbox, [json.dumps(make_event_dict("evt-r1", 0))])
        await first.poll_once()
        assert signal_ids(await first.poll_signals()) == ["evt-r1"]
        rotated = inbox.with_name("task-events.jsonl.new")
        rotated.write_text(json.dumps(make_event_dict("evt-r2", 1)) + "\n", encoding="utf-8")
        rotated.replace(inbox)
        await first.poll_once()
        assert signal_ids(await first.poll_signals()) == ["evt-r2"]
    finally:
        await first.stop()
    append_lines(inbox, [json.dumps(make_event_dict("evt-r3", 2))])
    second = DevTaskSourceAdapter(config)
    await second.start()
    try:
        # Exactly the new event: no loss, no resurrection of r1/r2.
        assert signal_ids(await second.poll_signals()) == ["evt-r3"]
        assert second.health_check()["gap_count"] == 0
    finally:
        await second.stop()


@pytest.mark.asyncio
async def test_legacy_cursor_shrink_while_stopped_gaps_and_resyncs(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    append_lines(inbox, [json.dumps(make_event_dict("evt-new", 0))])
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    # Legacy bare-int cursor pointing past EOF, no identity sidecar.
    config.cursor_path.parent.mkdir(parents=True, exist_ok=True)
    config.cursor_path.write_text("999999\n", encoding="utf-8")
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        health = adapter.health_check()
        assert health["gap_count"] == 1
        assert health["last_gap"]["reason"] == "inbox-truncated-or-rotated"
        assert signal_ids(await adapter.poll_signals()) == ["evt-new"]
    finally:
        await adapter.stop()


# -- queue backlog: truthful bit + in-runtime recovery ------------------------


@pytest.mark.asyncio
async def test_queue_full_spools_without_counting_then_recovers_in_runtime(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest, max_buffer_size=1)
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert await adapter.emit_signal(make_filler()) is True
        append_lines(inbox, [json.dumps(make_event_dict("evt-qf-1", 0))])
        queued = await adapter.poll_once()
        # Durable but NOT queued: the bit must say 0, not 1.
        assert queued == 0
        assert adapter.cursor_offset == inbox.stat().st_size
        health = adapter.health_check()
        assert health["queue_backlog_count"] == 1
        assert health["spool_pending_count"] == 1
        assert "evt-qf-1" in config.spool_path.read_text(encoding="utf-8")
        # Drain the filler; the backlog recovers on the next scan — no restart.
        assert signal_ids(await adapter.poll_signals()) == ["filler-1"]
        assert await adapter.poll_once() == 1
        assert signal_ids(await adapter.poll_signals()) == ["evt-qf-1"]
        assert adapter.health_check()["queue_backlog_count"] == 0
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_backlog_drains_before_fresh_lines_preserving_order(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest, max_buffer_size=2)
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert await adapter.emit_signal(make_filler("filler-1")) is True
        assert await adapter.emit_signal(make_filler("filler-2")) is True
        append_lines(inbox, [json.dumps(make_event_dict("evt-b1", 0))])
        assert await adapter.poll_once() == 0  # spooled, queue saturated
        assert signal_ids(await adapter.poll_signals()) == ["filler-1", "filler-2"]
        append_lines(inbox, [json.dumps(make_event_dict("evt-b2", 1))])
        # Backlog first, then the fresh line: global spool order holds.
        assert await adapter.poll_once() == 2
        assert signal_ids(await adapter.poll_signals()) == ["evt-b1", "evt-b2"]
    finally:
        await adapter.stop()


# -- F12 source side: durable pending + explicit in-runtime retry -------------


@pytest.mark.asyncio
async def test_drained_unacked_stays_pending_and_requeues_after_grant(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(
        inbox,
        [json.dumps(make_event_dict("evt-p1", 0)), json.dumps(make_event_dict("evt-p2", 1))],
    )
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == ["evt-p1", "evt-p2"]
        # Simulate pump-side policy denial: drained, never committed, never acked.
        health = adapter.health_check()
        assert health["spool_pending_count"] == 2
        assert health["drained_unacked_count"] == 2
        # Ordinary scans must NOT hammer the pump with the rejected events.
        assert await adapter.poll_once() == 0
        assert signal_ids(await adapter.poll_signals()) == []
        # The grant arrives: main calls requeue_pending — recovery, no restart.
        assert adapter.requeue_pending() == 2
        assert signal_ids(await adapter.poll_signals()) == ["evt-p1", "evt-p2"]
        adapter.note_admitted("evt-p1")
        adapter.note_admitted("evt-p2")
        assert adapter.health_check()["spool_pending_count"] == 0
        assert adapter.requeue_pending() == 0
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_pending_ledger_survives_restart_and_requeues_explicitly(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-persist", 0))])
    first = DevTaskSourceAdapter(config)
    await first.start()
    try:
        assert signal_ids(await first.poll_signals()) == ["evt-persist"]
        assert first.health_check()["spool_pending_count"] == 1
    finally:
        await first.stop()
    second = DevTaskSourceAdapter(config)
    await second.start()
    try:
        # No auto-duplication on restart ...
        assert signal_ids(await second.poll_signals()) == []
        assert second.health_check()["spool_pending_count"] == 1
        # ... but explicit requeue resumes the unacked backlog in order.
        assert second.requeue_pending() == 1
        assert signal_ids(await second.poll_signals()) == ["evt-persist"]
    finally:
        await second.stop()


@pytest.mark.asyncio
async def test_note_admitted_ignores_unknown_and_never_raises(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-ack", 0))])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == ["evt-ack"]
        adapter.note_admitted("no-such-event")
        adapter.note_admitted(object())
        adapter.note_admitted(None)
        assert adapter.health_check()["spool_pending_count"] == 1
        adapter.note_admitted("evt-ack")
        assert adapter.health_check()["spool_pending_count"] == 0
    finally:
        await adapter.stop()


# -- F14: full replay + safe compaction ---------------------------------------


@pytest.mark.asyncio
async def test_spool_replay_returns_all_beyond_1000_in_order(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    count = 1050
    append_lines(
        inbox,
        [json.dumps(make_event_dict(f"evt-{i:04d}", i)) for i in range(count)],
    )
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert len(await adapter.poll_signals()) == count
        replayed = adapter.spool_replay()
        assert len(replayed) == count
        assert replayed[0].event_id == "evt-0000"
        assert replayed[-1].event_id == "evt-1049"
        assert [e.event_id for e in replayed] == [f"evt-{i:04d}" for i in range(count)]
        window = adapter.spool_replay(limit=1000)
        assert len(window) == 1000
        assert window[0].event_id == "evt-0050"
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_compact_spool_drops_only_acked_preserving_order(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(
        inbox, [json.dumps(make_event_dict(f"evt-c{i}", i)) for i in range(5)]
    )
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert len(await adapter.poll_signals()) == 5
        adapter.note_admitted("evt-c0")
        adapter.note_admitted("evt-c2")
        adapter.note_admitted("evt-c3")
        with open(config.spool_path, "a", encoding="utf-8") as handle:
            handle.write("not-a-valid-spool-line\n")
        result = adapter.compact_spool()
        assert result["removed"] == 3
        assert result["kept"] == 3  # c1, c4 + the unparseable line
        assert result["kept_unparseable"] == 1
        assert [e.event_id for e in adapter.spool_replay()] == ["evt-c1", "evt-c4"]
        assert [e.event_id for e in adapter.pending_spool_events()] == ["evt-c1", "evt-c4"]
        assert adapter.health_check()["last_compaction"]["removed"] == 3
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_spool_budget_auto_compacts_before_backpressure(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-first", 0))])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == ["evt-first"]
        adapter.note_admitted("evt-first")
        used = adapter.spool_bytes
        # Shrink the budget below 2 records but above 1: without compaction
        # the next (same-size) event would wedge; with it, the acked record
        # is dropped and the event is admitted.
        adapter._config.spool_max_bytes = used + 10
        append_lines(inbox, [json.dumps(make_event_dict("evt-second", 1))])
        assert await adapter.poll_once() == 1
        assert signal_ids(await adapter.poll_signals()) == ["evt-second"]
        assert [e.event_id for e in adapter.spool_replay()] == ["evt-second"]
        assert adapter.health_check()["last_compaction"]["removed"] == 1
    finally:
        await adapter.stop()


# -- N4: managed-copy purge (stop != forget) ----------------------------------


@pytest.mark.asyncio
async def test_purge_managed_removes_targeted_copies_with_measured_counts(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    denied = make_event_dict("evt-denied-x", 0)
    denied["admission"]["grant_revision"] = "forged-grant"
    append_lines(
        inbox,
        [
            json.dumps(make_event_dict("evt-k1", 1)),
            json.dumps(denied),
            json.dumps(make_event_dict("evt-k2", 2)),
        ],
    )
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == ["evt-k1", "evt-k2"]
        cursor_before = adapter.cursor_offset
        result = adapter.purge_managed(
            reason="synthetic test deletion", event_ids={"evt-k1", "evt-denied-x"}
        )
        assert result["spool_removed"] == 1
        assert result["pending_removed"] == 1
        assert result["denied_removed"] == 1
        spool_text = config.spool_path.read_text(encoding="utf-8")
        assert "evt-k1" not in spool_text
        assert "evt-k2" in spool_text
        denied_text = config.error_log_path.read_text(encoding="utf-8")
        assert "evt-denied-x" not in denied_text
        assert [e.event_id for e in adapter.pending_spool_events()] == ["evt-k2"]
        # Cursor and producer inbox are untouched: surviving offsets valid.
        assert adapter.cursor_offset == cursor_before
        assert "evt-k1" in inbox.read_text(encoding="utf-8")
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_purge_managed_rejects_ambiguous_calls(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        with pytest.raises(ValueError):
            adapter.purge_managed(reason="ambiguous")
        with pytest.raises(ValueError):
            adapter.purge_managed(reason="ambiguous", event_ids=set())
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_purged_id_neither_resurrects_via_queue_nor_reemission(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-ghost", 0))])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        # Purged while still sitting in the volatile queue: filtered on drain.
        result = adapter.purge_managed(reason="synthetic test deletion", event_ids={"evt-ghost"})
        assert result["spool_removed"] == 1
        assert signal_ids(await adapter.poll_signals()) == []
        assert adapter.health_check()["purged_filtered_count"] == 1
        # Producer re-emission of the same ID: recorded, never re-admitted.
        denied_before = adapter.health_check()["denied_count"]
        append_lines(inbox, [json.dumps(make_event_dict("evt-ghost", 1))])
        await adapter.poll_once()
        assert signal_ids(await adapter.poll_signals()) == []
        assert adapter.health_check()["denied_count"] == denied_before + 1
        assert "evt-ghost" not in config.spool_path.read_text(encoding="utf-8")
    finally:
        await adapter.stop()


# -- N5: halt cooperation ------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_freezes_cursor_and_poll_never_advances(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-s1", 0))])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    assert signal_ids(await adapter.poll_signals()) == ["evt-s1"]
    cursor_at_stop = adapter.cursor_offset
    await adapter.stop()
    append_lines(inbox, [json.dumps(make_event_dict("evt-s2", 1))])
    assert await adapter.poll_once() == 0
    assert adapter.cursor_offset == cursor_at_stop
    assert adapter.health_check()["dev_task_state"] == DevTaskSourceState.STOPPED.value
    await adapter.start()
    try:
        assert signal_ids(await adapter.poll_signals()) == ["evt-s2"]
    finally:
        await adapter.stop()


# -- N6: lag contract fields ----------------------------------------------------


@pytest.mark.asyncio
async def test_health_exposes_lag_contract_fields(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest, max_buffer_size=2)
    denied = make_event_dict("evt-h-denied", 0)
    denied["admission"]["grant_revision"] = "forged-grant"
    append_lines(
        inbox,
        [json.dumps(denied), json.dumps(make_event_dict("evt-h1", 1))],
    )
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        # start() already admitted evt-h1 (queue: [h1]); saturate, then spool h2.
        assert signal_ids(await adapter.poll_signals()) == ["evt-h1"]
        assert await adapter.emit_signal(make_filler("f1")) is True
        assert await adapter.emit_signal(make_filler("f2")) is True
        append_lines(inbox, [json.dumps(make_event_dict("evt-h2", 2))])
        assert await adapter.poll_once() == 0  # spooled behind the full queue
        health = adapter.health_check()
        assert health["spool_pending_count"] == 2
        assert health["queue_backlog_count"] == 1
        assert health["drained_unacked_count"] == 1  # h1 drained, never acked
        assert health["pending_sample"] == ["evt-h1", "evt-h2"]
        assert health["denied_log_bytes"] > 0
        assert isinstance(health["inbox_dev"], int)
        assert isinstance(health["inbox_ino"], int)
        assert health["rotation_count"] == 0
        assert set(adapter.managed_paths()) == {
            "inbox",
            "cursor",
            "cursor_identity",
            "spool",
            "denied_log",
            "pending_ledger",
        }
        # Drain + ack + compact: lag clears and compaction is disclosed.
        assert signal_ids(await adapter.poll_signals()) == ["f1", "f2"]
        assert await adapter.poll_once() == 1
        assert signal_ids(await adapter.poll_signals()) == ["evt-h2"]
        adapter.note_admitted("evt-h1")
        adapter.note_admitted("evt-h2")
        assert adapter.compact_spool()["removed"] == 2
        health = adapter.health_check()
        assert health["spool_pending_count"] == 0
        assert health["last_compaction"]["removed"] == 2
    finally:
        await adapter.stop()
