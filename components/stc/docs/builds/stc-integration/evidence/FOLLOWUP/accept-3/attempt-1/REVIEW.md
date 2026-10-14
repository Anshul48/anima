# FOLLOWUP accept-3 — Builder delivery (attempt-1): pin holds 1/2, wiring adjudicated BLOCKED

Record type: builder delivery
Author role and date: acceptance3-builder / 2026-09-14
Packet: STC follow-up tranche, acceptance attempt-3 (re-run the approved
pinning-test task through the real pipeline on the A3-fixed tree: frame
pin live; SST tolerance NOT landed — sst read-only; SAME approved spec,
not re-approved).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (10 hashes re-verified byte-exact at B1, zero drift: A3 frame-pin
`cli_gateway aedffa12…bb392`, `test_a3_patch_format f99b2785…b1f2b`,
A1-fixed `dialectic_runner c072f1da…0ff5`, `test_dialectic eea1a7ee…0ec0`,
`cli.py 2ddfd6cb…d82f1` 594/0, `test_winner_carry 0b5c3a8a…69762`,
`harness_worker ced79ed5…7867`, `test_harness e96db8d0…70b45`,
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
  the A3-fixed tree. B1 READY (see `evidence/FOLLOWUP/accept-3/readiness.md`).
  B2 executed the exact P05-final command shape + `--choice 1`: the gateway
  leg WON twice (two valid §2 proposals, 57.8 s + 52.4 s), both verifies
  RAN TO JUDGMENT with ZERO stall and ZERO intervention, and the frame pin
  HELD on exactly one leg — the first marker-free unified diff ever emitted
  live (4299 B, custody success, full 76.4 s real-gates judgment). That
  proposal failed the gates on module-path wiring (guessed
  `praxist.dialectic.*` imports unresolvable — the live-exp caveat,
  adjudicated live at last): BLOCKED-WIRING verdict with exact evidence
  below. The other leg re-emitted the unified+trailer shape and died at
  apply, proving the pin constrains probabilistically (as stated upfront)
  and the strict SST fallback still rejects markers. The pipeline failed
  closed per contract: honest NEEDS_REPAIR `no-verified-candidate` partial,
  preserved whole. Per the binding success bar this is AUTOMATION-NOT-READY —
  valid evidence, NOT success. No mid-acceptance reshaping; no H1-context
  experiments (coordinator decision).
- Files or outputs changed: evidence ONLY, all under
  `evidence/FOLLOWUP/accept-3/` (`readiness.md`, `attempt-1/` with `dossier/`,
  live-run captures, status guards, `spend.jsonl`, veto rerun logs, this
  REVIEW). No STATE.md write; no commits; no tracked-file modification.
- Material implementation decisions: none (no implementation in scope). The
  stall guardrails (lease >500 MB or >10 min zero-event) were armed and
  watched read-only throughout; neither tripped (peak observed lease 218 MB
  mid-mirror, store/ledger cadence alive throughout, no nested dossier) —
  hence the intervention-free evidence this attempt owes is intact.
- Known limitations and checks not run: no champion, so merge / execution /
  judiciary / mutmut-on-champion remain undemonstrated live; worker-stage
  harnesses still never reached live (0 worker calls); the served gateway
  header is not preserved on success paths (finding A2 — carried); full
  `pytest tests/` beyond the P04 suite not run (precedent scope).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Predecessor gates (B1) | full reads | attempt-2 anatomy (A1 holds, medium ×2, A3 kills both); a3-fix PASS (pin verified, SST diff validated-but-unlanded); live-exp WIN + wiring caveat (adjudicate-live duty); FIX-B5 NOT-READY baseline; packet §Fix tranche; SAME spec | readiness.md Gate 0 | Read, not re-executed |
| Drift gate (B1) | rev-parse, 10 full-sha recomputes, numstat, 3 pins, sst status, custody marker-grep + bytes | HEAD `edf5389`; 10/10 exact (A3 pair at tasked new hashes); 594/0 + 333/7; pins exact; sst clean; custody `Begin Patch` grep rc=1 + bytes `43c24681…ec864` = verify-1 value (tolerance NOT landed); pin read live at :103-106 — zero drift | readiness.md Gate 1 | Hash-bound |
| Dry-run replay (B1, 0 calls) | bare + `--choice 1` dry-runs, real-gates, scratch dossiers (removed after) | bare exit 2, 0.80 + STOP, fresh `…cc907857`; choice exit 0, single pins target, RT-08, choice-recorded [1], invariants file, fresh `…59e18ed6` | readiness.md Gate 2 (values quoted) | Zero model calls |
| Scripted suites (B1, 0 calls) | winner-carry + A3 tests, real-gates | 24 passed (6 + 18) in 3.26 s | readiness.md Gate 2 | Direct proof |
| Frame-pin expectation (B1) | stated upfront in readiness | pin constrains probabilistically; SST fallback still strict — markers still fail; adjudication order fixed (pin hold → wiring → champion) | readiness.md | Pre-committed |
| B2 live run (exact P05-final shape) | `python -m stc run docs/builds/stc-integration/specs/p05-acceptance.md --target stc --budget time=600,tokens=500000,usd=10,iters=2,branching=1,depth=4 --choice 1`, real-gates, `STC_DOSSIER_DIR=…/attempt-1/dossier` | exit-1 class NEEDS_REPAIR, `no-verified-candidate` (2 branch refs, 0 verified); wall 17:42:15→17:56:43Z (868 s); 2 gateway calls/2 ok/0 worker; 0 refs scored; CLI RC 1 (`Error:` ClickException prefix) | `attempt-1/live-run-argv.txt`, `live-run-env.txt`, `live-run-stdout.txt`, `live-run-stderr.txt`, `dossier/` | 2 live calls; zero stall, zero intervention |
| A1 holds live (no stall) | read-only watch during run: lease `du`, top-level `ls`, nested-dossier probe, store/ledger mtimes | peak lease 218 MB mid-mirror (<500 MB alert); nested-dossier probe NEGATIVE; spend/store cadence alive throughout (legs 17:43:34 + 17:49:33, close 17:56:43); run completed on its own; `_quarantine/` created 17:42, EMPTY at close (armed, never needed) | this REVIEW (Diagnosis); `runs/*/leases/` (only empty `_quarantine`) | Read-only forensics; healthy mirror ≈300 MB single pass |
| Gateway legs WON on medium | dossier spend rows | leg 1: 57.847 s, exit 0, 6379 out_bytes; leg 2: 52.392 s, exit 0, 4969 out_bytes — both valid §2 `CandidateProposal` (DIVERGE pins-module targets, 5534 B + 4299 B patches); P2-H3a signature 4-for-4 across live-exp + attempt-1 + attempt-2 + attempt-3 | `dossier/spend.json`, `dossier/spend_ledger.jsonl`, `runs/*/events.json` NODE_PROPOSED ×2, `store.db` (7 sst_events) | n=2 live (medium profile) |
| Verify reached judgment ×2 (adjudicated live) | events.json VERIFIER_STARTED/FINISHED pairs | cand `_0_0`: VERIFIER_FINISHED fail, duration 0.0, apply-stage (`git apply failed: corrupt patch at line 187` + fallback `Unrecognized diff line format … '*** End Patch'`); cand `_1_0`: VERIFIER_FINISHED fail, duration 76.4108 s, full real-gates judgment (`stc_mypy, stc_pytest, stc_ruff` all false, reward 0.00) | `runs/*/events.json` (7 events) | Exact live evidence |
| Pin holds 1/2 (adjudication step 1) | exact-bytes marker scan of both live `patch_diff` payloads | cand 0 (5534 B): unified diff + trailing `*** End Patch`, NO Begin marker — pin did NOT hold; cand 1 (4299 B): pure marker-free unified diff (`--- /dev/null`, `@@ -0,0 +1,242 @@`, zero `***` anywhere) — pin HELD, first clean emission live | this REVIEW (Diagnosis); replay transcripts in session | Exact live bytes |
| Cand-0 anatomy (0-call replay) | exact 5534 live bytes → `git apply --whitespace=nowarn` + pristine SST `apply_proposal` in scratch | `git apply`: `corrupt patch at line 187`, RC 128; pristine custody: `success=False`, file absent, error string BYTE-IDENTICAL to the live stderr — strict fallback still rejects markers, as pre-committed | this REVIEW (Diagnosis) | Exact-bytes replay, /tmp only (removed) |
| Cand-1 custody path (0-call replay) | exact 4299 live bytes → pristine SST `apply_proposal` in scratch git repo | `success=True`, 4096 B real Python file (`2e6c187a…`, starts `from __future__ import…`): fallback carries past git-apply hunk-count strictness (`corrupt patch at line 128` on the strict path alone) — marker-free payloads flow to gates | this REVIEW (Diagnosis) | Exact-bytes replay, /tmp only (removed) |
| Wiring verdict: BLOCKED-WIRING (adjudication step 2) | ruff check + format + mypy strict + pytest collect on the exact custody output (real-gates toolchain) | ruff-check RC 1 (3 errors: import-sort + useless returns), ruff-format RC 1 (would reformat), mypy 5 errors incl. 3× `import-not-found` for `praxist.dialectic.{errors,models,runner}`, pytest collection ERROR `ModuleNotFoundError: No module named 'praxist'` — imports do NOT resolve; matches live `ruff=False mypy=False pytest=False` exactly | this REVIEW (Diagnosis) | Exact-bytes replay, /tmp only (removed) |
| Fail-closed close | events/store/dossier reads; `ls` absence checks | STATUS NEEDS_REPAIR + reason + 2 branch refs + empty veto/scores + spend + review stating absence-by-design; `merged.diff` / `execution_receipt.json` / `judiciary_verdict.json` ABSENT (ls-confirmed); no traceback escaped | `dossier/STATUS`, `branches.json`, `result.json`, `spend.json`, `review.md`, `runs/*/` | Honest partial, never padded |
| Escalation chain re-closed | qa_log + invariants + TREE_CREATED | 0.80/triggered/τ0.30 → choice-recorded [1] → `P05_ACCEPTANCE_INVARIANTS.md` → TREE_CREATED (fresh `TASK-P05_ACCEPTANCE-9f1632b8`, distinct from all prior ids) → allowed_paths exactly the pins module, base `edf5389` | `dossier/qa_log.json`, `dossier/P05_ACCEPTANCE_INVARIANTS.md`, `runs/*/events.json` | Injection-free (relayed pre-authorized choice) |
| Elapsed accumulation live | budget_state vs wall | reported `elapsed_seconds` 794.802 vs CLI wall 868 s (17:42:15→17:56:43); both gateway legs + both verify durations (0.0 + 76.4) inside the reported figure; residual is CLI preamble/teardown outside the runner wall (same shape as attempt-1/2) | `dossier/branches.json`, `runs/*/result.json` | No-champion shape; no under-report defect |
| Confinement held | pre/post tracked+full status, sst status, /tmp leftover check | tracked IDENTICAL (`d1edad82…` = FIX-B5 value, before == after); full status byte-identical before/after (`c7f24296…` = a3-fix verify-1 value, collapsed untracked dir); numstat still 594/0 + 333/7; sst clean before/after; zero run `/tmp` leftovers (no `stc-gateway-*`, no `p05-codex-home-*`; own pytest dirs removed, pre-existing dirs kept) | `status-before/after-*.txt`, `sst-before/after.txt` | Real tree untouched; all writes under untracked `FOLLOWUP/` |
| F1 sidecar correct | dossier listing | NO `spend-ledger.failures.jsonl` — correct: both gateway legs ok (F1 scope is harness stderr) | `dossier/` listing | F1 working as VERIFIED |
| Veto/fail-closed (unexercised live → rerun) | `pytest tests/unit/test_integration_dialectic.py -m "not live"`, BOTH interpreters | 61 passed on EACH (12.76 s real-gates, 12.45 s joint) = 58 pre-existing + 3 A1 regression; live veto_log `[]` (nothing to exercise veto with — 2 failed verifies) | `veto-failclosed-real.log`, `veto-failclosed-joint.log` | 0 live calls; scripted |
| Spend | `spend.jsonl` 2-row audit vs ledger | **2 CLI calls / 8** this stage (tranche 8/14; 6-call reserve NEVER touched); $0.00 metered; zero installs | `attempt-1/spend.jsonl` (2 rows) | CLI-session budget only |
| Scope/hygiene | pins at close, HEAD/log, STATE.md, stray sweep | HEAD still `edf5389`; no new commits; STATE.md untouched; all 3 pins exact; `trace-lite/` never listed, read, or written | git output (this session) | Tree left + this record |

## Diagnosis (what the evidence establishes)

- **The frame pin holds probabilistically: 1/2 legs clean.** Cand 1 is the
  first marker-free unified diff ever emitted live (4299 B, zero `***`
  anywhere): pristine custody applies it (`success=True`, 4096 B real
  Python) and it runs the full 76.4 s real-gates judgment. Cand 0 re-emits
  the attempt-2 shape (well-formed unified diff with a single trailing
  `*** End Patch`) and dies at apply with a byte-identical replay. The
  pin's installation is VERIFIED (a3-fix verify-1); its emission effect is
  now measured live at 1/2 — a probabilistic constraint, exactly as
  pre-committed in readiness. The strict SST fallback still rejects every
  marker-bearing payload (no custody safety net, as briefed).
- **Wiring is adjudicated at last: BLOCKED-WIRING.** The pin-held proposal
  reached import resolution and failed there: it imports
  `praxist.dialectic.errors/models/runner` (the model-guessed module path
  from the live-exp caveat; the real tree is `stc.integration.*`), and the
  gates prove it unresolvable — pytest collection
  `ModuleNotFoundError: No module named 'praxist'`, mypy 3×
  `import-not-found`, plus ruff lint/format red and 2 mypy strictness
  errors. All four gate signals reproduce on the exact live bytes through
  pristine custody, matching the live `ruff=False mypy=False pytest=False`
  verdict. This is the evidence-backed trigger for H1-context (real API
  signatures in-frame) — a coordinator decision; no H1 experiments were
  improvised here.
- **A1 is CLOSED live (third corroboration).** Both verifies mirrored,
  judged, and released — no recursion (nested-dossier probe negative,
  218 MB peak vs 1.2 GB-and-growing at attempt-1), no zero-event stall
  (cadence alive throughout), no quarantine use, no intervention of any
  kind.
- **The carried medium profile is 4-for-4.** Valid §2 emissions in 56.7 s
  (P2), 43.1 s (attempt-1), 45.5 s + 42.0 s (attempt-2), 57.8 s + 52.4 s
  (this run) on the exact shaped bytes that hang served at reasoning-max.
  Diverge emission through the real pipeline is now the reliable part;
  what is emitted is where champions go to die (format 1/2, wiring 1/1).
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
| W1 (BLOCKED-WIRING verdict) | high (capability gap, evidenced live) | §2 proposal module paths vs real tree | pin-held cand 1 imports `praxist.dialectic.*` (guessed; live-exp caveat); pytest `ModuleNotFoundError: No module named 'praxist'` + mypy 3× `import-not-found` on the exact live bytes through pristine custody | EVERY format-clean proposal so far (n=1) fails on wiring before any semantic judgment | Follow-up (out of acceptance scope; no product edits here): coordinator-owned — H1-context (real API signatures in-frame) is the evidence-backed next lever, with experiment calls still unspent should the coordinator release them |
| A3-partial (carried, narrowed) | medium (probabilistic constraint, measured 1/2) | §2 `patch_diff` emission | cand 0 re-emits unified+trailer despite the verified pin; strict fallback rejects (byte-identical replay) | Half of live emissions still die on patch format before any semantic judgment | Follow-up (coordinator-owned): SST landing of the validated tolerance diff, and/or stronger emission constraint |
| A2 (carried) | info (evidence gap, minor) | success-path gateway legs | `live-run-stderr.txt` holds only the final `Error:` line; no `header` handling exists in `cli_gateway.py`/`harness_worker.py` | Served header (reasoning/model confessor) unpreserved on success — medium corroborated triangulated instead of directly | Follow-up (optional): log the served header per gateway leg |
| F2 (carried) | info (cosmetic) | `dossier/review.md` | stamps `Contract: INT-2026-09-13.2`; run executed under follow-up tranche | Cosmetic drift | None here (template follow-up) |

No product defect in the acceptance owned surface beyond W1/A3-partial is
demonstrated: the loop failed closed exactly per contract on every leg, the
A1 mirror now performs live, and the pin demonstrably constrains (1/2).

## Verdict, reviewer only

AUTOMATION-NOT-READY + BLOCKED-WIRING (builder-reported outcome; B3 to rule)

- Criteria established: B1 READY gates (zero drift, pin live + SST strictness
  confirmed unlanded, dry-run chain with fresh diff ids, scripted suites
  24/24, pre-committed probabilistic expectation, explicit stall guardrails
  honored with zero intervention); B2 executed per contract (exact P05-final
  shape + pre-authorized `--choice 1`, full guards); gateway legs WON on
  medium twice (57.8 s + 52.4 s valid §2); A1 fix corroborated live a third
  time (both mirrors completed, no recursion, no stall, quarantine
  armed-but-empty); pin HELD 1/2 with the first clean emission live run to
  full 76.4 s real-gates judgment; BLOCKED-WIRING adjudicated live with
  exact-bytes anatomy reproduced on pristine custody (0 calls);
  pin-non-hold leg reproduced byte-identically (0 calls); honest
  no-champion partial preserved whole (STATUS, reason, refs, veto, budget,
  spend, review, prompt-payloads + stderr + status artifacts); escalation
  chain re-closed on fresh `TASK-P05_ACCEPTANCE-9f1632b8`; confinement held
  (tracked/full identical, sst clean, /tmp clean); P04 veto/fail-closed
  61/61 on both interpreters (0 calls); spend 2/8 CLI calls, $0.00, reserve
  untouched; zero product edits; zero unexplained drift.
- Unmet criteria or missing evidence: the binding success bar is NOT met — no
  champion, no FULL dossier (`merged.diff` / `execution_receipt.json` /
  `judiciary_verdict.json` absent by design). Root causes are the W1 wiring
  gap (product/capability boundary, now adjudicated live) and the
  probabilistic A3 remainder (1/2 emissions still marker-bearing), not the
  carried profile (4-for-4 on its legs) and not the mirror (fixed, proven
  live thrice). Live custody-apply-success was DEMONSTRATED this run
  (cand-1 fallback path); merge / execution / judiciary /
  mutmut-on-champion remain undemonstrated live.
- Baseline failures versus new regressions: zero regressions (no code changed;
  suites green: 61/61 both interpreters, 24/24 scripted). This run strictly
  advances the frontier over attempt-2 (2 proposals, both format-killed,
  wiring unadjudicated): 2 proposals, pin-held leg to full gates judgment,
  wiring adjudicated BLOCKED with exact evidence.
- Exact scope of independent execution/inspection: (for B3 to fill).
- Next action: acceptance B3 (fresh session) rules on this record per the
  follow-up brief; route W1 (wiring gap — H1-context lever) + A3-partial
  (SST landing and/or stronger constraint) + A2 (header gap) to coordinator
  follow-up scoping. No B4 repair exists within this packet (acceptance owns
  no product surface).

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings yet; W1/A3-partial/A2/F2 are follow-up items, not B4 repairs) | — | — | — | W1 wiring gap + A3 probabilistic remainder + A2 header gap ride to coordinator follow-up |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — this stage touched zero product files; tracked numstat is exactly the
# 2 pre-existing loose-set mods, both still matching the tasked hashes:
#  src/stc/cli.py 594/0 2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1
#  src/stc/orchestrator/dispatch.py 333/7 dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed)
536108e31a83fd88497802f236b774100d25be97b06cb558ed63b6a5e2fd5d50  evidence/FOLLOWUP/accept-3/readiness.md
37b5e0b7377857740604b94bace72f9b2a334e9a2d38d891a6cae6ba0abbc8ac  evidence/FOLLOWUP/accept-3/attempt-1/dossier/P05_ACCEPTANCE_INVARIANTS.md
f2da43908be9cdbe07e2e31d9de4e6a19655b4b8f0508d5ce03c8b8fa43c3172  evidence/FOLLOWUP/accept-3/attempt-1/dossier/STATUS
312e94e117cee9e9a4561705694f11c4f7ec65325ef3618d1e754187f544064d  evidence/FOLLOWUP/accept-3/attempt-1/dossier/branches.json
1682faa2fa9e33c14f0b03d63fca664d9f0c13c62fda2bbb85cd1f4fa6ceed90  evidence/FOLLOWUP/accept-3/attempt-1/dossier/qa_log.json
bb0eb3e0bdefda4c1442dfaa42c5ee02f2f25ac400138903251e187529311738  evidence/FOLLOWUP/accept-3/attempt-1/dossier/review.md
6a880ed8bfd799b1c2507ca3b1a3055268ecb61e9238829ab544b50c86d961d5  evidence/FOLLOWUP/accept-3/attempt-1/dossier/run_ref.json
977a18277227cb7651e5082bc45f96f8aa81ab74872a6f6383f11d72f17332ee  evidence/FOLLOWUP/accept-3/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9f1632b8/events.json
3677e254b6c1ed7aea3b2401dda0dd737a21fe27e30bf6d9ff614599b814c80a  evidence/FOLLOWUP/accept-3/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9f1632b8/inhibitors.json
ff5a31680aabc00134663c06344d7eba8044bffd0d1269e95e29f3b34df877b5  evidence/FOLLOWUP/accept-3/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9f1632b8/loss_ledger.json
e92e5616e9a1e40738c13bbafb27fc91a6c985895e33ef023542d84d6d0eb68c  evidence/FOLLOWUP/accept-3/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9f1632b8/result.json
f9ebfc979905688920cba6b25adbde736d380fdd4ed5ac08cbd4c5d3fd8887c1  evidence/FOLLOWUP/accept-3/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9f1632b8/store.db
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept-3/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9f1632b8/synthesis.json
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept-3/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9f1632b8/veto_log.json
49d2739c503f06f759468facbe25143feb1c547714f2ee3da9cef53031b6aea8  evidence/FOLLOWUP/accept-3/attempt-1/dossier/spend.json
6bffe014014944b36d303240d90d0096aa3d2e682d526ac95f4adeabbf146699  evidence/FOLLOWUP/accept-3/attempt-1/dossier/spend_ledger.jsonl
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept-3/attempt-1/dossier/veto_log.json
025d5f32ff982038a25a6fad9f477d1f76f752941075f6f26692df1d03719f89  evidence/FOLLOWUP/accept-3/attempt-1/live-run-argv.txt
7a3634dfc22e940d2fcd6f692307f12ac29d3d89341b181eece807327ef68655  evidence/FOLLOWUP/accept-3/attempt-1/live-run-env.txt
2cb755b69195efcc3a926144ec8a0bd3c247745330182193c92af8b58a0467fc  evidence/FOLLOWUP/accept-3/attempt-1/live-run-stderr.txt
e6d671d835c192ca2838a56652d86cfb3b8ce3e58123bb1c2c27a0c200433a94  evidence/FOLLOWUP/accept-3/attempt-1/live-run-stdout.txt
15dc55b6d04ff82d83a17efce82f6168ad4028b94522d1c6274c97f4001352f4  evidence/FOLLOWUP/accept-3/attempt-1/spend.jsonl
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/accept-3/attempt-1/sst-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/accept-3/attempt-1/sst-before.txt
c7f24296a7a48ceb546d11538922f6c757a5c50af8ed059b4e40ba80bf60c2c1  evidence/FOLLOWUP/accept-3/attempt-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/accept-3/attempt-1/status-after-tracked.txt
c7f24296a7a48ceb546d11538922f6c757a5c50af8ed059b4e40ba80bf60c2c1  evidence/FOLLOWUP/accept-3/attempt-1/status-before-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/accept-3/attempt-1/status-before-tracked.txt
f525c0fa3e0b2bf251d51cb99ff4f60274137a6bceefc0c43d8d0fa32cf0a291  evidence/FOLLOWUP/accept-3/attempt-1/veto-failclosed-joint.log
322417133428e465aeac446dfb2c07b0d78c360b0785bfca5ab4f5eabd70fa85  evidence/FOLLOWUP/accept-3/attempt-1/veto-failclosed-real.log
```

`git diff` tracked hunks belonging to this stage: NONE (no tracked file created
or modified; `git diff --numstat` shows only the 2 pre-existing loose-set mods).
