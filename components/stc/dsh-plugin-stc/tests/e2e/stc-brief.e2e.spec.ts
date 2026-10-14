/**
 * STC1 brief + correlation e2e: a scripted mock model drives stc_run through
 * the REAL agent loop under a known DSH session id; the spec then performs
 * the attach step the pending stc-run.ts one-line hook will do automatically
 * (Builder D's file; Builder C must not touch it) and proves the durable
 * DSH-session <-> STC-run correlation end to end. Quota-free: dry-run only,
 * no model calls, no spend. Runs via scripts/run-e2e.sh (SPEC_FILE=...).
 */
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs'
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
import { briefDir, createBrief, readBrief } from '../../src/stc-brief.ts'
import { attachSession, getBySession, getRun } from '../../src/stc-runstore.ts'

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

async function pollUntil(predicate: () => boolean, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (predicate()) return
    await new Promise((resolve) => setTimeout(resolve, 200))
  }
  throw new Error(`condition not met within ${timeoutMs}ms`)
}

describe('stc brief + session correlation through the agent loop', () => {
  it('loop-launched dry-run correlates to its DSH session and brief', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-e2e-brief-'))
    process.env['STC_ROOT'] = STC_ROOT
    process.env['STC_DSH_STORE'] = store
    process.env['PYTHONPATH'] = `${SST_SRC}:${PROMPT_KIT}`
    // Standalone brief under $STC_DSH_STORE/briefs/<id>/, created pre-launch.
    const brief = createBrief(
      briefDir(store, 'e2e-brief-1'),
      {
        task: 'e2e dry-run correlation probe',
        acceptance: ['run completes', 'session resolves to run'],
      },
      { id: 'e2e-brief-1' },
    )
    const adapter = new MockAdapter([
      toolCallResponse('call-1', 'stc_run', {
        spec: 'specs/sample_spec.md', mode: 'dry-run', confirm: 'RUN',
      }),
      textResponse('run launched.'),
    ])
    const ctx = await harness(adapter)
    const sessionId = 'e2e-brief'
    const handle = await ctx.agents.create({ sessionId: SessionId(sessionId), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    // Agent identity IS the DSH session identity (Agent.id: SessionId).
    expect(String(agent.id)).toBe(sessionId)
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'dry run it' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
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
    const runId = readdirSync(store).find((d) => d.startsWith('run-'))!.slice('run-'.length)
    // The pending stc-run.ts hook does exactly this line with exec.agent.id.
    const rec = attachSession(store, runId, { sessionId, briefId: brief.id })
    expect(rec.sessionId).toBe(sessionId)
    expect(rec.briefId).toBe(brief.id)
    // stc-run.ts record fields preserved through the merge.
    expect(typeof rec['argv']).toBe('object')
    expect(rec['mode']).toBe('dry-run')
    // Correlation resolves both directions from disk.
    const bySession = getBySession(store, sessionId)
    expect(bySession.length).toBe(1)
    expect(bySession[0]!.runId).toBe(runId)
    expect(getRun(store, runId)?.sessionId).toBe(sessionId)
    expect(readBrief(briefDir(store, brief.id))?.task).toContain('correlation probe')
    await handle.dispose()
    rmSync(store, { recursive: true, force: true })
    rmSync(join(STC_ROOT, 'dossier'), { recursive: true, force: true })
  }, 180_000)

  it('auto-attaches the loop-launched run to its DSH session without manual attach', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-e2e-brief-auto-'))
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
    const sessionId = 'e2e-brief-auto'
    const handle = await ctx.agents.create({ sessionId: SessionId(sessionId), agentOptions: { provider: 'mock', model: 'mock' } })
    const agent = handle.agent
    expect(String(agent.id)).toBe(sessionId)
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'dry run it' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, agent)
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
    const runId = readdirSync(store).find((d) => d.startsWith('run-'))!.slice('run-'.length)
    // NO manual attachSession call in this case: the stc-run.ts hook must have
    // attached exec.agent.id to run.json plus the sessions/ reverse index.
    expect(getRun(store, runId)?.sessionId).toBe(sessionId)
    const bySession = getBySession(store, sessionId)
    expect(bySession.length).toBe(1)
    expect(bySession[0]!.runId).toBe(runId)
    await handle.dispose()
    rmSync(store, { recursive: true, force: true })
    rmSync(join(STC_ROOT, 'dossier'), { recursive: true, force: true })
  }, 180_000)
})
