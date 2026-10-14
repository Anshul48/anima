/**
 * Real-task demo: coordinator-assisted manual-mode backend runs driven through
 * the REAL agent loop + tools, quota-free. The scripted "model" stands in for
 * the coordinator (labeled coordinator-assisted execution per the mandate):
 * every tool call below is one the coordinator authored after observing the
 * previous result (function entries evaluate lazily, in order).
 *
 * Task: repair a seeded bug (subtraction typo) in a self-built scratch repo.
 * Run 1 executes it; run 2 (follow-up, iters=2) shows iteration with pruned-
 * attempt feedback. Assertions cover WORKSPACE mechanics (preview/run/status/
 * log/dossier journey + durable evidence), NOT backend success: the backend
 * honestly reports NEEDS_REPAIR/no-verified-candidate on foreign trees
 * because its trusted test selection is hardwired to the STC suite map
 * (see docs/STC-DSH-RECORD.md). That diagnosed outcome is locked as a
 * tripwire (it must visibly flip if backend selection ever changes),
 * and the journey around it is what this spec exercises.
 */
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import {
  existsSync,
  mkdtempSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { execFileSync } from 'node:child_process'
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

const CALC_PY = '"""Tiny calculator (demo task source)."""\n\n\ndef add(a: int, b: int) -> int:\n    return a - b\n'
const TEST_PY = 'from src.calc import add\n\n\ndef test_add() -> None:\n    assert add(2, 3) == 5\n'
const SPEC_MD = [
  '# Fix calculator addition',
  '',
  '## Domain Invariants',
  'add(a, b) must return the arithmetic sum of its arguments.',
  '',
  '## Persistence & Storage',
  'None; pure functions only.',
  '',
  '## Communication Protocols',
  'Direct Python import from the calc module.',
  '',
  '## Boundary & Security',
  'No network, no filesystem access; change only src/calc.py.',
  '',
  '## Failure Resilience',
  'tests/test_calc.py must pass.',
  '',
].join('\n')
// Minimal unified diff (no index line: blob hashes are repo-specific).
const FIX_DIFF = [
  'diff --git a/src/calc.py b/src/calc.py',
  '--- a/src/calc.py',
  '+++ b/src/calc.py',
  '@@ -2,4 +2,4 @@',
  ' ',
  ' ',
  ' def add(a: int, b: int) -> int:',
  '-    return a - b',
  '+    return a + b',
  '',
].join('\n')

function buildTaskRepo(): string {
  const root = mkdtempSync(join(tmpdir(), 'stc-demo-task-'))
  mkdirSync(join(root, 'src'))
  mkdirSync(join(root, 'tests'))
  writeFileSync(join(root, 'src', 'calc.py'), CALC_PY)
  writeFileSync(join(root, 'src', '__init__.py'), '')
  writeFileSync(join(root, 'tests', 'test_calc.py'), TEST_PY)
  writeFileSync(join(root, 'tests', '__init__.py'), '')
  writeFileSync(join(root, 'spec.md'), SPEC_MD)
  const git = (args: string[]) =>
    execFileSync('git', args, { cwd: root, stdio: 'pipe' })
  git(['init', '-q'])
  git(['add', '-A'])
  git(['-c', 'user.email=demo@local', '-c', 'user.name=demo', 'commit', '-qm', 'init'])
  return root
}

function writeFixtures(
  dir: string,
  diverges: Array<{ title: string; rationale: string }>,
): void {
  mkdirSync(dir, { recursive: true })
  diverges.forEach((d, i) => {
    writeFileSync(
      join(dir, `0${i + 1}-diverge.json`),
      JSON.stringify(
        {
          branches: [
            {
              strategy_title: d.title,
              hypothesis_or_rationale: d.rationale,
              proposed_changes: FIX_DIFF,
            },
          ],
        },
        null,
        2,
      ) + '\n',
    )
  })
  writeFileSync(
    join(dir, `0${diverges.length + 1}-critique.json`),
    JSON.stringify(
      {
        value_score: 0.95,
        verdict: 'APPROVE',
        rationale: 'Single-line fix matches the invariant; touches only src/calc.py.',
      },
      null,
      2,
    ) + '\n',
  )
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

function allResultTexts(agent: Agent): string[] {
  return agent.session
    .snapshotEvents()
    .filter((e) => e.type === 'tool/result')
    .map((e) => {
      if (e.type !== 'tool/result') throw new Error('unreachable')
      return e.data.message.content
        .filter((block) => block.type === 'text')
        .map((block) => (block as { text: string }).text)
        .join('')
    })
}

function allResultErrors(agent: Agent): boolean[] {
  return agent.session
    .snapshotEvents()
    .filter((e) => e.type === 'tool/result')
    .map((e) => {
      if (e.type !== 'tool/result') throw new Error('unreachable')
      return e.data.message.isError === true
    })
}

async function pollUntil(predicate: () => boolean, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (predicate()) return
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw new Error(`condition not met within ${timeoutMs}ms`)
}

describe('real-task demo through the agent loop (coordinator-assisted)', () => {
  it('manual repair task + follow-up run with full evidence', async () => {
    const taskRoot = buildTaskRepo()
    const store = mkdtempSync(join(tmpdir(), 'stc-demo-store-'))
    // Dossier lives under STC_ROOT: stc_dossier's traversal guard requires it.
    const dossier = mkdtempSync(join(STC_ROOT, 'demo-dossier-'))
    const fixtures = mkdtempSync(join(tmpdir(), 'stc-demo-fixtures-'))
    writeFixtures(fixtures, [
      {
        title: 'Fix subtraction typo in add',
        rationale: 'add returns a-b; the spec invariant requires the sum.',
      },
    ])
    process.env['STC_ROOT'] = STC_ROOT
    process.env['STC_DSH_STORE'] = store
    process.env['STC_SOURCE_ROOT'] = taskRoot
    process.env['STC_DOSSIER_DIR'] = dossier
    process.env['STC_MANUAL_FIXTURE_DIR'] = fixtures
    process.env['PYTHONPATH'] = `${SST_SRC}:${PROMPT_KIT}`
    const spec = join(taskRoot, 'spec.md')
    const budget1 = 'time=300,iters=1,branching=1,depth=2'

    const runIdOf = (): string => {
      const dirs = readdirSync(store).filter((d) => d.startsWith('run-'))
      if (dirs.length === 0) throw new Error('no run dir yet')
      return dirs.sort()[dirs.length - 1] as string
    }
    const exitOf = (runId: string): Record<string, unknown> | null => {
      try {
        return JSON.parse(readFileSync(join(store, runId, 'exit.json'), 'utf8')) as Record<
          string,
          unknown
        >
      } catch {
        return null
      }
    }

    const adapter = new MockAdapter([
      () => toolCallResponse('call-1', 'stc_preview', { spec, mode: 'manual', budget: budget1 }),
      textResponse('preview ok.'),
      () =>
        toolCallResponse('call-2', 'stc_run', {
          spec,
          mode: 'manual',
          budget: budget1,
          confirm: 'RUN',
        }),
      textResponse('run 1 launched.'),
      () => toolCallResponse('call-3', 'stc_status', { job_id: 'stc-run-1' }),
      textResponse('run 1 status seen.'),
      () => toolCallResponse('call-4', 'stc_log', { run_id: runIdOf().slice('run-'.length) }),
      textResponse('run 1 log seen.'),
      () => toolCallResponse('call-5', 'stc_dossier', { dossier_path: dossier }),
      textResponse('run 1 dossier seen.'),
    ])
    const ctx = await harness(adapter)
    const handle = await ctx.agents.create({
      sessionId: SessionId('demo-task'),
      agentOptions: { provider: 'mock', model: 'mock' },
    })
    const agent = handle.agent
    const say = async (text: string) => {
      agent.followup(createUserMessage({ content: [{ type: 'text', text }], source: { kind: 'user' } }))
      await waitForIdle(ctx, agent)
    }

    await say('preview the manual repair run')
    expect(allResultErrors(agent)[0]).toBe(false)
    expect(allResultTexts(agent)[0]).toContain('--manual')
    expect(allResultTexts(agent)[0]).toContain('spec.md')

    await say('launch run 1')
    expect(allResultErrors(agent)[1]).toBe(false)
    expect(allResultTexts(agent)[1]).toContain('stc-run-1')
    await pollUntil(() => exitOf(runIdOf()) !== null, 240_000)
    const run1 = runIdOf()
    const exit1 = exitOf(run1)
    expect(exit1).not.toBeNull()
    console.log('RUN1-EXIT:', JSON.stringify(exit1))
    // Honest backend outcome on a foreign tree: process exits 1 (no champion).
    expect(String((exit1 as Record<string, unknown>)['detail'])).toContain('exit code: 1')
    const log1 = readFileSync(join(store, run1, 'console.log'), 'utf8')
    expect(log1).toContain('No champion')

    await say('status of run 1')
    expect(allResultErrors(agent)[2]).toBe(false)
    expect(allResultTexts(agent)[2]).toContain('stc-run-1')

    await say('log of run 1')
    expect(allResultErrors(agent)[3]).toBe(false)
    expect(allResultTexts(agent)[3]?.length).toBeGreaterThan(100)

    await say('dossier of run 1')
    expect(allResultErrors(agent)[4]).toBe(false)
    const dos1 = allResultTexts(agent)[4] as string
    expect(dos1).toContain('STATUS=')
    console.log('RUN1-DOSSIER:', dos1)
    // Diagnosed backend behavior on foreign trees (suite-map hardwire):
    // NEEDS_REPAIR with full evidence. Locks the behavior, not success.
    expect(readFileSync(join(dossier, 'STATUS'), 'utf8')).toContain('NEEDS_REPAIR')
    expect(dos1).toContain('STATUS=NEEDS_REPAIR')
    expect(existsSync(join(dossier, 'branches.json'))).toBe(true)

    // Follow-up: second attempt with iteration budget; fixtures restaged so
    // iteration 2 diverges with the pruned-attempt lesson in context.
    const budget2 = 'time=300,iters=2,branching=1,depth=2'
    for (const f of readdirSync(fixtures)) rmSync(join(fixtures, f))
    writeFixtures(fixtures, [
      {
        title: 'Fix subtraction typo in add (retry)',
        rationale: 'Same one-line fix; prior attempt pruned at verification.',
      },
      {
        title: 'Fix subtraction typo, second angle',
        rationale: 'Re-issues the fix with pruned-attempt context from iteration 1.',
      },
    ])
    const adapter2 = new MockAdapter([
      () =>
        toolCallResponse('call-6', 'stc_run', {
          spec,
          mode: 'manual',
          budget: budget2,
          confirm: 'RUN',
        }),
      textResponse('run 2 launched.'),
      () => toolCallResponse('call-7', 'stc_dossier', { dossier_path: dossier }),
      textResponse('run 2 dossier seen.'),
    ])
    const ctx2 = await harness(adapter2)
    const handle2 = await ctx2.agents.create({
      sessionId: SessionId('demo-followup'),
      agentOptions: { provider: 'mock', model: 'mock' },
    })
    const agent2 = handle2.agent
    const say2 = async (text: string) => {
      agent2.followup(
        createUserMessage({ content: [{ type: 'text', text }], source: { kind: 'user' } }),
      )
      await waitForIdle(ctx2, agent2)
    }
    await say2('launch follow-up run 2')
    expect(allResultErrors(agent2)[0]).toBe(false)
    await pollUntil(
      () => readdirSync(store).filter((d) => d.startsWith('run-')).length >= 2,
      240_000,
    )
    const run2 = readdirSync(store)
      .filter((d) => d.startsWith('run-') && d !== run1)
      .sort()[0] as string
    await pollUntil(() => exitOf(run2) !== null, 240_000)
    console.log('RUN2-EXIT:', JSON.stringify(exitOf(run2)))
    await say2('dossier after run 2')
    expect(allResultErrors(agent2)[1]).toBe(false)
    console.log('RUN2-DOSSIER:', allResultTexts(agent2)[1])

    await handle.dispose()
    await handle2.dispose()
    rmSync(store, { recursive: true, force: true })
    rmSync(dossier, { recursive: true, force: true })
    rmSync(fixtures, { recursive: true, force: true })
    rmSync(taskRoot, { recursive: true, force: true })
  }, 600_000)
})
