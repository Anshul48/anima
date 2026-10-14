# FOLLOWUP a1-fix — Builder delivery (attempt-1): mirror recursion fixed + bounded

Record type: builder delivery
Author role and date: a1-fix-builder / 2026-09-14
Packet: STC follow-up tranche, A1-fix stage (fix the unbounded recursive
self-copy in `mirror_source_tree` that stalled accept attempt-1; 0 live
calls).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (9 hashes re-verified byte-exact at B1, zero drift; the 2 owned
files now at the new hashes below, 7/7 non-owned still tasked-exact).
Pins: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after),
prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` (all exact at open and close).
Environment: joint ws-absolute `<ws>/trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`) +
real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`; pytest `-p no:cacheprovider`;
ruff/mypy caches redirected to /tmp (verified populated there).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Delivery section

- Behavior/artifact changed and why: `mirror_source_tree`
  (`src/stc/integration/dialectic_runner.py`) no longer copies the
  destination into itself when `dst` lives inside `src` (the live layout:
  leases at `<STC_DOSSIER_DIR>/runs/<run>/leases/<lease>` and the merged
  tree at `<run>/merged`, both under the in-repo dossier inside `ws/stc`).
  The fix excludes exactly the `dst` subtree via resolved-path comparison
  at every recursion level, snapshots directory listings, and loudly
  refuses the un-mirrorable shapes (`src == dst`, src-inside-dst) with
  `DialecticError` — never a silent partial. Both mirror call sites (lease
  :445, merged :815) are covered by the single fix point. B1 READY (see
  `evidence/FOLLOWUP/a1-fix/readiness.md` — predecessor gates, drift gate,
  call-site + failure-mode design justification, A2 deferral).
- Files or outputs changed: exactly the 2 owned files —
  `src/stc/integration/dialectic_runner.py`
  (`19a2e448…8283b` → `c072f1da…0ff5`: `mirror_source_tree` rewrite +
  private `_mirror_into` helper, 13 lines → 35) and
  `tests/unit/test_integration_dialectic.py`
  (`6e059f08…f1019` → `eea1a7ee…0ec0`: strictly append-only — 1 import
  line + 3 appended tests; pre-existing bytes proven bit-identical by
  reconstruction hash `6e059f08…` == tasked) — plus evidence under
  `evidence/FOLLOWUP/a1-fix/` (`readiness.md`, `attempt-1/` logs/guards,
  this REVIEW). No STATE.md write; no commits; no other product file
  touched (`cli_gateway.py` NOT joined — A2 deferred per the ≤5-line /
  schema-touch rule with written reasons in readiness.md).
- Material implementation decisions: (1) exclude-exactly-dst over
  git-mirror / lease-relocation / loud-refusal-as-fix (evidence layout
  requires the in-repo dossier; `.git` must stay mirrored per B1.3; a bare
  refusal would hard-fail the legitimate layout); (2) `_MIRROR_SKIP_DIRS`
  now applies at every level (was top-level-only — nested caches were pure
  waste; nothing depends on them); (3) `copy2`/`.git`-inclusion semantics
  preserved; (4) the 5 mypy strict errors in the test file are pre-existing
  (causation-proven below) and left untouched per the append-only
  constraint.
- Known limitations and checks not run: no live re-run (0-call brief — the
  fix rides the next acceptance live leg); A2 served-header preservation
  DEFERRED (needs ledger/dossier schema touch — see readiness.md);
  `test_cli.py` baseline untouched (out of scope); full `pytest tests/`
  beyond the dialectic unit + fixture files not run (brief scope).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Predecessor gates (B1) | full reads | accept attempt-1 A1 + diagnosis + intervention log + A2; accept readiness; winner-carry PASS; `mirror_source_tree` + lease/call-site + catch-all code; unit + fixture lease/mirror coverage (structurally blind: all leases outside fixture sources) | readiness.md Gate 0 | Read, not re-executed |
