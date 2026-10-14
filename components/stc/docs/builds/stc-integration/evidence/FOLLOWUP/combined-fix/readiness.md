# Combined-fix — B1 readiness (H1-prep findings → attempt-4 path)

Record type: builder readiness (B1 scope gate; no product edits this stage)
Author role and date: combined-fix-builder / 2026-09-15
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set re-verified byte-exact this session (10/10, full-sha recompute, zero
drift): `cli_gateway aedffa12…bb392`, `test_a3 f99b2785…b1f2b`,
`dialectic_runner c072f1da…0ff5`, `test_dialectic eea1a7ee…0ec0`,
`cli.py 2ddfd6cb…d82f1` (numstat 594/0), `test_winner_carry 0b5c3a8a…69762`,
`harness_worker ced79ed5…7867`, `test_harness e96db8d0…70b45`,
`__init__ 10571421…bac40`, `dispatch.py dc75c56e…13c7` (numstat 333/7).
Pins: sst `079f4de6…` (status clean), prompt-kit `4f442a6c…`, trace
`a24a9370…` (all exact). H1-prep transcripts all hash-exact
(`ctx-package.txt e0c814e5…adbca`, 3921 B; `custody/g2-collect/gates-bad/
gates-kg/j1-contrast/score-judiciary.txt` all match). W1 provenance third
pin: `auditor.py 0f76845d…c2` exact.
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.
Method: required full reads (all five records) + local deterministic
experiments in `/tmp` only. **0 live calls; 0 product edits at B1.**

## Gate 0 — G1-scope discrepancy: RESOLVED by decisive experiment (no drift)

**Question.** PATH-REVIEW G1 measures whole-tree gates red on pre-existing
files (123 ruff + 8 format + 18 mypy), yet the attempt-3 wiring verdict cites
~3 ruff errors. What does the live gate scope actually see?

**Experiment** (`/tmp/g1-scope-replay.py`, kept out of the tree): real
`mirror_source_tree` → `/tmp/combined-fix-lease` (217 MB, `.git` included,
`.venv` excluded per skip-set, dst-outside-src so no dst-exclusion — live dst
is a fresh empty lease dir at mirror time, hence gate-identical); exact
attempt-3 cand-1 bytes (4299 B, sha `a6c8f1d3…`, hash-asserted) applied via
pristine SST `apply_proposal` (output 4096 B `2e6c187a…` — byte-exact vs the
live record); then the EXACT substrate gate commands with cwd=mirror on the
real-gates toolchain (3.11.15, live-identical PYTHONPATH).

**Observed (lease scope, per-file attribution):**

- Lease composition: all 8 evidence `*.py` present (4 originals + 4 nested
  quarantine copies); `.git` + `.gitignore` + `pyproject.toml` present;
  `worktrees/` present but unscanned (gitignored — ruff honors `.gitignore`;
  0 hits). `evidence/` is NOT gitignored → scanned.
- `ruff check .`: **124 errors** = G1's 123 + 1 (candidate file contributes
  exactly I001 under project config — PATH-REVIEW §3 config note confirmed).
  Attribution: 50+50 `run_deep_research_campaign.py`, 8+8 `liveexp-probe.py`,
  3 `test_integration_adapters.py`, 1 candidate, 1+1+1+1
  (`test_integration_identity.py`, `memory.py`, `identity.py`, `adapters.py`).
- `ruff format --check .`: **8 files would be reformatted** = G1's 8
  (candidate file format-clean under project config — §3 confirmed).
- `mypy --strict src tests`: **23 errors in 9 files** = G1's 18 + 5
  candidate (3× `import-not-found` + 2× `no-untyped-def`). Evidence `*.py`
  never in mypy scope (src+tests only).
- `pytest --collect-only`: 500 collected + 1 collection error
  (`ModuleNotFoundError: No module named 'praxist'` on the candidate) —
  wiring reproduced in lease scope.
