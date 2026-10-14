# FOLLOWUP accept-2 — Builder delivery (attempt-1): honest partial, A1 holds live, patch-format anatomy

Record type: builder delivery
Author role and date: acceptance2-builder / 2026-09-14
Packet: STC follow-up tranche, acceptance attempt-2 (re-run the approved
pinning-test task through the real pipeline on the A1-fixed tree; SAME
approved spec, not re-approved).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (9 hashes re-verified byte-exact at B1, zero drift: A1-fixed
`dialectic_runner c072f1da…0ff5`, `test_dialectic eea1a7ee…0ec0`, `cli.py
2ddfd6cb…d82f1` 594/0, `test_winner_carry 0b5c3a8a…69762`, `harness_worker
ced79ed5…7867`, `cli_gateway f9dda17e…07b8a`, `test_harness e96db8d0…70b45`,
`__init__ 10571421…bac40`, `dispatch.py dc75c56e…13c7` 333/7).
Pins: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after),
prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` (all exact at open and close).
Environment: real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`;
shims verified present, no recreation) for the live leg + dry-run replays +
anatomy replays; joint `<ws>/trace/.venv-linux/bin/python` 3.12.3 for the
second veto rerun; `PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`; codex-cli
`0.154.0`.
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Delivery section

- Behavior/artifact changed and why: NOTHING changed in product code — this
  stage re-runs the approved pinning-test task through the real pipeline on
  the A1-fixed tree. B1 READY (see `evidence/FOLLOWUP/accept-2/readiness.md`).
  B2 executed the exact P05-final command shape + `--choice 1`: the gateway
  leg WON twice (two valid §2 proposals, 45.5 s + 42.0 s), both verifies
  RAN TO JUDGMENT through the fixed mirror with ZERO stall and ZERO
  intervention, and both candidates failed verify on patch FORMAT (exact
  anatomy below — adjudicated live this time). The pipeline failed closed
  per contract: honest NEEDS_REPAIR `no-verified-candidate` partial,
  preserved whole. Per the binding success bar this is AUTOMATION-NOT-READY —
  valid evidence, NOT success. No mid-acceptance reshaping; no H1-context
  experiments (coordinator decision).
- Files or outputs changed: evidence ONLY, all under
  `evidence/FOLLOWUP/accept-2/` (`readiness.md`, `attempt-1/` with `dossier/`,
  live-run captures, status guards, `spend.jsonl`, veto rerun logs, this
  REVIEW). No STATE.md write; no commits; no tracked-file modification.
- Material implementation decisions: none (no implementation in scope). The
  stall guardrails (lease >500 MB or >10 min zero-event) were armed and
  watched read-only throughout; neither tripped (peak observed lease 202 MB
  mid-mirror, store/ledger cadence alive throughout, no nested dossier) —
  hence the intervention-free evidence this attempt owes is intact.
- Known limitations and checks not run: no champion, so merge / execution /
  judiciary / mutmut-on-champion remain undemonstrated live; module-path
  wiring is STILL unadjudicated (both proposals carry guessed imports, but
  both failed upstream on patch format — see Diagnosis, NOT a
  BLOCKED-WIRING verdict); worker-stage harnesses still never reached live
  (0 worker calls); the served gateway header is not preserved on success
  paths (finding A2 — carried); full `pytest tests/` beyond the P04 suite
  not run (precedent scope).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Predecessor gates (B1) | full reads | attempt-1 anatomy (gateway win + A1 stall + intervention log); a1-fix PASS; live-exp WIN + wiring caveat (adjudicate-live duty); winner-carry PASS; FIX-B5 NOT-READY baseline; packet §Fix tranche; SAME spec | readiness.md Gate 0 | Read, not re-executed |