| Drift gate (B1) + close | rev-parse, 9 full-sha recomputes, numstat, 3 pins, sst status, at open AND close | HEAD `edf5389`; 9/9 exact at open; at close 7/7 non-owned still tasked-exact, 2 owned at new hashes; 594/0 + 333/7; pins exact; sst clean — zero unexplained drift | readiness.md Gate 1; `attempt-1/numstat-after.txt`, `sst-after.txt`, `status-after-*.txt` | Hash-bound |
| New regression tests 3/3, BOTH interpreters | `pytest tests/unit/test_integration_dialectic.py -k "mirror_..." -v`, joint + real-gates | 3 passed on EACH (2.59 s joint, 2.92 s real-gates): dst-inside-src terminates/excluded/faithful; disjoint faithful; self-reference refuses loudly | `attempt-1/dialectic-newtests-joint.log`, `dialectic-newtests-real.log` | Scripted, 0 CLI calls |
| Full dialectic unit file, BOTH interpreters | `pytest tests/unit/test_integration_dialectic.py`, joint + real-gates, post-format final bytes | 61 passed on EACH (13.30 s joint, 12.65 s real-gates) = 58 pre-existing + 3 new, zero regressions | `attempt-1/dialectic-unit-joint.log`, `dialectic-unit-real.log` | Scripted, 0 CLI calls |
| Fixture file green live-deselected, BOTH interpreters | `pytest tests/integration/test_dialectic_fixture.py -m "not live"`, joint + real-gates | joint 2 passed + 2 skipped (gate tools absent there — file design) + 1 deselected; real-gates 4 passed incl. real-gates full scenario + mutmut-once (79.57 s) + 1 deselected | `attempt-1/fixture-joint.log`, `attempt-1/fixture-real.log` | Live deselected per D13 |
| Old-vs-new discrimination (/tmp probe) | byte-exact pre-fix body vs new code on the identical live-layout fixture; shutil ops counted, hard-capped at 200 | OLD blows past the 200-op cap (201 copytree, 0 copy2 — unbounded, as diagnosed); NEW terminates in exactly 3 shutil ops with the exact expected 4-file set — the regression test discriminates the defect | `attempt-1/discrim-old-vs-new.log` (probe script itself in /tmp only) | Bounded probe, zero disk risk |
| Ruff on owned files | `ruff check` + `ruff format --check` (0.16.1, configured pyproject gates) on `dialectic_runner.py` + test file | All checks passed; 2 files already formatted (one `ruff format` pass applied to my appended test block only — append-only re-proven after) | `attempt-1/ruff.log` | Configured gates |
| Mypy strict on owned files | `mypy --strict --follow-imports=silent` (2.3.0, MYPYPATH=real-gates paths) | `dialectic_runner.py`: strict-clean. Test file: exactly 5 errors at 176/577/1170/1217, zero in my added ranges (import line + appended block) | `attempt-1/mypy.log` | Strict per pyproject (`strict=true`) |
| Pre-existing-5 causation | /tmp pristine reconstruction (import line + appended block removed) hashes `6e059f08…` == tasked byte-exact; same mypy flags on pristine | SAME 5 codes/messages at 175/576/1169/1216 (exact −1 shift from my import line); my change causes ZERO of the 5; fixing them would violate append-only | `attempt-1/mypy-preproxy.log` (reconstruction transcript + pristine run) | /tmp pristine; product hashes re-verified after |
| Confinement held | pre/post full+tracked status, numstat, sst status, cache sweeps | full status byte-identical to B1-open AND to the accept value (`c66f6283…`); tracked `d1edad82…` = FIX-B5 value; numstat still 594/0 + 333/7 (`de39b44…f1102` = winner-carry-verified value); sst clean; no `__pycache__` under owned dirs; cache-dir mtimes all pre-session | `status-after-*.txt`, `numstat-after.txt`, `sst-after.txt` | Tree left + this record |
| Spend | `spend.jsonl` 0-row audit | **0 CLI calls** this stage (tranche still 4/20; 6-call reserve NEVER touched); $0.00 metered; zero installs | `attempt-1/spend.jsonl` (empty, sha e3b0c44…) | CLI-session budget only |
| Scope/hygiene | pins at close, HEAD/log, STATE.md, stray sweep | HEAD still `edf5389`; no new commits; STATE.md untouched; all 3 pins exact; `trace-lite/` never listed, read, or written | git output (this session) | Tree left + this record |

