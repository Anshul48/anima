# Substrate roadmap — indexed gap map

> Public curation note: links to records excluded from this public release were converted to plaintext historical references; the original record identities are preserved inline.

> [!NOTE]
> **Active Migration Priority (2026-10-09)**: Project migration to native Linux takes precedence under governing direction SCOPE-UPDATE-20261009.md (historical record `../../migration_runs/windows-to-linux-20261008/SCOPE-UPDATE-20261009.md`, excluded from this public release). Routine roadmap progression is deferred during migration preparation and transfer. Exact exclusion applies strictly to `Utilities/trace-architecture`; other projects across Code and WSL are eligible under preserved rollback copies and a verified WSL deletion gate.

Source of truth: `prototype/programme-20261004/COMPLETION-MAP.md`
(§§1–5). This file indexes it; on conflict the map wins.
Standing envelopes bound every SATISFIED below: single-host, toy
scale, TEST-only SST, process-crash (not power-loss), no fsync.

## Priority order: A → C → B → D (user-ordered, D-004)

A = computationally useful knowledge; C = learned
schemas/operations; B = cumulative capability discovery; D =
computational/physical co-design. B/C swapped because B nears RSI;
D last but enabling HW work may start earlier. Not a rigid stage gate.

## 18-vector ambition (closeouts per IDEA-MAP:23–42)

| # | Vector | Standing |
|---|---|---|
| V1 | Organized-knowledge-first; breakthrough = both | Direction (D-002) |
| V2 | Dated project assessment | Historical synthesis only |
| V3 | TL/TRACE split now, reorganization later | Current posture |
| V4 | Exact-episodes vs conceptual-memory interaction | Proposal (four-store loop) |
| V5 | Self-organization evaluation candidates | Not adopted |
| V6 | STC construction + cumulative capability | Pilot preliminary; experience learning welcomed (D-005) |
| V7 | Async research must not block delivery | Direct instruction (B1) |
| V8 | SST-as-reusable-search | STC integration current (D-007); no TRACE mandate |
| V9 | Formulation-changing search | No method adopted |
| V10 | Obstacle→capability loop | Direction, not qualified generator |
| V11 | Noisy evaluation | No benchmark approved |
| V12 | Compiler / precise representation | B4 hypothesis |
| V13 | Schemas + deltas | Test it; keep fidelity + diversity (D-009) |
| V14 | Plastic boundaries / relationships | D-006; A2 details stay inspiration |
| V15 | Adaptation/learning/development/inheritance distinctions | No fixed five-layer mapping |
| V16 | Variation / selection / inheritance | Long-term ambition, D-004 conditions |
| V17 | Attention / metabolic allocation | Policies proposed |
| V18 | HW/SW co-design roadmap | Roadmap only; enabling work early, D later |

## Requirements: implemented vs measured vs future

### Implemented (SATISFIED in envelope; banked + accepted)

| ID | Claim | Evidence | Owner / next |
|---|---|---|---|
| R4 | Fusion/fission/coalitions | r1: fusion lineage + 3 transfers + 8→7 mechanisms + reuse 5/5; fission + reuse 4/4; quarantine path; round-2 accepted | Coordinator: none in envelope; cross-host needs multi-host design (DEFERRED) |
| R5 | Real state/ownership/lifecycle change | Mechanism inventory before/after; durable revocation/revision across reopen | Coordinator: none in envelope; cross-host DEFERRED |
| R9 | Consumer contracts | C1–C7 + OP-1–OP-6 + G1–G8, 9/9 conformance; CC1–CC9 coupling contract filed + tested in s006 (10/10), S6 ACCEPTED | Coordinator: new paths file deltas |
| R10 | Integrated Linux path | r1→r3→S5 carried; S5: 129 tests + procedure participant + vehicle, ACCEPT-WITH-NOTES | Coordinator: scale is future work, not a gap |
| R11 | Interruption/recovery/separation (declared paths) | Kill resume rc=-9/0, byte-identical; 5 refusal shapes; quarantine separation; S5 kill-during-settle/fusion matrices; s006 quarantine-transfer repair 13/13, S6 ACCEPTED | Coordinator: disk-loss + multi-writer DEFERRED, each needs scoped exercise |
| R12 | Independent verification | r1 two lanes; S5-A12 ACCEPT-WITH-NOTES (57/57 + legs + tamper 5/5); S5-A10 NOTE-1 CLOSED by READINESS-PASS 183.2 s | Coordinator: same bar for future candidates |
| S5-proc | Bounded procedure participant | 57/57 incl. wording + tamper; P1–P9/P14 enforced; P11–P13 contractual; L1–L5 process-crash-only | Coordinator: none in envelope |
| S6/J1 | Owed repairs + persistent-worlds journey | 48/48 + 10/10 demo, S6 ACCEPTED no notes; banked 2026-10-07 (manifest 48462368…) | Coordinator: none; regression suites carried |

