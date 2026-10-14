// Versioned delivery-policy registry with promotion controls.
// Pure logic (no DSH imports; node:test-covered). The discovery lane may
// propose candidates; only this module blesses them, and only with eval
// evidence that shows no regression vs the current blessed baseline.

import { createHash } from 'node:crypto'

export type PolicyStatus = 'candidate' | 'blessed' | 'retired'

export interface PolicyComposition {
  /** DSH profile the policy runs under (e.g. 'headless', 'web'). */
  profile: string
  /** Overlay patch paths, relative to the policy directory. */
  patches: string[]
  /** Tool names the policy may invoke. */
  tools: string[]
}

export interface PromotionEvidence {
  /** Eval artifact reference (path or content hash). */
  evalRef: string
  /** Held-out score of the candidate (0..1). */
  heldOutScore: number
  /** Baseline policy id compared against. */
  baselineId: string
  /** Held-out score of that baseline (0..1). */
  baselineScore: number
  /** Human or harness approver identity. */
  approver: string
  /** Release note. */
  note: string
}

export interface PromotionEvent {
  at: string
  from: PolicyStatus
  to: PolicyStatus
  evidence?: PromotionEvidence
  reason?: string
}

export interface PolicyRecord {
  id: string
  version: number
  status: PolicyStatus
  composition: PolicyComposition
  params: Record<string, unknown>
  /** sha256 over canonical (id, version, composition, params). */
  hash: string
  createdAt: string
  history: PromotionEvent[]
}

/** Candidate patch paths must stay inside the experiments area. */
const CANDIDATE_PATCH_ROOT = 'policy/candidates/'
const FORBIDDEN_PATCH_FRAGMENTS = ['..', 'profiles/', 'cordis.dev.yml', '/etc/', '~']

function canonicalContent(
  id: string,
  version: number,
  composition: PolicyComposition,
  params: Record<string, unknown>,
): string {
  return JSON.stringify({ id, version, composition, params })
}

export function hashContent(
  id: string,
  version: number,
  composition: PolicyComposition,
  params: Record<string, unknown>,
): string {
  return createHash('sha256').update(canonicalContent(id, version, composition, params)).digest('hex')
}

export function verifyRecord(record: PolicyRecord): boolean {
  return (
    record.hash ===
    hashContent(record.id, record.version, record.composition, record.params)
  )
}

function checkCandidateIsolation(composition: PolicyComposition): string | null {
  for (const p of composition.patches) {
    if (!p.startsWith(CANDIDATE_PATCH_ROOT)) {
      return `candidate patch must live under ${CANDIDATE_PATCH_ROOT}, got ${JSON.stringify(p)}`
    }
    for (const frag of FORBIDDEN_PATCH_FRAGMENTS) {
      if (p.includes(frag)) return `candidate patch contains forbidden fragment ${JSON.stringify(frag)}`
    }
  }
  return null
}

export function createCandidate(
  id: string,
  composition: PolicyComposition,
  params: Record<string, unknown> = {},
): PolicyRecord {
  if (!id || !/^[a-z0-9][a-z0-9-]*$/.test(id)) throw new Error(`bad policy id: ${JSON.stringify(id)}`)
  const isolated = checkCandidateIsolation(composition)
  if (isolated) throw new Error(`candidate rejected: ${isolated}`)
  if (composition.tools.length === 0) throw new Error('candidate must allow at least one tool')
  return {
    id,
    version: 1,
    status: 'candidate',
    composition,
    params,
    hash: hashContent(id, 1, composition, params),
    createdAt: new Date().toISOString(),
    history: [{ at: new Date().toISOString(), from: 'candidate', to: 'candidate', reason: 'created' }],
  }
}

/** Bless a candidate. Returns the new blessed record (same id, version+0, status blessed). */
export function promote(record: PolicyRecord, evidence: PromotionEvidence): PolicyRecord {
  if (!verifyRecord(record)) throw new Error(`policy ${record.id} v${record.version}: hash mismatch (tampered?)`)
  if (record.status !== 'candidate') {
    throw new Error(`only candidates promote; ${record.id} is ${record.status}`)
  }
  if (!evidence.evalRef) throw new Error('promotion needs an eval artifact reference')
  if (!evidence.approver) throw new Error('promotion needs an approver')
  if (
    !(evidence.heldOutScore >= 0 && evidence.heldOutScore <= 1) ||
    !(evidence.baselineScore >= 0 && evidence.baselineScore <= 1)
  ) {
    throw new Error('scores must be in [0,1]')
  }
  if (evidence.heldOutScore < evidence.baselineScore) {
    throw new Error(
      `no-regression violated: candidate ${evidence.heldOutScore} < baseline ${evidence.baselineId} ${evidence.baselineScore}`,
    )
  }
  const at = new Date().toISOString()
  return {
    ...record,
    status: 'blessed',
    history: [...record.history, { at, from: 'candidate', to: 'blessed', evidence }],
  }
}

export function retire(record: PolicyRecord, reason: string): PolicyRecord {
  if (!verifyRecord(record)) throw new Error(`policy ${record.id} v${record.version}: hash mismatch (tampered?)`)
  if (!reason) throw new Error('retirement needs a reason')
  const at = new Date().toISOString()
  return { ...record, status: 'retired', history: [...record.history, { at, from: record.status, to: 'retired', reason }] }
}

/** New version of a blessed policy returns to candidate for re-qualification. */
export function revise(
  record: PolicyRecord,
  composition: PolicyComposition,
  params: Record<string, unknown> = {},
): PolicyRecord {
  if (!verifyRecord(record)) throw new Error(`policy ${record.id} v${record.version}: hash mismatch (tampered?)`)
  const isolated = checkCandidateIsolation(composition)
  if (isolated) throw new Error(`revision rejected: ${isolated}`)
  const version = record.version + 1
  const at = new Date().toISOString()
  return {
    id: record.id,
    version,
    status: 'candidate',
    composition,
    params,
    hash: hashContent(record.id, version, composition, params),
    createdAt: record.createdAt,
    history: [...record.history, { at, from: record.status, to: 'candidate', reason: `revised to v${version}` }],
  }
}
