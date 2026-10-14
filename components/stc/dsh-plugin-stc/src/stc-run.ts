import { spawn, type ChildProcess } from 'node:child_process'
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { JobId, JobOutcome, JobRegistry } from '@deepseek-ai/dsh-jobs'
import { defaultStcRoot } from './dossier-read.ts'
import { backendEnv, previewArgs, runProbe } from './stc-exec.ts'
import { CONFIRM_PHRASE, guardLaunch } from './stc-guard.ts'
import {
  cancelCall,
  cancelMeta,
  cancelResult,
  logCall,
  logMeta,
  logResult,
  runCall,
  runMeta,
  runResult,
  statusCall,
  statusMeta,
  statusResult,
} from './stc-present.ts'

type Meta = Record<string, unknown>
const metaOf = (result: unknown): Meta =>
  ((result as { meta?: unknown }).meta as Meta | undefined) ?? {}
import {
  appendLog,
  attachSession,
  createRunDir,
  newRunId,
  readLogTail,
  readRecord,
  runDir,
  runExists,
  storeRoot,
  writeRecord,
} from './stc-runstore.ts'
import * as runstoreNS from './stc-runstore.ts'
import type { GenericCallView, GenericResultView } from './stc-present.ts'
import {
  findRunByJob,
  markInterrupted,
  recordContinuation,
  recover,
  redirectRun,
  resolveRunState,
} from './stc-recovery.ts'

export const name = 'stc-run'
export const inject = ['tools']

const KILL_GRACE_MS = 5000

function stcRoot(): string {
  return process.env['STC_ROOT'] ?? defaultStcRoot()
}

interface Spawned {
  child: ChildProcess
  dir: string
  outcome: Promise<JobOutcome>
  killed: { current: boolean }
}

function spawnStcRun(
  argv: string[],
  cwd: string,
  dir: string,
  onChunk: (text: string, channel: 'stdout' | 'stderr') => void,
  onProgress: (line: string) => void,
): Spawned {
  const killed = { current: false }
  const child = spawn(argv[0] as string, argv.slice(1), {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    env: backendEnv(),
  })
  const outcome = new Promise<JobOutcome>((resolve) => {
    let settled = false
    const finish = (o: JobOutcome) => {
      if (settled) return
      settled = true
      writeRecord(dir, 'exit.json', { ...o, pid: child.pid ?? null })
      resolve(o)
    }
    child.stdout?.on('data', (b: Buffer) => {
      const t = b.toString('utf8')
      appendLog(dir, t)
      onChunk(t, 'stdout')
    })
    child.stderr?.on('data', (b: Buffer) => {
      const t = b.toString('utf8')
      appendLog(dir, t)
      onChunk(t, 'stderr')
    })
    child.on('error', (err) => {
      onProgress(`spawn failed: ${err.message}`)
      finish({ status: 'failed', detail: `spawn failed: ${err.message}` })
    })
    child.on('close', (code, signal) => {
      if (killed.current || signal !== null) {
        finish({ status: 'killed', detail: signal ? `signal: ${signal}` : 'killed before exit' })
      } else {
        finish({ status: 'completed', detail: `exit code: ${code ?? 0}` })
      }
    })
  })
  onProgress(`spawned pid ${child.pid ?? 'unknown'}`)
  return { child, dir, outcome, killed }
}

function killSpawned(s: Spawned): void {
  if (s.killed.current) return
  s.killed.current = true
  try {
    s.child.kill('SIGTERM')
  } catch {
    /* already gone */
  }
  const timer = setTimeout(() => {
    try {
      if (s.child.exitCode === null) s.child.kill('SIGKILL')
    } catch {
      /* already gone */
    }
  }, KILL_GRACE_MS)
  timer.unref?.()
}

// --- recovery helpers (STC1; durable state lives in stc-recovery.ts) ---

function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

/**
 * Resolve a run id from run_id (preferred), job_id (durable run.json scan),
 * or session_id (Builder C's getBySession when it lands — feature-detected,
 * never hard-required).
 */
