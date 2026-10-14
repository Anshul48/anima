# Integration-contract walkthrough (DRAFT — for contract review, not ratified)

Status: design-tranche working draft, REDLINED per HANDOFF-NEXT.md
(R-ENV/R-HEAD/R-DIFF/R-TRIP/R-SEL/R-LINK/R-ED: D-α…D-ζ + E1–E4 applied;
reconstruction flags carried in AUTHORIZATION.md; still DRAFT, not
ratified). Approval basis: rev-2 plan approved for
the focused architecture session only, with Q1 Yes (genuine git isolation),
Q2 Yes (STC-owned 3.12 preferred, no install authorized), Q3 keep 12-incl-6
(topology-derived attempt-4 cap deferred to the later execution
authorization), the three in-session details (git isolation beyond
push-disable; baseline-vs-candidate identity names; trusted-orchestration
selection), and the authorized STATE spend clarification. Nothing here is
implemented, installed, or executed live; no readiness claim is made or
implied. Prototype: SKIPPED — no feasibility question resisted code reading
(see Non-claims).

Scope fence: the candidate evaluation path only — creation → custody →
per-node gates → selection → merge → judiciary → champion judgment. The
walkthrough follows ONE candidate end to end. Whole-STC architecture is not
reopened.

## Reading conventions

Every transition answers five questions: BYTES (which content is evaluated),
ENV (which interpreter + tools run it), TESTS (which checks run and at what
cadence), DEPS (which dependencies are reachable and under what discipline),
RECEIPT (which signed artifact binds the outcome and its inputs). An answer
may be explicitly vacuous (e.g. "no tests run at creation") — a missing
answer is a defect in this draft. Every answer traces to a code line or an
evidence hash; the path that establishes each claim is named in Non-claims
(honesty rule: no claim established on a narrower path than the one it
governs).

Identity vocabulary (per the approval: baseline and candidate identities
are distinct names, never one muddled key):

- `base_commit`: the frozen `main` HEAD the evaluation builds on (40-hex).
- `baseline_content_digest`: sha256 over the frozen baseline content the
  reusable baseline receipt binds — tracked baseline bytes PLUS the loose
  baseline inputs manifest (every untracked baseline file by path +
  content sha256). The 28-file close-out manifest is the worked example of
  the shape: 10 tracked files (git diff numstat 1114+/14-) + 18 untracked
  files (content-hash manifest) — the numstat never describes the untracked
  share.
- `candidate_content_digest`: per-candidate sha256 over the scratch ref SHA
  + the candidate's untracked-input manifest + the normalized diff bytes.
  Fresh per candidate; never reused across candidates.
- `env_digest`: sha256 over the environment fingerprint — the exact
  `sys.version` string, `ruff`/`mypy`/`pytest`/`mutmut` `--version`
  strings, the `uv.lock` content sha256, and `os_platform`. Every check
  records its exact fingerprint; 3.12.3 vs 3.12.10 are different
  fingerprints, recorded always, never a silent same. COMPATIBILITY is
  separate from provenance: the floor is Python ≥3.12 with all four
  gate tools + app deps present (fail closed ONLY on floor violation
  or missing tool). REUSE is governed by the requalification policy
  (§Q4): same (major, minor) + same tools-present set + same lockfile
  content hash ⇒ the ENV side requalifies; reuse ALSO requires the
  full T0 key match (`base_commit`, `baseline_content_digest`,
  `gate_argv`) — the lockfile content hash records dependency
  intent and is necessary, NEVER sufficient by itself. ANY lockfile
  content change or minor-version change ⇒ requalify the baseline
  (re-run T0). The identity record's `pip_digest` field
  (`test_integration_identity.py:110-113`) remains a recorded
  provenance field; reuse comparisons use the lockfile content hash.
  Windows↔Linux results are comparable with separate identities each
  (CI matrix precedent, `.github/workflows/ci.yml`).
- `gate_argv`: the exact gate command lines (frozen in §5 by this packet).

## T0 — Baseline pin (precondition, once per base)

Before any candidate is evaluated, trusted orchestration pins and receipts
the baseline the candidates build on.

- BYTES: `base_commit` + the full baseline tree including loose baseline
  inputs enumerated in the baseline manifest. Frozen: no baseline byte may
  change while candidates keyed to it are in flight; a changed baseline is
  a new baseline identity, never an edit.
- ENV: the authoritative env (§Q4: floor-compatible, fingerprinted at
  check time). The baseline receipt is valid under its recorded
  fingerprint and reusable per the requalification policy; a
  minor-version or lockfile change requalifies (re-run T0), never
  silently reuses.
- TESTS: whole-tree Gates 1–3 (the implemented argv: `ruff check .` +
  `ruff format --check .`; `mypy --strict src tests` per the
  src-or-dot/tests-if-present rule at `runner.py:363-369`;
  `pytest -v --tb=short -m "not live"` per `runner.py:430-432` and D13).
  This is the ONE whole-tree Gate-3 run per base; per-node runs reuse its
  verdict, never re-run it.
