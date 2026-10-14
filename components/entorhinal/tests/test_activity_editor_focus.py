"""Focused tests for the editor focus producer (synthetic only).

Covers ``src/entorhinal/activity/producers/editor_focus.py`` and its parity
with the ``editor-extension`` v0.1.0 rules: workspace scoping, suppression,
payload builders, heartbeat bounds, loopback gating, sender behavior, and
an end-to-end admitted roundtrip through the reference
``LocalActivityReceiver`` + ``GrantStore`` + ``InboxFileSink``.

No live editor, no real files, no network beyond loopback. Fixture paths
are synthetic (``/synth/...``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from entorhinal.activity.classify import LocalActivityClassifier
from entorhinal.activity.events import (
    ActivityEvent,
    ActivityKind,
    canonical_content_identity,
)
from entorhinal.activity.grants import GrantStore, SourceGrant
from entorhinal.activity.producers import browser_media
from entorhinal.activity.producers.browser_sender import (
    InboxFileSink,
    LocalActivityReceiver,
)
from entorhinal.activity.producers.editor_focus import (
    EDITOR_CLOCK_DOMAIN,
    EDITOR_SOURCE_ID,
    EditorMetadataSender,
    build_editor_event_dict,
    build_editor_heartbeat_dict,
    build_editor_payload,
    clamp_heartbeat_cadence,
    file_uri_for,
    filter_editor_event,
    is_loopback_receiver_url,
    normalize_language,
    normalize_roots,
    workspace_rel,
)

ROOTS = ["/synth/work/repo"]
GRANT_ID = "grant-editor-01"
TOKEN = "synth-editor-token-0123456789"


def _grant(**overrides) -> SourceGrant:
    base = dict(
        grant_id=GRANT_ID,
        source_id=EDITOR_SOURCE_ID,
        principal="synth-user",
        allow_apps=["VSCode"],
        allow_domains=[],
        allow_kinds=[
            ActivityKind.WINDOW_FOREGROUND,
            ActivityKind.WINDOW_BACKGROUND,
            ActivityKind.INPUT_MARKER,
            ActivityKind.HEARTBEAT,
        ],
    )
    base.update(overrides)
    return SourceGrant(**base)


# -- workspace allowlist ----------------------------------------------------


def test_normalize_roots_drops_relative_and_junk() -> None:
    assert normalize_roots(["/synth/work/repo", "relative/path", "", None, 42]) == [
        "/synth/work/repo"
    ]
    assert normalize_roots("not-a-list") == []
    assert normalize_roots(None) == []


def test_normalize_roots_dedupes_and_trims() -> None:
    assert normalize_roots(["/synth/a/", "  /synth/a ", "/synth/a/."]) == ["/synth/a"]


def test_workspace_rel_matches_inside_root() -> None:
    assert workspace_rel("/synth/work/repo/src/main.py", ROOTS) == (
        "/synth/work/repo",
        "src/main.py",
    )


def test_workspace_rel_rejects_sibling_prefix() -> None:
    # Segment-boundary aware: /synth/work/repo-other is NOT inside /synth/work/repo.
    assert workspace_rel("/synth/work/repo-other/main.py", ROOTS) is None


def test_workspace_rel_rejects_root_itself_and_escapes() -> None:
    assert workspace_rel("/synth/work/repo", ROOTS) is None
    assert workspace_rel("/synth/work/repo/../secret.py", ROOTS) is None
    assert workspace_rel("relative/main.py", ROOTS) is None
    assert workspace_rel("", ROOTS) is None


def test_workspace_rel_windows_case_insensitive() -> None:
    roots = ["C:\\synth\\repo"]
    assert workspace_rel("c:/synth/repo/src/main.py", roots) == (
        "C:/synth/repo",
        "src/main.py",
    )


def test_filter_editor_event_suppression_reasons() -> None:
    assert filter_editor_event("/synth/work/repo/a.py", ROOTS) == (True, "allowed")
    assert filter_editor_event("/elsewhere/a.py", ROOTS) == (
        False,
        "suppressed:outside-workspace",
    )
    assert filter_editor_event("/synth/work/repo/a.py", []) == (
        False,
        "suppressed:no-workspace",
    )


# -- language / uri / cadence -----------------------------------------------


def test_normalize_language() -> None:
    assert normalize_language("Python") == "python"
    assert normalize_language("c++") == "c++"
    assert normalize_language("  TypeScript  ") == "typescript"
    assert normalize_language("not a language!") is None
    assert normalize_language("") is None
    assert normalize_language(None) is None
    assert normalize_language("x" * 33) is None


def test_file_uri_for_posix_and_windows() -> None:
    assert file_uri_for("/synth/work/repo/a b.py") == "file:///synth/work/repo/a%20b.py"
    assert file_uri_for("C:\\synth\\repo\\a.py") == "file:///C:/synth/repo/a.py"
    assert file_uri_for("relative/a.py") == ""
    assert file_uri_for("") == ""


def test_clamp_heartbeat_cadence_bounds() -> None:
    assert clamp_heartbeat_cadence(60) == 60
    assert clamp_heartbeat_cadence(1) == 10
    assert clamp_heartbeat_cadence(9999) == 300
    assert clamp_heartbeat_cadence("nope") == 60
    assert clamp_heartbeat_cadence(None) == 60


def test_loopback_gate_parity_with_browser_media() -> None:
    corpus = [
        "http://127.0.0.1:8765",
        "http://localhost:8765/",
        "http://[::1]:8765",
        "https://127.0.0.1:8443",
        "http://127.0.0.1",
        "http://example.test:8765",
        "http://192.168.1.2:8765",
        "http://user:pass@127.0.0.1:8765",
        "ws://127.0.0.1:8765",
        "not-a-url",
        "",
        "   ",
    ]
    for raw in corpus:
        assert is_loopback_receiver_url(raw) is browser_media.is_loopback_receiver_url(raw), raw
    assert is_loopback_receiver_url("http://127.0.0.1:8765") is True
    assert is_loopback_receiver_url("http://example.test:8765") is False


# -- payload / event builders ------------------------------------------------


def test_build_editor_payload_metadata_only() -> None:
    payload = build_editor_payload(
        workspace_name="repo", file_rel="src/main.py", language_id="Python",
        edit_events=7, focus_s=12.5, heartbeat_seq=3,
    )
    assert payload == {
        "workspace": "repo",
        "file_rel": "src/main.py",
        "language": "python",
        "edit_events": 7,
        "focus_s": 12.5,
        "heartbeat_seq": 3,
    }
    # Unknown fields are absent, never guessed.
    assert build_editor_payload(workspace_name="", file_rel="") == {}
    assert "edit_events" not in build_editor_payload(
        workspace_name="r", file_rel="f", edit_events=-1
    )
    assert "focus_s" not in build_editor_payload(
        workspace_name="r", file_rel="f", focus_s=float("nan")
    )


def test_build_editor_event_dict_validates() -> None:
    blob = build_editor_event_dict(
        event_id="ed-synth-1",
        kind=ActivityKind.WINDOW_FOREGROUND,
        observed_at=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
        uri="file:///synth/work/repo/src/main.py",
        window_title="src/main.py — repo",
        payload=build_editor_payload(
            workspace_name="repo", file_rel="src/main.py", language_id="python"
        ),
        grant_id=GRANT_ID,
        source_seq=1,
    )
    assert blob["schema"] == "activity-event/1"
    assert blob["source_id"] == EDITOR_SOURCE_ID
    assert blob["clock_domain"] == EDITOR_CLOCK_DOMAIN
    assert blob["app"] == "VSCode"
    event = ActivityEvent.model_validate(blob)  # must re-validate cleanly
    assert event.idempotency_key() == f"{EDITOR_SOURCE_ID}\x00ed-synth-1"


def test_build_editor_event_dict_rejects_bad_source() -> None:
    with pytest.raises(Exception):
        build_editor_event_dict(
            event_id="ed-synth-bad",
            kind=ActivityKind.WINDOW_FOREGROUND,
            observed_at=None,
            uri="file:///synth/work/repo/a.py",
            window_title=None,
            payload={},
            grant_id=GRANT_ID,
            source_id="somewhere.else",
        )


def test_build_editor_heartbeat_dict() -> None:
    blob = build_editor_heartbeat_dict(event_id="ed-hb-1", observed_at=None, grant_id=GRANT_ID)
    event = ActivityEvent.model_validate(blob)
    assert event.kind == ActivityKind.HEARTBEAT
    assert event.payload["sender"] == "editor-extension"
    assert event.uri in (None, "")


def test_editor_file_identity_is_code_key() -> None:
    blob = build_editor_event_dict(
        event_id="ed-synth-2",
        kind=ActivityKind.WINDOW_FOREGROUND,
        observed_at=None,
        uri="file:///synth/work/repo/src/main.py",
        window_title="src/main.py — repo",
        payload=build_editor_payload(workspace_name="repo", file_rel="src/main.py"),
        grant_id=GRANT_ID,
    )
    identity = ActivityEvent.model_validate(blob).content_identity()
    assert identity is not None
    assert identity.kind == "code"
    assert identity.key == "file:/synth/work/repo/src/main.py"
    # Unknown identity stays unknown: unparseable URI yields None, never a guess.
    assert canonical_content_identity("not a uri at all", None, {}) is None


def test_editor_observation_votes_coding() -> None:
    """The existing classifier already votes coding on app + code extension."""
    classifier = LocalActivityClassifier()
    blob = build_editor_event_dict(
        event_id="ed-synth-3",
        kind=ActivityKind.WINDOW_FOREGROUND,
        observed_at=None,
        uri="file:///synth/work/repo/src/main.py",
        window_title="src/main.py — repo",
        payload=build_editor_payload(workspace_name="repo", file_rel="src/main.py"),
        grant_id=GRANT_ID,
    )
    event = ActivityEvent.model_validate(blob)
    from entorhinal.activity.sessions import ObservedSpan

    span = ObservedSpan(
        span_id="span-synth-ed-1",
        start=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
        end=datetime(2026, 10, 11, 12, 5, tzinfo=timezone.utc),
        active_seconds=300.0,
        elapsed_seconds=300.0,
        kind=event.kind.value,
        app=event.app,
        uri=event.uri,
        title_snapshot=event.window_title,
        content_identity=event.content_identity(),
        event_ids=[event.event_id],
    )
    label = classifier.classify_span(span)
    assert label.activity == "coding"
    assert label.confidence >= 0.5


# -- sender ------------------------------------------------------------------


def test_sender_requires_token_and_loopback() -> None:
    with pytest.raises(ValueError):
        EditorMetadataSender("http://127.0.0.1:8765", "", GRANT_ID, ROOTS)
    with pytest.raises(ValueError):
        EditorMetadataSender("http://example.test:8765", TOKEN, GRANT_ID, ROOTS)
    with pytest.raises(ValueError):
        EditorMetadataSender("http://192.168.1.2:8765", TOKEN, GRANT_ID, ROOTS)


def test_sender_default_disabled_drops() -> None:
    sender = EditorMetadataSender("http://127.0.0.1:8765", TOKEN, GRANT_ID, ROOTS)
    try:
        assert sender.enabled is False
        receipt = sender.send_focus("ed-drop-1", "/synth/work/repo/a.py", "repo")
        assert receipt.status == "dropped"
        assert receipt.admitted is False
        assert receipt.reason == "sender-disabled"
        assert sender.dropped == ["ed-drop-1:sender-disabled"]
    finally:
        sender.close()


def test_sender_suppresses_outside_workspace() -> None:
    sender = EditorMetadataSender(
        "http://127.0.0.1:8765", TOKEN, GRANT_ID, ROOTS, enabled=True
    )
    try:
        receipt = sender.send_focus("ed-sup-1", "/elsewhere/a.py", "repo")
        assert receipt.status == "dropped"
        assert receipt.reason == "suppressed:outside-workspace"
        heartbeat = sender.send_heartbeat("ed-hb-sup")
        # Heartbeat needs configured roots, not a file: admitted-path attempted.
        assert heartbeat.event_id == "ed-hb-sup"
    finally:
        sender.close()


def test_sender_heartbeat_without_roots_suppressed() -> None:
    sender = EditorMetadataSender("http://127.0.0.1:8765", TOKEN, GRANT_ID, [])
    try:
        sender.enable()
        receipt = sender.send_heartbeat("ed-hb-noroot")
        assert receipt.status == "dropped"
        assert receipt.reason == "suppressed:no-workspace"
    finally:
        sender.close()


def test_focus_roundtrip_through_reference_receiver(tmp_path) -> None:
    grants = GrantStore()
    grants.add(_grant())
    inbox = tmp_path / "activity-inbox.jsonl"
    receiver = LocalActivityReceiver(TOKEN, grants, InboxFileSink(inbox))
    receiver.start()
    try:
        with EditorMetadataSender(
            receiver.url, TOKEN, GRANT_ID, ROOTS, enabled=True
        ) as sender:
            receipt = sender.send_focus(
                "ed-e2e-1",
                "/synth/work/repo/src/main.py",
                "repo",
                language_id="python",
                observed_at=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
            )
        assert receipt.status == "admitted"
        assert receipt.admitted is True
        assert receipt.source_id == EDITOR_SOURCE_ID
        assert receipt.event_id == "ed-e2e-1"
    finally:
        receiver.stop()
    lines = inbox.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = ActivityEvent.model_validate(json.loads(lines[0]))
    assert event.source_id == EDITOR_SOURCE_ID
    assert event.grant_id == GRANT_ID
    assert event.kind == ActivityKind.WINDOW_FOREGROUND
    assert event.payload["file_rel"] == "src/main.py"
    assert event.payload["language"] == "python"
    assert event.content_identity() is not None
    assert event.content_identity().kind == "code"


def test_edit_marker_roundtrip_counts_only(tmp_path) -> None:
    grants = GrantStore()
    grants.add(_grant())
    inbox = tmp_path / "activity-inbox.jsonl"
    receiver = LocalActivityReceiver(TOKEN, grants, InboxFileSink(inbox))
    receiver.start()
    try:
        with EditorMetadataSender(
            receiver.url, TOKEN, GRANT_ID, ROOTS, enabled=True
        ) as sender:
            receipt = sender.send_edit_marker(
                "ed-e2e-2", "/synth/work/repo/src/main.py", "repo", 9,
                language_id="python",
            )
        assert receipt.admitted is True
    finally:
        receiver.stop()
    event = ActivityEvent.model_validate(
        json.loads(inbox.read_text(encoding="utf-8").strip())
    )
    assert event.kind == ActivityKind.INPUT_MARKER
    assert event.payload["edit_events"] == 9
    assert "content" not in json.dumps(event.payload)
    assert "selection" not in json.dumps(event.payload)


def test_grant_denial_paths_are_attributable(tmp_path) -> None:
    grants = GrantStore()
    grants.add(_grant())
    grants.revoke(GRANT_ID, "synth test revoke")
    inbox = tmp_path / "activity-inbox.jsonl"
    receiver = LocalActivityReceiver(TOKEN, grants, InboxFileSink(inbox))
    receiver.start()
    try:
        with EditorMetadataSender(
            receiver.url, TOKEN, GRANT_ID, ROOTS, enabled=True
        ) as sender:
            receipt = sender.send_focus("ed-deny-1", "/synth/work/repo/a.py", "repo")
        assert receipt.admitted is False
        assert receipt.reason == f"denied:grant-revoked:{GRANT_ID}"
    finally:
        receiver.stop()
    assert not inbox.exists()


def test_kind_outside_grant_denied(tmp_path) -> None:
    grants = GrantStore()
    grants.add(_grant(allow_kinds=[ActivityKind.WINDOW_FOREGROUND]))
    inbox = tmp_path / "activity-inbox.jsonl"
    receiver = LocalActivityReceiver(TOKEN, grants, InboxFileSink(inbox))
    receiver.start()
    try:
        with EditorMetadataSender(
            receiver.url, TOKEN, GRANT_ID, ROOTS, enabled=True
        ) as sender:
            receipt = sender.send_edit_marker(
                "ed-deny-2", "/synth/work/repo/a.py", "repo", 3
            )
        assert receipt.admitted is False
        assert receipt.reason == "denied:kind-not-permitted:input-marker"
    finally:
        receiver.stop()


def test_bad_token_denied(tmp_path) -> None:
    grants = GrantStore()
    grants.add(_grant())
    inbox = tmp_path / "activity-inbox.jsonl"
    receiver = LocalActivityReceiver(TOKEN, grants, InboxFileSink(inbox))
    receiver.start()
    try:
        with EditorMetadataSender(
            receiver.url, "wrong-token", GRANT_ID, ROOTS, enabled=True
        ) as sender:
            receipt = sender.send_focus("ed-deny-3", "/synth/work/repo/a.py", "repo")
        assert receipt.admitted is False
        assert receipt.reason == "denied:bad-or-missing-token"
    finally:
        receiver.stop()


def test_retry_same_event_id_hashes_equal() -> None:
    """content_hash excludes received_at: retries with the same event_id agree."""
    first = ActivityEvent.model_validate(
        build_editor_event_dict(
            event_id="ed-retry-1",
            kind=ActivityKind.WINDOW_FOREGROUND,
            observed_at=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
            uri="file:///synth/work/repo/a.py",
            window_title="a.py — repo",
            payload=build_editor_payload(workspace_name="repo", file_rel="a.py"),
            grant_id=GRANT_ID,
            source_seq=4,
        )
    )
    # Simulate a retry arriving later: identical content, new received_at.
    blob = first.to_json_dict()
    blob["received_at"] = "2026-10-11T12:05:00+00:00"
    retry = ActivityEvent.model_validate(blob)
    assert retry.content_hash() == first.content_hash()
    assert retry.idempotency_key() == first.idempotency_key()
