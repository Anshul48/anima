// STC run interruption / recovery state machine (no DSH imports; node:test-covered).
//
// Truthful pause/cancel/redirect/resume semantics over the durable run store:
//
// - `interrupted` is an explicit run state, distinct from the terminal
//   `killed` / `failed` / `completed` outcomes recorded in exit.json. A plain
//   stc_cancel leaves NO recovery record, so cancelled runs keep resolving to
//   `killed` (cancel-with-proof is untouched by this module).
// - Pause and interrupt share the `interrupted` state: there is no SIGSTOP'd
//   live-process primitive, because a stopped child cannot be truthfully
//   resumed across a restart. Interrupt = stop the live job (done by the
//   tool layer, which owns the jobs registry) + record checkpoint/snapshot
//   here; resume = verify, then launch a linked continuation run.
// - `recover` re-attaches to a live job or approves a resume ONLY after
//   verifying candidate/evaluator identity (run.json vs the interrupt-time
//   snapshot) and side-effect completion (every ledger entry completed with
//   proof). Anything uncertain -> `needs-decision` with evidence. Recovery
//   never silently retries, and a status query never mutates a record.
// - `redirect` terminally invalidates pending work under a new brief ref;
//   recovery after redirect is refused (start a new run under the new brief).
//
// All records persist as recovery.json (+ effects.json) inside the run dir.
// Builder C owns brief.json / stc-runstore.ts; this module only READS the
// runstore (readRecord/runDir/runExists/writeRecord) and never modifies it.

import { readdirSync } from 'node:fs'
import { join } from 'node:path'
import { readRecord, runDir, runExists, writeRecord } from './stc-runstore.ts'

export const RECOVERY_FILE = 'recovery.json'
export const EFFECTS_FILE = 'effects.json'
export const RUN_FILE = 'run.json'
export const EXIT_FILE = 'exit.json'

/** Durable run states. `interrupted` is explicit and never conflated with terminal outcomes. */
export type DurableRunState =
  | 'running'
  | 'interrupted'
  | 'redirected'
  | 'killed'
  | 'failed'
  | 'completed'
  | 'unknown'

export type EffectStatus = 'completed' | 'pending' | 'uncertain'

export interface SideEffect {
  id: string
  kind: string
  status: EffectStatus
  /** Evidence the effect completed (required for status completed). */
  proof?: string
  recordedAt: string
}

export interface EffectsLedger {
  runId: string
  effects: SideEffect[]
}

export interface IdentitySnapshot {
  argv: string[]
  cwd: string
  spec: string
  mode: string
  jobId: string
}

export interface HistoryEvent {
  at: string
  event: string
  detail?: string
}

export interface RecoveryRecord {
  version: 1
  runId: string
  state: 'interrupted' | 'redirected' | 'recovered'
  checkpoint: string
  reason: string
  interruptedAt: string
  snapshot: IdentitySnapshot
  history: HistoryEvent[]
  redirect?: { briefRef: string; at: string; reason: string; invalidated: string[] }
  recovery?: {
    at: string
    decision: string
    evidence: string[]
    continuedBy?: string
    skipped?: string[]
  }
}

export interface RunStateView {
  state: DurableRunState
  detail: string
  runId: string
  checkpoint: string
  reason: string
  briefRef: string
  decision: string
  continuedBy: string
}

export type RecoverDecision =
  | { decision: 'reattached'; evidence: string[] }
  | {
      decision: 'resumed'
      evidence: string[]
      resumePlan: {
        argv: string[]
        cwd: string
        spec: string
        mode: string
        resumedFrom: string
        /** Completed effect ids the continuation MUST skip (no duplicate side effects). */
        skip: string[]
      }
    }
  | { decision: 'needs-decision'; evidence: string[]; blockers: string[] }
  | { decision: 'already-terminal'; terminal: string; evidence: string[] }
  | { decision: 'refused-redirected'; evidence: string[]; briefRef: string }

