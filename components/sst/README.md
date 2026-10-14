# State Space Tree (SST) Engine

> **Asymmetric Dialectic MCTS Heuristic Search Engine for Autonomous Code Synthesis & Scientific Hypothesis Exploration**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/managed%20by-uv-purple.svg)](https://github.com/astral-sh/uv)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy.readthedocs.io/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

> License note: this directory now ships an Apache-2.0 `LICENSE` (added at
> publication; `pyproject.toml` already stated Apache-2.0). See the
> repo-root README license table.

---

## 1. Overview

The **State Space Tree (SST)** engine is a high-performance heuristic tree search system designed to discover verified code implementations and scientific hypotheses through **asymmetric dialectic rollouts**:

- **Frontier Planner / Diverge**: High-entropy divergent exploration ($T=1.2$) generating structurally novel candidate architectures.
- **Monotropic Refinement / Refine**: Low-entropy compiler and type-theory rigor ($T=0.05$) enforcing interfaces, eliminating syntax errors, and fixing type signatures.
- **Deterministic Sandboxed Verification**: Deterministic gate execution (syntax checking, isolated worktrees, test suites, secret scrubbing) where passing candidates are verified with zero human subjectivity.
- **Value Critic & Colimit Synthesis**: Semantic critique ($T=0.2$) evaluating survivability and synthesizing competing passing branches into unified Pareto-optimal solutions.
- **Event-Sourced Persistence & Live Streaming**: SQLite WAL append-only event sourcing with live Cytoscape.js DAG visualization (`:8501`).

```
                              ┌────────────────┐
                              │ Root Goal Node │
                              └───────┬────────┘
                                      │
                   ┌──────────────────┴──────────────────┐
                   │                                     │
           [DIVERGE (T=1.2)]                     [DIVERGE (T=1.2)]
           Candidate Branch A                    Candidate Branch B
                   │                                     │
           [REFINE (T=0.05)]                     [REFINE (T=0.05)]
           Type Rigor & Cleanup                  Type Rigor & Cleanup
                   │                                     │
           [GATE VERIFIER]                       [GATE VERIFIER]
           Pytest / Mypy / Syntax                Pytest / Mypy / Syntax
                   │ (PASS)                              │ (PASS)
                   └──────────────────┬──────────────────┘
                                      │
                           [SYNTHESIZE (T=0.3)]
                           Colimit Unified Merge
                                      │
                           [CHAMPION PROMOTION]
```

---

## 2. Quick Start

### Installation

Ensure Python 3.12+ and [uv](https://github.com/astral-sh/uv) are installed:

```bash
# Clone or navigate to the repository
cd sst

# Install dependencies into hermetic virtual environment
make install
# or
uv sync --all-extras
```

### CLI Usage

```bash
# Run a bounded MCTS search on a goal
uv run sst run --goal "Implement thread-safe ring buffer" --max-iterations 5

# Inspect search tree status
uv run sst status <tree_id>

# Promote champion candidate to workspace
uv run sst promote <tree_id>

# Launch interactive Cytoscape.js visualizer on http://127.0.0.1:8501
uv run sst visualize <tree_id> --port 8501

# Launch the task-to-result web UI (tasks, runs, alternatives, promote)
uv run sst ui --project-path <project> --port 8501

# Machine-readable run with documented exit codes (0 champion, 2 none, 3 usage, 4 crash)
uv run sst run --goal "..." --project-path <project> --test-command "<check>" --json
```

### Result honesty

- Verification requires acceptance commands: every command runs, each result is
  retained, and an empty list fails explicitly instead of passing.
- A failed or malformed model critique yields verdict `CRITIQUE_FAILED` (rank
  0.5, no semantic approval), never a fabricated `APPROVE`.
- The `SearchResult` envelope and CLI report record provider bindings
  (`profile:model:KIND`), so fixture/`TEST` runs are unmistakable.
- `promote` refuses unless the verifier passed on the exact logged bytes
  (integrity binding), the workspace still matches the search snapshot, the
  base commit is fresh (git), and human gates approved. See
  `docs/RECOVERY-LIMITS.md` for what the event log can and cannot reconstruct.

---

## 3. Architecture Documentation Suite

Detailed architecture specifications are located in [`docs/`](docs/):

1. [`01_PLAN_BROAD_STROKES.md`](docs/01_PLAN_BROAD_STROKES.md) - Executive vision, tripartite triad (`trace/`, `stc/`, `sst/`), failure modes.
2. [`02_EXECUTION_DAG.md`](docs/02_EXECUTION_DAG.md) - MCTS lifecycle, UCT formula, pruning shears, state transitions.
3. [`03_DATA_CONTRACTS.md`](docs/03_DATA_CONTRACTS.md) - Pydantic V2 immutable data contracts (`TaskPacket`, `CandidateProposal`, `ScoreBreakdown`, `SSTEvent`).
4. [`04_DIALECTIC_SEARCH.md`](docs/04_DIALECTIC_SEARCH.md) - AuDHD asymmetric dialectic rollouts, temperature profiles, negative inhibitor feedback.
5. [`05_VISUALIZER_GUIDE.md`](docs/05_VISUALIZER_GUIDE.md) - Cytoscape.js DAG visualizer, SSE live delta streaming, REST API endpoints.

---

## 4. Development Quality Gates

All contributions must pass strict quality gates:

```bash
# Run all gates sequentially
make gate
# or on Windows PowerShell:
.\run.ps1 -Gate
```

Individual gate commands:
- `make lint` - Ruff lint checks
- `make format-check` - Code formatting check
- `make typecheck` - Mypy strict type checking
- `make test` - Pytest automated test suites

---

## 5. Docker Deployment

```bash
# Build the container
docker build -t sst-engine:latest .

# Run the live visualizer service
docker compose up -d
```
