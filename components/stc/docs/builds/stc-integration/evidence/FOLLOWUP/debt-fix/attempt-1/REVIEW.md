# Debt-fix — B2 builder delivery (attempt-1): 29-item debt retired, Gates 1+2 green, 0 regressions

Record type: builder delivery (B2 adopt + complete + scripted proof)
Author role and date: debt-fix-adopter / 2026-09-18
Packet: STC follow-up tranche, G1 gate-debt retirement + evidence exclusion
(B1 readiness in `evidence/FOLLOWUP/debt-fix/readiness.md`; suspension state
in `evidence/FOLLOWUP/debt-fix/SUSPENDED.md`, adopted item-by-item, nothing
inherited).
Base/candidate identity: stc HEAD
`edf5389873e4d4a2a4752ee0aa2159289398495e` + loose set re-verified
byte-exact at adopt open (17/17 SUSPENDED snapshot + all combined-owned +
loose pins) and unchanged at close except the owned B2 hunks below (which
were already applied at suspension; this session applied ZERO product
edits — adoption, verification, and proof only). Pins: sst
`079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after),
prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` (all exact).
Environment: real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`)
+ joint `<ws>/trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc` (real tree) or the lease mirror
(item 3); ruff 0.16.1 / mypy 2.3.0 / pytest 9.1.1 (both interpreters).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`;
this packet = `evidence/FOLLOWUP/debt-fix/` with `readiness.md` (B1),
`baseline/` (B1 oracles, reconciled below), `attempt-1/` (this delivery +
proof), `SUSPENDED.md` (coordinator record, read-only, never edited).
**0 live calls; 0 CLI sessions; $0.00; tranche still 8/20, 6-call reserve
intact.**

## Delivery section

- Behavior/artifact changed and why: the 29-item G1 debt inventory is
  RETIRED (7 ruff + 4 format + 18 mypy, all lint/format/mypy-only, zero
  behavior change) and the immutable evidence dir is excluded from the
  Gate-1 lint scan via project config — executing coordinator options
  (a)+(b) from the combined W3 CUT. Gates 1+2 are GREEN on the lease
  (`ruff check .` / `ruff format --check .` / `mypy --strict src tests`
  all exit 0, substrate-argv-exact, in a lease-faithful mirror); the
  product's own G1 proof (substrate ×2) FLIPPED red→green on real-gates;
  every other suite outcome is IDENTICAL to its pre-fix oracle (zero
  regressions, proven per-suite and whole-tree on both interpreters).
- Files or outputs changed: 14 product/test files carry the B2 debt hunks
  (5 tracked pure-debt diffs + `cli.py` 1-line delta + 8 untracked debt
  files — all confirmed line-by-line against the B1 per-debt plan, §Item-1
  below) + evidence under `evidence/FOLLOWUP/debt-fix/attempt-1/` (21
  verified logs + 3 run/verify scripts + this REVIEW). This session
  applied no product edits (all 29 items were already applied at
  suspension; item 1 confirmed each and found nothing unapplied). No
  commits, no STATE.md writes; sst/prompt-kit/trace read-only;
  `trace-lite/` never listed, read, or written.
- Material implementation decisions: (a) full drift gate FIRST (17/17
  snapshot hashes + combined-owned + pins + numstat exact before any
  other work); the one extra delta found (2 specs timestamp-pollution
  files) was restored to HEAD per the combined "restore pollution"
  precedent, returning the tree to snapshot-exact 10 files 1114+/14-;
  (b) every inherited partial log treated as UNVERIFIED: the 3 gate logs
  reproduced BYTE-IDENTICAL (adopted), all suite partials superseded by
  fresh verified reruns (old hashes recorded below); baseline oracles
  reconciled by count + normalized diff, never trusted blindly; (c) all
  suite output staged in `/tmp/debtfix-stage/` during runs and copied to
  evidence/ only after completion (no concurrent evidence writes — the
  combined chaperone-sweep lesson); (d) mirror Gate-3 runs strictly
  SEQUENTIAL (combined parallel-contamination lesson); per-file reruns use
  `-q --tb=short` (byte-shape match to baseline) while item-3 uses the
  exact substrate argv (`-v --tb=short -m "not live"`); (e) the surviving
  /tmp diag script was adopted AND fixed (strict-apply order bug) and is
  preserved in-packet with the mirror script and the reconstruction
  prover for independent re-execution.
- Known limitations and checks not run: Gate 3 is NOT exit-0 (6 reds on
  real-gates, 8 on joint — all env/commit-blocked with identical
  pre-signatures, triaged per-test below; literal exit-0 rides to
  coordinator as findings F1–F4, not scope creep); joint Gates 1+2 are
  env-blocked (no ruff/mypy modules — F1); mutmut Gate 4 attempted in the
  briefed 30-min box (see MUTMUT-ROW); no live calls (all proof
  scripted); E2/E3 lease-dependency experiments not re-executed
  (mechanism re-observed at full scale in the mirror Gate-3 runs —
  W1/W2 green with whole-tree evidence; E2's red shape is not rerunnable
  post-fix by construction).

