"""Pydantic records for the SST task-to-result browser UI."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ProviderMode = Literal["fixture", "static", "operator"]

PROVIDER_MODES: tuple[str, ...] = ("fixture", "static", "operator")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class TaskRecord(BaseModel):
    """One UI-managed task definition persisted in <project>/.sst/ui-tasks.json."""

    task_id: str
    goal: str
    project_path: str
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)
    provider_mode: str = "fixture"
    token_budget: int | None = None
    cost_budget_usd: float | None = None
    time_budget_seconds: int = 300
    max_iterations: int = 5
    memory_insights: list[str] = Field(default_factory=list)
    fixture_code: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class RunRecord(BaseModel):
    """Index entry linking a run (tree_id) to its task. The event log is the source of truth."""

    run_id: str
    task_id: str
    provider_mode: str
    db_path: str
    project_path: str
    created_at: str = Field(default_factory=utc_now_iso)


class TaskFile(BaseModel):
    """On-disk shape of <project>/.sst/ui-tasks.json."""

    tasks: dict[str, TaskRecord] = Field(default_factory=dict)
    runs: dict[str, RunRecord] = Field(default_factory=dict)


class CreateTaskRequest(BaseModel):
    goal: str = Field(min_length=1)
    project_path: str = ""
    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)
    acceptance_commands: list[str] = Field(default_factory=list)
    provider_mode: str = "fixture"
    token_budget: int | None = None
    cost_budget_usd: float | None = None
    time_budget_seconds: int = 300
    max_iterations: int = 5
    memory_insights: list[str] = Field(default_factory=list)
    fixture_code: str = ""


class CreateRunRequest(BaseModel):
    task_id: str = Field(min_length=1)
    provider_mode: str | None = None
    token_budget: int | None = None
    cost_budget_usd: float | None = None
    time_budget_seconds: int | None = None
    max_iterations: int | None = None


class DecideRequest(BaseModel):
    run_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    verdict: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    approver: str = "operator"


class PromoteRequest(BaseModel):
    run_id: str = Field(min_length=1)
    candidate_id: str | None = None


class OutcomeRequest(BaseModel):
    run_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    verdict: str = Field(min_length=1)
    note: str | None = None
    actor: str = "operator"


def error_body(message: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": message}
    if extra:
        body.update(extra)
    return body
