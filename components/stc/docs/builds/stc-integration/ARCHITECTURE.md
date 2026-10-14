# STC Integration — Architecture (M1)

Contract: PROJECT.md `INT-2026-09-14.1` (fix tranche; M1 body @ .2 unchanged
except the deltas marked FIX below). This is the A2 design record.
Review status: A3 passed with dispositions (DESIGN_REVIEW.md); all 64 findings
disposed; 2 operator decisions folded in (D11, D14). A2-revisit 2026-09-14
added D15 + fix deltas (design: evidence/A2-revisit/REVIEW.md); M1 record immutable.

## 1. End-to-end behavior (with failure)

Operator runs `stc run specs/<real-stc-task>.md --target stc --dry-run` first
(zero model calls), then live. The CLI ingests the spec into a `SpecAtom`,
decomposes it into a `TreeOfConcerns`, and compiles one `TaskBundle` (≤25,600
bytes) per work item. Each bundle is projected to an SST `TaskPacket` (P01
disposition table governs every field); SST's controller searches candidates
with proposal/critique generation served by the CLI-backed gateway (D10);
every candidate verifies through the STC-side custody wrapper, which runs STC
substrate gates (ruff, mypy --strict, pytest) in a leased worktree; the
champion (possibly colimit-synthesized, with synthesis receipt) runs mutmut
once; the blind judiciary audits the final diff; the run ends with diff +
`ExecutionReceipt` + `JudiciaryVerdict` + review record + spend log.

Important failure: search exhausts with no passing candidate. Then the runner
returns a typed `NoChampionResult` with branch evidence refs; P05 renders a
partial NEEDS_REPAIR dossier (never the 5 success artifacts); the tranche
closes honest-partial with a named A2-revisit action.

## 2. Components and data flow

```text
spec.md → [ingest] → SpecAtom → [socratic] → TreeOfConcerns → [compile] → TaskBundle(s)
   │                     (prompt-kit grill templates assist intake; heuristic only)
   ▼
TaskBundle → [P01 projection] → SST TaskPacket → [SST controller] → CandidateProposal(s)
   │              (disposition table,   (gateway = CLI backend;
   │               AdapterContext)       DIVERGE/REFINE/CRITIQUE/SYNTHESIZE)
   ▼
CandidateProposal → [STC custody wrapper] → leased worktree → [substrate gates]
   │                (wraps verify_candidate_   (ruff/mypy/pytest per node;
   │                 proposal; D7-legal)        mutmut champion-only)
   ▼
ScoreBreakdown (native vocab + stc_* keys; coarse reward) → champion (+ synthesis receipt)
   ▼
champion → [mutmut once] → [judiciary, with_codex=False] → [dossier] → operator
```

State ownership:

| State | Owner | Notes |
| --- | --- | --- |
| SpecAtom, TreeOfConcerns, TaskBundle | STC schemas (existing) | Frozen; ≤25.6 KB ceiling enforced |
| TaskPacket, CandidateProposal, ScoreBreakdown, SSTree | SST core (existing) | Search-local; never edited by STC in place |
| AdapterContext, disposition table, reward rule | NEW `stc/integration/adapters.py` (P01) | Projection (not round-trip); reward = hard-gate fraction |
| Lease, custody report, ExecutionReceipt | STC worktree/substrate (existing) | Receipt is the acceptance authority |
| Memory shim contents | NEW file-backed store (P02) | `[source:path]`-first excerpts; `*` = match-all; HEAD/as-of stamps |
| Harness worker + CLI gateway backend | NEW (P03) | Implements `WorkerProtocol`; gateway backend implements ModelGateway invoke path; both spend-logged |
| Search orchestration | NEW `DialecticRunner` (P04) | Drives controller; owns store under evidence/P04; champion-veto; NoChampionResult |
| CLI + dossier | `stc run` extension (P05) | Self-hosted acceptance on STC; TL absent (D11) |

Interfaces and meanings:

