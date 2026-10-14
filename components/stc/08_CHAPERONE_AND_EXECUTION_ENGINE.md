# Chaperone: Execution Engine & Blind Notary (STC Subordinate Plan)

> **Status:** `[PROPOSED]`
> **Parent plan:** STC (`01_PLAN_BROAD_STROKES.md` §Positioning, ADR-007)
> **Rename:** `auto` + `auto-lite` → **Chaperone**

---

## 1. Genesis Ground Truth (preserved, not overturned)

- `auto`: ~2% real (schemas + empty CLI skeletons), **98% mock — `[REJECTED]`, cold-storage quarantine.** No engineering cycles to finish it as a builder.
- `auto-lite`: ~5% real (Pydantic CLI wrapper, requires `--patch`, zero LLM loops), **`[REJECTED]` as builder**, frozen read-only; **`[PROPOSED]` future as passive blind cryptographic notary.**
- Source: `03_WORKSPACE_REALITY_AUDIT_AND_TOOLS.md`, `05_DEEPSEEK_HARNESS_AND_CORDIS.md`.

The rename changes **role and name**, never these verdicts: Chaperone must not become another builder/orchestrator (that repeats the Architecture Astronaut Recursion the genesis rejects).

## 2. Role Split: STC (new auto) vs Chaperone (old auto)

| Concern | STC (orchestrator, new `auto`) | Chaperone (execution engine, old `auto`) |
| :--- | :--- | :--- |
| DAG order, leases, gates | Owns (N01–N22, `02_EXECUTION_DAG.md`) | Obeys; never reorders |
| Worker CLI execution | Never shells workers directly (ADR-007) | Runs `agy`/`aider`/`dsh` inside the leased worktree via `WorkerProtocol` |
| Custody attestation | Verifies receipts | Emits file-custody facts: what changed, by which lease, no unauthorized paths (notary role) |
| Merge authority | Sovereign only (N20) | None — cannot commit to `main` |

## 3. DAG Touchpoints

- **N10 lease:** Chaperone receives the lease record; confinement root = `worktrees/stc-{task_id}`.
- **N11 membrane:** Chaperone proves upstream `src/stc/protocols/interfaces.py` + `src/stc/schemas/models.py` present before dispatch.
- **N12 dispatch:** sole Chaperone-owned node; all worker I/O stays under the lease root (zero writes outside).
- **N17 receipts:** Chaperone supplies raw gate outputs; STC substrate signs.

## 4. Non-goals

- No spec compilation, no invariant authorship, no judiciary role, no promotion.
- No new LLM agent runner (reuse `agy`/`aider`/`dsh` per ADR-001).
- No Praxist coupling: Chaperone executes commanded work; optimization (if ever) sits above STC, post-Stage-5.

## 5. Acceptance

- [ ] `WorkerProtocol` implemented by the Chaperone runner; confinement test (write outside lease root fails closed).
- [ ] Notary custody report per lease: file list + hashes + lease id, verified against N11 receipt.
- [ ] Zero builder semantics: no prompt management, no test repair, no orchestration state.
