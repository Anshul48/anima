"""O3: POST /activity/v1/events real-route admission (main-owned).

Real-route twin of the reference ``LocalActivityReceiver``: Bearer auth
via the API auth model, F2-style principal->source/grant binding (caller
labels ignored), ActivityEvent validation, GrantStore.check(), sink to
the activity inbox file, identical ReceiverReceipt shapes. All data is
fresh synthetic per-test material.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from entorhinal.activity.events import ActivityEvent
from entorhinal.activity.grants import GrantStore, SourceGrant
from entorhinal.api.app import create_app
from entorhinal.runtime import build_runtime, close_runtime
from entorhinal.runtime.auth import AuthStore
from entorhinal.runtime.config import RuntimeConfig

SOURCE_ID = "entorhinal.activity.browser.01"
OTHER_SOURCE = "entorhinal.activity.editor.01"
GRANT_ID = "grant-synth-01"
PATH = "/activity/v1/events"


def _bootstrap(root: Path) -> dict[str, dict[str, str]]:
    auth = AuthStore(root / "auth_principals.json")
    _, source_secret = auth.create_principal(
        role="source",
        principal_id="test.activity-producer",
        allowed_purposes=["activity-ingest"],
        allowed_scopes=[],
        source_id=SOURCE_ID,
    )
    _, other_secret = auth.create_principal(
        role="source",
        principal_id="test.other-producer",
        allowed_purposes=["activity-ingest"],
        allowed_scopes=[],
        source_id=OTHER_SOURCE,
    )
    _, reader_secret = auth.create_principal(
        role="reader",
        principal_id="test.reader",
        allowed_purposes=["test read"],
        allowed_scopes=["scope:workspace.*"],
    )
    _, admin_secret = auth.create_principal(
        role="admin",
        principal_id="test.admin",
        allowed_purposes=["administration"],
        allowed_scopes=["*"],
    )
    return {
        "source": {"Authorization": f"Bearer {source_secret}"},
        "other": {"Authorization": f"Bearer {other_secret}"},
        "reader": {"Authorization": f"Bearer {reader_secret}"},
        "admin": {"Authorization": f"Bearer {admin_secret}"},
    }


def _event(**overrides: Any) -> dict[str, Any]:
    body = {
        "schema": "activity-event/1",
        "event_id": "evt-001",
        "source_id": SOURCE_ID,
        "grant_id": GRANT_ID,
        "kind": "window-foreground",
        "app": "SynthBrowser",
        "window_title": "SYNTHETIC lecture page",
        "uri": "https://lecture.example.test/watch?v=synth1",
        "foreground": True,
        "payload": {},
        "synthetic": True,
    }
    body.update(overrides)
    return body


@pytest.fixture
def env(tmp_path: Path):
    root = tmp_path / "rt"
    headers = _bootstrap(root)
    grants = GrantStore(root / "activity" / "grants.json")
    grants.add(SourceGrant(
        grant_id=GRANT_ID,
        source_id=SOURCE_ID,
        principal="test.activity-producer",
        allow_apps=["SynthBrowser"],
        allow_domains=["lecture.example.test"],
    ))
    rt = build_runtime(RuntimeConfig.from_root(root, default_allow=True))
    app = create_app(runtime=rt)
    client = TestClient(app)
    yield {"runtime": rt, "app": app, "client": client, "root": root, "headers": headers}
    client.close()
    asyncio.run(close_runtime(rt))


def test_admitted_event_lands_in_inbox(env) -> None:
    resp = env["client"].post(PATH, json=_event(), headers=env["headers"]["source"])
    assert resp.status_code == 200
    receipt = resp.json()
    assert receipt == {
        "status": "admitted",
        "source_id": SOURCE_ID,
        "event_id": "evt-001",
        "admitted": True,
        "reason": "admitted",
    }
    lines = (env["root"] / "activity" / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    stored = ActivityEvent.model_validate(json.loads(lines[0]))
    assert stored.event_id == "evt-001"
    assert stored.source_id == SOURCE_ID


def test_missing_credential_is_401(env) -> None:
    resp = env["client"].post(PATH, json=_event())
    assert resp.status_code == 401


def test_reader_role_is_403(env) -> None:
    resp = env["client"].post(PATH, json=_event(), headers=env["headers"]["reader"])
    assert resp.status_code == 403


def test_caller_source_label_ignored_for_identity(env) -> None:
    # The pinned principal admits only its own source; a forged source_id
    # naming another source is denied even though the JSON validates.
    resp = env["client"].post(
        PATH, json=_event(source_id=OTHER_SOURCE), headers=env["headers"]["source"]
    )
    assert resp.status_code == 403
    assert resp.json()["reason"] == "denied:principal-source-mismatch"


def test_other_principals_grant_is_denied(env) -> None:
    # A valid source principal cannot post against another principal's grant.
    resp = env["client"].post(
        PATH,
        json=_event(source_id=OTHER_SOURCE),
        headers=env["headers"]["other"],
    )
    assert resp.status_code == 403
    assert resp.json()["reason"] == "denied:grant-principal-mismatch"


def test_unknown_grant_is_denied(env) -> None:
    resp = env["client"].post(
        PATH, json=_event(grant_id="grant-nope"), headers=env["headers"]["source"]
    )
    assert resp.status_code == 403
    assert resp.json()["reason"] == "denied:unknown-grant:grant-nope"


def test_grant_scope_enforced(env) -> None:
    resp = env["client"].post(
        PATH, json=_event(app="OtherApp"), headers=env["headers"]["source"]
    )
    assert resp.status_code == 403
    assert resp.json()["reason"] == "denied:app-not-permitted"


def test_schema_violation_is_400_receipt(env) -> None:
    bad = _event()
    del bad["kind"]
    resp = env["client"].post(PATH, json=bad, headers=env["headers"]["source"])
    assert resp.status_code == 400
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reason"].startswith("rejected:schema:")


def test_bad_json_is_400_receipt(env) -> None:
    resp = env["client"].post(
        PATH,
        content="{not-json",
        headers={**env["headers"]["source"], "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.json()["reason"] == "rejected:bad-json"


def test_admin_may_post_with_grant_check(env) -> None:
    resp = env["client"].post(PATH, json=_event(), headers=env["headers"]["admin"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "admitted"
    denied = env["client"].post(
        PATH, json=_event(app="OtherApp"), headers=env["headers"]["admin"]
    )
    assert denied.status_code == 403
    assert denied.json()["reason"] == "denied:app-not-permitted"


def test_revoked_grant_is_denied(env) -> None:
    grants = GrantStore(env["root"] / "activity" / "grants.json")
    assert grants.revoke(GRANT_ID, "synthetic test revoke") is True
    resp = env["client"].post(PATH, json=_event(), headers=env["headers"]["source"])
    assert resp.status_code == 403
    assert resp.json()["reason"] == f"denied:grant-revoked:{GRANT_ID}"


def test_legacy_path_without_runtime_is_501() -> None:
    app = create_app()
    client = TestClient(app)
    try:
        resp = client.post(PATH, json=_event())
        assert resp.status_code == 501
    finally:
        client.close()
