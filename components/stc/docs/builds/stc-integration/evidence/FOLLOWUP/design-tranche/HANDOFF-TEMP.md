# TEMP session handoff — STC integration, post-close-out, pre-architecture-session

Status: TEMPORARY working note (not a tranche record). Consume at the start
of the focused architecture session, then delete at design-tranche close.
Supersedes nothing; the durable artifacts are `PLAN.md` (rev 2, same dir),
`STATE.md`, and commit `ea1ca30`.

## Where things stand (2026-09-19)

- Follow-up tranche CLOSED NOT-READY at `ea1ca30` (772 files, records-only).
  Debt-fix + combined-fix close-out verified PASS; accepts 1–3 consolidated
  PASS (attempt-3 BLOCKED-WIRING CONFIRMED); F1/carry/A1/A3 PASS; live-exp
  WIN. Zero champions ever; live judiciary / merge-execution /
  mutmut-on-champion / worker harnesses never exercised live.
- Candidate: HEAD `ea1ca30` (records close atop `edf5389`) + the same
  28-file loose set (tracked 1114+/14-), 28/28 hashes per the verify-1
  records. Product code UNCOMMITTED per the standing commit rule.
- Pins: sst `079f4de6…` (clean), prompt-kit `4f442a6c…`, trace `a24a9370…`.
- F2 (lease-layout skips), F3 (committed-bytes E2E), F4 (3.11-vs-3.12 env
  assert) explicitly UNRESOLVED; F1 (joint lacks ruff/mypy) env-blocked.
- Budget: 8/20 CLI spent, $0.00. CORRECTED box: **12 total remaining
  INCLUDING the protected 6-call reserve** (rev-1's "12 + 6" was wrong).
- Design-tranche `PLAN.md` rev 2 is drafted (same dir, uncommitted) and
  AWAITING operator disposition: Approve / Request changes / Cancel.
  **Do not start Work Plan unit 1 until approval.**

## Operator corrections folded into rev 2 (binding)

- Binding sequence: Design → isolated prototype if necessary → contract
  approval → implementation → actual-path preflight → readiness ruling →
  live attempt. No step's evidence substitutes for a later step's.
- Honesty rule: no claim established on a narrower path than the one it
  governs (the diag lesson, applied to our own work). Prototypes are
  feasibility-only and barred from readiness claims. Spec simulation is
  not preflight. A readiness-shaped claim fails the session.
- The contract must walk one candidate creation → judgment answering
  bytes / env / tests / deps / receipt at every transition, resolving:
  (1) candidate identity incl. untracked inputs, nested-lease ref
  selection, git metadata isolation, sufficient key (base_commit alone
  is insufficient); (2) trusted test selection (mandatory set,
  broaden-on-uncertainty, naming rule) + explicit auto-disable
  resolution; (3) pinned read-only lease deps + import-integrity proof;
  (4) authoritative 3.12 env by STC-owned-vs-TRACE comparison, frozen.
- No waiver by fallback: rejected amendments → re-draft or honest
  NOT-READY. Any waiver/downgrade/carve-out needs its own explicit
  approval.
- Scope fence: candidate evaluation path only; do not reopen the whole
  STC architecture. Isolated candidate commits are legitimate evaluation
  machinery (subject to the commit rule); whole-tree checks move cadence,
  never deleted for greenness.

## Open questions awaiting the operator (from PLAN.md)

1. Scratch refs in lease-local disposable git acceptable? (yes → D-CT1c,
   no → lease-scoped E2E). 2. NEW STC-owned 3.12 env an acceptable
   comparison outcome, or reuse existing envs only? (No in-session
   installs either way.) 3. Attempt-4 CLI cap within the corrected box?

## Standing operating constraints (do not renegotiate silently)

- Commit rule: coordinator commits records + STATE.md at packet/tranche
  boundaries only; builders/verifiers never commit; product stays
  uncommitted for review; no push (stc has no remote). Name staged paths;
  audit the staged set before committing.
- Read-only: `sst/`, `prompt-kit/`, `trace/`; `trace-lite/` never listed,
  read, or written. `01_INVARIANTS.md` is Sovereign-owned (draft
  amendments, never edit). Evidence files immutable (V1-INFO-1 precedent:
  errata append-only, originals byte-exact).
- Test pollution precedent: `specs/invariants/*.md` Timestamp+Checksum
  churn from test runs is restored via `git checkout --` after runs.
- Run discipline: sequential runs only (no parallel interpreters — shared
  worktree leases contaminate); stage outputs in `/tmp` during runs, copy
  to evidence/ only after completion (chaperone-sweep lesson).
- Envs: real-gates `<ws>/learn-anything/.venv` (3.11.15, full toolchain)
  + joint `<ws>/trace/.venv-linux` (3.12.3, pytest-only); shims
  `/tmp/p01-shim /tmp/p04-shim /tmp/p03-pinned-kit` are MACHINE STATE —
  re-verify before use, recreate per P01 packet if `/tmp` was cleaned.
- New-session hygiene was recommended for the architecture session; if
  taken, that session re-probes HEAD + 28/28 + pins + sst-clean cold.

## Pointer list (absolute workspace: <workspace-root>)

- `stc/docs/builds/stc-integration/evidence/FOLLOWUP/design-tranche/PLAN.md`
- `stc/docs/builds/stc-integration/STATE.md`
- `stc/docs/builds/stc-integration/evidence/FOLLOWUP/debt-fix/verify-1/REVIEW.md`
- `stc/docs/builds/stc-integration/evidence/FOLLOWUP/combined-fix/verify-1/REVIEW.md`
- `stc/docs/builds/stc-integration/evidence/FOLLOWUP/accept-123-verify/REVIEW.md`
- `stc/docs/builds/stc-integration/evidence/FOLLOWUP/debt-fix/attempt-1/run-diag-e2e.py`
- Gate code: `stc/src/stc/substrate/runner.py` (gates + receipt binding),
  `stc/src/stc/integration/dialectic_runner.py:460-505` (per-node verify),
  `:836-871` (merge + mutmut-once), `stc/src/stc/worktree/manager.py:407-481`
  (lease alloc from `main`), `stc/01_INVARIANTS.md` §5,
  `stc/ADR-INT-01-mutmut-champion-only.md`.

## Suggested next-session prompt

"Read `design-tranche/PLAN.md` (rev 2) and `HANDOFF-TEMP.md` in
`stc/docs/builds/stc-integration/evidence/FOLLOWUP/`. Re-probe HEAD +
28/28 + pins + sst-clean cold, confirm your understanding of D-CT1–D-CT7
and the three open questions — do not start Work Plan unit 1 until I
reply Approve."
