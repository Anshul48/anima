"""F3/F13 regression tests: forget runs on the durable SQLite runtime.

Covers:
1. ``forget_time_range`` tombstones only records inside the bounded window
   on a SQLiteEvidenceStore backend (F13).
2. The deletion proof reports the backend, a monotonic deletion generation,
   and producer-side residue disclosure (F13).
3. Owned sanitized-spool copies are purged while producer inbox lines are
   retained and disclosed (F13).
4. The ``entorhinal forget`` CLI operates on the durable runtime the daemon
   serves and refuses a directory without one (F3).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

import pytest
from typer.testing import CliRunner

from entorhinal.cli.main import app as cli_app
from entorhinal.evidence.sqlite_store import SQLiteEvidenceStore
from entorhinal.runtime.factory import build_runtime
from entorhinal.schemas.models import EvidenceRecord, SourceType


def _make_record(title: str, uri: str, secret: str) -> EvidenceRecord:
    return EvidenceRecord.create(
        source_type=SourceType.BROWSER,
        app_identifier="Chrome",
        window_title=title,
        target_uri=uri,
        sanitized_payload={"note": secret},
        previous_record_hash="0" * 64,
    )


@pytest.mark.asyncio
async def test_forget_time_range_filters_sqlite_store_window() -> None:
    """F13: on the SQLite backend, forget deletes only the bounded window."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            first = await store.append_evidence(_make_record("Keep Me", "https://x/keep", "KEEP_SECRET"))
            second = await store.append_evidence(_make_record("Also Keep", "https://x/keep2", "KEEP_SECRET_2"))
            assert first and second

            from entorhinal.user_control.service import UserControlService

            service = UserControlService(journal=store, storage_dir=root)  # type: ignore[arg-type]

            # Window entirely in the past: nothing committed then, nothing deleted.
            past_start = datetime.now(timezone.utc) - timedelta(days=2)
            past_end = past_start + timedelta(hours=1)
            proof_empty = await service.forget_time_range(
                start_time=past_start, end_time=past_end, reason="test past window"
            )
            assert proof_empty["backend"] == "SQLiteEvidenceStore"
            assert proof_empty["time_filter_applied"] is True
            assert proof_empty["tombstoned_records_count"] == 0
            assert proof_empty["deletion_generation"] == 1
            assert (await store.get_by_id(first)).sanitized_payload == {"note": "KEEP_SECRET"}

            # Window covering now: both records fall inside and are tombstoned.
            now = datetime.now(timezone.utc)
            proof = await service.forget_time_range(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                reason="test current window",
            )
            assert proof["tombstoned_records_count"] == 2
            assert proof["journal_integrity_valid"] is True
            assert proof["residual_leakage_count"] == 0
            assert proof["deletion_generation"] == 2
            assert (await store.get_by_id(first)).sanitized_payload == {}
            assert (await store.get_by_id(second)).sanitized_payload == {}
        finally:
            store.close()


