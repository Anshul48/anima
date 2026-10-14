# SECRET-SCAN.md — anima-release candidate scan

Scanned: 2026-10-14T10:14Z. Scanner: W3. Tree: final staged tree
(post-cleanup; re-run after commit — see method P7).

Fix-pass rescan: 2026-10-14 (focused fixer) on the sanitized tree (1289
files; operational records + 5 reflex files removed, 1 staging-hash note
added). P1 filenames + P6 non-text re-run on `git ls-files`: clean (only
`components/stc/.env.example`; no `.pem`/`.key`/`.db`/pycache/egg-info).
All content-hit files are byte-unchanged by the fix pass (only `.md`,
evidence `.log`, and 3 entorhinal test files outside the hit list were
edited; no secret-shaped content added). Verdict stands: no real secrets
ship.

## Method (all over the staged tree, no size exclusions)

- P1 filenames: `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*secret*`,
  `*credential*`, `*.pyc`.
- P2 content: `BEGIN (RSA|EC|DSA|OPENSSH)?PRIVATE KEY`.
- P3 content: `AKIA…`, `ghp_/gho_…`, `xox[baprs]-`, `sk-…`, `sk-ant-…`.
- P4 content (case-insensitive): `api_key|secret|passwd|password|bearer`
  with quoted assigned values.
- P5 content: `BEGIN CERTIFICATE`, `aws_secret_access_key` + 20 chars,
  `mongodb|postgres|mysql|redis://user:pass@`, any `-----BEGIN …-----`.
- P6: every non-text file listed for review.
- P7: after cleanup + commit, P1 re-run on `git ls-files` output.
- Masked-byte rule: my tool outputs mask secret-shaped spans as
  `[REDACTED]`, so exact bytes of some hits were unobservable to me. Those
  were forensically probed instead (length, charset distribution, fixture
  pairing, repeat count, span sha256) — noted per hit. Auditor confirms.

## Result: CLEAN — no real secrets. Hit inventory (all classified)

Filenames (P1): no `.env`/`*.pem`/`*.key`/`id_rsa*` anywhere. Only
`components/stc/.env.example` (clean template: empty key values, verified).
`*.pyc`/`__pycache__` from my own test runs — deleted before commit.
Non-text files (P6): only those same `.pyc` (deleted) + empty `py.typed`.

Content hits — every one is a synthetic redaction-test vector or a false
positive; each file now carries an in-tree synthetic-provenance label
(`SYNTHETIC PROVENANCE`, 9 files) or was already self-labeled (2 files):

| File:lines | Pattern | Classification + basis |
|---|---|---|
| entorhinal `src/.../evals/privacy_stress.py:10,103,120,141` | P2/P3/P4 | Synthetic: generator emits `fakeRSAKeyForTestingOnly…`, `sk_test_…` fakes; docstring-labeled. |
| entorhinal `src/.../fixtures/golden.py:39` | P3 | Synthetic: 40-char Bearer stub, 0 dots (not a JWT), numeric-filler body (36 digits); module declares synthetic corpus. Bytes masked in my view (span sha `91303c1d…`); auditor confirms. |
| entorhinal `src/.../fixtures/golden.py:371,1725` + `tests/test_phase1…:329,332` + `cli/init_wizard.py:540` | P3/P5 | Synthetic: AWS documentation EXAMPLE key pair (`AKIA…EXAMPLE` ×1–2 per file, verified by count); init_wizard carries the EXAMPLE pair but NOT the exact `SYNTHETIC PROVENANCE` label (corrected — label count is 9 new + 2 pre-existing). |
| entorhinal `src/.../fixtures/golden.py:1559` | P3 | Synthetic: `ghp_`+36 digits (all-numeric body, not random PAT alphabet); paired with `<REDACTED:GITHUB_TOKEN>` expectation, `pii_redacted:true`. Bytes masked (span sha `5d69059f…`); auditor confirms. |
| entorhinal `src/.../fixtures/golden.py:1756,1979,2010,2020` | P2/P3/P4 | Synthetic: truncated fake PEM; 43-char numeric-filler Bearer (0 dots) paired with `<REDACTED:OPENAI_API_KEY>`; literal sequential `sk_live_51AbcDef…` fake + redacted pair. |
| entorhinal `src/.../fixtures/golden.py:214,413,423` | P4 | Synthetic: `SuperSecretPassword!`, `sk-test-…` / `<REDACTED:…>` input→output pairs. |
| entorhinal `tests/test_phase1…:251,269,365,371,397` | P2/P4 | Synthetic: `my-master-password`, `SuperSecret*`, truncated fake PEM, `secret-12345678`; labeled. |
| entorhinal `tests/test_temporal_cutoff.py:325,335` | P4 | Synthetic: inert `redacted-ok` placeholders; labeled. |
| entorhinal `tests/test_dev_task_repair.py:34` | P3 | Synthetic: `FAKE_SECRET = "ghp_" + "Q"*32` (already self-labeled). |
| entorhinal `tests/test_integration_security…:224,240,245,461` | P4 | Synthetic: `MyUltraSecret…`, `[REDACTED]`, `classified_data` vectors; labeled. |
| reflex `tests/test_privacy_redactor.py:32,134-137,181-182` + docstring L3 | P3/P4 | Synthetic: 6-char Bearer stub (length-proven), `My$ecr3tP@ss`, `ClearTextPassword!`, 4 literal `[REDACTED]` markers; labeled. |
| reflex `tests/test_trace_bridge.py:107,109,120` | P3/P4 | Synthetic: `my_secret_pass123`, `raw_secret_value` with redact-asserts; ≤12-char token span; labeled. |
| sst `tests/unit/test_custody.py:76`, `test_evaluator.py:103`, `test_wave2_cli_json.py:136` | P3/P4 | Synthetic: literal `[REDACTED]` placeholders (verified counts); labeled. |
| stc `tests/unit/test_worktree.py:793` | P3 | False positive: branch name `…/stc-task-unrecorded-e2` matches `sk-`+8 pattern. |
| stc `dsh-plugin-stc/scripts/pilot-tasks.py:382` | P3 | False positive: English word `task-specific` in a comment. |
| stc `dsh-plugin-stc/scripts/live-pilot.py:242` | P4 | Benign: `line.startswith("…_API_KEY=")` — code logic, no values. |

Docs/provenance/config (`docs/`, READMEs, `pyproject.toml`s, `uv.lock`s,
`receipt.json`, pin JSONs): zero hits. `.env` contents were never read;
`relfex/.env`, `sst/.env`, `stc/.env` exist upstream only and are excluded.

## Verdict

No credentials, private keys, tokens, connection strings, or private-data
files ship. All pattern hits are synthetic vectors with in-tree labels
(9 new + 2 pre-existing) or demonstrated false positives. Auditor to
confirm the three masked-byte spans via recorded hashes.
