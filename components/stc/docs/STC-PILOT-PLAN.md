# Pilot plan: 6-episode live comparison (b1 vs b2)

Status: PREPARED — no spend authorized. The single budget decision at the
end is the only gate before paid execution. Treat all pilot results as
PRELIMINARY direction, never proof of an optimal policy. b2-gated stays
explicitly PROVISIONAL (mechanics winner only) until a full eval says
otherwise; inconclusive keeps it provisional, nothing auto-promotes.

## Question (narrower than the full batch)

On small real tasks, does b2-gated (preview→typed-confirm→run→verify)
outperform b1-direct (run→verify) on verified task success, and how do
their intervention/recovery/cost profiles differ? b0-single-agent (free
tool use) answers a different question (structure vs freedom) and waits
for the full batch.

## Policies (behavioral procedures, injected as system prompt)

- **b1-direct**: "For each task: launch the work directly, then verify
  with status/log/dossier reads. Recover from failures with at most one
  retry per step."
- **b2-gated**: "For each task: first preview (argv/spec), then launch
  ONLY with typed confirmation RUN, then verify with status/log/dossier
  reads. If a gate denies, fix the cause and re-preview before retrying."
- Mechanism: `DSH_SYSTEM_PROMPT` per episode (sdk-minimal honors it);
  identical tools, model, budgets. Prompt texts frozen in
  `scripts/live-pilot.py` (POLICY_PROMPTS) and hashed into the ledger.

## Tasks (dev set; deterministic verdicts, no pixels, no ambiguity)

1. **bug-repair**: seeded failing test in a scratch repo. Verdict: the
   named test flips red→green AND ruff+pytest gates pass AND diff touches
   only the target file.
2. **new-feature**: add a CLI flag in a scratch repo. Verdict: flag works
   (CLI output), a new test covers it, gates pass.
3. **unfamiliar-docs**: docs-only edit inside the STC repo (fixed file +
   fixed insertion). Verdict: exact diff match, no other files changed,
   repo gates unaffected (fast subset: ruff on the file).
Tasks 4–6 from the full proposal (cross-module, ambiguous, visible-UI)
wait for the full batch (need design judgment, ask-user rounds, pixels).

## Harness + verdicts + stop rules

- Runner `scripts/live-pilot.py`: fresh scratch repo + fresh DSH home per
  episode, SDK-driven (sdk-minimal), per-episode ceilings (≤4000 output
  tokens/call, 15 min request timeout, paid runs need `--authorize-spend`
  + non-empty `SAIL_API_KEY`), verdict checker per task, JSONL
  spend/event ledger. Failures/timeouts count in the denominator. The SDK
  exposes no hard turn cap or mid-run cancel, so turns are bounded by
  timeout + recorded (not capped) per episode; at flash-tier prices a
  single runaway episode costs cents, and the batch aborts past 80% cap.
- Dry validation DONE (2026-09-30): `--provider scripted` ran all 6
  episodes quota-free ($0.00): mechanics green (sessions, tools, ledger,
  usage extraction, verdict checkers run and correctly fail the probe),
  both refusal gates verified (paid-without-flag, heldout-without-flag).
- Stop rules: abort a policy after 3 consecutive fault-handling failures;
  abort the batch at 80% of cap with no separation; any episode past any
  ceiling is a failed episode, not an extension.

## Model

DeepSeek `deepseek-flash` (DeepSeek-V4.1-Flash; the legacy
`deepseek-v4-flash` name is accepted but retired) via Sail
(`SAIL_API_KEY` + `https://api.sailresearch.com/v1`; Sail slug
`deepseek-ai/DeepSeek-V4.1-Flash`, default mode, key + URL verified
2026-09-30 via /models).
Rationale: cheapest tool-capable tier keeps the pilot cheap; the
procedure contrast (gating) is model-agnostic enough for a preliminary
signal. DISCLOSED LIMIT: the ranking may not transfer to reasoning
models or other vendors — the full batch must name its target tier.

## Cost arithmetic (assumptions explicit; cap is binding, estimate is not)

- Worst case per episode: ~30 turns in 15 min × ~10k avg input ≈ 300k
  input tokens; 30 × 4k output cap = 120k output tokens. (Observed
  scripted journeys use far less; this is a ceiling, not a prediction.)
- VERIFIED pricing 2026-09-30 (api-docs.deepseek.com, flash tier):
  input (cache miss) $0.30/M peak / $0.15/M off-peak; output $1.20/M
  peak / $0.60/M off-peak. Peak = 01:00–04:00 + 06:00–10:00 UTC
  weekdays. Worst case at PEAK: 300k×$0.30 + 120k×$1.20 ≈ **$0.24/
  episode** → 6 episodes ≈ **$1.44**.
- **Hard cap $5.00** (≈3.4× over peak worst-case, ≈7× off-peak).
  Runner aborts at $4.00 without separation. Off-peak halves cost;
  run timing may wait for it (next off-peak: 04:00 UTC).

## What this comparison can (and cannot) establish

CAN: a preliminary directional signal on gated-vs-direct verified
success; per-policy intervention counts, recovery behavior, token/time
cost, and failure modes; a validated runner + ledger + verdicts reusable
for the full batch.
CANNOT: prove optimality (n=3 tasks, 2 policies, 1 model tier,
coordinator-designed tasks); transfer guarantees; any claim about b0,
ambiguous/pixel/deep tasks, or live champion search (separate problem).

## Held-out (arranged independently; contamination disclosed)

- `scripts/pilot-tasks.py` generates dev tasks AND held-out twins
  (seeded variants: different names/flags/bugs/files, disjoint content)
  plus `manifest.json` with sha256 per task. The runner refuses held-out
  tasks until the confirmation phase.
- DISCLOSED LIMITS (no curator available): the same coordinator authored
  both sets, so task-FAMILY leakage is possible; twins share structure
  with dev tasks by construction. Mitigations: content disjointness
  (asserted: no shared identifiers), frozen prompts (no tuning between
  pilot and confirmation), manifest hashes (tamper-evident). Treat
  confirmation as a leakage-bounded sanity check, not a clean eval.

## THE budget decision (single ask, before any paid execution)

Approve pilot execution with: model `deepseek-ai/DeepSeek-V4.1-Flash` (Sail, default mode),
key from `SAIL_API_KEY`, hard cap **$5.00** (abort at $4.00 without
separation), per-episode ceilings above. Pricing re-verified
(2026-09-30, peak $1.44 worst-case for 6; Sail-side pricing may differ
— ledger estimates labeled accordingly). Provide the key by writing
`SAIL_API_KEY=<key>` (single line) to the repo-root `.env`
(gitignored — never committed, never echoed to logs); the runner reads
env first, then that file, and passes the key only to the SDK. On key
arrival I run the 6 episodes and report preliminary results + ledger;
any overrun risk aborts first.
