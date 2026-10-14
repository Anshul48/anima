# Debt-fix + lease-exclusion — B1 readiness (G1 debt repair + evidence exclusion)

Record type: builder readiness (B1 scope gate; no product edits this stage)
Author role and date: debt-fix-builder / 2026-09-15
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set re-verified byte-exact this session (16/16, full-sha recompute, zero
drift): combined-owned `cli_gateway 29eb3906…01913`,
`auditor c59a8f40…0e21a`, `substrate/runner 8958eae1…5862a0f`,
`test_judiciary c87b3a74…40d9d`, `test_gateway_h1_context c3c886b1…79b91ba`,
`test_gateway_marker_refusal 106806c1…590c5`,
`test_pytest_gate_live_deselect 103348a5…36e60`; plus `cli.py 2ddfd6cb…d82f1`
(594/0), `dispatch.py dc75c56e…13c7` (333/7), `dialectic_runner c072f1da…0ff5`,
`test_dialectic eea1a7ee…0ec0`, `harness_worker ced79ed5…7867`,
`test_harness e96db8d0…70b45`, `test_a3 f99b2785…b1f2b`,
`test_winner_carry 0b5c3a8a…69762`, `__init__ 10571421…bac40`.
Pins: sst `079f4de6…` (clean before/after), prompt-kit `4f442a6c…`, trace
`a24a9370…` (all exact).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`;
this packet = `evidence/FOLLOWUP/debt-fix/` with `readiness.md` (this file),
`baseline/` (B1 reproductions), `attempt-1/` (B2 delivery + proof).
Method: required full reads (combined readiness + combined REVIEW + PATH-REVIEW
+ accept-123-verify REVIEW) + local deterministic experiments in `/tmp` only
+ read-only gate/tool replays on the pinned tree. **0 live calls; 0 product
edits at B1.**

## Predecessor gate (combined delivery + consolidated B3, by full read)

- Combined-fix attempt-1 REVIEW (builder delivery): W1/W2/W4/W5 landed and
  owned-tested (68/68 newtests both interpreters), veto 61/61 both, owned
  files ruff+format+mypy-strict green, whole-tree ruff still exactly 123 (new
  files contribute 0), 8 full-suite failures all triaged pre-existing with
  mirror-identical baselines, W3 CUT with coordinator options. Preserved: the
  8-failure triage (node IDs + causes + base proof) is this packet's pre-image
  for every affected suite; the "no B4 repair" boundary for the 8 is honored —
  this packet repairs only the 29-item debt inventory + the exclusion, and
  reports anything beyond as separate findings.
- Combined-fix readiness Gate 0 (G1 triple-proof): lease-faithful
  `mirror_source_tree` experiment proved the live whole-tree lease gates see
  exactly G1 (124 = 123 + 1 candidate, per-file attribution exact). Preserved:
  the lease-composition facts (all evidence `*.py` mirrored; gitignored
  `worktrees/` unscanned; `evidence/` scanned) and the W3 CUT reasoning with
  the exact debt inventory + coordinator options (a)/(b)/(c). This packet
  executes options (a)+(b): src/tests debt repair + exclusion of immutable
  evidence dirs.
- PATH-REVIEW (G1/G2/J1 baselines + gate commands + scope limits): G1 numbers
  (123 ruff = 7 + 116; 8 format = 4 + 4; 18 mypy in 8 files), exact gate
  commands (`ruff check .`, `ruff format --check .`, `mypy --strict src
  tests`, bare `pytest -v --tb=short` now D13 `-m "not live"` per W4), G2
  collection proof, J1 contrast, §6 scope limits (file-scoped gates,
  synthetic-local receipts, /tmp leases). Preserved: gate-command exactness
  (B2 reruns the identical commands), scope honesty (diagnostic vs live).
- Accept-123-verify REVIEW (consolidated rulings): all three PASS (attempt-3
  + BLOCKED-WIRING), veto/fail-closed 61/61 both interpreters, dry-run chain,
  live-byte anatomy, V123-INFO-1..4. Preserved: attempt bases/identities,
  BLOCKED-WIRING adjudication (the H1 lever this tranche unblocks), the
  FIX-B5 V1-INFO-1 immutability precedent (records stay byte-exact — binds
  the exclusion design: no edits to evidence files, ever).

## Drift gate

HEAD `edf5389` exact; 16/16 file shas exact (full recompute, §0 list); numstat
still exactly 594/0 + 333/7 on tracked; sst/prompt-kit/trace pins exact; sst
status clean. **Zero drift — PROCEED.**

## Baseline-failure reproduction (pinned candidate, outputs preserved)

All on the pinned tree, real-gates toolchain (ruff 0.16.1 / mypy 2.3.0),
`baseline/` logs:

- `ruff check .` → RC 1, **123 errors** (`baseline/ruff-check.log`): exactly
  7 src/tests (`adapters.py:170` I001, `identity.py:41` RUF022,
  `memory.py:292` C416, `test_integration_adapters.py:3` I001 + `:226`/`:419`
  RUF043, `test_integration_identity.py:3` I001) + 116 evidence (50+50
  `run_deep_research_campaign.py` incl. nested quarantine copy, 8+8
  `liveexp-probe.py`). Matches the tasked inventory exactly.
- `ruff format --check .` → RC 1, **8 files** (`baseline/ruff-format.log`):
  4 evidence + `adapters.py`, `memory.py`,
  `test_integration_adapters.py`, `test_integration_memory.py`. Exact match.
- `mypy --strict src tests` (live-identical gate PYTHONPATH
  `src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`) → RC 1,
  **18 errors in 8 files** (`baseline/mypy.log`): `bundler.py` 2, `cli.py` 1,
  `test_dialectic_fixture.py` 5, `test_pipeline.py` 1, `test_cli.py` 1,
  `test_compiler.py` 1, `test_integration_adapters.py` 2,
  `test_integration_dialectic.py` 5. Exact match. (Without the gate
  PYTHONPATH the count is 61 in 16 files — missing-module noise, not the
  gate scope; the gate runs with the toolchain env, so 18 is the baseline.)

## Per-debt repair plan (29 items; lint/format/mypy ONLY; zero behavior change)

Ruff (7) — `ruff check --fix` on exactly the 5 named files for the 4
safe fixes (I001×3 import-block blank lines, RUF022 `__all__` sort — both
reviewed via `--diff` pre-image: joining/sorting only, name sets identical),
plus 2 manual edits: `memory.py:292` C416 `[kw for kw in entry.keywords]` →
`list(entry.keywords)` (identical iteration semantics); `RUF043 ×2`
`match="1..3"` → `match=r"1\.\.3"`, `match="stc.spec_id"` →
`match=r"stc\.spec_id"` (messages verified to contain the literals —
`adapters.py:291` / `_check_binding` at `:417` — so the narrowed patterns
still match; strictly more precise, product behavior untouched).

Format (4) — `ruff format` on exactly `adapters.py`, `memory.py`,
`test_integration_adapters.py`, `test_integration_memory.py` (pre-imaged via
`--diff`: pure line-join whitespace, incl. identical implicit-concat strings).
Evidence files are NEVER formatted (immutable).

Mypy (18):
- `import-untyped` (yaml) ×5 — `bundler.py:12`, `cli.py:20`,
  `test_pipeline.py:6`, `test_compiler.py:22`, `test_cli.py:6` (the 18-count
  reconciles: 2+2+1+5+5+1+1+1 across the 8 files). Fix: per-line
  `# type: ignore[import-untyped]` (the mypy-documented remedy for
  stub-less third-party imports; single line, specific code, fail-visible
  via `warn_unused_ignores`). NOT a blanket ignore; NOT a config override
  (no `ignore_missing_imports` — the per-line form keeps every other check
  on those lines live). types-PyYAML is NOT installed in either gate env and
  installing into operator envs is out of scope — the in-repo fix greens
  every env. Runtime bytes unchanged (comments).