## Diagnosis (what the evidence establishes)

- **A1 FIXED at the root cause, bounded for all layouts.** The defect was
  `mirror_source_tree` walking `src.iterdir()` lazily with `copytree` and
  no destination exclusion: with `dst` inside `src` (both live call
  sites), the lease/merged tree was copied into itself level after level
  (accept attempt-1: depth 7, 1.232 GB, 31-min zero-event stall; natural
  endings only ENAMETOOLONG/disk-full). The fix excludes exactly `dst`
  (resolved-path comparison, every level), snapshots listings against
  concurrent lease creation, and raises `DialecticError` loudly on
  `src == dst` / src-inside-dst. The dst exclusion is not a silent
  partial: the destination is the artifact being created, not source
  content — all genuine source bytes mirror faithfully (pinned byte-exact
  by test, `.git` included per B1.3).
- **The regression test reproduces the live shape and discriminates.**
  `test_mirror_dst_inside_src_excludes_destination` builds the
  `<src>/docs/…/dossier/runs/<run>/leases/<lease>` layout with a
  pre-existing lease marker: post-fix it terminates with an EXACT 4-file
  bound and byte-exact content; the /tmp probe proves the byte-exact
  pre-fix body issues unbounded copy ops (>200 and climbing) on the
  identical fixture while the new code uses exactly 3. The old suite was
  blind because every fixture lease lived outside its source tree.
- **No regressions, no widening.** Full unit file 61/61 on both
  interpreters (58 pre-existing all still green); fixture file green on
  both (real-gates 4/4 incl. mutmut-once); ruff check+format green; mypy
  strict green on the product file with the test-file 5 proven
  pre-existing by hash-exact pristine reconstruction; test change proven
  append-only the same way.
- **A2 stays deferred.** Served-header preservation needs success-path
  stderr extraction (`cli_gateway.py`) + a `SpendLedger` schema/sidecar
  touch (`harness_worker.py`) + dossier surfacing + tests — multi-file
  with schema touch, failing the brief's inclusion rule. Written reasons
  in readiness.md; `cli_gateway.py` correctly NOT joined to owned files.

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| (none — no new defects found; the 5 mypy test-file errors are pre-existing, causation-proven, and append-only-protected) | — | — | `mypy-preproxy.log` | None for this stage | None here (coordinator may schedule the 5 separately) |

## Verdict, reviewer only

FIXED-BOUNDED (builder-reported outcome; B3/acceptance to rule)

- Criteria established: B1 READY gates (predecessors read, zero drift);
  smallest-correct fix at the root cause with call-site + failure-mode
  justification; bound (loud refusal + exclusion + snapshot listings)
  covering all self-referential layouts; both live call sites fixed at one
  point; 3/3 new tests + 61/61 unit + fixture green live-deselected on
  BOTH interpreters (0 calls); old-vs-new discrimination probe PASS;
  ruff green; mypy strict green on product, test-file 5 proven
  pre-existing; append-only proven by reconstruction hash; confinement
  held (status/numstat/pins/HEAD/STATE/sst all clean); spend 0; A2
  deferred in writing with reasons.
- Unmet criteria or missing evidence: none within the a1-fix brief. Live
  corroboration (a real verify completing through the fixed mirror)
  awaits the next acceptance live leg by design.
- Baseline failures versus new regressions: zero regressions (all 58
  pre-existing unit tests + all fixture tests green on both
  interpreters; no existing test touched — the new tests are appended).
