# ANIMA Integrated Macro-Architecture Synthesis (2026-10-08)

## 1. Executive Summary & Core Objective

The ANIMA macro-architecture initiative aims to significantly increase the effective capability of humans and cooperating AI systems to investigate, design, build, verify, learn, and adapt. The user concentrates on high-leverage strategic direction, architectural synthesis, and consequential choices, while autonomous and semi-autonomous subsystems handle systematic exploration, verification, construction, and operational maintenance.

ANIMA is not an acronym, nor is it a single monorepo or runtime engine. It is the unifying architectural umbrella, context coordinate, catalogue, and coordination framework across multiple independent, evolving computational projects.

### Priority Research Map: A → C → B → D
The long-term development roadmap is organized along four primary research bets, representing a progression of foundational capability rather than rigid waterfall gates:
- **Bet A (Attributable Memory & Computationally Useful Knowledge):** Structuring knowledge so that representations, past decisions, source traces, and interpretations are durable, inspectable, and machine-actionable.
- **Bet C (Learned Schemas, Operations & Workflow Procedures):** Transitioning from hardcoded pipelines to adaptive, reusable schemas, procedure repertoires, and self-improving workflows.
- **Bet B (Cumulative Capability Discovery & World Evolution):** Enabling autonomous systems to discover new composite operations, specialize expert societies, manage cognitive debt, and retire obsolete procedures.
- **Bet D (Computational / Physical Co-Design & Embodied Adaptation):** Extending adaptive software and organizational principles to physical, spatial, and hardware-constrained systems.

Foundational software development is designed to accelerate and support later physical and hardware co-design bets without waiting for Bet D to begin software exploration.

---

## 2. Namespace Disambiguation & Architectural Separation

To prevent persistent architectural confusion, the following critical distinctions are formally codified:

1. **Broad Substrate vs. STC Substrate Package:**
   - **Broad Substrate (`hosting.substrate`, `substrate/`):** The conceptual and future runtime environment for hosting worlds, managing plastic boundaries, state custody, lifecycle, resource allocations, and inter-world communication.
   - **STC Mechanical Substrate (`stc.substrate`):** A project-local Python support package inside `stc/` providing local execution primitives and container interfaces.
2. **TL Family vs. Sibling Implementations:**
   - **TL Selected Baseline:** `trace-architecture/tl-candidate-batch` plus `trace-architecture/tl-sys`.
   - **Sibling `trace-lite`:** An independent alternate implementation, distinct from the selected TL family.
3. **SST Concept vs. SST Project:**
   - **SST Project (`search.sst`, `sst/`):** The standalone bounded search and candidate generation module.
   - **Search as an Architectural Mechanism:** Broader exploratory search across programme spaces, repertoires, and hypothesis spaces.
4. **The Two Vector Rounds:**
   - **18-Vector Round (Oct 1–3, 2026, V1–V18):** Broad macro-architectural landscape mapping (membranes, holons, schemas, plastic relationships).
   - **8-Vector Developmental Worlds Round (Oct 5–7, 2026, Vectors 01–08):** In-depth developmental system design and empirical evidence dossiers located in `ANIMA/architecture/notes/2026-10-05-DEVELOPMENTAL-WORLDS/`.

---

## 3. The 8 Developmental Vectors & Core Architectural Mechanisms

The October 5–7 deep-dive established eight interconnected architectural vectors:

### Vector 01: Developmental Change & Plastic Boundaries
- **Mechanism:** Systems must support runtime restructuring, dynamic boundary renegotiation, and fluid composition of participants. Membranes define capability filters, resource allowances, and state custody without hardcoding permanent topologies.
- **Evidence/Limits:** Dynamic membranes introduce coordination latency and boundary-checking overhead. Plasticity must be bounded by explicit invariants.

### Vector 02: Attention, Commitments & Cognitive Debt
- **Mechanism:** Explicit tracking of attention allocation, outstanding obligations, asynchronous promises, and accumulated cognitive debt (unverified assumptions, deferred refactors, orphan states).
- **Evidence/Limits:** Unbounded attention registers degrade performance; background reconciliation and retirement cycles are essential.

### Vector 03: Expert Individuality & Societies of Mind
- **Mechanism:** Distinct, specialized agent personas and sub-societies with differentiated memory stores, foraging heuristics, and evaluation lenses. Disagreement and adversarial debate are structural features for catching blind spots.
- **Evidence/Limits:** Unchecked diversity causes coordination fragmentation; shared ontological anchors and formal debate protocols are required.

### Vector 04: Physical Construction & Co-Design
- **Mechanism:** Translating abstract computational decisions into physical, spatial, or hardware constraints (latency, power, pinouts, physical placement).
- **Evidence/Limits:** Hardware simulation requires high fidelity; early work focuses on software abstraction layers that mirror physical resource constraints.

### Vector 05: Creative Coverage & Outliers Under Compression
- **Mechanism:** Preventing premature convergence in search and synthesis by explicitly retaining outlier hypotheses and non-standard solutions under semantic compression.
- **Evidence/Limits:** Preserving outliers increases memory footprints; requires tiered storage where outliers are indexed with minimal metadata until re-activated.