- DEPS: lease-self-contained (T2-rule); no external reads beyond the pinned
  read-only set (§Q3).
- RECEIPT: the baseline receipt, keyed by
  `(base_commit, baseline_content_digest, env_digest, gate_argv)`, HMAC-signed
  per the §5 signing invariant. Immutable input to every candidate judged
  against this base. A red baseline fails closed: no candidate proceeds on
  a red base (its verdict would be uninterpretable), and the red is owned
  by the baseline, never charged to a candidate.

## T1 — Creation (candidate proposal genesis)

A worker emits a proposal: a unified diff against the pinned baseline plus
any new files the diff adds.

- BYTES: the proposal bytes — normalized unified diff + new-file contents.
  At creation these bytes are untrusted input, not an evaluation result.
  The candidate's untracked-input manifest opens here (every new file by
  path + sha256) and travels with the candidate thereafter.
- ENV: the worker emission env. RECORDED (provenance) but NON-NORMATIVE:
  no gate verdict may depend on where or how the bytes were emitted. Any
  check that only passes in the emission env is a finding against the
  check, not evidence for the candidate.
- TESTS: none run at creation. Coverage obligations attach at T3; the
  proposal MAY suggest additional tests (names + rationale), which the
  trusted selector may ADD but which can never remove, narrow, or satisfy
  any mandatory or affected coverage (§Q2).
- DEPS: worker-harness inputs (TaskBundle ≤ 25,600 bytes per §2, negative
  inhibitors, pinned prompt-kit). The proposal carries no dependency
  authority into the lease: T2 re-resolves everything from pins.
- RECEIPT: none at creation. The first binding artifact is the custody
  intake record at T2. (Any pre-custody hash is a transport checksum, not
  an evaluation receipt, and must never be cited as one.)

## T2 — Custody (lease allocation + proposal application + scratch ref)

Trusted orchestration builds a lease, applies the proposal, and commits the
result as a candidate-inclusive scratch ref in the lease's disposable git.
Current-code anchors: `mirror_source_tree` (`dialectic_runner.py:283-300`,
skip-set at :278-280, dst-exclusion (FOLLOWUP a1-fix) at :303-311),
`STCCustodyWrapper.verify_candidate_proposal` (:414-519),
`_resolve_commit_hash` (`runner.py:266-287`, raises on unresolvable HEAD).

- BYTES: the lease tree = baseline bytes (T0) + applied proposal bytes.
  Authoritative form: the scratch commit on `refs/scratch/<candidate_id>`
  in the lease git, whose tree MUST equal the applied lease bytes
  (verified by tree-hash comparison at intake; mismatch fails closed).
  Untracked candidate inputs that the diff mechanism cannot carry (new
  files outside diff context) are committed into the same scratch ref, so
  the ref + manifest jointly exhaust the candidate bytes — no evaluated
  byte lives outside the ref.
- ENV: custody runs under orchestration, not the gate env; no gates run at
  T2. The lease records the target `env_digest` it will be gated under.
- TESTS: none. Custody performs exactly two checks: (1) apply-clean +
  tree-hash equality; (2) baseline-manifest re-hash — the T0 baseline
  manifest is re-hashed at intake (`--locked` semantics: the manifest
  must be unchanged since the T0 pin; ~10 lines implementation
  scope). A proposal that does not apply is REJECTED (not scored):
  `apply_proposal` failure returns a deterministic non-pass
  (`dialectic_runner.py:468-479` shape), never a partial score. A
  drifted baseline manifest fails closed (re-pin T0, never proceed).
- DEPS: the lease is self-contained by construction: whole-tree mirror
  minus {.auto,.sst,.venv,__pycache__,.pytest_cache} minus the dst-subtree
  (FOLLOWUP a1-fix mirror rule — NOT Delta A1: the lease never
  mirrors its own destination path — recursion guard, verified by
  the a1-fix regression pins),
  `.git` included for commit binding. External reachability beyond the
  mirror is governed solely by §Q3 (pinned, read-only, enumerated).
- RECEIPT: the signed CustodyIntake linked record — `(candidate_id,
  base_commit ref, scratch_ref_SHA, candidate_content_digest, baseline
  receipt ref, target env_digest)` — signed by orchestration, linked
  by digest into the dossier (the ExecutionReceipt stays frozen and
  carries no new fields). This is the candidate's birth certificate:
  every downstream receipt names it, any downstream artifact that
  cannot resolve its intake record is untrusted, and verification
  MUST consume it (existence, signature auth, digest links,
  cross-identity agreement with the gate receipts; a tampered or
  substituted intake record MUST fail verification — preflight N6).