- `WorkerProtocol.dispatch(bundle, lease) -> str`: the ONLY path by which model
  output enters a worktree (ADR-007). P03's `HarnessWorker` wraps a prompt-kit
  `BaseHarness.execute(prompt, role, model, context)` call with
  `context["project_root"]=str(lease_root)` (F7 fix), checks `is_success`,
  enforces a dispatch timeout, and quarantines on breach. Chaperone snapshots
  cover repo_root + parent + .git/{refs,hooks,config,worktrees} (tripwire
  scope, honestly claimed — OS sandbox is post-M1).
- Custody wrapper (D9): STC-side subclass/wrapper of
  `CandidateCustodyManager.verify_candidate_proposal(task, proposal,
  source_dir, acceptance_command, timeout)` that applies the proposal via the
  parent logic, then runs STC substrate gates in a per-node lease instead of
  `acceptance_commands[0]`. No SST edits. `test_command` declared ignored.
- CLI gateway backend (D10): implements the ModelGateway invocation path used
  by the controller (diverge/refine/critique/synthesize) by delegating to a
  prompt-kit CLI harness. Every call counted in budgets and the spend log.
  Fixture mode uses SST mock; live mode uses this backend (never raw API keys
  without operator approval per R5).
- FIX (D15, .1): gateway live calls use the TEXT-EMISSION profile, not the
  worker shape — role-conditioned argv (`-s read-only`, `-C <fresh scratch
  dir>`, `--output-schema` or B1-chosen `-o`, `--ephemeral`), STC-owned
  append-only `shape_gateway_prompt()` framing around the opaque SST bytes
  (never edited; D7 intact), scratch cwd + post-call tracked-tree assertion
  (gateway writes fail closed). The worker/dispatch path keeps the agentic +
  lease + chaperone shape. Budget `elapsed_seconds` is runner-measured wall
  (`max(controller_value, own_wall)`); ledger rows stay the per-call
  authority. LAYOUT names all eight integration modules incl. `dossier.py`.
- `TraceMemoryProtocol`: P02's `FileBackedMemory` serves retrieval from
  versioned markdown + JSONL. Renderers preserve `[source:path]` prefixes
  (tested); bundler truncation/prune behavior is characterized, not trusted.

## 3. Alternatives considered (A3 additions)

- Engine-direct stack (SSTEngine + STC evaluator): rejected. The engine takes
  a concrete `SSTDeterministicEvaluator`, not the `EvaluatorProtocol`, so the
  "evaluator injection" seam does not exist there either; the engine is driven
  by the forbidden workspace-applying runner.
- Per-node fail-closed critique: rejected for M1. True per-node override needs
  subclassing private `_critique_candidate` (D7 exception); M1 uses
  champion-veto with a named event-scrape mechanism + decisive experiment.
- Winner-take-all merge: rejected. The controller auto-synthesizes ≥0.8 pairs
  with no toggle; M1 embraces synthesis with a receipt + loss-ledger.

## 4. Invariants and compatibility

- Kit FRAMEWORK.md governs all packets: authority rules, state vocabulary,
  evidence honesty (NOT RUN / UNVERIFIED), B1→B2→B3→B4→B5 discipline.
- STC 01_INVARIANTS.md §§1–4, 6–7 unchanged. §5 amended by ADR-INT-01 (P00):
  mutmut ≥85% on merged champion only; per-node gates are ruff + mypy + pytest.
  Gate-3 zero-skip honored via `@pytest.mark.live` opt-in (D13).
- TaskBundle ≤25,600 bytes always (bundler throws `BundleSizeExceededError`).
- Candidate identity = git HEAD + `git diff HEAD` bytes + untracked hashes +
  python/OS/pip-freeze digests, composed as a JSON map over pinned paths (P00).
- No worker self-certification: builders never run their own B3.

## 5. Failure handling, recovery, updates

- Confinement breach → violation record (bytes+hashes) + move-to-quarantine +
  lease quarantine by the HarnessWorker wrapper; evidence preserved.
- Harness unavailable → declared degraded-manual mode (a PARKED disposition for
  autonomous execution, not a silent skip); packet not READY-autonomous until a
  live harness passes `probe=True` handshake.
- Budget exhausted (R10) → tranche stops; STATE.md records partial completion
  precisely; no verdict inheritance by expired runs.
