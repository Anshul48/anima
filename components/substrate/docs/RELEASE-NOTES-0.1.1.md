# anima-substrate 0.1.1 (patch)

Correctness patch over 0.1.0 (`v0.1.0` preserved unchanged).
No behavior change: shipped code is identical except the version
string.

## Fixed

- Python compatibility: `requires-python` corrected to `>=3.11`.
  Core modules import `datetime.UTC` (introduced in 3.11), so the
  0.1.0 metadata (`>=3.10`) would have failed at import on 3.10.
  README, classifiers, ruff target, and CI matrix aligned.
- `docs/ROADMAP.md`: M1–M4 recorded as approved, implemented,
  independently accepted, and published (was: awaiting approval).

## Verification (observed, 2026-10-08)

- CI matrix green on this commit: `linux (3.11)` + `linux (3.12)`
  (ruff + full suite + quickstart + build).
- Wheel metadata: `Version: 0.1.1`, `Requires-Python: >=3.11`.
- Clean-room wheel install + quickstart OK.

## Assets

- `anima_substrate-0.1.1-py3-none-any.whl`
- `anima_substrate-0.1.1.tar.gz`
- `SHA256SUMS.txt`

License: Apache-2.0. Tag `v0.1.1`.
