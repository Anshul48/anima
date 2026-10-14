# WORKED-CASES: Concrete Reference Scenarios Across Project Records & Owners

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

**Version:** ANIMA-SOP-2026-10-10-v0.1  
**Status:** Proposed for owner-local adoption  
**Document Home:** `ANIMA/architecture/proposals/2026-10-10-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE/SOPs/WORKED-CASES.md`  
**Relative Cross-Links:**
- Suite Index & Everyday Guide: [README.md](README.md)
- Complete Procedures: [OPERATING-PROCEDURES.md](OPERATING-PROCEDURES.md)
- Primary Practice Evidence: [SOURCE-ADAPTATIONS.md](SOURCE-ADAPTATIONS.md)
- Integrated Context: [2026-10-10 Context Integration](../../../../context/integrations/2026-10-10/INDEX.md)
- Canonical Decisions: ANIMA Decisions & Corrections (historical record `../../../../context/DECISIONS-AND-CORRECTIONS.jsonl`, excluded from this public release)
- Architecture Notes: [ANIMA Architecture Notes](../../../notes/)

---

## 1. Introduction and Methodological Standards

This document works through six realistic reference cases illustrating how the connected Standard Operating Procedures ([OPERATING-PROCEDURES.md](OPERATING-PROCEDURES.md)) execute across actual ANIMA ecosystem projects (STC, SST, TRACE, TL, Substrate, Entorhinal, Reflex).

Each case demonstrates:
1. **Source Preservation:** Exact verbatim capture of raw input, timestamp, session/turn, and provenance.
2. **Intake Classification & Routing:** Proper triage between ordinary tasks, substantial changes, local component ideas, and macro proposals.
3. **Attributable Authority:** Clear delineation of who decides (User vs. Module Architect vs. Coordinator).
4. **Continuable Work:** How authorized, active execution proceeds unblocked without premature stops or administrative paralysis.
5. **Epistemic Discipline:** Explicit labeling of `reported`, `observed`, `verified`, `proposed`, `accepted`, and `deferred` states.
6. **Realistic Contract Artifacts:** Concrete contract representations (e.g., STC ↔ SST, TRACE ↔ TL) without asserting false, unmeasured implementation results.
7. **Exception & Failure Handling:** Robust handling of dirty trees, ambiguous directives, and inconclusive experiments without creating duplicate coordinators.

---

## 2. Case 1: Speculative Idea Arriving Mid-Build

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Coord as Coordinator / Architect
    participant Worker as STC Build Worker
    participant LocalDocs as stc/docs/FUTURE-IDEAS.md

    Note over Worker: Authorized Build Task Active (STC Dialectic Runner)
    User->>Coord: Turn 42: "What if we added an in-memory Redis layer for dynamic AST caching?"
    Coord->>Coord: Procedure 1: Classify as SPECULATIVE-IDEA (Non-blocking)
    Coord->>LocalDocs: File verbatim raw text, timestamp, Turn 42, Status: PROPOSED
    Coord-->>Worker: Continue active build unhindered (No interruption)
    Worker->>Worker: Finish Dialectic Runner implementation & pass unit tests
    Coord->>User: Report build completion; acknowledge cached idea filed in local docs
