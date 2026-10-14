# Live-model qualification — 2026-10-04 (SAIL Research)

Real model-generated search with meaningful acceptance checks and budget
evidence. Both attempts preserved with warts in
`docs/evidence/live-qual-2026-10-04/` (secret-free: key traveled via
environment only and was never printed, logged, or committed).

- Provider: SAIL Research, `https://api.sailresearch.com/v1`
  (OpenAI-compatible), model `deepseek-ai/DeepSeek-V4.1-Flash`.
- Auth: `SAIL_API_KEY` from untracked git-ignored `.env`, mapped at runtime
  to `OPENAI_API_KEY` with `OPENAI_BASE_URL` + `SST_MODEL` overrides.
- Probe: HTTP 200, `PROBE-OK`, real usage tokens (38 prompt / 31 completion).
- Task: fix `mul` in `math_mod.py` (`a + b` bug); acceptance `test_math.py`
  asserts `mul(3,4)==12`, `mul(0,5)==0`, `mul(-2,3)==-6`.
- Harness: `live_qual.py` — real `ModelGateway` (no stubs), real
  `SSTSearchController`, real custody, real acceptance, real budget tracking.

## Attempt 1 — `no_candidate` (kept as failure evidence)

Role defaults (diverge 2048) vs a reasoning model: ~2.4k tokens went to
chain-of-thought, the response came back `content: null`, and the gateway
stringified it into a literal `"None"` patch. All 3 candidates failed
acceptance honestly (`ImportError`, exit 1). Observed: 7,574 real tokens,
0 provider errors, 74.4s wall. See `run1-envelope.json`, `run1.stdout`,
`diverge-prompt.txt`.

## Fix (landed, defaults unchanged)

- `SearchPolicy.response_max_tokens`: per-request override for all roles
  (`None` keeps 2048/2048/2048/1024); CLI flag `--response-max-tokens`.
- Gateway maps null content to `""` (OpenAI-compatible + Ollama paths),
  never the literal `"None"`.
- Durable tests: `tests/unit/test_gateway.py` + override/default tests in
  `tests/unit/test_controller.py`.

## Attempt 2 — `CHAMPION_FOUND` (with `response_max_tokens=8192`)

Model-generated `def mul(a, b): return a * b` ("Direct Infix Primitive").
All 6 alternatives passed real acceptance (exit 0) with live `APPROVE`
critiques; 26,181 real tokens tracked in budget; 0 provider errors. See
`run2-envelope.json`, `run2.stdout`.

Provenance note: `run2.stderr` ends in a probe-script-only `AttributeError`
(`ScoreBreakdown` has no `value_score` attribute name the print statement
guessed). It fired after the envelope was saved; the envelope is complete
and the product code is unaffected.

## Budget honesty

26,181 tokens are observed usage. `cost_usd=0.0` in these envelopes does
NOT establish dollar spend: no USD pricing was configured, so dollar cost
was unknown. The release now enforces this honestly:

- `ProviderProfile` carries optional `input/output_usd_per_1k_tokens`;
  `GatewayResponse.cost_known` flags valid accounting (TEST fixture: $0
  known; unpriced live profiles: unknown, not zero).
- `SearchPolicy.max_cost_usd` defaults to `None` (the old $10 default was
  never enforced). A set USD cap with unpriced responses raises
  `UnpricedCostBudgetError` instead of running an unenforceable budget.

SAIL rates for this model were not available, so no dollar figure is
claimed. USD-cap enforcement is qualified by unit test with synthetic
rates, not by this run.