function resolveRunId(store: string, opts: { run_id?: string; job_id?: string; session_id?: string }): string {
  if (opts.run_id) {
    if (!runExists(store, opts.run_id)) throw new Error(`unknown run: ${opts.run_id}`)
    return opts.run_id
  }
  if (opts.job_id) return findRunByJob(store, opts.job_id)
  if (opts.session_id) {
    const fn = (runstoreNS as unknown as Record<string, unknown>)['getBySession']
    if (typeof fn !== 'function') {
      throw new Error('session_id resolution needs Builder C getBySession, which is not present; pass run_id')
    }
    // Builder C contract: getBySession(store, sessionId) -> RunRecord[]
    // (each with .runId). A session may own several runs; recovery acts on
    // exactly one, so multiples must disambiguate with run_id.
    let found: unknown
    try {
      found = (fn as (s: string, id: string) => unknown)(store, opts.session_id)
    } catch (err) {
      throw new Error(`session ${opts.session_id} resolves to no known run (${String((err as Error).message ?? err)})`)
    }
    const ids = Array.isArray(found)
      ? found
          .map((r) => str((r as Record<string, unknown> | null)?.['runId']))
          .filter((id) => id !== '' && runExists(store, id))
      : []
    if (ids.length === 1) return ids[0] as string
    if (ids.length === 0) throw new Error(`session ${opts.session_id} resolves to no known run`)
    throw new Error(`session ${opts.session_id} owns ${ids.length} runs (${ids.join(',')}); pass run_id to disambiguate`)
  }
  throw new Error('pass run_id (or job_id)')
}

/** Live-registry probe that never throws: unknown/foreign/gone jobs report gone. */
function probeJob(
  jobs: JobRegistry,
  caller: unknown,
  jobId: string | null,
): { live: boolean; jobState: string } {
  if (!jobId) return { live: false, jobState: '' }
  try {
    const view = jobs.get(jobId as JobId, caller as never)
    const status = str((view as unknown as Record<string, unknown>)['status'])
    return { live: status === 'running' || status === 'stopping', jobState: status }
  } catch {
    return { live: false, jobState: '' }
  }
}

function runJobId(store: string, runId: string): string | null {
  const run = readRecord(runDir(store, runId), 'run.json') as Record<string, unknown> | null
  const id = run ? str(run['jobId']) : ''
  return id || null
}

interface JobLaunch {
  jobs: JobRegistry
  owner: unknown
  argv: string[]
  cwd: string
  dir: string
  runId: string
  label: string
  recordBase: Record<string, unknown>
}

/** Spawn the child + register the background job; shared by stc_run and resume. */
function launchStcJob(spec: JobLaunch): string {
  const jobId = spec.jobs.start({
    kind: 'stc-run',
    label: spec.label,
    ...(spec.owner !== undefined ? { owner: spec.owner as never } : {}),
    run: (job) => {
      const s = spawnStcRun(
        spec.argv,
        spec.cwd,
        spec.dir,
        (text, channel) => job.append(text, { channel }),
        (line) => job.updateProgress(line),
      )
      writeRecord(spec.dir, 'run.json', {
        ...spec.recordBase,
        jobId: job.id,
        pid: s.child.pid ?? null,
      })
      return {
        cancel: () => killSpawned(s),
        done: s.outcome,
      }
    },
  })
  return String(jobId)
}

// Local presenters for the recovery tools (stc-present.ts is read-only).
function interruptCall(args: Meta): GenericCallView {
  return {
    card: 'generic',
    title: `Interrupt run ${str(args['run_id']) || str(args['job_id']) || '(missing run)'} @ ${str(args['checkpoint']) || '(no checkpoint)'}`,
    kind: 'other',
  }
}

function interruptResult(value: Meta): GenericResultView {
  return { card: 'generic', title: `Run ${str(value['runId']) || '?'} interrupted @ ${str(value['checkpoint']) || '?'}` }
}

function interruptMeta(value: Meta): Meta {
  return { runId: str(value['runId']), state: str(value['state']), checkpoint: str(value['checkpoint']) }
}

