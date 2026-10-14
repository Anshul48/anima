# FOLLOWUP a1-fix — Readiness (B1)

Record type: builder readiness
Author role and date: a1-fix-builder / 2026-09-14
Packet: STC follow-up tranche, A1-fix stage (fix the unbounded recursive
self-copy in `mirror_source_tree` that stalled accept attempt-1; 0 live
calls this stage).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (9 hashes re-verified byte-exact below, zero drift).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Gate 0 — Predecessor gates (full read, nothing inherited)

| Record | Outcome carried |
| --- | --- |
| `evidence/FOLLOWUP/accept/attempt-1/REVIEW.md` | **AUTOMATION-NOT-READY (honest partial)**: gateway leg WON on medium (43.1 s valid §2, P2-H3a live); first verify stalled 40 min in A1 unbounded recursive mirror (depth 7, 1.232 GB, 31 min zero-event); external stall-break fully logged; pipeline fail-closed per contract (quarantine + `VERIFIER_FINISHED` fail + `BUDGET_EXHAUSTED` + NEEDS_REPAIR). Finding **A1** (critical, this stage's target) + **A2** (info, header gap, assessed below) + F2 cosmetic carried. |
| `evidence/FOLLOWUP/accept/readiness.md` | B1 READY precedent: zero drift, dry-run chain, seeded-medium proven on the real login, winner 6/6. Live-leg shape (P05-final + `--choice 1`, real-gates, in-repo dossier) is the layout that triggers A1. |
| `evidence/FOLLOWUP/winner-carry/verify-1/REVIEW.md` | **PASS**: carry-owned `cli.py 2ddfd6cb…d82f1` + `test_winner_carry.py 0b5c3a8a…69762` verified; 7/7 non-hunk files drift-free at tasked hashes; ruff green; mypy strict clean on hunk (5 pre-existing off-hunk, causation-proven). |
| `src/stc/integration/dialectic_runner.py` | `mirror_source_tree` (:283-295), `_MIRROR_SKIP_DIRS` (:278-280), lease creation + both mirror call sites (:438-445 wrapper lease, :814-815 merged), catch-all quarantine (:487-497), `_lease_path` (:499-505) — all read in full. |
| `tests/unit/test_integration_dialectic.py` + `tests/integration/test_dialectic_fixture.py` | Lease/mirror coverage read in full: every existing lease lives OUTSIDE its fixture source tree (unit: `tmp_path/"leases"` vs `tmp_path/"src"`; fixture: same split; live `test_live_cli_node`: `tmp_path/"leases"` vs `tmp_path/"src"`) — the suites are structurally blind to dst-inside-src, matching the A1 diagnosis. |

## Gate 1 — Drift gate (re-verified this session, STOP on unexplained drift)

- HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` = tasked base. ✓
- 9/9 file hashes byte-exact at tasked values (full sha256 this session):
  `cli.py 2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1`
  (numstat 594/0),
  `test_winner_carry.py 0b5c3a8a85dea963ef8b95e43679bc504020152d105e89a2aaef05b677b69762`,
  `harness_worker ced79ed572d50f5c67d7e8556fe08127f59e0c529fc50bdaf1bc6898805a7867`,
  `cli_gateway f9dda17ec411c567dfccc51515cedfa69d79b75a6effd2c6e75c72ec76207b8a`,
  `test_harness e96db8d00a2950166f77ec6069ab98d9a944a344bfb452a4ffb7e6f3ce070b45`,
  `dialectic_runner 19a2e448553c221260071b1d8509fe62749d96548cb5220f2083eec33848283b`,
  `test_dialectic 6e059f08e203478f3a70489b99385dc5a81a09386c274baf16a83e2c76bf1019`,
  `__init__ 105714219afcfbef9c81c50ce4216de4ce93096482aff2a4597cb4aaf04bac40`,
  `dispatch.py dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7`
  (numstat 333/7). ✓
- Pins exact: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32`,
  prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`,
  trace `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`; sst status empty. ✓
- **Zero drift. No STOP.**

## Fix design (root cause + smallest correct fix + bound)

**Call-site analysis (both mirror call sites are vulnerable).**
`cli.py:1176-1177` sets `source_root = ws/stc` and
`dossier_dir = $STC_DOSSIER_DIR` (live: `evidence/FOLLOWUP/accept/attempt-1/dossier`,
INSIDE `ws/stc` per the packet evidence layout); `cli.py:1470` passes
`evidence_root = dossier_dir/"runs"`. `DialecticRunner.run_async` derives
`run_dir = evidence_root/run_id`, `leases_root = run_dir/"leases"`
(:675, :695), and `STCCustodyWrapper.verify_candidate_proposal` mirrors
`src = packet.source_repo_root` (= `ws/stc`) into
`lease_ws = leases_root/lease_id` (:427-445). The merge path mirrors the same
`source_repo_root` into `merged_dir = run_dir/"merged"` (:815). So BOTH
destinations live inside the source root on every real run; both recurse
today (the lease leg was reached first live; the merge leg would stall the
same way on any champion).

**Failure-mode reasoning.** `mirror_source_tree` iterates `src.iterdir()`
lazily and `shutil.copytree`s each top-level dir with no destination
exclusion. Once the copy reaches the `docs/…/dossier/runs/…/leases/<lease>`
subtree it copies the lease into itself level after level (observed depth 7,
1.2 GB, zero store/ledger writes; only natural endings ENAMETOOLONG /
disk-full). No timeout bounds the mirror (120 s gate timeouts sit downstream
in `execute_gates`, never reached). The catch-all (:487-497) quarantines only
AFTER the mirror raises — it cannot bound the copy itself.

**Choice: exclude exactly the destination subtree from the mirror (option 1),
confined to `mirror_source_tree`.** Rejected alternatives:
- *Mirror from git objects* — larger blast radius (new git-archive plumbing,
  still needs dst-exclusion reasoning for the checkout dir, and `.git` must
  stay IN the mirror because `_resolve_commit_hash` raises on non-git trees
  per the B1.3 comment at :275-277).
- *Place leases outside the source root* — breaks the packet evidence layout:
  the in-repo dossier (with its leases/quarantine exhibit) is the contracted
  evidence artifact (attempt-1's quarantine exhibit WAS the A1 proof); it also
  needs `cli.py` (not an owned file) or a `DialecticRunner` layout change with
  dossier-assembly coupling.
- *Refuse dst-inside-src with a loud error as THE fix* — turns the hang into a
  hard failure on the legitimate contracted layout; not a fix.

Excluding `dst` is not a "silent partial": the destination directory is the
artifact being created, not source content — every genuine source byte is
still mirrored (faithfulness is pinned by test). The exclusion is robust
because it keys on fully resolved paths (`Path.resolve()` + `is_relative_to`)
at EVERY recursion level, not on name matching: no layout, nesting depth, or
symlink spelling can smuggle the destination back into the traversal.

**The bound (required second half).** Exclusion alone fixes the live shape;
the bound closes every other self-referential layout loudly:
- `src == dst` or `src` inside `dst` → `DialecticError` (loud refusal; these
  shapes cannot be mirrored faithfully — never a silent partial).
- Directory listings are snapshotted (`list(iterdir())`) so concurrent lease
  creation (parallel node leases, sibling leases under the same `leases/`)
  cannot extend the traversal mid-copy.
- Sibling content (`store.db`, `events.json`, other leases) inside `src` but
  OUTSIDE `dst` still copies finitely — bounded by construction, unchanged
  semantics.

**Incidental hardening (same function, no extra surface).** The rewrite
replaces top-level-only `copytree` with a recursive helper, so
`_MIRROR_SKIP_DIRS` now applies at every level instead of only the top level
(previously a nested `.venv`/`__pycache__` was copied — pure waste; nothing
depends on nested caches: substrate gates and the FakeSubstrate `rglob("*.py")`
scans are unaffected). `.git` stays INCLUDED at all levels (B1.3 invariant
preserved). `copy2` metadata semantics preserved.

## Secondary assessment: A2 served-header preservation → DEFER

A2 needs: success-path `stderr` (which carries the served confessor header per
the P2 precedent) is dropped — `CLIGatewayBackend.generate` returns
`result.content` only (`cli_gateway.py:234`); the ledger `log_row` schema has
no header column (`note` truncated to `NOTE_BUDGET=300`, `harness_worker.py:621`);
surfacing needs `cli_gateway.py` extraction + `SpendLedger` schema/sidecar
touch (`harness_worker.py`) + dossier-assembly surfacing + tests. That is a
multi-file change with dossier/ledger schema touch — it fails the brief's
inclusion rule (≤5 lines in already-owned files; schema touch = DEFER).
**A2 DEFERRED with reasons recorded; `cli_gateway.py` does NOT join owned
files.** Owned files stay exactly: `src/stc/integration/dialectic_runner.py`
+ `tests/unit/test_integration_dialectic.py` (append-only).

## B2 proof plan (0 CLI calls)

- New regression tests (append-only): (1) dst-inside-src layout mirroring the
  live shape (`<src>/docs/…/dossier/runs/<run>/leases/<lease>` with a
  pre-existing dst marker): terminates, dst subtree excluded (exact file-count
  bound — no runaway), content faithful byte-exact; (2) disjoint-layout
  no-regression: faithful copy, skip-set excluded, `.git` included;
  (3) loud-refusal bound: `src == dst` and src-inside-dst raise
  `DialecticError`.
- Full `tests/unit/test_integration_dialectic.py` + `tests/integration/test_dialectic_fixture.py`
  green live-deselected on BOTH interpreters (joint 3.12.3
  `PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`; real-gates
  3.11.15 `PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`;
  `PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`).
- `ruff check` + `ruff format --check` and `mypy --strict` on owned files;
  sst clean before/after; tracked-diff audit (only the 2 pre-existing
  loose-set mods + this stage's owned-file delta); Hash Identity for every
  file created/modified. No commits, no STATE.md writes; sst/prompt-kit/trace
  read-only; `trace-lite/` never touched. Spend 0 (tranche 4/20; 6-call
  reserve untouched).

## Verdict

**READY** — predecessors read, zero drift, fix design justified with
call-site + failure-mode evidence, bound specified, A2 deferred in writing,
owned surface minimal (2 files), proof plan scripted. Proceeding to B2.