- GIT ISOLATION (Q1 as approved — beyond push-disable): the lease git MUST
  be incapable of mutating the original repository by construction, viz.
  (a) MIRROR leases (per-node path): the copied `.git` is sanitized at
  intake — remotes removed, copied `worktrees/` admin dropped — before any
  ref is created; refs created in the copy cannot propagate because no
  remote and no shared ref store exist. (b) SCRATCH-REF leases
  (integration cadence): a full independent clone (`--no-hardlinks`,
  remote removed post-clone); the scratch ref is created only inside the
  clone. `git worktree add` against the ORIGINAL repository is FORBIDDEN
  on every evaluation path (it writes `worktrees/` metadata into the
  original `.git` — precisely the mutation push-disabling does not
  prevent). (c) REF PROPAGATION + HEAD ASSERT, on EVERY lease:
  PRIMARY leases check out the scratch ref at intake and assert
  `HEAD == scratch_ref_SHA` at gate time (one `git rev-parse`
  comparison, zero API change); NESTED leases receive the exact
  `(lease_git_path, scratch_ref_SHA)` pair, clone-or-fetch that SHA,
  and assert `HEAD == scratch_ref_SHA` before running anything.
  Propagation (usability — nested leases must be TOLD the right ref)
  AND assertion (safety) are both required: assert-without-propagation
  is safe but unusable. Safety never depends on the `main` default:
  any silent fallback to `main` (the current `base_branch="main"`
  default at `worktree/manager.py:410`) is a contract violation and
  fails closed, and the implementation MUST re-specify every branch
  point.
  (d) CLEANUP deletes the disposable git whole (mirror copy or clone);
  quarantine preserves a COPY for inspection, never the live lease.
  Proof obligation (preflight N5): the original repo's ref advertisement
  + worktree list are byte-identical before and after any evaluation run.

## T3 — Per-node gates (fresh per candidate, scoped Gate-3)

Each candidate runs gates in its own lease against its scratch ref.
Current-code anchor: `execute_gates(lease_ws, task_id, epoch,
run_mutmut=False)` with NO `pytest_target` (`dialectic_runner.py:480-485`)
— the contract changes WHAT that call scopes, not the call shape.

- BYTES: the scratch-ref tree (T2). Gate verdicts bind
  `candidate_content_digest`; before gates, the lease asserts
  `HEAD == scratch_ref_SHA` (T2c) — a gate run that cannot resolve
  and assert the scratch ref fails closed (never falls back to
  `main` bytes).
- ENV: the authoritative env ONLY (§Q4: floor-compatible per the
  ≥3.12 + tools-present floor, fingerprinted per check).
  Floor-violating or tool-missing envs fail closed. Python 3.11 legs
  are advisory only and never receipted as authoritative. A candidate
  gated under any other env has no valid verdict.
- TESTS: three-class split. (a) Gates 1+2 run WHOLE-TREE (fast, green,
  interaction-catching; `ruff` + `mypy --strict src tests` as frozen).
  (b) Gate-3 runs CANDIDATE-SCOPED: `pytest_target` = the trusted
  selection for this candidate (§Q2: mandatory set + orchestrator-computed
  affected set + broadenings + candidate-suggested additions), always with
  `-m "not live"` (D13). (c) Whole-tree Gate-3 incl. the committed-E2E
  tests does NOT run per node — it moved to champion/merge cadence (T5),
  it was not deleted. (d) Gate-4 (mutmut) does not run per node
  (ADR-INT-01 champion-only, unchanged); the per-node receipt carries the
  documented non-execution marker. Skip invariant: 0 skipped absolute
  (D-CT4); the only procedural skips known (the two F2 tests) are removed
  by the §Q3 override, and env-conditional tool skipifs vanish with the
  single authoritative env.
- DEPS: lease-self-contained + §Q3 pinned read-only externals. The
  workspace override (`STC_WORKSPACE_ROOT`, specified — no current
  implementation: grep 2026-09-19 finds zero refs) resolves to pinned
  read-only resources ONLY; the import-integrity proof asserts
  `stc.__file__` under the lease, expected `sys.path` order, and pinned
  resource roots. Anything else reachable through the override is a
  finding, not a silent dependency. The §Q3 full-manifest tripwire is
  hashed pre-gates (detection-with-fail-closed; persistent change ⇒
  run fails).
- RECEIPT: the per-node ExecutionReceipt (Gates 1–3 reports + mutmut
  non-execution marker), HMAC-signed, binding `(candidate intake ref,
  baseline receipt ref, env_digest, gate_argv, selection record)`. The
  signed per-node SelectionRecord names: mandatory-set digest (bound
  to the versioned selection-config revision, §Q2), affected-computation
  inputs (diff manifest + owning-suite map revision), uncertainty
  broadenings taken, plausibly-affected-but-unrun tests with reasons,
  the ACTUAL gate argv executed alongside `contract_rev` (what ran
  beats what varies — a revision names intent, not execution), and
  the safeguard declaration (which safeguards ran; a dropped safeguard is
  explicit, named, and separately approved — normally: none dropped).
  Verification MUST consume the SelectionRecord (existence, signature
  auth, digest links to custody + receipts, cross-identity agreement;
  tampered/substituted records MUST fail verification — preflight N6).
  Scoped runs declare their safeguard set precisely: the
  `runner.py:212-219` trap takes effect ONLY when no explicit
  `run_mutmut` kwarg is passed (`runner.py:212-215` precedence), and
  both production call sites pass explicit bools (per-node `False`,
  `dialectic_runner.py:484`; merge `self._champion_mutmut`,
  `:860`/:881) — so at per-node cadence mutmut is ALREADY out by
  ADR-INT-01 as a coverage fact, not by the trap, and the receipt
  says so. The E1 behavioral check proves safeguard selection
  survives the production call path (§Q2).

