"""Main-owned control-repair regressions: F3/F13 CLI, F5/F12 pump, F6.3, F11, G23, N1/N4.

Covers:
1. F3: status/inspect/correct/grants/audit operate on the durable runtime
   store the daemon serves (a CLI one-shot sees daemon-committed rows).
2. F13: status/correct/grants render measured values, not literal claims.
3. F6.3: forget invalidates the runtime temporal projection; rebuilds adopt
   the persisted deletion generation.
4. F11: stop records are durable; a running daemon applies external
   stop/start via pump sync; sources CLI round-trips.
5. F5/F12: periodic in-runtime reconcile recovers spooled events;
   admission-lag fields are surfaced; retention ceiling pauses admission.
6. G23: retention measurement + explicit enforcement.
7. N1/N4: compiler purge and adapter purge_managed call sites.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Any, Dict, List

import pytest
from typer.testing import CliRunner

from entorhinal.cli.main import app as cli_app
from entorhinal.evidence.sqlite_store import SQLiteEvidenceStore
from entorhinal.runtime.config import RuntimeConfig, SourceSpec
from entorhinal.runtime.factory import build_runtime
from entorhinal.runtime.sources import (
    SourceLifecycle,
    STOPPED_RECORDS_FILENAME,
    register_adapter,
)
from entorhinal.schemas.models import EvidenceRecord, RawSignalEvent, SourceType
from entorhinal.user_control.deletion import CascadeDeletionEngine
from entorhinal.user_control.service import UserControlService


def _make_record(title: str = "Repair Title") -> EvidenceRecord:
    return EvidenceRecord.create(
        source_type=SourceType.BROWSER,
        app_identifier="Chrome",
        window_title=title,
        target_uri="https://example.test/repair",
        sanitized_payload={"note": "repair-secret"},
        previous_record_hash="0" * 64,
    )


def _make_signal() -> RawSignalEvent:
    return RawSignalEvent(
        source_type=SourceType.BROWSER,
        adapter_id="fake",
        app_identifier="Chrome",
        window_title="Repair Signal",
        target_uri="https://example.test/repair",
        raw_payload={"event_type": "focus"},
    )


class _ScriptedAdapter:
    """Minimal fake adapter with optional health/lag reporting."""

    def __init__(
        self,
        signals: List[Any] | None = None,
        lag: Dict[str, Any] | None = None,
    ) -> None:
        self._signals = list(signals or [])
        self._lag = lag or {}
        self.poll_calls = 0
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def is_healthy(self) -> bool:
        return self.started and not self.stopped

    async def poll_signals(self) -> List[Any]:
        self.poll_calls += 1
        pending, self._signals = self._signals, []
        return pending

    def health_check(self) -> Dict[str, Any]:
        return dict(self._lag)


class _SpooledEvent:
    """Fake spool entry exposing the tailer replay contract."""

    def __init__(self, signal: RawSignalEvent) -> None:
        self._signal = signal

    def to_raw_signal_event(self) -> RawSignalEvent:
        return self._signal


# --------------------------------------------------------------------------
# F3/F13: CLI on the durable runtime
# --------------------------------------------------------------------------

def test_cli_inspect_timeline_sees_daemon_committed_rows() -> None:
    """F3 core: a CLI one-shot reads the SQLite store the daemon serves."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            import asyncio

            async def _commit() -> None:
                await runtime.store.append_evidence(_make_record("F3-Canary-Title"))

            asyncio.run(_commit())
        finally:
            runtime.close()

        result = runner.invoke(cli_app, ["inspect", "timeline", "--dir", tmp_dir])
        assert result.exit_code == 0, result.output
        assert "F3-Canary-Title" not in result.output  # titles are truncated cols; app id shown
        assert "Chrome" in result.output
        assert "No evidence records found" not in result.output