```

### Scenario Context
During an active, authorized build task in `stc/` (implementing the dialectic runner custody wrapper under an established grant), the User remarks:
> *"What if we put an in-memory Redis layer between the dialectic runner and the workspace AST parser to cache multi-candidate diff evaluations?"*

### End-to-End Walkthrough

1. **Source Preservation & Intake (Procedure 1):**
   - The coordinator captures the exact turn: `[2026-10-10T14:15:00Z, Session main-macro, Turn 42]`.
   - The input is classified as `SPECULATIVE-IDEA` with scope `PROJECT-LOCAL (STC)`.
2. **Routing & Disposition:**
   - Because the idea is specific to STC's internal execution optimization and does not alter exported caller contracts, it is routed to `stc/docs/architecture/FUTURE-IDEAS.md`.
   - A concise entry is appended:
     ```markdown
     ### [IDEA-STC-20261010-01] In-Memory Redis Layer for AST Diff Caching
     - Date/Source: 2026-10-10, Session main-macro Turn 42 (User)
     - Epistemic Status: PROPOSED (Exploratory optimization)
     - Description: Speculative addition of Redis caching between dialectic runner and AST parser.
     - Evaluation Criteria: Requires evidence of AST parse bottleneck >15% wall-clock time.
     - Prerequisite: Benchmark baseline AST parsing latency under load.
     ```
   - Macro ANIMA context remains completely untouched.
3. **Who Decides:**
   - STC Module Architect owns future evaluation; User holds authority if an external Redis infrastructure dependency is introduced.
4. **Continuable Work:**
   - The active STC build worker is *not* interrupted, restarted, or diverted. The worker continues executing the authorized task (`dialectic_runner.py` custody wrapper), runs its local unit test suite, and completes on schedule.
5. **Outcome & Completed Record:**
   - Active build completes with passing tests.
   - The idea is safely preserved for future benchmarking without inducing cognitive debt or architectural thrash.

---

## 3. Case 2: Explicit Requirement Change from the User

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Coord as Macro Coordinator
    participant ActiveTask as Migration / Tooling Task
    participant ADR as DECISIONS-AND-CORRECTIONS.jsonl

    User->>Coord: "Focus exclusively on native Windows AGY execution. Suspend Linux container work."
    Coord->>Coord: Procedure 1: Classify as DIRECT-INSTRUCTION / CONSTRAINT-CHANGE
    Coord->>ActiveTask: Pause Linux container task; preserve uncommitted state
    Coord->>ADR: Append Decision: Windows-native AGY supersedes Linux container priority
    Coord->>Coord: Procedure 3: Draft ADR-014 (Explicit Supersession)
    Coord->>ActiveTask: Dispatch native Windows AGY execution packet
```

### Scenario Context
The project roadmap previously prioritized containerized Linux/WSL execution under `migration_runs/windows-to-linux-20261008/`. In the current coordinator session, the User issues an explicit directive:
> *"We need to complete context integration and architecture documentation using native Windows Antigravity (`agy`) execution directly. Suspend Linux container packaging for now; native Windows is our active execution baseline."*

### End-to-End Walkthrough

1. **Source Preservation & Intake (Procedure 1):**
   - Captured from `campaign/AUTHORIZATION.md` (2026-10-10).
   - Classified as `DIRECT-INSTRUCTION` and `CONSTRAINT-CHANGE` with scope `ANIMA-WIDE`.
2. **Authority & Supersession (Procedure 3):**
   - An explicit current instruction from the User immediately supersedes prior stale architectural roadmap notes without requiring prolonged debate.
   - The coordinator updates `ANIMA/context/DECISIONS-AND-CORRECTIONS.jsonl`:
     ```json
     {
       "id": "DEC-20261010-01",
       "date": "2026-10-10",
       "authority": "User (Coordinator Session)",
       "scope": "ANIMA-WIDE",
       "status": "ACCEPTED",
       "decision": "Prioritize native Windows Antigravity (agy) execution for documentary completion; suspend Linux container migration packaging.",
       "supersedes": "DEC-20261008-04",
       "rationale": "Direct user instruction prioritizing Windows-native toolchain velocity and documentary completion over remote container migrations."
     }
     ```
   - An ADR entry is recorded in `ANIMA/architecture/decisions/` linking bi-directionally to the suspended migration plan.
3. **Handling Active Work:**
   - Active tasks in `migration_runs/windows-to-linux-20261008/` are frozen with a dated status note: `PAUSED per User instruction 2026-10-10`. No files are deleted.
4. **Continuable Work & Dispatch (Procedure 4):**
   - The coordinator issues new task packets configured specifically for native Windows PowerShell / AGY environments, using local filesystem paths.
5. **Outcome & Completed Record:**
   - Clean operational pivot executed in a single turn.
   - Provenance, rationale, and prior state remain fully audited.

---

## 4. Case 3: Rejected Idea Reintroduced with a Materially New Qualifier

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Coord as Macro Coordinator / Architect
    participant ADR as DECISIONS-AND-CORRECTIONS.jsonl
    participant LocalDocs as trace-architecture/docs/

    User->>Coord: "Can TRACE query TL directly in-memory via read-only memory-mapped IPC?"
    Coord->>ADR: Inspect prior rejection (ADR-006: Direct shared mutable memory rejected)
    Coord->>Coord: Check qualifier: "read-only memory-mapped IPC" != "mutable shared memory"
    Coord->>Coord: Procedure 1 & 3: Valid new qualifying constraint identified
    Coord->>LocalDocs: File bounded research proposal in TRACE/TL docs
    Coord->>Coord: Procedure 2: Frame Bounded Investigation (Benchmark IPC vs. SQLite)
    Coord-->>User: Acknowledge qualified idea; schedule bounded benchmark