function recoverCall(args: Meta): GenericCallView {
  return {
    card: 'generic',
    title: `Recover run ${str(args['run_id']) || str(args['job_id']) || '(missing run)'}`,
    kind: 'execute',
  }
}

function recoverResult(value: Meta): GenericResultView {
  const d = str(value['decision'])
  return {
    card: 'generic',
    title: `Run ${str(value['runId']) || '?'} recover: ${d || '?'}`,
    content: [{ type: 'text', text: str(value['summary']) || d }],
  }
}

function recoverMeta(value: Meta): Meta {
  return {
    runId: str(value['runId']),
    decision: str(value['decision']),
    continuedBy: str(value['continuedBy']),
  }
}

function redirectCall(args: Meta): GenericCallView {
  return {
    card: 'generic',
    title: `Redirect run ${str(args['run_id']) || str(args['job_id']) || '(missing run)'} -> ${str(args['brief_ref']) || '(no brief)'}`,
    kind: 'other',
  }
}

function redirectResult(value: Meta): GenericResultView {
  return { card: 'generic', title: `Run ${str(value['runId']) || '?'} redirected -> ${str(value['briefRef']) || '?'}` }
}

function redirectMeta(value: Meta): Meta {
  return { runId: str(value['runId']), state: str(value['state']), briefRef: str(value['briefRef']) }
}

