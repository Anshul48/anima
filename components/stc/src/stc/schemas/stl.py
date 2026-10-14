"""Tier 7: Task Orchestration & Engine Schemas (STL Worker Models).

Decoupled from Biomimetic STC schemas to preserve clean architectural boundaries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskPriority(StrEnum):
    """Execution priority for a scheduled task."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(StrEnum):
    """Current lifecycle state of a task."""

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
