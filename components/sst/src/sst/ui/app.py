"""SST task-to-result browser UI: stdlib threaded HTTP server over the real backend.

Run with ``python -m sst.ui.app --project PATH --port 8501``.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sst.core.contracts import AlternativeCandidate
from sst.core.errors import IncompleteSearchError
from sst.core.events import EventKind
from sst.sandbox.outcomes import report_outcome as sandbox_report_outcome
from sst.storage.serializer import serialize_sst_tree
from sst.ui import pages
from sst.ui.decisions import run_decide_command, run_promote_command
from sst.ui.models import (
    PROVIDER_MODES,
    CreateRunRequest,
    CreateTaskRequest,
    DecideRequest,
    OutcomeRequest,
    PromoteRequest,
    TaskRecord,
    error_body,
    utc_now_iso,
)
from sst.ui.runner import RunManager
from sst.ui.tasks import TaskStore


class UIRequestHandler(http.server.BaseHTTPRequestHandler):
    """Routes pages and the JSON API. The server object carries shared state."""

    server_version = "SSTBrowserUI/0.1"

    # --- helpers ---

    @property
    def _ui_server(self) -> SSTUIServer:
        server = self.server
        assert isinstance(server, SSTUIServer)
        return server

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003 - stdlib signature
        pass

    def _send_json(self, payload: dict[str, Any] | list[Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _path_parts(self) -> tuple[list[str], dict[str, str]]:
        parsed = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in parsed.path.split("/") if p]
        query = dict(urllib.parse.parse_qsl(parsed.query))
        return parts, query

    # --- dispatch ---

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        parts, query = self._path_parts()
        try:
            if not parts:
                self._handle_index()
            elif parts == ["healthz"]:
                self._send_json({"ok": True})
            elif parts == ["api", "tasks"]:
                self._handle_list_tasks()
            elif len(parts) == 3 and parts[:2] == ["api", "tasks"]:
                self._handle_get_task(parts[2])
            elif len(parts) == 3 and parts[:2] == ["api", "runs"]:
                self._handle_get_run(parts[2])
            elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "result":
                self._handle_get_result(parts[2])
            elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "alternatives":
                self._handle_get_alternatives(parts[2])
            elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "events":
                self._handle_get_events(parts[2], query)
            elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "tree":
                self._handle_get_tree(parts[2])
            elif parts == ["api", "providers"]:
                self._handle_get_providers()
            elif len(parts) == 2 and parts[0] == "tasks":
                self._handle_task_page(parts[1])
            elif len(parts) == 2 and parts[0] == "runs":
                self._handle_run_page(parts[1])
            else:
                self._send_json(error_body(f"Not found: {self.path}"), 404)
        except Exception as exc:  # never leak a stack trace as HTML; JSON error instead
            self._send_json(error_body(f"{type(exc).__name__}: {exc}"), 500)

    def do_POST(self) -> None:  # noqa: N802 - stdlib signature
        parts, _query = self._path_parts()
        try:
            if parts == ["api", "tasks"]:
                self._handle_create_task()
            elif parts == ["api", "runs"]:
                self._handle_create_run()
            elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "cancel":
                self._handle_cancel_run(parts[2])
            elif parts == ["api", "decide"]:
                self._handle_decide()
            elif parts == ["api", "promote"]:
                self._handle_promote()
            elif parts == ["api", "outcomes"]:
                self._handle_outcome()
            else:
                self._send_json(error_body(f"Not found: {self.path}"), 404)
        except Exception as exc:
            self._send_json(error_body(f"{type(exc).__name__}: {exc}"), 500)

    # --- pages ---

    def _handle_index(self) -> None:
        server = self._ui_server
        tasks = server.tasks.list_tasks()
        payload = [
            {
                "task_id": t.task_id,
                "goal": t.goal,
                "provider_mode": t.provider_mode,
                "created_at": t.created_at,
                "run_count": len(server.tasks.list_runs(t.task_id)),
            }
            for t in tasks
        ]
        self._send_html(pages.index_page(payload, str(server.project_root)))

    def _handle_task_page(self, task_id: str) -> None:
        server = self._ui_server
        task = server.tasks.get_task(task_id)
        if task is None:
            self._send_html(pages.shell("Not found", '<div class="notice bad">Unknown task.</div>'), 404)
            return
        runs: list[dict[str, Any]] = []
        for record in server.tasks.list_runs(task_id):
            status = server.runs.run_status(record.run_id)
            if status is not None:
                runs.append(status)
        self._send_html(pages.task_page(task.model_dump(mode="json"), runs))

    def _handle_run_page(self, run_id: str) -> None:
        server = self._ui_server
        record = server.tasks.get_run(run_id)
        if record is None:
            self._send_html(pages.shell("Not found", '<div class="notice bad">Unknown run.</div>'), 404)
            return
        self._send_html(pages.run_page(run_id, record.task_id))

    # --- tasks API ---

    def _handle_list_tasks(self) -> None:
        server = self._ui_server
        tasks = [t.model_dump(mode="json") for t in server.tasks.list_tasks()]
        self._send_json({"tasks": tasks})

    def _handle_get_task(self, task_id: str) -> None:
        server = self._ui_server
        task = server.tasks.get_task(task_id)
        if task is None:
            self._send_json(error_body(f"Unknown task '{task_id}'."), 404)
            return
        runs = [r.model_dump(mode="json") for r in server.tasks.list_runs(task_id)]
        self._send_json({"task": task.model_dump(mode="json"), "runs": runs})

    def _handle_create_task(self) -> None:
        server = self._ui_server
        try:
            req = CreateTaskRequest.model_validate(self._read_json_body())
        except ValidationError as exc:
            self._send_json(error_body(f"Invalid task: {exc.errors()[0]['msg'] if exc.errors() else exc}"), 400)
            return
        if req.provider_mode not in PROVIDER_MODES:
            self._send_json(error_body(f"Unknown provider_mode '{req.provider_mode}'."), 400)
            return
        project_path = req.project_path.strip() or str(server.project_root)
        if not Path(project_path).exists():
            self._send_json(error_body(f"Project path does not exist: {project_path}"), 400)
            return
        task = TaskRecord(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            goal=req.goal.strip(),
            project_path=str(Path(project_path).resolve()),
            allowed_paths=list(req.allowed_paths),
            forbidden_paths=list(req.forbidden_paths),
            acceptance_commands=list(req.acceptance_commands),
            provider_mode=req.provider_mode,
            token_budget=req.token_budget,
            cost_budget_usd=req.cost_budget_usd,
            time_budget_seconds=req.time_budget_seconds,
            max_iterations=req.max_iterations,
            memory_insights=list(req.memory_insights),
            fixture_code=req.fixture_code,
            created_at=utc_now_iso(),
        )
        server.tasks.put_task(task)
        self._send_json({"task_id": task.task_id, "task": task.model_dump(mode="json")}, 201)

    # --- runs API ---

    def _handle_create_run(self) -> None:
        server = self._ui_server
        try:
            req = CreateRunRequest.model_validate(self._read_json_body())
        except ValidationError as exc:
            self._send_json(error_body(f"Invalid run request: {exc.errors()[0]['msg'] if exc.errors() else exc}"), 400)
            return
        try:
            record = server.runs.start_run(req)
        except (KeyError, ValueError) as exc:
            self._send_json(error_body(str(exc)), 400)
            return
        self._send_json({"run_id": record.run_id, "run": record.model_dump(mode="json")}, 201)

    def _handle_get_run(self, run_id: str) -> None:
        status = self._ui_server.runs.run_status(run_id)
        if status is None:
            self._send_json(error_body(f"Unknown run '{run_id}'."), 404)
            return
        self._send_json(status)

    def _handle_cancel_run(self, run_id: str) -> None:
        server = self._ui_server
        if server.tasks.get_run(run_id) is None:
            self._send_json(error_body(f"Unknown run '{run_id}'."), 404)
            return
        self._send_json(server.runs.cancel_run(run_id))

    def _handle_get_result(self, run_id: str) -> None:
        server = self._ui_server
        if server.tasks.get_run(run_id) is None:
            self._send_json(error_body(f"Unknown run '{run_id}'."), 404)
            return
        try:
            result = server.runs.load_result(run_id)
        except IncompleteSearchError as exc:
            self._send_json(error_body(str(exc), {"status": "incomplete"}), 409)
            return
        except ValueError as exc:
            self._send_json(error_body(str(exc)), 409)
            return
        self._send_json(result.model_dump(mode="json"))

    def _handle_get_alternatives(self, run_id: str) -> None:
        server = self._ui_server
        record = server.tasks.get_run(run_id)
        if record is None:
            self._send_json(error_body(f"Unknown run '{run_id}'."), 404)
            return
        try:
            result = server.runs.load_result(run_id)
        except (IncompleteSearchError, ValueError) as exc:
            self._send_json(error_body(str(exc), {"status": "incomplete"}), 409)
            return
        store = server.runs.open_store(run_id)
        events = store.get_events(run_id)
        champion_id = result.champion.candidate_id if result.champion else None
        enriched = [self._enrich_alternative(alt, events, champion_id) for alt in result.alternatives]
        self._send_json(
            {
                "run_id": run_id,
                "termination_reason": result.termination_reason.value,
                "champion_id": champion_id,
                "alternatives": enriched,
            }
        )

    def _enrich_alternative(
        self, alt: AlternativeCandidate, events: list[Any], champion_id: str | None
    ) -> dict[str, Any]:
        from sst.core.events import SSTEvent

        typed_events: list[SSTEvent] = events
        cand_id = alt.candidate.candidate_id
        is_champion = champion_id is not None and cand_id == champion_id
        reasons: list[str] = []
        verifier = alt.verifier_outcome
        if verifier is not None and not verifier.passed:
            reasons.append(f"Deterministic verifier failed (exit {verifier.exit_code}).")
        score = alt.score
        verdict = score.critic_verdict if score else None
        if verdict == "PRUNE":
            reasons.append(f"Critic verdict PRUNE: {score.critic_rationale if score else ''}".rstrip())
        elif verdict == "ESCALATE_HUMAN":
            reasons.append("Critic verdict ESCALATE_HUMAN: needs human review before promotion.")
        elif verifier is not None and verifier.passed and (score is None or verdict in (None, "CRITIQUE_FAILED")):
            reasons.append("CRITIQUE_FAILED: no usable critic verdict; scored by verifier fallback only.")
        if not is_champion and verifier is not None and verifier.passed and verdict == "APPROVE":
            reasons.append("Passed checks but a higher-scoring candidate became champion.")

        node_events = [e for e in typed_events if e.node_id == cand_id]
        decisions = [
            {
                "verdict": str(e.payload.get("verdict", "")),
                "reason": str(e.payload.get("reason", "")),
                "approver": str(e.payload.get("approver", "")),
                "event_id": e.event_id,
            }
            for e in node_events
            if e.kind is EventKind.HUMAN_DECISION_RECORDED
        ]
        for decision in decisions:
            if decision["verdict"] == "REJECTED":
                reasons.append(f"Rejected by {decision['approver'] or 'operator'}: {decision['reason']}")
        escalation = next((e for e in node_events if e.kind is EventKind.HUMAN_DECISION_REQUESTED), None)
        domain_verdicts = [
            str(e.payload.get("domain_verdict", ""))
            for e in node_events
            if e.kind is EventKind.OUTCOME_REPORTED and e.payload.get("domain_verdict")
        ]
        payload = alt.model_dump(mode="json")
        payload["is_champion"] = is_champion
        payload["rejection_reasons"] = reasons
        payload["decisions"] = decisions
        payload["escalated"] = escalation is not None
        payload["escalation_reason"] = str(escalation.payload.get("reason", "")) if escalation else ""
        payload["domain_verdicts"] = domain_verdicts
        return payload

    def _handle_get_events(self, run_id: str, query: dict[str, str]) -> None:
        server = self._ui_server
        if server.tasks.get_run(run_id) is None:
            self._send_json(error_body(f"Unknown run '{run_id}'."), 404)
            return
        try:
            store = server.runs.open_store(run_id)
        except ValueError as exc:
            self._send_json(error_body(str(exc)), 409)
            return
        try:
            since = int(query.get("since", "0"))
        except ValueError:
            since = 0
        node_filter = query.get("node", "")
        events = store.get_events(run_id)
        items: list[dict[str, Any]] = []
        for seq, event in enumerate(events, start=1):
            if seq <= since:
                continue
            if node_filter and event.node_id != node_filter:
                continue
            items.append(
                {
                    "seq": seq,
                    "event_id": event.event_id,
                    "kind": event.kind.value,
                    "node_id": event.node_id,
                    "actor": event.actor,
                    "created_at": event.created_at.isoformat(),
                    "payload": event.payload,
                }
            )
        self._send_json({"run_id": run_id, "events": items, "total": len(events)})

    def _handle_get_tree(self, run_id: str) -> None:
        server = self._ui_server
        if server.tasks.get_run(run_id) is None:
            self._send_json(error_body(f"Unknown run '{run_id}'."), 404)
            return
        try:
            store = server.runs.open_store(run_id)
        except ValueError as exc:
            self._send_json(error_body(str(exc)), 409)
            return
        tree = store.rebuild_tree_from_events(run_id)
        if tree is None:
            self._send_json(error_body(f"No tree events for run '{run_id}' yet."), 409)
            return
        self._send_json(serialize_sst_tree(tree))

    # --- providers API (mode/presence only; never secret values) ---

    def _handle_get_providers(self) -> None:
        has_key = bool(os.environ.get("OPENAI_API_KEY"))
        model = os.environ.get("SST_MODEL", "gpt-4o")
        operator_kind = "OPENAI_COMPATIBLE" if has_key else "TEST (fallback — no OPENAI_API_KEY)"
        self._send_json(
            {
                "openai_api_key_present": has_key,
                "sst_model": model,
                "modes": [
                    {
                        "id": "fixture",
                        "label": "Fixture (TEST provider — deterministic test double)",
                        "available": True,
                    },
                    {
                        "id": "static",
                        "label": "Static insights (memory provider + operator gateway)",
                        "available": True,
                    },
                    {
                        "id": "operator",
                        "label": f"Operator gateway ({operator_kind})",
                        "available": True,
                        "detail": operator_kind,
                    },
                ],
            }
        )

    # --- decisions / promotion / outcomes ---

    def _handle_decide(self) -> None:
        server = self._ui_server
        try:
            req = DecideRequest.model_validate(self._read_json_body())
        except ValidationError as exc:
            self._send_json(
                error_body(f"Invalid decide request: {exc.errors()[0]['msg'] if exc.errors() else exc}"), 400
            )
            return
        record = server.tasks.get_run(req.run_id)
        if record is None:
            self._send_json(error_body(f"Unknown run '{req.run_id}'."), 404)
            return
        if req.verdict not in ("APPROVED", "REJECTED", "REVISED"):
            self._send_json(error_body("verdict must be APPROVED, REJECTED, or REVISED."), 400)
            return
        outcome = run_decide_command(
            req.run_id, req.candidate_id, req.verdict, req.reason, req.approver, record.project_path
        )
        self._send_json({"run_id": req.run_id, "candidate_id": req.candidate_id, **outcome})

    def _handle_promote(self) -> None:
        server = self._ui_server
        try:
            req = PromoteRequest.model_validate(self._read_json_body())
        except ValidationError as exc:
            self._send_json(
                error_body(f"Invalid promote request: {exc.errors()[0]['msg'] if exc.errors() else exc}"), 400
            )
            return
        record = server.tasks.get_run(req.run_id)
        if record is None:
            self._send_json(error_body(f"Unknown run '{req.run_id}'."), 404)
            return
        outcome = run_promote_command(req.run_id, req.candidate_id, record.project_path)
        self._send_json({"run_id": req.run_id, "candidate_id": req.candidate_id, **outcome})

    def _handle_outcome(self) -> None:
        server = self._ui_server
        try:
            req = OutcomeRequest.model_validate(self._read_json_body())
        except ValidationError as exc:
            self._send_json(
                error_body(f"Invalid outcome request: {exc.errors()[0]['msg'] if exc.errors() else exc}"), 400
            )
            return
        record = server.tasks.get_run(req.run_id)
        if record is None:
            self._send_json(error_body(f"Unknown run '{req.run_id}'."), 404)
            return
        try:
            store = server.runs.open_store(req.run_id)
        except ValueError as exc:
            self._send_json(error_body(str(exc)), 409)
            return
        # Same function SSTSearchController.report_outcome delegates to.
        seq = sandbox_report_outcome(
            store,
            tree_id=req.run_id,
            candidate_id=req.candidate_id,
            verdict=req.verdict,
            actor=req.actor,
            note=req.note,
        )
        self._send_json({"run_id": req.run_id, "candidate_id": req.candidate_id, "sequence_id": seq})


class SSTUIServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, project_root: Path, port: int) -> None:
        self.project_root = project_root
        self.tasks = TaskStore(project_root)
        self.runs = RunManager(self.tasks)
        super().__init__(("127.0.0.1", port), UIRequestHandler)


def create_server(project_root: Path | str, port: int) -> SSTUIServer:
    """Creates (but does not start) the SST browser UI server bound to 127.0.0.1."""
    return SSTUIServer(Path(project_root).resolve(), port)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SST task-to-result browser UI (real backend).")
    parser.add_argument("--project", type=Path, default=Path("."), help="Project root (tasks file lives here).")
    parser.add_argument("--port", type=int, default=8501, help="Port to serve on (127.0.0.1).")
    args = parser.parse_args(argv)
    server = create_server(args.project, args.port)
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    print(f"SST Browser UI serving {server.project_root} at http://{host}:{port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