| Drift gate (B1) | rev-parse, 9 full-sha recomputes, numstat, 3 pins, sst status | HEAD `edf5389`; 9/9 exact (A1-fixed pair at tasked new hashes); 594/0 + 333/7; pins exact; sst clean — zero drift | readiness.md Gate 1 | Hash-bound |
| Dry-run replay (B1, 0 calls) | bare + `--choice 1` dry-runs, real-gates, scratch dossiers (removed after) | bare exit 2, 0.80 + STOP, fresh `…c92fbb4b`; choice exit 0, single pins target, RT-08, choice-recorded, invariants file, fresh `…eed05d58` | readiness.md Gate 2 (values quoted) | Zero model calls |
| Seeded-medium sanity (B1, 0 calls) | `_seed_codex_home()` on the REAL operator login + winner-test rerun | seeded config carries `medium` (operator `max` rewritten); operator bytes bit-identical before/after; winner tests 6/6 real-gates | readiness.md Gate 3 | Direct proof + P2 header precedent |
| Mirror-fix coverage (B1) | code read of fix point + both call sites | single fix `mirror_source_tree` :283-300 (dst-exclusion + loud refusal); lease call :467 + merged call :837 both route through it; line numbers match the verify-1 audit exactly | readiness.md Gate 4 | Static read |
| B2 live run (exact P05-final shape) | `python -m stc run docs/builds/stc-integration/specs/p05-acceptance.md --target stc --budget time=600,tokens=500000,usd=10,iters=2,branching=1,depth=4 --choice 1`, real-gates, `STC_DOSSIER_DIR=…/attempt-1/dossier` | exit-1 class NEEDS_REPAIR, `no-verified-candidate` (2 branch refs, 0 verified); wall 16:36:14→16:48:49Z (755 s); 2 gateway calls/2 ok/0 worker; 0 refs scored; CLI RC 1 (`Error:` ClickException prefix) | `attempt-1/live-run-argv.txt`, `live-run-env.txt`, `live-run-stdout.txt`, `live-run-stderr.txt`, `dossier/` | 2 live calls; zero stall, zero intervention |
| A1 holds live (no stall) | read-only watch during run: lease `du`, top-level `ls`, nested-dossier probe, store/ledger mtimes | peak lease 202 MB mid-mirror (<500 MB alert); lease top level holds the real tree (`docs/`, `src/`, …); nested-dossier probe NEGATIVE; spend/store cadence alive throughout (legs 16:37:19 + 16:43:00, close 16:48:48); run completed on its own; `_quarantine/` created 16:36, EMPTY at close (armed, never needed) | this REVIEW (Diagnosis); `runs/*/leases/` (only empty `_quarantine`) | Read-only forensics; healthy mirror ≈300 MB single pass |
| Gateway legs WON on medium | dossier spend rows | leg 1: 45.464 s, exit 0, 5967 out_bytes; leg 2: 41.976 s, exit 0, 4609 out_bytes — both valid §2 `CandidateProposal` (DIVERGE pins-module targets, 5182 B + 3929 B patches); P2-H3a signature 3-for-3 across live-exp + attempt-1 + attempt-2 | `dossier/spend.json`, `dossier/spend_ledger.jsonl`, `runs/*/events.json` NODE_PROPOSED ×2, `store.db` (7 sst_events) | n=2 live (medium profile) |
| Verify reached judgment ×2 (adjudicated live) | events.json VERIFIER_STARTED/FINISHED pairs | cand `_0_0`: VERIFIER_FINISHED fail, duration 0.0, apply-stage (`git apply failed: corrupt patch at line 169` + fallback `Unrecognized diff line format … '*** End Patch'`); cand `_1_0`: VERIFIER_FINISHED fail, duration 25.6875 s, full real-gates judgment (`stc_mypy, stc_pytest, stc_ruff` all false, reward 0.00) — FIRST live real-gates execution ever | `runs/*/events.json` (7 events) | Exact live evidence |
| Cand-0 anatomy (0-call replay) | exact 5182 live bytes → `git apply --whitespace=nowarn` in scratch repo | `error: corrupt patch at line 169`, RC 128 — BYTE-IDENTICAL to the live stderr; cause: well-formed unified diff (`--- /dev/null`, `@@ -0,0 +1,213 @@`) with a trailing `*** End Patch` apply_patch marker | this REVIEW (Diagnosis); replay transcript in session | Exact-bytes replay, /tmp only (removed) |
| Cand-1 anatomy (0-call replay) | exact 3929 live bytes → verbatim write to pins path (the custody direct-replacement path, `custody.py:200-216` read) → ruff check + format + mypy strict + pytest | file starts `*** Begin Patch` (verbatim garbage); ruff-check RC 1 (219 errors), ruff-format RC 2, mypy RC 2 (`Invalid syntax`), pytest RC 2 (collection error) — matches live `ruff=False mypy=False pytest=False` exactly | this REVIEW (Diagnosis); `custody.py:176-216` (format dispatch) | Exact-bytes replay, /tmp only (removed) |
| NOT wiring (no BLOCKED-WIRING verdict) | proposal text reads + gate-failure layering | both proposals carry guessed imports (`praxist.dialectic.*`, `dialectic.*`) but NEITHER reached import resolution: cand 0 died at apply, cand 1 died at parse — failures are patch-FORMAT class, one step upstream of the wiring caveat, which therefore REMAINS unadjudicated (second time) | `events.json` payloads; Diagnosis | Text present, never executed |
| Fail-closed close | events/store/dossier reads; `ls` absence checks | STATUS NEEDS_REPAIR + reason + 2 branch refs + empty veto/scores + spend + review stating absence-by-design; `merged.diff` / `execution_receipt.json` / `judiciary_verdict.json` ABSENT (ls-confirmed); no traceback escaped | `dossier/STATUS`, `branches.json`, `result.json`, `spend.json`, `review.md`, `runs/*/` | Honest partial, never padded |
| Escalation chain re-closed | qa_log + invariants + TREE_CREATED | 0.80/triggered/τ0.30 → choice-recorded [1] → `P05_ACCEPTANCE_INVARIANTS.md` → TREE_CREATED (fresh `TASK-P05_ACCEPTANCE-06f26d5e`, distinct from all prior ids) → allowed_paths exactly the pins module, base `edf5389` | `dossier/qa_log.json`, `dossier/P05_ACCEPTANCE_INVARIANTS.md`, `runs/*/events.json` | Injection-free (relayed pre-authorized choice) |
| Elapsed accumulation live | budget_state vs wall | reported `elapsed_seconds` 688.977 vs CLI wall 755 s (16:36:14→16:48:49); both gateway legs + both verify durations (0.0 + 25.7) inside the reported figure; residual is CLI preamble/teardown outside the runner wall (same shape as attempt-1) | `dossier/branches.json`, `runs/*/result.json` | No-champion shape; no under-report defect |
| Confinement held | pre/post tracked+full status, sst status, /tmp leftover check | tracked IDENTICAL (`d1edad82…` = FIX-B5 value, before == after); full status byte-identical before/after (`c66f6283…`, collapsed untracked dir); numstat still 594/0 + 333/7; sst clean before/after; zero `/tmp` leftovers newer than run start (caller-deletes + per-call cleanup); B1 scratch removed | `status-before/after-*.txt`, `sst-before/after.txt` | Real tree untouched; all writes under untracked `FOLLOWUP/` |
| F1 sidecar correct | dossier listing | NO `spend-ledger.failures.jsonl` — correct: both gateway legs ok (F1 scope is harness stderr) | `dossier/` listing | F1 working as VERIFIED |
| Veto/fail-closed (unexercised live → rerun) | `pytest tests/unit/test_integration_dialectic.py -m "not live"`, BOTH interpreters | 61 passed on EACH (12.18 s real-gates, 11.89 s joint) = 58 pre-existing + 3 A1 regression; live veto_log `[]` (nothing to exercise veto with — 2 failed verifies) | `veto-failclosed-real.log`, `veto-failclosed-joint.log` | 0 live calls; scripted |
| Spend | `spend.jsonl` 2-row audit vs ledger | **2 CLI calls / 10** this stage (tranche 6/14; 6-call reserve NEVER touched); $0.00 metered; zero installs | `attempt-1/spend.jsonl` (2 rows) | CLI-session budget only |
| Scope/hygiene | pins at close, HEAD/log, STATE.md, stray sweep | HEAD still `edf5389`; no new commits; STATE.md untouched; all 3 pins exact; `trace-lite/` never listed, read, or written | git output (this session) | Tree left + this record |

