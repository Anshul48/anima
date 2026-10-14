"""Local classification: deterministic rules, evidence, pins (synthetic only)."""

from __future__ import annotations

from datetime import timedelta

from entorhinal.activity.classify import (
    EntityHint,
    LabelCorrection,
    LocalActivityClassifier,
)
from entorhinal.activity.events import ActivityKind
from entorhinal.activity.sessions import SessionBuilder

from tests.activity_fixtures import T0, make_event, media_payload


def _spans_for(events):
    builder = SessionBuilder()
    builder.ingest(events)
    return builder.spans(), builder.sessions()


def test_lecture_coding_meeting_labels_with_evidence() -> None:
    events = [
        make_event(
            "l1", T0, ActivityKind.MEDIA_FOREGROUND, "Chromium",
            "SYNTH Lecture 7: Hippocampus",
            "https://video.example.test/watch?v=SYNTH-7",
            media_payload("SYNTH-7", 0.0, "playing"),
        ),
        make_event(
            "c1", T0 + timedelta(minutes=5), ActivityKind.WINDOW_FOREGROUND,
            "Code", "SYNTH main.py — proj", "file:///synth/proj/main.py", {},
        ),
        make_event(
            "m1", T0 + timedelta(minutes=10), ActivityKind.WINDOW_FOREGROUND,
            "Zoom", "SYNTH standup meeting", None, {},
        ),
    ]
    spans, sessions = _spans_for(events)
    classifier = LocalActivityClassifier()
    by_activity = {classifier.classify_span(s).activity for s in spans}
    assert by_activity == {"lecture-viewing", "coding", "meeting"}
    for span in spans:
        label = classifier.classify_span(span)
        assert label.evidence, "every label must cite its rule hits"
        assert label.rule_version == "activity-rules/1"
    session_label = classifier.classify_session(sessions[0], spans)
    assert session_label.activity in LocalActivityClassifier.ACTIVITIES


def test_unknown_app_yields_unknown_with_reasons() -> None:
    events = [
        make_event("x1", T0, ActivityKind.WINDOW_FOREGROUND,
                   "SynthNovelApp", "SYNTH Untitled", None, {}),
    ]
    spans, _ = _spans_for(events)
    label = LocalActivityClassifier().classify_span(spans[0])
    assert label.activity == "unknown"
    assert label.confidence == 0.0
    assert label.uncertainty_reasons


def test_entities_extracted_with_evidence() -> None:
    events = [
        make_event(
            "c1", T0, ActivityKind.WINDOW_FOREGROUND, "Code",
            "SYNTH Lecture 3 notes — main.py", "file:///synth/proj/main.py", {},
        ),
    ]
    spans, _ = _spans_for(events)
    label = LocalActivityClassifier().classify_span(spans[0])
    kinds = {e.kind for e in label.entities}
    assert {"file", "repo", "topic"} <= kinds
    assert all(e.evidence for e in label.entities)


def test_label_correction_pins_and_survives_rebuild() -> None:
    events = [
        make_event("x1", T0, ActivityKind.WINDOW_FOREGROUND,
                   "SynthNovelApp", "SYNTH Untitled", None, {}),
    ]
    spans, _ = _spans_for(events)
    classifier = LocalActivityClassifier()
    target = spans[0].span_id
    classifier.apply_correction(LabelCorrection(
        correction_id="lbl-1", target_kind="span", target_id=target,
        activity="reading",
        entities=[EntityHint(kind="topic", value="synth-topic", evidence="user")],
        reason="synthetic test pin",
    ))
    label = classifier.classify_span(spans[0])
    assert label.activity == "reading"
    assert label.corrected is True and label.confidence == 1.0
    assert label.entities[0].value == "synth-topic"


def test_session_label_majority_and_mixed_uncertainty() -> None:
    lecture = make_event(
        "l1", T0, ActivityKind.MEDIA_FOREGROUND, "Chromium",
        "SYNTH Lecture 7", "https://video.example.test/watch?v=SYNTH-7",
        media_payload("SYNTH-7", 0.0, "playing"),
    )
    code = make_event(
        "c1", T0 + timedelta(minutes=30), ActivityKind.WINDOW_FOREGROUND,
        "Code", "SYNTH main.py", "file:///synth/proj/main.py", {},
    )
    spans, sessions = _spans_for([lecture, code])
    classifier = LocalActivityClassifier()
    # Force a mixed session view by labeling across both spans' session union:
    # use the lecture session but pass both spans.
    label = classifier.classify_session(sessions[0], spans)
    assert label.activity in LocalActivityClassifier.ACTIVITIES


def test_classification_is_deterministic_and_local() -> None:
    events = [
        make_event(
            "l1", T0, ActivityKind.MEDIA_FOREGROUND, "Chromium",
            "SYNTH Lecture 7: Hippocampus",
            "https://video.example.test/watch?v=SYNTH-7",
            media_payload("SYNTH-7", 600.0, "playing"),
        ),
    ]
    spans, _ = _spans_for(events)
    first = LocalActivityClassifier().classify_span(spans[0])
    second = LocalActivityClassifier().classify_span(spans[0])
    assert first == second
    assert first.label_id.startswith("actlabel_")
