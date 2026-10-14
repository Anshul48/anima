# Substrate technical report — citable artifact guide (skeleton)

Status: skeleton for the 0.1.0 release round. Every section states
what is measured vs proposed; envelopes bound every claim
(single-host, toy scale, TEST-only SST, process-crash-only, no
fsync). Byte results are reported as bytes only — no token,
attention, cost, or intelligence conversions anywhere in this file.

## 1. Questions and hypotheses

- H1b / Q1-E1: capable central orchestration beats local negotiation
  at small scale (effort + bytes). HELD (X1/X1H).
- H3a / Q1-E1: local negotiation wins dialogue-heavy legs over split
  state. HELD 3-0 (X3). Standing rule: local wins when
  dialogue-rounds × split-state ≫ commitments.
- H2b / Q2-E2: composites vs fixed+tooling. ACCEPTED in envelope
  (ties + fixed wins effort/bytes; composite wins recovery + rework).
- Q3: is recovery independently reusable? DEMONSTRATED 10/10,
  contract COMPLETE (CC1–CC9).
- Q4/E3/E4: schema/workflow learning. ARC CLOSED negative in
  envelope (L1/L2/M1); M1-redux PASSED as an instrument (MAE 0.00) —
  the negative covers transfer/invention, not the instrument.
- U-exec: does the host demonstrate real-use value over a direct
  baseline? NEGATIVE, FINAL: HOST-VALUE-NOT-DEMONSTRATED.
- Standing semantics: D-005 signal classes (prediction discrepancy /
  explicit correction / independent-check failure / evaluator defect
  / comparative advantage) stay distinct in every future record.

## 2. Mechanisms and methods

- MiniHost lineage (`minihost.py`, sha `d01049a9…`, byte-pinned by
  tests): reuse-demo-001 → successor-001 → … → successor-006.
- Hybrid routing: central default, local lane iff ≥2 dialogue rounds
  AND split state.
- Fusion (lineage + custody transfers + mechanism removal) / fission
  (partition + back-transfer + restore) / quarantine separation /
  versioned relationships with void-by-ruling-only.
- Bounded procedure participant (`procedure.py`): advertise / run /
  recover / change with P1–P9/P14 enforced; wording + tamper legs.
- Relcheck vehicle + checker rev4 (`3ea4868d…`) + predicates
  (`d12adfa2…`) + frozen pins: mechanical grading, sealed envelopes,
  held-out authorship, blind rating with mtime-audited filing order.
- ADAPT-EXPERIMENT-DESIGN rev-2 (design only): non-degenerate
  held-out change bar (ND1–ND5), per-arm sensitivity gate, scored
  TIE when both arms adapt, VOID only on sensitivity failure, §8
  no-discovery scope bar. Authorizes no runs by itself.

## 3. Exact candidates, dependencies, environments

| Item | Pin |
|---|---|
| r1 candidate | `prototype/successor-002/`, IDENTITY 41 files |
| r2 candidate | `prototype/successor-003/`, IDENTITY 45 files |
| r3 candidate | `prototype/successor-004/`, IDENTITY 45 files |
| s005 candidate | `prototype/successor-005/`, IDENTITY 56 files |
| s006 candidate | `prototype/successor-006/`, IDENTITY 35 files, manifest `48462368…` |
| SST snapshot | Commit `df78f42…`, 54 files, `snapshot_hash 5f1f3789…` (recomputed exact) |
| STC freeze | Code `1d1c535…`, record `548615a…`; EXTERNAL_PINS sst = df78f42 |
| TRACE / TL | `a24a937` presence-only / absent |
| P1-adapter pins | STC docs pinned at 8fa8ac3-era by design (no HEAD-following) |
| Interpreters | 3.12.3 / 3.12.3; ext4 /tmp; quiet-load ≤2.0 |
| Budget | $0, offline, stdlib-only (+ pinned pydantic 2.13.5 for SST legs only) |

Producer qualification state: byte identity SATISFIED; SST owner
contract + gate record (Ask 1) and STC artifact decision +
contract/evidence (Ask 2B) genuinely missing — substrate consumes
qualified exports only. STC stays UNQUALIFIED doc-reader;
experimental use is unqualified-only with full-replay semantics
(`replay=full`, `skipped:[]`, effect-repeat).

## 4. Results (with capable baselines, costs, failures, limitations)

- X1/X1H: central wins small-scale (effort + bytes). Capable-central
  baseline retained as the working path.
- X3 H3a: H sweeps 3-0, central bytes 0.16/0.29/0.45×C with VALID
  ties, recovery parity, real SIGKILLs (RESULT.md byte-identical on
  coordinator repro). Claim: 2–6× on dialogue-heavy legs only.
