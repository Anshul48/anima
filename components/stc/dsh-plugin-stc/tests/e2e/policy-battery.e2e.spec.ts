/**
 * Mechanics battery: scripted mock model runs three delivery-policy shapes
 * through the REAL agent loop + tools + backend (quota-free). Each episode
 * appends one EpisodeResult JSON line to $POLICY_RESULTS for the theoracle.
 * HONEST SCOPE: this measures launch/verify/evidence/recovery MECHANICS,
 * not model task quality — that comparison needs the live batch.
 * Runs inside a DSH checkout via scripts/run-e2e.sh SPEC_FILE=policy-battery.e2e.spec.ts.
 */
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { appendFileSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
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
const SST_SRC = process.env['SST_SRC'] ?? ''
const PROMPT_KIT = process.env['PROMPT_KIT'] ?? ''
const RESULTS = process.env['POLICY_RESULTS'] ?? ''

function emit(result: Record<string, unknown>): void {
  if (RESULTS) appendFileSync(RESULTS, JSON.stringify(result) + '\n', 'utf8')
}

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

function results(agent: Agent): { isError: boolean; text: string }[] {
  return agent.session.snapshotEvents()
    .filter((e) => e.type === 'tool/result')
    .map((e) => {
      if (e.type !== 'tool/result') throw new Error('unreachable')
      return {
        isError: e.data.message.isError === true,
        text: e.data.message.content
          .filter((b) => b.type === 'text')
          .map((b) => (b as { text: string }).text)
          .join(''),
      }
    })
}

async function pollExit(store: string, want: string, timeoutMs: number): Promise<string> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const dirs = readdirSync(store).filter((d) => d.startsWith('run-'))
    if (dirs.length > 0) {
      try {
        const exit = JSON.parse(readFileSync(join(store, dirs[0]!, 'exit.json'), 'utf8'))
        if (exit.status === want) return join(store, dirs[0]!)
      } catch { /* not yet */ }
    }
    await new Promise((r) => setTimeout(r, 200))
  }
  throw new Error(`run did not reach ${want} within ${timeoutMs}ms`)
}

function prepEnv(store: string): void {
  process.env['STC_ROOT'] = STC_ROOT
  process.env['STC_DSH_STORE'] = store
  process.env['PYTHONPATH'] = `${SST_SRC}:${PROMPT_KIT}`
}

function cleanup(store: string): void {
  rmSync(store, { recursive: true, force: true })
  rmSync(join(STC_ROOT, 'dossier'), { recursive: true, force: true })
}

