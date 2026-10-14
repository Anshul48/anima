# Build handoff — implementation + deterministic preflight (design tranche CLOSED, authorization IN EFFECT)

Status: DESIGN APPROVED, CLEARED FOR BUILD 2026-09-19. The contract
(WALKTHROUGH.md + RATIFICATION.md, redlined + approval-corrected) and
the ONE coherent AUTHORIZATION.md (same dir, conditionally approved →
in effect) govern this build. No further architecture review: report
a concrete contradiction if one emerges, never silently change the
contract. Prior sessions closed; do not return to them. Product tree
was untouched through design (HEAD `ea1ca30`, 28/28 hashes,
1114+/14-); product edits are NOW authorized under §1 scope only.

## Budget box (coordinator-reconciled 2026-09-19 — the build's hard box)

- Spent (records): follow-up 8/20 → 12 left incl 6 reserve; design 3
  (doc-authorship: drafting session, HANDOFF-NEXT verdict session,
  P1/P2+corrections session `01a0ba10`). Pasted reviews uncounted —
  no box record; operator to correct if chargeable.
- Remaining: 3 spendable + 6 protected verification reserve.
- Implementation cap = lesser of 6 and 3 = **3 model-backed CLI
  sessions**. "≤6" is a ceiling, not a requirement. Local
  deterministic commands uncounted but logged. 0 live gateway calls
  (HARD — any attempt aborts). Reserve untouched. Cap-hit stops
  with an honest-partial report.
- Concrete 3-session plan (fits the allowance, no confirmation needed):
  S1 implement §1 scope; S2 `uv sync --locked` + §3 gate + preflight
  P1–P3/N1–N6; S3 fix/re-run reserve. If S1 overruns, S3 is consumed
  by the overrun and the preflight re-run needs a bounded budget
  amendment — never silent overrun, never reserve raid.

## Execution sequence (in this order, no skipping)

0. BOOTSTRAP (paste P3 below into the fresh build session). Cold
   re-probe FIRST: HEAD `ea1ca30`, 28/28
   (`/tmp/loose-manifest.sha256`, else debt-fix verify-1 REVIEW.md
   Identity block), pins sst `079f4de6`/prompt-kit `4f442a6c`/trace
   `a24a9370`, sst clean, product numstat 1114+/14-. Report
   PASS/FAIL with counts. On FAIL: stop, report, do not build.
1. IMPLEMENT AUTHORIZATION §1 scope ONLY (D-α…D-ζ + E1–E4 +
   C1–C12 corrections): F4 `>= (3, 12)` amendment; propagation AND
   head assert every lease; `normalize_diff()` + `_audit` +
   bundle durability; full-manifest tripwire WITH the honest label
   in code comments; versioned selection config + count tripwire;
   four linked records + actual argv + consumption checks + N6;
   E1 comments + behavioral check; E2 reversion-watch behavior;
   E4 intake re-hash. Untouched stays untouched (§5.1, A1 body,
   S5-1/2/3, D1). `01_INVARIANTS.md` never edited. Sequential runs
   only; stage outputs in `/tmp`, copy to evidence/ after
   completion; restore Timestamp+Checksum churn after test runs.
2. CONSTRUCT the env via the §2 box ONLY (`uv sync --locked`).
   Stop + report if interpreter/inputs unavailable. No pip venv.
3. PASS the §3 gate (all five exact-pass) or STOP for re-approval.
   This qualifies ONE actual env — nothing else.
4. RUN the preflight (P1–P3 + N1–N6, production path, 0 live calls).
   Wrong polarity, HMAC/auth failure, N5 delta, foreign-path write,
   floor/tool violation, tripwire trip, or live-call attempt ⇒ stop
   with a report (§5).
5. DELIVER: implemented changes + actual-path preflight results
   against P1–P3/N1–N6, or the concrete blocker encountered. No
   readiness ruling (separate decision), no attempt-4 (needs its
   own execution authorization + topology-derived cap).

## Standing constraints (do not renegotiate silently)

Commit rule (coordinator commits records + STATE at boundaries;
builders never commit; no push); `sst/`, `prompt-kit/`, `trace/`
read-only; `trace-lite/` never touched; evidence immutable
(errata append-only); no waiver by fallback — rejected/blocked
text returns to draft or honest NOT-READY.

## P3 — build-session bootstrap (paste into a FRESH session)

```text
STC integration build session (implementation + deterministic
preflight). Context: design tranche CLOSED, AUTHORIZATION.md IN
EFFECT. Read, in order:
stc/docs/builds/stc-integration/evidence/FOLLOWUP/design-tranche/HANDOFF-BUILD.md
(this file — your orders), AUTHORIZATION.md (the ONE coherent
authorization: scope §1, install §2, env gate §3, acceptance §4,
stops §5, box §6, rulings §7–§8, corrections §10), then
WALKTHROUGH.md + RATIFICATION.md (normative contract text), then
STATE.md.
Cold re-probe before any other work: HEAD==ea1ca30, 28/28 loose
hashes (manifest in /tmp/loose-manifest.sha256 if present, else
debt-fix verify-1 REVIEW.md Identity block), pins sst
079f4de6/prompt-kit 4f442a6c/trace a24a9370, sst clean, numstat
1114+/14- on the 10 tracked product files. Report PASS/FAIL with
counts.
Hard box: 3 model-backed CLI sessions for ALL of
implementation + preflight (cap = lesser of 6 and actual
allowance); 0 live gateway calls (any attempt = hard abort);
6-call verification reserve untouched; stop with a report on
cap-hit or any §5 stop. Local deterministic commands uncounted
but logged. Plan: S1 implement §1, S2 env+gate+preflight, S3
fix/re-run reserve.
On re-probe PASS: execute steps 1–5 of HANDOFF-BUILD.md in order.
No architecture review — implement the settled design; report a
concrete contradiction rather than silently changing the contract.
```
