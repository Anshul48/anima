// Presenter unit tests (no DSH imports).
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import {
  cancelCall,
  cancelMeta,
  cancelResult,
  dossierCall,
  dossierMeta,
  dossierResult,
  logCall,
  logMeta,
  logResult,
  pingCall,
  pingMeta,
  pingResult,
  previewCall,
  previewMeta,
  previewResult,
  runCall,
  runMeta,
  runResult,
  statusCall,
  statusMeta,
  statusResult,
} from '../src/stc-present.ts'

describe('stc presenters', () => {
  it('ping card', () => {
    assert.equal(pingCall().title, 'Ping STC bundle')
    assert.equal(pingCall().card, 'generic')
    assert.ok(pingResult({ stc_root: '/r' }).title?.includes('/r'))
    assert.deepEqual(pingMeta({ stc_root: '/r' }), { stc_root: '/r' })
  })

  it('dossier evidence card', () => {
    const call = dossierCall({ dossier_path: '/r/d' })
    assert.equal(call.kind, 'read')
    assert.deepEqual(call.locations, [{ path: '/r/d' }])
    const v = {
      path: '/r/d',
      status: 'NEEDS_REPAIR',
      outcome: 'no-champion',
      reason: 'no-verified-candidate',
      files_present: ['STATUS', 'branches.json'],
    }
    const res = dossierResult(v)
    assert.ok(res.title?.includes('NEEDS_REPAIR'))
    assert.ok(res.title?.includes('no-champion'))
    assert.ok(res.content?.[0]?.text.includes('no-verified-candidate'))
    assert.ok(res.content?.[0]?.text.includes('STATUS, branches.json'))
    assert.deepEqual(dossierMeta(v), v)
  })

  it('dossier card tolerates missing fields', () => {
    const res = dossierResult({})
    assert.equal(res.title, 'Dossier: ? / ?')
    assert.deepEqual(dossierMeta({}), {
      path: '',
      status: '',
      outcome: '',
      reason: '',
      files_present: [],
    })
  })

  it('preview cards (ok + failed)', () => {
    assert.ok(previewCall({ spec: 's.md', mode: 'dry-run' }).title.includes('s.md'))
    const ok = previewResult({ ok: true, argv: ['stc', 'run'], cwd: '/r', error: '' })
    assert.equal(ok.title, 'Preview ready')
    assert.ok(ok.content?.[0]?.text.includes('stc run'))
    const bad = previewResult({ ok: false, argv: [], cwd: '', error: 'boom' })
    assert.equal(bad.title, 'Preview failed')
    assert.ok(bad.content?.[0]?.text.includes('boom'))
    assert.deepEqual(previewMeta({ ok: true, argv: ['a'], cwd: 'c', error: '' }), {
      ok: true,
      argv: ['a'],
      cwd: 'c',
      error: '',
    })
  })

  it('run launch card', () => {
    const call = runCall({ spec: 's.md', mode: 'manual' })
    assert.equal(call.kind, 'execute')
    assert.ok(call.title.includes('manual'))
    assert.deepEqual(call.rawInput, { spec: 's.md', mode: 'manual' })
    const res = runResult({ kind: 'background', jobId: 'stc-run-1', runId: 'abc' })
    assert.ok(res.title?.includes('abc'))
    assert.ok(res.title?.includes('stc-run-1'))
    assert.deepEqual(runMeta({ kind: 'background', jobId: 'j', runId: 'r' }), {
      kind: 'background',
      jobId: 'j',
      runId: 'r',
    })
  })

  it('status card', () => {
    assert.ok(statusCall({ job_id: 'j' }).title.includes('j'))
    const res = statusResult({ jobId: 'j', state: 'done', progress: 'p', detail: 'd' })
    assert.ok(res.title?.includes('done'))
    assert.ok(res.content?.[0]?.text.includes('p'))
    assert.ok(res.content?.[0]?.text.includes('d'))
    assert.deepEqual(statusMeta({ jobId: 'j', state: 's', progress: '', detail: '' }), {
      jobId: 'j',
      state: 's',
      progress: '',
      detail: '',
    })
  })

  it('log card', () => {
    assert.ok(logCall({ run_id: 'r' }).title.includes('r'))
    const res = logResult({ runId: 'r', tail: 'hello' })
    assert.ok(res.title?.includes('r'))
    assert.equal(res.content?.[0]?.text, 'hello')
    assert.equal(logResult({ runId: 'r', tail: '' }).content?.[0]?.text, '(empty log)')
    assert.deepEqual(logMeta({ runId: 'r', tail: 'hey' }), { runId: 'r', bytes: 3 })
  })

  it('cancel card', () => {
    assert.ok(cancelCall({ job_id: 'j' }).title.includes('j'))
    const res = cancelResult({ jobId: 'j', result: 'killed' })
    assert.ok(res.title?.includes('killed'))
    assert.deepEqual(cancelMeta({ jobId: 'j', result: 'killed' }), { jobId: 'j', result: 'killed' })
  })
})
