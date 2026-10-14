"""Server-rendered HTML pages: task list, task detail, run detail. Vanilla JS, no build step."""

from __future__ import annotations

import html
from typing import Any

CSS = """
:root {
  --bg: #ffffff; --ink: #1c2733; --muted: #5b6b7b; --line: #dfe6ee;
  --accent: #1f4e79; --accent-ink: #ffffff; --wash: #f2f5f8;
  --ok: #1a7f37; --warn: #9a6700; --bad: #b42318; --info: #1f4e79;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
a { color: var(--accent); }
header.top { border-bottom: 1px solid var(--line); background: var(--wash); }
header.top .wrap { display: flex; align-items: center; gap: 1rem; }
header.top h1 { font-size: 1.05rem; margin: 0.7rem 0; font-weight: 650; }
header.top nav { margin-left: auto; font-size: 0.9rem; display: flex; gap: 1rem; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 1rem; }
main.wrap { padding-bottom: 3rem; }
h2 { font-size: 1.35rem; margin: 1.4rem 0 0.6rem; }
h3 { font-size: 1.05rem; margin: 1.4rem 0 0.5rem; border-bottom: 1px solid var(--line); padding-bottom: 0.3rem; }
.muted { color: var(--muted); } .small { font-size: 0.85rem; }
table { border-collapse: collapse; width: 100%; margin: 0.6rem 0; font-size: 0.93rem; }
th, td { text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.02em; }
tr:hover td { background: var(--wash); }
.pill { display: inline-block; padding: 0.1rem 0.55rem; border-radius: 999px; font-size: 0.8rem;
  font-weight: 600; border: 1px solid var(--line); background: var(--wash); color: var(--ink); white-space: nowrap; }
.pill.ok { color: var(--ok); border-color: var(--ok); background: #eef7f0; }
.pill.warn { color: var(--warn); border-color: var(--warn); background: #faf3e3; }
.pill.bad { color: var(--bad); border-color: var(--bad); background: #fbeeed; }
.pill.info { color: var(--info); border-color: var(--info); background: #edf2f7; }
form.card, section.card { border: 1px solid var(--line); border-radius: 8px; padding: 1rem 1.1rem;
  margin: 1rem 0; background: #fff; }
label { display: block; font-weight: 600; font-size: 0.88rem; margin: 0.7rem 0 0.25rem; }
input[type=text], input[type=number], textarea, select {
  width: 100%; padding: 0.5rem 0.6rem; font: inherit; border: 1px solid var(--line);
  border-radius: 6px; background: #fff; color: var(--ink); }
textarea { min-height: 4.2rem; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85rem; }
.hint { font-size: 0.82rem; color: var(--muted); font-weight: 400; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0 1.2rem; }
@media (max-width: 720px) { .grid2 { grid-template-columns: 1fr; } table { font-size: 0.85rem; } }
button, .btn { display: inline-block; font: inherit; font-weight: 600; cursor: pointer;
  border: 1px solid var(--accent); background: var(--accent); color: var(--accent-ink);
  padding: 0.45rem 1rem; border-radius: 6px; text-decoration: none; }
button.secondary { background: #fff; color: var(--accent); }
button.danger { background: #fff; color: var(--bad); border-color: var(--bad); }
button:disabled { opacity: 0.55; cursor: not-allowed; }
button:focus-visible, a:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible {
  outline: 3px solid #8fb6dd; outline-offset: 1px; }
pre { background: #0f1b29; color: #dbe7f3; padding: 0.8rem; border-radius: 6px; overflow-x: auto; font-size: 0.82rem; }
pre.light { background: var(--wash); color: var(--ink); border: 1px solid var(--line); }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.87em; }
details { border: 1px solid var(--line); border-radius: 6px; margin: 0.5rem 0; }
details summary { cursor: pointer; padding: 0.55rem 0.7rem; font-weight: 600; }
details .body { padding: 0 0.7rem 0.7rem; }
.bar { height: 0.55rem; background: var(--wash); border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
.bar > span { display: block; height: 100%; background: var(--accent); }
.tabs { display: flex; gap: 0.4rem; border-bottom: 1px solid var(--line); margin-top: 1rem; flex-wrap: wrap; }
.tabs button { background: none; border: none; color: var(--muted); border-radius: 6px 6px 0 0; padding: 0.5rem 0.9rem; }
.tabs button[aria-selected="true"] { color: var(--accent); background: var(--wash); font-weight: 700; }
.notice { border-left: 4px solid var(--accent); background: var(--wash); padding: 0.6rem 0.9rem; margin: 0.8rem 0; }
.notice.bad { border-color: var(--bad); background: #fbeeed; }
.notice.warn { border-color: var(--warn); background: #faf3e3; }
.notice.ok { border-color: var(--ok); background: #eef7f0; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}
"""


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def shell(title: str, body: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)} — SST Browser</title>
<style>{CSS}</style>
{extra_head}
</head>
<body>
<header class="top"><div class="wrap">
<h1>SST Task-to-Result Browser</h1>
<nav aria-label="Primary"><a href="/">Tasks</a><a href="/api/providers">Providers (JSON)</a></nav>
</div></header>
<main class="wrap">
{body}
</main>
</body>
</html>
"""


def index_page(tasks: list[dict[str, Any]], default_project: str) -> str:
    if tasks:
        rows = []
        for task in tasks:
            rows.append(
                "<tr>"
                f'<td><a href="/tasks/{_esc(task["task_id"])}">{_esc(task["task_id"])}</a></td>'
                f"<td>{_esc(task['goal'][:90])}</td>"
                f"<td>{_esc(task['provider_mode'])}</td>"
                f"<td>{task['run_count']}</td>"
                f'<td class="muted small">{_esc(task["created_at"][:19])}</td>'
                "</tr>"
            )
        table = (
            '<table><thead><tr><th scope="col">Task</th><th scope="col">Goal</th>'
            '<th scope="col">Provider mode</th><th scope="col">Runs</th><th scope="col">Created</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )
    else:
        table = (
            '<div class="notice"><strong>No tasks yet.</strong> '
            "Create one with the form below, then start a run from the task page.</div>"
        )
    body = f"""