## Diagnosis (what the evidence establishes)

- **A1 is CLOSED live.** Both verifies mirrored the full source tree into
  their leases, applied (or attempted apply), ran judgment, and released
  their leases — no recursion (nested-dossier probe negative, 202 MB peak
  vs 1.2 GB-and-growing at attempt-1), no zero-event stall (cadence alive
  throughout), no quarantine use, no intervention of any kind. The a1-fix
  verify-1 PASS is now corroborated by live execution through the exact
  layout that stalled.
- **Failure anatomy is patch-FORMAT class, adjudicated live (both
  candidates):**
  - Cand `_0_0` (5182 B): a well-formed new-file unified diff — correct
    `--- /dev/null` / `+++ b/…` / `@@ -0,0 +1,213 @@` shape per the spec's
    explicit instruction — with a single foreign trailer line `*** End Patch`
    (the codex apply_patch end marker leaking into the §2 `patch_diff`
    string). `git apply` rejects the whole patch (`corrupt patch at line
    169`); the SST manual fallback also rejects it (`Unrecognized diff line
    format … '*** End Patch'`). Apply-stage fail, gates never ran.
  - Cand `_1_0` (3929 B): pure `*** Begin Patch` / `*** Add File:` /
    `*** End Patch` apply_patch format (no `--- `/`@@`, so the custody
    dispatch at `custody.py:176` takes the direct-replacement branch
    `:200-216` and writes the ENTIRE marker text verbatim as the target
    file). Gates then ran on a file whose first line is `*** Begin Patch`:
    ruff-check 219 errors, ruff-format fail, mypy `Invalid syntax`, pytest
    collection error — all red, reward 0.00.
  - Both replays used the EXACT live bytes and reproduced the live verdicts
    precisely (cand-0 stderr byte-identical; cand-1 all-four-gates-red).
    The model emits apply_patch markers despite the spec's unified-diff
    instruction — the §2 `patch_diff` contract is parsed but its content
    convention is not followed.
