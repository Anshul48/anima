// Durable run-record store (no DSH imports; node:test-covered).
// Run dirs live outside the repo by default: $STC_DSH_STORE,
// else $DSH_HOME/stc-runs, else os.tmpdir()/stc-dsh-runs.

import { randomBytes } from 'node:crypto'
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { createBrief, type Brief, type BriefInput } from './stc-brief.ts'

export function storeRoot(): string {
  if (process.env['STC_DSH_STORE']) return resolve(process.env['STC_DSH_STORE'])
  if (process.env['DSH_HOME']) return resolve(process.env['DSH_HOME'], 'stc-runs')
  return join(tmpdir(), 'stc-dsh-runs')
}

export function newRunId(): string {
  return randomBytes(6).toString('hex')
}

export function runDir(store: string, id: string): string {
  return join(store, `run-${id}`)
}

/** Create a run dir. Returns the absolute dir. */
export function createRunDir(store: string, id: string): string {
  const dir = runDir(store, id)
  mkdirSync(dir, { recursive: true })
  return dir
}

export function appendLog(dir: string, text: string): void {
  appendFileSync(join(dir, 'console.log'), text, 'utf8')
}

/** Last `maxBytes` of console.log, '' when absent. */
export function readLogTail(dir: string, maxBytes = 32768): string {
  try {
    const buf = readFileSync(join(dir, 'console.log'), 'utf8')
    return buf.length > maxBytes ? buf.slice(buf.length - maxBytes) : buf
  } catch {
    return ''
  }
}

export function writeRecord(dir: string, name: string, value: unknown): void {
  writeFileSync(join(dir, name), JSON.stringify(value, null, 2) + '\n', 'utf8')
}

export function readRecord(dir: string, name: string): unknown {
  try {
    return JSON.parse(readFileSync(join(dir, name), 'utf8')) as unknown
  } catch {
    return null
  }
}

export function runExists(store: string, id: string): boolean {
  return existsSync(join(runDir(store, id), 'run.json'))
}

// --- DSH-session <-> STC-run correlation (STC1, additive) ---
//
// A run index record (run.json) carries nullable sessionId/briefId/policyId.
// The reverse index <store>/sessions/<sessionId>.json lists that session's
// run ids so getBySession() needs no tree scan. All writers below are
// idempotent: re-attaching the same link changes nothing.

export interface RunCorrelation {
  sessionId?: string
  briefId?: string
  policyId?: string
}

export interface RunRecord extends RunCorrelation {
  runId: string
  sessionId: string | null
  briefId: string | null
  policyId: string | null
  [key: string]: unknown
}

export interface CreateRunOptions extends RunCorrelation {
  /** Use this run id instead of minting one. */
  id?: string
  /** When present, a v1 brief is created in the run dir (id: briefId ?? new). */
  brief?: BriefInput
  now?: string
}

export interface CreatedRun {
  id: string
  dir: string
  record: RunRecord
  brief: Brief | null
}

function checkSessionId(sessionId: string): string {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(sessionId)) {
    throw new Error(`invalid session id for store paths: ${sessionId}`)
  }
  return sessionId
}

function sessionIndexFile(store: string, sessionId: string): string {
  return join(store, 'sessions', `${checkSessionId(sessionId)}.json`)
}

function indexSession(store: string, sessionId: string, runId: string, now: string): void {
  const file = sessionIndexFile(store, sessionId)
  mkdirSync(join(store, 'sessions'), { recursive: true })
  let runIds: string[] = []
  try {
    const raw = JSON.parse(readFileSync(file, 'utf8')) as { runIds?: unknown }
    if (Array.isArray(raw.runIds)) runIds = raw.runIds.filter((r): r is string => typeof r === 'string')
  } catch {
    /* absent or corrupt: rebuild from this run */
  }
  if (!runIds.includes(runId)) runIds.push(runId)
  writeFileSync(
    file,
    JSON.stringify({ sessionId, runIds, updatedAt: now }, null, 2) + '\n',
    'utf8',
  )
}

/**
 * Create a run dir + index record with correlation attached. Additive
 * companion to createRunDir(); nothing existing routes through here until
 * the stc-run.ts hook lands (see DESIGN note in evidence/stc1-brief/).
 */
export function createRun(store: string, opts: CreateRunOptions = {}): CreatedRun {
  if (opts.sessionId !== undefined) checkSessionId(opts.sessionId)
  const id = opts.id ?? newRunId()
  const now = opts.now ?? new Date().toISOString()
  const dir = createRunDir(store, id)
  let brief: Brief | null = null
  if (opts.brief !== undefined) {
    brief = createBrief(dir, opts.brief, { ...(opts.briefId ? { id: opts.briefId } : {}), now })
  }
  const record: RunRecord = {
    runId: id,
    sessionId: opts.sessionId ?? null,
    briefId: brief !== null ? brief.id : (opts.briefId ?? null),
    policyId: opts.policyId ?? null,
    createdAt: now,
  }
  writeRecord(dir, 'run.json', record)
  if (record.sessionId !== null) indexSession(store, record.sessionId, id, now)
  return { id, dir, record, brief }
}

/**
 * Attach (or re-attach, idempotently) session/brief/policy correlation to an
 * existing run. Only defined fields overwrite; the session reverse index is
 * refreshed. Throws `unknown run: <id>` when the run dir has no run.json.
 */
export function attachSession(store: string, runId: string, link: RunCorrelation): RunRecord {
  if (link.sessionId !== undefined) checkSessionId(link.sessionId)
  const dir = runDir(store, runId)
  const raw = readRecord(dir, 'run.json')
  if (raw === null || typeof raw !== 'object') throw new Error(`unknown run: ${runId}`)
  const now = new Date().toISOString()
  const record = raw as Record<string, unknown>
  if (link.sessionId !== undefined) record['sessionId'] = link.sessionId
  if (link.briefId !== undefined) record['briefId'] = link.briefId
  if (link.policyId !== undefined) record['policyId'] = link.policyId
  writeRecord(dir, 'run.json', record)
  const sessionId = record['sessionId']
  if (typeof sessionId === 'string') indexSession(store, sessionId, runId, now)
  return normalizeRecord(record)
}

/** Read one run index record; null when absent/corrupt. Old records without
 * correlation keys normalize to explicit nulls. */
export function getRun(store: string, runId: string): RunRecord | null {
  const raw = readRecord(runDir(store, runId), 'run.json')
  if (raw === null || typeof raw !== 'object') return null
  return normalizeRecord(raw as Record<string, unknown>)
}

function normalizeRecord(raw: Record<string, unknown>): RunRecord {
  const pick = (v: unknown): string | null => (typeof v === 'string' ? v : null)
  return {
    ...raw,
    runId: typeof raw['runId'] === 'string' ? (raw['runId'] as string) : '',
    sessionId: pick(raw['sessionId']),
    briefId: pick(raw['briefId']),
    policyId: pick(raw['policyId']),
  }
}

/** All run index records linked to a DSH conversation session; [] on miss. */
export function getBySession(store: string, sessionId: string): RunRecord[] {
  let runIds: unknown
  try {
    runIds = (
      JSON.parse(readFileSync(sessionIndexFile(store, sessionId), 'utf8')) as {
        runIds?: unknown
      }
    ).runIds
  } catch {
    return []
  }
  if (!Array.isArray(runIds)) return []
  const out: RunRecord[] = []
  for (const id of runIds) {
    if (typeof id !== 'string') continue
    const rec = getRun(store, id)
    if (rec !== null) out.push(rec)
  }
  return out
}
