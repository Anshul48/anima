# SUBSTRATE — Canonical Frontier Record v2 (2026-10-04)

Project-level living record. Frozen milestone records stay intact and are
linked, not rewritten:

- `prototype/w1-harden/CANONICAL-RECORD.md` (promoted pilot record, frozen)
- `prototype/windows-check-20261004/WINDOWS-REPORT.md` (ancillary Windows qual)
- `prototype/closeout-20261004/` (identity, acceptance tie, Windows incorporation)
- `prototype/evidence-20261004/` (byte-identical preserved /tmp evidence + README)

Grounding: ANIMA packet (OPERATIVE-BRIEF, SUBSTRATE/EXPERIMENTS tracks,
IDEA-MAP, DECISIONS D-001..D-017, REQUIREMENTS-AND-EVIDENCE),
`docs/SUBSTRATE-DIRECTION.md`, `docs/WORLD-BOUNDARIES.md`.
Priority map A → C → B → D. Labels: OBSERVED / REPRODUCED / VERIFIED /
ACCEPTED / PROPOSAL / DEFERRED / BLOCKED.

## 1. Candidate identities

- W1 toy prototype `prototype/w1/`: sha256 anchor `w1-harden/FREEZE.w1`
  (7 files). Untouched throughout (last verified closeout).
- Hardened pilot `prototype/w1-harden/`: 20 files, identity
  `closeout-20261004/IDENTITY.json` (= windows ORIGINAL-SHA256 20/20).
  Acceptance tie (non-backdated): `closeout-20261004/ACCEPTANCE-TIE.md`.
- Windows candidate `windows-check-20261004/candidate/`: separate 12-file
  identity `CANDIDATE-SHA256.json` (2 files patched per WINDOWS-KILL.patch).
- SST: was HEAD 079f4de dirty-with-hashes at pilot freeze; pilot
  SST-TEST evidence stays valid for frozen bytes only. Staging then
  drifted (cand-02 era, porcelain 46→55) and is preserved as history.
  SST owner has since LANDED clean release commit
  `df78f42894a65c48f524337a498032617689a013` (porcelain 0 at copy;
  `run_search -> SearchResult`, `execute_search` stable, TEST
  fixtures). Release r1 vendors its exact `src/` bytes
  (`snapshot_hash 5f1f3789…`, 54 files) as a SUBSTRATE-QUALIFIED
  SNAPSHOT (no owner release acceptance of the vehicle claimed).
- DSH: 639ed015397290b3745d163aafe02ffee4aa3f84 (anchor-only, verified).
- STC: HEAD 851e4a4b9072f203d18ed4fb33987cdd21d6a084 (read-only; no stretch).
- Reuse demo `prototype/reuse-demo-001/` (VERIFIED by coordinator re-run):
  minihost d01049a9, reuse_demo bf3a49fa, test_reuse 81468843,
  w1h_bridge c015e8a3, REUSE-REPORT 5f9b8804. 10/10, SIGKILL rc=-9,
  0 re-invokes.
- X3 `prototype/x3-20261004/` (VERIFIED by coordinator repro:
  RESULT.md byte-identical): H3a 3-0, ratios 0.16/0.29/0.45, VALID
  ties, recovery parity, minihost byte-copy d01049a9.
- Successor `prototype/successor-001/` (VERIFIED by coordinator re-run:
  15/15, demo exit 0, evidence audited; see
  `closeout-20261004/SUCCESSOR-VERIFICATION.md`): minihost d01049a9
  (identical 3rd copy), fusion 170d47f3, pipeline 292c7f15, resume
  10d3eb22, routing 08fa3cdb, sst_leg 4932422f, demo a47f6cca,
  tests e5daea49. Hybrid routing, real fusion + reuse, quarantine
  path, SST-TEST from cand-02 bytes ($0, TEST, champion_found).
  Predecessor milestone; superseded by frozen release r1
  (`prototype/successor-002/`, see
  `prototype/release-20261004/RELEASE-RECORD.md`).
- WORLD-CONTRACT-v1: `prototype/successor-contract/WORLD-CONTRACT-v1.md`
  (PROPOSAL, implemented by successor-001 C1–C7 with 2 documented
  boundary notes: no `scores[]` clause use, `proposed` pre-state).

## 2. Requirement frontier

