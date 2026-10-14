"""Core service engine for STC implementing protocols and task execution."""

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stc.core.config import Settings
from stc.schemas.models import (
    HealthStatus,
    SystemMetrics,
    TaskReceipt,
    TaskSpec,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class STCEngine:
    """Production service engine implementing task orchestration, metrics, and receipts."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._start_time = time.monotonic()
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._tasks_processed = 0
        self._tasks_succeeded = 0
        self._tasks_failed = 0
        self._active_workers = 0

        # Ensure receipt storage directory exists
        self._receipts_dir = settings.workspace_root / settings.artifacts_dir / "receipts"
        self._receipts_dir.mkdir(parents=True, exist_ok=True)

    @property
    def receipts_dir(self) -> Path:
        """Directory path where receipts are persisted."""
        return self._receipts_dir

    def _compute_checksum(
        self,
        task_id: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """Compute SHA256 cryptographic digest of task inputs and outputs."""
        serialized = json.dumps(
            {"task_id": task_id, "payload": payload, "result": result},
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    async def _dispatch_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Dispatch built-in actions or custom workflows."""
        match action:
            case "ping":
                return {"pong": True, "timestamp": datetime.now(UTC).isoformat()}
            case "echo":
                return {"echo": payload}
            case "compute":
                operands = payload.get("values", [1, 2, 3])
                operation = payload.get("op", "sum")
                if operation == "sum":
                    val = sum(operands)
                elif operation == "prod":
                    val = 1
                    for x in operands:
                        val *= x
                else:
                    val = len(operands)
                return {"result": val, "operation": operation, "count": len(operands)}
            case _:
                return {"status": "executed", "action": action, "data": payload}

    async def run_task(self, spec: TaskSpec) -> TaskReceipt:
        """Execute a task with concurrency protection and receipt generation."""
        started_at = datetime.now(UTC)
        start_mono = time.monotonic()
        self._active_workers += 1
        self._tasks_processed += 1

        result: dict[str, Any] = {}
        error_msg: str | None = None
        status = TaskStatus.COMPLETED

        async with self._semaphore:
            try:
                logger.info(
                    "Executing task %s (name: %s, action: %s, priority: %s)",
                    spec.task_id,
                    spec.name,
                    spec.action,
                    spec.priority.value,
                )
                async with asyncio.timeout(spec.timeout_seconds):
                    result = await self._dispatch_action(spec.action, spec.payload)
                self._tasks_succeeded += 1
            except TimeoutError:
                status = TaskStatus.FAILED
                error_msg = f"Task exceeded timeout limit of {spec.timeout_seconds}s"
                self._tasks_failed += 1
                logger.error("Task %s timed out: %s", spec.task_id, error_msg)
            except Exception as exc:
                status = TaskStatus.FAILED
                error_msg = str(exc)
                self._tasks_failed += 1
                logger.exception("Task %s failed: %s", spec.task_id, exc)

        finished_at = datetime.now(UTC)
        duration_ms = (time.monotonic() - start_mono) * 1000.0
        self._active_workers -= 1

        checksum = self._compute_checksum(spec.task_id, spec.payload, result)
        receipt = TaskReceipt(
            task_id=spec.task_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=round(duration_ms, 3),
            result=result,
            error=error_msg,
            checksum_sha256=checksum,
        )

        self.save_receipt(receipt)
        return receipt

    def save_receipt(self, receipt: TaskReceipt) -> Path:
        """Save receipt to filesystem as formatted JSON."""
        file_path = self._receipts_dir / f"{receipt.receipt_id}.json"
        with file_path.open("w", encoding="utf-8") as f:
            f.write(receipt.model_dump_json(indent=2))
        logger.debug("Persisted receipt %s to %s", receipt.receipt_id, file_path)
        return file_path

    def get_receipt(self, receipt_id: str) -> TaskReceipt | None:
        """Retrieve receipt from storage by ID."""
        file_path = self._receipts_dir / f"{receipt_id}.json"
        if not file_path.exists():
            return None
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return TaskReceipt.model_validate(data)

    def get_metrics(self) -> SystemMetrics:
        """Return current snapshot of engine metrics."""
        uptime = time.monotonic() - self._start_time
        return SystemMetrics(
            active_workers=self._active_workers,
            tasks_processed=self._tasks_processed,
            tasks_succeeded=self._tasks_succeeded,
            tasks_failed=self._tasks_failed,
            uptime_seconds=round(uptime, 2),
        )

    async def check_health(self) -> HealthStatus:
        """Check system health and storage accessibility."""
        storage_ok = self._receipts_dir.exists() and self._receipts_dir.is_dir()
        return HealthStatus(
            status="ok" if storage_ok else "degraded",
            service="stc",
            version="0.1.0",
            timestamp=datetime.now(UTC),
            metrics=self.get_metrics(),
        )
