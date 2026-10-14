"""Incremental + cold-rebuild task projection from committed task events.

Consumes :class:`CommittedTaskEvent` records (a validated
:class:`~entorhinal.schemas.task_event.TaskEvent` plus its durable commit
metadata) and maintains explicit task/attempt/outcome/correction state.

Conventions (documented here because the envelope leaves them open):

- Lifecycle transitions come from ``payload.value["transition"]`` with
  values ``goal|start|pause|resume|complete|abandon`` (aliases
  ``started|paused|resumed|completed|abandoned`` accepted). A LIFECYCLE
  event without a recognized transition is kept as a timeline note and
  does not change task status.
- A task is ``completed`` only when a CHECKED_OUTCOME with outcome
  ``succeeded`` (epistemic ``checked-outcome``) exists for it. A bare
  LIFECYCLE ``complete`` without independent verification yields status
  ``complete-asserted-unverified`` and its obligation stays open.
- Claim keys: an explicit producer ``revision.claim_key`` always wins;
  otherwise keys derive deterministically as
  ``claim:{source_id}:{scope}:{attribute}`` where scope is the task ID or
  ``session:{session_id}`` when no task is present.
- Revision identities are ``rev:{sha256(canonical fields)[:16]}`` --
  stable across rebuilds, distinct per content/time/commit change.
- Succession kinds (a new revision closes the prior open revision of the
  same claim): assumption-change, decision, correction, lifecycle status,
  artifact-revision, goal. Observation and checked-outcome revisions
  coexist; differing overlapping values surface as conflicts.
- Corrections (kind or epistemic ``correction``) target a claim/interval
  via ``revision.claim_key`` + ``valid_from``/``valid_to`` and name target
  events via ``corrects``/``supersedes``. Unscoped corrections apply from
  their own valid_from onward. Within a live correction scope, later
  non-correction observations are kept but flagged contested and do not
  displace the corrected value; only a later explicit correction can
  supersede an earlier one.
- Conflicts stay visible until an explicit correction or decision names
  every losing revision's source event in ``corrects``/``supersedes``.
- Unknown observed time is preserved as ``None``; validity lower bounds
  fall back observed -> received -> committed and record which bound was
  used in ``valid_from_source``.
- Episodes: explicit task IDs lead (``episode:task:{id}``, non
  provisional). Events without a task ID attach to a provisional
  session-fallback episode labeled as heuristic.
- Obligations arise from GOAL and LIFECYCLE start/goal events; open
  questions arise from OBSERVATION outcomes unknown/inconclusive/pending
  with a condition, or DECISION ``value["question"]`` entries.
- Unknown intervals arise from SOURCE_STATUS offline/gap/degraded
  reports and from producer-sequence gaps per (source, run).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field as PydanticField

from entorhinal.schemas.models import EvidenceRecord
from entorhinal.schemas.task_event import (
    AttemptOutcome,
    EpistemicStatus,
    TaskEvent,
    TaskEventKind,
)

logger = logging.getLogger(__name__)

PROJECTION_ID = "temporal-projection/1"
PROJECTION_VERSION = "1.0.0"

# Lifecycle transition vocabulary (canonical -> accepted aliases).
TRANSITIONS: Dict[str, str] = {
    "goal": "goal",
    "start": "start",
    "started": "start",
    "pause": "pause",
    "paused": "pause",
    "resume": "resume",
    "resumed": "resume",
    "complete": "complete",
    "completed": "complete",
    "abandon": "abandon",
    "abandoned": "abandon",
}

# Kinds whose new revision of a claim closes the prior open revision.
SUCCESSION_KINDS = frozenset(
    {
        TaskEventKind.ASSUMPTION_CHANGE,
        TaskEventKind.DECISION,
        TaskEventKind.CORRECTION,
        TaskEventKind.LIFECYCLE,
        TaskEventKind.ARTIFACT_REVISION,
        TaskEventKind.GOAL,
    }
)

DECISIVE_OUTCOMES = frozenset({AttemptOutcome.SUCCEEDED, AttemptOutcome.FAILED})
UNCERTAIN_OUTCOMES = frozenset(
    {AttemptOutcome.UNKNOWN, AttemptOutcome.INCONCLUSIVE, AttemptOutcome.PENDING}
)

OFFLINE_STATUSES = frozenset({"offline", "gap", "unknown", "degraded", "outage"})
ONLINE_STATUSES = frozenset({"online", "recovered", "healthy", "ok"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _stable_hash(text: str, length: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def claim_scope(event: TaskEvent) -> str:
    """Return the claim scope: task ID, or session fallback when absent."""
    if event.work.task_id:
        return event.work.task_id
    return f"session:{event.work.session_id}"


def derive_claim_key(event: TaskEvent, attribute: Optional[str] = None) -> str:
    """Derive the stable semantic claim key for an event/attribute.

    An explicit producer ``revision.claim_key`` always wins (used verbatim).
    Otherwise the key is ``claim:{source_id}:{scope}:{attribute}`` with a
    per-kind default attribute when none is given.
    """
    if event.revision.claim_key:
        return event.revision.claim_key
    scope = claim_scope(event)
    attr = attribute
    if attr is None:
        kind = event.kind
        if kind == TaskEventKind.GOAL:
            attr = "goal"
        elif kind == TaskEventKind.LIFECYCLE:
            attr = "status"
        elif kind == TaskEventKind.CHECKED_OUTCOME:
            attempt = event.work.attempt_id or (
                event.payload.attempt.attempt_id if event.payload.attempt else None
            )
            attr = f"outcome:{attempt or event.event_id}"
        elif kind == TaskEventKind.CORRECTION:
            attr = "correction"
        else:
            attr = "value"
    return f"claim:{event.source_id}:{scope}:{attr}"


def revision_identity(
    claim_key: str,
    value_repr: str,
    valid_from: Optional[datetime],
    commit_seq: int,
    event_id: str,
) -> str:
    """Return the deterministic, distinct revision identity for a claim version."""
    canonical = json.dumps(
        {
            "claim_key": claim_key,
            "value": value_repr,
            "valid_from": _iso(valid_from),
            "commit_seq": commit_seq,
            "event_id": event_id,
        },
        sort_keys=True,
    )
    return f"rev:{_stable_hash(canonical)}"


def _value_repr(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


@dataclass(frozen=True)
class CommittedTaskEvent:
    """One task event plus its durable commit metadata.

    ``commit_seq`` is the store commit sequence (knowledge order);
    ``committed_at`` the store commit time; ``evidence_id`` the committed
    evidence identity. Observed/received times, source order and clock
    domain ride on the wrapped :class:`TaskEvent`.
    """

    event: TaskEvent
    commit_seq: int
    committed_at: datetime
    evidence_id: str
    received_at: Optional[datetime] = None
    content_hash: Optional[str] = None

    @property
    def event_id(self) -> str:
        return self.event.event_id

    @property
    def source_id(self) -> str:
        return self.event.source_id

    @property
    def kind(self) -> TaskEventKind:
        return self.event.kind

    @property
    def observed_at(self) -> Optional[datetime]:
        return self.event.time.observed_at

    @property
    def task_id(self) -> Optional[str]:
        return self.event.work.task_id

    @property
    def sort_key(self) -> Tuple[int, str]:
        return (self.commit_seq, self.event_id)

    @classmethod
    def from_evidence_record(
        cls,
        record: EvidenceRecord,
        *,
        commit_seq: int,
        committed_at: datetime,
        received_at: Optional[datetime] = None,
        evidence_id: Optional[str] = None,
        content_hash: Optional[str] = None,
    ) -> Optional["CommittedTaskEvent"]:
        """Rebuild a committed task event from a stored evidence record.

        Returns ``None`` (with a logged warning) when the record payload is
        not a task-event envelope, so replay over mixed corpora skips
        non-task evidence visibly instead of crashing.
        """
        payload = record.sanitized_payload or {}
        try:
            event = TaskEvent.model_validate(payload)
        except Exception as exc:
            logger.warning("Skipping non-task evidence %s: %s", record.record_id, exc)
            return None
        if record.is_tombstone:
            logger.warning("Skipping tombstoned evidence %s", record.record_id)
            return None
        return cls(
            event=event,
            commit_seq=commit_seq,
            committed_at=committed_at,
            evidence_id=evidence_id or record.record_id,
            received_at=received_at,
            content_hash=content_hash,
        )


# ---------------------------------------------------------------------------
# Projected state models (all pydantic, extra=forbid, per repo conventions)
# ---------------------------------------------------------------------------


class CorrectionScope(BaseModel):
    """One correction's interval of effect over a revision."""

    model_config = ConfigDict(extra="forbid")

    correction_event_id: str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    commit_seq: int = 0

    def covers(self, moment: datetime) -> bool:
        if self.valid_from is not None and moment < self.valid_from:
            return False
        if self.valid_to is not None and moment >= self.valid_to:
            return False
        return True


