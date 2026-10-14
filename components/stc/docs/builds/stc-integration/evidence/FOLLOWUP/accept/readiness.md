# FOLLOWUP accept — Readiness (B1)

Record type: builder readiness
Author role and date: acceptance-builder / 2026-09-14
Packet: STC follow-up tranche, acceptance stage (carry live-exp WINNER P2-H3a
reasoning-medium through the real pipeline on the SAME approved P05 task).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (9 hashes re-verified byte-exact below, zero drift).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Gate 0 — Predecessor gates (full read, nothing inherited)

| Record | Outcome carried |
| --- | --- |
| `evidence/FOLLOWUP/live-exp/attempt-1/REVIEW.md` | **WIN P2-H3a**: identical shaped bytes hang served at reasoning-max (P1-H0b exit 124 @150 s) and emit a valid §2 diverge proposal at reasoning-medium in 56.66 s. **Caveat**: winner diff guesses `stc_gateway.…` paths (real tree: `stc.integration.…`) — verify-green NOT promised; wiring-fail disposition is BLOCKED-WIRING, not improvisation. |
| `evidence/FOLLOWUP/winner-carry/verify-1/REVIEW.md` | **PASS**: `cli.py 2ddfd6cb…d82f1` seeded-config lever (max→medium rewrite / insert-at-top) probe-identical to the P2 lever, confined argv/bytes untouched, winner tests 6/6 both interpreters + own 9/9 discrimination. |
| `evidence/FOLLOWUP/f1-fix/verify-1/REVIEW.md` | **PASS (F1 CLOSED)**: failure-evidence sidecar active — fast-fail full stderr preserved byte-exact, tail cause raised. |
| `evidence/P05-fix/attempt-1/REVIEW.md` + `verify-1/REVIEW.md` | Prior live shape (M1-final budget + `--choice 1`, real-gates, NEEDS_REPAIR partial anatomy) + honest-partial precedent (PARTIAL ruled, never padded). |
| `evidence/FIX-B5/REVIEW.md` | **NOT-READY baseline** this run must beat: honest no-champion partial, 0 live proposals ever. |
| `packets/P05-cli-acceptance.md` §Fix tranche | Acceptance deltas pattern: prompt + stderr + header + before/after status preserved; dossier complete per outcome; chain re-closed; no out-of-loop writes; e2e green. |
| `specs/p05-acceptance.md` | SAME approved spec (F-B3-3/F-B3-4 pins task), not re-approved. `--choice 1` reuse pre-authorized. |

Also read in full for lever mechanics: `evidence/FOLLOWUP/winner-carry/attempt-1/REVIEW.md`
(CARRIED; hunk `33476f34…124bb` → `2ddfd6cb…d82f1`, net +18).

## Gate 1 — Drift gate (re-verified this session, STOP on unexplained drift)

- HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` = tasked base. ✓
- 9/9 file hashes byte-exact at tasked values: `cli.py 2ddfd6cb…d82f1`
  (numstat 594/0), `test_winner_carry.py 0b5c3a8a…69762`, `harness_worker
  ced79ed5…7867`, `cli_gateway f9dda17e…07b8a`, `test_harness e96db8d0…70b45`,
  `dialectic_runner 19a2e448…8283b`, `test_dialectic 6e059f08…f1019`,
  `__init__ 10571421…bac40`, `dispatch.py dc75c56e…13c7` (numstat 333/7). ✓
- Pins exact: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32`,
  prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`,
  trace `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`; sst status empty. ✓
- **Zero drift. No STOP.**

## Gate 2 — Dry-run replay (real-gates, scratch dossiers, 0 calls)

- Bare: exit 2, `Ambiguity 0.80 >= 0.30`, dilemma + STOP, qa escalation-required,
  diff `diff_p05_acceptance_5a6df225` (fresh). ✓
- `--choice 1`: exit 0, single pins-module target
  `tests/unit/test_integration_runner_pins.py`, `Audit: with_codex=False
  (RT-08)`, qa choice-recorded, `P05_ACCEPTANCE_INVARIANTS.md` with fail-closed
  invariant, diff `diff_p05_acceptance_d326fcfa` (fresh, distinct from all
  prior ids). Source root `@ edf5389…`. ✓
- Chain intact on the carried candidate.

## Gate 3 — Seeded-medium sanity (0 calls)

- The dry-run path itself never seeds (0 model calls by construction — no
  gateway spawn), so seeding is not observable *through* the dry run. Proven
  directly instead, on the REAL operator login (`~/.codex`, `Path.home()`-based
  like the live path): `_seed_codex_home()` returned a seeded home whose
  `config.toml` carries `model_reasoning_effort = "medium"` (operator `max`
  line rewritten), and operator `config.toml` + `auth.json` bytes are
  bit-identical before/after. Seeded home deleted after. ✓
- `tests/unit/test_winner_carry.py` re-run on real-gates: **6 passed** (1.91 s). ✓
- Together with the P2 served header (`reasoning effort: medium`) precedent,
  the carried medium profile is confirmed on the exact live route.

## Live leg plan (B2)

- Exact P05-final command shape (cwd `ws/stc`, real-gates env):
  `python -m stc run docs/builds/stc-integration/specs/p05-acceptance.md
  --target stc --budget time=600,tokens=500000,usd=10,iters=2,branching=1,depth=4
  --choice 1`
  with `STC_DOSSIER_DIR=evidence/FOLLOWUP/accept/attempt-1/dossier`.
- Real-gates env: `<ws>/learn-anything/.venv/bin/python` 3.11.15,
  `PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`,
  `PYTHONDONTWRITEBYTECODE=1`. All three /tmp shims verified present (no
  recreation). codex-cli `0.154.0` confirmed on PATH. Operator login present
  (Gate 3 seed succeeded).
- Captures per P05 precedent: pre/post tracked+full status, sst before/after,
  live-run argv/env/stdout/stderr, dossier whole, `spend.jsonl` (every call).
- Budget: B1 spent **0** CLI calls. B2 may spend **≤11** (3 live-exp + 11 = 14
  tranche-spent; the 6-call verification reserve is NEVER touched). No
  H1-context experiments regardless of outcome (coordinator decision; 11
  experiment calls remain unspent).
- Dispositions: FULL dossier (proposal → champion → merged diff → receipt →
  verdict → real gates) = success; no-champion = honest NEEDS_REPAIR partial,
  AUTOMATION-NOT-READY with exact failure anatomy; verify-fail specifically on
  module-path wiring (live-exp caveat) = BLOCKED-WIRING with exact evidence.
- Veto/fail-closed: if the live run does not exercise veto/fail-closed paths,
  rerun the existing P04 veto/fail-closed suites (0 live calls) and cite.
- R1 stays deferred unless evidence shows it blocks. No product edits (evidence
  only). No commits, no STATE.md writes.

## Verdict

**READY** — all gates green, zero drift, medium profile proven on the live
route, live leg fully specified. Proceeding to B2.
