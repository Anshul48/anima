# STC offline operation — clean-checkout setup (verified 2026-09-22)

Reproduces the offline verification environment from a bare clone.
Zero live calls. Verified end-to-end on a fresh clone at `3263569`
(all commands below ran green there unless noted).

## 0. Prerequisites

- Python 3.12 (`python3 --version` → 3.12.x), `git`, `uv` on PATH.
- Network for the one-time `uv sync` fetch (or a warm `UV_CACHE_DIR`).
- The sibling checkouts this workspace assumes: `sst`, `prompt-kit`,
  `trace` next to `stc` (only `sst` + a prompt-kit PIN are on the
  offline path; `trace` is a roots-formality).

## 1. Clone + environment

```sh
git clone <stc-remote-or-bundle> stc && cd stc
git checkout -q 3263569   # or later; this doc was verified at 3263569
uv sync --locked          # builds ./.venv (44 packages, Python 3.12)
```

Equivalence check (fresh env must equal the tranche baseline env):

```sh
.venv/bin/python -c "
from importlib.metadata import distributions
ds = sorted((d.metadata['Name'], d.version) for d in distributions())
print(len(ds))"   # expect 42
```

## 2. External roots (pins)

```sh
# sst: sibling checkout at 079f4de6 (clean). No code pin; record the sha.
git -C ../sst rev-parse --short HEAD   # expect 079f4de

# prompt-kit: PRISTINE pin clone at 4f442a6c (the F3c test fails closed
# if prompt_kit resolves to the dirty sibling worktree instead).
git clone <prompt-kit> <pin-dir> && git -C <pin-dir> checkout -q 4f442a6c
git -C <pin-dir> status --porcelain | wc -l   # expect 0
```

## 3. Session environment

```sh
export PYTHONPATH="<sst>/src:<pin-dir>"
export STC_PROMPT_KIT_ROOT=<pin-dir>
export STC_SST_ROOT=<sst> STC_TRACE_ROOT=<trace> STC_WORKSPACE_ROOT=<workspace>
```

`STC_PROMPT_KIT_ROOT` must equal the pin dir: the lease
import-integrity proof rejects ambient PYTHONPATH entries outside the
enumerated roots (Q3), and drivers assert the resolved `prompt_kit`
lives under the pin.

## 4. Gates (fast, deterministic)

```sh
cd stc
.venv/bin/ruff check . && .venv/bin/ruff format --check .   # 114 files
.venv/bin/python -m mypy --strict src tests                 # 75 files
```

Caveat: a stale `.mypy_cache` (gitignored) built WITHOUT the pin on
the path poisons later runs with `import-not-found` on the two
`prompt_kit` imports. If Gate 2 reports those, `rm -rf .mypy_cache`
and re-run — the source ignores (`[import-untyped]`) are correct for
the documented env.

## 5. Offline test baseline (`-m "not live"`)

```sh
.venv/bin/python -m pytest tests/ -m "not live" -q -p no:cacheprovider
```

Expect green. Timing notes (this box, slow /mnt/c mount):

- Full unit+integration sweep ≈ 40–60 min; run chunked if needed
  (per-file, or per-test for `test_dag_pipeline.py`).
- `test_cli_run_json_mode` ≈ 130 s (strict confinement audit
  double-walks the checkout — characteristic, not a hang).
- `test_integration_dialectic.py` legs ≈ 5–35 s each (real gate
  subprocesses); `test_stc_source_real_gates_green_path` ≈ 220 s.
- Live-marked tests deselect; the F3c pin test + zero-call tripwires
  (`test_run_e2e.py`) prove the offline property.

## 6. What is NOT covered here

- Live qualification (`stc run --target stc` without `--dry-run` /
  `--manual`) needs SEPARATE authorization + budget + operator
  supervision — see the attempt-4 RUNBOOK, §4/§5 stops.
- `test_integration_runner_pins.py` (P05 spec committed at
  `specs/p05-acceptance.md`) was never built — out of scope for the
  offline tranche; the attempt-4 launch red-check asserted its absence.
- `store.db-shm`/`-wal` under evidence are SQLite transients: never
  commit, safe to leave untracked.