class ClaimRevision(BaseModel):
    """One version of a claim: distinct identity, validity, provenance."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    claim_key: str
    value: Any
    value_repr: str = ""
    valid_from: Optional[datetime] = None
    valid_from_source: str = "unknown"
    valid_to: Optional[datetime] = None
    source_event_id: str
    evidence_id: str = ""
    commit_seq: int = 0
    committed_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    source_sequence: int = 0
    producer_sequence: int = 0
    clock_domain: str = "unknown"
    precision_ms: Optional[float] = None
    uncertainty_ms: Optional[float] = None
    kind: str = ""
    epistemic: str = ""
    authoritative: bool = False  # authored by an explicit correction
    late_arrival: bool = False
    superseded_by: Optional[str] = None
    invalidated_by: List[CorrectionScope] = PydanticField(default_factory=list)
    contested_by: List[CorrectionScope] = PydanticField(default_factory=list)
    supporting_event_ids: List[str] = PydanticField(default_factory=list)
    contrary_event_ids: List[str] = PydanticField(default_factory=list)


class CorrectionRecord(BaseModel):
    """An explicit, attributable, scoped correction."""

    model_config = ConfigDict(extra="forbid")

    correction_event_id: str
    claim_key: str
    target_event_ids: List[str] = PydanticField(default_factory=list)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    scoped: bool = True  # False when scope defaulted to [valid_from, +inf)
    new_value_repr: Optional[str] = None
    author_kind: str = ""
    author_epistemic: str = ""
    commit_seq: int = 0
    committed_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    superseded_by: Optional[str] = None  # later explicit correction event id


class ConflictRecord(BaseModel):
    """Visible conflict between coexisting revisions with differing values."""

    model_config = ConfigDict(extra="forbid")

    conflict_id: str
    claim_key: str
    revision_ids: List[str] = PydanticField(default_factory=list)
    values: List[str] = PydanticField(default_factory=list)
    status: str = "open"  # open | resolved
    resolved_by: Optional[str] = None  # explicit resolution event id
    first_seen_commit_seq: int = 0


class TaskState(BaseModel):
    """Projected lifecycle state of one task."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    session_ids: List[str] = PydanticField(default_factory=list)
    goal: Optional[str] = None
    status: str = "unknown"
    status_event_id: Optional[str] = None
    status_commit_seq: int = 0
    verified_completion: bool = False
    verification_event_id: Optional[str] = None
    attempt_ids: List[str] = PydanticField(default_factory=list)
    lifecycle_event_ids: List[str] = PydanticField(default_factory=list)
    branch_ids: List[str] = PydanticField(default_factory=list)
    first_observed_at: Optional[datetime] = None
    last_observed_at: Optional[datetime] = None
    first_commit_seq: int = 0
    last_commit_seq: int = 0


class AttemptState(BaseModel):
    """One actually executed attempt; never deduped by command text."""

    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    task_id: Optional[str] = None
    session_id: str = ""
    branch_id: Optional[str] = None
    command_identity: Optional[str] = None
    check_identity: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    exit_status: Optional[int] = None
    working_directory: Optional[str] = None
    outcome: str = "unknown"
    outcome_verified: bool = False
    outcome_event_ids: List[str] = PydanticField(default_factory=list)
    attempt_event_ids: List[str] = PydanticField(default_factory=list)
    artifact_revisions: List[str] = PydanticField(default_factory=list)
    first_commit_seq: int = 0
    last_commit_seq: int = 0


class OutcomeState(BaseModel):
    """A checked (or asserted) outcome linked to an attempt/task."""

    model_config = ConfigDict(extra="forbid")

    outcome_event_id: str
    attempt_id: Optional[str] = None
    task_id: Optional[str] = None
    polarity: str = "unknown"
    verified: bool = False
    verifier: Optional[str] = None
    condition: Optional[str] = None
    artifact_revisions: List[str] = PydanticField(default_factory=list)
    commit_seq: int = 0
    committed_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None


class ObligationState(BaseModel):
    """Work that remains due until resolved or invalidated."""

    model_config = ConfigDict(extra="forbid")

    obligation_id: str
    task_id: Optional[str] = None
    description: str = ""
    source_event_id: str = ""
    source_commit_seq: int = 0
    status: str = "open"  # open | resolved | invalidated
    resolved_by: Optional[str] = None
    resolved_commit_seq: Optional[int] = None


