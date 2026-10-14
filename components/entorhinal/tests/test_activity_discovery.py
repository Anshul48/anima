"""Discovery: proposed connections with provenance, accept/reject (synthetic only)."""

from __future__ import annotations

from datetime import timedelta

from entorhinal.activity.classify import LocalActivityClassifier
from entorhinal.activity.discovery import ConnectionStatus, DiscoveryEngine
from entorhinal.activity.events import ActivityKind
from entorhinal.activity.sessions import SessionBuilder

from tests.activity_fixtures import T0, make_event, media_payload
from tests.test_activity_sessions import lecture_code_lecture_events


def _derivatives(events):
    builder = SessionBuilder()
    builder.ingest(events)
    spans, sessions = builder.spans(), builder.sessions()
    classifier = LocalActivityClassifier()
    labels = [classifier.classify_session(s, spans) for s in sessions]
    return spans, sessions, labels


def test_interrupted_by_discovered_for_lecture_case() -> None:
    spans, sessions, labels = _derivatives(lecture_code_lecture_events())
    engine = DiscoveryEngine()
    connections, _ = engine.discover(sessions, spans, labels)
    kinds = [c.kind.value for c in connections]
    assert "interrupted-by" in kinds
    link = next(c for c in connections if c.kind.value == "interrupted-by")
    assert link.evidence and link.provenance.get("rule") == "span-interleave"
    assert link.status == ConnectionStatus.PROPOSED


def test_bare_adjacency_never_proposes() -> None:
    events = [
        make_event("a1", T0, ActivityKind.WINDOW_FOREGROUND,
                   "SynthAppA", "SYNTH alpha", None, {}),
        make_event("b1", T0 + timedelta(minutes=1), ActivityKind.WINDOW_FOREGROUND,
                   "SynthAppB", "SYNTH beta", None, {}),
    ]
    spans, sessions, labels = _derivatives(events)
    assert len(sessions) == 2
    connections, considered = DiscoveryEngine().discover(sessions, spans, labels)
    assert connections == []
    assert len(considered) == 1
    assert "bare time adjacency" in considered[0].reason


def test_same_project_from_shared_repo() -> None:
    events = [
        make_event("a1", T0, ActivityKind.WINDOW_FOREGROUND, "Code",
                   "SYNTH a.py", "file:///synth/proj/a.py", {}),
        make_event("b1", T0 + timedelta(minutes=30), ActivityKind.WINDOW_FOREGROUND,
                   "Code", "SYNTH b.py", "file:///synth/proj/b.py", {}),
    ]
    spans, sessions, labels = _derivatives(events)
    assert len(sessions) == 2
    connections, _ = DiscoveryEngine().discover(sessions, spans, labels)
    kinds = [c.kind.value for c in connections]
    assert "same-project" in kinds


def test_same_content_for_restart_and_resume_of_for_considered() -> None:
    # Restart: same media from ~0 after progress -> same-content, not resume-of.
    restart_events = [
        make_event(
            "l1", T0, ActivityKind.MEDIA_FOREGROUND, "Chromium", "SYNTH Lecture 7",
            "https://video.example.test/watch?v=SYNTH-7",
            media_payload("SYNTH-7", 1500.0, "playing"),
        ),
        make_event("c1", T0 + timedelta(minutes=10), ActivityKind.WINDOW_FOREGROUND,
                   "Code", "SYNTH main.py", "file:///synth/proj/main.py", {}),
        make_event(
            "l2", T0 + timedelta(minutes=20), ActivityKind.MEDIA_FOREGROUND,
            "Chromium", "SYNTH Lecture 7",
            "https://video.example.test/watch?v=SYNTH-7",
            media_payload("SYNTH-7", 5.0, "playing"),
        ),
    ]
    spans, sessions, labels = _derivatives(restart_events)
    connections, _ = DiscoveryEngine().discover(sessions, spans, labels)
    kinds = [c.kind.value for c in connections]
    assert "same-content" in kinds
    assert "resume-of" not in kinds


def test_accept_reject_decisions_stick() -> None:
    spans, sessions, labels = _derivatives(lecture_code_lecture_events())
    engine = DiscoveryEngine()
    connections, _ = engine.discover(sessions, spans, labels)
    assert connections
    target = connections[0].connection_id
    accepted = engine.decide(target, True, actor="synth-user")
    assert accepted.status == ConnectionStatus.ACCEPTED
    assert accepted.decided_by == "synth-user"
    again, _ = engine.discover(sessions, spans, labels)
    assert next(c for c in again if c.connection_id == target).status == ConnectionStatus.ACCEPTED

    rejected = engine.decide(target, False, actor="synth-user")
    assert rejected.status == ConnectionStatus.REJECTED
    rediscovered, considered = engine.discover(sessions, spans, labels)
    assert target not in [c.connection_id for c in rediscovered]
    assert any("user rejected" in c.reason for c in considered)


def test_connection_ids_deterministic() -> None:
    spans, sessions, labels = _derivatives(lecture_code_lecture_events())
    first, _ = DiscoveryEngine().discover(sessions, spans, labels)
    second, _ = DiscoveryEngine().discover(sessions, spans, labels)
    assert [c.connection_id for c in first] == [c.connection_id for c in second]
    assert all(c.connection_id.startswith("actconn_") for c in first)
