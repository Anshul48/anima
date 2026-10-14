import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  appendLog,
  createRunDir,
  newRunId,
  readLogTail,
  readRecord,
  runExists,
  writeRecord,
} from '../src/stc-runstore.ts'
import { CONFIRM_PHRASE, VALID_MODES, guardLaunch } from '../src/stc-guard.ts'

describe('stc-runstore', () => {
  it('creates run dirs with hex12 ids', () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-store-'))
    const id = newRunId()
    assert.match(id, /^[0-9a-f]{12}$/)
    const dir = createRunDir(store, id)
    assert.ok(!runExists(store, id))
    writeRecord(dir, 'run.json', { id })
    assert.ok(runExists(store, id))
    assert.deepEqual(readRecord(dir, 'run.json'), { id })
  })

  it('appends and tails logs with a cap', () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-store-'))
    const dir = createRunDir(store, 'abc')
    assert.equal(readLogTail(dir), '')
    appendLog(dir, 'hello\n')
    appendLog(dir, 'world\n')
    assert.equal(readLogTail(dir), 'hello\nworld\n')
    assert.equal(readLogTail(dir, 6), 'world\n')
  })

  it('reads absent records as null', () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-store-'))
    const dir = createRunDir(store, 'x')
    assert.equal(readRecord(dir, 'nope.json'), null)
  })
})

describe('stc-guard', () => {
  it('allows a well-formed exec launch', () => {
    assert.equal(
      guardLaunch({ mode: 'exec', confirm: CONFIRM_PHRASE, exec_harness: '/bin/true' }),
      null,
    )
  })

  it('denies without typed confirmation', () => {
    assert.match(
      guardLaunch({ mode: 'manual', confirm: 'yes' }) ?? '',
      /confirm must be exactly/,
    )
  })

  it('denies unknown modes', () => {
    assert.match(
      guardLaunch({ mode: 'turbo', confirm: CONFIRM_PHRASE }) ?? '',
      /unknown mode/,
    )
  })

  it('denies exec without an executable', () => {
    assert.match(
      guardLaunch({ mode: 'exec', confirm: CONFIRM_PHRASE }) ?? '',
      /needs an executable/,
    )
    assert.match(
      guardLaunch({ mode: 'exec', confirm: CONFIRM_PHRASE, exec_harness: 'rel/path' }) ?? '',
      /absolute/,
    )
  })

  it('denies exe outside exec mode', () => {
    assert.match(
      guardLaunch({ mode: 'manual', confirm: CONFIRM_PHRASE, exec_harness: '/bin/true' }) ?? '',
      /only valid in exec mode/,
    )
  })

  it('matches the backend mode contract (lab.VALID_MODES)', () => {
    assert.deepEqual([...VALID_MODES].sort(), ['dry-run', 'exec', 'live', 'manual'])
  })

  it('rejects windows-style spec paths', () => {
    assert.match(
      guardLaunch({ mode: 'manual', confirm: CONFIRM_PHRASE, spec: 'C:\\x\\y' }) ?? '',
      /POSIX/,
    )
  })
})
