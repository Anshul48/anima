# Integration-contract design tranche — plan (rev 2: focused architecture session, approval-gated)

## Goal

In a focused architecture session (no implementation, no installs, no live
calls, no readiness claims), resolve the lease/gate contract contradictions
that closed the follow-up tranche NOT-READY — producing a revised contract,
written as one coherent candidate walkthrough, for operator/Sovereign
approval. Implementation, the actual-path preflight, the readiness ruling,
and any live attempt are explicitly sequenced AFTER contract approval and
are not this session's work.

## Success Criteria

- The contract walks one candidate from creation to final judgment,
  answering which bytes, which environment, which tests, which
  dependencies, and which receipt at every transition.
- All four architectural questions are resolved in contract text: (1)
  candidate identity at every layer including untracked inputs,
  nested-lease ref selection, git metadata isolation, and a sufficient
  baseline/receipt key; (2) a trusted test-selection rule with mandatory
  checks, broaden-on-uncertainty, and explicit auto-disable resolution;
  (3) lease external-dependency discipline with import-integrity proof;
  (4) the authoritative environment selected by comparison and frozen
  (interpreter + tool versions).
- A ratification packet (exact §5 / ADR / D-rule deltas) is drafted,
  discussed, and approved; rejected text never auto-becomes a waiver.
- Zero product-file edits, zero installs, and zero live model calls
  in-session (records and `/tmp` proofs only); any prototype is labeled
  feasibility-only and barred from readiness claims.
- No attempt-4, no implementation, and no readiness ruling until the
  approved contract is implemented and the actual-path preflight passes.

## Context And Current Facts

Candidate and close-out (this session, commit `ea1ca30`, records-only):
HEAD `ea1ca30` (records-only close atop `edf5389`) + the same 28-file loose
set (1114+/14-), 28/28 hashes exact per the verify-1 records;
debt-fix + combined-fix close-out verified PASS (Gates 1+2 green real-tree
and lease-mirror, 68/68 + 61/61 both interpreters, substrate flip holds);
accepts 1–3 consolidated PASS (attempt-3 BLOCKED-WIRING CONFIRMED); F1/carry/
A1/A3 PASS; live-exp WIN. Tranche 8/20 CLI, 6-call reserve intact, $0.00.
Tranche closed NOT-READY: 0 champions ever; live judiciary /
merge-execution / mutmut-on-champion / worker harnesses never exercised live.

Ground truth from code (read last session, not inherited):

- Per-node live verify (`dialectic_runner.py:480-485`) calls
  `execute_gates(lease_ws, task_id, epoch, run_mutmut=False)` with NO
  `pytest_target` — Gate-3 is the whole 527-test suite in the lease.
- Gate argv in code (`runner.py:289-292,361-369,420-432,635`): Gate-1
  `ruff check .` + `ruff format --check .`; Gate-2 `mypy --strict src tests`
  (both dirs appended when present); Gate-3
  `pytest -v --tb=short -m "not live"` (+ optional `pytest_target`); Gate-4
  `mutmut run`. Receipt requires commit binding (`_resolve_commit_hash`
  raises on non-git trees), hence `.git` rides in leases.
- Lease composition (`dialectic_runner.py:278-280,303-310`): whole-tree
  mirror minus `{.auto,.sst,.venv,__pycache__,.pytest_cache}` minus the
  dst-subtree (A1); `.git` deliberately included.
- F3 mechanism (`worktree/manager.py:474-481`): `allocate_lease` runs
  `git worktree add -b <branch> <target> main` — E2E tests that run the
  pipeline (`test_dag_pipeline` ×4, `test_cli_run_json_mode`) therefore
  evaluate COMMITTED-`main` bytes, never working-tree or candidate bytes.
- F2 mechanism (`test_integration_harness_worker.py:71-75`):
  `_workspace_root()` is `parents[3]` of the imported `stc` package — the
  real workspace root in-tree, but `/tmp` inside a lease mirror. Exactly 2
  tests skip in ANY lease (`test_f3c_prompt_kit_import_resolves_to_pinned_tree`,
  `test_fix_shape_gateway_prompt_preserves_real_diverge_bytes`), tripping the
  0-skipped invariant (`01_INVARIANTS.md` §5 + ADR-INT-01).
- F4 fact (`test_integration_identity.py:111`): the test asserts
  `python_version.startswith("3.12.")`. The CONTRACT agrees with the test,
  not the env: Target Environment is Python 3.12+
  (`01_INVARIANTS.md:5`), while real-gates runs 3.11.15. The env is the
  anomaly; F1 (joint 3.12 lacks ruff/mypy) is its coupled twin — today no
  single env runs all gates.