- **NOT a BLOCKED-WIRING verdict.** The live-exp caveat (guessed
  `praxist.dialectic.*` / `dialectic.*` imports) is present in both
  proposals' text, but neither proposal reached import resolution — cand 0
  died at apply, cand 1 died at parse. Wiring therefore remains
  UNADJUDICATED for the second time; the observed failure is one step
  upstream (patch format). H1-context experiments remain unspent per the
  brief (and would target wiring, not the observed format failure).
- **The carried medium profile is 3-for-3.** Valid §2 emissions in 56.7 s
  (P2), 43.1 s (attempt-1), 45.5 s + 42.0 s (this run) on the exact shaped
  bytes that hang served at reasoning-max. Diverge emission through the
  real pipeline is now the reliable part; verify judgment of what is
  emitted is where champions go to die.
- **Fail-closed machinery validated live again.** Two failed verifies →
  `no-verified-candidate` → STATUS + reason + refs + empty veto/scores +
  spend + review, zero success artifacts, no traceback. `_quarantine/`
  armed-but-empty shows the substrate-error path was never needed.
- **Pre-existing red/green notes.** F2 template stamp drift
  (`INT-2026-09-13.2` in `review.md`) persists — cosmetic, carried. R1
  stays deferred (no blocking evidence). `test_cli.py` baseline untouched
  (not re-run, out of scope).

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| A3 | high (capability gap, evidenced live ×3) | §2 `patch_diff` emission vs custody apply | attempt-1 cand (Begin Patch, never judged) + this run cand 0 (unified+trailer → apply fail) + cand 1 (Begin Patch → garbage → all gates red): the model emits apply_patch markers despite the spec's explicit unified-diff instruction; custody has no marker-tolerant path (git apply + strict fallback both reject; non-diff payloads written verbatim) | EVERY live proposal so far has failed (or would fail) on patch format before any semantic judgment | Follow-up (out of acceptance scope; no product edits here): coordinator-owned — strip/translate apply_patch markers at the custody boundary, or constrain emission to unified diff (framing/lever TBD) |
| A2 (carried) | info (evidence gap, minor) | success-path gateway legs | `live-run-stderr.txt` holds only the final `Error:` line; no `header` handling exists in `cli_gateway.py`/`harness_worker.py` | Served header (reasoning/model confessor) unpreserved on success — medium corroborated triangulated instead of directly | Follow-up (optional): log the served header per gateway leg |
| F2 (carried) | info (cosmetic) | `dossier/review.md` | stamps `Contract: INT-2026-09-13.2`; run executed under follow-up tranche | Cosmetic drift | None here (template follow-up) |

