# F1-fix — Builder delivery (attempt 1)

Record type: builder delivery
Author role and date: f1-fix-builder / 2026-09-14
Packet: STC follow-up tranche (F1 stderr-truncation gap) @ INT-2026-09-14.1
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set: 2 pre-existing tracked mods (`cli.py` 576/0, `dispatch.py` 333/7,
both at tasked hashes) + the 6 VERIFIED fix-delta files at verified hashes
(B1 Gate 1) + new evidence under `evidence/FOLLOWUP/f1-fix/`. Product change
is confined to the 3 F1-owned files below; nothing else touched.
Pins: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after),
prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` (all re-probed at B2 close).
Environment: joint `trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`); real-gates
`learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`. Zero model/CLI calls (fully
scripted); ruff 0.16.1 + mypy 2.3.0 from the real-gates env.

## Delivery section

- Behavior/artifact changed and why: F1 CLOSED. Every failed harness/gateway
  attempt now appends a record with FULL stdout + FULL stderr, exit status,
  effective model/profile, duration, and candidate identity (stc HEAD +
  owned-file full+short sha256) to the failure-evidence sidecar
  `<ledger.stem>.failures.jsonl` next to the spend ledger — which for live
  dossier runs is `dossier_dir/spend_ledger.failures.jsonl`, i.e. under the
  run dir (`cli.py:1334` passes that ledger; `dossier.py` copies ledger rows
  verbatim so the pointer propagates untouched). The ledger `note` keeps a
  short `[full stderr: <sidecar>#<id>]` pointer (never the only copy; the
  `note[:300]` backstop is retained harmlessly), and the raised gateway error
  carries the error TAIL + pointer instead of the truncated head. The
  B2-call-2 class of loss (300 chars of header, cause at byte ~5000+) is now
  unloseable: the cause is recoverable from the sidecar byte-exact.
- Files or outputs changed: 2 owned product files
  (`src/stc/integration/harness_worker.py`: sidecar helpers + `log_row`
  `failure_evidence` key + worker capture/write + dispatch pre-create/exclude;
  `src/stc/integration/cli_gateway.py`: `generate(profile=)` + evidence write
  + tail raise + `invoke` profile threading) and 1 owned test file (5 new
  `test_f1_*` tests + 3 helpers, append-only; zero existing tests modified),
  plus evidence under `evidence/FOLLOWUP/f1-fix/` (`readiness.md`,
  `attempt-1/` with 4 pytest logs, ruff/mypy logs, status guards, this
  REVIEW). No commits; no STATE.md writes; sst/prompt-kit/trace read-only;
  `trace-lite/` never touched; no argv/shaping changes.
- Material implementation decisions: (1) single JSONL sidecar, NOT one file
  per failure — `dispatch.py` honors `outer_exclude` by EXACT path only, so
  per-failure files under the ledger dir would trip the outer tripwire on
  fail-then-retry-success runs (which reach the post-run audit) and be
  quarantine-moved; the sidecar is touched pre-audit and exact-excluded,
  append-invisible exactly like the ledger file itself (proven by
  `test_f1_worker_failure_then_success_preserves_evidence_without_breach`).
  (2) `failure_evidence` row key present ONLY on failure rows — success rows
  keep the exact pre-fix key set (proven by
  `test_f1_success_path_writes_no_failure_records`). (3) Gateway evidence is
  written pre-raise (needs no chaperone); worker evidence in the attempt
  `finally` (covers result-failures, crashes, and timeouts uniformly).
  (4) Evidence helpers are best-effort and never raise (a logging failure
  warns; the raised tail still carries the cause even if the write fails).
- Known limitations and checks not run: no live re-run (0-CLI-call brief; the
  capacity-tail shape is mirrored scripted, not observed live); full
  `pytest tests/` beyond the P03 suite + adjacent dialectic/e2e files not run
  (out of F1 scope); `test_cli.py` pre-existing baseline untouched (not
  re-run).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Predecessor gate | full reads of FIX-B5 + P05-fix attempt + P05-fix verify-1 REVIEWs | FIX-B5 NOT-READY with F1 OPEN; P05-fix F1 finding + B3 endorsement confirmed | `evidence/FIX-B5/REVIEW.md`, `evidence/P05-fix/*/REVIEW.md` | Read, not re-executed |
