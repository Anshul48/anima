/**
 * STC bundle e2e suite: scripted mock model drives the REAL STC tools through
 * the REAL agent loop, jobs registry, and policy gate — quota-free. Uses the
 * real STC backend venv (dry-run + exec-cancel paths only; no model calls, no
 * spend). Runs inside a DSH checkout via scripts/run-e2e.sh (needs workspace
 * vitest + MockAdapter); STC_ROOT comes from the environment.
 */
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import type { Agent } from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import { mountAgentLoopTestDependencies } from '@deepseek-ai/dsh-agent-loop-testkit'
import LocalJobRegistry from '@deepseek-ai/dsh-jobs-local'
import * as ToolJobs from '@deepseek-ai/dsh-tool-jobs'
import { MockAdapter, textResponse, toolCallResponse } from '../../../core/agent-loop/tests/mock-adapter.ts'
import * as StcTools from '../../src/stc-tools.ts'
import * as StcRun from '../../src/stc-run.ts'
import * as StcPolicy from '../../src/stc-policy.ts'

const STC_ROOT = process.env['STC_ROOT'] ?? (() => { throw new Error('STC_ROOT env is required') })()
const SST_SRC = process.env['SST_SRC'] ?? '/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/sst/src'
const PROMPT_KIT = process.env['PROMPT_KIT'] ?? '/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/prompt-kit'

async function harness(adapter: MockAdapter) {
  const ctx = new Context()
  await mountAgentLoopTestDependencies(ctx)
  await ctx.plugin(AgentLoop, { agents: [] })
  await ctx.plugin(LocalJobRegistry)
  await ctx.plugin(ToolJobs)
  await ctx.plugin(StcTools)
  await ctx.plugin(StcRun)
  await ctx.plugin(StcPolicy)
  ctx.llm.registerAdapter(['mock'], adapter)
  return ctx
}

function waitForIdle(ctx: Context, agent: Agent): Promise<void> {
  return new Promise((resolve) => {
    const dispose = ctx.on('agent/status', ({ agent: subject, status }: any) => {
      if (subject === agent && status === 'idle') {
        dispose()
        resolve()
      }
    })
  })
}

function resultText(agent: Agent): string {
  const log = agent.session.snapshotEvents()
  const found = log.find((e) => e.type === 'tool/result')
  if (!found || found.type !== 'tool/result') throw new Error('no tool/result event')
  return found.data.message.content
    .filter((block) => block.type === 'text')
    .map((block) => (block as { text: string }).text)
    .join('')
}

function resultIsError(agent: Agent): boolean {
  const log = agent.session.snapshotEvents()
  const found = log.find((e) => e.type === 'tool/result')
  if (!found || found.type !== 'tool/result') throw new Error('no tool/result event')
  return found.data.message.isError === true
}

function resultMetas(agent: Agent): unknown[] {
  return agent.session
    .snapshotEvents()
    .filter((e) => e.type === 'tool/result')
    .map((e) => {
      if (e.type !== 'tool/result') throw new Error('unreachable')
      return (e.data as unknown as Record<string, unknown>)['meta']
    })
}

async function pollUntil(predicate: () => boolean, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (predicate()) return
    await new Promise((resolve) => setTimeout(resolve, 200))
  }
  throw new Error(`condition not met within ${timeoutMs}ms`)
}