- Exact scope of independent execution/inspection: (for B3 to fill).
- Next action: a1-fix verification (fresh session) rules on this record;
  on PASS, acceptance re-runs the P05 live shape through the fixed
  mirror within the 6-call reserve.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| A1 (accept attempt-1: unbounded recursive self-copy) | `mirror_source_tree` with no dst exclusion, dst-inside-src on both live call sites | Exclude exactly dst (resolved paths, every level) + snapshot listings + loud `DialecticError` on src==dst / src-inside-dst | this REVIEW + owned files at new hashes + all attempt-1 logs | None (live corroboration rides acceptance) |
| A2 (accept attempt-1: served-header gap) | (out of a1-fix scope) | DEFERRED with written reasons (schema touch) | readiness.md Secondary assessment | Rides coordinator follow-up scoping |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
c072f1dac2725f470bfeb9753288e2158064838467784d3f8ceb279b640a0ff5  src/stc/integration/dialectic_runner.py
eea1a7eea04eebbe21680836e4823e01bb2bfa62729f4bcd41bcb219f52a0ec0  tests/unit/test_integration_dialectic.py
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
9d2016b423fe3ab7ce6e93e8bd328562a58e13e37dbe43c47239d19878c9e076  evidence/FOLLOWUP/a1-fix/readiness.md
65c3a5b66914efc8653245f21ba0d9856d793ec4d2ec76934a6fa6ea58c048c3  evidence/FOLLOWUP/a1-fix/attempt-1/discrim-old-vs-new.log
b1e61e85202f6ce52efdbc4cf088a93476ae1315c8d27cfa190486f3699c964b  evidence/FOLLOWUP/a1-fix/attempt-1/dialectic-unit-joint.log
e2b96e4aeb0f024f0c8ca566409aec1b918dea29f65a47786bef5579ca1537f6  evidence/FOLLOWUP/a1-fix/attempt-1/dialectic-unit-real.log
56ea026be2b3af6bace12adc8ddd7e2d511deed863796612e41dba8fd9a8f805  evidence/FOLLOWUP/a1-fix/attempt-1/dialectic-newtests-joint.log
71bddad7cc0183f596d9c0007e1069ebc5496782d3cb2b2c33d461d088ec5d5e  evidence/FOLLOWUP/a1-fix/attempt-1/dialectic-newtests-real.log
9da5474e9db139251ef542cd051b0cde693977c3d465a2d940e70420b0c517bb  evidence/FOLLOWUP/a1-fix/attempt-1/fixture-joint.log
f7d2dbd08ccf3d77b67c6eccecc0137b7693c73b4ef3ab7ca5394237ed61e0e8  evidence/FOLLOWUP/a1-fix/attempt-1/fixture-real.log
4f76fa5fd7def5e9c31f05b3bcb14c6698602ba7488247b3d97a84fcf322ce3b  evidence/FOLLOWUP/a1-fix/attempt-1/ruff.log
21e4a54a1e1224fa6aa001a3f1199f99b872e50f560e99c43678fcaf44ebdc26  evidence/FOLLOWUP/a1-fix/attempt-1/mypy.log
ce02e896153ae3914718348fdd45b2b651e2feb3a7b6abbf0edadc2fd3a43d36  evidence/FOLLOWUP/a1-fix/attempt-1/mypy-preproxy.log
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/a1-fix/attempt-1/spend.jsonl
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/a1-fix/attempt-1/sst-after.txt
c66f62832b6b5c03e6feb3cfa69f88d81a3171999ad773e66159eb49424ab7df  evidence/FOLLOWUP/a1-fix/attempt-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/a1-fix/attempt-1/status-after-tracked.txt
de39b44044e81bde8694e83668951eb22b464d5fa990f476bda8637f7b0f1102  evidence/FOLLOWUP/a1-fix/attempt-1/numstat-after.txt
```

`git diff` tracked hunks belonging to this stage: NONE (both owned files
are untracked loose-set members; `git diff --numstat` shows only the 2
pre-existing loose-set mods: `src/stc/cli.py` 594/0, `2ddfd6cb…d82f1`;
`src/stc/orchestrator/dispatch.py` 333/7, `dc75c56e…13c7` — both still
tasked-exact).
```