- `no-any-return` ×6 — `bundler.py:325` (`yaml.safe_dump`, Any because yaml
  is stub-less), `test_integration_dialectic.py:1170,1217`
  (`return base(request)`, handler returns Any),
  `test_dialectic_fixture.py:271,278` (`return event["payload"]`),
  `:283` (`return json.loads(...)`). Fix: typed local + return
  (`text: str = base(request); return text`, etc.). Assigning Any to a
  declared local is allowed; the returned value is byte-identical.
  Line-count note: the dialectic-test fixes add one line each at 1170/1217 —
  safely ABOVE the W1 staleness-tripwire ranges (≤754); the 176/577 fixes
  are same-line. No tripwire shift (proven by W1 rerun at B2).
- `test_integration_adapters.py:175` arg-type + unused-ignore — field is
  `tuple[str, ...]` but the test passes `["pytest -q"]` with a stale
  `# type: ignore[list-item]`. Fix: pass `("pytest -q",)` and DROP the
  ignore (a true type fix, not a suppression swap: `tuple(...)` in
  `__post_init__` yields the identical `("pytest -q",)`; the assertion
  `== ("pytest -q",)` still passes).
- `ScriptGateway.profiles` assignment + unused-ignore ×2 —
  `test_integration_dialectic.py:176`, `test_dialectic_fixture.py:182`:
  `self.profiles["test"] = "test"` with stale `# type: ignore[dict-item]`
  (true code: `assignment`, str vs `ProviderProfile`). Fix: correct the
  ignore code to `[assignment]` (comment-only; runtime bytes unchanged). A
  "real" fix (constructing a `ProviderProfile`) would CHANGE the runtime
  object flowing through the veto/fixture paths — that is a behavior change
  risk for zero benefit, so per the brief's rule it is NOT implemented;
  the stale-code correction restores author intent with zero behavior delta.
  (Recorded here explicitly as the brief requires for type-vs-behavior
  judgments; no separate behavior change is needed — the tests pass as-is.)
