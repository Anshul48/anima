# FOLLOWUP winner-carry — B1 readiness (carry P2-H3a into the pipeline)

Author role and date: winner-carry-builder / 2026-09-14
Packet: STC follow-up tranche, winner-carry stage (carry the live-exp WINNER,
reasoning-medium, into the real pipeline via a one-line STC-owned change).
Base/candidate: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` + loose set
(all 8 hashes re-verified byte-exact below; own writes live under
`evidence/FOLLOWUP/winner-carry/`). Path shorthand: `evidence/...` below means
`docs/builds/stc-integration/evidence/...` on disk (prior-records convention).
Budget: 3/20 CLI spent entering, 6 hard reserve for acceptance+verification —
this stage spends 0.

## Gate 0 — predecessor gate (live-exp WIN + F1 PASS, by full read)

All three records read in full, in-session:

- `evidence/FOLLOWUP/live-exp/attempt-1/REVIEW.md`: verdict **WIN — P2-H3a**.
  Identical 5044 B shaped stdin (`3339af29…`) hangs served at reasoning-max
  (P1-H0b, exit 124 @150 s) and emits a valid §2 diverge proposal at
  reasoning-medium in 56.66 s (P2-H0b→P2-H3a: the ONLY differing byte is the
  scratch config's `model_reasoning_effort` line; header pair `max` vs
  `medium`; argv confined 9/9 both legs; SST bytes verbatim). Exact
  reproduction + proposed change + caveat (model-guessed `stc_gateway.…`
  import path; §2-parse win, not verify-green) serialized in §WINNER.
  Proposed STC-owned change (NOT made there): teach the live-run CODEX_HOME
  seeding (`cli.py: _seed_codex_home`) to write
  `model_reasoning_effort = "medium"` into the seeded `config.toml` for the
  gateway role. This stage implements exactly that proposal.
- `evidence/FOLLOWUP/live-exp/readiness.md`: Gate 3 live path confirmed —
  `CLIModelGateway`/`CLIGatewayBackend("codex")` + single `cli` TEST profile
  → fixed confined argv with scratch cwd + seeded scratch CODEX_HOME (deleted
  after). My change rides that seeding step; argv bytes untouched.
- `evidence/FOLLOWUP/f1-fix/verify-1/REVIEW.md`: verdict **PASS, F1 CLOSED**.
  76/76 P03 green on both interpreters, 5/5 F1-only + own 2-shape
  discrimination, confinement 16/16, ruff + mypy strict green. F1-owned bytes
  below are the VERIFIED hashes — argv pins VERIFIED, must stay byte-exact.
- Gate 0: SATISFIED.

## Gate 1 — drift gate (re-verified at B1, in-session)

- `git rev-parse HEAD` = `edf5389873e4d4a2a4752ee0aa2159289398495e` (tasked base).
- F1-owned byte-exact (full-sha recompute): `harness_worker.py
  ced79ed572d50f5c67d7e8556fe08127f59e0c529fc50bdaf1bc6898805a7867`,
  `cli_gateway.py f9dda17ec411c567dfccc51515cedfa69d79b75a6effd2c6e75c72ec76207b8a`,
  `test_integration_harness_worker.py
  e96db8d00a2950166f77ec6069ab98d9a944a344bfb452a4ffb7e6f3ce070b45`.
- Fix-owned byte-exact: `dialectic_runner
  19a2e448553c221260071b1d8509fe62749d96548cb5220f2083eec33848283b`,
  `test_dialectic 6e059f08e203478f3a70489b99385dc5a81a09386c274baf16a83e2c76bf1019`,
  `__init__ 105714219afcfbef9c81c50ce4216de4ce93096482aff2a4597cb4aaf04bac40`.
- Tracked mods exact: `cli.py
  33476f34c50ed726f699990102783fc507333e0bc165b033b0ded96eb8b124bb`
  (576/0), `dispatch.py dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7`
  (333/7); numstat identical to the live-exp baseline.
- Pins exact: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (status clean),
  prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
  `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`.
- Untracked = pre-existing loose set + `FOLLOWUP/` evidence only.
- Gate 1: SATISFIED — zero unexplained drift, proceeding (no STOP).

## Gate 2 — change design (one-line STC-owned carry)

Lever (the live-exp proposal, verbatim in intent): teach the live-run
CODEX_HOME seeding to write `model_reasoning_effort = "medium"` into the
seeded `config.toml` for the gateway role. Confined argv untouched (F1-owned
`build_gateway_command` READ-ONLY, pins VERIFIED); SST bytes untouched.

Seeded-config route viability (no STOP — route PROVEN live for this role):

1. `cli.py:1418-1429`: the live run seeds `codex_home = _seed_codex_home()`
   and passes `harness_env={"CODEX_HOME": str(codex_home)}` to
   `CLIGatewayBackend("codex")` — the gateway role's only live entry.
   `_seed_codex_home` has exactly ONE product caller (grep-confirmed).
2. `cli_gateway.py: generate()` → `run_harness_attempt(role="gateway",
   harness_env=...)` → `_run_confined_gateway_attempt` does
   `env.update(harness_env)` before spawning codex, so the codex subprocess
   reads the SEEDED `config.toml` (established P05 pattern).
3. Live proof: the P2-H3a probe seeded exactly this way (copy auth+config,
   flip the one line) and the served header confessed
   `reasoning effort: medium` with a §2-valid proposal in 56.66 s, while the
   P1-H0b leg (same bytes, `max`) hung served. The route takes effect.

Narrow hunk (owned file 1 of 2: `src/stc/cli.py`, `_seed_codex_home` only):

- Replace the copy-if-present tail with probe-identical logic: read the
  operator `config.toml` (or `""` when absent); rewrite every
  `model_reasoning_effort…`-prefixed line to
  `model_reasoning_effort = "medium"`; insert that line at the top when no
  such line exists; always write the seeded `config.toml`. All inside the
  existing `try/except OSError → None` (fail-closed semantics preserved).
- Logic is line-for-line the P2-H3a probe's proven lever
  (`liveexp-probe.py:106-117`), including its `strip().startswith` predicate
  — no new mechanism risk. Accepted predicate notes: a `#`-commented line
  cannot match (starts with `#`); a hypothetical
  `model_reasoning_effort_extra` key would match, but no such codex key
  exists and the predicate is probe-identical (won live).