class OpenQuestionState(BaseModel):
    """An unresolved question; never presented as fact."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    task_id: Optional[str] = None
    question: str = ""
    claim_key: Optional[str] = None
    source_event_id: str = ""
    source_commit_seq: int = 0
    status: str = "open"  # open | resolved | invalidated
    resolved_by: Optional[str] = None
    resolved_commit_seq: Optional[int] = None


class InterruptionRecord(BaseModel):
    """A pause/resume gap without an outcome in between."""

    model_config = ConfigDict(extra="forbid")

    interruption_id: str
    task_id: str = ""
    pause_event_id: str = ""
    paused_observed_at: Optional[datetime] = None
    pause_commit_seq: int = 0
    resume_event_id: Optional[str] = None
    resumed_observed_at: Optional[datetime] = None
    resume_commit_seq: Optional[int] = None
    outcome_during_pause: Optional[str] = None
    status: str = "open"  # open | resumed | ended-by-outcome


class EpisodeState(BaseModel):
    """Explicit-task episode, or a labeled provisional heuristic fallback."""

    model_config = ConfigDict(extra="forbid")

    episode_id: str
    task_ids: List[str] = PydanticField(default_factory=list)
    session_ids: List[str] = PydanticField(default_factory=list)
    boundary: str = "explicit-task"  # explicit-task | heuristic-provisional
    provisional: bool = False
    boundary_label: str = ""
    event_ids: List[str] = PydanticField(default_factory=list)
    attempt_ids: List[str] = PydanticField(default_factory=list)
    first_commit_seq: int = 0
    last_commit_seq: int = 0


class BranchState(BaseModel):
    """Branch parentage as observed; never fabricated."""

    model_config = ConfigDict(extra="forbid")

    branch_id: str
    parent_branch_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    task_ids: List[str] = PydanticField(default_factory=list)
    child_branch_ids: List[str] = PydanticField(default_factory=list)
    first_commit_seq: int = 0


class ArtifactRevisionEntry(BaseModel):
    """One observed artifact version pinned to event + commit."""

    model_config = ConfigDict(extra="forbid")

    path: str
    revision: str
    sha256: str
    verifier: Optional[str] = None
    event_id: str = ""
    task_id: Optional[str] = None
    commit_seq: int = 0
    observed_at: Optional[datetime] = None


class UnknownInterval(BaseModel):
    """An interval where absence of evidence is unknown, not inactivity."""

    model_config = ConfigDict(extra="forbid")

    interval_id: str
    source_id: str = ""
    reason: str = ""
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    start_commit_seq: int = 0
    end_commit_seq: Optional[int] = None
    open: bool = True


class SequenceGap(BaseModel):
    """A producer-sequence discontinuity: missing events, unknown content."""

    model_config = ConfigDict(extra="forbid")

    gap_id: str
    source_id: str = ""
    producer_run_id: str = ""
    expected_sequence: int = 0
    received_sequence: int = 0
    observed_commit_seq: int = 0


class TimelineEntry(BaseModel):
    """One ordered timeline note preserving times and order."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    kind: str = ""
    task_id: Optional[str] = None
    session_id: str = ""
    commit_seq: int = 0
    committed_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    source_sequence: int = 0
    producer_sequence: int = 0
    clock_domain: str = "unknown"
    summary: str = ""


# ---------------------------------------------------------------------------
# Task projection
# ---------------------------------------------------------------------------


