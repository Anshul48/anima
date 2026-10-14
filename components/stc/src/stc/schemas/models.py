"""Strict Pydantic V2 schemas for the Biomimetic Spec-to-Code Engine."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Re-export hormone schemas for unified access
from stc.schemas.hormones import (
    HormoneEvent,
    HormoneScope,
    HormoneSignalType,
)

# Decoupled STL task worker models
from stc.schemas.stl import (
    HealthStatus,
    SystemMetrics,
    TaskPriority,
    TaskReceipt,
    TaskSpec,
    TaskStatus,
)

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
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    action: str = Field(default="modify", pattern=r"^(create|modify|delete)$")
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
    compiled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

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
    leased_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "ArchetypeDiff",
    "ArchetypeOption",
    "AuditFinding",
    "ConcernDimension",
    "ExecutionReceipt",
    "FileTarget",
    "GateReport",
    "GeneType",
    "GenomeAtom",
    "HealthStatus",
    "HormoneEvent",
    "HormoneScope",
    "HormoneSignalType",
    "JudiciaryVerdict",
    "SpecAtom",
    "SystemMetrics",
    "TaskBundle",
    "TaskPriority",
    "TaskReceipt",
    "TaskSpec",
    "TaskStatus",
    "TreeOfConcerns",
    "WorktreeLease",
]