```

### Scenario Context
Historically, direct shared memory between TRACE and TL was evaluated and rejected (`ADR-006: Direct Shared Memory Coupling Rejected`) due to the risk of concurrent memory corruption and unversioned state leakage.

In a new session, the User suggests:
> *"What if TRACE reads TL's published atom store via a strictly read-only, memory-mapped IPC layer (`mmap`), backed by immutable snapshot byte fences?"*

### End-to-End Walkthrough

1. **Source Preservation & Intake (Procedure 1):**
   - Exact input captured. Classified as `INVESTIGATION-REQUEST` with scope `CROSS-PROJECT (TRACE ↔ TL)`.
2. **Checking Against Prior Rejections:**
   - The architect checks `DECISIONS-AND-CORRECTIONS.jsonl` and finds `ADR-006`.
   - *Qualifier Analysis:* The previous rejection was based on *concurrent mutable writes* and *unversioned pointer leakage*. The new proposal introduces a materially distinct qualifier: *strictly read-only memory mapping over immutable byte-fenced snapshots*.
   - *Triage Decision:* Because the qualifier directly addresses the original failure mechanism, the idea is not dismissed as a duplicate. It is accepted as a valid new investigative candidate.
3. **Who Decides:**
   - TRACE and TL Module Architects evaluate technical feasibility; User retains authority over cross-module contract changes.
4. **Routing & Bounded Research Protocol (Procedure 2):**
   - The proposal is logged in `projects/trace-architecture/docs/CONTEXT-CONTRACT.md` under *Proposed Future Transports*.
   - A bounded research protocol is framed:
     - *Question:* Does read-only `mmap` reduce atom retrieval latency by >30% compared to SQLite blob queries without violating process crash-isolation?
     - *Resource Ceiling:* 1 research worker, maximum 2 hours, sample 10,000 atom synthetic corpus.
     - *Stop Criterion:* If memory protection faults or platform compatibility issues occur on Windows/Linux, terminate and reject.
5. **Continuable Work:**
   - Routine TRACE build work continues using the standard SQLite atom store reader. The investigation proceeds asynchronously in an isolated lab workspace.
6. **Outcome & Completed Record:**
   - Historical rejection remains respected and preserved; the new qualified variant is evaluated strictly on its empirical merits.

---

## 5. Case 4: Failed or Inconclusive Experiment

```mermaid
sequenceDiagram
    autonumber
    participant Coord as Coordinator
    participant Worker as Research Specialist
    participant ExpLog as projects/sst/docs/research/
    participant Synth as SYNTHESIS.md

    Coord->>Worker: Dispatch Experiment: Evaluate AST Pruning Heuristic #4
    Worker->>Worker: Execute benchmark suite against 50 synthetic ASTs
    Worker->>Worker: Result: Heuristic reduces search space by 12% but increases latency by 45% (Net Negative)
    Worker->>Worker: Procedure 2: Trigger Honest Stop (Criterion not met)
    Worker->>ExpLog: Commit raw benchmark data & FAILURE receipt (Wilson et al. discipline)
    Worker->>Synth: Record: Heuristic #4 REFUTED; retain negative result
    Worker->>Coord: Report completion with negative outcome; do not alter baseline
