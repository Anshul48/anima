# STC: Biomimetic Spec-to-Code Autonomous Engineering Engine
## Volume 01: Master Plan in Broad Strokes

> **System:** STC (Spec-To-Code)  
> **Project Directory:** `code/utilities/stc`  
> **Target Environment:** Python 3.12+, `uv`, Git Worktrees, Project Trace, DeepSeek Harness (`dsh`), Codex CLI  
> **Status:** `[DECIDED]`  
> **Epistemic Standard:** Explicit tagging (`[DECIDED]`, `[PROPOSED]`, `[REJECTED]`, `[INVARIANT]`). Negative knowledge and disproven paths preserved verbatim.

---

## 1. Executive Summary & Foundational Thesis

### 1.1 The Problem: The Autonomous Coding Bottleneck
Autonomous agentic coding tools (Aider, OpenHands, Claude Engineer, Devin-style meta-agents) demonstrate high utility on isolated functions and leetcode-style challenges, but collapse rapidly when tasked with long-horizon, multi-subsystem engineering. This collapse is driven by three fatal pathologies diagnosed in the Biomimetic Chronicle:

1. **The Lone Genius Illusion ($O(N^2)$ Context Explosion):** Feeding a 50-page architecture document or an entire repository AST into an LLM context window saturates attention, dilutes critical system invariants, and produces hallucinatory, incompatible interfaces across modules.
2. **The Self-Certification Trap (The Conflict of Interest):** When the same LLM acts as the architect, implementer, tester, and verifier, it inevitably games its own tests—writing tautological assertions (`assert True`), mocking out real I/O, and silently introducing fallbacks (`try ... except: return []`) to mask bugs.
3. **The Architecture Astronaut Recursion (The Meta-Scaffold Trap):** Repeatedly abandoning stalled tools to build new meta-orchestrators from scratch (e.g., building `auto` to coordinate `praxist`, then building `auto-lite` to coordinate `auto`), resulting in layers of empty wrappers with 0% real execution logic.

### 1.2 The STC Solution
**STC (Spec-to-Code)** is not another generic LLM wrapper. It is a **biomimetic, distributed autonomous engineering engine** grounded in:
- **Hierarchical Compilation:** Specifications are compiled down through strict semantic layers (Spec $\to$ Tree of Concerns $\to$ Task Bundles $\to$ Leased Worktrees $\to$ Machine Receipts).
- **Dual-Store Cognitive Context:** Neocortex (immutable schemas, typing protocols, system invariants) + Hippocampus (content-addressed, append-only execution traces in Project Trace). Context is retrieved on demand ($O(1)$) in sub-25KB bundles, never accumulated ($O(N^2)$).
- **Trias Politica Governance:** Rigid separation of powers between the **Human Sovereign** (invariants & merge authority), the **Executive Workers** (Agy / Aider / DeepSeek coding in isolated worktrees), the **Substrate** (deterministic test execution and receipt generation), and the **Judiciary** (blind, adversarial Codex audits).
- **Genetic Code Bank:** Completed, verified implementations and disproven negative dead ends are cataloged into Project Trace as an evolving genetic repository for future software syntheses.

---

## 2. The 5 Core Pillars of STC

```
                                  [ HUMAN INTENT / SPECIFICATION ]
                                                 │
                                                 ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────┐
   │ PILLAR 1: SOCRATIC ELICITATION & ARCHETYPE DIFFING                                        │
   │ Decomposes natural language specs into a Tree of Concerns (TOC). Resolves ambiguities      │
   │ via structured 2-choice archetype diffs rather than exhausting the human with open queries.│
   └─────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                                 ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────┐
   │ PILLAR 2: CONTEXT COMPILER & HIPPOCAMPAL RETRIEVAL                                        │
   │ Queries Neocortex (immutable schemas/invariants) and Hippocampus (Project Trace traces) to │
   │ synthesize atomic, self-contained, sub-25KB task bundles. Zero prompt stuffing.            │
   └─────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                                 ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────┐
   │ PILLAR 3: CELLULAR MORPHOGENESIS & LEASED WORKTREES                                       │
   │ Spawns ephemeral Git worktrees for executive worker agents. Subsystems negotiate via rigid│
   │ PEP 544 typed membranes; upstream domain contracts dictate to downstream adapters.       │
   └─────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                                 ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────┐
   │ PILLAR 4: SUBSTRATE HARD GATES & CRYPTOGRAPHIC RECEIPTS                                   │
   │ Deterministic, non-mocked execution: `pytest` 100%, `mypy --strict` 0 errors, `ruff` 0    │
   │ warnings, mutation score thresholds. Emits signed, tamper-evident `receipt.json`.         │
   └─────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                                 ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────────┐
   │ PILLAR 5: TRIAS POLITICA JUDICIARY & PROMOTION                                            │
   │ Headless, blind adversarial audit by Codex CLI in a clean worktree. The Human Sovereign   │
   │ retains exclusive merge authority to `main`. Verified genes persist to Trace DB.          │
   └───────────────────────────────────────────────────────────────────────────────────────────┘
```

