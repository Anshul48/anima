import type { Context } from '@deepseek-ai/cordis'

export const name = 'stc-hello'
export const inject: string[] = []

export function apply(ctx: Context) {
  void ctx
  console.log('[stc-hello] STC bundle entry loaded')
}
