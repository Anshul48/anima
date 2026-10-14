# FOLLOWUP winner-carry — Independent verification (verify-1)

Record type: independent review
Author role and date: winner-carry-verifier (fresh session) / 2026-09-14
Packet: STC follow-up tranche, winner-carry stage (carry live-exp WINNER
P2-H3a reasoning-medium into the real pipeline).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set incl. the 2 carry-owned files at the builder-claimed hashes
(re-verified byte-exact below) + `evidence/FOLLOWUP/winner-carry/attempt-1/`
delivery under review + this `verify-1/` record. Builder REVIEW.md read in
full; every builder claim below was re-executed or re-inspected by me —
nothing inherited, 0 CLI calls. Path shorthand: `evidence/...` =
`docs/builds/stc-integration/evidence/...`.
Pins re-probed at open and close: sst
`079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after), prompt-kit
`4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`.
Environment: joint ws-absolute `<ws>/trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`; the brief's
`trace/.venv-linux/bin/python` shorthand does NOT resolve from `ws/stc` cwd —
`not found` — so the same binary was addressed absolutely; see V1-INFO-3);
real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`. All three /tmp shims present, no
recreation. My discrimination script + W1 splice probe lived in /tmp only
(logs preserved here). pytest runs used `-p no:cacheprovider`
(outcome-neutral, keeps the tree free of `.pytest_cache` writes); ruff/mypy
caches redirected to /tmp (verified populated there).

## Delivery section

- Behavior/artifact changed and why: NOTHING changed by me or, beyond the
  claimed 2 owned files, by the tranche under review — confirmed. This
  verify-1 record rules on the builder's winner-carry delivery (seeded-config
  reasoning-medium lever + new test file). Ruling: **CARRY VERIFIED** — the
  P2-H3a lever is in the real gateway seeding path, probe-identical in
  behavior, confined argv/bytes untouched, and proven by tests on both
  interpreters plus my own different-value discrimination.
- Files or outputs changed: this record + its logs/guards only (all under
  `evidence/FOLLOWUP/winner-carry/verify-1/`). No product file touched by me;
  no test file touched by me; no STATE.md write; no commits.
  sst/prompt-kit/trace read-only; `trace-lite/` never listed, read, or
  written.
