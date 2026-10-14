"""Thread-safe JSON persistence for UI tasks and the run index."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from sst.ui.models import RunRecord, TaskFile, TaskRecord

TASKS_FILENAME = "ui-tasks.json"


class TaskStore:
    """Loads/saves <project>/.sst/ui-tasks.json under a lock."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.file_path = project_root / ".sst" / TASKS_FILENAME
        self._lock = threading.Lock()
        self._data = TaskFile()
        self._load_locked()

    def _load_locked(self) -> None:
        if self.file_path.exists():
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = TaskFile.model_validate(raw)

    def _save_locked(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(self._data.model_dump_json(indent=2), encoding="utf-8")

    def list_tasks(self) -> list[TaskRecord]:
        with self._lock:
            return [self._data.tasks[k] for k in sorted(self._data.tasks)]

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._data.tasks.get(task_id)

    def put_task(self, task: TaskRecord) -> None:
        with self._lock:
            self._data.tasks[task.task_id] = task
            self._save_locked()

    def list_runs(self, task_id: str | None = None) -> list[RunRecord]:
        with self._lock:
            runs = list(self._data.runs.values())
        if task_id is not None:
            runs = [r for r in runs if r.task_id == task_id]
        return sorted(runs, key=lambda r: r.created_at)

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._data.runs.get(run_id)

    def put_run(self, run: RunRecord) -> None:
        with self._lock:
            self._data.runs[run.run_id] = run
            self._save_locked()