- `test_integration_dialectic.py:577` unused-ignore alone —
  `receipt.synth_score = 0.1  # type: ignore[misc]`: mypy (2.3.0, gate
  toolchain) does not flag the line, so the comment is dead. Fix: delete
  the comment (zero runtime delta; the `ValidationError` assertion is
  unaffected).

No other files touched. No test removed, no mark changed, no threshold
touched, no `noqa`, no config `ignore` lists. Any B2 surprise requiring a
behavior change stops and is reported as its own finding (not implemented).

## Lease-contract check (FIRST, before the exclusion design)

Governing contract text (quoted verbatim):

1. `01_INVARIANTS.md` §5 — "Software eligibility for review is governed by
   4 mechanical gates:" Gate 1 `uv run ruff check .` && `uv run ruff format
   --check .` (exit 0); Gate 2 `uv run mypy --strict src/` (exit 0);
   Gate 3 `uv run pytest -v --tb=short` (exit 0, 100% pass, 0 skipped);
   Gate 4 `mutmut run` kill rate ≥85%. The contract fixes the COMMANDS and
   the exit criteria; it does not enumerate which tree paths must exist in a
   lease, and it does not require historical records to be lint-scanned.
2. `ADR-INT-01` (ratified amendment of §5): per-node gates are 1–3 only
   (Gate 4 champion-only); Gate 3 deselects `@pytest.mark.live` per D13
   (zero-skip invariant intact).
3. `mirror_source_tree` + `_MIRROR_SKIP_DIRS`
   (`dialectic_runner.py:275-317`, code-as-contract): the lease is a
   whole-tree mirror minus the skip-set (`.auto .sst .venv __pycache__
   .pytest_cache`) minus the dst-subtree (A1); `.git` is deliberately
   INCLUDED ("substrate receipts require commit binding").
4. Operator guardrail (binding): exclude immutable historical evidence from
   executable lease contents ONLY after confirming it is not a runtime or
   test dependency; preserve originals + hashes; keep all source, tests,
   configuration, and required fixtures within gate coverage; record the
   exclusion explicitly.

Dependency determination (positive experiments, not assertions):

- E2 (`baseline/debtfix-e2.log`): lease-faithful mirror via the REAL
  `mirror_source_tree` with `evidence/` REMOVED → W1+W2 tests: **9 failed
  (FileNotFoundError), 17 passed, RC 1**. The failures are the tests that
  read `evidence/FOLLOWUP/h1-prep/ctx-package.txt` (W1 hash/verbatim pins)
  and `evidence/FOLLOWUP/.../events.json` + `stdout.txt` (W2 exact-live-byte
  pins). **The evidence dir AS A WHOLE is a Gate-3 test dependency.**
  Consequence: whole-evidence mirror exclusion would trade Gate 1 red for
  Gate 3 red — it is BLOCKED by the guardrail's own condition.
- E3 (`baseline/debtfix-e3.log`): mirror with ONLY the 4 gate-offending
  `.py` files removed → W1+W2+veto: **87 passed, RC 0**. The excluded SET
  (evidence `.py`) is not a dependency.
- No-import proof: zero `import`/`from` references to evidence paths in
  src/tests (grep); no `__init__.py` anywhere under `evidence/` (not
  packages); positive `ModuleNotFoundError` for both offending basenames in
  the lease env; judiciary scans `diff_text` + receipt only
  (`auditor.py:167-172` — never evidence/); mypy scope is `src tests` and
  pytest `testpaths` is `tests` (evidence `.py` never in scope — only the
  whole-tree ruff commands see them, which is exactly the G1 mechanism).
- E4 (`baseline/debtfix-e4-*.log`, read-only `--exclude` pre-image):
  `ruff check .` minus `docs/builds/stc-integration/evidence` → exactly
  the 7 src/tests errors; `ruff format --check .` likewise → exactly the 4
  src/tests files. The project-config exclusion mechanism removes precisely
  the evidence portion from BOTH Gate-1 commands.

## Exclusion design (mirror skip-set vs alternatives — decided by experiment)

- REJECTED — mirror skip-set by dir name (`evidence`): blocked by E2 (W1/W2
  Gate-3 tests read `evidence/` artifacts; removing the dir from leases
  fails Gate 3). Also coarse (`item.name` matches at every depth) and it
  would nick the W1 tripwire's artifact source.
- REJECTED — mirror skip-set by offending basenames (2 filenames): passes
  E3 mechanically but is a fragile filename allowlist — any future
  evidence `.py` re-reddens Gate 1 — and it reduces lease fidelity for zero
  benefit over the config mechanism.
- REJECTED — per-file `# noqa` / edits in evidence files: violates the
  FIX-B5 V1-INFO-1 immutability precedent (records stay byte-exact).