@pytest.mark.asyncio
async def test_forget_purges_spool_and_discloses_inbox_residue() -> None:
    """F13/I-1: owned spool copies are purged BY EVENT IDENTITY; producer
    inbox retention is disclosed; non-target spool lines sharing producer
    boilerplate survive (no over-purge)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        inbox = root / "inbox.jsonl"
        state_dir = root / "dev-task-state"
        state_dir.mkdir()
        spool = state_dir / "sanitized.spool.jsonl"

        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            record = _make_record("Residue Title", "https://x/residue", "RESIDUE_SECRET")
            record_id = await store.append_evidence(record)
            # Spool lines carry producer event ids; resolve the committed one.
            keys = store.event_keys_for([record_id])
            target_event_id = keys[record_id]["event_id"]
            inbox.write_text(
                '{"event_id": "evt-1", "title": "Residue Title", "payload": "RESIDUE_SECRET"}\n'
                '{"event_id": "evt-2", "title": "Unrelated", "payload": "nothing"}\n',
                encoding="utf-8",
            )
            spool.write_text(
                '{"event_id": "%s", "title": "Residue Title", "payload": "RESIDUE_SECRET"}\n'
                '{"event_id": "evt-9", "title": "Residue Title template", "payload": "other"}\n'
                % target_event_id,
                encoding="utf-8",
            )

            from entorhinal.user_control.service import UserControlService

            service = UserControlService(
                journal=store,  # type: ignore[arg-type]
                storage_dir=root,
                source_specs=[{
                    "name": "dev-task",
                    "adapter": "dev-task-inbox",
                    "options": {"inbox_path": str(inbox)},
                }],
            )
            now = datetime.now(timezone.utc)
            proof = await service.forget_time_range(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                reason="test residue handling",
            )
            assert proof["tombstoned_records_count"] == 1

            by_kind = {r["kind"]: r for r in proof["producer_residues"]}
            spool_item = by_kind["sanitized-spool"]
            assert spool_item["purge_scope"] == "event-identity"
            # Both spool lines mention a deleted marker ("Residue Title");
            # only the identity-attributed target line is purged.
            assert spool_item["matched_lines"] == 2
            assert spool_item["attributed_lines"] == 1
            assert spool_item["purged_lines"] == 1
            assert by_kind["inbox"]["matched_lines"] == 1
            assert by_kind["inbox"]["purged_lines"] == 0

            # Spool no longer carries the deleted payload; the non-target
            # line sharing boilerplate survives (I-1 no-over-purge).
            spool_text = spool.read_text(encoding="utf-8")
            assert "RESIDUE_SECRET" not in spool_text
            assert "evt-9" in spool_text
            # Producer inbox is untouched but disclosed as uncovered residue.
            assert "RESIDUE_SECRET" in inbox.read_text(encoding="utf-8")
            uncovered_kinds = {r["kind"] for r in proof["uncovered_residues"]}
            assert "inbox" in uncovered_kinds
            # The retained non-target marker match stays disclosed.
            assert "sanitized-spool" in uncovered_kinds
            assert target_event_id in proof["tombstoned_event_ids"]
            assert record_id in proof["tombstoned_record_ids"]
        finally:
            store.close()


def test_cli_forget_requires_durable_runtime() -> None:
    """F3: forget refuses a directory that has no daemon-served store."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = runner.invoke(cli_app, [
            "forget",
            "--start", "2026-08-17T00:00:00Z",
            "--end", "2026-08-17T23:59:59Z",
            "--dir", tmp_dir,
        ])
        assert result.exit_code == 1
        assert "No durable runtime" in result.stdout


def test_cli_forget_operates_on_runtime_store() -> None:
    """F3: forget tombstones records in the runtime evidence.db via the CLI."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        import asyncio

        record_id = asyncio.run(store.append_evidence(
            _make_record("CLI Forget Me", "https://x/cli", "CLI_SECRET")
        ))
        store.close()

        result = runner.invoke(cli_app, [
            "forget",
            "--start", "2020-01-01T00:00:00Z",
            "--end", "2030-01-01T00:00:00Z",
            "--reason", "CLI runtime forget test",
            "--dir", tmp_dir,
        ])
        assert result.exit_code == 0, result.stdout
        assert "Cryptographic Deletion Verification Proof" in result.stdout
        assert "SQLiteEvidenceStore" in result.stdout

        check = SQLiteEvidenceStore(root / "evidence.db")
        try:
            record = asyncio.run(check.get_by_id(record_id))
            assert record is not None
            assert record.sanitized_payload == {}
            assert record.is_tombstone is True
            assert check.get_meta("deletion_generation") == "1"
        finally:
            check.close()


def test_build_runtime_threads_source_specs_to_deletion_engine() -> None:
    """Factory wiring: source specs reach the deletion engine for residue scans."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        from entorhinal.runtime.config import RuntimeConfig, SourceSpec

        inbox = Path(tmp_dir) / "inbox.jsonl"
        inbox.write_text("{}\n", encoding="utf-8")
        config = RuntimeConfig.from_root(
            tmp_dir,
            sources=[SourceSpec(
                name="dev-task",
                adapter="dev-task-inbox",
                options={"inbox_path": str(inbox)},
            )],
        )
        runtime = build_runtime(config)
        try:
            engine = runtime.user_control.deletion_engine
            assert engine.storage_root == Path(tmp_dir)
            assert engine.source_specs[0]["options"]["inbox_path"] == str(inbox)
            kinds = {f["kind"] for f in engine._producer_files()}
            assert {"inbox", "sanitized-spool", "denial-log"} <= kinds
        finally:
            runtime.close()
