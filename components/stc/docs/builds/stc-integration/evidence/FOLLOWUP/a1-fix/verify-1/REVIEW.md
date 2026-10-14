# FOLLOWUP a1-fix — Independent verification (verify-1)

Record type: independent review
Author role and date: a1-fix-verifier (fresh session) / 2026-09-14
Packet: STC follow-up tranche, a1-fix stage (fix the unbounded recursive
self-copy in `mirror_source_tree` that stalled accept attempt-1; 0 live
calls).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set incl. the 2 A1-owned files at the builder-claimed new hashes
(re-verified byte-exact below) + `evidence/FOLLOWUP/a1-fix/attempt-1/`
delivery under review + this `verify-1/` record. Builder readiness.md and
REVIEW.md read in full; every builder claim below was re-executed or
re-inspected by me — nothing inherited, 0 CLI calls. Path shorthand:
`evidence/...` = `docs/builds/stc-integration/evidence/...`.
Pins re-probed at open and close: sst
`079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after), prompt-kit
`4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`.
Environment: joint ws-absolute `<ws>/trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`) +
real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`. All three /tmp shims present, no
recreation. My discrimination script + pristine reconstruction lived in /tmp
only (logs preserved here). pytest runs used `-p no:cacheprovider`;
ruff/mypy caches redirected to /tmp (verified populated there).

## Delivery section

- Behavior/artifact changed and why: NOTHING changed by me or, beyond the
  claimed 2 owned files, by the tranche under review — confirmed. This
  verify-1 record rules on the builder's a1-fix delivery (dst-exclusion +
  loud-refusal bound in `mirror_source_tree` + 3 appended regression tests).
  Ruling: **A1 FIX VERIFIED** — the mirror terminates on dst-inside-src,
  excludes exactly the destination, stays byte-faithful, refuses
  un-mirrorable shapes loudly, and the delta is confined to
  `mirror_source_tree` + one private helper.
- Files or outputs changed: this record + its logs/guards only (all under
  `evidence/FOLLOWUP/a1-fix/verify-1/`). No product file touched by me; no
  test file touched by me; no STATE.md write; no commits.
  sst/prompt-kit/trace read-only; `trace-lite/` never listed, read, or
  written.
- Material implementation decisions: none (verification only). A2-deferral:
  AGREE (see Independent findings V1-INFO-4); A2 NOT implemented.
- Known limitations and checks not run: no live re-run (0-CLI-call brief —
  the fix rides the next acceptance live leg inside the 6-call reserve);
  `test_cli.py` baseline untouched (out of scope); full `pytest tests/`
  beyond the dialectic unit + fixture files not run (brief scope).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Required full reads | read all 4 records in full | accept attempt-1 A1 finding + Diagnosis + intervention log; a1-fix readiness (gates + design + bound + A2 deferral) + attempt-1 delivery claims; winner-carry verify-1 PASS (predecessor hashes) | `evidence/FOLLOWUP/accept/attempt-1/REVIEW.md`, `evidence/FOLLOWUP/a1-fix/readiness.md`, `.../attempt-1/REVIEW.md`, `evidence/FOLLOWUP/winner-carry/verify-1/REVIEW.md` | Read, not re-executed (predecessor scope) |
