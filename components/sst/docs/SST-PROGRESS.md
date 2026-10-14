# SST coordinator progress / decision / evidence record

Started 2026-10-04. Coordinator execution authorized in-session (user: coordinator +
build/audit specialists, prompt `docs/SST-COORDINATOR-PROMPT-2026-10-04.md`).
Source tree is preserved input; implementation happens in isolated copies.

## Candidate identity (input snapshot, 2026-10-04)

- HEAD `079f4de6fd43881c2f1b529f0612f1df64a62f32` (main), same as STC pin.
- 19 tracked files modified (+1277/-81); `git diff` sha256
  `9835b4848a7cb9a3d696d28ee2ac908cf131324bd1e8a83006f0b8e29aa05815`.
- 16 untracked files (7 src: executor/memory protocols, outcomes, recovery,
  CLI memory, memory adapter, sandbox executor; 8 tests; 1 coordinator prompt).
- Isolated working copy: `/tmp/sst-coord/cand-01` (byte-identical copy, own
  `.venv` from `uv.lock`, own stores/evidence under `/tmp/sst-coord/`).
- Baseline gates on unmodified copy: ruff check 0; ruff format 1 offender
  (`tests/unit/test_visualizer.py`); mypy --strict 0; pytest 132/132
  (requires `no_proxy` for localhost: sandbox proxy otherwise 502s one test).

## Requirement-to-evidence map (abridged)

| Requirement | Status | Evidence / gap |
|---|---|---|
| Callable contract `run_search -> SearchResult` | implemented, unqualified | code inspected; needs integrated qual |
| `execute_search` STC-compat wrapper | implemented | signature stable; STC runner calls it |
| Honest empty-acceptance (no unqualified PASS) | GAP (repro R1) | custody returns passed=True |
| All acceptance commands run + retained | GAP (repro R2) | only first command runs |
| Failed/malformed critique never fabricates APPROVE | GAP (repro R3) | fallback verdict is APPROVE |
| Provider/mode identity visible to caller | GAP (repro R4) | envelope lacks it; CLI TEST fallback unlabeled |
| Task/policy budget precedence, zero-disables | GAP (repro R5) | TaskPacket budgets unused by controller |
| Outcome reports verbatim, non-authoritative | implemented | outcomes.py + tests; needs qual |
| Recovery via SEARCH_COMPLETED marker | implemented | recovery.py + tests; needs qual |
| Deterministic + real-model useful search demo | open | no keys/ollama in this env; operator mode first |
| Real STC caller qualification | open dependency | STC HEAD 851e4a4, pin 079f4de; working tree drifts from pin spot-hash |
| TRACE boundary | deferred to owner interface | protocol + none/static providers only |

## Accepted constraints / assumptions / decisions

- STC + TRACE trees are read-only; pins, config, active runs untouched.
- No API keys or model endpoint in this env: real-model qual needs credentials.
- Fix direction (reversible): empty acceptance -> explicit fail; run all commands
  with per-command retention; critique failure -> distinct non-APPROVE verdict
  (champion stays verifier-gated, caller-visible); envelope carries provider
  identity; effective budget = min(task, policy), 0/None disables.
- Solo coordinator until implementation/verify split justifies a verifier lane.

## Status 2026-10-04 (cand-01 in /tmp/sst-coord/cand-01)

- R1-R5 repaired + verified: gates lint 0, format 0, mypy --strict 0,
  pytest 137/137. Repro file `tests/unit/test_coord_truthfulness.py` kept.
- Demos pass: API champion+rejection, champion+budget/provider combos,
  recovery equality + IncompleteSearchError, CLI exit-2 honest negative.
- STC handoff written (isolated `docs/STC-HANDOFF.md`); STC tree untouched.

## Open dependencies (smallest actions)

1. Real-model qual: needs OPENAI/DEEPSEEK key or ollama + model (none in env).
2. Native Windows CLI: powershell interop fails from here; run 3 CLI commands
   on Windows or fix interop.
3. STC caller qual: needs STC owner window in pinned disposable env.

## Verifier lanes (2026-10-04)

- Lane 1: gates/recovery/compat PASS; found D1 promote integrity gap, D2
  CRITIQUE_FAILED eligibility, D3 ghost decide, D4 snapshot gap + latent
  APPROVE default. D1/D3/latent fixed with regression tests
  (`tests/unit/test_coord_integrity.py`); D2 kept as documented advisory
  semantics with CLI verdict display; D4 recorded limitation.
