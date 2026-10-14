// Backend-quoting bridge (no DSH imports; node:test-covered).
// Shells quota-free to scripts/stc_probe.py under the STC venv python.

import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { isAbsolute, resolve } from 'node:path'

const execFileAsync = promisify(execFile)

export const PROBE_TIMEOUT_MS = 30000

export interface ProbeResult {
  ok: boolean
  error?: string
  [key: string]: unknown
}

export function bundleRoot(): string {
  return resolve(new URL('.', import.meta.url).pathname, '..')
}

export function venvPython(stcRoot: string): string {
  return resolve(stcRoot, '.venv', 'bin', 'python')
}

/**
 * Backend env for spawned STC processes (`run --target stc` imports the
 * deliberate SST + prompt-kit pins). Pin-first: when both STC_SST_ROOT and
 * STC_PROMPT_KIT_ROOT are set to absolute checkouts, `<sst>/src` and
 * `<prompt-kit>` lead PYTHONPATH (ambient entries preserved after them).
 * When neither is set, the environment passes through unchanged (the e2e
 * specs provision PYTHONPATH directly). Any other combination is a
 * provisioning error — fail here with an actionable message instead of a
 * ModuleNotFoundError deep in the backend.
 */
export function backendEnv(env: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const out = { ...env, PYTHONUNBUFFERED: '1' }
  const sstRoot = (env['STC_SST_ROOT'] ?? '').trim()
  const pkRoot = (env['STC_PROMPT_KIT_ROOT'] ?? '').trim()
  if (!sstRoot && !pkRoot) return out
  if (!sstRoot || !pkRoot) {
    throw new Error(
      'stc backend misconfigured: set both STC_SST_ROOT and STC_PROMPT_KIT_ROOT ' +
        'to absolute pinned checkouts (see docs/STC-DSH-RELEASE.md)',
    )
  }
  if (!isAbsolute(sstRoot) || !isAbsolute(pkRoot)) {
    throw new Error(
      'stc backend misconfigured: STC_SST_ROOT and STC_PROMPT_KIT_ROOT must be absolute paths',
    )
  }
  const prior = (env['PYTHONPATH'] ?? '').trim()
  out['PYTHONPATH'] = [`${sstRoot}/src`, pkRoot, ...(prior ? [prior] : [])].join(':')
  return out
}

/** Run the probe. Never spawns STC runs; read-only quoting only. */
export async function runProbe(
  stcRoot: string,
  opArgs: string[],
  timeoutMs = PROBE_TIMEOUT_MS,
): Promise<ProbeResult> {
  const script = resolve(bundleRoot(), 'scripts', 'stc_probe.py')
  try {
    const { stdout } = await execFileAsync(venvPython(stcRoot), [script, ...opArgs], {
      cwd: stcRoot,
      timeout: timeoutMs,
      maxBuffer: 1024 * 1024,
      env: backendEnv(),
    })
    const parsed = JSON.parse(stdout) as ProbeResult
    if (typeof parsed.ok !== 'boolean') throw new Error('probe: bad envelope')
    return parsed
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return { ok: false, error: `probe failed: ${msg}` }
  }
}

export interface PreviewInput {
  spec: string
  mode: string
  budget?: string
  choice?: string
  task_id?: string
  exec_harness?: string
}

export function previewArgs(input: PreviewInput, backendRoot: string): string[] {
  return [
    '--op', 'outer',
    '--spec', input.spec,
    '--mode', input.mode,
    '--budget', input.budget ?? '',
    '--choice', input.choice ?? '',
    '--task-id', input.task_id ?? '',
    '--exec-harness', input.exec_harness ?? '',
    '--backend-root', backendRoot,
  ]
}