## Adoption gate (SUSPENDED items 0–6 disposition)

- Drift gate (FIRST): HEAD `edf5389` exact; 17/17 snapshot first16 exact
  (full-sha recompute); combined-owned `cli_gateway 29eb3906…`,
  `auditor c59a8f40…`, `runner 8958eae1…`, `test_judiciary c87b3a74…`,
  `h1 c3c886b1…`, `refusal 106806c1…`, `deselect 103348a5…` all exact;
  loose `dispatch dc75c56e…`, `dialectic_runner c072f1da…`,
  `harness_worker ced79ed5…`, `test_harness e96db8d0…`, `test_a3
  f99b2785…`, `winner_carry 0b5c3a8a…`, `__init__ 10571421…` all exact;
  pins exact; sst status clean. The 10 owned tracked files sum to exactly
  1114+/14- after restoring the specs pollution (below). **Zero
  unexplained drift — PROCEED.**
- Explained drift (1): `specs/invariants/SAMPLE_AUTH_INVARIANTS.md` +
  `TEST_DAG_SPEC_INVARIANTS.md` (2/2 + 2/2, Timestamp+Checksum lines
  only, written 2026-09-15T07:07Z inside the suspended session) — the
  known test-regeneration pollution class (combined REVIEW: "restored
  after every run"). Restored via `git checkout --` (precedented
  cleanup, not a product edit); numstat now snapshot-exact.
- Adopted-record notes (info-grade, all verified immaterial): (a)
  `baseline/` holds 19 logs, not 18 (SUSPENDED count quirk — all 19
  inventoried and reconciled); (b) `test_judiciary.py` collects 22, not
  the combined prose "15+5" (file hash-identical; 68-composition solved:
  9+17+2+22+18 with `test_a3` contributing 18); (c) bare-`pytest`
  (testpaths) order is integration-first vs baseline's explicit
  unit-first path order — counts AND node sets proven identical, and the
  bare form is the substrate-faithful one; (d) `worktrees/` IS copied
  into lease mirrors (code reads `_MIRROR_SKIP_DIRS` + dst-subtree only);
  the combined "gitignored worktrees/ skipped" holds at the RUFF layer
  (`.gitignore`), not the mirror layer — harmless to all gates
  (byte-faithful: B1 E3 mirror carries the same checkout).