- Third corroboration (product's own path): baseline
  `test_substrate_runner_real_clean_execution_and_save` FAILS with
  `violations_count=123` — G1's exact number through the gate regex.

**Resolution.** There is NO scope discrepancy: the live whole-tree lease gates
see exactly what G1 measured (plus candidate-file errors). The "~3 errors"
figure is the accept-3 builder's FILE-SCOPED bare-config replay on the
custody output — a different, documented scope (PATH-REVIEW §3 config note +
§6 limits), not the live gate scope. The live record preserves only booleans
(all False) — fully consistent with G1. **G1's premise is CONFIRMED
(triple-proven), not contradicted.**

## Workstream dispositions

### W1 H1-context — PROCEED (4th in build order: after W5, staleness rule)

- Shape: embed `ctx-package.txt` (3921 B, 110 lines, sha `e0c814e5…adbca`,
  trailing `\n`) as a mechanically generated module constant in
  `cli_gateway.py` (generation script in `/tmp`; hash test proves
  byte-exactness; never hand-edited). Placement: closing block immediately
  after `SST_PROMPT_END`, BEFORE the A3 pin lines + final emit instruction
  (pin + "Now emit…" stay last for recency). SST bytes verbatim between
  unchanged delimiters (D15/D7); no `allowed_paths` change (reference text).
- Frame-budget caution honored: sizing test pins package ≤ 4096 B budget +
  bounded frame overhead; medium-profile assumption explicit in code comment
  + REVIEW (attempt-4 must keep the medium profile; any stall is a
  prompt-size signal, not content).
- Staleness rule executed literally at B2: implement W5 first, then rebuild
  the six §-ranges from the post-W5 tree and diff vs `ctx-package.txt`
  (expect byte-identical — W5's edit sits below all pinned auditor ranges
  and touches no pinned runner range); record whole-file shas as-built.
- Tests (new file `tests/unit/test_gateway_h1_context.py`, `-m "not live"`):
  package hash-pin (`e0c814e5…`), placement (delimiters → SST verbatim →
  context → pin → emit-last), verbatim (every payload section == current
  source-range bytes; the staleness tripwire), sizing (3921 B / budgets).
- Committable-alone note: W1 + W2 hunks in `cli_gateway.py` are disjoint
  regions (frame/predicate); either order applies. Pin VALUES are post-W5
  per the staleness rule (mechanical, documented).

### W2 Marker refusal — PROCEED (MARKERS.md §5 exactly, one placement ruling)

- Placement ruling: the check lives inside `CLIGatewayBackend.generate`
  before `return result.content` (:240) — the spec's explicitly allowed
  equivalent ("or equivalently inside `CLIGatewayBackend.generate`"). This
  is REQUIRED for ledger honesty: the row is written in `generate`'s
  `finally`, so only in-`generate` refusal can set the note before the
  raise; `invoke`-placement would leave a silent-success row (and a second
  row would corrupt quota counts). All routed roles + the engine path are
  covered (single choke point).
- Predicate `marker_refusal_reason(response_text) -> str | None`: imports
  SST's `SSTSearchController._parse_json_dict` (verified light: stdlib +
  sst-internal only; imports fine in the live env — no reimplementation, no
  drift); scan targets = `branches[].proposed_changes` when branches is a
  non-empty list, else whole content; column-0 `***` match; first offending
  line truncated to 80 chars. Defensive `isinstance` guards on branch
  entries (SST would crash on non-dict branches; the predicate must not).
- Refusal error: `ProviderGatewayError` with `category="stc_marker_refusal"`,
  spec message shape (offending line `!r`, never full bytes), spec
  remediation, `profile=<passed profile>`. Upstream handling already proven
  (PATH-REVIEW §1a: all four invoke sites catch).
- Ledger: row keeps `ok=True` (harness truth); note set before the raise to
  `stc-refused: column0-triple-star (<sidecar>#<id>)` (within NOTE_BUDGET;
  write-failed fallback mirrors F1). NO `failure_evidence` row key (that key
  is documented failure-rows-only; the note carries the pointer per spec).
- Sidecar: NEW `<ledger-stem>.refusals.jsonl` via a `cli_gateway.py`-local
  best-effort writer (spec: no other product file changes): record = v, id,
  ts, harness, model, profile, task label, offending line, `sha256` of
  refused bytes, full bytes. NOT the F1 sidecar (policy decision, not
  harness failure). No gateway-internal retry (controller loop owns retry).
- Tests (new file `tests/unit/test_gateway_marker_refusal.py` — mandated
  name): full §5 matrix. Refuse: exact P2/a2c0/a3c0 trailer tails,
  exact a1/a2c1 apply_patch envelopes, unified+trailer, raw-fallback with
  markers, unparseable-JSON with markers. Admit: exact a3c1 bytes, §2
  known-good shape, indented `***`, markdown-bold, marker-free raw code.
  Exact live bytes loaded from dossier `events.json` at test time with
  size+sha guard pins (exact by construction). Ledger: refused row
  `ok=True` + refusal note + sidecar pointer; sidecar round-trips exact
  refused bytes by sha256. D-tests: SST bytes verbatim (D15/D7), admitted
  payloads byte-identical pre/post.
- Sanitizing stays rejected (MARKERS §2 — no byte rewriting anywhere).

### W3 G1 gate-debt — CUT (STOP; coordinator decision, reasons below)

B1 proves no pre-authorized shape delivers green gates:

- Mirror exclusion (authorized IF evidence reaches gates — CONFIRMED it
  does) removes only the evidence portion (116 ruff + 4 format). It cannot
  touch the src/tests portion: **7 ruff + 4 format + 18 mypy across ~9
  files**, still red on every gate. A partial exclusion is unprovable (no
  green) and changes shared verify+merge lease behavior for zero verified
  benefit — not implemented.
- Gate scoping is contract-blocked: §5 fixes Gate 1 as `ruff check .` +
  `ruff format --check .` (whole tree); narrowing the command needs a
  contract amendment. Mypy is worse: even the contract-literal `mypy
  --strict src` (narrower than the implemented `src tests`) leaves 3 src
  errors (`cli.py` 1 + `bundler.py` 2) — scoping alone cannot green it.
