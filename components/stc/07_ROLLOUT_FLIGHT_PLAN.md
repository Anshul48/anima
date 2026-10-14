# STC: Biomimetic Spec-to-Code Autonomous Engineering Engine
## Volume 07: Master Rollout Flight Plan & Implementation Playbook

> **System:** STC (Spec-To-Code)  
> **Project Directory:** `code/utilities/stc`  
> **Status:** `[DECIDED]`  
> **Execution Standard:** Grounded, staged rollout. Zero meta-recursion. Each stage delivers working physical code verified by un-mocked tests before the next stage begins.

---

## 1. The 6-Stage Rollout Roadmap

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │ STAGE 0: REPOSITORY FOUNDATION & DATA CONTRACTS (Day 1)                │
  │ Set up uv environment, pyproject.toml, Pydantic schemas & protocols    │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ STAGE 1: SUBSTRATE HARD GATES & SIGNED RECEIPTS (Days 2–3)             │
  │ Implement deterministic quality gates & HMAC-SHA256 receipt engine     │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ STAGE 2: SOCRATIC DECOMPOSITION & ARCHETYPE DIFFING (Days 4–5)         │
  │ Implement TOC parsing, ambiguity detection & structured 2-choice prompt│
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ STAGE 3: CONTEXT COMPILER & TRACE HIPPOCAMPUS (Days 6–7)               │
  │ Connect to Trace SQLite FTS5 & compile sub-25KB task bundles           │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ STAGE 4: MORPHOGENETIC WORKTREE ORCHESTRATION (Week 2)                 │
  │ Git worktree leases, branch isolation, TTL management & worker dispatch│
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ STAGE 5: BLIND JUDICIARY AUDIT & GENETIC MEMORY (Week 2+)              │
  │ Codex adversarial review & Project Trace genome atom ingestion         │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Stage-by-Stage Implementation Tasks & Exit Gates

### Stage 0: Repository Foundation & Data Contracts
- **Deliverables:**
  - `code/utilities/stc/pyproject.toml`: Configured for Python 3.12, `uv`, dependencies (`click`, `rich`, `pydantic>=2.7`, `pyyaml`, `pytest`, `mypy`, `ruff`, `mutmut`).
  - `code/utilities/stc/src/stc/protocols/interfaces.py`: Complete PEP 544 typed interfaces.
  - `code/utilities/stc/src/stc/schemas/models.py`: Complete Pydantic V2 immutable data contracts.
  - `tests/unit/test_schemas.py`: Schema validation and immutability tests.
- **Physical Exit Gate:**
  ```bash
  uv run mypy --strict src/ tests/
  uv run pytest tests/unit/test_schemas.py
  ```
  Both commands exit with code `0`.

---

### Stage 1: Substrate Hard Quality Gates & Cryptographic Receipts
- **Deliverables:**
  - `src/stc/substrate/runner.py`: Executes `ruff`, `mypy`, `pytest`, `mutmut` inside target worktrees.
  - `src/stc/substrate/receipt.py`: Aggregates gate outputs, computes SHA256 checksum, signs receipt.
  - `tests/unit/test_substrate.py`: Tests gate execution, tamper detection, receipt verification.
- **Physical Exit Gate:**
  - Intentionally inject a syntax error; verify Gate 1 (`ruff`) fails and receipt reflects `is_passing == False`.
  - Run with clean code; verify signed `receipt.json` is emitted and passes verification.

---

### Stage 2: Socratic Decomposition & Archetype Diffing Engine
- **Deliverables:**
  - `src/stc/socratic/decomposer.py`: Parses markdown into 5-dimensional `TreeOfConcerns`.
  - `src/stc/socratic/ambiguity.py`: Calculates `AmbiguityScore`; generates pairwise `ArchetypeDiff`.
  - `src/stc/cli.py` (partial): `stc spec <file>` interactive command.
  - `tests/unit/test_socratic.py`: Verifies TOC parsing, threshold evaluation, archetype generation.
- **Physical Exit Gate:**
  - Running `stc spec ./specs/sample_spec.md` in terminal displays Rich TOC table and presents interactive 2-choice prompt for any detected ambiguity.

---

### Stage 3: Context Compiler & Trace Hippocampus Connector
- **Deliverables:**
  - `src/stc/memory/trace_client.py`: Queries local Project Trace SQLite FTS5 database (`documents_fts`).
  - `src/stc/compiler/bundler.py`: Assembles `task_bundle.yaml`, enforces strict 25,600-byte ceiling.
  - `tests/unit/test_compiler.py`: Verifies query retrieval, budget enforcement, and hierarchical pruning.
- **Physical Exit Gate:**
  - Compiling a bundle for a sample feature emits `task_bundle.yaml` measuring $\le 25\text{KB}$ in $< 200\text{ms}$.

---

### Stage 4: Morphogenetic Worktree Orchestrator & Worker Dispatch
- **Deliverables:**
  - `src/stc/worktree/manager.py`: Allocates ephemeral Git worktrees under `worktrees/stc-{task_id}`, tracks TTL.
  - `src/stc/orchestrator/dispatch.py`: Dispatches CLI workers (`agy`, `aider`, `dsh`) inside leased worktree.
  - `tests/unit/test_worktree.py`: Verifies worktree creation, clean teardown, and lease locking.
- **Physical Exit Gate:**
  - Successfully creates a worktree, applies a commit, runs substrate gates, and purges the worktree without altering `main`.

---

### Stage 5: Blind Judiciary Audit & Trace Genome Catalog
- **Deliverables:**
  - `src/stc/judiciary/auditor.py`: Headless Codex CLI invocation for blind adversarial diff audit.
  - `src/stc/genome/store.py`: Ingests verified implementations and negative inhibitors into Trace SQLite DB.
  - `src/stc/cli.py` (complete): Full end-to-end `stc run <spec.md>` command.
  - `tests/integration/test_dag_pipeline.py`: Comprehensive end-to-end verification.
- **Physical Exit Gate:**
  - Running `stc run ./specs/feature_rrf.md` executes the complete DAG from spec intake down to signed receipt and Sovereign merge prompt.

---

## 3. Daily Operating Cadence for the Human Sovereign

| Time | Action | Artifact / Command |
| :--- | :--- | :--- |
| **Morning (10m)** | Review Invariant Amendments & Archetype Diffs | `stc spec <new_spec.md>` |
| **Daytime** | Background workers run in leased worktrees | `stc worktree list` |
| **Afternoon (15m)**| Inspect Machine Receipts & Judiciary Findings | `stc receipt show <receipt.json>` |
| **Evening (5m)** | Sovereign Promotion & Merge to Main | `stc promote <task_id>` |
