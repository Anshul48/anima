"""Session continuity: spans, stable logical sessions, corrections (synthetic only).

Covers the required lecture/code/lecture case (TWO sessions, THREE spans),
active-vs-elapsed accounting, unknown identity, different content, restart
boundaries, clock/order anomalies, and user corrections.
"""

from __future__ import annotations

from datetime import timedelta

from entorhinal.activity.events import ActivityKind
from entorhinal.activity.sessions import ActivityCorrection, SessionBuilder

from tests.activity_fixtures import T0, make_event, media_payload

LECTURE_TITLE = "SYNTH Lecture 7: Hippocampus"
LECTURE_URI = "https://video.example.test/watch?v=SYNTH-7"


def _lecture(event_id, at, position, state="playing", kind=ActivityKind.MEDIA_FOREGROUND):
    return make_event(
        event_id, at, kind, "Chromium", LECTURE_TITLE, LECTURE_URI,
        media_payload("SYNTH-7", position, state),
    )


def _code(event_id, at, path="file:///synth/proj/main.py"):
    return make_event(
        event_id, at, ActivityKind.WINDOW_FOREGROUND, "Code",
        "SYNTH main.py — proj", path, {},
    )


def lecture_code_lecture_events():
    return [
        _lecture("l1", T0, 0.0),
        _lecture("l2", T0 + timedelta(minutes=10), 600.0),
        _lecture("l3", T0 + timedelta(minutes=20), 1200.0),
        _lecture("l-pause", T0 + timedelta(minutes=30), 1800.0,
                 state="paused", kind=ActivityKind.MEDIA_MARKER),
        _code("c1", T0 + timedelta(minutes=31)),
        _code("c2", T0 + timedelta(minutes=33)),
        _code("c3", T0 + timedelta(minutes=35)),
        _lecture("l-resume", T0 + timedelta(minutes=36), 1800.0,
                 state="resumed", kind=ActivityKind.RESUME_MARKER),
        _lecture("l4", T0 + timedelta(minutes=40), 2040.0),
        _lecture("l5", T0 + timedelta(minutes=50), 2640.0),
    ]


def test_lecture_code_lecture_two_sessions_three_spans() -> None:
    builder = SessionBuilder()
    builder.ingest(lecture_code_lecture_events())
    spans = builder.spans()
    sessions = builder.sessions()
    assert len(spans) == 3
    assert len(sessions) == 2

    lecture = next(s for s in sessions if s.content_identity and "SYNTH-7" in s.content_identity.key)
    code = next(s for s in sessions if s.content_identity and s.content_identity.kind == "code")
    assert len(lecture.span_ids) == 2
    assert len(code.span_ids) == 1
    assert len(lecture.resumption_links) == 1
    link = lecture.resumption_links[0]
    assert "position-continuity" in link.evidence
    assert link.confidence >= 0.5
    # Coding interval is not charged to lecture active time: lecture active is
    # bounded by its own spans' capped steps, far below wall elapsed incl. gap.
    assert lecture.total_elapsed_seconds == 1800.0 + 840.0
    assert lecture.total_active_seconds <= 6 * 120.0


def test_pause_resume_provenance_preserved() -> None:
    builder = SessionBuilder()
    builder.ingest(lecture_code_lecture_events())
    first_span = builder.spans()[0]
    assert first_span.provenance.pause_intervals_s == []  # pause at span end
    assert "l-pause" in first_span.provenance.marker_event_ids
    resumed_span = builder.spans()[2]
    assert "l-resume" in resumed_span.provenance.marker_event_ids


def test_different_lectures_stay_distinct() -> None:
    events = [
        _lecture("a1", T0, 0.0),
        _lecture("a2", T0 + timedelta(minutes=5), 300.0),
        make_event(
            "b1", T0 + timedelta(minutes=6), ActivityKind.MEDIA_FOREGROUND,
            "Chromium", "SYNTH Lecture 8: Cortex",
            "https://video.example.test/watch?v=SYNTH-8",
            media_payload("SYNTH-8", 0.0, "playing"),
        ),
        make_event(
            "b2", T0 + timedelta(minutes=11), ActivityKind.MEDIA_FOREGROUND,
            "Chromium", "SYNTH Lecture 8: Cortex",
            "https://video.example.test/watch?v=SYNTH-8",
            media_payload("SYNTH-8", 300.0, "playing"),
        ),
    ]
    builder = SessionBuilder()
    builder.ingest(events)
    assert len(builder.spans()) == 2
    assert len(builder.sessions()) == 2


