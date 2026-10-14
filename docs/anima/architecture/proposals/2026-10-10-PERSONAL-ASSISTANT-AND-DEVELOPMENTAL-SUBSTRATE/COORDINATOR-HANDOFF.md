# Proposed Coordinator Handoff: Personal Assistant & Developmental Substrate

> [!WARNING]
> **AWAITING ARCHITECTURE ACCEPTANCE AND SEPARATE EXECUTION AUTHORIZATION**  
> This handoff package defines a proposed execution mandate. It does not grant execution authority, authorize product launches, advance module version pins, or modify source repositories. Canonical integration and acceptance are owned strictly by the parent coordinator and human sovereign.

**Document Status**: Proposed Coordinator Handoff  
**Date**: 2026-10-10  
**Target Recipient**: Programme Coordinator  
**Final Proposal Home**: `ANIMA/architecture/proposals/2026-10-10-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE/`  

---

The contracts and mechanisms below are prospective consumer needs. Select actual owner-qualified tools/STC artifacts before integration; no new Lite profile or producer API is established. The durable floor may be assistant-local and does not require the broad substrate. Local journal rollback never establishes rollback of outside effects. Read [the corrected caller needs](REALIZATION-PLAN.md#2-caller-needs-and-owner-contract-candidates).

## 1. Execution Objective & Scope

### 1.1 Objective
Execute the bounded first realization of the ANIMA architecture: implement and benchmark a **source-grounded personal software-construction assistant** operating on real repository objectives, utilizing the minimal computational floor, and demonstrating autonomous capability development, adaptation, and reuse across session restarts.

### 1.2 In-Scope Work
1. Implement the minimal computational floor (process sandbox, SQLite WAL persistence, versioned message envelopes).
2. Implement the Repertoire Manager and Progressive Reuse Ladder selector.
3. Integrate with STC-Lite candidate contract (`stc_caller_contract_candidate`).
4. Execute the 5-task acquisition and 5-task evaluation benchmark against the matched simpler baseline.
5. Produce the complete independent verification dossier.

### 1.3 Strict Out-of-Scope (Non-Goals)
- No modification of external project source trees (`stc/`, `substrate/`, `trace-architecture/`).
- No public product launch or network deployment.
- No autonomous commit pushes to upstream Git branches without sovereign promotion receipts.
- No heavy biomimetic hardware fabrication during this first slice.

---

## 2. Observable Completion Criteria & Verification Gates

The execution run is complete only when all five criteria are independently verified:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   OBSERVABLE COMPLETION CRITERIA                                       │
├────┬─────────────────────────────┬─────────────────────────────────────────────────────────────────────┤
│ #  │ Criterion                   │ Measurable Verification Standard                                    │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 1  │ End-to-End Task Execution   │ Assistant takes 5 real repository tasks from objective to verified  │
│    │                             │ code fix with 100% test pass rate and zero syntax/linter regressions│
├────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 2  │ Autonomous Repertoire Growth│ Assistant autonomously constructs, tests, and retains ≥ 2 reusable  │
│    │ & Adaptation                │ tool capabilities without human tool-management intervention.       │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 3  │ Transfer Advantage on       │ In fresh session restarts on held-out tasks, the assistant retrieves│
│    │ Unfamiliar Tasks            │ and adapts retained tools, achieving ≥ 30% reduction in total token │
│    │                             │ against the competent matched baseline without a fixed percentage.                  │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 4  │ Interrupted Crash Recovery  │ Process injected with SIGKILL mid-transformation successfully       │
│    │                             │ recovers consistent local state; preserves unknown outside effects.          │
├────┼─────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 5  │ Independent Verification    │ Independent verification agent reproduces all test receipts with    │
│    │ Dossier                     │ withheld builder justifications; zero unverified receipt gaps.      │
└────┴─────────────────────────────┴─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Required Interfaces & Hard-Path Mechanisms

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          CORE SYSTEM INTERFACES                           │
│                                                                           │
│  ┌────────────────────────┐                   ┌────────────────────────┐  │
│  │   Assistant Engine     │◄─────────────────►│   Repertoire Engine    │  │
│  │   Interface draft       │                   │   Interface draft       │  │
│  └───────────┬────────────┘                   └───────────┬────────────┘  │
│              │                                            │               │
│              ▼                                            ▼               │
│  ┌────────────────────────┐                   ┌────────────────────────┐  │
│  │   STC-Lite Worker      │                   │   Sandboxed Subprocess │  │
│  │   Caller draft       │                   │   Local floor draft │  │
│  └────────────────────────┘                   └────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Hard-Path Mechanism: TOCTOU-Proof Branch Promotion
- **Risk**: Branch-name merging (`git merge feature_branch`) allows unverified branch drift between verification and promotion.
- **Enforced Mechanism**: All promotions must bind exact, content-addressed commit SHA-256 hashes (`git merge <exact_commit_sha>`) and require an immutable `ExecutionReceipt` signed by the independent verifier.

### 3.2 Hard-Path Mechanism: Sandboxed Process Execution
- **Risk**: Generated tool scripts perform destructive writes or unauthorized network requests.
- **Enforced Mechanism**: Subprocesses execute with scrubbed environment variables (`PATH` restricted to minimal tools), read-only source directory mounts, and isolated ephemeral write directories (`/tmp/anima_sandbox_<uuid>`).

### 3.3 Hard-Path Mechanism: Active Graph Memory Pruning
- **Risk**: Graph memory accumulation causes context degradation and token ballooning.
- **Enforced Mechanism**: Active memory cache enforces a strict a measured per-task context budget prompt ceiling. Inactive capability profiles decay and are evicted to cold JSONL archives, leaving lightweight tombstone references.

---

## 4. Decision Rights & Authority Allocation

```
┌───────────────────────────────────────────────────────────────────────────┐
│                       AUTHORITY ALLOCATION MATRIX                         │
├───────────────────────┬───────────────────────────────────────────────────┤
│ Role                  │ Authority Scope & Permitted Actions               │
├───────────────────────┼───────────────────────────────────────────────────┤
│ Human Sovereign       │ • Objective changes, budget limits, spend grants. │
│ (User)                │ • Final promotion / release authorization.        │
│                       │ • Resolution of consequential semantic branches.  │
├───────────────────────┼───────────────────────────────────────────────────┤
│ Programme Coordinator │ • Task decomposition, worker brief assignment.    │
│                       │ • Baseline reconciliation, receipt tracking.      │
│                       │ • Subprocess & resource management within envelope│
├───────────────────────┼───────────────────────────────────────────────────┤
│ Independent Verifier  │ • Auditing candidate artifacts against contracts. │
│                       │ • Independent test reproduction & receipt signing.│
│                       │ • Fail-closed rejection of unverified candidates. │
├───────────────────────┼───────────────────────────────────────────────────┤
│ Specialist Builder /  │ • Code investigation, patch synthesis, tool script│
│ Assistant Worker      │   construction within sandbox.                    │
│                       │ • Zero self-promotion or release authority.       │
└───────────────────────┴───────────────────────────────────────────────────┘
```

---

## 5. Dependencies & Unblocked Producer Paths

The execution plan depends on the following released snapshot artifacts:
- `stc/` snapshot candidate: `stc_caller_contract_candidate` (commit-bound receipt generator).
- `substrate/` snapshot candidate: `assistant_local_floor_candidate` (SQLite WAL lifecycle).
- `ANIMA/catalogue/MODULES.json`: Module discovery metadata.

**Producer Freedom**: All component projects continue independent development on their respective branches; this realization binds exclusively to immutable snapshot hashes.

---

## 6. Independent Verification & Anti-Gaming Plan

1. **Trias Politica Enforcement**: The builder agent synthesizing code cannot sign verification receipts. Verification must be executed by a separate agent instance.
2. **Withheld Justifications**: The verification agent receives only the task specification, candidate patch diff, test scripts, and target repository. The builder's internal monologue and rationalizations are withheld to eliminate confirmation bias.
3. **Defect-sensitive checks**: Use owner-qualified repository checks and supported mutation testing when useful. Calibrate quality criteria against the actual target baseline and justified caller needs; a universal mutation percentage is not adopted. Missing required evidence remains a scoped failure.