def test_cli_status_reports_measured_values() -> None:
    """F13: status derives its verdict from measured store signals."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            import asyncio

            asyncio.run(runtime.store.append_evidence(_make_record()))
        finally:
            runtime.close()

        result = runner.invoke(cli_app, ["status", "--dir", tmp_dir])
        assert result.exit_code == 0, result.output
        assert "HEALTHY" in result.output
        assert "measured:" in result.output
        assert "Total Evidence Records" in result.output
        assert "100%" not in result.output
        assert "Standalone Autonomous" not in result.output


def test_cli_correct_grants_audit_round_trip_on_runtime() -> None:
    """F3: corrections/grants/audit persist across CLI invocations on one root."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_correct = runner.invoke(cli_app, [
            "correct", "project:cli-runtime", '{"name": "X"}', "--dir", tmp_dir,
        ])
        assert res_correct.exit_code == 0, res_correct.output
        assert "Correction Applied Successfully" in res_correct.output
        assert "<50ms" not in res_correct.output

        res_grant = runner.invoke(cli_app, [
            "grants", "grant", "--source", "browser", "--app", "Chrome",
            "--domain", "*.example.test*", "--dir", tmp_dir,
        ])
        assert res_grant.exit_code == 0, res_grant.output
        assert "Consent granted successfully" in res_grant.output

        res_list = runner.invoke(cli_app, ["grants", "list", "--dir", tmp_dir])
        assert res_list.exit_code == 0, res_list.output
        # Persisted grant visible (CliRunner's 80-col width wraps long cells,
        # so assert on the outcome columns plus the durable check below).
        assert "ALLOW" in res_list.output
        assert "browser" in res_list.output

        res_audit = runner.invoke(cli_app, ["audit", "--dir", tmp_dir])
        assert res_audit.exit_code == 0, res_audit.output
        assert "CONSENT_GRANTED" in res_audit.output

        # Corrections/grants survive a fresh runtime open (durable, not in-memory).
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir))
        try:
            assert len(runtime.user_control.list_corrections()) == 1
            rules = runtime.user_control.list_consent_rules()
            assert len(rules) == 1
            assert rules[0].app_pattern == "Chrome"
        finally:
            runtime.close()


def test_cli_inspect_graph_and_focus_exit_zero_on_populated_store() -> None:
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            import asyncio

            asyncio.run(runtime.store.append_evidence(_make_record()))
        finally:
            runtime.close()

        res_graph = runner.invoke(cli_app, ["inspect", "graph", "--dir", tmp_dir])
        assert res_graph.exit_code == 0, res_graph.output
        res_focus = runner.invoke(cli_app, ["inspect", "focus", "--dir", tmp_dir])
        assert res_focus.exit_code == 0, res_focus.output
        assert "Real-Time Immediate Focus" in res_focus.output


