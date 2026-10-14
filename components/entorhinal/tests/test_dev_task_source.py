"""Tests for source `entorhinal.dev-task.01` (M1-source, EAP-20261004-v0.2).

Covers the task-event envelope (accept valid; reject undeclared fields and
unresolved artifact paths) and the bounded inbox tailer (boundary start,
durable cursor, idle-vs-offline health, restart without loss/duplication).

No credential-bearing fixtures: the only secret-like string is AWS's
documented fake example key, used to prove producer-side redaction.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from entorhinal.schemas.task_event import (
    DEV_TASK_SOURCE_ID,
    ProducerManifest,
    TaskEvent,
    TaskEventAdmissionError,
    admit_task_event,
)
from entorhinal.sources.dev_task import (
    DevTaskSourceAdapter,
    DevTaskSourceConfig,
    DevTaskSourceState,
)

GRANT = "test-grant-1"
ALLOWLISTED_ARTIFACT = "/tmp/dev-task-test/artifacts/report.xml"
ARTIFACT_SHA = hashlib.sha256(b"report-bytes").hexdigest()


def make_manifest(inbox: Path, artifacts: list[str] | None = None) -> ProducerManifest:
    entries = [
        {"path": path, "sha256": ARTIFACT_SHA, "revision": "r1"}
        for path in (artifacts if artifacts is not None else [ALLOWLISTED_ARTIFACT])
    ]
    return ProducerManifest(
        manifest_version="entorhinal.producer-manifest/v1-draft",
        source_id=DEV_TASK_SOURCE_ID,
        inbox_path=str(inbox),
        activation_boundary_offset=0,
        permitted_fields=["contract_version", "source_id"],
        artifact_allow_list=entries,  # type: ignore[arg-type]
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


def make_event_dict(
    event_id: str = "evt-001",
    sequence: int = 0,
    kind: str = "goal",
    artifact_path: str | None = None,
    **overrides,
) -> dict:
    payload: dict = {
        "condition": "Fix the login redirect",
        "excerpts": [{"label": "goal-statement", "text": "Fix the login redirect", "truncated": False}],
    }
    if artifact_path is not None:
        payload["artifact_refs"] = [
            {
                "path": artifact_path,
                "sha256": ARTIFACT_SHA,
                "revision": "r1",
                "verifier": "test-harness",
            }
        ]
    event = {
        "contract_version": "entorhinal.task-event/v1-draft",
        "source_id": DEV_TASK_SOURCE_ID,
        "event_id": event_id,
        "producer_run_id": "run-1",
        "producer_sequence": sequence,
        "producer_version": "test-emitter/v0",
        "work": {"session_id": "s1", "task_id": "t1"},
        "kind": kind,
        "time": {
            "observed_at": "2026-10-04T00:00:00+00:00",
            "received_at": None,
            "committed_at": None,
            "clock_domain": "test-clock",
            "precision_ms": 1.0,
            "uncertainty_ms": None,
            "source_sequence": sequence,
        },
        "payload": payload,
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


# -- envelope ------------------------------------------------------------


def test_envelope_accepts_valid_event() -> None:
    manifest = make_manifest(Path("/tmp/dev-task-test/inbox/task-events.jsonl"))
    event, notes = admit_task_event(
        make_event_dict(artifact_path=ALLOWLISTED_ARTIFACT),
        source_id=DEV_TASK_SOURCE_ID,
        manifest=manifest,
    )
    assert event.event_id == "evt-001"
    assert event.kind.value == "goal"
    assert notes == [f"artifact resolved: {ALLOWLISTED_ARTIFACT} rev=r1"]


def test_envelope_rejects_undeclared_top_level_field() -> None:
    manifest = make_manifest(Path("/tmp/dev-task-test/inbox/task-events.jsonl"))
    candidate = make_event_dict()
    candidate["sneaky_new_field"] = "nope"
    with pytest.raises(TaskEventAdmissionError):
        admit_task_event(candidate, source_id=DEV_TASK_SOURCE_ID, manifest=manifest)
    with pytest.raises(ValidationError):
        TaskEvent.model_validate(candidate)


def test_envelope_rejects_undeclared_nested_field() -> None:
    manifest = make_manifest(Path("/tmp/dev-task-test/inbox/task-events.jsonl"))
    candidate = make_event_dict()
    candidate["payload"]["undeclared_nested"] = {"anything": True}
    with pytest.raises(TaskEventAdmissionError):
        admit_task_event(candidate, source_id=DEV_TASK_SOURCE_ID, manifest=manifest)


def test_envelope_rejects_unresolved_artifact_path() -> None:
    manifest = make_manifest(Path("/tmp/dev-task-test/inbox/task-events.jsonl"))
    candidate = make_event_dict(artifact_path="/tmp/dev-task-test/artifacts/evil.txt")
    with pytest.raises(TaskEventAdmissionError, match="allow-list"):
        admit_task_event(candidate, source_id=DEV_TASK_SOURCE_ID, manifest=manifest)


def test_envelope_rejects_wrong_source_and_grant() -> None:
    manifest = make_manifest(Path("/tmp/dev-task-test/inbox/task-events.jsonl"))
    wrong_source = make_event_dict()
    wrong_source["source_id"] = "entorhinal.someone-else.99"
    with pytest.raises(TaskEventAdmissionError, match="source_id"):
        admit_task_event(wrong_source, source_id=DEV_TASK_SOURCE_ID, manifest=manifest)
    wrong_grant = make_event_dict()
    wrong_grant["admission"]["grant_revision"] = "forged-grant"
    with pytest.raises(TaskEventAdmissionError, match="grant_revision"):
        admit_task_event(wrong_grant, source_id=DEV_TASK_SOURCE_ID, manifest=manifest)


def test_envelope_rejects_oversize_excerpt() -> None:
    candidate = make_event_dict()
    candidate["payload"]["excerpts"] = [
        {"label": "too-big", "text": "x" * 5000, "truncated": False}
    ]
    with pytest.raises(ValidationError):
        TaskEvent.model_validate(candidate)


def test_to_raw_signal_event_preserves_observed_time_and_source() -> None:
    event = TaskEvent.model_validate(make_event_dict())
    signal = event.to_raw_signal_event()
    assert signal.adapter_id == DEV_TASK_SOURCE_ID
    assert signal.captured_at == datetime(2026, 10, 4, 0, 0, 0, tzinfo=timezone.utc)
    assert signal.raw_payload["event_id"] == "evt-001"


# -- tailer --------------------------------------------------------------


@pytest.mark.asyncio
async def test_tailer_reads_from_boundary_and_advances_cursor(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    # Pre-boundary content must never be read.
    append_lines(inbox, [json.dumps({"stale": "before-activation"})])
    boundary = inbox.stat().st_size
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest, activation_boundary_offset=boundary)
    adapter = DevTaskSourceAdapter(config)

    append_lines(
        inbox,
        [
            json.dumps(make_event_dict("evt-101", 1)),
            json.dumps(make_event_dict("evt-102", 2)),
        ],
    )
    await adapter.start()
    try:
        signals = await adapter.poll_signals()
        assert [s.raw_payload["event_id"] for s in signals] == ["evt-101", "evt-102"]
        assert adapter.cursor_offset == inbox.stat().st_size
        stored = config.cursor_path.read_text(encoding="utf-8").strip()
        assert stored == str(inbox.stat().st_size)
        health = adapter.health_check()
        assert health["cursor_offset"] == inbox.stat().st_size
        assert health["lag_bytes"] == 0
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_tailer_reports_offline_vs_idle(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    manifest = make_manifest(inbox)
    adapter = DevTaskSourceAdapter(make_config(tmp_path, manifest))
    await adapter.start()
    try:
        # Inbox file does not exist -> offline, not idle, not healthy.
        health = adapter.health_check()
        assert health["dev_task_state"] == DevTaskSourceState.OFFLINE.value
        assert health["inbox_exists"] is False
        assert adapter.is_healthy() is False

        # Empty existing inbox -> connected-but-idle, healthy.
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.touch(exist_ok=True)
        await adapter.poll_once()
        health = adapter.health_check()
        assert health["dev_task_state"] == DevTaskSourceState.CONNECTED_IDLE.value
        assert health["inbox_exists"] is True
        assert adapter.is_healthy() is True
        assert health["last_heartbeat"] is not None
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_tailer_survives_restart_without_loss_or_duplication(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.touch(exist_ok=True)
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)

    append_lines(
        inbox,
        [json.dumps(make_event_dict(f"evt-{i}", i)) for i in range(3)],
    )
    first = DevTaskSourceAdapter(config)
    await first.start()
    try:
        batch_one = await first.poll_signals()
    finally:
        await first.stop()
    assert [s.raw_payload["event_id"] for s in batch_one] == ["evt-0", "evt-1", "evt-2"]

    # Restart with the same durable cursor; two new events arrive.
    append_lines(
        inbox,
        [json.dumps(make_event_dict(f"evt-{i}", i)) for i in range(3, 5)],
    )
    second = DevTaskSourceAdapter(config)
    await second.start()
    try:
        batch_two = await second.poll_signals()
    finally:
        await second.stop()

    seen = [s.raw_payload["event_id"] for s in batch_one + batch_two]
    assert seen == ["evt-0", "evt-1", "evt-2", "evt-3", "evt-4"]
    assert len(set(seen)) == 5


@pytest.mark.asyncio
async def test_tailer_denied_line_advances_with_attributable_disposition(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.touch(exist_ok=True)
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)

    denied = make_event_dict("evt-denied", 0)
    denied["undeclared"] = True
    append_lines(
        inbox,
        [json.dumps(denied), json.dumps(make_event_dict("evt-good", 1))],
    )
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        signals = await adapter.poll_signals()
        assert [s.raw_payload["event_id"] for s in signals] == ["evt-good"]
        health = adapter.health_check()
        assert health["denied_count"] == 1
        assert health["lag_bytes"] == 0
        dispositions = config.error_log_path.read_text(encoding="utf-8")
        assert "denied" in dispositions
        assert "offset_start" in dispositions
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_producer_redaction_runs_before_spool_persistence(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.touch(exist_ok=True)
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    adapter = DevTaskSourceAdapter(config)

    candidate = make_event_dict("evt-redact", 0)
    # AWS's documented fake example key (not a real credential).
    candidate["payload"]["excerpts"] = [
        {"label": "diag", "text": "key AKIAIOSFODNN7EXAMPLE leaked in log", "truncated": False}
    ]
    append_lines(inbox, [json.dumps(candidate)])
    await adapter.start()
    try:
        signals = await adapter.poll_signals()
        assert len(signals) == 1
        spooled = config.spool_path.read_text(encoding="utf-8")
        assert "AKIAIOSFODNN7EXAMPLE" not in spooled
        assert "<REDACTED:AWS_KEY>" in spooled
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_spool_budget_reports_backpressure_without_loss(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.touch(exist_ok=True)
    manifest = make_manifest(inbox)
    # Budget smaller than one record: nothing admitted, cursor held.
    config = make_config(tmp_path, manifest, spool_max_bytes=64)
    adapter = DevTaskSourceAdapter(config)
    append_lines(inbox, [json.dumps(make_event_dict("evt-blocked", 0))])
    await adapter.start()
    try:
        signals = await adapter.poll_signals()
        assert signals == []
        health = adapter.health_check()
        assert health["dev_task_state"] == DevTaskSourceState.BACKPRESSURE.value
        assert health["backpressure"] is True
        assert health["cursor_offset"] == 0
        assert health["lag_bytes"] > 0
        assert adapter.is_healthy() is False
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_tailer_reports_truncation_gap(tmp_path: Path) -> None:
    inbox = tmp_path / "capture-inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.touch(exist_ok=True)
    manifest = make_manifest(inbox)
    config = make_config(tmp_path, manifest)
    append_lines(inbox, [json.dumps(make_event_dict("evt-0", 0))])
    adapter = DevTaskSourceAdapter(config)
    await adapter.start()
    try:
        assert len(await adapter.poll_signals()) == 1
        # Simulate rotation: inbox replaced with shorter content.
        inbox.write_text("", encoding="utf-8")
        await adapter.poll_once()
        health = adapter.health_check()
        assert health["gap_count"] == 1
        assert health["last_gap"]["reason"] == "inbox-truncated-or-rotated"
    finally:
        await adapter.stop()


# -- external emitter end-to-end ------------------------------------------


def _write_test_manifest(path: Path, run_dir: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "manifest_version": "entorhinal.producer-manifest/v1-draft",
                "source_id": DEV_TASK_SOURCE_ID,
                "inbox_path": str(run_dir / "capture-inbox" / "task-events.jsonl"),
                "activation_boundary_offset": 0,
                "permitted_fields": ["contract_version", "source_id"],
                "artifact_allow_list": [],
                "grant_revision": GRANT,
                "retention_class": "payload-30d",
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_external_emitter_to_tailer_end_to_end(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    emitter = repo_root / "scripts" / "dev_task_emit.py"
    run_dir = tmp_path / "emitter-run"
    manifest_path = tmp_path / "manifest.json"
    _write_test_manifest(manifest_path, run_dir)

    def run_emit(*argv: str) -> None:
        completed = subprocess.run(
            [sys.executable, str(emitter), *argv],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(repo_root),
        )
        assert completed.returncode == 0, completed.stderr

    run_emit("init", "--run-dir", str(run_dir), "--manifest", str(manifest_path))
    run_emit(
        "goal", "--run-dir", str(run_dir), "--manifest", str(manifest_path),
        "--session", "s9", "--task", "t9", "--text", "End to end check",
    )
    run_emit(
        "attempt", "--run-dir", str(run_dir), "--manifest", str(manifest_path),
        "--session", "s9", "--task", "t9", "--attempt", "a1",
        "--check", "true-check", "--", "true",
    )

    manifest = make_manifest(run_dir / "capture-inbox" / "task-events.jsonl")
    adapter = DevTaskSourceAdapter(make_config(tmp_path, manifest))
    await adapter.start()
    try:
        signals = await adapter.poll_signals()
    finally:
        await adapter.stop()

    kinds = [s.raw_payload["kind"] for s in signals]
    assert kinds == ["goal", "attempt"]
    attempt = signals[1].raw_payload["payload"]["attempt"]
    assert attempt["exit_status"] == 0
    assert signals[1].raw_payload["payload"]["outcome"] == "succeeded"
