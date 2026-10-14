# CONTRACTS.md — anima-substrate contract pins

Two pinned contracts: the resume-coupling contract (CC1–CC9,
carried from successor-006) and the participant-family contract
(v1, new in this package). Both are enforced by tests; any §7-style
change needs a contract delta filed here.

## Part 1. Resume-coupling contract (CC1–CC9)

Carried from `prototype/successor-006/COUPLING-CONTRACT.md` (the 8
resume-coupling items behind the Q3
DEMONSTRATED-WITH-COUPLING-LIST verdict, formalized as a testable
contract). Source of the 8 items: `reuse-demo-001/REUSE-REPORT.md`
§"Interface gaps" (+ `closeout-20261004/REUSE-CALIBRATION.md`
§"Calibrated claim"); clause pins:
`successor-contract/WORLD-CONTRACT-v1.md` C1–C6.

Each item below states the promise, the implementing code in THIS
package, and the asserting test. All tests run through the consumer
surface (`anima_substrate.host.api`, plus the documented `open_run`
host surface) on fresh state:

```
.venv/bin/python -m pytest tests/test_coupling.py -q
```

Envelope (same as the carried code): single-host, local disk,
process-crash-only (no fsync), toy scale. The contract pins the
shapes a host and the resume engine share; it does NOT promise
cross-host refs, multi-writer safety, or disk-loss tolerance.

### CC1. Invoke call contract (gap 1)

- Promise: `invoke(caller, callee, capability, version, args_ref, fn,
  *, cost_usd, time_s, ...)`. Exactly one invocation is consumed per
  call, ON SUCCESS ONLY. A raised `fn` records an `invoke` entry with
  `payload.error` set and consumes nothing (no `consume` entry).
- Code: `host/minihost.py:MiniHost.invoke` (kwargs `cost_usd=`/`time_s=`;
  `consume` only on the success leg).
- Test: `tests/test_coupling.py::test_cc1_invoke_kwargs_and_consume_on_success_only`
  (signature pin + success consume-count equality + failed-invoke
  holdings-untouched).

### CC2. Invoke payload keys (gap 2)

- Promise: a success entry payload MUST carry `capability`,
  `args_ref`, `result_ref`, and MUST NOT carry `error`. The resume
  matcher keys on exactly these four conditions.
- Code: `host/resume.py:successful_invokes` / `host/resume.py:scan_succeeded`.
- Test: `tests/test_coupling.py::test_cc2_invoke_payload_keys` (shape on a
  real consumer run + error-entry exclusion from the matcher).

### CC3. Args files (gap 3)

- Promise: `store_args` writes JSON with at least `formulation_ref`
  and `candidate_refs` keys. Resume reads these keys; byte-level
  compatibility is required across the kill boundary.
- Code: `host/minihost.py:MiniHost.store_args`,
  `host/resume.py:check_args_keys` (runs on every plan step).
- Test: `tests/test_coupling.py::test_cc3_args_keys_and_byte_compat_across_kill`
  (missing-key refusal + real-SIGKILL resume with the args file
  byte-identical and still keying the matcher).

### CC4. Result schemas (gap 4)

- Promise: propose `result_ref` JSON carries `candidate_refs` and
  `champion_id`. (Score clause: NOT-APPLICABLE, not unimplemented —
  this pipeline has no `sched.score` capability; independent-checker
  verdicts take scoring's place. Carried from the successor-001 base
  report via successor-005 CONTRACT-GAPS.md.)
- Code: `host/resume.py:SchedWorld.write_proposal`,
  `host/resume.py:check_propose_result` (write-time assert + re-read).
- Test: `tests/test_coupling.py::test_cc4_result_schemas` (schema on a real
  run + malformed-result refusal).

### CC5. Host read shape (gap 5)

- Promise: resume reads `host.worlds[ID].lifecycle` and compares to
  the string `"active"`. Canonical lifecycle strings:
  `active|suspended|dissolved|retired` (+ pre-active `"proposed"`;
  `"retired"` declared but never exercised — no promise attaches).
- Code: `host/resume.py:require_active`, `host/minihost.py:MiniHost.worlds`.
- Test: `tests/test_coupling.py::test_cc5_lifecycle_read_shape` (active
  read + suspended refusal + denied invoke with recorded deny).

### CC6. Deny shape (gap 6)