def test_same_app_same_url_different_media_not_merged() -> None:
    # Same app and same browse URL, but different explicit media ids:
    # identity (not URL equality) decides.
    events = [
        make_event(
            "a1", T0, ActivityKind.MEDIA_FOREGROUND, "Chromium", "SYNTH watch",
            "https://video.example.test/browse",
            media_payload("SYNTH-A", 0.0, "playing"),
        ),
        make_event(
            "b1", T0 + timedelta(minutes=5), ActivityKind.MEDIA_FOREGROUND,
            "Chromium", "SYNTH watch",
            "https://video.example.test/browse",
            media_payload("SYNTH-B", 0.0, "playing"),
        ),
    ]
    builder = SessionBuilder()
    builder.ingest(events)
    assert len(builder.sessions()) == 2


def test_unknown_identity_never_auto_merges() -> None:
    events = [
        make_event("u1", T0, ActivityKind.WINDOW_FOREGROUND, "Chromium",
                   "SYNTH page one", "https://video.example.test/browse", {}),
        make_event("u2", T0 + timedelta(seconds=30), ActivityKind.WINDOW_FOREGROUND,
                   "Code", "SYNTH main.py", "file:///synth/proj/main.py", {}),
        make_event("u3", T0 + timedelta(minutes=1), ActivityKind.WINDOW_FOREGROUND,
                   "Chromium", "SYNTH page one", "https://video.example.test/browse", {}),
    ]
    builder = SessionBuilder()
    builder.ingest(events)
    assert len(builder.spans()) == 3
    sessions = builder.sessions()
    assert len(sessions) == 3
    unknown = [s for s in sessions if s.identity_status == "unknown"]
    assert len(unknown) == 2
    assert all("never auto-merged" in builder.span(s.span_ids[0]).identity_note for s in unknown)


def test_position_restart_opens_new_session() -> None:
    events = [
        _lecture("l1", T0, 1500.0),
        _code("c1", T0 + timedelta(minutes=10)),
        # Same lecture restarted from the beginning: rewatch, not resume.
        _lecture("l2", T0 + timedelta(minutes=20), 5.0),
    ]
    builder = SessionBuilder()
    builder.ingest(events)
    lecture_sessions = [s for s in builder.sessions()
                        if s.content_identity and "SYNTH-7" in s.content_identity.key]
    assert len(lecture_sessions) == 2
    assert lecture_sessions[1].considered_but_not_linked, "why-not must be recorded"


def test_same_key_without_continuity_stays_separate() -> None:
    # Same media id but NO position evidence and different titles: a gap plus
    # URL equality alone must not merge.
    first = make_event(
        "a1", T0, ActivityKind.WINDOW_FOREGROUND, "Chromium", "SYNTH watch A",
        "https://video.example.test/watch?v=SYNTH-7", {},
    )
    second = make_event(
        "a2", T0 + timedelta(minutes=2), ActivityKind.WINDOW_FOREGROUND, "Chromium",
        "SYNTH watch B (different title)",
        "https://video.example.test/watch?v=SYNTH-7", {},
    )
    builder = SessionBuilder()
    builder.ingest([_code("c", T0 + timedelta(minutes=1)), first, second])
    lecture = [s for s in builder.sessions()
               if s.content_identity and "SYNTH-7" in s.content_identity.key]
    assert len(lecture) == 2
    assert lecture[1].considered_but_not_linked[0].reasons_not_linked


def test_background_overlap_does_not_merge_or_charge_foreground() -> None:
    events = [
        _lecture("l1", T0, 0.0),
        make_event(
            "bg1", T0 + timedelta(minutes=5), ActivityKind.MEDIA_BACKGROUND,
            "MusicApp", "SYNTH background tunes", "https://audio.example.test/x",
            {"media_id": "SYNTH-BG", "media_host": "audio.example.test",
             "media_position_s": 10.0, "media_state": "playing"},
            foreground=False,
        ),
        _lecture("l2", T0 + timedelta(minutes=10), 600.0),
    ]
    builder = SessionBuilder()
    builder.ingest(events)
    assert len(builder.spans()) == 2  # foreground lecture + background music
    lecture = next(s for s in builder.sessions()
                   if s.content_identity and "SYNTH-7" in s.content_identity.key)
    assert len(lecture.span_ids) == 1
    assert lecture.total_active_seconds <= 2 * 120.0
    background = next(s for s in builder.sessions()
                      if s.content_identity and "SYNTH-BG" in s.content_identity.key)
    assert builder.span(background.span_ids[0]).background is True


