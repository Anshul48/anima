# FOLLOWUP a3-fix — Builder delivery (attempt-1): frame pin + validated SST tolerance proposal

Record type: builder delivery
Author role and date: a3-fix-builder / 2026-09-14
Packet: STC follow-up tranche, A3-fix stage (close the patch-format gap
that killed all three live proposals; 0 live calls).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (9 hashes re-verified byte-exact at B1, zero drift; the 2 owned
files now at the new hashes below, 8/8 non-owned still tasked-exact).
Pins: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after),
prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` (all exact at open and close).
Environment: joint ws-absolute `<ws>/trace/.venv-linux/bin/python` 3.12.3
(`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`) +
real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`; pytest `-p no:cacheprovider`;
ruff 0.16.1 / mypy 2.3.0 / git 2.43.0; ruff/mypy caches redirected to
/tmp (verified populated there).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Delivery section

- Behavior/artifact changed and why: custody is SST-owned (ruled with
  file paths at B1: `sst/src/sst/sandbox/custody.py`, the only custody
  in the workspace), so per branch (b) this stage delivers (1) the
  STC-owned unified-diff-only pin in the gateway emitter frame
  (`shape_gateway_prompt`, the single choke point for all gateway
  emission — SST bytes stay verbatim, D15/D7 intact), constraining the
  §2 `proposed_changes` emission that leaked apply_patch markers on all
  three live proposals; and (2) the SST custody-tolerance change as a
  concrete, validated, ready-to-land proposed diff (113+/1-, no SST
  edits): marker normalization R0-R3 at the `apply_proposal` boundary —
  byte-identical fast path for marker-free payloads, stray-envelope
  strip re-entering dispatch, Add-File-only translation to new-file
  unified diffs, loud refusal before any write for everything else.
  B1 READY (see `evidence/FOLLOWUP/a3-fix/readiness.md` — predecessor
  gates, drift gate, ownership determination, exact translation rules).
- Files or outputs changed: exactly the 2 owned files —
  `src/stc/integration/cli_gateway.py`
  (`f9dda17e…07b8a` → `aedffa12…bb392`: 4 frame-pin lines + docstring
  line, closing instruction only) and new
  `tests/unit/test_a3_patch_format.py` (`f99b2785…b1f2b`: exact live
  bytes hash-pinned + frame-pin tests + SST-proposal validation via
  scratch-apply of the evidence diff) — plus evidence under
  `evidence/FOLLOWUP/a3-fix/` (`readiness.md`, `attempt-1/` with the
  SST diff, logs, guards, this REVIEW). No STATE.md write; no commits;
  no other product file touched; sst/prompt-kit/trace read-only.
- Material implementation decisions: (1) branch (b) per the ownership
  ruling — no wrapper-side sanitizing (it would fork proposal identity
  across NODE_PROPOSED bytes / `patch_hash` / `render_merged_diff`;
  written reasons in readiness.md); (2) R1 refinement vs the B1 draft:
  stray-envelope-stripped remainders re-enter normal dispatch
  (blank → refuse) instead of requiring unified shape — avoids
  false-refusing stripped raw-code payloads (the raw path is legitimate
  SST semantics: controller raw-fallback + backends emit raw code) and
  removes the second dispatch predicate (smaller diff, no sync risk);
  newline state preserved for byte-fidelity; behavior on both observed
  live shapes unchanged; (3) `patch_hash` stays over the raw proposed
  bytes, preserving the identity invariant; (4) column-0-only marker
  matching, so legitimate diff content (e.g. context line ` ***bold***`)
  can never trigger — pinned by test.
- Known limitations and checks not run: the SST tolerance change is
  validated but NOT landed (sst read-only — needs an SST-authorized
  stage; the diff applies cleanly and is gate-green); the frame pin
  constrains emission probabilistically (live corroboration rides the
  next acceptance leg); indented (non-column-0) markers are an
  unobserved shape and fail closed, not translated; no live re-run
  (0-call brief); `test_cli.py` baseline untouched (out of scope);
  full `pytest tests/` beyond the new + affected files not run (brief
  scope); wiring remains UNADJUDICATED (orthogonal, carried).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Predecessor gates (B1) | full reads | accept-2 A3 + diagnosis + custody dispatch; a1-fix verify-1 PASS; live-exp P2 §2 + wiring caveat; a1 B1/B2 precedent; dossier chain re-hashed exact | readiness.md Gate 0 | Read, not re-executed |
