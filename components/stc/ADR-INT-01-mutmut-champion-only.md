# ADR-INT-01: Mutmut Mutation Testing on Merged Champion Only

- **Status:** RATIFIED
- **Date:** 2026-09-13
- **Authority:** Human Sovereign (Vanguard Architect) via Grill T2 Ratification
- **Contract Revision:** INT-2026-09-13.2 (Decisions D4, D13; Requirements R4; BT-17)
- **Target Component:** `stc` substrate runner / execution engine (`01_INVARIANTS.md` §5)

---

## Context

STC Master Program Invariants (`01_INVARIANTS.md` §5) define four deterministic substrate quality gates that every candidate must satisfy with machine-verifiable receipts:
1. **Gate 1:** Code Hygiene & Formatting (`ruff check` & `ruff format --check`)
2. **Gate 2:** Static Type Soundness (`mypy --strict src/`)
3. **Gate 3:** Deterministic Test Suite (`pytest -v --tb=short`, 100% pass, zero skip)
4. **Gate 4:** Mutation Robustness (`mutmut run`, kill rate $\ge 85\%$)

In the dialectic search engine introduced for M1 (`stc-integration`), multiple candidate branches and proposals are generated, critiqued, and mutated across leased worktree cells. Executing a full mutation analysis suite via `mutmut` on every intermediate search node imposes severe compute and latency bottlenecks ($O(N)$ full mutation passes across the candidate tree), choking candidate exploration.

During architectural deliberation (Grill T2), the Sovereign Vanguard weighed search exploration latency against the risk of mock gaming, deciding that mutation robustness remains an indispensable defense against artificial test generation, but can be applied selectively without weakening assurance.

---

## Decision

1. **Scope:** M1 dialectic search loop (`stc-integration`) only.
2. **Intermediate Search Nodes:** Quality gates evaluated per candidate node during tree search are restricted to Gates 1–3:
   - Gate 1: Ruff hygiene & formatting (exit code 0).
   - Gate 2: Mypy strict type soundness (exit code 0).
   - Gate 3: Pytest deterministic suite (exit code 0; live tests tagged `@pytest.mark.live` deselected per D13 to maintain deterministic zero-skip invariant).
   - Gate 4 (`mutmut`) is **omitted** from per-node `hard_gates` registers or recorded with a documented fingerprinted non-execution marker.
3. **Merged Champion Evaluation:** Gate 4 (`mutmut run` with kill rate $\ge 85\%$) executes **exclusively on the final merged champion proposal** before Judiciary review and final promotion.
4. **Receipt Generation:** The Execution Receipt for the champion candidate must include the full cryptographic receipt from the Gate 4 mutation run.

---

## Invariants Preserved

- `01_INVARIANTS.md` §§1–4, 6–7 remain completely unchanged.
- Gate 4 kill rate threshold remains strictly $\ge 85\%$ (the single normative bar).
- No mock gaming: synthetic or superficial mock assertions remain grounds for immediate adversarial rejection by the Judiciary.

---

## Reversion Condition

If champion-only mutation testing proves insufficient in practice—specifically, if mock gaming or superficial test suites survive intermediate dialectic search and routinely cause champion rejection at the final boundary, or if undetected defects pass into candidate promotion—this amendment shall immediately revert, and Gate 4 mutation testing will be re-instated at earlier search boundaries or on targeted candidate slices.
