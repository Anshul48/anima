# ANIMA Architecture Handoff (Stage 1 → Stage 2)

**Prepared Date:** 2026-10-08  
**Author:** Context Integration Curator  
**Target Recipient:** Fresh Stage 2 Architect Session  
**Authorizing Prompt:** [`ANIMA/architecture/notes/2026-10-08-ARCHITECTURE-AUTHORING-PROMPT.md`](../../../architecture/notes/2026-10-08-ARCHITECTURE-AUTHORING-PROMPT.md)  
**Runbook Reference:** [`ANIMA/architecture/notes/2026-10-08-TWO-STAGE-ARCHITECTURE-RUNBOOK.md`](../../../architecture/notes/2026-10-08-TWO-STAGE-ARCHITECTURE-RUNBOOK.md)

---

## 1. Handed-Off Baseline & Current Direction

The Stage 1 curation phase has assembled, preserved, deduplicated, and synthesized all accumulated macro-architectural context from the primary session (`01a0f85a-6e14-7e93-8bc3-83af412e7eec`), secondary reference anchors, and the Developmental Worlds packet.

### Core Governance Principles
1. **ANIMA Scope:** ANIMA is the macro-architectural umbrella, coordination coordinate, and catalogue. It does not own runtime implementations or monorepo code.
2. **Independent Track Ownership:** Substrate, STC, SST, TL, and TRACE evolve in their owning project folders. Macro architecture interacts via compact published contracts and bounded release pins.
3. **Evidence Discipline:** Candidate paths are not releases. Mocks are not live-caller qualifications. Unresolved choices must remain explicit.

---

## 2. Governed Baselines vs. Architect Freedoms

| Category | Fixed Baseline (Do Not Overturn) | Architect Freedom & Design Mandate |
|---|---|---|
| **Component Boundaries** | TL (source memory), TRACE (interpretation/episodic), STC (construction), SST (search), Substrate (world hosting). | Define interface protocols, inter-world messaging schemas, and composition patterns. |
| **Research Priorities** | A → C → B → D sequence is established direction. | Determine concrete intermediate milestones, capability metrics, and testbed configurations. |
| **Integration Model** | Compact contracts + bounded release pins (`catalogue/pins/`). | Author contract specifications (`ANIMA/architecture/contracts/`) and define verification suites. |
| **Execution Ownership** | Active DAG remains owned by `autonomous_runs/trace_ecosystem_20261002/`. | Propose new milestone architectures without modifying active programme state files. |

---

## 3. Consequential Choices for Stage 2

The Stage 2 Architect must address and propose solutions for the following architectural decisions:

1. **World Container & Membrane Protocol:**
   - How are world instances instantiated, isolated, and connected?
   - What is the standard envelope for state custody, permission grants, and resource quotas?
2. **First Integrated Realization:**
   - Propose the minimum viable end-to-end realization combining STC (as construction world), TRACE (as episodic memory), and TL (as source ground).
   - Define exact qualification tests for this baseline.
3. **Cognitive Debt & Retirement Automation:**
   - Define the schema for registering deferred refactors, unverified assumptions, and deprecated routines.
   - Establish the lifecycle state machine for retiring obsolete procedures from active traversal.
4. **Project Architect Directives Rollout:**
   - Finalize the shared directive template and specify how the programme coordinator will track project compliance across STC, SST, TL, TRACE, and Substrate.

---

## 4. Evidence Gaps & Impact Assessment

| Gap / Incomplete Area | Impact on Stage 2 Architecture | Severity / Action |
|---|---|---|
| **Paused B1/B2 Desktop Archive Review** (`2026-10-05-B-CONTEXT-REVIEW-PENDING.md`) | Historical exploratory notes on B1/B2 are unmerged. | **Non-blocking.** Current synthesis captures all active constraints. Keep review queued. |
| **Live-Caller SST Qualification** | SST integration in active programme is mock-verified, not caller-verified. | **Informational.** Architect must design for asynchronous/pluggable search without assuming synchronous zero-cost search. |
| **TL Cross-Document Organization** | Narrow single-document baseline is reported; multi-document reconciliation is open. | **Constraint.** Macro architecture must treat TL memory units as document-scoped atoms with overlay graph indexes. |

---

## 5. Entry Point & Next Steps

1. Review [START-HERE.md](../../../START-HERE.md) and [SYNTHESIS.md](SYNTHESIS.md).
2. Read the Stage 2 Prompt: [`ANIMA/architecture/notes/2026-10-08-ARCHITECTURE-AUTHORING-PROMPT.md`](../../../architecture/notes/2026-10-08-ARCHITECTURE-AUTHORING-PROMPT.md).
3. Place architectural proposals and contract designs in `ANIMA/architecture/proposals/2026-10-08-DEVELOPMENTAL-SUBSTRATE/`.
