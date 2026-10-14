"""Activity service: ingest, query, corrections, deletion, snapshots (synthetic only)."""

from __future__ import annotations

import json
from datetime import timedelta

from entorhinal.activity.classify import LabelCorrection
from entorhinal.activity.events import ActivityKind
from entorhinal.activity.service import ActivityService
from entorhinal.activity.sessions import ActivityCorrection
from entorhinal.activity.trace_port import (
    NullTraceOrganizer,
    RecordingTraceOrganizer,
    TraceEnrichment,
    validate_enrichment,
)

from tests.activity_fixtures import T0, grant_store, make_event, media_payload
from tests.test_activity_sessions import lecture_code_lecture_events


def _service() -> ActivityService:
    return ActivityService(grants=grant_store())


def test_ingest_idempotent_conflict_and_deny() -> None:
    service = _service()
    event = make_event("k1", T0)
    assert service.ingest(event).status == "admitted"
    assert service.ingest(event).status == "duplicate"
    changed = event.model_copy(update={"app": "Firefox"})
    assert service.ingest(changed).status == "conflict"
    denied = make_event("k2", T0, grant_id="grant-unknown")
    outcome = service.ingest(denied)
    assert outcome.status == "denied" and "unknown-grant" in outcome.reason


def test_end_to_end_sessions_labels_connections_views() -> None:
    service = _service()
    outcomes = service.ingest_many(lecture_code_lecture_events())
    assert all(o.status == "admitted" for o in outcomes)
    assert len(service.sessions()) == 2
    assert len(service.spans()) == 3
    assert service.labels()
    assert service.connections()
    lecture = next(s for s in service.sessions() if len(s.span_ids) == 2)
    view = service.get_session_view(lecture.session_id)
    assert view is not None
    assert len(view.spans) == 2
    assert view.session_label is not None
    assert view.session_label.activity == "lecture-viewing"
    explanation = service.explain_session(lecture.session_id)
    assert explanation is not None
    assert explanation.resumption_evidence
    assert "active" in explanation.summary
    assert service.get_session_view("actsess_missing") is None
    assert service.explain_session("actsess_missing") is None


def test_list_sessions_filters() -> None:
    service = _service()
    service.ingest_many(lecture_code_lecture_events())
    assert len(service.list_sessions(activity="lecture-viewing")) == 1
    assert len(service.list_sessions(activity="coding")) == 1
    assert service.list_sessions(activity="meeting") == []
    assert len(service.list_sessions(identity_status="known")) == 2


def test_session_and_label_corrections() -> None:
    service = _service()
    service.ingest_many(lecture_code_lecture_events())
    lecture = next(s for s in service.sessions() if len(s.span_ids) == 2)
    touched = service.submit_session_correction(ActivityCorrection(
        correction_id="svc-split-1", kind="split-session",
        targets={"session_id": lecture.session_id, "at_span_id": lecture.span_ids[1]},
        reason="synthetic test",
    ))
    assert len(touched) == 2
    assert len(service.sessions()) == 3
    assert service.session_corrections()

    code = next(s for s in service.sessions()
                if s.content_identity and s.content_identity.kind == "code")
    service.submit_label_correction(LabelCorrection(
        correction_id="svc-lbl-1", target_kind="session",
        target_id=code.session_id, activity="reading", reason="synthetic test",
    ))
    view = service.get_session_view(code.session_id)
    assert view is not None and view.session_label is not None
    assert view.session_label.activity == "reading"
    assert view.session_label.corrected is True


def test_connection_decisions() -> None:
    service = _service()
    service.ingest_many(lecture_code_lecture_events())
    connection = service.connections()[0]
    updated = service.decide_connection(connection.connection_id, True)
    assert updated.status.value == "accepted"
    current = next(c for c in service.connections()
                   if c.connection_id == connection.connection_id)
    assert current.status.value == "accepted"


def test_deletion_cascades_and_tombstones() -> None:
    service = _service()
    service.ingest_many(lecture_code_lecture_events())
    lecture = next(s for s in service.sessions() if len(s.span_ids) == 2)
    result = service.request_deletion(session_ids=[lecture.session_id],
                                      reason="synthetic deletion test")
    assert result.deleted_events == 7
    assert len(result.tombstone_ids) == 7
    assert result.remaining_sessions == 1
    assert len(service.tombstones()) == 7
    # Re-ingest of tombstoned events is rejected.
    again = service.ingest(lecture_code_lecture_events()[0])
    assert again.status == "rejected"