```

### Scenario Context
An experimental search heuristic (Heuristic #4: "Aggressive AST Subtree Pruning via Early Semantic Typing") was proposed for SST to reduce search tree expansion during candidate code generation.

### End-to-End Walkthrough

1. **Experiment Framing & Protocol (Procedure 2):**
   - *Question:* Does Heuristic #4 reduce overall dialectic search time by at least 25% across a standard 50-task benchmark corpus?
   - *Resource Ceiling:* 50 task runs, 10-minute timeout, maximum $1.00 compute spend.
   - *Stop Criterion:* If mean search time increases or task pass rate drops below baseline, halt immediately.
2. **Execution & Observed Evidence:**
   - The specialist runs the automated benchmark script `sst/benchmarks/run_heuristic_4.py`.
   - *Observed Outcome:* While the total explored node count dropped by 12%, the type-checker overhead per node increased evaluation time by 45%, resulting in a net 33% *slowdown* across the corpus.
3. **Enforcing the Honest Stop Decision:**
   - The worker does not tweak parameters indefinitely or engage in post-hoc rationalization.
   - Execution is terminated at the 50-task ceiling in accordance with pre-agreed criteria.
4. **Artifact Preservation & Negative Result Retention:**
   - The raw data is saved in read-only form under `projects/sst/docs/research/2026-10-heuristic-4/results.jsonl`.
   - A research receipt is published:
     ```markdown
     # EXPERIMENT RECEIPT: SST Search Heuristic #4 (AST Subtree Pruning)
     - Date: 2026-10-10
     - Status: REFUTED / FAILED
     - Hypothesis: Early semantic type pruning reduces dialectic search latency by ≥25%.
     - Observed Metric: +33% search latency (Node reduction: -12%; Type-check cost: +45%).
     - Decision: Do not adopt Heuristic #4. Retain baseline breadth-first AST expansion.
     - Lessons Learned: Type inference on partial AST fragments is too computationally expensive to run on inner search loops.
     ```
5. **Outcome & Baseline Integrity:**
   - SST codebase baseline remains clean and stable.
   - The negative result is permanently recorded to prevent future engineers or agents from re-running the same failed approach.

---

## 6. Case 5: Wanted Cross-Project Capability with No Qualified Release

```mermaid
sequenceDiagram
    autonumber
    participant STC as STC (Consumer Module)
    participant SST as SST (Producer Module)
    participant Probe as sst_compat_probe.py
    participant Contract as STC-SST-CALLER-CONTRACT.md

    Note over STC: STC needs live SST search capability
    STC->>Probe: Run probe against sibling `../sst` directory
    Probe->>STC: Output: DIRTY (`core/contracts.py`, `sandbox/custody.py` modified)
    STC->>STC: Procedure 5: Fail Closed! Unpinned/dirty tree refused
    STC->>Contract: Verify active pin remains `df78f4289...` (Pristine pin)
    STC->>STC: Fallback to mock search provider / pristine pin checkout
    STC-->>SST: Return probe findings; wait for SST owner to freeze release cand-03
```

### Scenario Context
STC (consumer) is actively developing its dialectic runner and desires to invoke live multi-branch search in SST (producer). However, SST's repository working tree is actively undergoing internal refactoring and has uncommitted modifications in `core/contracts.py` and `sandbox/custody.py`.

### End-to-End Walkthrough

1. **Consumer Integration Check (Procedure 5):**
   - STC executes its automated compatibility probe:
     `python dsh-plugin-stc/scripts/sst_compat_probe.py --sst-root ../sst`
2. **Observed Probe Results & Integrity Enforcement:**
   - The probe inspects the target directory and reports:
     ```text
     [SST COMPAT PROBE] Target: ../sst
     STATUS: DIRTY
     DIFF DETECTED IN SPOT FILES:
       - core/contracts.py (SHA256 mismatch against pin df78f428)
       - sandbox/custody.py (Uncommitted modifications detected)
     RESULT: FAIL-CLOSED. Tree cannot be leased for integration.
     ```
3. **Enforcing the Fail-Closed Rule:**
   - STC refuses to import or execute against the dirty `../sst` tree.
   - STC does *not* invent a temporary pin hash or track floating `main`.
4. **Realistic Contract Representation:**
   - STC consults its formal caller contract `projects/stc/docs/STC-SST-CALLER-CONTRACT.md`:
     ```markdown
     ## STC-side SST Caller Contract (Excerpt)
     - Active Pinned Commit: `df78f42894a65c48f524337a498032617689a013`
     - Resolution Rule: `STC_SST_ROOT` env wins, else sibling `../sst`.
     - Integrity Enforcement: Leases fail closed unless imported `sst` package matches spot file hashes.
     - Ownership Split:
       - SST supplies: Bounded alternatives/search, proposal scoring, event-sourced tree records.
       - STC retains: Domain evaluation, execution custody (leases, HMAC), spend ledger, champion veto.
     - Pin-Advance Requirement: SST owner must freeze and qualify a clean release before STC updates EXTERNAL_PINS.
     ```
5. **Continuable Work in Consumer & Producer:**
   - *STC (Consumer):* Configures `PYTHONPATH` to point to an isolated pristine checkout of the pinned commit `df78f4289`, or activates its deterministic mock search gateway. STC development and unit testing proceed unhindered.
   - *SST (Producer):* Continues internal refactoring at its own pace without external pressure to freeze prematurely.
6. **Outcome:**
   - Integration boundaries remain completely protected against silent corruption; neither team is blocked.

---

## 7. Case 6: Late Research Arriving After an Architectural Frontier was Frozen

```mermaid
sequenceDiagram
    autonumber
    actor External as External Source / Paper
    participant Coord as Macro Coordinator
    participant Baseline as Frozen 2026-10-05 Synthesis
    participant OpenIssues as ANIMA/context/OPEN-ISSUES.md

    External->>Coord: New paper arrives: "Dynamic Developmental World Topology"
    Coord->>Baseline: Check current baseline status: FROZEN (Stage 1 Synthesis Complete)
    Coord->>Coord: Procedure 1: Classify as LONG-TERM-RESEARCH
    Coord->>Coord: Check for immediate breaking flaws (None found)
    Coord->>OpenIssues: Log paper as Deferred Consideration for Bet D / Future Cycle
    Coord-->>Coord: Maintain frozen baseline; do not reopen completed architecture
