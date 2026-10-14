import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { defaultStcRoot, summarizeDossier } from './dossier-read.ts'
import { previewArgs, runProbe } from './stc-exec.ts'
import {
  dossierCall,
  dossierMeta,
  dossierResult,
  pingCall,
  pingMeta,
  pingResult,
  previewCall,
  previewMeta,
  previewResult,
} from './stc-present.ts'

type Meta = Record<string, unknown>
const metaOf = (result: unknown): Meta =>
  ((result as { meta?: unknown }).meta as Meta | undefined) ?? {}

export const name = 'stc-tools'
export const inject = ['tools']

function stcRoot(): string {
  return process.env['STC_ROOT'] ?? defaultStcRoot()
}

export function apply(ctx: Context) {
  ctx.tools.register(
    defineTool({
      name: 'stc_ping',
      description: 'Check that the STC plugin bundle is loaded and report its root.',
      parameters: {},
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            plugin: { type: 'string' },
            stc_root: { type: 'string' },
          },
        },
        render: (_args, value) => [
          { type: 'text', text: `STC bundle ok (root: ${value.stc_root})` },
        ],
        presentationMeta: (_args, value) => pingMeta(value as Meta),
      },
      async execute() {
        return { plugin: 'stc-tools', stc_root: stcRoot() }
      },
      presentCall: () => pingCall(),
      presentResult: (_args, result) => pingResult(metaOf(result)),
    }),
  )

  ctx.tools.register(
    defineTool({
      name: 'stc_dossier',
      description:
        'Read-only summary of an STC backend dossier directory ' +
        '(STATUS, outcome, reason, present files, spend totals, review head). ' +
        'Never writes. Path must resolve under STC_ROOT.',
      parameters: {
        dossier_path: {
          type: 'string',
          required: true,
          description: 'Absolute path of the dossier directory.',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            path: { type: 'string' },
            status: { type: 'string' },
            outcome: { type: 'string' },
            reason: { type: 'string' },
            files_present: { type: 'array', items: { type: 'string' } },
          },
        },
        render: (_args, value) => [
          {
            type: 'text',
            text:
              `dossier ${value.path}: STATUS=${value.status} ` +
              `outcome=${value.outcome}` +
              (value.reason ? ` reason=${value.reason}` : '') +
              ` files=[${value.files_present.join(',')}]`,
          },
        ],
        presentationMeta: (_args, value) => dossierMeta(value as Meta),
      },
      async execute(args) {
        if (typeof args.dossier_path !== 'string' || args.dossier_path.length === 0) {
          throw new Error('dossier_path must be a non-empty string')
        }
        const s = summarizeDossier(args.dossier_path, stcRoot())
        return {
          path: s.path,
          status: s.status,
          outcome: s.outcome,
          reason: s.reason ?? '',
          files_present: s.files_present,
        }
      },
      presentCall: (args) => dossierCall(args as Meta),
      presentResult: (_args, result) => dossierResult(metaOf(result)),
    }),
  )
  ctx.tools.register(
    defineTool({
      name: 'stc_preview',
      description:
        'Preview the exact backend argv for an STC run (quoted from backend ' +
        'builders via a quota-free probe; nothing is executed).',
      parameters: {
        spec: { type: 'string', required: true, description: 'Spec path.' },
        mode: { type: 'string', required: true, description: 'Run mode.' },
        budget: { type: 'string', description: 'Budget string (may be empty).' },
        choice: { type: 'string', description: 'Choice relay (may be empty).' },
        task_id: { type: 'string', description: 'Task id (may be empty).' },
        exec_harness: {
          type: 'string',
          description: 'Absolute exe path for exec mode (else empty).',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            ok: { type: 'boolean' },
            argv: { type: 'array', items: { type: 'string' } },
            cwd: { type: 'string' },
            error: { type: 'string' },
          },
        },
        render: (_args, value) =>
          value.ok
            ? [{ type: 'text', text: `argv: ${value.argv.join(' ')}\ncwd: ${value.cwd}` }]
            : [{ type: 'text', text: `preview failed: ${value.error}` }],
        presentationMeta: (_args, value) => previewMeta(value as Meta),
      },
      async execute(args) {
        const root = stcRoot()
        const res = await runProbe(
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
        if (!res.ok) {
          return { ok: false as const, argv: [], cwd: '', error: String(res.error ?? 'unknown') }
        }
        return {
          ok: true as const,
          argv: (res['argv'] as string[]) ?? [],
          cwd: String(res['cwd'] ?? ''),
          error: '',
        }
      },
      presentCall: (args) => previewCall(args as Meta),
      presentResult: (_args, result) => previewResult(metaOf(result)),
    }),
  )
  console.log('[stc-tools] registered stc_ping + stc_dossier + stc_preview')
}