<h2>Tasks</h2>
{table}
<h3>Create task</h3>
<form class="card" id="task-form" method="post" action="/api/tasks">
<div class="grid2"><div>
<label for="goal">Goal</label>
<textarea id="goal" name="goal" required placeholder="Implement correct multiplication"></textarea>
<label for="project_path">Project path <span class="hint">(source repo; defaults to server project)</span></label>
<input type="text" id="project_path" name="project_path" value="{_esc(default_project)}">
<label for="allowed_paths">Allowed scope <span class="hint">(one path per line)</span></label>
<textarea id="allowed_paths" name="allowed_paths" placeholder="math_mod.py"></textarea>
<label for="forbidden_paths">Forbidden scope <span class="hint">(one path per line)</span></label>
<textarea id="forbidden_paths" name="forbidden_paths"></textarea>
</div><div>
<label for="acceptance_commands">Acceptance commands <span class="hint">(one per line, run by the real verifier)</span></label>
<textarea id="acceptance_commands" name="acceptance_commands" placeholder="python test_math.py"></textarea>
<label for="provider_mode">Provider mode</label>
<select id="provider_mode" name="provider_mode">
<option value="fixture">Fixture — TEST provider (deterministic test double)</option>
<option value="static">Static insights — memory provider + operator gateway</option>
<option value="operator">Operator — live gateway (uses OPENAI_API_KEY when set)</option>
</select>
<label for="memory_insights">Static insights <span class="hint">(one per line; static mode only)</span></label>
<textarea id="memory_insights" name="memory_insights"></textarea>
<label for="fixture_code">Fixture code <span class="hint">(TEST-labeled; fixture mode only)</span></label>
<textarea id="fixture_code" name="fixture_code" placeholder="def mul(a, b): return a * b"></textarea>
</div></div>
<h3>Budgets</h3>
<div class="grid2"><div>
<label for="max_iterations">Max iterations</label>
<input type="number" id="max_iterations" name="max_iterations" value="5" min="1" max="100">
<label for="time_budget_seconds">Time budget (seconds)</label>
<input type="number" id="time_budget_seconds" name="time_budget_seconds" value="300" min="1">
</div><div>
<label for="token_budget">Token budget <span class="hint">(blank = unbounded)</span></label>
<input type="number" id="token_budget" name="token_budget" min="1">
<label for="cost_budget_usd">Cost budget (USD) <span class="hint">(blank = unbounded)</span></label>
<input type="number" id="cost_budget_usd" name="cost_budget_usd" step="0.01" min="0">
</div></div>
<p><button type="submit">Create task</button> <span class="muted small" id="task-status" role="status"></span></p>
</form>
<script>
document.getElementById("task-form").addEventListener("submit", async (ev) => {{
  ev.preventDefault();
  const form = ev.target;
  const lines = (name) => form.elements[name].value.split("\\n").map(s => s.trim()).filter(Boolean);
  const numOrNull = (name) => {{
    const raw = form.elements[name].value.trim();
    return raw === "" ? null : Number(raw);
  }};
  const payload = {{
    goal: form.elements["goal"].value.trim(),
    project_path: form.elements["project_path"].value.trim(),
    allowed_paths: lines("allowed_paths"),
    forbidden_paths: lines("forbidden_paths"),
    acceptance_commands: lines("acceptance_commands"),
    provider_mode: form.elements["provider_mode"].value,
    memory_insights: lines("memory_insights"),
    fixture_code: form.elements["fixture_code"].value,
    max_iterations: Number(form.elements["max_iterations"].value),
    time_budget_seconds: Number(form.elements["time_budget_seconds"].value),
    token_budget: numOrNull("token_budget"),
    cost_budget_usd: numOrNull("cost_budget_usd")
  }};
  const status = document.getElementById("task-status");
  status.textContent = "Creating…";
  try {{
    const resp = await fetch("/api/tasks", {{
      method: "POST", headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify(payload)
    }});
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    window.location.href = "/tasks/" + encodeURIComponent(data.task_id);
  }} catch (err) {{
    status.textContent = "Error: " + err.message;
  }}
}});
</script>
"""
    return shell("Tasks", body)


def task_page(task: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    if runs:
        rows = []
        for run in runs:
            status = str(run.get("status", "?"))
            cls = {"finished": "ok", "failed": "bad", "running": "info"}.get(status, "warn")
            summary = run.get("result_summary") or {}
            term = str(summary.get("termination_reason", ""))
            rows.append(
                "<tr>"
                f'<td><a href="/runs/{_esc(run["run_id"])}">{_esc(run["run_id"])}</a></td>'
                f'<td><span class="pill {cls}">{_esc(status)}</span></td>'
                f"<td>{_esc(run['provider_mode'])}</td>"
                f"<td>{_esc(term)}</td>"
                f'<td class="muted small">{_esc(run["created_at"][:19])}</td>'
                "</tr>"
            )
        run_table = (
            '<table><thead><tr><th scope="col">Run</th><th scope="col">Status</th>'
            '<th scope="col">Mode</th><th scope="col">Termination</th><th scope="col">Started</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )
    else:
        run_table = '<div class="notice"><strong>No runs yet.</strong> Start one below.</div>'
    body = f"""
