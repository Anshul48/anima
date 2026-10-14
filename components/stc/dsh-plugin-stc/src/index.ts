import type { Context } from '@deepseek-ai/cordis'
import * as hello from './hello.ts'
import * as policy from './stc-policy.ts'
import * as run from './stc-run.ts'
import * as tools from './stc-tools.ts'

/**
 * Single loader entry for @stc/dsh-plugin-stc.
 *
 * DSH's client-modules registry allows exactly ONE active loader row per
 * package (`reconcilePackage` throws on multiple sources), and Node refuses
 * to type-strip `.ts` under `node_modules` — so packaged installs must ship
 * one compiled JS entry. This module is that entry: it composes the four
 * internal plugins as Cordis fibers (each keeps its own `name`/`inject`),
 * and the release bundle + dev overlay each mount exactly this row.
 */
export const name = 'stc-bundle'

export function apply(ctx: Context) {
  ctx.plugin(hello)
  ctx.plugin(tools)
  ctx.plugin(run)
  ctx.plugin(policy)
  console.log('[stc-bundle] STC bundle composed (hello + tools + run + policy)')
}