No product defect in the acceptance owned surface beyond A3 is demonstrated:
the loop failed closed exactly per contract on every leg, and the A1 mirror
now performs live.

## Verdict, reviewer only

AUTOMATION-NOT-READY (builder-reported outcome; B3 to rule)

- Criteria established: B1 READY gates (zero drift, dry-run chain with fresh
  diff ids, seeded-medium proven on the real login, winner 6/6, mirror fix
  confirmed covering both call sites, explicit stall guardrails honored with
  zero intervention); B2 executed per contract (exact P05-final shape +
  pre-authorized `--choice 1`, full guards); gateway legs WON on medium
  twice (45.5 s + 42.0 s valid §2); A1 fix corroborated live (both mirrors
  completed, no recursion, no stall, quarantine armed-but-empty);
  verify REACHED judgment twice with exact patch-format anatomy reproduced
  on the live bytes (0 calls); first live real-gates execution ever
  (ruff+mypy+pytest on cand 1); honest no-champion partial preserved whole
  (STATUS, reason, refs, veto, budget, spend, review, prompt-payloads +
  stderr + status artifacts); escalation chain re-closed on fresh
  `TASK-P05_ACCEPTANCE-06f26d5e`; confinement held (tracked/full identical,
  sst clean, /tmp clean); P04 veto/fail-closed 61/61 on both interpreters (0
  calls); spend 2/10 CLI calls, $0.00, reserve untouched; zero product edits;
  zero unexplained drift.
- Unmet criteria or missing evidence: the binding success bar is NOT met — no
  champion, no FULL dossier (`merged.diff` / `execution_receipt.json` /
  `judiciary_verdict.json` absent by design). Root cause is the A3
  patch-format gap (product/capability boundary), not the carried profile
  (3-for-3 on its legs), not the mirror (fixed, proven live), and not
  proposal wiring (still never adjudicated). Live custody-apply-success /
  merge / execution / judiciary / mutmut-on-champion remain undemonstrated
  live.
- Baseline failures versus new regressions: zero regressions (no code changed;
  suites green: 61/61 both interpreters). This run strictly advances the
  frontier over attempt-1 (1 proposal, stall pre-empted verify) and FIX-B5
  (0 proposals): 2 proposals, verify-to-judgment ×2, real gates live ×1.
