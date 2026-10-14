# STC: Biomimetic Spec-to-Code Architecture & Technical Specification

> **System:** STC (Spec-To-Code Engine)  
> **Python Version:** 3.12+  
> **Toolchain:** `uv`, `git`, `ruff`, `mypy`, `pytest`, `mutmut`, `click`, `rich`  
> **Status:** `[DECIDED]` Master Architecture  

---

## 1. Architectural Philosophy

STC (Spec-to-Code) is engineered to solve autonomous long-horizon software development without falling prey to the **Lone Genius Illusion** (context saturation), the **Self-Certification Trap** (agents grading their own work), or the **Architecture Astronaut Recursion** (endless meta-scaffolds).

### Three Foundational Tenets:
1. **Decoupled Membranes (`protocols/` & `schemas/`):** Upstream domain contracts govern downstream implementations via PEP 544 `typing.Protocol` interfaces and immutable Pydantic V2 schemas. No circular contract drift.
2. **Sub-25KB Context Compilation:** LLM workers never receive 50-page architecture documents. Context is retrieved on-demand from the Neocortex (immutable schemas) and Hippocampus (Project Trace memory) into bounded, content-addressed `task_bundle.yaml` artifacts.
3. **Trias Politica Governance:** Rigid separation between the Human Sovereign (invariants & merge authority), Executive Workers (Agy / Aider / DeepSeek coding in isolated Git worktrees), Substrate Execution (deterministic gates & signed receipts), and Judiciary (blind adversarial Codex audit).

```
                            ┌─────────────────────────────────────────────────────────┐
                            │                 HUMAN SOVEREIGN (Vanguard)              │
                            │         Sets Invariants & Holds Promotion Authority      │
                            └────────────────────────────┬────────────────────────────┘
                                                         │
                                                         ▼
                            ┌─────────────────────────────────────────────────────────┐
                            │                     CLI / INGESTION                     │
                            │         `stc spec`  /  `stc compile`  /  `stc run`      │
                            └────────────────────────────┬────────────────────────────┘
                                                         │
                                                         ▼
       ┌─────────────────────────────────────────────────┴─────────────────────────────────────────────────┐
       │                                       STC ORCHESTRATION KERNEL                                    │
       │                                                                                                   │
       │  ┌───────────────────────┐   ┌───────────────────────┐   ┌─────────────────────────────────────┐  │
       │  │   Socratic Engine     │   │   Context Compiler    │   │      Worktree Leaser & Manager      │  │
       │  │ • TOC Decomposition   │──▶│ • Neocortex Queries   │──▶│ • Ephemeral Branch Sandboxing       │  │
       │  │ • Archetype Diffing   │   │ • Hippocampal Trace DB│   │ • Cross-OS Leased Directories       │  │
       │  │ • Invariant Locking   │   │ • Sub-25KB TaskBundle │   │ • Time-To-Live Enforcement          │  │
       │  └───────────────────────┘   └───────────────────────┘   └──────────────────┬──────────────────┘  │
       └─────────────────────────────────────────────────────────────────────────────┼─────────────────────┘
                                                                                     │
                                                                                     ▼
                                                                  ┌─────────────────────────────────────┐
                                                                  │          EXECUTIVE WORKERS          │
                                                                  │      `agy` / `aider` / `dsh`        │
                                                                  │    Executes in Leased Worktree      │
                                                                  └──────────────────┬──────────────────┘
                                                                                     │
                                                                                     ▼
       ┌─────────────────────────────────────────────────────────────────────────────┴─────────────────────┐
       │                                     SUBSTRATE & JUDICIARY VERIFICATION                            │
       │                                                                                                   │
       │  ┌───────────────────────────────────────────────────┐   ┌─────────────────────────────────────┐  │
       │  │             Mechanical Hard Quality Gates         │   │       Trias Politica Judiciary      │  │
       │  │ • Ruff Linter & Formatter (Exit 0)                │──▶│ • Codex CLI Blind Adversarial Audit │  │
       │  │ • Mypy Strict Typechecking (Exit 0)               │   │ • Mock Infiltration Detection       │  │
       │  │ • Pytest Unit & Integration (100% Pass)           │   │ • Silent Fallback Analysis          │  │
       │  │ • Mutmut Mutation Testing (>= 85% Kill Rate)      │   │ • Invariant Violation Probe         │  │
       │  │ • HMAC-SHA256 Signed `receipt.json`               │   │ • Verdict: APPROVED / QUARANTINED   │  │
       │  └───────────────────────────────────────────────────┘   └──────────────────┬──────────────────┘  │
       └─────────────────────────────────────────────────────────────────────────────┼─────────────────────┘
                                                                                     │
                                                                                     ▼
                            ┌─────────────────────────────────────────────────────────┐
                            │                 PROMOTION & GENOME INGESTION            │
                            │  • Human Sovereign reviews diff + signed receipt        │
                            │  • Merge to `main`                                      │
                            │  • Ingest structural genes & negative inhibitors to DB  │
                            └─────────────────────────────────────────────────────────┘
```