- SUSPENDED items 1–6: ALL CLOSED — (1) 29/29 + exclusion confirmed
  line-by-line, 0 unapplied (§Item-1); (2) all missing post logs produced
  (substrate2/3, g2-collect ×2, judiciary ×2, compiler-cli-joint) plus
  fresh verified reruns superseding every partial; (3) mirror lease
  gates on both interpreters with honest Gate-3 reporting (findings
  F1–F4); (4) DIAGNOSTIC e2e green (labeled, not live acceptance);
  (5) this REVIEW; (6) handoff hashes below.

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Adopt drift gate | rev-parse, 17 full-sha recomputes, loose-set + pins, sst status, numstat | HEAD `edf5389`; 17/17 exact; owned + pins exact; sst clean; 1114+/14- after precedented pollution restore; zero unexplained drift | this REVIEW (§Adoption) | Hash-bound |
| B2 reverse-reconstruction ×2 | `verify-reconstructions.py`: reverse planned fixes, re-hash (/tmp run, preserved in-packet) | cli.py minus 1 line == pinned `2ddfd6cb…d82f1`; dialectic-test minus 4 sites == pinned `eea1a7ee…0ec0` — byte-exact both | `attempt-1/verify-reconstructions.py` | Strongest proof: pre-image + delta-exactness |
| Gates 1+2, real tree | `[py -m ruff check .]`, `[py -m ruff format --check .]`, `[py -m mypy --strict src tests]` (substrate-argv-exact, gate env) | All checks passed! RC 0; 106 files formatted RC 0; no issues in 67 files RC 0 — byte-identical to the 3 inherited partials | `attempt-1/ruff-check.log`, `ruff-format.log`, `mypy.log` | Real tree; excludes evidence/ per config |
| P01 post (adapters/identity/memory) | `-q --tb=short` both interpreters | real 1 failed (record_shape env assert, same node/assert, +1 line shift from the planned I001 blank line) + 114 passed; joint 115 passed byte-identical to baseline modulo durations | `attempt-1/p01-postfiles-{real,joint}.log` | Supersedes partials `24baf412…`, `d925170f…` (outcome-identical) |
| Veto/newtests post | `-q --tb=short -m "not live"` both (`-m` moot: 89/89 collect either way) | 89/89 BOTH (61 veto + 9 H1 + 17 refusal + 2 deselect; W1 tripwire green — no range shift) | `attempt-1/veto-newtests-post-{real,joint}.log` | Supersedes `fa71ed99…`, `7f2668e1…` |
| Fixture/pipeline post | `-q --tb=short -m "not live"` both | real 5 passed/1 deselected BYTE-IDENTICAL to baseline (fresh 82.14 s run); joint 3/2-skip/1-desel identical | `attempt-1/fixture-pipeline-post-{real,joint}.log` | Supersedes `785ce690…`, `964aa8b5…` |
| Compiler/CLI post | `-q --tb=short` both (joint is the missing log) | BOTH 1 failed (`test_cli_run_json_mode`, committed-bytes E2E, `assert 1 == 0`) + 52 passed, normalized-identical to baseline | `attempt-1/compiler-cli-post-{real,joint}.log` | Supersedes `8fef2177…`; E2E gates committed bytes (unaffected by design) |
| Judiciary rerun (missing log) | `test_judiciary.py -q` both | 22/22 BOTH (path provably untouched: `auditor c59a8f40…`, `test_judiciary c87b3a74…` hash-exact) | `attempt-1/judiciary-post-{real,joint}.log` | Corroborates combined 68/68 (whose judiciary share is 22) |
| G2 collect post (missing logs) | `--collect-only -q` bare + `-m "not live"`, real-gates | 533 bare / 527+6 deselected; node SETS sorted-identical to baseline (order differs: gate-faithful testpaths order vs baseline explicit unit-first) | `attempt-1/g2-collect-post-{bare,deselected}.log` | Proves no test added/removed/renamed |
| Substrate post (missing logs) | the 2 named nodes (real) / +injected-syntax node (joint) | real **2 passed (FLIP from 2 failed)** — product's own G1 proof green; joint 3 failed with IDENTICAL tool-absence signatures (`No module named ruff`) | `attempt-1/substrate2-post-real.log`, `substrate3-post-joint.log` | The B2 headline flip |
| Mirror Gates 1+2, real | exact substrate argv in `/tmp/debtfix-lease-gates` (real `mirror_source_tree`, HEAD-bound, whole-tree evidence) | ruff-check RC 0, ruff-format RC 0 (106 files), mypy RC 0 (67 files) | `attempt-1/mirror-gates-real.log` + `run-mirror-gates.py` | Lease-faithful; `.git` in, skip-set out |
| Mirror Gates 1+2, joint | same, joint interpreter | RC 1 ×3, purely `No module named ruff/mypy` → finding F1 (env-blocked, options, no scope creep) | `attempt-1/mirror-gates-joint.log` | Bytes proven green by the real leg |
| Mirror Gate-3, real | `[py -m pytest -v --tb=short -m "not live"]` full suite in mirror (sequential; wall-boxed, argv-exact) | **6 failed, 519 passed, 2 skipped, 6 deselected** (750 s): substrate ×2 flipped to PASS; dag×4 + cli_json + record_shape persist identical; 2 harness procedural skips = lease-layout artifact (F2) | `attempt-1/mirror-gate3-real.log` | Zero regressions vs combined 8 (minus the flip) |
| Mirror Gate-3, joint | same, joint interpreter (sequential after real) | **8 failed, 514 passed, 5 skipped, 6 deselected** (164 s): identical 8 fails as combined (dag×4 + cli_json + substrate×3 tool-absence); +2 lease-layout skips (F2) | `attempt-1/mirror-gate3-joint.log` | Zero regressions (identical node set) |
| DIAGNOSTIC e2e (item 4) | `run-diag-e2e.py`: hand pins → strict-apply → custody → whole-tree Gates 1+2 + targeted Gate-3 + collect → HMAC receipt → score → judiciary → merge re-apply → champion → dossier (/tmp only) | RC 0: custody success (354 B `84d2058f…`), gates green (collect 534 = 533+1 pin), receipt passing + HMAC self-verify, score 1.00, judiciary APPROVED (0 findings), merge + re-audit APPROVED, 4 dossier artifacts hashed | `attempt-1/diag-e2e.log` + `run-diag-e2e.py` | DIAGNOSTIC, not live acceptance (hand pins, no search/competition, targeted Gate-3) |
| Mutmut box (Gate 4) | exact substrate argv `[py -m mutmut run]` cwd diag merge tree, `timeout -k 120 1800` (30-min box) | Attempted in-box (~3 min): 42 files mutated, then `failed to collect stats. runner returned 1` — baseline suite red (the Gate-3 reds), kill-rate UNMEASURED. Invocation staged in-log; unblocks when Gate-3 greens | `attempt-1/mutmut-box.log` | Honest unrun-with-cause (gate-ordering, not tool failure) |
| Baseline-oracle reconciliation | counts + normalized diffs vs `baseline/` (19 logs, all inventoried) | ruff 123 `-->`, 7 src/tests at plan lines; format 8 files; mypy 18 errors at 15 plan sites; suite oracles match post modulo durations + the 1 explained shift; E2/E3 mechanism re-observed (W1/W2 green whole-tree in mirror) | `baseline/` (hashes in Identity; originals byte-preserved, never edited) | Oracles corroborated, not inherited |
| Confinement | sst status, pins, HEAD/log, STATE.md, diff audit, mtime survey | sst clean; 3 pins exact; HEAD `edf5389`, no new commits; STATE.md untouched; tracked hunks exactly the 10 owned files (1114+/14-); unpinned untracked (dossier, test_run_e2e, test_dag_pipeline) predate B2 (mtimes 09-06/09-14); `trace-lite/` never touched; worktrees/ + `.leases.json` left clean (0 ACTIVE) | this REVIEW; status-after-last-write below | Tree left + this record |
| Spend | 0 CLI sessions; no installs; no env writes outside /tmp + evidence/ | $0.00; tranche still 8/20, 6-call reserve intact | this REVIEW | Fully scripted stage |

