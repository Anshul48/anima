# FOLLOWUP accept — Builder delivery (attempt-1): honest partial, mirror-recursion stall

Record type: builder delivery
Author role and date: acceptance-builder / 2026-09-14
Packet: STC follow-up tranche, acceptance stage (P05 live shape on the carried
reasoning-medium profile; SAME approved spec, not re-approved).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (9 hashes re-verified byte-exact at B1, zero drift: `cli.py
2ddfd6cb…d82f1` 594/0, `test_winner_carry.py 0b5c3a8a…69762`, `harness_worker
ced79ed5…7867`, `cli_gateway f9dda17e…07b8a`, `test_harness e96db8d0…70b45`,
`dialectic_runner 19a2e448…8283b`, `test_dialectic 6e059f08…f1019`, `__init__
10571421…bac40`, `dispatch.py dc75c56e…13c7` 333/7).
Pins: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (clean before/after),
prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
`a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` (all exact at open and close).
Environment: real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15
(`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`;
shims verified present, no recreation) for the live leg + dry-run replays;
joint `<ws>/trace/.venv-linux/bin/python` 3.12.3 for the second veto rerun;
`PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`; codex-cli `0.154.0`.
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Delivery section

- Behavior/artifact changed and why: NOTHING changed in product code — this
  stage runs the approved pinning-test task through the real pipeline on the
  carried medium profile. B1 READY (see `evidence/FOLLOWUP/accept/readiness.md`).
  B2 executed the exact P05-final command shape + `--choice 1`: the gateway leg
  WON (valid §2 proposal in 43.1 s — the P2-H3a signature live in the pipeline),
  then the first verify stalled 40 min in an UNBOUNDED RECURSIVE MIRROR
  (`mirror_source_tree` copying the source tree into a lease directory that
  lives INSIDE the source tree: `STC_DOSSIER_DIR` under `ws/stc`). After
  diagnosis proved the stall unrecoverable by the product (finding A1), the
  runaway copy was broken externally (full intervention log below — nothing
  hidden); the pipeline then failed closed exactly per contract: quarantine +
  `VERIFIER_FINISHED` fail + `BUDGET_EXHAUSTED` + honest NEEDS_REPAIR partial,
  preserved whole. Per the binding success bar this is AUTOMATION-NOT-READY —
  valid evidence, NOT success. No mid-acceptance reshaping (no prompt, profile,
  budget, or code change); no H1-context experiments (coordinator decision).
- Files or outputs changed: evidence ONLY, all under `evidence/FOLLOWUP/accept/`
  (`readiness.md`, `attempt-1/` with `dossier/`, live-run captures, status
  guards, `quarantine-manifest.txt`, `spend.jsonl`, veto rerun logs, this
  REVIEW). No STATE.md write; no commits; no tracked-file modification.
- Material implementation decisions: none (no implementation in scope). The
  external stall-breaking (deletion + permission lock inside the runaway lease
  dir ONLY) was the minimal act that could stop unbounded disk growth after the
  runtime kill channel failed three times; it is logged step-by-step under
  Diagnosis so B3 can separate product behavior from intervention effects.
- Known limitations and checks not run: the proposal never reached apply/gates
  judgment (stall first), so module-path wiring was NEVER adjudicated live —
  this is NOT a BLOCKED-WIRING verdict (see Diagnosis); worker-stage harnesses
  still never reached live (0 worker calls); the served gateway header is not
  preserved on success paths (finding A2 — medium corroborated triangulated);
  full `pytest tests/` beyond the P04 suite not run (precedent scope).

## Evidence

