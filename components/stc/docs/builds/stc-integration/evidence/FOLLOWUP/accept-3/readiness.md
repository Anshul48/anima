# FOLLOWUP accept-3 — Readiness (B1)

Record type: builder readiness
Author role and date: acceptance3-builder / 2026-09-14
Packet: STC follow-up tranche, acceptance attempt-3 (re-run the approved
pinning-test task through the real pipeline on the A3-fixed tree: frame
pin LIVE, SST tolerance NOT landed — sst stays read-only; SAME approved
spec, not re-approved).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (10 hashes re-verified byte-exact below, zero drift; A3 frame-pin
`cli_gateway aedffa12…bb392` + `test_a3_patch_format f99b2785…b1f2b`).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Gate 0 — Predecessor gates (full read, nothing inherited)

| Record | Outcome carried |
| --- | --- |
| `evidence/FOLLOWUP/accept-2/attempt-1/REVIEW.md` | **Attempt-2 anatomy**: A1 holds live (no stall, no recursion, quarantine armed-but-empty); medium legs WON twice (45.5 s + 42.0 s valid §2); A3 format killed BOTH (cand-0 unified+trailer → apply fail; cand-1 Begin Patch → verbatim garbage → all gates red). Wiring STILL unadjudicated (second time). Fail-closed NEEDS_REPAIR partial. A3/A2/F2 to follow-up. |
| `evidence/FOLLOWUP/a3-fix/verify-1/REVIEW.md` | **PASS (predecessor)**: frame pin verified (4 lines :103-106, single choke point, SST bytes verbatim; 12/12 own-probe + 18/18 new + 76/76 affected, both interpreters); SST tolerance diff VALIDATED-but-UNLANDED (34/34 dossier-sourced replay both interpreters; sst byte-unchanged). SST landing awaits an SST-authorized stage — NOT this run. |
| `evidence/FOLLOWUP/live-exp/attempt-1/REVIEW.md` | **WIN P2-H3a** + wiring caveat: guessed module paths may fail verify — **adjudicate live if format now passes** (attempt-2 never reached import resolution). |
| `evidence/FIX-B5/REVIEW.md` | **NOT-READY baseline** to beat: honest no-champion partial (now superseded by attempt-1/2 live proposals, but FULL dossier still undemonstrated). |
| `packets/P05-cli-acceptance.md` §Fix tranche | Acceptance deltas: prompt + stderr + header + before/after status preserved; dossier complete per outcome; chain re-closed; no out-of-loop writes; e2e green. |
| `specs/p05-acceptance.md` | SAME approved spec (F-B3-3/F-B3-4 pins task). `--choice 1` reuse pre-authorized. |

## Gate 1 — Drift gate (re-verified this session, STOP on unexplained drift)

- HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` = tasked base. ✓
- 10/10 file hashes byte-exact at tasked values: `cli_gateway
  aedffa1277ea9d4fee009531430bfbcff9fb9a8975837af7372654c9e46bb392`
  (A3 frame pin), `test_a3_patch_format
  f99b278588e0c7eec956a6203e5475c78f95c3d4e76f2946c892a13a125b1f2b`,
  `dialectic_runner
  c072f1dac2725f470bfeb9753288e2158064838467784d3f8ceb279b640a0ff5`
  (A1-fixed), `test_dialectic
  eea1a7eea04eebbe21680836e4823e01bb2bfa62729f4bcd41bcb219f52a0ec0`,
  `cli.py 2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1`
  (numstat 594/0), `test_winner_carry.py
  0b5c3a8a85dea963ef8b95e43679bc504020152d105e89a2aaef05b677b69762`,
  `harness_worker ced79ed572d50f5c67d7e8556fe08127f59e0c529fc50bdaf1bc6898805a7867`,
  `test_integration_harness_worker.py
  e96db8d00a2950166f77ec6069ab98d9a944a344bfb452a4ffb7e6f3ce070b45`,
  `__init__ 105714219afcfbef9c81c50ce4216de4ce93096482aff2a4597cb4aaf04bac40`,
  `dispatch.py dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7`
  (numstat 333/7). ✓
- Pins exact: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (status empty),
  prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`,
  trace `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`. ✓
- SST tolerance NOT landed (confirmed this session): `Begin Patch` grep over
  `sst/src/sst/sandbox/custody.py` rc=1 (no marker handling); strict fallback
  `Unrecognized diff line format` intact at :484; custody bytes
  `43c24681…ec864` = the verify-1 pinned value; sst status empty. ✓
- Frame pin live (confirmed this session): 4-line pin at
  `cli_gateway.py:103-106` + docstring note :85-86, read in full. ✓
- **Zero drift. No STOP.**

## Gate 2 — Dry-run replay (real-gates, scratch dossiers, 0 calls)

- Bare: exit 2, `Ambiguity 0.80 >= 0.30`, dilemma + STOP, qa
  escalation-required, diff `diff_p05_acceptance_cc907857` (fresh). ✓
