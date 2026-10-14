// Theororacle: authoritative scorer for delivery-policy episodes.
// Verified success first; failures, timeouts, and regressions stay in the
// denominator. Efficiency only breaks ties. Pure logic, node:test-covered.

export interface EpisodeResult {
  policy: string
  task: string
  /** The episode reached its declared terminal condition. */
  completed: boolean
  /** Required evidence artifacts were all present and well-formed. */
  evidenceComplete: boolean
  /** Existing checks that regressed during the episode. */
  regressions: number
  /** Faults injected (bad confirm, mid-run kill, missing dossier...). */
  faultsInjected: number
  /** Injected faults handled per protocol (denied/killed/reported). */
  faultsRecovered: number
  /** Model/tool round trips consumed. */
  toolCalls: number
  /** Wall ms. */
  durationMs: number
  /** True when the run timed out (counts as failure). */
  timedOut: boolean
}

export interface PolicyScore {
  policy: string
  episodes: number
  /** Mean verified success; every episode counts, failures included. */
  successRate: number
  /** Mean fault-recovery rate over episodes with injected faults. */
  recoveryRate: number | null
  /** Mean tool calls over successful episodes (tiebreak; lower better). */
  meanToolCallsOnSuccess: number | null
  /** Mean duration over successful episodes (tiebreak; lower better). */
  meanDurationMsOnSuccess: number | null
  failures: string[]
}

function verified(ep: EpisodeResult): boolean {
  return ep.completed && ep.evidenceComplete && ep.regressions === 0 && !ep.timedOut
}

/** Score one policy's episodes. Throws on empty input (no silent vacuity). */
export function scorePolicy(policy: string, episodes: EpisodeResult[]): PolicyScore {
  const mine = episodes.filter((e) => e.policy === policy)
  if (mine.length === 0) throw new Error(`theoracle: no episodes for policy ${JSON.stringify(policy)}`)
  const ok = mine.filter(verified)
  const faulted = mine.filter((e) => e.faultsInjected > 0)
  const failures = mine.filter((e) => !verified(e)).map((e) => e.task)
  return {
    policy,
    episodes: mine.length,
    successRate: ok.length / mine.length,
    recoveryRate:
      faulted.length === 0
        ? null
        : faulted.reduce((s, e) => s + e.faultsRecovered / e.faultsInjected, 0) / faulted.length,
    meanToolCallsOnSuccess:
      ok.length === 0 ? null : ok.reduce((s, e) => s + e.toolCalls, 0) / ok.length,
    meanDurationMsOnSuccess:
      ok.length === 0 ? null : ok.reduce((s, e) => s + e.durationMs, 0) / ok.length,
    failures,
  }
}

/**
 * Compare candidates against a baseline. Returns the winner id, or null when
 * nothing beats the baseline (keep the baseline on inconclusive — ties lose).
 * Ordering: higher successRate, then higher recoveryRate (null sorts last),
 * then fewer mean tool calls, then shorter mean duration.
 */
export function selectWinner(baseline: PolicyScore, candidates: PolicyScore[]): string | null {
  const better = (a: PolicyScore, b: PolicyScore): boolean => {
    if (a.successRate !== b.successRate) return a.successRate > b.successRate
    const ar = a.recoveryRate ?? -1
    const br = b.recoveryRate ?? -1
    if (ar !== br) return ar > br
    const at = a.meanToolCallsOnSuccess ?? Number.POSITIVE_INFINITY
    const bt = b.meanToolCallsOnSuccess ?? Number.POSITIVE_INFINITY
    if (at !== bt) return at < bt
    const ad = a.meanDurationMsOnSuccess ?? Number.POSITIVE_INFINITY
    const bd = b.meanDurationMsOnSuccess ?? Number.POSITIVE_INFINITY
    return ad < bd
  }
  let best: PolicyScore | null = null
  for (const c of candidates) {
    if (better(c, baseline) && (best === null || better(c, best))) best = c
  }
  return best?.policy ?? null
}