| Candidate identity + drift gate | `git rev-parse`, pins, sha256 recompute of 6 fix files + 2 tracked mods | HEAD `edf5389` = tasked base (one docs-only commit past `4544190`, zero non-`docs/builds` paths); all 6 fix hashes + `cli.py`/`dispatch.py` hashes exact; all 3 pins exact; sst clean | `evidence/FOLLOWUP/f1-fix/readiness.md` (Gates 0–1) | Hash-bound |
| (a) Fast-fail full stderr recoverable, cause at TAIL | `test_f1_gateway_failure_preserves_full_stderr_with_cause_at_tail` (scripted exit-1, >300-char header stderr, capacity cause past byte 300, via `CLIModelGateway.invoke`) | `stderr_full` byte-exact in sidecar; raised error contains the tail cause (`Selected model is at capacity`); record carries exit/model/profile/duration/identity | `attempt-1/f1-only-real.log` (5/5 PASSED) | Scripted mirror of the live capacity shape, not a live call |
| (b) Ledger note points at the artifact | same test + worker/crash/timeout tests | note ≤300 chars with `[full stderr: <sidecar>#<id>]`; `failure_evidence` = `<abspath>#<id>` resolving to the record | `attempt-1/f1-only-real.log` | Pointer + dedicated row key |
| Worker channel + tripwire safety | `test_f1_worker_failure_then_success_preserves_evidence_without_breach` | fail-then-retry dispatch SUCCEEDS (post-run audit passes — sidecar trips nothing); attempt-1 evidence complete; success row has no new key | `attempt-1/f1-only-real.log` | Decisive for the sidecar-over-files design |
| Crash + timeout paths | `test_f1_worker_crash_preserves_full_error`, `test_f1_gateway_timeout_records_partial_stdout` | crash: full `OSError: disk gone` preserved, exit None; timeout: exit-124 record with partial stdout + timeout message | `attempt-1/f1-only-real.log` | Both `not ok` shapes covered |
| (c) Success-path bytes unchanged | `test_f1_success_path_writes_no_failure_records` | gateway + worker success rows keep the EXACT 13-key pre-fix set; sidecar gains zero records; contents identical | `attempt-1/f1-only-real.log` | Byte-shape pinned |
| (d) P03 suite green, live-deselected, both interpreters | `pytest tests/unit/test_integration_harness_worker.py -m "not live"` joint + real-gates | 76 passed, 5 deselected on EACH (71 pre-existing + 5 new F1; 0 failures) | `attempt-1/p03-joint.log`, `attempt-1/p03-real.log` | Live deselected per D13 |
| Adjacent suites (regression) | `pytest tests/unit/test_integration_dialectic.py tests/integration/test_run_e2e.py -m "not live"` real-gates | 63 passed | `attempt-1/adjacent-real.log` | Shared-path collateral check |
| (d) ruff on owned files | `ruff check` + `ruff format --check` (0.16.1) on the 3 owned files | All checks passed; 3 files already formatted | `attempt-1/ruff.log` | Configured gates, not defaults |
| (d) mypy strict on owned files | `mypy --strict` (2.3.0) on 2 product + 1 test file | No issues in 2 files; no issues in 1 file | `attempt-1/mypy.log` | Strict per pyproject |
| Confinement held | pre/post tracked + full status; numstat; sst status; scope audit | tracked status IDENTICAL (guard hash `d1edad82…` = FIX-B5-era value); numstat still exactly 576/0 + 333/7; full delta = own `FOLLOWUP/` dir only; sst clean; owned-files-only diff (no argv/shaping/dispatch/cli/dossier changes) | `attempt-1/status-after-*.txt`, `attempt-1/sst-after.txt` | B1-before observation in readiness Gate 1 |
| Spend | 0 CLI sessions; no installs | $0.00 metered; budget reserve intact (20/20 remain incl. ≥6 acceptance) | this REVIEW | Fully scripted tranche |

## Diagnosis (what the evidence establishes)

- The truncation is fixed at the root for both failure-reporting paths
  (ledger note + raised error) on both channels (worker + gateway): full
  bytes always land in the sidecar first; short forms are pointers/tails.
