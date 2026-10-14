// Launch-guard predicates (no DSH imports; node:test-covered).
// Mirrors the legacy console launch guards (server.py:466-616) that stay
// meaningful under DSH: typed confirmation, exec-exe checks, SIM discipline.

import { accessSync, constants } from 'node:fs'
import { isAbsolute } from 'node:path'

export const CONFIRM_PHRASE = 'RUN'
export const VALID_MODES = ['dry-run', 'manual', 'live', 'exec'] as const

export interface RunGuardInput {
  mode: string
  confirm?: string
  exec_harness?: string
  spec?: string
}

/** Returns null when the launch is allowed, else a denial reason. */
export function guardLaunch(input: RunGuardInput): string | null {
  if (!(VALID_MODES as readonly string[]).includes(input.mode)) {
    return `unknown mode ${JSON.stringify(input.mode)}`
  }
  if (input.confirm !== CONFIRM_PHRASE) {
    return `confirm must be exactly ${JSON.stringify(CONFIRM_PHRASE)}`
  }
  const exe = input.exec_harness ?? ''
  if (input.mode === 'exec') {
    if (!exe) return 'exec mode needs an executable path'
    if (!isAbsolute(exe)) return `exec path must be absolute, got ${JSON.stringify(exe)}`
    try {
      accessSync(exe, constants.X_OK)
    } catch {
      return `exec path is not executable: ${exe}`
    }
  } else if (exe) {
    return 'exec_harness is only valid in exec mode'
  }
  if (input.spec && /\\/.test(input.spec)) {
    return 'Windows-style spec paths are rejected; use a POSIX path'
  }
  return null
}
