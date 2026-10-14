// Theororacle CLI: score episode JSONL and select a winner vs a baseline.
// Usage: node policy/score.ts <results.jsonl> <baseline-policy-id>
// Prints JSON {scores, winner} to stdout. Exit 2 on misuse.

import { readFileSync } from 'node:fs'
import { scorePolicy, selectWinner } from './theoracle.ts'
import type { EpisodeResult } from './theoracle.ts'

const [file, baselineId] = process.argv.slice(2)
if (!file || !baselineId) {
  console.error('usage: node policy/score.ts <results.jsonl> <baseline-policy-id>')
  process.exit(2)
}
const episodes = readFileSync(file, 'utf8')
  .split('\n')
  .filter((l) => l.trim() !== '')
  .map((l) => JSON.parse(l) as EpisodeResult)
const policies = [...new Set(episodes.map((e) => e.policy))]
const scores = policies.map((p) => scorePolicy(p, episodes))
const baseline = scores.find((s) => s.policy === baselineId)
if (!baseline) {
  console.error(`baseline policy ${JSON.stringify(baselineId)} has no episodes`)
  process.exit(2)
}
const winner = selectWinner(baseline, scores.filter((s) => s.policy !== baselineId))
console.log(JSON.stringify({ scores, winner }, null, 2))
