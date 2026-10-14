"""Main-owned activity integration: store -> sessions -> inspect -> forget.

Proves the integrated permitted-source path through durable storage, local
classification/continuity, inspection, and deletion cascade using NEW
synthetic activity only. The activity component itself is owned and tested
by the activity builder; these tests cover main's wiring (pump feed,
factory service, forget cascade, CLI inspection).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
from typing import Any, List

import pytest
from typer.testing import CliRunner

import sys

sys.path.insert(0, "tests")

from activity_fixtures import (  # noqa: E402
    SYNTH_BROWSER,
    SYNTH_GRANT_BROWSER,
    make_event,
    media_payload,
)

from entorhinal.activity.events import ActivityKind  # noqa: E402
from entorhinal.activity.grants import SourceGrant  # noqa: E402
from entorhinal.cli.main import app as cli_app  # noqa: E402
from entorhinal.runtime.config import RuntimeConfig  # noqa: E402
from entorhinal.runtime.factory import build_runtime  # noqa: E402

# Dynamic anchor: the store forget window keys on durable commit time
# (wall clock) while the activity cascade keys on observed_at. Anchoring
# fixtures to wall-now keeps both clocks aligned whenever the suite runs;
# a fixed T0 only passes within T0 +/- the forget window.
T0 = datetime.now(timezone.utc).replace(microsecond=0)


class _ScriptedAdapter:
    def __init__(self, signals: List[Any]) -> None:
        self._signals = list(signals)

    async def poll_signals(self) -> List[Any]:
        pending, self._signals = self._signals, []
        return pending


def _grant() -> SourceGrant:
    return SourceGrant(
        grant_id=SYNTH_GRANT_BROWSER,
        source_id=SYNTH_BROWSER,
        principal="synth-integration",
        note="NEW synthetic integration grant",
    )


def _lecture_events() -> List[Any]:
    """Two spans of the SAME synthetic lecture (continuity expected)."""
    return [
        make_event(
            "syn-int-001", T0,
            kind=ActivityKind.MEDIA_FOREGROUND,
            title="SYNTHETIC Lecture 7: Hippocampus",
            uri="https://video.example.test/watch?v=SYNTH-LECTURE-7",
            payload=media_payload("SYNTH-LECTURE-7", 120.0, "playing"),
        ),
        make_event(
            "syn-int-002", T0 + timedelta(minutes=5),
            kind=ActivityKind.MEDIA_FOREGROUND,
            title="SYNTHETIC Lecture 7: Hippocampus",
            uri="https://video.example.test/watch?v=SYNTH-LECTURE-7",
            payload=media_payload("SYNTH-LECTURE-7", 420.0, "playing"),
        ),
    ]


@pytest.mark.asyncio
async def test_activity_snapshot_survives_restart() -> None:
    """I-3: runtime close persists derived activity state; a rebuilt
    runtime on the same root recovers sessions instead of starting empty."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            assert runtime.activity is not None
            runtime.activity.grants.add(_grant())
            signals = [e.to_raw_signal_event() for e in _lecture_events()]
            runtime.sources._adapters["fake"] = _ScriptedAdapter(signals)
            await runtime._pump_once()
            assert len(runtime.activity.sessions()) == 1
        finally:
            runtime.close()
        rebuilt = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            assert rebuilt.activity is not None
            sessions = rebuilt.activity.sessions()
            assert len(sessions) == 1
            assert len(sessions[0].span_ids) >= 1
        finally:
            rebuilt.close()


@pytest.mark.asyncio
async def test_pump_feed_commits_and_builds_sessions() -> None:
    """Admitted activity signals commit durably AND feed local sessions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            assert runtime.activity is not None
            runtime.activity.grants.add(_grant())
            signals = [e.to_raw_signal_event() for e in _lecture_events()]
            runtime.sources._adapters["fake"] = _ScriptedAdapter(signals)
            await runtime._pump_once()

            stats = runtime.pump_stats()["fake"]
            assert stats["polled"] == 2
            assert stats["committed"] == 2
            assert stats["activity_admitted"] == 2
            assert stats["activity_not_admitted"] == 0
            assert await runtime.store.count_records() == 2

            sessions = runtime.activity.sessions()
            assert len(sessions) == 1  # same lecture continues one session
            assert len(sessions[0].span_ids) >= 1
            status = runtime.health()["activity"]
            assert status["available"] is True
            assert status["sessions"] == 1
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_activity_denied_without_grant_but_evidence_commits() -> None:
    """Grant-denied activity is counted, while the store commit stands."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            assert runtime.activity is not None
            # No grant added: service ingest denies; store admission allows.
            signals = [e.to_raw_signal_event() for e in _lecture_events()[:1]]
            runtime.sources._adapters["fake"] = _ScriptedAdapter(signals)
            await runtime._pump_once()
            stats = runtime.pump_stats()["fake"]
            assert stats["committed"] == 1
            assert stats["activity_admitted"] == 0
            assert stats["activity_not_admitted"] == 1
            assert runtime.activity.events() == []
        finally:
            runtime.close()


