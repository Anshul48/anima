# ANIMA Architectural Decisions & Open Questions

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

**Document Status**: Proposed Decisions Record  
**Date**: 2026-10-10  
**Final Proposal Home**: `ANIMA/architecture/proposals/2026-10-10-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE/`  
**Review Status**: Documentary integration and independent review complete; architecture acceptance and separate execution authorization remain pending. Review record (historical record `../../../coordination/2026-10-10-documentary-completion/FINAL-REVIEW.md`, excluded from this public release).

---

## 1. User and documentary commitments

The accepted scope is documentary completion. Architectural mechanisms below remain proposed.

| Commitment | Source and scope |
|---|---|
| Software construction is the immediate assistant target; research/experiment/artifact work is also a goal | Exact user answer (historical record `../../../context/integrations/2026-10-10/preserved/chats/personal-assistant.READABLE.md#personal-assistant-L166`, excluded from this public release), read with the preserved question/options |
| Preserve context, complete planning stages and deliver informing notes to related owners | Current user instruction (historical record `../../../context/integrations/2026-10-10/preserved/chats/current-coordinator.READABLE.md#current-coordinator-L286`, excluded from this public release); current authority (historical record `../../../coordination/2026-10-10-documentary-completion/AUTHORIZATION.md`, excluded from this public release) |
| Keep project ownership, scoped evidence and separate execution authority | Current documentary instruction and owner-published records; no runtime host, new global policy or release pin is adopted by this packet |

Nested worlds, participant development, retained competence and physical construction remain ambitions to accommodate and investigate. The minimal floor, progressive reuse ladder, contested active-memory policy and fusion custody mechanism are recommendations, not ratified user requirements. Their rationale is in [the personal-assistant analysis](../../notes/2026-10-09-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE.md) and the developmental reading room. Current direction does not adopt the supplied model's assurance thresholds or a mandatory whole-substrate host.

---

## 2. Proposed Architectural Choices