```

### Scenario Context
On 2026-10-05, the ANIMA macro architecture completed and froze its developmental worlds synthesis (`ANIMA/architecture/notes/2026-10-05-DEVELOPMENTAL-WORLDS/SYNTHESIS.md`). On 2026-10-09, an external research preprint on "Dynamic Developmental World Membrane Topology and Agent Homeostasis" is submitted into context.

### End-to-End Walkthrough

1. **Source Preservation & Intake (Procedure 1):**
   - Full citation, abstract, and core claims are captured.
   - Classified as `LONG-TERM-RESEARCH` with scope `EXPLORATORY / FUTURE BET D`.
2. **Frontier Analysis & Baseline Protection:**
   - The coordinator checks the active baseline status. The 2026-10-05 synthesis represents a frozen architectural milestone supporting active Stage 1 implementation.
   - *Triage Test:* Does the late-arriving research reveal a fatal correctness, security, or feasibility flaw in the current baseline?
   - *Finding:* No fatal flaw is identified; the paper proposes an alternative, more complex theoretical framework for long-term multi-agent homeostasis.
3. **Who Decides:**
   - Macro Coordinator determines immediate baseline impact; User determines long-term research priorities.
4. **Recording Disposition Without Churn (Procedure 3):**
   - The coordinator does *not* dismantle the accepted baseline or halt active development.
   - The paper is filed in `ANIMA/architecture/notes/` as an exploratory reference, and logged in `ANIMA/context/OPEN-ISSUES.md`:
     ```markdown
     ### [ISSUE-20261010-04] Evaluation of Dynamic Membrane Homeostasis Paper
     - Source: External Preprint (Submitted 2026-10-09)
     - Status: DEFERRED (Target: Future Cycle / Long-Term Bet D)
     - Impact on Current Baseline: None. Current fixed world container model remains active for Stage 1.
     - Reconsideration Trigger: Transition from single-world construction to multi-agent ecosystem lifecycle (Bet D).
     ```
5. **Outcome:**
   - Architectural stability is preserved; intellectual insights are safely retained for the appropriate future milestone.

---

## 8. Summary of Worked Operational Patterns

| Case # | Trigger Type | Primary Role & Decider | Action on Active Work | Recorded Output & Artifact |
|---|---|---|---|---|
| **1** | Speculative Idea Mid-Build | STC Module Architect | Active build continues without interruption | `stc/docs/architecture/FUTURE-IDEAS.md` (Status: `PROPOSED`) |
| **2** | Direct User Requirement Change | User (Authorized) | Suspend old tasks; pivot to native Windows AGY | `DECISIONS-AND-CORRECTIONS.jsonl` (`DEC-20261010-01`) |
| **3** | Rejected Idea + New Qualifier | TRACE / TL Architects | Active build continues; frame isolated lab benchmark | `CONTEXT-CONTRACT.md` (Proposed Future Transport) |
| **4** | Failed / Inconclusive Experiment | SST Research Specialist | Terminate at pre-set resource ceiling (Honest Stop) | `projects/sst/docs/research/` (Receipt: `REFUTED`) |
| **5** | Wanted Unqualified Dependency | STC Integration Owner | Fail-closed on dirty tree; activate mock/pristine pin | `STC-SST-CALLER-CONTRACT.md` (Retain frozen pin) |
| **6** | Late Research After Frozen Baseline | Macro Coordinator | Protect frozen baseline; log for future Bet D | `ANIMA/context/OPEN-ISSUES.md` (Status: `DEFERRED`) |
