# STC Master Program Invariants (Neocortex Ground Truth)

> **Status:** `[DECIDED]` & Ratified Neocortex Immutable Ground Truth  
> **System:** STC (Biomimetic Spec-To-Code Autonomous Engineering Engine)  
> **Target Environment:** Python 3.12+, `uv`, SQLite FTS5, Git Worktrees, Project Trace, Cordis Microkernel  
> **Authority:** Human Sovereign & Vanguard Architect  
> **Rule of Inviolability:** Executive worker agents and autonomous subagents are strictly forbidden from modifying or loosening any rule in this document. Any amendment requires explicit human sovereign ratification under an architectural decision record (ADR).

---

## 1. Constitutional Trias Politica & Separation of Powers

The STC autonomous engineering factory operates under a strict, non-negotiable **Separation of Powers**:

1. **The Sovereign Branch (Human Vanguard):**
   - Holds sole authority to establish invariants, resolve architectural dilemmas via Archetype Diffs, approve spec promotions, and merge code to `main`.
   - Never accepts natural-language declarations of task completion without machine-verified cryptographic receipts.

2. **The Executive Branch (Coding Workers / `agy` / Aider):**
   - Operates exclusively inside isolated, leased Git worktrees (`worktrees/stc-{task_id}`).
   - Prohibited from self-certifying. A worker model may never act as its own tester, verifier, or judge.
   - Prohibited from committing or merging directly into `main` or shared working branches.
   - Prohibited from generating or inserting superficial mock tests (`assert mock == True`) to fake gate passage.

3. **The Substrate Branch (Deterministic Quality Engines):**
   - Consists of machine executables (`uv run ruff`, `uv run mypy --strict`, `uv run pytest`, `uv run mutmut`).
   - Executes deterministically with fail-closed semantics: any exit code $\ne 0$ halts promotion immediately.
   - Emits tamper-evident, SHA-256 signed `ExecutionReceipt` structures.

4. **The Judiciary Branch (Blind Adversarial Auditor / Codex CLI / Fresh Isolated Session):**
   - Audits candidate pull requests in a fresh, isolated sandbox without conversational history or worker chat transcripts.
   - Operates with an explicit mandate of adversarial rejection: actively searches for mock infiltration, silent fallbacks (`try ... except: pass`), disabled assertions, and contract tampering.

---

## 2. Dual-Tier Cognitive Memory & Context Compilation

To eliminate the $O(N^2)$ context rot trap and LLM attention saturation, memory is partitioned into two distinct physical stores:

1. **Permanent Semantic Memory (Neocortex):**
   - Files: `01_INVARIANTS.md`, `src/stc/schemas/models.py`, `src/stc/protocols/interfaces.py`.
   - Immutable truth representing compile-time genotype. Never modified during task execution.

2. **Episodic Trace Store (Hippocampus):**
   - Project Trace physical SQLite database tables (`documents`, `attachments`, `atoms`, `proposals`, `events`, `lexical_fts`).
   - Append-only recording of execution traces, code diffs, and historical failure proofs.

3. **The Context Compilation Rule ($O(1)$ Retrieval):**
   - Context is **retrieved on-demand ($O(1)$)**, never **accumulated ($O(N^2)$)**.
   - The Context Compiler synthesizes atomic `TaskBundle` artifacts strictly bounded by a **25,600-byte (25 KB) hard ceiling**.
   - Workers receive only: exact goal, target file byte/line boundaries, membrane protocols, active invariants, and relevant negative inhibitor genes.

---

## 3. Cellular Morphogenesis & Rigid Typed Membranes

1. **Membranes Over Monoliths:**
   - Every subsystem interacts exclusively across PEP 544 `typing.Protocol` interfaces and frozen Pydantic V2 schemas (`ConfigDict(frozen=True, extra="forbid")`).
   - Direct cross-subsystem concrete class imports are forbidden.

2. **Worktree Cell Isolation:**
   - Every active task is allocated a leased Git worktree under `worktrees/stc-{task_id}`.
   - Worktrees have a default 1-hour time-to-live (TTL). Expiry follows an explicit transition: `Leased → Expired → Quarantined` — the worktree is frozen for inspection and its refutation recorded; resuming requires a brand-new lease record, never silent reuse. Expired or abandoned worktrees are quarantined and pruned.

3. **Cross-OS Execution Neutrality:**
   - Files may be edited across Windows filesystem paths.
   - Database operations, deterministic test suites, and mutation testing must maintain cross-OS parity. Tooling requiring Linux features (e.g. `mutmut`) must execute via WSL or Linux containers with path translation.

---

## 4. Scoped Pub/Sub Hormone Protocol

