"""Activity events + grants: schema, identity, opt-in enforcement (synthetic only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from entorhinal.activity.events import (
    ActivityEvent,
    ActivityKind,
    canonical_content_identity,
    canonical_media_id,
)
from entorhinal.activity.grants import GrantStore, SourceGrant
from entorhinal.schemas.models import RawSignalEvent

from tests.activity_fixtures import (
    SYNTH_BROWSER,
    SYNTH_GRANT_BROWSER,
    T0,
    grant_store,
    make_event,
    media_payload,
)


def test_event_schema_shape_and_namespace() -> None:
    event = make_event("e1", T0)
    blob = event.to_json_dict()
    assert blob["schema"] == "activity-event/1"
    assert blob["source_id"] == SYNTH_BROWSER
    with pytest.raises(ValidationError):
        make_event("e2", T0, source_id="entorhinal.dev-task.01")
    with pytest.raises(ValidationError):
        ActivityEvent.model_validate({**blob, "schema": "activity-event/9"})


def test_idempotency_key_and_content_hash_stable() -> None:
    first = make_event("e1", T0, source_seq=3)
    second = make_event("e1", T0, source_seq=3)
    assert first.idempotency_key() == second.idempotency_key()
    # received_at is transport metadata: retries hash equal.
    assert first.content_hash() == second.content_hash()
    changed = make_event("e1", T0 + timedelta(seconds=1), source_seq=3)
    assert changed.idempotency_key() == first.idempotency_key()
    assert changed.content_hash() != first.content_hash()


def test_observed_at_may_be_unknown_and_survives_bridge() -> None:
    event = make_event("e1", T0)
    event = event.model_copy(update={"observed_at": None})
    signal = event.to_raw_signal_event()
    assert signal.metadata["observed_at"] is None
    assert signal.signal_id == "e1"
    recovered = ActivityEvent.from_raw_signal_event(signal)
    assert recovered.observed_at is None
    assert recovered.event_id == "e1"


def test_raw_signal_bridge_roundtrip() -> None:
    event = make_event(
        "e9", T0, ActivityKind.MEDIA_FOREGROUND, "Chromium",
        "SYNTH Lecture 3", "https://video.example.test/watch?v=SYNTH-3",
        media_payload("SYNTH-3", 12.0, "playing"), source_seq=7,
    )
    signal = event.to_raw_signal_event()
    assert isinstance(signal, RawSignalEvent)
    assert signal.metadata["activity_schema"] == "activity-event/1"
    assert signal.metadata["source_sequence"] == 7
    recovered = ActivityEvent.from_raw_signal_event(signal)
    assert recovered.to_json_dict() == event.to_json_dict()


def test_evidence_record_reconstruction() -> None:
    from entorhinal.schemas.models import EvidenceRecord

    event = make_event("e5", T0)
    record = EvidenceRecord.create(
        source_type=event.to_raw_signal_event().source_type,
        app_identifier=event.app,
        sanitized_payload={
            "activity_event_id": event.event_id,
            "activity_event": event.to_json_dict(),
        },
        previous_record_hash="0" * 64,
        window_title=event.window_title,
        target_uri=event.uri,
    )
    recovered = ActivityEvent.from_evidence_record(record)
    assert recovered.event_id == "e5"
    with pytest.raises(ValueError):
        ActivityEvent.from_evidence_record(
            record.model_copy(update={"sanitized_payload": {}})
        )


def test_media_id_extraction_and_unknown_identity() -> None:
    assert canonical_media_id("https://video.example.test/watch?v=SYNTH-7") == (
        "video.example.test|v=SYNTH-7"
    )
    assert canonical_media_id("https://video.example.test/lecture/SYNTH-9") == (
        "video.example.test|lecture=SYNTH-9"
    )
    assert canonical_media_id("https://video.example.test/browse") is None
    assert canonical_media_id("not a url") is None
    unknown = canonical_content_identity("https://video.example.test/browse", "SYNTH browse")
    assert unknown is None
    explicit = canonical_content_identity(
        "https://video.example.test/browse", "SYNTH Lecture",
        {"media_id": "SYNTH-X", "media_host": "video.example.test"},
    )
    assert explicit is not None and explicit.key == "media:video.example.test:SYNTH-X"
    code = canonical_content_identity(None, "SYNTH main.py", {})
    assert code is None
    code_file = canonical_content_identity("file:///synth/proj/main.py", "SYNTH main.py", {})
    assert code_file is not None and code_file.kind == "code"


def test_grant_default_deny_unknown() -> None:
    store = GrantStore()
    event = make_event("e1", T0)
    allowed, reason = store.check(event)
    assert allowed is False and reason.startswith("denied:unknown-grant")


def test_grant_allow_revoke_expiry_and_scope() -> None:
    store = grant_store()
    event = make_event("e1", T0)
    assert store.check(event) == (True, "allowed")

    scoped = SourceGrant(
        grant_id="scoped", source_id=SYNTH_BROWSER, principal="t",
        allow_apps=["Chromium"], allow_domains=["video.example.test"],
        allow_kinds=[ActivityKind.MEDIA_FOREGROUND],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    store.add(scoped)
    ok_event = make_event(
        "ok", T0, ActivityKind.MEDIA_FOREGROUND, "Chromium",
        "SYNTH Lecture", "https://video.example.test/watch?v=SYNTH-1",
        grant_id="scoped",
    )
    assert store.check(ok_event)[0] is True
    wrong_app = ok_event.model_copy(update={"app": "Firefox"})
    assert store.check(wrong_app)[0] is False
    wrong_domain = ok_event.model_copy(update={"uri": "https://other.example.test/x"})
    assert store.check(wrong_domain)[0] is False
    wrong_kind = ok_event.model_copy(update={"kind": ActivityKind.WINDOW_FOREGROUND})
    assert store.check(wrong_kind)[0] is False

    expired = SourceGrant(
        grant_id="expired", source_id=SYNTH_BROWSER, principal="t",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    store.add(expired)
    assert store.check(make_event("x", T0, grant_id="expired"))[0] is False

    assert store.revoke(SYNTH_GRANT_BROWSER, "test") is True
    assert store.check(event)[0] is False
    assert store.revoke("nope") is False


def test_grant_source_mismatch_denied() -> None:
    store = grant_store()
    event = make_event("e1", T0, grant_id=SYNTH_GRANT_BROWSER)
    mismatched = event.model_copy(update={"source_id": "entorhinal.activity.file.01"})
    allowed, reason = store.check(mismatched)
    assert allowed is False and reason == "denied:grant-source-mismatch"


def test_grant_store_json_roundtrip(tmp_path) -> None:
    path = tmp_path / "grants.json"
    store = GrantStore(path)
    assert store.grants() == []
    store.add(SourceGrant(grant_id="g", source_id=SYNTH_BROWSER, principal="t"))
    reloaded = GrantStore(path)
    assert [g.grant_id for g in reloaded.grants()] == ["g"]
