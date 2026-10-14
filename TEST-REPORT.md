# TEST-REPORT.md — ANIMA candidate verification

Staged: 2026-10-14T10:14Z. Runner: W3. Host: Linux, CPython 3.12.3.
Envs: `/tmp/anima-smoke-venv` (root+substrate+sst), `/tmp/sst-pin-venv`
(sst frozen lock), `/tmp/anima-clean-venv` (clean-state full install).
Sandbox note: localhost HTTP tests need `NO_PROXY`/`no_proxy` bypass for
`127.0.0.1,localhost` (proxy env otherwise returns 502); applied below.

Fix pass: 2026-10-14 (focused fixer). Docs/curation/test-guard changes only;
no product algorithm edits. Re-verified rows 3, 4, 9, 11 in
`/tmp/anima-clean-venv` plus new rows 13–16. Rows 1, 2, 5–8, 10, 12 are
W3's original receipts, preserved; row 7's exit code is corrected (was
masked by the shell pipeline).

## Results (command → exit → outcome)

| # | Command (cwd) | Exit | Result |
|---|---|---|---|
| 1 | `pip install -r requirements/components-all.txt` (repo root, fresh venv + real pip 26.2.1) | 0 | all 6 dists built + installed: anima, anima-substrate, sst-engine, stc, entorhinal, reflex |
| 2 | `python -m pytest tests/ -q` (root, smoke venv, substrate only) | 0 | 4 passed, 4 skipped (aliases absent → skip, as designed) |
| 3 | `python -m pytest tests/ -q` (root, clean venv, all installed) | 0 | 8 passed, 0 skipped (re-verified in fix pass) |
| 4 | `import anima_substrate, sst, stc, entorhinal, reflex` + `import anima.<each>` (clean venv) | 0 | all native + alias imports OK; `anima.components()` all True (re-verified; entorhinal legacy no-auth banner prints, as documented) |
| 5 | `python components/substrate/examples/quickstart.py` | 0 | quickstart OK 7/7 (init, relcheck, byte-identical reopen, recover, settle) |
| 6 | `pytest tests/ -q` (components/substrate) | 0 | 207 passed, 11 skipped, 147 subtests passed (454s) |
| 7 | `pytest tests/ -q` (components/sst, latest-dep env) | 1 (pytest; pipeline printed 0) | 158 passed, 3 failed → localhost proxy artifact (see 8). CORRECTED: the original row claimed exit 0 because `| tail` without `pipefail` masked pytest's status; pytest exits 1 when any test fails. Failure cause stands (proxy), only the recorded exit was wrong. |
| 8 | `pytest tests/ -q` (components/sst, frozen-lock env + NO_PROXY) | 0 | **161 passed** — exact parity with CUT1 pin record |
| 9 | `pytest tests/unit/test_schemas.py -q` (components/stc) | 0 | 37 passed (re-verified in fix pass) |
| 10 | `pytest tests/test_fact_identity.py -q` (components/entorhinal) | 0 | 9 passed |
| 11 | `pytest tests/test_privacy_redactor.py -q` (components/reflex) | 0 | 14 passed, 11 subtests passed (re-verified in fix pass) |
| 12 | `anima-substrate --help`, `sst --help`, `stc --help`, `entorhinal --help`, `python components/reflex/main.py --help` | 0 | all CLIs respond (reflex has no installed console script; entry point is `main.py`) |
| 13 | `pytest tests/test_phase4_user_control_and_evals.py::test_evaluation_runner_track1_and_track2 -q` (components/entorhinal, clean venv) | 0 | 1 skipped: Track 1 + NOT_RUN + BLOCKED legs pass, consented-corpus PASS leg skips (fixture deliberately excluded; product BLOCKED behavior and F1≥0.88 / P≥0.85 / ECE≤0.10 thresholds unchanged) |
| 14 | `pytest tests/test_vnext/test_conformance.py tests/test_truth_checker.py tests/test_fact_identity.py -q` (components/entorhinal, clean venv) | 0 | 29 passed, 2 skipped: conformance passes via shipped repo-relative corpus (byte-identical to upstream); 2 Desktop-experiment tests skip publicly by design (machine path redacted) |
| 15 | tracked-tree relative-link resolver over all `*.md` | 0 | 0 broken across 245 files (132 repaired to shipped targets, remainder converted to plaintext historical refs with per-file curation notice) |
| 16 | P1 filename rescan on final tree (`git ls-files`) | 0 | clean: no `.env`/`*.pem`/`*.key`/`id_rsa*`/`*.db`/pycache/egg-info/`consented_trace`; only `components/stc/.env.example` |

