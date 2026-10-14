// Packaging contract guards (no DSH imports; node:test-covered).
//
// Regression tests for the two release-blocking defects the independent
// auditor found (2026-09-29):
//  - G1: packaged installs shipped .ts entries, which Node refuses to
//    type-strip under node_modules -> rows never activated.
//  - G2: five loader rows for one package trip DSH client-modules'
//    single-source guard -> web startup fails.
// The contract: exactly one loader row, one compiled JS entry, client key
// matching the row id.
import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const read = (rel: string): string => readFileSync(resolve(ROOT, rel), 'utf8')

function rowIds(yaml: string): string[] {
  return yaml
    .split('\n')
    .map((l) => l.match(/^\s*-\s+id:\s+(\S+)\s*$/))
    .filter((m) => m !== null)
    .map((m) => (m as RegExpMatchArray)[1] as string)
}

describe('packaging contract', () => {
  it('release bundle mounts exactly one loader row', () => {
    const ids = rowIds(read('cordis.bundle.yml'))
    assert.equal(ids.length, 1, `expected 1 row, got ${JSON.stringify(ids)} (G2)`)
  })

  it('package entry is compiled JS, never TS under node_modules', () => {
    const pkg = JSON.parse(read('package.json')) as {
      main: string
      exports: Record<string, string>
    }
    assert.match(pkg.main, /\.js$/, `main must be JS (G1): ${pkg.main}`)
    assert.ok(!pkg.main.includes('.ts'), `main must not be TS (G1): ${pkg.main}`)
    for (const [key, target] of Object.entries(pkg.exports)) {
      if (key === './package.json') continue
      assert.ok(
        !target.endsWith('.ts'),
        `export ${key} must not point at TS (G1): ${target}`,
      )
    }
    const subpaths = Object.keys(pkg.exports).filter(
      (k) => k !== '.' && k !== './client' && k !== './package.json',
    )
    assert.deepEqual(subpaths, [], `no subpath rows allowed (G2): ${subpaths}`)
  })

  it('client row.config key matches the single bundle row id', () => {
    const ids = rowIds(read('cordis.bundle.yml'))
    const client = read('client.js')
    const m = client.match(/key:\s*'(@[^'#]+)#([^'#]+)'/)
    assert.ok(m, 'client.js must register a plugins.row.config key')
    assert.ok(
      ids.includes(m[2] as string),
      `client key row ${m[2]} must be the bundle row ${JSON.stringify(ids)}`,
    )
  })

  it('built bundle (when present) is self-contained JS with host-only externals', () => {
    const lib = resolve(ROOT, 'lib', 'index.js')
    if (!existsSync(lib)) {
      console.log('    # skip: lib/index.js absent (run pnpm build first)')
      return
    }
    const js = readFileSync(lib, 'utf8')
    assert.ok(js.includes('stc-bundle'), 'bundle must contain the stc-bundle entry')
    assert.ok(js.includes('stc_ping'), 'bundle must contain the tool registrations')
    // Line-anchored: esbuild emits one import statement per line; a bare
    // /from\s*['"]/ also matches English prose inside string literals
    // (e.g. recovery copy "resume from\n  ...").
    const imports = [...js.matchAll(/^import\s.*?from\s*["']([^"']+)["']/gm)].map((m) => m[1])
    const bad = imports.filter(
      (s) => !(s as string).startsWith('node:') && !(s as string).startsWith('@deepseek-ai/'),
    )
    assert.deepEqual(bad, [], `bundle externals must be host-only: ${bad}`)
    assert.ok(!js.includes("from './") && !js.includes('from "./'), 'bundle must not keep relative imports')
  })
})
