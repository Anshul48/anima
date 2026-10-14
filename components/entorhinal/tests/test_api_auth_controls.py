"""F1/F2 controls: authenticated disclosure routes and bound ingest identity.

Every HTTP disclosure and governance route on the runtime serving path
requires an authenticated principal with the right role; ingest binds the
stored source to the configured authenticated source, never to
caller-supplied labels. All data is fresh synthetic per-test material.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from entorhinal.api.app import create_app
from entorhinal.runtime import build_runtime, close_runtime
from entorhinal.runtime.auth import AuthStore
from entorhinal.runtime.config import RuntimeConfig

CONFIGURED_SOURCE = "entorhinal.dev-task.01"


def _bootstrap(root: Path) -> dict[str, dict[str, str]]:
    auth = AuthStore(root / "auth_principals.json")
    _, source_secret = auth.create_principal(
        role="source",
        principal_id="test.source",
        allowed_purposes=["ingest"],
        allowed_scopes=[],
        source_id=CONFIGURED_SOURCE,
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


def _obs_payload(obs_id: str) -> dict[str, Any]:
    return {
        "contract_version": "vNext-2026.1",
        "observation_id": obs_id,
        "observed_at_ms": 1786960800000.0,
        "source_system": "caller.supplied.box",
        "source_subsystem": "synthetic_probe",
        "consent_scope": "scope:whatever.caller.claims",
        "epistemic_uncertainty": {
            "grounding_confidence": 0.98,
            "is_inferred": False,
            "freshness_ttl_ms": 300000.0,
        },
        "perception_payload": {
            "app_identifier": "synth-probe",
            "window_title": "SYNTHETIC probe window",
            "target_uri": "file:///synthetic/probe.txt",
            "custom_attributes": {"probe": True},
        },
    }


@pytest.fixture
def env(tmp_path: Path):
    root = tmp_path / "rt"
    headers = _bootstrap(root)
    rt = build_runtime(RuntimeConfig.from_root(root, default_allow=True))
    rt.pipeline.debounced_window_ms = 0
    app = create_app(runtime=rt)
    client = TestClient(app)
    yield {"runtime": rt, "app": app, "client": client, "root": root, "headers": headers}
    client.close()
    asyncio.run(close_runtime(rt))


def _snapshot_body() -> dict[str, Any]:
    return {
        "consumer_id": "test.reader",
        "stated_purpose": "test read",
        "requested_scopes": ["scope:workspace.*"],
        "token_or_size_budget": 2048,
        "max_freshness_seconds": 86400,
    }


# --------------------------------------------------------------------------
# F1: every disclosure/governance route authenticates
# --------------------------------------------------------------------------

_DISCLOSURE_GETS = [
    "/api/v1/context/timeline",
    "/api/v1/context/focus",
    "/api/v1/context/graph",
    "/api/v1/context/explain/fact-nope",
    "/api/v1/sources/health",
    "/api/v1/user/corrections",
    "/api/v1/user/grants",
    "/api/v1/user/audit",
    "/api/v1/user/export",
    "/api/v1/admin/principals",
]


@pytest.mark.parametrize("route", _DISCLOSURE_GETS)
def test_anonymous_disclosure_denied(env, route: str) -> None:
    res = env["client"].get(route)
    assert res.status_code == 401, (route, res.text)


def test_anonymous_writes_denied(env) -> None:
    client = env["client"]
    assert client.post("/api/v1/ingest", json=_obs_payload("obs-anon-1")).status_code == 401
    assert client.post("/api/v1/observations", json=_obs_payload("obs-anon-2")).status_code == 401
    assert client.post("/api/v1/context/request", json=_snapshot_body()).status_code == 401
    assert (
        client.post("/api/v1/context/packet", json={"task_id": "t", "purpose": "resumption"}).status_code
        == 401
    )
    assert client.post("/api/v1/user/forget", json={}).status_code == 401
    assert client.post("/api/v1/admin/principals", json={}).status_code == 401


def test_unknown_credential_denied(env) -> None:
    res = env["client"].get(
        "/api/v1/context/timeline", headers={"Authorization": "Bearer ent_unknown000"}
    )
    assert res.status_code == 401


def test_role_separation(env) -> None:
    client, headers = env["client"], env["headers"]
    # Source principals ingest but never read disclosure routes.
    assert (
        client.get("/api/v1/context/timeline", headers=headers["source"]).status_code == 403
    )
    assert (
        client.post("/api/v1/context/request", headers=headers["source"], json=_snapshot_body()).status_code
        == 403
    )
    # Reader principals read but never ingest or govern.
    assert (
        client.post("/api/v1/ingest", headers=headers["reader"], json=_obs_payload("obs-r-1")).status_code
        == 403
    )
    assert client.get("/api/v1/user/export", headers=headers["reader"]).status_code == 403
    assert client.get("/api/v1/admin/principals", headers=headers["reader"]).status_code == 403
    # Granted reads succeed.
    assert (
        client.get("/api/v1/context/timeline", headers=headers["reader"]).status_code == 200
    )
    assert (
        client.get("/api/v1/user/export", headers=headers["admin"]).status_code == 200
    )


def test_consumer_id_must_match_principal(env) -> None:
    body = _snapshot_body()
    body["consumer_id"] = "someone.else"
    res = env["client"].post("/api/v1/context/request", headers=env["headers"]["reader"], json=body)
    assert res.status_code == 403


def test_health_minimal_public_full_authenticated(env) -> None:
    client, headers = env["client"], env["headers"]
    public = client.get("/api/v1/health")
    assert public.status_code == 200
    assert set(public.json().keys()) == {"status", "service", "version"}
    full = client.get("/api/v1/health", headers=headers["reader"])
    assert full.status_code == 200
    body = full.json()
    assert body["fact_id_algorithm"] == "fact-id/1"
    assert body["cluster_id_algorithm"] == "cluster-id/1"
    assert "journal_records_count" in body


def test_websocket_requires_token(env) -> None:
    client = env["client"]
    # No credential: handshake refused.
    try:
        with client.websocket_connect("/ws/v1/context/focus") as ws:
            ws.receive_json()
        raise AssertionError("unauthenticated websocket was accepted")
    except Exception:
        pass
    # Reader credential: first frame arrives promptly.
    token = env["headers"]["reader"]["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(f"/ws/v1/context/focus?token={token}") as ws:
        frame = ws.receive_json()
    assert frame["type"] == "focus_update"


def test_runtime_path_has_no_bypass_knob(env) -> None:
    with pytest.raises(ValueError):
        create_app(runtime=env["runtime"], require_auth=False)


# --------------------------------------------------------------------------
# F2: ingest identity comes from the authenticated binding
# --------------------------------------------------------------------------

def test_ingest_binds_configured_source_not_caller_label(env) -> None:
    client, headers, rt = env["client"], env["headers"], env["runtime"]
    res = client.post("/api/v1/observations", headers=headers["source"], json=_obs_payload("obs-f2-1"))
    assert res.status_code == 200, res.text
    evidence_id = res.json()["evidence_id"]
    assert evidence_id
    stored = asyncio.run(rt.store.get_by_id(evidence_id))
    assert stored is not None
    receipt = asyncio.run(rt.store.get_receipt(CONFIGURED_SOURCE, "obs-f2-1"))
    assert receipt is not None
    assert receipt.source_id == CONFIGURED_SOURCE
    # The caller-claimed source was NOT minted as an identity.
    assert asyncio.run(rt.store.get_receipt("caller.supplied.box", "obs-f2-1")) is None


def test_wrong_source_principal_rejected(env) -> None:
    auth = AuthStore(env["root"] / "auth_principals.json")
    _, secret = auth.create_principal(
        role="source",
        principal_id="test.source.other",
        allowed_purposes=["ingest"],
        allowed_scopes=[],
        source_id="some.other.source",
    )
    res = env["client"].post(
        "/api/v1/ingest",
        headers={"Authorization": f"Bearer {secret}"},
        json=_obs_payload("obs-f2-wrong"),
    )
    assert res.status_code == 403


# --------------------------------------------------------------------------
# Principal lifecycle: revoke/unknown handling
# --------------------------------------------------------------------------

def test_revoked_principal_is_unknown(env) -> None:
    client, headers = env["client"], env["headers"]
    auth = AuthStore(env["root"] / "auth_principals.json")
    _, secret = auth.create_principal(
        role="reader",
        principal_id="test.reader.temp",
        allowed_purposes=["test read"],
        allowed_scopes=["scope:workspace.*"],
    )
    temp = {"Authorization": f"Bearer {secret}"}
    assert client.get("/api/v1/context/timeline", headers=temp).status_code == 200
    res = client.post("/api/v1/admin/principals/test.reader.temp/revoke", headers=headers["admin"])
    assert res.status_code == 200
    assert client.get("/api/v1/context/timeline", headers=temp).status_code == 401


def test_admin_principal_lifecycle(env) -> None:
    client, headers = env["client"], env["headers"]
    created = client.post(
        "/api/v1/admin/principals",
        headers=headers["admin"],
        json={
            "role": "reader",
            "principal_id": "test.reader.http",
            "allowed_purposes": ["test read"],
            "allowed_scopes": ["scope:workspace.*"],
            "max_budget": 512,
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["secret"].startswith("ent_")
    # The secret is shown once: the list endpoint carries no secret material.
    listed = client.get("/api/v1/admin/principals", headers=headers["admin"])
    assert listed.status_code == 200
    for entry in listed.json():
        assert "secret" not in entry
        assert "secret_sha256" not in entry
    assert any(e["principal_id"] == "test.reader.http" for e in listed.json())
    # Duplicate creation is a conflict, not a second credential.
    dup = client.post(
        "/api/v1/admin/principals",
        headers=headers["admin"],
        json={
            "role": "reader",
            "principal_id": "test.reader.http",
            "allowed_purposes": ["test read"],
            "allowed_scopes": ["scope:workspace.*"],
        },
    )
    assert dup.status_code == 409
