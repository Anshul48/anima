# ARCHITECTURE.md — anima-substrate package

Maintained substrate package: persistent project worlds, pinned
participants, crash-atomic local host. Stdlib-only, offline, $0 in
base; the SST search leg is a caller-staged optional extra (see
`docs/SST-STAGING.md`).

## 1. Layout

```
src/anima_substrate/
  __init__.py        version + family registration
  __main__.py        python -m anima_substrate
  cli.py             anima-substrate entry point (all ops)
  host/
    api.py           consumer surface (init/open/run/ops/J1/org/export/recipes)
    minihost.py      ledger, worlds, grants, invoke/deny, reopen-by-replay
    resume.py        resume-by-skip engine (C1–C3 matcher)
    pipeline.py      sched lanes (central/local), S3 flow, split-pair
    routing.py       routing rule, coordinators, channels (+ M3 persist)
    fusion.py        fuse/fission/quarantine/reuse
    recover.py       ledger forensics + completion (R1/R11)
    procedure.py     accountable procedure executor (S5)
    recipes.py       propose→assess→retain→reuse loop (M4)
    calibrate.py     lane byte calibration (2.61x, re-proven)
  participants/
    __init__.py      family contract v1 + registry
    sched/           sched toy family (fixtures + domain + checker + family)
    relcheck/        file-backed release-identity family (v1/v2)
    sst/             SST optional-extra family (pins only, no SST bytes)
  demos/
    successor_demo.py  integrated S1–S6 + SST + settle demo
    j1_demo.py         J1 persistent-worlds journey demo (10 stages)
  accept/            frozen S1–S6 accept pack + EXPECTED.json
tests/               ported suites (s005 57+39+17, s006 9+7+10+13+6)
                     + maintained suites (families, M1, M3, M4, SST,
                     calibrate/demo)
examples/            quickstart script (installed-package flow)
docs/                CONSUMER / CONTRACTS / ARCHITECTURE / RECOVERY /
                     SST-STAGING
```

## 2. Host

One ledger (`ledger.jsonl`, append-only, monotonic seq) per run
root; per-world state dirs; `worlds.json` creation specs;
`CONFIG.json` metadata; `channels.json` (M3); `ROUTING-LOG.jsonl`;
`artifacts/`. Worlds are born with creation-fixed
capabilities/representations, funded from host holdings (delegation
never manufactures resources), and invoked accountably (success
records `result_ref`, failure records `error` and burns nothing).
Reopen replays the ledger (registry/holdings/grants/lifecycle),
restores creation lineage + authorities + procedure tables from
`create` payloads, re-applies revocations, and restores channels.

## 3. Participant families (contract v1)

A family = one kind of task work behind four operations
(create/run/recover/change) plus advertised caps/reps/grant shape.
Families register themselves and bind the public host surface only
(`host.api`, `host.minihost`, public constants) — adding one needs
zero host edits (enforced by `tests/test_families.py`).

| family | version | task work |
|---|---|---|
| sched | v1 | toy sched task class (single-world work plan) |
| relcheck | v1 | release-identity pins over real caller files |
| relcheck | v2 | v1 + compat rules; upgrade target for v1 worlds |
| sst | v1 | snapshot-verified TEST search (staged root only) |

## 4. Milestones (mandate M1–M4)

- M1 usable journey: `init` → `family-create` (relcheck) →
  `family-run` on real files → close/reopen byte-verified →
  `settle` stranded=0; install = `pip install` from a built wheel;
  3 seeded failure cases raise actionable errors (cause + fix).
  Evidence: `tests/test_m1_journey.py` (+ gated wheel test).
- M2 pinned participants: ≥2 base families + SST optional extra
  via caller-provided root at pinned `df78f42` + compat probe;
  relcheck v1→v2 upgrade with old pins reproducible; refusals via
  consumer interfaces. Evidence: `tests/test_families.py`,
  `tests/test_sst_staging.py`, `tests/test_successor.py` SST legs.
- M3 persistent organization: channels + relationship evidence +
  custody persist across reopen (byte-verified inventories);
  `export-composite` produces a portable executable consumed
  unmodified in a fresh separate state dir (explicit new grants,
  lineage preserved); kill-during-persist converges via
  reopen + recover. Evidence: `tests/test_m3_org.py`.
- M4 experience loop: propose → assess (P0–P3 + independent
  re-hash) → retain → reuse on a meaningfully different task, with
  a filed prereg (programme format) predating comparison runs, a
  from-scratch baseline with costs/interventions, and
  superiority_claimed=false. Evidence: `tests/test_m4_loop.py`,
  `runs/m4/` (witnessed instance).

## 5. Limits (package envelope)

Carried from successor-006 LIMITS.md (16 items), with package
deltas marked. Every verdict in this package holds only inside
these limits.

1. Toy scale, deterministic stubs. Scheduling grids are 4–5 tasks /
   4–5 slots; one deterministic backtracking solver is shared by all
   worlds (only VALID + bytes + lane behavior are measured).
