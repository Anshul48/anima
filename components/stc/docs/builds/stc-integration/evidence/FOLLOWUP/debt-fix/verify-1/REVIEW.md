# Debt-fix — close-out independent verification (verify-1): PASS, debt share complete

Record type: independent verification (coordinator close-out, fresh session)
Author role and date: coordinator / 2026-09-19
Packet: STC follow-up tranche, G1 debt retirement + evidence exclusion
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set re-verified byte-exact this session (**28/28 full-sha recompute**,
zero drift — values below == attempt-1 Identity block exactly); tracked
numstat exactly 10 files 1114+/14-; pins sst `079f4de6…` (clean before/after),
prompt-kit `4f442a6c…`, trace `a24a9370…` (all exact).
Environment: real-gates `<ws>/learn-anything/.venv/bin/python` **3.11.15**
(primary, per operator instruction to conform to available Python 3.11)
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`)
+ joint `<ws>/trace/.venv-linux/bin/python` 3.12.3 (newtests + veto sanity
only) (`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`; pytest `-p no:cacheprovider`.
All runs SEQUENTIAL; outputs staged in `/tmp/closeout-stage/` during runs and
copied to `verify-1/` only after completion (no concurrent evidence writes).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.
**0 live calls; 0 CLI sessions; $0.00; tranche still 8/20, 6-call reserve
intact.**

## Delivery section

- Behavior/artifact changed and why: NOTHING changed by me — confirmed. This
  record rules on the debt-fix attempt-1 builder delivery (29-item G1 debt
  retirement + ruff-exclude of immutable evidence + Gates 1+2 green +
  substrate flip + diagnostic e2e). Ruling: **record VERIFIED (PASS)** — every
  outcome claim re-executed on the hash-pinned tree or re-inspected from exact
  log bytes; the debt share is DONE; Gate-3 literal exit-0 remains blocked by
  coordinator findings F1–F4 (env/commit, out of debt scope — correctly routed,
  not scope-crept). One info-grade provenance note (V-CO-INFO-1, verdict-neutral):
  the builder's `fixture-pipeline-post-real.log` is byte-identical to the
  baseline pre log (durations included); the outcome is independently
  re-established by my fresh rerun (81.60 s, same 5/1).
- Files or outputs changed: this record + its 12 logs only (all under
  `evidence/FOLLOWUP/debt-fix/verify-1/`). No product file touched; no test
  file touched; no STATE.md write; no commits. sst/prompt-kit/trace
  read-only; `trace-lite/` never listed, read, or written.
- Material implementation decisions: none (verification only).
- Known limitations and checks not run: no live calls (0-CLI brief — live
  judiciary / merge-execution / mutmut-on-champion remain unproven by design);
  full-suite, mirror Gate-3, diagnostic e2e, mutmut box, and joint per-file
  legs REUSED from attempt-1 under the hash-bound rationale below (tree
  28/28 exact + envs intact + all rerunnable rows reproduced) — not re-executed.

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Required full reads | read all 5 records in full | debt-fix readiness + attempt-1 REVIEW + SUSPENDED.md + combined readiness + combined attempt-1 REVIEW | `evidence/FOLLOWUP/debt-fix/`, `evidence/FOLLOWUP/combined-fix/` | Read, not re-executed (predecessor scope) |
| Drift gate (mine) | rev-parse, 28 full-sha recomputes, numstat, 3 pins, sst status, at open | HEAD `edf5389`; 28/28 exact (full values in Identity); 1114+/14-; pins exact; sst clean; zero drift | this REVIEW (Identity) | Hash-bound |
| Reverse-reconstruction (mine) | `verify-reconstructions.py` (in-packet script, unmodified) on real-gates 3.11 | ALL RECONSTRUCTIONS EXACT, RC 0: cli.py pre-image `2ddfd6cb…d82f1`, dialectic-test pre-image `eea1a7ee…0ec0` (typed blocks 2/2) | `verify-1/recon.log` | Strongest proof, re-executed |
| Gates 1+2, real tree (mine) | `[py -m ruff check .]`, `[py -m ruff format --check .]`, `[py -m mypy --strict src tests]` (substrate-argv-exact, gate env, real-gates) | All checks passed RC 0; 106 files formatted RC 0; no issues in 67 files RC 0 — **byte-identical file to builder `mirror-gates-real.log`** (`00e27712…`, deterministic tool output) | `verify-1/gates-real-tree.log` | Real tree; excludes evidence/ per config |
| Mirror rebuild + Gates 1+2 (mine) | `run-mirror-gates.py` (in-packet, unmodified) + the 3 exact gate commands in `/tmp/debtfix-lease-gates`, real-gates | mirror ready HEAD `edf5389` whole-tree evidence intact RC 0; gates RC 0 ×3 (same `00e27712…` bytes) | `verify-1/mirror-build.log`, `verify-1/mirror-gates-real.log` | Lease-faithful; `.git` in, skip-set out |
| P01 post (mine) | `pytest test_integration_{adapters,identity,memory}.py -q --tb=short`, real-gates | 1 failed + 114 passed: SAME node `test_record_shape_and_env_keys` (3.11-vs-3.12 env assert, F4); normalized diff vs builder post shows ONLY hex-address variance | `verify-1/p01-postfiles-real.log` | Outcome-identical to oracle |
| Veto/newtests post (mine) | `pytest test_integration_dialectic.py -m "not live" -q`, BOTH interpreters | 61/61 BOTH (13.59 s real, 13.75 s joint) | `verify-1/veto-{real,joint}.log` (copies also in combined verify-1) | Shared replay |
| Fixture/pipeline post (mine) | `pytest test_dialectic_fixture.py test_pipeline.py -q -m "not live"`, real-gates | 5 passed/1 deselected (81.60 s) — outcome-identical; see V-CO-INFO-1 | `verify-1/fixture-pipeline-post-real.log` | Fresh run, genuine duration |
| Compiler/CLI post (mine) | `pytest test_cli.py test_compiler.py -q --tb=short`, real-gates | 1 failed + 52 passed (552 s): SAME node `test_cli_run_json_mode` (`assert 1 == 0`, committed-bytes E2E, F3); progress-dot order differs only (argv file order — V-CO-INFO-2) | `verify-1/compiler-cli-post-real.log` | Outcome-identical to oracle |
| Judiciary + W1/W2/W4/A3 (mine) | 5-file newtests run `-q`, BOTH interpreters | 68/68 BOTH (12.70 s real, 11.45 s joint); real log identical to builder's modulo duration | combined `verify-1/newtests-{real,joint}.log` | Covers judiciary 22 + A3 18 + H1 9 + refusal 17 + deselect 2 |
| G2 collect (mine) | `--collect-only -q` bare + `-m "not live"`, real-gates | 533 bare / 527 + 6 deselected — exact counts | `verify-1/collect-{bare,deselected}.log` | No test added/removed |
| Substrate flip (mine) | the 2 named nodes, real-gates | 2 passed (36.73 s) — flip HOLDS post-fix | `verify-1/substrate2-real.log` | Product's own G1 proof green |
| Reuse rationale (not rerun) | hash + env + process argument | tree 28/28 exact; both venvs + all 3 shims intact; every rerunnable row reproduced with outcome-identical results → builder full-suite, mirror Gate-3 ×2, diag-e2e, mutmut-box, joint per-file legs stand as valid evidence | attempt-1 logs (hashes in that REVIEW's Identity) | No tree/env change since builder runs |
| Confinement | sst status, pins, HEAD/log, STATE.md, diff audit | sst clean; pins exact; HEAD `edf5389`, no new commits; STATE.md untouched by me; tracked hunks exactly the 10 owned files; `trace-lite/` never touched | this REVIEW | Tree left + this record |
| Spend | 0 CLI sessions; no installs | $0.00; tranche still 8/20, 6-call reserve intact | this REVIEW | Fully scripted stage |

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| V-CO-INFO-1 | info (provenance note, outcome re-established — verdict-neutral) | attempt-1 `fixture-pipeline-post-real.log` vs `baseline/fixture-pipeline-pre-real.log` | The two files are BYTE-IDENTICAL (123 B, incl. `82.14s (0:01:22)`); all other 7 pre/post suite pairs genuinely differ. Most plausible reading: staging slip (baseline bytes placed as the post log; prose written from the misplaced file), not selective fabrication (7/8 reruns + all scripts genuine). Outcome independently re-established by my fresh run: 5 passed/1 deselected, 81.60 s, same file pair. Originals left byte-exact per V1-INFO-1 precedent | None — outcome claim verified by my rerun | None (erratum recorded here) |
| V-CO-INFO-2 | info (argv order, verdict-neutral) | verify-1 vs attempt-1 `compiler-cli-post-real.log` | Progress-dot order differs (F at position 12 vs 53): file order on my argv (`test_cli.py test_compiler.py`) vs builder's. Same failing node + same 1/52 counts | None — outcome-identical | None |
| V-CO-INFO-3 | info (coincidence note, verdict-neutral) | verify-1 `fixture-pipeline-post-real.log` first16 `785ce690c5332477` | Matches the recorded superseded-partial first16 — i.e. the (now-overwritten) suspended run printed the same 81.60 s duration. Genuine coincidence across ~80 s200 ms-clustered gate work; my run was independently executed and observed. Either reading leaves every outcome unchanged | None | None |
| (no FAIL-grade findings) | — | — | — | — | — |

Erratum corroboration (V123-INFO-1, accept-2 `qa_log.json` manifest typo):
recomputed file sha256 `53e79d5aae9cdce562ea52996fff171c242f9df7f79418a54d5bde6fc8f72db6`
(64 hex) vs REVIEW line-202 60-hex spliced value — erratum stands as recorded
in accept-123-verify REVIEW; original left byte-exact (append-only, FIX-B5
V1-INFO-1 precedent). No other errata found.

## Verdict, reviewer only

**PASS** — debt-fix attempt-1 record verified accurate and complete; debt share
complete (29/29 + byte-exact exclusion, Gates 1+2 green real-tree AND
lease-mirror, substrate flip holds, zero regressions on every rerunnable row).
Gate-3 literal exit-0 remains blocked by F1–F4 (joint tool absence; lease-layout
procedural skips; committed-bytes E2E reds; 3.11-vs-3.12 env assert) — all
env/commit, none debt-owned, correctly routed to coordinator. Tranche stays
NOT-READY per the live-success bar (no live champion ever; attempt-4 not run).

- Criteria established: 5 required full reads; 28/28 drift gate; reconstructions
  exact; gates RC 0 ×3 real-tree + ×3 lease-mirror; every affected suite rerun
  post-fix on real-gates 3.11 with outcomes identical to reconciled oracles
  (p01 same node, fixture same 5/1, compiler-cli same node, newtests 68/68,
  veto 61/61, collect 533/527+6, substrate 2/2); joint sanity 68/68 + 61/61;
  byte-identical gate reproduction (`00e27712…`); sst clean, pins exact, $0.00,
  reserve intact; zero product edits.
- Unmet criteria or missing evidence: none within the debt-fix brief. Full-suite
  / mirror Gate-3 / diag-e2e / mutmut rows reused under the hash-bound rationale
  (no tree/env change; all rerunnable rows reproduced).
- Baseline failures versus new regressions: ZERO regressions (every post outcome
  == its oracle; the single provenance note concerns log bytes, not outcomes,
  and is covered by independent rerun).
- Exact scope of independent execution/inspection: everything in the Evidence
  table marked (mine) was executed or read by me in this session (inherited
  nothing): 5 full reads; HEAD + 28 file hashes + 3 pins + sst + numstat;
  recon + 6 gate invocations + mirror rebuild + 9 pytest invocations (real 7,
  joint 2); all pre/post byte comparisons; mtime sequencing; erratum recompute.
- Next action: coordinator records debt-fix VERIFIED, commits records-only,
  reports follow-up tranche NOT-READY (F2/F3/F4 explicitly unresolved; F1
  env-blocked), and holds the integration-contract design tranche before any
  attempt-4. No B4 repair exists within this packet.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3-grade findings; V-CO-INFO-1/2/3 are notes, not defects) | — | — | — | F1–F4 ride to coordinator design tranche |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — verification only; zero product files touched)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
a3c791903d78f7bd01a8cab9d6138f83efdcbbba4193f315e0bc4105ca2b8873  evidence/FOLLOWUP/debt-fix/verify-1/collect-bare.log
c41224ee20cd07bfe7dce2c2336e28a2ebfca5ac8e310f2a5d8e0c061852338b  evidence/FOLLOWUP/debt-fix/verify-1/collect-deselected.log
016117501158e18bf340e69ddd9d253e711446cad7c79b7b83e84dc66513f3e3  evidence/FOLLOWUP/debt-fix/verify-1/compiler-cli-post-real.log
785ce690c53324770e774bcdc6357d74856995baa1778299a2f636e419108758  evidence/FOLLOWUP/debt-fix/verify-1/fixture-pipeline-post-real.log
00e27712aeaa3e8f6b28dec8277ef58360f10203a269c9e90ca571c225349850  evidence/FOLLOWUP/debt-fix/verify-1/gates-real-tree.log
6e4546637ce3d05413d84de72198c4e3854ac5a37e0e2911457c4e2f6c4796b6  evidence/FOLLOWUP/debt-fix/verify-1/mirror-build.log
00e27712aeaa3e8f6b28dec8277ef58360f10203a269c9e90ca571c225349850  evidence/FOLLOWUP/debt-fix/verify-1/mirror-gates-real.log
25d1f61bc63e364e9d0390f2430245828e80150453c242bdedc6d7b50243193a  evidence/FOLLOWUP/debt-fix/verify-1/p01-postfiles-real.log
a86d158b5e5c1bffbcb05f7f5f0724e887bfae22d83ba6408bd8b495ed6f38e0  evidence/FOLLOWUP/debt-fix/verify-1/recon.log
81085f885efcb3729f33b3c2b60ea0f727ec7602c508c7d234cbb07724a48d28  evidence/FOLLOWUP/debt-fix/verify-1/substrate2-real.log
a90707204069ff8ab4242e5cc96adf2283dc74e3aef40d16ad8315980b6691ae  evidence/FOLLOWUP/debt-fix/verify-1/veto-joint.log
74a6ced8cf0f4e2291eeddbd5a21beed212e113ad318b899ecd7141214905dab  evidence/FOLLOWUP/debt-fix/verify-1/veto-real.log
# DRIFT-GATE recompute (28/28 exact vs attempt-1 Identity — verification input, not output)
96cf197e9b1c731b2c5bfb59d5f0d5b2d7a9f8a63a30221a52c784e446f8ac51  pyproject.toml
d0a97611358454ecdeafdf0273a47cf0803850d2cca6f249503adcbb90921bea  src/stc/cli.py
b21be978def892872c64b46783b603c01117b7f64bf9bad1e381fe52c3b73e0a  src/stc/compiler/bundler.py
8f53fba96ee78ab6709e7722c2a1fdffa0c9ff9383654fcebba36e14a4dd903e  src/stc/integration/adapters.py
8edb6892e66d9067b6a15dfd63f5178a3064f2db1f6e93e146273b1fc4b3fbca  src/stc/integration/identity.py
3ba90a5ce51db3a8a768afd6e5a9d2942ff8384ac0e478ce3659126743e5f712  src/stc/integration/memory.py
93f54ff4a940cf6b87d9cdc491ce57604f8e6b1217bc9d1db4419002b2c2480c  tests/integration/test_pipeline.py
6ffe08c264cc55147dea26aadf06555c3cd43b98174c7999792c45335c05341b  tests/integration/test_dialectic_fixture.py
168c12675c1d9e1d4765652512610d9150f2e4312a3a2635102f1416b8fde6ca  tests/unit/test_cli.py
bc2b355054133dea216bd51f740744aa2b50a06fa023b7436d347cee62af2126  tests/unit/test_compiler.py
ee60aba90d911363a4f90c70e66c014f917541ac3a49b64e78a8d7544f51edec  tests/unit/test_integration_adapters.py
031bc293a9fb1684ca77495c8a0c322d94672c888689578f79cd971d74b29bf1  tests/unit/test_integration_identity.py
143fe07b9097527ab55613b3874e4445ad93aa3ccc2ca3955da58368d0f687db  tests/unit/test_integration_memory.py
8bc8005dc71af8f7d87d449540dbd4ee1c2b1b4e017a5e0068a082c4a9eb8f38  tests/unit/test_integration_dialectic.py
c59a8f408c0c8c5f7aff155c2360be14c696348e09b3a2edde46e7cdb270e21a  src/stc/judiciary/auditor.py
dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7  src/stc/orchestrator/dispatch.py
8958eae167c53ffdddd475dace8096161a6365806971c115e6aa4d7535862a0f  src/stc/substrate/runner.py
c87b3a74d1e653b68521d4c40592bf9faa0d40130a33fb0495f1f2bcf2a40d9d  tests/unit/test_judiciary.py
29eb3906b35a7aad78206bbe1f17e20d9214a16a865e450b2b5c73056a501913  src/stc/integration/cli_gateway.py
c072f1dac2725f470bfeb9753288e2158064838467784d3f8ceb279b640a0ff5  src/stc/integration/dialectic_runner.py
c3c886b19b612d12c1e4ea5bb4034ffdcb696ca2ecb5ae0445f6d3bac79b91ba  tests/unit/test_gateway_h1_context.py
106806c187d53637a3d9f15eda2cf01bf0e9d99ef9330c8897e4c464611590c5  tests/unit/test_gateway_marker_refusal.py
103348a5538e51e2f253c7a249e205f97f2bc70bd77b8bd2d8d55e4ece036e60  tests/unit/test_pytest_gate_live_deselect.py
ced79ed572d50f5c67d7e8556fe08127f59e0c529fc50bdaf1bc6898805a7867  src/stc/integration/harness_worker.py
e96db8d00a2950166f77ec6069ab98d9a944a344bfb452a4ffb7e6f3ce070b45  tests/unit/test_integration_harness_worker.py
0b5c3a8a85dea963ef8b95e43679bc504020152d105e89a2aaef05b677b69762  tests/unit/test_winner_carry.py
f99b278588e0c7eec956a6203e5475c78f95c3d4e76f2946c892a13a125b1f2b  tests/unit/test_a3_patch_format.py
105714219afcfbef9c81c50ce4216de4ce93096482aff2a4597cb4aaf04bac40  src/stc/integration/__init__.py
```

`git diff` tracked hunks belonging to this session: NONE (evidence-only
`verify-1/` writes; `git diff --numstat` shows only the 10 pre-existing
loose-set mods, 1114+/14-, still tasked-exact).