class TaskProjection:
    """Incremental task projection with deterministic cold rebuild.

    Apply committed events via :meth:`apply` (idempotent per event ID) or
    rebuild from scratch via :meth:`rebuild`. Both paths execute the same
    ordered application, so their digests agree. Deletion/revocation
    tombstones are honored by both paths, including historical views.
    """

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        """Clear all projected state (tombstones/generations preserved by caller)."""
        self._tasks: Dict[str, TaskState] = {}
        self._attempts: Dict[str, AttemptState] = {}
        self._outcomes: Dict[str, OutcomeState] = {}
        self._claims: Dict[str, List[ClaimRevision]] = {}
        self._corrections: Dict[str, CorrectionRecord] = {}  # by event id
        self._conflicts: Dict[str, ConflictRecord] = {}  # by conflict id
        self._obligations: Dict[str, ObligationState] = {}
        self._questions: Dict[str, OpenQuestionState] = {}
        self._interruptions: Dict[str, InterruptionRecord] = {}
        self._open_interruption_by_task: Dict[str, str] = {}
        self._episodes: Dict[str, EpisodeState] = {}
        self._branches: Dict[str, BranchState] = {}
        self._artifacts: Dict[str, List[ArtifactRevisionEntry]] = {}
        self._unknown: Dict[str, UnknownInterval] = {}
        self._open_unknown_by_source: Dict[str, str] = {}
        self._gaps: Dict[str, SequenceGap] = {}
        self._timeline: List[TimelineEntry] = []
        self._log: List[CommittedTaskEvent] = []
        self._seen_event_ids: set[str] = set()
        self._last_producer_seq: Dict[Tuple[str, str], int] = {}
        self._deleted_event_ids: Dict[str, int] = {}  # event id -> generation
        self._deleted_claim_keys: Dict[str, int] = {}
        self._revoked_sources: Dict[str, int] = {}
        self._deletion_generation = 0
        self._revocation_generation = 0

    # -- accessors ------------------------------------------------------

    @property
    def tasks(self) -> Dict[str, TaskState]:
        return self._tasks

    @property
    def attempts(self) -> Dict[str, AttemptState]:
        return self._attempts

    @property
    def outcomes(self) -> Dict[str, OutcomeState]:
        return self._outcomes

    @property
    def claims(self) -> Dict[str, List[ClaimRevision]]:
        return self._claims

    @property
    def corrections(self) -> Dict[str, CorrectionRecord]:
        return self._corrections

    @property
    def conflicts(self) -> Dict[str, ConflictRecord]:
        return self._conflicts

    @property
    def obligations(self) -> Dict[str, ObligationState]:
        return self._obligations

    @property
    def open_questions(self) -> Dict[str, OpenQuestionState]:
        return self._questions

    @property
    def interruptions(self) -> Dict[str, InterruptionRecord]:
        return self._interruptions

    @property
    def episodes(self) -> Dict[str, EpisodeState]:
        return self._episodes

    @property
    def branches(self) -> Dict[str, BranchState]:
        return self._branches

    @property
    def artifacts(self) -> Dict[str, List[ArtifactRevisionEntry]]:
        return self._artifacts

    @property
    def unknown_intervals(self) -> Dict[str, UnknownInterval]:
        return self._unknown

    @property
    def sequence_gaps(self) -> Dict[str, SequenceGap]:
        return self._gaps

    @property
    def timeline(self) -> List[TimelineEntry]:
        return self._timeline

    @property
    def event_log(self) -> List[CommittedTaskEvent]:
        return list(self._log)

    @property
    def watermark(self) -> int:
        return max((entry.commit_seq for entry in self._log), default=0)

    @property
    def deletion_generation(self) -> int:
        return self._deletion_generation

    @property
    def revocation_generation(self) -> int:
        return self._revocation_generation

    @property
    def deleted_event_ids(self) -> Dict[str, int]:
        return dict(self._deleted_event_ids)

    @property
    def deleted_claim_keys(self) -> Dict[str, int]:
        return dict(self._deleted_claim_keys)

    # -- core application -------------------------------------------------

    @classmethod
    def rebuild(cls, events: Iterable[CommittedTaskEvent]) -> "TaskProjection":
        """Cold rebuild: sort by (commit_seq, event_id) and apply in order."""
        projection = cls()
        ordered = sorted(events, key=lambda entry: entry.sort_key)
        for entry in ordered:
            projection.apply(entry)
        return projection

    def apply(self, entry: CommittedTaskEvent) -> None:
        """Apply one committed event idempotently (no-op on re-application)."""
        if entry.event_id in self._seen_event_ids:
            return
        if self._is_excluded(entry):
            self._seen_event_ids.add(entry.event_id)
            return
        self._seen_event_ids.add(entry.event_id)
        self._log.append(entry)
        # Keep the log ordered even under out-of-order incremental arrival.
        self._log.sort(key=lambda item: item.sort_key)
        event = entry.event
        self._record_sequence_gap(entry)
        self._record_timeline(entry)
        self._record_episode(entry)
        self._record_branch(entry)
        self._record_artifacts(entry)
        handler = {
            TaskEventKind.GOAL: self._apply_goal,
            TaskEventKind.LIFECYCLE: self._apply_lifecycle,
            TaskEventKind.OBSERVATION: self._apply_observation,
            TaskEventKind.DECISION: self._apply_decision,
            TaskEventKind.ASSUMPTION_CHANGE: self._apply_assumption_change,
            TaskEventKind.ARTIFACT_REVISION: self._apply_artifact_revision_claim,
            TaskEventKind.ATTEMPT: self._apply_attempt,
            TaskEventKind.CHECKED_OUTCOME: self._apply_checked_outcome,
            TaskEventKind.CORRECTION: self._apply_correction,
            TaskEventKind.SOURCE_STATUS: self._apply_source_status,
        }.get(event.kind)
        if handler is not None:
            handler(entry)
        self._recompute_conflicts_for_event(entry)
        self._resolve_obligations_and_questions(entry)

    def _is_excluded(self, entry: CommittedTaskEvent) -> bool:
        if entry.event_id in self._deleted_event_ids:
            return True
        if entry.source_id in self._revoked_sources:
            return True
        return False

    def _claim_excluded(self, claim_key: str) -> bool:
        return claim_key in self._deleted_claim_keys

    # -- shared helpers -----------------------------------------------------

    def _ensure_task(self, entry: CommittedTaskEvent) -> Optional[TaskState]:
        task_id = entry.task_id
        if task_id is None:
            return None
        task = self._tasks.get(task_id)
        if task is None:
            task = TaskState(task_id=task_id, first_commit_seq=entry.commit_seq)
            self._tasks[task_id] = task
        session_id = entry.event.work.session_id
        if session_id not in task.session_ids:
            task.session_ids.append(session_id)
        observed = entry.observed_at
        if observed is not None:
            if task.first_observed_at is None or observed < task.first_observed_at:
                task.first_observed_at = observed
            if task.last_observed_at is None or observed > task.last_observed_at:
                task.last_observed_at = observed
        task.last_commit_seq = max(task.last_commit_seq, entry.commit_seq)
        return task

    def _valid_from_for(self, entry: CommittedTaskEvent) -> Tuple[Optional[datetime], str]:
        event = entry.event
        if event.revision.valid_from is not None:
            return event.revision.valid_from, "explicit"
        if event.time.observed_at is not None:
            return event.time.observed_at, "observed"
        if entry.received_at is not None:
            return entry.received_at, "received"
        return entry.committed_at, "committed"

    def _add_revision(
        self,
        entry: CommittedTaskEvent,
        claim_key: str,
        value: Any,
        *,
        authoritative: bool = False,
    ) -> Optional[ClaimRevision]:
        if self._claim_excluded(claim_key):
            logger.warning("Skipping revision for deleted claim %s", claim_key)
            return None
        event = entry.event
        valid_from, source = self._valid_from_for(entry)
        valid_to = event.revision.valid_to
        value_text = _value_repr(value)
        revision = ClaimRevision(
            revision_id=revision_identity(
                claim_key, value_text, valid_from, entry.commit_seq, entry.event_id
            ),
            claim_key=claim_key,
            value=value,
            value_repr=value_text,
            valid_from=valid_from,
            valid_from_source=source,
            valid_to=valid_to,
            source_event_id=entry.event_id,
            evidence_id=entry.evidence_id,
            commit_seq=entry.commit_seq,
            committed_at=entry.committed_at,
            observed_at=entry.observed_at,
            received_at=entry.received_at,
            source_sequence=event.time.source_sequence,
            producer_sequence=event.producer_sequence,
            clock_domain=event.time.clock_domain,
            precision_ms=event.time.precision_ms,
            uncertainty_ms=event.time.uncertainty_ms,
            kind=event.kind.value,
            epistemic=event.epistemic.value,
            authoritative=authoritative,
            supporting_event_ids=[entry.event_id],
        )
        revisions = self._claims.setdefault(claim_key, [])
        # Late arrival: committed after a revision with a later valid_from.
        for prior in revisions:
            if (
                prior.valid_from is not None
                and valid_from is not None
                and prior.valid_from > valid_from
            ):
                revision.late_arrival = True
                break
        revisions.append(revision)
        revisions.sort(key=lambda rev: (rev.commit_seq, rev.source_event_id))
        # Succession: a succession-kind revision closes the prior open one
        # only when it does not predate it in valid time (late older history
        # stays visible without displacing the current belief).
        if event.kind in SUCCESSION_KINDS or authoritative:
            for prior in revisions:
                if prior.revision_id == revision.revision_id:
                    continue
                if prior.valid_to is not None or prior.superseded_by is not None:
                    continue
                if (
                    prior.valid_from is not None
                    and valid_from is not None
                    and valid_from < prior.valid_from
                ):
                    continue
                prior.valid_to = valid_from
                prior.superseded_by = revision.revision_id
        # A live correction scope contests (but keeps) later non-correction
        # revisions that overlap it.
        if not authoritative:
            for record in self._corrections.values():
                if record.claim_key != claim_key or record.superseded_by is not None:
                    continue
                scope = CorrectionScope(
                    correction_event_id=record.correction_event_id,
                    valid_from=record.valid_from,
                    valid_to=record.valid_to,
                    commit_seq=record.commit_seq,
                )
                if record.valid_from is not None and valid_from is not None:
                    if valid_from < record.valid_from:
                        continue
                if record.valid_to is not None and valid_from is not None:
                    if valid_from >= record.valid_to:
                        continue
                revision.contested_by.append(scope)
        return revision

    # -- per-kind handlers ----------------------------------------------------

    def _apply_goal(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        task = self._ensure_task(entry)
        condition = event.payload.condition
        if task is not None:
            if condition and task.goal is None:
                task.goal = condition
            if task.status in ("unknown",):
                task.status = "open"
                task.status_event_id = entry.event_id
                task.status_commit_seq = entry.commit_seq
            task.lifecycle_event_ids.append(entry.event_id)
        claim_key = derive_claim_key(event)
        if condition:
            self._add_revision(entry, claim_key, {"goal": condition})
        if task is not None and condition:
            self._add_obligation(
                task.task_id, f"achieve: {condition}", entry
            )

    def _apply_lifecycle(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        task = self._ensure_task(entry)
        raw = event.payload.value.get("transition")
        transition = TRANSITIONS.get(str(raw).strip().lower()) if raw is not None else None
        if task is not None:
            task.lifecycle_event_ids.append(entry.event_id)
            if transition in ("goal", "start"):
                if task.status == "unknown":
                    task.status = "open"
                    task.status_event_id = entry.event_id
                    task.status_commit_seq = entry.commit_seq
                detail = event.payload.condition or f"task {transition}"
                self._add_obligation(task.task_id, f"achieve: {detail}", entry)
            elif transition == "pause":
                task.status = "paused"
                task.status_event_id = entry.event_id
                task.status_commit_seq = entry.commit_seq
                self._open_interruption(task.task_id, entry)
            elif transition == "resume":
                if task.status == "paused":
                    task.status = "in-progress"
                elif task.status == "unknown":
                    task.status = "in-progress"
                task.status_event_id = entry.event_id
                task.status_commit_seq = entry.commit_seq
                self._close_interruption(task.task_id, entry, outcome=None)
            elif transition == "complete":
                # Completion requires independent verification; a bare
                # lifecycle complete is recorded but stays unverified.
                if task.verified_completion:
                    task.status = "completed"
                else:
                    task.status = "complete-asserted-unverified"
                task.status_event_id = entry.event_id
                task.status_commit_seq = entry.commit_seq
                self._close_interruption(task.task_id, entry, outcome=None)
            elif transition == "abandon":
                task.status = "abandoned"
                task.status_event_id = entry.event_id
                task.status_commit_seq = entry.commit_seq
                self._close_interruption(task.task_id, entry, outcome=None)
            # Unrecognized/missing transition: timeline note only.
            if transition is not None and task is not None:
                claim_key = derive_claim_key(event)
                self._add_revision(entry, claim_key, {"status": task.status})

    def _apply_observation(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        self._ensure_task(entry)
        for name, item in event.payload.value.items():
            if name == "transition":
                continue
            claim_key = derive_claim_key(event, f"value:{name}")
            self._add_revision(entry, claim_key, {name: item})
        outcome = event.payload.outcome
        if outcome in UNCERTAIN_OUTCOMES and event.payload.condition:
            self._add_question(
                entry.task_id,
                event.payload.condition,
                event.revision.claim_key,
                entry,
            )

    def _apply_decision(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        self._ensure_task(entry)
        for name, item in event.payload.value.items():
            if name in ("transition", "question", "obligation"):
                continue
            claim_key = derive_claim_key(event, f"value:{name}")
            self._add_revision(entry, claim_key, {name: item})
        question = event.payload.value.get("question")
        if isinstance(question, str) and question.strip():
            self._add_question(
                entry.task_id, question.strip(), event.revision.claim_key, entry
            )
        obligation = event.payload.value.get("obligation")
        if isinstance(obligation, str) and obligation.strip() and entry.task_id:
            self._add_obligation(entry.task_id, obligation.strip(), entry)
        self._apply_explicit_resolution(entry)

    def _apply_assumption_change(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        self._ensure_task(entry)
        for name, item in event.payload.value.items():
            if name == "transition":
                continue
            claim_key = derive_claim_key(event, f"value:{name}")
            self._add_revision(entry, claim_key, {name: item})
        self._apply_explicit_resolution(entry)

    def _apply_artifact_revision_claim(self, entry: CommittedTaskEvent) -> None:
        self._ensure_task(entry)
        for ref in entry.event.payload.artifact_refs:
            claim_key = derive_claim_key(entry.event, f"artifact:{ref.path}")
            self._add_revision(
                entry, claim_key, {"revision": ref.revision, "sha256": ref.sha256}
            )

    def _attempt_id_for(self, entry: CommittedTaskEvent) -> str:
        event = entry.event
        if event.work.attempt_id:
            return event.work.attempt_id
        if event.payload.attempt is not None:
            return event.payload.attempt.attempt_id
        return f"attempt:{entry.event_id}"

    def _apply_attempt(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        task = self._ensure_task(entry)
        attempt_id = self._attempt_id_for(entry)
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            attempt = AttemptState(
                attempt_id=attempt_id,
                task_id=entry.task_id,
                session_id=event.work.session_id,
                branch_id=event.work.branch_id,
                first_commit_seq=entry.commit_seq,
            )
            self._attempts[attempt_id] = attempt
        record = event.payload.attempt
        if record is not None:
            attempt.command_identity = record.command_identity
            attempt.check_identity = record.check_identity
            attempt.started_at = record.started_at
            attempt.ended_at = record.ended_at
            attempt.exit_status = record.exit_status
            attempt.working_directory = record.working_directory
        if event.payload.outcome is not None:
            attempt.outcome = event.payload.outcome.value
        attempt.attempt_event_ids.append(entry.event_id)
        for ref in event.payload.artifact_refs:
            label = f"{ref.path}@{ref.revision}"
            if label not in attempt.artifact_revisions:
                attempt.artifact_revisions.append(label)
        attempt.last_commit_seq = entry.commit_seq
        if task is not None and attempt_id not in task.attempt_ids:
            task.attempt_ids.append(attempt_id)
            if task.status in ("unknown", "open"):
                task.status = "in-progress"
                task.status_event_id = entry.event_id
                task.status_commit_seq = entry.commit_seq
        episode = self._episode_for(entry)
        if episode is not None and attempt_id not in episode.attempt_ids:
            episode.attempt_ids.append(attempt_id)

    def _apply_checked_outcome(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        task = self._ensure_task(entry)
        attempt_id = self._attempt_id_for(entry) if (
            event.work.attempt_id or event.payload.attempt is not None
        ) else None
        polarity = event.payload.outcome.value if event.payload.outcome else "unknown"
        verifier: Optional[str] = None
        for ref in event.payload.artifact_refs:
            if ref.verifier:
                verifier = ref.verifier
                break
        verified = event.epistemic == EpistemicStatus.CHECKED_OUTCOME
        outcome = OutcomeState(
            outcome_event_id=entry.event_id,
            attempt_id=attempt_id,
            task_id=entry.task_id,
            polarity=polarity,
            verified=verified,
            verifier=verifier,
            condition=event.payload.condition,
            artifact_revisions=[
                f"{ref.path}@{ref.revision}" for ref in event.payload.artifact_refs
            ],
            commit_seq=entry.commit_seq,
            committed_at=entry.committed_at,
            observed_at=entry.observed_at,
        )
        self._outcomes[entry.event_id] = outcome
        if attempt_id is not None and attempt_id in self._attempts:
            attempt = self._attempts[attempt_id]
            attempt.outcome = polarity
            attempt.outcome_verified = verified
            attempt.outcome_event_ids.append(entry.event_id)
            attempt.last_commit_seq = entry.commit_seq
        claim_key = derive_claim_key(event)
        self._add_revision(entry, claim_key, {"outcome": polarity, "verified": verified})
        if task is not None and polarity == AttemptOutcome.SUCCEEDED.value and verified:
            task.verified_completion = True
            task.verification_event_id = entry.event_id
            if task.status == "complete-asserted-unverified":
                task.status = "completed"
                task.status_event_id = entry.event_id
                task.status_commit_seq = entry.commit_seq
        if task is not None and polarity in (
            AttemptOutcome.SUCCEEDED.value,
            AttemptOutcome.FAILED.value,
        ):
            interruption_id = self._open_interruption_by_task.get(task.task_id)
            if interruption_id is not None:
                record = self._interruptions[interruption_id]
                record.outcome_during_pause = polarity
                record.status = "ended-by-outcome"

    def _is_explicit_correction(self, entry: CommittedTaskEvent) -> bool:
        event = entry.event
        return (
            event.kind == TaskEventKind.CORRECTION
            or event.epistemic == EpistemicStatus.CORRECTION
        )

    def _apply_correction(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        self._ensure_task(entry)
        claim_key = event.revision.claim_key or derive_claim_key(event)
        if self._claim_excluded(claim_key):
            logger.warning("Skipping correction for deleted claim %s", claim_key)
            return
        valid_from, from_source = self._valid_from_for(entry)
        scoped = event.revision.valid_from is not None or event.revision.valid_to is not None
        targets = list(event.revision.corrects) + list(event.revision.supersedes)
        record = CorrectionRecord(
            correction_event_id=entry.event_id,
            claim_key=claim_key,
            target_event_ids=targets,
            valid_from=valid_from,
            valid_to=event.revision.valid_to,
            scoped=scoped,
            author_kind=event.kind.value,
            author_epistemic=event.epistemic.value,
            commit_seq=entry.commit_seq,
            committed_at=entry.committed_at,
            observed_at=entry.observed_at,
        )
        # A later explicit correction supersedes earlier overlapping ones on
        # the same claim; nothing else may silently override a correction.
        for prior in self._corrections.values():
            if prior.claim_key != claim_key or prior.superseded_by is not None:
                continue
            if self._scopes_overlap(
                prior.valid_from, prior.valid_to, record.valid_from, record.valid_to
            ):
                prior.superseded_by = entry.event_id
        # Invalidate targets FIRST (while still open, so scope overlap is
        # evaluated against the uncorrected intervals), then add the
        # authoritative revision. A correction with no value entries is a
        # pure scoped invalidation of its targets.
        self._corrections[entry.event_id] = record
        scope = CorrectionScope(
            correction_event_id=entry.event_id,
            valid_from=record.valid_from,
            valid_to=record.valid_to,
            commit_seq=entry.commit_seq,
        )
        for revision in self._claims.get(record.claim_key, []):
            if revision.source_event_id == entry.event_id:
                continue
            if revision.authoritative and revision.commit_seq >= entry.commit_seq:
                continue
            if targets and revision.source_event_id not in targets:
                continue
            if not self._revision_overlaps_scope(revision, scope):
                continue
            if not any(
                item.correction_event_id == entry.event_id
                for item in revision.invalidated_by
            ):
                revision.invalidated_by.append(scope)
        value_entries = {
            name: item
            for name, item in event.payload.value.items()
            if name not in ("transition", "question", "obligation")
        }
        if value_entries:
            record.new_value_repr = _value_repr(value_entries)
            for name, item in value_entries.items():
                key = claim_key
                if not event.revision.claim_key:
                    key = derive_claim_key(event, f"value:{name}")
                    record.claim_key = key
                self._add_revision(entry, key, {name: item}, authoritative=True)
        self._apply_explicit_resolution(entry)

    @staticmethod
    def _scopes_overlap(
        first_from: Optional[datetime],
        first_to: Optional[datetime],
        second_from: Optional[datetime],
        second_to: Optional[datetime],
    ) -> bool:
        latest_start: Optional[datetime] = None
        if first_from is not None and second_from is not None:
            latest_start = max(first_from, second_from)
        else:
            latest_start = first_from or second_from
        earliest_end: Optional[datetime] = None
        if first_to is not None and second_to is not None:
            earliest_end = min(first_to, second_to)
        else:
            earliest_end = first_to or second_to
        if latest_start is not None and earliest_end is not None:
            return latest_start < earliest_end
        return True

    @staticmethod
    def _revision_overlaps_scope(revision: ClaimRevision, scope: CorrectionScope) -> bool:
        return TaskProjection._scopes_overlap(
            revision.valid_from, revision.valid_to, scope.valid_from, scope.valid_to
        )

    def _apply_explicit_resolution(self, entry: CommittedTaskEvent) -> None:
        """Resolve conflicts explicitly named by a correction/decision."""
        event = entry.event
        named = set(event.revision.corrects) | set(event.revision.supersedes)
        if not named:
            return
        for conflict in self._conflicts.values():
            if conflict.status != "open":
                continue
            if event.revision.claim_key and conflict.claim_key != event.revision.claim_key:
                continue
            revisions = self._claims.get(conflict.claim_key, [])
            by_id = {rev.revision_id: rev for rev in revisions}
            involved = [by_id[rid] for rid in conflict.revision_ids if rid in by_id]
            losers = [rev for rev in involved if rev.source_event_id in named]
            survivors = [rev for rev in involved if rev.source_event_id not in named]
            if losers and len(survivors) == 1:
                conflict.status = "resolved"
                conflict.resolved_by = entry.event_id

    def _apply_source_status(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        raw_status = event.payload.value.get("status")
        status = str(raw_status).strip().lower() if raw_status is not None else ""
        source_id = entry.source_id
        if status in OFFLINE_STATUSES:
            if source_id in self._open_unknown_by_source:
                return
            interval_id = f"unknown:{source_id}:{entry.commit_seq}:{entry.event_id}"
            interval = UnknownInterval(
                interval_id=interval_id,
                source_id=source_id,
                reason=f"source-status:{status or 'unspecified'}",
                started_at=entry.observed_at or entry.received_at or entry.committed_at,
                start_commit_seq=entry.commit_seq,
                open=True,
            )
            self._unknown[interval_id] = interval
            self._open_unknown_by_source[source_id] = interval_id
        elif status in ONLINE_STATUSES:
            interval_id = self._open_unknown_by_source.pop(source_id, None)
            if interval_id is not None and interval_id in self._unknown:
                interval = self._unknown[interval_id]
                interval.ended_at = (
                    entry.observed_at or entry.received_at or entry.committed_at
                )
                interval.end_commit_seq = entry.commit_seq
                interval.open = False

    # -- obligations / questions / interruptions -------------------------------

    def _add_obligation(
        self, task_id: str, description: str, entry: CommittedTaskEvent
    ) -> ObligationState:
        obligation_id = (
            f"obl:{_stable_hash(entry.source_id + task_id + description + entry.event_id, 12)}"
        )
        existing = self._obligations.get(obligation_id)
        if existing is not None:
            return existing
        obligation = ObligationState(
            obligation_id=obligation_id,
            task_id=task_id,
            description=description,
            source_event_id=entry.event_id,
            source_commit_seq=entry.commit_seq,
        )
        self._obligations[obligation_id] = obligation
        return obligation

    def _add_question(
        self,
        task_id: Optional[str],
        question: str,
        claim_key: Optional[str],
        entry: CommittedTaskEvent,
    ) -> OpenQuestionState:
        question_id = (
            f"q:{_stable_hash(entry.source_id + (task_id or '') + question + entry.event_id, 12)}"
        )
        existing = self._questions.get(question_id)
        if existing is not None:
            return existing
        state = OpenQuestionState(
            question_id=question_id,
            task_id=task_id,
            question=question,
            claim_key=claim_key,
            source_event_id=entry.event_id,
            source_commit_seq=entry.commit_seq,
        )
        self._questions[question_id] = state
        return state

    def _resolve_obligations_and_questions(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        named = set(event.revision.corrects) | set(event.revision.supersedes)
        for obligation in self._obligations.values():
            if obligation.status != "open":
                continue
            if obligation.source_event_id in named and self._is_explicit_correction(entry):
                obligation.status = "invalidated"
                obligation.resolved_by = entry.event_id
                obligation.resolved_commit_seq = entry.commit_seq
                continue
            if obligation.task_id != entry.task_id or entry.task_id is None:
                continue
            if event.kind == TaskEventKind.CHECKED_OUTCOME and event.payload.outcome == AttemptOutcome.SUCCEEDED:
                if event.epistemic == EpistemicStatus.CHECKED_OUTCOME:
                    obligation.status = "resolved"
                    obligation.resolved_by = entry.event_id
                    obligation.resolved_commit_seq = entry.commit_seq
        for question in self._questions.values():
            if question.status != "open":
                continue
            if question.source_event_id in named and self._is_explicit_correction(entry):
                question.status = "invalidated"
                question.resolved_by = entry.event_id
                question.resolved_commit_seq = entry.commit_seq
                continue
            if question.task_id is not None and question.task_id != entry.task_id:
                continue
            if question.claim_key is not None and entry.commit_seq > question.source_commit_seq:
                revisions = self._claims.get(question.claim_key, [])
                for revision in revisions:
                    if revision.commit_seq <= question.source_commit_seq:
                        continue
                    if revision.commit_seq > entry.commit_seq:
                        continue
                    text = revision.value_repr.lower()
                    if "succeeded" in text or "failed" in text:
                        question.status = "resolved"
                        question.resolved_by = revision.source_event_id
                        question.resolved_commit_seq = revision.commit_seq
                        break

    def _open_interruption(self, task_id: str, entry: CommittedTaskEvent) -> None:
        if task_id in self._open_interruption_by_task:
            return
        interruption_id = f"int:{task_id}:{entry.event_id}"
        record = InterruptionRecord(
            interruption_id=interruption_id,
            task_id=task_id,
            pause_event_id=entry.event_id,
            paused_observed_at=entry.observed_at,
            pause_commit_seq=entry.commit_seq,
        )
        self._interruptions[interruption_id] = record
        self._open_interruption_by_task[task_id] = interruption_id

    def _close_interruption(
        self, task_id: str, entry: CommittedTaskEvent, outcome: Optional[str]
    ) -> None:
        interruption_id = self._open_interruption_by_task.pop(task_id, None)
        if interruption_id is None:
            return
        record = self._interruptions.get(interruption_id)
        if record is None or record.status != "open":
            return
        record.resume_event_id = entry.event_id
        record.resumed_observed_at = entry.observed_at
        record.resume_commit_seq = entry.commit_seq
        record.outcome_during_pause = outcome or record.outcome_during_pause
        record.status = "resumed"

    # -- conflicts ---------------------------------------------------------------

    def _recompute_conflicts_for_event(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        touched: set[str] = set()
        for revisions_key, revisions in self._claims.items():
            if any(rev.source_event_id == entry.event_id for rev in revisions):
                touched.add(revisions_key)
        if event.revision.claim_key:
            touched.add(event.revision.claim_key)
        for claim_key in touched:
            self._recompute_conflicts(claim_key)

    def _recompute_conflicts(self, claim_key: str) -> None:
        revisions = self._claims.get(claim_key, [])
        active = [
            rev
            for rev in revisions
            if rev.superseded_by is None and not rev.invalidated_by
        ]
        groups: Dict[str, List[ClaimRevision]] = {}
        for rev in active:
            groups.setdefault(rev.value_repr, []).append(rev)
        if len(groups) < 2:
            return
        members: List[ClaimRevision] = []
        for group in groups.values():
            members.extend(group)
        # Only revisions with mutually overlapping validity conflict.
        overlapping: List[ClaimRevision] = []
        for rev in members:
            for other in members:
                if rev.revision_id == other.revision_id:
                    continue
                if rev.value_repr == other.value_repr:
                    continue
                if self._scopes_overlap(
                    rev.valid_from, rev.valid_to, other.valid_from, other.valid_to
                ):
                    overlapping.append(rev)
                    break
        if len(overlapping) < 2:
            return
        member_ids = sorted(rev.revision_id for rev in overlapping)
        conflict_id = f"conflict:{_stable_hash(claim_key + '|' + '|'.join(member_ids), 12)}"
        existing = self._conflicts.get(conflict_id)
        if existing is not None:
            return
        values = sorted({rev.value_repr for rev in overlapping})
        self._conflicts[conflict_id] = ConflictRecord(
            conflict_id=conflict_id,
            claim_key=claim_key,
            revision_ids=member_ids,
            values=values,
            first_seen_commit_seq=max(rev.commit_seq for rev in overlapping),
        )

    # -- structural recorders ------------------------------------------------------

    def _record_sequence_gap(self, entry: CommittedTaskEvent) -> None:
        key = (entry.source_id, entry.event.producer_run_id)
        previous = self._last_producer_seq.get(key)
        current = entry.event.producer_sequence
        if previous is not None and current > previous + 1:
            gap_id = f"gap:{entry.source_id}:{entry.event.producer_run_id}:{previous + 1}-{current}"
            self._gaps[gap_id] = SequenceGap(
                gap_id=gap_id,
                source_id=entry.source_id,
                producer_run_id=entry.event.producer_run_id,
                expected_sequence=previous + 1,
                received_sequence=current,
                observed_commit_seq=entry.commit_seq,
            )
        if previous is None or current > previous:
            self._last_producer_seq[key] = current

    def _record_timeline(self, entry: CommittedTaskEvent) -> None:
        event = entry.event
        summary = event.payload.condition or ""
        if not summary and event.payload.value:
            first_key = sorted(event.payload.value.keys())[0]
            summary = f"{first_key}={event.payload.value[first_key]}"
        if not summary and event.payload.attempt is not None:
            summary = event.payload.attempt.command_identity
        self._timeline.append(
            TimelineEntry(
                event_id=entry.event_id,
                kind=event.kind.value,
                task_id=entry.task_id,
                session_id=event.work.session_id,
                commit_seq=entry.commit_seq,
                committed_at=entry.committed_at,
                observed_at=entry.observed_at,
                received_at=entry.received_at,
                source_sequence=event.time.source_sequence,
                producer_sequence=event.producer_sequence,
                clock_domain=event.time.clock_domain,
                summary=summary[:280],
            )
        )
        self._timeline.sort(key=lambda item: (item.commit_seq, item.event_id))

    def _episode_id_for(self, entry: CommittedTaskEvent) -> str:
        if entry.task_id:
            return f"episode:task:{entry.task_id}"
        return f"episode:session:{entry.event.work.session_id}"

    def _episode_for(self, entry: CommittedTaskEvent) -> Optional[EpisodeState]:
        return self._episodes.get(self._episode_id_for(entry))

    def _record_episode(self, entry: CommittedTaskEvent) -> None:
        episode_id = self._episode_id_for(entry)
        episode = self._episodes.get(episode_id)
        if episode is None:
            provisional = entry.task_id is None
            episode = EpisodeState(
                episode_id=episode_id,
                boundary="heuristic-provisional" if provisional else "explicit-task",
                provisional=provisional,
                boundary_label=(
                    "heuristic:session-fallback (no explicit task ID; provisional)"
                    if provisional
                    else "explicit:task-id"
                ),
                first_commit_seq=entry.commit_seq,
            )
            self._episodes[episode_id] = episode
        if entry.task_id and entry.task_id not in episode.task_ids:
            episode.task_ids.append(entry.task_id)
        session_id = entry.event.work.session_id
        if session_id not in episode.session_ids:
            episode.session_ids.append(session_id)
        if entry.event_id not in episode.event_ids:
            episode.event_ids.append(entry.event_id)
        episode.event_ids.sort(
            key=lambda eid: next(
                (item.commit_seq for item in self._log if item.event_id == eid), 0
            )
        )
        episode.last_commit_seq = entry.commit_seq

    def _record_branch(self, entry: CommittedTaskEvent) -> None:
        work = entry.event.work
        branch_id = work.branch_id
        task = self._tasks.get(work.task_id or "")
        if branch_id is None:
            if work.parent_branch_id and task is not None:
                # Parent-only reference: record the parent so lineage is kept.
                self._ensure_branch(work.parent_branch_id, entry, parent_of=None)
            return
        branch = self._ensure_branch(branch_id, entry, parent_of=work.parent_branch_id)
        if work.parent_task_id and branch.parent_task_id is None:
            branch.parent_task_id = work.parent_task_id
        if work.task_id and work.task_id not in branch.task_ids:
            branch.task_ids.append(work.task_id)
        if work.parent_branch_id:
            parent = self._ensure_branch(work.parent_branch_id, entry, parent_of=None)
            if branch_id not in parent.child_branch_ids:
                parent.child_branch_ids.append(branch_id)
                parent.child_branch_ids.sort()
        if task is not None and branch_id not in task.branch_ids:
            task.branch_ids.append(branch_id)

    def _ensure_branch(
        self, branch_id: str, entry: CommittedTaskEvent, parent_of: Optional[str]
    ) -> BranchState:
        branch = self._branches.get(branch_id)
        if branch is None:
            branch = BranchState(branch_id=branch_id, first_commit_seq=entry.commit_seq)
            self._branches[branch_id] = branch
        if parent_of and branch.parent_branch_id is None:
            branch.parent_branch_id = parent_of
        return branch

    def _record_artifacts(self, entry: CommittedTaskEvent) -> None:
        for ref in entry.event.payload.artifact_refs:
            history = self._artifacts.setdefault(ref.path, [])
            history.append(
                ArtifactRevisionEntry(
                    path=ref.path,
                    revision=ref.revision,
                    sha256=ref.sha256,
                    verifier=ref.verifier,
                    event_id=entry.event_id,
                    task_id=entry.task_id,
                    commit_seq=entry.commit_seq,
                    observed_at=entry.observed_at,
                )
            )
            history.sort(key=lambda item: (item.commit_seq, item.event_id))

    # -- user control: deletion / revocation ----------------------------------------

    def adopt_generations(self, *, deletion: int, revocation: int) -> None:
        """Adopt durable control generations after a rebuild from the store.

        The runtime projection holder rebuilds from committed records (which
        already exclude tombstoned evidence) and then adopts the store's
        persisted deletion/revocation generations so served views report the
        generations consumers use to detect forget/revoke. Generations never
        move backwards.
        """
        self._deletion_generation = max(self._deletion_generation, int(deletion))
        self._revocation_generation = max(self._revocation_generation, int(revocation))

    def apply_deletion(self, targets: Iterable[str], reason: str = "") -> int:
        """Tombstone event IDs and/or claim keys; returns the new generation.

        Targets naming an event ID exclude that event; targets naming a claim
        key exclude that claim. Every query -- including historical cutoff
        queries -- honors these tombstones. Reason is recorded in the log
        only (never stored denied content).
        """
        materialized = list(targets)
        self._deletion_generation += 1
        generation = self._deletion_generation
        known_events = {entry.event_id for entry in self._log} | set(self._deleted_event_ids)
        for target in materialized:
            if target in self._claims or (
                target.startswith("claim:") and target not in known_events
            ):
                self._deleted_claim_keys[target] = generation
            else:
                self._deleted_event_ids[target] = generation
        logger.info(
            "Applied deletion generation %d (%d targets): %s",
            generation,
            len(materialized),
            reason,
        )
        self._reproject_after_control()
        return generation

    def apply_revocation(self, sources: Iterable[str], reason: str = "") -> int:
        """Revoke whole sources; returns the new revocation generation."""
        self._revocation_generation += 1
        generation = self._revocation_generation
        for source_id in sources:
            self._revoked_sources[source_id] = generation
        logger.info("Applied revocation generation %d: %s", generation, reason)
        self._reproject_after_control()
        return generation

    def _reproject_after_control(self) -> None:
        """Rebuild projected state from the log honoring current tombstones."""
        log = list(self._log)
        tombstoned_events = dict(self._deleted_event_ids)
        tombstoned_claims = dict(self._deleted_claim_keys)
        revoked = dict(self._revoked_sources)
        deletion_generation = self._deletion_generation
        revocation_generation = self._revocation_generation
        self._reset()
        self._deleted_event_ids = tombstoned_events
        self._deleted_claim_keys = tombstoned_claims
        self._revoked_sources = revoked
        self._deletion_generation = deletion_generation
        self._revocation_generation = revocation_generation
        for entry in log:
            self.apply(entry)

    def spawn_filtered(
        self,
        max_commit_seq: Optional[int] = None,
        max_committed_at: Optional[datetime] = None,
    ) -> "TaskProjection":
        """Return a new projection over the log prefix, honoring tombstones.

        Used for knowledge-cutoff queries: only entries at or below the
        watermark are applied, while the *current* deletion/revocation
        generations (and their tombstones) apply to every historical view.
        """
        child = TaskProjection()
        child._deleted_event_ids = dict(self._deleted_event_ids)
        child._deleted_claim_keys = dict(self._deleted_claim_keys)
        child._revoked_sources = dict(self._revoked_sources)
        child._deletion_generation = self._deletion_generation
        child._revocation_generation = self._revocation_generation
        for entry in self._log:
            if max_commit_seq is not None and entry.commit_seq > max_commit_seq:
                continue
            if max_committed_at is not None and entry.committed_at > max_committed_at:
                continue
            child.apply(entry)
        return child

    # -- digest / serialization -------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Canonical dictionary of the full projected state (JSON-safe)."""
        return {
            "projection_id": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
            "watermark": self.watermark,
            "deletion_generation": self._deletion_generation,
            "revocation_generation": self._revocation_generation,
            "tasks": {key: item.model_dump(mode="json") for key, item in sorted(self._tasks.items())},
            "attempts": {key: item.model_dump(mode="json") for key, item in sorted(self._attempts.items())},
            "outcomes": {key: item.model_dump(mode="json") for key, item in sorted(self._outcomes.items())},
            "claims": {
                key: [rev.model_dump(mode="json") for rev in revisions]
                for key, revisions in sorted(self._claims.items())
            },
            "corrections": {key: item.model_dump(mode="json") for key, item in sorted(self._corrections.items())},
            "conflicts": {key: item.model_dump(mode="json") for key, item in sorted(self._conflicts.items())},
            "obligations": {key: item.model_dump(mode="json") for key, item in sorted(self._obligations.items())},
            "open_questions": {key: item.model_dump(mode="json") for key, item in sorted(self._questions.items())},
            "interruptions": {key: item.model_dump(mode="json") for key, item in sorted(self._interruptions.items())},
            "episodes": {key: item.model_dump(mode="json") for key, item in sorted(self._episodes.items())},
            "branches": {key: item.model_dump(mode="json") for key, item in sorted(self._branches.items())},
            "artifacts": {
                key: [item.model_dump(mode="json") for item in history]
                for key, history in sorted(self._artifacts.items())
            },
            "unknown_intervals": {key: item.model_dump(mode="json") for key, item in sorted(self._unknown.items())},
            "sequence_gaps": {key: item.model_dump(mode="json") for key, item in sorted(self._gaps.items())},
            "timeline": [item.model_dump(mode="json") for item in self._timeline],
            "deleted_event_ids": dict(sorted(self._deleted_event_ids.items())),
            "deleted_claim_keys": dict(sorted(self._deleted_claim_keys.items())),
            "revoked_sources": dict(sorted(self._revoked_sources.items())),
        }

    def state_digest(self) -> str:
        """Deterministic digest of the projected state (rebuild agreement)."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