### Pillar 1: Socratic Elicitation & Archetype Diffing `[DECIDED]`
- **Hierarchical Tree of Concerns (TOC):** Dissects monolithic specifications into 5 standard dimensions:
  1. *Domain Invariants & Business Logic*
  2. *Data Persistence & Storage Contracts*
  3. *Communication Protocols & Boundaries*
  4. *Security, Redaction & Auth*
  5. *Failure Modes, Retries & Circuit Breakers*
- **Archetype Diffing:** Avoids the "Oracle Paradox" (where agents ask questions the human does not know how to answer). Instead, the engine generates two contrasting, complete architectural archetypes (e.g., Option A: Fail-closed strict validation vs. Option B: Stale-while-revalidate grace window) with tradeoffs explicitly mapped. The human chooses in seconds.

### Pillar 2: Context Compiler & Hippocampal Retrieval `[DECIDED]`
- **Sub-25KB Task Bundles:** The LLM coding agent is never exposed to the whole codebase. It receives a hyper-focused, content-addressed `task_bundle.yaml` containing:
  - Exact file targets and line ranges.
  - Upstream interface protocols (`protocols.py`) and schemas (`schemas.py`).
  - Strict acceptance criteria and invariant constraints.
  - Negative lessons learned from previous failed attempts (inhibitors).
- **Dual-Trace Hippocampus:** Semantic summaries in ADRs are always linked by content hash (SHA256) to raw byte diffs and compiler traces in Project Trace to avoid lossy summarization collapse.

### Pillar 3: Cellular Morphogenesis & Leased Git Worktrees `[DECIDED]`
- **Asymmetric DAG of Authority:** Upstream domain contracts govern downstream adapters. Components communicate strictly across typed membranes (`typing.Protocol`). Circular negotiations between agents are strictly prohibited.
- **Physical Worktree Leases:** Workers operate in ephemeral directories (`worktrees/stc-task-XYZ`). They have no write access to other worktrees or `main`. Leases expire automatically if tasks abort.

### Pillar 4: Substrate Hard Gates & Machine Receipts `[DECIDED]`
- **Binary Hard Gates:** No human review occurs until all mechanical gates pass:
  1. Unit & Integration test pass rate: **100%**.
  2. Static type checker: `mypy --strict` **0 errors**.
  3. Linter & style: `ruff check` and `ruff format` **0 violations**.
  4. Mutation testing: `mutmut` survives **0 undetected mutations**.
- **Cryptographic Machine Receipts:** Execution generates a tamper-evident `receipt.json` containing git commit hash, exit codes, test summaries, latency benchmarks, and receipt signature.

### Pillar 5: Trias Politica Judiciary & Genetic Memory `[DECIDED]`
- **Blind Adversarial Review:** An isolated Codex CLI instance reviews the code diff, the `task_bundle.yaml`, and the `receipt.json` without access to the worker's chat transcripts. It specifically probes for hidden mocks, silent exception swallowing, and boundary violations.
- **Genetic Ingestion:** Upon promotion by the Human Sovereign, the implementation's interfaces, test patterns, and refutation logs are indexed into the Trace Genome Database as reusable genes and negative inhibitors.

---

## 3. Scope & System Boundaries

### What STC IS:
- A deterministic, production-grade CLI and orchestration library written in Python 3.12+.
- The execution engine that transforms verified specifications into working software.
- The glue integrating `trace` (cognitive memory), `stl` (standard tooling library), `dsh` (Cordis plugin bus), and external CLI workers (`agy`, `codex`).

### What STC IS NOT:
- ❌ NOT an LLM chatbot or interactive coding UI.
- ❌ NOT a monolithic single-agent script that runs in an unbounded loop.
- ❌ NOT a mock-heavy simulation (like `praxist-research-lab`'s simulator or `auto-lite`'s dummy validator).

---

## 4. Architectural Decisions & Negative Knowledge

| Decision ID | Context / Question | Decision | Rationale & Negative Knowledge |
| :--- | :--- | :---: | :--- |
| **ADR-001** | Should STC write its own internal agent runner or use existing CLI workers? | **Use CLI Workers (`agy`, `codex`, `dsh`)** | Building an LLM agent from scratch takes months and duplicates existing tools. STC focuses on compilation, governance, and substrate verification. |
| **ADR-002** | How should context be passed to workers? | **Sub-25KB Task Bundles (`task_bundle.yaml`)** | Prompt stuffing leads to context rot and $O(N^2)$ hallucination. Small, bounded bundles enforce focus. |
| **ADR-003** | How are tests certified? | **Substrate Machine Receipts (`receipt.json`)** | Prose claims like "All tests pass" are untrusted hearsay. Only signed exit codes and test runner outputs count. |
| **ADR-004** | How do we handle agent questions to the user? | **Archetype Diffing (2 concrete options)** | Open-ended interrogations induce cognitive fatigue and fail when the user doesn't know the low-level answer. |
| **ADR-005** | How do we avoid Windows file-locking & CRLF bugs? | **Hermetic WSL/Container Substrate** | Windows SQLite and file locks cause intermittent test flakes. Editing is allowed on Windows NTFS, but verification runs in Linux/WSL. |
| **ADR-006** | How are subsystems decoupled? | **PEP 544 Protocols & Pydantic V2 Schemas** | Static membranes prevent circular contract oscillation between subagents. |