### Vector 06: Construction Repertoires & Reusable Deltas
- **Mechanism:** Accumulating reusable construction patterns, code deltas, verified macros, and repair templates that can be indexed and retrieved by semantic intent.
- **Evidence/Limits:** Library bloat and schema drift; repertoires require continuous pruning, regression validation, and relevance ranking.

### Vector 07: Programme Search & Resource Allocation
- **Mechanism:** Multi-scale search over candidate execution programs, schedules, and agent allocations, leveraging heuristic guidance from SST and historical run traces.
- **Evidence/Limits:** Combinatorial explosion; search horizons must be strictly bounded with early exit criteria.

### Vector 08: Retention, Retirement & Descendant Inheritance
- **Mechanism:** Generational inheritance of verified capabilities, schemas, and compressed knowledge to descendant worlds/runs, combined with deliberate retirement of obsolete procedures. Old procedures are removed from active traversal while retaining audit logs.
- **Evidence/Limits:** Inheritance risks transferring latent defects; descendants must independently re-validate inherited baselines upon activation.

---

## 4. Biological Analogies & Constraint Enforcement Systems

Discussions in A/B contexts (notably 4A, 4B, and 4C) established crucial biological principles:
- **Hippocampal vs. Entorhinal Grounding:**
  - *Hippocampus:* High-fidelity episodic recording, rapid indexing of temporal events, uncompressed recent context.
  - *Entorhinal Cortex:* Spatial/relational grid mapping, conceptual geometry, tracking user trajectories and operational context over long horizons.
- **Constraint Enforcement & Immune Mechanics:**
  - Robust systems require active constraint monitors (analogous to biological immune surveillance and metabolic checkpoints) that identify divergence, state corruption, or resource exhaustion before catastrophic failure.
- **Limits of Analogy:** Metaphors are generative guides, not formal specifications. Every biological concept must map to concrete computational state machines, schemas, and verifiable contracts.

---

## 5. Independent Module Evolution & Release-Based Integration (October 8 Governance)

The user's latest strategic direction (2026-10-08) establishes the operational paradigm for ANIMA:

1. **Independent Track Ownership:**
   - Substrate, STC, SST, TL, and TRACE are developed independently by their respective project owners.
   - Architectural discussions and local design choices belong inside each project's repository.
2. **Compact Interface Contracts:**
   - Integration requirements are agreed early via compact, published interface contracts (under `ANIMA/architecture/contracts/` or project `docs/`).
   - Contracts define capabilities, schemas, error semantics, resource expectations, and verification suites.
3. **Completed Bounded Releases & Consumer Pins:**
   - ANIMA and consuming modules integrate only completed, qualified, bounded releases.
   - Consumers deliberately pin specific release identities (`catalogue/pins/`).
   - Mutable source paths (`catalogue/MODULES.json`) provide discovery metadata, never implicit runtime dependencies.
4. **Explicit Exclusions & Deferred Obligations:**
   - Releases may explicitly exclude specific integrations (e.g., TRACE launching initially without SST), provided the exclusion and future obligation are formally recorded.
5. **Standard Operating Procedures (SOPs):**
   - Macro-architecture produces shared SOP templates (`ANIMA/architecture/templates/MODULE-ARCHITECTURE-DIRECTIVE.md`), which project architects adapt locally. The programme coordinator oversees rollout.

---

## 6. Local Project Implications

| Project | Role | Current Status | Integration Mandate |
|---|---|---|---|
| **TL** | Attributable source memory & organization | Historical narrow baseline reported | Maintain selected `tl-candidate-batch` + `tl-sys` identity; resolve broader multi-document organization. |
| **TRACE** | Episodic & interpretation memory | Product landing `trace-build` | Enforce semantic gates; support initial release with explicit SST deferral. |
| **STC** | Construction & execution world | Mixed implementation in progress | Ground DSH execution; incubate early workflow/procedure learning without claiming general adaptivity. |
| **SST** | Bounded candidate search | Standalone implementation | Qualify real-caller integration; distinguish mock testing from operational qualification. |
| **Substrate** | World hosting & lifecycle | Design proposal phase | Define world container contracts, state custody, and dynamic boundary protocols. |
| **Entorhinal**| Activity tracking & local context | Autonomous utility | Provide background user activity mapping without imposing central cognitive load. |

---

## 7. Open Consequential Choices & Stage 2 Handoff

The macro-architect in Stage 2 (`ANIMA/architecture/notes/2026-10-08-ARCHITECTURE-AUTHORING-PROMPT.md`) must resolve:
1. **World Container Contract:** Exact structural schema for inter-world boundaries, permission membranes, and state handoffs.
2. **First Realization Scope:** Selecting the concrete baseline world (e.g., STC construction world + TRACE episodic memory + TL source grounding) for end-to-end qualification.
3. **Cognitive Debt Protocol:** Formal schema for recording, penalizing, and retiring orphan assumptions and superseded procedures.
4. **Contract Formalization:** Transforming informal track briefs into machine-verifiable contract definitions.

*Note on Paused Review:* The comprehensive B1/B2 Desktop archive review remains paused (`ANIMA/architecture/notes/2026-10-05-B-CONTEXT-REVIEW-PENDING.md`). This pause does not block Stage 2 architectural synthesis.
