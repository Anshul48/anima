import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  DOSSIER_FILES,
  defaultStcRoot,
  resolveUnderRoot,
  summarizeDossier,
} from '../src/dossier-read.ts'

function makeDossier(status: string, outcome: string): string {
  const root = mkdtempSync(join(tmpdir(), 'stc-root-'))
  const dir = join(root, 'dossier-1')
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'STATUS'), status + '\n')
  writeFileSync(
    join(dir, 'branches.json'),
    JSON.stringify({ outcome, reason: outcome === 'champion' ? undefined : 'no-budget' }),
  )
  writeFileSync(join(dir, 'spend.json'), JSON.stringify({ totals: { usd: 1.5 }, rows: [] }))
  writeFileSync(join(dir, 'review.md'), '# review\nline\n')
  return dir
}

describe('dossier-read', () => {
  it('summarizes a complete dossier', () => {
    const dir = makeDossier('COMPLETE', 'champion')
    const s = summarizeDossier(dir, join(dir, '..'))
    assert.equal(s.status, 'COMPLETE')
    assert.equal(s.outcome, 'champion')
    assert.equal(s.reason, null)
    assert.deepEqual(s.spend_totals, { usd: 1.5 })
    assert.ok(s.review_head?.startsWith('# review'))
    assert.ok(s.files_present.includes('STATUS'))
  })

  it('reports unknown for missing pieces, never throws', () => {
    const root = mkdtempSync(join(tmpdir(), 'stc-root-'))
    const dir = join(root, 'empty')
    mkdirSync(dir)
    const s = summarizeDossier(dir, root)
    assert.equal(s.status, 'unknown')
    assert.equal(s.outcome, 'unknown')
    assert.deepEqual(s.files_present, [])
  })

  it('rejects traversal escapes', () => {
    const root = mkdtempSync(join(tmpdir(), 'stc-root-'))
    assert.throws(() => resolveUnderRoot(join(root, '..', 'etc'), root), /escapes|not found/)
  })

  it('rejects missing dossiers', () => {
    const root = mkdtempSync(join(tmpdir(), 'stc-root-'))
    assert.throws(() => summarizeDossier(join(root, 'nope'), root), /not found/)
  })

  it('covers the backend artifact names', () => {
    for (const f of [
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
    ]) {
      assert.ok((DOSSIER_FILES as readonly string[]).includes(f), f)
    }
  })

  it('default root resolves to the stc checkout', () => {
    assert.ok(defaultStcRoot().endsWith('stc'))
  })
})