## T4 — Selection (trusted orchestration picks the champion lineage)

Scores and vetoes from per-node receipts feed the deterministic selection
of which verified lineage proceeds. Anchors: `_verified_nodes` (:958-965),
`_score_map` (:968-985), `scrape_tainted_scores` (:225),
`_best_untainted` (:988-1002: best verified, untainted, non-escalated).

- BYTES: no new bytes. Selection operates on receipted verdicts + the
  loss ledger + veto/taint records. Selectable nodes are exactly the
  VERIFIED set (per-node receipt passing); tainted or ESCALATE_HUMAN
  nodes are ineligible by rule, never by discretion.
- ENV: none (pure function over receipts). Deterministic: same inputs ⇒
  same selection, byte-identical.
- TESTS: none run. Selection consumes T3 verdicts; it never re-runs,
  re-scopes, or second-guesses a gate verdict. A disputed verdict is a
  finding against the gate path, resolved by re-running the GATE, never
  by adjusting selection.
- DEPS: the SST event log (scores, critiques, vetoes) as read-only input.
  SST custody itself is unchanged by this contract (tolerance stays
  validated-but-unlanded).
- RECEIPT: the signed selection-outcome record — `(verified set,
  tainted map, scores summary, selected node OR no-champion reason)` —
  signed by orchestration and embedded in the final dossier either way
  (`ChampionResult` :201-222 / `NoChampionResult` :186-198). (Distinct
  from the per-node SelectionRecord, T3: that binds coverage per
  candidate; this binds the outcome across candidates.) Verification
  MUST consume it like every other linked record (N6 control list).
  No-champion is a first-class receipted outcome, not an absence of one.

## T5 — Merge (re-apply + whole-tree integration gates + mutmut-once)

The selected lineage is re-applied onto a fresh lease and judged
whole-tree, including the committed-E2E tests against the scratch ref.
Anchors: merge re-apply + `pytest_target` FORBIDDEN
(`dialectic_runner.py:836-861`, comment at :853-854),
`count_mutmut_runs` (:124), `_mutmut_disposition` (:625).

- BYTES: a FRESH lease (never a reused per-node lease) built from the
  baseline + the selected proposal, committed as its own scratch ref;
  nested E2E leases propagate THAT ref's exact SHA (§T2c). The E2E tests
  therefore evaluate candidate-inclusive bytes for the first time — this
  is the F3 fix point, and the preflight N2 negative control proves it is
  load-bearing (omit the ref ⇒ E2E evaluates `main` ⇒ candidate
  assertion fails).
- ENV: the authoritative env (same fingerprint as T3, or a
  requalified baseline per §Q4; an unrequalified different env here
  would compare unbindable verdicts).
- TESTS: whole-tree Gates 1–3 UNSCOPED (no `pytest_target` — the merge
  path keeps the current forbidden-target rule so the safeguard set
  stays whole-tree + mutmut by construction; the `runner.py:212-219`
  trap is additionally irrelevant here because the merge call site
  passes an explicit `run_mutmut` bool, which takes precedence per
  `runner.py:212-215`) + Gate-4 `mutmut run` exactly once per merge
  evaluation (kill rate ≥ 85%, counted-once disposition; each retry
  is its own merge evaluation with its own receipt). 0 skipped
  absolute; live deselected per D13. Cost note (accepted): 750 s+
  per merge; per-node cost drops under scoping.
- DEPS: same discipline as T3 (§Q3). The merge lease's externals are
  pinned identically; any drift between per-node and merge externals is
  a finding.
- RECEIPT: the post-merge ExecutionReceipt (all four gates), HMAC-signed,
  binding `(merge scratch ref, T4 selection-outcome ref, env_digest,
  gate_argv)` TOGETHER with the linked merge record — binding is
  established by the verified receipt-and-linked-record ensemble, not
  the receipt alone. The linked merge record pins exactly
  (`merge_scratch_ref`, `selection_outcome_ref`, `env_digest`,
  `merged_diff_sha256`); the mutmut disposition rides `ChampionResult`,
  not the merge record (the ExecutionReceipt stays frozen — the
  digest rides the linked record, §T6). `mutmut_count == 1` per
  post-merge receipt or the disposition is recorded non-passing.
  Reversion watch (Delta A1): if scoped per-node selection is shown
  to let mock-gaming suites reach champion routinely, the ADR-INT-01
  reversion condition triggers.