| Drift gate (B1) + close | rev-parse, 9 full-sha recomputes, numstat, 3 pins, sst status, at open AND close | HEAD `edf5389`; 9/9 exact at open; at close 8/8 non-owned still tasked-exact, 2 owned at new hashes; 594/0 + 333/7; pins exact; sst clean — zero unexplained drift | readiness.md Gate 1; `attempt-1/numstat-after.txt`, `sst-after.txt`, `status-after-*.txt` | Hash-bound |
| Ownership (B1) | full reads + workspace glob + def/marker greps | custody ONLY at `sst/src/sst/sandbox/custody.py` (:179-216 dispatch+direct-replacement, :343-494 fallback), sst clean at pin; no STC copy; STC owns only the wrapper delegation (:468/:838) + emitter frame → branch (b) | readiness.md Ownership | Static + hash-bound |
| Live-byte pins (B1) | events.json + store.db extraction, both stores | cand-0 5182 B `44a77e30…09a11`, cand-1 3929 B `0c7052d6…b2fe3`, byte-identical across stores; dossier hashes match accept-2 Identity | readiness.md Fix design | Hash-bound |
| New tests 18/18, BOTH interpreters | `pytest tests/unit/test_a3_patch_format.py -m "not live" -v`, joint + real-gates, final bytes | 18 passed on EACH (2.65 s joint, 3.03 s real-gates): hash pins, dossier cross-check, 4 frame tests, diff-applies, cand-0 apply-succeeds (fallback-carries), cand-1 translate (git-carries), 8 refusal shapes, no-regression byte-identity | `attempt-1/a3-newtests-joint.log`, `a3-newtests-real.log` | Scripted, 0 CLI calls |
| Affected suite, BOTH interpreters | `pytest tests/unit/test_integration_harness_worker.py -m "not live"`, joint + real-gates | 76 passed + 5 deselected on EACH (16.23 s joint, 16.76 s real-gates) — frame pin breaks nothing (frame tests assert substrings, verified by read) | `attempt-1/harness-worker-unit-joint.log`, `harness-worker-unit-real.log` | Live deselected per D13 |
| Pristine-vs-patched discrimination (/tmp probe) | exact live bytes through pristine vs scratch-patched SST custody | pristine cand-0 FAILS with live-byte-identical stderr; pristine cand-1 "succeeds" writing 3929 B verbatim garbage (file sha == payload sha); patched applies both (4923 B + 3716 B, pinned content) | `attempt-1/discrim-pristine-vs-patched.log` (probe script itself in /tmp only) | /tmp scratch, sst untouched |
| SST diff applies cleanly | `git apply --check` + apply to scratch copy of pinned base | CHECK-OK; applied tree byte-identical to prototype; diff scope exactly 113+/1- (helpers + call site + hash line), zero churn | `attempt-1/sst-proposal-gates.log`, `attempt-1/sst-custody-tolerance.diff` | Pinned base `079f4de6` |
| Proposal gate-green (SST config) | ruff check + format --check + mypy --strict on scratch-patched copy | All checks passed; already formatted; strict-clean (one format iteration caught and fixed in-session, diff regenerated) | `attempt-1/sst-proposal-gates.log` | Land-ready evidence |
| Ruff on owned files | `ruff check` + `ruff format --check` (0.16.1, configured pyproject gates) | All checks passed; 2 files already formatted (one autofix+format pass on the new test file only — hash pins re-verified after) | `attempt-1/ruff.log` | Configured gates |
| Mypy strict on owned files | `mypy --strict --follow-imports=silent` (2.3.0, MYPYPATH=real-gates paths) | Success: no issues found in 2 source files (new test file strict-clean, zero pre-existing) | `attempt-1/mypy.log` | Strict per pyproject (`strict=true`) |
| Confinement held | pre/post full+tracked status, numstat, sst status, cache sweeps | tracked `d1edad82…` = FIX-B5 value; numstat still 594/0 + 333/7 (`de39b44…`); full status differs from B1-open by exactly the 1 new owned-file line; sst clean (0 B); no repo `__pycache__`/pytest-cache writes; ruff/mypy caches in /tmp only | `status-after-*.txt`, `numstat-after.txt`, `sst-after.txt` | Tree left + this record |
| Spend | `spend.jsonl` 0-row audit | **0 CLI calls** this stage (tranche still 6/20; 6-call reserve NEVER touched); $0.00 metered; zero installs | `attempt-1/spend.jsonl` (empty, sha e3b0c44…) | CLI-session budget only |
| Scope/hygiene | pins at close, HEAD/log, STATE.md, stray sweep | HEAD still `edf5389`; no new commits; STATE.md untouched; all 3 pins exact; `trace-lite/` never listed, read, or written | git output (this session) | Tree left + this record |