- Discrepancy (found last session): §5 fixes Gate-2 as
  `mypy --strict src/`, but the implementation AND all evidence run
  `mypy --strict src tests`. Likewise §5 Gate-3 is bare
  `pytest -v --tb=short` while code + ADR-INT-01 (D13) run
  `-m "not live"`. The contract text trails the implementation in both
  places.

Why the diagnostic E2E passed while live Gate-3 could not: `run-diag-e2e.py`
runs Gate-3 TARGETED at its single new pin file
(`pytest -v --tb=short -m "not live" tests/unit/test_debtfix_diag_pin.py`,
also via `execute_gates(pytest_target=PINS)`), with hand-written
strict-clean pins and mutmut off. It never executes the F3 E2E tests, the
F2 skipping tests, the F4 env assert, or the substrate tests — while Gates
1+2 run whole-tree (green post-debt). The diag is therefore an existence
proof that candidate-scoped Gate-3 CAN pass with the current machinery;
live per-node verify runs the identical machinery WITHOUT `pytest_target`,
so every candidate pays for the whole tree's F1–F4 blocks. The difference
is scope, not machinery. (Merge path additionally notes
`dialectic_runner.py:854` that `pytest_target` is forbidden there because
of the substrate auto-disable trap at `runner.py:212-219`.) This session
must not repeat that mistake: no claim established on a narrower path than
the one it governs.

What survives regardless of the redesign: confinement, elapsed accounting,
F1 sidecar capture, marker refusal, the H1 context package, the diagnostic
replay chain, and all close-out verification evidence.

## Constraints And Non-goals

- Binding sequence: Design → isolated prototype if necessary → contract
  approval → implementation → actual-path preflight → readiness ruling →
  live attempt. No step's evidence substitutes for a later step's: a
  prototype demonstrates feasibility only and can never establish
  production-pipeline readiness; readiness requires the implemented
  dispositions running on the actual path. Spec simulation is not preflight.
- Scope discipline: the walkthrough covers the candidate evaluation path
  only (creation → custody → per-node gates → judiciary → merge → champion
  judgment). Do not reopen the whole STC architecture.
- No product-file edits, no installs, and no live model calls in-session;
  records and `/tmp` proofs only. `sst/`, `prompt-kit/`, `trace/` stay
  read-only.
- `01_INVARIANTS.md` is Sovereign-owned (Rule of Inviolability): the session
  drafts amendment text for ratification, never edits the file.
- Do not assume commits are incompatible with search; an isolated candidate
  commit is a legitimate evaluation mechanism subject to the commit rule.
- Do not remove whole-tree checks merely to get green: the design separates
  baseline, candidate, and integration checks and keeps interaction coverage
  where it belongs, with explicit evidence-reuse rules.
- No waiver by fallback: if an amendment is rejected, the outcome is
  re-discussion or honest NOT-READY — never an automatic waiver or
  downgrade. Any waiver needs its own explicit approval.
- Budget box (corrected): 20 − 8 = 12 CLI total remaining, OF WHICH 6 are
  the protected verification reserve. $0 installs default in-session; env
  construction is post-approval work.
- Non-goals: implementing the dispositions; running the preflight or any
  readiness ruling; running attempt-4; SST custody changes (tolerance stays
  validated-but-unlanded unless the contract requires it); trace-lite; OS
  confinement.

## Key Decisions

- D-CT1 — gate bytes / F3 (RECOMMENDED): three-class split. (a) Per-node
  gates become candidate-scoped: Gate-3 runs with `pytest_target` =
  explicitly selected tests per the trusted rule (D-CT5), Gates 1+2 stay
  whole-tree (fast, green, interaction-catching). (b) Whole-tree
  integration Gate-3 (including the committed-E2E tests) moves to
  champion/merge cadence. (c) At integration cadence, E2E leases branch
  from a candidate-inclusive scratch ref committed in the LEASE's
  disposable git (never `main`, discarded with the lease) — the isolated
  candidate commit, reconciled with the no-product-commit rule because no
  shared history is touched. (d) The contract specifies HOW nested leases
  select that ref (explicit ref-propagation rule, no silent `main`
  fallback — creating a ref does not fix code that branches from `main`
  until the branch point is re-specified); lease-local git metadata must
  be provably incapable of mutating shared history (disposable clone /
  worktree semantics with push disabled by construction); receipts bind
  the FULL candidate (scratch ref + untracked-input manifest + content
  digest). REJECTED: status-quo whole-tree-per-node (F3-impossible,
  proven); commit-to-`main`-first (couples every evaluation to shared
  history and review order); CI-only E2E (loses machinery regression
  signal for machinery candidates like the P05 runner pins);
  base_commit-only keying (loses uncommitted bytes — the current loose
  set would be invisible to the key).