function now(): string {
  return new Date().toISOString()
}

function asRecord(v: unknown): Record<string, unknown> {
  return (typeof v === 'object' && v !== null ? v : {}) as Record<string, unknown>
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function strArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((e): e is string => typeof e === 'string') : []
}

/** Absolute run dir, or throw for an unknown run id. */
export function requireRunDir(store: string, runId: string): string {
  if (!runId || !runExists(store, runId)) throw new Error(`unknown run: ${runId || '(missing run_id)'}`)
  return runDir(store, runId)
}

export function readRecovery(dir: string): RecoveryRecord | null {
  const v = readRecord(dir, RECOVERY_FILE)
  if (!v || typeof v !== 'object') return null
  return v as RecoveryRecord
}

export function readEffects(dir: string): EffectsLedger | null {
  const v = readRecord(dir, EFFECTS_FILE)
  if (!v || typeof v !== 'object') return null
  return v as EffectsLedger
}

function snapshotOf(run: Record<string, unknown>): IdentitySnapshot {
  return {
    argv: strArray(run['argv']),
    cwd: str(run['cwd']),
    spec: str(run['spec']),
    mode: str(run['mode']),
    jobId: str(run['jobId']),
  }
}

function snapshotDiff(a: IdentitySnapshot, b: IdentitySnapshot): string[] {
  const out: string[] = []
  if (JSON.stringify(a.argv) !== JSON.stringify(b.argv)) out.push('argv differs from interrupt-time snapshot')
  if (a.cwd !== b.cwd) out.push(`cwd changed: ${JSON.stringify(a.cwd)} vs ${JSON.stringify(b.cwd)}`)
  if (a.spec !== b.spec) out.push(`spec changed: ${JSON.stringify(a.spec)} vs ${JSON.stringify(b.spec)}`)
  if (a.mode !== b.mode) out.push(`mode changed: ${JSON.stringify(a.mode)} vs ${JSON.stringify(b.mode)}`)
  return out
}

/**
 * Record an explicit interruption at a declared checkpoint. The caller (tool
 * layer) stops the live job first; this persists the checkpoint + identity
 * snapshot. Refuses already-terminal runs so cancel/completion proof is never
 * rewritten. Idempotent while interrupted (first checkpoint wins).
 */
export function markInterrupted(
  store: string,
  runId: string,
  opts: { checkpoint: string; reason?: string; jobStopped?: string },
): RecoveryRecord {
  const dir = requireRunDir(store, runId)
  const checkpoint = (opts.checkpoint ?? '').trim()
  if (!checkpoint) throw new Error('interrupt needs a declared checkpoint')
  const existing = readRecovery(dir)
  if (existing && existing.state === 'interrupted') {
    existing.history.push({ at: now(), event: 'interrupt-duplicate', detail: checkpoint })
    writeRecord(dir, RECOVERY_FILE, existing)
    return existing
  }
  if (existing && existing.state === 'redirected') {
    throw new Error(`run ${runId} was redirected (brief ${existing.redirect?.briefRef ?? '?'}); start a new run`)
  }
  const exit = asRecord(readRecord(dir, EXIT_FILE))
  const terminal = str(exit['status'])
  if (terminal === 'completed' || terminal === 'failed') {
    throw new Error(`run ${runId} is already terminal (${terminal}); interrupt refused`)
  }
  if (terminal === 'killed' && !existing) {
    throw new Error(`run ${runId} was already cancelled (killed); interrupt refused`)
  }
  const run = asRecord(readRecord(dir, RUN_FILE))
  const rec: RecoveryRecord = {
    version: 1,
    runId,
    state: 'interrupted',
    checkpoint,
    reason: opts.reason ?? '',
    interruptedAt: now(),
    snapshot: snapshotOf(run),
    history: [
      ...(existing?.history ?? []),
      {
        at: now(),
        event: 'interrupted',
        detail: `checkpoint=${checkpoint}${opts.jobStopped ? ` job=${opts.jobStopped}` : ''}${opts.reason ? ` reason=${opts.reason}` : ''}`,
      },
    ],
    ...(existing?.recovery ? { recovery: existing.recovery } : {}),
  }
  writeRecord(dir, RECOVERY_FILE, rec)
  return rec
}

