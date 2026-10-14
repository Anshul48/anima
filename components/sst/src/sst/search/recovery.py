"""Crash-recovery and caller helpers reconstructing search results from the event log.

Recovery semantics (see also SST0 wave-2 addendum §10):

- The append-only event log is the source of truth. The live DAG read model
  is rebuilt by replaying it (``SQLiteSSTStore.rebuild_tree_from_events``).
- ``SEARCH_COMPLETED`` is the finished-marker: it is appended on every
  terminal path (champion / no-candidate / budget / cancel). A tree without
  it did not finish — after a crash, callers must treat the run as
  incomplete, never as successful.
- Re-emission is idempotent: ``append_event`` returns the existing sequence
  id when the ``idempotency_key`` already exists, so replaying or resuming
  with the same deterministic keys converges instead of duplicating. The
  exception is ``PROVIDER_ERROR`` events, which carry unique keys: each
  provider failure is a distinct audit record and re-runs append new ones.
- :func:`get_search_result` rebuilds the :class:`SearchResult` envelope from
  the log so callers can recover the termination outcome, champion, and
  alternatives without re-running search. Reconstructed proposals carry the
  fields persisted in ``NODE_PROPOSED``/``SYNTHESIS_PROPOSED`` payloads;
  timestamps and unpersisted in-memory fields naturally differ from the
  original envelope.
"""

from __future__ import annotations

from typing import Any

from sst.core.contracts import (
    AlternativeCandidate,
    BudgetConsumed,
    CandidateProposal,
    GatewayBinding,
    ProviderErrorRecord,
    ScoreBreakdown,
    SearchResult,
    TerminationReason,
)
from sst.core.errors import IncompleteSearchError
from sst.core.events import EventKind, SSTEvent
from sst.core.models import DeterministicGateResult
from sst.protocols.storage import TreeStoreProtocol