- sst/prompt-kit/trace/STC-base drift → 5-path pin table (P00) + extended
  re-readiness rule; rebase only under coordinator direction.
- Repair exhausted → operator chooses from enumerated options (re-scope,
  A2-revisit session [pre-authorized], park with fallback, abort tranche).
- FIX (.1): gateway-agency failure branch — agent timeout/derailment still
  fails closed via the controller's `ProviderGatewayError → warning → empty`
  path (honest partial, never padded); gateway-side repo writes fail closed
  via the post-call tracked-tree assertion. Live legs run unsandboxed
  (operator shell or unsandboxed session, decided at B1); any live run inside
  a sandbox is NOT evidence for agency-vs-environment separation (INFO-1).

## 6. Validation strategy

- Adapter packets: projection-table conformance tests (every field disposed),
  reward-rule tests, vocabulary tests, mypy --strict, pytest.
- Worker packet: breach-injection tests (outer write, .git tamper, utime
  reset), cwd-assertion test, is_success/timeout tests, spoof-membrane tests.
- Runner packet: fixture search with failing branch + garbage-critique node;
  assert prune + veto + champion + mutmut-once (counting rule) + synthesis
  receipt; concurrency lease experiment.
- M1 acceptance (P05): self-hosted real STC task end-to-end; dossier contains
  diff, receipt, verdict, review record, spend log (or partial NEEDS_REPAIR
  set); escalation chain demonstrated on a real ≥τ ambiguity. No invented
  numeric thresholds.

## 7. Unknowns

- Discovery (B1 each packet): exact CLI harness command shapes; mutmut WSL
  path parity; live-harness availability (handshake).
- FIX (.1): C2 separation is a Phase 0 experiment (unsandboxed re-run, no
  code), not an open unknown — decision rule in evidence/A2-revisit/REVIEW.md.
  Fix-B1 discovery: codex `--output-schema` semantics, read-only scratch-cwd
  behavior, effective model/reasoning header. D7-exception trigger defined
  (shaped + unsandboxed smoke fails AND template bytes proven the blocker)
  but NOT met; operator authority required if ever invoked.
- User decision: Q1 (CLI invocation caps) — defaults apply until set.
- Deferred: LocalTrace-backed memory; OS-level sandbox; D7-exception critique
  subclass (trigger: champion-veto proves insufficient); API-harness builders.

## 8. Dependency DAG and packet boundaries (serialized per D12)

```text
P00 (checkpoint + ADR) → P01 (adapters) → P02 (memory) → P03 (worker + gateway backend)
  → P04 (dialectic runner) → P05 (run-extension + self-hosted acceptance) → B5 (tranche integration)
```

One builder at a time; no shared-file contention by construction. Shared
surfaces: `stc/integration/` layout (P01 defines, others extend sequentially);
`dispatch.py` hunk (P03 only); `cli.py` run-extension (P05 only).

## 9. UI/UX note (D3/D8/D14)

M1 CLI extends `run`: `stc run <spec> --target stc --dry-run/--manual/--budget`.
`--dry-run` renders packets + budgets with a composite zero-model-call proof
(gateway.invoke wrap + harness.execute wrap + with_codex=False assert).
Escalation renders ArchetypeDiff options inline; the Q&A log records the full
chain (ambiguity → choice → locked invariant → branch effect). Dossier output
is a directory: diff + receipt + verdict + review + spend log (+ branch refs).

## 10. Effort and sessions

Initial sessions: 1 coordinator + 6 builders (P00–P05, serialized) +
6 verifiers (fresh context each) + 1 dedicated B5 session = 14. Repairs add
bounded B4 effort inside builder sessions per RUNBOOK (new sessions only when
a repair needs isolation). One pre-authorized A2-revisit planning session held
in reserve.

FIX (.1): A2-revisit consumed 2026-09-14 (this design). Fix tranche topology:
Phase 0 operator-shell diagnostic (~30–45 min wall, no session) + 3
affected-scope builder/verifier pairs serialized per D12 (P03-fix, P04-fix
small, P05-fix incl. ~30–60 min live re-run) + 1 dedicated fix-integration
close. Model config unchanged by default (operator codex config); lighter
reasoning only as an operator-approved bounded experiment.