/**
 * Upsert one side-effect attestation in the run's ledger. `proof` is required
 * when status is completed; without proof the entry stays non-verifying and
 * recovery reports needs-decision.
 */
export function recordEffect(
  store: string,
  runId: string,
  effect: { id: string; kind: string; status: EffectStatus; proof?: string },
): EffectsLedger {
  const dir = requireRunDir(store, runId)
  if (!effect.id.trim()) throw new Error('effect needs an id')
  if (effect.status !== 'completed' && effect.status !== 'pending' && effect.status !== 'uncertain') {
    throw new Error(`unknown effect status: ${JSON.stringify(effect.status)}`)
  }
  if (effect.status === 'completed' && !(effect.proof ?? '').trim()) {
    throw new Error(`completed effect ${JSON.stringify(effect.id)} needs proof`)
  }
  const ledger: EffectsLedger = readEffects(dir) ?? { runId, effects: [] }
  const entry: SideEffect = {
    id: effect.id,
    kind: effect.kind,
    status: effect.status,
    ...(effect.proof ? { proof: effect.proof } : {}),
    recordedAt: now(),
  }
  const at = ledger.effects.findIndex((e) => e.id === effect.id)
  if (at >= 0) ledger.effects[at] = entry
  else ledger.effects.push(entry)
  writeRecord(dir, EFFECTS_FILE, ledger)
  return ledger
}

/**
 * Terminally invalidate a run's pending work under a new brief ref. The caller
 * stops the live job first and reports it via `jobStopped`. Refuses
 * already-terminal runs (cancel/completion proof wins over redirect).
 */
export function redirectRun(
  store: string,
  runId: string,
  opts: { briefRef: string; reason?: string; jobStopped?: string },
): RecoveryRecord {
  const dir = requireRunDir(store, runId)
  const briefRef = (opts.briefRef ?? '').trim()
  if (!briefRef) throw new Error('redirect needs a brief_ref')
  const existing = readRecovery(dir)
  if (existing && existing.state === 'redirected') return existing
  const exit = asRecord(readRecord(dir, EXIT_FILE))
  const terminal = str(exit['status'])
  if (terminal === 'completed' || terminal === 'failed') {
    throw new Error(`run ${runId} is already terminal (${terminal}); redirect refused`)
  }
  if (terminal === 'killed' && !existing) {
    throw new Error(`run ${runId} was already cancelled (killed); redirect refused`)
  }
  const ledger = readEffects(dir)
  const invalidated = (ledger?.effects ?? [])
    .filter((e) => e.status !== 'completed')
    .map((e) => e.id)
  const run = asRecord(readRecord(dir, RUN_FILE))
  const rec: RecoveryRecord = {
    version: 1,
    runId,
    state: 'redirected',
    checkpoint: existing?.checkpoint ?? '',
    reason: opts.reason ?? existing?.reason ?? '',
    interruptedAt: existing?.interruptedAt ?? now(),
    snapshot: existing?.snapshot ?? snapshotOf(run),
    history: [
      ...(existing?.history ?? []),
      {
        at: now(),
        event: 'redirected',
        detail:
          `brief=${briefRef} invalidated=[${invalidated.join(',')}]` +
          `${opts.jobStopped ? ` job=${opts.jobStopped}` : ''}${opts.reason ? ` reason=${opts.reason}` : ''}`,
      },
    ],
    redirect: { briefRef, at: now(), reason: opts.reason ?? '', invalidated },
    ...(existing?.recovery ? { recovery: existing.recovery } : {}),
  }
  writeRecord(dir, RECOVERY_FILE, rec)
  return rec
}