Product capability (R) vs research resolution (Q) are tracked separately:
a negative experiment can ACCEPT a Q within its envelope while the
corresponding R stays unsatisfied. Detail + provenance + authorship:
`prototype/programme-20261004/COMPLETION-MAP.md` (vectors, A/B
contexts, A→C→B→D, per-requirement evidence/remaining/ownership,
producer + U-execute states).

| ID | Requirement | Status | Evidence / gap | Next action |
|---|---|---|---|---|
| R1 | Nested orgs, locally owned responsibility | PARTIAL (obligations + escalation, toy scale) | Written obligations O1–O5 + E1–E3 enforced structurally (H-commitment guard, void-by-ruling-only, giver-actor transfers); worlds self-solve/verify; coordinator sees exports only. Local POLICY invention (not just execution) absent | Policy learning is E4-adjacent, deferred |
| R2 | Heterogeneous participants/representations/ops | PARTIAL | Construct/explore worlds, v1/v2 declared-loss mapping; mapping hand-written, toy evaluator | X3 incompatible-representation task; learned mapping stays deferred |
| R3 | Revisable cooperation/boundaries | PARTIAL | Versioned relationships, v1 pin after v2; no learned revision | X3 revision-under-evidence probe |
| R4 | Integration/assimilation/fusion/fission, coalitions, composites | SATISFIED single-host | Release r1: fusion (lineage + 3 transfers + channel removal 8→7) + reuse 5/5; fission (partition + back-transfer + lineage + channel restore) + reuse 4/4; quarantine separation path. All accepted round 2. Cross-host → deferred (multi-host design) | None for r1 |
| R5 | Actual state/ownership/responsibility/lifecycle change | SATISFIED (single-host envelope) | Fusion: 3 custody transfers + settle-then-dissolve + composite creation + channel removal (mechanism inventory before/after); revocation flips + revision switches durable across reopen; S5 commitment transfer. All on one ledger — cross-host change untested | Cross-host change awaits a multi-host design (no current requirement) |
| R6 | Composite reuse + continuity/lineage/inheritance | PARTIAL (reuse + lineage; recipe inheritance deferred) | X3-T3 + successor S4: follow-up runs through the fused composite with derived_from×2 + fusion entry, lineage_ok, VALID 5/5. Developmental-recipe inheritance (descendant advantage on unfamiliar work) untested | Recipe inheritance needs a learning loop (E3-adjacent, deferred) |
| R7 | Adaptation to changed conditions | PARTIAL (authorized-mechanism adaptation) | X3-T2 + successor S3: v1→v2 revision + capability revocation mid-task → escalation → ruling → void-notice → re-propose by new owner → VALID. Adaptation runs through authorized mechanisms (revise/revoke/rule), not autonomous discovery | Autonomous adaptation discovery is B-frontier, deferred |
| R8 | Local negotiation reduces central load | PARTIAL (conditional mechanism) | X3: obligations + direct negotiation + escalation cut central context 2–6× with equal VALID outcomes where multi-round clarification over split state is required; X1/X2 still bound the small-scale case | Successor ships hybrid routing (central default, local lane for dialogue-heavy legs) |
| R9 | Consumer contracts | SATISFIED for this path | WORLD-CONTRACT-v1 C1–C7 + ORG-OPS OP-1–OP-6 (fusion/reuse/revision/revocation/quarantine/fission: commitments, custody, resources, lifecycle, lineage, recovery) + G1–G8 mapping; 9/9 conformance; OP-4 gap found + fixed in acceptance | New paths need contract deltas |
| R10 | Integrated Linux path, meaningfully different envs | SATISFIED (toy-scale, two envs; generations r1→r3→S5) | Release r1: one ledger, hybrid routing, scheduling env (independent checker) + SST-search env (df78f42 snapshot, TEST, champion_found, $0); 33/33 + demo exit 0 + CLI/API + accept pack, independently accepted. Carried through r2/r3; S5 (successor-005): 129 tests + procedure participant + relcheck vehicle, ACCEPT-WITH-NOTES. Toy scale + single-host + TEST-only bound the claim | Scale/complexity growth is future work, not a current gap |
| R11 | Interruption/failure/changed-condition handling + declared recovery/separation | SATISFIED (declared paths) | Kill resume (rc=-9, 0 re-invokes, byte-identical); mid-task revision + revocation + ruling → re-propose; 5 refusal shapes with deny; quarantine separation with commitment transfer + settle. Kill-during-settle/fusion COVERED in S5 (39/39 atomicity, incl. real-SIGKILL matrices); kill-during-quarantine-transfer REPAIRED in s006 (supported complete/rollback ops, 13/13, S6-ACCEPTANCE.md ACCEPT); disk loss, multi-writer stay deferred per LIMITS | Each remaining deferred path needs its own scoped exercise |
| R12 | Independent verification via consumer behavior | SATISFIED (all candidates) | Pilot: H2 + Windows architect. Reuse/X3/successor-001: coordinator direct re-runs. Release r1 (successor-002): two independent lanes — round 1 REJECT (A1–A9 PASS, A10 FAIL OP-4 + 7 notes, all fixed) then round 2 ACCEPT-WITH-NOTES (A10 8/8, A8, A1/A6/A9 spots; 3 record notes fixed + coordinator-confirmed). S5-A12: ACCEPT-WITH-NOTES (recount + all suites incl. 57/57 + own kill legs + pins reproduced + tamper 5/5 + wording re-audit + post-hashes; S5-A10 lane-RED environmental, NOTE-1 gating CLOSED by coordinator READINESS-PASS 183.2 s). All through consumer paths on fresh state | Future candidates: same bar |
| Q1/E1 | Local negotiation vs capable central | CONDITIONAL: central wins small (H1b), local wins dialogue-heavy (H3a) | X1/X1H: central wins effort+bytes at toy scale. X3 (recovery held constant, coordinator-reproduced RESULT-identical): H sweeps 3-0, central bytes 0.16/0.29/0.45×C with VALID ties, recovery parity, real SIGKILLs. Rule: local wins when dialogue-rounds × split-state ≫ commitments | No further E1 runs without a new hypothesis |
| Q2/E2 | Composites vs fixed+tooling | ACCEPTED H2b in envelope | X2 ties + fixed wins effort/bytes; composite wins recovery + E1 rework | Recovery retained; rest needs harder test |
| Q3 | Recovery independently reusable | DEMONSTRATED, contract COMPLETE | Unmodified resume_to_verdict on separate MiniHost: 10/10, SIGKILL rc=-9, 0 re-invokes (coordinator re-ran); CC1–CC9 coupling contract filed + tested in successor-006 (S6-ACCEPTANCE.md ACCEPT) | None |
| Q4/E3/E4 | Schema/workflow learning | ARC CLOSED (negatives in envelope); no learning in s005 | L1 negative (no recipe surface), L2 step-0 abort (byte-mass conservation), M1 abort (2 obs vs ~20), M1-redux PASS (exact held-out mapping, binding non-discovery). s005: no learning of any kind (LIMITS). Negatives resolve their Qs; corresponding Rs stay unsatisfied | Bounded probe only if it resolves a live uncertainty |
| Q5 | Permanent host (extend-DSH / Cordis-seam / distinct) | UNDECIDED (recommendation ready on request) | Mechanism note (pre-X3): DSH/Cordis = composition only; world semantics would be a TS port, not seam reuse. Python MiniHost lineage now carries v1 + hybrid + fusion + SST consumption with the least complexity satisfying R1–R12 in-envelope. No evidence yet favors migration | Bring user evidence + alternatives before any migration/semantic commitment (standing obligation) |
| S5-proc | Bounded procedure participant (accountable executor, NOT sandbox) | SATISFIED in envelope | 57/57 procedure tests (advertise/run/recover/change/wording + tamper legs); P1–P9/P14 enforced, P11–P13 contractual non-claims; L1–L5 process-crash-only; S5-A12 ACCEPT-WITH-NOTES | Reuse-beyond-one-vehicle evidence (J1 journey, successor-006) |
| U-exec | Real-use task + change + recovery + comparison | COMPLETE FINAL, INDEPENDENTLY ACCEPTED | §7.8 FILED 2026-10-06T13:35:45Z; acceptance experiment complete: HOST-VALUE-NOT-DEMONSTRATED (6 failing cells), H-vs-D TIED every rated leg (arm-invariant bytes 099f4e33), H-kill recovery TRUE, change legs VOID (adaptation untested), r5 NOT banked. Auditor re-ran + accepted (INDEPENDENT-ACCEPTANCE.md 2026-10-07) | Adaptation protocol design (ADAPT-EXPERIMENT-DESIGN); no r5 |
| P1-prod | Producer qualification (SST/STC callers) | Byte identity SATISFIED; contracts/evidence missing | SST df78f42 clean, 54-file 5f1f3789 recomputed exact; STC freeze 548615a (record-only over code 1d1c535, EXTERNAL_PINS sst=df78f42 unchanged, full-replay recovery code-verified); TRACE presence-only a24a937; TL absent. Missing: SST owner contract + gate record; STC artifact decision + contract/evidence (Ask 2B) | Owners; substrate consumes qualified exports only, stages upgrades deliberately |

