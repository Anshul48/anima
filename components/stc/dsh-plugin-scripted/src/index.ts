import type { Context } from '@deepseek-ai/cordis'
import { LlmAdapter } from '@deepseek-ai/dsh-llm'
import { readFileSync } from 'node:fs'

export const name = 'stc-scripted-provider'
export const inject: string[] = ['llm']

type Block = { text: string } | { toolCall: { id: string; name: string; args: unknown } }
interface Turn {
  blocks: Block[]
  finish: 'stop' | 'tool-calls'
}

/**
 * Scripted LLM adapter (TEST FIXTURE). Serves turns from the JSON array at
 * STC_SCRIPT_FILE, one entry per model call, then throws loudly on
 * exhaustion (same contract as the agent-loop MockAdapter). Every turn in
 * the script is a coordinator-authored decision — label runs using this
 * provider as coordinator-assisted, zero-model-call execution.
 */
class ScriptedAdapter extends LlmAdapter {
  private readonly script: Turn[]
  readonly requests: unknown[] = []

  constructor(script: Turn[]) {
    super()
    this.script = [...script]
  }

  override resolveModel(provider: string, model: string): Promise<Record<string, unknown>> {
    return Promise.resolve({ provider, id: model, name: model })
  }

  override async *stream(options: unknown): AsyncIterable<Record<string, unknown>> {
    this.requests.push(options)
    const turn = this.script.shift()
    if (!turn) throw new Error('ScriptedAdapter: script exhausted')
    let index = 0
    for (const block of turn.blocks) {
      if ('text' in block) {
        yield { type: 'block-start', index, blockType: 'text' }
        yield { type: 'text-delta', index, text: block.text }
        yield { type: 'block-end', index, block: { type: 'text', text: block.text } }
      } else {
        const argsJson = JSON.stringify(block.toolCall.args)
        yield { type: 'block-start', index, blockType: 'tool-call' }
        yield {
          type: 'tool-call-delta',
          index,
          id: block.toolCall.id,
          name: block.toolCall.name,
          argumentsDelta: argsJson.slice(0, 5),
        }
        yield { type: 'tool-call-delta', index, id: block.toolCall.id, argumentsDelta: argsJson.slice(5) }
        yield {
          type: 'block-end',
          index,
          block: { type: 'tool-call', id: block.toolCall.id, name: block.toolCall.name, arguments: argsJson },
        }
      }
      index += 1
    }
    yield { type: 'usage', usage: { inputTokens: 10, outputTokens: 5 } }
    yield { type: 'finish', reason: { kind: turn.finish } }
  }
}

export function apply(ctx: Context) {
  const path = process.env['STC_SCRIPT_FILE']
  if (!path) throw new Error('STC_SCRIPT_FILE env is required (scripted provider fixture)')
  const script = JSON.parse(readFileSync(path, 'utf8')) as Turn[]
  ctx.llm.registerAdapter(['scripted'], new ScriptedAdapter(script))
  console.log(`[stc-scripted] serving ${script.length} scripted turns from ${path}`)
}
