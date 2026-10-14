/**
 * STC1 recovery e2e: truthful interruption/recovery through the REAL agent
 * loop — quota-free (scripted mock model, real STC backend venv, exec/sleep
 * fixture only; no model calls, no spend). Runs inside a DSH checkout via
 * scripts/run-e2e.sh with SPEC_FILE=stc-recovery.e2e.spec.ts.
 *
 * Flow: launch -> interrupt at a declared checkpoint -> simulated DSH restart
 * (fresh Context/registry, same durable store) -> status shows explicit
 * interrupted state -> recover reports needs-decision (no silent retry) ->
 * attest verified side effects -> recover resumes a linked continuation that
 * skips completed effects -> redirect invalidates pending work. Cancel proof
 * (killed, no recovery record) is asserted intact.
 */
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
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
import { recordEffect, resolveRunState } from '../../src/stc-recovery.ts'
import { attachSession } from '../../src/stc-runstore.ts'

const STC_ROOT = process.env['STC_ROOT'] ?? (() => { throw new Error('STC_ROOT env is required') })()
const SST_SRC = process.env['SST_SRC'] ?? '/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/sst/src'
const PROMPT_KIT = process.env['PROMPT_KIT'] ?? '/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/prompt-kit'
const SLEEP = `${STC_ROOT}/operator-console/fixtures/EXEC-ECHO/sleep.sh`

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

interface ToolResult {
  text: string
  isError: boolean
}