- Exact scope of independent execution/inspection: (for B3 to fill).
- Next action: acceptance B3 (fresh session) rules on this record per the
  follow-up brief; route A3 (patch-format gap) + A2 (header gap) + the still
  unadjudicated wiring caveat to coordinator follow-up scoping. No B4
  repair exists within this packet (acceptance owns no product surface).

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings yet; A3/A2/F2 are follow-up items, not B4 repairs) | — | — | — | A3 patch-format gap + A2 header gap + wiring caveat ride to coordinator follow-up |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — this stage touched zero product files; tracked numstat is exactly the
# 2 pre-existing loose-set mods, both still matching the tasked hashes:
#  src/stc/cli.py 594/0 2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1
#  src/stc/orchestrator/dispatch.py 333/7 dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
06a9db1571994fde0388b1bcd1e5e54f1dd602f0dac9f6b70d807093e320fbba  evidence/FOLLOWUP/accept-2/readiness.md
edcd0a218c732b6953684a8353db2e4840096eb5e113dbc8c94faa3acc1dab77  evidence/FOLLOWUP/accept-2/attempt-1/dossier/P05_ACCEPTANCE_INVARIANTS.md
f2da43908be9cdbe07e2e31d9de4e6a19655b4b8f0508d5ce03c8b8fa43c3172  evidence/FOLLOWUP/accept-2/attempt-1/dossier/STATUS
6152992be1577af9423ea0bdab8e3f189d2b193993c7d77cc7100ba35103f8aa  evidence/FOLLOWUP/accept-2/attempt-1/dossier/branches.json
53e79d5aae9cdce562f9df7f79418a54d5bde6fc8f72db6  evidence/FOLLOWUP/accept-2/attempt-1/dossier/qa_log.json
e47a18568af8ed6805e781930f13c3f73f7f85adffd8c3586bc9a7e3f72f907b  evidence/FOLLOWUP/accept-2/attempt-1/dossier/review.md
356036a573fcf0474445cbb6fcfa28db6ce9beac6fb699d629ab7650b474d8f8  evidence/FOLLOWUP/accept-2/attempt-1/dossier/run_ref.json
683860d0e3c49bd22bc3603c84ee2749b0c42db2f6d64351474958df25e00c1b  evidence/FOLLOWUP/accept-2/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-06f26d5e/events.json
3677e254b6c1ed7aea3b2401dda0dd737a21fe27e30bf6d9ff614599b814c80a  evidence/FOLLOWUP/accept-2/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-06f26d5e/inhibitors.json
ab45ad939a1170864428616231e23fc2112b14885cc018a0fb28cbd98528fcab  evidence/FOLLOWUP/accept-2/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-06f26d5e/loss_ledger.json
4c1340ec2c15b690e207d9443d03a99e858e7c39906360637eb9333581fa4ba3  evidence/FOLLOWUP/accept-2/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-06f26d5e/result.json
cc93680c932f4dad2f23cb142d2c6353b5d6ff910c655cb4d9df841511b2e293  evidence/FOLLOWUP/accept-2/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-06f26d5e/store.db
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept-2/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-06f26d5e/synthesis.json
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept-2/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-06f26d5e/veto_log.json
ded35598230d4656fe55b074bc0dd6f35a3a229cf90bcd85a9bb577a32e263df  evidence/FOLLOWUP/accept-2/attempt-1/dossier/spend.json
9e2522179c58f01f5d01541ed9a795fc21170be44ada55b96724a97e911173a3  evidence/FOLLOWUP/accept-2/attempt-1/dossier/spend_ledger.jsonl
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept-2/attempt-1/dossier/veto_log.json
025d5f32ff982038a25a6fad9f477d1f76f752941075f6f26692df1d03719f89  evidence/FOLLOWUP/accept-2/attempt-1/live-run-argv.txt
8e95aec8f31ad97b48ea1ebd582a4bfb14c5440ad95e924fbdc0617b8913a185  evidence/FOLLOWUP/accept-2/attempt-1/live-run-env.txt
d2c7ed4032e117c2c13391e9cb8e7006250c379efcff35ca29dc7d878a110ac3  evidence/FOLLOWUP/accept-2/attempt-1/live-run-stderr.txt
4b3ed2311548fe370a98ad14173fb7a9b5f99102cbfd65f1f1ea111b077f180d  evidence/FOLLOWUP/accept-2/attempt-1/live-run-stdout.txt
ab01610ffa069aa9831d07422454727aa675574ec21826fc03fa6aa118f21a5e  evidence/FOLLOWUP/accept-2/attempt-1/spend.jsonl
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/accept-2/attempt-1/sst-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/accept-2/attempt-1/sst-before.txt
c66f62832b6b5c03e6feb3cfa69f88d81a3171999ad773e66159eb49424ab7df  evidence/FOLLOWUP/accept-2/attempt-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/accept-2/attempt-1/status-after-tracked.txt
c66f62832b6b5c03e6feb3cfa69f88d81a3171999ad773e66159eb49424ab7df  evidence/FOLLOWUP/accept-2/attempt-1/status-before-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/accept-2/attempt-1/status-before-tracked.txt
6485fce58b1f050774db1e98003e07a19cbf931444a2768ea2d9fb3431c9e37b  evidence/FOLLOWUP/accept-2/attempt-1/veto-failclosed-joint.log
1c5763c07bb5f8d6ff415bdf2f14da608f668a34db781e5fcfbd5e7ae72d70ea  evidence/FOLLOWUP/accept-2/attempt-1/veto-failclosed-real.log
```

`git diff` tracked hunks belonging to this stage: NONE (no tracked file created
or modified; `git diff --numstat` shows only the 2 pre-existing loose-set mods).
```
