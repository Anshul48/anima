# STC: Biomimetic Spec-to-Code Autonomous Engineering Engine
## Volume 04: Data Contracts & Typing Protocols (Lossless Pydantic V2 & PEP 544)

> **System:** STC (Spec-To-Code)  
> **Project Directory:** `code/utilities/stc`  
> **Standard:** Pydantic V2 (`pydantic.BaseModel`), PEP 544 (`typing.Protocol`), Strict Immutability (`frozen=True`)  
> **Status:** `[DECIDED]`  

---

## 1. Abstract System Protocols (PEP 544 Membranes)

The interfaces below establish the rigid membrane between STC subsystems. No subsystem may import concrete implementations from another subsystem; all communication occurs across these abstract protocols.

```python
"""Module: stc.protocols.interfaces
Abstract PEP 544 interfaces for the Biomimetic Spec-to-Code Engine.
"""

from __future__ import annotations
from pathlib import Path
from typing import Protocol, runtime_checkable

from stc.schemas.models import (
    ArchetypeDiff,
    ExecutionReceipt,
    GenomeAtom,
    JudiciaryVerdict,
    SpecAtom,
    TaskBundle,
    TreeOfConcerns,
    WorktreeLease,
)


@runtime_checkable
class SpecIngestorProtocol(Protocol):
    """Protocol for reading and sanitizing raw specifications."""

    def ingest_path(self, path: Path) -> SpecAtom: ...
    def ingest_string(self, content: str, source_name: str) -> SpecAtom: ...


@runtime_checkable
class SocraticDecomposerProtocol(Protocol):
    """Protocol for decomposing specifications into a Tree of Concerns (TOC)."""

    def decompose(self, spec: SpecAtom) -> TreeOfConcerns: ...
    def detect_ambiguity(self, toc: TreeOfConcerns) -> list[ArchetypeDiff]: ...
    def lock_invariants(self, toc: TreeOfConcerns, selected_archetypes: list[int]) -> Path: ...


@runtime_checkable
class TraceMemoryProtocol(Protocol):
    """Protocol for querying the Project Trace cognitive memory store."""

    def query_semantic_context(self, keywords: list[str], max_results: int = 3) -> list[str]: ...
    def query_negative_inhibitors(self, component: str) -> list[str]: ...


@runtime_checkable
class ContextCompilerProtocol(Protocol):
    """Protocol for assembling sub-25KB task bundles."""

    def compile_task(
        self,
        task_id: str,
        spec: SpecAtom,
        toc: TreeOfConcerns,
        inhibitors: list[str],
    ) -> TaskBundle: ...


@runtime_checkable
class WorktreeManagerProtocol(Protocol):
    """Protocol for isolated Git worktree management."""

    def allocate_lease(self, task_id: str, base_branch: str = "main") -> WorktreeLease: ...
    def release_lease(self, lease: WorktreeLease, purge: bool = True) -> None: ...
    def get_diff(self, lease: WorktreeLease) -> str: ...


@runtime_checkable
class WorkerProtocol(Protocol):
    """Protocol for executive workers (`agy` / `aider` / `dsh`) confined to a leased worktree."""

    def dispatch(self, bundle: TaskBundle, lease: WorktreeLease) -> str: ...
    def confinement_root(self, lease: WorktreeLease) -> Path: ...


@runtime_checkable
class SubstrateRunnerProtocol(Protocol):
    """Protocol for running deterministic quality gates and generating receipts.

    OS/mutmut execution policy (`run_mutmut`, Windows defer-to-WSL) is runner
    configuration owned by `stc.substrate` + `stc.core.config` — never membrane
    surface. The membrane carries only identity, targeting, and correlation.
    """

    def execute_gates(
        self,
        worktree_path: Path,
        task_id: str,
        epoch_index: int = 1,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        pytest_target: str | None = None,
    ) -> ExecutionReceipt: ...

    def verify_receipt(self, receipt: ExecutionReceipt) -> bool: ...


@runtime_checkable
class JudiciaryAuditorProtocol(Protocol):
    """Protocol for blind adversarial inspection of diffs."""

    def audit_diff(
        self,
        diff_text: str,
        bundle: TaskBundle,
        receipt: ExecutionReceipt,
    ) -> JudiciaryVerdict: ...


@runtime_checkable
class GenomeStoreProtocol(Protocol):
    """Protocol for saving verified implementations and negative knowledge."""

    def save_gene(self, gene: GenomeAtom) -> str: ...
    def find_genes(self, tags: list[str]) -> list[GenomeAtom]: ...


@runtime_checkable
class HormoneBusProtocol(Protocol):
    """Protocol for scoped pub/sub cellular hormone message bus."""

    def publish(self, event: HormoneEvent) -> str: ...
    def subscribe(self, subsystem_id: str, topics: list[str] | None = None) -> None: ...
    def poll_events(self, subsystem_id: str, max_events: int = 10) -> list[HormoneEvent]: ...
```

