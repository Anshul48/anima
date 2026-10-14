# ANIMA Macro-Architecture: Personal Assistant & Developmental Substrate

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

**Document Status**: Proposed Architecture Candidate  
**Date**: 2026-10-10  
**Final Proposal Home**: `ANIMA/architecture/proposals/2026-10-10-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE/`  
**Review Status**: Documentary integration and independent review complete; architecture acceptance and separate execution authorization remain pending. Review record (historical record `../../../coordination/2026-10-10-documentary-completion/FINAL-REVIEW.md`, excluded from this public release).

---

## 1. Architectural Ambitions & Foundational Model

### 1.1 The Core Ambition
The overarching goal of the ANIMA architecture is to establish an open-ended **developmental computational environment** in which useful organization, capabilities, and cooperative relationships can autonomously emerge, persist, compose, adapt, and transfer across generations ([SYNTHESIS.md](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/SYNTHESIS.md), [VECTOR-01](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-01-DEVELOPMENTAL-CHANGE.md)). 

This goes fundamentally beyond static agent frameworks, fixed tool-use loops, or hardcoded orchestrators:
- **Plastic Boundaries & Co-Adaptation**: Computational entities do not simply call fixed APIs; they negotiate protocols, adapt representation mappings, and refine mutual cooperation based on empirical interaction evidence ([VECTOR-06](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-06-CONSTRUCTION-REPERTOIRES.md)).
- **Organizational Transitions**: Recurring ad-hoc coalitions can consolidate shared state and fuse into persistent composites, undergo internal specialization, or split (fission) when coordination bottlenecks or conflicting obligations arise ([VECTOR-03](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-03-EXPERT-INDIVIDUALITY.md), [VECTOR-07](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-07-PROGRAMME-SEARCH.md)).
- **Inheritance of Competence**: Descendant systems inherit not merely static snapshots of code, but verified developmental repertoires, construction recipes, and selection policies that enable rapid adaptation to unfamiliar environments ([VECTOR-08](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-08-RETENTION-AND-DESCENDANTS.md)).

