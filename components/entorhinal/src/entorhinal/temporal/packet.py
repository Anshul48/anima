"""Bounded resumption-packet builder (advisory only).

Builds the first-consumer packet for a paused task from a
:class:`~entorhinal.temporal.projection.TaskProjection`: current task state,
changed assumptions, relevant prior attempts with outcome/version, open
obligations, supporting excerpts, conflicts/missing intervals, and optional
explicitly labeled hypotheses.

Budget: the builder counts the ACTUAL consumer serialization (canonical
JSON) in characters and deterministic regex tokens (tokenizer id
``m2-regex-v1``: ``\\w+`` words plus single punctuation symbols). Content is
pruned in a fixed priority order until the serialization fits; every pruned
item is disclosed in the omission list and ``overflow`` is set. The budget
is never silently exceeded. Hypotheses are flagged and never presented as
facts. The packet carries no commands and no authority tokens: command
identities appear only as labeled observed references.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from entorhinal.temporal.cutoff import TemporalQuery
from entorhinal.temporal.projection import (
    PROJECTION_ID,
    PROJECTION_VERSION,
    TaskProjection,
)

TOKENIZER_ID = "m2-regex-v1"
_TOKEN_RE = re.compile(r"\w+|[^\w\s]")

# Excerpt-selection policy versions. v1 (oldest-first) is frozen: it built all
# round-1/round-2 packets and is reproducible on request. v2 retains excerpts
# by signal class (decisions/corrections longest). See _prune_excerpt.
EXCERPT_SELECTION_V1 = "excerpt-selection/1"
EXCERPT_SELECTION_V2 = "excerpt-selection/2"
EXCERPT_SELECTIONS = (EXCERPT_SELECTION_V1, EXCERPT_SELECTION_V2)

# Bounded omission ledger: the audit trail of prunes must not itself crowd
# content out of the budget. Past the entry cap, oldest entries compact into
# a single disclosed summary (counts + section histogram preserved); most
# recent prunes retained longest. Under token budgets the ledger additionally
# yields down to its floor before retained content is pruned; pure
# char-budget packets keep their full ledger (overflow disclosed).
OMISSION_LEDGER_MAX_ENTRIES = 12
OMISSION_LEDGER_MIN_KEPT = 3
OMISSION_SUMMARY_REASON = "omissions-compacted"


def _excerpt_rank(label: str) -> int:
    """Signal rank for v2 pruning (higher retained longer).

    Ranks 0-2 duplicate structured packet sections (task_state /
    prior_attempts) and are pruned first. Rank 3 may carry unique
    diagnostic content. Unclassified labels (4) are retained
    conservatively: the builder must not sacrifice content whose
    redundancy it cannot assess. Decisions/corrections (5) define
    currently-required behavior and are retained longest.
    """
    return {
        "lifecycle-statement": 0,
        "goal-statement": 1,
        "command-output-tail": 2,
        "observation-statement": 3,
        "verifier-report": 3,
        "decision-statement": 5,
        "correction-statement": 5,
    }.get(label, 4)

DISCLAIMER = (
    "ADVISORY ONLY. This packet summarizes observed evidence for resuming "
    "work; it issues no commands and grants no authority. Direct user "
    "instruction and fresh observation take precedence. Observed command "
    "identities are references to past attempts, not instructions to run."
)


def count_chars(serialized: str) -> int:
    """Count characters of the actual consumer serialization."""
    return len(serialized)


def count_tokens(serialized: str) -> int:
    """Deterministic token estimate (tokenizer ``m2-regex-v1``).

    Counts ``\\w+`` words plus single non-space symbols. This is a
    documented approximation of downstream tokenization, counted on the
    real serialized bytes -- not on a summary or a guess.
    """
    return len(_TOKEN_RE.findall(serialized))


class PacketEnrichmentHook(Protocol):
    """Interface for optional learned enrichment (never a live dependency).

    Implementations propose candidate hypotheses from packet context. The
    builder always flags hook output as hypotheses and records the hook
    identity; hook output can never become a verified fact.
    """

    hook_id: str

    def propose(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return candidate hypothesis dicts (text + basis), possibly empty."""
        ...  # pragma: no cover - interface only