## T6 — Judiciary audit (blind adversarial review of the merged champion)

The merged diff is audited against the bundle and the post-merge receipt.
Anchor: `_audit` (:946-955: `with_codex=False` asserted per RT-08;
`audit_diff(merged_diff, bundle, receipt)`).

- BYTES: `merged_diff` (rendered at :850-851) + the post-merge receipt.
  DIFF-BINDING DEFINITION (exact, frozen): base = the merge lease's
  baseline tree (`base_commit` tree + baseline manifest); result = the
  merge scratch-ref tree; policy =
  `git diff --no-ext-diff --unified=3 <base> <result>` with default
  whitespace handling (NO ignore-whitespace). One shared
  `normalize_diff()` helper, used at render (`:850`) AND audit,
  canonicalizes transport only (LF endings, trailing newline at EOF,
  exact hunk headers) — it MUST NOT reorder hunks or touch in-line
  whitespace. The auditor recomputes the diff from the merge scratch
  ref and compares against the rendered bytes. The auditor sees the
  diff and the receipted verdicts, never worker chat transcripts or
  search history (blind rule, §1 Judiciary branch).
- ENV: audit runs in the orchestration context with the pinned auditor;
  no candidate code executes here (diff inspection, not execution).
- TESTS: none executed. The audit searches for mock infiltration, silent
  fallbacks, disabled assertions, and contract tampering — including
  re-verification that the receipt HMACs verify and that the merge
  receipt's bytes equal the audited diff's bytes (receipt↔diff binding
  check; mismatch fails closed). LIVE path: `merged_dir` is passed to
  `_audit` so the auditor checks live-against-rendered now. EVIDENCE
  path: a `git bundle` of the scratch ref + the rendered diff bytes
  are stored in the evidence dir, so verification survives lease
  deletion forever; the auditor checks bundle-against-rendered later.
  Mismatch fails closed either way.
- DEPS: the TaskBundle + negative inhibitors + the receipt chain
  (baseline ← per-node ← selection ← post-merge). The chain must resolve
  unbroken; a dangling ref fails closed.
- RECEIPT: the `JudiciaryVerdict`, naming the exact
  `(merged_diff sha256, post_merge_receipt id)` pair it rules on. A
  verdict that cannot name its pair rules on nothing. `merged_diff_sha256`
  rides the linked merge record (T5), not the frozen ExecutionReceipt.

## T7 — Champion judgment (final dossier, receipted either way)

The run assembles the typed outcome. Anchors: `ChampionResult` (:201-222),
`_no_champion` (:1067), `run()` assembly (:689-911).

- BYTES: the champion's merged bytes (by scratch ref + diff sha) or, for
  no-champion, the `reason` + the receipted losing lineage. Either way
  the dossier binds bytes, never narratives.
- ENV: the authoritative fingerprint, repeated from the chain (all legs
  same fingerprint, or requalified per §Q4 with the requalification
  recorded — otherwise the dossier is internally inconsistent and
  fails closed).
- TESTS: none further. T7 assembles; it never re-runs. Any "one more
  check" belongs to a defined transition with its own receipt.
- DEPS: none new. The dossier embeds or content-addresses every input it
  cites (receipts, linked records, verdicts, veto log, loss ledger,
  synthesis receipts).
- RECEIPT: the final dossier — `ChampionResult` (merged diff +
  post-merge receipt + retry receipts + mutmut disposition + synthesis
  receipts + loss ledger + judiciary verdict + first verdict + veto log +
  scores + evidence dir, HMAC'd over the digest list of the linked
  CustodyIntake + per-node SelectionRecords + selection-outcome
  record + merge record) or
  `NoChampionResult` (reason + branch refs + scores + veto log +
  budget state + evidence dir). Promotion requires the full chain
  green; anything else is an honest no-champion with its reason
  receipted.

## Q1 — Candidate identity (RESOLVED in contract text)