- File-by-file debt fixes are explicitly NOT pre-authorized, and the
  evidence-116 is unfixable-by-edit anyway (immutable historical records —
  FIX-B5 V1-INFO-1 precedent: records stay byte-exact).
- Exact debt inventory for the coordinator (all triple-proven: G1 baselines
  + lease mirror + product's own 123-count test): ruff =
  `adapters.py:170` I001, `identity.py:41` RUF022, `memory.py:292` C416,
  `test_integration_adapters.py:3` I001 + `:226`/`:419` RUF043,
  `test_integration_identity.py:3` I001, + 116 evidence; format = 4
  evidence + `adapters.py`, `memory.py`, `test_integration_adapters.py`,
  `test_integration_memory.py`; mypy 18 in 8 files (`cli.py` 1,
  `bundler.py` 2, `test_dialectic_fixture.py` 5, `test_pipeline.py` 1,
  `test_cli.py` 1, `test_compiler.py` 1, `test_integration_adapters.py` 2,
  `test_integration_dialectic.py` 5).
- Coordinator options: (a) authorize a debt-fix tranche for the src/tests
  files + (b) authorize lease/config exclusion of immutable evidence dirs
  (mirror skip-set or ruff `exclude`), or (c) amend the §5 gate contract.
  Until then, no admitted leg can verify while G1 stands (unchanged).

### W4 G2 live-tests-in-gate — PROCEED (tiny by design)

- Shape: `cmd = [..., "-m", "not live"]` in `_run_gate_pytest`
  (`runner.py:429`). Contract-REQUIRED, not merely allowed: D13 (live tests
  "deselected in gate runs" — pyproject marker text, ADR-INT-01, P03 packet).
  Zero behavioral change to non-live selection (bare `-m "not live"` on a
  tree with no live marks = full run).
- Test placement: NEW file (not appended to `test_substrate.py`, which is
  RED at baseline for G1 reasons — `..._real_clean_execution_and_save`
  fails with 123 violations, proven above). New file keeps the W4 affected
  suite green; B2 additionally runs `test_substrate.py` before/after to
  prove identical outcomes (no behavior change to existing tests). Test is
  behavioral + fail-safe: fixture tree (tmp_path) with a `mark.live`
  `assert False` test (would fail the gate if collected — never a live
  call) + a passing test + minimal config registering the `live` marker;
  assert gate exit 0 with the live test deselected.
- Out of scope (noted, not expanded): mutmut's internal pytest invocation
  on the champion path.

### W5 J1 attribution — PROCEED (1st in build order: staleness rule)

- Shape: in `audit_diff`, keep the `+++ b/` arm (:220) first and
  unconditional; add an `elif` attributing bare `+++ <path>` (excluding
  `+++ /dev/null`, which must never attribute), same `.strip()` style as
  the existing arm (consistent with the code's existing non-validating
  contract — a `++`-prefixed content-line collision is the same accepted
  theoretical class as the pre-existing `++ b/` content collision, and
  rarer). Steps 1–2 (receipt signature + gate-failure findings) untouched —
  fail-closed on gates stays intact.
- No `render_merged_diff` change: the synthetic arm already emits `+++ b/`
  (:573/:579); the verbatim arm passes bare diffs through, which `audit_diff`
  now attributes — the two agree post-fix. Only `auditor.py` is modified
  (below all W1-pinned ranges); `dialectic_runner.py` untouched.
- The "2-byte contrast" reading: post-fix, bare AND `b/` shapes both scan
  (the contrast collapses — the pre-fix bare→skip IS the bug). Tests assert
  both shapes yield the `ZERO_MOCK_VIOLATION` finding on the J1 contrast
  bytes, plus: clean bare diff → APPROVED (no over-attribution), `/dev/null`
  exclusion, multi-file bare attribution, gate-failure fail-closed intact
  (red receipt + bare diff → SUBSTRATE_GATE_FAILURE still present).
- Test placement: appended to `tests/unit/test_judiciary.py` (green
  baseline: judiciary+a3 = 35 passed), reusing `_make_valid_receipt` /
  `_make_task_bundle`.

## B2 proof plan (0 CLI calls)

Per-workstream new tests green + every suite importing a touched module
rerun, live-deselected, BOTH interpreters (joint 3.12.3 / real-gates 3.11.15,
prior PYTHONPATH shapes, `PYTHONDONTWRITEBYTECODE=1`, cwd `ws/stc`) + `ruff
check`/`format` + `mypy --strict` on every owned file + sst clean +
tracked-diff audit. Reuse valid prior evidence (veto 61/61 stands for
untouched paths); test_substrate before/after comparison for W4 no-change
proof. Hash Identity for every file created/modified. No commits, no
STATE.md writes; sst/prompt-kit/trace read-only; `trace-lite/` never
touched. Spend 0 (tranche 8/20, 6 hard reserve untouched).
