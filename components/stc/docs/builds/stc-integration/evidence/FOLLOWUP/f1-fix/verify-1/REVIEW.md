# F1-fix — Independent verification (verify-1)

Record type: independent review
Author role and date: f1-fix-verifier (fresh session) / 2026-09-14
Packet: STC follow-up tranche (F1 stderr-truncation gap) @ INT-2026-09-14.1
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set incl. the 3 F1-owned files at the builder-claimed hashes (re-verified
byte-exact below) + `evidence/FOLLOWUP/f1-fix/attempt-1/` delivery under review
+ this `verify-1/` record. Builder REVIEW.md read in full; every builder claim
below was re-executed or re-inspected by me — nothing inherited, 0 CLI calls.
Pins re-probed at open and close: sst
`079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after), prompt-kit
`4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`.
Environment: joint `trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`); real-gates
`learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`. All three /tmp shims present, no
recreation. My discrimination script lived in /tmp only (log preserved here).

## Delivery section

- Behavior/artifact changed and why: NOTHING changed by me or, beyond the
  claimed 3 owned files, by the tranche under review — confirmed. This verify-1
  record rules on the builder's F1 delivery (failure-evidence sidecar + pointer
  note + raised tail). Ruling: **F1 CLOSED** — every fast-failure byte is now
  preserved recoverably; success paths and confinement behavior are unchanged.
- Files or outputs changed: this record + its logs/guards only (all under
  `evidence/FOLLOWUP/f1-fix/verify-1/`). No product file touched by me; no
  STATE.md write; no commits. sst/prompt-kit/trace read-only; `trace-lite/`
  never listed, read, or written.
- Material implementation decisions: none (verification only).
- Known limitations and checks not run: no live re-run (0-CLI-call brief; the
  capacity-tail shape is mirrored scripted, not observed live); `test_cli.py`
  pre-existing baseline untouched (not re-run, out of F1 scope); full
  `pytest tests/` beyond the P03 suite + targeted confinement set not run.

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Required full reads | read all 5 records in full | FIX-B5 F1 carried OPEN (§4); P05-fix F1 finding (`note[:300]` both paths); P05-fix verify-1 F1 endorsed (row-2 note exactly 300 chars, mid-word); F1 readiness design + gates; attempt-1 delivery claims | `evidence/FIX-B5/REVIEW.md`, `evidence/P05-fix/*/REVIEW.md`, `evidence/FOLLOWUP/f1-fix/readiness.md`, `.../attempt-1/REVIEW.md` | Read, not re-executed (predecessor scope) |
| Candidate identity (8 hashes) | `git rev-parse`, sha256 recompute of all 8 files | HEAD `edf5389` = tasked base; F1-owned byte-exact: `harness_worker.py ced79ed5…7867`, `cli_gateway.py f9dda17e…07b8a`, `test_integration_harness_worker.py e96db8d0…70b45`; fix-owned byte-exact at VERIFIED hashes: `dialectic_runner 19a2e448…8283b`, `test_dialectic 6e059f08…f1019`, `__init__ 10571421…bac40`; tracked mods exact: `cli.py 33476f34…124bb`, `dispatch.py dc75c56e…13c7` | sha256 output (this session) | Hash-bound |
| Pins + sst clean | rev-parse ×3 repos at open and close; sst status at open and close | All 3 pins exact at both ends; sst status empty both times | `verify-1/sst-after.txt` (empty, sha e3b0c44…) | Read-only repos |
| Builder evidence integrity | sha256 recompute of all 10 attempt-1 Identity entries | 10/10 byte-exact vs REVIEW.md Identity block (9 logs/guards + readiness `4ebfb816…`) | `attempt-1/REVIEW.md` Identity block | No post-hoc edits |
| (a) F1-only 5/5, BOTH interpreters (mine) | `pytest test_integration_harness_worker.py -m "not live" -k test_f1_ -v`, joint + real-gates | 5 passed / 76 deselected on EACH (7.96s joint, 8.47s real-gates) | `verify-1/f1-only-joint.log`, `verify-1/f1-only-real.log` | Scripted, 0 CLI calls |
| (d) P03 suite green, BOTH interpreters (mine) | full file `-m "not live"`, joint + real-gates | 76 passed, 5 deselected on EACH (71 pre-existing + 5 new F1; 0 failures) | `verify-1/p03-joint.log`, `verify-1/p03-real.log` | Live deselected per D13 |
| Own discrimination (DIFFERENT shapes) | own /tmp script: Shape A worker CRASH with 676B exception (sentinel `VERIFY1-CRASH-SENTINEL-ZQ49K2` at tail; builder crash was short "disk gone"); Shape B gateway exit-2 via `generate()` profile=None (sentinel `VERIFY1-GW-SENTINEL-Q7XD21` at tail; builder used invoke/profile/cli exit-1) | 2/2 PASS: `stderr_full` byte-exact in sidecar both shapes; notes ≤300 chars with `[full stderr: …#id]`; `failure_evidence` resolves; Shape B raised error carries the tail sentinel; both sentinels absent from `stderr[:300]` (old code would have lost them) | `verify-1/discrim.log` | ScriptRunner-only, 0 CLI calls; script itself in /tmp, removed with its tmpdir |
| Line audit: owned-files-only | `grep -rln` F1 identifiers over `src/` | F1 refs in exactly the 2 owned product files; zero in `dispatch.py`, `cli.py`, `dossier.py`, `dialectic_runner.py`, adapters/identity/memory (hashes/manifest confirm untouched) | grep output (this session) | Static + hash-bound |
| Line audit: confinement isolation | F1-identifier grep restricted to `build_native_command`, `build_gateway_command`, `shape_gateway_prompt`, `snapshot/assert_tracked_status_unchanged`, `_run_confined_gateway_attempt` bodies | NONE found — argv/shaping/assertion paths contain zero F1 logic; `note[:300]` backstop retained only at `harness_worker.py:621` (`note[:NOTE_BUDGET]`); old `cli_gateway.py:191` truncated-head raise is gone (tail raise) | grep output; `harness_worker.py:621`, `cli_gateway.py:227-233` | Static read |
| Line audit: test append-only | F1 refs in test lines 1–1289 | Exactly one: the `failure_evidence_path` import (line 46); all 5 `test_f1_*` + 3 helpers live in the appended block (lines 1290–1498); zero existing tests reference F1 helpers | `test_integration_harness_worker.py:46,1290-1498` | Static read |
| Success-row key set unchanged | code read (`log_row` adds `failure_evidence` ONLY `if ... is not None`) + passing builder test asserting the exact 13-key pre-fix set + my reruns | `test_f1_success_path_writes_no_failure_records` PASSED on both interpreters; gateway + worker success rows keep exact key set; sidecar gains zero records | `harness_worker.py:623-624`; f1-only logs | Code + green test |
| Confinement behavior byte-identical | targeted verbose rerun (real-gates): all `test_fix_*` argv/shaping/`-o`/assertion tests + native-argv + tripwire + ledger-exclusion + pre-existing failure-log tests | 16 passed, 0 failed — incl. confined-codex argv pins, worker-argv-unchanged, SST-bytes-verbatim shaping (×2), `-o` prefer + stdout fallback, assertion fail-closed/pass, ledger-exclusion, quarantine, `test_gateway_generate_failure_logs_and_raises` (pre-existing failure contract intact) | `verify-1/confinement-real.log` | Behavior proof (no pre-F1 bytes exist: files are untracked loose, so isolation-grep + green pins jointly establish it) |
| (d) ruff on owned files | `ruff check` + `ruff format --check` (0.16.1, configured pyproject gates) on the 3 owned files | All checks passed; 3 files already formatted | `verify-1/ruff.log` | Configured gates |
| (d) mypy strict on owned files | `mypy --strict` (2.3.0) on 2 product + 1 test file | No issues in 2 files; no issues in 1 file | `verify-1/mypy.log` | Strict per pyproject |
| Drift gate | recompute all 22 FIX-TRANCHE manifest entries | 16 MATCH + exactly the 6 fix differs (3 at F1 hashes, 3 at VERIFIED hashes); `dossier.py` MATCHes manifest (untouched since 83bc1e2); zero unexplained drift | `FIX-TRANCHE/snapshot/MANIFEST.sha256` | Hash-bound |
| Scope/hygiene | `git diff --numstat`, full/tracked status, `git log`, STATE.md status, sst status | numstat exactly 576/0 + 333/7; tracked guard `d1edad82…` = FIX-B5-era value; full-status hash `4f5e3d14…` = builder's after-guard byte-exact; HEAD still `edf5389`; no new commits; STATE.md untouched; sst clean; `trace-lite/` never touched | `verify-1/status-after-*.txt`, `verify-1/numstat-after.txt` | Tree left as found + this record |
| Spend | 0 CLI sessions; no installs | $0.00 metered; budget reserve intact (20/20 remain incl. ≥6 acceptance) | this REVIEW | Fully scripted tranche |

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| V1-INFO-1 | info (design working as intended) | own Shape A run | crash note landed at exactly 300 chars (reason long, pointer preserved, backstop cut the head) | None — the backstop now trims a pointer note whose full bytes live in the sidecar; harmless per design | None |
| (no FAIL-grade findings) | — | — | — | — | — |

No product defect in the F1 owned surface is demonstrated: failures preserve
full bytes on every exercised path (gateway fast-fail, worker fail-then-retry,
worker crash short + long, gateway timeout, gateway exit-2 noprofile), and the
success + confinement paths are observably unchanged.

## Verdict, reviewer only

PASS

- Criteria established: (a) fast-fail full stderr recoverable byte-exact with
  tail cause on gateway + worker + crash + timeout shapes (builder 5/5 re-run
  green on both interpreters, plus my 2/2 DIFFERENT-shape discrimination);
  (b) ledger note ≤300 chars pointing at `<sidecar>#<id>` + dedicated row key
  present only on failure rows; (c) success rows keep the exact pre-fix 13-key
  set, zero failure records, identical contents; (d) P03 suite 76 passed /
  5 deselected on BOTH interpreters + 16/16 targeted confinement/shape tests +
  ruff check/format + mypy strict all green on owned files; confinement held
  (owned-files-only delta, argv/shaping/assertion bodies free of F1 logic and
  behaviorally green, tracked identical, sst clean); 0 CLI calls, $0.00.
- Unmet criteria or missing evidence: none within the F1 brief. Live
  end-to-end demonstration of a capacity-tail recovery awaits the next live
  run (out of this scripted brief by design, same boundary the builder stated).
- Baseline failures versus new regressions: zero regressions (all 71
  pre-existing P03 tests pass unmodified on both interpreters; 16/16
  confinement/shape pins green; builder evidence 10/10 intact).
- Exact scope of independent execution/inspection: everything in the Evidence
  table was executed or read by me in this session (inherited nothing): the 5
  required full reads; HEAD + 8 file hashes + 3 pins at open and close; 10-line
  builder-manifest recompute; 22-entry drift recompute; f1-only (both
  interpreters) + full P03 (both interpreters) + 16-test confinement reruns;
  own 2-shape /tmp discrimination script (distinct sentinels, byte-exact
  assertions); F1-footprint + confinement-isolation + append-only greps;
  `log_row`/raise/dispatch code reads; ruff + mypy gates; full/tracked/numstat
  + sst + STATE + log hygiene guards. Live run NOT re-executed (briefed).
  `trace-lite/` never listed, read, or written.
- Next action: F1-fix VERIFIED (coordinator to record F1 CLOSED); the fix
  rides the next live run, where a real capacity-tail recovery will
  corroborate the scripted mirrors.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings; V1-INFO-1 is a design confirmation, not a defect) | — | — | — | None (live corroboration rides the next live run) |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — verification only; the 3 F1-owned files are the builder's delivery,
# re-hashed byte-exact above and untouched by this session)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
21e6134b4aec4889e8703e83e89502060ce28fb4a44e3f32ed08b86586c3e7a2  evidence/FOLLOWUP/f1-fix/verify-1/confinement-real.log
21e2ecff5c8a6c29b4a28551f446dbc1b19ddfa763394ce004bef66878b3135a  evidence/FOLLOWUP/f1-fix/verify-1/discrim.log
3363f3d6b6a13f3d7960ed68141d10c3a906c41ac8daed97d9994b4d537e8909  evidence/FOLLOWUP/f1-fix/verify-1/f1-only-joint.log
50783ceca0999b327f2897d2b3ffb70bb9ed2ce4e97ffe00c8fb88eeba72b565  evidence/FOLLOWUP/f1-fix/verify-1/f1-only-real.log
4103ff0d6cfc0b79da764fced6185a3ab256fb17a73ec97b31269a0b1b8951bd  evidence/FOLLOWUP/f1-fix/verify-1/mypy.log
26c25bb4b6dcabc24c7844eddf0f8561cd838752668e4043ddb1605747f4b836  evidence/FOLLOWUP/f1-fix/verify-1/p03-joint.log
f6a0d9df2a5d1fd1b0b8027c0b754c385056bed33ce1d00d87715aab4c80e1ff  evidence/FOLLOWUP/f1-fix/verify-1/p03-real.log
46ad9071b671f966440da30ea1960bcdda06f7dbe577e27c2ed5e033cf7bb53f  evidence/FOLLOWUP/f1-fix/verify-1/ruff.log
b19c8afba00370783b13b492afb14c8075fcfc9f3653d5f387ddbdf2e0b42444  evidence/FOLLOWUP/f1-fix/verify-1/numstat-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/f1-fix/verify-1/sst-after.txt
4f5e3d14c70fad9c401a1046db40d58c74ce5bd24041bce17134cbdcb42b3335  evidence/FOLLOWUP/f1-fix/verify-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/f1-fix/verify-1/status-after-tracked.txt
```

`git diff` tracked hunks belonging to this session: NONE (evidence-only
`verify-1/` writes; `git diff --numstat` shows only the 2 pre-existing
loose-set mods, both still matching the tasked hashes).