<p class="small"><a href="/">&larr; All tasks</a></p>
<h2>Task {_esc(task["task_id"])}</h2>
<p>{_esc(task["goal"])}</p>
<table><tbody>
<tr><th scope="row">Project</th><td><code>{_esc(task["project_path"])}</code></td></tr>
<tr><th scope="row">Allowed</th><td><code>{_esc(", ".join(task["allowed_paths"]) or "—")}</code></td></tr>
<tr><th scope="row">Forbidden</th><td><code>{_esc(", ".join(task["forbidden_paths"]) or "—")}</code></td></tr>
<tr><th scope="row">Acceptance</th><td><code>{_esc("; ".join(task["acceptance_commands"]) or "—")}</code></td></tr>
<tr><th scope="row">Provider mode</th><td>{_esc(task["provider_mode"])}</td></tr>
<tr><th scope="row">Budgets</th><td>iterations={_esc(task["max_iterations"])} time={_esc(task["time_budget_seconds"])}s
tokens={_esc(task["token_budget"])} cost={_esc(task["cost_budget_usd"])}</td></tr>
</tbody></table>
<h3>Runs</h3>
{run_table}
<h3>Start run</h3>
<form class="card" id="run-form">
<div class="grid2"><div>
<label for="run_mode">Provider mode</label>
<select id="run_mode" name="provider_mode">
<option value="">Task default ({_esc(task["provider_mode"])})</option>
<option value="fixture">Fixture — TEST provider</option>
<option value="static">Static insights</option>
<option value="operator">Operator gateway</option>
</select>
<label for="run_iterations">Max iterations <span class="hint">(blank = task default)</span></label>
<input type="number" id="run_iterations" name="max_iterations" min="1">
</div><div>
<label for="run_time">Time budget (seconds) <span class="hint">(blank = task default)</span></label>
<input type="number" id="run_time" name="time_budget_seconds" min="1">
<label for="run_tokens">Token budget <span class="hint">(blank = task default)</span></label>
<input type="number" id="run_tokens" name="token_budget" min="1">
</div></div>
<p><button type="submit">Start run</button> <span class="muted small" id="run-status" role="status"></span></p>
</form>
<script>
document.getElementById("run-form").addEventListener("submit", async (ev) => {{
  ev.preventDefault();
  const form = ev.target;
  const numOrNull = (name) => {{
    const raw = form.elements[name].value.trim();
    return raw === "" ? null : Number(raw);
  }};
  const payload = {{ task_id: "{_esc(task["task_id"])}", provider_mode: form.elements["provider_mode"].value || null,
    max_iterations: numOrNull("max_iterations"), time_budget_seconds: numOrNull("time_budget_seconds"),
    token_budget: numOrNull("token_budget") }};
  const status = document.getElementById("run-status");
  status.textContent = "Starting…";
  try {{
    const resp = await fetch("/api/runs", {{
      method: "POST", headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify(payload)
    }});
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    window.location.href = "/runs/" + encodeURIComponent(data.run_id);
  }} catch (err) {{
    status.textContent = "Error: " + err.message;
  }}
}});
</script>
"""
    return shell(f"Task {task['task_id']}", body)


def run_page(run_id: str, task_id: str) -> str:
    body = f"""