- r1 calibrate: **2.61× bytes-only** (810 vs 310 canonical-JSON
  bytes, S2 envelope). No token/attention/cost equivalence claimed.
- S5: 129 tests; 57/57 procedure suite; READINESS-PASS 175.8 s
  (builder) / 183.2 s (NOTE-1 closure, claims-diff 0); frozen
  1161/1161; tamper 5/5. S5-A12 ACCEPT-WITH-NOTES; S5-A10 lane-RED
  environmental (preserved as diagnosis).
- S6: 48/48 tests + 10/10 J1 demo re-observed by auditor; ACCEPT, no
  notes. Journey: persistent project + nested experiment worlds, real
  delegation, real-SIGKILL resume byte-identical (0 re-executed
  invokes), fuse with ownership change, composite reused unmodified
  ×2, settle stranded=0.
- U-execute (FINAL, independently accepted): overall
  HOST-VALUE-NOT-DEMONSTRATED with 6 failing cells named
  (H-change-adapt, comparison-void:D/change, rubric-missing ×2,
  rubric-bar ×2 on kill). H-vs-D exact TIE every rated leg —
  graded bytes deterministic and arm-invariant (`099f4e33…`, 5065 B,
  identical across arms AND legs). Kill bar missed equally on both
  arms (rater variance on identical bytes: clean 2/1/2 PASS vs kill
  1/0/2 FAIL) — a property of the shared artifact, not of either
  arm. H-kill recovery TRUE (unilateral). C11 ×4 disclosed and
  re-run legitimately (incl. baseline package-layout fix + C1 D
  re-runs). Cost/speed superiority unclaimed by design.
- VOID legs (preserved, not scored): H-change / D-change VOID ×2 —
  degenerate held-out revision (added distinct suite target = 0);
  adaptation UNTESTED, not disproven. r5 NOT banked; banked line
  unchanged (r1/r2/r3/H2/s005).
- Limitations: toy scale; single-host; TEST-only SST; process-crash
  only (no fsync; power/media = disk-loss class); no
  cross-host/multi-writer/disk-loss; no learning of any kind in s005;
  s006 carries no SST leg (loud refusal); no permanent host selected.

## 5. Reproduction pointers

- Index: `REPRODUCE-ALL.md` (identities → suites → demos, $0/offline).
- Two-minute review: `prototype/programme-20261004/S6-REVIEW-ROUTE.md`.
- Per-tree: `REPRODUCE.md` / `RUNBOOK.md` / `CONSUMER.md` next to the
  code; U-execute `RUNBOOK.md` + `PREREG.md` (§§1–8 + C1–C11).
- Rule: prove bytes first (`sha256sum -c IDENTITY.sha256`), run
  through consumer interfaces on fresh state, keep audit writes in
  fresh `runs/` dirs + `/tmp`.

## 6. Primary sources (read these, not summaries of them)

- Canonical map: `prototype/programme-20261004/COMPLETION-MAP.md`;
  project record: `CANONICAL-RECORD.md`.
- r1/r2/r3: `prototype/release-20261004/RELEASE-RECORD.md`,
  `prototype/release-r2/RELEASE-RECORD.md`,
  `prototype/release-r3/RELEASE-RECORD.md`.
- s005 lane verdict: `prototype/programme-20261004/S5-lane/VERDICT.md`.
- s006: `prototype/successor-006/` (RUNBOOK, LIMITS,
  COUPLING-CONTRACT, CONSUMER, PROVENANCE) +
  `prototype/programme-20261004/S6-ACCEPTANCE.md`.
- U-execute: `prototype/programme-20261004/U-execute/runs/
  U-OVERALL-FINAL.md` +
  `U-execute/runs/INDEPENDENT-ACCEPTANCE.md` (interim
  `U-OVERALL-NOTE.md` kept as history).
- Learning arc: `L1-transfer/`, `L2-transfer/`, `M1-mapping/`,
  `M1-redux/` under `prototype/programme-20261004/`.
- Boundaries: `STC-CONSUMER-BOUNDARY.md`,
  `STC-548615a-ASSESSMENT.md`, `ADAPT-EXPERIMENT-DESIGN.md`,
  `MECHANISM-REUSE-ASSESSMENT.md`, `LICENSE-AUDIT.md`.
- ANIMA packet (sibling `../ANIMA/context/`, cited by locator only —
  never copied in-tree): `IDEA-MAP.md`, `SOURCE-EXCERPTS.md`,
  `DECISIONS-AND-CORRECTIONS.jsonl` (D-001–D-017), `OPEN-ISSUES.md`,
  `REQUIREMENTS-AND-EVIDENCE.md`. B1/B2 fuller review is PAUSED;
  the O-11 reported addition was never observed and must not be inferred.