## 3. Accepted decisions (within envelopes)

- Working path: central orchestration + evidence/tooling/docs (H1b/H2b/X1H).
- Retain narrowly: checkpoint schema + identity rule, grant_settle +
  unsettled-terminal check, host_reopen, resume-by-skip, descriptor
  re-supply + fail-closed withholding (RECOVERY-REUSE.md).
- Linux/Ubuntu is the shipping target; Windows check ancillary and closed.
- SST consumption (r1-era posture, superseded — see next bullets):
  within-run self-consistent cand-02 bytes with a preserved 50-file
  manifest per run; the coordinator's static staging hash WITHDRAWN
  (unreproducible + snapshot mutates). Principle retained: the pin
  advances only on an SST clean landing; fresh runs against drifted
  live HEAD prove nothing about frozen evidence.
- Release r1 (`prototype/successor-002/`, FROZEN 2026-10-04) was the
  first useful result: hybrid routing (local iff ≥2 rounds AND
  split), v1 + ORG-OPS contracts, fusion + fission + quarantine,
  SST-TEST from the df78f42 snapshot ($0). 33/33 suites, demo exit 0,
  calibrate 2.61x (bytes-only), independently accepted (round 2).
  Full account: `prototype/release-20261004/RELEASE-RECORD.md`.
  Successor-001 remains the intact predecessor milestone. r2/r3/S5
  since frozen/accepted — see §6 Done paragraphs.