<p class="small"><a href="/tasks/{_esc(task_id)}">&larr; Task {_esc(task_id)}</a></p>
<h2>Run <code>{_esc(run_id)}</code></h2>
<div id="run-banner" role="status"></div>
<section class="card" aria-label="Run status">
<div id="run-summary" class="small muted">Loading…</div>
<h3>Budget consumption</h3>
<div id="budget" class="small">Loading…</div>
<p><button type="button" class="danger" id="cancel-btn">Cancel run</button>
<span class="muted small" id="cancel-status" role="status"></span></p>
</section>
<div class="tabs" role="tablist" aria-label="Run views">
<button role="tab" aria-selected="true" data-tab="alternatives" id="tabbtn-alternatives">Alternatives</button>
<button role="tab" aria-selected="false" data-tab="actions" id="tabbtn-actions">Decide / Promote</button>
<button role="tab" aria-selected="false" data-tab="events" id="tabbtn-events">Events</button>
<button role="tab" aria-selected="false" data-tab="graph" id="tabbtn-graph">Graph</button>
</div>
<section id="tab-alternatives" role="tabpanel" aria-labelledby="tabbtn-alternatives"></section>
<section id="tab-actions" role="tabpanel" aria-labelledby="tabbtn-actions" hidden></section>
<section id="tab-events" role="tabpanel" aria-labelledby="tabbtn-events" hidden></section>
<section id="tab-graph" role="tabpanel" aria-labelledby="tabbtn-graph" hidden></section>
<script>
const RUN_ID = "{_esc(run_id)}";
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => (
  {{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}}[c]));
let pollTimer = null;
let graphLoaded = false;

document.querySelectorAll(".tabs button").forEach((btn) => {{
  btn.addEventListener("click", () => {{
    document.querySelectorAll(".tabs button").forEach(b => b.setAttribute("aria-selected", "false"));
    btn.setAttribute("aria-selected", "true");
    document.querySelectorAll('[role="tabpanel"]').forEach(p => {{ p.hidden = true; }});
    const panel = document.getElementById("tab-" + btn.dataset.tab);
    panel.hidden = false;
    if (btn.dataset.tab === "graph" && !graphLoaded) {{ graphLoaded = true; loadGraph(); }}
    if (btn.dataset.tab === "events") loadEvents();
  }});
}});

function pill(text, cls) {{ return `<span class="pill ${{cls}}">${{esc(text)}}</span>`; }}

function statusPill(status) {{
  const cls = {{"finished": "ok", "failed": "bad", "running": "info"}}[status] || "warn";
  return pill(status, cls);
}}