| Candidate identity (9 hashes) | `git rev-parse`, sha256 recompute of all files, at open AND close | HEAD `edf5389` = tasked base; A1-owned byte-exact: `dialectic_runner c072f1da…0ff5`, `test_dialectic eea1a7ee…0ec0`; 7/7 unchanged byte-exact at tasked hashes: `cli.py 2ddfd6cb…d82f1`, `test_winner_carry 0b5c3a8a…69762`, `harness_worker ced79ed5…7867`, `cli_gateway f9dda17e…07b8a`, `test_harness e96db8d0…70b45` (= `test_integration_harness_worker.py`, V1-INFO-1), `__init__ 10571421…bac40`, `dispatch.py dc75c56e…13c7` | sha256 output (this session, open + close) | Hash-bound |
| Pins + sst clean | rev-parse ×3 repos at open and close; sst status at open and close | All 3 pins exact at both ends; sst status empty both times | `verify-1/sst-after.txt` (empty, sha e3b0c44…) | Read-only repos |
| Builder evidence integrity | sha256 recompute of all 18 attempt-1 Identity entries | 18/18 byte-exact vs REVIEW.md Identity block (2 owned files + readiness + 15 logs/guards) | `attempt-1/REVIEW.md` Identity block | No post-hoc edits |
| New regression tests 3/3, BOTH interpreters (mine) | `pytest tests/unit/test_integration_dialectic.py -k "mirror_" -v`, joint + real-gates | 3 passed on EACH (2.77 s joint, 2.88 s real-gates) | `verify-1/dialectic-newtests-joint.log`, `verify-1/dialectic-newtests-real.log` | Scripted, 0 CLI calls |
| Full dialectic unit file, BOTH interpreters (mine) | `pytest tests/unit/test_integration_dialectic.py`, joint + real-gates | 61 passed on EACH (12.56 s joint, 13.44 s real-gates) = 58 pre-existing + 3 new, zero regressions | `verify-1/dialectic-unit-joint.log`, `verify-1/dialectic-unit-real.log` | Scripted, 0 CLI calls |
| Fixture file green live-deselected, BOTH interpreters (mine) | `pytest tests/integration/test_dialectic_fixture.py -m "not live" -v`, joint + real-gates | joint 2 passed + 2 skipped (gate tools absent there — file design) + 1 deselected; real-gates 4 passed incl. full scenario + mutmut-once (78.96 s) + 1 deselected | `verify-1/fixture-joint.log`, `verify-1/fixture-real.log` | Live deselected per D13 |
| Own discrimination (DIFFERENT layout) | own /tmp script, BOTH interpreters: depth-5 `repo/out/artifacts/scratch/ws-7/sandbox` (vs builder depth-9), distinct names, pre-existing dst marker, symlink-to-dst inside src, symlinked dst spelling, nested `.venv`, `.git` | 13/13 checks PASS on EACH: termination; exact 4-file bound; no nested copy; marker once + preserved; byte-faithfulness ×3 (code, binary, `.git`); nested `.venv` excluded; symlink-to-dst not materialized; aliased dst spelling same set; src==dst + src-inside-dst raise `DialecticError` ("into itself") | `verify-1/discrim.log` | /tmp script, 0 CLI calls; script itself outside the repo |
| Delta audit: uniform +22 shift | full read of mirror region :275-317 + call sites + catch-all + elapsed lines; line arithmetic vs readiness-quoted pre-fix numbers | `_MIRROR_SKIP_DIRS` :278-280 unchanged (above delta); def :283 unchanged; body 13→35 (+22); lease call :445→:467, catch-all :487-497→:509-519, elapsed :706-708→:728-730 and :742-747→:764-769, `_lease_path` :499-505→:521-527, merged :815→:837 — every post-delta anchor shifted by exactly +22 | `src/stc/integration/dialectic_runner.py` (this session) | Static read + arithmetic |
| Delta audit: P04-fix lines byte-identical | mechanical byte-compare of current :728-730/:764-769 vs `P04-fix/attempt-1/owned-delta.diff` added lines | `wall match: True`, `elapsed match: True` — search-wall trio + INFO-2 comment + `max()` block byte-identical at the +22 shift | this REVIEW; `evidence/P04-fix/attempt-1/owned-delta.diff` | Byte-exact, independent of builder |
| Delta audit: no widening | import-block + `__all__` read; `DialecticError` + `_mirror_into` + `mirror_source_tree` grep over `src/` + `tests/`; 7 unchanged hashes (above) | No new imports (`time` is P04's; fix uses `shutil`/`Path`/`Final` already present); `__all__` unchanged (`_mirror_into` private, unexported); new raise sites only :293 (preserved not-found) + :297 (loud refusal); exactly 2 product call sites (:467 lease, :837 merged); `cli.py`/`harness_worker`/`cli_gateway`/winner+harness tests hash-immutable → zero argv/shaping/gateway change | `src/stc/integration/dialectic_runner.py:1-82,120,283-317`; grep output | Hash-bound + static |
| Delta audit: `.git` inclusion invariant | skip-set read + B1.3 comment + test pins | `.git` absent from `_MIRROR_SKIP_DIRS`; B1.3 comment :275-277 preserved; inclusion pinned by builder test (`.git/objects/pack`) AND my probe check7 (`.git/refs/HEAD`) | `dialectic_runner.py:275-280`; `verify-1/discrim.log` | Static + behavioral |
| Test change append-only (own proof) | remove import line 42 + appended block (1-based L1240+) from current bytes, hash | Reconstruction hashes `6e059f08…f1019` == tasked pre-fix value byte-exact (first attempt off-by-one caught and corrected in-session) → pre-existing bytes bit-identical | this REVIEW (method quoted) | Byte-exact, independent of builder |
| Ruff on owned files | `ruff check` + `ruff format --check` (0.16.1, configured pyproject gates) on both owned files | All checks passed; 2 files already formatted | `verify-1/ruff.log` | Configured gates |
| Mypy strict on owned files | `mypy --strict --follow-imports=silent` (2.3.0, MYPYPATH=real-gates paths) | `dialectic_runner.py`: strict-clean. Test file: exactly 5 errors at 176/577/1170/1217, zero in added ranges (import L42 + appended L1240+) | `verify-1/mypy.log` | Strict per pyproject (`strict=true`) |
| Pre-existing-5: OWN causation test | /tmp pristine reconstruction (hash-exact `6e059f08…` == tasked); same mypy flags/MYPYPATH; product hashes re-verified untouched after | SAME 5 codes/messages at 175/576/1169/1216 (exact −1 shift from the import line); the A1 change causes ZERO of the 5; fixing them would violate append-only | `verify-1/mypy-preproxy.log` | /tmp pristine; V1-INFO-2 |
| Scope/hygiene | `git diff --numstat`, full/tracked status, `git log`, STATE.md status, sst status, stray + bytecode sweep | numstat exactly 594/0 + 333/7 (`de39b44…`); tracked `d1edad82…` = FIX-B5 value; full status byte-IDENTICAL to builder's (`c66f6283…`); HEAD still `edf5389`; no new commits; STATE.md untouched; sst clean; only recent-mtime repo files are the 2 hash-verified builder-owned files; zero new `__pycache__`; `trace-lite/` never touched | `verify-1/numstat-after.txt`, `verify-1/status-after-*.txt`, `verify-1/sst-after.txt` | Tree left as found + this record |
| Spend | 0 CLI sessions; no installs | $0.00 metered; tranche still 4/20, 6-call reserve intact | this REVIEW | Fully scripted stage |

## Diagnosis (what the evidence establishes)

- **A1 FIXED at the root cause, bounded for all layouts — verified
  independently.** `mirror_source_tree` (:283-300) resolves both paths,
  refuses `src == dst` / src-inside-dst loudly, and excludes exactly the
  resolved `dst` subtree at every recursion level of `_mirror_into`
  (:303-317) with snapshotted listings. My own different-layout probe
  (depth-5, distinct names, pre-existing marker, two symlink spellings)
  terminates with an exact 4-file bound and byte-exact content on both
  interpreters; the loud-refusal bound raises `DialecticError` on both
  un-mirrorable shapes. Both live call sites (lease :467, merged :837)
  are covered at the single fix point.
- **The delta is confined to the mirror.** The uniform +22 line shift of
  every post-delta anchor (lease call, catch-all, `_lease_path`, P04
  elapsed lines, merged call site), byte-identical P04-fix lines against
  the independent P04 delta diff, zero new imports, unchanged `__all__`,
  and hash-immutable argv/shaping/gateway files jointly prove no
  widening. (The brief's `:706-708/:742-747` are pre-fix numbers; the
  byte-identical content now sits at `:728-730/:764-769`.)
- **No regressions, no silent partials.** All 58 pre-existing unit tests
  + all fixture tests green on both interpreters; the test change is
  proven append-only by hash-exact reconstruction; the dst exclusion
  drops only the artifact being created (never source bytes —
  faithfulness pinned byte-exact twice over, builder + mine); `.git`
  stays mirrored per B1.3; the nested skip-set tightening only removes
  cache waste nothing depends on.
- **A2 stays deferred — agreed with reasons (V1-INFO-4).** Served-header
  preservation needs `cli_gateway.py` extraction + a `SpendLedger`
  schema/sidecar touch (`harness_worker.py`) + dossier surfacing +
  tests: multi-file with schema touch, failing the brief's inclusion
  rule, for an info-severity evidence gap whose underlying fact
  (reasoning-medium) is already corroborated triangulated. Correctly
  out of this stage; NOT implemented here.

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| V1-INFO-1 | info (brief shorthand, no impact) | tasked `test_harness e96db8d0…70b45` | No `tests/unit/test_harness.py` exists; the hash resolves to `tests/unit/test_integration_harness_worker.py`, re-verified byte-exact at open and close | None — all 9 hashes verified | None (naming shorthand only) |
| V1-INFO-2 | info (pre-existing, outside the A1 delta — builder claim CONFIRMED by own experiment) | test file :176 (×2 codes), :577, :1170, :1217 | My post-change run: exactly these 5, zero in added ranges. My /tmp pristine-reconstruction run (hash-exact `6e059f08…`): same 5 codes/messages at the exact −1 import-line shift, zero new. Product file strict-clean | None for this stage — the A1 delta adds zero strict errors; fixing the 5 would violate append-only | None here (coordinator may schedule the 5 separately) |
| V1-INFO-3 | info (path shorthand, no impact) | joint interpreter path | Used ws-absolute `<ws>/trace/.venv-linux/bin/python`, verified 3.12.3, with the briefed joint PYTHONPATH (same binary-shape convention as winner-carry V1-INFO-3) | None — all runs valid | None (brief shorthand only) |
| V1-INFO-4 | info (A2-deferral ruling: AGREE — not implemented) | success-path gateway legs | A2 is an info-severity evidence gap, not a defect: medium is corroborated triangulated (43.1 s behavioral win + B1 seed proof on the real login + winner-carry tests). The fix needs gateway extraction + SpendLedger schema/sidecar touch + dossier surfacing + tests — multi-file with schema touch, failing the ≤5-line inclusion rule; joining `cli_gateway.py`/`harness_worker.py` would break their F1-VERIFIED hash-bound state for an optional log line | None for this stage | None here (rides coordinator follow-up scoping) |
| (no FAIL-grade findings) | — | — | — | — | — |

No product defect in the A1-owned surface is demonstrated: the mirror
terminates on dst-inside-src with exact exclusion and byte-faithfulness
on every exercised shape (builder depth-9 dossier layout; my depth-5
layout with pre-existing marker and two symlink spellings; disjoint
layout), refuses un-mirrorable shapes loudly, keeps `.git`, skips
caches at every level, and adds zero strict errors — with the P04
elapsed lines byte-identical and every non-owned file hash-immutable.

## Verdict, reviewer only

PASS

- Criteria established: (a) A1-owned files byte-exact at claimed new
  hashes with 7/7 non-owned files drift-free at open AND close; (b) new
  tests 3/3 on BOTH interpreters + full unit file 61/61 on BOTH +
  fixture green live-deselected on BOTH (2+2skip joint, 4/4 real-gates)
  + my 13/13 DIFFERENT-layout discrimination on BOTH (termination,
  exact-bound exclusion, byte-faithfulness, symlink spellings,
  loud-refusal pair); (c) line-level delta audit: uniform +22 shift of
  all five post-delta anchors, P04-fix lines byte-identical against the
  independent P04 delta, zero new imports, `__all__` unchanged, exactly
  2 product call sites, argv/shaping/gateway hash-immutable, `.git`
  invariant preserved and behaviorally pinned; (d) ruff check+format
  green and mypy strict green on the product file, with the test-file 5
  proven pre-existing by my own hash-exact pristine causation test
  (FAIL-capable, passed); (e) builder evidence 18/18 intact; tracked
  diff exactly 594/0 + 333/7; full/tracked/numstat guards reproduce
  predecessor values byte-exact; HEAD/pins/STATE.md/sst clean; test
  change proven append-only by my own reconstruction; A2-deferral
  agreed with written reasons, not implemented; 0 CLI calls, $0.00.
- Unmet criteria or missing evidence: none within the a1-fix brief.
  Live corroboration (a real verify completing through the fixed
  mirror) awaits the next acceptance live leg by design.
- Baseline failures versus new regressions: zero regressions (all 58
  pre-existing unit tests + all fixture tests green on both
  interpreters; no existing test touched — the new tests are appended
  and the import is a single inserted line).
- Exact scope of independent execution/inspection: everything in the
  Evidence table was executed or read by me in this session (inherited
  nothing): the 4 required full reads; HEAD + 9 file hashes + 3 pins at
  open and close; 18-line builder-manifest recompute; new-tests (both
  interpreters) + full unit (both) + fixture live-deselected (both) +
  own 2-interpreter /tmp discrimination (distinct layout, byte-exact
  assertions); full mirror-region + call-site + catch-all + elapsed +
  import-block + `__all__` reads; confinement/import/caller greps;
  mechanical P04 byte-compare against the independent P04 delta; own
  append-only reconstruction; ruff + mypy gates + my own /tmp pristine
  causation experiment; full/tracked/numstat + sst + STATE + log +
  stray/bytecode hygiene guards. Live run NOT re-executed (briefed).
  `trace-lite/` never listed, read, or written.
- Next action: a1-fix VERIFIED (coordinator to record A1 CLOSED for the
  acceptance stage, A2 DEFERRED with the V1-INFO-4 reasons); acceptance
  re-runs the P05 live shape through the fixed mirror within the
  6-call reserve, then verification.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings; V1-INFO-1/2/3/4 are confirmations/notes, not defects) | — | — | — | None (live corroboration rides acceptance) |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — verification only; the 2 A1-owned files are the builder's delivery,
