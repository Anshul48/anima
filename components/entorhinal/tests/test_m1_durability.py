"""M1 durability acceptance slice (E1): factory, serve path, receipts, lifecycle.

Demonstrates through the actual serve/HTTP path backed by the runtime
factory: transactional commit, committed receipts matching stored records,
retry/conflict/failure semantics, projector-degraded catch-up, persistent
grants, and real source start/stop/health with cursor-after-commit.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from entorhinal.api.app import create_app
from entorhinal.evidence.receipts import CommitState
from entorhinal.runtime import build_runtime, close_runtime, register_adapter
from entorhinal.runtime.auth import AuthStore
from entorhinal.runtime.config import RuntimeConfig, SourceSpec
from entorhinal.schemas.models import RawSignalEvent, SourceType
from entorhinal.sources.base import BaseSourceAdapter


def _bootstrap_test_auth(root: Path) -> dict[str, dict[str, str]]:
    """Create persisted source/reader/admin principals for the serving path.

    The runtime HTTP surface authenticates every route; tests bootstrap
    explicit role credentials against the same auth store the app loads.
    """
    auth = AuthStore(root / "auth_principals.json")
    _, source_secret = auth.create_principal(
        role="source",
        principal_id="test.source",
        allowed_purposes=["ingest"],
        allowed_scopes=[],
        source_id="entorhinal.dev-task.01",
    )
    _, reader_secret = auth.create_principal(
        role="reader",
        principal_id="test.reader",
        allowed_purposes=["test read"],
        allowed_scopes=["scope:workspace.*", "scope:browser.*", "scope:terminal.*"],
    )
    _, admin_secret = auth.create_principal(
        role="admin",
        principal_id="test.admin",
        allowed_purposes=["administration"],
        allowed_scopes=["*"],
    )
    return {
        "source": {"Authorization": f"Bearer {source_secret}"},
        "reader": {"Authorization": f"Bearer {reader_secret}"},
        "admin": {"Authorization": f"Bearer {admin_secret}"},
    }


# --------------------------------------------------------------------------
# Stub source adapter (stands in for the sibling dev-task adapter)
# --------------------------------------------------------------------------

class StubSourceAdapter(BaseSourceAdapter):
    """In-memory SourcePort with cursor-after-commit semantics."""

    def __init__(self, spec=None, **kwargs):
        super().__init__(**kwargs)
        self._spec = spec
        self.started = False
        self.stopped = False
        self.cursor = 0
        self.admitted_ids: list[str] = []

    @property
    def adapter_id(self) -> str:
        return "stub.m1"

    @property
    def source_type(self) -> SourceType:
        return SourceType.TERMINAL_PTY

    async def start(self) -> None:
        await super().start()
        self.started = True

    async def stop(self) -> None:
        await super().stop()
        self.stopped = True

    def note_admitted(self, signal: RawSignalEvent) -> None:
        """Advance the cursor. The runtime calls this ONLY after durable commit."""
        self.cursor += 1
        self.admitted_ids.append(signal.signal_id)


STUB_INSTANCES: list[StubSourceAdapter] = []


def _stub_factory(spec) -> StubSourceAdapter:
    inst = StubSourceAdapter(spec=spec)
    STUB_INSTANCES.append(inst)
    return inst


register_adapter("m1-stub", _stub_factory)


def _obs_payload(obs_id: str, branch: str = "main", app: str = "code") -> dict[str, Any]:
    return {
        "contract_version": "vNext-2026.1",
        "observation_id": obs_id,
        "observed_at_ms": 1786960800000.0,
        "source_system": "reflex.linux.native",
        "source_subsystem": "at_spi_accessibility",
        "consent_scope": "scope:developer.ide",
        "epistemic_uncertainty": {
            "grounding_confidence": 0.98,
            "is_inferred": False,
            "freshness_ttl_ms": 300000.0,
        },
        "perception_payload": {
            "app_identifier": app,
            "window_title": "engine.py - entorhinal - Visual Studio Code",
            "target_uri": "file:///workspace/entorhinal/src/engine.py",
            "custom_attributes": {"git_branch": branch, "cursor_line": 142},
        },
    }


@pytest.fixture
def runtime_env(tmp_path: Path):
    config = RuntimeConfig.from_root(tmp_path / "rt", default_allow=True)
    headers = _bootstrap_test_auth(tmp_path / "rt")
    rt = build_runtime(config)
    rt.pipeline.debounced_window_ms = 0  # retries must reach the store, not debounce
    app = create_app(runtime=rt)
    client = TestClient(app)
    yield {"runtime": rt, "app": app, "client": client, "root": tmp_path / "rt", "headers": headers}
    client.close()
    asyncio.run(close_runtime(rt))


# --------------------------------------------------------------------------
# HTTP durable ingest through the factory path
# --------------------------------------------------------------------------

def test_http_commit_receipt_matches_stored_record(runtime_env):
    rt = runtime_env["runtime"]
    client = runtime_env["client"]
    res = client.post("/api/v1/observations", headers=runtime_env["headers"]["source"], json=_obs_payload("obs-m1-001"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == CommitState.COMMITTED_PROJECTED.value
    assert body["admitted"] is True
    stored = asyncio.run(rt.store.get_by_id(body["evidence_id"]))
    assert stored is not None
    assert stored.provenance_hash == body["provenance_hash"]
    assert stored.app_identifier == "code"


def test_http_exact_retry_returns_same_receipt(runtime_env):
    client = runtime_env["client"]
    rt = runtime_env["runtime"]
    first = client.post("/api/v1/observations", headers=runtime_env["headers"]["source"], json=_obs_payload("obs-m1-002")).json()
    second = client.post("/api/v1/observations", headers=runtime_env["headers"]["source"], json=_obs_payload("obs-m1-002")).json()
    assert second["evidence_id"] == first["evidence_id"]
    assert second["provenance_hash"] == first["provenance_hash"]
    assert asyncio.run(rt.store.count_records()) == 1


def test_http_conflicting_reuse_is_409(runtime_env):
    client = runtime_env["client"]
    assert client.post("/api/v1/observations", headers=runtime_env["headers"]["source"], json=_obs_payload("obs-m1-003")).status_code == 200
    res = client.post("/api/v1/observations", headers=runtime_env["headers"]["source"], json=_obs_payload("obs-m1-003", branch="evil"))
    assert res.status_code == 409


def test_http_storage_failure_is_503_with_no_record(runtime_env):
    client = runtime_env["client"]
    rt = runtime_env["runtime"]
    before = asyncio.run(rt.store.count_records())
    rt.store.fail_next_commits = 1
    res = client.post("/api/v1/observations", headers=runtime_env["headers"]["source"], json=_obs_payload("obs-m1-004"))
    assert res.status_code == 503
    assert asyncio.run(rt.store.count_records()) == before
    # Retry after the fault clears commits normally.
    res2 = client.post("/api/v1/observations", headers=runtime_env["headers"]["source"], json=_obs_payload("obs-m1-004"))
    assert res2.status_code == 200


def test_http_projector_failure_degraded_then_catch_up(runtime_env):
    client = runtime_env["client"]
    rt = runtime_env["runtime"]

    def boom(record):
        raise RuntimeError("projector down")

    rt.store.set_projector(boom)
    try:
        res = client.post("/api/v1/observations", headers=runtime_env["headers"]["source"], json=_obs_payload("obs-m1-005"))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == CommitState.COMMITTED_PENDING_DEGRADED.value
        assert asyncio.run(rt.store.pending_count()) == 1
    finally:
        rt.store.set_projector(lambda rec: rt.compiler.process_incremental_event(rec))
    out = asyncio.run(rt.store.drain_pending())
    assert out["projected"] == 1 and out["still_pending"] == 0
    # F2: rows are stored under the CONFIGURED source, not caller labels.
    receipt = asyncio.run(rt.store.get_receipt("entorhinal.dev-task.01", "obs-m1-005"))
    assert receipt is not None and receipt.state == CommitState.COMMITTED_PROJECTED


def test_http_health_reports_store_and_sources(runtime_env):
    client = runtime_env["client"]
    headers = runtime_env["headers"]["reader"]
    data = client.get("/api/v1/health", headers=headers).json()
    assert data["status"] == "healthy"
    assert data["store"]["backend"] == "sqlite"
    assert data["store"]["journal_mode"] == "DELETE"
    assert "sources" in data
    src = client.get("/api/v1/sources/health", headers=headers).json()
    assert src["lifecycle_running"] is False
    # Unauthenticated callers get minimal liveness only.
    minimal = client.get("/api/v1/health").json()
    assert minimal["status"] == "healthy"
    assert "store" not in minimal


def test_policy_deny_default_and_persistent_grant(tmp_path: Path):
    """Default-deny runtime 403s; an explicit grant permits and survives rebuild."""
    root = tmp_path / "deny"
    headers = _bootstrap_test_auth(root)
    rt1 = build_runtime(RuntimeConfig.from_root(root))  # default_allow=False
    try:
        c1 = TestClient(create_app(runtime=rt1))
        denied = c1.post(
            "/api/v1/observations", headers=headers["source"], json=_obs_payload("obs-deny")
        )
        assert denied.status_code == 403
        import asyncio as _aio

        from entorhinal.schemas.models import SourceType as _ST

        _aio.run(rt1.user_control.grant_consent(_ST.OS_WINDOW, "*", "*"))
        ok = c1.post(
            "/api/v1/observations", headers=headers["source"], json=_obs_payload("obs-deny")
        )
        assert ok.status_code == 200, ok.text
        c1.close()
    finally:
        asyncio.run(close_runtime(rt1))
    # Grants persist across restart; the committed event survives too.
    rt2 = build_runtime(RuntimeConfig.from_root(root))
    try:
        assert len(rt2.user_control.list_consent_rules()) == 1
        c2 = TestClient(create_app(runtime=rt2))
        retry = c2.post(
            "/api/v1/observations", headers=headers["source"], json=_obs_payload("obs-deny")
        )
        assert retry.status_code == 200
        assert asyncio.run(rt2.store.count_records()) == 1
        c2.close()
    finally:
        asyncio.run(close_runtime(rt2))


# --------------------------------------------------------------------------
# Source lifecycle + cursor-after-commit
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_source_lifecycle_start_stop_health(tmp_path: Path):
    STUB_INSTANCES.clear()
    config = RuntimeConfig.from_root(
        tmp_path / "lc", default_allow=True,
        sources=[SourceSpec(name="stub", adapter="m1-stub")],
    )
    rt = build_runtime(config)
    try:
        assert rt.sources.health()["lifecycle_running"] is False
        await rt.start_sources()
        assert len(STUB_INSTANCES) == 1
        stub = STUB_INSTANCES[0]
        assert stub.started and not stub.stopped
        health = rt.sources.health()
        assert health["lifecycle_running"] is True
        assert health["sources"]["stub"]["is_healthy"] is True
        await rt.stop_sources()
        assert stub.stopped is True
        assert rt.sources.health()["lifecycle_running"] is False
    finally:
        await close_runtime(rt)


def test_app_lifespan_shutdown_stops_runtime(tmp_path: Path):
    """Lifespan shutdown stops sources + store (SIGTERM never reaches serve finally)."""
    from starlette.testclient import TestClient

    STUB_INSTANCES.clear()
    config = RuntimeConfig.from_root(
        tmp_path / "ls", default_allow=True,
        sources=[SourceSpec(name="stub", adapter="m1-stub")],
    )
    rt = build_runtime(config)
    asyncio.run(rt.start_sources())
    assert STUB_INSTANCES[0].started and not STUB_INSTANCES[0].stopped
    app = create_app(runtime=rt)
    with TestClient(app):
        pass
    assert STUB_INSTANCES[0].stopped is True
    assert rt.store._closed is True
    assert rt.sources.health()["lifecycle_running"] is False


@pytest.mark.asyncio
async def test_cursor_advances_only_after_durable_admission(tmp_path: Path):
    STUB_INSTANCES.clear()
    config = RuntimeConfig.from_root(
        tmp_path / "cur", default_allow=True,
        sources=[SourceSpec(name="stub", adapter="m1-stub")],
    )
    rt = build_runtime(config)
    try:
        await rt.sources.start()
        await rt.pipeline.start()
        stub = STUB_INSTANCES[0]

        def _sig(i: int) -> RawSignalEvent:
            return RawSignalEvent(
                signal_id=f"sig-{i}",
                source_type=SourceType.TERMINAL_PTY,
                adapter_id="stub.m1",
                app_identifier="bash",
                raw_payload={"event_type": "command_execution", "cmd": f"echo {i}"},
            )

        # Failed commit: no cursor movement, no record.
        rt.store.fail_next_commits = 1
        failed = await rt.admit_signal("stub", _sig(1))
        assert failed.state == CommitState.RETRYABLE_STORAGE_FAILURE
        assert stub.cursor == 0
        assert await rt.store.count_records() == 0
        # Successful commit: cursor advances exactly once.
        ok_receipt = await rt.admit_signal("stub", _sig(1))
        assert ok_receipt.committed
        assert stub.cursor == 1
        assert stub.admitted_ids == ["sig-1"]
    finally:
        await close_runtime(rt)


@pytest.mark.asyncio
async def test_pump_admits_polled_signals_end_to_end(tmp_path: Path):
    STUB_INSTANCES.clear()
    config = RuntimeConfig.from_root(
        tmp_path / "pump", default_allow=True,
        sources=[SourceSpec(name="stub", adapter="m1-stub")],
    )
    rt = build_runtime(config)
    try:
        await rt.start_sources()
        stub = STUB_INSTANCES[0]
        await stub.emit_signal(RawSignalEvent(
            signal_id="pump-1",
            source_type=SourceType.TERMINAL_PTY,
            adapter_id="stub.m1",
            app_identifier="bash",
            raw_payload={"event_type": "command_execution", "cmd": "pytest -q"},
        ))
        deadline = time.time() + 10.0
        while stub.cursor == 0 and time.time() < deadline:
            await asyncio.sleep(0.05)
        assert stub.cursor == 1
        assert await rt.store.count_records() == 1
        receipt = await rt.store.get_receipt("stub", "pump-1")
        assert receipt is not None and receipt.committed
    finally:
        await close_runtime(rt)


# --------------------------------------------------------------------------
# serve wiring (no socket bind; uvicorn.Server.serve faked)
# --------------------------------------------------------------------------

def test_serve_wire_sources_starts_and_stops_adapter(tmp_path: Path, monkeypatch):
    import uvicorn

    from typer.testing import CliRunner

    from entorhinal.cli.main import app as cli_app

    STUB_INSTANCES.clear()
    served: list[str] = []

    async def fake_serve(self):
        served.append("served")

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)
    runner = CliRunner()
    result = runner.invoke(cli_app, [
        "serve", "--wire-sources", "--source", "m1-stub:stub",
        "--dir", str(tmp_path / "srv"),
    ])
    assert result.exit_code == 0, result.output
    assert served == ["served"]
    assert len(STUB_INSTANCES) == 1
    stub = STUB_INSTANCES[0]
    assert stub.started is True and stub.stopped is True  # clean shutdown
    assert "m1-stub" in result.output
    assert (tmp_path / "srv" / "evidence.db").exists()


def test_serve_source_opts_reach_adapter_factory(tmp_path: Path, monkeypatch):
    import uvicorn

    from typer.testing import CliRunner

    from entorhinal.cli.main import app as cli_app

    STUB_INSTANCES.clear()

    async def fake_serve(self):
        return None

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)
    runner = CliRunner()
    result = runner.invoke(cli_app, [
        "serve", "--wire-sources", "--source", "m1-stub:stub",
        "--source-opt", "stub.inbox_path=/tmp/inbox.jsonl",
        "--dir", str(tmp_path / "srv3"),
    ])
    assert result.exit_code == 0, result.output
    assert STUB_INSTANCES[0]._spec.options == {"inbox_path": "/tmp/inbox.jsonl"}


def test_serve_source_opts_support_dotted_names(tmp_path: Path, monkeypatch):
    """--source-opt longest-matches dotted source names (e.g. entorhinal.dev-task.01)."""
    import uvicorn

    from typer.testing import CliRunner

    from entorhinal.cli.main import app as cli_app

    STUB_INSTANCES.clear()

    async def fake_serve(self):
        return None

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)
    runner = CliRunner()
    result = runner.invoke(cli_app, [
        "serve", "--wire-sources", "--source", "m1-stub:entorhinal.dev-task.01",
        "--source-opt", "entorhinal.dev-task.01.inbox_path=/tmp/inbox.jsonl",
        "--source-opt", "entorhinal.dev-task.01.manifest_path=/tmp/m.json",
        "--dir", str(tmp_path / "srv4"),
    ])
    assert result.exit_code == 0, result.output
    assert STUB_INSTANCES[0]._spec.options == {
        "inbox_path": "/tmp/inbox.jsonl", "manifest_path": "/tmp/m.json",
    }


def test_serve_wire_sources_without_adapter_is_truthful(tmp_path: Path, monkeypatch):
    import uvicorn

    from typer.testing import CliRunner

    from entorhinal.cli.main import app as cli_app

    async def fake_serve(self):
        return None

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)
    runner = CliRunner()
    result = runner.invoke(cli_app, [
        "serve", "--wire-sources", "--dir", str(tmp_path / "srv2"),
    ])
    assert result.exit_code == 0, result.output
    assert "no source adapter is configured" in result.output


def test_serve_dev_task_without_options_fails_closed(tmp_path: Path, monkeypatch):
    """Explicit --source without required opts fails closed, never half-starts."""
    import uvicorn

    from typer.testing import CliRunner

    from entorhinal.cli.main import app as cli_app

    async def fake_serve(self):
        return None  # pragma: no cover - startup must fail before serving

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)
    runner = CliRunner()
    result = runner.invoke(cli_app, [
        "serve", "--wire-sources", "--dir", str(tmp_path / "srv3"),
        "--source", "dev-task-inbox:entorhinal.dev-task.01",
    ])
    assert result.exit_code == 1, result.output
    assert "Failed to start configured sources" in result.output
    assert "inbox_path" in result.output or "manifest_path" in result.output


# --------------------------------------------------------------------------
# Demo: commit -> reopen -> same-receipt retry
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_demo_commit_reopen_same_receipt_retry(tmp_path: Path):
    """Short demo: commit, close/reopen, retry returns the ORIGINAL receipt."""
    from entorhinal.evidence.sqlite_store import SQLiteEvidenceStore

    db = tmp_path / "demo.db"
    record = {
        "source_type": "terminal_pty",
        "app_identifier": "pytest",
        "window_title": None,
        "target_uri": None,
        "sanitized_payload": {"event_type": "checked_outcome", "exit_status": 0},
        "classification": "internal",
    }
    first = SQLiteEvidenceStore(db)
    r1 = await first.commit_event("entorhinal.dev-task.01", "demo-evt-1", record)
    assert r1.committed
    print(f"\ncommit: seq={r1.commit_seq} evidence={r1.evidence_id} hash={r1.content_hash[:16]}...")
    first.close()  # simulate process exit

    second = SQLiteEvidenceStore(db)  # restart
    try:
        retry = await second.commit_event("entorhinal.dev-task.01", "demo-evt-1", record)
        assert retry.is_duplicate is True
        assert retry.evidence_id == r1.evidence_id
        assert retry.commit_seq == r1.commit_seq
        assert await second.count_records() == 1
        print(f"retry after reopen: same evidence={retry.evidence_id} (one effect)")
    finally:
        second.close()