@pytest.mark.asyncio
async def test_forget_cascades_into_activity_state() -> None:
    """Forget tombstones store rows and cascades into derived activity."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            runtime.activity.grants.add(_grant())
            signals = [e.to_raw_signal_event() for e in _lecture_events()]
            runtime.sources._adapters["fake"] = _ScriptedAdapter(signals)
            await runtime._pump_once()
            assert len(runtime.activity.events()) == 2

            proof = await runtime.user_control.forget_time_range(
                start_time=T0 - timedelta(hours=1),
                end_time=T0 + timedelta(hours=1),
                reason="activity cascade test",
            )
            assert proof["tombstoned_records_count"] == 2
            cascade = proof.get("activity_deletion")
            assert cascade is not None, proof
            assert cascade["deleted_events"] == 2
            assert cascade["remaining_events"] == 0
            assert "activity_deletion_error" not in proof
        finally:
            runtime.close()


def test_cli_activity_sessions_and_explain() -> None:
    """CLI inspects sessions and explanations from committed evidence."""
    import asyncio

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        runtime = build_runtime(RuntimeConfig.from_root(tmp_dir, default_allow=True))
        try:
            runtime.activity.grants.add(_grant())

            async def _admit() -> None:
                for event in _lecture_events():
                    await runtime.admit_signal(
                        "fake", event.to_raw_signal_event()
                    )

            asyncio.run(_admit())
            sessions = runtime.activity.sessions()
            assert len(sessions) == 1
            session_id = sessions[0].session_id
        finally:
            runtime.close()

        res_sessions = runner.invoke(cli_app, ["activity", "sessions", "--dir", tmp_dir])
        assert res_sessions.exit_code == 0, res_sessions.output
        assert session_id in res_sessions.output
        # F2: inspection surfaces elapsed + gap-capped steps, not active alone.
        assert "Elapsed" in res_sessions.output
        assert "GapCaps" in res_sessions.output

        res_explain = runner.invoke(
            cli_app, ["activity", "explain", session_id, "--dir", tmp_dir]
        )
        assert res_explain.exit_code == 0, res_explain.output
        assert session_id in res_explain.output
        assert "Span Timing" in res_explain.output
        assert "CappedSteps" in res_explain.output

        # After forget, inspection reflects the tombstoned state (no sessions).
        start_iso = (T0 - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = (T0 + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        res_forget = runner.invoke(cli_app, [
            "forget", "--start", start_iso,
            "--end", end_iso, "--dir", tmp_dir,
        ])
        assert res_forget.exit_code == 0, res_forget.output
        res_after = runner.invoke(cli_app, ["activity", "sessions", "--dir", tmp_dir])
        assert res_after.exit_code == 0, res_after.output
        assert "No logical sessions" in res_after.output


def test_provision_grant_issues_principal_and_grant() -> None:
    """activity provision-grant (§8.5): source principal + persisted grant."""
    from entorhinal.activity.grants import GrantStore
    from entorhinal.runtime.auth import AuthStore

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_boot = runner.invoke(cli_app, ["auth", "bootstrap", "--dir", tmp_dir])
        assert res_boot.exit_code == 0, res_boot.output
        res = runner.invoke(cli_app, [
            "activity", "provision-grant", "--dir", tmp_dir,
            "--source-id", SYNTH_BROWSER,
            "--principal", "synth-producer-01",
            "--grant-id", "grant-synth-01",
            "--app", "Chromium",
            "--domain", "video.example.test",
            "--kind", "window-foreground",
            "--kind", "media-foreground",
            "--label", "synthetic producer",
        ])
        assert res.exit_code == 0, res.output
        assert "grant-synth-01" in res.output
        assert "synth-producer-01" in res.output
        config = RuntimeConfig.from_root(tmp_dir)
        auth = AuthStore(config.auth_path)
        principal = auth.get("synth-producer-01")
        assert principal is not None
        assert principal.role == "source"
        assert principal.source_id == SYNTH_BROWSER
        grants = GrantStore(config.storage_root / "activity" / "grants.json")
        grant = grants.get("grant-synth-01")
        assert grant is not None
        assert grant.source_id == SYNTH_BROWSER
        assert grant.principal == "synth-producer-01"
        assert grant.allow_apps == ["Chromium"]
        assert grant.allow_domains == ["video.example.test"]
        assert {k.value for k in grant.allow_kinds} == {
            "window-foreground", "media-foreground"}


def test_provision_grant_refuses_empty_auth_store() -> None:
    """Provisioning requires auth bootstrap first (no implicit admin)."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        res = runner.invoke(cli_app, [
            "activity", "provision-grant", "--dir", tmp_dir,
            "--source-id", SYNTH_BROWSER,
            "--principal", "synth-producer-01",
        ])
        assert res.exit_code == 1, res.output
        assert "bootstrap" in res.output


def test_provision_grant_rejects_bad_kind() -> None:
    """Unknown --kind values fail with the valid list (no partial write)."""
    from entorhinal.runtime.auth import AuthStore

    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmp_dir:
        res_boot = runner.invoke(cli_app, ["auth", "bootstrap", "--dir", tmp_dir])
        assert res_boot.exit_code == 0, res_boot.output
        res = runner.invoke(cli_app, [
            "activity", "provision-grant", "--dir", tmp_dir,
            "--source-id", SYNTH_BROWSER,
            "--principal", "synth-producer-01",
            "--kind", "key-log",
        ])
        assert res.exit_code == 1, res.output
        assert "media-foreground" in res.output
        config = RuntimeConfig.from_root(tmp_dir)
        assert AuthStore(config.auth_path).get("synth-producer-01") is None
