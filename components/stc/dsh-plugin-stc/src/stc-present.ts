// Tool presentation cards (no DSH imports; node:test-covered).
// Pure presenters for the DSH card vocabulary (`GenericCallView` /
// `GenericResultView` in @deepseek-ai/dsh-tools presentation): pending
// titles, completed titles + reformatted content, and replay-safe
// `presentationMeta` payloads persisted on tool/result events. The
// existing tool node renders these — no custom node kinds, no custom
// session events, no client changes.

export interface TextBlock {
  type: 'text'
  text: string
}

export type ToolCallKind =
  | 'read'
  | 'edit'
  | 'delete'
  | 'move'
  | 'search'
  | 'execute'
  | 'fetch'
  | 'other'

export interface GenericCallView {
  card: 'generic'
  title: string
  kind?: ToolCallKind
  rawInput?: unknown
  content?: TextBlock[]
  locations?: Array<{ path: string; line?: number }>
}

export interface GenericResultView {
  card: 'generic'
  title?: string
  content?: TextBlock[]
}

const text = (t: string): TextBlock => ({ type: 'text', text: t })

function str(v: unknown, fallback = ''): string {
  return typeof v === 'string' ? v : fallback
}

/** Non-empty lines joined; drops empties so cards stay tight. */
function lines(...parts: Array<string | undefined | null | false>): string {
  return parts.filter((p): p is string => typeof p === 'string' && p.length > 0).join('\n')
}

export interface ToolResultLike {
  isError?: boolean
  content?: unknown
  meta?: unknown
}

// --- stc_ping ---

export function pingCall(): GenericCallView {
  return { card: 'generic', title: 'Ping STC bundle', kind: 'fetch' }
}

export function pingResult(value: Record<string, unknown>): GenericResultView {
  return {
    card: 'generic',
    title: `STC bundle ok (${str(value['stc_root']) || 'unknown root'})`,
  }
}

export function pingMeta(value: Record<string, unknown>): Record<string, unknown> {
  return { stc_root: str(value['stc_root']) }
}

// --- stc_dossier (the evidence card) ---

export function dossierCall(args: Record<string, unknown>): GenericCallView {
  const p = str(args['dossier_path'])
  return {
    card: 'generic',
    title: `Dossier ${p || '(missing path)'}`,
    kind: 'read',
    ...(p ? { locations: [{ path: p }] } : {}),
  }
}

export function dossierResult(value: Record<string, unknown>): GenericResultView {
  const status = str(value['status'])
  const outcome = str(value['outcome'])
  const reason = str(value['reason'])
  const files = Array.isArray(value['files_present'])
    ? (value['files_present'] as unknown[]).filter((f): f is string => typeof f === 'string')
    : []
  return {
    card: 'generic',
    title: `Dossier: ${status || '?'} / ${outcome || '?'}`,
    content: [
      text(
        lines(
          `path: ${str(value['path'])}`,
          reason && `reason: ${reason}`,
          files.length > 0 && `files: ${files.join(', ')}`,
        ),
      ),
    ],
  }
}

export function dossierMeta(value: Record<string, unknown>): Record<string, unknown> {
  return {
    path: str(value['path']),
    status: str(value['status']),
    outcome: str(value['outcome']),
    reason: str(value['reason']),
    files_present: Array.isArray(value['files_present']) ? value['files_present'] : [],
  }
}

// --- stc_preview ---

export function previewCall(args: Record<string, unknown>): GenericCallView {
  return {
    card: 'generic',
    title: `Preview ${str(args['spec']) || '(missing spec)'} (${str(args['mode']) || '?'})`,
    kind: 'read',
  }
}

export function previewResult(value: Record<string, unknown>): GenericResultView {
  if (value['ok'] !== true) {
    return {
      card: 'generic',
      title: 'Preview failed',
      content: [text(str(value['error']) || 'unknown error')],
    }
  }
  const argv = Array.isArray(value['argv'])
    ? (value['argv'] as unknown[]).filter((a): a is string => typeof a === 'string')
    : []
  return {
    card: 'generic',
    title: 'Preview ready',
    content: [text(lines(`argv: ${argv.join(' ')}`, `cwd: ${str(value['cwd'])}`))],
  }
}

export function previewMeta(value: Record<string, unknown>): Record<string, unknown> {
  return {
    ok: value['ok'] === true,
    argv: Array.isArray(value['argv']) ? value['argv'] : [],
    cwd: str(value['cwd']),
    error: str(value['error']),
  }
}

// --- stc_run ---

export function runCall(args: Record<string, unknown>): GenericCallView {
  return {
    card: 'generic',
    title: `Launch STC ${str(args['mode']) || '?'} run: ${str(args['spec']) || '(missing spec)'}`,
    kind: 'execute',
    rawInput: { spec: str(args['spec']), mode: str(args['mode']) },
  }
}

export function runResult(value: Record<string, unknown>): GenericResultView {
  return {
    card: 'generic',
    title: `Run ${str(value['runId']) || '?'} launched (${str(value['jobId']) || '?'})`,
  }
}

export function runMeta(value: Record<string, unknown>): Record<string, unknown> {
  return { kind: str(value['kind']), jobId: str(value['jobId']), runId: str(value['runId']) }
}

// --- stc_status ---

export function statusCall(args: Record<string, unknown>): GenericCallView {
  return { card: 'generic', title: `Status ${str(args['job_id']) || '(missing job)'}`, kind: 'fetch' }
}

export function statusResult(value: Record<string, unknown>): GenericResultView {
  const state = str(value['state'])
  const progress = str(value['progress'])
  const detail = str(value['detail'])
  return {
    card: 'generic',
    title: `${str(value['jobId']) || '?'}: ${state || '?'}`,
    content: [text(lines(progress && `progress: ${progress}`, detail && `detail: ${detail}`))],
  }
}

export function statusMeta(value: Record<string, unknown>): Record<string, unknown> {
  return {
    jobId: str(value['jobId']),
    state: str(value['state']),
    progress: str(value['progress']),
    detail: str(value['detail']),
  }
}

// --- stc_log ---

export function logCall(args: Record<string, unknown>): GenericCallView {
  return { card: 'generic', title: `Log run ${str(args['run_id']) || '(missing run)'}`, kind: 'read' }
}

export function logResult(value: Record<string, unknown>): GenericResultView {
  return {
    card: 'generic',
    title: `Run ${str(value['runId']) || '?'} log`,
    content: [text(str(value['tail']) || '(empty log)')],
  }
}

export function logMeta(value: Record<string, unknown>): Record<string, unknown> {
  return { runId: str(value['runId']), bytes: str(value['tail']).length }
}

// --- stc_cancel ---

export function cancelCall(args: Record<string, unknown>): GenericCallView {
  return {
    card: 'generic',
    title: `Cancel ${str(args['job_id']) || '(missing job)'}`,
    kind: 'other',
  }
}

export function cancelResult(value: Record<string, unknown>): GenericResultView {
  return { card: 'generic', title: `${str(value['jobId']) || '?'}: ${str(value['result']) || '?'}` }
}

export function cancelMeta(value: Record<string, unknown>): Record<string, unknown> {
  return { jobId: str(value['jobId']), result: str(value['result']) }
}
