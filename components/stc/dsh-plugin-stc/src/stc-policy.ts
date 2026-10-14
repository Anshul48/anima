import type { Context } from '@deepseek-ai/cordis'
import { guardLaunch } from './stc-guard.ts'

export const name = 'stc-policy'

/**
 * Waterfall policy for STC tools. Guards stc_run launches (typed confirm,
 * exec-exe checks, mode allowlist) at the dispatch layer, so even a
 * compromised prompt-injection path cannot bypass the launch contract.
 * Allowlists STC read tools unconditionally; defers to other policy for
 * non-STC tools via next().
 */
export function apply(ctx: Context) {
  ctx.on('tools/pre-execute', async (exec: unknown, next: unknown) => {
    const e = exec as { name: string; arguments: Record<string, unknown> }
    const nxt = next as () => Promise<unknown>
    if (e.name === 'stc_run') {
      const denied = guardLaunch({
        mode: String(e.arguments['mode'] ?? ''),
        confirm: e.arguments['confirm'] as string | undefined,
        exec_harness: e.arguments['exec_harness'] as string | undefined,
        spec: e.arguments['spec'] as string | undefined,
      })
      if (denied) return { kind: 'deny', reason: `stc policy: ${denied}` }
      return nxt()
    }
    if (
      e.name === 'stc_ping' ||
      e.name === 'stc_dossier' ||
      e.name === 'stc_preview' ||
      e.name === 'stc_status' ||
      e.name === 'stc_log'
    ) {
      return nxt()
    }
    if (e.name === 'stc_cancel') {
      return nxt()
    }
    return nxt()
  })
  console.log('[stc-policy] pre-execute gate mounted')
}