describe('mechanics battery', () => {
  it('b1-direct: run then verify records', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-bat-b1-'))
    prepEnv(store)
    const started = Date.now()
    let completed = false
    let evidenceComplete = false
    try {
      const adapter = new MockAdapter([
        toolCallResponse('call-1', 'stc_run', {
          spec: 'specs/sample_spec.md', mode: 'dry-run', confirm: 'RUN',
        }),
        textResponse('launched.'),
      ])
      const ctx = await harness(adapter)
      const handle = await ctx.agents.create({ sessionId: SessionId('bat-b1'), agentOptions: { provider: 'mock', model: 'mock' } })
      const agent = handle.agent
      agent.followup(createUserMessage({ content: [{ type: 'text', text: 'dry run it' }], source: { kind: 'user' } }))
      await waitForIdle(ctx, agent)
      const [first] = results(agent)
      expect(first!.isError).toBe(false)
      const runDir = await pollExit(store, 'completed', 120_000)
      const log = readFileSync(join(runDir, 'console.log'), 'utf8')
      evidenceComplete = log.length > 100
      expect(evidenceComplete).toBe(true)
      await handle.dispose()
      completed = true
      emit({
        policy: 'b1-direct', task: 'dry-run-verify', completed: true,
        evidenceComplete, regressions: 0, faultsInjected: 0, faultsRecovered: 0,
        toolCalls: results(agent).length, durationMs: Date.now() - started, timedOut: false,
      })
    } catch (err) {
      emit({
        policy: 'b1-direct', task: 'dry-run-verify', completed: false,
        evidenceComplete, regressions: 0, faultsInjected: 0, faultsRecovered: 0,
        toolCalls: -1, durationMs: Date.now() - started, timedOut: false,
      })
      throw err
    } finally {
      cleanup(store)
    }
    expect(completed).toBe(true)
  }, 180_000)

  it('b2-gated: preview, deny bad confirm, run, check dossier evidence', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-bat-b2-'))
    prepEnv(store)
    const started = Date.now()
    let evidenceComplete = false
    try {
      const adapter = new MockAdapter([
        toolCallResponse('call-1', 'stc_preview', { spec: 'specs/sample_spec.md', mode: 'dry-run' }),
        toolCallResponse('call-2', 'stc_run', {
          spec: 'specs/sample_spec.md', mode: 'dry-run', confirm: 'please',
        }),
        toolCallResponse('call-3', 'stc_run', {
          spec: 'specs/sample_spec.md', mode: 'dry-run', confirm: 'RUN',
        }),
        textResponse('gated run done.'),
      ])
      const ctx = await harness(adapter)
      const handle = await ctx.agents.create({ sessionId: SessionId('bat-b2'), agentOptions: { provider: 'mock', model: 'mock' } })
      const agent = handle.agent
      agent.followup(createUserMessage({ content: [{ type: 'text', text: 'gated dry run' }], source: { kind: 'user' } }))
      await waitForIdle(ctx, agent)
      const rs = results(agent)
      // call-1 preview ok; call-2 denied; call-3 launches (background).
      expect(rs[0]!.isError).toBe(false)
      expect(rs[0]!.text).toContain('--target')
      expect(rs[1]!.isError).toBe(true)
      expect(rs[2]!.isError).toBe(false)
      const runDir = await pollExit(store, 'completed', 120_000)
      const log = readFileSync(join(runDir, 'console.log'), 'utf8')
      evidenceComplete = log.length > 100
      expect(evidenceComplete).toBe(true)
      await handle.dispose()
      emit({
        policy: 'b2-gated', task: 'gated-verify', completed: true,
        evidenceComplete, regressions: 0, faultsInjected: 1, faultsRecovered: 1,
        toolCalls: rs.length, durationMs: Date.now() - started, timedOut: false,
      })
    } catch (err) {
      emit({
        policy: 'b2-gated', task: 'gated-verify', completed: false,
        evidenceComplete, regressions: 0, faultsInjected: 1, faultsRecovered: 0,
        toolCalls: -1, durationMs: Date.now() - started, timedOut: false,
      })
      throw err
    } finally {
      cleanup(store)
    }
  }, 180_000)

  it('p1-aci: sense, act, cancel, verify kill records', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-bat-p1-'))
    prepEnv(store)
    const started = Date.now()
    let evidenceComplete = false
    try {
      const adapter = new MockAdapter([
        toolCallResponse('call-1', 'stc_ping', {}),
        toolCallResponse('call-2', 'stc_run', {
          spec: 'specs/sample_spec.md', mode: 'exec', confirm: 'RUN',
          exec_harness: join(STC_ROOT, 'operator-console/fixtures/EXEC-ECHO/sleep.sh'),
        }),
        toolCallResponse('call-3', 'stc_cancel', { job_id: 'stc-run-1', reason: 'battery recovery' }),
        textResponse('cycled.'),
      ])
      const ctx = await harness(adapter)
      const handle = await ctx.agents.create({ sessionId: SessionId('bat-p1'), agentOptions: { provider: 'mock', model: 'mock' } })
      const agent = handle.agent
      // Turn 1: sense + launch.
      agent.followup(createUserMessage({ content: [{ type: 'text', text: 'start exec' }], source: { kind: 'user' } }))
      await waitForIdle(ctx, agent)
      await new Promise((r) => setTimeout(r, 8000))
      // Turn 2 (scripted third response): cancel.
      agent.followup(createUserMessage({ content: [{ type: 'text', text: 'cancel it' }], source: { kind: 'user' } }))
      await waitForIdle(ctx, agent)
      const rs = results(agent)
      expect(rs[0]!.isError).toBe(false)
      expect(rs[1]!.isError).toBe(false)
      expect(rs[2]!.isError).toBe(false)
      const runDir = await pollExit(store, 'killed', 60_000)
      const run = JSON.parse(readFileSync(join(runDir, 'run.json'), 'utf8'))
      let pidDead = false
      try {
        process.kill(run.pid, 0)
      } catch {
        pidDead = true
      }
      evidenceComplete = pidDead
      expect(pidDead).toBe(true)
      await handle.dispose()
      emit({
        policy: 'p1-aci', task: 'cancel-recovery', completed: true,
        evidenceComplete, regressions: 0, faultsInjected: 1, faultsRecovered: 1,
        toolCalls: rs.length, durationMs: Date.now() - started, timedOut: false,
      })
    } catch (err) {
      emit({
        policy: 'p1-aci', task: 'cancel-recovery', completed: false,
        evidenceComplete, regressions: 0, faultsInjected: 1, faultsRecovered: 0,
        toolCalls: -1, durationMs: Date.now() - started, timedOut: false,
      })
      throw err
    } finally {
      cleanup(store)
    }
  }, 240_000)
})