- Material implementation decisions: none (verification only).
- Known limitations and checks not run: no live re-run (0-CLI-call brief; the
  carried medium profile rides the next live run inside the 6-call reserve);
  `test_cli.py` pre-existing baseline untouched (not re-run, out of scope);
  full `pytest tests/` beyond the winner file + P05 e2e file not run; patch
  correctness/verify-green is acceptance's verdict per the live-exp caveat.

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Required full reads | read all 4 records in full | live-exp WIN P2-H3a + proposal + caveat; F1 PASS predecessor; winner-carry readiness (gates + design + proof plan) + attempt-1 delivery claims | `evidence/FOLLOWUP/live-exp/attempt-1/REVIEW.md`, `evidence/FOLLOWUP/f1-fix/verify-1/REVIEW.md`, `evidence/FOLLOWUP/winner-carry/readiness.md`, `.../attempt-1/REVIEW.md` | Read, not re-executed (predecessor scope) |
| Candidate identity (9 hashes) | `git rev-parse`, sha256 recompute of all files, at open AND close | HEAD `edf5389` = tasked base; carry-owned byte-exact: `cli.py 2ddfd6cb…d82f1`, `test_winner_carry.py 0b5c3a8a…69762`; 7/7 non-hunk byte-exact at tasked hashes: `harness_worker ced79ed5…7867`, `cli_gateway f9dda17e…07b8a`, `test_harness e96db8d0…70b45`, `dialectic_runner 19a2e448…8283b`, `test_dialectic 6e059f08…f1019`, `__init__ 10571421…bac40`, `dispatch.py dc75c56e…13c7` | sha256 output (this session, open + close) | Hash-bound |
| Pins + sst clean | rev-parse ×3 repos at open and close; sst status at open and close | All 3 pins exact at both ends; sst status empty both times | `verify-1/sst-after.txt` (empty, sha e3b0c44…) | Read-only repos |
| Builder evidence integrity | sha256 recompute of all 14 attempt-1 Identity entries | 14/14 byte-exact vs REVIEW.md Identity block (2 owned files + readiness + 11 logs/guards, incl. `numstat-after.txt de39b44…f1102`) | `attempt-1/REVIEW.md` Identity block | No post-hoc edits |
| Winner tests 6/6, BOTH interpreters (mine) | `pytest tests/unit/test_winner_carry.py -v`, joint + real-gates | 6 passed on EACH (1.46 s joint, 2.00 s real-gates): max→medium verbatim; insert-at-top; missing-config; None-without-login; idempotence+cleanup; operator-untouched | `verify-1/winner-only-joint.log`, `verify-1/winner-only-real.log` | Scripted, 0 CLI calls |
| P05 e2e file green, BOTH interpreters (mine) | `pytest tests/integration/test_run_e2e.py -m "not live" -v`, joint + real-gates | joint 4 passed + 1 skipped (manual needs gate tools, absent there — file design, `requires_gate_tools` skipif); real-gates 5 passed incl. manual fixture (28.95 s) | `verify-1/p05-e2e-joint.log`, `verify-1/p05-e2e-real.log` | Live deselected per D13 |
| Own discrimination (DIFFERENT value) | own /tmp script, BOTH interpreters: operator config with `model_reasoning_effort="high"` (value the builder never used) + odd formatting (leading spaces, no `=` spaces, trailing comment) + a SECOND occurrence; operator bytes read BEFORE and AFTER | 9/9 checks PASS on EACH: whole-line rewrite ×2 to exactly `model_reasoning_effort = "medium"` (comment dropped, probe-identical semantics); other lines verbatim; auth copied byte-exact; operator config + auth bit-identical before/after; second seed distinct home with same rewrite; both homes cleaned | `verify-1/discrim.log` | /tmp script, 0 CLI calls; script itself outside the repo |
| Hunk audit: confinement | grep `model_reasoning_effort` over `cli.py`; read `_seed_codex_home` 1081–1120 in full | ALL carry refs lie in [1084,1116] ⊂ `_seed_codex_home` [1081,1120]: docstring note (1084–1085) + lever (1100–1117) + trial comment (1105–1110). Zero refs elsewhere in the file | `src/stc/cli.py:1081-1120`; grep output (this session) | Static read |
| Hunk audit: probe-identical lever | line-by-line vs `liveexp-probe.py:106-116` (REASONING=medium) | Predicate `strip().startswith` identical; rewrite/insert lines identical (`medium` literal = f-string at medium); join `+ "\n"` vs probe `+ ("\n" if lines else "")` — behaviorally identical (lines never empty post-insert). Net +18 (594−576) matches the claimed hunk | `src/stc/cli.py:1100-1117`; `liveexp-probe.py:106-117` | Static read + numstat arithmetic |
| Hunk audit: trial comment cites P2-H3a | read 1105–1110 | Cites live-exp P2-H3a, shaped `3339af29…`, P1-H0b exit-124@150 s hang, valid §2 at medium in 56.66 s, confessing header `reasoning effort: medium`, argv+SST untouched | `src/stc/cli.py:1105-1110` | Static read |
| Hunk audit: no new imports | import-statement scan of [1081,1120]; module import block read | Exactly ONE import in range: function-local `import tempfile` (1090), serving the pre-existing `mkdtemp` call; module-level import block ends at line 65 — zero additions; `shutil`/`Path` already module-level | `src/stc/cli.py:5-65,1090,1097` | Static read |
| Hunk audit: argv builders untouched | hash recompute (above) + `_seed_codex_home` reference grep over `src/` + call-site read | `cli_gateway` + `harness_worker` byte-exact to F1-VERIFIED hashes (argv builders immutable); exactly ONE product caller (`cli.py:1436`); test-local同名 helpers live in hash-verified untouched files | `src/stc/cli.py:1436-1447`; grep output | Hash-bound + static |
| Seeding route at call site | read 1436–1447 | `None` → fail-closed `ClickException`; else `harness_env={"CODEX_HOME": …}` → `CLIGatewayBackend("codex")` — the live-exp-proven route, unchanged | `src/stc/cli.py:1436-1447` | Static read |
| Ruff on owned files | `ruff check` + `ruff format --check` (0.16.1, configured pyproject gates) on `cli.py` + new test | All checks passed; 2 files already formatted | `verify-1/ruff.log` | Configured gates |
| Mypy strict on owned files | `mypy --strict --follow-imports=silent` (2.3.0, MYPYPATH=real-gates paths) | test file: no issues (rc=0); `cli.py`: exactly 5 errors at 237/661/664 (`no-untyped-call` on `yaml.safe_load`) + 1361/1368 (`unused-ignore`) — zero in hunk range [1081,1120] | `verify-1/mypy.log` | Strict per pyproject (`strict=true`, `python_version=3.12`) |
| W1 pre-existing-5: OWN causation test | /tmp proxy: current `cli.py` with ONLY lever lines 1100–1117 swapped for a 2-line copy-if-present stub (delta −16); same mypy flags/MYPYPATH; product hash re-verified untouched after splicing | SAME 5 codes/messages: 237/661/664 unshifted (above splice), 1361/1368 → 1345/1352 (exact −16 splice shift); zero new errors; hunk range clean in both runs → the lever causes ZERO of the 5; W1 CONFIRMED pre-existing, no weakening | `verify-1/mypy-preproxy.log` (splice transcript + proxy run); product sha `2ddfd6cb…` re-verified in-log | /tmp proxy; the 5 are definition-site-local diagnostics outside the hunk function |
| KNOWN DISCREPANCY ruling | recompute attempt-1 `numstat-after.txt` (coreutils + OpenSSL + hashlib + from-spec pure-Python SHA-256); fresh independent `git diff --numstat` capture + hash | Listed `de39b44…f1102` is the TRUE sha256 of the 60-byte file (4-way agreement); my fresh capture reproduces it byte-exact; tree state = claimed 594/0 + 333/7 → record CORRECT, false alarm from the coincidental sha1-empty hex prefix (V1-INFO-1) | this REVIEW; `verify-1/numstat-after.txt` (`de39b44…f1102`, 60 B) | Hash-bound, independently reproduced |
| Scope/hygiene | `git diff --numstat`, full/tracked status, `git log`, STATE.md status, sst status | numstat exactly 594/0 + 333/7; tracked = the 2 pre-existing files only (guard `d1edad82…` = FIX-B5 value); full status byte-IDENTICAL to builder's (`c66f6283…`); HEAD still `edf5389`; no new commits; STATE.md untouched; sst clean; `trace-lite/` never touched | `verify-1/numstat-after.txt`, `verify-1/status-after-*.txt`, `verify-1/sst-after.txt` | Tree left as found + this record |
| Stray-file check | root cache dirs + `__pycache__`/`*.pyc` sweep; mtime + git-ignored attribution | `.pytest_cache` (Sep 3), `.ruff_cache` (Sep 13), `src/**/__pycache__` (Sep 5), `.mypy_cache` (Sep 14 15:01–15:02, predates my first write 15:11:51 = builder-era) — ALL pre-existing + git-ignored; my caches verified in /tmp; `git status` shows zero strays | `git check-ignore`; stat output (this session) | Ignored paths; left untouched |
| Spend | 0 CLI sessions; no installs | $0.00 metered; cumulative 3/20, 6-call reserve intact | this REVIEW | Fully scripted stage |

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| V1-INFO-1 | info (briefed discrepancy ruled: record CORRECT, no erratum, no defect) | attempt-1 `numstat-after.txt` + REVIEW.md Identity line | Recompute by 4 independent SHA-256 implementations (coreutils 9.4, OpenSSL CLI, Python hashlib, from-spec pure-Python — all agree, all correct on empty/`hello` vectors): the 60-byte file's true digest IS the listed `de39b44…f1102`. My fresh `git diff --numstat` capture reproduces the same 60 bytes and the same digest. Tree state matches the claim (594/0 + 333/7). The "empty" suspicion came from the digest's coincidental `de39b44…` (sha1-empty) hex prefix | None — the Identity entry is accurate; no record correction needed | None |
| V1-INFO-2 | info (pre-existing, outside owned hunk — builder W1 CONFIRMED by own experiment) | `cli.py:237,661,664` (`safe_load` untyped via yaml shim), `cli.py:1361,1368` (unused `type: ignore`) | My post-hunk run: exactly these 5, zero in [1081,1120]. My /tmp lever→stub proxy run: same 5 codes/messages modulo the exact −16 splice shift, zero new. The hunk (function-internal + docstring, no module-level names, no imports) cannot induce these definition-site-local diagnostics | None for this stage — hunk is strict-clean; fixing the 5 would widen beyond the narrow hunk | None here (coordinator may schedule separately, as the builder noted) |
| V1-INFO-3 | info (path shorthand, no impact) | briefed joint interpreter path | `trace/.venv-linux/bin/python` does not resolve from `ws/stc` cwd (`not found` — no such `stc/trace/` entry); used ws-absolute `<ws>/trace/.venv-linux/bin/python`, verified 3.12.3, with the briefed joint PYTHONPATH | None — same binary, same env shape; all runs valid | None (brief shorthand only) |
| (no FAIL-grade findings) | — | — | — | — | — |

