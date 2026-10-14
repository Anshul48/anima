"""M2 temporal projection tests (E2): task/attempt/outcome/correction state.

Uses tmp_path fixtures only; never touches the live capture daemon.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from entorhinal.schemas.task_event import DEV_TASK_SOURCE_ID, TaskEvent
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
    attempt: Optional[str] = None,
    branch: Optional[str] = None,
    parent_branch: Optional[str] = None,
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
    attempt_record: Optional[Dict[str, Any]] = None,
    excerpts: Optional[List[Dict[str, Any]]] = None,
    artifact_refs: Optional[List[Dict[str, Any]]] = None,
    clock: str = "test-clock",
) -> Dict[str, Any]:
    observed = BASE + timedelta(minutes=observed_min) if observed_min is not None else None
    work: Dict[str, Any] = {"session_id": session}
    if task is not None:
        work["task_id"] = task
    if attempt is not None:
        work["attempt_id"] = attempt
    if branch is not None:
        work["branch_id"] = branch
    if parent_branch is not None:
        work["parent_branch_id"] = parent_branch
    payload: Dict[str, Any] = {}
    if value is not None:
        payload["value"] = value
    if condition is not None:
        payload["condition"] = condition
    if outcome is not None:
        payload["outcome"] = outcome
    if attempt_record is not None:
        payload["attempt"] = attempt_record
    if excerpts is not None:
        payload["excerpts"] = excerpts
    if artifact_refs is not None:
        payload["artifact_refs"] = artifact_refs
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
            "clock_domain": clock,
            "precision_ms": 1.0,
            "uncertainty_ms": 5.0,
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
    received_min: Optional[float] = None,
) -> CommittedTaskEvent:
    event = TaskEvent.model_validate(event_dict)
    received = (
        BASE + timedelta(minutes=received_min) if received_min is not None else None
    )
    return CommittedTaskEvent(
        event=event,
        commit_seq=commit_seq,
        committed_at=BASE + timedelta(minutes=committed_min),
        evidence_id=f"ev-{event_dict['event_id']}",
        received_at=received,
        content_hash=f"hash-{event_dict['event_id']}",
    )


def attempt_record(attempt_id: str, command: str, exit_status: Optional[int] = None) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "attempt_id": attempt_id,
        "command_identity": command,
        "check_identity": "pytest",
        "started_at": BASE.isoformat(),
    }
    if exit_status is not None:
        record["ended_at"] = (BASE + timedelta(minutes=1)).isoformat()
        record["exit_status"] = exit_status
    return record


# -- interleaved tasks ------------------------------------------------------------


def test_interleaved_tasks_tracked_separately() -> None:
    entries = [
        commit(make_event("g1", 0, "goal", task="t1", condition="Fix login redirect"), 1),
        commit(make_event("g2", 1, "goal", task="t2", condition="Add logout button"), 2),
        commit(make_event("s1", 2, "lifecycle", task="t1", value={"transition": "start"}), 3),
        commit(make_event("s2", 3, "lifecycle", task="t2", value={"transition": "start"}), 4),
        commit(
            make_event(
                "a1", 4, "attempt", task="t1", attempt="att-1",
                attempt_record=attempt_record("att-1", "pytest tests/login"),
            ),
            5,
        ),
        commit(
            make_event(
                "a2", 5, "attempt", task="t2", attempt="att-2",
                attempt_record=attempt_record("att-2", "pytest tests/logout"),
            ),
            6,
        ),
    ]
    projection = TaskProjection()
    for entry in entries:
        projection.apply(entry)
    assert set(projection.tasks) == {"t1", "t2"}
    assert projection.tasks["t1"].goal == "Fix login redirect"
    assert projection.tasks["t2"].goal == "Add logout button"
    assert projection.tasks["t1"].attempt_ids == ["att-1"]
    assert projection.tasks["t2"].attempt_ids == ["att-2"]
    assert projection.attempts["att-1"].command_identity == "pytest tests/login"
    assert projection.attempts["att-2"].command_identity == "pytest tests/logout"
    assert projection.tasks["t1"].status == "in-progress"
    # Episodes follow explicit task IDs.
    assert projection.episodes["episode:task:t1"].boundary == "explicit-task"
    assert projection.episodes["episode:task:t1"].provisional is False
    assert projection.episodes["episode:task:t2"].event_ids == ["g2", "s2", "a2"]


def test_repeated_identical_commands_are_distinct_attempts() -> None:
    entries = [
        commit(make_event("g", 0, "goal", condition="Stabilize flaky test"), 1),
        commit(
            make_event(
                "a1", 1, "attempt", attempt="att-1",
                attempt_record=attempt_record("att-1", "pytest tests/flaky -x", 1),
                outcome="failed",
            ),
            2,
        ),
        commit(
            make_event(
                "a2", 2, "attempt", attempt="att-2",
                attempt_record=attempt_record("att-2", "pytest tests/flaky -x", 1),
                outcome="failed",
            ),
            3,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    assert set(projection.attempts) == {"att-1", "att-2"}
    assert projection.attempts["att-1"].command_identity == "pytest tests/flaky -x"
    assert projection.attempts["att-2"].command_identity == "pytest tests/flaky -x"
    assert projection.attempts["att-1"].attempt_event_ids == ["a1"]
    assert projection.attempts["att-2"].attempt_event_ids == ["a2"]
    assert projection.tasks["t1"].attempt_ids == ["att-1", "att-2"]


def test_changed_assumption_supersession() -> None:
    entries = [
        commit(make_event("g", 0, "goal", condition="Tune retries"), 1),
        commit(
            make_event("v1", 1, "assumption-change", value={"retries": 1}, observed_min=1),
            2,
        ),
        commit(
            make_event("v2", 2, "assumption-change", value={"retries": 3}, observed_min=5),
            3,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    key = f"claim:{SOURCE}:t1:value:retries"
    revisions = projection.claims[key]
    assert len(revisions) == 2
    assert revisions[0].value == {"retries": 1}
    assert revisions[0].superseded_by == revisions[1].revision_id
    assert revisions[1].value == {"retries": 3}
    assert revisions[1].superseded_by is None
    assert revisions[0].revision_id != revisions[1].revision_id
    assert revisions[0].valid_to == revisions[1].valid_from
    # No conflict: succession is versioned supersession, not disagreement.
    assert projection.conflicts == {}


def test_correction_scoping_and_replay_survival() -> None:
    key = f"claim:{SOURCE}:t1:value:timeout"
    entries = [
        commit(make_event("g", 0, "goal", condition="Fix timeouts"), 1),
        commit(
            make_event(
                "o1", 1, "observation", value={"timeout": 30}, observed_min=1,
                epistemic="observation",
            ),
            2,
        ),
        commit(
            make_event(
                "c1", 2, "correction", value={"timeout": 60}, observed_min=4,
                epistemic="correction", claim_key=key, corrects=["o1"],
                valid_from_min=2, valid_to_min=10,
            ),
            3,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    record = projection.corrections["c1"]
    assert record.claim_key == key
    assert record.target_event_ids == ["o1"]
    assert record.scoped is True
    assert record.author_epistemic == "correction"
    revisions = projection.claims[key]
    assert len(revisions) == 2
    original = next(rev for rev in revisions if rev.source_event_id == "o1")
    assert len(original.invalidated_by) == 1
    assert original.invalidated_by[0].correction_event_id == "c1"
    corrected = next(rev for rev in revisions if rev.source_event_id == "c1")
    assert corrected.authoritative is True
    assert corrected.value == {"timeout": 60}
    # Replay survival: rebuild from the event log reproduces corrections.
    replayed = TaskProjection.rebuild(projection.event_log)
    assert replayed.state_digest() == projection.state_digest()
    assert replayed.corrections["c1"].target_event_ids == ["o1"]
    replayed_original = next(
        rev for rev in replayed.claims[key] if rev.source_event_id == "o1"
    )
    assert len(replayed_original.invalidated_by) == 1


def test_conflict_visible_until_explicitly_resolved() -> None:
    key = f"claim:{SOURCE}:t1:value:port"
    entries = [
        commit(make_event("g", 0, "goal", condition="Bind service port"), 1),
        commit(
            make_event(
                "o1", 1, "observation", value={"port": 8000}, observed_min=1,
                epistemic="observation",
            ),
            2,
        ),
        commit(
            make_event(
                "o2", 2, "observation", value={"port": 9000}, observed_min=2,
                epistemic="observation",
            ),
            3,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    assert len(projection.conflicts) == 1
    conflict = next(iter(projection.conflicts.values()))
    assert conflict.claim_key == key
    assert conflict.status == "open"
    assert len(conflict.revision_ids) == 2
    # An unrelated later observation does not resolve it.
    projection.apply(
        commit(
            make_event(
                "o3", 3, "observation", value={"host": "loopback"}, observed_min=3,
                epistemic="observation",
            ),
            4,
        )
    )
    assert next(iter(projection.conflicts.values())).status == "open"
    # Explicit decision naming the loser resolves it.
    projection.apply(
        commit(
            make_event(
                "d1", 4, "decision", value={"port": 9000}, observed_min=5,
                claim_key=key, supersedes=["o1"],
            ),
            5,
        )
    )
    assert next(iter(projection.conflicts.values())).status == "resolved"
    assert next(iter(projection.conflicts.values())).resolved_by == "d1"


def test_unknown_outage_handling() -> None:
    entries = [
        commit(make_event("g", 0, "goal", condition="Keep serving"), 1),
        commit(
            make_event("off", 1, "source-status", task=None, value={"status": "offline"},
                       observed_min=2),
            2,
        ),
        commit(
            make_event("on", 2, "source-status", task=None, value={"status": "online"},
                       observed_min=9),
            3,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    assert len(projection.unknown_intervals) == 1
    interval = next(iter(projection.unknown_intervals.values()))
    assert interval.open is False
    assert interval.reason == "source-status:offline"
    assert interval.started_at == BASE + timedelta(minutes=2)
    assert interval.ended_at == BASE + timedelta(minutes=9)
    # Absence during the outage is unknown: task status is untouched by it.
    assert projection.tasks["t1"].status == "open"
    # A producer-sequence jump is recorded as a gap, not fabricated content.
    projection.apply(commit(make_event("late", 9, "observation", value={"x": 1}), 4))
    assert len(projection.sequence_gaps) == 1
    gap = next(iter(projection.sequence_gaps.values()))
    assert (gap.expected_sequence, gap.received_sequence) == (3, 9)


def test_pause_resume_interruption_without_outcome() -> None:
    entries = [
        commit(make_event("g", 0, "goal", condition="Migrate store"), 1),
        commit(
            make_event("p", 1, "lifecycle", value={"transition": "pause"}, observed_min=3),
            2,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    assert projection.tasks["t1"].status == "paused"
    assert len(projection.interruptions) == 1
    interruption = next(iter(projection.interruptions.values()))
    assert interruption.status == "open"
    assert interruption.pause_event_id == "p"
    assert interruption.outcome_during_pause is None
    projection.apply(
        commit(
            make_event("r", 2, "lifecycle", value={"transition": "resume"}, observed_min=8),
            3,
        )
    )
    assert projection.tasks["t1"].status == "in-progress"
    assert next(iter(projection.interruptions.values())).status == "resumed"
    assert next(iter(projection.interruptions.values())).resume_event_id == "r"


def test_branch_parentage_and_artifact_revisions() -> None:
    sha_a = "a" * 64
    sha_b = "b" * 64
    entries = [
        commit(make_event("g", 0, "goal", condition="Ship feature"), 1),
        commit(
            make_event(
                "r1", 1, "artifact-revision", branch="b-main",
                artifact_refs=[{"path": "/repo/app.py", "sha256": sha_a,
                                "revision": "r1", "verifier": "harness"}],
            ),
            2,
        ),
        commit(
            make_event(
                "r2", 2, "artifact-revision", branch="b-child", parent_branch="b-main",
                artifact_refs=[{"path": "/repo/app.py", "sha256": sha_b,
                                "revision": "r2", "verifier": "harness"}],
            ),
            3,
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    assert projection.branches["b-child"].parent_branch_id == "b-main"
    assert projection.branches["b-main"].child_branch_ids == ["b-child"]
    assert projection.tasks["t1"].branch_ids == ["b-main", "b-child"]
    history = projection.artifacts["/repo/app.py"]
    assert [entry.revision for entry in history] == ["r1", "r2"]
    assert history[1].verifier == "harness"
    key = f"claim:{SOURCE}:t1:artifact:/repo/app.py"
    assert len(projection.claims[key]) == 2


def test_verified_completion_requires_independent_check() -> None:
    entries = [
        commit(make_event("g", 0, "goal", condition="Pass suite"), 1),
        commit(
            make_event("done", 1, "lifecycle", value={"transition": "complete"}), 2
        ),
    ]
    projection = TaskProjection.rebuild(entries)
    assert projection.tasks["t1"].status == "complete-asserted-unverified"
    assert projection.tasks["t1"].verified_completion is False
    open_obligations = [o for o in projection.obligations.values() if o.status == "open"]
    assert len(open_obligations) == 1
    projection.apply(
        commit(
            make_event(
                "ok", 2, "checked-outcome", outcome="succeeded",
                epistemic="checked-outcome",
                artifact_refs=[{"path": "/repo/x.py", "sha256": "c" * 64,
                                "revision": "r3", "verifier": "external-runner"}],
            ),
            3,
        )
    )
    assert projection.tasks["t1"].verified_completion is True
    assert projection.tasks["t1"].status == "completed"
    assert projection.outcomes["ok"].verified is True
    assert projection.outcomes["ok"].verifier == "external-runner"
    assert all(o.status == "resolved" for o in projection.obligations.values())


# -- independent expected state -----------------------------------------------------


def build_mixed_stream() -> List[CommittedTaskEvent]:
    """Interleaved two-task stream exercising every projected relation."""
    return [
        commit(make_event("g1", 0, "goal", task="t1", condition="Fix login redirect"), 1, 0.5),
        commit(make_event("g2", 1, "goal", task="t2", condition="Add logout button"), 2, 1.5),
        commit(make_event("s1", 2, "lifecycle", task="t1", value={"transition": "start"}), 3, 2.5),
        commit(
            make_event("d1", 3, "assumption-change", task="t1", value={"retries": 1},
                       observed_min=3),
            4, 3.5,
        ),
        commit(
            make_event("d2", 4, "assumption-change", task="t1", value={"retries": 3},
                       observed_min=4),
            5, 4.5,
        ),
        commit(
            make_event("a1", 5, "attempt", task="t1", attempt="att-1", branch="b-main",
                       attempt_record=attempt_record("att-1", "pytest tests/login", 1),
                       outcome="failed"),
            6, 5.5,
        ),
        commit(
            make_event("o1", 6, "checked-outcome", task="t1", attempt="att-1",
                       outcome="failed", epistemic="checked-outcome"),
            7, 6.5,
        ),
        commit(
            make_event("p1", 7, "lifecycle", task="t1", value={"transition": "pause"},
                       observed_min=7),
            8, 7.5,
        ),
        commit(
            make_event("q1", 8, "observation", task="t1", outcome="unknown",
                       condition="Why did the redirect loop?", observed_min=8,
                       epistemic="observation"),
            9, 8.5,
        ),
        commit(
            make_event(
                "r1", 9, "artifact-revision", task="t2", branch="b-child",
                parent_branch="b-main",
                artifact_refs=[{"path": "/repo/app.py", "sha256": "d" * 64,
                                "revision": "r7", "verifier": "harness"}],
            ),
            10, 9.5,
        ),
        commit(
            make_event("stray", 10, "observation", task=None, session="s9",
                       value={"note": "untracked"}, observed_min=10),
            11, 10.5,
        ),
    ]


def assert_matches_independent_expectation(projection: TaskProjection) -> None:
    """Hand-written expected state (E2: not just mutual agreement)."""
    # Tasks.
    assert set(projection.tasks) == {"t1", "t2"}
    assert projection.tasks["t1"].goal == "Fix login redirect"
    assert projection.tasks["t1"].status == "paused"
    assert projection.tasks["t1"].attempt_ids == ["att-1"]
    assert projection.tasks["t2"].status == "open"
    # Attempts and outcomes.
    assert projection.attempts["att-1"].command_identity == "pytest tests/login"
    assert projection.attempts["att-1"].exit_status == 1
    assert projection.attempts["att-1"].outcome == "failed"
    assert projection.attempts["att-1"].outcome_verified is True
    assert projection.outcomes["o1"].polarity == "failed"
    # Assumption supersession.
    key = f"claim:{SOURCE}:t1:value:retries"
    revisions = projection.claims[key]
    assert [rev.value for rev in revisions] == [{"retries": 1}, {"retries": 3}]
    assert revisions[0].superseded_by == revisions[1].revision_id
    # Obligations and questions.
    assert sum(1 for o in projection.obligations.values() if o.status == "open") == 3
    assert sum(1 for q in projection.open_questions.values() if q.status == "open") == 1
    question = next(iter(projection.open_questions.values()))
    assert question.question == "Why did the redirect loop?"
    # Interruptions.
    assert len(projection.interruptions) == 1
    interruption = next(iter(projection.interruptions.values()))
    assert (interruption.task_id, interruption.status) == ("t1", "open")
    # Episodes: explicit task IDs lead; the stray is provisional heuristic.
    assert projection.episodes["episode:task:t1"].provisional is False
    assert projection.episodes["episode:task:t1"].boundary == "explicit-task"
    stray = projection.episodes["episode:session:s9"]
    assert stray.provisional is True
    assert stray.boundary == "heuristic-provisional"
    assert stray.event_ids == ["stray"]
    # Branches and artifacts.
    assert projection.branches["b-child"].parent_branch_id == "b-main"
    assert [e.revision for e in projection.artifacts["/repo/app.py"]] == ["r7"]
    # Watermark and times.
    assert projection.watermark == 11
    assert projection.tasks["t1"].last_commit_seq == 9
    timeline_ids = [entry.event_id for entry in projection.timeline]
    assert timeline_ids == ["g1", "g2", "s1", "d1", "d2", "a1", "o1", "p1", "q1", "r1", "stray"]


def test_incremental_vs_cold_rebuild_agreement_with_independent_expected_state() -> None:
    entries = build_mixed_stream()
    incremental = TaskProjection()
    for entry in entries:
        incremental.apply(entry)
    assert_matches_independent_expectation(incremental)
    cold = TaskProjection.rebuild(list(reversed(entries)))
    assert_matches_independent_expectation(cold)
    assert cold.state_digest() == incremental.state_digest()
    # Idempotent re-application changes nothing.
    for entry in entries:
        incremental.apply(entry)
    assert incremental.state_digest() == cold.state_digest()


def test_deterministic_stable_ids_across_rebuilds() -> None:
    entries = build_mixed_stream()
    first = TaskProjection.rebuild(entries)
    second = TaskProjection.rebuild(list(reversed(entries)))

    def identifiers(projection: TaskProjection) -> Dict[str, List[str]]:
        return {
            "revisions": sorted(
                rev.revision_id for revs in projection.claims.values() for rev in revs
            ),
            "obligations": sorted(projection.obligations),
            "questions": sorted(projection.open_questions),
            "conflicts": sorted(projection.conflicts),
            "interruptions": sorted(projection.interruptions),
            "episodes": sorted(projection.episodes),
        }

    assert identifiers(first) == identifiers(second)
    assert first.state_digest() == second.state_digest()
    # Revision identities are distinct per version.
    key = f"claim:{SOURCE}:t1:value:retries"
    assert first.claims[key][0].revision_id != first.claims[key][1].revision_id


def test_committed_stream_adapter_over_sqlite_store(tmp_path) -> None:
    """Task events committed through the real SQLite store project correctly."""
    from entorhinal.evidence.receipts import CommitState
    from entorhinal.evidence.sqlite_store import SQLiteEvidenceStore
    from entorhinal.schemas.models import (
        ClassificationLevel,
        EvidenceRecord,
        SourceType,
        generate_uuidv7,
    )

    store = SQLiteEvidenceStore(tmp_path / "evidence.db")
    try:
        dicts = [
            make_event("g1", 0, "goal", task="t1", condition="Fix login redirect"),
            make_event("s1", 1, "lifecycle", task="t1", value={"transition": "start"}),
        ]
        receipts = []
        for candidate in dicts:
            event = TaskEvent.model_validate(candidate)
            signal = event.to_raw_signal_event()
            record = EvidenceRecord(
                record_id=generate_uuidv7(),
                schema_version="1.0.0",
                persisted_at=BASE,
                source_type=SourceType.TERMINAL_PTY,
                app_identifier="dev-task:test",
                window_title=None,
                target_uri=None,
                sanitized_payload=signal.raw_payload,
                classification=ClassificationLevel.INTERNAL,
                provenance_hash="0" * 64,
                previous_record_hash="0" * 64,
            )
            receipt = store.commit_event_sync(
                source_id=SOURCE,
                event_id=event.event_id,
                record=record,
                observed_at=event.time.observed_at,
                received_at=BASE,
                source_seq=event.time.source_sequence,
                clock_domain=event.time.clock_domain,
            )
            assert receipt.state == CommitState.COMMITTED_PROJECTED
            receipts.append(receipt)
        import asyncio

        stored = asyncio.run(store.scan_evidence(limit=10))
        assert len(stored) == 2
        by_event = {receipt.event_id: receipt for receipt in receipts}
        projection = TaskProjection()
        for record in stored:
            event_id = (record.sanitized_payload or {}).get("event_id")
            receipt = by_event[event_id]
            assert receipt.commit_seq is not None and receipt.committed_at is not None
            entry = CommittedTaskEvent.from_evidence_record(
                record,
                commit_seq=receipt.commit_seq,
                committed_at=receipt.committed_at,
                received_at=BASE,
            )
            assert entry is not None
            projection.apply(entry)
        assert projection.tasks["t1"].goal == "Fix login redirect"
        assert projection.tasks["t1"].status == "open"
        assert projection.watermark == 2
        # Non-task payloads are skipped visibly, not crashed on.
        other = EvidenceRecord(
            record_id=generate_uuidv7(),
            schema_version="1.0.0",
            persisted_at=BASE,
            source_type=SourceType.OS_WINDOW,
            app_identifier="other",
            window_title=None,
            target_uri=None,
            sanitized_payload={"not": "a task event"},
            classification=ClassificationLevel.INTERNAL,
            provenance_hash="0" * 64,
            previous_record_hash="0" * 64,
        )
        assert (
            CommittedTaskEvent.from_evidence_record(
                other, commit_seq=99, committed_at=BASE
            )
            is None
        )
    finally:
        store.close()
