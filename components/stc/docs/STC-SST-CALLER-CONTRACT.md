# STC-side SST caller contract (STC-owned, 2026-10-04)

Status: STC-side contract + acceptance procedure. SST implementation
is owned by the SST owner; STC consumes it only through deliberate
pins. Current integration acceptance waits on a usable qualified SST
version; nothing here claims it.

## 1. Deliberate pin

- Pin: `df78f42894a65c48f524337a498032617689a013`
  (lease_git.EXTERNAL_PINS["sst"], contract revision INT-2026-10-04.1;
  amended from 079f4de6 per §4 on SST cand-02 handoff
  docs/STC-HANDOFF.md @ df78f42).
- Resolution: `STC_SST_ROOT` env wins, else sibling `../sst`
  (lease_git._externals_roots). No vendoring, no substitutes.
- Integrity: leases fail closed unless the imported `sst` package's
  spot files match pin blobs (prove_import_integrity; spot list:
  `__init__.py`, `core/contracts.py`, `sandbox/custody.py`).
  A dirty SST tree is refused at lease time, never silently consumed.
- Probe: `dsh-plugin-stc/scripts/sst_compat_probe.py --sst-root <root>`
  reports COMPATIBLE / DIRTY (with exact files) / MISSING-SURFACE /
  NO-GIT. Observed 2026-10-04: pristine pin → COMPATIBLE;
  sibling working tree → DIRTY (`core/contracts.py`,
  `sandbox/custody.py` differ).

## 2. Called surface (STC dialectic runner)

Construction (dialectic_runner.py, STC-owned custody wrapper):

- `SSTSearchController(task, gateway, store, custody_manager, policy,
  capsule_compiler)` with `task: TaskPacket` (STC-built),
  `gateway`: STC gateway, `custody_manager`: STCCustodyWrapper
  (composition over CandidateCustodyManager + substrate + leases),
  `policy`: STC SearchPolicy, capsule from workspace root.
- Call: `await controller.execute_search(tree_id)` →
  `CandidateProposal | None`. STC maps SpendCapExceededError to the
  honest budget-exhausted path (the controller only catches
  ProviderGatewayError).
- Events scraped from SQLiteSSTStore: NODE_PROPOSED /
  SYNTHESIS_PROPOSED branch refs, score map, tainted-score veto +
  reselection of best untainted verified node.

Required SST surface (probe-enforced): contracts
(CandidateProposal, ScoreBreakdown, TaskPacket), controller +
execute_search, policy, store, custody, capsule compiler, gateway,
events (EventKind, SSTEvent), models (DeterministicGateResult).
`run_search`/`SearchResult` are newer optional surface: reported,
never required.

## 3. Ownership split

- SST supplies: bounded alternatives/search, proposal scoring,
  event-sourced tree records.
- STC retains: domain evaluation, execution custody (leases,
  baseline manifest, HMAC), resource accounting (spend ledger,
  wall clock authoritative), verdicts/dossiers, champion veto +
  reselection, judiciary audit, mutmut-once, permitted integration.

## 4. Pin-advance procedure (when SST owner delivers)

1. SST owner freezes + qualifies a version; STC records the offered
   commit + evidence pointer (no silent latest-tracking).
2. Run sst_compat_probe → must be COMPATIBLE on surface; bytes are
   compared against the OFFERED pin (amend EXTERNAL_PINS only here,
   as a contract amendment with dated record).
3. Stage: backend suite + e2e + a bounded caller exercise through
   DialecticRunner against the new pin; existing runs keep the old
   pin (no migration of started runs).
4. On green: amend the pin + contract revision note; on red: keep the
   old pin and return findings to the SST owner.

## 5. Current state and obligation

- STC qualification runs resolve SST from the pristine pin
  (e.g. PYTHONPATH to an exact-pin checkout); the dirty sibling
  fails closed as designed.
- Live-model proposal/search consumption at the current tree is
  UNQUALIFIED (historical: zero live proposals; current tree needs
  the SST owner's qualified version + a budgeted live batch).
  This obligation stays visible; it is not satisfied by fixture,
  mock, or TEST-provider runs.