| Criterion | Command or evaluation method | Observed result | Evidence path | Scope/limitations |
| --- | --- | --- | --- | --- |
| Predecessor gates (B1) | full reads | live-exp WIN P2-H3a + caveat; winner-carry PASS; F1 PASS (sidecar active); P05-fix shape + honest-partial precedent; FIX-B5 NOT-READY baseline; packet §Fix tranche; SAME spec | readiness.md Gate 0 | Read, not re-executed |
| Drift gate (B1) | rev-parse, 9 full-sha recomputes, numstat, 3 pins, sst status | HEAD `edf5389`; 9/9 exact; 594/0 + 333/7; pins exact; sst clean — zero drift | readiness.md Gate 1 | Hash-bound |
| Dry-run replay (B1, 0 calls) | bare + `--choice 1` dry-runs, real-gates, scratch dossiers (removed after) | bare exit 2, 0.80 + STOP, fresh `…5a6df225`; choice exit 0, single pins target, RT-08, choice-recorded, invariants file, fresh `…d326fcfa` | readiness.md Gate 2 (values quoted) | Zero model calls |
| Seeded-medium sanity (B1, 0 calls) | `_seed_codex_home()` on the REAL operator login + winner-test rerun | seeded config carries `medium` (operator `max` rewritten); operator bytes bit-identical before/after; winner tests 6/6 real-gates; dry-run path itself never seeds (0 calls by construction) | readiness.md Gate 3 | Direct proof + P2 header precedent |
| B2 live run (exact P05-final shape) | `python -m stc run docs/builds/stc-integration/specs/p05-acceptance.md --target stc --budget time=600,tokens=500000,usd=10,iters=2,branching=1,depth=4 --choice 1`, real-gates, `STC_DOSSIER_DIR=…/attempt-1/dossier` | exit-1 class NEEDS_REPAIR, `budget-exhausted` (2335.6 s ≥ 600 s), 1 gateway call/1 ok/0 worker, 0 refs scored; wall 15:19:01→16:01Z; CLI RC inferred 1 (`Error:` ClickException prefix) | `attempt-1/live-run-argv.txt`, `live-run-env.txt`, `live-run-stdout.txt`, `live-run-stderr.txt`, `dossier/` | 1 live call; stall + intervention (see Diagnosis) |
| Gateway leg WON on medium | dossier spend row + store NODE_PROPOSED payload | 43.123 s, exit 0, 4368 out_bytes, VALID §2 `CandidateProposal` (DIVERGE `Custody-Double Defensive Pin Matrix`, 3685 B patch, pins-module target) — P2-H3a signature live; same shaped bytes hang served at max (P1-H0b + B2/retry history) | `dossier/spend.json`, `dossier/spend_ledger.jsonl`, `runs/*/store.db` seq 2 | n=1 live (P2 replicate n=1) |
| Stall root cause (A1) | lease forensics during stall (read-only) + pipeline's own quarantine artifact | `mirror_source_tree` dst-inside-src infinite recursion: lease at `…/dossier/runs/…/leases/_0_0` inside source root `ws/stc`; nesting depth 7, 1,232,091,654 B and growing ~20 MB/min at 15:53; lease top-level only ~17 entries (`src/`, `tests/` never reached); 31 min with zero store/ledger writes | this REVIEW (Diagnosis + intervention log); `runs/*/leases/_quarantine/` + `quarantine-manifest.txt` (404 files, 1.28 MB residue) | Proven pre-intervention; post-intervention residue is partial |
| Fail-closed close | events/store/dossier reads; `ls` absence checks | `VERIFIER_FINISHED` fail (substrate error, 7-deep nested path in message) → `BUDGET_EXHAUSTED` → STATUS NEEDS_REPAIR + reason + 1 branch ref + empty veto/scores + spend + review stating absence-by-design; `merged.diff` / `execution_receipt.json` / `judiciary_verdict.json` ABSENT (ls-confirmed); quarantine dir + 2000-char reason file written by the pipeline's own catch-all (`dialectic_runner.py:487-497`) | `runs/*/events.json` (5 events), `store.db` seq 1–5, `dossier/STATUS`, `branches.json`, `result.json`, `spend.json`, `review.md`, `leases/_quarantine/` | Honest partial, never padded |
| Escalation chain re-closed | qa_log + invariants + TREE_CREATED | 0.80/triggered → choice-recorded [1] → `P05_ACCEPTANCE_INVARIANTS.md` → TREE_CREATED (fresh `TASK-P05_ACCEPTANCE-9a89f20e`, distinct from all replay ids) → allowed_paths exactly the pins module, base `edf5389` | `dossier/qa_log.json`, `dossier/P05_ACCEPTANCE_INVARIANTS.md`, `runs/*/events.json` | Injection-free (relayed pre-authorized choice) |
| Elapsed accumulation live | budget_state vs wall | reported `elapsed_seconds` 2335.637 ≈ runner-wall of the stalled verify (P04-fix `max()` path on the real loop) | `dossier/branches.json`, `runs/*/result.json` | No-champion shape |
| Confinement held | pre/post tracked+full status, sst status, /tmp leftover check | tracked IDENTICAL (`d1edad82…` = FIX-B5 value, before == after); full status byte-identical; numstat still 594/0 + 333/7; sst clean before/after; zero `/tmp` codex-home/gateway leftovers (caller-deletes + per-call cleanup); B1 scratch removed | `status-before/after-*.txt`, `sst-before/after.txt` | Real tree untouched; all writes under untracked `FOLLOWUP/` |
| F1 sidecar correct | dossier listing | NO `spend-ledger.failures.jsonl` — correct: gateway leg ok; the substrate error is not a harness failure (F1 scope is harness stderr) | `dossier/` listing | F1 working as VERIFIED |
| Veto/fail-closed (unexercised live → rerun) | `pytest tests/unit/test_integration_dialectic.py -m "not live"`, BOTH interpreters | 58 passed on EACH (13.54 s real-gates, 12.96 s joint); live veto_log `[]` (nothing to exercise veto with — 1 failed verify) | `veto-failclosed-real.log`, `veto-failclosed-joint.log` | 0 live calls; scripted |
| Proposal wiring (NOT adjudicated) | full NODE_PROPOSED payload read | `*** Begin Patch` (3685 B, no `@@`) importing `praxist.dialectic.*` (guessed path — the live-exp caveat class) — but the run never reached apply judgment, so wiring was never tested live; would-have-failed analysis only (see Diagnosis) | `store.db` seq 2 payload (quoted in session) | No BLOCKED-WIRING verdict (stall pre-empted it) |
| Spend | `spend.jsonl` 1-row audit vs ledger | **1 CLI call / 11** this stage (tranche 4/14; 6-call reserve NEVER touched); $0.00 metered; zero installs | `attempt-1/spend.jsonl` (1 row) | CLI-session budget only |
| Scope/hygiene | pins at close, HEAD/log, STATE.md, stray sweep | HEAD still `edf5389`; no new commits; STATE.md untouched; all 3 pins exact; `trace-lite/` never listed, read, or written | git output (this session) | Tree left + this record |

