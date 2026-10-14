"""M2 resumption-packet tests (E2/E3): bounded advisory consumer packets.

Uses tmp_path fixtures only; never touches the live capture daemon.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from entorhinal.schemas.task_event import DEV_TASK_SOURCE_ID, TaskEvent
from entorhinal.temporal.packet import (
    EXCERPT_SELECTION_V1,
    EXCERPT_SELECTION_V2,
    PacketRequest,
    ResumptionPacketBuilder,
    count_chars,
    count_tokens,
)
from entorhinal.temporal.projection import CommittedTaskEvent, TaskProjection

GRANT = "m2-test-grant"
SOURCE = DEV_TASK_SOURCE_ID
BASE = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


def make_event(
    event_id: str,
    sequence: int,
    kind: str,
    *,
    task: Optional[str] = "t-resume",
    session: str = "s1",
    attempt: Optional[str] = None,
    observed_min: Optional[float] = 0.0,
    value: Optional[Dict[str, Any]] = None,
    condition: Optional[str] = None,
    outcome: Optional[str] = None,
    epistemic: str = "assertion",
    claim_key: Optional[str] = None,
    corrects: Optional[List[str]] = None,
    supersedes: Optional[List[str]] = None,
    attempt_record: Optional[Dict[str, Any]] = None,
    excerpts: Optional[List[Dict[str, Any]]] = None,
    artifact_refs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    observed = BASE + timedelta(minutes=observed_min) if observed_min is not None else None
    work: Dict[str, Any] = {"session_id": session}
    if task is not None:
        work["task_id"] = task
    if attempt is not None:
        work["attempt_id"] = attempt
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


def build_resumption_fixture() -> List[CommittedTaskEvent]:
    """Fixed multi-event fixture: failed attempt, changed assumption, pause."""
    return [
        commit(
            make_event("g", 0, "goal", condition="Fix login redirect",
                       excerpts=[{"label": "goal", "text": "Fix login redirect"}]),
            1, 0.5,
        ),
        commit(
            make_event("s", 1, "lifecycle", value={"transition": "start"}), 2, 1.5
        ),
        commit(
            make_event("a0", 2, "assumption-change", value={"retries": 1}, observed_min=2),
            3, 2.5,
        ),
        commit(
            make_event(
                "att1", 3, "attempt", attempt="att-1",
                attempt_record={
                    "attempt_id": "att-1",
                    "command_identity": "pytest tests/login",
                    "check_identity": "pytest",
                    "started_at": BASE.isoformat(),
                    "ended_at": (BASE + timedelta(minutes=4)).isoformat(),
                    "exit_status": 1,
                },
                outcome="failed",
                excerpts=[{"label": "failure", "text": "1 failed: redirect loop"}],
            ),
            4, 3.5,
        ),
        commit(
            make_event("o1", 4, "checked-outcome", attempt="att-1", outcome="failed",
                       epistemic="checked-outcome",
                       artifact_refs=[{"path": "/repo/app.py", "sha256": "e" * 64,
                                       "revision": "r11", "verifier": "harness"}]),
            5, 4.5,
        ),
        commit(
            make_event("a1", 5, "assumption-change", value={"retries": 3}, observed_min=5),
            6, 5.5,
        ),
        commit(
            make_event("q1", 6, "observation", outcome="unknown",
                       condition="Why did the redirect loop?", observed_min=6,
                       epistemic="observation"),
            7, 6.5,
        ),
        commit(
            make_event("z1", 7, "observation", value={"zone": "a"}, observed_min=7,
                       epistemic="observation"),
            8, 7.5,
        ),
        commit(
            make_event("z2", 8, "observation", value={"zone": "b"}, observed_min=8,
                       epistemic="observation"),
            9, 8.5,
        ),
        commit(
            make_event("p1", 9, "lifecycle", value={"transition": "pause"}, observed_min=9,
                       excerpts=[{"label": "pause-note", "text": "pausing for review"}]),
            10, 9.5,
        ),
    ]


# -- fixed-fixture demonstration ------------------------------------------------------------


def test_packet_on_fixed_fixture_with_printed_example(capsys) -> None:
    projection = TaskProjection.rebuild(build_resumption_fixture())
    builder = ResumptionPacketBuilder(projection)
    packet = builder.build(
        PacketRequest(task_id="t-resume", include_hypotheses=True, ttl_seconds=300)
    )
    print("\n=== M2 example resumption packet ===")
    print(json.dumps(json.loads(packet.serialize()), indent=2)[:4000])
    captured = capsys.readouterr()
    assert "M2 example resumption packet" in captured.out
    # Key fields asserted on the demonstrated packet.
    assert packet.task_state.task_id == "t-resume"
    assert packet.task_state.goal == "Fix login redirect"
    assert packet.task_state.status == "paused"
    assert packet.task_state.open_interruption_ids != []
    assert any(
        item.claim_key.endswith(":value:retries") and item.revision_count == 2
        for item in packet.changed_assumptions
    )
    assert len(packet.prior_attempts) == 1
    attempt = packet.prior_attempts[0]
    assert attempt.attempt_id == "att-1"
    assert attempt.outcome == "failed"
    assert attempt.observed_command_identity == "pytest tests/login"
    assert attempt.artifact_revisions == []
    assert attempt.outcome_event_ids == ["o1"]
    assert any(o.status == "open" for o in packet.open_obligations)
    assert any(q.question == "Why did the redirect loop?" for q in packet.open_questions)
    assert any(e.label == "failure" for e in packet.supporting_excerpts)
    assert any(c.claim_key.endswith(":value:zone") for c in packet.conflicts)
    assert all(h.is_hypothesis for h in packet.hypotheses)
    assert packet.hypotheses != []
    assert packet.metadata.watermark == 10
    assert packet.metadata.projection_identity == "temporal-projection/1"
    assert packet.metadata.expires_at is not None
    assert packet.metadata.deletion_generation == 0
    assert packet.disclaimer.startswith("ADVISORY ONLY")
    # Budget counted on the real serialization.
    serialized = packet.serialize()
    assert packet.budget.used_chars == count_chars(serialized)
    assert packet.budget.used_tokens == count_tokens(serialized)
    assert packet.budget.used_chars <= (packet.budget.budget_chars or 0)
    assert packet.budget.overflow is False
    assert packet.metadata.packet_hash != ""


def test_deterministic_packet_id_across_rebuilds() -> None:
    entries = build_resumption_fixture()
    first = ResumptionPacketBuilder(TaskProjection.rebuild(entries)).build(
        PacketRequest(task_id="t-resume")
    )
    second = ResumptionPacketBuilder(TaskProjection.rebuild(list(reversed(entries)))).build(
        PacketRequest(task_id="t-resume")
    )
    assert first.packet_id == second.packet_id
    assert first.metadata.projection_digest == second.metadata.projection_digest


def test_budget_enforcement_and_overflow_disclosure() -> None:
    projection = TaskProjection.rebuild(build_resumption_fixture())
    builder = ResumptionPacketBuilder(projection)
    packet = builder.build(
        PacketRequest(task_id="t-resume", include_hypotheses=True,
                      budget_chars=1500, budget_tokens=None)
    )
    assert packet.budget.overflow is True
    assert packet.omissions != []
    assert packet.budget.omission_count == len(packet.omissions)
    # Hypotheses (lowest priority) are disclosed as pruned first.
    assert packet.hypotheses == []
    assert any(item.section == "hypotheses" for item in packet.omissions)
    # Counts always describe the ACTUAL final serialization.
    serialized = packet.serialize()
    assert packet.budget.used_chars == count_chars(serialized)
    assert packet.budget.used_tokens == count_tokens(serialized)
    # Mandatory core survives: task state + obligations + metadata.
    assert packet.task_state.task_id == "t-resume"
    assert packet.open_obligations != []
    assert packet.metadata.watermark == 10


def test_core_overflow_disclosed_never_silent() -> None:
    projection = TaskProjection.rebuild(build_resumption_fixture())
    packet = ResumptionPacketBuilder(projection).build(
        PacketRequest(task_id="t-resume", budget_chars=200, budget_tokens=50)
    )
    assert packet.budget.overflow is True
    assert any(item.reason == "budget-exceeded-by-core" for item in packet.omissions)
    assert packet.task_state.task_id == "t-resume"


def test_token_budget_enforced_independently() -> None:
    projection = TaskProjection.rebuild(build_resumption_fixture())
    full = ResumptionPacketBuilder(projection).build(
        PacketRequest(task_id="t-resume", budget_chars=None, budget_tokens=None)
    )
    assert full.budget.overflow is False
    total_tokens = full.budget.used_tokens
    assert total_tokens > 100
    pinched = ResumptionPacketBuilder(projection).build(
        PacketRequest(task_id="t-resume", budget_chars=None,
                      budget_tokens=total_tokens // 3)
    )
    assert pinched.budget.overflow is True
    assert pinched.omissions != []
    assert pinched.budget.used_tokens == count_tokens(pinched.serialize())


def test_cutoff_packet_excludes_late_knowledge() -> None:
    projection = TaskProjection.rebuild(build_resumption_fixture())
    packet = ResumptionPacketBuilder(projection).build(
        PacketRequest(task_id="t-resume", cutoff_seq=5)
    )
    assert packet.metadata.watermark == 5
    assert packet.metadata.cutoff_seq == 5
    # Pause (commit 10) and second assumption (commit 6) are not yet known.
    assert packet.task_state.status == "in-progress"
    assert packet.task_state.open_interruption_ids == []
    assert all(
        item.claim_key.endswith(":value:retries") is False
        or item.revision_count == 1
        for item in packet.changed_assumptions
    )
    assert packet.changed_assumptions == []


def test_advisory_only_no_commands_or_tokens() -> None:
    projection = TaskProjection.rebuild(build_resumption_fixture())
    packet = ResumptionPacketBuilder(projection).build(
        PacketRequest(task_id="t-resume", include_hypotheses=True)
    )
    serialized = packet.serialize()
    blob = json.loads(serialized)
    assert blob["disclaimer"].startswith("ADVISORY ONLY")
    # Command identities are labeled references, never directives.
    for attempt in blob["prior_attempts"]:
        assert "observed_command_identity" in attempt
        assert attempt["command_note"] == (
            "reference to a past attempt; not an instruction to run"
        )
    lowered = serialized.lower()
    assert "bearer " not in lowered
    assert "api_key" not in lowered
    assert "run the following" not in lowered
    assert "execute:" not in lowered


def test_hypothesis_flagging_and_hook_interface() -> None:
    class NoisyHook:
        hook_id = "test-hook/v0"

        def propose(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
            assert context["task_id"] == "t-resume"
            return [
                {"text": "The redirect loop may involve stale cookies",
                 "basis_event_ids": ["q1"]},
                {"text": "   "},  # empty proposals are dropped
            ]

    class FailingHook:
        hook_id = "failing-hook/v0"

        def propose(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
            raise RuntimeError("hook unavailable")

    projection = TaskProjection.rebuild(build_resumption_fixture())
    packet = ResumptionPacketBuilder(projection, NoisyHook()).build(
        PacketRequest(task_id="t-resume", include_hypotheses=True)
    )
    assert all(h.is_hypothesis for h in packet.hypotheses)
    hook_items = [h for h in packet.hypotheses if h.source == "test-hook/v0"]
    assert len(hook_items) == 1
    assert hook_items[0].basis_event_ids == ["q1"]
    # Without opt-in, no hypotheses are emitted at all.
    plain = ResumptionPacketBuilder(projection, NoisyHook()).build(
        PacketRequest(task_id="t-resume", include_hypotheses=False)
    )
    assert plain.hypotheses == []
    # A failing hook degrades to no hook output, never a failed packet.
    degraded = ResumptionPacketBuilder(projection, FailingHook()).build(
        PacketRequest(task_id="t-resume", include_hypotheses=True)
    )
    assert all(h.source == "projection-derivation" for h in degraded.hypotheses)


def test_packet_metadata_completeness() -> None:
    projection = TaskProjection.rebuild(build_resumption_fixture())
    packet = ResumptionPacketBuilder(projection).build(
        PacketRequest(task_id="t-resume", ttl_seconds=120,
                      max_evidence_age_seconds=10**9)
    )
    metadata = packet.metadata
    assert metadata.store_identity == "sqlite-store/1"
    assert metadata.projection_identity == "temporal-projection/1"
    assert metadata.projection_version == "1.0.0"
    assert metadata.projection_digest == projection.state_digest()
    assert metadata.watermark == 10
    assert metadata.issued_at is not None and metadata.expires_at is not None
    assert (metadata.expires_at - metadata.issued_at).total_seconds() == 120
    assert metadata.source_freshness["sources_seen"] == [SOURCE]
    assert metadata.freshness_met is True
    assert metadata.deletion_generation == 0
    assert metadata.revocation_generation == 0
    # Missing evidence against a freshness requirement is disclosed, not
    # hidden (deterministic regardless of wall clock).
    stale = ResumptionPacketBuilder(TaskProjection()).build(
        PacketRequest(task_id="t-missing", max_evidence_age_seconds=100)
    )
    assert stale.metadata.freshness_met is False
    assert stale.metadata.source_freshness["stale_reason"] == (
        "no observed evidence in scope"
    )


# -- excerpt-selection versions (F-R2-1 repair) -------------------------------------------


def build_excerpt_shape_fixture(pad: int = 0) -> List[CommittedTaskEvent]:
    """Decision/correction older than lifecycle chatter (A-ep19 shape).

    Commit order (oldest first): goal, decision, correction, command tail,
    observation, verifier report, unseen label, lifecycle pause note.
    ``pad`` normalizes every excerpt text to exactly that many characters
    (for deterministic partial-pruning budgets).
    """
    def _t(text: str) -> str:
        return text.ljust(pad, "x")[:pad] if pad else text

    gc = _t("Build a log-line parser")
    dc = _t("DECISION: quoted spans are single fields; backslash escapes "
           "whitespace outside spans")
    cc = _t("CORRECTION: empty spans yield empty-string fields")
    ac = _t("2 failed, 4 passed")
    oc = _t("suite red on quoting tests")
    vc = _t("failing: test_quoted_span")
    uc = _t("unclassified content")
    lc = _t("pausing with suite red")
    assert len({len(t) for t in (gc, dc, cc, ac, oc, vc, uc, lc)}) == 1 if pad else True
    return [
        commit(
            make_event("g", 0, "goal", condition="Parse log lines",
                       excerpts=[{"label": "goal-statement", "text": gc}]),
            1, 0.5,
        ),
        commit(
            make_event("d1", 1, "observation", observed_min=1,
                       epistemic="observation",
                       excerpts=[{"label": "decision-statement",
                                  "text": dc}]),
            2, 1.5,
        ),
        commit(
            make_event("c1", 2, "observation", observed_min=2,
                       epistemic="observation",
                       excerpts=[{"label": "correction-statement",
                                  "text": cc}]),
            3, 2.5,
        ),
        commit(
            make_event("a1", 3, "observation", observed_min=3,
                       epistemic="observation",
                       excerpts=[{"label": "command-output-tail",
                                  "text": ac}]),
            4, 3.5,
        ),
        commit(
            make_event("o1", 4, "observation", observed_min=4,
                       epistemic="observation",
                       excerpts=[{"label": "observation-statement",
                                  "text": oc}]),
            5, 4.5,
        ),
        commit(
            make_event("v1", 5, "observation", observed_min=5,
                       epistemic="observation",
                       excerpts=[{"label": "verifier-report",
                                  "text": vc}]),
            6, 5.5,
        ),
        commit(
            make_event("u1", 6, "observation", observed_min=6,
                       epistemic="observation",
                       excerpts=[{"label": "future-unseen-label",
                                  "text": uc}]),
            7, 6.5,
        ),
        commit(
            make_event("p1", 7, "lifecycle", value={"transition": "pause"},
                       observed_min=7,
                       excerpts=[{"label": "lifecycle-statement",
                                  "text": lc}]),
            8, 7.5,
        ),
    ]


def test_v1_oldest_first_frozen() -> None:
    """v1 (frozen): oldest excerpt pruned first regardless of signal class.

    This pins the F-R2-1 mechanism: the decision (commit 2) is pruned at
    step 2 while the newer lifecycle chatter (commit 8) is still kept.
    """
    projection = TaskProjection.rebuild(build_excerpt_shape_fixture())
    builder = ResumptionPacketBuilder(projection)
    packet = builder.build(
        PacketRequest(task_id="t-resume", budget_chars=None,
                      budget_tokens=None,
                      excerpt_selection=EXCERPT_SELECTION_V1)
    )
    assert [e.label for e in packet.supporting_excerpts][0] == "goal-statement"
    first = builder._prune_excerpt(packet, EXCERPT_SELECTION_V1)
    assert first.section == "supporting_excerpts"
    assert first.item_id.endswith(":goal-statement")
    assert first.detail == "oldest excerpt pruned first"
    second = builder._prune_excerpt(packet, EXCERPT_SELECTION_V1)
    assert second.item_id.endswith(":decision-statement")
    assert any(e.label == "lifecycle-statement"
               for e in packet.supporting_excerpts)


def test_v2_prune_order_retains_decisions_over_chatter() -> None:
    """v2: lowest signal class pruned first, oldest within class."""
    projection = TaskProjection.rebuild(build_excerpt_shape_fixture())
    builder = ResumptionPacketBuilder(projection)
    packet = builder.build(
        PacketRequest(task_id="t-resume", budget_chars=None,
                      budget_tokens=None,
                      excerpt_selection=EXCERPT_SELECTION_V2)
    )
    victims = []
    while packet.supporting_excerpts:
        omission = builder._prune_excerpt(packet, EXCERPT_SELECTION_V2)
        assert omission.section == "supporting_excerpts"
        assert "excerpt-selection/2" in omission.detail
        victims.append(omission.item_id.split(":", 1)[1])
    assert victims == [
        "lifecycle-statement",
        "goal-statement",
        "command-output-tail",
        "observation-statement",
        "verifier-report",
        "future-unseen-label",
        "decision-statement",
        "correction-statement",
    ]


def test_v2_budget_pruning_keeps_decision_until_last() -> None:
    """Public-build property: a pruned decision implies nothing else kept."""
    projection = TaskProjection.rebuild(build_excerpt_shape_fixture(pad=600))
    builder = ResumptionPacketBuilder(projection)
    full = builder.build(
        PacketRequest(task_id="t-resume", budget_chars=None,
                      budget_tokens=None,
                      excerpt_selection=EXCERPT_SELECTION_V2)
    )
    assert full.budget.overflow is False
    # Uniform ~700-char excerpts vs ~140-char omissions: a 1000-char pinch
    # forces exactly two excerpt prunes (one frees ~560 < 1000, two ~1120).
    packet = builder.build(
        PacketRequest(task_id="t-resume",
                      budget_chars=full.budget.used_chars - 1000,
                      budget_tokens=None,
                      excerpt_selection=EXCERPT_SELECTION_V2)
    )
    assert packet.budget.overflow is True
    kept = [e.label for e in packet.supporting_excerpts]
    omitted = [o.item_id.split(":", 1)[1] for o in packet.omissions
               if o.section == "supporting_excerpts"]
    assert omitted != []
    # Lowest rank goes first: any excerpt pruning drops lifecycle chatter.
    assert "lifecycle-statement" in omitted
    # Decision survives unless every excerpt is gone.
    assert kept == [] or "decision-statement" in kept
    # Every omission is explicit with its reason.
    assert all(o.reason == "budget-prune" for o in packet.omissions
               if o.section == "supporting_excerpts")


def test_unknown_excerpt_selection_rejected() -> None:
    projection = TaskProjection.rebuild(build_excerpt_shape_fixture())
    with pytest.raises(ValueError, match="unknown excerpt_selection"):
        ResumptionPacketBuilder(projection).build(
            PacketRequest(task_id="t-resume", excerpt_selection="bogus")
        )


def test_omission_ledger_compacts_past_cap() -> None:
    """The omission ledger is bounded: oldest entries elide into a summary."""
    from entorhinal.temporal.packet import OMISSION_SUMMARY_REASON
    events = [
        commit(
            make_event(f"d{i}", i, "decision", observed_min=float(i),
                       value={"choice": f"choice-{i:02d}"},
                       excerpts=[{"label": "decision-statement",
                                  "text": f"decision number {i:02d} with padding " + "x" * 120}]),
            100 + i, float(i),
        )
        for i in range(20)
    ]
    projection = TaskProjection.rebuild(events)
    packet = ResumptionPacketBuilder(projection).build(
        PacketRequest(task_id="t-resume", budget_chars=None, budget_tokens=1400)
    )
    assert packet.budget.overflow is True
    summaries = [o for o in packet.omissions if o.reason == OMISSION_SUMMARY_REASON]
    assert len(summaries) == 1
    assert "items pruned in total" in summaries[0].detail
    assert len(packet.omissions) <= 14
    # Most recent drops retained longest: newest decision excerpt survives.
    assert any("decision number 19" in e.text for e in packet.supporting_excerpts)


def test_default_excerpt_selection_is_v2_with_v1_reproducible() -> None:
    """Round-3 repair: the live product default prunes as v2; v1 stays explicit."""
    assert PacketRequest(task_id="t-resume").excerpt_selection == EXCERPT_SELECTION_V2
    projection = TaskProjection.rebuild(build_excerpt_shape_fixture(pad=600))
    builder = ResumptionPacketBuilder(projection)
    full = builder.build(
        PacketRequest(task_id="t-resume", budget_chars=None, budget_tokens=None)
    )
    pinch = full.budget.used_chars - 1000
    defaulted = builder.build(
        PacketRequest(task_id="t-resume", budget_chars=pinch, budget_tokens=None)
    )
    explicit_v2 = builder.build(
        PacketRequest(task_id="t-resume", budget_chars=pinch, budget_tokens=None,
                      excerpt_selection=EXCERPT_SELECTION_V2)
    )
    assert [o.item_id for o in defaulted.omissions] == [
        o.item_id for o in explicit_v2.omissions
    ]
    assert any(
        o.item_id.endswith(":lifecycle-statement") for o in defaulted.omissions
    )
    explicit_v1 = builder.build(
        PacketRequest(task_id="t-resume", budget_chars=pinch, budget_tokens=None,
                      excerpt_selection=EXCERPT_SELECTION_V1)
    )
    assert any(o.item_id.endswith(":goal-statement") for o in explicit_v1.omissions)
