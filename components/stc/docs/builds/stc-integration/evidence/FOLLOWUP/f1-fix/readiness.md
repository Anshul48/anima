# F1-fix — B1 readiness (preserve full harness evidence on gateway/harness failures)

Author role and date: f1-fix-builder / 2026-09-14
Packet: STC follow-up tranche (F1 stderr-truncation gap) @ INT-2026-09-14.1
Base/candidate: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` + loose set
(this tranche's own writes under `evidence/FOLLOWUP/f1-fix/`).

## Gate 0 — predecessor gate (FIX-B5 NOT-READY record read)

- `evidence/FIX-B5/REVIEW.md` read in full: verdict **NOT-READY** (honest
  no-champion partial, valid evidence, automation not ready); F1 carried OPEN
  (§4: "preserve full harness stderr (file artifact or raised tail)").
- `evidence/P05-fix/attempt-1/REVIEW.md` read in full (F1 finding: `note[:300]`
  at `harness_worker.py:493` + `cli_gateway.py` raised error; B2 call-2 cause
  lost mid-word, recovered only via out-of-band diag).
- `evidence/P05-fix/verify-1/REVIEW.md` read in full (F1 endorsed: row-2 note
  exactly 300 chars ending mid-word on the live path).
- Gate 0: SATISFIED — F1 is the authorized follow-up input; no B4 route was
  available in-packet, so this tranche is the repair.

## Gate 1 — candidate identity + drift

- `git rev-parse HEAD` = `edf5389873e4d4a2a4752ee0aa2159289398495e` (matches
  tasked base). HEAD is exactly one commit ahead of the FIX-B5 base `4544190`;
  that commit (`edf5389`, "fix tranche close") contains 196 files, ALL under
  `docs/builds/` (verified: `git show --name-only` has zero non-docs paths) —
  evidence + STATE only, zero product files. Drift EXPLAINED, no STOP.
- 6 fix-owned hashes re-verified byte-exact vs tasked prefixes:
  `__init__.py 10571421…bac40` ✓, `cli_gateway.py b6b73ed3…cacc7` ✓,
  `harness_worker.py 49017ef4…20535` ✓,
  `test_integration_harness_worker.py 3b4a9654…11ce6` ✓,
  `dialectic_runner.py 19a2e448…8283b` ✓,
  `test_integration_dialectic.py 6e059f08…f1019` ✓.
- Tracked mods: `cli.py 33476f34…124bb` ✓, `dispatch.py dc75c56e…13c7` ✓
  (numstat 576/0 + 333/7 — the pre-existing loose set, untouched).
- Pins re-probed: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (status clean),
  prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
  `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`. All exact.
- sst/prompt-kit/trace read-only; `trace-lite/` never touched (this session:
  never listed, read, or written).
- Gate 1: SATISFIED — no unexplained drift.

## Gate 2 — environment (0 CLI calls; fully scripted)

- Joint `trace/.venv-linux/bin/python` 3.12.3
  (`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`); real-gates
  `learn-anything/.venv/bin/python` 3.11.15
  (`PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`);
  `PYTHONDONTWRITEBYTECODE=1`; pytest cwd `ws/stc`.
- Shims verified present, no recreation: `/tmp/p01-shim/rich`,
  `/tmp/p03-pinned-kit/prompt_kit`, `/tmp/p04-shim/{dotenv,pydantic_settings,yaml}`.
- Both interpreter binaries verified present. This tranche spends 0 CLI calls
  (scripted runners/harnesses only); the ≥6 acceptance+verification reserve is
  untouched.
- Gate 2: SATISFIED.

## F1 fix design (owned files ONLY)

### Root cause

Full failure bytes EXIST in `HarnessResult` (`content` = full stdout,
`error` = full stderr, only `.strip()`-ed) but are discarded after logging:
`SpendLedger.log_row` truncates `note[:300]` (`harness_worker.py:493`) and the
gateway raises with `note[:300]` (`cli_gateway.py:191`) — a truncated HEAD, so
a codex-header echo buries the real cause (capacity error at byte ~5000+).

### Fix: failure-evidence sidecar + pointer note + raised tail

1. **`harness_worker.py`** (product):
   - `failure_evidence_path(ledger_path)`: sidecar
     `<ledger.parent>/<ledger.stem>.failures.jsonl` next to the spend ledger.
     Live dossier runs pass `dossier_dir/spend_ledger.jsonl` (`cli.py:1334`),
     so artifacts land UNDER THE RUN DIR (`spend_ledger.failures.jsonl`);
     default ledger lands under `evidence/P03/`. Dossier `spend.json` copies
     ledger rows verbatim, so the pointer propagates with `dossier.py`
     untouched.
   - `write_failure_evidence(...)`: appends ONE JSON record per failed attempt:
     FULL `stdout_full` + FULL `stderr_full`, `exit_code`, `timed_out`,
     effective `model`/`profile`, `duration_s`, `out_bytes`, ids
     (`channel/harness/task_id/lease_id/attempt`), and candidate identity
     (`stc_head` via `git rev-parse`, `owned_files` full+short sha256 of the
     two owned product files — best-effort, never raises). Returns
     `(path, record_id)` or `None` on OSError (warn, never masks).
   - `SpendLedger.log_row(..., failure_evidence: str | None = None)`: adds the
     `"failure_evidence"` row key (`<abs path>#<id>`) ONLY when not None —
     success rows stay byte-identical. The `note[:300]` backstop is kept.
   - `HarnessWorker.worker_fn_for`: captures full stdout/stderr per attempt; on
     any `not ok` attempt writes the record and sets the note to
     `{reason} [full stderr: {sidecar}#{id}]` (short pointer, never the only
     copy). Crash path (exception, no result) records `stderr_full` = full
     exception text.
   - `HarnessWorker.dispatch`: pre-creates (touches) the sidecar BEFORE the
     chaperone audit window and adds it to `outer_exclude` (exact-path, same
     mechanism as the ledger file itself).
