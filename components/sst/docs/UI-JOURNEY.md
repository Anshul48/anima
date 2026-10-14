# SST Task-to-Result Browser UI

Real-backend browser UI for the full SST journey: create task → start run →
live progress → compare alternatives → decide → promote → reopen.

## Run

```sh
cd /tmp/sst-coord/ui-build
UV_CACHE_DIR=/tmp/sst-coord/uv-cache uv sync --all-extras --frozen
.venv/bin/python -m sst.ui.app --project PATH --port 8501
```

Open `http://127.0.0.1:8501`. Stdlib `http.server` only (threaded), no new
dependencies, no build step (vanilla JS + inline HTML).

## Pages

- `/` — task list + create-task form (goal, project path, allowed/forbidden
  scope, acceptance commands, provider mode, token/cost/time/iteration
  budgets, static insights, TEST-labeled fixture code).
- `/tasks/{id}` — task detail, run history, start-run form (mode/budget
  overrides).
- `/runs/{id}` — live status (2s poll), budget-consumption bars,
  provider/failure banners, Alternatives tab (rationale, diff, checks, critic
  verdict incl. honest `CRITIQUE_FAILED`, rejection reasons, evidence event
  links), Decide/Promote tab with gate outcomes, Events tab, optional Graph
  tab (Cytoscape via the same CDN mechanism as `sst visualize`; tables remain
  authoritative offline).

Covered states: empty (no tasks / no alternatives), unavailable-provider
(banner when provider errors are recorded), running, cancelled, exhausted,
failed (traceback shown), completed, incomplete (no worker, no finished
marker — e.g. restart mid-run).

## JSON API

- `POST /api/tasks`, `GET /api/tasks`, `GET /api/tasks/{id}`
- `POST /api/runs {task_id, provider_mode?, budgets...}` → `{run_id}`
  (`run_id` is the `tree_id`; event log is the source of truth)
- `GET /api/runs/{id}` — status + progress + budget + result summary
- `POST /api/runs/{id}/cancel`
- `GET /api/runs/{id}/result` — `SearchResult` JSON (409 while incomplete)
- `GET /api/runs/{id}/alternatives` — enriched with `is_champion`,
  `rejection_reasons`, `decisions`, escalation, non-authoritative domain
  verdicts, `evidence_refs` event links
- `GET /api/runs/{id}/events?since=&node=` — append-only log feed
- `GET /api/runs/{id}/tree` — serialized DAG (same shape as the visualizer)
- `POST /api/decide {run_id, candidate_id, verdict, reason, approver?}`
- `POST /api/promote {run_id, candidate_id?}`
- `POST /api/outcomes {run_id, candidate_id, verdict, note?}` — domain
  verdict via the same `report_outcome` the controller delegates to
- `GET /api/providers` — mode/presence only (`openai_api_key_present` bool;
  never secret values)

## Backend wiring (no mocks)

- Runs execute `SSTSearchController.run_search` in a worker thread;
  cancel calls `controller.cancel()`.
- `SQLiteSSTStore` per request/thread (thread-safe, one connection per op).
- Results via `get_search_result` (reopen = load by `tree_id`).
- Decide/promote invoke the real `sst` CLI commands in-process via
  `click.testing.CliRunner` — identical gates, no reimplementation.
- Provider modes: `fixture` (TEST-kind gateway returning the task's
  fixture code; still verified by real acceptance commands), `static`
  (static memory provider + CLI default gateway), `operator` (CLI default
  gateway: `OPENAI_COMPATIBLE` when `OPENAI_API_KEY` is set, else TEST).

## Persistence

- Tasks + run index: `<project>/.sst/ui-tasks.json`.
- Runs: existing `<task-project>/.sst/<tree_id>.db` event logs.

## Tests

`tests/unit/test_ui_journey.py` starts the real server on an ephemeral port
and drives the whole journey over HTTP with `urllib`, asserting on-disk/db
effects (tasks file, event log, decision/promotion events, promoted file
bytes) plus a restart-and-reopen pass.

## Browser execution and JS screening

The HTTP journey fetches HTML without executing JavaScript, so it missed a
shipped run-page `SyntaxError` (extra `)` in the graph mapping) that left the
page on "Loading…". Two durable guards:

- `test_served_js_has_balanced_delimiters` screens every inline script on
  every served page for delimiter balance (string/comment/regex aware). It
  fails on the pre-fix bytes and passes on the fixed ones. It is a screen,
  not a parser.
- The authoritative check is real browser execution: see
  `.delivery/windows-qualification/` (`native_browser_probe.py`,
  `browser-20261004-135819/report.json`) for the headless-Chrome procedure
  and evidence. Re-run it for UI changes that touch served scripts.

## Provider selection

The UI `operator` mode delegates to the CLI default gateway: `OPENAI_API_KEY`
(OpenAI) > `DEEPSEEK_API_KEY` (DeepSeek) > `TEST` fixture, with
`OPENAI_BASE_URL`/`SST_MODEL` overrides. There is no separate manual
candidate-submission channel; human input flows through decide/promote.