- REJECTED — `.gitignore` additions for tracked records: confusing,
  affects non-gate tooling, weaker than an explicit recorded exclusion.
- REJECTED — contract amendment: unnecessary; the §5 COMMANDS stay literal
  under the chosen design.
- ADOPTED — ruff `exclude` for the immutable evidence dir in project
  config (`pyproject.toml [tool.ruff] exclude =
  ["docs/builds/stc-integration/evidence"]`, with an in-config comment
  citing this record + the contract): Gate-1 commands stay §5-literal
  (`ruff check .`, `ruff format --check .` — the tool honors project
  config, exactly as it already honors `.gitignore` for `worktrees/`, the
  load-bearing precedent); lease CONTENTS stay whole-tree (W1/W2 fixtures
  intact, E3-green); immutable originals byte-preserved (hashes re-pinned
  at B2 close); exclusion explicit, recorded, and future-proof (any new
  `.py` under `evidence/` is covered). Removes from gate coverage ONLY
  never-executed record `.py` files — all of src/, tests/, configuration,
  and required fixtures (`.txt`/`.json`, never in ruff scope anyway) stay
  covered. This is a scoped records exclusion, not a weakened check: the
  excluded files are immutable (unfixable by policy) and unexecuted
  (proven) — linting them serves no quality function.

## Affected-check selection (explicit justification per file)

No mechanical full-suite repetition on the real tree. Per-file checks (each
run pre-fix = `baseline/` AND post-fix = `attempt-1/`, BOTH interpreters
unless noted; pass→fail anywhere is a STOP):

- `adapters.py` / `identity.py` / `memory.py` (import-sort, `__all__`-sort,
  C416, format): covered by their P01 suites
  (`test_integration_adapters` / `test_integration_identity` /
  `test_integration_memory`) + veto (adapters in closure via
  `receipt_to_score`). Pre: P01 real 1 failed (record_shape, env-version)
  + 114 passed; joint 115 passed (`baseline/p01-prefiles-*.log`).
- `test_integration_adapters.py` (I001, RUF043×2, format, tuple fix): its
  own suite pre+post (above) — the tuple fix and RUF043 narrowing are the
  only semantic-adjacent edits; identical outcomes prove neutrality.
- `test_integration_identity.py` (I001): own suite (above); the env fail
  must reproduce IDENTICALLY (same node, same assert).
- `test_integration_memory.py` (format): own suite (above).
- `test_integration_dialectic.py` (5 mypy): veto 61/61 pre+post both
  interpreters (`baseline/veto-newtests-pre-*.log`: 89/89 incl. newtests).
  Also guards the W1 tripwire ranges (no shift ≤754).