# ---------------------------------------------------------------------------
# Packet schema
# ---------------------------------------------------------------------------


class PacketTaskState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    goal: Optional[str] = None
    status: str = "unknown"
    verified_completion: bool = False
    verification_event_id: Optional[str] = None
    attempt_ids: List[str] = Field(default_factory=list)
    branch_ids: List[str] = Field(default_factory=list)
    session_ids: List[str] = Field(default_factory=list)
    open_interruption_ids: List[str] = Field(default_factory=list)
    last_commit_seq: int = 0


class ChangedAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_key: str
    current_value_repr: Optional[str] = None
    current_revision_id: Optional[str] = None
    previous_value_repr: Optional[str] = None
    previous_revision_id: Optional[str] = None
    change_commit_seq: int = 0
    revision_count: int = 0


class PriorAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    observed_command_identity: Optional[str] = None
    command_note: str = "reference to a past attempt; not an instruction to run"
    check_identity: Optional[str] = None
    exit_status: Optional[int] = None
    outcome: str = "unknown"
    outcome_verified: bool = False
    artifact_revisions: List[str] = Field(default_factory=list)
    attempt_event_ids: List[str] = Field(default_factory=list)
    outcome_event_ids: List[str] = Field(default_factory=list)


class ObligationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_id: str
    description: str = ""
    status: str = "open"
    source_event_id: str = ""
    resolved_by: Optional[str] = None


class QuestionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str = ""
    status: str = "open"
    claim_key: Optional[str] = None
    source_event_id: str = ""
    resolved_by: Optional[str] = None


class ExcerptEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    text: str
    event_id: str = ""
    commit_seq: int = 0
    truncated: bool = False


class ConflictEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_id: str
    claim_key: str
    values: List[str] = Field(default_factory=list)
    revision_ids: List[str] = Field(default_factory=list)
    status: str = "open"
    resolved_by: Optional[str] = None


class MissingIntervalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_id: str
    reason: str = ""
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    open: bool = True
    note: str = "absence of evidence here is unknown, not inactivity"


class HypothesisEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    text: str = ""
    is_hypothesis: bool = True
    basis_event_ids: List[str] = Field(default_factory=list)
    source: str = "projection-derivation"
    confidence: Optional[float] = None
    confidence_note: str = "uncalibrated/unknown"


class OmissionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    item_id: str = ""
    reason: str = "budget-prune"
    detail: str = ""


class PacketMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_identity: str = "sqlite-store/1"
    projection_identity: str = PROJECTION_ID
    projection_version: str = PROJECTION_VERSION
    projection_digest: str = ""
    watermark: int = 0
    cutoff_seq: Optional[int] = None
    issued_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    ttl_seconds: int = 300
    source_freshness: Dict[str, Any] = Field(default_factory=dict)
    freshness_met: bool = True
    deletion_generation: int = 0
    revocation_generation: int = 0
    packet_hash: str = ""


class PacketBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_chars: Optional[int] = None
    budget_tokens: Optional[int] = None
    used_chars: int = 0
    used_tokens: int = 0
    tokenizer: str = TOKENIZER_ID
    overflow: bool = False
    omission_count: int = 0


class ResumptionPacket(BaseModel):
    """The advisory resumption packet handed to the consumer."""

    model_config = ConfigDict(extra="forbid")

    packet_id: str
    task_state: PacketTaskState
    changed_assumptions: List[ChangedAssumption] = Field(default_factory=list)
    prior_attempts: List[PriorAttempt] = Field(default_factory=list)
    open_obligations: List[ObligationEntry] = Field(default_factory=list)
    open_questions: List[QuestionEntry] = Field(default_factory=list)
    supporting_excerpts: List[ExcerptEntry] = Field(default_factory=list)
    conflicts: List[ConflictEntry] = Field(default_factory=list)
    missing_intervals: List[MissingIntervalEntry] = Field(default_factory=list)
    hypotheses: List[HypothesisEntry] = Field(default_factory=list)
    omissions: List[OmissionEntry] = Field(default_factory=list)
    metadata: PacketMetadata = Field(default_factory=PacketMetadata)
    budget: PacketBudget = Field(default_factory=PacketBudget)
    disclaimer: str = DISCLAIMER

    def serialize(self) -> str:
        """Canonical consumer serialization (what the budget counts)."""
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )


