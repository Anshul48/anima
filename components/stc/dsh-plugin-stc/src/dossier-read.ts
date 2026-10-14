// Pure dossier read-model helpers (no DSH imports; node:test-covered).
// Mirrors the backend dossier layout from src/stc/integration/dossier.py.

import { readFileSync, realpathSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

export const DOSSIER_FILES = [
  'STATUS',
  'qa_log.json',
  'veto_log.json',
  'spend.json',
  'branches.json',
  'run_ref.json',
  'review.md',
  'merged.diff',
  'execution_receipt.json',
  'judiciary_verdict.json',
] as const

export type DossierFile = (typeof DOSSIER_FILES)[number]

export const MAX_TEXT_BYTES = 65536
export const REVIEW_HEAD_BYTES = 2048

export interface DossierSummary {
  path: string
  status: string // STATUS file content, or 'unknown'
  outcome: string // branches.json outcome, or 'unknown'
  reason: string | null
  files_present: string[]
  spend_totals: unknown
  review_head: string | null
}

/** Resolve `p` under `root`, rejecting traversal escapes. Throws on violation. */
export function resolveUnderRoot(p: string, root: string): string {
  const realRoot = realpathSync(root)
  const abs = resolve(realRoot, p)
  let real: string
  try {
    real = realpathSync(abs)
  } catch {
    throw new Error(`dossier not found: ${p}`)
  }
  if (real !== realRoot && !real.startsWith(realRoot + '/')) {
    throw new Error(`path escapes STC root: ${p}`)
  }
  return real
}

function readCapped(path: string, cap: number): string | null {
  try {
    const st = statSync(path)
    if (!st.isFile() || st.size > MAX_TEXT_BYTES * 4) return null
    const text = readFileSync(path, 'utf8')
    return text.length > cap ? text.slice(0, cap) : text
  } catch {
    return null
  }
}

function readJson(path: string): unknown {
  const text = readCapped(path, MAX_TEXT_BYTES)
  if (text === null) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

/** Read-only summary of a backend dossier directory. Never writes. */
export function summarizeDossier(dossierDir: string, stcRoot: string): DossierSummary {
  const dir = resolveUnderRoot(dossierDir, stcRoot)
  const present: string[] = []
  for (const f of DOSSIER_FILES) {
    try {
      if (statSync(join(dir, f)).isFile()) present.push(f)
    } catch {
      /* absent */
    }
  }
  const statusRaw = readCapped(join(dir, 'STATUS'), 64)
  const branches = readJson(join(dir, 'branches.json')) as Record<string, unknown> | null
  const spend = readJson(join(dir, 'spend.json')) as Record<string, unknown> | null
  const review = readCapped(join(dir, 'review.md'), REVIEW_HEAD_BYTES)
  return {
    path: dir,
    status: statusRaw === null ? 'unknown' : statusRaw.trim() || 'unknown',
    outcome:
      branches !== null && typeof branches['outcome'] === 'string'
        ? (branches['outcome'] as string)
        : 'unknown',
    reason:
      branches !== null && typeof branches['reason'] === 'string'
        ? (branches['reason'] as string)
        : null,
    files_present: present,
    spend_totals: spend !== null ? (spend['totals'] ?? null) : null,
    review_head: review,
  }
}

/** Default STC root: the checkout containing this bundle (…/stc/dsh-plugin-stc/src → …/stc). */
export function defaultStcRoot(): string {
  return resolve(new URL('.', import.meta.url).pathname, '..', '..')
}
