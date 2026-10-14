# SST -> STC handoff (candidate cand-02, 2026-10-04)

SST-side preparation + disposable-caller validation. No STC file is touched by
this pack; STC actions below are proposals for the STC owner.

## Proposed contract (additive, backward compatible)

- `execute_search(tree_id)` UNCHANGED. `run_search(tree_id) -> SearchResult`
  recommended: termination, champion, alternatives, budget, provider errors,
  gateway bindings, event-log ref.
- `report_outcome(...)`: verdicts verbatim, never authoritative.
- `get_search_result`: rebuilds from log; `IncompleteSearchError` when unfinished.

## Behavior changes since pin 079f4de (validated in disposable env)

STC HEAD 851e4a4 (disposable copy, source untouched) + SST cand-02:
`tests/unit/test_integration_dialectic.py` +
`tests/integration/test_dialectic_fixture.py`.

1. Gateway bindings introspection is defensive: foreign profile/route shapes
   (e.g. STC ScriptGateway stuffing strings) degrade to kind UNKNOWN instead
   of raising. (SST-side fix from this exercise; committed regression test.)
2. Critique failure/malformed/no-route yields `CRITIQUE_FAILED` (rank 0.5,
   rationale discloses no semantic approval) instead of fabricated APPROVE.
   Fallback scores (0.5) no longer cross the 0.8 synthesis threshold.
3. Task budgets bind: effective cap = min(task, policy); 0/None disables a
   side. `TaskPacket.time_budget_seconds` default is now None (no caller
   bound; policy governs). STC's explicit Budgets values now actually bind.
4. Custody: empty acceptance fails; ALL commands run with per-command
   retention. (No STC impact: STC replaces custody with its own wrapper.)
5. Cost honesty (closeout): `SearchPolicy.max_cost_usd` default is now
   `None` (unbounded; the old $10 default was never enforced). A set USD
   cap (task or policy) with unpriced responses now raises
   `UnpricedCostBudgetError` instead of running an unenforceable budget.
   STC callers that set `cost_budget_usd` must either price their profiles
   (`input/output_usd_per_1k_tokens`) or leave the cap unset.
   `GatewayResponse` gains `cost_known` (TEST fixture: True at $0).
6. Response caps (closeout, additive): `SearchPolicy.response_max_tokens`
   overrides the per-request 2048/1024 role defaults (needed for reasoning
   models); CLI flag `--response-max-tokens`. Gateway maps null content to
   `""`, never literal `"None"`.
5. SearchResult/CLI expose gateway bindings; promote enforces integrity
   binding + workspace staleness; decide validates node ids.

## Validated STC-side patch (owner to land)

In `scrape_tainted_scores` (disposable copy tested GREEN):

```python
verdict = str(evt.payload.get("verdict", ""))
...
if verdict == "CRITIQUE_FAILED":
    rule = "explicit-critique-failed"
elif rationale == FALLBACK_CRITIQUE_RATIONALE:
    ...
```

Plus rule-name test updates (`exact-fallback-rationale` ->
`explicit-critique-failed` where the veto now fires on the explicit verdict).
Proven: veto fires, `champion-vetoed-no-alternative` + escalated exclusion
behave as before.

## STC recalibrations required (owner decisions)

- `test_veto_reselects...`, `test_fixture_wiring_stub_substrate`: their
  veto-then-reselect-to-synthesis scenario is UNREACHABLE under honest scores
  (tainted 0.5 can never be synthesis-paired, and can only be champion when
  nothing scores higher). Retire or repurpose (veto->NoChampion is covered by
  `test_all_tainted...`).
- `test_fix_elapsed...`: STC's explicit task budgets now bind inside SST;
  recalibrate budgets/expectations (SST-side honors caller bounds by design).
- Pre-existing env failures (identical on pristine HEAD, not regressions):
  `test_live_cli_node` (no codex auth), `test_stc_source_real_gates...`
  (node_modules symlink loop in this env).

## Re-pin note

Working tree drifts from pin 079f4de in spot-hash files; advance the pin only
AFTER observing actual consumption. No silent migration of existing runs.

## Open joint run (owner window, pinned disposable env)

Real task: search -> proposal -> STC custody/execution -> gates/verdict ->
caller-visible result + feedback, plus one integrated rejection case.
