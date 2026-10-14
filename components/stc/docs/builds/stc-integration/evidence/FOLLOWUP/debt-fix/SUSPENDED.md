# FOLLOWUP debt-fix — SUSPENDED (operator pause, 2026-09-15T07:19:26Z)

Author role and date: coordinator / 2026-09-15
Builder session: ENDED VOLUNTARILY (child terminal, result delivered — no kill
needed). Builder's closing claim (UNREVIEWED — adopting flow must re-verify,
not inherit): "B1 readiness complete; B2 edits applied with Gates 1+2 green;
post-fix suites so far identical to baseline. Awaiting resume signal."

## What exists

- B1: `readiness.md` (drift gate zero; G1 triple-proof; ruff-`exclude`
  design adopted after E2 blocked mirror skip-set; per-debt plan; lease
  contract cited: 01_INVARIANTS.md §5 + ADR-INT-01 + `mirror_source_tree`
  code-as-contract + operator guardrail).
- Baselines: `baseline/` (18 logs: ruff-check/format, mypy, per-file
  pre-images, E2/E3/E4 dependency experiments, g2-collect, substrate2/3 pre).
- B2 partial: `attempt-1/` (10 logs: ruff-check, ruff-format, mypy,
  p01-postfiles joint+real, veto-newtests-post joint+real,
  fixture-pipeline-post joint+real, compiler-cli-post-real). NO REVIEW.md.
- Spend: 0 live calls (tranche still 8/20, 6-call reserve intact).

## Tree state at suspension (first16(sha256) : file)

- 96cf197e9b1c731b : pyproject.toml (ruff exclude ADDED)
- d0a97611358454ec : src/stc/cli.py (debt edits; was 594/0 2ddfd6cb…)
- b21be978def89287 : src/stc/compiler/bundler.py (debt edits)
- c59a8f408c0c8c5f : src/stc/judiciary/auditor.py (W5, unchanged)
- dc75c56eb48a0975 : src/stc/orchestrator/dispatch.py (unchanged 333/7)
- 8958eae167c53ffd : src/stc/substrate/runner.py (W4, unchanged)
- 93f54ff4a940cf6b : tests/integration/test_pipeline.py (debt edits)
- 168c12675c1d9e1d : tests/unit/test_cli.py (debt edits)
- bc2b355054133dea : tests/unit/test_compiler.py (debt edits)
- c87b3a74d1e653b6 : tests/unit/test_judiciary.py (W5, unchanged)
- ee60aba90d911363 : tests/unit/test_integration_adapters.py (debt edits?)
- 031bc293a9fb1684 : tests/unit/test_integration_identity.py (debt edits?)
- 143fe07b9097527a : tests/unit/test_integration_memory.py (debt edits?)
- 8bc8005dc71af8f7 : tests/unit/test_integration_dialectic.py (debt edits?)
- 6ffe08c264cc5514 : tests/integration/test_dialectic_fixture.py (debt edits?)
- 29eb3906b35a7aad : src/stc/integration/cli_gateway.py (W1+W2, unchanged)
- c072f1dac2725f47 : src/stc/integration/dialectic_runner.py (A1, unchanged)

(tracked numstat at suspension: 10 files, 1114+/14-; untracked loose set
unchanged apart from the debt files above.)

## What remains (for the adopting builder — RE-VERIFY, do not inherit)

1. Confirm every B2 edit against the B1 per-debt plan (line-by-line); finish
   any unapplied debt item; confirm pyproject exclusion byte-exact.
2. Missing post logs: substrate2/3-post, g2-collect-post, judiciary rerun,
   compiler-cli-post-joint (only real exists).
3. GREEN baseline lease gates demo (exact substrate gate commands in a
   lease-faithful mirror, both interpreters) with the honest Gate-3
   reporting rule (env/commit-blocked reds → coordinator finding).
4. DIAGNOSTIC end-to-end local proof (known-good pins diff →
   custody → gates → judiciary → champion → dossier; mutmut 30-min box or
   staged invocation). Label diagnostic, NOT live acceptance.
5. Write attempt-1/REVIEW.md (delivery + triage + Identity) and close.
6. Hand to final verification → attempt-4 → erratum + commit + report.

Resumption rule: the adopting builder runs a full drift gate (HEAD edf5389 +
all hashes above + pins + sst clean) and treats every partial log as
UNVERIFIED until reproduced or byte-reconciled. No live calls until
attempt-4. Tranche 8/20; 6-call reserve untouched.