---

## 2. Immutable Data Contracts (Pydantic V2 Schemas)

All data moving through the STC pipeline is serialized and validated via these frozen Pydantic models.

```python
"""Module: stc.schemas.models
Strict Pydantic V2 schemas for the Biomimetic Spec-to-Code Engine.
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, field_validator


# =====================================================================
# Tier 0: Spec Ingestion Schemas
# =====================================================================


class SpecAtom(BaseModel):
    """Validated raw specification atom."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_id: str = Field(..., description="Unique slug for the specification")
    source_path: str = Field(..., description="Path or origin of the specification")
    raw_content: str = Field(..., min_length=10, description="Raw specification text")
    content_sha256: str = Field(..., min_length=64, max_length=64)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =====================================================================
# Tier 1: Socratic Elicitation Schemas
# =====================================================================


class ConcernDimension(BaseModel):
    """A single concern dimension in the Tree of Concerns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension_name: str
    invariants: list[str] = Field(default_factory=list)
    contracts: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    acceptance_tests: list[str] = Field(default_factory=list)


class TreeOfConcerns(BaseModel):
    """Hierarchical 5-dimensional decomposition of an architectural spec."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_id: str
    domain_invariants: ConcernDimension
    persistence_storage: ConcernDimension
    communication_protocols: ConcernDimension
    boundary_security: ConcernDimension
    failure_resilience: ConcernDimension
    ambiguity_score: float = Field(ge=0.0, le=1.0)


class ArchetypeOption(BaseModel):
    """A concrete, pre-baked architectural opinion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    option_id: str = Field(..., pattern=r"^option_[a-z]$")
    title: str = Field(..., min_length=5)
    tradeoff_pro: str
    tradeoff_con: str
    invariants_to_lock: list[str]


class ArchetypeDiff(BaseModel):
    """Contrasting architectural choice presented to the Human Sovereign."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    diff_id: str
    concern_dimension: str
    core_dilemma: str
    option_a: ArchetypeOption
    option_b: ArchetypeOption
    selected_option: str | None = None


# =====================================================================
# Tier 2: Task Bundle & Context Compilation Schemas
# =====================================================================


class FileTarget(BaseModel):
    """Target file for worker modification with restored line and byte offsets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    action: str = Field("modify", pattern=r"^(create|modify|delete)$")
    expected_symbols: list[str] = Field(default_factory=list)
    start_line: int | None = Field(default=None, ge=1, description="1-indexed starting line offset")
    end_line: int | None = Field(
        default=None, ge=1, description="1-indexed ending line offset (inclusive)"
    )
    start_byte: int | None = Field(default=None, ge=0, description="0-indexed start byte offset")
    end_byte: int | None = Field(
        default=None, ge=0, description="0-indexed end byte offset (exclusive)"
    )

    @model_validator(mode="after")
    def validate_offsets(self) -> FileTarget:
        """Enforce monotonic line and byte offset invariants."""
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError(
                f"end_line ({self.end_line}) cannot be less than start_line ({self.start_line})"
            )
        if (
            self.start_byte is not None
            and self.end_byte is not None
            and self.end_byte < self.start_byte
        ):
            raise ValueError(
                f"end_byte ({self.end_byte}) cannot be less than start_byte ({self.start_byte})"
            )
        return self


class TaskBundle(BaseModel):
    """Compiled sub-25KB execution package for executive workers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    epoch_index: int = Field(ge=1, le=3)
    spec_id: str
    goal_statement: str
    invariants: list[str]
    target_files: list[FileTarget]
    membrane_protocols: list[str]
    negative_inhibitors: list[str]
    correlation_id: str = Field(
        default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}",
        description="Distributed trace correlation identifier",
    )
    causation_id: str | None = Field(
        default=None,
        description="Identifier of causal event or parent task",
    )
    compiled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("goal_statement")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Goal statement cannot be whitespace only")
        return v


# =====================================================================
# Tier 3: Worktree Lease Schemas
# =====================================================================


class WorktreeLease(BaseModel):
    """Active Git worktree lease descriptor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lease_id: str
    task_id: str
    branch_name: str
    worktree_path: str
    leased_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    is_active: bool = True


# =====================================================================
# Tier 4: Substrate Hard Gates & Receipts Schemas
# =====================================================================


class GateReport(BaseModel):
    """Report from a single mechanical quality gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_name: str
    exit_code: int
    duration_seconds: float
    violations_count: int
    raw_output_snippet: str


class ExecutionReceipt(BaseModel):
    """Tamper-evident machine receipt for zero-defect certification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: str
    task_id: str
    epoch_index: int
    commit_hash: str
    timestamp_utc: str
    python_version: str
    os_platform: str
    gate_ruff: GateReport
    gate_mypy: GateReport
    gate_pytest: GateReport
    gate_mutmut: GateReport
    sha256_signature: str
    correlation_id: str = Field(
        default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}",
        description="Distributed trace correlation identifier",
    )
    causation_id: str | None = Field(
        default=None,
        description="Identifier of causal event or parent task",
    )

    @property
    def is_passing(self) -> bool:
        """Returns True only if all deterministic gates exited with code 0."""
        return (
            self.gate_ruff.exit_code == 0
            and self.gate_mypy.exit_code == 0
            and self.gate_pytest.exit_code == 0
            and self.gate_mutmut.exit_code == 0
        )


# =====================================================================
# Tier 5 & 6: Judiciary & Genome Schemas
# =====================================================================


class AuditFinding(BaseModel):
    """Specific finding during blind judiciary review."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_name: str
    severity: str = Field(..., pattern=r"^(CRITICAL|HIGH|MEDIUM|LOW)$")
    filepath: str
    line_number: int | None = None
    snippet: str
    rationale: str


class JudiciaryVerdict(BaseModel):
    """Structured verdict from the blind judiciary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    status: str = Field(..., pattern=r"^(APPROVED|QUARANTINED|REJECTED)$")
    findings: list[AuditFinding] = Field(default_factory=list)
    summary_rationale: str


class GeneType(StrEnum):
    STRUCTURAL = "structural"
    BEHAVIORAL = "behavioral"
    INHIBITOR = "inhibitor"


class GenomeAtom(BaseModel):
    """Evolving software gene persisted in the Project Trace database."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gene_id: str
    gene_type: GeneType
    component_name: str
    pattern_signature: str
    raw_code_or_rule: str
    receipt_reference: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## 3. Scoped Hormone Pub/Sub Schemas (`stc.schemas.hormones`)

Biomimetic intercellular endocrine signaling protocol for distributed coordination and alarm broadcasting.

```python
"""Module: stc.schemas.hormones
Scoped Pub/Sub Hormone Protocol models.
"""