function toolResults(agent: Agent): ToolResult[] {
  return agent.session
    .snapshotEvents()
    .filter((e) => e.type === 'tool/result')
    .map((e) => {
      if (e.type !== 'tool/result') throw new Error('unreachable')
      const text = e.data.message.content
        .filter((block) => block.type === 'text')
        .map((block) => (block as { text: string }).text)
        .join('')
      return { text, isError: e.data.message.isError === true }
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

function runDirs(store: string): string[] {
  return readdirSync(store).filter((d) => d.startsWith('run-'))
}

function readJson(path: string): any {
  return JSON.parse(readFileSync(path, 'utf8'))
}

function isPidDead(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return false
  } catch {
    return true
  }
}

function useStore(store: string): void {
  process.env['STC_ROOT'] = STC_ROOT
  process.env['STC_DSH_STORE'] = store
  process.env['PYTHONPATH'] = `${SST_SRC}:${PROMPT_KIT}`
}

function cleanupDossier(): void {
  rmSync(join(STC_ROOT, 'dossier'), { recursive: true, force: true })
}

describe('stc recovery through the agent loop', () => {
  it('interrupt -> restart -> needs-decision -> attested resume with skip list', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-e2e-recovery-'))
    useStore(store)
    // choice:'1' relays the operator gate so the run genuinely proceeds to the
    // (sleeping, quota-free) harness instead of exiting at the ambiguity gate.
    const SLEEP_ARGS = {
      spec: 'specs/sample_spec.md', mode: 'exec', confirm: 'RUN', exec_harness: SLEEP, choice: '1',
    }
    const LIVE_LINE = 'Running dialectic loop'

    // Phase A: launch a live exec run; once it has observably produced
    // output, interrupt it at a declared checkpoint (same agent, appended
    // script — the mock consumes entries in order across followups).
    const scriptA: Array<ReturnType<typeof textResponse>> = [
      toolCallResponse('call-1', 'stc_run', SLEEP_ARGS),
      textResponse('run launched.'),
    ]
    const ctx1 = await harness(new MockAdapter(scriptA))
    const h1 = await ctx1.agents.create({ sessionId: SessionId('e2e-rec-a'), agentOptions: { provider: 'mock', model: 'mock' } })
    h1.agent.followup(createUserMessage({ content: [{ type: 'text', text: 'launch it' }], source: { kind: 'user' } }))
    await waitForIdle(ctx1, h1.agent)
    const launched = toolResults(h1.agent)
    expect(launched.length).toBe(1)
    expect(launched[0]!.isError).toBe(false)
    expect(launched[0]!.text).toContain('stc-run-1')

    expect(runDirs(store).length).toBe(1)
    const runId = runDirs(store)[0]!.slice('run-'.length)
    const dir = join(store, `run-${runId}`)
    await pollUntil(() => {
      try {
        return readFileSync(join(dir, 'console.log'), 'utf8').includes(LIVE_LINE)
      } catch {
        return false
      }
    }, 60_000)

    scriptA.push(
      toolCallResponse('call-2', 'stc_interrupt', {
        job_id: 'stc-run-1', checkpoint: 'e2e-checkpoint-1', reason: 'e2e pause probe',
      }),
      textResponse('interrupted.'),
    )
    h1.agent.followup(createUserMessage({ content: [{ type: 'text', text: 'interrupt it' }], source: { kind: 'user' } }))
    await waitForIdle(ctx1, h1.agent)
    const phaseA = toolResults(h1.agent)
    expect(phaseA.length).toBe(2)
    expect(phaseA[1]!.isError).toBe(false)
    expect(phaseA[1]!.text).toContain('interrupted')
    expect(phaseA[1]!.text).toContain('e2e-checkpoint-1')
    await h1.dispose()

    await pollUntil(() => {
      try {
        return readJson(join(dir, 'exit.json')).status === 'killed'
      } catch {
        return false
      }
    }, 60_000)
    const run = readJson(join(dir, 'run.json'))
    expect(isPidDead(run.pid)).toBe(true)
    const recovery = readJson(join(dir, 'recovery.json'))
    expect(recovery.state).toBe('interrupted')
    expect(recovery.checkpoint).toBe('e2e-checkpoint-1')
    expect(recovery.snapshot.spec).toBe('specs/sample_spec.md')
    expect(recovery.snapshot.mode).toBe('exec')
    const log = readFileSync(join(dir, 'console.log'), 'utf8')
    expect(log).toContain(LIVE_LINE)

    // Phase B: simulated DSH restart (fresh registry, same store). Status must
    // report the explicit interrupted state; recovery with no side-effect
    // evidence must report needs-decision and launch nothing.
    const beforeRecovery = readFileSync(join(dir, 'recovery.json'), 'utf8')
    const ctx2 = await harness(new MockAdapter([
      toolCallResponse('call-1', 'stc_status', { run_id: runId }),
      toolCallResponse('call-2', 'stc_recover', { run_id: runId }),
      textResponse('recovery evaluated.'),
    ]))
    const h2 = await ctx2.agents.create({ sessionId: SessionId('e2e-rec-b'), agentOptions: { provider: 'mock', model: 'mock' } })
    h2.agent.followup(createUserMessage({ content: [{ type: 'text', text: 'status then recover' }], source: { kind: 'user' } }))
    await waitForIdle(ctx2, h2.agent)
    const phaseB = toolResults(h2.agent)
    expect(phaseB.length).toBe(2)
    expect(phaseB[0]!.isError).toBe(false)
    expect(phaseB[0]!.text).toContain('interrupted')
    expect(phaseB[0]!.text).toContain('e2e-checkpoint-1')
    expect(phaseB[1]!.isError).toBe(false)
    expect(phaseB[1]!.text).toContain('needs-decision')
    await h2.dispose()

    // No resurrection: still exactly one run, no continuation linked.
    expect(runDirs(store).length).toBe(1)
    const afterB = readJson(join(dir, 'recovery.json'))
    expect(afterB.state).toBe('interrupted')
    expect(afterB.recovery?.continuedBy ?? '').toBe('')
    expect(JSON.parse(beforeRecovery).checkpoint).toBe(afterB.checkpoint)

    // Phase B2: the same recovery via Builder C session correlation
    // (stc_recover feature-detects getBySession; session linkage must not
    // trip the identity check, which covers argv/cwd/spec/mode only).
    attachSession(store, runId, { sessionId: 'e2e-rec-session' })
    const ctx2b = await harness(new MockAdapter([
      toolCallResponse('call-1', 'stc_recover', { session_id: 'e2e-rec-session' }),
      textResponse('session recovery evaluated.'),
    ]))
    const h2b = await ctx2b.agents.create({ sessionId: SessionId('e2e-rec-b2'), agentOptions: { provider: 'mock', model: 'mock' } })
    h2b.agent.followup(createUserMessage({ content: [{ type: 'text', text: 'recover by session' }], source: { kind: 'user' } }))
    await waitForIdle(ctx2b, h2b.agent)
    const phaseB2 = toolResults(h2b.agent)
    expect(phaseB2.length).toBe(1)
    expect(phaseB2[0]!.isError).toBe(false)
    expect(phaseB2[0]!.text).toContain('needs-decision')
    expect(phaseB2[0]!.text).toContain(runId)
    await h2b.dispose()
    expect(runDirs(store).length).toBe(1)

    // Phase C: attest the one verified side effect (console output captured
    // durably — observed on disk above, not assumed).
    recordEffect(store, runId, {
      id: 'exec-console-output',
      kind: 'console-output',
      status: 'completed',
      proof: `console.log contains ${JSON.stringify(LIVE_LINE)}`,
    })

    // Phase D: recover again -> verified resume launches a linked continuation
    // with identical identity that skips the completed effect.
    const ctx3 = await harness(new MockAdapter([
      toolCallResponse('call-1', 'stc_recover', { run_id: runId }),
      textResponse('resumed.'),
    ]))
    const h3 = await ctx3.agents.create({ sessionId: SessionId('e2e-rec-d'), agentOptions: { provider: 'mock', model: 'mock' } })
    h3.agent.followup(createUserMessage({ content: [{ type: 'text', text: 'recover now' }], source: { kind: 'user' } }))
    await waitForIdle(ctx3, h3.agent)
    const phaseD = toolResults(h3.agent)
    expect(phaseD.length).toBe(1)
    expect(phaseD[0]!.isError).toBe(false)
    expect(phaseD[0]!.text).toContain('resumed')

    const continuedBy = readJson(join(dir, 'recovery.json')).recovery.continuedBy as string
    expect(typeof continuedBy).toBe('string')
    expect(continuedBy.length).toBeGreaterThan(0)
    expect(runDirs(store).length).toBe(2)
    const next = readJson(join(store, `run-${continuedBy}`, 'run.json'))
    expect(next.resumedFrom).toBe(runId)
    expect(next.resumeSkip).toEqual(['exec-console-output'])
    expect(next.argv).toEqual(run.argv)
    expect(next.spec).toBe(run.spec)
    expect(next.mode).toBe(run.mode)
    expect(next.cwd).toBe(run.cwd)

    // Follow-up in the same flow: the continuation runs; stop it test-side
    // (external SIGKILL — the run's own close handler still records exit).
    await pollUntil(() => {
      try {
        return readFileSync(join(store, `run-${continuedBy}`, 'console.log'), 'utf8').includes(LIVE_LINE)
      } catch {
        return false
      }
    }, 60_000)
    process.kill(next.pid, 'SIGKILL')
    await pollUntil(() => {
      try {
        return readJson(join(store, `run-${continuedBy}`, 'exit.json')).status === 'killed'
      } catch {
        return false
      }
    }, 60_000)
    await h3.dispose()
    rmSync(store, { recursive: true, force: true })
    cleanupDossier()
  }, 300_000)

  it('live run reattaches; redirect invalidates pending and refuses recovery', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-e2e-redirect-'))
    useStore(store)
    const ctx = await harness(new MockAdapter([
      toolCallResponse('call-1', 'stc_run', {
        spec: 'specs/sample_spec.md', mode: 'exec', confirm: 'RUN', exec_harness: SLEEP, choice: '1',
      }),
      toolCallResponse('call-2', 'stc_recover', { job_id: 'stc-run-1' }),
      toolCallResponse('call-3', 'stc_redirect', { job_id: 'stc-run-1', brief_ref: 'brief-v2', reason: 'e2e scope change' }),
      toolCallResponse('call-4', 'stc_recover', { job_id: 'stc-run-1' }),
      textResponse('redirected.'),
    ]))
    const h = await ctx.agents.create({ sessionId: SessionId('e2e-rec-e'), agentOptions: { provider: 'mock', model: 'mock' } })
    h.agent.followup(createUserMessage({ content: [{ type: 'text', text: 'run, reattach, redirect, recover' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, h.agent)
    const results = toolResults(h.agent)
    expect(results.length).toBe(4)
    expect(results[0]!.isError).toBe(false)
    expect(results[1]!.isError).toBe(false)
    expect(results[1]!.text).toContain('reattached')
    expect(results[2]!.isError).toBe(false)
    expect(results[2]!.text).toContain('redirected')
    expect(results[2]!.text).toContain('brief-v2')
    expect(results[3]!.isError).toBe(false)
    expect(results[3]!.text).toContain('refused-redirected')
    await h.dispose()

    expect(runDirs(store).length).toBe(1)
    const runId = runDirs(store)[0]!.slice('run-'.length)
    const dir = join(store, `run-${runId}`)
    await pollUntil(() => {
      try {
        return readJson(join(dir, 'exit.json')).status === 'killed'
      } catch {
        return false
      }
    }, 60_000)
    expect(isPidDead(readJson(join(dir, 'run.json')).pid)).toBe(true)
    const recovery = readJson(join(dir, 'recovery.json'))
    expect(recovery.state).toBe('redirected')
    expect(recovery.redirect.briefRef).toBe('brief-v2')
    expect(resolveRunState(store, runId, '').state).toBe('redirected')
    rmSync(store, { recursive: true, force: true })
    cleanupDossier()
  }, 300_000)

  it('cancel proof intact: killed with no recovery record', async () => {
    const store = mkdtempSync(join(tmpdir(), 'stc-e2e-cancelproof-'))
    useStore(store)
    const ctx = await harness(new MockAdapter([
      toolCallResponse('call-1', 'stc_run', {
        spec: 'specs/sample_spec.md', mode: 'exec', confirm: 'RUN', exec_harness: SLEEP, choice: '1',
      }),
      toolCallResponse('call-2', 'stc_cancel', { job_id: 'stc-run-1', reason: 'e2e cancel proof' }),
      textResponse('cancelled.'),
    ]))
    const h = await ctx.agents.create({ sessionId: SessionId('e2e-rec-c'), agentOptions: { provider: 'mock', model: 'mock' } })
    h.agent.followup(createUserMessage({ content: [{ type: 'text', text: 'run then cancel' }], source: { kind: 'user' } }))
    await waitForIdle(ctx, h.agent)
    const results = toolResults(h.agent)
    expect(results.length).toBe(2)
    expect(results[1]!.isError).toBe(false)
    await h.dispose()

    const runId = runDirs(store)[0]!.slice('run-'.length)
    const dir = join(store, `run-${runId}`)
    await pollUntil(() => {
      try {
        return readJson(join(dir, 'exit.json')).status === 'killed'
      } catch {
        return false
      }
    }, 60_000)
    expect(isPidDead(readJson(join(dir, 'run.json')).pid)).toBe(true)
    expect(() => readFileSync(join(dir, 'recovery.json'), 'utf8')).toThrow()
    expect(resolveRunState(store, runId, '').state).toBe('killed')
    rmSync(store, { recursive: true, force: true })
    cleanupDossier()
  }, 300_000)
})