# --------------------------------------------------------------------------
# F6.3: projection invalidation on forget
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forget_invalidates_temporal_projection() -> None:
    """F6.3: forget bumps the generation and forces a projection rebuild."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            await runtime.store.append_evidence(_make_record())
            first = await runtime.projection.get()
            assert runtime.projection.build_count == 1
            assert runtime.projection.is_built is True

            now = datetime.now(timezone.utc)
            proof = await runtime.user_control.forget_time_range(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                reason="f6.3 test",
            )
            assert proof["tombstoned_records_count"] == 1
            assert proof["deletion_generation"] == 1
            assert runtime.projection.is_built is False
            assert "forget" in (runtime.projection.last_invalidated_reason or "")

            second = await runtime.projection.get()
            assert second is not first
            assert runtime.projection.build_count == 2
            assert second.deletion_generation == 1
            assert "post_forget_hook_error" not in proof
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_post_forget_hook_failure_is_recorded_not_silent() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            await store.append_evidence(_make_record())

            def _boom(_proof: Dict[str, Any]) -> None:
                raise RuntimeError("hook exploded")

            service = UserControlService(
                journal=store,  # type: ignore[arg-type]
                storage_dir=root,
                on_forget=_boom,
            )
            now = datetime.now(timezone.utc)
            proof = await service.forget_time_range(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                reason="hook failure test",
            )
            assert proof["tombstoned_records_count"] == 1
            assert "hook exploded" in proof["post_forget_hook_error"]
        finally:
            store.close()


# --------------------------------------------------------------------------
# F11: durable stop records + pump sync + sources CLI
# --------------------------------------------------------------------------

class _RegistryStubAdapter(_ScriptedAdapter):
    @property
    def adapter_id(self) -> str:
        return "f11-stub"


_F11_INSTANCES: List[_RegistryStubAdapter] = []


def _f11_factory(spec: SourceSpec) -> _RegistryStubAdapter:
    adapter = _RegistryStubAdapter()
    _F11_INSTANCES.append(adapter)
    return adapter


register_adapter("test-stub-f11", _f11_factory)


@pytest.mark.asyncio
async def test_stop_source_persists_across_lifecycle_restart() -> None:
    """F11: a stop survives daemon restarts; start() honors the record."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        stop_file = Path(tmp_dir) / STOPPED_RECORDS_FILENAME
        specs = [SourceSpec(name="s1", adapter="test-stub-f11")]
        first = SourceLifecycle(specs, storage_path=stop_file)
        assert stop_file.exists() is False
        result = await first.stop_source("s1", reason="operator halt")
        assert result["durable"] is True
        assert stop_file.exists()

        _F11_INSTANCES.clear()
        second = SourceLifecycle(specs, storage_path=stop_file)
        assert "s1" in second.stopped_sources()
        await second.start()  # must skip s1 without touching the registry
        assert "s1" not in second.adapters()
        assert _F11_INSTANCES == []
        await second.stop()