## Diagnosis (what the evidence establishes)

- **The A3 gap is closed on both sides of the boundary.** Emission side:
  the STC frame now pins pure-unified-diff `proposed_changes` naming
  the exact forbidden markers, at the single choke point every gateway
  call traverses, with SST bytes still verbatim (D15/D7 proven by
  test, including marker-bearing SST input). Custody side: the SST
  proposal gives `apply_proposal` a deterministic marker path — the
  exact 5182 B now apply (fallback carries past the 213-vs-165 hunk
  count git rejects), the exact 3929 B translate to a git-appliable
  diff (exact count 127), 8 untranslatable shapes refuse before any
  write with the workspace left empty, and marker-free payloads
  (unified new/modify, raw, markdown-bold) behave byte-identically
  pristine-vs-patched.
- **The discrimination proves the tests target the defect.** Pristine
  SST custody on the exact bytes reproduces the live record precisely
  (cand-0 stderr byte-identical; cand-1 file bytes == payload bytes,
  the verbatim-garbage path); the scratch-patched proposal flips both
  to byte-exact clean content. The regression tests cannot pass on the
  old behavior.
- **No regressions, no widening.** The affected frame-host suite is
  76/76 on both interpreters; ruff + mypy strict green on both owned
  files; the SST diff touches exactly 3 hunks (113+/1-) with the
  fallback/dispatch/scope logic otherwise byte-identical; R0 keeps
  every marker-free payload on its exact current path.
- **What remains is landing + live corroboration.** The tolerance
  change needs an SST-authorized stage to land (this stage proves it
  applies cleanly and is gate-green); the frame pin's emission effect
  is judged on the next acceptance live leg inside the reserve.

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| (none — no new defects found; the accept-2 `:176` dispatch citation is off by 5 lines from the true `:181` predicate, substance confirmed — noted in readiness, not a defect) | — | — | readiness.md Ownership | None for this stage | None here |

## Verdict, reviewer only

FIXED-PROPOSED (builder-reported outcome; B3/acceptance to rule)

- Criteria established: B1 READY gates (predecessors read, zero drift,
  custody ruled SST-owned with file paths); smallest-correct branch-(b)
  fix (4-line frame pin + validated SST proposal, R1 refinement
  justified); exact live bytes hash-pinned and dossier-cross-checked;
  18/18 new tests + 76/76 affected suite on BOTH interpreters (0
  calls); pristine-vs-patched discrimination with live-byte-identical
  failure replay; SST diff applies cleanly, scope-audited 113+/1-,
  ruff+mypy-strict green under SST config; ruff+mypy-strict green on
  owned files; confinement held (tracked/numstat/pins/HEAD/STATE/sst
  all clean, full status +1 owned line only); spend 0.
- Unmet criteria or missing evidence: none within the a3-fix brief. SST
  landing awaits an SST-authorized stage by design; live corroboration
  (a real proposal emitting clean unified diff through the pinned
  frame, a real verify through tolerant custody) awaits the next
  acceptance live leg.
- Baseline failures versus new regressions: zero regressions (76/76
  affected-suite tests green on both interpreters; no existing test
  touched — the new tests are a new file).