from __future__ import annotations
import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class HormoneSignalType(StrEnum):
    """Permitted biomimetic hormone signal categories per 01_INVARIANTS.md."""

    CONTRACT_DRIFT = "contract_drift"
    TEST_FAILURE = "test_failure"
    CONCURRENCY_PRESSURE = "concurrency_pressure"
    SCHEMA_MUTATION = "schema_mutation"
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    DIRECTIVE_AMENDMENT = "directive_amendment"
    INVARIANT_VIOLATION = "invariant_violation"


class HormoneScope(BaseModel):
    """Receptor boundary scope restricting event delivery to matched cellular pairs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    producer_subsystem: str = Field(..., min_length=1, description="Originating subsystem cell")
    target_subsystems: list[str] = Field(
        ..., min_length=1, description="Authorized target consumer subsystem IDs"
    )
    topic: str = Field(..., min_length=1, description="Functional topic e.g. 'membrane.contracts'")
    channel: str = Field(
        ...,
        min_length=1,
        description="Scoped channel identifier (e.g. 'provider:consumer' or 'cell.isolated')",
    )


class HormoneEvent(BaseModel):
    """Cryptographically hashed, scoped cellular hormone signal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(
        default_factory=lambda: f"hormone_{uuid.uuid4().hex[:12]}",
        description="Unique event identifier",
    )
    signal_type: HormoneSignalType = Field(..., description="Categorical hormone type")
    scope: HormoneScope = Field(..., description="Receptor routing scope")
    payload: dict[str, Any] = Field(default_factory=dict, description="Structured event payload")
    payload_sha256: str = Field(
        default="",
        description="Bit-exact SHA-256 digest of canonical JSON payload",
    )
    correlation_id: str = Field(
        default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}",
        description="Distributed trace correlation identifier",
    )
    causation_id: str | None = Field(
        default=None,
        description="Identifier of causal event or trigger",
    )
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Event emission timestamp in UTC",
    )
    ttl_seconds: float = Field(
        default=300.0,
        gt=0.0,
        le=86400.0,
        description="Time-to-live before signal decays",
    )

    @model_validator(mode="before")
    @classmethod
    def compute_payload_hash(cls, data: Any) -> Any:
        """Automatically compute payload_sha256 if omitted or empty."""
        if isinstance(data, dict):
            payload = data.get("payload", {})
            sha = data.get("payload_sha256")
            if not sha:
                serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                data["payload_sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return data
```

---

## 4. Decoupled Standard Task Library (STL) Schemas (`stc.schemas.stl`)

To decouple the execution engine and external task runners from Biomimetic STC internal schemas, the STL schemas provide an agnostic interface for ad-hoc background tasks.

```python
"""Module: stc.schemas.stl
Decoupled task execution schemas for STL workers.
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskSpec(BaseModel):
    """Specification model describing an atomic unit of work to execute."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(
        default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}",
        description="Unique identifier for the task",
    )
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable task name")
    action: str = Field(..., min_length=1, max_length=64, description="Action or verb to execute")
    priority: TaskPriority = Field(
        default=TaskPriority.NORMAL,
        description="Task execution priority",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary task payload parameters"
    )
    timeout_seconds: float = Field(
        default=30.0, gt=0.0, le=3600.0, description="Maximum execution duration in seconds"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Creation timestamp in UTC",
    )


