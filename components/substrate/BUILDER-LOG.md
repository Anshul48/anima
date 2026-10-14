# BUILDER-LOG.md — anima-substrate consolidation builder log

Resumed consolidation (prior builder died on transient provider-network
error; its partial `src/` work survived). This log records commands,
counts, and failures. All commands run from the workspace root
(`<workspace-root>/substrate`)
unless noted. Tooling: `./.venv` (pytest/ruff/build). Package is
stdlib-only, offline, $0.

## 2026-10-07 — resume + survey

- `ls` survey: `src/anima_substrate/` present (host/ 10 modules,
  participants/sched/, demos/, accept/, cli.py); NO tests/,
  examples/, BUILDER-LOG.md, PROVENANCE.md. Confirmed prior-builder
  state; nothing redone.
- Coordinator docs found in-tree at
  `prototype/programme-20261004/`: CONSOLIDATION-MATRIX.md,
  LICENSE-AUDIT.md, COMPLETION-MAP.md (via refs), PREREG-LOG.md,
  S6-ACCEPTANCE.md, SUBSTRATE-SOFTWARE-MANDATE-PROPOSAL.md. Read all.
- `.venv/bin/pip install -e .` FAILED: `ValueError: Unknown classifier
  ... Topic :: System :: Recovery` (hatchling metadata validation).
  Fixed `pyproject.toml` classifier → `Topic :: System :: Systems
  Administration` (owned file; one-line fix). Re-install OK:
  `import anima_substrate` OK, version 0.1.0, `list_families()` → []
  (no family registered yet — expected; M2 work below).
- SST sibling check: `../sst` clean at `df78f42` (HEAD
  `df78f42894a65c48f524337a498032617689a013`); `../sst/.venv` python
  has pydantic 2.13.5 (== s005 pinned). Manifest recomputation over
  live `../sst/src` (read-only, s005 `make_snapshot_manifest`
  functions): 54 files, hash
  `5f1f3789...cad96` — EXACT match to
  `prototype/successor-005/vendor/SNAPSHOT-MANIFEST.json`. Caller-
  provided SST staging is therefore viable for M2 (no vendored bytes).

## 2026-10-07 — coordinator takeover (builder lost twice to infra)

- Prior builder died on transient provider-network error; resumed
  builder died on runtime restart. Both left coherent shared-tree work;
  coordinator verified state directly and finished the remainder.
- Fixes by coordinator: hatchling src-layout config (wheel shipped
  empty — removed `targets.*.packages`); curated sdist include+exclude
  (10.6MB → 242KB, zero prototype/.venv/pycache leaks); durability
  wording disclaimer in `host/api.py` (procedure wording test red→green)
  + PROVENANCE sha refresh; SPDX headers on 47 maintained files +
  full PROVENANCE file-record recompute (39/39).
- Verified: ruff check + format clean (47 files); per-file suites green
  (families 22, m1 2+1skip, m3 15, m4 7, sst-staging 4+7skip, calibrate 2,
  conformance 9, coupling 10, fission 7, j1 6, quarantine 13+13sub,
  successor 14+3skip, atomicity 39+101sub, procedure 56+1fix→57);
  wheel install in clean room + quickstart OK + CLI smoke outside
  checkout (ephemeral /tmp venv, removed after).
- Open at handoff: full one-process `pytest tests/` (CI-equivalent);
  multi-file summary line anomaly under watch (rc=0, per-file OK).
- M4 comparison prereg: per-run filing inside test_m4_loop (prereg
  written to run dir before any comparison run — compliant by
  construction, auditor to judge).
