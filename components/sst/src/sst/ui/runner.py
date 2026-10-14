"""Run management: real SSTSearchController runs in worker threads.

Every run drives the production backend — SQLiteSSTStore, SSTSearchController.run_search,
get_search_result, and the same gateway/memory/custody wiring the CLI uses. No mocks.
"""

from __future__ import annotations

import asyncio
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from sst.cli import main as cli_main
from sst.cli.memory import build_memory_provider
from sst.context.capsule import ContextCapsuleCompiler
from sst.core.contracts import SearchResult, TaskPacket
from sst.core.errors import IncompleteSearchError
from sst.core.events import EventKind
from sst.gateway.contracts import (
    GatewayRequest,
    GatewayResponse,
    ModelCatalog,
    ModelCatalogEntry,
    ProviderKind,
    ProviderProfile,
)
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager, compute_workspace_digest
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.search.recovery import get_search_result
from sst.storage.store import SQLiteSSTStore
from sst.ui.models import PROVIDER_MODES, CreateRunRequest, RunRecord, TaskRecord, utc_now_iso
from sst.ui.tasks import TaskStore

RUNNING = "running"
FINISHED = "finished"
FAILED = "failed"
INCOMPLETE = "incomplete"


class FixtureGateway(ModelGateway):
    """Deterministic TEST-kind gateway for the UI's TEST-labeled fixture mode.

    Returns the task's ``fixture_code`` verbatim for every synthesis role and an
    APPROVE verdict for critique. Candidates still pass through the real
    custody verifier with the task's real acceptance commands, so a fixture run
    only succeeds when the fixture code genuinely satisfies acceptance.
    """

    def __init__(self, code: str) -> None:
        super().__init__()
        profile = ProviderProfile(
            name="fixture",
            kind=ProviderKind.TEST,
            api_base="test://fixture",
            selected_model="fixture-model",
            catalog=ModelCatalog(models=[ModelCatalogEntry(id="fixture-model", display_label="Fixture (TEST)")]),
        )
        self.register_profile(profile)
        for role in ("diverge", "refine", "synthesize", "critique"):
            self.set_route(role, "fixture", "fixture-model")
        self._code = code

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        if request.role == "critique":
            content = '{"value_score": 0.95, "verdict": "APPROVE", "rationale": "Fixture approval (TEST provider)."}'
        else:
            content = self._code
        return GatewayResponse(
            content=content,
            profile="fixture",
            model="fixture-model",
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
            cost_usd=0.0,
            cost_known=True,
        )


class LiveRun:
    """In-memory state for one worker-thread run."""

    def __init__(
        self,
        run_id: str,
        record: RunRecord,
        controller: SSTSearchController,
        policy: SearchPolicy,
        task_packet: TaskPacket,
    ) -> None:
        self.run_id = run_id
        self.record = record
        self.controller = controller
        self.policy = policy
        self.task_packet = task_packet
        self.thread: threading.Thread | None = None
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.failure: str | None = None
        self.cancel_requested = False