## Item-1 — line-by-line B2 confirmation vs the B1 per-debt plan (29/29 + exclusion; 0 unapplied)

Proof key: [R]everse-reconstruction byte-exact to pinned pre-hash;
[D]iff pure-debt (file was clean at B1, current `git diff` is the whole
delta); [S]ite-inspected fixed code vs plan + baseline pre-image;
[G]reen gates (`ruff check`, `ruff format --check`, `mypy --strict`
all RC 0); [T]est-identity (own suite post == pre oracle).

Ruff (7/7): `adapters.py:170` I001 blank-line fix [S: `--fix` hunk
present; G; T p01]; `identity.py:41` RUF022 `__all__` sort [S: current
order == baseline `--fix` pre-image exactly, name set identical; G; T];
`memory.py:292` C416 `list(entry.keywords)` [S: pre-image
`[kw for kw in …]` replaced; G; T]; `test_adapters.py:3` I001 [S; G; T];
`test_adapters.py:226→227` RUF043 `match=r"1\\.\\.3"` [S: literal
`1..3` proven at `adapters.py:292` message; G; T passing re-proves
match]; `test_adapters.py:419→416` RUF043 `match=r"stc\\.spec_id"` [S:
literal proven at `_check_binding("evidence stc.spec_id", …)` (now
`:410`, −3 net shift from format joins explained); G; T];
`test_identity.py:3` I001 [S; G; T p01].

Format (4/4): `adapters.py`, `memory.py`, `test_adapters.py`,
`test_memory.py` [S: spot-joined lines match baseline `--diff`
pre-images (e.g. adapters `:330`); G `106 files already formatted`;
T all own suites identical].

Mypy (18/18): yaml `import-untyped` ×5 — `bundler.py:12`,
`cli.py:20`, `test_pipeline.py:6`, `test_compiler.py:22`,
`test_cli.py:6`, each per-line `# type: ignore[import-untyped]`
[D for 4 (pure 1-line diffs); R for cli.py (whole-file pre-image
`2ddfd6cb…d82f1`); G; T]; `no-any-return` ×6 — `bundler.py:325`
(`dumped: str`, [D]); `dialectic:1170,1217` (`text: str`, [R] whole-file
`eea1a7ee…0ec0`); `fixture:271,278,283` (`payload…`/`events…` typed
locals, [S] line shifts +1/+2 as predicted; declared types match the
`->` annotations); `test_adapters.py:175` arg-type + dropped
`[list-item]` ignore (`("pytest -q",)` tuple, [S]; `__post_init__`
`tuple(…)` yields identical bytes; G `warn_unused_ignores` clean; T];
`dialectic:176` + `fixture:182` `[dict-item]`→`[assignment]` stale-code
correction (comment-only, [R] for dialectic, [S] for fixture — the
"real" `ProviderProfile` construction correctly NOT implemented per the
brief's behavior-change rule); `dialectic:577` dead `[misc]` comment
deleted ([R]). All 18 baseline error lines verified present in
`baseline/mypy.log` at the plan's 15 sites [reconciled].

Exclusion (byte-exact): `pyproject.toml` +14/0 under `[tool.ruff]` —
12-line comment citing this record + `01_INVARIANTS.md` §5 (Gate-1
commands stay literal; `.gitignore`/`worktrees/` precedent; lease
contents stay whole-tree per E2; records immutable per FIX-B5 V1-INFO-1)
+ `exclude = ["docs/builds/stc-integration/evidence"]` [D; G]. The
guardrail's four conditions hold: proven non-dependency (E3 + grep +
no-`__init__` + `ModuleNotFoundError` + judiciary/mypy/pytest scope
proofs, all re-read and re-observed), originals byte-preserved (evidence
hashes untouched — no evidence file modified this session), full
src/tests/config/fixture coverage retained, exclusion explicitly
recorded here and in-config.

No other files touched: tracked numstat is EXACTLY the 10 owned files
(1114+/14-); untracked debt files contain exactly the planned fixes
(proven for 2 by whole-file reconstruction, inspected for 6, all gated
green + suite-identical); every other pinned hash exact; unpinned
untracked (`dossier.py`, `test_run_e2e.py`, `test_dag_pipeline.py`)
predate B2 by mtime; specs pollution restored twice (adopt + close).

## Triage — Gate-3 reds are all env/commit-blocked (identical pre-signatures; zero regressions)

