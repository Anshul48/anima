"""Task-event envelope for source `entorhinal.dev-task.01` (EAP-20261004-v0.2).

Contract: `entorhinal.task-event/v1-draft`. This is the first real producer path:
an external emitter publishes explicit task events as JSONL into one configured
inbox file; Entorhinal only observes (tails) that inbox.

Strictness posture (default-deny):
- every model here uses ``extra="forbid"``: undeclared fields are rejected;
- artifact references resolve against an explicit producer manifest allow-list;
- payload excerpts are bounded and sanitized before any spool persistence.

No credential-bearing values may appear in fixtures or defaults.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from entorhinal.schemas.models import RawSignalEvent, SourceType

TASK_EVENT_CONTRACT_VERSION = "entorhinal.task-event/v1-draft"

DEV_TASK_SOURCE_ID = "entorhinal.dev-task.01"

# Payload excerpt bounds (characters). Excerpts carry deliberately emitted short
# diagnostic text only; whole environment dumps are outside this source.
MAX_EXCERPT_CHARS = 4096
MAX_EXCERPT_COUNT = 8
MAX_TOTAL_EXCERPT_CHARS = 16384

# Bounded free-form value map inside the payload.
MAX_VALUE_ENTRIES = 32
MAX_VALUE_STRING_CHARS = 1024


class TaskEventKind(str, Enum):
    """Explicit task-event kinds. Unknown kinds are rejected, never coerced."""

    GOAL = "goal"
    LIFECYCLE = "lifecycle"
    OBSERVATION = "observation"
    DECISION = "decision"
    ASSUMPTION_CHANGE = "assumption-change"
    ARTIFACT_REVISION = "artifact-revision"
    ATTEMPT = "attempt"
    CHECKED_OUTCOME = "checked-outcome"
    CORRECTION = "correction"
    SOURCE_STATUS = "source-status"


class EpistemicStatus(str, Enum):
    """Epistemic standing of the event content."""

    OBSERVATION = "observation"
    ASSERTION = "assertion"
    HYPOTHESIS = "hypothesis"
    CORRECTION = "correction"
    CHECKED_OUTCOME = "checked-outcome"


class AttemptOutcome(str, Enum):
    """Structured outcome polarity for attempt / checked-outcome payloads."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    PENDING = "pending"
    UNKNOWN = "unknown"


class WorkIdentity(BaseModel):
    """Session/task/attempt/branch identity with parent links.

    Omitted context is explicit (None); callers must never fabricate a
    search tree or invent parent IDs.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    task_id: Optional[str] = Field(default=None, min_length=1)
    attempt_id: Optional[str] = Field(default=None, min_length=1)
    branch_id: Optional[str] = Field(default=None, min_length=1)
    parent_session_id: Optional[str] = Field(default=None, min_length=1)
    parent_task_id: Optional[str] = Field(default=None, min_length=1)
    parent_attempt_id: Optional[str] = Field(default=None, min_length=1)
    parent_branch_id: Optional[str] = Field(default=None, min_length=1)


class EventTiming(BaseModel):
    """Observed / received / committed times with clock metadata.

    The emitter sets ``observed_at`` (or leaves it None when genuinely
    unknown) and ``source_sequence``. The daemon fills ``received_at`` and
    ``committed_at``; they are None on the producer side of the inbox.
    Unknown observed time remains unknown: it is never backfilled with the
    received time.
    """

    model_config = ConfigDict(extra="forbid")

    observed_at: Optional[datetime] = Field(default=None)
    received_at: Optional[datetime] = Field(default=None)
    committed_at: Optional[datetime] = Field(default=None)
    clock_domain: str = Field(default="unknown", min_length=1)
    precision_ms: Optional[float] = Field(default=None, ge=0.0)
    uncertainty_ms: Optional[float] = Field(default=None, ge=0.0)
    source_sequence: int = Field(..., ge=0)


class PayloadExcerpt(BaseModel):
    """One bounded, sanitized diagnostic excerpt."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=128)
    text: str = Field(..., max_length=MAX_EXCERPT_CHARS)
    truncated: bool = Field(default=False)