---

## 2. Directory Layout & Architecture

```
code/utilities/stc/
├── 01_PLAN_BROAD_STROKES.md          # Volume 01: Core thesis, 5 pillars, architectural decisions
├── 02_EXECUTION_DAG.md               # Volume 02: Acyclic execution DAG, node specs, rollback circuits
├── 03_LOSSLESS_SUBSYSTEM_SPECS.md    # Volume 03: Exhaustive specifications for all 6 subsystems
├── 04_DATA_CONTRACTS_AND_SCHEMAS.md  # Volume 04: Pydantic V2 schemas and PEP 544 typed protocols
├── 05_CLI_AND_INTERFACE_SPEC.md      # Volume 05: Click + Rich CLI commands and headless JSON API
├── 06_VERIFICATION_AND_TEST_HARNESS.md # Volume 06: Zero-mock test suites and mutation testing
├── 07_ROLLOUT_FLIGHT_PLAN.md         # Volume 07: 6-stage physical implementation playbook
├── ARCHITECTURE.md                   # This document
├── README.md                         # Quickstart, installation, and operator manual
├── pyproject.toml                    # Dependencies, tool configs (ruff, mypy, pytest, mutmut)
├── Makefile                          # UNIX / WSL developer task runner
├── run.ps1                           # Windows PowerShell automation helper
├── src/stc/                          # Core Python package
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                        # Click CLI entrypoint
│   ├── core/                         # Configuration, logging, errors
│   │   ├── config.py
│   │   ├── errors.py
│   │   └── logging.py
│   ├── protocols/                    # PEP 544 abstract typing membranes
│   │   ├── __init__.py
│   │   └── interfaces.py
│   ├── schemas/                      # Pydantic V2 immutable data contracts
│   │   ├── __init__.py
│   │   └── models.py
│   ├── socratic/                     # Pillar 1: Socratic decomposition & archetype diffs
│   │   ├── __init__.py
│   │   ├── decomposer.py
│   │   └── ambiguity.py
│   ├── compiler/                     # Pillar 2: Context compiler & memory bundler
│   │   ├── __init__.py
│   │   └── bundler.py
│   ├── memory/                       # Hippocampus & Trace DB interface
│   │   ├── __init__.py
│   │   └── trace_client.py
│   ├── worktree/                     # Pillar 3: Morphogenetic leased worktree manager
│   │   ├── __init__.py
│   │   └── manager.py
│   ├── substrate/                    # Pillar 4: Substrate quality gates & receipts
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   └── receipt.py
│   ├── judiciary/                    # Pillar 5: Trias Politica blind audit engine
│   │   ├── __init__.py
│   │   └── auditor.py
│   ├── genome/                       # Genetic code bank & Trace atom store
│   │   ├── __init__.py
│   │   └── store.py
│   └── orchestrator/                 # Master DAG pipeline orchestrator
│       ├── __init__.py
│       └── engine.py
└── tests/                            # Automated test suite
    ├── conftest.py
    ├── unit/
    └── integration/
```

---

## 3. Subsystem Interaction Matrix

| Subsystem | Upstream Input | Downstream Output | Enforced Contract |
| :--- | :--- | :--- | :--- |
| **`stc.socratic`** | Raw Markdown / Text | `TreeOfConcerns`, `ArchetypeDiff` | Validated 5-tuple, $\Delta\text{entropy} < \tau$ |
| **`stc.compiler`** | Invariants, Schemas, Trace Atoms | `task_bundle.yaml` | **Size $\le 25,600$ Bytes**, valid YAML |
| **`stc.worktree`** | `task_id`, branch name | Leased isolated directory | Clean Git status, 1-hour TTL |
| **`stc.substrate`**| Worktree directory | `receipt.json` | Exit code 0 on all gates, HMAC signature |
| **`stc.judiciary`**| Git diff, `task_bundle.yaml` | `JudiciaryVerdict` | Zero mock infiltration, zero silent fallbacks |
| **`stc.genome`**   | Verified commit, receipt | Trace DB Genome Atom | Ingested into SQLite table with SHA256 index |