- SST snapshot re-based to the owner's clean release commit df78f42
  (porcelain 0; `snapshot_hash 5f1f3789…`, 54 files). The cand-02
  staging snapshot is preserved as history. Owner release acceptance
  of the vehicle still outstanding (evidence request stands).
- No permanent host, migration, or governing semantic commitment without
  user-facing evidence + alternatives first.

## 4. Open items needing the user (escalation format)

None at this time. All current paths are executable under existing
authorization (U re-scope answered by FINISH directive: rectification
+ filing underway; producer asks with owners; Q5 with user when ripe).
Standing obligations: Q5 evidence + alternatives before any
migration/semantic commitment; producer qualification before
consumption claims.

## 5. Deferred obligations (visible, owned)

- Clean/live SST: SST owner (keys, budget, live qual). Substrate
  consumes the df78f42/5f1f3789 SUBSTRATE-QUALIFIED SNAPSHOT only;
  owner release acceptance outstanding.
- STC-backend stretch, TRACE participation: respective owners; not attempted.
- Mapping learning/training, real evaluator, distributed ledger, Host
  locking, multi-kill/disk-loss, non-exists predicates: deferred per
  LIMITS.md; each needs its own scoped plan before becoming a promise.
- E3/E4 full, recipe inheritance, autonomous discovery, cross-host,
  multi-writer, HW co-design: deferred until a bounded probe earns its
  cost. Broader visions (A2 five-layer equations, V16 evolution
  machinery, V17 attention policy, personal-model, memory-tiers) stay
  hypotheses/proposals per ../ANIMA/context/ authorship — never cited
  as results. B1/B2 review paused by user; O-11 unobserved addition
  must not be inferred.

## 6. Health

Done: release r1 FROZEN and independently accepted (round 2).
Closeout, reuse (Q3), X3 H3a, contracts (v1 + ORG-OPS), fission,
df78f42 snapshot, packaging, two acceptance rounds (REJECT→fix→ACCEPT-
WITH-NOTES→notes fixed+confirmed) — every worker claim re-executed or
evidence-audited. Remaining: SST-vehicle acceptance (owner),
Q5 host judgment (user, non-blocking), future research with scoped
plans (policy/recipe learning, scale, cross-host) — each owned in
RELEASE-RECORD.md §6.