- Behavior deltas vs today: (a) seeded config always carries the medium
  line; (b) a seeded `config.toml` is now written even when the operator has
  none (minimal file, medium line only — probe-identical; codex defaults
  otherwise preserved). Auth handling, temp-dir prefix, chmod, and the
  caller-deletes contract are unchanged. No new imports (`shutil`/`Path`
  already module-level, `tempfile` already function-local) — the default DAG
  path gains no new module dependencies.
- Pre-existing wart observed, NOT touched (out of narrow scope): on OSError
  after `mkdtemp` the temp dir leaks (no cleanup) — same before/after.
- Trial-cited comment per P05 precedent at the lever: cites the P2-H3a
  outcome (identical shaped `3339af29…` hangs served at max / emits valid §2
  at medium in 56.66 s) + the confessing header
  (`reasoning effort: medium`).

Test additions (owned file 2 of 2 — DECISION: create
`tests/unit/test_winner_carry.py`; reasons):

1. No existing test file covers product `stc.cli._seed_codex_home`
   (grep: zero test references to the product function; the `_seed_*`
   helpers in `test_integration_harness_worker.py` /
   `test_dialectic_fixture.py` are unrelated test-local copies).
2. The only topical candidate, tracked `tests/unit/test_cli.py`, is a
   deliberately-untouched pre-existing baseline across the whole tranche
   (F1 verify explicitly left it untouched); appending would add a third
   tracked mod and risk baseline disturbance.
3. Both VERIFIED-hash test files (`test_integration_harness_worker.py`,
   `test_integration_dialectic.py`) are drift-pinned byte-exact — appending
   there would break Gate 1 by construction.
4. A new untracked test file keeps the tracked diff to exactly the 2
   pre-existing files + the narrow `cli.py` hunk, matching the B2 audit
   shape; the carry tests (seeded-config contents, idempotence/cleanup) are
   cohesive and self-contained. No existing test is weakened (nothing
   touched).

Planned tests (all scripted, 0 CLI calls; HOME faked via monkeypatched
`Path.home`, seeded homes removed in `finally`):

- max→medium replacement with all other operator lines preserved verbatim;
- medium-line insertion at top when the operator config lacks the key;
- minimal seeded config written when the operator has no `config.toml`;
- `None` (fail-closed) when `auth.json` is absent;
- idempotence: two seeds → distinct homes, both carry the line, both clean
  up (dirs gone after `rmtree`);
- operator `config.toml` bytes bit-identical after seeding (never written).

Gate 2: SATISFIED — design confined to the 2 owned files; argv files
READ-ONLY (reference reads done: `build_gateway_command` codex shape +
`_run_confined_gateway_attempt` env flow, zero edits).

## Gate 3 — B2 proof plan (0 CLI calls) + environments

- Joint `trace/.venv-linux/bin/python` 3.12.3
  (`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`) and
  real-gates `learn-anything/.venv/bin/python` 3.11.15
  (`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
  all three shims present, no recreation; `PYTHONDONTWRITEBYTECODE=1`; cwd
  `ws/stc`. (Both interpreters + shims re-confirmed present at B1.)
- B2 evidence (under `evidence/FOLLOWUP/winner-carry/attempt-1/` + REVIEW.md):
  new-file tests green on BOTH interpreters; full P05 e2e file
  (`tests/integration/test_run_e2e.py`) green live-deselected on BOTH
  (manual test skips on joint — gate-tools probe needs ruff/mypy modules,
  absent there — and runs on real-gates, per file design); `ruff check` +
  `ruff format --check` and `mypy --strict` on owned files via real-gates
  `python -m` (ruff 0.16.1 / mypy 2.3.0, the F1-verify versions; joint has
  neither module); sst status clean; tracked-diff audit (exactly the 2
  pre-existing files, `cli.py` numstat grown only by the narrow hunk,
  `dispatch.py` still 333/7); Hash Identity for every file created/modified.
- No commits, no STATE.md writes; sst/prompt-kit/trace read-only;
  `trace-lite/` never listed/read/written. Status-after-last-write.

## B1 verdict: READY

No B1 evidence changes the plan or triggers a STOP: predecessors green by
full read, zero drift, seeded-config route proven live for the gateway role,
change confined to the narrow `cli.py` hunk + new test file. Proceed to B2.

## Spend (B1)

CLI calls so far: 0 (this stage) / 3 cumulative. Reserve 6 intact, untouched.