/**
 * Resolve the truthful durable state of a run. PURE READ — never writes, so a
 * status query can never resurrect work. `jobState` is the live registry view
 * when the caller has it (`running`/`stopping`/terminal/undefined-when-gone).
 */
export function resolveRunState(store: string, runId: string, jobState?: string): RunStateView {
  const dir = requireRunDir(store, runId)
  const rec = readRecovery(dir)
  const exit = asRecord(readRecord(dir, EXIT_FILE))
  const terminal = str(exit['status'])
  const base: RunStateView = {
    state: 'unknown',
    detail: '',
    runId,
    checkpoint: rec?.checkpoint ?? '',
    reason: rec?.reason ?? '',
    briefRef: rec?.redirect?.briefRef ?? '',
    decision: rec?.recovery?.decision ?? '',
    continuedBy: rec?.recovery?.continuedBy ?? '',
  }
  if (rec?.state === 'redirected') {
    return {
      ...base,
      state: 'redirected',
      detail:
        `redirected to brief ${rec.redirect?.briefRef ?? '?'}; ` +
        `pending invalidated [${(rec.redirect?.invalidated ?? []).join(',')}]; start a new run under the new brief`,
    }
  }
  if (rec?.state === 'interrupted' && !rec.recovery) {
    return {
      ...base,
      state: 'interrupted',
      detail: `interrupted at checkpoint ${rec.checkpoint}${rec.reason ? ` (${rec.reason})` : ''}; recover to reattach or resume`,
    }
  }
  if (rec?.state === 'interrupted' && rec.recovery?.decision === 'resumed') {
    return {
      ...base,
      state: 'interrupted',
      detail: `interrupted at checkpoint ${rec.checkpoint}; resumed by run ${rec.recovery.continuedBy ?? '(launch pending)'}`,
    }
  }
  if (terminal === 'completed' || terminal === 'failed' || terminal === 'killed') {
    return { ...base, state: terminal, detail: str(exit['detail']) || `exit: ${terminal}` }
  }
  if (jobState === 'running' || jobState === 'stopping') {
    return {
      ...base,
      state: 'running',
      detail: rec?.recovery?.decision === 'reattached' ? 'reattached to live job' : `job ${jobState}`,
    }
  }
  if (jobState === 'completed' || jobState === 'failed' || jobState === 'killed') {
    return { ...base, state: jobState, detail: `job ${jobState} (no exit record yet)` }
  }
  return {
    ...base,
    state: 'unknown',
    detail: 'no live job handle and no exit record (e.g. after a restart); interrupt at a declared checkpoint or recover to make the state explicit',
  }
}

/**
 * Evaluate recovery for a run. `probe` reports whether the original job is
 * still live in this process (`live`) or not (`gone`, e.g. after a restart).
 *
 * - live job, no terminal exit -> `reattached` (no relaunch; the run continues)
 * - gone + verified identity + every ledger effect completed with proof ->
 *   `resumed` with a resume plan whose `skip` list names every completed
 *   effect (the continuation MUST NOT repeat them)
 * - identity drift, missing/uncertain effect evidence, or never-interrupted ->
 *   `needs-decision` with evidence and blockers (NO silent retry)
 * - terminal exit / prior cancel -> `already-terminal`; post-redirect ->
 *   `refused-redirected` (both launch nothing)
 *
 * Only the reattached/resumed evaluations persist a recovery stamp; every
 * other outcome leaves the run exactly as it was (plus one history line
 * recording the evaluation, which changes no state and launches nothing).
 */