Every evaluated byte is attributable to exactly one identity at every
layer; no byte is evaluated anonymously and no key conflates baseline
with candidate (per the approval's naming correction).

- AT REST (lease tree): identity = scratch ref SHA + untracked-input
  manifest. The manifest is content-addressed (path + sha256 per file);
  an empty manifest is explicit (`untracked: {}`, cf. the identity
  record shape at `test_integration_identity.py:109`), never absent.
- IN RECEIPTS: per-node and post-merge receipts bind
  `candidate_content_digest` (scratch SHA + manifest + normalized diff)
  AND the baseline receipt ref. The BASELINE receipt binds
  `baseline_content_digest` (never `candidate_content_digest` — the
  rev-2 name is corrected here) keyed by
  `(base_commit, baseline_content_digest, env_digest, gate_argv)`.
- REF PROPAGATION + HEAD ASSERT (every lease): ref selection is
  explicit propagation, never inference: the parent passes
  `(lease_git_path, scratch_ref_SHA)`; the child clones-or-fetches
  that SHA and asserts `HEAD == SHA` before running. PRIMARY leases
  check out the scratch ref at intake and assert `HEAD == SHA` at
  gate time. BOTH are required — assert-without-propagation is safe
  but unusable — and safety never depends on the `main` default.
  No silent `main` fallback exists anywhere on the evaluation path;
  the `base_branch="main"` default (`worktree/manager.py:410`) is a
  contract violation wherever it can trigger, and the implementation
  MUST re-specify every branch point (creating a ref does not fix code
  that branches from `main` until the branch point is re-specified).
- GIT METADATA ISOLATION: per §T2(a)–(d) — sanitized mirror copies,
  independent clones for scratch-ref leases, no `worktree add` against
  the original, whole-delete cleanup. Push-disabling appears NOWHERE as
  an isolation argument: it is neither necessary (no remotes exist) nor
  sufficient (ref creation, worktree registration, and prune are all
  local operations a push control cannot see).
- WHY `base_commit`-ONLY KEYING IS INSUFFICIENT (rejected): the entire
  current loose set — 18 untracked files of the 28-file manifest — is
  invisible to a `base_commit` key. Any key that cannot see an evaluated
  byte cannot bind it.

## Q2 — Trusted test selection (RESOLVED in contract text)

The generated proposal MUST NOT decide its own examination — and per the
approval, neither may it narrow it. Affected coverage is a TRUSTED
ORCHESTRATION responsibility, computed deterministically from candidate
bytes; candidate-suggested tests are additive-only input.

- MANDATORY SET (always runs per node, regardless of selection),
  frozen in ONE versioned selection-config data file (never prose —
  the IDs went missing in prose once already), carrying the config
  revision, the exact node IDs, the M3 file paths with per-file node
  counts, and the owning-suite map revision; the SelectionRecord's
  mandatory-set digest binds the config revision automatically:
  M1 env+identity pin, node-level —
  `tests/unit/test_integration_identity.py::test_record_shape_and_env_keys`
  (the F4 assert that proves the authoritative env ran); M2
  lease-import integrity, node-level —
  `tests/unit/test_integration_harness_worker.py::test_f3c_prompt_kit_import_resolves_to_pinned_tree`
  + `...::test_fix_shape_gateway_prompt_preserves_real_diverge_bytes`
  (`:78` + `:1025`, which prove the §Q3 override resolves); M3 custody
  shape pins, file-level — `tests/unit/test_a3_patch_format.py` +
  `tests/unit/test_gateway_marker_refusal.py` (both files whole, which
  prove the candidate arrived intact). File-level is NOT literally
  rename-proof (a move OUT of the file escapes it) ⇒ the config ALSO
  pins per-file node counts as a tripwire (count change = finding).
  Missing files or node IDs fail closed. Contents frozen by
  ratification; additions/removals are contract amendments, never
  implementation discretion. Rationale for smallness: the mandatory
  set is the floor, not the ceiling; breadth comes from the affected
  set + broadenings. Tiny fixed layer + adaptive breadth stands.
- AFFECTED SET: orchestration maps the candidate diff (paths + symbols)
  through the OWNING-SUITE MAP (STC-owned, versioned, receipted by
  revision) to test files, plus declared dependents. The map is data,
  and stale map entries are findings with an owner, not silent gaps.
- BROADEN-ON-UNCERTAINTY: any path or symbol the map cannot resolve ⇒
  run the broader scope (owning directory suite at minimum; whole Gate-3
  class at maximum). Uncertainty NEVER narrows.
- NAMING RULE: any plausibly-affected-but-unrun test is named in the
  selection record with its reason. An unnamed omission is a defect in
  the receipt, not an optimization.
- CANDIDATE-SUGGESTED TESTS: appended to the run list with provenance
  marked `suggested`; they may ADD coverage and may satisfy NOTHING:
  a suggested test never displaces a mandatory or affected test, and a
  run consisting solely of suggested tests is invalid on its face.
- AUTO-DISABLE RESOLUTION (explicit, coverage grounds): the
  `runner.py:212-219` trap (`pytest_target` + `PYTEST_CURRENT_TEST`
  ⇒ mutmut off) takes effect ONLY when the caller passes no explicit
  `run_mutmut` kwarg — explicit kwargs take precedence
  (`runner.py:212-215`) — and BOTH production call sites pass
  explicit bools (per-node `run_mutmut=False`,
  `dialectic_runner.py:484`; merge `run_mutmut=self._champion_mutmut`,
  `:860`/:881, a `bool` defaulting `True`, `:673`). Coverage is
  therefore decided by the call sites, never by the trap: per-node
  runs declare `safeguards: [ruff, mypy, scoped-pytest]` with mutmut
  already excluded by ADR-INT-01 (the trap has nothing to take AND
  cannot arm); merge runs forbid `pytest_target` entirely (current
  rule kept) so the safeguard set stays whole-tree + mutmut by
  construction. Implementation scope: the precedence invariant is
  recorded as a code comment at the trap AND at each production call
  site, plus a small BEHAVIORAL check at the execution boundary
  proving safeguard selection survives the production call path
  (behavioral assertions on observed gate execution through the real
  call path — never AST assertions). No scoping may silently drop a
  safeguard — dropped safeguards are explicit, named, and separately
  approved.

## Q3 — Lease external-dependency discipline (RESOLVED in contract text)

Leases are self-contained; the ONLY external reachability is the pinned
read-only set below, and reaching it proves nothing about the candidate
until the import-integrity proof passes.

- ENUMERATED SET (closed; additions are contract amendments): the
  pinned prompt-kit tree (`4f442a6c…`), the pinned trace prompt-kit
  (`a24a9370…`-tree path), and the sst read-only API surface — each by
  content pin, mounted/visible read-only. No other host path is
  reachable through the override; the lease MUST NOT inherit ambient
  `PYTHONPATH` entries beyond the enumerated set (current close-out
  `PYTHONPATH` values with `/tmp/*-shim` entries are MACHINE STATE and
  are re-pinned or dropped at implementation — shims never ride
  implicitly).
- OVERRIDE MECHANICS: tests resolve the workspace via
  `STC_WORKSPACE_ROOT` when set, else the current `parents[3]`
  inference (`test_integration_harness_worker.py:71-75`) as fallback.
  In-lease runs set the override ALWAYS (deterministic); fallback exists
  for real-tree runs only. The fallback resolving inside a lease (a
  `/tmp` root) is a finding, not a supported configuration.
- IMPORT-INTEGRITY PROOF (per lease, before gates): assert
  `stc.__file__` resolves UNDER the lease path; assert `sys.path` order
  puts the lease first; assert each enumerated external resolves to its
  pinned content (spot-hash). Failure fails the lease closed — a test
  importing original-checkout STC code through the override evaluates
  the wrong bytes and its verdict is void.
- FULL-MANIFEST TRIPWIRE (detection scope, honest label): the lease
  tree is hashed as a FULL manifest (every enumerated file) at lease
  open, pre-gates, and close; content deltas AND additions/deletions
  fail the run (not just spot-checks). chmod-based prevention is
  DROPPED (theater on Windows/OneDrive). The guarantee is LABELED
  detection-with-fail-closed, never "read-only": a persistent change
  ⇒ the run fails; a transient write-then-restore inside one
  hash interval is invisible to hashing and is a RESIDUAL RISK the
  authorization accepts explicitly. Prevention awaits container
  read-only mounts — noted as future, not built. Precedent:
  `dispatch.py:127` ("Outer dirs under tripwire watch").
- REJECTED: allowed-skip carve-out (weakens the invariant for a fixable
  cause); provisioning sibling checkouts into leases (breaks
  self-containment); unpinned workspace pointers (reproduces the
  coupling the lease exists to prevent).

## Q4 — Authoritative environment (RESOLVED by comparison; floor RULED, D-α closed)

The contract's Target Environment is Python 3.12+ (`01_INVARIANTS.md:5`,
a floor) and `pyproject.toml:10` requires-python is `>=3.12` (a floor)
— but the F4 assert (`test_integration_identity.py:111`,
`startswith("3.12.")`) is a minor-series PIN, not a floor: it accepts
3.12.x ONLY and rejects 3.13. The earlier draft's claim that the test
"agrees with the contract" was factually wrong and is STRUCK. RULED
(D-α, operator 2026-09-19): FLOOR + amending the F4 test to a
`>= (3, 12)` check as implementation scope; narrow-the-contract-to-3.12.x
REJECTED. The floor establishes eligibility only: each actual env is
qualified individually via the authorization's env-acceptance
checklist (N4 polarity survives — `>= (3, 12)` still fails on 3.11) —
this certifies no future runtime in advance. Real-gates 3.11.15 remains
the anomaly either way. Probed 2026-09-19 (read-only, no installs):

