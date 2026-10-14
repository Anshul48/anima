import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import { backendEnv, bundleRoot, previewArgs, runProbe, venvPython } from '../src/stc-exec.ts'

const STC_ROOT = resolve(bundleRoot(), '..')

describe('stc-exec', () => {
  it('builds probe argv in contract order', () => {
    const argv = previewArgs(
      { spec: 'specs/demo.md', mode: 'exec', exec_harness: '/bin/true' },
      STC_ROOT,
    )
    assert.deepEqual(argv.slice(0, 6), ['--op', 'outer', '--spec', 'specs/demo.md', '--mode', 'exec'])
    assert.ok(argv.includes('/bin/true'))
    assert.ok(argv.includes(STC_ROOT))
  })

  it('quotes outer argv via the backend probe', async () => {
    const res = await runProbe(
      STC_ROOT,
      previewArgs({ spec: 'specs/demo.md', mode: 'manual' }, STC_ROOT),
    )
    assert.equal(res.ok, true)
    const argv = res['argv'] as string[]
    assert.ok(argv.includes('run'))
    assert.ok(argv.includes('--target'))
    assert.ok(argv.includes('stc'))
  })

  it('returns probe misuse as data, not a throw', async () => {
    const res = await runProbe(
      STC_ROOT,
      previewArgs({ spec: 'x', mode: 'bogus-mode' }, STC_ROOT),
    )
    assert.equal(res.ok, false)
    assert.match(String(res.error), /unknown mode/)
  })

  it('venv python resolves under the stc root', () => {
    assert.equal(venvPython(STC_ROOT), resolve(STC_ROOT, '.venv', 'bin', 'python'))
  })

  it('passes env through when no pins are set', () => {
    const out = backendEnv({ PATH: '/bin', PYTHONPATH: '/keep' })
    assert.equal(out['PYTHONPATH'], '/keep')
    assert.equal(out['PYTHONUNBUFFERED'], '1')
  })

  it('prepends pin roots pin-first when both pins are set', () => {
    const out = backendEnv({
      STC_SST_ROOT: '/pins/sst',
      STC_PROMPT_KIT_ROOT: '/pins/pk',
      PYTHONPATH: '/keep',
    })
    assert.equal(out['PYTHONPATH'], '/pins/sst/src:/pins/pk:/keep')
  })

  it('rejects half-provisioned pins with an actionable error', () => {
    assert.throws(() => backendEnv({ STC_SST_ROOT: '/pins/sst' }), /both STC_SST_ROOT/)
  })

  it('rejects relative pin roots', () => {
    assert.throws(
      () =>
        backendEnv({ STC_SST_ROOT: 'rel/sst', STC_PROMPT_KIT_ROOT: '/pins/pk' }),
      /absolute paths/,
    )
  })
})