- `test_dialectic_fixture.py` (5 mypy): own file pre+post both
  (`baseline/fixture-pipeline-pre-*.log`: real 5 passed/1 deselected;
  joint 3 passed/2 skipped/1 deselected — env-conditional skips).
- `test_pipeline.py` (yaml ignore): own file (above — same logs).
- `test_compiler.py` + `test_cli.py` (yaml ignores) + `cli.py`/`bundler.py`
  (comment-only / typed-local): own files pre+post both
  (`baseline/compiler-cli-pre-*.log`: real 1 failed
  [`test_cli_run_json_mode`, `assert 1 == 0`, committed-bytes E2E] + 52
  passed; joint identical: same node + 52 passed). Identical-outcome rule.
- `test_gateway_h1_context.py` (reread, not edited): RERUN both (reads
  the edited dialectic-test file; tripwire must stay green).
- `test_gateway_marker_refusal.py` + `test_pytest_gate_live_deselect.py`
  (not edited; closure-untouched — cli_gateway imports only sst +
  harness_worker): RERUN both anyway (cheap: 19 tests; `baseline/`
  newtests logs double as pre-image).
- `test_judiciary.py` / J1: REUSE combined `newtests` logs (auditor.py
  untouched, sha-verified `c59a8f40…`; J1 contrast path provably
  untouched — say so in REVIEW, cite log hash).
- `test_substrate.py::test_substrate_runner_real_clean_execution_and_save`
  + `::test_clean_tree_emits_verifiable_receipt_json` (+ joint-only
  `test_injected_syntax_error…`): RERUN (the product's own G1 proof;
  predicted flip on real-gates; pre: real 2 failed with
  `violations_count=123` through the gate regex, joint 3 failed —
  `baseline/substrate2-pre-real.log`, `substrate3-pre-joint.log`).
- G2 collect: `--collect-only` bare vs `-m "not live"` pre+post on
  real-gates (counts must be identical; pre: 533 bare, 527 + 6 deselected —
  `baseline/g2-collect-pre-*.log`).
- `dag_pipeline` ×4 + `test_cli_run_json_mode` E2E: NOT rerun on the real
  tree pre/post (they gate COMMITTED-`main` bytes via `git worktree add`,
  proven at `manager.py:474-481` — working-tree edits cannot reach them;
  provably unaffected). Re-observed in the mirror Gate-3 run; identical
  signatures expected.
- Contract-forced full runs (cited): §5 Gate 3 IS the full suite
  (`pytest -v --tb=short`, ADR-INT-01/D13 `-m "not live"`) — so B2 runs
  the full Gate-3 command in the lease-faithful mirror on BOTH
  interpreters; Gates 1+2 likewise with the exact substrate commands.
  Predicted (honest, from code reading — NOT promised green): Gates 1+2
  exit 0; Gate 3 flips the debt-owned fails where the env permits
  (substrate ×2 on real-gates) while joint tool-absence (no ruff/mypy
  modules), the 3.11-vs-3.12 env assert, and committed-bytes E2E reds
  persist with identical signatures. Any remaining red is triaged per-test
  with pre/post signatures; literal Gate-3 exit-0 (if env/commit-blocked)
  is reported as a coordinator finding with options (provision joint
  tools; commit tranche; version-assert disposition) — NOT fixed by scope
  creep. Zero regressions is the hard rule.

## B2 proof plan (0 CLI calls — summary)

(1) GREEN baseline lease gates: exact substrate gate commands in a
lease-faithful `mirror_source_tree` mirror — `ruff check .`, `ruff format
--check .`, `mypy --strict src tests` (gate toolchain), `pytest -v
--tb=short -m "not live"` collect + run BOTH interpreters — with the
honest Gate-3 reporting rule above. (2) H1/refusal/G2/J1 local checks
rerun-or-reused per the selection above. (3) DIAGNOSTIC end-to-end local
proof (labeled diagnostic, NOT live acceptance): hand-written pins diff →
custody → whole-tree gates → judiciary → champion → dossier assembly in
/tmp, bounded; mutmut-on-champion attempted in a 30-min box else the exact
invocation staged + documented unrun. (4) ruff/format/mypy on every owned
file; sst clean; tracked-diff audit; Hash Identity; no commits, no
STATE.md writes; sst/prompt-kit/trace read-only; `trace-lite/` never
touched. Spend 0 (tranche 8/20, 6-call reserve intact).
