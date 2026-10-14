"""Producers: inbox tailer durability + browser sender/receiver (synthetic only)."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from entorhinal.activity.events import ActivityKind
from entorhinal.activity.grants import GrantStore
from entorhinal.activity.producers.browser_sender import (
    BrowserMetadataSender,
    InboxFileSink,
    LocalActivityReceiver,
    filter_dom_event,
    scrub_url,
)
from entorhinal.activity.producers.inbox import (
    ActivityInboxAdapter,
    ActivityInboxConfig,
    ActivityInboxState,
    register_activity_adapters,
)

from tests.activity_fixtures import (
    SYNTH_FILE,
    SYNTH_GRANT_BROWSER,
    SYNTH_GRANT_FILE,
    T0,
    grant_store,
    make_event,
    media_payload,
)


def _write_inbox(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def _config(tmp_path: Path, **overrides) -> ActivityInboxConfig:
    base = dict(
        inbox_path=tmp_path / "inbox.jsonl",
        cursor_path=tmp_path / "cursor.txt",
        spool_path=tmp_path / "spool.jsonl",
        error_log_path=tmp_path / "errors.jsonl",
        grants_path=tmp_path / "grants.json",
    )
    base.update(overrides)
    return ActivityInboxConfig(**base)


def test_register_activity_adapters() -> None:
    keys = register_activity_adapters()
    assert "activity-inbox" in keys
    from entorhinal.runtime.sources import registered_adapters

    assert "activity-inbox" in registered_adapters()


@pytest.mark.asyncio
async def test_inbox_admits_from_boundary_and_spools(tmp_path: Path) -> None:
    grants = grant_store()
    grants._path = tmp_path / "grants.json"
    grants.save()
    inbox = tmp_path / "inbox.jsonl"
    event = make_event(
        "i1", T0, ActivityKind.MEDIA_FOREGROUND, "Chromium", "SYNTH Lecture 1",
        "https://video.example.test/watch?v=SYNTH-1",
        media_payload("SYNTH-1", 0.0, "playing"),
        source_id=SYNTH_FILE, grant_id=SYNTH_GRANT_FILE,
    )
    _write_inbox(inbox, ["pre-boundary-noise\n", json.dumps(event.to_json_dict()) + "\n"])
    boundary = len("pre-boundary-noise\n")
    adapter = ActivityInboxAdapter(_config(tmp_path, activation_boundary_offset=boundary))
    await adapter.start()
    try:
        assert adapter.inbox_state == ActivityInboxState.CONNECTED_ACTIVE
        signals = await adapter.poll_signals()
        assert len(signals) == 1
        assert signals[0].signal_id == "i1"
        assert (tmp_path / "spool.jsonl").exists()
        health = adapter.health_check()
        assert health["cursor_offset"] == inbox.stat().st_size
        assert health["denied_count"] == 0
    finally:
        await adapter.stop()
    assert adapter.inbox_state == ActivityInboxState.STOPPED


@pytest.mark.asyncio
async def test_inbox_denies_grant_violations_and_malformed(tmp_path: Path) -> None:
    grants = grant_store()
    grants._path = tmp_path / "grants.json"
    grants.save()
    inbox = tmp_path / "inbox.jsonl"
    good = make_event("good", T0, source_id=SYNTH_FILE, grant_id=SYNTH_GRANT_FILE)
    denied = make_event("denied", T0, source_id=SYNTH_FILE, grant_id="grant-unknown")
    lines = [
        json.dumps(good.to_json_dict()) + "\n",
        json.dumps(denied.to_json_dict()) + "\n",
        "not json\n",
        json.dumps({"schema": "activity-event/1"}) + "\n",
    ]
    _write_inbox(inbox, lines)
    adapter = ActivityInboxAdapter(_config(tmp_path))
    await adapter.start()
    try:
        signals = await adapter.poll_signals()
        assert [s.signal_id for s in signals] == ["good"]
        health = adapter.health_check()
        assert health["denied_count"] == 1
        assert health["malformed_count"] == 2
        assert (tmp_path / "errors.jsonl").exists()
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_inbox_restart_resumes_without_loss_or_dup(tmp_path: Path) -> None:
    grants = grant_store()
    grants._path = tmp_path / "grants.json"
    grants.save()
    inbox = tmp_path / "inbox.jsonl"
    first = make_event("r1", T0, source_id=SYNTH_FILE, grant_id=SYNTH_GRANT_FILE)
    _write_inbox(inbox, [json.dumps(first.to_json_dict()) + "\n"])
    config = _config(tmp_path)
    adapter = ActivityInboxAdapter(config)
    await adapter.start()
    assert [s.signal_id for s in await adapter.poll_signals()] == ["r1"]
    await adapter.stop()

    second = make_event("r2", T0 + timedelta(minutes=1),
                        source_id=SYNTH_FILE, grant_id=SYNTH_GRANT_FILE)
    with open(inbox, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(second.to_json_dict()) + "\n")
    adapter2 = ActivityInboxAdapter(config)
    await adapter2.start()
    try:
        assert [s.signal_id for s in await adapter2.poll_signals()] == ["r2"]
        replayed = adapter2.spool_replay()
        assert [e.event_id for e in replayed] == ["r1", "r2"]
    finally:
        await adapter2.stop()


@pytest.mark.asyncio
async def test_inbox_truncation_gap_and_offline(tmp_path: Path) -> None:
    grants = grant_store()
    grants._path = tmp_path / "grants.json"
    grants.save()
    inbox = tmp_path / "inbox.jsonl"
    event = make_event("t1", T0, source_id=SYNTH_FILE, grant_id=SYNTH_GRANT_FILE)
    _write_inbox(inbox, [json.dumps(event.to_json_dict()) + "\n"])
    adapter = ActivityInboxAdapter(_config(tmp_path))
    await adapter.start()
    try:
        assert await adapter.poll_signals()
        inbox.write_text("", encoding="utf-8")  # truncate/rotate
        await adapter.poll_once()
        assert adapter.inbox_state == ActivityInboxState.GAP
        assert adapter.health_check()["gap_count"] == 1
        inbox.unlink()
        await adapter.poll_once()
        assert adapter.inbox_state == ActivityInboxState.OFFLINE
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_inbox_backpressure_on_spool_budget(tmp_path: Path) -> None:
    grants = grant_store()
    grants._path = tmp_path / "grants.json"
    grants.save()
    inbox = tmp_path / "inbox.jsonl"
    lines = []
    for index in range(5):
        event = make_event(f"b{index}", T0 + timedelta(seconds=index),
                            source_id=SYNTH_FILE, grant_id=SYNTH_GRANT_FILE)
        lines.append(json.dumps(event.to_json_dict()) + "\n")
    _write_inbox(inbox, lines)
    adapter = ActivityInboxAdapter(_config(tmp_path, spool_max_bytes=300))
    await adapter.start()
    try:
        assert adapter.inbox_state == ActivityInboxState.BACKPRESSURE
        assert adapter.health_check()["backpressure"] is True
    finally:
        await adapter.stop()


def test_scrub_url_strips_credentials() -> None:
    cleaned = scrub_url("https://video.example.test/watch?v=SYNTH-1&token=abc&password=x")
    assert "token" not in cleaned and "password" not in cleaned
    assert "v=SYNTH-1" in cleaned
    assert scrub_url("not a url") == ""


def test_filter_dom_event_suppression() -> None:
    allowed, _ = filter_dom_event(
        {"url": "https://video.example.test/watch?v=SYNTH-1"}, ["video.example.test"])
    assert allowed is True
    assert filter_dom_event(
        {"url": "https://video.example.test/x", "is_incognito": True},
        ["video.example.test"])[0] is False
    assert filter_dom_event(
        {"url": "https://other.example.test/x"}, ["video.example.test"])[0] is False
    assert filter_dom_event(
        {"url": "https://video.example.test/x", "element_tag": "input",
         "element_attributes": {"type": "password"}}, ["video.example.test"])[0] is False


def test_sender_requires_enable_and_token() -> None:
    with pytest.raises(ValueError):
        BrowserMetadataSender("http://127.0.0.1:9", "", "g", [])
    sender = BrowserMetadataSender(
        "http://127.0.0.1:9", "tok", SYNTH_GRANT_BROWSER, ["video.example.test"])
    receipt = sender.send_navigation("e1", "https://video.example.test/x", "SYNTH")
    assert receipt.admitted is False and receipt.reason == "sender-disabled"


def test_receiver_auth_grant_and_sink_roundtrip(tmp_path: Path) -> None:
    grants = grant_store()
    received: list = []
    receiver = LocalActivityReceiver("synth-token-01", grants, received.append)
    receiver.start()
    try:
        sender = BrowserMetadataSender(
            receiver.url, "synth-token-01", SYNTH_GRANT_BROWSER,
            ["video.example.test"], enabled=True)
        ok = sender.send_media_state(
            "m1", "https://video.example.test/watch?v=SYNTH-1", "SYNTH Lecture 1",
            "SYNTH-1", 5.0, 3600.0, "playing", observed_at=T0)
        assert ok.admitted is True and ok.event_id == "m1"
        assert len(received) == 1 and received[0].event_id == "m1"

        blocked = sender.send_navigation(
            "m2", "https://other.example.test/x", "SYNTH other", observed_at=T0)
        assert blocked.admitted is False  # client-side domain suppression

        bad_sender = BrowserMetadataSender(
            receiver.url, "wrong-token", SYNTH_GRANT_BROWSER,
            ["video.example.test"], enabled=True)
        denied = bad_sender.send_navigation(
            "m3", "https://video.example.test/x", "SYNTH", observed_at=T0)
        assert denied.admitted is False and "token" in (denied.reason or "")

        revoked_grants = grant_store()
        revoked_grants.revoke(SYNTH_GRANT_BROWSER, "test")
        receiver2 = LocalActivityReceiver("synth-token-01", revoked_grants, received.append)
        receiver2.start()
        try:
            sender2 = BrowserMetadataSender(
                receiver2.url, "synth-token-01", SYNTH_GRANT_BROWSER,
                ["video.example.test"], enabled=True)
            grant_denied = sender2.send_navigation(
                "m4", "https://video.example.test/x", "SYNTH", observed_at=T0)
            assert grant_denied.admitted is False and "revoked" in (grant_denied.reason or "")
        finally:
            receiver2.stop()
    finally:
        receiver.stop()


def test_receiver_rejects_loopback_violation_and_bad_json() -> None:
    with pytest.raises(ValueError):
        LocalActivityReceiver("t", grant_store(), lambda e: None, host="0.0.0.0")
    import httpx

    receiver = LocalActivityReceiver("t", grant_store(), lambda e: None)
    receiver.start()
    try:
        # Loopback: bypass the sandbox egress proxy like the sender does.
        with httpx.Client(trust_env=False, timeout=5.0) as client:
            response = client.post(
                receiver.url + "/activity/v1/events", content="nope",
                headers={"Authorization": "Bearer t"})
            assert response.status_code == 400
            missing = client.post(receiver.url + "/activity/v1/events", json={})
            assert missing.status_code == 401
    finally:
        receiver.stop()


def test_inbox_file_sink_appends(tmp_path: Path) -> None:
    sink = InboxFileSink(tmp_path / "inbox.jsonl")
    event = make_event("s1", T0)
    sink(event)
    lines = (tmp_path / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["event_id"] == "s1"