@pytest.mark.asyncio
async def test_pump_sync_applies_external_stop_and_start() -> None:
    """F11: one-shot CLI records take effect on a running daemon via sync."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        stop_file = Path(tmp_dir) / STOPPED_RECORDS_FILENAME
        specs = [SourceSpec(name="s1", adapter="test-stub-f11")]
        _F11_INSTANCES.clear()
        daemon = SourceLifecycle(specs, storage_path=stop_file)
        await daemon.start()
        assert "s1" in daemon.adapters()
        live = daemon.adapters()["s1"]
        assert isinstance(live, _RegistryStubAdapter)

        cli_view = SourceLifecycle([], storage_path=stop_file)
        cli_view.record_stop("s1", reason="cli stop")
        outcome = await daemon.sync_stopped_with_adapters()
        assert outcome["stopped"] == ["s1"]
        assert live.stopped is True
        assert "s1" not in daemon.adapters()

        cli_view.clear_stop_record("s1")
        outcome = await daemon.sync_stopped_with_adapters()
        assert outcome["started"] == ["s1"]
        assert "s1" in daemon.adapters()
        await daemon.stop()


@pytest.mark.asyncio
async def test_corrupt_stop_file_is_disclosed_not_fatal() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        stop_file = Path(tmp_dir) / STOPPED_RECORDS_FILENAME
        stop_file.write_text("{not json", encoding="utf-8")
        lifecycle = SourceLifecycle(
            [SourceSpec(name="s1", adapter="test-stub-f11")],
            storage_path=stop_file,
        )
        assert lifecycle.stopped_sources() == {}
        health = lifecycle.health()
        assert "corrupt" in health["stopped_records_error"]


def test_sources_cli_stop_start_list_round_trip() -> None:
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_stop = runner.invoke(cli_app, [
            "sources", "stop", "dev-task", "--reason", "cli test", "--dir", tmp_dir,
        ])
        assert res_stop.exit_code == 0, res_stop.output
        assert "stop recorded" in res_stop.output
        assert (Path(tmp_dir) / STOPPED_RECORDS_FILENAME).exists()

        res_list = runner.invoke(cli_app, ["sources", "list", "--dir", tmp_dir])
        assert res_list.exit_code == 0, res_list.output
        assert "dev-task" in res_list.output
        assert "stopped" in res_list.output

        res_start = runner.invoke(cli_app, ["sources", "start", "dev-task", "--dir", tmp_dir])
        assert res_start.exit_code == 0, res_start.output
        assert "stop cleared" in res_start.output

        res_list2 = runner.invoke(cli_app, ["sources", "list", "--dir", tmp_dir])
        assert res_list2.exit_code == 0, res_list2.output
        assert "dev-task" not in res_list2.output


# --------------------------------------------------------------------------
# F5/F12: periodic reconcile, lag surfacing, retention pause
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_periodic_reconcile_commits_spooled_events() -> None:
    """F5/F12: spooled-but-uncommitted events recover in-runtime, no restart."""

    class _SpoolAdapter(_ScriptedAdapter):
        def __init__(self, spooled: List[_SpooledEvent]) -> None:
            super().__init__(signals=[])
            self._spooled = spooled

        def spool_replay(self, limit: Any = None) -> List[_SpooledEvent]:
            return list(self._spooled)

    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            adapter = _SpoolAdapter([_SpooledEvent(_make_signal())])
            runtime.sources._adapters["fake"] = adapter
            outcome = await runtime._reconcile_spools()
            assert outcome["replayed"] == 1
            assert outcome["committed"] == 1
            assert outcome["errors"] == 0
            assert await runtime.store.count_records() == 1
            # Idempotent: a second replay returns the original receipt.
            outcome2 = await runtime._reconcile_spools()
            assert outcome2["replayed"] == 1
            assert await runtime.store.count_records() == 1
            assert runtime.health()["pump"]["counters"]["reconcile_runs"] >= 2
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_pump_loop_runs_periodic_reconcile() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            runtime.reconcile_interval_s = 0.0  # reconcile every loop tick
            await runtime.start_sources()
            import asyncio

            await asyncio.sleep(0.35)
            await runtime.stop_sources()
            counters = runtime.health()["pump"]["counters"]
            assert counters.get("reconcile_runs", 0) >= 2  # startup + periodic
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_retention_ceiling_pauses_admission_visibly() -> None:
    """G23 pump side: at the ceiling the pump pauses and says so."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            adapter = _ScriptedAdapter(signals=[_make_signal()])
            runtime.sources._adapters["fake"] = adapter
            runtime.retention_max_bytes = 1  # every real db exceeds this
            await runtime._pump_once()
            assert adapter.poll_calls == 0
            assert runtime.pump_stats().get("fake", {}).get("polled", 0) == 0
            retention = runtime.health()["pump"]["retention"]
            assert retention["paused"] is True
            assert retention["db_bytes"] is not None and retention["db_bytes"] >= 1

            runtime.retention_max_bytes = 1 << 40
            await runtime._pump_once()
            assert adapter.poll_calls == 1
            assert runtime.health()["pump"]["retention"]["paused"] is False
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_admission_lag_surfaces_tailer_fields() -> None:
    """F12 pump side: documented tailer lag fields appear in pump health."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            runtime.sources._adapters["fake"] = _ScriptedAdapter(lag={
                "spool_pending_count": 3,
                "queue_backlog_count": 1,
                "gap_count": 2,
                "backpressure": True,
            })
            lag = runtime.health()["pump"]["admission_lag"]
            assert lag["fake"]["spool_pending_count"] == 3
            assert lag["fake"]["gap_count"] == 2
            assert lag["fake"]["backpressure"] is True
        finally:
            runtime.close()


# --------------------------------------------------------------------------
# G23: retention measurement + enforcement
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retention_status_measures_age_and_size() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            await store.append_evidence(_make_record())
            fresh = store.retention_status(max_age_days=30, max_db_bytes=1 << 30)
            assert fresh["evidence_count"] == 1
            assert fresh["expired_count"] == 0
            assert fresh["over_age_ceiling"] is False
            assert fresh["over_size_ceiling"] is False
            assert fresh["oldest_committed_at"] is not None

            tiny = store.retention_status(max_age_days=30, max_db_bytes=1)
            assert tiny["over_size_ceiling"] is True
        finally:
            store.close()


@pytest.mark.asyncio
async def test_enforce_retention_tombstones_only_expired() -> None:
    """G23: enforcement tombstones the measured expired set via the engine."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            record_id = await runtime.store.append_evidence(_make_record())
            assert runtime.store.retention_status(max_age_days=0)["expired_count"] == 1
            proof = await runtime.user_control.enforce_retention(max_age_days=0)
            assert proof["retention_enforced"] is True
            assert proof["tombstoned_records_count"] == 1
            assert proof["deletion_generation"] == 1
            assert proof["residual_leakage_count"] == 0
            rec = await runtime.store.get_by_id(record_id)
            assert rec is not None and rec.is_tombstone is True

            # Second pass: candidate still measured, nothing left to tombstone.
            proof2 = await runtime.user_control.enforce_retention(max_age_days=0)
            assert proof2["tombstoned_records_count"] == 0
        finally:
            runtime.close()