## Scope honesty

- Full suites run: root, substrate, sst (W3 receipts; not re-run in the fix
  pass — no algorithm or dependency changes).
- Smokes re-verified in fix pass (rows 3, 4, 9, 11, 13, 14): root 8,
  imports/components, stc schemas 37, reflex redactor 14+11sub, entorhinal
  guard + conformance/truth/fact-identity 29+2skip.
- Not run: stc/entorhinal/reflex full suites (time-boxed per brief: small
  meaningful smokes; pin records + upstream CI qualify sst/stc pins).
- EXCLUDED, not claimed as passing: 4 reflex test files whose bodies were
  `pass`-only upstream (`test_adversarial_context_bridge`,
  `test_ecosystem_adapters`, `test_fakes_standalone_smoke`,
  `test_integration_security_and_failure`) plus `clear_failing_tests.py`
  (the script that stripped them). Quarantine copies preserved privately;
  genuine prior bodies were not available offline, so nothing was restored
  and no qualification is claimed over those files.
- Entorhinal Track 2: the PASS leg requires the deliberately excluded
  private consented corpus, so it skips when the fixture manifest is absent
  (row 13). The BLOCKED-without-manifest product behavior is still
  asserted by the same test; thresholds unchanged.
- 9 comment-only `SYNTHETIC PROVENANCE` labels were added to redaction-test
  files (see SECRET-SCAN.md; corrected from "10" — 9 new + 2 pre-existing);
  the sst label edits predate run 8 (161/161 ran on labeled tree).
- Residue: fix-pass runs used `PYTHONDONTWRITEBYTECODE=1` and
  `-p no:cacheprovider`; no `__pycache__`/`.pytest_cache` left in-tree.
  Worktree clean at commit.

## Professional publication pass on public `5cf1708` (2026-10-14)

Documentation/licensing/metadata/CI-only descendant of
`5cf1708a1587caa6fd3b248071f0f384216b5e56`; no component source, fixture,
or dependency edits (one metadata exception: the placeholder
`entorhinal` pyproject description replaced with a real one). Targeted
verification in a fresh `uv venv --seed` (CPython 3.12), not the whole
legacy suite:

| Check (cwd: repo root) | Exit | Result |
|---|---|---|
| `pip install -e . -e components/substrate pytest` | 0 | root + substrate dists installed |
| `python examples/quickstart.py` | 0 | availability report; relcheck `valid=True checked=2`; close/reopen byte-identical; `ANIMA quickstart OK` |
| `python components/substrate/examples/quickstart.py` | 0 | `quickstart OK`, settle stranded=0 |
| `pytest tests/ -p no:cacheprovider` | 0 | 4 passed, 4 skipped (skips = components not installed in this venv) |
| `pytest components/substrate/tests/ -q -p no:cacheprovider` | 0 | 207 passed, 11 skipped (progress markers; quiet mode) |
| all 6 `pyproject.toml` parse + license field | 0 | every file declares `Apache-2.0` |
| `LICENSE` files | 0 | root/substrate/sst/entorhinal/reflex byte-identical Apache-2.0; stc keeps its upstream Apache-2.0 copy (`Copyright 2026 STC Contributors`) |
| SVG parse (`assets/*.svg`) + relative-link check (README, `docs/ARCHITECTURE.md`, `docs/CODE-TOUR.md`) | 0 | well-formed; 0 bad links |
| fixture byte-exactness vs `5cf1708` | 0 | `golden.py` blob `03431009…`, `test_integration_security_and_failure.py` blob `5c00892f…` — identical before/after |
| no-deletion inventory vs `5cf1708` | 0 | `git diff --diff-filter=D` empty; every `5cf1708` tracked path present |
| secret scan | 0 | filename scan clean (only `stc/.env.example`); no `sk_live_`/`sk_test_…` literals in `components/ src/ tests/ examples/` |

Note: full all-components install/test was verified for the identical
professional file set in the earlier (superseded-base) pass and runs in
CI (`.github/workflows/ci.yml`); it was not repeated here per the
targeted-verification scope.