describe('stc bundle through the agent loop', () => {
  it('stc_ping answers with the bundle root', async () => {
    process.env['STC_ROOT'] = STC_ROOT
    const adapter = new MockAdapter([
      toolCallResponse('call-1', 'stc_ping', {}),
      textResponse('pong seen.'),
    ])
    const ctx = await harness(adapter)
    const handle = await ctx.agents.create({ sessionId: SessionId('e2e-ping'), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'ping stc' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
    expect(resultIsError(agent)).toBe(false)
    expect(resultText(agent)).toContain(STC_ROOT)
    await handle.dispose()
  })

  it('stc_dossier reads a real dossier layout', async () => {
    const root = mkdtempSync(join(tmpdir(), 'stc-e2e-dos-'))
    process.env['STC_ROOT'] = root
    const dir = join(root, 'dossier-1')
    mkdirSync(dir)
    writeFileSync(join(dir, 'STATUS'), 'COMPLETE\n')
    writeFileSync(join(dir, 'branches.json'), JSON.stringify({ outcome: 'champion' }))
    const adapter = new MockAdapter([
      toolCallResponse('call-1', 'stc_dossier', { dossier_path: dir }),
      textResponse('dossier seen.'),
    ])
    const ctx = await harness(adapter)
    const handle = await ctx.agents.create({ sessionId: SessionId('e2e-dossier'), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'read dossier' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
    expect(resultIsError(agent)).toBe(false)
    expect(resultText(agent)).toContain('STATUS=COMPLETE')
    await handle.dispose()
    rmSync(root, { recursive: true, force: true })
  })

  it('stc_preview quotes backend argv', async () => {
    process.env['STC_ROOT'] = STC_ROOT
    const adapter = new MockAdapter([
      toolCallResponse('call-1', 'stc_preview', { spec: 'specs/sample_spec.md', mode: 'dry-run' }),
      textResponse('preview seen.'),
    ])
    const ctx = await harness(adapter)
    const handle = await ctx.agents.create({ sessionId: SessionId('e2e-preview'), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'preview dry run' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
    expect(resultIsError(agent)).toBe(false)
    const text = resultText(agent)
    expect(text).toContain('--target')
    expect(text).toContain('specs/sample_spec.md')
    await handle.dispose()
  })

  it('tool results carry presentation meta for cards', async () => {
    const root = mkdtempSync(join(STC_ROOT, 'e2e-meta-'))
    process.env['STC_ROOT'] = STC_ROOT
    const dir = join(root, 'dossier-1')
    mkdirSync(dir)
    writeFileSync(join(dir, 'STATUS'), 'COMPLETE\n')
    writeFileSync(join(dir, 'branches.json'), JSON.stringify({ outcome: 'champion' }))
    const adapter = new MockAdapter([
      toolCallResponse('call-1', 'stc_ping', {}),
      toolCallResponse('call-2', 'stc_dossier', { dossier_path: dir }),
      toolCallResponse('call-3', 'stc_preview', { spec: 'specs/sample_spec.md', mode: 'dry-run' }),
      textResponse('cards seen.'),
    ])
    const ctx = await harness(adapter)
    const handle = await ctx.agents.create({ sessionId: SessionId('e2e-meta'), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'show cards' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
    const metas = resultMetas(agent)
    expect(metas.length).toBe(3)
    expect(metas[0]).toEqual({ stc_root: STC_ROOT })
    const dos = metas[1] as Record<string, unknown>
    expect(dos['status']).toBe('COMPLETE')
    expect(dos['outcome']).toBe('champion')
    expect(dos['path']).toBe(dir)
    expect(dos['files_present']).toContain('STATUS')
    const prev = metas[2] as Record<string, unknown>
    expect(prev['ok']).toBe(true)
    expect(prev['error']).toBe('')
    expect(prev['argv']).toContain('--target')
    expect(typeof prev['cwd']).toBe('string')
    await handle.dispose()
    rmSync(root, { recursive: true, force: true })
  })

  it('policy denies stc_run without typed confirmation', async () => {
    process.env['STC_ROOT'] = STC_ROOT
    const adapter = new MockAdapter([
      toolCallResponse('call-1', 'stc_run', { spec: 'specs/sample_spec.md', mode: 'dry-run', confirm: 'yes' }),
      textResponse('denied as expected.'),
    ])
    const ctx = await harness(adapter)
    const handle = await ctx.agents.create({ sessionId: SessionId('e2e-deny'), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'run without confirm' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
    expect(resultIsError(agent)).toBe(true)
    expect(resultText(agent)).toContain('confirm')
    await handle.dispose()
  })

  it('stc_run dry-run completes with durable records', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-e2e-store-'))
    process.env['STC_ROOT'] = STC_ROOT
    process.env['STC_DSH_STORE'] = store
    process.env['PYTHONPATH'] = `${SST_SRC}:${PROMPT_KIT}`
    const adapter = new MockAdapter([
      toolCallResponse('call-1', 'stc_run', {
        spec: 'specs/sample_spec.md', mode: 'dry-run', confirm: 'RUN',
      }),
      textResponse('run launched.'),
    ])
    const ctx = await harness(adapter)
    const handle = await ctx.agents.create({ sessionId: SessionId('e2e-run'), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'dry run it' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
    console.log('RUN-RESULT-ERROR:', resultIsError(agent))
    console.log('RUN-RESULT-TEXT:', resultText(agent))
    expect(resultIsError(agent)).toBe(false)
    expect(resultText(agent)).toContain('stc-run-')
    await pollUntil(() => {
      const dirs = readdirSync(store).filter((d) => d.startsWith('run-'))
      if (dirs.length === 0) return false
      try {
        const exit = JSON.parse(readFileSync(join(store, dirs[0]!, 'exit.json'), 'utf8'))
        return exit.status === 'completed'
      } catch {
        return false
      }
    }, 120_000)
    const runDir = join(store, readdirSync(store).find((d) => d.startsWith('run-'))!)
    const log = readFileSync(join(runDir, 'console.log'), 'utf8')
    expect(log.length).toBeGreaterThan(100)
    await handle.dispose()
    rmSync(store, { recursive: true, force: true })
    rmSync(join(STC_ROOT, 'dossier'), { recursive: true, force: true })
  }, 180_000)

  it('stc_cancel kills a live exec run with proof', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-e2e-cancel-'))
    process.env['STC_ROOT'] = STC_ROOT
    process.env['STC_DSH_STORE'] = store
    process.env['PYTHONPATH'] = `${SST_SRC}:${PROMPT_KIT}`
    const adapter = new MockAdapter([
      toolCallResponse('call-1', 'stc_run', {
        spec: 'specs/sample_spec.md', mode: 'exec', confirm: 'RUN',
        exec_harness: STC_ROOT + '/operator-console/fixtures/EXEC-ECHO/sleep.sh',
      }),
      toolCallResponse('call-2', 'stc_cancel', { job_id: 'stc-run-1', reason: 'e2e cancel probe' }),
      textResponse('cancelled.'),
    ])
    const ctx = await harness(adapter)
    const handle = await ctx.agents.create({ sessionId: SessionId('e2e-cancel'), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'start exec run' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
    expect(resultIsError(agent)).toBe(false)
    await new Promise((resolve) => setTimeout(resolve, 8000))
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'cancel it' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
    const log = agent.session.snapshotEvents()
    const cancels = log.filter((e) => e.type === 'tool/result')
    const lastText = cancels.length > 0 ? resultText(agent) : ''
    expect(cancels.length).toBeGreaterThan(0)
    await pollUntil(() => {
      const dirs = readdirSync(store).filter((d) => d.startsWith('run-'))
      if (dirs.length === 0) return false
      try {
        const exit = JSON.parse(readFileSync(join(store, dirs[0]!, 'exit.json'), 'utf8'))
        return exit.status === 'killed'
      } catch {
        return false
      }
    }, 60_000)
    const runDir = join(store, readdirSync(store).find((d) => d.startsWith('run-'))!)
    const run = JSON.parse(readFileSync(join(runDir, 'run.json'), 'utf8'))
    let pidDead = false
    try {
      process.kill(run.pid, 0)
    } catch {
      pidDead = true
    }
    expect(pidDead).toBe(true)
    await handle.dispose()
    rmSync(store, { recursive: true, force: true })
    rmSync(join(STC_ROOT, 'dossier'), { recursive: true, force: true })
  }, 240_000)
})