def test_cli_retention_reports_and_enforces() -> None:
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            import asyncio

            asyncio.run(runtime.store.append_evidence(_make_record()))
        finally:
            runtime.close()

        res_show = runner.invoke(cli_app, ["retention", "--dir", tmp_dir])
        assert res_show.exit_code == 0, res_show.output
        assert "Retention Status" in res_show.output
        assert "Expired Rows" in res_show.output

        res_enforce = runner.invoke(
            cli_app, ["retention", "--max-age-days", "0", "--enforce", "--dir", tmp_dir]
        )
        assert res_enforce.exit_code == 0, res_enforce.output
        assert "Retention Enforcement Proof" in res_enforce.output


# --------------------------------------------------------------------------
# N1/N4: sibling purge call sites
# --------------------------------------------------------------------------

class _PurgeCompiler:
    """Fake compiler exposing the agreed N1 purge_evidence entry point."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.purge_calls: List[Dict[str, Any]] = []

    async def compile_batch_projection(self) -> List[Any]:
        return []

    def get_active_facts(self) -> List[Any]:
        return []

    async def purge_evidence(
        self, record_ids: List[str], *, reason: str = ""
    ) -> Dict[str, int]:
        self.purge_calls.append({"record_ids": record_ids, "reason": reason})
        if self.fail:
            raise RuntimeError("purge exploded")
        return {"focus_cleared": 1, "aggregates_rebuilt": 1}


@pytest.mark.asyncio
async def test_compiler_purge_called_with_measured_counts() -> None:
    """N1: the engine calls compiler.purge_evidence and records its counts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            await store.append_evidence(_make_record())
            compiler = _PurgeCompiler()
            engine = CascadeDeletionEngine(journal=store, compiler=compiler)  # type: ignore[arg-type]
            now = datetime.now(timezone.utc)
            proof = await engine.forget_time_range(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                reason="n1 test",
            )
            assert proof["tombstoned_records_count"] == 1
            assert proof["focus_aggregates_purged"] is True
            assert proof["focus_purge_counts"] == {
                "focus_cleared": 1, "aggregates_rebuilt": 1,
            }
            assert proof["focus_purge_error"] is None
            assert len(compiler.purge_calls) == 1
            assert compiler.purge_calls[0]["record_ids"] == proof["tombstoned_record_ids"]
        finally:
            store.close()


@pytest.mark.asyncio
async def test_compiler_purge_failure_is_disclosed() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            await store.append_evidence(_make_record())
            engine = CascadeDeletionEngine(
                journal=store, compiler=_PurgeCompiler(fail=True)  # type: ignore[arg-type]
            )
            now = datetime.now(timezone.utc)
            proof = await engine.forget_time_range(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                reason="n1 failure test",
            )
            assert proof["tombstoned_records_count"] == 1
            assert proof["focus_aggregates_purged"] is False
            assert "purge exploded" in (proof["focus_purge_error"] or "")
        finally:
            store.close()


