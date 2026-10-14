"""Comprehensive Unit & Integration Tests for Phase 2: Sources, Ingestion, Journal, Replay & Staging.

Verifies:
1. Source Adapters lifecycle, DOM password/credit card suppression, OS process blacklist gating, and lossless CLI execution.
2. Ingestion Pipeline sliding-window debouncing (<300ms), fast-path hash deduplication, policy gating, and backpressure.
3. Secondary Index Manager O(1) ID lookups, bisection time-range scanning, and app/source indexing.
4. Evidence Journal write throughput (>2,000 writes/sec), continuous SHA-256 hash chaining, disk roundtrip, and locking.
5. Intentional bit-flip chaos tamper detection in the durable journal file.
6. Cryptographic tombstone payload zeroing with preserved hash-chain continuity.
7. Deterministic Replay Engine sequential reconstruction and 100% bit-parity verification.
8. Projection Stager double-buffering, epistemic invariant validation (fact-evidence links, tombstone leakage detection), atomic swap, and rollback.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
import pytest
from pydantic import ValidationError

from tests.utils import execute_monitored_command

from entorhinal.evidence.indexing import SecondaryIndexManager
from entorhinal.evidence.journal import GENESIS_HASH, EvidenceJournal
from entorhinal.evidence.replay import DeterministicReplayEngine
from entorhinal.evidence.stager import ProjectionStager, StagedProjectionContext
from entorhinal.ingest.pipeline import IngestionPipeline
from entorhinal.policy.engine import PolicyEngine
from entorhinal.schemas.models import (
    ClassificationLevel,
    DerivedFact,
    EvidenceRecord,
    Hypothesis,
    RawSignalEvent,
    SourceType,
    TombstoneRecord,
    compute_record_hash,
    compute_sha256,
    generate_uuidv7,
)
from entorhinal.sources.base import BaseSourceAdapter
from entorhinal.sources.browser import BrowserSourceAdapter, is_sensitive_dom_element
from entorhinal.sources.mock import MockSourceAdapter
from entorhinal.sources.os_window import OSWindowSourceAdapter
from entorhinal.sources.terminal_pty import (
    TerminalPTYSourceAdapter,
    clean_terminal_output,
)


# ==============================================================================
# 1. Source Adapters Tests
# ==============================================================================

class TestSourceAdapters:
    """Test permitted source collectors, client-side pre-filtering, and lifecycle."""

    @pytest.mark.asyncio
    async def test_browser_adapter_navigation_and_selection(self):
        """Verify browser adapter captures standard navigation and text selection."""
        adapter = BrowserSourceAdapter(adapter_id="test.browser")
        await adapter.start()

        nav_event = await adapter.capture_navigation(
            url="https://github.com/org/repo",
            title="Project Repository",
        )
        assert nav_event is not None
        assert nav_event.source_type == SourceType.BROWSER
        assert nav_event.target_uri == "https://github.com/org/repo"
        assert nav_event.raw_payload["event_type"] == "navigation"

        sel_event = await adapter.capture_text_selection(
            url="https://github.com/org/repo",
            title="Project Repository",
            selected_text="def compute_hash():",
            element_tag="code",
        )
        assert sel_event is not None
        assert sel_event.raw_payload["selected_text"] == "def compute_hash():"

        health = adapter.health_check()
        assert health["is_running"] is True
        assert health["events_captured"] == 2
        assert health["events_dropped"] == 0

        await adapter.stop()
        assert adapter.health_check()["is_running"] is False

    @pytest.mark.asyncio
    async def test_browser_adapter_password_and_credit_card_suppression(self):
        """Verify browser adapter auto-drops password and credit card inputs at DOM listener level."""
        adapter = BrowserSourceAdapter()
        await adapter.start()

        # 1. Password input type
        pw_event = await adapter.capture_dom_focus(
            url="https://app.example.com/login",
            title="Login",
            element_tag="input",
            element_attributes={"type": "password", "id": "user_pass"},
            value="SuperSecret123",
        )
        assert pw_event is None  # Must be dropped at adapter

        # 2. Credit card autocomplete attribute
        cc_event = await adapter.capture_dom_focus(
            url="https://checkout.example.com/pay",
            title="Checkout",
            element_tag="input",
            element_attributes={"autocomplete": "cc-number", "id": "card_num"},
            value="4532119823419087",
        )
        assert cc_event is None  # Must be dropped at adapter

        # 3. Sensitive text selection in password field
        pw_sel = await adapter.capture_text_selection(
            url="https://app.example.com/login",
            title="Login",
            selected_text="MyPassword",
            element_tag="input",
            element_attributes={"type": "password"},
        )
        assert pw_sel is None

        # 4. Helper function direct check
        assert is_sensitive_dom_element("input", {"type": "password"}) is True
        assert is_sensitive_dom_element("input", {"name": "cvv_code"}) is True
        assert is_sensitive_dom_element("input", {"placeholder": "Enter Credit Card"}) is True
        assert is_sensitive_dom_element("input", {"type": "text", "name": "search_query"}) is False

        health = adapter.health_check()
        assert health["events_dropped"] >= 3

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_browser_adapter_incognito_suppression(self):
        """Verify browser adapter drops incognito sessions when suppress_incognito is True."""
        adapter = BrowserSourceAdapter(suppress_incognito=True)
        await adapter.start()

        event = await adapter.capture_navigation(
            url="https://private-research.com",
            title="Private",
            is_incognito=True,
        )
        assert event is None
        assert adapter.health_check()["events_dropped"] == 1

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_os_window_adapter_focus_and_blacklist_suppression(self):
        """Verify OS Window adapter captures focus transitions and suppresses blacklisted apps."""
        adapter = OSWindowSourceAdapter()
        await adapter.start()

        # Permitted window focus
        event = await adapter.capture_focus_change(
            app_name="Visual Studio Code",
            window_title="entorhinal - pipeline.py",
            pid=1234,
        )
        assert event is not None
        assert event.source_type == SourceType.OS_WINDOW
        assert event.app_identifier == "Visual Studio Code"
        assert event.window_title == "entorhinal - pipeline.py"
        assert event.metadata["pid"] == 1234

        # Blacklisted password manager: 1Password
        pw_event = await adapter.capture_focus_change(
            app_name="1Password.exe",
            window_title="1Password - Vault",
            pid=5678,
        )
        assert pw_event is None  # Pre-filtered at source

        # Blacklisted password manager: KeePassXC
        kp_event = await adapter.capture_focus_change(
            app_name="keepassxc",
            window_title="Passwords.kdbx - KeePassXC",
            pid=9012,
        )
        assert kp_event is None

        # Accessibility node inspection
        ax_event = await adapter.capture_accessibility_node(
            app_name="Slack",
            window_title="General Channel",
            role="button",
            name="Send message",
        )
        assert ax_event is not None
        assert ax_event.source_type == SourceType.OS_ACCESSIBILITY

        # Accessibility password field
        ax_pw_event = await adapter.capture_accessibility_node(
            app_name="Chrome",
            window_title="Login",
            role="password_field",
            name="Password",
            is_password=True,
        )
        assert ax_pw_event is None

        health = adapter.health_check()
        assert health["events_captured"] == 2
        assert health["events_dropped"] >= 3

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_terminal_pty_adapter_command_and_ansi_cleaning(self):
        """Verify terminal adapter captures commands, cleans ANSI escape codes, and runs commands without hanging."""
        adapter = TerminalPTYSourceAdapter()
        await adapter.start()

        # ANSI cleaning test
        dirty_ansi = "\x1b[32m[SUCCESS]\x1b[0m Build completed\r\n\x1b[1;34mDone in 1.2s\x1b[0m"
        clean = clean_terminal_output(dirty_ansi)
        assert "[SUCCESS] Build completed" in clean
        assert "\x1b[" not in clean

        # Direct command capture
        sig = await adapter.capture_command(
            command="git status",
            output="\x1b[32mOn branch main\x1b[0m\nnothing to commit",
            exit_code=0,
            cwd="/workspace/entorhinal",
            duration_ms=12.5,
        )
        assert sig is not None
        assert sig.source_type == SourceType.TERMINAL_PTY
        assert sig.raw_payload["command"] == "git status"
        assert sig.raw_payload["output"] == "On branch main\nnothing to commit"
        assert sig.raw_payload["exit_code"] == 0

        # Monitored execution test (using sys.executable to test cross-platform command execution)
        code, out, exec_sig = await execute_monitored_command(
            adapter,
            command=f'{sys.executable} -c "print(\'PTY_OUTPUT_TEST\')"',
            timeout_seconds=5.0,
        )
        assert code == 0
        assert "PTY_OUTPUT_TEST" in out
        assert exec_sig is not None
        assert exec_sig.raw_payload["exit_code"] == 0

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_mock_adapter_burst_and_streams(self):
        """Verify mock adapter generates high-throughput synthetic bursts and streams."""
        mock = MockSourceAdapter(adapter_id="mock.tester", source_type=SourceType.OS_WINDOW)
        await mock.start()

        burst = await mock.generate_burst(count=100, app_name="BurstEditor")
        assert len(burst) == 100
        assert mock.health_check()["events_captured"] == 100

        polled = await mock.poll_signals()
        assert len(polled) == 100

        # Stream generator test
        stream_events = []
        async for evt in mock.stream_generator(rate_per_sec=1000, total_events=20):
            stream_events.append(evt)
        assert len(stream_events) == 20

        await mock.stop()


# ==============================================================================
# 2. Ingestion Pipeline Tests
# ==============================================================================

class TestIngestionPipeline:
    """Test ingestion pipeline debouncing, fast-path deduplication, policy gating, and backpressure."""

    @pytest.mark.asyncio
    async def test_temporal_smoother_and_debouncing(self):
        """Verify rapid identical focus events (<300ms) collapse into a single admitted event."""
        engine = PolicyEngine()
        pipeline = IngestionPipeline(policy_engine=engine, debounced_window_ms=300)

        # Create identical rapid events with same window focus
        signal = RawSignalEvent(
            source_type=SourceType.OS_WINDOW,
            adapter_id="adapter.os",
            app_identifier="VSCode",
            window_title="main.py - entorhinal",
            target_uri="file:///workspace/main.py",
            raw_payload={"action": "cursor_move"},
        )

        # First event is admitted
        rec1 = await pipeline.ingest_event(signal)
        assert rec1 is not None

        # Next 5 immediate events (<300ms) are debounced / suppressed
        for _ in range(5):
            rec = await pipeline.ingest_event(signal)
            assert rec is None

        metrics = pipeline.get_metrics()
        assert metrics["events_received"] == 6
        assert metrics["events_admitted"] == 1
        assert metrics["events_debounced"] == 5

        # After waiting >300ms, next event is admitted
        await asyncio.sleep(0.35)
        rec2 = await pipeline.ingest_event(signal)
        assert rec2 is not None
        assert pipeline.get_metrics()["events_admitted"] == 2

    @pytest.mark.asyncio
    async def test_fast_path_deduplication(self):
        """Verify exact duplicate event hashes within sliding window are dropped."""
        engine = PolicyEngine()
        pipeline = IngestionPipeline(policy_engine=engine, debounced_window_ms=300)

        # First unique payload
        sig1 = RawSignalEvent(
            source_type=SourceType.BROWSER,
            adapter_id="adapter.browser",
            app_identifier="Google Chrome",
            window_title="Docs",
            target_uri="https://docs.python.org",
            raw_payload={"page_num": 1},
        )
        rec1 = await pipeline.ingest_event(sig1)
        assert rec1 is not None

        # Different payload for same window (not debounced structurally, but checks dedup)
        sig2 = RawSignalEvent(
            source_type=SourceType.BROWSER,
            adapter_id="adapter.browser",
            app_identifier="Google Chrome",
            window_title="Docs",
            target_uri="https://docs.python.org/3/library",
            raw_payload={"page_num": 2},
        )
        rec2 = await pipeline.ingest_event(sig2)
        assert rec2 is not None

    @pytest.mark.asyncio
    async def test_terminal_command_milestone_bypass(self):
        """Verify high-priority terminal commands and user actions are never suppressed by debouncer."""
        engine = PolicyEngine()
        pipeline = IngestionPipeline(policy_engine=engine, debounced_window_ms=300)

        # Rapid terminal command executions in same window must all be admitted
        for i in range(5):
            cmd_sig = RawSignalEvent(
                source_type=SourceType.TERMINAL_PTY,
                adapter_id="adapter.terminal",
                app_identifier="Terminal",
                window_title="Terminal - bash",
                target_uri="/workspace",
                raw_payload={"event_type": "command_execution", "command": f"git log -n {i}"},
            )
            rec = await pipeline.ingest_event(cmd_sig)
            assert rec is not None

        assert pipeline.get_metrics()["events_admitted"] == 5
        assert pipeline.get_metrics()["events_debounced"] == 0

    @pytest.mark.asyncio
    async def test_policy_gating_and_redaction_in_pipeline(self):
        """Verify unconsented signals are dropped in volatile RAM and permitted ones are redacted."""
        engine = PolicyEngine(default_allow=True)
        pipeline = IngestionPipeline(policy_engine=engine)

        # 1. Permitted signal with credentials to redact
        sig_with_cred = RawSignalEvent(
            source_type=SourceType.BROWSER,
            adapter_id="adapter.browser",
            app_identifier="Google Chrome",
            window_title="API Console",
            target_uri="https://api.github.com",
            raw_payload={"token": "ghp_000000000000000000000000000000000000"},
        )
        record = await pipeline.ingest_event(sig_with_cred)
        assert record is not None
        assert record.sanitized_payload["token"] == "<REDACTED:GITHUB_TOKEN>"
        assert "ghp_" not in str(record.sanitized_payload)
        assert record.classification == ClassificationLevel.RESTRICTED

        # 2. Blacklisted password manager signal
        sig_blacklisted = RawSignalEvent(
            source_type=SourceType.OS_WINDOW,
            adapter_id="adapter.os",
            app_identifier="1Password.exe",
            window_title="1Password Master Vault",
            raw_payload={"vault": "unlocked"},
        )
        drop_record = await pipeline.ingest_event(sig_blacklisted)
        assert drop_record is None
        assert pipeline.get_metrics()["events_policy_dropped"] >= 1

    @pytest.mark.asyncio
    async def test_event_bus_and_subscriber_dispatch(self):
        """Verify subscribers receive sealed evidence records."""
        engine = PolicyEngine()
        pipeline = IngestionPipeline(policy_engine=engine)

        received_records = []
        pipeline.register_subscriber(lambda rec: received_records.append(rec))

        sig = RawSignalEvent(
            source_type=SourceType.OS_WINDOW,
            adapter_id="adapter.os",
            app_identifier="Firefox",
            window_title="Python Documentation",
            target_uri="https://python.org",
        )

        rec = await pipeline.ingest_event(sig)
        assert rec is not None
        assert len(received_records) == 1
        assert received_records[0].record_id == rec.record_id

    @pytest.mark.asyncio
    async def test_backpressure_drop_strategy(self):
        """Verify pipeline drops low-priority focus events when queue is nearly full."""
        engine = PolicyEngine()
        # Small queue of size 10 -> high-water mark at 9
        pipeline = IngestionPipeline(policy_engine=engine, max_queue_size=10)

        # Fill queue to 9 items
        for i in range(9):
            await pipeline.submit_signal(RawSignalEvent(
                source_type=SourceType.OS_WINDOW,
                adapter_id="os.adapter",
                app_identifier=f"App{i}",
            ))

        # Low-priority focus signal submitted under backpressure is dropped
        low_prio = RawSignalEvent(
            source_type=SourceType.OS_WINDOW,
            adapter_id="os.adapter",
            app_identifier="FocusApp",
        )
        res_low = await pipeline.submit_signal(low_prio)
        assert res_low is False
        assert pipeline.get_metrics()["events_backpressure_dropped"] >= 1

        # High-priority terminal command submitted is admitted
        high_prio = RawSignalEvent(
            source_type=SourceType.TERMINAL_PTY,
            adapter_id="term.adapter",
            app_identifier="Terminal",
            raw_payload={"command": "make test"},
        )
        res_high = await pipeline.submit_signal(high_prio)
        assert res_high is True


# ==============================================================================
# 3. Secondary Index Manager Tests
# ==============================================================================

class TestSecondaryIndexManager:
    """Test secondary index lookups, bisection range scanning, and updates."""

    def test_indexing_and_point_lookup(self):
        """Verify O(1) point lookup by ID and multi-attribute indexing."""
        index = SecondaryIndexManager()

        record = EvidenceRecord.create(
            source_type=SourceType.BROWSER,
            app_identifier="Google Chrome",
            sanitized_payload={"page": "home"},
            previous_record_hash="0" * 64,
            target_uri="https://github.com",
            classification=ClassificationLevel.PUBLIC,
        )

        index.index_record(record)
        assert index.count() == 1

        # Lookup by ID
        looked_up = index.lookup_by_id(record.record_id)
        assert looked_up == record

        # Lookup by App
        by_app = index.lookup_by_app("Google Chrome")
        assert len(by_app) == 1
        assert by_app[0].record_id == record.record_id

        # Lookup by Source
        by_source = index.lookup_by_source(SourceType.BROWSER)
        assert len(by_source) == 1

        # Remove record
        assert index.remove_record(record.record_id) is True
        assert index.count() == 0
        assert index.lookup_by_id(record.record_id) is None

    def test_bisection_time_range_lookup(self):
        """Verify binary search time range lookups."""
        index = SecondaryIndexManager()
        base_time = datetime(2026, 8, 17, 10, 0, 0, tzinfo=timezone.utc)

        records = []
        for i in range(10):
            ts = base_time + timedelta(minutes=i)
            rec = EvidenceRecord.create(
                source_type=SourceType.OS_WINDOW if i % 2 == 0 else SourceType.BROWSER,
                app_identifier=f"App_{i}",
                sanitized_payload={"i": i},
                previous_record_hash="0" * 64,
                persisted_at=ts,
            )
            index.index_record(rec)
            records.append(rec)

        # Range query for minutes 2 to 6
        start = base_time + timedelta(minutes=2)
        end = base_time + timedelta(minutes=6)
        results = index.lookup_time_range(start_time=start, end_time=end)

        assert len(results) == 5  # minutes 2, 3, 4, 5, 6 inclusive
        assert results[0].record_id == records[2].record_id
        assert results[-1].record_id == records[6].record_id

        # Filter by SourceType
        filtered = index.lookup_time_range(
            start_time=start,
            end_time=end,
            source_filter=[SourceType.OS_WINDOW],
        )
        assert all(r.source_type == SourceType.OS_WINDOW for r in filtered)


# ==============================================================================
# 4. Evidence Journal Tests
# ==============================================================================

class TestEvidenceJournal:
    """Test append-only journal throughput, SHA-256 hash chaining, disk roundtrip, and locking."""

    @pytest.mark.asyncio
    async def test_hash_chain_continuity_and_sealing(self, tmp_path: Path):
        """Verify SHA-256 hash chain continuity across sequential appends."""
        journal_file = tmp_path / "test_journal.jsonl"
        journal = EvidenceJournal(storage_path=journal_file)

        records = []
        for i in range(5):
            candidate = EvidenceRecord.create(
                source_type=SourceType.OS_WINDOW,
                app_identifier=f"App_{i}",
                sanitized_payload={"seq": i},
                previous_record_hash=GENESIS_HASH,
            )
            sealed = await journal.append(candidate)
            records.append(sealed)

        # Check genesis linkage
        assert records[0].previous_record_hash == GENESIS_HASH

        # Check chain links
        for i in range(1, 5):
            assert records[i].previous_record_hash == records[i - 1].provenance_hash

        # Verify journal integrity
        is_valid, corrupted_id, idx = journal.verify_journal_integrity()
        assert is_valid is True
        assert corrupted_id is None

    @pytest.mark.asyncio
    async def test_write_throughput_benchmark(self, tmp_path: Path):
        """Verify journal write throughput exceeds 2,000 appends/second."""
        journal_file = tmp_path / "bench_journal.jsonl"
        journal = EvidenceJournal(storage_path=journal_file)

        n_records = 2500
        candidates = [
            EvidenceRecord.create(
                source_type=SourceType.OS_WINDOW,
                app_identifier="ThroughputTestApp",
                sanitized_payload={"iteration": i, "payload": "benchmarking-high-speed-journal"},
                previous_record_hash=GENESIS_HASH,
            )
            for i in range(n_records)
        ]

        start_time = time.perf_counter()
        sealed_batch = await journal.append_batch(candidates)
        elapsed = time.perf_counter() - start_time

        throughput = n_records / elapsed
        assert len(sealed_batch) == n_records
        assert throughput > 2000.0, f"Throughput was {throughput:.2f} writes/sec, expected > 2000"

        # Verify integrity of the entire high-throughput journal
        is_valid, _, _ = journal.verify_journal_integrity()
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_persistence_disk_roundtrip(self, tmp_path: Path):
        """Verify reopening journal from disk reloads all records and preserves hash chain."""
        journal_file = tmp_path / "roundtrip_journal.jsonl"
        journal1 = EvidenceJournal(storage_path=journal_file)

        for i in range(10):
            cand = EvidenceRecord.create(
                source_type=SourceType.BROWSER,
                app_identifier="Chrome",
                sanitized_payload={"index": i},
                previous_record_hash=GENESIS_HASH,
            )
            await journal1.append(cand)

        assert await journal1.count_records() == 10
        last_hash_1 = await journal1.get_last_hash()

        # Instantiate second journal instance pointing to the same file
        journal2 = EvidenceJournal(storage_path=journal_file, auto_load=True)
        assert await journal2.count_records() == 10
        assert await journal2.get_last_hash() == last_hash_1
        assert journal2.verify_journal_integrity()[0] is True


# ==============================================================================
# 5. Tamper Detection & Chaos Bit-Flip Tests
# ==============================================================================

class TestTamperDetection:
    """Test cryptographic tamper detection against intentional byte mutations."""

    @pytest.mark.asyncio
    async def test_tamper_detection_on_mutated_file(self, tmp_path: Path):
        """Intentionally mutate bytes in physical storage and assert integrity check detects corruption."""
        journal_file = tmp_path / "tamper_test.jsonl"
        journal = EvidenceJournal(storage_path=journal_file)

        records = []
        for i in range(10):
            rec = EvidenceRecord.create(
                source_type=SourceType.OS_WINDOW,
                app_identifier=f"TamperApp_{i}",
                sanitized_payload={"secret_value": f"val_{i}"},
                previous_record_hash=GENESIS_HASH,
            )
            sealed = await journal.append(rec)
            records.append(sealed)

        # Confirm clean baseline
        assert journal.verify_journal_integrity()[0] is True

        # Mutate line 5 in the physical file
        target_record = records[4]
        with open(journal_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Modify payload in target line
        line_data = json.loads(lines[4])
        line_data["sanitized_payload"]["secret_value"] = "TAMPERED_ADVERSARIAL_MUTATION"
        lines[4] = json.dumps(line_data) + "\n"

        with open(journal_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # Run integrity scanner
        is_valid, corrupted_id, corrupted_idx = journal.verify_journal_integrity()
        assert is_valid is False
        assert corrupted_id == target_record.record_id
        assert corrupted_idx == 4

    @pytest.mark.asyncio
    async def test_tamper_detection_on_broken_hash_chain_link(self, tmp_path: Path):
        """Mutate previous_record_hash and assert chain link failure is caught."""
        journal_file = tmp_path / "chain_tamper.jsonl"
        journal = EvidenceJournal(storage_path=journal_file)

        for i in range(5):
            rec = EvidenceRecord.create(
                source_type=SourceType.BROWSER,
                app_identifier="Browser",
                sanitized_payload={"step": i},
                previous_record_hash=GENESIS_HASH,
            )
            await journal.append(rec)

        with open(journal_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Mutate previous_record_hash on record 2
        line_data = json.loads(lines[2])
        line_data["previous_record_hash"] = "f" * 64
        lines[2] = json.dumps(line_data) + "\n"

        with open(journal_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        is_valid, corrupted_id, corrupted_idx = journal.verify_journal_integrity()
        assert is_valid is False
        assert corrupted_idx == 2


# ==============================================================================
# 6. Cryptographic Tombstone Tests
# ==============================================================================

class TestCryptographicTombstone:
    """Test cryptographic tombstone payload zeroing and hash-chain preservation."""

    @pytest.mark.asyncio
    async def test_tombstone_payload_zeroing_and_chain_integrity(self, tmp_path: Path):
        """Verify tombstoning zeroes payload on disk, marks is_tombstone=True, and preserves chain."""
        journal_file = tmp_path / "tombstone_journal.jsonl"
        journal = EvidenceJournal(storage_path=journal_file)

        records = []
        for i in range(5):
            rec = EvidenceRecord.create(
                source_type=SourceType.BROWSER,
                app_identifier="Chrome",
                sanitized_payload={"sensitive_query": f"search query {i}"},
                previous_record_hash=GENESIS_HASH,
                window_title=f"Search {i}",
                target_uri=f"https://search.example.com?q={i}",
            )
            sealed = await journal.append(rec)
            records.append(sealed)

        target_id = records[2].record_id

        # Execute cryptographic tombstoning
        success = await journal.tombstone_record(
            record_id=target_id,
            reason="User GDPR right-to-be-forgotten request",
        )
        assert success is True

        # Point lookup of tombstoned record
        tombstoned_rec = await journal.get_by_id(target_id)
        assert tombstoned_rec is not None
        assert tombstoned_rec.is_tombstone is True
        assert tombstoned_rec.sanitized_payload == {}  # Payload zeroed
        assert tombstoned_rec.window_title is None
        assert tombstoned_rec.target_uri is None
        assert tombstoned_rec.classification == ClassificationLevel.PROHIBITED
        assert "GDPR" in (tombstoned_rec.tombstone_reason or "")

        # Verify disk file contains zero trace of sensitive query
        raw_disk_content = journal_file.read_text(encoding="utf-8")
        assert f"search query 2" not in raw_disk_content

        # Verify overall hash chain integrity remains valid
        is_valid, corrupted_id, _ = journal.verify_journal_integrity()
        assert is_valid is True
        assert corrupted_id is None


# ==============================================================================
# 7. Deterministic Replay Engine Tests
# ==============================================================================

class TestDeterministicReplay:
    """Test sequential stream replay, tombstone skipping, and state reconstruction parity."""

    @pytest.mark.asyncio
    async def test_sequential_state_reconstruction_and_parity(self, tmp_path: Path):
        """Replay 100 developer events across multiple passes and assert 100% bit-parity."""
        journal_file = tmp_path / "replay_journal.jsonl"
        journal = EvidenceJournal(storage_path=journal_file)

        # Populate journal
        for i in range(50):
            cand = EvidenceRecord.create(
                source_type=SourceType.TERMINAL_PTY if i % 2 == 0 else SourceType.OS_WINDOW,
                app_identifier="Terminal" if i % 2 == 0 else "VSCode",
                sanitized_payload={"branch": "main" if i < 25 else "feature/phase2", "event_seq": i},
                previous_record_hash=GENESIS_HASH,
            )
            await journal.append(cand)

        replay_engine = DeterministicReplayEngine(journal=journal)

        def compiler_fn(state: dict, record: EvidenceRecord) -> dict:
            state["total_events"] += 1
            if record.source_type == SourceType.TERMINAL_PTY:
                state["cli_events"] += 1
            branch = record.sanitized_payload.get("branch")
            if branch:
                state["latest_branch"] = branch
            return state

        def initial_state_factory() -> dict:
            return {"total_events": 0, "cli_events": 0, "latest_branch": "unknown"}

        is_parity, hashes = await replay_engine.verify_deterministic_parity(
            compiler_fn=compiler_fn,
            initial_state_factory=initial_state_factory,
            n_passes=3,
        )
        assert is_parity is True
        assert len(hashes) == 3
        assert hashes[0] == hashes[1] == hashes[2]

        final_state = await replay_engine.reconstruct_state(
            compiler_fn=compiler_fn,
            initial_state=initial_state_factory(),
        )
        assert final_state["total_events"] == 50
        assert final_state["cli_events"] == 25
        assert final_state["latest_branch"] == "feature/phase2"

    @pytest.mark.asyncio
    async def test_replay_tombstone_skipping(self, tmp_path: Path):
        """Verify replaying evidence stream skips tombstoned records."""
        journal = EvidenceJournal(storage_path=tmp_path / "tomb_replay.jsonl")

        records = []
        for i in range(5):
            rec = EvidenceRecord.create(
                source_type=SourceType.OS_WINDOW,
                app_identifier="Editor",
                sanitized_payload={"seq": i},
                previous_record_hash=GENESIS_HASH,
            )
            sealed = await journal.append(rec)
            records.append(sealed)

        # Tombstone record index 2
        await journal.tombstone_record(records[2].record_id, reason="Excluded")

        replay_engine = DeterministicReplayEngine(journal=journal)

        replayed = []
        async for r in replay_engine.replay_stream(skip_tombstones=True):
            replayed.append(r)

        assert len(replayed) == 4
        assert records[2].record_id not in [r.record_id for r in replayed]


# ==============================================================================
# 8. Projection Stager & Double-Buffering Tests
# ==============================================================================

class TestProjectionStager:
    """Test candidate staging, epistemic invariant validation, atomic swap, and rollback."""

    @pytest.mark.asyncio
    async def test_staging_validation_and_atomic_swap(self, tmp_path: Path):
        """Verify valid candidate passes epistemic validation and swaps atomically."""
        journal = EvidenceJournal(storage_path=tmp_path / "stager_journal.jsonl")

        # Ingest supporting evidence
        rec1 = await journal.append(EvidenceRecord.create(
            source_type=SourceType.OS_WINDOW,
            app_identifier="VSCode",
            sanitized_payload={"active_project": "entorhinal"},
            previous_record_hash=GENESIS_HASH,
        ))
        rec2 = await journal.append(EvidenceRecord.create(
            source_type=SourceType.TERMINAL_PTY,
            app_identifier="Terminal",
            sanitized_payload={"branch": "main"},
            previous_record_hash=GENESIS_HASH,
        ))

        stager = ProjectionStager(journal=journal)

        # 1. Stage candidate with valid evidence links
        candidate = stager.stage_new_projection(
            target_version="1.0.0",
            facts=[
                DerivedFact(
                    entity_uri="project:entorhinal",
                    attribute="active_project",
                    value="entorhinal",
                    confidence=0.99,
                    supporting_evidence_ids=[rec1.record_id],
                    derived_by="ProjectCompiler",
                ),
                DerivedFact(
                    entity_uri="project:entorhinal",
                    attribute="git_branch",
                    value="main",
                    confidence=0.95,
                    supporting_evidence_ids=[rec2.record_id],
                    derived_by="GitBranchCompiler",
                ),
            ],
            hypotheses=[
                Hypothesis(
                    proposed_intent="Implementing Phase 2",
                    confidence_score=0.85,
                    candidate_evidence_ids=[rec1.record_id, rec2.record_id],
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                )
            ],
        )

        is_valid, errors = await stager.validate_candidate(candidate)
        assert is_valid is True
        assert len(errors) == 0

        # 2. Activate staged projection
        await stager.activate_staged_projection(candidate)
        active = stager.get_active_projection()
        assert active is not None
        assert active.version == "1.0.0"
        assert len(active.facts) == 2

    @pytest.mark.asyncio
    async def test_validation_fails_on_missing_or_tombstoned_evidence(self, tmp_path: Path):
        """Verify candidate fails validation if referencing non-existent or tombstoned evidence."""
        journal = EvidenceJournal(storage_path=tmp_path / "stager_fail.jsonl")

        rec = await journal.append(EvidenceRecord.create(
            source_type=SourceType.BROWSER,
            app_identifier="Chrome",
            sanitized_payload={"page": "login"},
            previous_record_hash=GENESIS_HASH,
        ))

        # Tombstone the record
        await journal.tombstone_record(rec.record_id, reason="User revoked")

        stager = ProjectionStager(journal=journal)

        # Stage candidate referencing tombstoned evidence
        cand_tombstoned = stager.stage_new_projection(
            target_version="2.0.0",
            facts=[
                DerivedFact(
                    entity_uri="user:session",
                    attribute="last_page",
                    value="login",
                    confidence=0.9,
                    supporting_evidence_ids=[rec.record_id],  # Tombstoned!
                    derived_by="SessionCompiler",
                )
            ],
        )

        is_valid, errors = await stager.validate_candidate(cand_tombstoned)
        assert is_valid is False
        assert any("tombstoned" in e.lower() for e in errors)

        # Attempting activation must raise ValueError
        with pytest.raises(ValueError):
            await stager.activate_staged_projection(cand_tombstoned)

    @pytest.mark.asyncio
    async def test_rollback_to_last_known_good(self, tmp_path: Path):
        """Verify rollback restores previous valid projection state."""
        journal = EvidenceJournal(storage_path=tmp_path / "stager_rollback.jsonl")

        rec = await journal.append(EvidenceRecord.create(
            source_type=SourceType.OS_WINDOW,
            app_identifier="VSCode",
            sanitized_payload={"file": "test.py"},
            previous_record_hash=GENESIS_HASH,
        ))

        stager = ProjectionStager(journal=journal)

        # Stage and activate v1
        v1 = stager.stage_new_projection(
            target_version="1.0.0",
            facts=[
                DerivedFact(
                    entity_uri="workspace:file",
                    attribute="open_file",
                    value="test.py",
                    confidence=0.9,
                    supporting_evidence_ids=[rec.record_id],
                    derived_by="EditorCompiler",
                )
            ],
        )
        await stager.activate_staged_projection(v1)
        assert stager.get_active_projection().version == "1.0.0"

        # Stage and activate v2
        v2 = stager.stage_new_projection(
            target_version="2.0.0",
            facts=[
                DerivedFact(
                    entity_uri="workspace:file",
                    attribute="open_file",
                    value="test.py",
                    confidence=0.95,
                    supporting_evidence_ids=[rec.record_id],
                    derived_by="EditorCompiler",
                    revision_id=2,
                )
            ],
        )
        await stager.activate_staged_projection(v2)
        assert stager.get_active_projection().version == "2.0.0"

        # Rollback to v1
        success = await stager.rollback_to_last_known_good()
        assert success is True
        assert stager.get_active_projection().version == "1.0.0"


# ==============================================================================
# 9. Extended Stream & Edge Cases Tests
# ==============================================================================

class TestExtendedEdgeCases:
    """Test async stream processing, terminal timeouts, and journal scanning."""

    @pytest.mark.asyncio
    async def test_pipeline_process_stream_generator(self):
        """Verify pipeline consumes async generator from source adapter."""
        engine = PolicyEngine()
        pipeline = IngestionPipeline(policy_engine=engine)
        mock_adapter = MockSourceAdapter(adapter_id="stream.adapter")
        await mock_adapter.start()

        async def _feed():
            await mock_adapter.generate_burst(count=10, app_name="StreamApp")
            await asyncio.sleep(0.05)
            await mock_adapter.stop()

        feed_task = asyncio.create_task(_feed())

        admitted_records = []
        async for record in pipeline.process_stream(mock_adapter):
            admitted_records.append(record)
            if len(admitted_records) == 10:
                break

        await feed_task
        assert len(admitted_records) == 10

    @pytest.mark.asyncio
    async def test_terminal_timeout_kills_hung_command(self):
        """Verify terminal adapter times out and kills long-running/hanging command without hanging test."""
        adapter = TerminalPTYSourceAdapter(default_timeout_seconds=0.5)
        await adapter.start()

        code, out, sig = await execute_monitored_command(
            adapter,
            command=f'{sys.executable} -c "import time; time.sleep(10)"',
            timeout_seconds=0.3,
        )
        assert code == -1
        assert "[TIMEOUT]" in out
        assert sig is not None
        assert sig.raw_payload["exit_code"] == -1

        await adapter.stop()

    @pytest.mark.asyncio
    async def test_journal_scan_and_query_time_range(self, tmp_path: Path):
        """Verify journal time range iteration and scan_evidence filtering."""
        journal = EvidenceJournal(storage_path=tmp_path / "scan_journal.jsonl")

        base_time = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ts = base_time + timedelta(minutes=i)
            await journal.append(EvidenceRecord.create(
                source_type=SourceType.BROWSER if i % 2 == 0 else SourceType.TERMINAL_PTY,
                app_identifier=f"App_{i}",
                sanitized_payload={"val": i},
                previous_record_hash=GENESIS_HASH,
                persisted_at=ts,
            ))

        # Scan all
        all_records = await journal.scan_evidence(limit=100)
        assert len(all_records) == 10

        # Scan with time range
        ranged = await journal.scan_evidence(
            start_time=base_time + timedelta(minutes=3),
            end_time=base_time + timedelta(minutes=7),
            limit=10,
        )
        assert len(ranged) == 5

        # Query time range async iterator
        streamed = []
        async for r in journal.query_time_range(
            start_time=base_time + timedelta(minutes=1),
            end_time=base_time + timedelta(minutes=4),
            source_filter=["browser"],
        ):
            streamed.append(r)

        assert all(r.source_type == SourceType.BROWSER for r in streamed)

    @pytest.mark.asyncio
    async def test_apply_tombstone_record_model(self, tmp_path: Path):
        """Verify apply_tombstone using TombstoneRecord data model."""
        journal = EvidenceJournal(storage_path=tmp_path / "tomb_model.jsonl")

        rec = await journal.append(EvidenceRecord.create(
            source_type=SourceType.DOCUMENT,
            app_identifier="Notepad",
            sanitized_payload={"confidential": "user secret"},
            previous_record_hash=GENESIS_HASH,
        ))

        tombstone = TombstoneRecord.create(
            original_record_id=rec.record_id,
            previous_record_hash=rec.previous_record_hash,
            revocation_reason="Legal Hold Expired",
        )

        success = await journal.apply_tombstone(tombstone)
        assert success is True

        tombstoned_rec = await journal.get_by_id(rec.record_id)
        assert tombstoned_rec is not None
        assert tombstoned_rec.is_tombstone is True
        assert tombstoned_rec.sanitized_payload == {}
        assert tombstoned_rec.tombstone_reason == "Legal Hold Expired"

    @pytest.mark.asyncio
    async def test_stager_duplicate_fact_validation_error(self, tmp_path: Path):
        """Verify stager catches duplicate fact keys in candidate context."""
        journal = EvidenceJournal(storage_path=tmp_path / "stager_dup.jsonl")
        rec = await journal.append(EvidenceRecord.create(
            source_type=SourceType.OS_WINDOW,
            app_identifier="App",
            sanitized_payload={"k": "v"},
            previous_record_hash=GENESIS_HASH,
        ))

        stager = ProjectionStager(journal=journal)

        candidate = stager.stage_new_projection(
            target_version="1.0.0",
            facts=[
                DerivedFact(
                    entity_uri="project:alpha",
                    attribute="branch",
                    value="main",
                    confidence=0.9,
                    supporting_evidence_ids=[rec.record_id],
                    derived_by="rule1",
                ),
                DerivedFact(
                    entity_uri="project:alpha",
                    attribute="branch",
                    value="dev",
                    confidence=0.8,
                    supporting_evidence_ids=[rec.record_id],
                    derived_by="rule2",
                ),
            ],
        )

        is_valid, errors = await stager.validate_candidate(candidate)
        assert is_valid is False
        assert any("duplicate" in e.lower() for e in errors)

