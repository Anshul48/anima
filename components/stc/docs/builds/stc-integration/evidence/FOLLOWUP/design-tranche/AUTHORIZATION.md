# Implementation + preflight authorization (CONDITIONALLY APPROVED — see status)

Status: CONDITIONALLY APPROVED 2026-09-19 (operator rulings §7 +
final-review qualifications folded; enumerated corrections §10).
Takes effect AFTER the §10 corrections are applied and the no-drift
guard re-passes — applied this turn, guard PASS (see the stop
report). NOTHING outside the §1 scope is authorized, and §1 takes
effect only under the §3 gate + §6 box. The redlined
WALKTHROUGH.md + RATIFICATION.md (same dir) are the normative
contract text; this file is the ONE coherent execution
authorization (no competing descriptions). Scope fence: the
candidate evaluation path only (creation → custody → per-node
gates → selection → merge → judiciary → champion judgment).

## 1. Scope (implemented, then preflighted — nothing else)

D-α…D-ζ + E1–E4 as redlined:

- D-α §5.5/Q4 (RULED floor): floor compatibility (≥3.12 + four
  tools + app deps) + per-check exact fingerprint + requalification
  policy for reuse + `uv sync --locked` construction. INCLUDES the
  F4-test amendment (`>= (3, 12)` check). The floor establishes
  eligibility only — each actual env is qualified individually via
  §3; no blanket certification of future releases. Reuse requires
  the full T0 key match AND the env requalification match; the
  lockfile content hash is necessary, NEVER sufficient by itself.
- D-β §5.3/T2: ref propagation AND head assert on EVERY lease +
  primary-lease checkout rule (checkout at intake, assert at gate
  time) + every branch point re-specified.
- D-γ T6/§5.6: exact diff-binding definition (base/result/policy
  frozen) + shared transport-only `normalize_diff()` at render AND
  audit + `merged_dir` passed to `_audit` + `git bundle` + rendered
  diff bytes in the evidence dir + linked merge record pinning
  exactly (`merge_scratch_ref`, `selection_outcome_ref`,
  `env_digest`, `merged_diff_sha256`); binding is established by
  the verified receipt-and-linked-record ensemble, not the receipt
  alone.
- D-δ §5.4/Q3: full-manifest tripwire (open/pre-gates/close;
  additions/deletions fail) labeled detection-with-fail-closed;
  chmod prevention dropped. Write-restore residual risk accepted
  explicitly (decision 2). The honest label
  ("detection-with-fail-closed, never read-only") MUST survive into
  the implementation's code comments, not just the contract text;
  "read-only" describes the external mount mode only, never the
  tripwire guarantee.
- D-ε §5.2/Q2: exact mandatory IDs (M1 node + M2 2 nodes + M3 both
  files) frozen in ONE versioned selection-config data file with
  per-file node-count tripwire; missing-fails-closed.
- D-ζ §5.2/§5.3/T2–T7: signed linked CustodyIntake + per-node
  SelectionRecord + selection-outcome record + merge record, with
  verification-consumption checks + ACTUAL argv per run alongside
  `contract_rev` + N6 tamper control (N6 names all four records;
  dossier digest list covers all four). ExecutionReceipt stays
  frozen (no new fields).
- E1: auto-disable rationale on coverage grounds + precedence
  invariant as code comment at trap AND call sites + behavioral
  check at the execution boundary (behavioral assertions, never
  AST). E2: Delta A1 reversion-watch sentence mirrored in T5
  RECEIPT (verbatim) + FOLLOWUP-a1-fix mirror citation relabeled
  (NOT Delta A1). E3: per-merge-evaluation qualification.
  E4: intake baseline-manifest re-hash (`--locked` semantics).

Untouched by this authorization: S5-1, S5-2, S5-3, §5.1, A1 body,
D1 (vehicle ADR-INT-02, RULED). `01_INVARIANTS.md` stays Sovereign-owned:
implementation follows the ratified text, never edits the file.

## 2. Installation box (`uv sync --locked`, separate gate)

Construction = STC `pyproject.toml` + `uv.lock` via
`uv sync --locked` (asserts the lockfile stays unchanged; the
lockfile already covers ruff/mypy/pytest/mutmut — no dependency
additions). No pip venv, no TRACE-owned env, no installs beyond
this box. If the 3.12 interpreter or sync inputs are unavailable:
STOP, report, no fallback. $0 installs default outside this box.