| Failure | Cause (out of B2 reach) | Proof of pre-existence |
| --- | --- | --- |
| `test_dag_pipeline` ×4 (both) | E2E pipeline halted on red gates; gates COMMITTED-`main` bytes (pre-debt) via `git worktree add` — working-tree fixes cannot reach them | Identical node IDs + assert texts in combined `full-{real,joint}.log` (order differs only: gate-faithful testpaths order) |
| `test_cli_run_json_mode` (both) | Same committed-bytes E2E (`assert 1 == 0`) | Normalized-identical to `baseline/compiler-cli-pre-*` (durations only) + combined full logs |
| `test_record_shape_and_env_keys` (real only) | Environmental: asserts 3.12, real-gates is 3.11.15; passes on joint | Same node/assert as baseline (+1 planned line shift); passes joint pre and post |
| `test_substrate` ×3 (joint only) | Env: joint lacks ruff/mypy modules (`No module named ruff/mypy`) | Signatures identical to `baseline/substrate3-pre-joint.log` (run-ids/timings only) |
| substrate ×2 (real) | — | **FLIPPED to PASS (post-fix + mirror Gate-3)** — the retired debt |

Coordinator findings (env/commit-blocked → options, NOT scope creep):
F1 joint tool absence (Gates 1+2 un-runnable on joint): (a) install
ruff+mypy into the joint env, (b) keep joint as pytest-only leg.
F2 lease-layout procedural skips (2 harness tests skip in ANY lease,
incl. live, via import-path `_workspace_root()`; collide with the §5
0-skipped invariant which forces exit 1): (a) accept + document, (b)
follow-up: lease-aware workspace resolution, (c) contract
clarification. F3 committed-bytes E2E reds (dag×4 + cli_json): uncover
at commit/attempt-4 (pre-existing, routed). F4 3.11-vs-3.12 env assert:
disposition (version pin or dual-env-tolerant assert — coordinator
call). Observation (info): `[tool.mutmut]` uses deprecated config keys
(`paths_to_mutate`, `tests_dir`) — works with warnings on mutmut 3.8.0;
hygiene follow-up, not this packet.

## Verdict, reviewer only

ATTEMPT-1 COMPLETE (builder-reported outcome; final verification to rule).

- Criteria established: adopt drift gate zero (17/17 + owned + pins +
  numstat, 1 explained pollution restored); B1 per-debt plan confirmed
  29/29 + byte-exact exclusion (2 whole-file reverse-reconstructions,
  5 pure-debt diffs, all sites inspected, 0 unapplied, 0 product edits
  by this session); Gates 1+2 green real-tree AND lease-mirror
  (substrate-argv-exact); every affected suite rerun post-fix on both
  interpreters with outcomes identical to reconciled oracles (1
  explained +1 shift; 1 explained byte-identical duration); substrate
  ×2 flipped red→green (real); whole-tree Gate-3 in mirror both
  interpreters with zero regressions (real 8→6 exactly minus the flip,
  joint identical 8); DIAGNOSTIC e2e green (custody→gates→judiciary→
  champion→dossier); mutmut attempted in-box with honest
  unrun-with-cause; sst clean, pins exact, $0.00, reserve intact; no
  behavior change (test-identity everywhere + fix-by-fix neutrality);
  no weakened checks, no removed tests, no blanket ignores.
- Unmet criteria or missing evidence: Gate-3 literal exit-0 (blocked by
  F1–F4, all env/commit, none debt-owned — debt's share is DONE: Gates
  1+2 green + substrate flip); Gate-4 kill-rate (baseline-red-blocked,
  unblocks with Gate-3). Both ride to coordinator, not B4.
- Baseline failures versus new regressions: ZERO regressions (every
  post outcome == its pre oracle modulo durations + 1 explained shift;
  whole-tree failure sets == combined sets minus the substrate flip on
  real / identical on joint). Frontier advanced: attempt-4 now has a
  verified GREEN Gates-1+2 lease path, a flipped product G1 proof, and
  a green diagnostic champion chain — pending only the F1–F4
  env/commit dispositions.
- Exact scope of independent execution/inspection: (for final verification to fill).
- Next action: final verification rules on this record (0-call
  hash/command replays); coordinator dispositions F1–F4; then attempt-4
  → erratum + commit + report.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings; the 6/8 Gate-3 reds are pre-existing env/commit blocks with identical pre-signatures, not B4 repairs) | — | — | — | F1–F4 ride to coordinator; debt share complete |

## Identity (sha256 of every file created or modified)