class _PurgeAdapter:
    """Fake adapter exposing the agreed N4 purge_managed hook."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: List[Dict[str, Any]] = []

    def managed_paths(self) -> Dict[str, str]:
        return {"spool": "/tmp/spool.jsonl", "inbox": "/tmp/inbox.jsonl"}

    def purge_managed(
        self,
        *,
        reason: str,
        event_ids: List[str] | None = None,
        match_all: bool = False,
    ) -> Dict[str, int]:
        self.calls.append({"reason": reason, "event_ids": event_ids, "match_all": match_all})
        if self.fail:
            raise RuntimeError("purge_managed exploded")
        return {"spool_removed": 4, "pending_removed": 1, "denied_removed": 0}


@pytest.mark.asyncio
async def test_adapter_purge_managed_called_and_merged() -> None:
    """N4: live adapters purge managed copies; results merge into the proof."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            record = _make_record()
            await store.append_evidence(record)
            adapter = _PurgeAdapter()
            service = UserControlService(
                journal=store,  # type: ignore[arg-type]
                storage_dir=root,
                adapter_accessor=lambda: {"dev-task": adapter},
            )
            now = datetime.now(timezone.utc)
            proof = await service.forget_time_range(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                reason="n4 test",
            )
            assert proof["tombstoned_records_count"] == 1
            # append_evidence keys event_id=record.record_id (store evidence_id differs).
            assert proof["tombstoned_event_ids"] == [record.record_id]
            assert proof["adapter_purge"]["dev-task"] == {
                "spool_removed": 4, "pending_removed": 1, "denied_removed": 0,
            }
            assert proof["adapter_managed_paths"]["dev-task"]["spool"] == "/tmp/spool.jsonl"
            assert len(adapter.calls) == 1
            assert adapter.calls[0]["reason"] == "n4 test"
            assert adapter.calls[0]["event_ids"] == [record.record_id]
            assert adapter.calls[0]["match_all"] is False
        finally:
            store.close()


@pytest.mark.asyncio
async def test_grant_consent_requeues_adapter_backlog() -> None:
    """F12: a new grant triggers adapter requeue; counts are audit-logged."""

    class _RequeueAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def requeue_pending(self) -> int:
            self.calls += 1
            return 3

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            adapter = _RequeueAdapter()
            service = UserControlService(
                journal=store,  # type: ignore[arg-type]
                storage_dir=root,
                adapter_accessor=lambda: {"dev-task": adapter},
            )
            rule_id = await service.grant_consent(
                source_type=SourceType.BROWSER,
                app_pattern="Chrome",
                domain_pattern="*",
            )
            assert rule_id
            assert adapter.calls == 1
            logs = await service.get_audit_log(limit=5)
            granted = [e for e in logs if e.get("action") == "CONSENT_GRANTED"]
            assert granted
            assert granted[0]["details"]["requeued_pending"] == {"dev-task": 3}
        finally:
            store.close()