| Env | Interpreter | ruff | mypy | pytest |
| --- | --- | --- | --- | --- |
| real-gates (`learn-anything/.venv`) | 3.11.15 | 0.16.1 | 2.3.0 | 9.1.1 |
| joint (`trace/.venv-linux`) | 3.12.3 | ABSENT | ABSENT | 9.1.1 |
| STC-owned 3.12 (proposed) | 3.12.x at construction | pinned at construction | pinned at construction | pinned at construction |

Comparison on the four ordered dimensions:

- OWNERSHIP: (i) STC-owned — the tranche owns the env; no foreign
  writer. (ii) TRACE one-shot — the TRACE project owns the env; STC
  receipts would depend on a foreign upgrade policy.
- CROSS-PROJECT COUPLING: (i) none — construction touches only
  STC-owned paths. (ii) HIGH — installs into a shared TRACE env; a
  TRACE-side upgrade can drift tool versions under already-issued STC
  receipts, splitting `env_digest` history.
- REPRODUCIBILITY: (i) full — pinned at construction, recreatable from
  the pin record. (ii) partial — reproducible only while TRACE holds
  still, which STC cannot compel.
- RECEIPT ENV BINDING: (i) `env_digest` binds an env the tranche
  controls; every receipt's env claim is auditable. (ii) same digest
  shape, weaker claim — the bound env can change out from under the
  digest's meaning via foreign upgrade (same digest string, drifted
  reality, unless re-probed per run — which concedes the point).