```text
# B2 DEBT-MODIFIED product/test files (post-fix bytes, this packet's candidate delta)
96cf197e9b1c731b2c5bfb59d5f0d5b2d7a9f8a63a30221a52c784e446f8ac51  pyproject.toml (exclusion +14/0)
d0a97611358454ecdeafdf0273a47cf0803850d2cca6f249503adcbb90921bea  src/stc/cli.py (yaml ignore; pre 2ddfd6cb…d82f1)
b21be978def892872c64b46783b603c01117b7f64bf9bad1e381fe52c3b73e0a  src/stc/compiler/bundler.py (yaml ignore + typed local)
8f53fba96ee78ab6709e7722c2a1fdffa0c9ff9383654fcebba36e14a4dd903e  src/stc/integration/adapters.py (I001 + format + tuple-site file)
8edb6892e66d9067b6a15dfd63f5178a3064f2db1f6e93e146273b1fc4b3fbca  src/stc/integration/identity.py (RUF022 sort)
3ba90a5ce51db3a8a768afd6e5a9d2942ff8384ac0e478ce3659126743e5f712  src/stc/integration/memory.py (C416 + format)
93f54ff4a940cf6b87d9cdc491ce57604f8e6b1217bc9d1db4419002b2c2480c  tests/integration/test_pipeline.py (yaml ignore)
6ffe08c264cc55147dea26aadf06555c3cd43b98174c7999792c45335c05341b  tests/integration/test_dialectic_fixture.py (3 no-any-return + assignment)
168c12675c1d9e1d4765652512610d9150f2e4312a3a2635102f1416b8fde6ca  tests/unit/test_cli.py (yaml ignore)
bc2b355054133dea216bd51f740744aa2b50a06fa023b7436d347cee62af2126  tests/unit/test_compiler.py (yaml ignore)
ee60aba90d911363a4f90c70e66c014f917541ac3a49b64e78a8d7544f51edec  tests/unit/test_integration_adapters.py (I001 + RUF043x2 + format + tuple)
031bc293a9fb1684ca77495c8a0c322d94672c888689578f79cd971d74b29bf1  tests/unit/test_integration_identity.py (I001)
143fe07b9097527ab55613b3874e4445ad93aa3ccc2ca3955da58368d0f687db  tests/unit/test_integration_memory.py (format)
8bc8005dc71af8f7d87d449540dbd4ee1c2b1b4e017a5e0068a082c4a9eb8f38  tests/unit/test_integration_dialectic.py (2 no-any-return + assignment + del; pre eea1a7ee…0ec0)
# COMBINED/PREDECESSOR-OWNED (verified unchanged this session, first16 == SUSPENDED pins)
c59a8f408c0c8c5f7aff155c2360be14c696348e09b3a2edde46e7cdb270e21a  src/stc/judiciary/auditor.py (W5)
dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7  src/stc/orchestrator/dispatch.py (333/7)
8958eae167c53ffdddd475dace8096161a6365806971c115e6aa4d7535862a0f  src/stc/substrate/runner.py (W4)
c87b3a74d1e653b68521d4c40592bf9faa0d40130a33fb0495f1f2bcf2a40d9d  tests/unit/test_judiciary.py (W5 tests)
29eb3906b35a7aad78206bbe1f17e20d9214a16a865e450b2b5c73056a501913  src/stc/integration/cli_gateway.py (W1+W2)
c072f1dac2725f470bfeb9753288e2158064838467784d3f8ceb279b640a0ff5  src/stc/integration/dialectic_runner.py (A1)
c3c886b19b612d12c1e4ea5bb4034ffdcb696ca2ecb5ae0445f6d3bac79b91ba  tests/unit/test_gateway_h1_context.py (W1)
106806c187d53637a3d9f15eda2cf01bf0e9d99ef9330c8897e4c464611590c5  tests/unit/test_gateway_marker_refusal.py (W2)
103348a5538e51e2f253c7a249e205f97f2bc70bd77b8bd2d8d55e4ece036e60  tests/unit/test_pytest_gate_live_deselect.py (W4)
ced79ed572d50f5c67d7e8556fe08127f59e0c529fc50bdaf1bc6898805a7867  src/stc/integration/harness_worker.py
e96db8d00a2950166f77ec6069ab98d9a944a344bfb452a4ffb7e6f3ce070b45  tests/unit/test_integration_harness_worker.py
0b5c3a8a85dea963ef8b95e43679bc504020152d105e89a2aaef05b677b69762  tests/unit/test_winner_carry.py
f99b278588e0c7eec956a6203e5475c78f95c3d4e76f2946c892a13a125b1f2b  tests/unit/test_a3_patch_format.py
105714219afcfbef9c81c50ce4216de4ce93096482aff2a4597cb4aaf04bac40  src/stc/integration/__init__.py
# CREATED attempt-1/ (this REVIEW.md is the record itself and is not self-listed)
402d4753d29b410f3b944c567cf9b97fa16076a3756c61ba2a2775d3ca85afb8  evidence/FOLLOWUP/debt-fix/attempt-1/compiler-cli-post-real.log
f3d53a7b1f56b6b441b1c57c3af5c161427f02259b2f6a97e1bfa838169f5417  evidence/FOLLOWUP/debt-fix/attempt-1/compiler-cli-post-joint.log
d17a3408f7d2eac16dd20847cb19b2d3c4afe45cb41ed352eb5f06168602049e  evidence/FOLLOWUP/debt-fix/attempt-1/diag-e2e.log
2cd4c93a06c40e5f802ed42f2268a4fadc8b3e5669107ffda1b8fe558019dc77  evidence/FOLLOWUP/debt-fix/attempt-1/fixture-pipeline-post-real.log
6a9dfa34bda24cb5a81b6200f67b02417b648afcb357d4a97900c991e91a0d01  evidence/FOLLOWUP/debt-fix/attempt-1/fixture-pipeline-post-joint.log
fb4124f5e96a8a69648aa0028009bcd036ee58763d0a2c7801540f3fc33528e7  evidence/FOLLOWUP/debt-fix/attempt-1/g2-collect-post-bare.log
67721d5347b6946890d607c504df57a5161e14be8fa674346558a2b1eb07c51b  evidence/FOLLOWUP/debt-fix/attempt-1/g2-collect-post-deselected.log
108e214efe6bc8424927a11ab9ab589e0fe79119313b9b8e4d09f15f69b9b0c4  evidence/FOLLOWUP/debt-fix/attempt-1/judiciary-post-real.log
8fb9a8a066f6ed5ef146656b2069cf35e4c4e4e2d20beea91ec9867f13fad518  evidence/FOLLOWUP/debt-fix/attempt-1/judiciary-post-joint.log
09579826128c816be02faba9d780b4ccf36e62cb9d98ed9154f2c0fde3c69003  evidence/FOLLOWUP/debt-fix/attempt-1/mirror-gate3-real.log
ca7d1461175181322cd31551d8172e1e86859bc4181fe11be0330badb3ef3868  evidence/FOLLOWUP/debt-fix/attempt-1/mirror-gate3-joint.log
00e27712aeaa3e8f6b28dec8277ef58360f10203a269c9e90ca571c225349850  evidence/FOLLOWUP/debt-fix/attempt-1/mirror-gates-real.log
59042cf34c828cf00c87ef7c002014c9e3c63c859234568811283add7a4b252e  evidence/FOLLOWUP/debt-fix/attempt-1/mirror-gates-joint.log
44f839d3e357f215a4e765c2ac7986fc4898314e5d3ae36fedeeb22033871f28  evidence/FOLLOWUP/debt-fix/attempt-1/mutmut-box.log
5bffadce8703c13cc5b58128f78b6683cf364d25c5ebace94758f720bc10cfc7  evidence/FOLLOWUP/debt-fix/attempt-1/mypy.log
d31cc44fad1f1af069992156288d6dbe8736e8fd6cd69b7f19319593024820ce  evidence/FOLLOWUP/debt-fix/attempt-1/p01-postfiles-real.log
dacded11ef1f705d3ece2ba3c3b91042bb1b547c2f55bbce443c129be1592416  evidence/FOLLOWUP/debt-fix/attempt-1/p01-postfiles-joint.log
54119daa5340845025ce7e21854518ecbd10af001d08e5758adca1cbd33e04c9  evidence/FOLLOWUP/debt-fix/attempt-1/run-diag-e2e.py
9c2800342fa79863be52a11b49733b284f530cdbc958de4bee0b5086aa322a9d  evidence/FOLLOWUP/debt-fix/attempt-1/run-mirror-gates.py
82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18  evidence/FOLLOWUP/debt-fix/attempt-1/ruff-check.log
567cf9662cb4d79c3e23b3904f6b02d25d7ae3d1f3da6155dd946d1e871cad4e  evidence/FOLLOWUP/debt-fix/attempt-1/ruff-format.log
24b19046e07f1a2afedc5edd20e09d8734b56430cace0860cb712ee901d14462  evidence/FOLLOWUP/debt-fix/attempt-1/substrate2-post-real.log
117736976613eb34055764ff431bcd388caba31996abbb9d7d9e9cfdf3bf298e  evidence/FOLLOWUP/debt-fix/attempt-1/substrate3-post-joint.log
117ba55de8ea68bada17c32be0648212f327239ee35fb8d9c5995d74396f433b  evidence/FOLLOWUP/debt-fix/attempt-1/verify-reconstructions.py
7d19e58f99a2a5b41d8f5d86c0107f3313c8c1991032beb7c3b6b2062336cf90  evidence/FOLLOWUP/debt-fix/attempt-1/veto-newtests-post-real.log
95f942bf25c88258dab3a5c310ad0bf0066d5398e7135e6ff1c231c212aba16b  evidence/FOLLOWUP/debt-fix/attempt-1/veto-newtests-post-joint.log
# ADOPTED B1 packet files (predecessor originals, byte-preserved — read, never edited)
94c2b557aa4b67b8791922e1a8f543315a092d1b8585cacea1ec9e45f8f8bb81  evidence/FOLLOWUP/debt-fix/readiness.md
a2786416b03b358fdeb0b82c368ad62ffd5bd522aae048342cea053e254a41b8  evidence/FOLLOWUP/debt-fix/baseline/compiler-cli-pre-real.log
99c37c4ed44dd7f914ddf9b7c6c9a80046a45cb95369119ac7a12ba59ab13faf  evidence/FOLLOWUP/debt-fix/baseline/compiler-cli-pre-joint.log
122dfb27b70dc605048f0f7875fec251780dd2fb7a5beca55ec14388d8ae43e5  evidence/FOLLOWUP/debt-fix/baseline/debtfix-e2.log
c6ac1986642688f5ebf9ecb88e713c9faa5f89015e8d79d7748995e6936c3537  evidence/FOLLOWUP/debt-fix/baseline/debtfix-e3.log
b2964815319099199c885c0e5e27c5761e1162417ac307ba65fc2beefe22bd7b  evidence/FOLLOWUP/debt-fix/baseline/debtfix-e4-check.log
81a067e178a0969a8cd7ee261580bd16f692490e2283f48937e5770b1743bd65  evidence/FOLLOWUP/debt-fix/baseline/debtfix-e4-format.log
2cd4c93a06c40e5f802ed42f2268a4fadc8b3e5669107ffda1b8fe558019dc77  evidence/FOLLOWUP/debt-fix/baseline/fixture-pipeline-pre-real.log
09fbbe76c236698df40f75639af8ea6a3b8105392c26205f512e91956e3e84ba  evidence/FOLLOWUP/debt-fix/baseline/fixture-pipeline-pre-joint.log
469fa1db6b7241318e1d8dea991bab3879d49181caae1ab11b0101a4e9104c48  evidence/FOLLOWUP/debt-fix/baseline/g2-collect-pre-bare.log
df45ca3249e044883ca80adb8b8d91557a0f74682f70ff3fb4aef3a2c7023b16  evidence/FOLLOWUP/debt-fix/baseline/g2-collect-pre-deselected.log
e791db0797f2bfcdfb31bf21ee1e30101a48f33a36957c9f1a48f288ee9500c7  evidence/FOLLOWUP/debt-fix/baseline/mypy.log
328381d3915134abcaa6b403be0e153e3585f5c1c06497402ceb3325e11e78dd  evidence/FOLLOWUP/debt-fix/baseline/p01-prefiles-real.log
3fe94a6390a85a145d88f55f4e07a2f497ad64651627bbc70a0c6d19f2975fac  evidence/FOLLOWUP/debt-fix/baseline/p01-prefiles-joint.log
93ce843a9d749c32733164fb2843c33a985fa597e699d83855e5e67a9666b94d  evidence/FOLLOWUP/debt-fix/baseline/ruff-check.log
d16bb2009ab4abbbf7179b93e56404c604700799ca96be6a7f0c4cc6d8789f83  evidence/FOLLOWUP/debt-fix/baseline/ruff-format.log
b4d1867884c063b5cf32f6d2348b5dd3ec9161fc1ef353b919541b41adecb0f4  evidence/FOLLOWUP/debt-fix/baseline/substrate2-pre-real.log
ddd512fd839dad9bda52b5c8391ee4955954a5efdaec074bd7756ce6143a9d5f  evidence/FOLLOWUP/debt-fix/baseline/substrate3-pre-joint.log
2d32b0d251919804dca6720533264030c7a547dfcd3de206a8e0811d1a8bc454  evidence/FOLLOWUP/debt-fix/baseline/veto-newtests-pre-real.log
141694bc47c16d26adc49c8769d41d7b7e6475858c6c88dbe89de5c340680dbb  evidence/FOLLOWUP/debt-fix/baseline/veto-newtests-pre-joint.log
```

