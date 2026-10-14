# SST Dialectic Search & Cognitive Division of Labor

> **Document Version:** 1.0.0  
> **Package:** `sst-engine` (`src/sst/prompts`, `src/sst/search`)  
> **Status:** Production Architecture Standard  

---

## 1. The Dialectic Search Philosophy

Traditional AI code generation approaches suffer from a fundamental tension between exploration and precision:
- High-temperature sampling discovers novel architectures but produces invalid syntax, broken imports, and hallucinated interfaces.
- Low-temperature sampling produces syntactically valid code but rapidly collapses into repetitive, conservative local minima.

SST resolves this contradiction by implementing an **asymmetric dialectic division of labor**. Rather than forcing a single model invocation to simultaneously brainstorm, refine, verify, and critique, the cognitive workload is partitioned across dedicated functional roles:

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           ASYMMETRIC DIALECTIC ROLLS                             │
├───────────────────┬───────────────────┬───────────────────┬──────────────────────┤
│ Functional Role   │ Hyperparameters   │ Target Paradigm   │ Primary Mandate      │
├───────────────────┼───────────────────┼───────────────────┼──────────────────────┤
│ 1. DIVERGE        │ T=1.20, p=0.95    │ High Entropy      │ Brainstorm N radical │
│                   │ (Fast / Cheap)    │ Unconstrained     │ structural proposals │
├───────────────────┼───────────────────┼───────────────────┼──────────────────────┤
│ 2. REFINE         │ T=0.05, p=0.10    │ Monotropic Rigor  │ Type hygiene, exact  │
│                   │ (Long Context)    │ Zero Drift        │ diffs, AST contracts │
├───────────────────┼───────────────────┼───────────────────┼──────────────────────┤
│ 3. CRITIQUE       │ T=0.20, p=0.30    │ Prefrontal Cortex │ Qualitative audit,   │
│                   │ (Frontier Model)  │ Value Critic      │ value score [0, 1]   │
├───────────────────┼───────────────────┼───────────────────┼──────────────────────┤
│ 4. SYNTHESIZE     │ T=0.20, p=0.30    │ Colimit Blending  │ Merge complementary  │
│                   │ (Frontier Model)  │ Dialectic Union   │ passing solutions    │
├───────────────────┼───────────────────┼───────────────────┼──────────────────────┤
│ 5. HUMAN_DECISION │ Asynchronous      │ Sovereign Oracle  │ Breaking changes,    │
│                   │ (Manual Review)   │ Gatekeeper        │ irreversible actions │
└───────────────────┴───────────────────┴───────────────────┴──────────────────────┘
```

---

## 2. Deep Dive: Functional Dialectic Roles

### 2.1 The `DIVERGE` Role (High-Entropy Exploration)
- **Mandate**: Ingests the task specification and context capsule to generate diverse hypotheses and structural mutations.
- **Operational Profile**: High temperature ($T=1.20$), elevated top-$p$ ($0.95$). Encouraged to consider unconventional concurrency models, cache layouts, and architectural patterns.
- **Negative Feedback Ingestion**: Explicitly fed **Negative Inhibitors** from `trace/` and rationales from previously pruned sister branches to ensure it does not repeat failed patterns.

### 2.2 The `REFINE` Role (Monotropic Implementation)
- **Mandate**: Translates the abstract strategy from `DIVERGE` into a concrete, minimal, syntax-verified unified diff or file implementation.
- **Operational Profile**: Near-deterministic temperature ($T=0.05$), low top-$p$ ($0.10$).
- **Strict Formatting**: Enforces valid Git unified diff headers or clean file blocks, exact import matching against existing codebase symbols, and zero hallucinated third-party dependencies.

### 2.3 The `CRITIQUE` Role (Prefrontal Value Network)
- **Mandate**: Evaluates candidate branches that have passed the deterministic test suite.
- **Operational Profile**: Cold frontier model ($T=0.20$, top-$p=0.30$).
- **Scoring Dimensions**:
  1. *Architectural Fit*: Does the code respect existing design patterns and boundaries?
  2. *Security & Isolation*: Does the patch introduce potential resource leaks or security vulnerabilities?
  3. *Simplicity & Modularity*: Does the change solve the problem with minimal conceptual overhead?
- Emits a normalized value score $V \in [0.0, 1.0]$. Branches scoring below $0.70$ are pruned.

### 2.4 The `SYNTHESIZE` Role (Colimit Dialectic Merge)
- **Mandate**: Triggered when two or more distinct branches independently pass all mechanical tests and receive high critique scores.
- **Mechanism**: Computes the categorical colimit of the passing branches:
  - Branch A might achieve maximum throughput through SIMD vectorization.
  - Branch B might achieve superior resilience through defensive error recovery.
  - `SYNTHESIZE` merges the vectorization from Branch A with the error handling from Branch B, producing a strictly superior child node.

### 2.5 The `HUMAN_DECISION` Role (Human Escalation Oracle)
- **Mandate**: Prevents catastrophic autonomous actions.
- **Escalation Triggers**:
  - File or module deletions affecting core public interfaces.
  - Value scores exhibiting severe uncertainty or bimodal critic disagreement.
  - Modifications to security boundary definitions or cryptographical credentials.
- Pauses the branch until approved via `sst decide <tree_id> <candidate_id> --verdict APPROVED`.

---

## 3. Integration with Project Trace (Memory Substrate)

SST establishes a two-way membrane with Project Trace (`trace/`):

```
┌──────────────┐         1. Query Negative Inhibitors & Atoms          ┌──────────────┐
│              │ ───────────────────────────────────────────────────> │              │
│  SST ENGINE  │                                                      │ TRACE MEMORY │
│   (`sst/`)   │ <─────────────────────────────────────────────────── │   STORE      │
│              │         2. Return Forbidden Patterns & Signatures     │  (`trace/`)  │
│              │                                                      │              │
│              │         3. Emit Refutations from Pruned Branches     │              │
│              │ ───────────────────────────────────────────────────> │              │
└──────────────┘                                                      └──────────────┘
```

1. **Pre-Search Ingestion**: Before initializing a search tree, SST queries Trace's FTS5 database (`query_negative_inhibitors`) to retrieve known anti-patterns, past regression causes, and boundary conditions.
2. **Post-Search Learning**: When a candidate branch is pruned (either deterministically or semantically), SST packages the failure traceback and critic rationale into a refutation record and emits it back to Trace. Future search runs immediately inherit these lessons.

---

## 4. Integration with STC (Execution Factory)

When running within the broader autonomous engineering ecosystem, SST hands off execution to Spec-To-Code (STC):
- **Leased Worktrees**: STC provisions isolated, copy-on-write Git worktrees for each active MCTS branch.
- **Substrate Gates**: STC provides rigorous multi-stage gate evaluation (`ruff`, `mypy --strict`, `pytest`, and `mutmut` mutation testing).
- **Notary Receipts**: STC signs verified candidate receipts before SST permanently marks the node `PROMOTED`.