2. **`cli_gateway.py`** (product):
   - `CLIGatewayBackend.generate(..., profile: str | None = None)`: on failure
     writes the record, logs the pointer note, and raises with the error TAIL
     (last 300 chars, where the real cause lives) + artifact pointer instead
     of the truncated head. `generate_async` threads `profile`;
     `CLIModelGateway.invoke` passes its resolved `profile_name` so the
     record carries the effective profile. Confinement path untouched (no
     stderr truncation there). Success path byte-identical (no record, no new
     row key, same response).
3. **`tests/unit/test_integration_harness_worker.py`** (append-only, no
   weakening): new `test_f1_*` tests proving (a) fast-fail full stderr
   recoverable byte-exact from the sidecar with a >300-char stderr whose real
   cause sits at the TAIL (capacity-error mirror), gateway + worker channels;
   (b) ledger note points at the record; (c) success-path rows/bytes unchanged
   (exact pre-fix key set, zero failure records); (d) crash path preserved.

### Why a single JSONL sidecar, not one file per failure (tripwire constraint)

`dispatch.py` `_enumerate_outer` honors `outer_exclude` by EXACT path only;
new files under an excluded dir still trip the outer wire (proven by
`test_ledger_exclusion_does_not_hide_siblings`). A fail-then-retry-success
worker run returns normally, so the post-run audit WOULD flag per-failure
files as "created path" breaches (and quarantine-move the evidence). A single
sidecar touched before the audit window + exact-excluded is append-invisible,
exactly like the ledger file itself. Gateway path has no chaperone (its
tracked-status assertion runs inside `run_harness_attempt`, before any write)
and is safe either way; it shares the sidecar for one recovery shape.

### Non-goals / confinement

- No argv/shaping changes (confinement paths untouched); no `dispatch.py`,
  `cli.py`, `dossier.py`, `dialectic_runner.py` changes; no STATE.md writes; no
  commits. `note[:300]` backstop retained (harmless once notes are pointers).

## B1 verdict: READY

B2 plan (0 CLI calls): implement the design above → new `test_f1_*` green →
existing P03 suite (`test_integration_harness_worker.py -m "not live"`) green
on BOTH interpreters → `ruff check` + `ruff format --check` + `mypy --strict`
on owned files → `evidence/FOLLOWUP/f1-fix/attempt-1/` + REVIEW.md with Hash
Identity for every file created/modified.

## Spend (B1)

CLI calls: 0. Cap 20 incl. ≥6 acceptance+verification reserve → 20 remain.

## Hash Identity (B1)

This record is the B1 write; per tranche precedent it is not self-listed here.
Its sha256 is recorded in `evidence/FOLLOWUP/f1-fix/attempt-1/REVIEW.md`.