export function apply(ctx: Context) {
  ctx.inject(['jobs'], (jobCtx) => {
    const jobs = (jobCtx as unknown as { jobs: JobRegistry }).jobs

    ctx.tools.register(
      defineTool({
        name: 'stc_run',
        description:
          `Launch an STC backend run as a background job (returns a job id; ` +
          `use stc_status/stc_log to follow it). Requires confirm="${CONFIRM_PHRASE}".`,
        parameters: {
          spec: { type: 'string', required: true },
          mode: { type: 'string', required: true },
          confirm: { type: 'string', required: true },
          budget: { type: 'string' },
          choice: { type: 'string' },
          task_id: { type: 'string' },
          exec_harness: { type: 'string' },
          label: { type: 'string' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              kind: { type: 'string' },
              jobId: { type: 'string' },
              runId: { type: 'string' },
            },
          },
          render: (_args, value) => [
            { type: 'text', text: `started background job ${value.jobId} (run ${value.runId})` },
          ],
          presentationMeta: (_args, value) => runMeta(value as Meta),
        },
        async execute(args, exec) {
          const denied = guardLaunch({
            mode: args.mode,
            confirm: args.confirm,
            exec_harness: args.exec_harness,
            spec: args.spec,
          })
          if (denied) throw new Error(`stc_run denied: ${denied}`)
          const root = stcRoot()
          const quoted = await runProbe(
            root,
            previewArgs(
              {
                spec: args.spec,
                mode: args.mode,
                budget: args.budget,
                choice: args.choice,
                task_id: args.task_id,
                exec_harness: args.exec_harness,
              },
              root,
            ),
          )
          if (!quoted.ok) throw new Error(`stc_run preview failed: ${quoted.error}`)
          const argv = quoted['argv'] as string[]
          const cwd = String(quoted['cwd'] ?? root)
          const store = storeRoot()
          const runId = newRunId()
          const dir = createRunDir(store, runId)
          const label = args.label || `stc ${args.mode} ${args.spec}`
          const recordBase = {
            runId,
            argv,
            cwd,
            spec: args.spec,
            mode: args.mode,
            startedAt: new Date().toISOString(),
          }
          writeRecord(dir, 'run.json', recordBase)
          const jobId = launchStcJob({
            jobs,
            owner: exec.agent?.id,
            argv,
            cwd,
            dir,
            runId,
            label,
            recordBase,
          })
          // Auto-attach AFTER launch: launchStcJob's starter synchronously
          // rewrites run.json (recordBase + jobId/pid), which would clobber a
          // sessionId attached before it (jobs.start runs spec.run inline).
          attachSession(store, runId, { sessionId: exec.agent ? String(exec.agent.id) : undefined })
          return { kind: 'background', jobId: String(jobId), runId }
        },
        presentCall: (args) => runCall(args as Meta),
        presentResult: (_args, result) => runResult(metaOf(result)),
      }),
    )

    ctx.tools.register(
      defineTool({
        name: 'stc_status',
        description:
          'Project one STC run job (state, progress, terminal detail). ' +
          'With run_id, reports the durable run state (running/interrupted/' +
          'redirected/terminal) from the run dir — a read-only query that ' +
          'never resumes or otherwise changes the run.',
        parameters: {
          job_id: { type: 'string' },
          run_id: { type: 'string' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              jobId: { type: 'string' },
              state: { type: 'string' },
              progress: { type: 'string' },
              detail: { type: 'string' },
              runId: { type: 'string' },
            },
          },
          render: (_args, value) => [
            {
              type: 'text',
              text: `${value.jobId || value.runId}: ${value.state}${value.progress ? ` (${value.progress})` : ''}${value.detail ? ` — ${value.detail}` : ''}`,
            },
          ],
          presentationMeta: (_args, value) => statusMeta(value as Meta),
        },
        async execute(args, exec) {
          if (args.run_id) {
            const store = storeRoot()
            const runId = resolveRunId(store, { run_id: args.run_id })
            const jobId = args.job_id ?? runJobId(store, runId) ?? ''
            const probe = probeJob(jobs, exec.agent?.id, jobId || null)
            const view = resolveRunState(store, runId, probe.jobState)
            return {
              jobId,
              state: view.state,
              progress: view.checkpoint ? `checkpoint ${view.checkpoint}` : '',
              detail: view.detail,
              runId,
            }
          }
          if (!args.job_id) throw new Error('stc_status needs job_id or run_id')
          const view = jobs.get(args.job_id as JobId, exec.agent?.id)
          const v = view as unknown as Record<string, unknown>
          return {
            jobId: String(v['id'] ?? args.job_id),
            state: String(v['status'] ?? 'unknown'),
            progress: String(v['progress'] ?? ''),
            detail: String(v['detail'] ?? ''),
            runId: '',
          }
        },
        presentCall: (args) => {
          const a = args as Meta
          if (a['run_id'] && !a['job_id']) {
            return {
              card: 'generic',
              title: `Run status ${str(a['run_id'])}`,
              kind: 'fetch',
            } satisfies GenericCallView
          }
          return statusCall(a)
        },
        presentResult: (_args, result) => statusResult(metaOf(result)),
      }),
    )

    ctx.tools.register(
      defineTool({
        name: 'stc_log',
        description: 'Tail the durable console log of an STC run (by run id).',
        parameters: {
          run_id: { type: 'string', required: true },
          max_bytes: { type: 'number' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              runId: { type: 'string' },
              tail: { type: 'string' },
            },
          },
          render: (_args, value) => [{ type: 'text', text: value.tail || '(empty log)' }],
        presentationMeta: (_args, value) => logMeta(value as Meta),
        },
        async execute(args) {
          const store = storeRoot()
          if (!runExists(store, args.run_id)) throw new Error(`unknown run: ${args.run_id}`)
          return {
            runId: args.run_id,
            tail: readLogTail(runDir(store, args.run_id), args.max_bytes ?? 32768),
          }
        },
        presentCall: (args) => logCall(args as Meta),
        presentResult: (_args, result) => logResult(metaOf(result)),
      }),
    )

    ctx.tools.register(
      defineTool({
        name: 'stc_cancel',
        description: 'Cancel a running STC run job (SIGTERM, SIGKILL escalation).',
        parameters: {
          job_id: { type: 'string', required: true },
          reason: { type: 'string' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              jobId: { type: 'string' },
              result: { type: 'string' },
            },
          },
          render: (_args, value) => [{ type: 'text', text: `${value.jobId}: ${value.result}` }],
        presentationMeta: (_args, value) => cancelMeta(value as Meta),
        },
        async execute(args, exec) {
          const result = jobs.kill(args.job_id as JobId, exec.agent?.id, args.reason)
          return { jobId: args.job_id, result }
        },
        presentCall: (args) => cancelCall(args as Meta),
        presentResult: (_args, result) => cancelResult(metaOf(result)),
      }),
    )

    ctx.tools.register(
      defineTool({
        name: 'stc_interrupt',
        description:
          'Pause/interrupt an STC run at a declared checkpoint: stops the live ' +
          'job when there is one (same SIGTERM/SIGKILL path as cancel) and ' +
          'records checkpoint + identity snapshot as recovery.json. Refuses ' +
          'already-terminal runs so cancel/completion proof is never rewritten.',
        parameters: {
          run_id: { type: 'string' },
          job_id: { type: 'string' },
          checkpoint: { type: 'string', required: true },
          reason: { type: 'string' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              runId: { type: 'string' },
              state: { type: 'string' },
              checkpoint: { type: 'string' },
              jobStopped: { type: 'string' },
            },
          },
          render: (_args, value) => [
            {
              type: 'text',
              text: `${value.runId}: ${value.state} @ ${value.checkpoint} (job ${value.jobStopped})`,
            },
          ],
          presentationMeta: (_args, value) => interruptMeta(value as Meta),
        },
        async execute(args, exec) {
          const store = storeRoot()
          const runId = resolveRunId(store, { run_id: args.run_id, job_id: args.job_id })
          const jobId = args.job_id ?? runJobId(store, runId)
          let stopped = 'gone'
          if (jobId) {
            try {
              stopped = jobs.kill(
                jobId as JobId,
                exec.agent?.id,
                args.reason ?? `stc_interrupt @ ${args.checkpoint}`,
              )
            } catch {
              stopped = 'gone'
            }
          }
          const rec = markInterrupted(store, runId, {
            checkpoint: args.checkpoint,
            reason: args.reason,
            jobStopped: stopped,
          })
          return { runId, state: rec.state, checkpoint: rec.checkpoint, jobStopped: stopped }
        },
        presentCall: (args) => interruptCall(args as Meta),
        presentResult: (_args, result) => interruptResult(metaOf(result)),
      }),
    )

    ctx.tools.register(
      defineTool({
        name: 'stc_recover',
        description:
          'Recover an interrupted STC run: re-attaches when the job is still ' +
          'live, else resumes ONLY after verifying identity + side-effect ' +
          'completion (a verified resume launches a linked continuation run ' +
          'that skips completed effects). Uncertain recovery reports ' +
          'needs-decision with evidence and launches nothing.',
        parameters: {
          run_id: { type: 'string' },
          job_id: { type: 'string' },
          session_id: { type: 'string' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              runId: { type: 'string' },
              decision: { type: 'string' },
              summary: { type: 'string' },
              continuedBy: { type: 'string' },
              jobId: { type: 'string' },
            },
          },
          render: (_args, value) => [
            {
              type: 'text',
              text: `${value.runId}: ${value.decision}${value.continuedBy ? ` -> ${value.continuedBy}` : ''}\n${value.summary}`,
            },
          ],
          presentationMeta: (_args, value) => recoverMeta(value as Meta),
        },
        async execute(args, exec) {
          const store = storeRoot()
          const runId = resolveRunId(store, {
            run_id: args.run_id,
            job_id: args.job_id,
            session_id: args.session_id,
          })
          const jobId = args.job_id ?? runJobId(store, runId)
          const probe = probeJob(jobs, exec.agent?.id, jobId)
          const outcome = recover(store, runId, {
            probe: () => (probe.live ? 'live' : 'gone'),
          })
          if (outcome.decision === 'resumed') {
            const plan = outcome.resumePlan
            const newId = newRunId()
            const dir = createRunDir(store, newId)
            const recordBase = {
              runId: newId,
              argv: plan.argv,
              cwd: plan.cwd,
              spec: plan.spec,
              mode: plan.mode,
              startedAt: new Date().toISOString(),
              resumedFrom: plan.resumedFrom,
              resumeSkip: plan.skip,
            }
            writeRecord(dir, 'run.json', recordBase)
            const newJob = launchStcJob({
              jobs,
              owner: exec.agent?.id,
              argv: plan.argv,
              cwd: plan.cwd,
              dir,
              runId: newId,
              label: `stc resume ${plan.mode} ${plan.spec} (from ${plan.resumedFrom})`,
              recordBase,
            })
            recordContinuation(store, runId, newId)
            return {
              runId,
              decision: 'resumed',
              summary: [...outcome.evidence, `continuation run ${newId} (job ${newJob}) skips [${plan.skip.join(',')}]`].join('\n'),
              continuedBy: newId,
              jobId: newJob,
            }
          }
          if (outcome.decision === 'reattached') {
            return {
              runId,
              decision: 'reattached',
              summary: outcome.evidence.join('\n'),
              continuedBy: '',
              jobId: jobId ?? '',
            }
          }
          if (outcome.decision === 'needs-decision') {
            return {
              runId,
              decision: 'needs-decision',
              summary: [...outcome.blockers, ...outcome.evidence].join('\n'),
              continuedBy: '',
              jobId: jobId ?? '',
            }
          }
          if (outcome.decision === 'refused-redirected') {
            return {
              runId,
              decision: 'refused-redirected',
              summary: outcome.evidence.join('\n'),
              continuedBy: '',
              jobId: jobId ?? '',
            }
          }
          return {
            runId,
            decision: 'already-terminal',
            summary: outcome.evidence.join('\n'),
            continuedBy: '',
            jobId: jobId ?? '',
          }
        },
        presentCall: (args) => recoverCall(args as Meta),
        presentResult: (_args, result) => recoverResult(metaOf(result)),
      }),
    )

    ctx.tools.register(
      defineTool({
        name: 'stc_redirect',
        description:
          'Redirect an STC run to a new brief: stops the live job when there ' +
          'is one and terminally invalidates pending work in recovery.json. ' +
          'Recovery after redirect is refused; start a new run under the new brief.',
        parameters: {
          run_id: { type: 'string' },
          job_id: { type: 'string' },
          brief_ref: { type: 'string', required: true },
          reason: { type: 'string' },
        },
        output: {
          schema: {
            type: 'object',
            additionalProperties: false,
            properties: {
              runId: { type: 'string' },
              state: { type: 'string' },
              briefRef: { type: 'string' },
              invalidated: { type: 'string' },
              jobStopped: { type: 'string' },
            },
          },
          render: (_args, value) => [
            {
              type: 'text',
              text: `${value.runId}: ${value.state} -> ${value.briefRef} (invalidated [${value.invalidated}], job ${value.jobStopped})`,
            },
          ],
          presentationMeta: (_args, value) => redirectMeta(value as Meta),
        },
        async execute(args, exec) {
          const store = storeRoot()
          const runId = resolveRunId(store, { run_id: args.run_id, job_id: args.job_id })
          const jobId = args.job_id ?? runJobId(store, runId)
          let stopped = 'gone'
          if (jobId) {
            try {
              stopped = jobs.kill(
                jobId as JobId,
                exec.agent?.id,
                args.reason ?? `stc_redirect -> ${args.brief_ref}`,
              )
            } catch {
              stopped = 'gone'
            }
          }
          const rec = redirectRun(store, runId, {
            briefRef: args.brief_ref,
            reason: args.reason,
            jobStopped: stopped,
          })
          return {
            runId,
            state: rec.state,
            briefRef: rec.redirect?.briefRef ?? '',
            invalidated: (rec.redirect?.invalidated ?? []).join(','),
            jobStopped: stopped,
          }
        },
        presentCall: (args) => redirectCall(args as Meta),
        presentResult: (_args, result) => redirectResult(metaOf(result)),
      }),
    )
    console.log(
      '[stc-run] registered stc_run + stc_status + stc_log + stc_cancel + stc_interrupt + stc_recover + stc_redirect',
    )
  })
}
