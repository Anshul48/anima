"""Unit tests for the STCEngine service implementation."""

import asyncio
from typing import Any

import pytest

from stc.schemas.models import TaskSpec, TaskStatus
from stc.services.engine import STCEngine


@pytest.mark.asyncio
async def test_run_ping_task(engine: STCEngine) -> None:
    """Verify executing a ping task."""
    spec = TaskSpec(name="ping-check", action="ping")
    receipt = await engine.run_task(spec)

    assert receipt.status == TaskStatus.COMPLETED
    assert receipt.task_id == spec.task_id
    assert receipt.result.get("pong") is True
    assert len(receipt.checksum_sha256) == 64
    assert receipt.duration_ms >= 0.0

    # Verify persistence
    stored = engine.get_receipt(receipt.receipt_id)
    assert stored is not None
    assert stored.receipt_id == receipt.receipt_id


@pytest.mark.asyncio
async def test_run_compute_task(engine: STCEngine) -> None:
    """Verify executing an algebraic compute task."""
    spec = TaskSpec(
        name="sum-values",
        action="compute",
        payload={"op": "sum", "values": [10, 20, 30]},
    )
    receipt = await engine.run_task(spec)

    assert receipt.status == TaskStatus.COMPLETED
    assert receipt.result["result"] == 60
    assert receipt.result["count"] == 3


@pytest.mark.asyncio
async def test_run_echo_task(engine: STCEngine) -> None:
    """Verify echo action execution."""
    spec = TaskSpec(
        name="echo-check",
        action="echo",
        payload={"message": "stc running"},
    )
    receipt = await engine.run_task(spec)

    assert receipt.status == TaskStatus.COMPLETED
    assert receipt.result["echo"]["message"] == "stc running"


@pytest.mark.asyncio
async def test_task_timeout(engine: STCEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify task timeout handling and failure receipt generation."""

    async def slow_action(_action: str, _payload: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.5)
        return {"done": True}

    monkeypatch.setattr(engine, "_dispatch_action", slow_action)
    spec = TaskSpec(name="slow-task", action="slow", timeout_seconds=0.05)
    receipt = await engine.run_task(spec)

    assert receipt.status == TaskStatus.FAILED
    assert "timeout" in (receipt.error or "").lower()


@pytest.mark.asyncio
async def test_metrics_and_health(engine: STCEngine) -> None:
    """Verify health reporting and system metrics counters."""
    await engine.run_task(TaskSpec(name="t1", action="ping"))
    health = await engine.check_health()

    assert health.status == "ok"
    assert health.service == "stc"
    assert health.metrics.tasks_processed == 1
    assert health.metrics.tasks_succeeded == 1
    assert health.metrics.tasks_failed == 0
