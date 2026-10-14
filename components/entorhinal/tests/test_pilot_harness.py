"""M3 pilot harness tests: freeze, conditions C0-C4, trial scaffold.

Uses tmp_path fixtures only with small synthetic TaskEvents constructed
here; never touches the live capture daemon or its inbox/store.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pilot.conditions import (  # noqa: E402
    PRIMARY_BUDGET_TOKENS,
    SENSITIVITY_BUDGET_TOKENS,
    TOKENIZER_ID,
    FrozenPrefix,
    build_all_conditions,
    build_c0,
    build_c1,
    build_c2,
    build_c3,
    build_c4,
    corpus_units,
)
from pilot.freeze import (  # noqa: E402
    FreezeError,
    freeze_case,
    verify_frozen_case,
)
from pilot.trial import (  # noqa: E402
    ConsumerInput,
    ConsumerOutput,
    TrialError,
    VerifierInput,
    reset_workdir,
    run_trial,
)

BASE = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
SOURCE = "entorhinal.dev-task.01"
GRANT = "pilot-test-grant"


def make_event(
    event_id: str,
    sequence: int,
    kind: str,
    *,
    task: Optional[str] = "task-a",
    session: str = "sess-t",
    attempt: Optional[str] = None,
    observed_min: float = 0.0,
    value: Optional[Dict[str, Any]] = None,
    condition: Optional[str] = None,
    outcome: Optional[str] = None,
    epistemic: str = "assertion",
    claim_key: Optional[str] = None,
    excerpts: Optional[List[Dict[str, Any]]] = None,
    attempt_record: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    observed = BASE + timedelta(minutes=observed_min)
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
    if excerpts is not None:
        payload["excerpts"] = excerpts
    if attempt_record is not None:
        payload["attempt"] = attempt_record
    revision: Dict[str, Any] = {}
    if claim_key is not None:
        revision["claim_key"] = claim_key
    return {
        "contract_version": "entorhinal.task-event/v1-draft",
        "source_id": SOURCE,
        "event_id": event_id,
        "producer_run_id": "run-pilot-test",
        "producer_sequence": sequence,
        "producer_version": "pilot-test-emitter/v0",
        "work": work,
        "kind": kind,
        "time": {
            "observed_at": observed.isoformat(),
            "received_at": None,
            "committed_at": None,
            "clock_domain": "test-clock",
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


def prefix_events() -> List[Dict[str, Any]]:
    return [
        make_event("t-goal-a", 0, "goal", task="task-a",
                   value={"goal": "fix flaky retry test"}, observed_min=0.0),
        make_event("t-start-a", 1, "lifecycle", task="task-a",
                   value={"transition": "start"}, observed_min=1.0),
        make_event("t-attempt-1", 2, "attempt", task="task-a", attempt="att-1",
                   attempt_record={
                       "attempt_id": "att-1",
                       "command_identity": "pytest tests/test_retry.py -x",
                       "check_identity": "pytest",
                       "started_at": (BASE + timedelta(minutes=2)).isoformat(),
                       "ended_at": (BASE + timedelta(minutes=3)).isoformat(),
                       "exit_status": 1,
                       "working_directory": "/work/widget",
                   },
                   observed_min=3.0),
        make_event("t-outcome-1", 3, "checked-outcome", task="task-a",
                   attempt="att-1", outcome="failed",
                   condition="retry backoff assertion",
                   excerpts=[{"label": "tail",
                              "text": "FAILED test_backoff - assert 3 == 5"}],
                   observed_min=4.0),
        make_event("t-decision", 4, "decision", task="task-a",
                   value={"decision": "raise max retries to 5"},
                   claim_key="claim:config:max-retries", observed_min=5.0),
        make_event("t-goal-b", 5, "goal", task="task-b",
                   value={"goal": "document retry config"}, observed_min=6.0),
        make_event("t-pause-a", 6, "lifecycle", task="task-a",
                   value={"transition": "pause"}, observed_min=7.0),
    ]


def future_event() -> Dict[str, Any]:
    return make_event("t-future-outcome", 7, "checked-outcome", task="task-a",
                      attempt="att-2", outcome="succeeded",
                      condition="retry backoff assertion after fix",
                      excerpts=[{"label": "tail", "text": "FUTURE-SECRET outcome"}],
                      observed_min=9.0)


def commit_events(store_path: Path, events: List[Dict[str, Any]], start: int = 0) -> None:
    from entorhinal.evidence.sqlite_store import SQLiteEvidenceStore
    from entorhinal.schemas.models import (
        ClassificationLevel,
        EvidenceRecord,
        SourceType,
    )

    store = SQLiteEvidenceStore(store_path)
    try:
        for order, event in enumerate(events, start=start):
            record = EvidenceRecord(
                record_id=f"pilot-rec-{order:03d}-{event['event_id']}",
                schema_version="1.0.0",
                persisted_at=BASE + timedelta(minutes=order),
                source_type=SourceType.TERMINAL_PTY,
                app_identifier="pilot-test",
                sanitized_payload=event,
                classification=ClassificationLevel.INTERNAL,
                provenance_hash="0" * 64,
                previous_record_hash="0" * 64,
            )
            receipt = store.commit_event_sync(
                source_id=SOURCE,
                event_id=event["event_id"],
                record=record,
                observed_at=BASE + timedelta(minutes=order),
                received_at=BASE + timedelta(minutes=order),
                source_seq=order,
                clock_domain="test-clock",
            )
            assert receipt.committed, f"commit failed: {receipt.reason}"
    finally:
        store.close()


def make_workdir(root: Path, *, backdate_s: float = 3600.0) -> Path:
    """Create the starting workdir with mtimes safely before any commit time."""
    src = root / "workdir_src"
    (src / "conf").mkdir(parents=True, exist_ok=True)
    (src / "conf" / "retry.yaml").write_text("max_retries: 3\n", encoding="utf-8")
    (src / "NOTES.md").write_text("# notes\n", encoding="utf-8")
    old = datetime.now(timezone.utc).timestamp() - backdate_s
    for path in (src / "conf" / "retry.yaml", src / "NOTES.md"):
        os.utime(path, (old, old))
    return src


def freeze_fixture(tmp_path: Path, cutoff: int = 7) -> Path:
    workdir_src = make_workdir(tmp_path)  # workdir state must predate commits
    store_path = tmp_path / "store.db"
    commit_events(store_path, prefix_events())
    case_dir = tmp_path / "case-t-01"
    freeze_case(
        store_path=store_path,
        cutoff_seq=cutoff,
        workdir_src=workdir_src,
        out_dir=case_dir,
        case_id="case-t-01",
        journey="previous-failure-recovery",
        task_id="task-a",
        requirement="retry backoff test passes",
        verifier_procedure="run pytest tests/test_retry.py; pass iff exit 0",
        task_prompt="Resume task-a: fix flaky retry test.",
        fresh_observation="conf/retry.yaml pins max_retries=3 at cutoff.",
    )
    return case_dir


# ---------------------------------------------------------------------------
# Freeze: future exclusion + fail-closed
# ---------------------------------------------------------------------------


def test_freeze_excludes_post_cutoff_event_and_newer_file(tmp_path: Path) -> None:
    workdir_src = make_workdir(tmp_path)  # eligible state predates commits
    store_path = tmp_path / "store.db"
    commit_events(store_path, prefix_events())
    cutoff = len(prefix_events())
    # Plant the future AFTER the cutoff commit exists, then freeze at K.
    commit_events(store_path, [future_event()], start=cutoff)
    # Plant a file modified after the cutoff time.
    planted = workdir_src / "FUTURE.txt"
    planted.write_text("future bytes", encoding="utf-8")
    os.utime(planted, (datetime.now(timezone.utc).timestamp() + 3600,) * 2)

    case_dir = tmp_path / "case-future"
    frozen = freeze_case(
        store_path=store_path,
        cutoff_seq=cutoff,
        workdir_src=workdir_src,
        out_dir=case_dir,
        case_id="case-future",
        journey="changed-assumptions",
        task_id="task-a",
        requirement="retry backoff test passes",
        verifier_procedure="run pytest; pass iff exit 0",
    )
    assert frozen.event_count == cutoff
    assert "FUTURE.txt" in frozen.excluded_files

    exported = (case_dir / "prefix" / "events.jsonl").read_text(encoding="utf-8")
    assert "FUTURE-SECRET" not in exported
    assert "t-future-outcome" not in exported
    assert not (case_dir / "workdir" / "FUTURE.txt").exists()
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["cutoff_seq"] == cutoff
    assert all(entry["commit_seq"] <= cutoff for entry in
               (json.loads(line) for line in exported.splitlines() if line.strip()))
    # Accepted freeze re-verifies cleanly.
    verify_frozen_case(case_dir)


def test_freeze_and_reset_preserve_exec_bit(tmp_path: Path) -> None:
    workdir_src = make_workdir(tmp_path)
    script = workdir_src / "run_tests.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(script, 0o755)
    old = datetime.now(timezone.utc).timestamp() - 3600.0
    os.utime(script, (old, old))
    store_path = tmp_path / "store.db"
    commit_events(store_path, prefix_events())
    case_dir = tmp_path / "case-mode"
    freeze_case(
        store_path=store_path, cutoff_seq=len(prefix_events()),
        workdir_src=workdir_src, out_dir=case_dir,
        case_id="case-mode", journey="j", task_id="task-a",
        requirement="r", verifier_procedure="v",
    )
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    entry = next(e for e in manifest["files"] if e["path"] == "run_tests.sh")
    assert entry["mode"] == "0o755"
    assert os.access(case_dir / "workdir" / "run_tests.sh", os.X_OK)
    verify_frozen_case(case_dir)
    reset_workdir(case_dir, tmp_path / "trial-work")
    assert os.access(tmp_path / "trial-work" / "run_tests.sh", os.X_OK)
    # Tampering the frozen copy's mode must fail verification.
    os.chmod(case_dir / "workdir" / "run_tests.sh", 0o644)
    with pytest.raises(FreezeError, match="mode mismatch"):
        verify_frozen_case(case_dir)


def test_freeze_fails_closed_on_bad_cutoff_or_tamper(tmp_path: Path) -> None:
    store_path = tmp_path / "store.db"
    commit_events(store_path, prefix_events())
    workdir_src = make_workdir(tmp_path)
    with pytest.raises(FreezeError):
        freeze_case(
            store_path=store_path, cutoff_seq=999, workdir_src=workdir_src,
            out_dir=tmp_path / "bad-k", case_id="x", journey="j",
            task_id="task-a", requirement="r", verifier_procedure="v",
        )
    assert not (tmp_path / "bad-k").exists()
    with pytest.raises(FreezeError):
        freeze_case(
            store_path=tmp_path / "missing.db", cutoff_seq=1,
            workdir_src=workdir_src, out_dir=tmp_path / "bad-s",
            case_id="x", journey="j", task_id="task-a",
            requirement="r", verifier_procedure="v",
        )
    # Tamper with an accepted freeze: verification must refuse it.
    case_dir = freeze_fixture(tmp_path)
    (case_dir / "workdir" / "NOTES.md").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(FreezeError):
        verify_frozen_case(case_dir)


# ---------------------------------------------------------------------------
# Conditions: budgets, determinism, C3 equality
# ---------------------------------------------------------------------------


def test_all_builders_enforce_primary_and_sensitivity_budgets(tmp_path: Path) -> None:
    case_dir = freeze_fixture(tmp_path)
    prefix = FrozenPrefix.load(case_dir)
    assert len(prefix.events) == 7
    for budget in (PRIMARY_BUDGET_TOKENS, SENSITIVITY_BUDGET_TOKENS):
        results = build_all_conditions(prefix, budget=budget, seed=11)
        assert set(results) == {"C0", "C1", "C2", "C3", "C4"}
        for condition_id, result in results.items():
            assert result.tokens_used <= budget, condition_id
            assert result.tokenizer == TOKENIZER_ID
            assert "token_method" in result.params
            assert result.method_identity == "pilot-conditions/1"
    # Tiny budget forces overflow disclosure, never silent overrun. (C0's
    # prompt-only header can legitimately fit; the memory conditions cannot.)
    tiny = build_all_conditions(prefix, budget=64, seed=11)
    for condition_id, result in tiny.items():
        assert result.tokens_used <= 64, condition_id
    for condition_id in ("C1", "C2", "C3", "C4"):
        assert tiny[condition_id].overflow is True, condition_id
        assert tiny[condition_id].omitted, condition_id


def test_c0_carries_no_history_and_c1_orders_recent_first(tmp_path: Path) -> None:
    case_dir = freeze_fixture(tmp_path)
    prefix = FrozenPrefix.load(case_dir)
    c0 = build_c0(prefix)
    assert "flaky retry" in c0.context_text  # task prompt present
    assert "seq=" not in c0.context_text  # zero history units
    assert c0.params["history_units"] == 0
    c1 = build_c1(prefix)
    positions = [c1.context_text.index(f"seq={seq}") for seq in (7, 6, 5, 1)]
    assert positions == sorted(positions), "C1 must list most recent first"


def test_c2_and_c4_run_and_are_deterministic(tmp_path: Path) -> None:
    case_dir = freeze_fixture(tmp_path)
    prefix = FrozenPrefix.load(case_dir)
    first_c2 = build_c2(prefix)
    second_c2 = build_c2(prefix)
    assert first_c2.context_text == second_c2.context_text
    assert first_c2.params["retrieval"] == "bm25-okapi"
    assert first_c2.params["k1"] == 1.2 and first_c2.params["b"] == 0.75
    assert first_c2.params["top_unit"] is not None
    first_c4 = build_c4(prefix, seed=3)
    second_c4 = build_c4(prefix, seed=3)
    assert first_c4.context_text == second_c4.context_text
    assert first_c4.params["seed"] == 3
    assert first_c4.params["features"] == [
        "tfidf", "recency", "outcome", "task_match", "entity_overlap"]
    assert "eligible prefix only" in first_c4.params["fit_corpus"]
    assert first_c4.params["iterations"] == 200
    # Query-aware: C2/C4 surface the outcome-bearing failure unit.
    assert "t-outcome-1" in first_c2.context_text
    assert "t-outcome-1" in first_c4.context_text
    # Same corpus as C1: identical unit universe.
    assert first_c2.params["corpus_units"] == len(corpus_units(prefix)) == 7


def test_c3_packet_equals_builder_output_at_same_k(tmp_path: Path) -> None:
    from entorhinal.temporal.packet import (
        EXCERPT_SELECTION_V2,
        PacketRequest,
        ResumptionPacketBuilder,
        count_tokens as packet_count,
    )
    from entorhinal.temporal.projection import CommittedTaskEvent, TaskProjection

    case_dir = freeze_fixture(tmp_path)
    prefix = FrozenPrefix.load(case_dir)
    c3 = build_c3(prefix)
    committed = [
        CommittedTaskEvent(
            event=item.event,
            commit_seq=item.commit_seq,
            committed_at=item.committed_at,
            evidence_id=item.evidence_id,
        )
        for item in prefix.events
    ]
    from pilot.conditions import prefit_budget
    direct = ResumptionPacketBuilder(TaskProjection.rebuild(committed)).build(
        PacketRequest(
            task_id=prefix.task_id,
            consumer_id="pilot-consumer",
            purpose="m3-pilot-comparison",
            cutoff_seq=prefix.cutoff_seq,
            budget_chars=None,
            budget_tokens=prefit_budget(PRIMARY_BUDGET_TOKENS),
            excerpt_selection=EXCERPT_SELECTION_V2,
            include_hypotheses=False,
        )
    )
    # Volatile seal fields (issue/expiry time, hash over them) differ per
    # build; everything else must be identical at the same K.
    got = json.loads(c3.context_text)
    want = json.loads(direct.serialize())
    for doc in (got, want):
        for volatile in ("issued_at", "expires_at", "packet_hash"):
            doc["metadata"].pop(volatile, None)
    assert got == want
    assert c3.params["projection_digest"] == direct.metadata.projection_digest
    assert c3.params["packet_id"] == direct.packet_id
    assert c3.tokens_used == packet_count(c3.context_text)
    assert c3.params["excerpt_selection"] == EXCERPT_SELECTION_V2
    assert c3.params["prefit"]["effective_m2_budget"] == prefit_budget(PRIMARY_BUDGET_TOKENS)
    assert c3.params["prefit"]["downstream_proxy"]["encoding"] == "o200k_base"


def test_prefit_helpers() -> None:
    from pilot.conditions import (
        PREFIT_FACTOR,
        prefit_budget,
        unit_divisor,
    )
    assert PREFIT_FACTOR == 1.5
    assert prefit_budget(2048) == 1365
    assert prefit_budget(512) == 341
    normal = unit_divisor("the retry helper succeeded after three attempts")
    assert 0.3 < normal < 2.0
    assert unit_divisor("") == 0.0
    assert unit_divisor("   ") == float("inf")


def test_c1_prefit_fits_within_effective_budget(tmp_path: Path) -> None:
    from pilot.conditions import prefit_budget
    case_dir = freeze_fixture(tmp_path)
    prefix = FrozenPrefix.load(case_dir)
    c1 = build_c1(prefix, budget=150)
    assert c1.tokens_used <= prefit_budget(150)
    assert c1.overflow is True
    assert c1.params["prefit"]["effective_m2_budget"] == prefit_budget(150)
    assert c1.params["prefit"]["divisor_cap"] == 4.0
    assert "proxy_tokens" in c1.params["prefit"]["downstream_proxy"]


# ---------------------------------------------------------------------------
# Trial scaffold: reset fidelity, isolation, records
# ---------------------------------------------------------------------------


def _consumer(inp: ConsumerInput) -> ConsumerOutput:
    assert inp.workdir.is_dir()
    (inp.workdir / "attempt.log").write_text("tried fix\n", encoding="utf-8")
    return ConsumerOutput(
        output_text="draft continuation",
        recovery_actions=["edit conf/retry.yaml"],
        costs={"input_tokens": inp.context_tokens},
        notes="synthetic",
    )


def _verifier(inp: VerifierInput) -> Dict[str, Any]:
    return {"passed": False, "reason": "synthetic verifier"}


def test_trial_reset_restores_exact_bytes_and_records_trial(tmp_path: Path) -> None:
    case_dir = freeze_fixture(tmp_path)
    prefix = FrozenPrefix.load(case_dir)
    context = build_c1(prefix)
    record = run_trial(
        case_dir=case_dir,
        condition_id="C1",
        context_text=context.context_text,
        context_tokens=context.tokens_used,
        consumer_fn=_consumer,
        verifier_fn=_verifier,
        trial_root=tmp_path / "trials",
        consumer_identity="test-consumer/0",
        trial_id="case-t-01:C1:t1",
    )
    assert record.invalid_reason is None
    assert record.consumer_identity == "test-consumer/0"
    assert record.recovery_actions == ["edit conf/retry.yaml"]
    assert record.verifier_result == {"passed": False, "reason": "synthetic verifier"}
    assert set(record.latencies_ms) == {"reset_ms", "consumer_ms", "verifier_ms"}
    assert record.context_hash == hashlib.sha256(
        context.context_text.encode("utf-8")).hexdigest()
    assert any("no trial history" in note for note in record.isolation_notes)
    assert (tmp_path / "trials" / "case-t-01_C1_t1" / "trial_record.json").is_file()

    # Reset restores exact bytes even after the consumer mutated the workdir.
    trial_workdir = tmp_path / "trials" / "case-t-01_C1_t1" / "workdir"
    assert (trial_workdir / "attempt.log").read_text() == "tried fix\n"
    fresh = tmp_path / "reset-check"
    info = reset_workdir(case_dir, fresh)
    assert info["starting_state_hash"] == prefix.starting_state_hash
    assert (fresh / "conf" / "retry.yaml").read_text(encoding="utf-8") == "max_retries: 3\n"
    assert not (fresh / "attempt.log").exists()


def test_trial_records_consumer_failure_as_invalid(tmp_path: Path) -> None:
    case_dir = freeze_fixture(tmp_path)

    def bad_consumer(_inp: ConsumerInput) -> ConsumerOutput:
        raise ValueError("boom")

    record = run_trial(
        case_dir=case_dir,
        condition_id="C0",
        context_text="ctx",
        context_tokens=1,
        consumer_fn=bad_consumer,
        verifier_fn=_verifier,
        trial_root=tmp_path / "trials",
        consumer_identity="test-consumer/0",
        trial_id="case-t-01:C0:bad",
    )
    assert record.invalid_reason is not None and "boom" in record.invalid_reason

    with pytest.raises(TrialError):
        run_trial(
            case_dir=case_dir,
            condition_id="C0",
            context_text="ctx",
            context_tokens=1,
            consumer_fn=_consumer,
            verifier_fn=_verifier,
            trial_root=tmp_path / "trials",
            consumer_identity="",
            trial_id="case-t-01:C0:empty",
        )


# ---------------------------------------------------------------------------
# Worked fixture example: 2-task prefix, 1 case, 5 budgeted contexts
# ---------------------------------------------------------------------------


def test_worked_fixture_example_two_tasks_five_conditions(tmp_path: Path, capsys) -> None:
    case_dir = freeze_fixture(tmp_path)
    prefix = FrozenPrefix.load(case_dir)
    tasks = sorted({event.task_id for event in prefix.events})
    assert tasks == ["task-a", "task-b"]
    results = build_all_conditions(prefix, budget=PRIMARY_BUDGET_TOKENS, seed=7)
    print("=== worked fixture: case-t-01 (2 tasks, K=7) ===")
    for condition_id in ("C0", "C1", "C2", "C3", "C4"):
        result = results[condition_id]
        assert result.tokens_used <= PRIMARY_BUDGET_TOKENS
        print(f"{condition_id}: tokens={result.tokens_used} "
              f"overflow={result.overflow} omitted={len(result.omitted)} "
              f"sha={hashlib.sha256(result.context_text.encode()).hexdigest()[:12]}")
    captured = capsys.readouterr()
    assert "C4:" in captured.out
