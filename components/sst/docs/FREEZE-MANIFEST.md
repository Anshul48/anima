# SST freeze manifest — release candidate (2026-10-04, INDEPENDENTLY VERIFIED)

Core + task-to-result UI + Windows-qualification browser correction +
live-model qualification + budget-honesty closeout.
Supersedes cand-01 (preserved at `.delivery/cand-01`, not part of release).

## Identity

- Base: git HEAD `079f4de6fd43881c2f1b529f0612f1df64a62f32` (branch main).
- Tracked diff: 26 files, +1924/-173 (see `.delivery/cand-02.patch`,
  apply-checked against clean HEAD; regenerated at closeout).
- Untracked, intended for release: 14 src (UI package, executor/memory
  protocols, outcomes, recovery, CLI memory, memory adapter, sandbox
  executor); 12 tests (incl. `test_gateway.py`,
  `test_coord_truthfulness.py`, `test_coord_integrity.py`,
  `test_ui_journey.py`); 9 docs (progress, coordinator prompt,
  continuation, STC handoff, UI journey, recovery limits, Windows
  qualification, live qualification, this manifest); 9 live-qual evidence
  files under `docs/evidence/live-qual-2026-10-04/`.
- NOT for release: `.env` (credentials, git-ignored), `.delivery/`
  (copied checkouts, patches, browser profiles), `.venv/`, caches.
- Dependencies: `uv.lock` (frozen); requires-python >=3.12; UI is stdlib-only.
- Platform qualified: Linux (this env). Native Windows: 145/145 + launcher
  + headless-Chrome journey per WINDOWS-QUALIFICATION receipt.
- Durable delivery (local, uncommitted): `.delivery/cand-02/` (runnable
  tree, synced) + `.delivery/cand-02.patch` + `.delivery/run-ui.ps1` +
  `.delivery/WINDOWS-HANDOFF.md`.

## Contracts and interfaces

- `run_search -> SearchResult`; `execute_search` unchanged (STC-compatible).
- CLI: `run [--json]` (0/2/3/4/130) with `--response-max-tokens` override,
  `ui --port --project-path`, `status/decide/promote/visualize` with
  integrity + staleness + human gates.
- UI: `/`, `/tasks/{id}`, `/runs/{id}` + JSON API (tasks, runs, cancel,
  result, alternatives, events, decide, promote, outcomes, providers).
  Provider modes: fixture (TEST-labeled, real acceptance), static, operator.
  UI runs use role-default response caps (no UI knob; CLI/API carry it).
- Outcome reports verbatim; recovery via SEARCH_COMPLETED (see RECOVERY-LIMITS.md).
- Cost accounting: priced profiles report `cost_known=True`; unpriced live
  profiles report unknown. USD caps require pricing (else
  `UnpricedCostBudgetError`); `max_cost_usd` default is `None` (unbounded).

## Evidence

- Gates: ruff 0, format 0, mypy --strict 0 everywhere; pytest 161/161 on
  Linux. (Sandboxed runs need `no_proxy=127.0.0.1,localhost` for the 3
  localhost-server tests.)
- UI: committed real-HTTP journey test + JS-delimiter regression screen
  (fails pre-fix, passes fixed) + coordinator live smoke + verifier
  journey/negative/cancel/reopen probes + Windows headless-Chrome journey
  (see `.delivery/windows-qualification/`).
- Live model: `deepseek-ai/DeepSeek-V4.1-Flash` via SAIL Research —
  attempt 1 `no_candidate` (reasoning tokens exhausted the 2048 cap;
  failure kept), attempt 2 `CHAMPION_FOUND` with
  `response_max_tokens=8192` (6/6 acceptance passes, live APPROVEs,
  26,181 real tokens, 0 provider errors). Full record:
  `docs/LIVE-QUALIFICATION-2026-10-04.md` + `docs/evidence/`.
  Dollar spend unmeasured (no pricing); tokens only.
- STC disposable exercise (STC HEAD 851e4a4, source untouched): caller path
  proven against cand-02; 2 SST-side fixes from it (defensive bindings,
  None time default); Rule-4 veto patch VALIDATED; 3 STC recalibrations
  documented with root causes (see STC-HANDOFF.md).
- Verifier lanes: final 5/5 PASS + narrow confirmation on exact bytes;
  closeout re-verification on final bytes (see SST-PROGRESS.md).

## Accepted semantics and limitations

- Critique advisory: CRITIQUE_FAILED eligible at 0.5, visible everywhere.
- Integrity binding is unkeyed tamper-evidence (HMAC future).
- USD caps need priced profiles; unpriced + capped is a hard error, and
  SAIL-run dollar cost is explicitly unclaimed.
- STC adoption + live caller qual: open, owner window needed. TRACE deferred.
- Caller-visible vs earlier candidate: `max_cost_usd` default $10 -> None
  (the $10 was never enforced); `GatewayResponse` gains `cost_known`;
  `SearchPolicy` gains `response_max_tokens`; CLI gains
  `--response-max-tokens`. All additive except the dishonest default.

## Upgrade policy

Additive models/fields; `execute_search` stable. Behavior changes: honest
custody/critique/budgets, promote binding + staleness, None time default,
priced-cost enforcement, null-content mapping. Re-pin only after observed
consumption; existing runs keep versions.