These choices are recommended by the architect and submitted for integration:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   PROPOSED ARCHITECTURAL CHOICES                                       │
├─────────┬──────────────────────────────────┬───────────────────────────────────────────────────────────┤
│ Choice  │ Description                      │ Rationale & Tradeoff Analysis                             │
├─────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────┤
│ P-01    │ Minimal Shared Floor             │ Decouples the personal assistant from full substrate      │
│         │ Architecture                     │ completion, delivering immediate software value while     │
│         │                                  │ preserving an open-ended runway for developmental growth. │
├─────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────┤
│ P-02    │ STC-Lite as Assurance Profile    │ Avoids a separate STC code fork; provides fast task-commit│
│         │                                  │ binding while preserving full mutation gate upgrades.     │
├─────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────┤
│ P-03    │ Epistemic Repertoire Learning    │ Repertoire learning modifies executable tool scripts, AST │
│         │ (Code & Metadata, No Weights)    │ rules, and selection priors—achieving developmental       │
│         │                                  │ adaptation using existing frozen foundation models.       │
├─────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────┤
│ P-04    │ Multi-Tier Memory with           │ Combines hot (measured hot-context budget), warm SQLite journals, and cold      │
│         │ Lightweight Provenance Pointers  │ content-addressed blob archives to prevent prompt bloat.  │
└─────────┴──────────────────────────────────┴───────────────────────────────────────────────────────────┘
```

---

## 3. Provisional Replaceable Mechanisms

The programme coordinator is authorized to replace or refine these provisional mechanisms within the accepted baseline:

1. **Storage Backend for Warm Repertoire**: Initial implementation uses SQLite with Write-Ahead Logging (WAL); coordinator may substitute DuckDB or JSONL files if workload profile justifies.
2. **Semantic Similarity Scoring**: Initial tool selector uses hybrid BM25 + embedding cosine similarity; coordinator may adjust vector index parameters or rerankers.
3. **AST Transformation Syntax**: Initial Python AST manipulation uses Python's standard `ast` and `libcst`; coordinator may swap or extend transformation libraries.

---

## 4. Routine Implementation Choices (Owned by Coordinator)

The following routine execution details are fully delegated to the programme coordinator:
- Subprocess execution flags and timeout limits.
- Temporary scratch directory naming conventions (`/tmp/anima_sandbox_<uuid>/`).
- Internal logger formatting, trace levels, and telemetry retention intervals.
- Specific compiler and linter invocation flags across supported language toolchains.

---

## 5. Consequential Unresolved Decisions (Requiring Human Sovereign Input)

The following three consequential decisions require human sovereign steering. Concise recommendations, concrete alternatives, and downstream consequences are presented below:

### Decision 1: Host Runtime Environment for First Realization
- **Context**: The first realization requires sandboxed subprocess execution and file system isolation. The user operates in a Windows native environment (`agy`) with WSL Linux mirrors available.
- **Alternatives**:
  1. *Option A (Recommended)*: **Native Windows Subprocess Sandbox** (`agy` native). Uses native Windows processes with temporary directory isolation, environment scrubbing, and explicit path sandboxing.
     - *Consequence*: Zero cross-OS latency, full compatibility with current workspace tools, but relies on process-level isolation rather than Linux cgroups.
  2. *Option B*: **WSL Linux Execution Environment**. Executes sandboxed tools inside WSL Ubuntu.
     - *Consequence*: Stronger container isolation, but introduces Windows/Linux path translation overhead and migration dependencies.
  3. *Option C*: **Docker / OCI Container Sandbox**.
     - *Consequence*: Maximum isolation, but heavy startup latency (~1-3s per tool call) and Docker daemon dependency.
- **Architect Recommendation**: **Option A (Native Windows Sandbox)** for the first slice, with Option B available as a qualified provider if Linux-only tools are demanded.

### Decision 2: State Custody Migration Protocol during Composite Fusion
- **Context**: When two participants fuse into a persistent composite, custody of their internal state must be unified without risking data loss.
- **Alternatives**:
  1. *Option A (Recommended)*: **Staged Two-Phase Pointer Swap**. The composite creates a unified state journal, writes a staged snapshot, validates data integrity, and atomically swaps state custody pointers.
     - *Consequence*: Fully transactional, fail-closed, recoverable via WAL, modest memory overhead during migration.
  2. *Option B*: **Shared Distributed Blackboard**. Participants retain separate storage and communicate over an in-memory shared bus.
     - *Consequence*: Simple to implement, but vulnerable to synchronization drift and partial crash corruption.
- **Architect Recommendation**: **Option A (Two-Phase Pointer Swap)** to guarantee strict state consistency and crash recovery.

### Decision 3: Contested Memory Reclamation & Pruning Policy
- **Context**: Active graph memory is strictly contested. A policy must decide when an unused tool or relationship record is pruned to cold storage.
- **Alternatives**:
  1. *Option A (Recommended)*: **Adaptive Utility-Cost Decay**. Tools decay in priority based on elapsed task cycles and failure count; tools with high reconstruction cost or critical recovery roles are protected from eviction.
     - *Consequence*: Highly resilient, prevents losing critical rare tools, requires tracking invocation costs.
  2. *Option B*: **Strict LRU Byte Ceiling**. Evict least recently used tools whenever active cache exceeds 50MB.
     - *Consequence*: Trivial implementation, but risks evicting rare but vital error-recovery capabilities.
- **Architect Recommendation**: **Option A (Adaptive Utility-Cost Decay)** to balance memory ceilings with capability retention.

---

## 6. Disposition of Open Issues (O-04 & O-05)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     OPEN ISSUES DISPOSITION                                            │
├─────────┬──────────────────────────────────┬───────────────────────────────────────────────────────────┤
│ Issue   │ Subject & Scope                  │ Architecture Disposition                                  │
├─────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────┤
│ O-04    │ Host Selection & Organizational  │ Resolved for 1st slice: Decoupled minimal floor on native │
│         │ Transition Semantics             │ Windows runtime; general substrate remains candidate host.│
├─────────┼──────────────────────────────────┼───────────────────────────────────────────────────────────┤
│ O-05    │ State-Transfer & Relationship    │ Resolved for 1st slice: Transactional two-phase snapshot  │
│         │ Semantics Across Boundaries      │ commit with explicit rollback journals.                   │
└─────────┴──────────────────────────────────┴───────────────────────────────────────────────────────────┘
```
