// STC1 recovery state machine tests (no DSH imports; node:test-covered).
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  createRunDir,
  newRunId,
  readRecord,
  runDir,
  writeRecord,
} from '../src/stc-runstore.ts'
import {
  findRunByJob,
  markInterrupted,
  readEffects,
  readRecovery,
  recordContinuation,
  recordEffect,
  recover,
  redirectRun,
  resolveRunState,
} from '../src/stc-recovery.ts'

const ARGV = ['python3', '-m', 'stc', 'run', '--target', 'specs/sample_spec.md']

function seedRun(store: string, overrides: Record<string, unknown> = {}): string {
  const runId = newRunId()
  const dir = createRunDir(store, runId)
  writeRecord(dir, 'run.json', {
    runId,
    argv: ARGV,
    cwd: '/tmp/stc-root',
    spec: 'specs/sample_spec.md',
    mode: 'dry-run',
    startedAt: '2026-10-03T00:00:00.000Z',
    jobId: 'stc-run-1',
    pid: 4242,
    ...overrides,
  })
  return runId
}

function freshStore(): string {
  return mkdtempSync(join(tmpdir(), 'stc-recovery-'))
}

describe('markInterrupted', () => {
  it('records an explicit interrupted state with checkpoint + identity snapshot', () => {
    const store = freshStore()
    const runId = seedRun(store)
    const rec = markInterrupted(store, runId, { checkpoint: 'ckpt-1', reason: 'operator pause' })
    assert.equal(rec.state, 'interrupted')
    assert.equal(rec.checkpoint, 'ckpt-1')
    assert.equal(rec.reason, 'operator pause')
    assert.deepEqual(rec.snapshot.argv, ARGV)
    assert.equal(rec.snapshot.spec, 'specs/sample_spec.md')
    assert.equal(rec.snapshot.mode, 'dry-run')
    assert.deepEqual(readRecovery(runDir(store, runId)), rec)
  })

  it('requires a declared checkpoint', () => {
    const store = freshStore()
    const runId = seedRun(store)
    assert.throws(() => markInterrupted(store, runId, { checkpoint: '  ' }), /declared checkpoint/)
  })

  it('rejects unknown runs', () => {
    assert.throws(() => markInterrupted(freshStore(), 'nope', { checkpoint: 'c' }), /unknown run/)
  })

  it('is idempotent while interrupted (first checkpoint wins)', () => {
    const store = freshStore()
    const runId = seedRun(store)
    const first = markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    const second = markInterrupted(store, runId, { checkpoint: 'ckpt-2' })
    assert.equal(second.checkpoint, 'ckpt-1')
    assert.equal(second.interruptedAt, first.interruptedAt)
  })

  it('refuses completed/failed runs (terminal proof stands)', () => {
    const store = freshStore()
    const done = seedRun(store)
    writeRecord(runDir(store, done), 'exit.json', { status: 'completed', detail: 'exit code: 0' })
    assert.throws(() => markInterrupted(store, done, { checkpoint: 'c' }), /already terminal \(completed\)/)
    const failed = seedRun(store)
    writeRecord(runDir(store, failed), 'exit.json', { status: 'failed', detail: 'boom' })
    assert.throws(() => markInterrupted(store, failed, { checkpoint: 'c' }), /already terminal \(failed\)/)
  })

  it('refuses cancelled runs (killed without a recovery record stays killed)', () => {
    const store = freshStore()
    const runId = seedRun(store)
    writeRecord(runDir(store, runId), 'exit.json', { status: 'killed', detail: 'signal: SIGTERM' })
    assert.throws(() => markInterrupted(store, runId, { checkpoint: 'c' }), /already cancelled/)
  })

  it('refuses runs after redirect (redirect wins)', () => {
    const store = freshStore()
    const runId = seedRun(store)
    redirectRun(store, runId, { briefRef: 'brief-v2' })
    assert.throws(() => markInterrupted(store, runId, { checkpoint: 'c' }), /redirected/)
  })
})