- Lane 2 (delta): 3/3 PASS incl. file-op tamper refusal. Residual note:
  binding is unkeyed tamper-evidence; HMAC is future hardening.
- Final: lint 0, format 0, mypy --strict 0, pytest 141/141 (both lanes).

## Freeze

- cand-01 frozen in `/tmp/sst-coord/cand-01`: HEAD 079f4de + 20 files
  (+1567/-151, sha `004f4cc0…`) + 20 untracked. Manifest + STC handoff in
  candidate `docs/`. Source tree holds only this record (no code changes).
- Reviewable patch `/tmp/sst-coord/cand-01.patch` (268,638 bytes,
  `git apply --check` PASS against clean HEAD).

## Delivery continuation (2026-10-04, authorized)

- UI lane built task-to-result UI (new files only, verified clean); integrated
  with `sst ui` mount. One assembly interaction fixed (UI snapshot fn).
- Core: D4 workspace-staleness enforced (exclusion-aware digest, committed
  tests); recovery limits documented; operator mode = fixture/static +
  human decide/promote (documented, UI-selectable).
- Landed verified delta into source working tree (20 files +1676/-153,
  uncommitted for review). Landed gates in source env: 145/145, lint/format/
  mypy 0. Durable `.delivery/cand-02/` + patch + `run-ui.ps1` + handoff.
- STC disposable exercise (STC source untouched): caller path proven; 2 SST
  fixes from it (defensive bindings, None time default); Rule-4 veto patch
  VALIDATED for owner; 3 STC recalibrations documented (see STC-HANDOFF.md).
- Verifiers: final 5/5 PASS + 4/4 confirmation on exact bytes. No live-model
  claims anywhere (no credentials).

## Windows receipt integration (2026-10-04)

- Landed the prepared 2-line browser fix (hashes verified both ends).
- Added `test_served_js_has_balanced_delimiters`: fails on pre-fix bytes,
  passes fixed. Tokenizer handles strings/comments/regex/templates.
- Wired `DEEPSEEK_API_KEY` provider selection (OpenAI > DeepSeek > TEST)
  with precedence test; UI operator mode inherits it.
- Excluded `.delivery/` from ruff so the repo's own bare gates stay green.
- Full gates: 147/147, lint/format/mypy 0 (bare and scoped). Independent
  confirm lane 4/4 PASS on final bytes. Durable + patch refreshed.

## Remaining external obligations

1. Live-model search qual (no credentials here; provider config ready for
   either key; prepared task in WINDOWS-HANDOFF.md).
2. STC owner: land Rule 4, recalibrate 3 tests, re-pin after observed use.
3. Commit decision for the landed working tree (left uncommitted).

## Native Windows architect verification (2026-10-04)

Attributable update; earlier records and failures are retained. Full receipt:
`docs/WINDOWS-QUALIFICATION-2026-10-04.md`.

- cand-02 matches the landed implementation across 83 source/test/config files.
  On native Windows, frozen dependencies install and gates pass: lint 0,
  format 0, strict mypy 0, pytest 145/145. Evidence in
  `.delivery/windows-qualification/`. The previous interop failure does not
  require the user to run these gates now.
- Actual Chrome execution of the original UI FAILED: extra closing
  parentheses in `src/sst/ui/pages.py` lines 599-600 cause a JavaScript syntax
  error and leave the run page at Loading. The HTTP test did not execute JS.
  Original browser report/screenshot are retained.
- A two-line correction is independently exercised in the isolated
  `cand-02-browser-fix` copy: browser create/run/alternatives/decide/promote/
  reopen/negative/cancel all pass, zero uncaught JS errors; focused HTTP
  journey test and page lint/format pass. Apply-checked proposal:
  `.delivery/windows-qualification/ui-browser-fix.patch`. **Owner integration
  and delivery refresh are still outstanding; original source/snapshot were
  not changed by this probe.** This is routine SST work, not an external-only
  blocker. A client-disconnect traceback remains recorded as a polish issue.
- `.delivery/run-ui.ps1` repaired locally: supported `--project-path`, project
  resolution before directory change, sync failure checking and CLI exit
  propagation. Corrected launcher observed healthy on Windows; native CLI
  TEST positive/negative smoke exits 0/2.
- No real generation claimed: browser qualification uses explicitly TEST
  fixture code and real acceptance execution. `operator` delegates to the
  default gateway, not a separate manual candidate-input channel. Live-model
  qualification, actual STC adoption/caller qualification and final release
  bookkeeping remain open. STC/TRACE source, pins and runs were untouched.

## Live-model qualification (2026-10-04, SAIL Research)