- The sidecar placement (next to the spend ledger) puts live-run evidence
  inside the dossier dir with zero dossier/CLI changes, since the dossier
  already copies ledger rows verbatim.
- The tripwire analysis (exact-path exclusions + audit-on-success) ruled out
  per-failure files; the passing fail-then-retry test proves the sidecar
  survives the audit it must live under.

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| (none — no new defects observed; F1 is closed by this tranche) | — | — | — | — | — |

## Verdict, reviewer only

F1-FIXED (builder-reported outcome; B3/acceptance to rule)

- Criteria established: (a) fast-fail full stderr recoverable byte-exact
  with tail cause (gateway via `invoke`, worker, crash, timeout); (b) ledger
  note ≤300 chars pointing at `<sidecar>#<id>` + dedicated row key;
  (c) success rows keep the exact pre-fix key set, zero failure records,
  identical contents; (d) P03 suite 76 passed / 5 deselected on BOTH
  interpreters + adjacent 63 passed + ruff check/format + mypy strict all
  green on owned files; confinement held (tracked identical, sst clean,
  owned-files-only); 0 CLI calls, $0.00.
- Unmet criteria or missing evidence: none within the F1 brief. Live
  end-to-end demonstration of a capacity-tail recovery awaits the next live
  run (out of this scripted brief by design).
- Baseline failures versus new regressions: zero regressions (all 71
  pre-existing P03 tests pass unmodified on both interpreters; adjacent
  suites green).
- Exact scope of independent execution/inspection: (for B3 to fill).
- Next action: acceptance/B3 rules on this tranche; on VERIFIED, coordinator
  records F1 CLOSED and the fix rides the next live run.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| F1 (high, evidence-preservation) | `note[:300]` head truncation in ledger + raised error discarded full stderr | Sidecar with full bytes + pointer note + raised tail (this tranche) | `attempt-1/f1-only-real.log` (5/5) + P03 logs + lint logs | None (B3 to confirm) |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned, F1 fix)
ced79ed572d50f5c67d7e8556fe08127f59e0c529fc50bdaf1bc6898805a7867  src/stc/integration/harness_worker.py
f9dda17ec411c567dfccc51515cedfa69d79b75a6effd2c6e75c72ec76207b8a  src/stc/integration/cli_gateway.py
e96db8d00a2950166f77ec6069ab98d9a944a344bfb452a4ffb7e6f3ce070b45  tests/unit/test_integration_harness_worker.py
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
3245665767898877c45a5f8e81cf5c27f757b006123758b1e8de989d0496bd9e  evidence/FOLLOWUP/f1-fix/attempt-1/adjacent-real.log
366776823bc9ce9edc214a2a3912e867ccebe2bc38770f7f2b1de576c7819316  evidence/FOLLOWUP/f1-fix/attempt-1/f1-only-real.log
8c7c95724512aaf74c747077096362f9151c7779f5ccf370ed3b15e484041ecf  evidence/FOLLOWUP/f1-fix/attempt-1/mypy.log
434e565c89e1af3b4db4ab490dbbf649df5e5b87cf16d0a226cc6e2404e4e390  evidence/FOLLOWUP/f1-fix/attempt-1/p03-joint.log
1598e4c0555f46c32a274f412d01c9f2dfe74dfbd3c986a1fea2bfc4532e512b  evidence/FOLLOWUP/f1-fix/attempt-1/p03-real.log
f9c45d476a59fa79477633c375c0b31d5fde1bdebbc0b1a62d48796388fe17eb  evidence/FOLLOWUP/f1-fix/attempt-1/ruff.log
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/f1-fix/attempt-1/sst-after.txt
4f5e3d14c70fad9c401a1046db40d58c74ce5bd24041bce17134cbdcb42b3335  evidence/FOLLOWUP/f1-fix/attempt-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/f1-fix/attempt-1/status-after-tracked.txt
4ebfb8161b9a8039a3236e76cd3212d646739d734ebd5becddba424844f10b28  evidence/FOLLOWUP/f1-fix/readiness.md
```

`git diff` tracked hunks belonging to this tranche: NONE (owned files are
untracked loose; `git diff --numstat` shows only the 2 pre-existing loose-set
mods above, both still matching the tasked hashes).
