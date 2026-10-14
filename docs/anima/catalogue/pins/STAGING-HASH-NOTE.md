# Staging hash note (STC CUT2 pin vs staged tree)

The pin file `construction.stc.1f93f15c.json` is preserved byte-identical to
the historical record; its hashes were NOT rewritten. One of its eight
file hashes does not match the staged tree. This note records both values
and the reason.

## The stale entry

File: `components/stc/04_DATA_CONTRACTS_AND_SCHEMAS.md`
(`construction.stc@1f93f15c`, frozen 2026-10-06)

- Historical pin value (in JSON, pre-commit working-tree state):
  `fc0de3669c10da9382787d04b203b7f5d0346ae9b2cadf55df8e4e036a74082`
- Actual staged-tree sha256 (git-archive of pin commit `1f93f15c`):
  `fc0de3669c10da9382784df2dfe2acebb19e68ae1d0981f9a91e02700ca74082`

## Why they differ

The pin JSON itself states the cause (approval condition C-C2-2): "pins sit
pre-commit in working tree". The recorded hash reflects the freeze working
tree; the staged tree holds the committed bytes of `1f93f15c`. Uniform
archive mtimes (2026-10-06T21:52, the pin commit time) and the correctly
absent post-pin `STC-COORDINATOR-PROMPT.md` confirm the staged tree is the
true pin commit — so the file was intentionally left unchanged and the
historical criterion was not quietly rewritten.

## Current match table (7/8)

| Pinned file | Pin JSON | Staged tree | Status |
|---|---|---|---|
| sst `docs/03_DATA_CONTRACTS.md` | `fb36ce2a…` | same | MATCH |
| sst `src/sst/search/policy.py` | `a7b7f68a…` | same | MATCH |
| stc `01_PLAN_BROAD_STROKES.md` | `025282f9…` | same | MATCH |
| stc `04_DATA_CONTRACTS_AND_SCHEMAS.md` | `fc0de366…7d04b…` | `fc0de366…4df2d…` | STALE (pre-commit state, see above) |
| stc `docs/STC-DSH-RECORD.md` | `3e146827…` | same | MATCH |
| stc `docs/STC-DSH-RELEASE.md` | `4f2f4a53…` | same | MATCH |
| stc `docs/STC-SST-CALLER-CONTRACT.md` | `a7ac87f3…` | same | MATCH |
| stc `src/stc/schemas/models.py` (TaskBundle) | `da7a958d…` | same | MATCH |

Reproduce: `sha256sum` each staged path and compare with the two pin JSONs
in this directory. Frozen contract docs ship byte-identical to the pin,
including historical absolute workspace links inside `STC-DSH-RECORD.md`
(frozen evidence, not live paths).