def _as_str_list(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _proposal_from_event(event: SSTEvent, tree_id: str) -> CandidateProposal | None:
    """Rebuilds a candidate proposal from a NODE/SYNTHESIS_PROPOSED event."""
    node_id = event.node_id
    if not node_id:
        return None
    payload = event.payload
    parent_ids = _as_str_list(payload.get("parent_ids"))
    if not parent_ids and payload.get("parent_id") is not None:
        parent_ids = [str(payload["parent_id"])]
    raw_ops = payload.get("file_operations", [])
    file_operations = [dict(op) for op in raw_ops if isinstance(op, dict)] if isinstance(raw_ops, list) else []
    return CandidateProposal(
        candidate_id=node_id,
        tree_id=tree_id,
        parent_ids=parent_ids,
        role=str(payload.get("role", "DIVERGE")),
        title=str(payload.get("title", f"Candidate {node_id}")),
        rationale=str(payload.get("rationale", "")),
        target_paths=_as_str_list(payload.get("target_paths")),
        patch_diff=str(payload.get("patch_diff", "")),
        file_operations=file_operations,
        model_id=str(payload.get("model_id", "")),
    )


def get_search_result(store: TreeStoreProtocol, tree_id: str) -> SearchResult:
    """Reconstructs the SearchResult envelope for ``tree_id`` from the event log.

    Requires the ``SEARCH_COMPLETED`` finished-marker; raises
    :class:`IncompleteSearchError` when the tree has no events or never
    finished (e.g. crashed mid-run). Callers recovering from a crash must
    treat that outcome as "unknown, re-run or resume" — never as success.
    """
    events = store.get_events(tree_id)
    if not any(e.kind is EventKind.TREE_CREATED for e in events):
        raise IncompleteSearchError(f"No TREE_CREATED event found for tree '{tree_id}'.")
    completed = next((e for e in reversed(events) if e.kind is EventKind.SEARCH_COMPLETED), None)
    if completed is None:
        raise IncompleteSearchError(
            f"No SEARCH_COMPLETED finished-marker for tree '{tree_id}': the run did not finish."
        )

    payload = completed.payload
    termination = TerminationReason(str(payload.get("termination_reason", TerminationReason.NO_CANDIDATE.value)))

    proposals: dict[str, CandidateProposal] = {}
    for event in events:
        if event.kind in {EventKind.NODE_PROPOSED, EventKind.SYNTHESIS_PROPOSED}:
            proposal = _proposal_from_event(event, tree_id)
            if proposal is not None:
                proposals[proposal.candidate_id] = proposal

    verifier_outcomes: dict[str, DeterministicGateResult] = {}
    for event in events:
        if event.kind is EventKind.VERIFIER_FINISHED and event.node_id:
            verifier_outcomes[event.node_id] = DeterministicGateResult(
                passed=bool(event.payload.get("passed", False)),
                exit_code=int(event.payload.get("exit_code", 0)),
                stdout=str(event.payload.get("stdout", "")),
                stderr=str(event.payload.get("stderr", "")),
                duration_seconds=float(event.payload.get("duration_seconds", 0.0)),
            )

    scores: dict[str, ScoreBreakdown] = {}
    for event in events:
        if event.kind is EventKind.SCORE_RECORDED and event.node_id:
            value = min(1.0, max(0.0, float(event.payload.get("value_score", 0.0))))
            verdict = str(event.payload.get("verdict", "APPROVE" if value >= 0.7 else "PRUNE"))
            scores[event.node_id] = ScoreBreakdown(
                passed_hard_gates=True,
                hard_gates={"verifier_passed": True},
                soft_scores={"value_score": value},
                normalized_reward=value,
                critic_verdict=verdict,
                critic_rationale=str(event.payload.get("critique", "")),
            )

    evidence_refs: dict[str, list[str]] = {}
    for event in events:
        if event.node_id:
            evidence_refs.setdefault(event.node_id, []).append(event.event_id)

    # Same ranking as the live run: score descending, unscored last.
    evaluated_ids = [cid for cid in proposals if cid in verifier_outcomes]
    ranked = sorted(
        evaluated_ids,
        key=lambda cid: scores[cid].normalized_reward if cid in scores else -1.0,
        reverse=True,
    )
    alternatives = [
        AlternativeCandidate(
            candidate=proposals[cid],
            score=scores.get(cid),
            verifier_outcome=verifier_outcomes.get(cid),
            evidence_refs=evidence_refs.get(cid, []),
        )
        for cid in ranked
    ]

    champion_id = payload.get("champion_node_id")
    champion: CandidateProposal | None = None
    if champion_id is not None:
        champion = proposals.get(str(champion_id))
        if champion is None:
            raise IncompleteSearchError(
                f"SEARCH_COMPLETED names champion '{champion_id}' with no proposal event for tree '{tree_id}'."
            )

    budget_payload: dict[str, Any] = payload.get("budget", {})
    if not isinstance(budget_payload, dict):
        budget_payload = {}
    budget = BudgetConsumed(
        tokens_consumed=int(budget_payload.get("tokens_consumed", 0)),
        estimated_cost_usd=float(budget_payload.get("estimated_cost_usd", 0.0)),
        elapsed_seconds=float(budget_payload.get("elapsed_seconds", 0.0)),
        iterations_completed=int(budget_payload.get("iterations_completed", 0)),
    )

    provider_errors = [
        ProviderErrorRecord(
            role=str(e.payload.get("role", "")),
            category=str(e.payload.get("category", "")),
            remediation=str(e.payload.get("remediation", "")),
            message=str(e.payload.get("message", "")),
            profile=e.payload.get("profile"),
            iteration=e.payload.get("iteration"),
        )
        for e in events
        if e.kind is EventKind.PROVIDER_ERROR
    ]

    db_path = getattr(store, "db_path", None)
    event_log_ref = f"sqlite:{db_path}::tree:{tree_id}" if db_path is not None else f"store::tree:{tree_id}"

    raw_bindings = payload.get("gateway_bindings", [])
    gateway_bindings = [
        GatewayBinding(
            role=str(b.get("role", "*")),
            profile=str(b.get("profile", "")),
            model=str(b.get("model", "")),
            kind=str(b.get("kind", "UNKNOWN")),
        )
        for b in raw_bindings
        if isinstance(b, dict)
    ]

    return SearchResult(
        tree_id=tree_id,
        termination_reason=termination,
        champion=champion,
        alternatives=alternatives,
        budget_consumed=budget,
        provider_errors=provider_errors,
        gateway_bindings=gateway_bindings,
        event_log_ref=event_log_ref,
    )