- Promise: `deny(actor, action, reason)` — positional order pinned.
  Every refusal path raises AND records a deny.
- Code: `host/minihost.py:MiniHost.deny` + all refusal sites.
- Test: `tests/test_coupling.py::test_cc6_deny_positional_order` (signature
  pin + recorded entry actor/action/reason).

### CC7. World-handle file conventions (gap 7)

- Promise: resume needs `world.state_dir` (path-like) plus
  `verdicts/verdict.json` (phase verdict) and the
  `formulations/*.json` glob (latest artifact). The v1 SHOULD
  (`latest.json` manifest replacing the glob) is NOT implemented —
  the glob remains normative per the clause's own fallback
  (obedience, not deviation; carried from successor-005).
- Code: `host/resume.py:SchedWorld`, `host/resume.py:latest_formulation`,
  `host/resume.py:read_verdict`.
- Test: `tests/test_coupling.py::test_cc7_world_handle_shape` (dir +
  latest-glob + phase-verdict + per-task history on a real run).

### CC8. Suspend/reattach shapes (gap 8)

- Promise: `suspend(world_id, actor, reason, pending_effects)` /
  `reattach(world_id, actor, reason)` — world_id first, actor second.
- Code: `host/minihost.py:suspend` / `host/minihost.py:reattach`,
  `host/fusion.py:quarantine_world` (suspends with `pending_effects`
  naming the standby transfer).
- Test: `tests/test_coupling.py::test_cc8_suspend_reattach_shapes`
  (signature pins + roundtrip + reattach-when-active refusal).

### CC9. Unmodified-engine resume (the Q3 demonstration itself)

- Promise: the resume engine this contract couples to drives
  resume-by-skip on a fresh host WITHOUT modification:
  re-driving a finished plan skips every step with
  `re_executed_invokes == 0`. (Port note: s006 additionally pinned
  `resume.py` byte-identical to frozen s005; the maintained package
  replaces byte pins with PROVENANCE discipline — every shipped
  file's sha256 recorded in `PROVENANCE.md` and enforced by
  `tests/test_successor.py::test_14`.)
- Code: `host/resume.py` (sha recorded in `PROVENANCE.md`).
- Test: `tests/test_coupling.py::test_cc9_engine_carried_unmodified_and_resumes`
  (PROVENANCE consistency + full-plan second drive skips all).

### Coverage claim

9/9 items implemented in this package, each with a consuming code path
and an asserting test above. The two carried qualifications
(CC4-score not-applicable, CC7-glob fallback) and the
`retired`-unexercised note are the only qualifications; none changes
an implemented promise.

## Part 2. Participant-family contract (v1, package-new)

A participant family is everything a world needs to do one KIND of
task work: its advertised capabilities/representations, its grant
shape, and four operations — create (advertise), run, recover,
change (upgrade). Families are added by adding a module that
registers itself; the host is never edited for a new family.

Contract v1 (frozen rules — `participants/__init__.py`):

- C1. Every family operation takes an explicit state dir chosen by
  the caller and writes nothing outside it.
- C2. Capabilities are advertised at world creation and never change
  afterwards; a version upgrade births a successor world with
  lineage back to the old one (the old pins keep verifying).
- C3. run() reports measured cost (ledger consumes) and never claims
  generality beyond the task it ran.
- C4. recover() never invents state: it replays, adopts, or reports.

Registered families (`anima-substrate families`):

| family | version | kind | staging |
|---|---|---|---|
| sched | v1 | toy sched task class (carried fixtures + work plan) | none (stdlib) |
| relcheck | v1 | file-backed release-identity checks over real files | none (stdlib) |
| relcheck | v2 | v1 + compat-rule checks; upgrades v1 worlds | none (stdlib) |
| sst | v1 | snapshot-verified TEST search | caller-staged root at pinned `df78f42` (see `docs/SST-STAGING.md`) |

Family surface checks (`tests/test_families.py`): registry
roundtrip, duplicate-registration refusal, unknown-family refusal
naming what IS registered, public-surface-only imports (families
bind `anima_substrate.host.api` / `anima_substrate.host.minihost`
(plus public `host.pipeline` / `host.routing` constants where a
family needs them)
and the registry — no private host modules), per-family
create/run/recover/change through the consumer surface, and the
relcheck v1→v2 upgrade with old pins reproducible.

Contract delta log (append; never edit entries):

- (none yet — v1 is the initial filing)