function renderSummary(data) {{
  const ev = data.events || {{}};
  const live = data.live || {{}};
  const summary = data.result_summary || null;
  let banner = "";
  if (data.status === "finished" && summary) {{
    const term = summary.termination_reason;
    if (term === "champion_found") banner = `<div class="notice ok"><strong>Champion found:</strong>
      <code>${{esc(summary.champion_id)}}</code> — ${{esc(summary.champion_title || "")}}</div>`;
    else if (term === "budget_exhausted") banner = `<div class="notice warn"><strong>Budget exhausted.</strong>
      No champion; increase budgets or narrow scope and re-run.</div>`;
    else if (term === "cancelled") banner = `<div class="notice warn"><strong>Run cancelled.</strong>
      Partial results below; nothing was promoted.</div>`;
    else banner = `<div class="notice"><strong>No verified candidate.</strong>
      The search finished without a champion.</div>`;
    if ((summary.provider_errors || 0) > 0) banner += `<div class="notice bad"><strong>Provider failures recorded:</strong>
      ${{summary.provider_errors}} error(s). Check the Events tab and provider configuration.</div>`;
  }} else if (data.status === "failed") {{
    banner = `<div class="notice bad"><strong>Run failed.</strong>
      <pre class="light">${{esc(data.error || "unknown error")}}</pre></div>`;
  }} else if (data.status === "incomplete") {{
    banner = `<div class="notice warn"><strong>Incomplete run.</strong>
      No live worker and no finished marker in the event log (e.g. server restarted mid-run).</div>`;
  }}
  document.getElementById("run-banner").innerHTML = banner;
  document.getElementById("run-summary").innerHTML =
    `Status: ${{statusPill(data.status)}} &nbsp; Mode: <code>${{esc(data.provider_mode)}}</code>
     &nbsp; Events: ${{ev.event_count || 0}} &nbsp; Proposed: ${{ev.proposed || 0}}
     &nbsp; Verified: ${{ev.verified || 0}} &nbsp; Verify failed: ${{ev.verify_failed || 0}}
     &nbsp; Scored: ${{ev.scored || 0}} &nbsp; Provider errors: ${{ev.provider_errors || 0}}
     &nbsp; Escalations: ${{ev.escalations || 0}} &nbsp; Decisions: ${{ev.decisions || 0}}
     &nbsp; Promotions: ${{ev.promotions || 0}}` +
    (data.status === "running" ? `<br>Iteration: ${{live.iterations_completed ?? 0}}
     &nbsp; Elapsed: ${{live.elapsed_seconds ?? 0}}s` : "") +
    (summary ? `<br>Termination: <code>${{esc(summary.termination_reason)}}</code>
     &nbsp; Alternatives: ${{summary.alternatives}}` : "");
  renderBudget(data, live, summary);
  document.getElementById("cancel-btn").disabled = (data.status !== "running");
}}

function bar(used, cap) {{
  if (cap === null || cap === undefined || cap === 0) return `<span class="muted">unbounded</span>`;
  const pct = Math.min(100, Math.round((used / cap) * 100));
  return `<div class="bar" role="img" aria-label="${{used}} of ${{cap}}"><span style="width:${{pct}}%"></span></div>
    <span class="muted">${{used}} / ${{cap}} (${{pct}}%)</span>`;
}}

function renderBudget(data, live, summary) {{
  const budgets = data.budgets || {{}};
  const consumed = (summary && summary.budget_consumed) || live;
  const rows = [
    ["Iterations", consumed.iterations_completed ?? 0, budgets.max_iterations ?? null],
    ["Tokens", consumed.tokens_consumed ?? 0,
      budgets.task_token_budget ?? budgets.max_token_budget ?? null],
    ["Cost (USD)", consumed.estimated_cost_usd ?? 0,
      budgets.task_cost_budget_usd ?? budgets.max_cost_usd ?? null],
    ["Elapsed (s)", Math.round(consumed.elapsed_seconds ?? 0),
      budgets.task_time_budget_seconds ?? budgets.max_time_seconds ?? null]
  ];
  document.getElementById("budget").innerHTML = "<table><tbody>" + rows.map(([label, used, cap]) =>
    `<tr><th scope="row">${{esc(label)}}</th><td>${{esc(used)}}</td><td>${{bar(used, cap)}}</td></tr>`
  ).join("") + "</tbody></table>" +
  ((summary && summary.gateway_bindings) ? "<p class='small muted'>Gateway: " +
    summary.gateway_bindings.map(b => esc(`${{b.role}}→${{b.profile}}/${{b.model}} [${{b.kind}}]`)).join("; ") + "</p>" : "");
}}

