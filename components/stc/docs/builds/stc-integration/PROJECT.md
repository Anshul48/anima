# STC Integration — Current contract

Revision: INT-2026-09-14.1 (fix tranche ONLY — the INT-2026-09-13.2 M1
record stays INTEGRATED and immutable; see change record)
Status: M1 INTEGRATED @ .2 (immutable); fix tranche planned @ .1 (A2-revisit
design delivered) — awaits operator go-ahead for Phase 0 + Phase 1
Kit: `trace/docs/prompt-kit` (FRAMEWORK + A/B role prompts + templates)
Project root: `stc/docs/builds/stc-integration/`

## Outcome and scope

- Intended user outcome: one working spec-to-code loop that takes architecture
  material (starting with real TL work), searches candidate implementations
  dialectically, gates them mechanically, and returns verified diffs plus
  machine receipts — with the human sovereign deciding only genuine dilemmas.
- First useful milestone (M1): end-to-end run on real TL architecture material:
  intake → compile → dialectic search in leased worktrees → substrate gates →
  champion merge → verdict + receipt. Manual fallback exists at every step.
- Users and representative workflow: the operator (you) runs `stc compile
  <spec>` on a TL architecture question; the coordinator dispatches bounded
  packets to CLI-agent builders; you answer only ArchetypeDiff-style escalations;
  the run ends with a candidate diff, gate receipts, and a review record.
- Inputs and outputs: input = spec text + repo target; output = verified diff +
  ExecutionReceipt + JudiciaryVerdict + review record. Intermediate: TaskBundle,
  TaskPacket, CandidateProposal, ScoreBreakdown (all typed, hashed).
- Important exceptions/failure cases: worker confinement breach; all candidates
  fail gates; search budget exhausted with no champion; harness unavailable;
  cross-repo drift (sst/prompt-kit move under us).
- Non-goals and deferred ambitions: full TRACE memory (file-backed shim only in
  M1); Praxist integration; Trillion Dreams; mutmut per-node gating (champion
  only, see D4); forking sst/prompt-kit behavior (adapters live in STC).

## Requirements and targets

| ID | Requirement or proposed target | Status/authority | Source | How checked |
| --- | --- | --- | --- | --- |
| R1 | Integration code lives in STC; sst + prompt-kit consumed as sibling path deps | USER_DECISION | Grill T1 | pyproject + import graph |
| R2 | CLI-agent harnesses (agy/codex/muse) are the primary worker driver | USER_DECISION | Grill T1 | P03 acceptance |
| R3 | M1 acceptance runs REAL work self-hosted on STC (no trace-lite contact); LLM sessions + file shim are the TRACE substitute | USER_DECISION (amended in A3 review) | Grill T1 + A3 Q&A | P05 evidence |
| R4 | Mutmut ≥85% runs on merged champion only, not per search node | USER_DECISION (Sovereign ratification amending STC invariant §5) | Grill T2 | ADR + runner config |
| R5 | Builders may consume CLI-session budget autonomously; API-key spend needs per-case approval | USER_DECISION | Grill T2 | STATE spend log |
| R6 | No hard calendar cap; optimize for lasting quality and architecture | USER_DECISION | Grill T2 | Milestone-driven STATE |
| R7 | STC working tree pushed to git before integration edits; prune later as needed | USER_DECISION | Grill T1 note | P00 evidence |
| R8 | Originals stay authoritative; summaries are navigation-only | PROPOSAL (adopted from kit 00 + audit) | This plan | P02 acceptance |
| R9 | Acceptance binds to executed checks + full candidate identity incl. untracked files | PROPOSAL (adopted from kit B2/B3) | This plan | Every packet review |
| R10 | Per-packet wall budget 120 min, ≤40 CLI worker invocations (defaults, operator-adjustable) | PROPOSAL | This plan | STATE budget rows |

## Decisions and unresolved questions

| ID | Decision/question | Accepted/proposed/open/superseded | Rationale and source | Impact/dependents |
| --- | --- | --- | --- | --- |
| D1 | STC-root topology | Accepted | Grill T1; matches membrane discipline | All packets |
| D2 | CLI-agent primary harness | Accepted | Grill T1; uses existing sessions, no new keys | P03, P04 |
| D3 | Real-TL first use; integration focus stays on tooling, TL-arch shapes UI/UX | Accepted | Grill T1 + note | P05, ARCHITECTURE §UI |
| D4 | Mutmut champion-only (invariant amendment) | Accepted (ratified) | Grill T2; search cost vs mock-defense trade-off | P04, ADR-INT-01 |
| D5 | Spend authority: CLI auto / API ask | Accepted | Grill T2 | Coordinator prompt |
| D6 | Timebox: 2–4 days, quality over deadline | Accepted | Grill T2 | EXECUTION.md |
| D7 | No SST/prompt-kit forks in M1; STC-side adapters + wrappers only | Proposed | Minimize cross-repo blast radius; revisit if a defect blocks | P01, P04 |
| D8 | UI shape: `stc compile <spec>` CLI first; richer UX later | Proposed | Smallest operable surface for the TL-arch use case | P05 |
| Q1 | Exact per-packet CLI invocation caps for your sessions | Open | Affects P03/P04 budgets; defaults in R10 apply until set | P03–P05 |
| D9 | Seam: controller stack + STC-side custody-wrapper (no SST edits) | Accepted (A3) | RT-01/BT-01; only D7-legal wiring that exists | P04 |
| D10 | CLI-backed ModelGateway backend owned by P03/P04; gateway calls budgeted | Accepted (A3) | RT-02/BT-04; closes second model channel | P03, P04 |
| D11 | Trace-lite absent from M1; P05 self-hosted on STC | Accepted (operator A3) | BT-09; LLM+shim is the TRACE substitute | P05 |
| D12 | Tranche serialized (P01→P02); no parallel builders | Accepted (A3) | F4a/BT-15; fits D6 quality focus | EXECUTION |
| D13 | Live tests `@pytest.mark.live`, deselected in gate runs | Accepted (A3) | BT-08 vs code-enforced zero-skip | P03, P04 |
| D14 | P05 extends existing `run` command (not `compile`) | Accepted (operator A3) | RT-07/BT-03 collision | P05 |
| D15 | Gateway text-emission contract (STC-side profile + shaping ownership + gateway confinement); D7 intact, no SST edit | Accepted (A2-revisit; D1–D14 not reopened — sandbox confound scoped to this additive decision + Phase 0 experiment) | C1–C4: controller emits-text contract vs agentic harness shape; evidence/A2-revisit/REVIEW.md | P03-fix, P05-fix |