- Exact scope of independent execution/inspection: (for B3 to fill).
- Next action: a3-fix verification (fresh session) rules on this
  record; on PASS, coordinator schedules SST landing + acceptance
  re-run of the P05 live shape within the 6-call reserve.

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| A3 (accept-2: apply_patch markers in §2 vs marker-intolerant custody) | Model emits codex markers despite the unified-diff instruction; SST custody dispatch has no marker path (git+fallback reject; non-diffs written verbatim) | STC frame pin (unified-diff-only, markers named) + SST tolerance proposal (R0 no-op / R1 strip+redispatch / R2 Add-translate / R3 loud refusal), validated on the exact live bytes | this REVIEW + owned files at new hashes + all attempt-1 logs + `sst-custody-tolerance.diff` | SST landing + live corroboration ride coordinator follow-up |
| A2 (served-header gap, carried) | (out of a3-fix scope) | Carried (unchanged) | — | Rides coordinator follow-up scoping |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
aedffa1277ea9d4fee009531430bfbcff9fb9a8975837af7372654c9e46bb392  src/stc/integration/cli_gateway.py
# CREATED (owned)
f99b278588e0c7eec956a6203e5475c78f95c3d4e76f2946c892a13a125b1f2b  tests/unit/test_a3_patch_format.py
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
14d30da297ac7e4397e3c2ea56167d4a4142c46aa2d171787ba40cefff75d544  evidence/FOLLOWUP/a3-fix/readiness.md
84fb6e207e5a8b082156730aee199c2823067d4ddbfa8a4a91102110b5891f32  evidence/FOLLOWUP/a3-fix/attempt-1/sst-custody-tolerance.diff
627c9582cc48c6cebad32f862e43bf84efdee88d3c1e88261c948bb0ac98b4bd  evidence/FOLLOWUP/a3-fix/attempt-1/discrim-pristine-vs-patched.log
169fd908047ac33015ce034375525bd8a568623ea712cd31b744ce87113a4a82  evidence/FOLLOWUP/a3-fix/attempt-1/a3-newtests-real.log
d6a4106aae33eb34e57aee74a3466e722d99b725eb75adb480d466198cae40f5  evidence/FOLLOWUP/a3-fix/attempt-1/a3-newtests-joint.log
691318d7ddb5468f64ba2c5e5b005f716ed1eacd2482981ec845f309b27500f5  evidence/FOLLOWUP/a3-fix/attempt-1/harness-worker-unit-real.log
a5e330d6504535872acbf0ad7052dde39cc061d3a91238b725171e2323753161  evidence/FOLLOWUP/a3-fix/attempt-1/harness-worker-unit-joint.log
0d55242239c8130dd382f079647fa4e301732075d39f8232069b0301854555f1  evidence/FOLLOWUP/a3-fix/attempt-1/ruff.log
a084226b415f181284973b38f8ec86bae4c2b4ee5d4203be45827489fb67bb0b  evidence/FOLLOWUP/a3-fix/attempt-1/mypy.log
2106398b3265c20eee6a2534890161ef6bdda31438f675673ce07fbaa445baca  evidence/FOLLOWUP/a3-fix/attempt-1/sst-proposal-gates.log
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/a3-fix/attempt-1/spend.jsonl
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/a3-fix/attempt-1/sst-after.txt
c7f24296a7a48ceb546d11538922f6c757a5c50af8ed059b4e40ba80bf60c2c1  evidence/FOLLOWUP/a3-fix/attempt-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/a3-fix/attempt-1/status-after-tracked.txt
de39b44044e81bde8694e83668951eb22b464d5fa990f476bda8637f7b0f1102  evidence/FOLLOWUP/a3-fix/attempt-1/numstat-after.txt
```

`git diff` tracked hunks belonging to this stage: NONE (both owned files
are untracked loose-set members; `git diff --numstat` shows only the 2
pre-existing loose-set mods: `src/stc/cli.py` 594/0, `2ddfd6cb…d82f1`;
`src/stc/orchestrator/dispatch.py` 333/7, `dc75c56e…13c7` — both still
tasked-exact).
