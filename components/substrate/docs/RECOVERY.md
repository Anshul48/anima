# RECOVERY.md — interruption boundaries + recovery procedures

Crash model (carried): single host, local disk, PROCESS crash only
(`Popen.kill()` / `os._exit`). No fsync anywhere: durability across
power/media loss is the disk-loss class and out of scope. Side
files are old-or-new (temp + `os.replace`); the LEDGER is not
tear-proof (a torn tail line refuses loudly as disk-loss).

## 1. Reopen (every command starts here)

`api.open_run(state_dir)` replays `ledger.jsonl`
(registry/holdings/grants/lifecycle), restores creation lineage +
authorities + procedure tables from `create` payloads, re-applies
ledger `revoke` entries (WITHOUT this a revocation LAPSES), and
restores `channels.json` (M3; missing ≡ no channels yet, torn ≡
loud disk-loss refusal). One balance-neutral `host_reopen` marker
is appended. Worlds without creation specs come back ledger-only
with authority WITHHELD (fail closed) — birth worlds through
`birth_world` / the family create path so specs are recorded.

## 2. recover_op (R1/R11)

`api.recover_op(state_dir, worlds=None, ...)`:

1. Repairs `worlds.json` specs missing for ledger-known worlds.
2. Refuses fail-closed when conservation fails (fix the violation
   first; `inspect` reports read-only).
3. Completes interrupted births + fusions automatically.
4. Completes ONE interrupted fission when `--fission/--left/--right/
   --partition` name it (refuses with exact re-run steps
   otherwise; supplied partition must agree with recorded
   progress).
5. Adopts side-complete procedure steps (L3) and reports
   adopted / re-runnable (L2) / nothing-to-do (never spawns).
6. Detects partial quarantines and prints the supported repair
   ops (operator picks complete vs rollback — never automated).
7. Settles exactly `--worlds` (default: settles NOTHING), never a
   world inside an uncompleted partial op.

Every step is ledger-conditional: re-running after a kill during
recovery converges. Covered: kill-during-settle / fuse / fission /
quarantine-transfer / procedure-step / spec-repair / recovery
itself (kill-at-every-boundary tests + repeated kills + real
SIGKILL legs).

## 3. Procedure interruption (L1–L5)

- L1 before-begin / before-second-begin: no trace / partial skip.
- L2 killed mid-step: re-runs fresh (reported re-runnable).
- L3 DONE without invoke: verified then adopted exactly-once
  (or refuse-adopt + re-run).
- L4 torn ledger tail: loud disk-loss refusal (restore from
  backup; the documented procedure re-runs the round).
- L5 kill during adopt: converges exactly-once.
- Recovery never spawns; timeouts kill the child group.

## 4. Quarantine-transfer repair (R11, operator-directed)

- `ops quarantine-complete`: finish recorded handoffs + append the
  `quarantine` entry.
- `ops quarantine-rollback`: reverse recorded handoffs + reattach
  + append `quarantine_rollback`.
Both validate-before-mutate and converge on re-run after a kill
during repair. A started direction must finish (the ops refuse to
mix handoff directions). `recover_op` detects + names the steps.

## 5. Channel persist (M3)

`channels.json` is rewritten crash-atomically on every registry
mutation (get/send/remove). Kill-during-persist lands old-or-new;
reopen loads whatever landed and `recover_op` runs clean (no
repair entries exist for channels — there is nothing partial to
complete). Proven by `test_kill_during_channel_persist_converges`
(hook `SUBSTRATE_CRASH_MID_SIDE_WRITE=channels.json`, rc=42).

## 6. Export/import failure classes (M3)

- Export writes fresh bundles only (existing out dir refuses);
  `EXPORT.json` lands LAST, so a killed export is an unverifiable
  dir that import refuses (`no EXPORT.json … re-export`).
- Import verifies every bundle byte against its pin
  pre-mutation (tamper refuses naming the file), requires a FRESH
  state dir, explicit full grants (all three keys, non-negative),
  and re-verifies procedure pins against staged bytes (manifest
  refs rewritten to the new root; the bundle is never written).

## 7. Test-only crash hooks (never set in production)

| hook | effect |
|---|---|
| `SUBSTRATE_CRASH_AFTER_APPENDS=N` | `os._exit(42)` after N ledger appends |
| `SUBSTRATE_CRASH_AT=point` | `os._exit(42)` at a named op boundary |
| `SUBSTRATE_CRASH_MID_APPEND=N` | tear the Nth ledger append (disk-loss fixture) |
| `SUBSTRATE_CRASH_MID_SIDE_WRITE=name` | die mid-write of side file `name` (rc=42, target untouched) |

## 8. Operator rules

1. Never hand-edit `ledger.jsonl`, `worlds.json`, `channels.json`,
   or staged bundles: reopen verifies and refuses mismatches.
2. A `<name>.tmp-<pid>` file is a benign replace orphan (never
   read; safe to delete).
3. `retired` lifecycle is declared but unexercised — do not rely
   on it.
4. Out of scope (operator repair, no automation): disk loss,
   multi-writer, cross-host.
