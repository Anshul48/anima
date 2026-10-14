"""Full UI journey over real HTTP against the real backend (no mocks)."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

from sst.core.events import EventKind
from sst.gateway.contracts import GatewayRequest
from sst.storage.store import SQLiteSSTStore
from sst.ui.app import create_server
from sst.ui.runner import FixtureGateway


class UIClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            status = exc.code
        try:
            body: Any = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return status, body

    def get(self, path: str) -> tuple[int, Any]:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
        return self._request("POST", path, payload)

    def get_text(self, path: str) -> tuple[int, str]:
        with urllib.request.urlopen(self.base_url + path, timeout=30) as response:
            return response.status, response.read().decode("utf-8")


def _wait_ready(client: UIClient) -> None:
    deadline = time.time() + 15.0
    while time.time() < deadline:
        try:
            status, _ = client.get("/healthz")
        except OSError:
            time.sleep(0.1)
            continue
        if status == 200:
            return
    raise AssertionError("UI server did not become ready")


def _js_delimiter_error(script: str) -> str | None:
    """Returns a description of the first (){ }[] imbalance, else None.

    String/comment/template aware so HTML-embedded UI scripts can be screened
    without a JS runtime. Catches the shipped fault class (extra `)` breaking
    the whole run page); it is not a full parser — real browser execution in
    the Windows qualification remains the authoritative UI check.
    """
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    regex_lead = set(",=:[!&|?{};(")
    regex_words = {"return", "typeof", "case", "delete", "void", "in", "of", "new", "instanceof", "yield", "await"}
    i = 0
    line = 1
    n = len(script)
    while i < n:
        ch = script[i]
        if ch == "\n":
            line += 1
            i += 1
        elif ch == "/" and i + 1 < n and script[i + 1] == "/":
            while i < n and script[i] != "\n":
                i += 1
        elif ch == "/" and i + 1 < n and script[i + 1] == "*":
            i += 2
            while i + 1 < n and not (script[i] == "*" and script[i + 1] == "/"):
                if script[i] == "\n":
                    line += 1
                i += 1
            i += 2
        elif ch == "/" and i + 1 < n and script[i + 1] not in "/ *\n":
            j = i - 1
            while j >= 0 and script[j] in " \t\r\n":
                j -= 1
            k = j
            while k >= 0 and (script[k].isalnum() or script[k] in "_$"):
                k -= 1
            word = script[k + 1 : j + 1]
            if j < 0 or script[j] in regex_lead or word in regex_words:
                i += 1
                in_class = False
                while i < n:
                    c = script[i]
                    if c == "\\":
                        i += 2
                        continue
                    if c == "[":
                        in_class = True
                    elif c == "]":
                        in_class = False
                    elif c == "/" and not in_class:
                        break
                    elif c == "\n":
                        break
                    i += 1
                i += 1
                continue
            else:
                i += 1
                continue
        elif ch in "'\"`":
            quote = ch
            i += 1
            while i < n and script[i] != quote:
                if script[i] == "\\":
                    i += 1
                elif script[i] == "\n":
                    line += 1
                i += 1
            i += 1
        elif ch in "([{":
            stack.append((ch, line))
            i += 1
        elif ch in pairs:
            if not stack or stack[-1][0] != pairs[ch]:
                return f"unmatched {ch!r} at line {line}"
            stack.pop()
            i += 1
        else:
            i += 1
    if stack:
        opener, opener_line = stack[-1]
        return f"unclosed {opener!r} from line {opener_line}"
    return None


def test_served_js_has_balanced_delimiters(tmp_path: Path) -> None:
    """Every inline script on every UI page must be delimiter-balanced.

    Regression test for the shipped run-page fault (extra `)` in the graph
    mapping broke the whole page): the HTTP journey fetches HTML without
    executing JS, so this screens the served bytes directly.
    """
    import re

    project_root = tmp_path / "project"
    project_root.mkdir()
    server = create_server(project_root, 0)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = UIClient(f"http://127.0.0.1:{port}")
        _wait_ready(client)
        status, created = client.post(
            "/api/tasks",
            {
                "goal": "Delimiter screen",
                "project_path": str(project_root),
                "allowed_paths": [],
                "forbidden_paths": [],
                "acceptance_commands": [],
                "provider_mode": "fixture",
                "fixture_code": "x = 1\n",
            },
        )
        assert status == 201, created
        assert isinstance(created, dict)
        task_id = str(created["task_id"])
        status, run_created = client.post("/api/runs", {"task_id": task_id})
        assert status == 201, run_created
        assert isinstance(run_created, dict)
        run_id = str(run_created["run_id"])
        pages = {"/": None, f"/tasks/{task_id}": None, f"/runs/{run_id}": None}
        for path in pages:
            status, html = client.get_text(path)
            assert status == 200, path
            scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.DOTALL)
            assert scripts, f"no inline script found on {path}"
            for script in scripts:
                error = _js_delimiter_error(script)
                assert error is None, f"{path}: {error}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_ui_full_journey(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "math_mod.py").write_text("def mul(a, b): return a + b\n", encoding="utf-8")
    (repo / "test_math.py").write_text("from math_mod import mul\nassert mul(3, 4) == 12\n", encoding="utf-8")
    project_root = tmp_path / "project"
    project_root.mkdir()

    server = create_server(project_root, 0)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = UIClient(f"http://127.0.0.1:{port}")
        _wait_ready(client)

        # --- providers: presence only, never secret values ---
        status, providers = client.get("/api/providers")
        assert status == 200
        assert isinstance(providers, dict)
        assert isinstance(providers["openai_api_key_present"], bool)
        assert "sk-" not in json.dumps(providers)
        assert {m["id"] for m in providers["modes"]} == {"fixture", "static", "operator"}

        # --- create task ---
        status, created = client.post(
            "/api/tasks",
            {
                "goal": "Implement correct multiplication",
                "project_path": str(repo),
                "allowed_paths": ["math_mod.py"],
                "forbidden_paths": [],
                "acceptance_commands": ["python test_math.py"],
                "provider_mode": "fixture",
                "max_iterations": 2,
                "time_budget_seconds": 120,
                "fixture_code": "def mul(a, b): return a * b\n",
            },
        )
        assert status == 201, created
        assert isinstance(created, dict)
        task_id = str(created["task_id"])
        tasks_file = project_root / ".sst" / "ui-tasks.json"
        assert tasks_file.exists()
        assert task_id in tasks_file.read_text(encoding="utf-8")

        status, listed = client.get("/api/tasks")
        assert status == 200
        assert isinstance(listed, dict)
        assert any(t["task_id"] == task_id for t in listed["tasks"])

        # --- start run ---
        status, run_created = client.post("/api/runs", {"task_id": task_id})
        assert status == 201, run_created
        assert isinstance(run_created, dict)
        run_id = str(run_created["run_id"])
        assert run_id.startswith("tree_")

        # --- poll progress until finished ---
        deadline = time.time() + 180.0
        observed_statuses: set[str] = set()
        final_status: dict[str, Any] = {}
        while time.time() < deadline:
            status, payload = client.get(f"/api/runs/{run_id}")
            assert status == 200, payload
            assert isinstance(payload, dict)
            observed_statuses.add(str(payload["status"]))
            if payload["status"] == "finished":
                final_status = payload
                break
            assert payload["status"] in ("running", "finished")
            assert "live" in payload
            time.sleep(0.5)
        assert final_status, f"run never finished; saw {observed_statuses}"
        summary = final_status["result_summary"]
        assert summary["termination_reason"] == "champion_found"
        assert summary["champion_id"]
        assert final_status["events"]["event_count"] > 0
        assert final_status["events"]["verified"] >= 1

        # --- run persisted in the existing .sst/*.db event log ---
        db_path = repo / ".sst" / f"{run_id}.db"
        assert db_path.exists()
        store = SQLiteSSTStore(db_path)
        kinds = [e.kind for e in store.get_events(run_id)]
        assert EventKind.TREE_CREATED in kinds
        assert EventKind.SEARCH_COMPLETED in kinds

        # --- result envelope ---
        status, result = client.get(f"/api/runs/{run_id}/result")
        assert status == 200, result
        assert isinstance(result, dict)
        assert result["termination_reason"] == "champion_found"
        assert result["champion"] is not None
        assert "def mul(a, b): return a * b" in result["champion"]["patch_diff"]
        assert result["champion"]["target_paths"] == ["math_mod.py"]
        assert any(b["kind"] == "TEST" for b in result["gateway_bindings"])

        # --- alternatives compare ---
        status, alts = client.get(f"/api/runs/{run_id}/alternatives")
        assert status == 200, alts
        assert isinstance(alts, dict)
        assert len(alts["alternatives"]) >= 1
        champions = [a for a in alts["alternatives"] if a["is_champion"]]
        assert len(champions) == 1
        assert champions[0]["evidence_refs"]
        assert champions[0]["candidate"]["candidate_id"] == summary["champion_id"]
        champion_id = str(summary["champion_id"])

        # --- events feed ---
        status, events_payload = client.get(f"/api/runs/{run_id}/events")
        assert status == 200
        assert isinstance(events_payload, dict)
        assert any(e["kind"] == "SEARCH_COMPLETED" for e in events_payload["events"])
        status, filtered = client.get(f"/api/runs/{run_id}/events?node={champion_id}")
        assert status == 200
        assert isinstance(filtered, dict)
        assert all(e["node_id"] == champion_id for e in filtered["events"])

        # --- decide through the real CLI gate ---
        status, decision = client.post(
            "/api/decide",
            {
                "run_id": run_id,
                "candidate_id": champion_id,
                "verdict": "APPROVED",
                "reason": "UI journey test approval",
                "approver": "journey-test",
            },
        )
        assert status == 200, decision
        assert isinstance(decision, dict)
        assert decision["ok"] is True, decision
        decisions = [e for e in store.get_events(run_id) if e.kind is EventKind.HUMAN_DECISION_RECORDED]
        assert len(decisions) == 1
        assert decisions[0].payload["verdict"] == "APPROVED"

        # --- promote through the real CLI gate: real effect on disk ---
        status, promotion = client.post("/api/promote", {"run_id": run_id})
        assert status == 200, promotion
        assert isinstance(promotion, dict)
        assert promotion["ok"] is True, promotion
        assert "def mul(a, b): return a * b" in (repo / "math_mod.py").read_text(encoding="utf-8")
        promotions = [e for e in store.get_events(run_id) if e.kind is EventKind.PROMOTION_RECORDED]
        assert len(promotions) == 1

        # --- cancel on a finished run is a graceful no-op ---
        status, cancelled = client.post(f"/api/runs/{run_id}/cancel", {})
        assert status == 200
        assert isinstance(cancelled, dict)
        assert cancelled["status"] in ("cancelled", "not_running")

        # --- pages render ---
        status, index_html = client.get_text("/")
        assert status == 200
        assert task_id in index_html
        status, task_html = client.get_text(f"/tasks/{task_id}")
        assert status == 200
        assert run_id in task_html
        status, run_html = client.get_text(f"/runs/{run_id}")
        assert status == 200
        assert run_id in run_html
        assert "Budget consumption" in run_html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10.0)

    # --- reopen after restart: status + result load from the event log by tree_id ---
    server2 = create_server(project_root, 0)
    port2 = int(server2.server_address[1])
    thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
    thread2.start()
    try:
        client2 = UIClient(f"http://127.0.0.1:{port2}")
        _wait_ready(client2)
        status, reopened = client2.get(f"/api/runs/{run_id}")
        assert status == 200, reopened
        assert isinstance(reopened, dict)
        assert reopened["status"] == "finished"
        assert reopened["result_summary"]["termination_reason"] == "champion_found"
        status, result2 = client2.get(f"/api/runs/{run_id}/result")
        assert status == 200
        assert isinstance(result2, dict)
        assert result2["champion"]["candidate_id"] == champion_id
    finally:
        server2.shutdown()
        server2.server_close()
        thread2.join(timeout=10.0)


def test_fixture_gateway_reports_known_zero_cost() -> None:
    """Fixture (TEST) responses are free by construction: cost_known must be True."""
    gateway = FixtureGateway(code="V = 1\n")
    for role in ("diverge", "critique"):
        resp = gateway.invoke(GatewayRequest(role=role, messages=[{"role": "user", "content": "x"}]))
        assert resp.cost_usd == 0.0
        assert resp.cost_known is True