class TaskReceipt(BaseModel):
    """Tamper-evident record of task execution results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(
        default_factory=lambda: f"rcpt_{uuid.uuid4().hex[:12]}",
        description="Unique receipt identifier",
    )
    task_id: str = Field(..., description="Referenced task identifier")
    status: TaskStatus = Field(..., description="Final task completion status")
    started_at: datetime = Field(..., description="Execution start timestamp in UTC")
    finished_at: datetime = Field(..., description="Execution finish timestamp in UTC")
    duration_ms: float = Field(..., ge=0.0, description="Elapsed execution time in milliseconds")
    result: dict[str, Any] = Field(
        default_factory=dict, description="Execution outputs and computed values"
    )
    error: str | None = Field(default=None, description="Error message if task failed")
    checksum_sha256: str = Field(..., description="Content hash of execution payload and result")


class SystemMetrics(BaseModel):
    """Snapshot of current system execution metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    active_workers: int = Field(default=0, ge=0, description="Number of currently active workers")
    tasks_processed: int = Field(default=0, ge=0, description="Total tasks processed")
    tasks_succeeded: int = Field(default=0, ge=0, description="Total successful tasks")
    tasks_failed: int = Field(default=0, ge=0, description="Total failed tasks")
    uptime_seconds: float = Field(default=0.0, ge=0.0, description="Engine uptime in seconds")


class HealthStatus(BaseModel):
    """Service health and diagnostics report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = Field(default="ok", description="Overall health state ('ok' or 'degraded')")
    service: str = Field(default="stc", description="Service name")
    version: str = Field(default="0.1.0", description="Service semver version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Current server timestamp in UTC",
    )
    metrics: SystemMetrics = Field(
        default_factory=SystemMetrics,
        description="Current system metrics",
    )
```
