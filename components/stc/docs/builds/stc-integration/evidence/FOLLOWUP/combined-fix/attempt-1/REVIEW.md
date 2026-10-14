# Combined-fix — B2 builder delivery (attempt-1): 4 fixes landed, W3 cut, 0 regressions

Record type: builder delivery (B2 implement + scripted proof)
Author role and date: combined-fix-builder / 2026-09-15
Packet: STC follow-up tranche, H1-prep findings → attempt-4 path (B1 readiness
in `evidence/FOLLOWUP/combined-fix/readiness.md`, hash `b878e811…`).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set re-verified byte-exact at B1 open (10/10, zero drift) and unchanged
at close except the owned hunks below. Pins: sst `079f4de6…` (clean
before/after), prompt-kit `4f442a6c…`, trace `a24a9370…` (all exact).
Environment: real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`)
+ joint `<ws>/trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`; ruff 0.16.1 / mypy 2.3.0.
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.
**0 live calls; 0 CLI sessions; $0.00; 6-call reserve untouched.**

## Delivery section

- Behavior/artifact changed and why: four of the five H1-prep workstreams
  implemented, each independently owned/tested/committable-alone (disjoint
  hunks; build order W5 → W4 → W2 → W1 per the W1 staleness rule):
  - W1 H1-context: `H1_CONTEXT_PACKAGE` (3921 B pinned payload, mechanically
    generated, never hand-edited) + closing-block frame hook after
    `SST_PROMPT_END`, before the A3 pin (pin + emit instruction stay last).
    SST bytes verbatim; no `allowed_paths` change; medium-profile assumption
    explicit (frame-budget caution).
  - W2 Marker refusal: MARKERS.md §5 exactly — `marker_refusal_reason`
    predicate (SST's own `_parse_json_dict`, column-0 `***`), refusal
    `ProviderGatewayError(category="stc_marker_refusal")`, `ok=True` ledger
    row with `stc-refused:` note, NEW `<stem>.refusals.jsonl` sidecar with
    full refused bytes, no internal retry, no byte rewriting anywhere.
    Placement inside `generate()` before `return` (the spec's allowed
    equivalent — required for ledger-note honesty, see readiness).
  - W4 G2 gate: D13 `-m "not live"` in the substrate pytest gate invocation.
  - W5 J1 attribution: bare-`+++ <path>` attribution arm in `audit_diff`
    (`/dev/null` excluded); no `render_merged_diff` change needed (synthetic
    arm already `b/` — the two agree post-fix); receipt/gate steps untouched
    (fail-closed on gates intact).
  - W3 G1 gate-debt: CUT at B1 with written reasons (readiness): the B1
    lease-faithful experiment triple-proved G1 (124 = 123 + 1 candidate;
    per-file attribution exact; product's own test shows 123), and no
    pre-authorized shape greens the gates — mirror exclusion leaves 7 ruff
    + 4 format + 18 mypy in src/tests; gate scoping is §5-contract-blocked;
    file-by-file debt fixes are not pre-authorized (and the evidence-116 is
    uneditable as immutable records). Coordinator decision recorded in
    readiness with the exact inventory + options. NOT implemented (no faith
    edits).
- Files or outputs changed: 4 product/test files modified (1 untracked loose
  + 3 tracked), 3 test files created, evidence under
  `evidence/FOLLOWUP/combined-fix/` (readiness + `attempt-1/` logs + this
  REVIEW). No commits, no STATE.md writes; sst/prompt-kit/trace read-only;
  `trace-lite/` never touched.
- Material implementation decisions: (a) W2 in-`generate` placement (above);
  (b) W1 staleness rule executed literally — post-W5 range rebuild is
  byte-IDENTICAL to the pinned artifact (W5's edit sits below all pinned
  ranges), payload stands, as-built whole-file shas recorded in-code
  (`auditor.py c59a8f40…`, other two unchanged); (c) W4/W1/W2 tests in NEW
  files (W4 because `test_substrate.py` is red at baseline for G1 reasons;
  W5 appended to green `test_judiciary.py`); (d) W5 `/dev/null` exclusion +
  the 2-byte-contrast reading (post-fix both shapes scan — the pre-fix
  bare→skip IS the bug); all per readiness, no deviations.
- Known limitations and checks not run: W3 unimplemented by design (gates
  still red on pre-existing debt — no admitted leg can verify while G1
  stands); mutmut's internal pytest path out of W4 scope (noted); no live
  calls (all proof scripted); full-suite pre-existing failures documented
  below with mirror-identical baselines.

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| B1 drift gate | rev-parse, 10 full-sha recomputes, numstat, 3 pins, sst status, 7 transcript hashes | HEAD `edf5389`; 10/10 exact; 594/0 + 333/7; pins exact; sst clean; all 7 h1-prep transcripts hash-exact; zero drift | readiness.md | Hash-bound |
| B1 G1 experiment | real `mirror_source_tree` → /tmp lease + exact cand-1 bytes via pristine SST custody + exact gate commands, real-gates | lease HAS all 8 evidence .py (gitignored `worktrees/` skipped, non-ignored `evidence/` scanned); ruff 124 = 123+1 (I001-only candidate); format 8 = 8; mypy 23 = 18+5; pytest collect reproduces `ModuleNotFoundError: praxist`; G1 CONFIRMED, no scope discrepancy (§3/~3-error figure is file-scoped replay) | readiness.md Gate 0 | /tmp scripts (kept out of tree) |
| W1 tests (new file) | `pytest tests/unit/test_gateway_h1_context.py`, both interpreters | 9/9 each: package hash-pin (`e0c814e5…`, 3921 B), artifact byte-equality, range-verbatim staleness tripwire, read-only head, placement (SST→context→pin→emit-last), D15/D7 verbatim, no-`allowed_paths`, sizing budgets, no frame `***` lines | `attempt-1/newtests-{real,joint}.log` (within 68/68) | 0 calls |
| W2 tests (new file, mandated name) | `pytest tests/unit/test_gateway_marker_refusal.py`, both interpreters | 17/17 each: full §5 matrix — exact P2 stdout + a2c0/a3c0 trailers refused, exact a1/a2c1 envelopes refused, synthetic trailer/raw/unparseable refused, truncation + branch-selection semantics, exact a3c1 + known-good + indented/bold/raw admitted, ledger `ok=True` + note + sidecar sha256 round-trip + no-F1-sidecar + single-harness-call, admitted byte-identical, D15/D7 | `attempt-1/newtests-{real,joint}.log` (within 68/68); exact live bytes with size+sha guard pins | 0 calls |
| W4 tests (new file) | `pytest tests/unit/test_pytest_gate_live_deselect.py`, both interpreters | 2/2 each: behavioral — live `assert False` probe deselected (exit 0, "1 passed, 1 deselected"), live skip cannot trip 0-skipped invariant | `attempt-1/newtests-{real,joint}.log` (within 68/68) | 0 calls; fail-safe probes (never live calls) |
| W5 tests (appended) | `pytest tests/unit/test_judiciary.py`, both interpreters | file green both (15 baseline + 5 new): bare attribution + filepath, 2-byte contrast collapse (rules+snippets equal), bare-clean APPROVED, `/dev/null` exclusion, multifile + gate-fail-closed intact | `attempt-1/newtests-{real,joint}.log` (within 68/68) | 0 calls |
| Veto/fail-closed rerun | `pytest tests/unit/test_integration_dialectic.py -m "not live"`, both interpreters | 61/61 EACH (12.56 s real, 13.14 s joint) | `attempt-1/veto-{real,joint}.log` | 0 calls |
| Full suite, real-gates | `pytest tests/unit tests/integration -m "not live"` (sequential) | 8 failed, 519 passed, 6 deselected (44:16) — ALL 8 pre-existing (see triage; whole-tree ruff still exactly 123 = new files contribute 0) | `attempt-1/full-real.log` | 0 calls |
| Full suite, joint | same on 3.12.3 (sequential) | 8 failed, 516 passed, 3 skipped (env-conditional gate-tool skipifs, pass on real), 6 deselected (31:30) — ALL 8 pre-existing | `attempt-1/full-joint.log` | 0 calls |
| Real baseline (pre-B2 mirror) | same 8 node IDs in `/tmp/combined-fix-lease` (pre-B2 bytes), real-gates | IDENTICAL 8 failed (124 = 123 + mirror's cand-1 file; circuit-breaker assert text identical) | `attempt-1/baseline-8-mirror-real.log` | Proves zero regressions |
| Joint baseline (pre-B2 mirror) | same 8 + identity, joint | IDENTICAL 8 failed; identity passes at base too | `attempt-1/baseline-joint-mirror.log` | Proves zero regressions |
| Owned-file gates | `ruff check` + `ruff format --check` + `mypy --strict --follow-imports=silent` (a3 precedent) on all 7 owned files | All checks passed; 7 formatted; no issues in 7 files | `attempt-1/ruff.log`, `attempt-1/mypy.log` | Owned files only (tree debt is W3's) |
| Confinement | sst status, pins, HEAD/log, STATE.md, diff audit | sst clean; 3 pins exact; HEAD `edf5389`, no new commits; STATE.md untouched; tracked hunks exactly 594/0 + 7/0 + 333/7 + 2/1 + 157/0; specs/worktrees/leases pollution restored after every run (0 ACTIVE leases); `trace-lite/` never touched | `attempt-1/sst-after.txt`; status-after-last-write below | Tree left + this record |
| Spend | 0 CLI sessions; no installs | $0.00; tranche still 8/20, 6-call reserve intact | this REVIEW | Fully scripted stage |

## Triage — the 8 failures are all pre-existing (mirror-identical both ends)

| Failure | Cause (out of my hunks' reach) | Base proof |
| --- | --- | --- |
| `test_cli_run_json_mode` (both) | E2E pipeline exit 1 at base (gates-red fixture) | Fails identically in pre-B2 mirror, both interpreters |
| `test_record_shape_and_env_keys` (real only) | Environmental: asserts `python_version.startswith("3.12.")`, real-gates is 3.11.15; passes on joint | Fails at base on 3.11, passes at base on 3.12 |
| `test_substrate` ×2 real / ×3 joint | G1 debt (ruff 123 at base AND patched — my files add 0); joint-only `test_injected_syntax_error` is a ruff-message-shape env difference | Identical node IDs + signatures in mirror baselines |
| `test_dag_pipeline` ×4 (both) | E2E pipeline halted on red gates (G1); circuit-breaker expects `FAIL (pytest)`, gets `FAIL (mypy, pytest)` | Identical node IDs + assert texts in mirror baselines |

Methodology notes (honest accounting): (a) the first full-suite attempt ran
both interpreters in PARALLEL and cross-contaminated via shared worktree
leases — DISCARDED; all evidence above is from SEQUENTIAL runs; (b) a
concurrent evidence write during joint-full was swept by the product's own
chaperone dynamic confinement (`dispatch.py:399`, attested in
`/tmp/stc-quarantine-hc82p7t3/violation.json`, 2 created + 2 modified-noted
items) — the two swept logs were recovered byte-complete and the joint sha
matches the violation attestation (`fcd81f35…`); outcomes unaffected
(mirror-joint baseline without concurrency fails the same 8); (c) one
mid-run `.leases.json` copy carried a mirror-path ACTIVE entry into the real
tree — repaired by removing that entry (11 entries, 0 ACTIVE); the joint run
then self-healed the registry via normal test re-lease (12 terminal entries,
0 ACTIVE at close).

## Verdict, reviewer only

ATTEMPT-1 COMPLETE (builder-reported outcome; B3 to rule).

- Criteria established: B1 zero-drift + decisive G1 experiment (G1 confirmed,
  W3 cut with coordinator decision); W1/W2/W4/W5 implemented per their specs
  (65 workstream tests: 9 + 17 + 2 + 5 new + 32 in-file neighbors, all green
  both interpreters within the 68/68 dedicated logs); veto 61/61 both;
  affected suites rerun (full unit+integration both interpreters);
  every failure reproduced identically at the pre-B2 base (zero regressions);
  owned files ruff+format+mypy-strict green; whole-tree ruff count unchanged
  (123); sst clean, pins exact, $0.00, reserve intact; zero product edits
  beyond the four workstream hunks; zero unexplained drift.
- Unmet criteria or missing evidence: W3 (G1 debt) is NOT fixed — no admitted
  leg can verify while G1 stands (coordinator options in readiness). The 8
  full-suite failures are pre-existing/out-of-scope (G1 + env + E2E), proven
  by mirror-identical baselines — not B4 repairs for this packet.
- Baseline failures versus new regressions: zero regressions (8 = 8 at base
  on both interpreters, identical node IDs + signatures; ruff debt count
  unchanged at 123). Frontier advanced: attempt-4 now has a verified H1
  context path, deterministic marker enforcement, D13-live-deselected gates,
  and closed J1 attribution — pending only the G1 debt decision.
- Exact scope of independent execution/inspection: (for B3 to fill).
- Next action: B3 rules on this record; coordinator decides W3 (debt tranche
  + evidence exclusion, or contract amendment) to unblock attempt-4 live
  verification.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings yet; the 8 suite failures are pre-existing with mirror-identical baselines, not B4 repairs) | — | — | — | W3 G1-debt decision rides to coordinator |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned product/test files)
29eb3906b35a7aad78206bbe1f17e20d9214a16a865e450b2b5c73056a501913  src/stc/integration/cli_gateway.py (W1+W2; untracked loose)
c59a8f408c0c8c5f7aff155c2360be14c696348e09b3a2edde46e7cdb270e21a  src/stc/judiciary/auditor.py (W5; tracked 7/0)
8958eae167c53ffdddd475dace8096161a6365806971c115e6aa4d7535862a0f  src/stc/substrate/runner.py (W4; tracked 2/1)
c87b3a74d1e653b68521d4c40592bf9faa0d40130a33fb0495f1f2bcf2a40d9d  tests/unit/test_judiciary.py (W5 tests; tracked 157/0)
# (tracked pre-existing loose-set mods, untouched: cli.py 594/0 2ddfd6cb…d82f1,
#  dispatch.py 333/7 dc75c56e…13c7 — still tasked-exact)
# CREATED (product tests)
c3c886b19b612d12c1e4ea5bb4034ffdcb696ca2ecb5ae0445f6d3bac79b91ba  tests/unit/test_gateway_h1_context.py (W1, 9 tests)
106806c187d53637a3d9f15eda2cf01bf0e9d99ef9330c8897e4c464611590c5  tests/unit/test_gateway_marker_refusal.py (W2, 17 tests)
103348a5538e51e2f253c7a249e205f97f2bc70bd77b8bd2d8d55e4ece036e60  tests/unit/test_pytest_gate_live_deselect.py (W4, 2 tests)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
b878e81163b4003ca160b14c4f5b5559a41deb0de04b49f4c440b640713f2766  evidence/FOLLOWUP/combined-fix/readiness.md
09e30f5f090266b27292407a79d7210a5513afcc050016918d8eed17c517dff8  evidence/FOLLOWUP/combined-fix/attempt-1/baseline-8-mirror-real.log
884585b8d0168b8995415d59b35f996f3478ec9ad506017470bfba79e4c46316  evidence/FOLLOWUP/combined-fix/attempt-1/baseline-joint-mirror.log
a8cb40b35c1db025c855b7b01d652ec3b3e2d88e31420190d586d4a52fbc6ddb  evidence/FOLLOWUP/combined-fix/attempt-1/full-joint.log
51f1417cdaa20b1387a5448f669a1e0ba3229de632e7af1d51c07b59381d3128  evidence/FOLLOWUP/combined-fix/attempt-1/full-real.log
050c52a2b0c61e8b681ef5c485e0bc03340b8d55148e0acef27d744c8be42033  evidence/FOLLOWUP/combined-fix/attempt-1/mypy.log
fcd81f35112f6b5a6fd92078c50c0669e3a1a6556837fcaa05a97862fa01def4  evidence/FOLLOWUP/combined-fix/attempt-1/newtests-joint.log
2ee27ecc2f00eca0b014019175043b15c14a5e5c39200a1c0997953f4c59176f  evidence/FOLLOWUP/combined-fix/attempt-1/newtests-real.log
ca12518fd2220b91c2981024717ba99ba46404ff3bdf3477aee3992735ab0b06  evidence/FOLLOWUP/combined-fix/attempt-1/ruff.log
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/combined-fix/attempt-1/sst-after.txt
75e39ddb98643ada9411d01d853c3f4cce5bae92480ba2d53beb50727d633cb7  evidence/FOLLOWUP/combined-fix/attempt-1/veto-real.log
03664e52d3042057306e2242f0677335ab40be82214bbc5b39fa5c64124dc61a  evidence/FOLLOWUP/combined-fix/attempt-1/veto-joint.log
```

`git diff` tracked hunks belonging to this session: exactly the three owned
hunks (`auditor.py` 7/0, `runner.py` 2/1, `test_judiciary.py` 157/0) atop the
two pre-existing loose-set mods (`cli.py` 594/0, `dispatch.py` 333/7).
