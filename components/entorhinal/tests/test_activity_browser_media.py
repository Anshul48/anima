"""Focused tests for the browser media-producer contract (NEW synthetic only).

Covers `entorhinal.activity.producers.browser_media` (pure helpers mirroring
the extension v0.2.0 content script) plus one end-to-end media-payload
roundtrip through the existing `BrowserMetadataSender` +
`LocalActivityReceiver` + `GrantStore` reference path. All fixtures are NEW
synthetic events on `.example.test` hosts; nothing reads user stores and no
live browser is involved.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from entorhinal.activity.events import (
    ActivityEvent,
    ActivityKind,
    canonical_content_identity,
)
from entorhinal.activity.grants import GrantStore, SourceGrant
from entorhinal.activity.producers.browser_media import (
    BROWSER_SOURCE_ID,
    build_heartbeat_event_dict,
    build_media_marker_payload,
    build_media_payload,
    build_producer_event_dict,
    canonical_media_id,
    clamp_heartbeat_cadence,
    clamp_position,
    host_granted,
    is_loopback_receiver_url,
    normalize_hosts,
    normalize_media_state,
)
from entorhinal.activity.producers.browser_sender import (
    BrowserMetadataSender,
    InboxFileSink,
    LocalActivityReceiver,
)

SYNTH_GRANT = "grant-synth-browser-media-01"
T0 = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def _grant_store() -> GrantStore:
    store = GrantStore()
    store.add(SourceGrant(
        grant_id=SYNTH_GRANT, source_id=BROWSER_SOURCE_ID,
        principal="synth-tester", note="NEW synthetic test grant",
    ))
    return store


# -- canonical media identity: parity with events.canonical_media_id --------

IDENTITY_CASES = [
    ("https://video.example.test/watch?v=SYNTH-9", "video.example.test|v=SYNTH-9"),
    ("https://video.example.test/watch?lecture=L7&x=1", "video.example.test|lecture=L7"),
    ("https://lectures.example.test/play/xyz789", "lectures.example.test|play=xyz789"),
    ("https://lectures.example.test/video/abc123", "lectures.example.test|video=abc123"),
    ("https://lectures.example.test/embed/xyz?autoplay=1", "lectures.example.test|embed=xyz"),
    ("https://plain.example.test/about", None),
    ("https://plain.example.test/", None),
    ("not-a-url", None),
    ("", None),
]


@pytest.mark.parametrize("uri,expected", IDENTITY_CASES)
def test_canonical_media_id_cases(uri, expected):
    assert canonical_media_id(uri) == expected


def test_explicit_payload_id_takes_precedence_over_uri_parse():
    identity = canonical_content_identity(
        "https://video.example.test/watch?v=URI-ID",
        "SYNTH title",
        {"media_id": "EXPLICIT-ID", "media_host": "video.example.test"},
    )
    assert identity is not None
    assert identity.key == "media:video.example.test:EXPLICIT-ID"


def test_unknown_identity_is_none_never_guessed():
    assert canonical_content_identity(
        "https://plain.example.test/about", "SYNTH title", {}
    ) is None


# -- media state / position normalization ------------------------------------

STATE_CASES = [
    ("playing", "playing"), ("PAUSED", "paused"), ("Seeking", "seeking"),
    ("ended", "ended"), ("idle", "idle"), ("buffering", "idle"),
    ("", "idle"), (None, "idle"), (123, "idle"), (True, "idle"),
]


@pytest.mark.parametrize("raw,expected", STATE_CASES)
def test_normalize_media_state(raw, expected):
    assert normalize_media_state(raw) == expected


def test_clamp_position_valid_and_duration_cap():
    assert clamp_position(321.5, 1800.0) == 321.5
    assert clamp_position(0.0) == 0.0  # restart claim preserved exactly
    assert clamp_position(9999.0, 100.0) == 100.0  # capped, not dropped


def test_clamp_position_unknown_is_none_never_zero():
    assert clamp_position(-5.0) is None
    assert clamp_position(float("nan")) is None
    assert clamp_position(float("inf")) is None
    assert clamp_position("321") is None
    assert clamp_position(None) is None
    assert clamp_position(True) is None


def test_clamp_heartbeat_cadence_bounds():
    assert clamp_heartbeat_cadence(30) == 30
    assert clamp_heartbeat_cadence(1) == 10
    assert clamp_heartbeat_cadence(9999) == 300
    assert clamp_heartbeat_cadence("bogus") == 30
    assert clamp_heartbeat_cadence(None) == 30


# -- per-host grants ----------------------------------------------------------

def test_normalize_hosts_drops_wildcards_and_junk():
    assert normalize_hosts(["Lectures.Example.test ", "a.example.test", "a.example.test"]) == [
        "lectures.example.test", "a.example.test",
    ]
    assert normalize_hosts(["*", "*.example.test", "", "a/b", 42, None]) == []
    assert normalize_hosts("not-a-list") == []


def test_host_granted_exact_and_subdomain_only():
    grants = ["lectures.example.test"]
    assert host_granted("https://lectures.example.test/watch?v=1", grants)
    assert host_granted("https://cdn.lectures.example.test/x", grants)
    assert not host_granted("https://evillectures.example.test/x", grants)
    assert not host_granted("https://other.test/x", grants)
    assert not host_granted("https://lectures.example.test/x", [])
    assert not host_granted("not-a-url", grants)
    assert not host_granted("", grants)


def test_is_loopback_receiver_url():
    assert is_loopback_receiver_url("http://127.0.0.1:8765")
    assert is_loopback_receiver_url("http://localhost:8765/activity/v1/events")
    assert is_loopback_receiver_url("http://[::1]:8765")
    assert not is_loopback_receiver_url("http://192.168.1.2:8765")
    assert not is_loopback_receiver_url("https://example.test/")
    assert not is_loopback_receiver_url("http://user@127.0.0.1:8765")
    assert not is_loopback_receiver_url("file:///tmp/x")
    assert not is_loopback_receiver_url("")
    assert not is_loopback_receiver_url(None)  # type: ignore[arg-type]


# -- payload builders ----------------------------------------------------------

def test_build_media_payload_full_snapshot():
    payload = build_media_payload(
        media_id="video.example.test|v=SYNTH-9",
        media_host="video.example.test",
        media_state="playing",
        position_s=321.5,
        duration_s=1800.0,
        media_title="SYNTH Lecture 9",
        media_element="video",
        muted=False,
        playback_rate=1.5,
        audible=True,
        page_visible=True,
        heartbeat_seq=12,
    )
    assert payload == {
        "media_state": "playing",
        "media_id": "video.example.test|v=SYNTH-9",
        "media_host": "video.example.test",
        "media_title": "SYNTH Lecture 9",
        "media_duration_s": 1800.0,
        "media_position_s": 321.5,
        "media_element": "video",
        "media_muted": False,
        "media_rate": 1.5,
        "media_audible": True,
        "page_visible": True,
        "heartbeat_seq": 12,
    }


def test_build_media_payload_unknown_fields_absent():
    payload = build_media_payload(
        media_id="  ", media_host=None, media_state="buffering",
        position_s=float("nan"), duration_s=-3, media_element="canvas",
        playback_rate=99.0,
    )
    assert payload == {"media_state": "idle"}


def test_build_media_marker_payload_semantics():
    base = build_media_payload(
        media_id="m1", media_host="video.example.test", media_state="paused",
        position_s=100.0, duration_s=600.0,
    )
    pause = build_media_marker_payload(marker="pause", base=base)
    assert pause["marker"] == "pause"
    assert "seek_from_s" not in pause
    seeked = build_media_marker_payload(marker="seeked", base=base, seek_from_s=88.5)
    assert seeked["marker"] == "seeked"
    assert seeked["seek_from_s"] == 88.5
    with pytest.raises(ValueError):
        build_media_marker_payload(marker="rewind", base=base)


def test_built_event_dicts_validate_as_activity_event():
    payload = build_media_payload(
        media_id="m1", media_host="video.example.test", media_state="playing",
        position_s=10.0, duration_s=600.0,
    )
    blob = build_producer_event_dict(
        event_id="syn-media-0001", kind=ActivityKind.MEDIA_FOREGROUND,
        observed_at=T0, uri="https://video.example.test/watch?v=SYNTH-9",
        window_title="SYNTH Lecture 9", payload=payload, foreground=True,
        grant_id=SYNTH_GRANT, source_seq=7, synthetic=True,
        redaction_labels=["synthetic-fixture"],
    )
    event = ActivityEvent.model_validate(blob)
    assert blob["schema"] == "activity-event/1"
    assert event.idempotency_key() == f"{BROWSER_SOURCE_ID}\x00syn-media-0001"
    assert event.content_identity() is not None
    assert event.content_identity().key == "media:video.example.test:m1"
    # Retries hash equal: received_at is transport metadata, not content.
    twin = ActivityEvent.model_validate(dict(blob))
    assert twin.content_hash() == event.content_hash()


def test_built_heartbeat_event_dict():
    blob = build_heartbeat_event_dict(
        event_id="syn-hb-0001", observed_at=T0, grant_id=SYNTH_GRANT,
        synthetic=True,
    )
    event = ActivityEvent.model_validate(blob)
    assert event.kind == ActivityKind.HEARTBEAT
    assert event.payload["sender"] == "browser-extension"


def test_builder_rejects_non_activity_source_namespace():
    with pytest.raises(Exception):
        build_producer_event_dict(
            event_id="syn-bad-1", kind=ActivityKind.MEDIA_FOREGROUND,
            observed_at=T0, uri="https://video.example.test/", window_title="t",
            payload={}, source_id="evil.source.01", grant_id=SYNTH_GRANT,
        )


# -- end-to-end: media payload through sender + reference receiver -------------

def test_media_payload_roundtrip_through_reference_receiver(tmp_path: Path):
    inbox_path = tmp_path / "activity-inbox.jsonl"
    grants = _grant_store()
    receiver = LocalActivityReceiver(
        token="synth-token", grants=grants, sink=InboxFileSink(inbox_path),
    )
    receiver.start()
    try:
        with BrowserMetadataSender(
            receiver_url=receiver.url, token="synth-token",
            grant_id=SYNTH_GRANT, allow_domains=["video.example.test"],
            enabled=True,
        ) as sender:
            payload = build_media_payload(
                media_id="video.example.test|v=SYNTH-9",
                media_host="video.example.test",
                media_state="playing", position_s=321.5, duration_s=1800.0,
            )
            blob = build_producer_event_dict(
                event_id="syn-e2e-0001", kind=ActivityKind.MEDIA_FOREGROUND,
                observed_at=T0, uri="https://video.example.test/watch?v=SYNTH-9",
                window_title="SYNTH Lecture 9", payload=payload,
                grant_id=SYNTH_GRANT, source_seq=1, synthetic=True,
                redaction_labels=["synthetic-fixture"],
            )
            # The sender posts ActivityEvent-shaped traffic; post the exact
            # contract dict through the sender's transport to prove parity.
            event = ActivityEvent.model_validate(blob)
            receipt = sender._post(event)
            assert receipt.admitted is True
            assert receipt.event_id == "syn-e2e-0001"
    finally:
        receiver.stop()
    lines = inbox_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    stored = ActivityEvent.model_validate_json(lines[0])
    assert stored.payload["media_position_s"] == 321.5
    assert stored.content_identity().key == (
        "media:video.example.test:video.example.test|v=SYNTH-9"
    )


def test_reference_receiver_still_denies_unknown_grant(tmp_path: Path):
    inbox_path = tmp_path / "activity-inbox.jsonl"
    receiver = LocalActivityReceiver(
        token="synth-token", grants=_grant_store(),
        sink=InboxFileSink(inbox_path),
    )
    receiver.start()
    try:
        with BrowserMetadataSender(
            receiver_url=receiver.url, token="synth-token",
            grant_id="grant-unknown", allow_domains=["video.example.test"],
            enabled=True,
        ) as sender:
            receipt = sender.send_navigation(
                event_id="syn-deny-1",
                url="https://video.example.test/watch?v=SYNTH-9",
                title="SYNTH page",
            )
            assert receipt.admitted is False
            assert receipt.reason == "denied:unknown-grant:grant-unknown"
    finally:
        receiver.stop()
    assert not inbox_path.exists()
