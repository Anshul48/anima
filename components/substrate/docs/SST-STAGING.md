# SST-STAGING.md — caller-staged SST optional extra (M2)

The base package is stdlib-only and ships NO SST bytes and NO
pydantic. The SST search leg runs only over a caller-staged SST
checkout that passes the compat probe; otherwise every SST entry
point refuses loudly BEFORE any SST import.

## 1. Pin (all three must hold)

| item | pinned value |
|---|---|
| SST commit | `df78f42894a65c48f524337a498032617689a013` (`df78f42`) |
| snapshot (construction `substrate-snapshot-v1`) | 54 files, hash `5f1f37893b0f5ab9ff7dcf0ce2c60b287b51647e2f18f627eabf5510537cad96` |
| pydantic (SST interpreter) | exactly `2.13.5` |

The pinned manifest (relpaths + sha256, no bytes) ships at
`participants/sst/SNAPSHOT-MANIFEST.json`. Label everywhere:
SUBSTRATE-QUALIFIED SNAPSHOT — NO SST-OWNER RELEASE ACCEPTANCE.

## 2. Stage

```
# 1. check out SST at the pin (read-only use; we never write there)
git clone <sst-remote> /path/to/sst
cd /path/to/sst && git checkout df78f42894a65c48f524337a498032617689a013

# 2. SST interpreter with the pinned pydantic
python3 -m venv /path/to/sst/.venv
/path/to/sst/.venv/bin/pip install 'pydantic==2.13.5'

# 3. point the package at the staging
export SUBSTRATE_SST_ROOT=/path/to/sst
export SUBSTRATE_SST_VENV_PY=$SUBSTRATE_SST_ROOT/.venv/bin/python  # optional override
```

`SUBSTRATE_SST_VENV_PY` defaults to
`$SUBSTRATE_SST_ROOT/.venv/bin/python` when unset.

## 3. Probe

```python
from anima_substrate.participants.sst.staged import probe
rep = probe()  # uses SUBSTRATE_SST_ROOT / SUBSTRATE_SST_VENV_PY
assert rep["verdict"] == "MATCH"
```

The probe checks, in order: root present → snapshot MATCH (54
files, byte pin) → git HEAD == pin when `.git` is staged (exports
without `.git` rely on the byte pin, reported) → interpreter
present → pydantic == 2.13.5. First failure raises `SSTBoundary`
naming it. Consumption (`run_tasks(..., with_sst=True)`,
`sst@v1` family, `run_demo` SST stage) re-verifies pre AND post
run; any drift aborts with the file list.

## 4. Upgrade (re-pin procedure)

A new SST pin is a re-qualification, never a silent bump:

1. Check out the candidate commit; rebuild the venv at whatever
   pydantic the candidate qualifies with.
2. Regenerate a candidate manifest with
   `participants/sst/manifest.py:write_manifest` (staging tooling,
   writes outside the package).
3. Run the FULL suite with the candidate staged
   (`tests/test_successor.py` SST legs + `tests/test_sst_staging.py`
   + `TestRunDemoStaged`): every leg must pass unmodified except
   the pin constants.
4. On green: update `PINNED_SST_COMMIT`, `PINNED_SNAPSHOT_HASH`,
   `PINNED_PYDANTIC`, `SNAPSHOT-MANIFEST.json` in ONE change, file
   a contract delta in `docs/CONTRACTS.md`, and keep the old pin
   reproducible (old manifest + old checkout still verify —
   the verifier takes an explicit manifest path for exactly this).
5. On any red: the candidate is NOT adopted; the old pin stands.

## 5. Troubleshooting

| symptom | cause → fix |
|---|---|
| `SUBSTRATE_SST_ROOT unset` | no staging → stage per §2 or drop `with_sst` |
| `staged tree missing: .../src/sst` | wrong root → point at the checkout (parent of `src/`) |
| `changed bytes (...): <files>` | checkout drifted → `git status` + restore, or re-stage clean |
| `extra files (...): ...__pycache__...` | never happens (`__pycache__` excluded); any other extra → remove it |
| `pydantic X != pinned 2.13.5` | wrong interpreter → use the §2 venv (re-qualification required for any other version) |
| `HEAD ... != pinned ...` | checkout moved → `git checkout df78f42` |
| child `rc=...` / envelope errors | SST-side failure → the error quotes child stdout/stderr; fix staging, never the snapshot |
