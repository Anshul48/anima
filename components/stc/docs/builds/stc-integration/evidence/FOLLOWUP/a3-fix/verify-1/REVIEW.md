# FOLLOWUP a3-fix — Independent verification (verify-1)

Record type: independent review
Author role and date: a3-fix-verifier (fresh session) / 2026-09-14
Packet: STC follow-up tranche, a3-fix stage (close the patch-format gap
that killed all three live proposals: emitter-frame unified-diff pin +
SST custody-tolerance evidence diff; 0 live calls).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set incl. the 2 A3-owned files at the builder-claimed new hashes
(re-verified byte-exact below) + `evidence/FOLLOWUP/a3-fix/attempt-1/`
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
recreation. My frame-pin + SST-validation scripts lived in /tmp only
(logs preserved here). pytest runs used `-p no:cacheprovider`;
ruff/mypy caches redirected to /tmp.

## Delivery section

- Behavior/artifact changed and why: NOTHING changed by me or, beyond the
  claimed 2 owned files, by the tranche under review — confirmed. This
  verify-1 record rules on the builder's a3-fix delivery (unified-diff-only
  pin in `shape_gateway_prompt` + new `test_a3_patch_format.py` + validated
  SST custody-tolerance proposal diff). Ruling: **A3 FIX VERIFIED** — the
  frame pins pure-unified-diff emission at the single choke point with SST
  bytes still verbatim, and the evidence diff translates both exact live
  payloads to byte-exact clean content while leaving marker-free payloads
  bit-identical.
- Files or outputs changed: this record + its logs/guards only (all under
  `evidence/FOLLOWUP/a3-fix/verify-1/`). No product file touched by me; no
  test file touched by me; no STATE.md write; no commits.
  sst/prompt-kit/trace read-only; `trace-lite/` never listed, read, or
  written.
- Material implementation decisions: none (verification only). A2 stays
  carried (out of a3-fix scope, unchanged).
- Known limitations and checks not run: no live re-run (0-CLI-call brief —
  the pin's emission effect + tolerant custody ride the next acceptance
  live leg inside the 6-call reserve); SST landing awaits an
  SST-authorized stage by design; `test_cli.py` baseline untouched (out of
  scope); full `pytest tests/` beyond the new + affected files not run
  (brief scope); wiring remains UNADJUDICATED (orthogonal, carried).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Required full reads | read all 4 records in full | accept-2 A3 finding + Diagnosis (cand-0 unified+trailer → apply fail; cand-1 Begin Patch → verbatim garbage; custody `custody.py:176-216` no marker path); a3-fix readiness (drift gate, custody SST-owned ruling, R0-R3 rules) + attempt-1 delivery claims; a1-fix verify-1 PASS (predecessor hashes) | `evidence/FOLLOWUP/accept-2/attempt-1/REVIEW.md`, `evidence/FOLLOWUP/a3-fix/readiness.md`, `.../attempt-1/REVIEW.md`, `evidence/FOLLOWUP/a1-fix/verify-1/REVIEW.md` | Read, not re-executed (predecessor scope) |