def test_deletion_by_time_app_domain() -> None:
    service = _service()
    service.ingest_many(lecture_code_lecture_events())
    before = len(service.events())
    result = service.request_deletion(app_substring="Code", reason="synthetic test")
    assert result.deleted_events == 3
    assert len(service.events()) == before - 3
    result2 = service.request_deletion(domain="video.example.test", reason="synthetic test")
    assert result2.deleted_events == 7
    assert service.sessions() == []


def test_snapshot_save_load_roundtrip(tmp_path) -> None:
    service = _service()
    service.ingest_many(lecture_code_lecture_events())
    lecture = next(s for s in service.sessions() if len(s.span_ids) == 2)
    service.submit_session_correction(ActivityCorrection(
        correction_id="snap-split-1", kind="split-session",
        targets={"session_id": lecture.session_id, "at_span_id": lecture.span_ids[1]},
        reason="synthetic test",
    ))
    connection = service.connections()[0]
    service.decide_connection(connection.connection_id, True)
    target = tmp_path / "snapshot"
    service.save_snapshot(target)
    assert (target / "events.jsonl").exists()

    loaded = ActivityService.load_snapshot(target, grants=grant_store())
    assert len(loaded.sessions()) == len(service.sessions())
    assert [s.session_id for s in loaded.sessions()] == [s.session_id for s in service.sessions()]
    assert loaded.session_corrections()
    decided = [c for c in loaded.connections() if c.connection_id == connection.connection_id]
    assert decided and decided[0].status.value == "accepted"


def test_from_evidence_records_loader() -> None:
    from entorhinal.schemas.models import EvidenceRecord

    service = _service()
    service.ingest_many(lecture_code_lecture_events())
    records = []
    prev = "0" * 64
    for event in service.events():
        signal = event.to_raw_signal_event()
        record = EvidenceRecord.create(
            source_type=signal.source_type,
            app_identifier=signal.app_identifier,
            sanitized_payload=dict(signal.raw_payload),
            previous_record_hash=prev,
            window_title=signal.window_title,
            target_uri=signal.target_uri,
        )
        records.append(record)
        prev = record.provenance_hash
    records.append(EvidenceRecord.create(
        source_type=records[0].source_type, app_identifier="Other",
        sanitized_payload={"note": "non-activity record"},
        previous_record_hash=prev,
    ))
    rebuilt = ActivityService.from_evidence_records(records, grants=grant_store())
    assert len(rebuilt.sessions()) == 2
    assert len(rebuilt.spans()) == 3
    assert rebuilt.load_skipped == 1


def test_trace_port_null_and_validation() -> None:
    organizer = NullTraceOrganizer()
    enrichment = organizer.organize({"ids": ["actsess_a", "actspan_b"]})
    assert enrichment.preserved_ids == ["actsess_a", "actspan_b"]
    assert validate_enrichment(["actsess_a", "actspan_b"], enrichment) == []
    assert validate_enrichment(["actsess_a", "missing"], enrichment) != []

    bad = TraceEnrichment(organizer_id="x", extra_connections=[{"kind": "k"}],
                          preserved_ids=[])
    assert validate_enrichment([], bad) != []

    recorder = RecordingTraceOrganizer()
    recorder.organize({"ids": []})
    assert len(recorder.seen) == 1


def test_service_snapshot_files_are_json(tmp_path) -> None:
    service = _service()
    service.ingest_many(lecture_code_lecture_events())
    target = tmp_path / "snap"
    service.save_snapshot(target)
    meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
    assert meta["service_version"] == "activity-service/1"
    assert meta["event_count"] == len(lecture_code_lecture_events())


def test_media_marker_events_classify_as_lecture() -> None:
    service = _service()
    service.ingest(make_event(
        "mm1", T0, ActivityKind.MEDIA_MARKER, "Chromium", "SYNTH Lecture 2",
        "https://video.example.test/watch?v=SYNTH-2",
        media_payload("SYNTH-2", 100.0, "paused"),
    ))
    labels = [l for l in service.labels() if l.target_kind == "session"]
    assert labels and labels[0].activity == "lecture-viewing"