describe('recover', () => {
  it('interrupt -> recover with completed side effects resumes without duplication', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    recordEffect(store, runId, { id: 'fx-1', kind: 'dossier-write', status: 'completed', proof: 'dossier/STATUS=COMPLETE' })
    recordEffect(store, runId, { id: 'fx-2', kind: 'spend-log', status: 'completed', proof: 'spend.jsonl has 3 lines' })
    const out = recover(store, runId, { probe: () => 'gone' })
    assert.equal(out.decision, 'resumed')
    if (out.decision !== 'resumed') throw new Error('unreachable')
    assert.deepEqual(out.resumePlan.argv, ARGV)
    assert.equal(out.resumePlan.spec, 'specs/sample_spec.md')
    assert.equal(out.resumePlan.mode, 'dry-run')
    assert.equal(out.resumePlan.resumedFrom, runId)
    assert.deepEqual(out.resumePlan.skip, ['fx-1', 'fx-2'])
    const rec = readRecovery(runDir(store, runId))
    assert.equal(rec?.recovery?.decision, 'resumed')
    assert.deepEqual(rec?.recovery?.skipped, ['fx-1', 'fx-2'])
  })

  it('uncertain side effect -> needs-decision, no silent retry', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    recordEffect(store, runId, { id: 'fx-1', kind: 'dossier-write', status: 'uncertain' })
    const out = recover(store, runId, { probe: () => 'gone' })
    assert.equal(out.decision, 'needs-decision')
    if (out.decision !== 'needs-decision') throw new Error('unreachable')
    assert.ok(out.blockers.some((b) => b.includes('fx-1')))
    assert.ok(out.evidence.some((e) => e.includes('ckpt-1')))
    const rec = readRecovery(runDir(store, runId))
    assert.equal(rec?.state, 'interrupted')
    assert.equal(rec?.recovery?.continuedBy, undefined)
  })

  it('pending side effect -> needs-decision', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    recordEffect(store, runId, { id: 'fx-1', kind: 'dossier-write', status: 'completed', proof: 'ok' })
    recordEffect(store, runId, { id: 'fx-2', kind: 'merge', status: 'pending' })
    const out = recover(store, runId, { probe: () => 'gone' })
    assert.equal(out.decision, 'needs-decision')
    if (out.decision !== 'needs-decision') throw new Error('unreachable')
    assert.ok(out.blockers.some((b) => b.includes('fx-2')))
  })

  it('completed-without-proof never verifies (proof is required)', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    assert.throws(
      () => recordEffect(store, runId, { id: 'fx-1', kind: 'k', status: 'completed' }),
      /needs proof/,
    )
  })

  it('missing effects ledger -> needs-decision', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    const out = recover(store, runId, { probe: () => 'gone' })
    assert.equal(out.decision, 'needs-decision')
    if (out.decision !== 'needs-decision') throw new Error('unreachable')
    assert.ok(out.blockers.some((b) => b.includes('no side-effect completion evidence')))
  })

  it('identity drift -> needs-decision (candidate/evaluator changed)', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    recordEffect(store, runId, { id: 'fx-1', kind: 'k', status: 'completed', proof: 'p' })
    const dir = runDir(store, runId)
    const run = readRecord(dir, 'run.json') as Record<string, unknown>
    writeRecord(dir, 'run.json', { ...run, argv: [...ARGV, '--different-flag'] })
    const out = recover(store, runId, { probe: () => 'gone' })
    assert.equal(out.decision, 'needs-decision')
    if (out.decision !== 'needs-decision') throw new Error('unreachable')
    assert.ok(out.blockers.some((b) => b.includes('identity changed')))
  })

  it('never-interrupted run -> needs-decision (interrupt first)', () => {
    const store = freshStore()
    const runId = seedRun(store)
    const out = recover(store, runId, { probe: () => 'gone' })
    assert.equal(out.decision, 'needs-decision')
    if (out.decision !== 'needs-decision') throw new Error('unreachable')
    assert.ok(out.blockers.some((b) => b.includes('never interrupted')))
  })

  it('live job -> reattached, no relaunch', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    const out = recover(store, runId, { probe: () => 'live' })
    assert.equal(out.decision, 'reattached')
    const rec = readRecovery(runDir(store, runId))
    assert.equal(rec?.recovery?.decision, 'reattached')
    assert.equal(rec?.recovery?.continuedBy, undefined)
  })

  it('completed / cancelled runs -> already-terminal (launch nothing)', () => {
    const store = freshStore()
    const done = seedRun(store)
    writeRecord(runDir(store, done), 'exit.json', { status: 'completed', detail: 'exit code: 0' })
    const a = recover(store, done, { probe: () => 'gone' })
    assert.equal(a.decision, 'already-terminal')
    const cancelled = seedRun(store)
    writeRecord(runDir(store, cancelled), 'exit.json', { status: 'killed', detail: 'signal: SIGTERM' })
    const b = recover(store, cancelled, { probe: () => 'gone' })
    assert.equal(b.decision, 'already-terminal')
    if (b.decision !== 'already-terminal') throw new Error('unreachable')
    assert.equal(b.terminal, 'killed')
  })

  it('recordContinuation links the launched continuation', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    recordEffect(store, runId, { id: 'fx-1', kind: 'k', status: 'completed', proof: 'p' })
    const out = recover(store, runId, { probe: () => 'gone' })
    assert.equal(out.decision, 'resumed')
    const rec = recordContinuation(store, runId, 'next-run')
    assert.equal(rec.recovery?.continuedBy, 'next-run')
    assert.throws(() => recordContinuation(store, seedRun(store), 'x'), /no approved resume/)
  })
})