| Candidate identity (10 hashes) | `git rev-parse`, sha256 recompute of all files, at open AND close | HEAD `edf5389` = tasked base; A3-owned byte-exact: `cli_gateway aedffa12…bb392`, `test_a3_patch_format f99b2785…b1f2b`; 8/8 unchanged byte-exact at tasked hashes: `dialectic_runner c072f1da…0ff5`, `test_dialectic eea1a7ee…0ec0`, `cli.py 2ddfd6cb…d82f1`, `test_winner_carry 0b5c3a8a…69762`, `harness_worker ced79ed5…7867`, `test_harness e96db8d0…70b45` (= `test_integration_harness_worker.py`, V3-INFO-1), `__init__ 10571421…bac40` (= `integration/__init__.py`), `dispatch.py dc75c56e…13c7` | sha256 output (this session, open + close) | Hash-bound |
| Pins + sst clean | rev-parse ×3 repos at open and close; sst status at open and close; sst custody bytes before/after my validation | All 3 pins exact at both ends; sst status empty both times (0 B); custody bytes `43c24681…ec864` identical before/after — ZERO sst bytes changed | `verify-1/sst-after.txt` (empty, sha e3b0c44…) | Read-only repos |
| Builder evidence integrity | sha256 recompute of all 17 attempt-1 Identity entries | 17/17 byte-exact vs REVIEW.md Identity block (2 owned files + readiness + 14 logs/guards) | `attempt-1/REVIEW.md` Identity block | No post-hoc edits |
| Dossier chain | sha256 of attempt-2 events.json + store.db | `683860d0…` + `cc93680c…` byte-exact vs accept-2 REVIEW Identity | this REVIEW | Hash-bound |
| New A3 tests 18/18, BOTH interpreters (mine) | `pytest tests/unit/test_a3_patch_format.py -m "not live" -v`, joint + real-gates | 18 passed on EACH (2.66 s joint, 2.91 s real-gates) | `verify-1/a3-newtests-joint.log`, `verify-1/a3-newtests-real.log` | Scripted, 0 CLI calls |
| Affected suite, BOTH interpreters (mine) | `pytest tests/unit/test_integration_harness_worker.py -m "not live"`, joint + real-gates | 76 passed + 5 deselected on EACH (16.08 s joint, 16.51 s real-gates) — frame pin breaks nothing | `verify-1/harness-worker-unit-joint.log`, `verify-1/harness-worker-unit-real.log` | Live deselected per D13 |
| Own frame-pin check (DIFFERENT SST input) | own /tmp script, BOTH interpreters: distinct marker-bearing input (`V3-FRAME-PROBE-7Q` sentinel + both markers + unicode + trailing prose, NOT the builder's `x.py/+code` input) through `shape_gateway_prompt` | 12/12 PASS on EACH: SST-verbatim-once between delimiters; delimiters exact + once-each; pin fragments all present, ordered, in the post-END frame, before the terminal emit line; zero column-0 `***` frame lines; SST markers preserved; deterministic (first run caught my own scoping bug — pin search hit SST-block occurrences — corrected in-session, see V3-INFO-4) | `verify-1/frame-pin.log` | /tmp script, 0 CLI calls; script itself outside the repo |
| Own SST-diff validation (dossier-sourced bytes) | own /tmp script, BOTH interpreters: `git apply --check` + apply of the evidence diff to a /tmp copy of pinned sst; exact live bytes from attempt-2 events.json (NOT test embeddings) through pristine-vs-patched custody; own marker-free payloads (v3-new/mod/raw/bold) | 34/34 PASS on EACH: check rc=0 + apply rc=0; cand-0 pristine FAILS (`corrupt patch at line 169` + fallback `Unrecognized diff line format … '*** End Patch'`) → patched `success=True` 4923 B `75f3af96…`; cand-1 pristine "succeeds" writing 3929 B verbatim (file sha == payload sha) → patched `success=True` 3716 B `f746b09d…` 127 lines; R0 no-op + pristine-vs-patched byte-identity on all 4 own payloads; sst bytes + status unchanged (one in-session seed fix on my bold case, V3-INFO-4) | `verify-1/sst-diff-validation.log` | /tmp scratch, sst untouched |
| Frame delta audit: pin confined to closing instruction | full read of `cli_gateway.py` (346 lines) | Pin is exactly 4 lines at :103-106 inside the `shape_gateway_prompt` return list — after `SST_PROMPT_END` (:101) + blank (:102), before the terminal "Now emit…" lines (:107-108); docstring gains the A3 note (:85-86); no `***` at column 0 anywhere in the file (grep rc=1); single choke point confirmed — sole product call site is `generate` :171 (`invoke` routes through it) | `src/stc/integration/cli_gateway.py:74-110,171` | Static read + grep |
| D15/D7 intact | delimiter + verbatim reads; pre-existing frame-test reads | Delimiters unchanged (`SST_PROMPT_BEGIN/END` exact); `sst_prompt` embedded as one verbatim list element (:100); my probe + the 76/76 suite prove verbatim-with-markers behaviorally; pre-existing frame tests assert substring properties only (`in shaped`, `in call["prompt"]` — read at :1011-1058), never byte-exact shaped output | `cli_gateway.py:73-110`; `test_integration_harness_worker.py:1011-1058`; `verify-1/frame-pin.log` | Static + behavioral |
| No other product deltas | 8 unchanged hashes (above); `Begin Patch` + custody-def greps over `src/` + `tests/`; SST diff scope | `Begin Patch` appears only in `cli_gateway.py` (quoted mid-line pin text) + the new test file; no real custody defs under `stc/` (sole `def apply_proposal` hit is inside a test-embedded live-bytes string literal); SST diff touches exactly 1 file, 3 hunks, 113+/1- (`git apply --stat`); `__all__` still exports the same 6 names | grep output; diffstat | Hash-bound + static |
| Ruff on owned files | `ruff check` + `ruff format --check` (0.16.1, configured pyproject gates) on both owned files | All checks passed; 2 files already formatted | `verify-1/ruff.log` | Configured gates |
| Mypy strict on owned files | `mypy --strict --follow-imports=silent` (2.3.0, MYPYPATH=real-gates paths, cache in /tmp) | Success: no issues found in 2 source files (new test file strict-clean, zero pre-existing) | `verify-1/mypy.log` | Strict per pyproject (`strict=true`) |
| Scope/hygiene | `git diff --numstat`, full/tracked status, `git log`, STATE.md status, sst status, stray + bytecode sweep | numstat exactly 594/0 + 333/7 (`de39b44…`); tracked `d1edad82…` = FIX-B5 value; full status byte-IDENTICAL to builder's (`c7f24296…`, collapsed untracked dirs); HEAD still `edf5389`; no new commits; STATE.md untouched; sst clean; only recent-mtime repo files under `src/`+`tests/` are the 2 hash-verified builder-owned files; zero new `__pycache__`; `trace-lite/` never touched | `verify-1/numstat-after.txt`, `verify-1/status-after-*.txt`, `verify-1/sst-after.txt` | Tree left as found + this record |
| Spend | 0 CLI sessions; no installs | $0.00 metered; tranche still 6/20, 6-call reserve intact | this REVIEW | Fully scripted stage |

## Diagnosis (what the evidence establishes)

- **A3 is closed on both sides of the boundary — verified
  independently.** Emission side: the STC frame now pins
  pure-unified-diff `proposed_changes` naming the exact forbidden
  markers, at the single choke point every gateway call traverses
  (`generate` :171), with SST bytes still verbatim — proven by my own
  distinct-input probe (12/12 both interpreters) and the 76/76
  affected suite on both interpreters. Custody side: the SST proposal
  flips both exact live verdicts — the 5182 B now applies (fallback
  carries past the 213-vs-165 hunk count git rejects) and the 3929 B
  translates to a git-appliable diff (exact count 127) — to byte-exact
  pinned content, while my own four marker-free payloads behave
  bit-identically pristine-vs-patched (34/34 both interpreters).
- **The discrimination proves the tests target the defect.** Pristine
  SST custody on the dossier-sourced bytes reproduces the live record
  precisely (cand-0 `corrupt patch at line 169` + fallback rejection,
  file absent; cand-1 file bytes == payload bytes, the
  verbatim-garbage path); the scratch-patched proposal flips both to
  byte-exact clean content. The regression tests cannot pass on the
  old behavior.
- **The delta is confined to the frame pin + one new test file.** The
  pin is 4 lines in the closing instruction plus a docstring note;
  delimiters and the verbatim embedding are untouched; no column-0
  `***` line exists in the product file; no custody logic lives under
  `stc/`; the SST diff is exactly 3 hunks / 113+/1- in the single
  owned file; all 8 non-owned files are hash-immutable and the
  tracked diff is exactly the 2 pre-existing loose-set mods.
- **What remains is landing + live corroboration.** The tolerance
  change needs an SST-authorized stage to land (this stage proves it
  applies cleanly and behaves correctly on the exact live bytes); the
  frame pin's emission effect is judged on the next acceptance live
  leg inside the reserve. SST itself is byte-unchanged (clean
  before/after, custody sha identical).

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| V3-INFO-1 | info (brief shorthand, no impact) | tasked `test_harness e96db8d0…70b45` + `__init__ 10571421…bac40` | The hashes resolve to `tests/unit/test_integration_harness_worker.py` and `src/stc/integration/__init__.py` respectively (there is no `tests/unit/test_harness.py`; `src/stc/__init__.py` hashes differently) — both re-verified byte-exact at open and close | None — all 10 hashes verified | None (naming shorthand only) |
| V3-INFO-2 | info (citation note, no impact) | accept-2 REVIEW `custody.py:176` dispatch citation | Builder readiness already notes the predicate is actually at :181; substance confirmed behaviorally by my pristine-vs-patched replay (dispatch + fallback + verbatim paths all observed) — not a defect | None for this stage | None here |
| V3-INFO-3 | info (path shorthand, no impact) | joint interpreter path | Used ws-absolute `<ws>/trace/.venv-linux/bin/python`, verified 3.12.3, with the briefed joint PYTHONPATH (same binary-shape convention as a1-fix V1-INFO-3) | None — all runs valid | None (brief shorthand only) |
| V3-INFO-4 | info (own-probe corrections, disclosed) | my /tmp scripts (first runs) | Frame probe v1 searched pin fragments over the whole shaped text so SST-block marker occurrences broke ordering checks — rescoped to the post-`SST_PROMPT_END` frame and fixed fragment order. SST probe v1 seeded the bold-context case with a stray leading space (both sides failed identically — still identical behavior). Both corrected in-session; final logs are the all-green reruns (12/12 + 34/34 on both interpreters) | None — final evidence is the corrected reruns, preserved in full | None (method note only) |
| (no FAIL-grade findings) | — | — | — | — | — |

No product defect in the A3-owned surface is demonstrated: the frame
pins unified-diff-only emission with SST bytes verbatim on every
exercised input (builder's plus my distinct probe), the SST proposal
applies cleanly and flips both live verdicts to byte-exact clean
content while keeping marker-free payloads bit-identical, and the
change adds zero lint/type errors — with sst byte-unchanged and every
non-owned file hash-immutable.

## Verdict, reviewer only

PASS

- Criteria established: (a) A3-owned files byte-exact at claimed new
  hashes with 8/8 non-owned files drift-free at open AND close; (b)
  new tests 18/18 on BOTH interpreters + affected suite 76/76 (+5
  deselected) on BOTH + my 12/12 DIFFERENT-input frame-pin probe on
  BOTH + my 34/34 dossier-sourced SST-diff validation on BOTH
  (apply-check + apply, verdict flips, R0 no-op, byte-identity);
  (c) line-level delta audit: pin confined to the closing instruction
  (:103-106 + docstring), D15/D7 intact (delimiters + verbatim
  embedding + substring-only pre-existing tests), single choke point,
  no column-0 `***` in product code, no custody logic under `stc/`,
  SST diff exactly 1 file / 3 hunks / 113+/1-; (d) ruff check+format
  green and mypy strict green on both owned files; (e) builder
  evidence 17/17 intact; dossier chain byte-exact; tracked diff
  exactly 594/0 + 333/7; full/tracked/numstat guards reproduce
  predecessor values byte-exact; HEAD/pins/STATE.md/sst clean with
  ZERO sst bytes changed; A2 carried unchanged; 0 CLI calls, $0.00.
- Unmet criteria or missing evidence: none within the a3-fix brief.
  SST landing awaits an SST-authorized stage by design; live
  corroboration (a real proposal emitting clean unified diff through
  the pinned frame, a real verify through tolerant custody) awaits
  the next acceptance live leg.
- Baseline failures versus new regressions: zero regressions (all 76
  affected-suite tests green on both interpreters; no existing test
  touched — the new tests are a new file).
- Exact scope of independent execution/inspection: everything in the
  Evidence table was executed or read by me in this session (inherited
  nothing): the 4 required full reads; HEAD + 10 file hashes + 3 pins
  at open and close; 17-line builder-manifest recompute; dossier-chain
  recompute; new-tests (both interpreters) + affected suite (both) +
  own 2-interpreter /tmp frame-pin probe (distinct SST input) + own
  2-interpreter /tmp SST-diff validation (dossier-sourced bytes,
  scratch apply, pristine-vs-patched replay, own clean payloads);
  full `cli_gateway.py` + `test_a3_patch_format.py` + SST-diff reads;
  frame-test + choke-point + marker + custody-def greps; SST diffstat;
  ruff + mypy gates; full/tracked/numstat + sst + STATE + log +
  stray/bytecode hygiene guards. Live run NOT re-executed (briefed).
  `trace-lite/` never listed, read, or written.
- Next action: a3-fix VERIFIED (coordinator to schedule SST landing +
  acceptance re-run of the P05 live shape within the 6-call reserve,
  then verification).

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings; V3-INFO-1/2/3/4 are confirmations/notes, not defects) | — | — | — | None (SST landing + live corroboration ride coordinator follow-up) |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — verification only; the 2 A3-owned files are the builder's delivery,
# re-hashed byte-exact above and untouched by this session)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
6f0568bd109674edb48fccfd2b5bc9ab4906d08b7e181d7e6affbb64558b239b  evidence/FOLLOWUP/a3-fix/verify-1/a3-newtests-joint.log
5ba53f29a8e47a9ace625c00b1b5d417f740e376acaa3c3dad151df14feb93e8  evidence/FOLLOWUP/a3-fix/verify-1/a3-newtests-real.log
81d8781b6194a0a367eb5d146f94dec06f0b8ffaa9a5cbad2314a35c038ad087  evidence/FOLLOWUP/a3-fix/verify-1/harness-worker-unit-joint.log
27168007aac606679a5b44f5c5f85b24f5fc144c0a1f4adf56d1f2adfae44dcd  evidence/FOLLOWUP/a3-fix/verify-1/harness-worker-unit-real.log
f9af65340a1e119715b74379596482927429add9461000ef79b4cbdf26fa4513  evidence/FOLLOWUP/a3-fix/verify-1/frame-pin.log
c40b854bbecd8b5349f768d5a63d640a40adc275a6a8b02bc68aa350efa0d7cf  evidence/FOLLOWUP/a3-fix/verify-1/sst-diff-validation.log
4f76fa5fd7def5e9c31f05b3bcb14c6698602ba7488247b3d97a84fcf322ce3b  evidence/FOLLOWUP/a3-fix/verify-1/ruff.log
f9b031e5c45aa702cd4fef028d465551cb20a2c4698e0913c7b00766b20ac4d8  evidence/FOLLOWUP/a3-fix/verify-1/mypy.log
de39b44044e81bde8694e83668951eb22b464d5fa990f476bda8637f7b0f1102  evidence/FOLLOWUP/a3-fix/verify-1/numstat-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/a3-fix/verify-1/sst-after.txt
c7f24296a7a48ceb546d11538922f6c757a5c50af8ed059b4e40ba80bf60c2c1  evidence/FOLLOWUP/a3-fix/verify-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/a3-fix/verify-1/status-after-tracked.txt
```

`git diff` tracked hunks belonging to this session: NONE (evidence-only
`verify-1/` writes; `git diff --numstat` shows only the 2 loose-set mods:
`src/stc/cli.py` 594/0, `2ddfd6cb…d82f1`;
`src/stc/orchestrator/dispatch.py` 333/7, `dc75c56e…13c7` — both still
tasked-exact).
```
