import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  briefDir,
  briefExists,
  createBrief,
  listBriefVersions,
  newBriefId,
  readBrief,
  reviseBrief,
} from '../src/stc-brief.ts'
import {
  attachSession,
  createRun,
  createRunDir,
  getBySession,
  getRun,
  runExists,
  writeRecord,
} from '../src/stc-runstore.ts'

const scratch = () => mkdtempSync(join(tmpdir(), 'stc-brief-'))

describe('stc-brief create/read', () => {
  it('creates a v1 brief with stamped fields', () => {
    const dir = join(scratch(), 'run-1')
    const b = createBrief(
      dir,
      {
        task: 'add retry to the executor',
        constraints: ['quota-free'],
        acceptance: ['tests green'],
        refs: ['src/stc-exec.ts'],
        decisions: [{ text: 'use backoff', by: 'builder-c' }],
      },
      { id: 'brief1', now: '2026-10-03T00:00:00.000Z' },
    )
    assert.equal(b.id, 'brief1')
    assert.equal(b.version, 1)
    assert.equal(b.supersedes, null)
    assert.equal(b.createdAt, '2026-10-03T00:00:00.000Z')
    assert.equal(b.updatedAt, '2026-10-03T00:00:00.000Z')
    assert.deepEqual(b.decisions, [
      { at: '2026-10-03T00:00:00.000Z', text: 'use backoff', by: 'builder-c' },
    ])
    assert.ok(briefExists(dir))
    assert.deepEqual(readBrief(dir), b)
    assert.deepEqual(readBrief(dir, 1), b)
    assert.deepEqual(listBriefVersions(dir), [1])
  })

  it('mints hex12 ids by default', () => {
    assert.match(newBriefId(), /^[0-9a-f]{12}$/)
    const b = createBrief(scratch(), { task: 't' })
    assert.match(b.id, /^[0-9a-f]{12}$/)
  })

  it('reads misses as null', () => {
    const dir = scratch()
    assert.equal(readBrief(dir), null)
    assert.equal(readBrief(dir, 3), null)
    assert.deepEqual(listBriefVersions(dir), [])
    const d2 = join(scratch(), 'b')
    createBrief(d2, { task: 't' })
    assert.equal(readBrief(d2, 2), null)
  })

  it('refuses a second create and an empty task', () => {
    const dir = scratch()
    createBrief(dir, { task: 't' })
    assert.throws(() => createBrief(dir, { task: 'other' }), /already exists/)
    assert.throws(() => createBrief(scratch(), { task: '  ' }), /non-empty/)
  })

  it('supports standalone briefs/<id>/ dirs', () => {
    const store = scratch()
    const dir = briefDir(store, 'standalone-1')
    assert.equal(dir, join(store, 'briefs', 'standalone-1'))
    const b = createBrief(dir, { task: 'standalone intent' })
    assert.equal(readBrief(dir)?.task, 'standalone intent')
    assert.equal(b.version, 1)
  })
})

describe('stc-brief revise', () => {
  it('appends immutable revisions with history', () => {
    const dir = scratch()
    createBrief(dir, { task: 'v1 task', constraints: ['c1'] }, { now: '2026-10-03T00:00:00.000Z' })
    const v1bytes = readFileSync(join(dir, 'brief-v1.json'), 'utf8')
    const v2 = reviseBrief(
      dir,
      { task: 'v2 task', decisions: [{ text: 'pivot' }] },
      { now: '2026-10-03T01:00:00.000Z' },
    )
    assert.equal(v2.version, 2)
    assert.equal(v2.supersedes, 1)
    assert.equal(v2.task, 'v2 task')
    assert.deepEqual(v2.constraints, ['c1'])
    assert.equal(v2.decisions.length, 1)
    assert.equal(v2.createdAt, '2026-10-03T00:00:00.000Z')
    assert.equal(v2.updatedAt, '2026-10-03T01:00:00.000Z')
    // v1 file untouched: immutability.
    assert.equal(readFileSync(join(dir, 'brief-v1.json'), 'utf8'), v1bytes)
    assert.deepEqual(readBrief(dir, 1)?.task, 'v1 task')
    assert.deepEqual(readBrief(dir)?.version, 2)
    assert.deepEqual(listBriefVersions(dir), [1, 2])
    const v3 = reviseBrief(dir, { acceptance: ['a1'] })
    assert.equal(v3.version, 3)
    assert.equal(v3.supersedes, 2)
    assert.deepEqual(v3.acceptance, ['a1'])
    assert.deepEqual(listBriefVersions(dir), [1, 2, 3])
  })

  it('throws when there is nothing to revise', () => {
    assert.throws(() => reviseBrief(scratch(), { task: 'x' }), /no brief/)
  })

  it('round-trips through fresh reads (persistence)', () => {
    const dir = scratch()
    createBrief(dir, { task: 'persist me', refs: ['r1'] })
    reviseBrief(dir, { constraints: ['c9'] })
    const latest = JSON.parse(readFileSync(join(dir, 'brief.json'), 'utf8'))
    assert.equal(latest.version, 2)
    assert.deepEqual(readBrief(dir), latest)
    assert.deepEqual(listBriefVersions(dir), [1, 2])
  })
})

