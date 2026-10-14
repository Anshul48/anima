# FOLLOWUP winner-carry — Builder delivery (attempt-1): P2-H3a carried

Record type: builder delivery
Author role and date: winner-carry-builder / 2026-09-14
Packet: STC follow-up tranche, winner-carry stage.
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (all 8 hashes re-verified byte-exact at B1; only `cli.py` changed
since, by this stage's narrow hunk: `33476f34…124bb` → `2ddfd6cb…d82f1`).
Pins: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after),
prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` (all exact at open and close).
Environment: joint `trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`); real-gates
`learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`. All three /tmp shims present, no
recreation. Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Delivery section

- Behavior/artifact changed and why: the live-exp WINNER (P2-H3a,
  reasoning-medium) is carried into the real pipeline via the proposed
  one-line STC-owned change. `_seed_codex_home()` (`src/stc/cli.py`, the P05
  pattern; exactly ONE product caller — the live-run gateway backend at
  `cli.py:1418-1429`) now writes `model_reasoning_effort = "medium"` into
  the seeded `config.toml` for the gateway role: every
  `model_reasoning_effort…`-prefixed operator line is rewritten to medium,
  else the medium line is inserted at the top; a seeded `config.toml` is
  written even when the operator has none. Logic is line-for-line the P2-H3a
  probe's proven lever (`liveexp-probe.py:106-117`), including its
  `strip().startswith` predicate — no new mechanism risk. Confined argv
  untouched (F1-owned builders READ-ONLY, pins re-verified byte-exact);
  SST bytes untouched; auth handling, temp prefix, chmod, caller-deletes and
  fail-closed (`OSError → None`) semantics unchanged; no new imports (the
  default DAG path gains no new module dependencies). Trial-cited comment at
  the lever per P05 precedent (P2-H3a outcome + confessing header).
- Files or outputs changed: owned product hunk in `src/stc/cli.py` (2
  regions: docstring + lever; 32 diff lines vs the B1 file, net +18) + new
  owned test file `tests/unit/test_winner_carry.py` (6 tests; created per
  the B1 decision — no existing test covers product `_seed_codex_home`, the
  `test_cli.py` baseline stays untouched, both VERIFIED-hash test files are
  drift-pinned) + this `evidence/FOLLOWUP/winner-carry/` record. No STATE.md
  write; no commits. sst/prompt-kit/trace read-only; `trace-lite/` never
  listed, read, or written.
- Material implementation decisions: (1) probe-identical lever logic rather
  than a fresh design (the exact bytes that won live); (2) new test file
  over appending (B1 reasons stand); (3) the 5 `mypy --strict` errors in
  `cli.py` are pre-existing (proven identical on the byte-exact pre-hunk
  file) and OUTSIDE the narrow hunk — left untouched per the owned-files
  constraint, reported as findings, not fixed.
- Known limitations and checks not run: patch CORRECTNESS / verify-green is
  acceptance's job (live-exp caveat stands: the winner's diff guesses
  `stc_gateway.…` paths); no live re-run here (0-CLI-call brief — the
  medium profile rides the next live run inside the 6-call reserve);
  `test_cli.py` baseline untouched (not re-run, out of scope); full
  `pytest tests/` beyond the winner file + P05 e2e file not run.

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Required full reads | read all 5 records in full | live-exp REVIEW (WIN P2-H3a + reproduction + proposal + caveat) + readiness Gate 3 + F1 verify-1 PASS + `cli.py` seeding + `cli_gateway`/`harness_worker` argv (reference only) | predecessor records; `cli.py:1081-1102,1418-1429`; `cli_gateway.py`; `harness_worker.py:424-530,680-782` | Read, not re-executed |
| Candidate + drift gate (B1) | rev-parse, 8 full-sha recomputes, numstat, 3 pins, sst status | HEAD `edf5389`; 8/8 exact; 576/0 + 333/7; pins exact; sst clean — zero drift | readiness Gates 0–1 | Hash-bound |
| Seeded-config route viability (no STOP) | code-flow read + live proof | `cli.py:1418-1429` seeds → `harness_env CODEX_HOME` → `generate(role=gateway)` → `env.update(harness_env)` before spawn; P2 header confessed `reasoning effort: medium` with §2-valid output on this exact route | readiness Gate 2; `P2-H3a/header.txt`, `config-toml.txt` | Proven live by predecessor |
| Winner tests 6/6, BOTH interpreters | `pytest tests/unit/test_winner_carry.py -v`, joint + real-gates (post-format rerun) | 6 passed on EACH (max→medium verbatim; insert-at-top; missing-config; None-without-login; idempotence+cleanup; operator-untouched) | `attempt-1/winner-only-joint.log`, `attempt-1/winner-only-real.log` | Scripted, 0 CLI calls |
| P05 e2e file green, BOTH interpreters | `pytest tests/integration/test_run_e2e.py -m "not live" -v`, joint + real-gates | joint 4 passed + 1 skipped (manual needs gate tools, absent there — file design); real-gates 5 passed incl. manual fixture (26.68 s) | `attempt-1/p05-e2e-joint.log`, `attempt-1/p05-e2e-real.log` | Live deselected per D13 |
| Ruff on owned files | `ruff check` + `ruff format --check` (0.16.1) on `cli.py` + new test | All checks passed; 2 files already formatted (one format fix applied to the new test, then green) | `attempt-1/ruff.log` | Configured gates |
| Mypy strict on owned files | `mypy --strict --follow-imports=silent` (2.3.0, MYPYPATH=real-gates paths) | test file: no issues (rc=0); `cli.py`: exactly 5 errors, ALL pre-existing (seeFinding W1) — zero in the hunk, zero new | `attempt-1/mypy.log`, `attempt-1/mypy-prehunk-baseline.log` | Silent-follow (dependency noise excluded) |
| Pre-existing-5 proof | byte-exact pre-hunk reconstruction (sha `33476f34…124bb` = B1 hash) swapped in, same mypy run, hunk restored + checksum-verified | identical 5 errors at 237/661/664/1343/1350 (post-hunk 1361/1368 = +18 line shift); restored file `2ddfd6cb…` triple-checksum-matched | `mypy-prehunk-baseline.log` (pre-hunk sha printed at swap time) | Swap-restore verified |
| Hunk-shape audit | `diff` pre-hunk vs post-hunk `cli.py` | exactly 2 regions (docstring + lever), 32 diff lines, net +18 — nothing else | this REVIEW (diff quoted in session) | Textual |
| Drift re-confirm at close | full-sha recompute of all 8 + new test | 7/7 non-hunk files byte-exact at B1 hashes (F1-owned 3 incl. argv builders, fix-owned 3, `dispatch.py` 333/7); `cli.py` = new hunk hash only | sha256 output (this session) | Hash-bound |
| Tracked-diff audit | `git diff --numstat`, tracked/full status | numstat exactly `594/0 cli.py` (= 576 + 18 hunk) + `333/7 dispatch.py`; tracked = the 2 pre-existing files only; untracked adds = this record + the new test file | `attempt-1/numstat-after.txt`, `status-after-*.txt` (tracked guard `d1edad82…` = FIX-B5 value) | Tree left + this record |
| Pins + sst clean at close | rev-parse ×3, sst status | all 3 pins exact; sst status empty (0 B) | `attempt-1/sst-after.txt` (e3b0c44…) | Read-only repos |
| Spend | 0 CLI sessions; no installs | $0.00; cumulative 3/20, 6-call reserve intact | this REVIEW | Fully scripted stage |

## Findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| W1 | info (pre-existing, outside owned hunk) | `cli.py:237,661,664` (`safe_load` untyped via yaml shim), `cli.py:1361,1368` (unused `type: ignore`) | `mypy.log` post-hunk 5 errors ≡ `mypy-prehunk-baseline.log` 5 errors on the byte-exact B1 file (same codes, same code, +18 shift) | None for this stage — `mypy --strict` on `cli.py` was already non-clean before the hunk; the hunk adds zero new errors and the hunk lines themselves are strict-clean | None here (fixing would widen beyond the briefed narrow hunk; coordinator may schedule separately) |
| (no FAIL-grade findings) | — | — | — | — | — |

## Verdict, reviewer only

**CARRIED — P2-H3a reasoning-medium is in the real pipeline path.**

- Criteria established: live-exp WIN + F1 PASS predecessors (full read);
  zero drift at B1; seeded-config route proven viable for the gateway role
  (flow read + P2 live header); narrow `cli.py` hunk only (probe-identical
  lever, trial-cited comment, docstring note); new test file 6/6 on both
  interpreters; P05 e2e file green live-deselected on both (4+skip joint,
  5/5 real-gates); ruff check+format green on owned files; mypy strict
  green on the new test and new-error-free on `cli.py` (5 pre-existing,
  proven); argv pins byte-exact; tracked diff = 2 pre-existing files +
  hunk shape; sst clean; pins exact; 0 CLI calls, $0.00.
- Unmet criteria or missing evidence: live corroboration of the carried
  profile (out of this scripted brief by design — acceptance runs the P05
  live shape on this profile inside the 6-call reserve); patch
  correctness/verify-green (acceptance's verdict per the live-exp caveat).
- Baseline failures versus new regressions: zero regressions (P05 e2e
  green on both interpreters incl. the real-gates manual fixture; no
  existing test touched or weakened).
- Exact scope of independent execution/inspection: everything in the
  Evidence table was executed or read by me in this session: the 5
  required full reads; HEAD + 8 hashes + numstat + 3 pins + sst at open;
  argv/env-flow reference reads (zero edits outside owned files); hunk
  implementation + new test authorship (+1 format fix); winner-only (both
  interpreters, pre- and post-format) + P05 e2e (both interpreters) +
  ruff + mypy (+ byte-exact pre-hunk baseline proof with swap-restore
  checksums) + close drift/pins/sst/status guards. `trace-lite/` never
  listed, read, or written.
- Next action: coordinator schedules serialized acceptance (NOT mine):
  run the P05 live shape on this medium profile within the 6-call
  reserve, then verification. Winner-carry spends no more.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| Format drift in new test (ruff format --check rc=1) | my manual line wraps | `ruff format` applied to the owned test file; gates + both-interpreter runs re-executed green | `ruff.log`, `winner-only-*.log` (post-format) | None |
| (W1 mypy-5) | pre-existing cli.py strict errors | proven pre-existing, left untouched per narrow-hunk constraint | `mypy.log`, `mypy-prehunk-baseline.log` | Coordinator may schedule separately |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1  src/stc/cli.py
# CREATED (owned + evidence; this REVIEW.md is the record itself and is not self-listed)
0b5c3a8a85dea963ef8b95e43679bc504020152d105e89a2aaef05b677b69762  tests/unit/test_winner_carry.py
4c889a4cc1702d2e20e44465a0274df1e258d2731ca836e3b68c495bc035ecf5  evidence/FOLLOWUP/winner-carry/readiness.md
3d47d9b02956a05c6353695682930566111a632ae24857c6f2fba128826fa6a9  evidence/FOLLOWUP/winner-carry/attempt-1/mypy-prehunk-baseline.log
3976ec62fcc9294ecaea592e788a0dee22bc268549eff5bab0e373bb36e35fd5  evidence/FOLLOWUP/winner-carry/attempt-1/mypy.log
de39b44044e81bde8694e83668951eb22b464d5fa990f476bda8637f7b0f1102  evidence/FOLLOWUP/winner-carry/attempt-1/numstat-after.txt
1e3ffb1544f8e4b7ed7b02322a7114cab31b92dc4ad3a1a55c389692039643da  evidence/FOLLOWUP/winner-carry/attempt-1/p05-e2e-joint.log
71690538e85b59e2e2a9f936d072d168111d19e0b7f1965a2638ebae701bfcaf  evidence/FOLLOWUP/winner-carry/attempt-1/p05-e2e-real.log
c59e2237c281f94c0c0e7b7a2560a7889cd183106d1e8dae1e65f9a947db443f  evidence/FOLLOWUP/winner-carry/attempt-1/ruff.log
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/winner-carry/attempt-1/sst-after.txt
c66f62832b6b5c03e6feb3cfa69f88d81a3171999ad773e66159eb49424ab7df  evidence/FOLLOWUP/winner-carry/attempt-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/winner-carry/attempt-1/status-after-tracked.txt
26c765bd821257f56bb064e3ea2ae4487356878cf0c158636df718523de5ab61  evidence/FOLLOWUP/winner-carry/attempt-1/winner-only-joint.log
119bf40acd36f7d442caedf87a8c81b2399dd2b752a9b8aa970549d8a30f573b  evidence/FOLLOWUP/winner-carry/attempt-1/winner-only-real.log
```

`git diff` tracked hunks belonging to this stage: `src/stc/cli.py` only
(numstat 576/0 → 594/0, net +18, the seeding hunk + docstring note);
`src/stc/orchestrator/dispatch.py` 333/7 untouched (pre-existing).
