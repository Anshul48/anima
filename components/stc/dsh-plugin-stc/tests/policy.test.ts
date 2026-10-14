import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  createCandidate,
  promote,
  retire,
  revise,
  verifyRecord,
} from '../policy/registry.ts'
import { scorePolicy, selectWinner } from '../policy/theoracle.ts'
import type { EpisodeResult } from '../policy/theoracle.ts'

const COMP = { profile: 'headless', patches: ['policy/candidates/v1.yml'], tools: ['stc_run'] }

describe('policy registry', () => {
  it('creates hash-locked candidates', () => {
    const r = createCandidate('b1-direct', COMP)
    assert.equal(r.status, 'candidate')
    assert.equal(r.version, 1)
    assert.ok(verifyRecord(r))
  })

  it('rejects bad ids and empty tools', () => {
    assert.throws(() => createCandidate('Bad Id', COMP), /bad policy id/)
    assert.throws(() => createCandidate('x', { ...COMP, tools: [] }), /at least one tool/)
  })

  it('isolates candidates from delivery paths', () => {
    assert.throws(
      () => createCandidate('evil', { ...COMP, patches: ['cordis.dev.yml'] }),
      /must live under/,
    )
    assert.throws(
      () => createCandidate('evil', { ...COMP, patches: ['policy/candidates/../x.yml'] }),
      /forbidden fragment/,
    )
  })

  it('detects tampering', () => {
    const r = createCandidate('b1-direct', COMP)
    const tampered = { ...r, params: { rigged: true } }
    assert.equal(verifyRecord(tampered), false)
    assert.throws(
      () => promote(tampered, {
        evalRef: 'e', heldOutScore: 1, baselineId: 'b', baselineScore: 0, approver: 'op', note: 'n',
      }),
      /hash mismatch/,
    )
  })

  it('promotes only with no-regression evidence + approver', () => {
    const r = createCandidate('b1-direct', COMP)
    const good = {
      evalRef: 'eval-1', heldOutScore: 0.8, baselineId: 'b0', baselineScore: 0.8,
      approver: 'operator', note: 'ties keep challenger out; this is the baseline seed',
    }
    const blessed = promote(r, good)
    assert.equal(blessed.status, 'blessed')
    assert.equal(blessed.history.at(-1)?.evidence?.approver, 'operator')
    const r2 = createCandidate('p1', COMP)
    assert.throws(
      () => promote(r2, { ...good, heldOutScore: 0.7 }),
      /no-regression violated/,
    )
    assert.throws(() => promote(r2, { ...good, approver: '' }), /approver/)
    assert.throws(() => promote(blessed, good), /only candidates promote/)
  })

  it('revisions return to candidate with a new hash', () => {
    const blessed = promote(createCandidate('b1-direct', COMP), {
      evalRef: 'e', heldOutScore: 1, baselineId: 'b', baselineScore: 0, approver: 'op', note: 'seed',
    })
    const v2 = revise(blessed, { ...COMP, tools: ['stc_run', 'stc_log'] })
    assert.equal(v2.version, 2)
    assert.equal(v2.status, 'candidate')
    assert.ok(verifyRecord(v2))
    assert.notEqual(v2.hash, blessed.hash)
  })

  it('retires with a reason', () => {
    const r = retire(createCandidate('old', COMP), 'superseded')
    assert.equal(r.status, 'retired')
    assert.throws(() => retire(createCandidate('x', COMP), ''), /reason/)
  })
})

function ep(partial: Partial<EpisodeResult> & { policy: string; task: string }): EpisodeResult {
  return {
    completed: true, evidenceComplete: true, regressions: 0,
    faultsInjected: 0, faultsRecovered: 0, toolCalls: 3, durationMs: 1000,
    timedOut: false, ...partial,
  }
}

describe('theoracle', () => {
  it('scores verified success with failures in the denominator', () => {
    const s = scorePolicy('b1', [
      ep({ policy: 'b1', task: 't1' }),
      ep({ policy: 'b1', task: 't2', completed: false }),
      ep({ policy: 'b1', task: 't3', timedOut: true }),
    ])
    assert.equal(s.episodes, 3)
    assert.equal(s.successRate, 1 / 3)
    assert.deepEqual(s.failures, ['t2', 't3'])
  })

  it('requires evidence and zero regressions', () => {
    const s = scorePolicy('b1', [
      ep({ policy: 'b1', task: 't1', evidenceComplete: false }),
      ep({ policy: 'b1', task: 't2', regressions: 1 }),
    ])
    assert.equal(s.successRate, 0)
    assert.equal(s.meanToolCallsOnSuccess, null)
  })

  it('measures fault recovery separately', () => {
    const s = scorePolicy('p1', [
      ep({ policy: 'p1', task: 't1', faultsInjected: 2, faultsRecovered: 1 }),
      ep({ policy: 'p1', task: 't2' }),
    ])
    assert.equal(s.successRate, 1)
    assert.equal(s.recoveryRate, 0.5)
  })

  it('throws on empty input (no vacuous wins)', () => {
    assert.throws(() => scorePolicy('nobody', [ep({ policy: 'b1', task: 't' })]), /no episodes/)
  })

  it('keeps the baseline on ties; challengers must strictly beat', () => {
    const base = scorePolicy('b0', [ep({ policy: 'b0', task: 't', toolCalls: 5 })])
    const tie = scorePolicy('p1', [ep({ policy: 'p1', task: 't', toolCalls: 5 })])
    const faster = scorePolicy('p2', [ep({ policy: 'p2', task: 't', toolCalls: 3 })])
    const worse = scorePolicy('p3', [ep({ policy: 'p3', task: 't', completed: false })])
    assert.equal(selectWinner(base, [tie, worse]), null)
    assert.equal(selectWinner(base, [tie, faster]), 'p2')
  })
})
