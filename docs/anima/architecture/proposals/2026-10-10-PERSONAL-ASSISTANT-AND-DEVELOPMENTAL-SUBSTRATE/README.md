# ANIMA Macro-Architecture & Developmental Substrate Proposal

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

**Document Status**: Proposed Architecture Candidate  
**Date**: 2026-10-10  
**Final Proposal Home**: `ANIMA/architecture/proposals/2026-10-10-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE/`  
**Review Status**: Documentary integration and independent review complete; architecture acceptance and separate execution authorization remain pending. Review record (historical record `../../../coordination/2026-10-10-documentary-completion/FINAL-REVIEW.md`, excluded from this public release).

---

## 1. Executive Orientation & Core Thesis

This proposal establishes a coherent macro-architecture for the ANIMA developmental computational environment and defines its first demanding, domain-grounded vertical realization: a **personal software-construction assistant that develops, adapts, composes, and retains executable capabilities through real work**.

The proposal bridges two core ambitions without subordinating one to the other:
1. **Immediate High-Leverage Domain Value**: An autonomous personal assistant focused immediately on software construction (investigation, architecture, code generation, independent verification, and artifact delivery under human steering), with research-to-experiment-to-artifact workflows integrated alongside (D-022 (historical record `../../../context/integrations/2026-10-10/preserved/documents/anima/context/DECISIONS-AND-CORRECTIONS.jsonl`, excluded from this public release), personal-assistant.READABLE.md#personal-assistant-L166 (historical record `../../../context/integrations/2026-10-10/preserved/chats/personal-assistant.READABLE.md#personal-assistant-L166`, excluded from this public release)).
2. **Computational Environment for Organizational Development**: A substrate wherein computational entities, boundaries, shared representations, and cooperative procedures genuinely develop over time—supporting within-lifetime adaptation, persistent composites, structural specialization, co-adaptation, dissolution/fission, and cross-generation inheritance ([VECTOR-01](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-01-DEVELOPMENTAL-CHANGE.md), [VECTOR-06](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-06-CONSTRUCTION-REPERTOIRES.md), [VECTOR-08](../../notes/2026-10-05-DEVELOPMENTAL-WORLDS/VECTOR-08-RETENTION-AND-DESCENDANTS.md)).

### The Architectural Strategy: Small Shared Floor, Progressive Reuse

Rather than either (a) bloating the Software Task Coordinator (STC) into a universal monolith or (b) blocking all assistant value until a heavyweight developmental substrate is fully fabricated, this architecture introduces a **minimal, stable computational floor** ([ARCHITECTURE.md](ARCHITECTURE.md#2-the-smallest-stable-computational-floor)). 

The proposed system would use the **Progressive Reuse Rule** (the generalized 3-Box principle, [personal-assistant design note (proposal)](../../notes/2026-10-09-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE.md)):
- If existing tools suffice, adjust the invocation sequence.
- If a method repeatedly fails or is awkward, adapt the participating procedure.
- If the repertoire lacks required capability, construct a new executable tool/skill.
- If coordination or representation overhead across capabilities dominates, alter the organization (form a composite, consolidate state, specialize roles, or dissolve).

---

## 2. Input Frontier & Catalogue Corrections

### Input Frontier & Snapshot Accounting
The documentary input baseline for this proposal is derived strictly from the approved campaign payload:
- **98 Documentary Snapshots**: Exactly 96 ANIMA documentary snapshots plus two named genesis condensations:
  - `B1 condensed.txt` (SHA-256: `2ac91ef6aa377c90892a3b10ecf4c91cb58ed0e5a105fa651c917615cdfbb47f`)
  - `B2 condensed.txt` (SHA-256: `45bdcde52a76c1a623d9fcb4e51a97e338e41cd3e5e2db2a8108f58292d87dfa`)
- **41 Related-Project Mirrors**: Snapshots of independent projects (such as `substrate/`, `entorhinal/`, `relfex/`, `migration_runs/`, and `autonomous_runs/`) are preserved strictly as separate context mirrors; they are **never counted inside the 98 documentary snapshots**.

### Corrections to Context-Draft Candidate
Root coordinator review identified structural deficiencies in the provisional context derivative (`jobs/context-integration/attempt-01/workspace/output/`):
1. **Invalid Relative Link Paths**: The context candidate contained broken input-relative paths (`inputs/anima/...`). In this proposal packet, all links are authored relative to the final canonical home (`ANIMA/architecture/proposals/2026-10-10-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE/`).
2. **Pending R1–R7 Closure**: The context draft prematurely asserted closure of review findings R1–R7. In this architecture packet, integrated independent review remains explicitly pending until formal coordinator integration and independent audit.
3. **Evidence-Strength Labeling**: Context candidate claims and dispositions have been reviewed and labeled with explicit epistemic precision (`[Hypothesis]`, `[Reported]`, `[Observed]`, `[Independently Reproduced]`, `[Verified]`, `[Accepted Direction]`) rather than automatic adoption.
4. **Preservation of Owner Negative Results**: Substrate alpha package evidence preserves `HOST-VALUE-NOT-DEMONSTRATED`, tied direct vs. host outputs, and degenerate/VOID changed-condition tests ([ROADMAP.md](../../../../../components/substrate/docs/ROADMAP.md)). Alpha process recovery and fusion represent mechanical lifecycle persistence, not acquired autonomous competence.

---

## 3. Packet Reading Routes

This proposal packet consists of six substantive, interconnected documents:

```
ANIMA/architecture/proposals/2026-10-10-PERSONAL-ASSISTANT-AND-DEVELOPMENTAL-SUBSTRATE/
├── README.md                          # Executive overview, status, catalogue truth, reading routes
├── ARCHITECTURE.md                    # Core architecture, mechanisms, state, 4 worked journeys, alternatives
├── REALIZATION-PLAN.md                # First bounded slice, matched baseline, qualification, hardware path
├── DECISIONS-AND-OPEN-QUESTIONS.md    # Commitments, proposed choices, replaceable mechanisms, open branches
├── COORDINATOR-HANDOFF.md             # Execution handoff package (marked awaiting acceptance/authorization)
└── REVIEW.md                          # Rigorous self-critique, baseline audit, authority & feasibility analysis
```

### Reading by Role

- **For the Human Sovereign / Integrator**:
  1. Start with [README.md](README.md) for top-level direction and corrections.
  2. Read [ARCHITECTURE.md §1, §6, §7](ARCHITECTURE.md) for the core model, the progressive reuse ladder, and the four traced worked journeys.
  3. Inspect [DECISIONS-AND-OPEN-QUESTIONS.md §5](DECISIONS-AND-OPEN-QUESTIONS.md#5-consequential-unresolved-decisions-requiring-human-sovereign-input) for the few consequential branch points requiring human steering.
  4. Review [REVIEW.md](REVIEW.md) for critical examination of ordinary automation vs. developmental improvement.

- **For the Programme Coordinator (Prospective Execution)**:
  1. Read [COORDINATOR-HANDOFF.md](COORDINATOR-HANDOFF.md) for the complete self-contained execution package, interfaces, and completion criteria.
  2. Read [REALIZATION-PLAN.md](REALIZATION-PLAN.md) for dependency ordering, contract candidates, and test/qualification protocols.
  3. Consult [ARCHITECTURE.md §2–§5](ARCHITECTURE.md) for data structures, state models, and hard-path mechanisms (recovery, memory reclamation, authority transitions).

- **For Independent Reviewers & Auditors**:
  1. Read [REVIEW.md](REVIEW.md) for the architectural self-audit and explicit limitations.
  2. Check [ARCHITECTURE.md §9](ARCHITECTURE.md#9-source-to-design-traceability-map) (Source-to-Design Traceability Map) to verify that claims link to exact source anchors.
  3. Evaluate [REALIZATION-PLAN.md §3](REALIZATION-PLAN.md#3-matched-baseline-comparison--anti-leakage-protocols) to verify fair baseline comparisons and anti-leakage controls.

---

## 4. Prospective Procedures Notice

Shared Standard Operating Procedures (`SOPs/README.md`) and project-specific handoffs (`project-handoffs/`, `SOP-ISSUANCE.md`) are being produced by separate documentary workers. Throughout this packet, references to those procedures are marked as **prospective** until formally supplied, integrated, and accepted by the parent coordinator.