describe('redirectRun', () => {
  it('records invalidation of pending work', () => {
    const store = freshStore()
    const runId = seedRun(store)
    recordEffect(store, runId, { id: 'fx-done', kind: 'k', status: 'completed', proof: 'p' })
    recordEffect(store, runId, { id: 'fx-open', kind: 'k', status: 'pending' })
    recordEffect(store, runId, { id: 'fx-maybe', kind: 'k', status: 'uncertain' })
    const rec = redirectRun(store, runId, { briefRef: 'brief-v2', reason: 'scope changed' })
    assert.equal(rec.state, 'redirected')
    assert.equal(rec.redirect?.briefRef, 'brief-v2')
    assert.deepEqual(rec.redirect?.invalidated, ['fx-open', 'fx-maybe'])
  })

  it('recover after redirect is refused (no resume, no retry)', () => {
    const store = freshStore()
    const runId = seedRun(store)
    redirectRun(store, runId, { briefRef: 'brief-v2' })
    const out = recover(store, runId, { probe: () => 'gone' })
    assert.equal(out.decision, 'refused-redirected')
    if (out.decision !== 'refused-redirected') throw new Error('unreachable')
    assert.equal(out.briefRef, 'brief-v2')
  })

  it('requires a brief ref and refuses terminal runs', () => {
    const store = freshStore()
    const runId = seedRun(store)
    assert.throws(() => redirectRun(store, runId, { briefRef: ' ' }), /brief_ref/)
    writeRecord(runDir(store, runId), 'exit.json', { status: 'completed', detail: 'ok' })
    assert.throws(() => redirectRun(store, runId, { briefRef: 'b' }), /already terminal/)
  })

  it('is idempotent while redirected', () => {
    const store = freshStore()
    const runId = seedRun(store)
    const first = redirectRun(store, runId, { briefRef: 'brief-v2' })
    const second = redirectRun(store, runId, { briefRef: 'brief-v3' })
    assert.equal(second.redirect?.briefRef, 'brief-v2')
    assert.deepEqual(second, first)
  })
})