## 3. Env-acceptance checklist + gate (pre-approval iff exact-pass)

All five must hold on the constructed env, else NO pre-approval:

1. Floor ✓ — interpreter ≥3.12 (major, minor reported).
2. Tools ✓ — ruff/mypy/pytest/mutmut present + app deps installed
   (`--version` strings recorded).
3. Fingerprint recorded — exact `env_digest` (interpreter string,
   tool versions, lockfile content hash, `os_platform`) written to
   the env receipt.
4. F4 passes — the mandatory M1 node green under the amended
   `>= (3, 12)` check (D-α RULED floor).
5. Gates 1–2 green on the pinned baseline (T0 whole-tree Gates 1–3
   receipt pinned per `(base_commit, baseline_content_digest,
   env_digest, gate_argv)`; T0 re-runs on ANY requalification
   trigger — lockfile content change or minor-version change).

GATE: exact-pass on all five ⇒ pre-approval to run the preflight
stands WITHOUT re-approval. ANY deviation (floor miss, tool
missing/drifted, fingerprint surprise, F4 red, Gates 1–2 red,
requalification trigger) ⇒ STOP and seek EXPLICIT re-approval —
never silent proceed, never waiver by fallback. Passing this gate
qualifies THIS actual env only — the floor is eligibility, not a
blanket certification of future runtimes.

## 4. Preflight acceptance (production pipeline, real call path)

P1 green actual-path per-node run + P2 green actual-path
integration run (live-against-rendered AND bundle-against-rendered
diff checks pass) + P3 dry-run/collect counts owned + N1–N6 ALL
showing the REQUIRED red/green polarity + receipt chain resolves
unbroken + N5 original-repo identity byte-identical + SelectionRecord
validity (config revision bound, actual argv recorded, safeguard
declaration matches observed gate execution — the E1 behavioral
proof). A negative control showing the wrong polarity fails the
preflight. The readiness ruling is a SEPARATE decision on this
evidence — this authorization does not pre-rule it, and contains
zero readiness assertions by construction.

## 5. Stop conditions (any one stops the run with a report)

Wrong polarity on any negative control; HMAC/signature/auth
failure; N5 delta (original-repo ref/worktree identity drift);
foreign-path write (outside the lease + enumerated pinned set);
floor/tool violation; tripwire trip (persistent change); ANY
live-call attempt (HARD ABORT — see §6); CLI-cap hit.

## 6. Call accounting (hard box)

- 0 live gateway calls. HARD. Any live-call attempt aborts the run
  (stop condition) — it is never "one small call".
- ≤6 model-backed CLI sessions for implementation + preflight
  (V9 wording: builders = CLI-AGENT spend; local deterministic
  commands are uncounted but logged).
- The 6-call verification reserve stays UNTOUCHED (later
  verification only, never implementation).
- Cap-hit stops with a report (honest partial, never silent
  overrun). Attempt-4 needs its own execution authorization with
  a topology-derived cap — this file does not grant it.

## 7. Operator rulings (all four RULED 2026-09-19 — approval basis)

1. D-α: FLOOR + F4-test amendment RULED (narrow-to-3.12.x
   REJECTED). Floor = eligibility; each actual env qualified
   individually via §3. N4 polarity survives (`>= (3, 12)` fails
   on 3.11). V4 stands; the struck claim stays struck.
2. Detection-only externals ACCEPTED explicitly. Residual risk
   owned: transient write-then-restore is invisible to hashing;
   three checkpoints narrow the window but do not eliminate it.
   The honest label MUST survive into implementation comments.
3. Linked records + N6 ACCEPTED, with: (a) the T4
   selection-outcome record named in the N6 control list AND the
   dossier digest list; (b) merge-record fields pinned now
   (`merge_scratch_ref`, `selection_outcome_ref`, `env_digest`,
   `merged_diff_sha256`; mutmut disposition rides
   `ChampionResult`). CONFIRMED: binding is established by the
   verified receipt-and-linked-record ensemble, not the receipt
   alone.
4. Vehicle ADR-INT-02 CONFIRMED, with the D1 wording fix
   ("floor + fingerprint + requalification" — the word "freeze"
   denotes the rejected rule and appears in no recorded decision
   text).

## 8. Reconstruction-flag dispositions (all six closed 2026-09-19)