No product defect in the carry-owned surface is demonstrated: the seeded
config carries reasoning-medium on every exercised shape (max→medium,
insert-at-top, missing-config, my high→medium double-occurrence with odd
formatting), fail-closed and caller-deletes semantics are unchanged, the
operator login is never written, argv builders are byte-exact, and the hunk
adds zero strict errors.

## Verdict, reviewer only

PASS

- Criteria established: (a) carry-owned files byte-exact at claimed hashes
  with 7/7 non-hunk files drift-free; (b) winner tests 6/6 on BOTH
  interpreters + P05 e2e green live-deselected on BOTH (4+skip joint, 5/5
  real-gates) + my 9/9 DIFFERENT-value discrimination on BOTH (before/after
  operator bytes); (c) line-level hunk audit: docstring + lever only, all
  refs inside `_seed_codex_home`, probe-identical behavior, P2-H3a trial
  comment, no new imports, exactly one product caller, argv builders
  hash-immutable; (d) ruff check+format green and mypy strict green on the
  new test, with the `cli.py` 5 proven hunk-independent by my own
  lever-swap causation test (hunk range strict-clean in both runs —
  FAIL-capable, passed); (e) builder evidence 14/14 intact; the briefed
  numstat discrepancy ruled a false alarm with an independently reproduced
  digest; tracked diff exactly 594/0 + 333/7; HEAD/pins/STATE.md/sst clean;
  0 CLI calls, $0.00.
