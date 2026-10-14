# SST Cytoscape.js Visualizer & Live Streaming Guide

> **Document Version:** 1.0.0  
> **Package:** `sst-engine` (`src/sst/visualizer`)  
> **Status:** Production Architecture Standard  

---

## 1. Overview & Architecture

The State Space Tree visualizer provides real-time, interactive graphical inspection of active and completed MCTS search trees. It renders Directed Acyclic Graphs (DAGs) using **Cytoscape.js** and the **Dagre** hierarchical layout engine.

```
┌─────────────────┐       GET /api/stream (SSE)       ┌────────────────────────┐
│   SST Search    │ ────────────────────────────────> │ Interactive Browser UI │
│   Controller    │      Live Deltas & Snapshots      │     (Cytoscape.js)     │
└────────┬────────┘                                   └────────────────────────┘
         │                                                        ▲
         ▼                                                        │
┌─────────────────┐             GET /api/tree                     │
│ SQLite WAL DB   │ ──────────────────────────────────────────────┘
│ (.sst/<id>.db)  │
└─────────────────┘
```

The visualizer operates in two complementary modes:
1. **Live HTTP/SSE Streaming Server**: Binds to `:8501` to stream node expansions, test evaluations, and pruning events to connected web browsers in real time.
2. **Headless HTML Exporter**: Compiles the complete tree snapshot into a zero-dependency, self-contained HTML file suitable for offline analysis, CI artifacts, and post-mortems.

---

## 2. Server Endpoints & Protocol

When launched via `sst visualize --serve --port 8501`, the internal HTTP server provides the following REST and streaming endpoints:

| Method | Route | Response Format | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | `text/html; charset=utf-8` | Complete single-page application with bundled CSS and Cytoscape scripts. |
| `GET` | `/api/tree` | `application/json` | Serialized snapshot of the DAG (nodes, edges, winning path, goal). |
| `GET` | `/api/events` | `application/json` | Full historical event sequence for the active search tree. |
| `GET` | `/api/stream` | `text/event-stream` | Server-Sent Events (SSE) stream emitting real-time node additions and status deltas. |

### 2.1 The SSE Streaming Protocol
Upon connecting to `/api/stream`, clients receive an initial full snapshot event followed by atomic update deltas:

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"type": "snapshot", "tree": {"treeId": "tree_abc123", "nodes": [...]}}

data: {"type": "delta", "event": {"kind": "NODE_PROPOSED", "node_id": "cand_01", ...}}
```

The browser UI processes incoming deltas without reloading the page, seamlessly updating node colors, status badges, and winning path highlights as the search progresses.

---

## 3. UI Features & Visual Language

- **Color Coding**:
  - 🟣 **`CORTEX_PLANNER` / `CRITIQUE`**: Purple badges denoting architectural decisions.
  - 🔴 **`DIVERGE` (`ADHD_EXPLORER`)**: Warm red badges denoting high-entropy exploratory mutations.
  - 🔵 **`REFINE` (`ASD_EXPLOITER`)**: Cool blue badges denoting precision implementations.
  - 🟢 **`PASS_DETERMINISTIC`**: Bright green borders indicating verified test execution.
  - 🔴 **`PRUNED_SEMANTIC` / `FAIL_DETERMINISTIC`**: Translucent red background indicating abandoned or failed nodes.
- **Winning Path**: The optimal trajectory from root to champion leaf is highlighted with thick green connecting edges and glowing halos.
- **Side Panel Details**: Clicking any node displays its complete metadata:
  - Generation prompt tokens and cost ($USD).
  - Deterministic test execution stdout/stderr traceback.
  - Qualitative feedback from the semantic value critic.
  - Exact code diff syntax preview.

---

## 4. Standalone Offline HTML Export

To generate an offline visualization report without running a persistent web server:

```bash
# Export visualization to a standalone HTML file
uv run sst visualize tree_12345678 --export-html ./report.html
```

The resulting file:
- Inlines the complete tree state as an embedded JSON `<script>` payload.
- Can be opened directly in any web browser (`file:///.../report.html`) without internet access or local servers.
- Is ideal for attaching to GitHub Actions runs or pull requests.

---

## 5. Security & XSS Hardening

Because the visualizer renders arbitrary code diffs and LLM-generated text, strict cross-site scripting (XSS) defenses are enforced:
1. **JSON Tag Neutralization**: All JSON payloads embedded in `<script>` tags have forward slashes escaped (`</script>` $\to$ `<\/script>`) to prevent arbitrary script tag breakout.
2. **DOM Escaping**: Dynamic DOM manipulation in the client UI uses text-node assignment (`div.textContent = text; div.innerHTML`) via `escapeHtml()` before rendering titles, diffs, or critic comments.
3. **Localhost Binding**: By default, the server binds strictly to `127.0.0.1`, preventing unauthorized local network access unless explicitly overridden.

---

## 6. Running with Docker Compose

SST provides a turnkey containerized service for running the live visualizer:

```bash
# Start visualizer container
docker compose up -d sst-visualizer

# View visualizer logs
docker compose logs -f sst-visualizer
```

Open `http://localhost:8501` to view the live dashboard.