async function loadAlternatives() {{
  const panel = document.getElementById("tab-alternatives");
  try {{
    const resp = await fetch("/api/runs/" + encodeURIComponent(RUN_ID) + "/alternatives");
    const data = await resp.json();
    if (!resp.ok) {{
      panel.innerHTML = `<div class="notice"><strong>Alternatives unavailable:</strong> ${{esc(data.error || resp.statusText)}}
        (available once the run finishes).</div>`;
      return;
    }}
    if (!data.alternatives.length) {{
      panel.innerHTML = `<div class="notice"><strong>No alternatives.</strong>
        No candidate reached evaluation in this run.</div>`;
      return;
    }}
    panel.innerHTML = data.alternatives.map((alt) => {{
      const cand = alt.candidate;
      const score = alt.score || {{}};
      const ver = alt.verifier_outcome || {{}};
      const verdict = score.critic_verdict || (ver.passed ? "CRITIQUE_FAILED" : "PRUNE");
      const verdictCls = verdict === "APPROVE" ? "ok" : (verdict === "CRITIQUE_FAILED" ? "warn" : "bad");
      const reasons = (alt.rejection_reasons || []).map(r => `<li>${{esc(r)}}</li>`).join("");
      const evidence = (alt.evidence_refs || []).map(e =>
        `<a href="#evt" data-evidence="${{esc(e)}}"><code>${{esc(e)}}</code></a>`).join(" ");
      return `<details ${{alt.is_champion ? "open" : ""}}>
        <summary>${{alt.is_champion ? "★ Champion — " : ""}}<code>${{esc(cand.candidate_id)}}</code>
        ${{esc(cand.title)}} &nbsp; ${{pill(verdict, verdictCls)}}
        ${{ver.passed ? pill("verifier passed", "ok") : pill("verifier failed", "bad")}}</summary>
        <div class="body">
        <p><strong>Rationale:</strong> ${{esc(cand.rationale || "—")}}</p>
        <p class="small muted">Targets: <code>${{esc((cand.target_paths || []).join(", "))}}</code>
        &nbsp; Model: <code>${{esc(cand.model_id || "?")}}</code>
        &nbsp; Score: ${{score.normalized_reward ?? "—"}}</p>
        ${{score.critic_rationale ? `<p><strong>Critic:</strong> ${{esc(score.critic_rationale)}}</p>` : ""}}
        ${{alt.escalated ? `<div class="notice warn"><strong>Human decision requested:</strong>
          ${{esc(alt.escalation_reason || "")}}</div>` : ""}}
        ${{(alt.decisions || []).map(d => `<p>${{pill(d.verdict, d.verdict === "APPROVED" ? "ok" : "bad")}}
          by ${{esc(d.approver)}}: ${{esc(d.reason)}}</p>`).join("")}}
        ${{(alt.domain_verdicts || []).map(v => `<p class="small muted">Domain verdict (non-authoritative):
          ${{esc(v)}}</p>`).join("")}}
        ${{reasons ? `<p><strong>Why not champion:</strong></p><ul>${{reasons}}</ul>` : ""}}
        <details><summary>Patch / diff</summary><div class="body">
        <pre>${{esc(cand.patch_diff || "(no diff)")}}</pre></div></details>
        <p><strong>Checks:</strong> exit=${{ver.exit_code ?? "?"}}
        duration=${{ver.duration_seconds ?? "?"}}s</p>
        ${{ver.stderr ? `<pre class="light">${{esc(String(ver.stderr).slice(0, 2000))}}</pre>` : ""}}
        <p class="small"><strong>Evidence events:</strong> ${{evidence || "—"}}</p>
        </div></details>`;
    }}).join("");
    panel.querySelectorAll("[data-evidence]").forEach(a => a.addEventListener("click", (ev) => {{
      ev.preventDefault();
      document.getElementById("tabbtn-events").click();
      highlightEvent(a.dataset.evidence);
    }}));
    renderActions(data.alternatives);
  }} catch (err) {{
    panel.innerHTML = `<div class="notice bad"><strong>Failed to load alternatives:</strong> ${{esc(err.message)}}</div>`;
  }}
}}