2. Single machine, local disk. Refs are host-local paths;
   kill-resume is proven across `Popen.kill()` on one machine, not
   across machines. No multi-writer concurrency, no disk loss.
   Side files are crash-atomic (temp+`os.replace`, old-or-new); the
   LEDGER is explicitly NOT tear-proof (a kill inside an append may
   tear the tail line → loud disk-loss refusal, tested). No fsync
   is issued anywhere: the guarantee is atomicity across a PROCESS
   crash, never durability across power/media loss.
3. One injected kill per J1/S3 run, mid-task, on local disk.
   Kill-during-settle/fusion/fission/quarantine-transfer/procedure-
   step are covered (defined behavior + recovery completion, proven
   by kill-at-every-boundary tests incl. repeated kills and a real
   SIGKILL leg). Kill DURING repair converges on re-run.
4. Central-bytes accounting is a serialized-bytes ratio inside the
   task envelope ONLY. RE-PROVEN in this package: 2.61x (810/310,
   `tests/test_calibrate_demo.py`). J1 work plans claim NO lane
   bytes (no clarification dialogue by design).
5. Fusion/fission/quarantine/nest are structural but single-host.
   Cross-host anything is NOT implemented. (Portable composites
   move worlds between state dirs on the SAME host — M3.)
6. Revocation is an authority-stamp flip replayed after reopen ONLY
   via `reapply_revocations` (raw reopen lapses — demonstrated in
   carried conformance). Capability sets are fixed at world
   creation; genuinely NEW capabilities require a new world.
   Representation revision switches the ACTIVE version between
   pre-advertised versions only.
7. SST leg: OPTIONAL EXTRA (package delta — s006 NOT-carried).
   Staged-or-refuse over a caller-provided root at pinned
   `df78f42` + pinned pydantic 2.13.5 (compat probe). Unstaged
   callers get a loud refusal naming `SUBSTRATE_SST_ROOT`. No SST
   bytes ship in this package.
8. Ledger timestamps (`at` fields) are wall-clock and excluded from
   byte-identity comparisons (artifact bytes are timestamp-free and
   ARE compared). Run dirs embed a UTC timestamp; reruns create new
   dirs rather than overwriting.
9. (Package delta — s006 item lifted in part.) Channels persist to
   `channels.json` (crash-atomic, restored on reopen).
   Relationship evidence + custody persist via ledger replay
   (byte-verified inventories). Still absent: per-grant siloed
   balances, content-addressed refs (paths retained). Lifecycle
   `retired` is declared but never exercised.
10. No learning of any kind: no local POLICY invention, no learned
    mappings/evaluators/revision, no recipe inheritance, no
    autonomous adaptation discovery. J1 delegation amounts are
    OPERATOR-SUPPLIED, never invented. M4 recipes retain assessed
    profiles with costs — superiority is never claimed.
11. `settle` is ATOMIC on refusal (zero partial dissolves; only a
    `deny` entry). A DIRECT `settle_op` on a composite with a
    partial fission still does NOT refuse (custody-orthogonal by
    contract); only `recover_op`'s targeted settle withholds
    still-blocked worlds. Complete partial ops through `recover_op`
    first.
12. Nesting is LEDGER-RECORDED, not OS-isolated: a nested
    experiment world is a peer world with `derived_from` lineage +
    a `nest` entry, sharing one ledger and one filesystem with its
    project. No containment, sandboxing, or resource policing
    beyond grant accounting is claimed.
13. The quarantine complete-vs-rollback DECISION is not automated
    and never will be in this envelope: `recover_op` detects +
    points at the supported ops, and the operator chooses. A
    complete refused because a rollback started (or vice versa)
    must be finished in the started direction — the ops refuse to
    mix handoff directions rather than guess.
14. (Package delta — s006 item lifted.) `export-composite`
    produces a PORTABLE EXECUTABLE bundle consumed unmodified in a
    fresh separate state dir on the same host (M3). Same-host only:
    cross-host refs stay unimplemented. The J1 evidence export
    (`j1-export-*.json`) remains evidence, not executable.
15. (Package delta — s006 gap CLOSED.) The full 57-test procedure
    suite is ported and green in this tree
    (`tests/test_procedure.py` 57/57); procedure behavior is
    verified here, not carried on byte-identity.
16. J1 verify is single-checker: one `sched.verify` verdict per
    task (optionally cross-world). No independent second checker,
    no adversarial tasks, no quality bar beyond VALID + the toy
    prefs-total. The journey demonstrates mechanics, not task value.

## 6. H2: frozen, out of scope (recorded)

Content-derived routing + lane tasks (`task_json` /
`lane_override` / `derive_routing_inputs`, `test_lane_tasks`
18/18) exist only in the frozen experimental
`prototype/programme-20261004/H2-lane/` tree (ACCEPT-WITH-NOTES as
verified). H2 was never merged into the successor line and is NOT
merged here either: `run_tasks` has no lane-override params, and
no half-carry is attempted. H2 stays frozen as-verified; any
future adoption needs its own merge + re-qualification.

## 7. Beyond the finish line (retained from the mandate)

Local policy invention; learned mappings/revisions; autonomous
adaptation discovery; recipe inheritance (descendant advantage);
cross-host / multi-writer / disk-loss; STC execution integration;
permanent host selection; HW/SW co-design and all V16/V18
machinery. Each needs its own mandate + discriminating protocol
before any claim. No B1/B2 work. No adaptation experiments were
run for this package.
