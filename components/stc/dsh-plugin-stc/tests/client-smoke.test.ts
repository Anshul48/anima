// Browser-face logic smoke (no DSH/browser needed; node:test-covered).
//
// Executes the real client.js with stubbed loader/React/slots and asserts
// what it registers and what its renderers return. This verifies client
// LOGIC (registration, locale copy, render trees, subject gating); pixels,
// layout, and live mounting still need a real browser (see walkthrough).
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

interface El {
  type: string
  props: Record<string, unknown>
  children: unknown[]
}

function loadClient() {
  const created: El[] = []
  const React = {
    createElement: (type: string, props: Record<string, unknown> | null, ...children: unknown[]): El => {
      const el: El = { type, props: props ?? {}, children }
      created.push(el)
      return el
    },
  }
  const locales: Record<string, Record<string, Record<string, string>>> = {}
  const registrants: Array<{ meta: Record<string, unknown>; render: (...a: never[]) => unknown }> = []
  let captured: { id: string; factory: (r: (n: string) => unknown) => unknown } | null = null
  const sandbox = {
    window: { __ModuleLoader__: { load: (m: typeof captured) => { captured = m } } },
    console,
  }
  vm.createContext(sandbox)
  vm.runInContext(readFileSync(resolve(ROOT, 'client.js'), 'utf8'), sandbox, { filename: 'client.js' })
  assert.ok(captured, 'client.js must call __ModuleLoader__.load')
  const plugin = (
    captured as unknown as {
      factory: (r: (n: string) => unknown) => { inject: string[]; apply: (c: unknown) => void }
    }
  ).factory((name: string) => {
    if (name === 'react') return React
    throw new Error(`unexpected require(${name})`)
  })
  const ctx = {
    effect: (fn: () => unknown) => {
      fn()
      return () => {}
    },
    locale: {
      register: (ns: string, dict: Record<string, Record<string, string>>) => {
        locales[ns] = dict
      },
    },
    slots: {
      inject: (_name: string, fn: () => unknown) => {
        fn()
      },
      register: (meta: Record<string, unknown>, render: (...a: never[]) => unknown) => {
        registrants.push({ meta, render })
        return {}
      },
    },
  }
  plugin.apply(ctx)
  return { plugin, locales, registrants, created }
}

describe('client face logic', () => {
  it('registers locale + two slot contributors', () => {
    const { plugin, locales, registrants } = loadClient()
    assert.deepEqual([...plugin.inject], ['slots', 'locale'])
    assert.ok(locales['stcBundle'], 'stcBundle locale registered')
    assert.ok(locales['stcBundle']?.['en']?.['section'])
    assert.ok(locales['stcBundle']?.['zh']?.['section'])
    const names = registrants.map((r) => r.meta['name'])
    assert.ok(names.includes('plugins.detail.section'))
    assert.ok(names.includes('plugins.row.config'))
  })

  it('detail section renders for STC subjects, null otherwise', () => {
    const { locales, registrants } = loadClient()
    const reg = registrants.find((r) => r.meta['name'] === 'plugins.detail.section')
    assert.ok(reg)
    const t = (k: string): string => locales['stcBundle']?.['en']?.[k] ?? k
    const render = reg.render as unknown as (p: {
      t: (k: string) => string
      subject: unknown
    }) => El | null
    const mine = { kind: 'row', pkg: { name: '@stc/dsh-plugin-stc' } }
    const el = render({ t, subject: mine })
    assert.ok(el && typeof el === 'object')
    assert.equal(el.type, 'section')
    assert.equal(el.props['data-stc-section'], 'row')
    assert.ok(String(el.props['aria-label']).length > 0)
    const kids = el.children as El[]
    assert.equal(kids[0]?.type, 'h4')
    assert.equal(kids[1]?.type, 'p')
    const foreign = { kind: 'row', pkg: { name: '@other/pkg' } }
    assert.equal(render({ t, subject: foreign }), null)
  })

  it('row config renders summary string and config page', () => {
    const { locales, registrants } = loadClient()
    const reg = registrants.find((r) => r.meta['name'] === 'plugins.row.config')
    assert.ok(reg)
    assert.equal(reg.meta['key'], '@stc/dsh-plugin-stc#stc-bundle')
    const t = (k: string): string => locales['stcBundle']?.['en']?.[k] ?? k
    const render = reg.render as unknown as (p: { t: (k: string) => string; view: string }) => unknown
    const summary = render({ t, view: 'summary' })
    assert.equal(typeof summary, 'string')
    assert.ok((summary as string).length > 0)
    const page = render({ t, view: 'page' }) as El
    assert.equal(page.type, 'div')
    assert.ok('data-stc-config' in page.props)
  })
})