function renderActions(alternatives) {{
  const panel = document.getElementById("tab-actions");
  const options = alternatives.map(a =>
    `<option value="${{esc(a.candidate.candidate_id)}}">${{esc(a.candidate.candidate_id)}} — ${{esc(a.candidate.title)}}</option>`
  ).join("");
  panel.innerHTML = `
  <h3>Record human decision</h3>
  <form class="card" id="decide-form">
  <label for="decide_candidate">Candidate</label>
  <select id="decide_candidate" name="candidate_id">${{options}}</select>
  <label for="decide_verdict">Verdict</label>
  <select id="decide_verdict" name="verdict">
  <option value="APPROVED">APPROVED</option><option value="REJECTED">REJECTED</option>
  <option value="REVISED">REVISED</option></select>
  <label for="decide_reason">Reason</label>
  <textarea id="decide_reason" name="reason" required></textarea>
  <label for="decide_approver">Approver</label>
  <input type="text" id="decide_approver" name="approver" value="operator">
  <p><button type="submit">Record decision</button> <span class="small" id="decide-status" role="status"></span></p>
  </form>
  <h3>Promote to workspace</h3>
  <form class="card" id="promote-form">
  <p class="small muted">Promotes the champion (or the selected candidate) through the same gates as
  <code>sst promote</code>: verifier-passed, integrity binding, base-commit freshness, and human-approval checks.</p>
  <label for="promote_candidate">Candidate <span class="hint">(blank = recommended champion)</span></label>
  <select id="promote_candidate" name="candidate_id"><option value="">Champion (recommended)</option>${{options}}</select>
  <p><button type="submit">Promote</button> <span class="small" id="promote-status" role="status"></span></p>
  </form>
  <h3>Report domain outcome</h3>
  <form class="card" id="outcome-form">
  <p class="small muted">Records a domain verdict verbatim. Never authoritative; never a promotion input.</p>
  <label for="outcome_candidate">Candidate</label>
  <select id="outcome_candidate" name="candidate_id">${{options}}</select>
  <label for="outcome_verdict">Verdict</label>
  <input type="text" id="outcome_verdict" name="verdict" required placeholder="e.g. e2e:pass">
  <label for="outcome_note">Note</label>
  <input type="text" id="outcome_note" name="note">
  <p><button type="submit" class="secondary">Report outcome</button>
  <span class="small" id="outcome-status" role="status"></span></p>
  </form>`;
  const postForm = (formId, statusId, url, build) => {{
    document.getElementById(formId).addEventListener("submit", async (ev) => {{
      ev.preventDefault();
      const form = ev.target;
      const status = document.getElementById(statusId);
      status.textContent = "Working…";
      try {{
        const resp = await fetch(url, {{ method: "POST",
          headers: {{"Content-Type": "application/json"}}, body: JSON.stringify(build(form)) }});
        const data = await resp.json();
        const ok = resp.ok && (data.ok !== false);
        status.innerHTML = (ok ? pill("accepted", "ok") : pill("refused", "bad")) +
          `<pre class="light">${{esc(data.output || data.error || "")}}</pre>`;
        loadAlternatives();
      }} catch (err) {{
        status.textContent = "Error: " + err.message;
      }}
    }});
  }};
  postForm("decide-form", "decide-status", "/api/decide", (f) => ({{
    run_id: RUN_ID, candidate_id: f.elements["candidate_id"].value,
    verdict: f.elements["verdict"].value, reason: f.elements["reason"].value,
    approver: f.elements["approver"].value || "operator" }}));
  postForm("promote-form", "promote-status", "/api/promote", (f) => {{
    const cand = f.elements["candidate_id"].value;
    return cand ? {{ run_id: RUN_ID, candidate_id: cand }} : {{ run_id: RUN_ID }};
  }});
  postForm("outcome-form", "outcome-status", "/api/outcomes", (f) => ({{
    run_id: RUN_ID, candidate_id: f.elements["candidate_id"].value,
    verdict: f.elements["verdict"].value, note: f.elements["note"].value || null }}));
}}

let allEvents = [];
async function loadEvents() {{
  const panel = document.getElementById("tab-events");
  try {{
    const resp = await fetch("/api/runs/" + encodeURIComponent(RUN_ID) + "/events");
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    allEvents = data.events || [];
    if (!allEvents.length) {{
      panel.innerHTML = `<div class="notice"><strong>No events yet.</strong></div>`;
      return;
    }}
    panel.innerHTML = `<p class="small muted">${{allEvents.length}} events (append-only log).</p>` +
      allEvents.map((e) => `<details id="event-${{esc(e.event_id)}}">
        <summary><code>#${{e.seq}} ${{esc(e.kind)}}</code>
        ${{e.node_id ? `<code>${{esc(e.node_id)}}</code>` : ""}}
        <span class="muted small">${{esc(e.created_at || "")}}</span></summary>
        <div class="body"><pre class="light">${{esc(JSON.stringify(e.payload || {{}}, null, 2).slice(0, 4000))}}</pre></div>
      </details>`).join("");
  }} catch (err) {{
    panel.innerHTML = `<div class="notice bad"><strong>Failed to load events:</strong> ${{esc(err.message)}}</div>`;
  }}
}}