## Diagnosis (what the evidence establishes)

- **A1 ROOT CAUSE (product defect, proven): unbounded recursive self-copy in
  `mirror_source_tree` (`dialectic_runner.py:283-295`).** The verify lease is
  created at `<STC_DOSSIER_DIR>/runs/<run>/leases/<lease>` while the mirrored
  source root is `ws/stc` — and this run's `STC_DOSSIER_DIR` is inside `ws/stc`
  (the packet's evidence layout). `mirror_source_tree` walks `src.iterdir()`
  lazily with no exclusion for the destination, so once the copy reaches the
  `docs/…/dossier/runs/…/leases/_0_0` subtree it copies the lease into itself,
  level after level: observed nesting depth **7**, size **1,232,091,654 B**
  still growing ~20 MB/min at 15:53Z, lease top level holding only ~17 entries
  (`src/`, `tests/` never reached), zero store/ledger writes for 31+ min. The
  product has no self-recovery from this state: no timeout bounds the mirror
  (the 120 s gate timeouts sit downstream in `execute_gates`, never reached),
  and the only natural endings are ENAMETOOLONG or disk-full — both
  destructive. E2E/fixture suites never caught it because their leases live
  outside their fixture source trees. Fix direction (coordinator-owned, NOT
  attempted here): exclude the lease/dossier path from the mirror (or mirror
  from git objects / place leases outside the source root).
- **Intervention log (exact, for B3 separation).** At ~15:53Z, with A1 proven
  and disk growth unbounded: (1) runtime process-terminate requested 3× — each
  timed out (`Work Stop compatibility request timed out`); host-namespace kill
  unavailable (unsandboxed execution needs human approval; approvals disabled).
  (2) `mv` of the lease dir → Permission denied (busy tree on the 9P mount).
  (3) `rm -rf` of the depth-7 frontier → copier survived (copytree re-makedirs).
  (4) `rm -rf` of the whole 1.2 GB lease → bulk deleted, copier recreating the
  skeleton. (5) `chmod a-w` on the lease root + content strip → the mirror
  raised `shutil.Error` → the pipeline's own catch-all quarantined the lease
  with a reason file and closed honestly (16:01:04Z). My deletions are the
  PROXIMATE trigger of the `VERIFIER_FINISHED` substrate error; the RECURSION
  is the product's own doing (proven pre-intervention). Nothing else was
  touched: no source file, no store edit, no second intervention.
- **Fail-closed machinery validated live.** The `except Exception` catch-all
  (`dialectic_runner.py:487-488`) quarantined with a 2000-char reason whose
  nested path (lease path ×7 + `.git/objects/…`) independently proves A1; the
  controller recorded `VERIFIER_FINISHED(passed=false)` then
  `BUDGET_EXHAUSTED` (`2335.6s >= 600s`, TRUE — wall 15:19:01→16:01Z); the CLI
  rendered the honest partial (STATUS + reason + 1 branch ref + empty
  veto/scores + spend + review, zero success artifacts). No traceback escaped.
- **The carried medium profile WON its leg.** 43.1 s valid §2 emission on the
  exact shaped bytes that hang served at reasoning-max is the P2-H3a signature
  reproduced inside the real pipeline (seeded-config route — the only gateway
  route per winner-carry audit — proven max→medium on this operator login at
  B1 Gate 3). The stall is downstream of and unrelated to the profile.
- **Wiring was never adjudicated — no BLOCKED-WIRING verdict.** The proposal's
  `*** Begin Patch` (non-unified-diff) format + `praxist.dialectic.*` imports
  are the live-exp caveat class, but verify never reached apply: would-have
  analysis only (no-`@@` → SST direct-file-replacement → garbage content →
  ruff/pytest fail). H1-context experiments remain unspent per the brief.
- **Pre-existing red/green notes.** F2 template stamp drift (`INT-2026-09-13.2`
  in `review.md`) persists — cosmetic, carried. R1 stays deferred (no blocking
  evidence). `test_cli.py` baseline untouched (not re-run, out of scope).

## Independent findings

| ID | Severity | Location | Evidence/reproduction | Impact | Required correction |
| --- | --- | --- | --- | --- | --- |
| A1 | critical (product defect, hang + unbounded disk growth) | `src/stc/integration/dialectic_runner.py:283-295` (`mirror_source_tree`) + lease placement under `STC_DOSSIER_DIR` inside the source root | depth-7 nesting, 1.232 GB @15:53Z growing ~20 MB/min, 31 min zero-event stall, pipeline's own quarantine reason with 7-deep nested path; e2e suites blind (leases outside fixture sources) | EVERY real live verify with an in-repo dossier hangs; disk fills until ENAMETOOLONG/disk-full | Follow-up (out of acceptance scope; no product edits here): exclude lease/dossier path from mirror, or mirror from git, or leases outside source root |
| A2 | info (evidence gap, minor) | success-path gateway legs | `live-run-stderr.txt` holds only the final `Error:` line; no `header` handling exists in `cli_gateway.py`/`harness_worker.py`; run's seeded CODEX_HOME correctly deleted | Served header (reasoning/model confessor) unpreserved on success — medium corroborated triangulated (behavior + B1 seed proof + winner-carry tests) instead of directly | Follow-up (optional): log the served header per gateway leg |
| F2 (carried) | info (cosmetic) | `dossier/review.md` | stamps `Contract: INT-2026-09-13.2`; run executed under follow-up tranche | Cosmetic drift | None here (template follow-up) |

No product defect in the acceptance owned surface beyond A1 is demonstrated:
the loop failed closed exactly per contract once the stall broke.

## Verdict, reviewer only

AUTOMATION-NOT-READY (builder-reported outcome; B3 to rule)

- Criteria established: B1 READY gates (zero drift, dry-run chain with fresh
  diff ids, seeded-medium proven on the real login, winner 6/6); B2 executed
  per contract (exact P05-final shape + pre-authorized `--choice 1`, full
  guards); gateway leg WON on medium (43.1 s valid §2 — first live proposal
  through the carried profile); honest no-champion partial preserved whole
  (STATUS, reason, refs, veto, budget, spend, review, prompt-payload + stderr
  + status artifacts, quarantine exhibit); escalation chain re-closed on fresh
  `TASK-P05_ACCEPTANCE-9a89f20e`; confinement held (tracked/full identical,
  sst clean, /tmp clean); P04 veto/fail-closed 58/58 on both interpreters (0
  calls); spend 1/11 CLI calls, $0.00, reserve untouched; zero product edits;
  zero unexplained drift.
- Unmet criteria or missing evidence: the binding success bar is NOT met — no
  champion, no FULL dossier (`merged.diff` / `execution_receipt.json` /
  `judiciary_verdict.json` absent by design). Root cause is the A1 mirror
  recursion (product defect), not the carried profile (which won its leg) and
  not proposal wiring (never adjudicated). Live custody-apply / gates / merge /
  execution / judiciary / mutmut remain undemonstrated live.
- Baseline failures versus new regressions: zero regressions (no code changed;
  suites green). The B2 failure is a product defect in first-live-reach code
  (no verify had ever run live before — M1/P05-fix both died at diverge), plus
  the documented external stall-breaking, which is fully separated above.
- Exact scope of independent execution/inspection: (for B3 to fill).
- Next action: acceptance B3 (fresh session) rules on this record per the
  follow-up brief; route A1 (mirror dst-inside-src recursion) + A2 (header gap)
  + the unadjudicated wiring caveat to coordinator follow-up scoping. No B4
  repair exists within this packet (acceptance owns no product surface).

## Repair dispositions, if applicable

| Finding | Cause | Fix or justified disposition | New evidence | Remaining issue |
| --- | --- | --- | --- | --- |
| (none — no B3 findings yet; A1/A2/F2 are follow-up items, not B4 repairs) | — | — | — | A1 mirror recursion + A2 header gap + wiring caveat ride to coordinator follow-up |

## Identity (sha256 of every file created or modified)

```text
# MODIFIED (owned)
# (none — this stage touched zero product files; tracked numstat is exactly the
# 2 pre-existing loose-set mods, both still matching the tasked hashes:
#  src/stc/cli.py 594/0 2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1
#  src/stc/orchestrator/dispatch.py 333/7 dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7)
# CREATED (evidence; this REVIEW.md is the record itself and is not self-listed;
# the 404 pipeline-quarantined mirror-copies are manifested in
# quarantine-manifest.txt (1.28 MB residue; nested readiness.md == live readiness.md
# byte-exact 93372d97… — mirror copies faithful))
93372d97c0afed1b8e808a739a6b8ad17f3d4763721b2cb428e9c878732ba93c  evidence/FOLLOWUP/accept/readiness.md
363973a78142a5707c68cc55fe36285b5b1af47d498c3f27c1abfa78af37c48f  evidence/FOLLOWUP/accept/attempt-1/dossier/P05_ACCEPTANCE_INVARIANTS.md
f2da43908be9cdbe07e2e31d9de4e6a19655b4b8f0508d5ce03c8b8fa43c3172  evidence/FOLLOWUP/accept/attempt-1/dossier/STATUS
a359f6abeaf7a934dc45282949b55f15fe81de8e51a1d15b235aa50e0683aad4  evidence/FOLLOWUP/accept/attempt-1/dossier/branches.json
c27c6c1be20488ed8bdf09c9cc85ea694caa4dea1221171d1ae5ddb610321628  evidence/FOLLOWUP/accept/attempt-1/dossier/qa_log.json
e7ddd0767b4f67eb889d9eda9d1a6aca9d029761dcf22fecbbb6ba51798e2eb2  evidence/FOLLOWUP/accept/attempt-1/dossier/review.md
c8c78345bb14e7413672de32957e813a69aff0088b0041e685e03b0f2c1ad1b3  evidence/FOLLOWUP/accept/attempt-1/dossier/run_ref.json
e997b3b7b4eff3171252298eb669685edca0cce50367794c07ab7a9bbe6943f1  evidence/FOLLOWUP/accept/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9a89f20e/events.json
3677e254b6c1ed7aea3b2401dda0dd737a21fe27e30bf6d9ff614599b814c80a  evidence/FOLLOWUP/accept/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9a89f20e/inhibitors.json
2b7cf9bdf06b705203ff0fc187cca2695fe2af5f9ddb4a5f2eeccb7eed8db6be  evidence/FOLLOWUP/accept/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9a89f20e/loss_ledger.json
225a8f92815f99c92cafbaf5c0d6a070b3627917bdafafc21265dd45e3680481  evidence/FOLLOWUP/accept/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9a89f20e/result.json
37190db8a367ce12e47cf3b7f28a21fe6c17afe77a0d28ed670765854634be95  evidence/FOLLOWUP/accept/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9a89f20e/store.db
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9a89f20e/synthesis.json
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept/attempt-1/dossier/runs/TASK-P05_ACCEPTANCE-9a89f20e/veto_log.json
b596ba412767481bf90dda8419d076c1c4d434fa8fe7ebf0cac84fc54df69f62  evidence/FOLLOWUP/accept/attempt-1/dossier/spend.json
7e30e0f0ef7aaae4247def00387b9f262b933e8e08f6a57a48141826c2cfaa4d  evidence/FOLLOWUP/accept/attempt-1/dossier/spend_ledger.jsonl
4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945  evidence/FOLLOWUP/accept/attempt-1/dossier/veto_log.json
a4b98c4080521bfabd8fd0be97ad790dfeafc50c375e4ae37598a6a4c28ee55f  evidence/FOLLOWUP/accept/attempt-1/live-run-argv.txt
1111ab897702dd87bd0bfd1c81c9410fdadbf0d48de4d3262d270cc8c5808c55  evidence/FOLLOWUP/accept/attempt-1/live-run-env.txt
f558f3a5db588b1b3116be99ffc5ab791b424b80e33cbb1eb0e8dd3aa01fcdbe  evidence/FOLLOWUP/accept/attempt-1/live-run-stderr.txt
f85d2cc84b6fb911e9fa667f8d2915466fb93b0f5163171342ffdcd39ca5c368  evidence/FOLLOWUP/accept/attempt-1/live-run-stdout.txt
22346c0e946377125320f3bb0d969ee5ff58348ec0b23ce8aa25ad7184fcf205  evidence/FOLLOWUP/accept/attempt-1/quarantine-manifest.txt
515b23877097a22117e86f35d7a25a3656f7b31e7591e4337e3af4c344012015  evidence/FOLLOWUP/accept/attempt-1/spend.jsonl
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/accept/attempt-1/sst-after.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  evidence/FOLLOWUP/accept/attempt-1/sst-before.txt
c66f62832b6b5c03e6feb3cfa69f88d81a3171999ad773e66159eb49424ab7df  evidence/FOLLOWUP/accept/attempt-1/status-after-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/accept/attempt-1/status-after-tracked.txt
c66f62832b6b5c03e6feb3cfa69f88d81a3171999ad773e66159eb49424ab7df  evidence/FOLLOWUP/accept/attempt-1/status-before-full.txt
d1edad825762ba7eeb6de88d6dfe84571808c44d4f1fcde155384009ab3e37e3  evidence/FOLLOWUP/accept/attempt-1/status-before-tracked.txt
88959fb24f707ec8d54d2a2b23d8775f927c77ddf1262f0d1d8db5731881ca6c  evidence/FOLLOWUP/accept/attempt-1/veto-failclosed-joint.log
c6849b5b61fe1e8717797e6849f30fb46924f0f09d8801d70d86190c59912d3c  evidence/FOLLOWUP/accept/attempt-1/veto-failclosed-real.log
```

`git diff` tracked hunks belonging to this stage: NONE (no tracked file created
or modified; `git diff --numstat` shows only the 2 pre-existing loose-set mods).
```

## Coordinator-reply appendix (answers to the 15:47Z check)

1. Was the worker/verifier tree alive and progressing? YES alive, NO
   progressing — stuck 15:21→16:01Z inside `mirror_source_tree` (unbounded
   recursive self-copy, NOT gates/mutmut/agentic loop: gates are 120 s-bounded
   each and were never reached; mutmut is forced OFF per node; no second CLI
   call ever started). Heartbeats: lease `.git/index` write 15:39Z, nesting
   depth 7 / 1.232 GB @15:53Z growing ~20 MB/min.
2. Stall deadline / action: deadline was the A1 proof (15:53Z); action was
   diagnose-and-break-externally (kill channel failed 3×; `mv` denied; `rm`
   raced; `chmod a-w` + strip broke the copy) → pipeline fail-closed honestly
   at 16:01Z. NOT-READY-with-diagnosis close delivered; 11-call cap respected
   (1 spent; no H1 experiments).
