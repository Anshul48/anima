# anima-substrate 0.1.0 (alpha research artifact)

Small, offline, stdlib-only Python host for persistent project worlds:
nested delegation, pinned participant families, crash-atomic local
state, fusion/fission/quarantine, portable composites, and an
evidence-grounded propose → assess → retain → reuse loop.

## Install

```
pip install anima_substrate-0.1.0-py3-none-any.whl
python -c "import anima_substrate; print(anima_substrate.__version__)"
```

Linux/Ubuntu + Python 3.10–3.12 (verified on 3.12). Zero runtime
dependencies. Quickstart: `examples/quickstart.py` in the sdist,
or the README journey.

## Verification (observed, 2026-10-08)

- Full suite: 207 passed, 11 skipped (SST-conditional, explicit
  reasons), 147 subtests passed, 0 failed.
- `ruff check` + `ruff format --check`: clean (48 files).
- Independent acceptance: ACCEPT-WITH-NOTES
  (`prototype/programme-20261004/PKG-ACCEPTANCE.md`), all notes
  closed before this tag (dist rebuilt byte-coherent, install +
  quickstart re-verified from the final artifacts).
- Wheel/sdist contents verified: 31 py + 8 JSON fixtures + LICENSE,
  no leaks; sdist rebuilds a wheel; clean-room install + CLI smoke
  outside the checkout.

## Limitations (envelope)

Single host, toy scale, process-crash-only (no fsync). No
cross-host, multi-writer, or disk-loss tolerance. No learning of
any kind. STC material explicitly unqualified (full-replay only).
See README + `docs/ROADMAP.md` for the full ambition vs delivered
scope, including the preserved U-experiment negative and VOID
adaptation legs.

## Assets

- `anima_substrate-0.1.0-py3-none-any.whl` — installable wheel
- `anima_substrate-0.1.0.tar.gz` — source distribution
- `SHA256SUMS.txt` — checksums

License: Apache-2.0. Commit `9d07c11`, tag `v0.1.0`.
Note: CI workflow fix (`pip install -e .` before tests) landed in
`56d6693`; `main` is green. Shipped code is identical in both
commits (CI-only delta); the tag stays on the accepted candidate.