## Authorization and resources

- Work already authorized, with source and limits: M1 packets P00–P05 implementation
  in STC checkout (grill + A3 2026-09-13); CLI-agent spend per R5/R10; read-only
  inspection of sst, prompt-kit, trace. Trace-lite: ABSENT (no read, no write).
  No merge/release authority. No installs (B1 uses existing envs).
- Decisions/actions reserved by the user: API spend; merges to any `main`;
  invariant amendments beyond D4; scope changes crossing into sst/prompt-kit;
  D7-exception subclassing (RT-03 deferred trigger).
- Available environment, tools, people, compute, and time: WSL + Windows 11 host;
  agy/codex/muse CLIs; existing venvs; operator on call for escalations.
- Material limitations needing confirmation: Q1 caps; mutmut via WSL/Linux path
  parity for champion runs.

## Evidence and assumptions

| Claim | Observed/source-inspected/historical/assumed | Evidence and date | Required verification |
| --- | --- | --- | --- |
| STC schemas/protocols/custody seams exist as described | SOURCE_INSPECTED | models.py, interfaces.py, dispatch.py read 2026-09-13 | B1 per packet |
| SST TaskPacket/CandidateProposal/ScoreBreakdown + EvaluatorProtocol exist | SOURCE_INSPECTED | contracts.py, models.py, evaluator.py read 2026-09-13 | B1 per packet |
| Prompt-kit harness registry incl. CLI profiles exists | SOURCE_INSPECTED | harnesses/__init__.py, catalog.py read 2026-09-13 | P03 B1 handshake |
| Prompt-kit B3 trusts parsed verdict; grill is heuristic; identity omits untracked | SOURCE_INSPECTED + historical audit | orchestrator.py:1415–1490; audit 2026-09-13 | P01/P05 must not rely on these |
| SST custody runs acceptance_commands[0] only; PASS when empty | SOURCE_INSPECTED | custody.py:267–280 | P04 routes around via STC substrate |
| STC default builder runs ruff-format, not model implementation | HISTORICAL (audit) | audit 2026-09-13 | P03 B1 re-verify |
| One-day integration plausible | HISTORICAL_UNVERIFIED | audit 2026-09-13 | Superseded by D6 (quality focus) |

## Do-not-inherit list

- Prompt-kit grill percentage as architectural validation.
- Prompt-kit VERIFIED as proof acceptance executed.
- SST custody PASS with empty acceptance commands as a green gate.
- STC default `cli.py` builder path as model implementation.
- Any `INTEGRATION_EXECUTION_PLAN.md` from prior chats (not present in workspace;
  this plan supersedes it).

## Source map

| Source ID | Path/attachment/message | Relevant sections | Availability and qualifications |
| --- | --- | --- | --- |
| KIT | trace/docs/prompt-kit/ | FRAMEWORK, RUNBOOK, all prompts + templates | Read in full 2026-09-13 |
| AUDIT | trace-lite/docs/arch-review/INTEGRATION_READINESS_AUDIT_2026-09-13.md | All | Read; findings re-verified at seams |
| STC-INV | stc/01_INVARIANTS.md | §§1–7 | Read; §5 amended by D4 via ADR-INT-01 (to be written in P02) |
| GRILL | This session 2026-09-13 | 6 answers + subagent permission | Authoritative user decisions |

## Change record

| Revision | Change and reason | Authority/evidence | Affected packets |
| --- | --- | --- | --- |
| INT-2026-09-13.1 | Initial contract from grill | User grill | P00–P05 |
| INT-2026-09-13.2 | A3 revision: 64 findings disposed (DESIGN_REVIEW.md); seam choice, gateway owned, TL absent, serialized, run-extension | Red/blue audits + operator A3 answers | All packets, ARCH, EXECUTION, STATE |
| INT-2026-09-14.1 | A2-revisit fix tranche: D15 gateway text-emission contract (profile + shaping + confinement), INFO-2 runner-wall elapsed, B5-OBS-1 LAYOUT, P05 live re-run executes approved pins task; R1 stays backlog. SCOPE: fix tranche ONLY — .2 M1 record stays INTEGRATED and immutable; D1–D14 not reopened; D7-exception trigger defined but not met | P05 honest-partial + B5 record + INFO-1 sandbox confound (new evidence); design evidence/A2-revisit/REVIEW.md | P03/P04/P05 §Fix tranche, ARCH FIX deltas |