Done: release r2 FROZEN and independently accepted
(successor-003 + release-r2, A1–A10 PASS builder + lane,
ACCEPT-WITH-NOTES; F1 LOW concurred, F2 LOW filed with successor
fix owned). Done: learning arc closed — L1 negative (no recipe
surface), L2 step-0 abort (byte-mass conservation, crossover
ungeneratable), M1 abort (2 obs. vs ~20), M1-redux PASS (exact
held-out cost mapping, binding non-discovery), H2 experimental host
accepted+ frozen (46/46). Done: P1 producer survey (SST 0/4 nearest,
STC 0/4 + design answer needed; asks filed). Remaining: F2 atomic
spec writes (R3, launched), quarantine-transfer/multi-writer/
disk-loss/cross-host (owned deferreds), U-branch (producer owners),
Q5 host judgment (user, non-blocking), policy invention (gated: no
trade-off surface exists yet).

Done: release r3 FROZEN and independently accepted
(successor-004 + release-r3, A1–A10 PASS builder + lane,
ACCEPT-WITH-NOTES, no new product findings). Done: U-branch step-0
negative (no honest useful task fits the qualified envelope;
REALUSE-DESIGN.md; all load-bearing claims coordinator-verified;
U-execute BLOCKED behind reopen invariants I1–I6, re-scope decision
with user). Standing: r1/r2/r3 frozen+accepted; H2 experimental host
accepted; learning arc closed; P1 reconciled (SST identity citable,
contract+evidence genuinely missing). U re-scope answered by FINISH
directive (rectification + filing underway, this round). Standing:
producer asks (owners), Q5 (user).

Done: successor-005 (S5 bounded procedure participant + relcheck
vehicle) builder-verified and S5-A12 independently ACCEPTED-WITH-
NOTES (S5-lane/VERDICT.md). Builder: 9/9, 7/7, 17/17, 39/39, 56/56
full + 2 focused P9 pins (57 loader count), loop L2=12/L3=28,
READINESS-PASS 175.8 s, R-A diff empty, pins byte-identical,
negatives 24/24 + 7/7 + tamper loud, frozen 1161/1161 + 41/41 +
45/45 + 45/45 + 46/46, IDENTITY 56/56. Lane: recount + all suites
green incl. 57/57 (L2=13/L3=27), own kill legs converged, pins
reproduced, tamper 5/5 + control, wording re-audit PASS,
post-hashes identical. Load-bearing find: P9 orphan race (K09 red →
key-subtree exclusion + regression, independently audited 5/5).
S5-A10 is lane-RED on two environmental timeout kills (all-green
partials, zero failures; box ~5× too slow) — NOTE-1 (gating) required
one observed READINESS-PASS on a capable box. NOTE-1 CLOSED by
coordinator: fresh READINESS-PASS (exit 0, 10/10 checks, host wall
183.2 s, both arms ACCEPT, claims-diff 0, frozen pre/post clean) on
native-ext4 scratch at launch load 0.98, candidate s005 IDENTITY
56/56 unchanged, pins 1fee2241/2dbb0439 unchanged, interpreters
3.12.3/3.12.3; evidence package
successor-005/runs/note1-closure/ (log + launch-load + both VALID
reports + ledgers). Prior timeout reds preserved as diagnosis.
U-execute CLOSED 2026-10-07: §7.8 filed, experiment complete,
overall HOST-VALUE-NOT-DEMONSTRATED independently accepted, r5 NOT
banked by design (see COMPLETION-MAP U-exec row +
U-execute/runs/INDEPENDENT-ACCEPTANCE.md). Standing: producer asks
(owners), Q5 (user). Next: owed repairs + J1 persistent-worlds
journey (successor-006) per SUBSTRATE-COMPLETION-PROPOSAL.

Done: successor-006 (owed repairs + J1) independently ACCEPTED
(S6-ACCEPTANCE.md, no notes): 48/48 tests + 10/10 demo re-observed
by auditor on fresh state through consumer interfaces — CC1–CC9
coupling contract (Q3/R9 owed item closed), quarantine-transfer
complete/rollback repair (R11 owed item closed), J1 journey
(persistent project + nested experiment + real delegation +
real-SIGKILL resume + fuse + unmodified composite reuse ×2 +
settle-0). BANKED 2026-10-07 (35/35, manifest 48462368…;
routine — banking is not an architectural decision); frozen
predecessors untouched. PUBLISHED 2026-10-08 as anima-substrate 0.1.0
(Anshul48/anima-substrate, tag v0.1.0, CI green, release assets
verified, fresh-clone repro OK). Companion research: MECHANISM-REUSE-ASSESSMENT.md,
ADAPT-EXPERIMENT-DESIGN.md (design only, no runs), STC-CONSUMER-
BOUNDARY.md. Review route: S6-REVIEW-ROUTE.md.