@pytest.mark.asyncio
async def test_reconcile_compacts_adapter_spool() -> None:
    """F14: reconcile asks adapters to compact acknowledged spool entries."""

    class _CompactAdapter(_ScriptedAdapter):
        def __init__(self) -> None:
            super().__init__(signals=[])
            self.compact_calls = 0

        def spool_replay(self, limit: Any = None) -> List[Any]:
            return []

        def compact_spool(self) -> Dict[str, int]:
            self.compact_calls += 1
            return {"kept": 0, "removed": 2}

    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            adapter = _CompactAdapter()
            runtime.sources._adapters["fake"] = adapter
            await runtime._reconcile_spools()
            assert adapter.compact_calls == 1
            counters = runtime.health()["pump"]["counters"]
            assert counters.get("spool_compacted_removed") == 2
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_revoke_bumps_revocation_generation_adopted_on_rebuild() -> None:
    """F11/API-5: revoke persists a generation the holder adopts on rebuild."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            rule_id = await runtime.user_control.grant_consent(
                source_type=SourceType.BROWSER,
                app_pattern="Chrome",
                domain_pattern="*",
            )
            assert await runtime.user_control.revoke_consent(rule_id) is True
            assert runtime.store.get_meta("revocation_generation") == "1"
            projection = await runtime.projection.get()
            assert projection.revocation_generation == 1
            assert runtime.projection.status()["revocation_generation"] == 1
        finally:
            runtime.close()


def test_correction_created_fact_ids_are_stable() -> None:
    """F10 (main file): correction anchors survive repeated application."""
    from entorhinal.schemas.models import CorrectionAction, UserCorrection
    from entorhinal.user_control.corrections import CorrectionManager

    manager = CorrectionManager()
    corr = UserCorrection(
        target_entity_or_fact_id="project:stable-test",
        override_action=CorrectionAction.OVERWRITE,
        corrected_value={"name": "Renamed"},
    )
    manager.register_correction_object(corr)
    first = manager.apply_to_facts([])
    second = manager.apply_to_facts([])
    assert len(first) == 1 and len(second) == 1
    assert first[0].fact_id == second[0].fact_id
    assert first[0].fact_id.startswith("fact-v1-")
    # A distinct correction value yields a distinct id (no collision).
    manager2 = CorrectionManager()
    corr2 = UserCorrection(
        target_entity_or_fact_id="project:stable-test",
        override_action=CorrectionAction.OVERWRITE,
        corrected_value={"name": "Other"},
    )
    manager2.register_correction_object(corr2)
    other = manager2.apply_to_facts([])
    assert other[0].fact_id != first[0].fact_id


def test_auth_cli_bootstrap_grant_list_revoke_round_trip() -> None:
    """F1 seam: auth CLI bootstraps, grants, lists, and revokes."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_list0 = runner.invoke(cli_app, ["auth", "list", "--dir", tmp_dir])
        assert res_list0.exit_code == 0, res_list0.output
        assert "No principals" in res_list0.output

        res_boot = runner.invoke(cli_app, ["auth", "bootstrap", "--dir", tmp_dir])
        assert res_boot.exit_code == 0, res_boot.output
        assert "admin.bootstrap" in res_boot.output
        assert "shown ONCE" in res_boot.output

        res_boot2 = runner.invoke(cli_app, ["auth", "bootstrap", "--dir", tmp_dir])
        assert res_boot2.exit_code == 1  # second bootstrap refuses
        assert "already has principals" in res_boot2.output

        res_grant = runner.invoke(cli_app, [
            "auth", "grant", "--id", "reader.t1", "--role", "reader",
            "--purpose", "resumption", "--scope", "scope:terminal",
            "--dir", tmp_dir,
        ])
        assert res_grant.exit_code == 0, res_grant.output
        assert "reader.t1" in res_grant.output

        res_list = runner.invoke(cli_app, ["auth", "list", "--dir", tmp_dir])
        assert res_list.exit_code == 0, res_list.output
        assert "reader.t1" in res_list.output
        assert "ent_" not in res_list.output  # secrets never listed

        res_revoke = runner.invoke(cli_app, ["auth", "revoke", "reader.t1", "--dir", tmp_dir])
        assert res_revoke.exit_code == 0, res_revoke.output
        res_revoke2 = runner.invoke(cli_app, ["auth", "revoke", "reader.t1", "--dir", tmp_dir])
        assert res_revoke2.exit_code == 1
        assert "not found" in res_revoke2.output


@pytest.mark.asyncio
async def test_adapter_without_hook_is_skipped_silently() -> None:
    """N4: adapters lacking purge_managed do not appear in the proof."""

    class _Plain:
        pass

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = SQLiteEvidenceStore(root / "evidence.db")
        try:
            await store.append_evidence(_make_record())
            service = UserControlService(
                journal=store,  # type: ignore[arg-type]
                storage_dir=root,
                adapter_accessor=lambda: {"dev-task": _Plain()},
            )
            now = datetime.now(timezone.utc)
            proof = await service.forget_time_range(
                start_time=now - timedelta(hours=1),
                end_time=now + timedelta(hours=1),
                reason="n4 skip test",
            )
            assert "adapter_purge" not in proof
        finally:
            store.close()