Superseded UNVERIFIED B2 partials (first16, recorded for the audit trail;
the 3 gate logs reproduced byte-identical; the 7 suite partials were
outcome-identical and are replaced by the verified reruns above):
`ruff-check 82b3e6a6c090a576`, `ruff-format 567cf9662cb4d79c`, `mypy
5bffadce8703c13c`, `p01-real 24baf4123b0d3cf5`, `p01-joint
d925170f3f3eb1d5`, `veto-real fa71ed99cf0bc61c`, `veto-joint
7f2668e16dcb307e`, `fixture-real 785ce690c5332477`, `fixture-joint
964aa8b54b66e3fe`, `compiler-cli-real 8fef21778b8677ad`.

`git diff` tracked hunks belonging to this packet: exactly the 10 owned
files (1114+/14-: `pyproject.toml` 14/0, `cli.py` 595/1, `bundler.py`
3/2, `auditor.py` 7/0, `dispatch.py` 333/7, `runner.py` 2/1,
`test_pipeline.py` 1/1, `test_cli.py` 1/1, `test_compiler.py` 1/1,
`test_judiciary.py` 157/0). This session's own working-tree writes are
evidence-only (`attempt-1/` + this REVIEW); the specs pollution from
this session's E2E runs was restored to HEAD at close (precedented).

## Handoff to final verification (item 6 — not mine)

- Exact candidate: stc HEAD `edf5389` + loose set at the Identity hashes
  above (14 debt-modified + 14 owned-unchanged + unpinned-untouched by
  mtime); tracked numstat exactly 10 files 1114+/14-; pins sst
  `079f4de6…` (clean) / prompt-kit `4f442a6c…` / trace `a24a9370…`.
- Reserve status: tranche 8/20 spent (unchanged); 6-call verification
  reserve INTACT; this stage spent 0 live calls.
- Suggested 0-call replays: `verify-reconstructions.py` (strongest,
  seconds); the 3 gate logs (minutes); any suite row (commands in
  Evidence); mirror rebuild via `run-mirror-gates.py` + Gate-3 argv.
- Coordinator dispositions needed: F1–F4 (options in Triage); then
  attempt-4 → erratum + commit + report per the suspension resumption
  rule.