export function recover(
  store: string,
  runId: string,
  opts?: { probe?: () => 'live' | 'gone' },
): RecoverDecision {
  const dir = requireRunDir(store, runId)
  const rec = readRecovery(dir)
  const run = asRecord(readRecord(dir, RUN_FILE))
  const exit = asRecord(readRecord(dir, EXIT_FILE))
  const terminal = str(exit['status'])

  if (rec?.state === 'redirected') {
    return {
      decision: 'refused-redirected',
      briefRef: rec.redirect?.briefRef ?? '',
      evidence: [
        `run was redirected to brief ${rec.redirect?.briefRef ?? '?'} at ${rec.redirect?.at ?? '?'}`,
        `invalidated pending work: [${(rec.redirect?.invalidated ?? []).join(',')}]`,
        'resume refused: start a new run under the new brief',
      ],
    }
  }
  if (terminal === 'completed' || terminal === 'failed') {
    return {
      decision: 'already-terminal',
      terminal,
      evidence: [`exit.json records terminal status ${terminal}: ${str(exit['detail']) || '(no detail)'}`],
    }
  }
  if (terminal === 'killed' && !rec) {
    return {
      decision: 'already-terminal',
      terminal: 'killed',
      evidence: ['exit.json records killed with no recovery record: this run was cancelled; cancel proof stands'],
    }
  }

  const liveness = opts?.probe?.() ?? 'gone'
  if (liveness === 'live') {
    const stamped: RecoveryRecord = {
      version: 1,
      runId,
      state: rec?.state ?? (terminal === 'killed' ? 'interrupted' : 'recovered'),
      checkpoint: rec?.checkpoint ?? '',
      reason: rec?.reason ?? '',
      interruptedAt: rec?.interruptedAt ?? now(),
      snapshot: rec?.snapshot ?? snapshotOf(run),
      history: [...(rec?.history ?? []), { at: now(), event: 'reattached', detail: 'live job found in registry; run continues' }],
      ...(rec?.redirect ? { redirect: rec.redirect } : {}),
      recovery: { at: now(), decision: 'reattached', evidence: ['job is live in this process; no relaunch needed'] },
    }
    writeRecord(dir, RECOVERY_FILE, stamped)
    return { decision: 'reattached', evidence: ['job is live in this process; no relaunch needed'] }
  }

  if (!rec || rec.state === 'recovered') {
    noteEvaluation(dir, rec, 'needs-decision: run was never interrupted')
    return {
      decision: 'needs-decision',
      blockers: ['run was never interrupted at a declared checkpoint'],
      evidence: [
        'no recovery record: there is no checkpoint or identity snapshot to resume from',
        'interrupt at a declared checkpoint first, then recover',
      ],
    }
  }

  const drift = snapshotDiff(snapshotOf(run), rec.snapshot)
  if (drift.length > 0) {
    noteEvaluation(dir, rec, `needs-decision: identity drift (${drift.join('; ')})`)
    return {
      decision: 'needs-decision',
      blockers: ['candidate/evaluator identity changed since interruption'],
      evidence: [...drift, `snapshot taken at ${rec.interruptedAt}; refusing to resume a different run`],
    }
  }

  const ledger = readEffects(dir)
  if (!ledger || ledger.effects.length === 0) {
    noteEvaluation(dir, rec, 'needs-decision: no side-effect evidence')
    return {
      decision: 'needs-decision',
      blockers: ['no side-effect completion evidence'],
      evidence: [
        `interrupted at checkpoint ${rec.checkpoint} with identity verified, but no effects ledger attests side-effect completion`,
        'attest completed side effects with proof, or decide explicitly; refusing silent retry',
      ],
    }
  }
  const unverified = ledger.effects.filter((e) => e.status !== 'completed' || !(e.proof ?? '').trim())
  if (unverified.length > 0) {
    noteEvaluation(dir, rec, `needs-decision: ${unverified.length} unverified effect(s)`)
    return {
      decision: 'needs-decision',
      blockers: unverified.map((e) => `effect ${e.id} (${e.kind}) is ${e.status}${e.proof ? '' : ' without proof'}`),
      evidence: [
        `interrupted at checkpoint ${rec.checkpoint} with identity verified, but ${unverified.length} side effect(s) are not verifiably complete`,
        ...unverified.map((e) => `- ${e.id} [${e.kind}]: ${e.status}${e.proof ? ` proof=${e.proof}` : ' (no proof)'}`),
        'refusing silent retry: completed effects would repeat or pending effects would fork',
      ],
    }
  }

  const skip = ledger.effects.map((e) => e.id)
  const evidence = [
    `interrupted at checkpoint ${rec.checkpoint}; candidate/evaluator identity verified unchanged`,
    `all ${skip.length} side effect(s) verifiably complete with proof; continuation must skip [${skip.join(',')}]`,
  ]
  const stamped: RecoveryRecord = {
    ...rec,
    history: [...rec.history, { at: now(), event: 'resume-approved', detail: `skip=[${skip.join(',')}]` }],
    recovery: { at: now(), decision: 'resumed', evidence, skipped: skip },
  }
  writeRecord(dir, RECOVERY_FILE, stamped)
  const snap = snapshotOf(run)
  return {
    decision: 'resumed',
    evidence,
    resumePlan: {
      argv: snap.argv,
      cwd: snap.cwd,
      spec: snap.spec,
      mode: snap.mode,
      resumedFrom: runId,
      skip,
    },
  }
}