- F1 CONFIRMED: §5.6 is the right home (merge binding is a §5
  gates/receipts concern; A1 body stays untouched).
- F2 AMENDED: genuine catch — "Amendment A1" (Delta A1) vs the
  "A1 mirror-recursion fix" (FOLLOWUP a1-fix) collided. The
  dst-exclusion citation is KEPT but relabeled explicitly
  (FOLLOWUP a1-fix, NOT Delta A1); the REAL E2 — mirroring the
  extended Delta A1 reversion trigger — is restored as the
  verbatim reversion-watch sentence at the end of the T5 RECEIPT
  bullet. E2 is now satisfied (no-waiver rule honored).
- F3 CONFIRMED: T5-only placement suffices (§5.1's "re-run on
  every merge" implies per-merge counting; retry semantics pinned
  in T5 + P2 assert). No §5.1/Delta-A1 reopen.
- F4 CONFIRMED: behavioral check in implementation scope (drive
  `execute_gates` through the production call path, assert
  observed mutmut behavior matches the declaration); P1 asserts
  its verdict.
- F5 CONFIRMED, with tightening applied: T5's "T4 selection ref"
  → "T4 selection-outcome ref".
- F6 AMENDED: `pip_digest` stays recorded (M1 node shape
  untouched); the lockfile content hash is the stable reuse
  comparator BUT necessary, never sufficient — reuse requires
  the full T0 key match AND the env requalification match
  (final-review correction).

## 10. Approval corrections applied (enumerated — nothing travels by summary)

C1. WALKTHROUGH T2 anchor + DEPS: "A1" mirror citations relabeled
    FOLLOWUP a1-fix, explicitly NOT Delta A1 (F2).
C2. WALKTHROUGH T5 RECEIPT: verbatim Delta A1 reversion-watch
    sentence appended (the REAL E2); "T4 selection ref" →
    "T4 selection-outcome ref" (F5); merge-record fields pinned
    (`merge_scratch_ref`, `selection_outcome_ref`, `env_digest`,
    `merged_diff_sha256`); ensemble-binding reading stated (3b).
C3. WALKTHROUGH T4 RECEIPT: selection-outcome record consumption
    under N6 stated (3a).
C4. WALKTHROUGH T7 + RATIFICATION §5.6: dossier digest list covers
    all four linked records (3a).
C5. WALKTHROUGH Q4 + RATIFICATION §5.5: D-α RULED floor
    (narrow REJECTED); floor = eligibility, per-env qualification,
    no blanket future certification (1).
C6. WALKTHROUGH env_digest + Q4 REUSE + RATIFICATION §5.5 REUSE:
    lockfile content hash necessary, NEVER sufficient — reuse
    requires the full T0 key match AND the env requalification
    match (F6 amended).
C7. RATIFICATION §5.3: dst-subtree relabeled FOLLOWUP-a1-fix,
    NOT Delta A1 (F2); disposition row matches.
C8. RATIFICATION §5.6: merge-record fields pinned; ensemble
    binding stated (3b).
C9. RATIFICATION N6: selection-outcome record named in the
    control list (3a).
C10. RATIFICATION D1 + D1 row: "floor + fingerprint +
    requalification"; vehicle ADR-INT-02 RULED (4).
C11. RATIFICATION §5.5 row: D-α RULED floor recorded (1).
C12. AUTHORIZATION §§1/3/7/8: rulings recorded; honest label
    required in implementation comments; "read-only" scoped to
    the external mount mode only (2); §3 gate qualifies THIS
    env only (1).
C13. No-drift guard re-run after C1–C12: PASS (stop report).

## 9. Honesty block

- This authorization was established by CODE READING on the cited
  lines (re-probed cold 2026-09-19: HEAD `ea1ca30`, 28/28 hashes,
  pins sst `079f4de6`/prompt-kit `4f442a6c`/trace `a24a9370`, sst
  clean, numstat 1114+/14- on the 10 tracked product files) plus
  the cited evidence hashes. It governs NOTHING until approved,
  and after approval governs ONLY the §1 scope.
- Zero readiness assertions appear in this file by construction;
  a readiness-shaped claim fails the session (none found on
  self-audit). No claim here is established on a narrower path
  than the one it governs.
- No-drift guard re-probed at close (HEAD + 28/28 + pins +
  sst-clean + product numstat): see the stop report.