class ArtifactRef(BaseModel):
    """Reference to one exact allow-listed artifact file.

    A mutable path is not an immutable evidence version: the content hash
    and revision pin the version the producer observed. The path must match
    an entry of the producer manifest allow-list exactly (after
    normalization); anything else is rejected at admission.
    """

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., min_length=1, max_length=1024)
    sha256: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    revision: str = Field(..., min_length=1, max_length=128)
    verifier: Optional[str] = Field(default=None, min_length=1, max_length=256)

    @field_validator("path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        normalized = normalize_artifact_path(value)
        if not normalized:
            raise ValueError("artifact path must be a non-empty absolute posix path")
        return normalized


class AttemptRecord(BaseModel):
    """One actually executed attempt: command/check identity and real outcome.

    The emitter executes the command in an external harness and records the
    real start/end and exit status. Entorhinal never executes commands.
    """

    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(..., min_length=1, max_length=256)
    command_identity: str = Field(..., min_length=1, max_length=1024)
    check_identity: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    started_at: datetime
    ended_at: Optional[datetime] = Field(default=None)
    exit_status: Optional[int] = Field(default=None)
    working_directory: Optional[str] = Field(default=None, min_length=1, max_length=1024)


class TaskEventPayload(BaseModel):
    """Structured outcome/value/condition plus bounded evidence."""

    model_config = ConfigDict(extra="forbid")

    outcome: Optional[AttemptOutcome] = Field(default=None)
    value: Dict[str, Optional[str | int | float | bool]] = Field(default_factory=dict)
    condition: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    excerpts: List[PayloadExcerpt] = Field(default_factory=list, max_length=MAX_EXCERPT_COUNT)
    artifact_refs: List[ArtifactRef] = Field(default_factory=list, max_length=32)
    attempt: Optional[AttemptRecord] = Field(default=None)

    @field_validator("value")
    @classmethod
    def _bound_value_map(
        cls, mapping: Dict[str, Optional[str | int | float | bool]]
    ) -> Dict[str, Optional[str | int | float | bool]]:
        if len(mapping) > MAX_VALUE_ENTRIES:
            raise ValueError(f"value map exceeds {MAX_VALUE_ENTRIES} entries")
        for key, item in mapping.items():
            if len(key) > 128:
                raise ValueError("value key exceeds 128 characters")
            if isinstance(item, str) and len(item) > MAX_VALUE_STRING_CHARS:
                raise ValueError("value string exceeds bound")
        return mapping

    @model_validator(mode="after")
    def _bound_total_excerpts(self) -> "TaskEventPayload":
        total = sum(len(excerpt.text) for excerpt in self.excerpts)
        if total > MAX_TOTAL_EXCERPT_CHARS:
            raise ValueError(
                f"total excerpt text {total} exceeds {MAX_TOTAL_EXCERPT_CHARS} characters"
            )
        return self


class RevisionLink(BaseModel):
    """Correction / supersession links with a stable claim key and validity."""

    model_config = ConfigDict(extra="forbid")

    corrects: List[str] = Field(default_factory=list, max_length=32)
    supersedes: List[str] = Field(default_factory=list, max_length=32)
    claim_key: Optional[str] = Field(default=None, min_length=1, max_length=512)
    valid_from: Optional[datetime] = Field(default=None)
    valid_to: Optional[datetime] = Field(default=None)


class AdmissionLifecycle(BaseModel):
    """Admission and lifecycle metadata carried with the event."""

    model_config = ConfigDict(extra="forbid")

    grant_revision: str = Field(..., min_length=1, max_length=128)
    redaction_outcome: Optional[str] = Field(default=None, max_length=1024)
    retention_class: str = Field(default="payload-30d", min_length=1, max_length=128)
    deletion_generation: int = Field(default=0, ge=0)
    revocation_generation: int = Field(default=0, ge=0)


class AssistanceResources(BaseModel):
    """Model/policy/config identity and resource accounting when used.

    Unknown measurements remain None with a reason; they are never zeroed
    into fake precision.
    """

    model_config = ConfigDict(extra="forbid")

    model_identity: Optional[str] = Field(default=None, min_length=1, max_length=256)
    policy_identity: Optional[str] = Field(default=None, min_length=1, max_length=256)
    config_identity: Optional[str] = Field(default=None, min_length=1, max_length=256)
    branch_lineage: List[str] = Field(default_factory=list, max_length=32)
    latency_ms: Optional[float] = Field(default=None, ge=0.0)
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    status: str = Field(default="unknown", min_length=1, max_length=64)
    status_reason: Optional[str] = Field(default=None, max_length=1024)


class TaskEvent(BaseModel):
    """Envelope `entorhinal.task-event/v1-draft` for source `entorhinal.dev-task.01`."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["entorhinal.task-event/v1-draft"] = Field(
        default="entorhinal.task-event/v1-draft"
    )
    source_id: str = Field(..., min_length=1, max_length=256)
    event_id: str = Field(..., min_length=1, max_length=256)
    producer_run_id: str = Field(..., min_length=1, max_length=256)
    producer_sequence: int = Field(..., ge=0)
    producer_version: str = Field(..., min_length=1, max_length=256)
    work: WorkIdentity
    kind: TaskEventKind
    time: EventTiming
    payload: TaskEventPayload = Field(default_factory=TaskEventPayload)
    epistemic: EpistemicStatus
    revision: RevisionLink = Field(default_factory=RevisionLink)
    admission: AdmissionLifecycle
    assistance: AssistanceResources = Field(default_factory=AssistanceResources)

    def to_raw_signal_event(self) -> RawSignalEvent:
        """Convert into a RawSignalEvent, preserving observed time and source identity.

        Unlike the legacy observation path, the original observed timestamp
        and the configured source ID are retained on the converted signal.
        """
        captured = self.time.observed_at or datetime.now(timezone.utc)
        app_id = f"dev-task:{self.work.session_id}"
        title = f"{self.kind.value}:{self.event_id}"
        return RawSignalEvent(
            # Stable event ID is the idempotency key: every conversion of the
            # same task event MUST carry the same signal_id so exact retries
            # and spool replays commit exactly once.
            signal_id=self.event_id,
            source_type=SourceType.TERMINAL_PTY,
            adapter_id=self.source_id,
            captured_at=captured,
            app_identifier=app_id,
            window_title=title,
            target_uri=None,
            raw_payload=self.model_dump(mode="json"),
            metadata={
                "contract_version": self.contract_version,
                "event_id": self.event_id,
                # Original observed time (ISO string) or None when genuinely
                # unknown. RawSignalEvent.captured_at cannot stay None, so the
                # store path reads this key to preserve unknown observations.
                "observed_at": self.time.observed_at.isoformat()
                if self.time.observed_at is not None
                else None,
                "producer_run_id": self.producer_run_id,
                "producer_sequence": self.producer_sequence,
                "kind": self.kind.value,
                "epistemic": self.epistemic.value,
                "source_sequence": self.time.source_sequence,
                "clock_domain": self.time.clock_domain,
            },
        )


def normalize_artifact_path(path: str) -> str:
    """Normalize an artifact path for exact allow-list comparison.

    Only absolute posix paths without ``..`` segments are accepted; anything
    else normalizes to the empty string (rejected by the caller).
    """
    text = (path or "").strip()
    if not text.startswith("/"):
        return ""
    posix = PurePosixPath(text)
    if ".." in posix.parts:
        return ""
    return posix.as_posix()


class ManifestArtifact(BaseModel):
    """One exact allow-listed artifact file in the producer manifest."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., min_length=1, max_length=1024)
    sha256: Optional[str] = Field(
        default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    revision: Optional[str] = Field(default=None, min_length=1, max_length=128)

    @field_validator("path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        normalized = normalize_artifact_path(value)
        if not normalized:
            raise ValueError("manifest artifact path must be a non-empty absolute posix path")
        return normalized


class ProducerManifest(BaseModel):
    """Producer/capture manifest for source `entorhinal.dev-task.01`.

    Names the exact resolved inbox file, the activation boundary, the
    permitted envelope fields, the exact artifact allow-list, the grant
    revision and the retention class. Source identity and grants come from
    this runtime configuration, never from caller-supplied labels.
    """

    model_config = ConfigDict(extra="forbid")

    manifest_version: str = Field(..., min_length=1, max_length=128)
    source_id: str = Field(..., min_length=1, max_length=256)
    inbox_path: str = Field(..., min_length=1, max_length=1024)
    activation_boundary_offset: int = Field(..., ge=0)
    permitted_fields: List[str] = Field(..., min_length=1)
    artifact_allow_list: List[ManifestArtifact] = Field(default_factory=list)
    grant_revision: str = Field(..., min_length=1, max_length=128)
    retention_class: str = Field(..., min_length=1, max_length=128)
    notes: Optional[str] = Field(default=None, max_length=4096)

    def allow_listed_paths(self) -> set[str]:
        """Exact normalized allow-listed artifact paths."""
        return {entry.path for entry in self.artifact_allow_list}


class TaskEventAdmissionError(ValueError):
    """Raised when a candidate task event fails default-deny admission."""


def admit_task_event(
    data: Dict[str, Any],
    *,
    source_id: str,
    manifest: ProducerManifest,
) -> Tuple[TaskEvent, List[str]]:
    """Validate and admit one candidate task event (default-deny).

    Checks, in order: envelope structure (undeclared fields rejected),
    configured source ID match, grant revision match, artifact allow-list
    membership. Returns the admitted event plus a list of admission notes
    (currently the artifact resolution record). Raises
    TaskEventAdmissionError on any denial.
    """
    try:
        event = TaskEvent.model_validate(data)
    except Exception as exc:
        raise TaskEventAdmissionError(f"envelope rejected: {exc}") from exc

    if event.source_id != source_id:
        raise TaskEventAdmissionError(
            f"source_id {event.source_id!r} does not match configured {source_id!r}"
        )
    if manifest.source_id != source_id:
        raise TaskEventAdmissionError("manifest source_id does not match configured source")
    if event.admission.grant_revision != manifest.grant_revision:
        raise TaskEventAdmissionError(
            f"grant_revision {event.admission.grant_revision!r} does not match "
            f"manifest {manifest.grant_revision!r}"
        )

    allowed = manifest.allow_listed_paths()
    notes: List[str] = []
    for ref in event.payload.artifact_refs:
        if ref.path not in allowed:
            raise TaskEventAdmissionError(
                f"artifact path {ref.path!r} is not on the manifest allow-list"
            )
        notes.append(f"artifact resolved: {ref.path} rev={ref.revision}")
    return event, notes