To prevent **Hormone Broadcast Storms** (where a failure signal causes multiple unrelated agents to panic and rewrite code):

1. **Zero Global Natural Language Broadcasts:**
   - Signals such as `CONTRACT_DRIFT`, `TEST_FAILURE`, `CONCURRENCY_PRESSURE`, or `SCHEMA_MUTATION` must be emitted as strictly typed `HormoneEvent` models with SHA-256 payload hashes.
   - Events must specify an explicit `HormoneScope` (producer ID, target consumer IDs, and topic boundary).

2. **Receptor Matching:**
   - Only immediate consumer-provider pairs with registered receptors receive and process a published hormone event. Unrelated subsystem cells never receive foreign signals.

---

## 5. Deterministic Substrate Quality Gates & Machine Receipts

Software eligibility for review is governed by 4 mechanical gates:

| Gate | Tool | Command Line | Exit Criterion |
| :--- | :--- | :--- | :--- |
| **Gate 1: Code Hygiene & Formatting** | Ruff | `uv run ruff check .` && `uv run ruff format --check .` | Exit Code == 0 (0 warnings, 0 lint errors) |
| **Gate 2: Static Type Soundness** | Mypy | `uv run mypy --strict src/` | Exit Code == 0 (0 type errors, 0 Any leaks) |
| **Gate 3: Deterministic Test Suite** | Pytest | `uv run pytest -v --tb=short` | Exit Code == 0 (100% pass, 0 failed, 0 skipped) |
| **Gate 4: Mutation Robustness** | Mutmut | `uv run mutmut run` (via WSL / Linux container) | Kill rate $\ge 85\%$ — the single normative bar (kills trivial mock gaming). `0 surviving mutants` is additionally required only for the Stage-1 RRF anchor slice (see `05_CLI_AND_INTERFACE_SPEC.md` worked example). |

### Receipt Signing Invariant
- The Substrate Runner must compute a SHA-256 hash over the canonical JSON representation of all gate reports, commit hash, task ID, correlation ID, and environment metadata.
- An altered or forged receipt invalidates the candidate instantly.

### Normative Threshold Register (sole definition — all volumes reference this)
- `tau = 0.30`: an ambiguity score at or above this halts compilation and triggers `ArchetypeDiff`.
- Mutation kill rate `≥ 85%`: the Gate 4 bar. `0 surviving mutants`: Stage-1 RRF anchor slice only.

---

## 6. Trace Genetic Memory & Negative Inhibitors

1. **Software Genetics:**
   - Relying on LLM weights alone causes regression to the statistical median of public code.
   - Verified implementations are cataloged as **Structural Genes** (interfaces/schemas) and **Behavioral Genes** (proven algorithms) in Project Trace SQLite.

2. **Negative Inhibitor Genes:**
   - Every refuted design, deadlock bug, or failed architecture is hashed into `proposals` with `status='REFUTED'` and `proposal_type='negative_inhibitor'`.
   - The Context Compiler MUST inject relevant negative inhibitors into the `TaskBundle` before coding begins.

---

## 7. Invariant Enforcement Matrix

| Invariant | Design Requirement | Required Evidence | Violation Response |
| :--- | :--- | :--- | :--- |
| **Trias Politica** | No worker may certify its own work. | Independent `ExecutionReceipt` + Judiciary verdict. | Candidate rejected; worktree wiped. |
| **Context Ceiling** | `TaskBundle` $\le 25,600$ bytes. | Byte measurement check in bundler. | Throw `BundleSizeExceededError`; prune. |
| **Zero Mock Policy** | Unit tests must not mock internal domain logic. | Mutmut mutation kill score $\ge 85\%$. | Quarantine branch; flag mock gaming. |
| **Fail-Closed Gates** | All 4 substrate gates must exit 0. | Machine `ExecutionReceipt.is_passing == True`. | Candidate denied review. |
| **Cryptographic Provenance** | Receipts and task bundles must have correlation IDs. | Bit-exact SHA-256 signature verification. | Candidate treated as untrusted. |
| **Scoped Hormones** | No global error broadcast storms. | Typed `HormoneEvent` with explicit `HormoneScope`. | Reject untyped chatter signals. |
| **Trace Genetic Epigenetics** | Refuted patterns saved as negative inhibitors. | Row in `proposals` table with `REFUTED` status. | Compiler blocks repeat flawed designs. |

---

## 8. Epistemic Status & Governance Register

- **Current Version:** `1.0.0`
- **Ratification Date:** September 2026
- **Amendments:** Requires Sovereign approval, formal Git commit on `main`, and synchronization across all active worktrees.
