# STC Integration — Execution (M1)

Contract: INT-2026-09-13.2. Kit: `trace/docs/prompt-kit`.
Milestone: working `stc run` loop accepted on a self-hosted real STC task.

## Dependency DAG (serialized per D12)

```text
Wave 0:  P00 (checkpoint + ADR)
Wave 1:  P01 (adapters)
Wave 2:  P02 (memory)
Wave 3:  P03 (harness worker + CLI gateway backend)   [needs P02]
Wave 4:  P04 (dialectic runner)                       [needs P03]
Wave 5:  P05 (run-extension + self-hosted acceptance) [needs P04]
Wave 6:  B5 tranche integration (dedicated session)   [needs P05 VERIFIED]
```

One builder at a time; no shared-file contention by construction. Parallelism
was cut in A3 (F4a/BT-15): the 6-packet chain fits the D6 quality focus, and
serialization removes the merger/ownership problem entirely.

## Session topology (initial: 14 + 1 reserve)

| Role | Sessions | Notes |
| --- | --- | --- |
| Coordinator | 1 | Owns STATE.md (sole writer — BT-12), dispatch, routing; no product edits |
| Builders | 6 (P00–P05) | B1 then B2 each, serialized; bounded B4 inside builder session per RUNBOOK |
| Verifiers | 6 (P00–P05) | Fresh context per packet; B3 only, no fixes |
| B5 integration | 1 (dedicated) | Post-P05-VERIFIED; authors the tranche B5 record (BT-07) |
| A2-revisit reserve | 1 (pre-authorized) | Only if hypothesis fails or contract BLOCKS (BT-10) |

Count changes if: a repair needs isolation (new B4 session); a packet BLOCKS
on contract (reserve planning session activates); operator approves D7 revisit.

## Terminal dispositions (BT-10)

- VERIFIED per packet: all acceptance criteria evidenced on the named candidate.
- Degraded-manual: a PARKED disposition for autonomous execution with fallback
  (manual mode demonstrated); dependents may proceed only where the packet
  names manual compatibility (P03/P05 do; P01/P02/P04 never degrade).
- Honest-partial tranche stop: P05 partial dossier + named A2-revisit action =
  legitimate terminal state, reported precisely.
- Repair exhaustion: operator chooses — re-scope packet / activate A2-revisit /
  park with recorded fallback / abort tranche. No silent weakening.

## Exact launch messages

Variables: `KIT=trace/docs/prompt-kit`,
`PROJ=stc/docs/builds/stc-integration`, `REV=INT-2026-09-13.2`.

**Coordinator boot:**

```text
Read KIT/FRAMEWORK.md, PROJ/PROJECT.md, PROJ/ARCHITECTURE.md, PROJ/EXECUTION.md, PROJ/STATE.md, PROJ/DESIGN_REVIEW.md.
Contract revision REV. Follow KIT/prompts/coordinator.md for tranche P00–P05 + B5.
Execution authorization: implement M1 packets in the STC checkout; CLI-agent spend per PROJECT.md R5/R10 (builders report, you write STATE); read-only on sst, prompt-kit, trace; trace-lite ABSENT (no contact). No merges, no releases, no API spend, no sst/prompt-kit edits, no installs.
Available workers/tools: CLI-agent sessions (agy/codex/muse) + declared manual fallback; WSL + Windows 11 host.
Builders run serialized (D12). If you cannot launch sessions, give me the next ready launch message. Maintain STATE.md after every transition.
```

**Builder (per packet Pxx):**

```text
Read KIT/FRAMEWORK.md.
Project: PROJ. Packet: PROJ/packets/Pxx-<name>.md. Contract revision REV. Candidate/base: <P00 pin table>.
Run KIT/prompts/B1-readiness.md, then KIT/prompts/B2-build.md if READY and authorized.
Implement this packet; emit a spend record (zeros allowed); save the delivery record under PROJ/evidence/Pxx/attempt-N/ using KIT/templates/REVIEW.md. Report transitions; do not write STATE.md. Do not claim independent verification.
```

**Verifier (fresh session, per packet):**

```text
Read KIT/FRAMEWORK.md and KIT/prompts/B3-verify.md.
Project: PROJ. Packet: <packet path>. Contract revision REV.
Candidate: <exact identity/location from delivery>. Delivery: <delivery record path>.
Inspect the candidate and reproduce the decisive checks. Write the review record (KIT/templates/REVIEW.md) with PASS/FAIL/INCONCLUSIVE mapped criterion-by-criterion. Do not fix product code.
```

**Repair (on FAIL/INCONCLUSIVE):**

```text
Follow KIT/prompts/B4-repair.md.
Packet: <path>. Candidate: <identity>. Findings: <review path>. Contract revision REV.
Repair within the existing contract (≤2 cycles default); return material contract conflicts to planning with evidence. Then return the candidate to B3 for affected-scope verification.
```

**B5 tranche integration (dedicated session, after P05 VERIFIED):**

```text
Read KIT/FRAMEWORK.md and KIT/prompts/B5-integrate.md.
Project: PROJ. Contract revision REV.
Integrate this verified tranche: P00–P05 at <their VERIFIED candidate identities + review paths>.
Integration authorization: read-only assembly + integration checks; reserved: any merge/release, any packet-scope behavior change (route to B4 instead).
Confirm prerequisite candidates/verdicts match the combined tree; run the milestone workflow (dry-run + manual + dossier inspection); reassess degraded items; write the integration record and update capability claims. Mark INTEGRATED only when the combined criteria pass.
```

**A2-revisit reserve (pre-authorized; only on trigger):**

Triggers: P05 honest-partial dossier, a packet BLOCKED on contract, or
champion-veto-proves-insufficient evidence (RT-03 deferred trigger).

```text
Read KIT/FRAMEWORK.md, PROJ/PROJECT.md, PROJ/ARCHITECTURE.md, PROJ/DESIGN_REVIEW.md, PROJ/STATE.md.
Contract revision REV. This is the pre-authorized A2-revisit planning session (BT-10).
Trigger: <dossier / finding / evidence path>.
Follow KIT/prompts/A2-design.md for the affected scope only: revise the design, update the affected packet(s), record the decision in PROJECT.md's change record, and bump the contract revision. Do not implement product code. Do not reopen settled decisions without new evidence.
Return: revised packet links, the new revision, and the exact re-entry launch (which B1/B2/B3 reruns).
```

**Escalation format (coordinator → operator):**

Builders and the coordinator escalate only genuine dilemmas, in exactly
this shape (mechanical failures stay in the repair loop):

```text
ARCHETYPE DIFF <id> — <packet/candidate>
Dilemma: <one sentence>
Context: <what blocked, evidence path>
Option A: <title> — pro / con / locks [...]
Option B: <title> — pro / con / locks [...]
Recommendation: <A|B + one-line why>
Cost of waiting: <what stalls until decided>
```

> **Note (INT-2026-09-13.2):** LAUNCH_KIT.md is the authoritative single source
> for all paste-ready prompts. Where this file disagrees with LAUNCH_KIT.md,
> LAUNCH_KIT.md wins. This patch was applied to align the two files.

## Stop conditions

Tranche stops when: B5 INTEGRATED (M1 done); honest-partial close (P05 partial
+ A2-revisit named); any packet repair budget exhausted (operator picks from
enumerated options); a required dependency BLOCKS with no fallback; operator
halts. Partial completion is reported precisely per STATE.md — sessions ending
≠ milestone passing.
