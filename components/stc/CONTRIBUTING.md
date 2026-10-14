# Contributing to STC (Spec-to-Code)

Thank you for contributing to **STC**! STC is a production-grade, distributed autonomous engineering engine implementing the **Biomimetic Spec-to-Code Architecture**.

To maintain our zero-defect engineering standard, all contributions are governed by strict mechanical quality gates, the Trias Politica separation of powers, and the normative invariants defined in [`01_INVARIANTS.md`](01_INVARIANTS.md).

---

## 🏛️ Ground Rules & Constitutional Invariants

All code submitted to STC must comply with the normative invariants in [`01_INVARIANTS.md`](01_INVARIANTS.md):

1. **Separation of Powers (Trias Politica):**
   - **Legislative / Sovereign (Human):** Holds exclusive merge authority (`stc promote`).
   - **Executive / Builder (Worker):** Implements code exclusively within leased Git worktrees (`worktrees/stc-{task_id}`).
   - **Judicial / Critic (Auditor):** Performs blind, adversarial audits without access to builder chat history (`stc judge`).

2. **Bounded Context & Slicing:**
   - Tasks must never exceed the hard **25,600-byte (25 KB)** context ceiling.
   - Context is compiled deterministically through Neocortex invariants and Hippocampal memory (Project Trace).

3. **Subsystem Membrane Isolation:**
   - Cross-subsystem communication must use **PEP 544 typed protocols** (`src/stc/protocols/interfaces.py`) and **frozen Pydantic V2 schemas** (`src/stc/schemas/models.py`).
   - Direct concrete imports across subsystem boundaries are strictly forbidden.

4. **Zero-Mock Policy:**
   - No `unittest.mock`, `MagicMock`, or monkey-patching in domain logic, storage, or execution tests.
   - Tests must run against real physical substrate fixtures (ephemeral SQLite databases, real Git repositories, real subprocess gates).

5. **Fail-Closed Execution:**
   - Bare `except:` clauses, `except Exception: pass`, and silent fallback returns (`return []`, `return None`) are prohibited.
   - Failures must bubble up typed exceptions derived from `STCError`.

---

## 🚀 Development Setup

STC uses [uv](https://docs.astral.sh/uv/) for lightning-fast, reproducible dependency management.

### Prerequisites
- Python 3.12+
- `uv` (v0.12+)
- Git 2.45+ (with worktree support)

### Initial Setup
```bash
# Clone the repository
git clone https://github.com/Anshul48/stc.git
cd stc

# Install virtual environment and all dependency groups
uv sync --all-groups

# Configure environment
cp .env.example .env
```

---

## 🛡️ Mechanical Quality Gates (Substrate Gates)

Before submitting any code, verify that all four deterministic substrate gates pass with exit code 0:

```bash
# Gate 1: Code hygiene, formatting, and linting
uv run ruff check .
uv run ruff format --check .

# Gate 2: Static type soundness (strict mode, zero Any leaks)
uv run mypy --strict src/ tests/

# Gate 3: Deterministic test suite (100% pass, 0 failed, 0 skipped)
uv run pytest -v

# Gate 4: Mutation robustness testing (target: >= 85.00% kill rate)
uv run mutmut run
```

---

## 🌿 Worktree Lease Protocol

When developing new features or bug fixes:

1. **Allocate a Leased Worktree:**
   ```bash
   uv run stc worktree lease TASK-001 --branch feature/task-001
   ```
2. **Implement your changes inside the leased worktree directory (`worktrees/stc-TASK-001`).** Never modify `main` directly.
3. **Run mechanical gates inside the worktree:**
   ```bash
   uv run stc gate run TASK-001 --all
   ```
4. **Inspect machine receipt:**
   ```bash
   uv run stc receipt show ./artifacts/receipts/rcpt_TASK-001.json
   ```
5. **Run the blind judicial audit:**
   ```bash
   uv run stc judge TASK-001 --receipt ./artifacts/receipts/rcpt_TASK-001.json
   ```
6. **Submit PR or promote:**
   Only the Human Sovereign merges changes to `main`.

---

## 📋 Pull Request Requirements

When opening a Pull Request:

1. **Clear Title & Conventional Commit:** e.g., `feat(compiler): add negative inhibitor injection` or `fix(worktree): handle win32 lock contention`.
2. **Machine Receipt:** Include a verifiable `receipt.json` showing all gates exit 0.
3. **No Contract Tampering:** Ensure protocols in `src/stc/protocols/interfaces.py` and models in `src/stc/schemas/models.py` only tighten, never weaken, invariants.
4. **Scope Discipline:** PRs must be cleanly scoped to specific task deliverables.

---

## 📜 Architectural References

Before modifying architecture or protocols, review the core volumes:
- [`01_INVARIANTS.md`](01_INVARIANTS.md): Non-negotiable constitutional invariants and threshold register.
- [`02_EXECUTION_DAG.md`](02_EXECUTION_DAG.md): 22-node execution DAG lifecycle.
- [`03_LOSSLESS_SUBSYSTEM_SPECS.md`](03_LOSSLESS_SUBSYSTEM_SPECS.md): Subsystem engineering specifications.
- [`04_DATA_CONTRACTS_AND_SCHEMAS.md`](04_DATA_CONTRACTS_AND_SCHEMAS.md): Data models and typed protocols.
- [`07_ROLLOUT_FLIGHT_PLAN.md`](07_ROLLOUT_FLIGHT_PLAN.md): Rollout stages and operating cadence.
- [`08_CHAPERONE_AND_EXECUTION_ENGINE.md`](08_CHAPERONE_AND_EXECUTION_ENGINE.md): Chaperone worker execution engine.
