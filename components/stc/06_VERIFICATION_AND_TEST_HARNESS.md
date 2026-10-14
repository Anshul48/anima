# STC: Biomimetic Spec-to-Code Autonomous Engineering Engine
## Volume 06: Verification & Test Harness Specification

> **System:** STC (Spec-To-Code)  
> **Project Directory:** `code/utilities/stc`  
> **Test Frameworks:** `pytest`, `pytest-asyncio`, `pytest-cov`, `mutmut`, `hypothesis`  
> **Coverage Invariant:** Branch coverage $\ge 90\%$, Zero-Mock Policy on core business logic, 100% typechecked (`mypy --strict`)  
> **Status:** `[DECIDED]`  

---

## 1. The Zero-Mock Verification Philosophy

In traditional agentic development, tests heavily rely on `unittest.mock.MagicMock` or `pytest-mock`, allowing agents to deceive themselves into believing code functions when dependencies fail.

### STC Verification Invariants:
1. **Real SQLite Databases:** Tests interacting with Project Trace or SQLite FTS5 must use temporary physical SQLite databases (`tmp_path / "test.db"`) with real schema migrations and real SQL queries.
2. **Real Git Worktrees:** Tests for `stc.worktree` must execute against temporary real Git repositories initialized with `git init` and real commits. No mocking `subprocess.run` to fake git exit codes.
3. **Hermetic Subprocesses:** Quality gates test real tool invocations (`ruff`, `mypy`, `pytest`).
4. **Adversarial Mutation Testing:** All test suites must be evaluated under `mutmut` to ensure tests fail when operators or comparison logic are inverted.

---

## 2. Test Suite Matrix

```
tests/
├── conftest.py                       # Global fixtures (temp git repos, sqlite dbs)
├── unit/
│   ├── test_schemas.py               # Pydantic V2 validations and immutability
│   ├── test_socratic.py              # TOC decomposition & ambiguity heuristics
│   ├── test_compiler.py              # Context compilation & 25KB budget gate
│   ├── test_worktree.py              # Worktree lease, branch isolation, TTL
│   ├── test_substrate.py             # Ruff/mypy/pytest gate runners & receipts
│   ├── test_judiciary.py             # Mock detection & silent fallback regexes
│   └── test_genome.py                # Trace gene ingestion & query
└── integration/
    ├── test_dag_pipeline.py          # End-to-end DAG execution from spec to receipt
    ├── test_circuit_breaker.py       # Gate failures, rollback, and epoch bounding
    └── test_cross_os_compat.py       # CRLF vs LF line endings & Windows paths
```

### 2.1 Key Unit Test Scenarios

#### `test_schemas.py`
- Verify that modifying attributes on `SpecAtom`, `TreeOfConcerns`, or `ExecutionReceipt` raises `pydantic.ValidationError` (enforcing `frozen=True`).
- Verify that `SpecAtom` enforces 64-character SHA256 checksums.
- Verify that `TaskBundle` rejects empty or whitespace-only `goal_statement`.
- Verify that `ExecutionReceipt.is_passing` returns `True` if and only if all gate exit codes are `0`.

#### `test_socratic.py`
- Test decomposition of a complete specification: all 5 dimensions populated with $>0$ items, resulting in `ambiguity_score < 0.30`.
- Test decomposition of an incomplete specification (e.g. missing error handling): verify `ambiguity_score >= 0.30` and triggers generation of exactly two `ArchetypeOption` objects.
- Verify archetype options present contrasting choices (conservative fail-closed vs resilient grace window).

#### `test_compiler.py`
- Test context compilation under the 25KB limit: bundle serialized to YAML must measure $\le 25,600$ bytes.
- Test context pruning: when injected traces exceed 25KB, the compiler must automatically drop low-ranking episodic traces while preserving Neocortex invariants.
- Test negative inhibitor injection: verify that past failure records appear in `task_bundle.negative_inhibitors`.

#### `test_worktree.py`
- Test allocation of a leased worktree: verify physical directory creation at `worktrees/stc-{task_id}`, verify clean `git status`, verify branch created at `feature/stc-{task_id}-e{epoch}`.
- Test release and purge: verify directory removal and branch pruning.
- Test lease collision: attempting to lease an already leased worktree raises `WorktreeLeaseActiveError`.

#### `test_substrate.py`
- Test execution of gate suite: verify correct capture of stdout, duration, and exit code.
- Test cryptographic signing: verify `receipt.sha256_signature` is a valid HMAC-SHA256 hash of the receipt payload.
- Test receipt tampering: altering 1 character in `receipt.json` causes `stc.substrate.verify_receipt` to return `False`.

#### `test_judiciary.py`
- Test mock detection: diff containing `unittest.mock.patch` or `MagicMock` on storage entities flags `CRITICAL` finding.
- Test silent fallback detection: diff containing `except Exception: pass` or `except: return []` flags `CRITICAL` finding.
- Test invariant compliance: diff adhering to locked invariants passes with `APPROVED` status.

---

## 3. Integration & Chaos Test Scenarios

### 3.1 Scenario: Bounded Epoch Circuit Breaker (`test_circuit_breaker.py`)
1. Create a synthetic test file that deliberately fails a substrate gate (e.g. introduces a type error in `src/`).
2. Run `stc.orchestrator.execute_dag()`.
3. Assert that Gate 2 (`mypy`) exits with code `1`.
4. Assert that `ExecutionReceipt.is_passing` is `False`.
5. Assert that the pipeline rolls back to Node N09 (Context Compilation) with `epoch_index = 2`.
6. Inject the failure diagnostic into `negative_inhibitors`.
7. Repeat failure until `epoch_index > 3`.
8. Assert that the pipeline quarantines the task, freezes the worktree, and halts without entering an infinite loop.

### 3.2 Scenario: Cross-OS Neutrality (`test_cross_os_compat.py`)
1. Ingest files with Windows `\r\n` (CRLF) line endings.
2. Run `stc spec` and `stc compile`.
3. Verify output files are normalized to standard UTF-8 and POSIX `\n` (LF).
4. Verify SQLite storage handles Windows absolute paths with backslashes (`C:\...`) and forward slashes (`C:/...`) equivalently.

---

## 4. Mutation Testing Standards (`mutmut`)

STC includes configuration for `mutmut` in `pyproject.toml`:
```toml
[tool.mutmut]
paths_to_mutate = "src/stc/"
backup = false
runner = "pytest -v --tb=no"
tests_dir = "tests/unit/"
```

### Mutation Survival Rules:
- Any surviving mutant in `stc.schemas` or `stc.substrate` is an automatic CI failure.
- Tests must detect:
  - Boundary mutations (`<` changed to `<=`)
  - Arithmetic mutations (`+` changed to `-`)
  - Boolean mutations (`True` changed to `False`)
  - Inverted condition checks (`if x` changed to `if not x`)