class RunManager:
    """Starts, tracks, and cancels real backend runs; reads status from the event log."""

    def __init__(self, tasks: TaskStore) -> None:
        self._tasks = tasks
        self._lock = threading.Lock()
        self._live: dict[str, LiveRun] = {}

    def _build_gateway(self, mode: str, task: TaskRecord) -> ModelGateway:
        if mode == "fixture":
            return FixtureGateway(task.fixture_code)
        return cli_main._get_default_gateway()

    def start_run(self, req: CreateRunRequest) -> RunRecord:
        task = self._tasks.get_task(req.task_id)
        if task is None:
            raise KeyError(f"Unknown task '{req.task_id}'.")
        mode = req.provider_mode or task.provider_mode
        if mode not in PROVIDER_MODES:
            raise ValueError(f"Unknown provider_mode '{mode}'. Expected one of {list(PROVIDER_MODES)}.")
        if mode == "fixture" and not task.fixture_code.strip():
            raise ValueError("Fixture mode requires the task to carry TEST-labeled fixture_code.")

        project = Path(task.project_path)
        if not project.exists():
            raise ValueError(f"Task project path does not exist: {task.project_path}")

        run_id = f"tree_{uuid.uuid4().hex[:12]}"
        db_path = cli_main._resolve_db_path(project, run_id)
        store = SQLiteSSTStore(db_path)
        custody_dir = (
            project / ".sst" / "worktrees" if (project / ".sst").exists() else project / ".auto" / "worktrees" / "sst"
        )
        custody = CandidateCustodyManager(base_worktree_dir=custody_dir)
        base_commit = cli_main._get_git_commit(project) or "non_git_workspace"
        snapshot_hash = compute_workspace_digest(project)

        packet = TaskPacket(
            task_id=task.task_id,
            goal=task.goal,
            source_repo_root=str(project),
            base_commit=base_commit,
            snapshot_hash=snapshot_hash,
            allowed_paths=list(task.allowed_paths),
            forbidden_paths=list(task.forbidden_paths),
            acceptance_commands=list(task.acceptance_commands),
            token_budget=req.token_budget if req.token_budget is not None else task.token_budget,
            cost_budget_usd=req.cost_budget_usd if req.cost_budget_usd is not None else task.cost_budget_usd,
            time_budget_seconds=(
                req.time_budget_seconds if req.time_budget_seconds is not None else task.time_budget_seconds
            ),
        )
        max_iterations = req.max_iterations if req.max_iterations is not None else task.max_iterations
        policy = SearchPolicy(max_iterations=max_iterations)

        if mode == "static":
            memory_provider = build_memory_provider("static", insights=list(task.memory_insights))
        else:
            memory_provider = None
        capsule_compiler = ContextCapsuleCompiler(workspace_root=project, memory_provider=memory_provider)
        gateway = self._build_gateway(mode, task)
        controller = SSTSearchController(
            task=packet,
            gateway=gateway,
            store=store,
            custody_manager=custody,
            policy=policy,
            capsule_compiler=capsule_compiler,
        )

        record = RunRecord(
            run_id=run_id,
            task_id=task.task_id,
            provider_mode=mode,
            db_path=str(db_path),
            project_path=str(project),
            created_at=utc_now_iso(),
        )
        live = LiveRun(run_id=run_id, record=record, controller=controller, policy=policy, task_packet=packet)

        def _target() -> None:
            try:
                asyncio.run(controller.run_search(run_id))
            except Exception:
                live.failure = traceback.format_exc(limit=5)
            finally:
                live.finished_at = time.time()

        thread = threading.Thread(target=_target, name=f"sst-run-{run_id}", daemon=True)
        live.thread = thread
        with self._lock:
            self._live[run_id] = live
        self._tasks.put_run(record)
        thread.start()
        return record

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            live = self._live.get(run_id)
        if live is None:
            return {"run_id": run_id, "status": "not_running", "detail": "No live worker for this run."}
        live.cancel_requested = True
        live.controller.cancel()
        if live.thread is not None:
            live.thread.join(timeout=5.0)
        if live.thread is not None and live.thread.is_alive():
            return {"run_id": run_id, "status": "cancelling", "detail": "Cancel requested; worker still finishing."}
        return {"run_id": run_id, "status": "cancelled", "detail": "Worker stopped."}

    def _live_snapshot(self, live: LiveRun) -> dict[str, Any]:
        tracker = live.controller.budget_tracker
        return {
            "iterations_completed": tracker.iterations_completed,
            "tokens_consumed": tracker.tokens_consumed,
            "estimated_cost_usd": tracker.estimated_cost_usd,
            "elapsed_seconds": round(time.time() - live.started_at, 2),
            "cancel_requested": live.cancel_requested,
        }

    def run_status(self, run_id: str) -> dict[str, Any] | None:
        """Builds the status/progress payload for a run from the live worker and event log."""
        record = self._tasks.get_run(run_id)
        if record is None:
            return None
        with self._lock:
            live = self._live.get(run_id)
        worker_alive = live is not None and live.thread is not None and live.thread.is_alive()

        events_summary: dict[str, Any] = {
            "event_count": 0,
            "proposed": 0,
            "verified": 0,
            "verify_failed": 0,
            "scored": 0,
            "provider_errors": 0,
            "escalations": 0,
            "decisions": 0,
            "promotions": 0,
            "has_finished_marker": False,
            "last_kind": None,
            "last_at": None,
        }
        db_path = Path(record.db_path)
        if db_path.exists():
            store = SQLiteSSTStore(db_path)
            events = store.get_events(run_id)
            events_summary["event_count"] = len(events)
            for event in events:
                if event.kind in {EventKind.NODE_PROPOSED, EventKind.SYNTHESIS_PROPOSED}:
                    events_summary["proposed"] += 1
                elif event.kind is EventKind.VERIFIER_FINISHED:
                    if event.payload.get("passed") is True:
                        events_summary["verified"] += 1
                    else:
                        events_summary["verify_failed"] += 1
                elif event.kind is EventKind.SCORE_RECORDED:
                    events_summary["scored"] += 1
                elif event.kind is EventKind.PROVIDER_ERROR:
                    events_summary["provider_errors"] += 1
                elif event.kind is EventKind.HUMAN_DECISION_REQUESTED:
                    events_summary["escalations"] += 1
                elif event.kind is EventKind.HUMAN_DECISION_RECORDED:
                    events_summary["decisions"] += 1
                elif event.kind is EventKind.PROMOTION_RECORDED:
                    events_summary["promotions"] += 1
                elif event.kind is EventKind.SEARCH_COMPLETED:
                    events_summary["has_finished_marker"] = True
            if events:
                events_summary["last_kind"] = events[-1].kind.value
                events_summary["last_at"] = events[-1].created_at.isoformat()

        if worker_alive:
            status = RUNNING
        elif events_summary["has_finished_marker"]:
            status = FINISHED
        elif live is not None and live.failure:
            status = FAILED
        else:
            status = INCOMPLETE

        payload: dict[str, Any] = {
            "run_id": run_id,
            "task_id": record.task_id,
            "provider_mode": record.provider_mode,
            "db_path": record.db_path,
            "project_path": record.project_path,
            "created_at": record.created_at,
            "status": status,
            "events": events_summary,
        }
        if live is not None:
            payload["live"] = self._live_snapshot(live)
            payload["budgets"] = {
                "max_iterations": live.policy.max_iterations,
                "max_token_budget": live.policy.max_token_budget,
                "max_cost_usd": live.policy.max_cost_usd,
                "max_time_seconds": live.policy.max_time_seconds,
                "task_token_budget": live.task_packet.token_budget,
                "task_cost_budget_usd": live.task_packet.cost_budget_usd,
                "task_time_budget_seconds": live.task_packet.time_budget_seconds,
            }
            if live.failure and status == FAILED:
                payload["error"] = live.failure
        if status == FINISHED:
            summary = self.result_summary(run_id)
            if summary is not None:
                payload["result_summary"] = summary
        if status == INCOMPLETE and live is not None and live.failure:
            payload["error"] = live.failure
        return payload

    def result_summary(self, run_id: str) -> dict[str, Any] | None:
        try:
            result = self.load_result(run_id)
        except (KeyError, IncompleteSearchError, ValueError):
            return None
        champion = result.champion
        return {
            "termination_reason": result.termination_reason.value,
            "champion_id": champion.candidate_id if champion else None,
            "champion_title": champion.title if champion else None,
            "alternatives": len(result.alternatives),
            "provider_errors": len(result.provider_errors),
            "budget_consumed": result.budget_consumed.model_dump(mode="json"),
            "gateway_bindings": [b.model_dump(mode="json") for b in result.gateway_bindings],
        }

    def open_store(self, run_id: str) -> SQLiteSSTStore:
        record = self._tasks.get_run(run_id)
        if record is None:
            raise KeyError(f"Unknown run '{run_id}'.")
        db_path = Path(record.db_path)
        if not db_path.exists():
            raise ValueError(f"No event log found for run '{run_id}' at {record.db_path}.")
        return SQLiteSSTStore(db_path)

    def load_result(self, run_id: str) -> SearchResult:
        """Rebuilds the SearchResult envelope from the event log (reopen path)."""
        store = self.open_store(run_id)
        return get_search_result(store, run_id)
