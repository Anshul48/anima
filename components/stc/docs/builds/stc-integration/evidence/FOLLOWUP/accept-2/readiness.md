# FOLLOWUP accept-2 — Readiness (B1)

Record type: builder readiness
Author role and date: acceptance2-builder / 2026-09-14
Packet: STC follow-up tranche, acceptance attempt-2 (re-run the approved
pinning-test task through the real pipeline on the A1-fixed tree; SAME
approved spec, not re-approved).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (9 hashes re-verified byte-exact below, zero drift; A1-fixed pair
`dialectic_runner c072f1da…0ff5` + `test_dialectic eea1a7ee…0ec0`).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Gate 0 — Predecessor gates (full read, nothing inherited)

| Record | Outcome carried |
| --- | --- |
| `evidence/FOLLOWUP/accept/attempt-1/REVIEW.md` | **Attempt-1 anatomy**: gateway leg WON on medium (43.1 s valid §2); first verify stalled 40 min in unbounded recursive mirror (A1, proven); external stall-breaking fully logged; fail-closed NEEDS_REPAIR partial preserved. Wiring NEVER adjudicated live (no BLOCKED-WIRING verdict). A2 header gap carried. |
| `evidence/FOLLOWUP/a1-fix/verify-1/REVIEW.md` | **PASS (predecessor)**: dst-exclusion + loud-refusal bound at the single `mirror_source_tree` fix point; 3/3 new + 61/61 unit + fixture green both interpreters; own 13/13 different-layout discrimination; P04 lines byte-identical at +22; A2-deferral agreed. |
| `evidence/FOLLOWUP/live-exp/attempt-1/REVIEW.md` | **WIN P2-H3a** + wiring caveat: guessed module paths may fail verify — **adjudicate live this time if reached** (attempt-1 never reached apply judgment). |
| `evidence/FOLLOWUP/winner-carry/verify-1/REVIEW.md` | **PASS**: seeded-config medium route (the live route); 6/6 + 9/9 discrimination. |
| `evidence/FIX-B5/REVIEW.md` | **NOT-READY baseline** to beat: honest no-champion partial, 0 live proposals ever (now superseded by attempt-1's 1 live proposal, but FULL dossier still undemonstrated). |
| `packets/P05-cli-acceptance.md` §Fix tranche | Acceptance deltas: prompt + stderr + header + before/after status preserved; dossier complete per outcome; chain re-closed; no out-of-loop writes; e2e green. |
| `specs/p05-acceptance.md` | SAME approved spec (F-B3-3/F-B3-4 pins task). `--choice 1` reuse pre-authorized. |

## Gate 1 — Drift gate (re-verified this session, STOP on unexplained drift)

- HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` = tasked base. ✓
- 9/9 file hashes byte-exact at tasked values: `dialectic_runner
  c072f1dac2725f470bfeb9753288e2158064838467784d3f8ceb279b640a0ff5`
  (A1-fixed), `test_dialectic
  eea1a7eea04eebbe21680836e4823e01bb2bfa62729f4bcd41bcb219f52a0ec0`,
  `cli.py 2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1`
  (numstat 594/0), `test_winner_carry.py
  0b5c3a8a85dea963ef8b95e43679bc504020152d105e89a2aaef05b677b69762`,
  `harness_worker ced79ed572d50f5c67d7e8556fe08127f59e0c529fc50bdaf1bc6898805a7867`,
  `cli_gateway f9dda17ec411c567dfccc51515cedfa69d79b75a6effd2c6e75c72ec76207b8a`,
  `test_integration_harness_worker.py
  e96db8d00a2950166f77ec6069ab98d9a944a344bfb452a4ffb7e6f3ce070b45`,
  `__init__ 105714219afcfbef9c81c50ce4216de4ce93096482aff2a4597cb4aaf04bac40`,
  `dispatch.py dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7`
  (numstat 333/7). ✓
- Pins exact: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (status empty),
  prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`,
  trace `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`. ✓
- **Zero drift. No STOP.**

## Gate 2 — Dry-run replay (real-gates, scratch dossiers, 0 calls)

- Bare: exit 2, `Ambiguity 0.80 >= 0.30`, dilemma + STOP, qa
  escalation-required, diff `diff_p05_acceptance_c92fbb4b` (fresh). ✓
- `--choice 1`: exit 0, single pins-module target
  `tests/unit/test_integration_runner_pins.py`, `Audit: with_codex=False
  (RT-08)`, qa `status=choice-recorded`, `P05_ACCEPTANCE_INVARIANTS.md`
  with fail-closed invariant, diff `diff_p05_acceptance_eed05d58` (fresh,
  distinct from all prior ids). Source root `@ edf5389…`. ✓
- Scratch dossiers removed after. Chain intact on the A1-fixed candidate.

## Gate 3 — Seeded-medium sanity (0 calls)

- Direct `_seed_codex_home()` on the REAL operator login: operator config
  carries `model_reasoning_effort = "max"`; seeded config carries
  `model_reasoning_effort = "medium"`; operator `config.toml` + `auth.json`
  bit-identical before/after; seeded home deleted after. ✓
- `tests/unit/test_winner_carry.py` re-run on real-gates: **6 passed**
  (1.83 s). ✓
- Carried medium profile confirmed on the exact live route.

## Gate 4 — Mirror-fix coverage (code read this session)

- Single fix point `mirror_source_tree` (`dialectic_runner.py:283-300`):
  resolves both paths, loud-refuses `src == dst` / src-inside-dst, excludes
  exactly the resolved `dst` subtree at every `_mirror_into` level
  (:303-317). B1.3 `.git`-inclusion comment + skip-set unchanged. ✓
- **BOTH live call sites route through it**: lease mirror :467
  (`mirror_source_tree(src, lease_ws)`) and merged mirror :837
  (`mirror_source_tree(Path(packet.source_repo_root), merged_dir)`). ✓
- Line numbers match the a1-fix verify-1 audit (:467 / :837) exactly —
  the verified fix is the fix in this tree.

## Stall guardrails (EXPLICIT — attempt-1 must not repeat)

- During the B2 verify leg(s), watch from OUTSIDE the run tree (read-only
  probes only): lease dir byte size (`du -sb`) and store/event cadence
  (`store.db` mtime + row count, `events.json` mtime).
- **Alert thresholds: lease >500 MB OR >10 min zero-event** (no new store
  rows AND no events.json write AND no spend-ledger append).
- **NO external intervention inside the run tree this time** — no `rm`,
  `chmod`, `mv`, or any write into the dossier/run/lease dirs while the
  run is alive. Attempt-1's breaking was a one-time diagnosed necessity;
  repeating it would void the intervention-free evidence this attempt owes.
- If a stall recurs (thresholds tripped + A1-shape confirmed read-only):
  kill the run **via the runtime channel only** (process terminate), then
  preserve the partial exactly as left (no cleanup of the runaway growth
  beyond what the runtime kill itself does). Report the stall with the
  read-only forensics; the partial stands as intervention-free evidence.
- Normal-progress expectations (non-alerting): gateway leg ~1 min (P2 56.7 s
  / attempt-1 43.1 s precedent); each verify mirror bounded (whole-tree
  copy minus ~dossier, single pass — seconds, not minutes); 120 s gate
  timeouts bound `execute_gates`; mutmut forced OFF per node.

## Live leg plan (B2)

- Exact P05-final command shape (cwd `ws/stc`, real-gates env):
  `python -m stc run docs/builds/stc-integration/specs/p05-acceptance.md
  --target stc --budget time=600,tokens=500000,usd=10,iters=2,branching=1,depth=4
  --choice 1`
  with `STC_DOSSIER_DIR=evidence/FOLLOWUP/accept-2/attempt-1/dossier`.
- Real-gates env: `<ws>/learn-anything/.venv/bin/python` 3.11.15,
  `PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`,
  `PYTHONDONTWRITEBYTECODE=1`. All three /tmp shims verified present (no
  recreation). codex-cli `0.154.0` confirmed on PATH. Operator login present
  (Gate 3 seed succeeded).
- Captures per P05 precedent: pre/post tracked+full status, sst before/after,
  live-run argv/env/stdout/stderr, dossier whole, `spend.jsonl` (every call).
- Budget: B1 spent **0** CLI calls. B2 may spend **≤10** (4 spent + 10 = 14
  tranche-spent; the 6-call verification reserve is NEVER touched). No
  H1-context experiments regardless of outcome (coordinator decision;
  experiment calls remain).
- Dispositions: FULL dossier (proposal → champion → merged diff → receipt →
  verdict → real gates) = success; no-champion = honest NEEDS_REPAIR partial,
  AUTOMATION-NOT-READY with exact failure anatomy; verify-fail specifically on
  module-path wiring (live-exp caveat, adjudicated live this time) =
  BLOCKED-WIRING with exact evidence.
- Veto/fail-closed: if the live run does not exercise veto/fail-closed paths,
  rerun the existing P04 veto/fail-closed suites (0 live calls) and cite.
- R1 stays deferred unless evidence shows it blocks. No product edits (evidence
  only). No commits, no STATE.md writes.

## Verdict

**READY** — all gates green, zero drift, medium profile proven on the live
route, mirror fix confirmed covering both call sites, stall guardrails
explicit with intervention-free discipline. Proceeding to B2.
