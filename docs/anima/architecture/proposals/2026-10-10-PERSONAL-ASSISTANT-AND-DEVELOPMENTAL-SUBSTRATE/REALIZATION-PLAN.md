# ANIMA Realization Plan: First Bounded Slice & Qualification

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

**Document Status**: Proposed Plan Candidate  
**Date**: 2026-10-10  
**Final Proposal Home**: `ANIMA/architecture/proposals/2026-10-10-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE/`  
**Review Status**: Documentary integration and independent review complete; architecture acceptance and separate execution authorization remain pending. Review record (historical record `../../../coordination/2026-10-10-documentary-completion/FINAL-REVIEW.md`, excluded from this public release).

---

## 1. Executive Summary & First Bounded Vertical Slice

The first realization of ANIMA is a **source-grounded personal software-construction assistant** operating on real repository objectives. It incorporates research-to-experiment-to-artifact capabilities, executes under the minimal computational floor, and autonomously develops, adapts, reuses, and prunes executable capabilities using the Progressive Reuse Ladder ([ARCHITECTURE.md](ARCHITECTURE.md#6-the-progressive-reuse-ladder-generalized-3-box-principle)).

### The First Journey Milestone:
1. **Real Repository Task**: The assistant receives an authentic software objective in an authorized repository (e.g., resolving a TOCTOU race condition in CLI branch promotion).
2. **Investigation & Plan**: Unpacks requirements, checks ASTs, surfaces consequential architecture choices, and drafts an implementation plan.
3. **Execution & Checked Synthesis**: Synthesizes the fix, executes sandboxed test suites, runs mutation checks, and verifies receipt enforcement.
4. **Session Restart & Unfamiliar Change**: In a completely clean session with fresh working context, the assistant receives a related but altered task (e.g., verifying promotions on a different Python CLI with altered schema).
5. **Demonstrated Adaptation & Transfer**: Recovers relevant past experience, retrieves or adapts the retained verification tool, completes the task with lower token/time cost, and passes independent verification without human tool-management intervention.

---

## 2. Caller needs and owner contract candidates

These are consumer needs to discuss, not published APIs, selected release versions or implementation orders for neighboring projects. Producer owners publish and qualify their own artifacts; the assistant later chooses an exact available artifact and qualifies its caller. No STC-Lite v1.1, substrate-floor v0.2 or TL/TRACE v1.0 release is established by this packet.

### 2.1 Software-construction boundary

Use the [STC DSH record](../../../../../components/stc/docs/STC-DSH-RECORD.md), [published release envelope](../../../../../components/stc/docs/STC-DSH-RELEASE.md) and [STC/SST caller contract](../../../../../components/stc/docs/STC-SST-CALLER-CONTRACT.md) as observed owner records. Ask for the smallest supported task/artifact/check/verdict and interruption interface. Needed caller information includes accepted constraints, task and candidate identity, artifact custody, check evidence, effect uncertainty and explicit continuation. Current recovery may involve full replay and repeated effects; do not substitute resume-by-skip or automatic idempotence. Signed receipts, a Lite assurance profile and upgrade gates from pasted commentary are optional design candidates, not current STC guarantees or imposed mutation thresholds. If no current STC release fits, use already available tools for the bounded initial request and retain STC integration as a scoped dependency.

### 2.2 Assistant-local durable foundation

Recommend a small obligation/progress/capability journal, explicit process boundaries, versioned state/message records and resumable checkpoints. SQLite WAL or atomic files are replaceable local storage candidates, not an owner-qualified substrate release. Atomic journal changes can protect local state; they cannot roll back arbitrary outside effects. Preserve unknown effect outcomes, idempotency limits and authorized reconciliation. Fusion/state transfer needs an explicit fencing/checkpoint protocol and compatible state migration, not an assumed automatic cross-project two-phase commit. The independently useful broad substrate remains an optional host experiment; the assistant need not wait for its next release.

### 2.3 Optional evidence and retrieval participants

TL organizes/retrieves attributable evidence; TRACE owns its higher-level meaning/context responsibilities. Start from the owner-published TL export candidate (historical record `../../../../trace-architecture/handoffs/TL-EXPORT-CONTRACT-0.2.md`, excluded from this public release) and TRACE release record (historical record `../../../../trace-architecture/handoffs/TRACE-RELEASE2-2026-10-05.md`, excluded from this public release). These records are discussion inputs, not an adopted consumer pin. Caller needs are source identity, supported locators/offsets, freshness/version, uncertainty/failure behavior, costs and actual return semantics. Do not impose Markdown line anchors, shared cold-store mechanics or a combined universal TL/TRACE API. Each optional capability integrates only when its actual owner-qualified artifact and caller fit are established.

---

## 3. Matched Baseline Comparison & Anti-Leakage Protocols

To rigorously evaluate whether developmental learning provides genuine capability advancement rather than ordinary prompt-engineering or model memorization, the first slice enforces a **strict matched-baseline protocol**.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                      EXPERIMENTAL CONDITIONS                              │
├───────────────────┬───────────────────────────────────────────────────────┤
│ Condition         │ Configuration & Capabilities                          │
├───────────────────┼───────────────────────────────────────────────────────┤
│ 1. Capable        │ • Identical LLM (same model, temperature, context).   │
│    Baseline       │ • Full access to filesystem, Bash/Python tools.       │
│    (Simpler)      │ • Persistent flat notes (MEMORY.md / scratchpad).     │
│                   │ • Allowed to write ad-hoc scripts in-session.         │
│                   │ • May invent/reuse procedures and selectors as useful.    │
├───────────────────┼───────────────────────────────────────────────────────┤
│ 2. ANIMA          │ • Identical LLM, base tools, and compute budget.      │
│    Developmental  │ • Structured Capability Repertoire & Lineage Store.   │
│    Assistant      │ • Progressive Reuse Ladder (3-Box rule).              │
│                   │ • Autonomous selection policy & memory reclamation.   │
└───────────────────┴───────────────────────────────────────────────────────┘
```

The baseline receives the same authorized memory, published capabilities, task information and acquisition/maintenance budget, and may retain useful scripts, procedures or a selector if its own work produces them. A weaker no-repertoire condition may be a separately labeled ablation, never the decisive baseline. Freeze and carry each condition's permitted acquired state into held-out evaluation; clear answer-bearing task context equally. If simpler organization reaches the same capability at lower total cost, reject the added machinery.

### 3.1 Accounting for Full Operational Costs
Comparisons must account for the complete cost envelope, not just steady-state inference:
Record API/token usage, actual monetary charge when available, elapsed/compute time, storage and human attention separately, including acquisition and maintenance. Compare the resource/capability tradeoff; use a scalar score only with explicitly declared, justified units and weights. Do not add raw token counts to seconds.

A capability that saves 500 inference tokens but costs 50,000 tokens in background consolidation or causes catalog retrieval failures scores as a net loss.

### 3.2 Acquisition vs. Evaluation Split & Anti-Leakage
1. **Disjoint Task Sets**:
   - *Acquisition Set ($D_{\text{train}}$)*: 5 real repository tasks used to discover and refine tools (e.g., Python CLI parser fixes, lint wrappers).
   - *Evaluation Set ($D_{\text{test}}$)*: 5 held-out, structurally altered tasks (e.g., Rust AST mutation audit, altered JSON schemas) never seen during acquisition.
2. **Context Isolation**: Evaluation tasks execute in fresh subprocesses with clean working memory, preventing prompt contamination or leaked test assertions.

---

## 4. Valid Changed Conditions & Failure Injection

The owner negative result in substrate alpha (`HOST-VALUE-NOT-DEMONSTRATED`, [ROADMAP.md](../../../../../components/substrate/docs/ROADMAP.md)) occurred because the held-out changed-condition test was degenerate, leaving adaptation unexercised. This realization plan specifies non-degenerate changed conditions.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                      VALID CHANGED CONDITIONS                             │
├───────────────────┬───────────────────────────────┬───────────────────────┤
│ Changed Condition │ Nature of Environmental Break │ Expected Adaptation   │
├───────────────────┼───────────────────────────────┼───────────────────────┤
│ 1. Schema Drift   │ JSON error output format      │ Adapter patches       │
│                   │ changes from flat to nested.  │ parsing logic; does   │
│                   │                               │ not rewrite builder.  │
├───────────────────┼───────────────────────────────┼───────────────────────┤
│ 2. Toolchain      │ Repository switches from      │ Repertoire selects    │
│    Migration      │ Python `unittest` to `pytest`.│ or constructs pytest  │
│                   │                               │ runner wrapper.       │
├───────────────────┼───────────────────────────────┼───────────────────────┤
│ 3. Dependency     │ Library upgrade breaks CLI    │ Assistant detects     │
│    Incompatibility│ flags in helper script.       │ syntax break, adapts  │
│                   │                               │ invocation signature. │
└───────────────────┴───────────────────────────────┴───────────────────────┘
```

### 4.1 Failure Injection & Rollback Testing
- **Injected Tool Crash**: Introduce a synthetic segfault / exception in an adapted tool during execution. The system must catch the error, roll back the transaction, fall back to step-by-step interpretation, and log an empirical failure episode in the capability ledger.
- **Interrupted Workflow Recovery**: Terminate the assistant process mid-transformation (`SIGKILL`). On reboot, the assistant must read the SQLite WAL journal, identify the uncommitted transaction, clean orphaned temp files, and resume execution without human intervention.

---

## 5. Staged Qualification & Independent Verification

Progress follows a strict 5-stage qualification pipeline:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                       QUALIFICATION PIPELINE                              │
│                                                                           │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐             │
│  │ Stage 1:     │─────►│ Stage 2:     │─────►│ Stage 3:     │             │
│  │ Component    │      │ Integrated   │      │ Qualification│             │
│  │ Unit Checks  │      │ Operation    │      │ Test Suite   │             │
│  └──────────────┘      └──────────────┘      └──────┬───────┘             │
│                                                     │                     │
│                        ┌──────────────┐             │                     │
│                        │ Stage 5:     │◄────────────┘                     │
│                        │ Sovereign    │      ┌──────────────┐             │
│                        │ Promotion    │◄─────│ Stage 4:     │             │
│                        │ (User Gate)  │      │ Independent  │             │
│                        └──────────────┘      │ Verification │             │
│                                              └──────────────┘             │
└───────────────────────────────────────────────────────────────────────────┘
```

1. **Stage 1: Component Unit Checks**: Individual modules (`stc`, `substrate-floor`, `repertoire-store`) pass 100% of unit tests in isolation.
2. **Stage 2: Integrated Operation**: Assistant executes end-to-end software construction on sample repository.
3. **Stage 3: Qualification Test Suite**: System executes the 5 acquisition tasks and 5 held-out evaluation tasks under timed conditions.
4. **Stage 4: Independent Verification**: An independent verification agent (withheld builder justifications) inspects execution receipts, reproduces test runs, and audits commit hashes.
5. **Stage 5: Sovereign Promotion**: Human sovereign reviews the verification dossier and authorizes promotion into accepted baseline.

---

## 6. Dependency Sequencing & Producer Freedom

To prevent project gridlock, independent producers develop without waiting for cross-project synchronization:

```
Timeline / Sequence
─────────────────────────────────────────────────────────────────────────────
[STC Track]          ──► Select owner-qualified STC capability if usable ──────────────┐
                                                                         ▼
[Substrate Track]    ──► Optional host; assistant-local journal first ──► [Assistant Integration]
                                                                         ▲
[ANIMA Core]         ──► Author Repertoire & Selection Engine ───────────┘
                                                                         │
                                                                         ▼
                                                          [Execute 1st Slice Benchmark]
```

- **Zero Mutable Pins**: Dependencies bind strictly to released commit SHA-256 snapshots, never mutable branch HEADs.
- **Unblocked Development**: STC and Substrate teams remain completely free to evolve internal algorithms as long as candidate contracts remain satisfied.

---

## 7. Parallel Hardware & Biomimetic Entry Path

While software construction is the immediate priority, the architecture preserves an active, parallel entry path for physical construction and biomimetic actuation ([VECTOR-04](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-04-PHYSICAL-CONSTRUCTION.md)):

```
┌───────────────────────────────────────────────────────────────────────────┐
│                      PARALLEL HARDWARE ENTRY PATH                         │
│                                                                           │
│  ┌───────────────────────────────┐     ┌───────────────────────────────┐  │
│  │ Software Construction Track   │     │ Physical Construction Track   │  │
│  │ (Immediate Priority)          │     │ (Parallel Research Track)     │  │
│  │ • Code Generation & Testing   │     │ • Motor-Driven Bench Testing  │  │
│  │ • AST Mutation & Repair       │     │ • Sensor Calibration Telemetry│  │
│  │ • Software Repertoire Growth  │     │ • Thermal / Torque Drift Model│  │
│  └───────────────────────────────┘     └───────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

- **Pragmatic Bridge**: Initial hardware experiments utilize low-cost motor-driven actuator testbeds to evaluate real-time sensor calibration, latency compensation, and physical safety tripwires.
- **Preservation of Long-Term Ambitions**: Motor-based prototyping is explicitly treated as a pragmatic testing bridge; it does not replace or diminish the long-term goal of biomimetic, multi-material physical actuation.