- Unmet criteria or missing evidence: none within the winner-carry brief.
  Live corroboration of the carried profile awaits acceptance (out of this
  scripted brief by design, inside the 6-call reserve); patch
  correctness/verify-green is acceptance's verdict per the live-exp caveat.
- Baseline failures versus new regressions: zero regressions (P05 e2e green
  on both interpreters incl. the real-gates manual fixture; no existing
  test touched or weakened — the carry tests live in a new file).
- Exact scope of independent execution/inspection: everything in the Evidence
  table was executed or read by me in this session (inherited nothing): the
  4 required full reads; HEAD + 9 file hashes + 3 pins at open and close;
  14-line builder-manifest recompute; winner-only (both interpreters) +
  P05 e2e (both interpreters) + own 2-interpreter /tmp discrimination
  (distinct value, byte-exact assertions); full `_seed_codex_home` +
  call-site + probe-lever + error-site reads; confinement/import/caller
  greps; ruff + mypy gates + my own /tmp lever-swap causation experiment;
  4-way hash cross-check of the disputed numstat file + fresh numstat
  capture; full/tracked/numstat + sst + STATE + log + stray-file hygiene
  guards. Live run NOT re-executed (briefed). `trace-lite/` never listed,
  read, or written.
- Next action: winner-carry VERIFIED (coordinator to record the carry
  ACCEPTED for the acceptance stage); acceptance runs the P05 live shape on
  this medium profile within the 6-call reserve, then verification.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings; V1-INFO-1/2/3 are confirmations/notes, not defects) | — | — | — | None (live corroboration rides acceptance) |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — verification only; the 2 carry-owned files are the builder's delivery,
# re-hashed byte-exact above and untouched by this session)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
abb1e73f1099987b6974553c21b509b1b0f61ee4e91e440b1d77cf18968fec58  evidence/FOLLOWUP/winner-carry/verify-1/discrim.log
d4ddd0384c649bf2ade1651e512f15d559e2b59d6187b6a147d142f70a2be90e  evidence/FOLLOWUP/winner-carry/verify-1/mypy-preproxy.log
ee0d6536223a72054bb096d4680fb81d45bfadee47d8b98768a4c26dacae0279  evidence/FOLLOWUP/winner-carry/verify-1/mypy.log
de39b44044e81bde8694e83668951eb22b464d5fa990f476bda8637f7b0f1102  evidence/FOLLOWUP/winner-carry/verify-1/numstat-after.txt
89ad22b00d4bdc5c7f7ecf327f9e0958dcb0b736ba1c122f8b1f0954e6d6194e  evidence/FOLLOWUP/winner-carry/verify-1/p05-e2e-joint.log
05566a049eec4181dc9fdd744baa1762a6ab6806319074e7a96a0a1123944023  evidence/FOLLOWUP/winner-carry/verify-1/p05-e2e-real.log
576367823b2d114238afabab3c12d2ef59b33d531284eb580c9c93ffb255b214  evidence/FOLLOWUP/winner-carry/verify-1/ruff.log
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/winner-carry/verify-1/sst-after.txt
c66f62832b6b5c03e6feb3cfa69f88d81a3171999ad773e66159eb49424ab7df  evidence/FOLLOWUP/winner-carry/verify-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/winner-carry/verify-1/status-after-tracked.txt
910e60298644ba7d58da2f96d65013fb51cc98d3bcbfa366fa6f38b747e4f613  evidence/FOLLOWUP/winner-carry/verify-1/winner-only-joint.log
74c6ce828dad4bbbc704a32516b0e75acce5348c3afcad3d2ee447319b1a4a7f  evidence/FOLLOWUP/winner-carry/verify-1/winner-only-real.log
```

`git diff` tracked hunks belonging to this session: NONE (evidence-only
`verify-1/` writes; `git diff --numstat` shows only the 2 loose-set mods:
`src/stc/cli.py` 594/0 = 576 pre-existing + 18 hunk, `2ddfd6cb…d82f1`;
`src/stc/orchestrator/dispatch.py` 333/7 untouched, `dc75c56e…13c7`).
```

