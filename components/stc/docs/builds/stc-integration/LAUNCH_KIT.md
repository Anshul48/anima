# STC Integration — Complete launch kit (M1)

Contract revision: INT-2026-09-13.2. Single source for every paste-ready
prompt. If a prompt below ever disagrees with EXECUTION.md, this file wins and
EXECUTION.md must be patched to match.

Variables: `KIT=trace/docs/prompt-kit`,
`PROJ=stc/docs/builds/stc-integration`, `REV=INT-2026-09-13.2`.

Fire order: 1 (coordinator boot) → 2 (P00 builder) → 3 (P00 verifier) →
[4 on FAIL/INCONCLUSIVE] → next packet's 2→3 → … → 5 (B5) after P05 VERIFIED.
6 only if a hypothesis fails or a packet BLOCKS on contract.

## 1. Coordinator boot

```text
Read KIT/FRAMEWORK.md, PROJ/PROJECT.md, PROJ/ARCHITECTURE.md, PROJ/EXECUTION.md, PROJ/STATE.md, PROJ/DESIGN_REVIEW.md.
Contract revision REV. Follow KIT/prompts/coordinator.md for tranche P00–P05 + B5.
Execution authorization: implement M1 packets in the STC checkout; CLI-agent spend per PROJECT.md R5/R10 (builders report, you write STATE); read-only on sst, prompt-kit, trace; trace-lite ABSENT (no contact). No merges, no releases, no API spend, no sst/prompt-kit edits, no installs.
Available workers/tools: CLI-agent sessions (agy/codex/muse) + declared manual fallback; WSL + Windows 11 host.
Builders run serialized (D12). If you cannot launch sessions, give me the next ready launch message. Maintain STATE.md after every transition.
```

## 2. Builder (per packet, B1 then B2)

```text
Read KIT/FRAMEWORK.md.
Project: PROJ. Packet: PROJ/packets/Pxx-<name>.md. Contract revision REV. Candidate/base: <P00 pin table>.
Run KIT/prompts/B1-readiness.md, then KIT/prompts/B2-build.md if READY and authorized.
Implement this packet; emit a spend record (zeros allowed); save the delivery record under PROJ/evidence/Pxx/attempt-N/ using KIT/templates/REVIEW.md. Report transitions; do not write STATE.md. Do not claim independent verification.
```

Packet files: `packets/P00-checkpoint.md`, `packets/P01-adapters.md`,
`packets/P02-memory.md`, `packets/P03-worker.md`, `packets/P04-runner.md`,
`packets/P05-cli-acceptance.md`.

## 3. Verifier (fresh session per packet, B3)

```text
Read KIT/FRAMEWORK.md and KIT/prompts/B3-verify.md.
Project: PROJ. Packet: <packet path>. Contract revision REV.
Candidate: <exact identity/location from delivery>. Delivery: <delivery record path>.
Inspect the candidate and reproduce the decisive checks. Write the review record (KIT/templates/REVIEW.md) with PASS/FAIL/INCONCLUSIVE mapped criterion-by-criterion. Do not fix product code.
```

## 4. Repair (on FAIL/INCONCLUSIVE, B4)

```text
Follow KIT/prompts/B4-repair.md.
Packet: <path>. Candidate: <identity>. Findings: <review path>. Contract revision REV.
Repair within the existing contract (≤2 cycles default); return material contract conflicts to planning with evidence. Then return the candidate to B3 for affected-scope verification.
```

On repair exhaustion the coordinator offers the operator exactly these options:
re-scope packet / activate A2-revisit (prompt 6) / park with recorded fallback /
abort tranche. No silent weakening.

## 5. B5 tranche integration (dedicated session, after P05 VERIFIED)

```text
Read KIT/FRAMEWORK.md and KIT/prompts/B5-integrate.md.
Project: PROJ. Contract revision REV.
Integrate this verified tranche: P00–P05 at <their VERIFIED candidate identities + review paths>.
Integration authorization: read-only assembly + integration checks; reserved: any merge/release, any packet-scope behavior change (route to B4 instead).
Confirm prerequisite candidates/verdicts match the combined tree; run the milestone workflow (dry-run + manual + dossier inspection); reassess degraded items; write the integration record and update capability claims. Mark INTEGRATED only when the combined criteria pass.
```

## 6. A2-revisit reserve (pre-authorized; only on trigger)

Triggers: P05 honest-partial dossier, a packet BLOCKED on contract, or
champion-veto-proves-insufficient evidence (RT-03 deferred trigger).

```text
Read KIT/FRAMEWORK.md, PROJ/PROJECT.md, PROJ/ARCHITECTURE.md, PROJ/DESIGN_REVIEW.md, PROJ/STATE.md.
Contract revision REV. This is the pre-authorized A2-revisit planning session (BT-10).
Trigger: <dossier / finding / evidence path>.
Follow KIT/prompts/A2-design.md for the affected scope only: revise the design, update the affected packet(s), record the decision in PROJECT.md's change record, and bump the contract revision. Do not implement product code. Do not reopen settled decisions without new evidence.
Return: revised packet links, the new revision, and the exact re-entry launch (which B1/B2/B3 reruns).
```

## 7. Escalation format (coordinator → operator)

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
