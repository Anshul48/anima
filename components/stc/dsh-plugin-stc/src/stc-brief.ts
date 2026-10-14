// Versioned durable brief records (no DSH imports; node:test-covered).
//
// A brief records task INTENT + decisions (task, constraints, acceptance,
// repo/material refs, decision log). It never records learned procedures —
// those belong to the STC3 experience lane, cited to episodes.
//
// Durability: each revision is immutable. revise() appends brief-v<N>.json
// and refreshes brief.json (latest-version pointer); prior version files are
// never rewritten. Briefs live either in a run dir (run-scoped) or in
// $STC_DSH_STORE/briefs/<id>/ (standalone); all functions take the dir.

import { randomBytes } from 'node:crypto'
import { mkdirSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { readRecord, writeRecord } from './stc-runstore.ts'

export interface BriefDecisionInput {
  text: string
  by?: string
  /** ISO timestamp; stamped with now when omitted. */
  at?: string
}

export interface BriefDecision {
  at: string
  text: string
  by?: string
}

export interface BriefInput {
  task: string
  constraints?: string[]
  acceptance?: string[]
  /** Repo/material refs (paths, URLs, dossier ids). */
  refs?: string[]
  decisions?: BriefDecisionInput[]
}

export interface Brief {
  id: string
  version: number
  createdAt: string
  updatedAt: string
  task: string
  constraints: string[]
  acceptance: string[]
  refs: string[]
  decisions: BriefDecision[]
  /** Previous version number, or null for v1. */
  supersedes: number | null
}

export interface BriefRevisePatch {
  task?: string
  constraints?: string[]
  acceptance?: string[]
  refs?: string[]
  /** Appended to the existing decision log (never replaces it). */
  decisions?: BriefDecisionInput[]
}

export function newBriefId(): string {
  return randomBytes(6).toString('hex')
}

/** Standalone brief dir: <store>/briefs/<briefId> (pure join, no mkdir). */
export function briefDir(store: string, briefId: string): string {
  return join(store, 'briefs', briefId)
}

export function briefExists(dir: string): boolean {
  return readRecord(dir, 'brief.json') !== null
}

function stampDecisions(
  decisions: BriefDecisionInput[] | undefined,
  now: string,
): BriefDecision[] {
  return (decisions ?? []).map((d) => ({
    at: d.at ?? now,
    text: d.text,
    ...(d.by !== undefined ? { by: d.by } : {}),
  }))
}

function checkTask(task: unknown): string {
  if (typeof task !== 'string' || task.trim() === '') {
    throw new Error('brief task must be a non-empty string')
  }
  return task
}

/**
 * Create a v1 brief in `dir` (mkdir -p). Throws when `dir` already holds a
 * brief — use revise() — or when the task is empty.
 */
export function createBrief(
  dir: string,
  input: BriefInput,
  opts: { id?: string; now?: string } = {},
): Brief {
  const task = checkTask(input.task)
  mkdirSync(dir, { recursive: true })
  if (briefExists(dir)) throw new Error(`brief already exists in ${dir}`)
  const now = opts.now ?? new Date().toISOString()
  const brief: Brief = {
    id: opts.id ?? newBriefId(),
    version: 1,
    createdAt: now,
    updatedAt: now,
    task,
    constraints: [...(input.constraints ?? [])],
    acceptance: [...(input.acceptance ?? [])],
    refs: [...(input.refs ?? [])],
    decisions: stampDecisions(input.decisions, now),
    supersedes: null,
  }
  writeRecord(dir, 'brief-v1.json', brief)
  writeRecord(dir, 'brief.json', brief)
  return brief
}

/** Latest brief (default) or one pinned version; null when absent/corrupt. */
export function readBrief(dir: string, version?: number): Brief | null {
  const name = version === undefined ? 'brief.json' : `brief-v${version}.json`
  const raw = readRecord(dir, name) as Record<string, unknown> | null
  if (raw === null || typeof raw !== 'object') return null
  if (typeof raw['id'] !== 'string' || typeof raw['version'] !== 'number') return null
  return raw as unknown as Brief
}

/** Sorted ascending version numbers present as brief-v<N>.json files. */
export function listBriefVersions(dir: string): number[] {
  let names: string[]
  try {
    names = readdirSync(dir)
  } catch {
    return []
  }
  return names
    .map((n) => /^brief-v(\d+)\.json$/.exec(n)?.[1])
    .filter((m): m is string => m !== undefined)
    .map(Number)
    .filter((v) => Number.isInteger(v) && v >= 1)
    .sort((a, b) => a - b)
}

/**
 * Append a new immutable revision. Array fields replace when provided and
 * carry over otherwise; decisions append; createdAt/id are preserved.
 * Throws when `dir` holds no brief yet.
 */
export function reviseBrief(
  dir: string,
  patch: BriefRevisePatch,
  opts: { now?: string } = {},
): Brief {
  const latest = readBrief(dir)
  if (latest === null) throw new Error(`no brief to revise in ${dir}`)
  if (patch.task !== undefined) checkTask(patch.task)
  const now = opts.now ?? new Date().toISOString()
  const next: Brief = {
    id: latest.id,
    version: latest.version + 1,
    createdAt: latest.createdAt,
    updatedAt: now,
    task: patch.task ?? latest.task,
    constraints: patch.constraints !== undefined ? [...patch.constraints] : latest.constraints,
    acceptance: patch.acceptance !== undefined ? [...patch.acceptance] : latest.acceptance,
    refs: patch.refs !== undefined ? [...patch.refs] : latest.refs,
    decisions: [...latest.decisions, ...stampDecisions(patch.decisions, now)],
    supersedes: latest.version,
  }
  writeRecord(dir, `brief-v${next.version}.json`, next)
  writeRecord(dir, 'brief.json', next)
  return next
}