function highlightEvent(eventId) {{
  requestAnimationFrame(() => {{
    const el = document.getElementById("event-" + eventId);
    if (el) {{ el.open = true; el.scrollIntoView(); }}
  }});
}}

async function loadGraph() {{
  const panel = document.getElementById("tab-graph");
  panel.innerHTML = `<p class="small muted">Loading tree…</p>`;
  try {{
    const resp = await fetch("/api/runs/" + encodeURIComponent(RUN_ID) + "/tree");
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    panel.innerHTML = `<div id="cy" style="height:420px;border:1px solid var(--line);border-radius:6px;"></div>
      <p class="small muted">Same Cytoscape.js mechanism as <code>sst visualize</code>. ` +
      `Requires network access to the CDN; the tables above remain the source of truth offline.</p>`;
    const loadScript = (src) => new Promise((resolve, reject) => {{
      const s = document.createElement("script");
      s.src = src; s.onload = resolve; s.onerror = () => reject(new Error("CDN load failed: " + src));
      document.head.appendChild(s);
    }});
    if (!window.cytoscape) {{
      await loadScript("https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js");
      await loadScript("https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js");
      await loadScript("https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.min.js");
    }}
    const nodes = data.nodes || [];
    const edges = data.edges || [];
    const elements = [
      ...nodes.map(n => ({{ data: {{ id: n.id, label: (n.title || n.id).slice(0, 28) }} }})),
      ...edges.map(e => ({{ data: {{ id: e.id, source: e.source, target: e.target }} }}))
    ];
    const cy = window.cytoscape({{
      container: document.getElementById("cy"), elements,
      style: [
        {{ selector: "node", style: {{ "background-color": "#1f4e79", "label": "data(label)",
          "color": "#1c2733", "font-size": "10px", "text-valign": "bottom" }} }},
        {{ selector: "edge", style: {{ "width": 1.5, "line-color": "#8fa3b8",
          "target-arrow-color": "#8fa3b8", "target-arrow-shape": "triangle", "curve-style": "bezier" }} }}
      ],
      layout: {{ name: "dagre", rankDir: "TB", nodeSep: 40, rankSep: 60 }}
    }});
    cy.on("tap", "node", (ev) => {{
      const id = ev.target.id();
      document.getElementById("tabbtn-alternatives").click();
      const el = Array.from(document.querySelectorAll("#tab-alternatives code"))
        .find(c => c.textContent === id);
      if (el) el.closest("details").open = true;
    }});
  }} catch (err) {{
    panel.innerHTML = `<div class="notice warn"><strong>Graph unavailable:</strong> ${{esc(err.message)}}.
      The alternatives table and event log carry the same information.</div>`;
  }}
}}

async function refresh() {{
  try {{
    const resp = await fetch("/api/runs/" + encodeURIComponent(RUN_ID));
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || resp.statusText);
    renderSummary(data);
    if (data.status !== "running") {{
      if (pollTimer) {{ clearInterval(pollTimer); pollTimer = null; }}
      loadAlternatives();
      if (!document.getElementById("tab-events").hidden) loadEvents();
    }}
  }} catch (err) {{
    document.getElementById("run-summary").textContent = "Error: " + err.message;
  }}
}}

document.getElementById("cancel-btn").addEventListener("click", async () => {{
  const status = document.getElementById("cancel-status");
  status.textContent = "Cancelling…";
  try {{
    const resp = await fetch("/api/runs/" + encodeURIComponent(RUN_ID) + "/cancel", {{ method: "POST" }});
    const data = await resp.json();
    status.textContent = data.detail || data.status || resp.statusText;
    refresh();
  }} catch (err) {{
    status.textContent = "Error: " + err.message;
  }}
}});

refresh();
loadAlternatives();
pollTimer = setInterval(refresh, 2000);
</script>
"""
    return shell(f"Run {run_id}", body)
