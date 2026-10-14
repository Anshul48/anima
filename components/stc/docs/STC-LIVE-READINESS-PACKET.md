# Live readiness packet: SST consumption + quality batch (2026-10-04)

One concrete packet. No spend authorized by this document; the single
budget decision (§6) gates all paid legs. Quota-free legs (§2a) run
any time.

## 1. Dependency identity

| Dependency | Identity (observed 2026-10-04) | Status |
|---|---|---|
| SST pin (authoritative) | `079f4de6fd43881c2f1b529f0612f1df64a62f32` (EXTERNAL_PINS; execute_search only) | Consumed; live-model use UNQUALIFIED |
| SST sibling (candidate) | `df78f42…` (full: `df78f42894a65c48f524337a498032617689a013`), clean tree, `run_search` present | AWAITS owner blessing; probe DIRTY-vs-old-pin as expected for a newer commit |
| Model | Sail `deepseek-ai/DeepSeek-V4.1-Flash`, default mode, `https://api.sailresearch.com/v1` | Key + URL verified 2026-09-30; key held by operator |
| Pricing (official DeepSeek) | `deepseek-flash`: $0.30 in / $1.20 out per M peak; half off-peak | Re-confirmed 2026-10-04 (multiple sources); Sail-side may differ — ledger $ labeled estimates |

## 2. Acceptance checks

**2a. SST pin-advance (quota-free; runs after owner blesses a commit).**
Per caller-contract §4, in order: (1) record offered commit +
evidence pointer; (2) `sst_compat_probe.py --sst-root <offered>
--git-repo <offered>` → must be COMPATIBLE on surface (amend
EXTERNAL_PINS only here, as a dated contract amendment); (3) stage:
backend suite `-m "not live"` + plugin e2e + bounded caller
exercise (§2b) against the new pin; (4) green → amend pin +
contract revision; red → keep old pin, return findings to owner.
Started runs keep their pin (no migration).

**2b. Bounded SST caller exercise (paid; calibration-first).**
DialecticRunner live-search runs against the new pin: run 1 is
CALIBRATION (measure token profile; no success claim); runs 2–3
proceed only inside resized ceilings. Measures per run: proposals
emitted (count), champion-or-honest-NoChampion, ledger integrity,
verdict/dossier shape. Ceilings: ≤500k input + ≤200k output tokens
per run pre-calibration (≈$0.39 peak worst each); 20 min timeout.
Stop: probe non-COMPATIBLE, calibration >2× estimate (resize or
stop), any ceiling breach fails the run (never extends it).

**2c. Quality batch (paid; existing plans govern).**
Pilot first: 6 episodes, b1 vs b2, `scripts/live-pilot.py`
(PILOT-PLAN: ≤4000 output tokens/call, 15 min timeout,
`--authorize-spend` + `SAIL_API_KEY`, verdict checkers, JSONL
ledger). Full batch (18 episodes, +b0, tasks 4–6) proceeds only on
a pilot directional signal. Promotion stays human-gated;
inconclusive keeps b2-gated provisional.

## 3. Estimated cost (assumptions explicit; caps bind, estimates don't)

- Pilot worst/peak: $0.24/episode → 6 ≈ **$1.44** (existing
  arithmetic; off-peak halves).
- Full batch worst/peak: 18 × $0.24 ≈ **$4.32**.
- SST exercise worst/peak: 3 × $0.39 ≈ **$1.17** pre-calibration.
- Program worst/peak total ≈ **$7** (off-peak ≈ $3.50).

## 4. Hard caps (recommended; operator sets final numbers)

- Pilot: **$5.00**, abort at $4.00 without separation.
- Full batch: **$15.00**, abort at $12.00 without separation.
- SST exercise: **$4.00**, abort at $3.20 without separation.
- Combined program ceiling: **$20.00** across all paid legs.

## 5. Stop conditions (all legs)

Abort a policy after 3 consecutive fault-handling failures; abort
the batch at 80% of cap with no separation; any episode/run past
any ceiling is a failed episode, not an extension; probe
non-COMPATIBLE stops the SST leg immediately with findings
returned to the owner; any overrun risk aborts first, spend
ledger per episode/run.

## 6. The ask (single decision before any paid execution)

1. Bless (or name) the SST commit for §2a, or decline live SST
   consumption for this window.
2. Approve legs (SST exercise / pilot / full batch — any subset)
   and set final caps (defaults §4).
3. Provide `SAIL_API_KEY` via repo-root `.env` (gitignored, single
   line, never echoed); confirm off-peak timing preference.