/** Append one history line for a non-terminal evaluation (creates no state, launches nothing). */
function noteEvaluation(dir: string, rec: RecoveryRecord | null, detail: string): void {
  if (!rec) return
  writeRecord(dir, RECOVERY_FILE, {
    ...rec,
    history: [...rec.history, { at: now(), event: 'recover-evaluated', detail }],
  } satisfies RecoveryRecord)
}

/** Link a launched continuation run back to the interrupted run (tool layer, after spawn). */
export function recordContinuation(store: string, runId: string, continuedBy: string): RecoveryRecord {
  const dir = requireRunDir(store, runId)
  const rec = readRecovery(dir)
  if (!rec?.recovery || rec.recovery.decision !== 'resumed') {
    throw new Error(`run ${runId} has no approved resume to link`)
  }
  const stamped: RecoveryRecord = {
    ...rec,
    history: [...rec.history, { at: now(), event: 'continued', detail: `continuedBy=${continuedBy}` }],
    recovery: { ...rec.recovery, continuedBy },
  }
  writeRecord(dir, RECOVERY_FILE, stamped)
  return stamped
}

/**
 * Resolve a run id from a jobs-registry job id by scanning durable run.json
 * records (agents learn the job id from stc_run before any run id exists on
 * disk elsewhere). Refuses ambiguity: after a restart, registry counters
 * repeat, so two runs may share one job id — then the caller must pass run_id.
 */
export function findRunByJob(store: string, jobId: string): string {
  if (!jobId.trim()) throw new Error('job_id must be a non-empty string')
  let entries: string[]
  try {
    entries = readdirSync(store)
  } catch {
    throw new Error(`unknown job: ${jobId}`)
  }
  const matches: string[] = []
  for (const name of entries) {
    if (!name.startsWith('run-')) continue
    const run = asRecord(readRecord(join(store, name), RUN_FILE))
    if (str(run['jobId']) === jobId) matches.push(str(run['runId']) || name.slice('run-'.length))
  }
  if (matches.length === 0) throw new Error(`unknown job: ${jobId}`)
  if (matches.length > 1) {
    const live = matches.filter((id) => {
      const exit = asRecord(readRecord(runDir(store, id), EXIT_FILE))
      const t = str(exit['status'])
      return t !== 'completed' && t !== 'failed' && t !== 'killed'
    })
    if (live.length === 1) return live[0] as string
    throw new Error(
      `job ${jobId} matches ${matches.length} runs across restarts (${matches.join(',')}); pass run_id to disambiguate`,
    )
  }
  return matches[0] as string
}