Receipt item 2 closed with a real model run. Credentials arrived as
`SAIL_API_KEY` in untracked `.env` (now git-ignored); model
`deepseek-ai/DeepSeek-V4.1-Flash` via `https://api.sailresearch.com/v1`
(OpenAI-compatible). Probe: HTTP 200, `PROBE-OK`, real usage tokens.

- First live run exposed a genuine interop defect: the reasoning model spent
  ~2.4k tokens on chain-of-thought inside the hardcoded 2048 cap, returned
  `content: null`, and the gateway stringified it to a literal `"None"` patch
  (termination `no_candidate`, 7,574 real tokens, 0 provider errors).
- Fix (3 small source edits, defaults unchanged): `SearchPolicy.
  response_max_tokens` override (`None` keeps role defaults
  2048/2048/2048/1024); controller `_role_max_tokens()` at all 4 role sites;
  gateway maps null content to `""` instead of `"None"`. Durable tests:
  `tests/unit/test_gateway.py` (2) + 3 override/default tests in
  `tests/unit/test_controller.py`.
- Second live run: **CHAMPION_FOUND** — model-generated `mul` fix, all 6
  alternatives passed real acceptance (`test_math.py` exit 0) with live
  `APPROVE` critiques, 26,181 real tokens tracked in budget, 0 provider
  errors. Envelope: `/tmp/sst-live-qual/run2/live-envelope.json`.
  Cost evidence is tokens only (`cost_usd` stays 0.0 — the gateway prices no
  openai_compatible usage; pre-existing gap, not new).
- Gates after change: **152 passed**, ruff check/format clean, strict mypy
  clean. (Full suite must run with `no_proxy=127.0.0.1,localhost` under the
  sandboxed proxy or the 3 localhost-server tests fail environmentally.)
- `.env` added to `.gitignore`; envelope verified secret-free; key never
  printed or committed.

Remaining: STC owner adoption (item 3) and the commit/release word.

## Closeout (2026-10-04, authorized release commit)

User found two gaps: stale FREEZE-MANIFEST and unmeasured USD cost. Both
closed; local release commit explicitly authorized.

- Manifest reconciled: 26 tracked files +1924/-173, 14 src / 12 tests /
  9 docs / 9 evidence untracked-for-release, gates 161/161, live-model
  status, caller-visible changes. `.env`/`.delivery/`/`.venv`/caches
  excluded from release.
- Evidence durable: both live attempts + harness + repo + diverge prompt
  at `docs/evidence/live-qual-2026-10-04/` (secret-scanned clean; only
  env-var names in a docstring). Full record:
  `docs/LIVE-QUALIFICATION-2026-10-04.md`.
- Budget honesty: `ProviderProfile` USD rates, `GatewayResponse.cost_known`
  (TEST/fixture: true at $0; unpriced live: unknown), `max_cost_usd`
  default $10 -> None, `UnpricedCostBudgetError` fail-fast on capped +
  unpriced, `FixtureGateway` marked known-zero (found by closeout probe).
  CLI gains `--response-max-tokens` (the live-success config, now on the
  documented path). 9 new closeout tests (gateway pricing x3, controller
  caps x4, CLI flag x1, fixture cost x1). STC-HANDOFF notes the
  caller-visible changes. SAIL dollar spend remains unclaimed (no rates).
- UI uses role-default response caps (no UI knob; CLI/API carry it) —
  recorded as accepted scope, reversible.
- Per-check coverage (all Linux, this env; revision = base 079f4de +
  closeout tree, SHA recorded at commit):
  - pytest 161/161, ruff 0, format 0, mypy --strict 0 (final bytes;
    needs `no_proxy=127.0.0.1,localhost` under sandbox proxy).
  - CLI `--json` + `--response-max-tokens 4096`, TEST: exit 0,
    champion_found (`/tmp/sst-closeout/cli2.*`).
  - UI fixture journey + $1 cap: create/run/result/alternatives/events/
    decide/promote-verbatim/reopen all green (closeout probe A).
  - UI operator + $0.01 cap + unpriced SAIL: run failed with
    `UnpricedCostBudgetError` surfaced (closeout probe B).
  - Live model (pre-closeout bytes + response cap): CHAMPION_FOUND,
    26,181 tokens; closeout re-verified the same config path via CLI flag.
  - Windows native: prior receipt 145/145 + launcher + Chrome journey
    (unchanged; fresh host run optional).
- Independent audit lane on final bytes before commit (see below).
- Externally open after release: STC adoption (owner), TRACE (future).