describe('runstore correlation', () => {
  it('createRun persists session/brief/policy correlation', () => {
    const store = scratch()
    const { id, dir, record, brief } = createRun(store, {
      sessionId: 'session-7',
      policyId: 'b2-gated',
      brief: { task: 'run task', acceptance: ['done'] },
    })
    assert.match(id, /^[0-9a-f]{12}$/)
    assert.ok(runExists(store, id))
    assert.equal(record.sessionId, 'session-7')
    assert.equal(record.policyId, 'b2-gated')
    assert.ok(brief !== null)
    assert.equal(record.briefId, brief!.id)
    assert.deepEqual(readBrief(dir)?.task, 'run task')
    const bySession = getBySession(store, 'session-7')
    assert.equal(bySession.length, 1)
    assert.equal(bySession[0]!.runId, id)
    assert.equal(bySession[0]!.briefId, brief!.id)
  })

  it('createRun honours explicit ids and links without a brief body', () => {
    const store = scratch()
    const r = createRun(store, { id: 'runabc', sessionId: 's-1', briefId: 'external-brief' })
    assert.equal(r.id, 'runabc')
    assert.equal(r.brief, null)
    assert.equal(r.record.briefId, 'external-brief')
    assert.equal(getRun(store, 'runabc')?.sessionId, 's-1')
  })

  it('createRun works with no correlation at all', () => {
    const store = scratch()
    const r = createRun(store)
    assert.equal(r.record.sessionId, null)
    assert.equal(r.record.briefId, null)
    assert.equal(r.record.policyId, null)
    assert.deepEqual(getBySession(store, 'nobody'), [])
  })

  it('attachSession merges links into existing runs', () => {
    const store = scratch()
    const dir = createRunDir(store, 'legacy1')
    writeRecord(dir, 'run.json', { runId: 'legacy1', spec: 's', mode: 'dry-run' })
    const rec = attachSession(store, 'legacy1', { sessionId: 'sess-A', briefId: 'b-A' })
    assert.equal(rec.sessionId, 'sess-A')
    assert.equal(rec.briefId, 'b-A')
    assert.equal(rec.policyId, null)
    // Pre-existing fields preserved.
    assert.equal(rec['spec'], 's')
    assert.equal(getBySession(store, 'sess-A').length, 1)
    // Partial re-attach only touches defined fields; index stays single-entry.
    const rec2 = attachSession(store, 'legacy1', { policyId: 'p1' })
    assert.equal(rec2.sessionId, 'sess-A')
    assert.equal(rec2.policyId, 'p1')
    assert.equal(getBySession(store, 'sess-A').length, 1)
  })

  it('one session fans out to many runs', () => {
    const store = scratch()
    const a = createRun(store, { sessionId: 'multi' })
    const b = createRun(store, { sessionId: 'multi' })
    const found = getBySession(store, 'multi').map((r) => r.runId).sort()
    assert.deepEqual(found, [a.id, b.id].sort())
  })

  it('unknown session/run/policy misses behave', () => {
    const store = scratch()
    assert.deepEqual(getBySession(store, 'nope'), [])
    assert.equal(getRun(store, 'nope'), null)
    assert.throws(() => attachSession(store, 'nope', { sessionId: 's' }), /unknown run: nope/)
  })

  it('rejects path-unsafe session ids before writing', () => {
    const store = scratch()
    assert.throws(() => createRun(store, { sessionId: '../evil' }), /invalid session id/)
    assert.throws(() => attachSession(store, 'x', { sessionId: 'a/b' }), /invalid session id/)
    assert.deepEqual(getBySession(store, '../evil'), [])
  })

  it('old run.json records normalize to explicit nulls', () => {
    const store = scratch()
    const dir = createRunDir(store, 'old1')
    writeRecord(dir, 'run.json', { runId: 'old1' })
    assert.deepEqual(getRun(store, 'old1'), { runId: 'old1', sessionId: null, briefId: null, policyId: null })
  })

  it('correlation survives a disk round-trip', () => {
    const store = scratch()
    const { id } = createRun(store, { sessionId: 'disk-sess', brief: { task: 't' } })
    const raw = JSON.parse(readFileSync(join(store, `run-${id}`, 'run.json'), 'utf8'))
    assert.equal(raw.sessionId, 'disk-sess')
    assert.ok(typeof raw.briefId === 'string')
    const idx = JSON.parse(readFileSync(join(store, 'sessions', 'disk-sess.json'), 'utf8'))
    assert.deepEqual(idx.runIds, [id])
    assert.equal(getBySession(store, 'disk-sess')[0]!.runId, id)
  })
})