- D-CT2 — F2 lease skips (RECOMMENDED): lease-aware workspace resolution —
  tests resolve the workspace via an explicit override (e.g.
  `STC_WORKSPACE_ROOT`) with the current inference as fallback, specified
  (not implemented) in-session — PLUS external-dependency discipline: the
  override may expose ONLY pinned, read-only resources enumerated in the
  contract, and the contract requires an import-integrity proof that tests
  still import candidate STC code rather than original-checkout code
  (`stc.__file__` under the lease, `sys.path` order, pinned resource
  roots asserted). Anything else reachable through the override is a
  finding, not a silent dependency. REJECTED: allowed-skip carve-out
  (weakens the invariant for a fixable cause); provisioning sibling
  checkouts into leases (breaks lease self-containment, heavy);
  unpinned workspace pointers (reproduces the coupling the lease exists
  to prevent).
- D-CT3 — authoritative env / F4 versions + F1 tools (RECOMMENDED):
  authoritative interpreter stays 3.12 per the contract's Target
  Environment; the MECHANISM is decided by an in-session comparison of (i)
  a new STC-owned 3.12 env against (ii) a one-shot ruff+mypy install into
  the TRACE shared 3.12 env — compared on ownership, cross-project
  coupling, reproducibility, and receipt env binding, with the winning
  env's interpreter + tool versions FROZEN in the contract. Lean: STC-owned
  (no cross-project mutation; the tranche controls what its receipts
  bind). No installs are requested or performed in-session either way —
  env construction is post-approval work, and installation approval is
  requested separately with the comparison attached. Real-gates 3.11 stays
  a best-effort secondary leg, never authoritative. REJECTED:
  3.11-primary + assert relaxation (contradicts the contract; would need
  a Sovereign downgrade amendment); dual-authoritative envs (doubles
  cost, split-brain receipts); installing before the comparison is
  approved (ordering violation).
- D-CT4 — skip invariant (RECOMMENDED): keep 0-skipped absolute, no
  manifest. D-CT2 removes the only procedural skips; D-CT3 removes the
  env-conditional gate-tool skipifs (they exist because joint lacks tools);
  live-marked tests are already deselected per D13. A manifest is the
  documented fallback only if D-CT2 is rejected (and adopting it needs its
  own explicit approval per the no-waiver rule).
- D-CT5 — classes, evidence reuse, and test selection (RECOMMENDED):
  baseline health = whole-tree Gates 1–3 receipt pinned per
  (base_commit, candidate_content_digest including untracked inputs,
  env_digest, gate_argv), run once per base and reused across nodes;
  candidate checks = fresh per node, scoped (D-CT1a); integration checks =
  whole-tree incl. E2E at champion/merge cadence (D-CT1b/c). Reuse rule:
  baseline receipts are immutable inputs; candidate evidence is never
  reused across candidates; integration re-runs on every merge.
  Whole-tree interaction coverage is preserved — it moves cadence, it is
  not deleted. Trusted selection rule: the generated proposal must not
  decide its own entire examination — the contract names a MANDATORY set
  that always runs regardless of selection, candidate-selected affected
  suites beyond that, a broaden-on-uncertainty rule (uncertain impact ⇒
  run the broader scope), and a naming rule (any plausibly affected but
  unrun test is named with a reason). The substrate auto-disable behavior
  (`runner.py:212-219`: `pytest_target` + `PYTEST_CURRENT_TEST` forces
  mutmut off) is resolved explicitly: scoped runs declare their safeguard
  set in the receipt, and no scoping may silently drop a safeguard —
  dropped safeguards are explicit, named, and separately approved.
- D-CT6 — contract text (RECOMMENDED): ratification packet amending §5 to
  the implemented argv (`mypy --strict src tests`, pytest `-m "not live"`
  per D13) and recording the three-class cadence + scratch-ref protocol +
  selection rule + env freeze + lease-dependency discipline. REJECTED:
  narrowing the implementation to §5-literal `mypy src` (would un-gate
  15 test-file errors and contradict all evidence); leaving the text/code
  split undocumented (repeats this tranche).