- `--choice 1`: exit 0, single pins-module target
  `tests/unit/test_integration_runner_pins.py`, `Audit: with_codex=False
  (RT-08)`, qa `status=choice-recorded` + `selected_choices=[1]` +
  `note=choice recorded via --choice/--yes`, `P05_ACCEPTANCE_INVARIANTS.md`
  with fail-closed invariant, diff `diff_p05_acceptance_59e18ed6` (fresh,
  distinct from all prior ids). Source root `@ edf5389…`. ✓
- Scratch dossiers removed after. One first-run write to the default
  `./dossier/` (empty dir, untracked) was deleted in-session; tree restored
  (`?? dossier/` absent again). Chain intact on the A3-fixed candidate.
- Scripted suites (0 calls): `test_winner_carry.py` + `test_a3_patch_format.py`
  **24 passed** (6 + 18) on real-gates in 3.26 s. ✓

## Frame-pin live expectation (stated upfront)

- The pin constrains emission PROBABILISTICALLY: it instructs pure-unified-diff
  `proposed_changes` and names the forbidden `***` markers, but the model may
  still emit markers (attempt-2 proved the §2 contract parses while its content
  convention is not followed). A marker-bearing proposal this run is a pin
  non-hold on that leg, not a defect in the pin's installation (verified).
- The SST fallback is still STRICT (tolerance unlanded): any `***`-marker
  payload fails exactly as in attempt-2 (apply-stage `corrupt patch` /
  `Unrecognized diff line format`, or verbatim-garbage → all gates red).
  Markers still fail — there is no custody safety net this run.
- Live adjudication order per brief: (1) did the pin hold (marker-free unified
  diffs?); (2) if yes and gates run: wiring verdict (imports resolve? tests
  pass?) — a wiring failure IS a BLOCKED-WIRING verdict with exact evidence
  (no H1-context improvisation — coordinator decision); (3) if champion: full
  close per contract. No-champion = honest NEEDS_REPAIR partial with exact
  anatomy.

## Stall guardrails (EXPLICIT — attempt-1 must not repeat)

- During the B2 verify leg(s), watch from OUTSIDE the run tree (read-only
  probes only): lease dir byte size (`du -sb`) and store/event cadence
  (`store.db` mtime + row count, `events.json` mtime).
- **Alert thresholds: lease >500 MB OR >10 min zero-event** (no new store
  rows AND no events.json write AND no spend-ledger append).
- **NO external intervention inside the run tree** — no `rm`, `chmod`, `mv`,
  or any write into the dossier/run/lease dirs while the run is alive.
  Attempt-2 owes the intervention-free precedent; this run keeps it.
- If a stall recurs (thresholds tripped + A1-shape confirmed read-only):
  kill the run **via the runtime channel only** (process terminate), then
  preserve the partial exactly as left (no cleanup of the runaway growth
  beyond what the runtime kill itself does). Report the stall with the
  read-only forensics; the partial stands as intervention-free evidence.
- Normal-progress expectations (non-alerting): gateway leg ~1 min (P2 56.7 s
  / attempt-1 43.1 s / attempt-2 45.5 s + 42.0 s precedent); each verify mirror
  bounded (whole-tree copy minus ~dossier, single pass — seconds, not
  minutes); 120 s gate timeouts bound `execute_gates`; mutmut forced OFF per
  node.

## Live leg plan (B2)

- Exact P05-final command shape (cwd `ws/stc`, real-gates env):
  `python -m stc run docs/builds/stc-integration/specs/p05-acceptance.md
  --target stc --budget time=600,tokens=500000,usd=10,iters=2,branching=1,depth=4
  --choice 1`
  with `STC_DOSSIER_DIR=evidence/FOLLOWUP/accept-3/attempt-1/dossier`.
- Real-gates env: `<ws>/learn-anything/.venv/bin/python` 3.11.15,
  `PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`,
  `PYTHONDONTWRITEBYTECODE=1`. All three /tmp shims verified present (no
  recreation). codex-cli `0.154.0` confirmed on PATH. Operator login present
  (config carries `model_reasoning_effort = "max"`; seeded home rewrites to
  medium per the winner-carry route).
- Captures per P05 precedent: pre/post tracked+full status, sst before/after,
  live-run argv/env/stdout/stderr, dossier whole, `spend.jsonl` (every call).
- Budget: B1 spent **0** CLI calls. B2 may spend **≤8** (6 spent + 8 = 14
  tranche-spent; the 6-call verification reserve is NEVER touched). No
  H1-context experiments regardless of outcome (coordinator decision).
- Dispositions: FULL dossier (proposal → champion → merged diff → receipt →
  verdict → real gates) = success; no-champion = honest NEEDS_REPAIR partial,
  AUTOMATION-NOT-READY with exact failure anatomy; verify-fail specifically on
  module-path wiring (live-exp caveat, adjudicated live if reached) =
  BLOCKED-WIRING with exact evidence.
- Veto/fail-closed: if the live run does not exercise veto/fail-closed paths,
  rerun the existing P04 veto/fail-closed suites (0 live calls) and cite.
- R1 stays deferred unless evidence shows it blocks. No product edits (evidence
  only). No commits, no STATE.md writes.

## Verdict

**READY** — all gates green, zero drift, frame pin confirmed live with SST
strictness confirmed unlanded, dry-run chain with fresh diff ids, scripted
suites 24/24, stall guardrails explicit with intervention-free discipline.
Proceeding to B2.