### Measured (conditional / negative / partial — claim-bounding)

| ID | Claim | Evidence | Owner / next |
|---|---|---|---|
| R8 | Local negotiation cuts central load | CONDITIONAL: 2–6× dialogue-heavy (X3 H3a 3-0, 0.16/0.29/0.45); central wins small-scale. Calibrate 2.61× bytes-only, task-envelope-only | Coordinator: rule held; no runs without new hypothesis |
| Q1/E1 | Local vs capable central | CONDITIONAL rule (H1b + H3a) | Coordinator: no further E1 runs without new hypothesis |
| Q2/E2 | Composites vs fixed+tooling | H2b in envelope | Coordinator: recovery retained; harder test needed |
| Q3 | Recovery reuse | 10/10 unmodified resume; contract COMPLETE (CC1–CC9, S6 ACCEPT) | Coordinator: none |
| Q4/E3/E4 | Schema/workflow learning | ARC CLOSED negative (L1/L2/M1/M1-redux); M1-redux PASSED as instrument (MAE 0.00) — negative covers transfer/invention only | Coordinator: bounded probe only on live uncertainty; D-005 signal semantics binds all future learning work |
| U-exec | Real-use acceptance | COMPLETE FINAL, INDEPENDENTLY ACCEPTED: HOST-VALUE-NOT-DEMONSTRATED (6 failing cells); H-vs-D TIED every rated leg; H-kill recovery TRUE; change legs VOID (adaptation untested); r5 NOT banked | Coordinator: ADAPT-EXPERIMENT-DESIGN rev-2 (design only; runs need separate objective + prereg) |
| P1-prod | Producer qualification | Byte identity SATISFIED (SST df78f42/54-file recompute exact; STC pin landed+persists; TRACE presence-only; TL absent); contracts/evidence genuinely missing | SST owner (Ask 1: contract + gate record); STC owner (Ask 2B: artifact decision + contract/evidence). Substrate consumes qualified exports only |

### Future (PARTIAL / UNDECIDED / DEFERRED — needs mandate + protocol)

| ID | Gap | Owner / next |
|---|---|---|
| R1 | Local POLICY invention (execution exists) | Deferred; policy learning is E4-adjacent |
| R2 | Learned participant mapping (hand-written v1/v2 exists) | Deferred |
| R3 | Learned revision | Deferred probe |
| R6 | Developmental-recipe inheritance (reuse + lineage exist) | Deferred; needs learning loop |
| R7 | Autonomous discovery (authorized-mechanism adaptation exists) | B-frontier DEFERRED |
| Q5 | Permanent host | UNDECIDED, standing user obligation; reversible trials + successors advance meanwhile |
| V16/V18/V17 | Evolution machinery; HW co-design; attention policy | Long-term / roadmap / proposal; each needs own mandate + discriminating protocol |
| Cross-cutting | Cross-host, multi-writer, disk-loss, all learning forms, D-008 training + primitive mutation, multi-party collective, second environment (O-04), V10/E3-E4 loop, personal-model, memory-tiers, A2 equations | Deferred ambitions with owning statements; B1/B2 review PAUSED by user — do not begin |

## Mandate proposals (M1–M4 ACCEPTED and published in 0.1.0)

- `SUBSTRATE-SOFTWARE-MANDATE-PROPOSAL.md`: M1 usable journey → M2
  pinned participants → M3 persistent organization → M4 experience
  loop (no invention/discovery claims). APPROVED by user addendum,
  IMPLEMENTED in `anima-substrate`, independently accepted
  (`PKG-ACCEPTANCE.md` ACCEPT-WITH-NOTES, notes closed), published
  as 0.1.0 (`v0.1.0`). Below-the-line proposals stay decision-gated.
- `ADAPT-EXPERIMENT-DESIGN.md` rev-2: discriminating adaptation
  protocol — tie-valid with per-arm sensitivity, VOID only on
  sensitivity failure, no-discovery scope bar (§8). Design only.
- `STC-CONSUMER-BOUNDARY.md`: Ask-2B blocked/unblocked table;
  experimental adapter stays unqualified-only with full-replay
  composition rules. No adapter code changes.
