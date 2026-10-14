# Contributing to anima-substrate

The maintained package lives in `src/anima_substrate/` (see
`pyproject.toml`); `prototype/` holds frozen research generations
plus programme records. Contract and evidence rules below are
summaries — the in-tree contracts and acceptance records govern.

## Dev setup

- Target: Linux/Ubuntu, Python 3.11–3.12, `$0`, offline base.
- The repo root carries a project virtualenv at `.venv/`. If it is
  absent, create it (Ubuntu ships `python3` without pip):

```sh
python3 -m venv --without-pip .venv
curl -sL -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
./.venv/bin/python /tmp/get-pip.py
./.venv/bin/python -m pip install -e . pytest ruff build
export PYTHONDONTWRITEBYTECODE=1
```

- Do not create the project env in `/tmp`, and do not install into
  the system interpreter.
- Runtime code is **stdlib-only** (`dependencies = []`). The SST
  participant stages a caller-provided SST checkout at the pinned
  commit and shells to the caller's interpreter for `pydantic`
  legs (see `docs/SST-STAGING.md`). Never vendor third-party
  packages in-tree.

## Test commands

```sh
./.venv/bin/python -m pytest tests/ -q          # full suite (~16 min)
./.venv/bin/python -m pytest tests/test_families.py -q   # fast subset
./.venv/bin/python examples/quickstart.py       # consumer journey
```

- SST-conditional tests skip with an explicit reason when no SST
  root is staged; skips are reported separately, never silent.
- Full reproduction index (all generations): `REPRODUCE-ALL.md`.
- Consumer/reviewer entry point: `docs/REVIEW.md`.

## Lint

```sh
./.venv/bin/python -m ruff check src tests examples
./.venv/bin/python -m ruff format --check src tests examples
```

Same gate runs in CI (`.github/workflows/ci.yml`, Python 3.11 +
3.12). Keep the tree warning-clean; no blanket suppressions, no
dropped tests to manufacture green.

## Contract-change policy

1. **Frozen trees are read-only.** Banked generations
   (`successor-002` … `successor-006`, `release-*`, `H2-lane`,
   `U-execute` finals) are never edited; new work copies forward into
   a new tree with a `PROVENANCE.md` copy-forward record and per-file
   adaptation list (see `prototype/successor-006/PROVENANCE.md`).
2. **Contract edits need a delta.** Changes to
   `WORLD-CONTRACT-v1.md`, `ORG-OPS`, the CC1–CC9 coupling contract,
   or any frozen predicate/checker file require a filed contract delta
   (or `RULES-AMENDMENT` entry for experiment rules) **before** the
   code change; silent repair is forbidden.
3. **Prereg before execution.** Experiments file a hash-chained
   `PREREG-LOG` entry + countersign before the first non-throwaway run;
   predicate edits after filing mean a new entry + re-freeze.
4. **Banking is routine**, not an architectural decision: identity
   file + manifest + untouched predecessors, unless an explicit freeze
   hold says otherwise.
5. **Envelope discipline.** Every claim states its envelope
   (single-host, toy scale, TEST-only SST, process-crash-only, no
   fsync unless stated). Out-of-envelope behavior is unpromised; new
   paths file their own `LIMITS.md`.

## Evidence standards

- Re-run through **consumer interfaces on fresh state**; auditor
  state goes under `runs/` (fresh dirs) and `/tmp` only.
- Prove bytes before behavior: `sha256sum -c IDENTITY.sha256`
  (and snapshot-manifest checks where an SST leg exists).
- Independent acceptance lane before any banked claim: the auditor
  re-runs eval/derive/blinding from filed bytes and files their own
  verdict (precedent: `S6-ACCEPTANCE.md`, `U-execute/runs/
  INDEPENDENT-ACCEPTANCE.md`).
- Report negatives honestly and keep them: failed cells, VOID legs,
  superseded records (`.superseded-void`), and rater/auditor warts
  stay in the record with their cause named.
- Byte results are calibrated as bytes only — no token, attention,
  cost, or intelligence conversions (precedent: R8 `2.61x
  (bytes-only)`).
- No learning/discovery verbiage without a discriminating protocol:
  the Q4 negative and D-005 signal semantics bind all future work;
  no runs without a new hypothesis.
- Held-out authorship + sealed envelope + disclosed throwaway
  validation for any graded change content.