def test_out_of_order_ingest_is_deterministic() -> None:
    events = lecture_code_lecture_events()
    forward = SessionBuilder.rebuild(events)
    backward = SessionBuilder.rebuild(list(reversed(events)))
    assert [s.session_id for s in forward.sessions()] == [s.session_id for s in backward.sessions()]
    assert [s.span_id for s in forward.spans()] == [s.span_id for s in backward.spans()]
    assert forward.sessions()[0].model_dump() == backward.sessions()[0].model_dump()


def test_replay_is_stable_and_duplicate_safe() -> None:
    events = lecture_code_lecture_events()
    builder = SessionBuilder()
    builder.ingest(events)
    before = [s.model_dump(mode="json") for s in builder.sessions()]
    builder.ingest(events)  # exact replay: no-op
    after = [s.model_dump(mode="json") for s in builder.sessions()]
    assert before == after
    rebuilt = SessionBuilder.rebuild(events, builder.corrections())
    assert [s.model_dump(mode="json") for s in rebuilt.sessions()] == before


def test_unknown_observed_time_and_clock_anomaly_noted() -> None:
    first = make_event("u1", T0)
    first = first.model_copy(update={"observed_at": None})
    second = make_event("u2", T0 + timedelta(minutes=1))
    builder = SessionBuilder()
    builder.ingest([first, second])
    span = builder.spans()[0]
    assert "received" in span.provenance.order_basis
    assert any("unknown" in note for note in span.provenance.clock_notes)

    future = make_event("f1", T0)
    future = future.model_copy(update={
        "observed_at": future.received_at + timedelta(hours=1),
    })
    builder2 = SessionBuilder()
    builder2.ingest([future])
    assert any("clock-anomaly" in note for note in builder2.spans()[0].provenance.clock_notes)


def test_split_and_merge_corrections_outrank_inference() -> None:
    builder = SessionBuilder()
    builder.ingest(lecture_code_lecture_events())
    lecture = next(s for s in builder.sessions() if len(s.span_ids) == 2)
    split = ActivityCorrection(
        correction_id="corr-split-1", kind="split-session",
        targets={"session_id": lecture.session_id, "at_span_id": lecture.span_ids[1]},
        reason="synthetic test: these are separate viewings",
    )
    touched = builder.apply_correction(split)
    assert len(touched) == 2
    assert len(builder.sessions()) == 3

    # Rebuild replays the split: inference does not relink.
    rebuilt = SessionBuilder.rebuild(lecture_code_lecture_events(), builder.corrections())
    assert len(rebuilt.sessions()) == 3

    # Merge them back by user confirmation.
    parts = [s.session_id for s in rebuilt.sessions()
             if s.content_identity and "SYNTH-7" in s.content_identity.key]
    assert len(parts) == 2
    merge = ActivityCorrection(
        correction_id="corr-merge-1", kind="merge-sessions",
        targets={"session_ids": parts}, reason="synthetic test: actually one viewing",
    )
    # Merge targets inference-built ids, but the split changed them; apply on
    # the rebuilt (split) state instead.
    merged = rebuilt.apply_correction(merge)
    assert len(merged) == 1
    assert merged[0].resumption_links[0].user_confirmed is True
    assert merged[0].resumption_links[0].confidence == 1.0


def test_reassign_span_correction() -> None:
    builder = SessionBuilder()
    builder.ingest(lecture_code_lecture_events())
    lecture = next(s for s in builder.sessions() if len(s.span_ids) == 2)
    code = next(s for s in builder.sessions() if len(s.span_ids) == 1
                and s.content_identity and s.content_identity.kind == "code")
    moved_span = lecture.span_ids[1]
    correction = ActivityCorrection(
        correction_id="corr-move-1", kind="reassign-span",
        targets={"span_id": moved_span, "to_session_id": code.session_id},
        reason="synthetic test: misattributed span",
    )
    touched = builder.apply_correction(correction)
    assert code.session_id in [s.session_id for s in touched]
    view = builder.session(code.session_id)
    assert view is not None and moved_span in view.span_ids


def test_unrelated_code_files_stay_distinct() -> None:
    builder = SessionBuilder()
    builder.ingest([
        _code("c1", T0, "file:///synth/proj-a/main.py"),
        _code("c2", T0 + timedelta(minutes=2), "file:///synth/proj-b/other.py"),
    ])
    assert len(builder.sessions()) == 2
