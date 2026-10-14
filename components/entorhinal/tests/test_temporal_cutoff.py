"""M2 dual-time query tests (E2): valid-time vs knowledge-cutoff.

Uses tmp_path fixtures only; never touches the live capture daemon.

SYNTHETIC PROVENANCE: the "redacted-ok" values below are inert synthetic
placeholders, never real secrets.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from entorhinal.schemas.task_event import DEV_TASK_SOURCE_ID, TaskEvent
from entorhinal.temporal.cutoff import TemporalQuery
from entorhinal.temporal.projection import CommittedTaskEvent, TaskProjection

GRANT = "m2-test-grant"
SOURCE = DEV_TASK_SOURCE_ID
BASE = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


def make_event(
    event_id: str,
    sequence: int,
    kind: str,
    *,
    task: Optional[str] = "t1",
    session: str = "s1",
    observed_min: Optional[float] = 0.0,
    value: Optional[Dict[str, Any]] = None,
    condition: Optional[str] = None,
    outcome: Optional[str] = None,
    epistemic: str = "assertion",
    claim_key: Optional[str] = None,
    corrects: Optional[List[str]] = None,
    supersedes: Optional[List[str]] = None,
    valid_from_min: Optional[float] = None,
    valid_to_min: Optional[float] = None,
) -> Dict[str, Any]:
    observed = BASE + timedelta(minutes=observed_min) if observed_min is not None else None
    work: Dict[str, Any] = {"session_id": session}
    if task is not None:
        work["task_id"] = task
    payload: Dict[str, Any] = {}
    if value is not None:
        payload["value"] = value
    if condition is not None:
        payload["condition"] = condition
    if outcome is not None:
        payload["outcome"] = outcome
    revision: Dict[str, Any] = {}
    if claim_key is not None:
        revision["claim_key"] = claim_key
    if corrects:
        revision["corrects"] = corrects
    if supersedes:
        revision["supersedes"] = supersedes
    if valid_from_min is not None:
        revision["valid_from"] = (BASE + timedelta(minutes=valid_from_min)).isoformat()
    if valid_to_min is not None:
        revision["valid_to"] = (BASE + timedelta(minutes=valid_to_min)).isoformat()
    return {
        "contract_version": "entorhinal.task-event/v1-draft",
        "source_id": SOURCE,
        "event_id": event_id,
        "producer_run_id": "run-m2",
        "producer_sequence": sequence,
        "producer_version": "m2-test-emitter/v0",
        "work": work,
        "kind": kind,
        "time": {
            "observed_at": observed.isoformat() if observed else None,
            "received_at": None,
            "committed_at": None,
            "clock_domain": "test-clock",
            "precision_ms": 1.0,
            "uncertainty_ms": None,
            "source_sequence": sequence,
        },
        "payload": payload,
        "epistemic": epistemic,
        "revision": revision,
        "admission": {
            "grant_revision": GRANT,
            "retention_class": "payload-30d",
            "deletion_generation": 0,
            "revocation_generation": 0,
        },
        "assistance": {},
    }


def commit(
    event_dict: Dict[str, Any],
    commit_seq: int,
    committed_min: float = 0.0,
) -> CommittedTaskEvent:
    return CommittedTaskEvent(
        event=TaskEvent.model_validate(event_dict),
        commit_seq=commit_seq,
        committed_at=BASE + timedelta(minutes=committed_min),
        evidence_id=f"ev-{event_dict['event_id']}",
        received_at=BASE + timedelta(minutes=committed_min),
    )


def at(minutes: float) -> datetime:
    return BASE + timedelta(minutes=minutes)


# -- late arrival -------------------------------------------------------------------


def test_late_arrival_excluded_from_cutoff() -> None:
    key = f"claim:{SOURCE}:t1:value:mode"
    entries = [
        commit(make_event("g", 0, "goal", condition="Set mode"), 1, 0.5),
        commit(
            make_event("v1", 1, "assumption-change", value={"mode": "fast"}, observed_min=1),
            2, 1.5,
        ),
        # Observed at t+2 but committed much later (commit_seq 4).
        commit(
            make_event("late", 2, "assumption-change", value={"mode": "safe"}, observed_min=2),
            4, 20.0,
        ),
        commit(
            make_event("v3", 3, "observation", value={"load": "high"}, observed_min=3,
                       epistemic="observation"),
            3, 2.5,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    query = TemporalQuery(projection)
    # Full knowledge: the late arrival revised current belief.
    full = query.valid_at(at(25))
    assert full.values[key].status == "known"
    assert full.values[key].value == {"mode": "safe"}
    assert full.values[key].source_event_id == "late"
    # Cutoff k=3 (before the late commit): excluded despite early observation.
    cut = query.valid_at(at(25), cutoff_seq=3)
    assert cut.watermark == 3
    assert cut.values[key].status == "known"
    assert cut.values[key].value == {"mode": "fast"}
    assert cut.values[key].source_event_id == "v1"
    # The cutoff projection itself never saw the late event.
    view = query.known_by_commit(3)
    assert view.watermark == 3
    assert [entry.event_id for entry in view.event_log] == ["g", "v1", "v3"]
    assert view.claims[key][-1].value == {"mode": "fast"}


def test_valid_time_vs_knowledge_cutoff() -> None:
    key = f"claim:{SOURCE}:t1:value:level"
    entries = [
        commit(make_event("g", 0, "goal", condition="Tune level"), 1, 0.5),
        commit(
            make_event("v1", 1, "assumption-change", value={"level": 1}, observed_min=1),
            2, 1.5,
        ),
        commit(
            make_event("v2", 2, "assumption-change", value={"level": 2}, observed_min=10),
            3, 10.5,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    query = TemporalQuery(projection)
    # Valid time: each version true in its own interval.
    assert query.valid_at(at(2)).values[key].value == {"level": 1}
    assert query.valid_at(at(11)).values[key].value == {"level": 2}
    # Knowledge cutoff: at k=2, v2 was not yet known, so the k=2 view
    # still holds v1 (with the open validity it had then) -- the later
    # value must not leak into the earlier cutoff.
    cut = query.valid_at(at(11), cutoff_seq=2)
    assert cut.values[key].status == "known"
    assert cut.values[key].value == {"level": 1}
    assert cut.values[key].source_event_id == "v1"
    # ... and the past was known identically.
    assert query.valid_at(at(2), cutoff_seq=2).values[key].value == {"level": 1}


def test_known_by_time_cutoff() -> None:
    entries = [
        commit(make_event("g", 0, "goal", condition="Clock check"), 1, 0.5),
        commit(
            make_event("v1", 1, "assumption-change", value={"n": 1}, observed_min=1),
            2, 5.0,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    query = TemporalQuery(projection)
    early = query.known_by_time(at(1))
    assert [entry.event_id for entry in early.event_log] == ["g"]
    late = query.known_by_time(at(6))
    assert [entry.event_id for entry in late.event_log] == ["g", "v1"]


# -- unknown intervals ----------------------------------------------------------------


def test_unknown_intervals_stay_unknown() -> None:
    key = f"claim:{SOURCE}:t1:value:temp"
    entries = [
        commit(make_event("g", 0, "goal", condition="Watch temp"), 1, 0.5),
        commit(
            make_event("off", 1, "source-status", task=None, value={"status": "offline"},
                       observed_min=2),
            2, 2.5,
        ),
        commit(
            make_event("on", 2, "source-status", task=None, value={"status": "online"},
                       observed_min=9),
            3, 9.5,
        ),
        commit(
            make_event("v1", 3, "observation", value={"temp": 21}, observed_min=12,
                       epistemic="observation"),
            4, 12.5,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    query = TemporalQuery(projection)
    inside = query.valid_at(at(5))
    assert len(inside.unknown_interval_ids) == 1
    # No revision covers the outage: unknown, never a fabricated value.
    assert inside.values[key].status == "unknown"
    outside = query.valid_at(at(13))
    assert outside.unknown_interval_ids == []
    assert outside.values[key].value == {"temp": 21}
    # Before any observation: unknown, not false.
    before = query.valid_at(at(0.7))
    assert before.values.get(key) is None or before.values[key].status == "unknown"


def test_conflict_visible_at_valid_time() -> None:
    key = f"claim:{SOURCE}:t1:value:zone"
    entries = [
        commit(make_event("g", 0, "goal", condition="Pick zone"), 1, 0.5),
        commit(
            make_event("o1", 1, "observation", value={"zone": "a"}, observed_min=1,
                       epistemic="observation"),
            2, 1.5,
        ),
        commit(
            make_event("o2", 2, "observation", value={"zone": "b"}, observed_min=2,
                       epistemic="observation"),
            3, 2.5,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    query = TemporalQuery(projection)
    view = query.valid_at(at(5))
    assert view.values[key].status == "conflicted"
    assert len(view.values[key].revision_ids) == 2
    assert len(view.conflict_ids) == 1


# -- correction scope in valid time ------------------------------------------------------


def test_correction_scope_limits_valid_time_effect() -> None:
    key = f"claim:{SOURCE}:t1:value:limit"
    entries = [
        commit(make_event("g", 0, "goal", condition="Cap load"), 1, 0.5),
        commit(
            make_event("o1", 1, "observation", value={"limit": 10}, observed_min=1,
                       epistemic="observation"),
            2, 1.5,
        ),
        commit(
            make_event(
                "c1", 2, "correction", value={"limit": 50}, observed_min=4,
                epistemic="correction", claim_key=key, corrects=["o1"],
                valid_from_min=3, valid_to_min=8,
            ),
            3, 4.5,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    query = TemporalQuery(projection)
    # Inside the scope: corrected value wins.
    inside = query.valid_at(at(5))
    assert inside.values[key].status == "known"
    assert inside.values[key].value == {"limit": 50}
    # Outside the scope: the original observation still stands.
    before = query.valid_at(at(2))
    assert before.values[key].status == "known"
    assert before.values[key].value == {"limit": 10}
    # After the scope ends with no covering revision: unknown.
    after = query.valid_at(at(9))
    assert after.values[key].status == "unknown"


def test_pure_invalidation_reports_corrected_removed() -> None:
    key = f"claim:{SOURCE}:t1:value:flag"
    entries = [
        commit(make_event("g", 0, "goal", condition="Check flag"), 1, 0.5),
        commit(
            make_event("o1", 1, "observation", value={"flag": True}, observed_min=1,
                       epistemic="observation"),
            2, 1.5,
        ),
        commit(
            make_event(
                "c1", 2, "correction", observed_min=4, epistemic="correction",
                claim_key=key, corrects=["o1"],
            ),
            3, 4.5,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    query = TemporalQuery(projection)
    # Unscoped correction applies from its own valid_from onward.
    assert query.valid_at(at(2)).values[key].value == {"flag": True}
    removed = query.valid_at(at(6))
    assert removed.values[key].status == "corrected-removed"


# -- deletion / revocation on historical queries ---------------------------------------------


def test_deletion_honored_on_historical_queries() -> None:
    key = f"claim:{SOURCE}:t1:value:secret"
    entries = [
        commit(make_event("g", 0, "goal", condition="Handle value"), 1, 0.5),
        commit(
            make_event("v1", 1, "assumption-change", value={"secret": "redacted-ok"},
                       observed_min=1),
            2, 1.5,
        ),
        commit(
            make_event("v2", 2, "assumption-change", value={"other": 1}, observed_min=3),
            3, 3.5,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    assert projection.claims[key][-1].value == {"secret": "redacted-ok"}
    generation = projection.apply_deletion([key], reason="test deletion honored")
    assert generation == 1
    assert key not in projection.claims
    query = TemporalQuery(projection)
    # Current generations apply to every historical cutoff view.
    historical = query.valid_at(at(2), cutoff_seq=3)
    assert historical.deletion_generation == 1
    assert historical.values[key].status == "deleted"
    assert query.known_by_commit(3).claims.get(key) is None


def test_event_deletion_and_source_revocation_exclude_history() -> None:
    entries = [
        commit(make_event("g", 0, "goal", condition="Do work"), 1, 0.5),
        commit(
            make_event("a1", 1, "attempt", task="t1", observed_min=1,
                       condition="attempt happened"),
            2, 1.5,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    assert len(projection.timeline) == 2
    projection.apply_deletion(["a1"], reason="test event deletion")
    assert [entry.event_id for entry in projection.event_log] == ["g"]
    query = TemporalQuery(projection)
    assert [entry.event_id for entry in query.known_by_commit(2).event_log] == ["g"]
    projection.apply_revocation([SOURCE], reason="test revocation")
    assert projection.event_log == []
    assert query.known_by_commit(2).event_log == []
    assert projection.tasks == {}