class PacketRequest(BaseModel):
    """Consumer request for a resumption packet."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    consumer_id: str = "external-assistant"
    purpose: str = "resumption"
    cutoff_seq: Optional[int] = None
    valid_at: Optional[datetime] = None
    budget_chars: Optional[int] = 24000
    budget_tokens: Optional[int] = 6000
    # Round-3 repaired default: v2 retains decisions/corrections longest.
    # Pass EXCERPT_SELECTION_V1 explicitly to reproduce round-1/round-2 packets.
    excerpt_selection: str = EXCERPT_SELECTION_V2
    include_hypotheses: bool = False
    ttl_seconds: int = 300
    max_evidence_age_seconds: Optional[int] = None
    store_identity: str = "sqlite-store/1"


class ResumptionPacketBuilder:
    """Build bounded advisory resumption packets from a projection."""

    def __init__(
        self,
        projection: TaskProjection,
        enrichment_hook: Optional[PacketEnrichmentHook] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._projection = projection
        self._hook = enrichment_hook
        # Clock override for byte-reproducible builds (round-3 R9): trial
        # contexts pin issued_at/expires_at to cutoff-derived time so the
        # serialized packet, context_hash, and packet_hash are stable
        # across builds. Live serving keeps the wall clock (default).
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def build(self, request: PacketRequest) -> ResumptionPacket:
        """Build, budget-enforce, and seal one resumption packet."""
        if request.excerpt_selection not in EXCERPT_SELECTIONS:
            raise ValueError(
                f"unknown excerpt_selection {request.excerpt_selection!r}; "
                f"expected one of {list(EXCERPT_SELECTIONS)}"
            )
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        base = self._projection
        if request.cutoff_seq is not None:
            base = base.spawn_filtered(max_commit_seq=request.cutoff_seq)
        query = TemporalQuery(base)

        task_state = self._gather_task_state(base, request.task_id)
        assumptions = self._gather_changed_assumptions(base, query, request)
        attempts = self._gather_prior_attempts(base, request.task_id)
        obligations = self._gather_obligations(base, request.task_id)
        questions = self._gather_questions(base, request.task_id)
        excerpts = self._gather_excerpts(base, request.task_id)
        conflicts = self._gather_conflicts(base, request.task_id)
        missing = self._gather_missing(base)
        hypotheses = (
            self._gather_hypotheses(base, request) if request.include_hypotheses else []
        )

        packet = ResumptionPacket(
            packet_id=self._packet_id(request, base),
            task_state=task_state,
            changed_assumptions=assumptions,
            prior_attempts=attempts,
            open_obligations=obligations,
            open_questions=questions,
            supporting_excerpts=excerpts,
            conflicts=conflicts,
            missing_intervals=missing,
            hypotheses=hypotheses,
            metadata=self._gather_metadata(base, request, now),
        )
        self._enforce_budget(packet, request)
        self._seal(packet, base, request, now)
        return packet

    # -- gathering ---------------------------------------------------------------

    def _gather_task_state(
        self, base: TaskProjection, task_id: str
    ) -> PacketTaskState:
        task = base.tasks.get(task_id)
        open_interruptions = sorted(
            record.interruption_id
            for record in base.interruptions.values()
            if record.task_id == task_id and record.status == "open"
        )
        if task is None:
            return PacketTaskState(task_id=task_id, open_interruption_ids=open_interruptions)
        return PacketTaskState(
            task_id=task_id,
            goal=task.goal,
            status=task.status,
            verified_completion=task.verified_completion,
            verification_event_id=task.verification_event_id,
            attempt_ids=list(task.attempt_ids),
            branch_ids=list(task.branch_ids),
            session_ids=list(task.session_ids),
            open_interruption_ids=open_interruptions,
            last_commit_seq=task.last_commit_seq,
        )

    def _gather_changed_assumptions(
        self, base: TaskProjection, query: TemporalQuery, request: PacketRequest
    ) -> List[ChangedAssumption]:
        out: List[ChangedAssumption] = []
        for claim_key in sorted(base.claims.keys()):
            revisions = base.claims[claim_key]
            task_touched = any(
                self._event_task(base, rev.source_event_id) == request.task_id
                for rev in revisions
            )
            if not task_touched:
                continue
            if len(revisions) < 2:
                continue
            ordered = sorted(revisions, key=lambda rev: (rev.commit_seq, rev.revision_id))
            current = ordered[-1]
            if request.valid_at is not None:
                evaluated = query.evaluate_claim(base, claim_key, request.valid_at)
                if evaluated.status == "known" and evaluated.revision_id:
                    match = next(
                        (
                            rev
                            for rev in revisions
                            if rev.revision_id == evaluated.revision_id
                        ),
                        None,
                    )
                    if match is not None:
                        current = match
            previous = next(
                (rev for rev in reversed(ordered) if rev.revision_id != current.revision_id),
                None,
            )
            out.append(
                ChangedAssumption(
                    claim_key=claim_key,
                    current_value_repr=current.value_repr,
                    current_revision_id=current.revision_id,
                    previous_value_repr=previous.value_repr if previous else None,
                    previous_revision_id=previous.revision_id if previous else None,
                    change_commit_seq=current.commit_seq,
                    revision_count=len(revisions),
                )
            )
        out.sort(key=lambda item: (item.change_commit_seq, item.claim_key))
        return out

    def _event_task(self, base: TaskProjection, event_id: str) -> Optional[str]:
        for entry in base.event_log:
            if entry.event_id == event_id:
                return entry.task_id
        return None

    def _gather_prior_attempts(
        self, base: TaskProjection, task_id: str
    ) -> List[PriorAttempt]:
        task = base.tasks.get(task_id)
        attempt_ids = list(task.attempt_ids) if task else []
        if not attempt_ids:
            attempt_ids = sorted(
                attempt.attempt_id
                for attempt in base.attempts.values()
                if attempt.task_id == task_id
            )
        attempts = [base.attempts[aid] for aid in attempt_ids if aid in base.attempts]
        attempts.sort(key=lambda attempt: (attempt.last_commit_seq, attempt.attempt_id))
        return [
            PriorAttempt(
                attempt_id=attempt.attempt_id,
                observed_command_identity=attempt.command_identity,
                check_identity=attempt.check_identity,
                exit_status=attempt.exit_status,
                outcome=attempt.outcome,
                outcome_verified=attempt.outcome_verified,
                artifact_revisions=list(attempt.artifact_revisions),
                attempt_event_ids=list(attempt.attempt_event_ids),
                outcome_event_ids=list(attempt.outcome_event_ids),
            )
            for attempt in attempts
        ]

    def _gather_obligations(
        self, base: TaskProjection, task_id: str
    ) -> List[ObligationEntry]:
        items = [
            obligation
            for obligation in base.obligations.values()
            if obligation.task_id == task_id
        ]
        items.sort(key=lambda item: (item.source_commit_seq, item.obligation_id))
        return [
            ObligationEntry(
                obligation_id=item.obligation_id,
                description=item.description,
                status=item.status,
                source_event_id=item.source_event_id,
                resolved_by=item.resolved_by,
            )
            for item in items
        ]

    def _gather_questions(
        self, base: TaskProjection, task_id: str
    ) -> List[QuestionEntry]:
        items = [
            question
            for question in base.open_questions.values()
            if question.task_id == task_id or question.task_id is None
        ]
        items.sort(key=lambda item: (item.source_commit_seq, item.question_id))
        return [
            QuestionEntry(
                question_id=item.question_id,
                question=item.question,
                status=item.status,
                claim_key=item.claim_key,
                source_event_id=item.source_event_id,
                resolved_by=item.resolved_by,
            )
            for item in items
        ]

    def _gather_excerpts(
        self, base: TaskProjection, task_id: str
    ) -> List[ExcerptEntry]:
        out: List[ExcerptEntry] = []
        for entry in base.event_log:
            if entry.task_id != task_id:
                continue
            for excerpt in entry.event.payload.excerpts:
                out.append(
                    ExcerptEntry(
                        label=excerpt.label,
                        text=excerpt.text,
                        event_id=entry.event_id,
                        commit_seq=entry.commit_seq,
                        truncated=excerpt.truncated,
                    )
                )
        out.sort(key=lambda item: (item.commit_seq, item.event_id, item.label))
        return out

    def _gather_conflicts(
        self, base: TaskProjection, task_id: str
    ) -> List[ConflictEntry]:
        out: List[ConflictEntry] = []
        for conflict in base.conflicts.values():
            revisions = base.claims.get(conflict.claim_key, [])
            by_id = {rev.revision_id: rev for rev in revisions}
            touched = any(
                self._event_task(base, by_id[rid].source_event_id) == task_id
                for rid in conflict.revision_ids
                if rid in by_id
            )
            if not touched:
                continue
            out.append(
                ConflictEntry(
                    conflict_id=conflict.conflict_id,
                    claim_key=conflict.claim_key,
                    values=list(conflict.values),
                    revision_ids=list(conflict.revision_ids),
                    status=conflict.status,
                    resolved_by=conflict.resolved_by,
                )
            )
        out.sort(key=lambda item: item.conflict_id)
        return out

    def _gather_missing(self, base: TaskProjection) -> List[MissingIntervalEntry]:
        items = sorted(
            base.unknown_intervals.values(), key=lambda item: item.interval_id
        )
        entries = [
            MissingIntervalEntry(
                interval_id=item.interval_id,
                reason=item.reason,
                started_at=item.started_at,
                ended_at=item.ended_at,
                open=item.open,
            )
            for item in items
        ]
        for gap in sorted(base.sequence_gaps.values(), key=lambda item: item.gap_id):
            entries.append(
                MissingIntervalEntry(
                    interval_id=gap.gap_id,
                    reason=(
                        f"producer-sequence gap: expected {gap.expected_sequence}, "
                        f"received {gap.received_sequence} "
                        f"(run {gap.producer_run_id})"
                    ),
                    open=False,
                )
            )
        return entries

    def _gather_hypotheses(
        self, base: TaskProjection, request: PacketRequest
    ) -> List[HypothesisEntry]:
        out: List[HypothesisEntry] = []
        for conflict in sorted(base.conflicts.values(), key=lambda item: item.conflict_id):
            if conflict.status != "open":
                continue
            revisions = base.claims.get(conflict.claim_key, [])
            by_id = {rev.revision_id: rev for rev in revisions}
            basis = sorted(
                {
                    by_id[rid].source_event_id
                    for rid in conflict.revision_ids
                    if rid in by_id
                }
            )
            out.append(
                HypothesisEntry(
                    hypothesis_id=f"hyp:{conflict.conflict_id}",
                    text=(
                        f"Unresolved conflicting reports for {conflict.claim_key}; "
                        "the true value needs an independent check."
                    ),
                    basis_event_ids=basis,
                )
            )
        for question in sorted(
            base.open_questions.values(), key=lambda item: item.question_id
        ):
            if question.status != "open":
                continue
            if question.task_id is not None and question.task_id != request.task_id:
                continue
            out.append(
                HypothesisEntry(
                    hypothesis_id=f"hyp:{question.question_id}",
                    text=f"Open question may still matter: {question.question}",
                    basis_event_ids=[question.source_event_id],
                )
            )
        if self._hook is not None:
            context = {
                "task_id": request.task_id,
                "watermark": base.watermark,
                "open_conflicts": sorted(
                    conflict.conflict_id
                    for conflict in base.conflicts.values()
                    if conflict.status == "open"
                ),
            }
            try:
                proposals = self._hook.propose(context) or []
            except Exception:
                proposals = []
            hook_id = getattr(self._hook, "hook_id", "enrichment-hook")
            for index, proposal in enumerate(proposals):
                text = str(proposal.get("text", "")).strip()
                if not text:
                    continue
                basis = proposal.get("basis_event_ids") or []
                out.append(
                    HypothesisEntry(
                        hypothesis_id=f"hyp:{hook_id}:{index}",
                        text=text,
                        basis_event_ids=[str(item) for item in basis],
                        source=str(hook_id),
                    )
                )
        out.sort(key=lambda item: item.hypothesis_id)
        return out

    # -- metadata / identity ----------------------------------------------------------

    def _packet_id(self, request: PacketRequest, base: TaskProjection) -> str:
        canonical = json.dumps(
            {
                "task_id": request.task_id,
                "cutoff_seq": request.cutoff_seq,
                "watermark": base.watermark,
                "digest": base.state_digest(),
                "hypotheses": request.include_hypotheses,
            },
            sort_keys=True,
        )
        return f"packet:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"

    def _gather_metadata(
        self, base: TaskProjection, request: PacketRequest, now: datetime
    ) -> PacketMetadata:
        last_committed: Optional[datetime] = None
        last_observed: Optional[datetime] = None
        sources: List[str] = []
        for entry in base.event_log:
            if entry.committed_at is not None and (
                last_committed is None or entry.committed_at > last_committed
            ):
                last_committed = entry.committed_at
            observed = entry.observed_at
            if observed is not None and (
                last_observed is None or observed > last_observed
            ):
                last_observed = observed
            if entry.source_id not in sources:
                sources.append(entry.source_id)
        sources.sort()
        open_unknown = sum(1 for item in base.unknown_intervals.values() if item.open)
        freshness: Dict[str, Any] = {
            "sources_seen": sources,
            "last_committed_at": last_committed.isoformat() if last_committed else None,
            "last_observed_at": last_observed.isoformat() if last_observed else None,
            "open_unknown_intervals": open_unknown,
            "sequence_gaps": len(base.sequence_gaps),
        }
        freshness_met = True
        if request.max_evidence_age_seconds is not None:
            if last_observed is None:
                freshness_met = False
                freshness["stale_reason"] = "no observed evidence in scope"
            else:
                age = (now - last_observed).total_seconds()
                freshness["evidence_age_seconds"] = age
                if age > request.max_evidence_age_seconds:
                    freshness_met = False
                    freshness["stale_reason"] = (
                        f"evidence age {age:.0f}s exceeds "
                        f"{request.max_evidence_age_seconds}s requirement"
                    )
        expires_at = now + timedelta(seconds=request.ttl_seconds)
        return PacketMetadata(
            store_identity=request.store_identity,
            projection_identity=PROJECTION_ID,
            projection_version=PROJECTION_VERSION,
            projection_digest=base.state_digest(),
            watermark=base.watermark,
            cutoff_seq=request.cutoff_seq,
            issued_at=now,
            expires_at=expires_at,
            ttl_seconds=request.ttl_seconds,
            source_freshness=freshness,
            freshness_met=freshness_met,
            deletion_generation=base.deletion_generation,
            revocation_generation=base.revocation_generation,
        )

    # -- budget enforcement --------------------------------------------------------------

    def _over_budget(self, packet: ResumptionPacket, request: PacketRequest) -> bool:
        serialized = packet.serialize()
        if request.budget_chars is not None and count_chars(serialized) > request.budget_chars:
            return True
        if request.budget_tokens is not None and count_tokens(serialized) > request.budget_tokens:
            return True
        return False

    def _prune_excerpt(
        self, packet: ResumptionPacket, selection: str
    ) -> OmissionEntry:
        """Drop one excerpt under the requested selection policy.

        v1 (frozen): oldest first. v2: lowest signal class first, oldest
        within class; decisions/corrections retained longest.
        """
        if selection == EXCERPT_SELECTION_V2:
            victim = min(
                packet.supporting_excerpts,
                key=lambda item: (
                    _excerpt_rank(item.label),
                    item.commit_seq,
                    item.event_id,
                    item.label,
                ),
            )
            packet.supporting_excerpts = [
                item for item in packet.supporting_excerpts if item is not victim
            ]
            return OmissionEntry(
                section="supporting_excerpts",
                item_id=f"{victim.event_id}:{victim.label}",
                detail=(
                    "pruned under excerpt-selection/2: "
                    f"{victim.label} rank {_excerpt_rank(victim.label)} "
                    "(oldest-first within rank)"
                ),
            )
        dropped = packet.supporting_excerpts.pop(0)
        return OmissionEntry(
            section="supporting_excerpts",
            item_id=f"{dropped.event_id}:{dropped.label}",
            detail="oldest excerpt pruned first",
        )

    def _prune_step(
        self, packet: ResumptionPacket, request: PacketRequest
    ) -> Optional[OmissionEntry]:
        """Drop the single lowest-priority item; None when only core remains."""
        if packet.hypotheses:
            dropped = packet.hypotheses.pop(0)
            return OmissionEntry(
                section="hypotheses",
                item_id=dropped.hypothesis_id,
                detail="lowest priority under budget pressure",
            )
        if packet.supporting_excerpts:
            return self._prune_excerpt(packet, request.excerpt_selection)
        if packet.prior_attempts:
            dropped = packet.prior_attempts.pop(0)
            return OmissionEntry(
                section="prior_attempts",
                item_id=dropped.attempt_id,
                detail="oldest attempt pruned first; newest retained longest",
            )
        if packet.changed_assumptions:
            dropped = packet.changed_assumptions.pop(0)
            return OmissionEntry(
                section="changed_assumptions",
                item_id=dropped.claim_key,
                detail="oldest change pruned first",
            )
        if packet.open_questions:
            dropped = packet.open_questions.pop(0)
            return OmissionEntry(
                section="open_questions",
                item_id=dropped.question_id,
                detail="oldest question pruned first",
            )
        resolved_conflicts = [item for item in packet.conflicts if item.status != "open"]
        if resolved_conflicts:
            dropped = resolved_conflicts[0]
            packet.conflicts = [
                item for item in packet.conflicts if item.conflict_id != dropped.conflict_id
            ]
            return OmissionEntry(
                section="conflicts",
                item_id=dropped.conflict_id,
                detail="resolved conflict pruned before open conflicts",
            )
        if packet.missing_intervals:
            closed = [item for item in packet.missing_intervals if not item.open]
            victim = closed[0] if closed else packet.missing_intervals[0]
            packet.missing_intervals = [
                item for item in packet.missing_intervals if item.interval_id != victim.interval_id
            ]
            return OmissionEntry(
                section="missing_intervals",
                item_id=victim.interval_id,
                detail="closed interval pruned before open unknown intervals",
            )
        if packet.conflicts:
            dropped = packet.conflicts.pop(0)
            return OmissionEntry(
                section="conflicts",
                item_id=dropped.conflict_id,
                detail="open conflict pruned only after all lower-priority content",
            )
        return None

    def _compact_omissions(
        self, packet: ResumptionPacket, request: PacketRequest
    ) -> None:
        """Bound the omission ledger, eliding oldest entries into a summary.

        Elision fires past the entry cap, and (token budgets only) while the
        packet is over budget with the ledger above its floor, so audit
        detail yields to retained content. Pure char-budget packets keep
        every entry up to the entry cap.
        """
        elided = 0
        elided_sections: Dict[str, int] = {}
        total_pruned = 0
        for entry in packet.omissions:
            if entry.reason == OMISSION_SUMMARY_REASON:
                continue
            total_pruned += 1
        summary = next(
            (
                entry
                for entry in packet.omissions
                if entry.reason == OMISSION_SUMMARY_REASON
            ),
            None,
        )
        if summary is not None:
            match = re.search(r"(\d+) oldest omission", summary.detail)
            elided = int(match.group(1)) if match else 0
            total_pruned += elided
            for section, count in re.findall(r"(\S+):(\d+)", summary.detail):
                elided_sections[section] = int(count)
        token_pressured = request.budget_tokens is not None
        while True:
            kept = sum(
                1
                for entry in packet.omissions
                if entry.reason != OMISSION_SUMMARY_REASON
            )
            past_cap = len(packet.omissions) > OMISSION_LEDGER_MAX_ENTRIES + 1
            yield_to_content = (
                token_pressured
                and kept > OMISSION_LEDGER_MIN_KEPT
                and self._over_budget(packet, request)
            )
            if not (past_cap or yield_to_content):
                break
            victim = next(
                (
                    entry
                    for entry in packet.omissions
                    if entry.reason != OMISSION_SUMMARY_REASON
                ),
                None,
            )
            if victim is None or kept <= OMISSION_LEDGER_MIN_KEPT:
                break
            packet.omissions.remove(victim)
            elided_sections[victim.section] = elided_sections.get(victim.section, 0) + 1
            elided += 1
        if elided:
            histogram = ",".join(
                f"{section}:{elided_sections[section]}"
                for section in sorted(elided_sections)
            )
            detail = (
                f"{elided} oldest omission entries elided to bound the ledger "
                f"({histogram}); {total_pruned} items pruned in total"
            )
            if summary is None:
                packet.omissions.insert(
                    0,
                    OmissionEntry(
                        section="omissions",
                        reason=OMISSION_SUMMARY_REASON,
                        detail=detail,
                    ),
                )
            else:
                summary.detail = detail

    def _enforce_budget(self, packet: ResumptionPacket, request: PacketRequest) -> None:
        packet.budget = PacketBudget(
            budget_chars=request.budget_chars,
            budget_tokens=request.budget_tokens,
        )
        if not self._over_budget(packet, request):
            return
        while self._over_budget(packet, request):
            # Shrink the audit ledger before sacrificing content: eliding an
            # old omission entry (disclosed via the summary) must win over
            # dropping retained content when either would fit.
            self._compact_omissions(packet, request)
            if not self._over_budget(packet, request):
                break
            omission = self._prune_step(packet, request)
            if omission is None:
                break
            packet.omissions.append(omission)
            self._compact_omissions(packet, request)
        packet.budget.overflow = self._over_budget(packet, request) or bool(packet.omissions)
        if self._over_budget(packet, request):
            # Mandatory core alone exceeds the budget: disclose, never
            # silently exceed.
            packet.omissions.append(
                OmissionEntry(
                    section="packet-core",
                    item_id=packet.packet_id,
                    reason="budget-exceeded-by-core",
                    detail=(
                        "mandatory core (task state, obligations, metadata) "
                        "exceeds the declared budget; packet emitted with "
                        "explicit overflow"
                    ),
                )
            )
            packet.budget.overflow = True

    def _seal(
        self,
        packet: ResumptionPacket,
        base: TaskProjection,
        request: PacketRequest,
        now: datetime,
    ) -> None:
        # Refresh volatile metadata, then count the FINAL serialization.
        packet.metadata.issued_at = now
        packet.metadata.expires_at = now + timedelta(seconds=request.ttl_seconds)
        packet.metadata.projection_digest = base.state_digest()
        packet.metadata.watermark = base.watermark
        serialized = packet.serialize()
        packet.budget.used_chars = count_chars(serialized)
        packet.budget.used_tokens = count_tokens(serialized)
        packet.budget.omission_count = len(packet.omissions)
        # Hash the canonical form with an empty hash slot (documented).
        packet.metadata.packet_hash = ""
        fingerprint = packet.serialize()
        packet.metadata.packet_hash = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        # Final recount includes the hash itself; overflow reflects reality.
        final_serialized = packet.serialize()
        packet.budget.used_chars = count_chars(final_serialized)
        packet.budget.used_tokens = count_tokens(final_serialized)
        if request.budget_chars is not None and packet.budget.used_chars > request.budget_chars:
            packet.budget.overflow = True
        if request.budget_tokens is not None and packet.budget.used_tokens > request.budget_tokens:
            packet.budget.overflow = True