describe('resolveRunState', () => {
  it('reports interrupted distinctly from killed/failed/completed', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-9', reason: 'r' })
    writeRecord(runDir(store, runId), 'exit.json', { status: 'killed', detail: 'signal: SIGTERM' })
    const v = resolveRunState(store, runId, '')
    assert.equal(v.state, 'interrupted')
    assert.ok(v.detail.includes('ckpt-9'))
  })

  it('cancelled runs (killed, no recovery record) resolve to killed', () => {
    const store = freshStore()
    const runId = seedRun(store)
    writeRecord(runDir(store, runId), 'exit.json', { status: 'killed', detail: 'signal: SIGTERM' })
    assert.equal(resolveRunState(store, runId, '').state, 'killed')
  })

  it('reports redirected, completed, failed, running, and unknown truthfully', () => {
    const store = freshStore()
    const red = seedRun(store)
    redirectRun(store, red, { briefRef: 'brief-v2' })
    assert.equal(resolveRunState(store, red, '').state, 'redirected')

    const done = seedRun(store)
    writeRecord(runDir(store, done), 'exit.json', { status: 'completed', detail: 'exit code: 0' })
    assert.equal(resolveRunState(store, done, '').state, 'completed')

    const bad = seedRun(store)
    writeRecord(runDir(store, bad), 'exit.json', { status: 'failed', detail: 'boom' })
    assert.equal(resolveRunState(store, bad, '').state, 'failed')

    const live = seedRun(store)
    assert.equal(resolveRunState(store, live, 'running').state, 'running')
    assert.equal(resolveRunState(store, live, 'stopping').state, 'running')

    const orphan = seedRun(store)
    const u = resolveRunState(store, orphan, '')
    assert.equal(u.state, 'unknown')
    assert.ok(u.detail.includes('restart'))
  })

  it('resumed runs name their continuation without resurrecting', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    recordEffect(store, runId, { id: 'fx-1', kind: 'k', status: 'completed', proof: 'p' })
    assert.equal(recover(store, runId, { probe: () => 'gone' }).decision, 'resumed')
    recordContinuation(store, runId, 'next-run')
    const v = resolveRunState(store, runId, '')
    assert.equal(v.state, 'interrupted')
    assert.ok(v.detail.includes('next-run'))
    assert.equal(v.continuedBy, 'next-run')
  })

  it('status never resurrects: pure read, byte-identical records', () => {
    const store = freshStore()
    const runId = seedRun(store)
    markInterrupted(store, runId, { checkpoint: 'ckpt-1' })
    const dir = runDir(store, runId)
    const before = readFileSync(join(dir, 'recovery.json'), 'utf8')
    for (const jobState of ['', 'running', 'stopping', 'killed', 'completed', 'failed']) {
      resolveRunState(store, runId, jobState)
    }
    const after = readFileSync(join(dir, 'recovery.json'), 'utf8')
    assert.equal(after, before)
  })
})

describe('effects ledger', () => {
  it('upserts by id and reads back', () => {
    const store = freshStore()
    const runId = seedRun(store)
    assert.equal(readEffects(runDir(store, runId)), null)
    recordEffect(store, runId, { id: 'fx-1', kind: 'k', status: 'pending' })
    recordEffect(store, runId, { id: 'fx-1', kind: 'k', status: 'completed', proof: 'done' })
    const ledger = readEffects(runDir(store, runId))
    assert.equal(ledger?.effects.length, 1)
    assert.equal(ledger?.effects[0]?.status, 'completed')
  })

  it('rejects unknown statuses and empty ids', () => {
    const store = freshStore()
    const runId = seedRun(store)
    assert.throws(
      () => recordEffect(store, runId, { id: 'x', kind: 'k', status: 'done' as never }),
      /unknown effect status/,
    )
    assert.throws(() => recordEffect(store, runId, { id: ' ', kind: 'k', status: 'pending' }), /needs an id/)
  })
})

describe('findRunByJob', () => {
  it('resolves the run for a job id', () => {
    const store = freshStore()
    const runId = seedRun(store, { jobId: 'stc-run-7' })
    assert.equal(findRunByJob(store, 'stc-run-7'), runId)
    assert.throws(() => findRunByJob(store, 'stc-run-zzz'), /unknown job/)
    assert.throws(() => findRunByJob(store, ' '), /non-empty/)
  })

  it('refuses ambiguity across restarts (caller must pass run_id)', () => {
    const store = freshStore()
    seedRun(store, { jobId: 'stc-run-1' })
    seedRun(store, { jobId: 'stc-run-1' })
    assert.throws(() => findRunByJob(store, 'stc-run-1'), /disambiguate/)
  })

  it('prefers the non-terminal run when exactly one is still open', () => {
    const store = freshStore()
    const old = seedRun(store, { jobId: 'stc-run-1' })
    writeRecord(runDir(store, old), 'exit.json', { status: 'killed', detail: 'gone' })
    const fresh = seedRun(store, { jobId: 'stc-run-1' })
    assert.equal(findRunByJob(store, 'stc-run-1'), fresh)
  })
})
