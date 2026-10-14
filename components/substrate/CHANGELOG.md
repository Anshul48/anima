# Changelog

All notable changes to the substrate publication package.
Format follows Keep-a-Changelog headings.

## [0.1.1] — 2026-10-08

Patch release (`v0.1.1`; `v0.1.0` preserved unchanged).

### Fixed

- Python compatibility: `requires-python` corrected to `>=3.11`
  (core modules import `datetime.UTC`, 3.11+; 3.10 installs would
  fail at import). README, classifiers, ruff target, and CI matrix
  (3.11 + 3.12) aligned; both versions verified in CI.
- `docs/ROADMAP.md`: M1–M4 now recorded as approved, implemented,
  independently accepted, and published in 0.1.0.

## [0.1.0] — 2026-10-08

First public release: `anima-substrate` maintained package (M1–M4)
plus curated research archive. Tag `v0.1.0`, commit `9d07c11`;
repo `https://github.com/Anshul48/anima-substrate`;
release `https://github.com/Anshul48/anima-substrate/releases/tag/v0.1.0`.

### Added

- `src/anima_substrate/` — persistent worlds, nested delegation,
  pinned families (`sched`, `relcheck` v1/v2, caller-staged `sst`),
  crash-atomic host, quarantine repair, portable composites,
  propose → assess → retain → reuse loop; CLI + programmatic API.
- `tests/` — 207 passed, 11 skipped (SST-conditional, explicit),
  147 subtests; ported procedure 57/57, atomicity 39/39.
- `examples/quickstart.py`, `docs/` (ARCHITECTURE, CONTRACTS,
  RECOVERY, ROADMAP, TECHNICAL-REPORT, RESEARCH-ARCHIVE, SST-STAGING).
- `LICENSE` (Apache-2.0, Copyright 2026 Anshul48), `CONTRIBUTING.md`,
  `CITATION.cff`, Linux CI (ruff + pytest + quickstart + build).

### Resolved before release

- LICENSE-AUDIT M1/M2: owner Anshul48 <anshulraj48@gmail.com>;
  agent-authored bytes assigned to owner. T2: SST bytes EXCLUDED
  (caller-staged at pinned `df78f42`, no vendored bytes, no NOTICE
  needed).
- PKG-ACCEPTANCE.md ACCEPT-WITH-NOTES: all notes closed (dist
  rebuilt byte-coherent; install + quickstart re-verified).
- CI green on `main` (`56d6693`; CI-only delta after the tag).

## History pointers (prototype programme, banked — not repackaged here)

Honest pointers to the frozen in-tree record. Each entry names the
candidate tree, its identity file, and its acceptance verdict.

- **r1** — `prototype/successor-002/` (`IDENTITY.sha256`, 41 files),
  frozen 2026-10-04. Hybrid routing, v1 + ORG-OPS contracts,
  fusion + fission + quarantine, SST-TEST from the df78f42 snapshot
  ($0). Independently accepted round 2 (ACCEPT-WITH-NOTES, notes
  fixed + coordinator-confirmed). Record:
  `prototype/release-20261004/RELEASE-RECORD.md`. Calibrate:
  `calibrate.py` 2.61x **bytes-only** (810 vs 310 canonical-JSON
  bytes, S2 envelope).
- **r2** — `prototype/successor-003/` (`IDENTITY.sha256`, 45 files),
  2026-10-04 round. Carried r1; builder A1–A10 PASS + finding F1 LOW
  (concurred); F2 LOW filed with successor fix owned. Record:
  `prototype/release-r2/RELEASE-RECORD.md`.
- **r3** — `prototype/successor-004/` (`IDENTITY.sha256`, 45 files),
  2026-10-04 round. Carried r2; A1–A10 PASS, no new product findings
  (two content-neutral file events disclosed). Record:
  `prototype/release-r3/RELEASE-RECORD.md`.
- **s005** — `prototype/successor-005/` (`IDENTITY.sha256`, 56 files).
  S5 bounded procedure participant + relcheck vehicle: 129 tests,
  57/57 procedure suite, READINESS-PASS 175.8 s. S5-A12 independently
  ACCEPTED-WITH-NOTES; S5-A10 lane-RED was environmental and NOTE-1
  gating CLOSED by coordinator READINESS-PASS (183.2 s, claims-diff 0).
  Verdict: `prototype/programme-20261004/S5-lane/VERDICT.md`.
- **s006** — `prototype/successor-006/` (`IDENTITY.sha256`, 35 files;
  manifest `48462368…`), banked 2026-10-07. Owed repairs (CC1–CC9
  coupling contract; quarantine-transfer complete/rollback) + J1
  persistent-worlds journey. Independently ACCEPTED, no notes:
  48/48 tests + 10/10 demo re-observed.
  Verdict: `prototype/programme-20261004/S6-ACCEPTANCE.md`;
  review route: `prototype/programme-20261004/S6-REVIEW-ROUTE.md`.
- **U-execute (negative, FINAL)** — real-use acceptance experiment,
  `prototype/programme-20261004/U-execute/`. Overall verdict
  **HOST-VALUE-NOT-DEMONSTRATED** (6 failing cells named): H-vs-D
  exact TIE on every rated leg (deterministic arm-invariant bytes);
  kill bar missed on both arms equally (rater variance on identical
  bytes); **change legs VOID** — adaptation UNTESTED, not disproven;
  **r5 NOT banked**. Independently accepted 2026-10-07:
  `U-execute/runs/INDEPENDENT-ACCEPTANCE.md`;
  final: `U-execute/runs/U-OVERALL-FINAL.md`.
- **Learning arc (closed negative)** — L1 negative, L2 step-0 abort,
  M1 abort; M1-redux PASSED as an instrument (MAE 0.00) — the
  negative covers transfer/invention, not the instrument. No learning
  of any kind in s005. Bounded probes only on live uncertainty.