### 1.2 The First Demanding Application: Personal Software-Construction Assistant
Following explicit human sovereign direction (D-022 (historical record `../../../context/integrations/2026-10-10/preserved/documents/anima/context/DECISIONS-AND-CORRECTIONS.jsonl`, excluded from this public release), personal-assistant.READABLE.md#personal-assistant-L166 (historical record `../../../context/integrations/2026-10-10/preserved/chats/personal-assistant.READABLE.md#personal-assistant-L166`, excluded from this public release)), the primary vertical target is a **personal software-construction assistant** with research-to-experiment-to-artifact capabilities integrated alongside. 

Software construction is selected because:
1. It possesses rigorous, automated, and objective feedback loops (syntax, type-checkers, compilers, test suites, mutation tests, linter invariants).
2. A design risk is an expanding, poorly assessed tool repertoire. The [personal-assistant analysis](../../notes/2026-10-09-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE.md) proposes graduated reuse, adaptation and construction as a response; its local benefit and retirement policy still require evidence.
3. It provides a demanding crucible for testing whether retained experience, learned skills, and organizational changes deliver measurable advantage on held-out, unfamiliar tasks.

### 1.3 Strict Separation of Architectural Primitives
A primary design vulnerability identified in earlier ecosystem drafts was the conflation of naming, runtime containment, and authority. This architecture enforces strict orthogonal separation across eight fundamental primitives:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                       ORTHOGONAL PRIMITIVES                               │
├───────────────────┬───────────────────────────────────────────────────────┤
│ Primitive         │ Definition & Scope                                    │
├───────────────────┼───────────────────────────────────────────────────────┤
│ 1. Identity       │ Content-addressed, cryptographic ID (UUID / SHA-256). │
│                   │ Stable across restarts; distinct from display labels. │
├───────────────────┼───────────────────────────────────────────────────────┤
│ 2. State Custody  │ The exact component or storage engine holding the     │
│                   │ canonical mutable bytes; controls transaction commits.│
├───────────────────┼───────────────────────────────────────────────────────┤
│ 3. Containment    │ Structural lifecycle boundary (parent/child nesting). │
│                   │ Determines process lifecycle, crash isolation domains.│
├───────────────────┼───────────────────────────────────────────────────────┤
│ 4. Ownership      │ Legal/governance entity holding deletion and mutation │
│                   │ rights over assets, source trees, and records.        │
├───────────────────┼───────────────────────────────────────────────────────┤
│ 5. Collaboration  │ Ephemeral or durable communication topology; message  │
│                   │ channels connecting participants across boundaries.   │
├───────────────────┼───────────────────────────────────────────────────────┤
│ 6. Authority      │ Explicit cryptographic / capability tokens defining   │
│                   │ permitted actions, spend limits, and promotion rights.│
├───────────────────┼───────────────────────────────────────────────────────┤
│ 7. Resources      │ Controllable budgets: token limits, execution time,   │
│                   │ memory allocation, disk space, and active graph space.│
├───────────────────┼───────────────────────────────────────────────────────┤
│ 8. Execution Host │ Concrete physical or virtual runtime environment      │
│                   │ (Windows AGY, Linux subprocess, container, sandbox).  │
└───────────────────┴───────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Discovery vs. Authority**: A catalogue entry or namespaced path in `ANIMA/catalogue/MODULES.json` provides *discovery only*. It grants zero execution authority, implies no runtime containment, and does not establish inter-module compatibility. Authority is conferred strictly through explicit, signed capability grants and consumer qualification.

---

## 2. The Smallest Stable Computational Floor

To prevent fragile framework churn and decouple the assistant from long-term substrate experimentation, the architecture establishes a **minimal shared computational floor**. The floor enforces versioned communication, state persistence, lifecycle management, and resource confinement while leaving domain logic entirely within participating worlds.

```
                  ┌─────────────────────────────────────────┐
                  │        HUMAN SOVEREIGN (User)           │
                  │   Direction, Constraints, Promotion     │
                  └────────────────────┬────────────────────┘
                                       │ Directives / Approvals
                                       ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                    ANIMA PERSONAL ASSISTANT WORLD                         │
│  ┌────────────────────────┐                   ┌────────────────────────┐  │
│  │   Assistant Core       │                   │   Repertoire Manager   │  │
│  │   (Investigate, Plan,  │◄─────────────────►│   (Retrieve, Evaluate, │  │
│  │    Steer, Recover)     │                   │    Adapt, Construct)   │  │
│  └───────────┬────────────┘                   └───────────┬────────────┘  │
│              │                                            │               │
│              ▼                                            ▼               │
│  ┌────────────────────────┐                   ┌────────────────────────┐  │
│  │  STC Construction World│                   │  Learned Capabilities  │  │
│  │  (Build, Mutate, Check)│                   │  & Procedures Store    │  │
│  └────────────────────────┘                   └────────────────────────┘  │
├───────────────────────────────────────────────────────────────────────────┤
│                    MINIMAL COMPUTATIONAL FLOOR                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────────────┐  │
│  │ Identity & State│  │ Versioned Msg   │  │ Sandboxed Capability      │  │
│  │ Persistence     │  │ & Event Ledger  │  │ Execution Confinement     │  │
│  └─────────────────┘  └─────────────────┘  └───────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Core Floor Data Structures & Protocols

#### A. Participant / World Descriptor
```json
{
  "$schema": "https://anima.org/schemas/v1/participant-descriptor.json",
  "participant_id": "world_pa_core_01a1",
  "schema_version": "1.0.0",
  "owner_authority": "auth_sovereign_user",
  "containment_parent": null,
  "state_custody_engine": "sqlite_wal_journal",
  "active_status": "ACTIVE",
  "resource_envelope": {
    "max_wall_time_sec": 3600,
    "token_budget_per_cycle": 100000,
    "max_active_graph_bytes": 52428800
  },
  "capabilities_exported": [
    "cap_investigate_software_objective",
    "cap_execute_construction_plan"
  ],
  "dependencies_declared": [
    {"module": "stc", "contract_version": "^1.0.0", "profile": "lite"}
  ]
}
```

#### B. Capability & Repertoire Record
```json
{
  "capability_id": "cap_rust_mutation_audit_v2",
  "version": "2.1.0",
  "desired_effect": "Perform mutmut/cargo-mutants mutation testing on Rust submodules and generate kill-rate dossier",
  "applicability_conditions": {
    "languages": ["rust"],
    "manifest_required": ["Cargo.toml"],
    "minimum_test_pass_rate": 1.0,
    "max_workspace_files": 2000
  },
  "executable_artifact": {
    "artifact_type": "python_script",
    "content_sha256": "8f3b2a...e4",
    "entrypoint": "mutant_runner.py::run_audit",
    "confinement_profile": "read_src_write_tmp_sandboxed"
  },
  "lineage": {
    "constructed_by": "world_pa_core_01a1",
    "derived_from": "cap_rust_mutation_audit_v1",
    "construction_recipe_id": "rec_ast_mutation_wrapper_04"
  },
  "empirical_performance": {
    "invocations_count": 14,
    "success_count": 13,
    "failure_count": 1,
    "mean_execution_sec": 42.4,
    "last_assessed_at": "2026-10-09T18:40:00Z"
  }
}
```

#### C. Versioned Message Envelope
```json
{
  "message_id": "msg_01a109bf_8472",
  "schema_version": "1.1.0",
  "causation_id": "msg_01a109be_1102",
  "correlation_id": "task_stc_fix_parser_toctou",
  "sender_id": "world_pa_core_01a1",
  "recipient_id": "world_stc_builder_worker",
  "authority_token": "token_scoped_exec_stc_20261010",
  "timestamp": "2026-10-10T12:00:00.104Z",
  "payload_type": "EXECUTE_CHECKED_TRANSFORMATION",
  "payload_body": {
    "target_repo_path": "/workspace/target_project",
    "target_commit": "b8f9ccb5a4d04360db5a5b39dd2d12da3665501b",
    "transformation_plan_ref": "art_plan_ast_fix_01"
  }
}
```

### 2.2 Execution Confinement & Sandbox Guarantee
Earlier substrate evaluations suffered from caller-trusted procedure execution, relying on purely contractual filesystem restrictions ([CONSUMER.md](../../../../../components/substrate/docs/CONSUMER.md)). 

The computational floor enforces **structural containment**:
1. **Subprocess Confinement**: Executable tools, generated scripts, and candidate procedures run in isolated worker subprocesses with explicit environment scrubbing, read-only mounts for source references, and isolated staging directories for write outputs.
2. **Fail-Closed Gate Checks**: Any procedure attempting undeclared network access, unauthorized workspace overwrites, or out-of-boundary process execution is terminated immediately and logged as a security failure episode.

---

## 3. Plastic Boundaries & Relationship Models

In ANIMA, relationships between entities are first-class, stateful, and plastic ([VECTOR-01](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-01-DEVELOPMENTAL-CHANGE.md), [VECTOR-06](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-06-CONSTRUCTION-REPERTOIRES.md)).

```
┌───────────────────────────────────────────────────────────────────────────┐
│                           RELATIONSHIP STATE                              │
│                                                                           │
│  ┌───────────────────────┐                     ┌───────────────────────┐  │
│  │   Participant A       │◄═══════════════════►│   Participant B       │  │
│  └───────────────────────┘                     └───────────────────────┘  │
│             │                                               │             │
│             ▼                                               ▼             │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ Relationship Record (Rel-ID)                                        │  │
│  │ • Participants: [A, B]                                              │  │
│  │ • Protocol & Schema Mapping: Versioned translation table            │  │
│  │ • Permeability / Routing: Permitted message classes                 │  │
│  │ • Shared State Cache: Synchronized task blackboard / cache          │  │
│  │ • Evidence Ledger: History of latency, errors, schema mismatches   │  │
│  │ • Mutual Adaptation Policy: Allowed parameter & mapping revisions   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Relationship Plasticity Mechanics
A relationship can dynamically modify:
1. **Permeability & Filtering**: Widening or throttling specific event notifications based on relevance feedback.
2. **Representation Translation**: Adapting schema mismatches (e.g., converting AST node structures or error classifications) without requiring source modifications in either participant.
3. **Delegated Responsibility**: Shifting routine sub-tasks (such as initial lint verification) from the caller to the callee based on proven execution reliability.
4. **Consolidated Shared State**: Merging redundant local caches into a shared, synchronised relationship blackboard.

### 3.2 Epistemic Learning Loop (Without Weight Updates)
Developmental change in ANIMA does not require training deep model weights. Instead, learning operates over **executable artifacts, structured policies, and verified selection mappings**:

```
 ┌────────────────┐       ┌─────────────────┐       ┌─────────────────┐
 │ Interaction    │──────►│ Empirical       │──────►│ Repertoire      │
 │ Evidence / Log │       │ Assessment      │       │ Adaptation Loop │
 └────────────────┘       └─────────────────┘       └────────┬────────┘
                                                             │
           ┌─────────────────────────────────────────────────┴────────┐
           ▼                                                          ▼
┌──────────────────────┐                                   ┌──────────────────────┐
│ Tool/Procedure       │                                   │ Selection / Routing  │
│ Adaptation           │                                   │ Policy Revision      │
│ (Refactor script,    │                                   │ (Update applicability│
│  fix edge conditions)│                                   │  rules, costs, priors)│
└──────────────────────┘                                   └──────────────────────┘
```

1. **Observations**: Success/failure traces, execution wall-clock time, token costs, schema errors, and human intervention logs.
2. **Permitted Actions**:
   - Update applicability metadata (narrow preconditions on failure, broaden on success).
   - Generate and test a patched procedure variant.
   - Adjust routing weights in the selection policy.
   - Flag deprecated capabilities for memory reclamation.
3. **Retained Artifacts**: Checked Python/Bash scripts, AST transformation rules, versioned JSON schemas, and calibration matrices.
4. **Behavioral Consequence**: On subsequent tasks, the selector retrieves more accurate tools, avoids known failure modes, and executes adapted procedures with lower latency and human steering overhead.

---

## 4. Developmental Transformations & Organizational Evolution

ANIMA supports four structural transformations across computational entities ([VECTOR-03](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-03-EXPERT-INDIVIDUALITY.md), [SYNTHESIS.md](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/SYNTHESIS.md)):

```
┌───────────────────────────────────────────────────────────────────────────┐
│                      ORGANIZATIONAL TRANSITIONS                           │
│                                                                           │
│ 1. Coalition Formation (Temporary)                                        │
│    [Participant A] ◄--- Ad-hoc Task Channel ---> [Participant B]          │
│                                                                           │
│ 2. Composite Fusion (Durable)                                             │
│    ┌─── Composite Entity ─────────────────────────────────────────────┐   │
│    │  [Participant A] ◄--- Internal Unified State ---► [Participant B]│   │
│    │  Exported Unified Interface: Cap_AB                              │   │
│    └───▲──────────────────────────────────────────────────────────────┘   │
│        │                                                                  │
│ 3. Structural Assimilation                                                │
│    One participant absorbs the state and routines of another;             │
│    redundant dispatch overhead is eliminated.                             │
│                                                                           │
│ 4. Fission / Dissolution (Specialization or Failure Split)                │
│    [Composite AB] ─── (Bottleneck / Conflicting Demands) ───► [A] + [B]   │
└───────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Transformation Lifecycle & Preconditions
- **Coalition Preconditions**: Matching task requirements, compatible protocol versions, verified authority grants.
- **Fusion Preconditions**: Demonstrated recurring interaction (> $N$ episodes), positive co-adaptation metrics, measured reduction in coordination overhead, zero unresolved state conflicts.
- **Dissolution Triggers**: Negative cooperation metrics, recurring deadlocks, irreconcilable schema drift, or explicit human sovereign directive.

### 4.2 State Custody Migration & Crash Recovery
When entities fuse or dissolve, state custody must remain strictly consistent:
1. **Two-Phase State Commit**: State transfer executes via a staged snapshot -> verification -> atomic pointer swap.
2. **Idempotent Rollback**: If an interruption occurs during fusion/fission, the system rolls back to the pre-transition state journal without data corruption.
3. **No Phantom Authorities**: Authority tokens bound to pre-fusion entities are revoked and reissued to the composite under explicit policy rules.

---

## 5. Memory, Constraints, and Contested Graph Space

### 5.1 The Three-Tier Memory Hierarchy
Active working context is strictly limited and expensive. Memory is organized across three tiers:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          MEMORY HIERARCHY                                 │
├───────────────────┬───────────────────────────────┬───────────────────────┤
│ Tier              │ Contents & Latency            │ Storage & Limits      │
├───────────────────┼───────────────────────────────┼───────────────────────┤
│ Hot: Working      │ Active prompt context,        │ In-memory RAM;        │
│ Memory            │ current task AST, immediate   │ Hard ceiling < a measured per-task context budget / │
│                   │ error buffers (< 1 sec)       │ prompt window limits  │
├───────────────────┼───────────────────────────────┼───────────────────────┤
│ Warm: Session &   │ Episode journals, verified    │ Local SQLite / WAL;   │
│ Relationship State│ candidate receipts, recent    │ 10 MB - 100 MB;       │
│                   │ capability profiles (< 50 ms) │ indexed vector/lexical│
├───────────────────┼───────────────────────────────┼───────────────────────┤
│ Cold: Durable     │ Historical snapshots, legacy  │ Content-addressed     │
│ Heritage Archives │ capabilities, raw execution   │ blob store (SHA-256); │
│                   │ traces, retired tools (> 1 s) │ unbounded; cold read  │
└───────────────────┴───────────────────────────────┴───────────────────────┘
```

### 5.2 Contested Graph Space & Active Reclamation
This proposal treats active graph space as a bounded resource, drawing on the [attention and commitments argument](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-02-ATTENTION-AND-COMMITMENTS.md). The reclamation mechanism below is proposed, not a ratified automatic-deletion policy. Retain source history and obligation/effect evidence; consequential authority and irreversible deletion remain owner-governed.
- **No Indiscriminate Graph Retention**: Retired or superseded entities are pruned from active indices and moved to cold storage.
- **Lightweight Tombstones**: Pruned items leave compact tombstone references (ID + SHA-256 + summary + reclamation date) to support historical provenance without polluting active retrieval.
- **Reclamation Cost Accounting**: Memory pruning and catalog consolidation are tracked as explicit resource expenditures.

---

## 6. The Progressive Reuse Ladder (Generalized 3-Box Principle)

To eliminate tool-management paralysis and avoid building unnecessary components, the personal assistant executes all problem-solving via the **Progressive Reuse Ladder**:

```
                         ┌──────────────────────────────────┐
                         │   Incoming Software Objective    │
                         └─────────────────┬────────────────┘
                                           │
                                           ▼
                 ┌──────────────────────────────────────────────────┐
                 │ Step 1: Can existing tools solve this?          │
                 │ ──► Adjust Action Sequence / Invocations        │
                 └─────────────────────────┬────────────────────────┘
                                           │ (No - Repeated Failure)
                                           ▼
                 ┌──────────────────────────────────────────────────┐
                 │ Step 2: Can an existing procedure be adapted?   │
                 │ ──► Modify Parameters / AST Transformation Rules │
                 └─────────────────────────┬────────────────────────┘
                                           │ (No - Missing Capability)
                                           ▼
                 ┌──────────────────────────────────────────────────┐
                 │ Step 3: Construct a Missing Capability          │
                 │ ──► Synthesize Tool Script + Verify in Sandbox   │
                 └─────────────────────────┬────────────────────────┘
                                           │ (Coordination Overhead High)
                                           ▼
                 ┌──────────────────────────────────────────────────┐
                 │ Step 4: Reorganize Multi-Entity Architecture     │
                 │ ──► Fuse into Composite / Consolidate State      │
                 └──────────────────────────────────────────────────┘
```

---

## 7. Four Fully Traced Worked Journeys

### Journey 1: Source-Grounded Software Construction & Retention
- **Scenario**: The user instructs the assistant to fix a TOCTOU race condition in a CLI branch promotion tool.
- **Trace**:
  1. *Investigation*: Assistant searches repository, locates unpinned `git merge branch_name` in `cli.py`, retrieves candidate fix recipes.
  2. *Ladder Decision*: Existing tools suffice for code editing, but mutation test verification lacks a specific receipt validator -> Step 3: Construct `validate_promotion_receipt.py`.
  3. *Construction & Check*: Assistant writes code, executes local unit tests, runs mutation checks, and verifies fail-closed receipt enforcement.
  4. *Session Restart & Unfamiliar Change*: In a fresh session, user requests promotion verification for a different Python CLI. Assistant retrieves retained `validate_promotion_receipt.py` via semantic match, checks applicability, and applies it directly without re-synthesizing from scratch.
- **Resource/Cost Trace**: 32K prompt tokens (investigation) + 14K tokens (tool synthesis) -> 4.2K tokens on second session (reused tool).

### Journey 2: Co-Adapting Shared Representation with Failure/Dissolution
- **Scenario**: An investigation worker (Participant A) and a test-generation worker (Participant B) collaborate over AST error formats.
- **Trace**:
  1. *Mismatch*: Participant A emits JSON AST spans; Participant B expects line-column tuples.
  2. *Adaptive Translation*: The relationship channel instantiates a bidirectional translation adapter.
  3. *Failure / Insoluble Schema Drift*: Participant A updates to a non-standard AST dialect that drops column offsets entirely. The translation adapter emits conversion failures.
  4. *Dissolution*: After 3 failed conversion cycles, the relationship aborts the adapter, dissolves the shared channel, falls back to raw text diffs, and requests human sovereign clarification regarding the intended parser schema.
- **Outcome**: The system prevents silent error masking and cleanly terminates unviable cooperation.

### Journey 3: Composite Descendant Retaining Competence in Changed Environment
- **Scenario**: A composite entity `RustBuilderComposite` (formed by fusing Cargo check, lint, and mutant-test runners) is transferred to a fresh workspace targeting Windows PowerShell from Linux Bash.
- **Trace**:
  1. *Inheritance*: Descendant inherits composite state, recipe DAG, and selection policy.
  2. *Environment Change*: Bash pipeline commands fail on PowerShell runtime.
  3. *Adaptation*: The composite detects environment flag `OS=Windows_NT`, activates its internal fallback recipe, and translates shell invocations to native Windows CLI commands without dismantling the composite's internal state machine or test verification logic.
- **Outcome**: Competence is preserved across environmental migration.

### Journey 4: Physical Construction & Hardware Co-Design Stress Test
- **Scenario**: Prototype calibration of a motor-driven biomimetic actuator with non-software sensor feedback (Hall effect sensors + thermocouple).
- **Trace**:
  1. *Uncertain Specimen State*: Physical hardware exhibits thermal drift and non-linear torque response.
  2. *Non-Software Evidence*: Continuous sensor telemetry streams into a dedicated hardware interface world.
  3. *Revisable Calibration Model*: The assistant fits a local polynomial calibration curve, applies torque limits to prevent overheating, and records the calibrated physical profile in warm memory.
  4. *Safety Tripwire / Consequential Choice*: Temperature exceeds 75°C. System engages hardware emergency stop, refuses auto-adaptation, and escalates to the human sovereign for physical inspection.
- **Outcome**: The architecture accommodates uncertain physical measurements and strict hardware safety tripwires without architectural mutation.

---

## 8. Consequential Architectural Alternatives

| Option / Decision | Approach | Consequential Tradeoffs | Selection & Rationale |
|---|---|---|---|
| **A. Monolithic STC vs. Small Floor vs. Full Substrate** | Expand STC into universal assistant vs. build massive substrate vs. minimal floor | STC expansion creates unmaintainable tool sprawl. Full substrate delays domain utility by months. Small floor provides immediate software value while leaving substrate growth open. | **Selected: Small Shared Floor**. Delivers immediate software assistant while maintaining developmental runway. |
| **B. Global Shared Ontology vs. Plastic Local Schemas** | Force all modules into one schema vs. allow pair-wise plastic translation | Global ontology breaks across diverse domains (software, science, robotics). Plastic translation handles domain differences with fallback to text. | **Selected: Plastic Local Schemas**. Enables modular independence and graceful error recovery. |
| **C. Immutable Global Graph vs. Pruned Multi-Tier Memory** | Keep all nodes forever in active graph vs. contest active space with cold archives | Global graph degrades retrieval speed and balloons token/RAM costs. Pruned tiering preserves provenance while keeping hot context lean (measured hot-context budget). | **Selected: Pruned Multi-Tier Memory**. Prevents graph bloat and protects prompt performance. |

---

## 9. Source-to-Design Traceability Map

```
┌──────────────────────────────────────┬──────────────────────────────────────────┬──────────────────────────────────────────────┐
│ Design Element                       │ Curated Source / Direct User Anchor      │ Epistemic Status & Rationale                 │
├──────────────────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────┤
│ Software-Construction Priority       │ D-022; personal-assistant.READABLE.md    │ [Accepted Direction] Explicit user choice in │
│                                      │ #personal-assistant-L166                 │ live session 2026-10-09.                     │
├──────────────────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────┤
│ Progressive Reuse (3-Box Rule)       │ personal-assistant.READABLE.md           │ [Proposed Principle] Tests tool         │
│                                      │ personal-assistant note (proposal)                 │ management paralysis via graduated response. │
├──────────────────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────┤
│ Minimal Floor & Decoupled Substrate  │ 2026-10-09-PERSONAL-ASSISTANT-AND-       │ [Proposed Architecture] Prevents blocking    │
│                                      │ DEVELOPMENTAL-SUBSTRATE.md:37            │ on substrate while preserving host runway.   │
├──────────────────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────┤
│ Contested Active Graph Space         │ VECTOR-02-ATTENTION-AND-COMMITMENTS.md:14│ [Accepted Constraint] Working memory is      │
│                                      │ personal-assistant.READABLE.md#L323      │ scarce; retired nodes must be pruned.        │
├──────────────────────────────────────┼──────────────────────────────────────────┼──────────────────────────────────────────────┤
│ Trias Politica & Verification Gates  │ current-coordinator.READABLE.md          │ [Accepted Baseline] Builder cannot self-     │
│                                      │ #current-coordinator-L125                │ promote without independent verification.    │
└──────────────────────────────────────┴──────────────────────────────────────────┴──────────────────────────────────────────────┘
```

---

## 10. Disposition of Major System Ambitions

```
┌──────────────────────────────────────────┬────────────────────┬────────────────────────────────────────────────────────┐
│ Ambition / Capability                    │ Disposition        │ Implementation Mechanism & Trigger                     │
├──────────────────────────────────────────┼────────────────────┼────────────────────────────────────────────────────────┤
│ Personal Software-Construction Assistant │ First Realization  │ STC-Lite + Minimal Floor + Local Capability Repertoire│
├──────────────────────────────────────────┼────────────────────┼────────────────────────────────────────────────────────┤
│ Research-to-Experiment-to-Artifact       │ First Realization  │ Integrated research loop feeding construction targets  │
├──────────────────────────────────────────┼────────────────────┼────────────────────────────────────────────────────────┤
│ Repertoire Construction & Adaptation     │ First Realization  │ AST & Python script synthesis in sandboxed workers     │
├──────────────────────────────────────────┼────────────────────┼────────────────────────────────────────────────────────┤
│ Composite Fusion & Dissolution           │ Specified Ext.     │ Staged state commit; triggered by repeat interaction   │
├──────────────────────────────────────────┼────────────────────┼────────────────────────────────────────────────────────┤
│ Cross-Generation Repertoire Inheritance  │ Specified Ext.     │ Cold archive serialization of verified recipes         │
├──────────────────────────────────────────┼────────────────────┼────────────────────────────────────────────────────────┤
│ Biomimetic / Hardware Physical Actuation │ Deferred           │ Bounded sensor calibration test; deferred to hardware  │
│                                          │                    │ design milestone.                                      │
└──────────────────────────────────────────┴────────────────────┴────────────────────────────────────────────────────────┘
```
