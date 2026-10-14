"""Coordinator integration tests: dev-task adapter + runtime factory + store.

Covers the integration seams between the sibling workers' deliverables:
adapter registration, stable-id idempotency through conversion, unknown
observed-time preservation, and startup spool reconciliation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from entorhinal.runtime import (
    RuntimeConfig,
    SourceSpec,
    build_runtime,
    registered_adapters,
)
from entorhinal.schemas.task_event import (
    DEV_TASK_SOURCE_ID,
    ProducerManifest,
    TaskEvent,
)
from entorhinal.sources import dev_task as dev_task_module

pytestmark = pytest.mark.asyncio

GRANT = "test-grant-1"
ALLOWLISTED_ARTIFACT = "/tmp/dev-task-test/artifacts/report.xml"
ARTIFACT_SHA = hashlib.sha256(b"report-bytes").hexdigest()


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


def make_event_dict(event_id: str = "evt-001", sequence: int = 0) -> dict:
    return {
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


def _write_manifest(tmp_path: Path, inbox: Path) -> Path:
    manifest = make_manifest(inbox)
    path = tmp_path / "producer-manifest.json"
    path.write_text(manifest.model_dump_json(), encoding="utf-8")
    return path


def _spec(name: str, inbox: Path, manifest_path: Path, **options) -> SourceSpec:
    opts = {"inbox_path": str(inbox), "manifest_path": str(manifest_path)}
    opts.update({k: str(v) for k, v in options.items()})
    return SourceSpec(name=name, adapter="dev-task-inbox", options=opts)


async def test_dev_task_adapter_registered_and_builds(tmp_path: Path):
    assert "dev-task-inbox" in registered_adapters()
    inbox = tmp_path / "inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("", encoding="utf-8")
    manifest_path = _write_manifest(tmp_path, inbox)
    adapter = dev_task_module.dev_task_adapter_factory(
        _spec(DEV_TASK_SOURCE_ID, inbox, manifest_path)
    )
    assert adapter.adapter_id == DEV_TASK_SOURCE_ID
    assert adapter.health_check()["inbox_path"] == str(inbox)


async def test_dev_task_factory_fail_closed(tmp_path: Path):
    inbox = tmp_path / "inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("", encoding="utf-8")
    manifest_path = _write_manifest(tmp_path, inbox)
    with pytest.raises(ValueError, match="inbox_path"):
        dev_task_module.dev_task_adapter_factory(
            SourceSpec(name="x", adapter="dev-task-inbox", options={})
        )
    with pytest.raises(ValueError, match="manifest_path"):
        dev_task_module.dev_task_adapter_factory(
            SourceSpec(
                name="x",
                adapter="dev-task-inbox",
                options={"inbox_path": str(inbox)},
            )
        )
    other = tmp_path / "other.jsonl"
    other.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        dev_task_module.dev_task_adapter_factory(
            _spec(DEV_TASK_SOURCE_ID, other, manifest_path)
        )


async def test_conversion_idempotent_through_runtime(tmp_path: Path):
    inbox = tmp_path / "inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("", encoding="utf-8")
    manifest_path = _write_manifest(tmp_path, inbox)
    event = TaskEvent.model_validate(make_event_dict(event_id="evt-stable-1"))
    first = event.to_raw_signal_event()
    second = event.to_raw_signal_event()
    assert first.signal_id == "evt-stable-1" == second.signal_id

    config = RuntimeConfig.from_root(
        tmp_path / "runtime",
        sources=[_spec(DEV_TASK_SOURCE_ID, inbox, manifest_path)],
        default_allow=True,
    )
    runtime = build_runtime(config)
    try:
        await runtime.start_sources()
        try:
            r1 = await runtime.admit_signal(DEV_TASK_SOURCE_ID, first)
            r2 = await runtime.admit_signal(DEV_TASK_SOURCE_ID, second)
            assert r1.committed and r2.committed
            assert r2.is_duplicate
            assert r2.evidence_id == r1.evidence_id
            assert r2.content_hash == r1.content_hash
            assert await runtime.store.count_records() == 1
        finally:
            await runtime.stop_sources()
    finally:
        runtime.close()


async def test_unknown_observed_time_preserved(tmp_path: Path):
    inbox = tmp_path / "inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("", encoding="utf-8")
    manifest_path = _write_manifest(tmp_path, inbox)
    data = make_event_dict(event_id="evt-unknown-time")
    data["time"]["observed_at"] = None
    event = TaskEvent.model_validate(data)
    config = RuntimeConfig.from_root(
        tmp_path / "runtime",
        sources=[_spec(DEV_TASK_SOURCE_ID, inbox, manifest_path)],
        default_allow=True,
    )
    runtime = build_runtime(config)
    try:
        await runtime.start_sources()
        try:
            receipt = await runtime.admit_signal(
                DEV_TASK_SOURCE_ID, event.to_raw_signal_event()
            )
            assert receipt.committed
        finally:
            await runtime.stop_sources()
    finally:
        runtime.close()
    with sqlite3.connect(config.db_path) as conn:
        row = conn.execute(
            "SELECT observed_at FROM evidence WHERE event_id = ?",
            ("evt-unknown-time",),
        ).fetchone()
    assert row is not None
    assert row[0] is None


async def test_spool_reconciliation_commits_after_restart(tmp_path: Path):
    inbox = tmp_path / "inbox" / "task-events.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    inbox.write_text("", encoding="utf-8")
    manifest_path = _write_manifest(tmp_path, inbox)
    line = json.dumps(make_event_dict(event_id="evt-spooled-1")) + "\n"
    with open(inbox, "a", encoding="utf-8") as handle:
        handle.write(line)

    spec = _spec(DEV_TASK_SOURCE_ID, inbox, manifest_path)
    # Phase 1: standalone tailer scan spools the event but nothing commits it
    # (simulates a crash between durable spool and store commit).
    lone = dev_task_module.dev_task_adapter_factory(spec)
    await lone.start()  # start() runs one synchronous scan itself
    try:
        assert len(lone.spool_replay()) == 1
        assert lone.health_check()["events_captured"] == 1
    finally:
        await lone.stop()

    # Phase 2: full runtime start reconciles the spool into the store.
    config = RuntimeConfig.from_root(
        tmp_path / "runtime", sources=[spec], default_allow=True
    )
    runtime = build_runtime(config)
    try:
        await runtime.start_sources()
        try:
            assert await runtime.store.count_records() == 1
            receipt = await runtime.store.get_receipt(DEV_TASK_SOURCE_ID, "evt-spooled-1")
            assert receipt is not None and receipt.committed
            # Pump must not create a second effect for the same event.
            await asyncio.sleep(0.5)
            assert await runtime.store.count_records() == 1
        finally:
            await runtime.stop_sources()
    finally:
        runtime.close()

    # Phase 3: a further restart stays at one effect.
    runtime2 = build_runtime(config)
    try:
        await runtime2.start_sources()
        try:
            assert await runtime2.store.count_records() == 1
        finally:
            await runtime2.stop_sources()
    finally:
        runtime2.close()