- D-CT7 — sequencing gate (RECOMMENDED, corrected): attempt-4 requires
  contract approval → implementation of the dispositions → a green
  actual-path preflight on the production pipeline (implemented
  dispositions, real call path, F3 E2E + F2-named tests included — no spec
  simulation) → a readiness ruling from that evidence. THIS session
  delivers the contract plus the preflight SPEC (including negative
  controls, specified for post-approval execution) — never a green run or
  a readiness claim. REJECTED (this session's own rev-1 error): promising
  an actual green preflight before implementing the changes that make the
  path work.

## Recommended Approach

Specify the contract before touching code, and prove nothing beyond what
the session's path supports. Concretely: (1) draft the walkthrough —
one candidate from creation to final judgment, five answers (bytes,
environment, tests, dependencies, receipt) at every transition, resolving
the four architectural questions in contract language; (2) compile the
ratification packet (exact deltas + protocols + selection rule + env
freeze + post-approval preflight spec); (3) build an isolated prototype
ONLY if a named feasibility question cannot be settled by code reading —
time-boxed, `/tmp`-local, labeled feasibility-only, and barred by the
honesty audit from supporting any readiness claim (skip it entirely if
reading suffices); (4) discuss the packet to approval. Then stop:
implementation, the actual-path preflight, the readiness ruling, and any
live attempt belong to later authorizations. The session's honesty rule,
posted on its own work: no claim established on a narrower path than the
one it governs — the walkthrough states, for every check it defines,
which path establishes it.

## Work Plan

1. Candidate walkthrough draft (records only): creation → custody →
   per-node gates → judiciary → merge → champion judgment; five answers
   at every transition; the four architectural questions resolved in
   contract language (nested-lease ref selection, metadata isolation,
   full-candidate binding, mandatory/broaden/naming selection rules,
   auto-disable resolution, lease-dependency enumeration + import proof,
   env comparison + freeze). Depends on: nothing.
2. Ratification packet (records only): exact §5 / ADR-INT-01 / D-rule text
   deltas + the scratch-ref, selection, env, and lease-dependency
   protocols + the post-approval preflight spec (actual-path run with
   negative controls: must reproduce F3/F2 reds when pointed at unscoped
   gates or when the scratch ref is omitted). Depends on: unit 1.
3. Isolated prototype (ONLY if a named feasibility question resists code
   reading; records + `/tmp`, 0 calls): time-boxed, labeled
   feasibility-only with its non-claims stated; skip if reading suffices.
   Depends on: unit 1 (the question must be named there).
4. Discussion + approval: walk operator/Sovereign through the packet;
   record dispositions per decision. Rejected text returns to draft or to
   honest NOT-READY — never to waiver. Depends on: units 1–3. Session ends
   here.
5. (Sequenced, NOT started) Implementation of the dispositions →
   actual-path preflight → readiness ruling → attempt-4. Starts only on
   explicit approval of the contract AND a separate implementation
   authorization.

## Validation Plan

- Walkthrough completeness audit: every transition answers bytes,
  environment, tests, dependencies, and receipt; every answer traced to a
  code line or evidence hash; no orphan claims. (Manual read.)
- Honesty audit (highest-value step): no claim established on a narrower
  path than the one it governs; any prototype labeled feasibility-only
  with non-claims stated; the packet contains zero readiness assertions.
  A readiness-shaped claim fails the session. (Manual read.)
- No-drift / no-touch guards: HEAD + 28/28 hashes + pins + sst-clean
  re-probed at session close; 0 product edits, 0 installs, 0 live calls
  verified. (Scripted.)
- Ratification review: packet checked against the four architectural
  questions; open questions closed or explicitly carried with an owner.
  (Manual read + operator.)
- (Specified, not executed) Post-approval acceptance for the preflight run:
  green actual-path run + negative controls + dry-run/collect + readiness
  ruling. Listed so this session's spec is judged against the bar it sets.

## Risks / Rollback

- Sovereign rejects an amendment: re-draft or honest NOT-READY. Waivers,
  downgrades, and carve-outs each need their own explicit approval — none
  arise by fallback. (No-waiver rule.)
- Scratch refs judged incompatible with the commit rule: fallback is
  lease-scoped E2E (option A), re-walked; the plan's structure is
  unchanged, only D-CT1c's mechanism swaps.
- Env comparison deadlocks (no acceptable env): honest NOT-READY with the
  comparison as evidence; no silent downgrade to 3.11-primary.
- Prototype-as-proof temptation (presenting feasibility as readiness):
  barred by the honesty audit + labeling rule; a violation fails the
  session rather than weakening the claim.
- Champion-cadence whole-tree cost (750 s+ per merge): accepted and
  budgeted in the post-approval box; per-node cost drops under scoping.
- Rollback: the session writes records + `/tmp` only — rollback is
  deleting the design-tranche additions; the candidate tree is untouched
  by construction (no-drift guard proves it).

## Open Questions

1. Are candidate-inclusive scratch refs in lease-local disposable git
   acceptable evaluation machinery (never `main`, auto-discarded)? This
   sits on the no-product-commit boundary and needs your explicit call —
   yes keeps D-CT1c, no switches to lease-scoped E2E.
2. For the authoritative-env comparison: is provisioning a NEW STC-owned
   3.12 env an acceptable outcome (construction post-approval), or must
   the design reuse existing envs only? No installs are requested
   in-session either way.
3. What CLI-call cap governs attempt-4 within the corrected box (12 total
   remaining INCLUDING the protected 6-call reserve)? A number, or "keep
   the reserve untouched," sets the post-approval readiness box.