# re-hashed byte-exact above and untouched by this session)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
e1dd55e264b6e915f10617bf38dcc03466bdd634802ce4732d243415ee6ad3b3  evidence/FOLLOWUP/a1-fix/verify-1/dialectic-newtests-joint.log
1f0e269de2a5349ac876c632dda0f0d5b299299b0ee0992ba6ad61ae9e0522da  evidence/FOLLOWUP/a1-fix/verify-1/dialectic-newtests-real.log
bbb66016a6370eef1e04ada51bf33ffd7b655016a17e25154c00deb310d63a8b  evidence/FOLLOWUP/a1-fix/verify-1/dialectic-unit-joint.log
442b901d3936fb607fd2df90b656bfc19f5f93085ef91c1f3443b9230597a45e  evidence/FOLLOWUP/a1-fix/verify-1/dialectic-unit-real.log
6b81f7e030bc3a2c03334b4fd3b4e60d4ee39b7671b7f16da219ab2b08135fa0  evidence/FOLLOWUP/a1-fix/verify-1/fixture-joint.log
3668597917cf95e06514829615a07f43f4b6a9d8616394ad9c59fd2591aefbe0  evidence/FOLLOWUP/a1-fix/verify-1/fixture-real.log
dc147278cc09e6d5d1e2cc3481062251d543dca6002e4d36e6479c3508a1f9cf  evidence/FOLLOWUP/a1-fix/verify-1/discrim.log
06aef71e4c5b2035b0c4ffa33dd4e0180d7e653e7f0487ab77262a78fe95d687  evidence/FOLLOWUP/a1-fix/verify-1/ruff.log
8b26e360cea96e8f9c48f825c08a361f53aea1b70e06ea4b69d011bb09598fa1  evidence/FOLLOWUP/a1-fix/verify-1/mypy.log
4b39228ffe410b273f61f3456ba9392c0d4ad92b32a9bc48929cdcb4c4fcb1cc  evidence/FOLLOWUP/a1-fix/verify-1/mypy-preproxy.log
de39b44044e81bde8694e83668951eb22b464d5fa990f476bda8637f7b0f1102  evidence/FOLLOWUP/a1-fix/verify-1/numstat-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/a1-fix/verify-1/sst-after.txt
c66f62832b6b5c03e6feb3cfa69f88d81a3171999ad773e66159eb49424ab7df  evidence/FOLLOWUP/a1-fix/verify-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/a1-fix/verify-1/status-after-tracked.txt
```

`git diff` tracked hunks belonging to this session: NONE (evidence-only
`verify-1/` writes; `git diff --numstat` shows only the 2 loose-set mods:
`src/stc/cli.py` 594/0, `2ddfd6cb…d82f1`;
`src/stc/orchestrator/dispatch.py` 333/7, `dc75c56e…13c7` — both still
tasked-exact).
```