DECISION (matches Q2 approval): (i) STC-owned 3.12, constructed from
STC `pyproject.toml` + `uv.lock` via `uv sync --locked` — `--locked`
asserts the lockfile stays unchanged (installed-uv `--help` verified;
`--frozen` merely syncs without updating and is NOT sufficient
without an explicit lock check). The lockfile already covers the FULL
gate toolchain (ruff, mypy, pytest, mutmut — all four present in
`uv.lock` + `pyproject`), so construction needs no dependency
additions. No pip venv (split-brain), no TRACE-owned env (Q2 intent
preserved structurally). If the 3.12 interpreter or sync inputs are
unavailable: stop, report, no fallback. NO INSTALL IS AUTHORIZED by
this session — construction is post-approval work under a separate
installation authorization with this comparison attached.
Real-gates 3.11 stays a best-effort secondary leg, never authoritative.
REJECTED: 3.11-primary + assert relaxation (contradicts the contract;
  would need a Sovereign downgrade amendment); dual-authoritative envs
  (split-brain receipts); installing before comparison approval
  (ordering violation — now satisfied in the correct order).

ENV RULE, THREE-WAY SPLIT (ratified text, §5.5 — compatibility,
provenance, and reuse are DISTINCT and must never be conflated):
COMPATIBILITY (floor): the product supports Python ≥3.12 with
ruff/mypy/pytest/mutmut present + app deps installed; fail closed
ONLY on floor violation or missing tool (N4 stays as the
floor-polarity test). PROVENANCE (fingerprint): every check records
its EXACT env fingerprint (`env_digest`: interpreter string, tool
`--version`s, lockfile content hash, `os_platform`); patch drift is
a different fingerprint, recorded always, never a silent same.
REUSE (requalification policy): same (major, minor) + same
tools-present set + same lockfile content hash ⇒ the ENV side
requalifies; reuse ALSO requires the full T0 key match
(`base_commit`, `baseline_content_digest`, `gate_argv`) — the
lockfile content hash records dependency intent and is necessary,
NEVER sufficient by itself. ANY lockfile content change or
minor-version change ⇒ requalify the baseline (re-run T0).
Windows↔Linux results comparable with separate identities each.
The rule binds NOW; the construction numbers bind at construction —
freezing numbers for an env that does not exist yet would be
fabrication, and this draft does not do it.

## Non-claims and path governance (honesty audit surface)

- This draft was established by CODE READING on the stated lines plus
  the cited evidence hashes. It governs NOTHING until ratified,
  implemented, and preflighted on the actual path.
- No prototype was built: the skip test was "name a feasibility
  question code reading cannot settle" — none survived: scratch-commit
  isolation is standard git object-store semantics (independent clone ⇒
  disjoint ref stores), the selector is specified data + deterministic
  rules, and every isolation/selection claim carries a preflight
  proof obligation (N1–N6) that FAILS if the claim is false. A
  prototype would demonstrate feasibility only and is correctly absent.
- Path-governance table: T0–T7 transitions are ESTABLISHED by this
  draft (design path) and GOVERN only the ratification decision; the
  PRODUCTION path (implemented dispositions on the real call path) is
  established solely by the post-approval preflight. No sentence in
  this draft may be cited as production-pipeline evidence.
- Zero readiness assertions appear in this draft by construction; a
  readiness-shaped claim fails the session (none found on self-audit).

## Carried items (explicit owners, not this session's work)

- C1 Attempt-4 call cap: DERIVED from the actual call topology of the
  implemented dispositions and presented WITH the later execution
  authorization (Q3). This session assumes no number — including not
  three. Budget box stands: 12 CLI remaining INCLUDING the protected
  6-call verification reserve; implementation + deterministic preflight
  require ZERO live calls.
- C2 Env construction + version capture: post-approval, separate
  installation authorization, comparison attached. Construction via
  `uv sync --locked` on STC `pyproject.toml` + `uv.lock` (full
  toolchain, no additions). Captured versions are recorded by receipt
  (not by re-drafting this contract) unless they violate the
  floor rule — which fails closed instead. Reuse follows the
  requalification policy (§Q4), never silent spanning.
- C3 Mandatory-set contents: exact IDs + versioned selection config
  specified above (M1–M3); Sovereign approves or amends at
  ratification. The SELECTION RULE needs no further work; only the
  initial list contents are dispositional.
