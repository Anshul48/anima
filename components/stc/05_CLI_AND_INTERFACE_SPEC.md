# STC: Biomimetic Spec-to-Code Autonomous Engineering Engine
## Volume 05: CLI & Interface Specification (Click + Rich + JSON Automation)

> **System:** STC (Spec-To-Code)  
> **Project Directory:** `code/utilities/stc`  
> **Tooling:** `click`, `rich`, Python 3.12+  
> **Status:** `[DECIDED]`  
> **Interface Standard:** Dual-mode design: Rich visual terminal UI for Human Sovereign interactive steering, and pure streamable JSON stdout for headless automation (`dsh`, CI/CD, agent scripts).

---

## 1. Global CLI Architecture

The CLI binary `stc` is exposed via entrypoints configured in `pyproject.toml`:
```bash
stc [GLOBAL_OPTIONS] COMMAND [ARGS]...
```

### Global Flags
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--verbose` | `-v` | `False` | Enable DEBUG level logs and subshell command traces. |
| `--json` | `-j` | `False` | Output pure JSON to stdout (suppresses Rich styles and spinners). |
| `--root` | `-r` | `.` | Root path of the target software repository. |
| `--trace-db` | | `../trace/data/trace.db` | Explicit path to the Project Trace SQLite database. |

---

## 2. Command Hierarchy & Terminal Ergonomics

### 2.1 Command: `stc spec` (Intake & Socratic Elicitation)
Parses a raw specification, builds the Tree of Concerns (TOC), and presents interactive Archetype Diffs if ambiguities exist.

```bash
stc spec ./specs/feature_rrf.md
```

#### Terminal Interaction (Rich Mode):
```
┌──────────────────────── Tree of Concerns: feature_rrf ────────────────────────┐
│ Dimensions Evaluated:                                                         │
│  • Domain Invariants:        4 rules detected                                 │
│  • Persistence & Storage:    SQLite FTS5 + Flat Vector Arrays                 │
│  • Communication Protocols:  PEP 544 FusionEngine Protocol                    │
│  • Boundary & Security:      Internal package memory boundary                 │
│  • Failure Resilience:       Zero division damping guard                      │
│                                                                               │
│ Ambiguity Score: 0.45 [THRESHOLD EXCEEDED: >= 0.30]                           │
└───────────────────────────────────────────────────────────────────────────────┘

[?] ARCHETYPE DILEMMA DETECTED: Tied Rank Normalization Strategy
  (1) Archetype Alpha (Deterministic Strict):
      Breaks ties by secondary document ID ascending. 100% reproducible order.
  (2) Archetype Beta (Averaging Rank):
      Averages ranks across tied candidates. Standard statistical treatment.

Select choice [1/2]: 1
[+] Invariant locked: "Tied fusion ranks MUST break ties using doc_id ASC."
[+] Written to specs/invariants/STC-001_INVARIANTS.md
```

### 2.2 Command: `stc compile` (Context Compilation)
Queries the Neocortex and Hippocampus (Trace DB) to compile a hyper-targeted, sub-25KB `task_bundle.yaml`.

```bash
stc compile STC-001 --spec ./specs/feature_rrf.md --out ./artifacts/task_bundle.yaml
```

#### Verification & Budget Checks:
- Checks total bundle size. If $> 25\text{KB}$, compilation fails with non-zero exit code:
  ```
  [!] CRITICAL: Task bundle size (28,410 bytes) exceeds 25,600 byte ceiling!
  [-] Hierarchical context pruning triggered...
  [+] Pruned 4 redundant historical traces.
  [+] Final bundle size: 21,450 bytes. (PASS)
  [+] Saved to artifacts/task_bundle.yaml
  ```

### 2.3 Command: `stc worktree` (Leased Worktree Lifecycle)
Allocates, inspects, and cleans isolated Git worktrees.

```bash
# Allocate a leased worktree for a task
stc worktree lease STC-001 --branch feature/stc-001-rrf

# List all active worktree leases
stc worktree list

# Release and clean a worktree
stc worktree release STC-001 --purge
```

#### Headless JSON Output (`--json`):
```json
{
  "lease_id": "lease_7a8b9c",
  "task_id": "STC-001",
  "worktree_path": "<workspace-root>/stc/worktrees/stc-001",
  "branch_name": "feature/stc-001-rrf",
  "status": "ACTIVE",
  "expires_at": "2026-09-03T11:15:00Z"
}
```

### 2.4 Command: `stc gate run` (Substrate Mechanical Gates)
Executes deterministic tests and static analysis inside the leased worktree.

```bash
stc gate run STC-001 --all
```

#### Progress & Gate Summary (Rich UI):
```
Running Mechanical Substrate Gates on worktrees/stc-001...
  [✓] Gate 1: Ruff Linter & Formatter (0.18s) - 0 violations
  [✓] Gate 2: Mypy Strict Type Check   (1.42s) - 0 errors
  [✓] Gate 3: Pytest Verification      (2.11s) - 18/18 passed (100%)
  [✓] Gate 4: Mutmut Mutation Testing  (5.80s) - Score: 91.3% (Killed: 21/23)

[+] All Substrate Gates PASSED.
[+] Cryptographic receipt generated: artifacts/receipts/rcpt_STC-001.json
[+] SHA256: 9b71d224bd62f3785d96d46ad3ea3d73319bfbc2890caadae2dff72519673ca7
```

### 2.5 Command: `stc judge` (Trias Politica Judiciary Audit)
Triggers a blind, adversarial Codex review of the diff against locked invariants.

```bash
stc judge STC-001 --receipt ./artifacts/receipts/rcpt_STC-001.json
```

#### Judiciary Output:
```
Dispatching Blind Judiciary Auditor (Codex CLI)...
Audit Target: diff between main and feature/stc-001-rrf (42 lines changed)
Context: 0 worker chats provided (Strict Blind Audit)

[✓] Mock Infiltration Check: Passed (Real SQLite statements detected)
[✓] Silent Fallback Check: Passed (Zero empty except blocks)
[✓] Invariant Compliance: Passed (doc_id ASC tie-break verified in test_fusion.py:48)

VERDICT: APPROVED
Receipt endorsed by Judiciary.
```

### 2.6 Command: `stc promote` (Sovereign Merge & Genome Ingestion)
The final promotion gate. Requires Sovereign confirmation, merges to `main`, and logs positive genes and negative inhibitors to the Trace DB.

```bash
stc promote STC-001
```

```
[?] Sovereign Merge Authority Required.
  Task: STC-001 (Reciprocal Rank Fusion)
  Commit: e4d3c2b1 (42 lines changed, 4 tests added)
  Receipt: rcpt_STC-001.json (VERIFIED)
  Judiciary: APPROVED

Merge to main? [y/N]: y
[+] Merged branch feature/stc-001-rrf to main.
[+] Ingested 1 Structural Gene and 1 Behavioral Gene into Trace Genome DB.
[+] Released worktree worktrees/stc-001. Task STC-001 COMPLETED.
```

### 2.7 Command: `stc run` (End-to-End Orchestrated Pipeline)
Executes the full DAG from raw spec to promotion candidate.
```bash
stc run ./specs/feature_rrf.md --non-interactive --fail-fast
```
