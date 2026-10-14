# Alt A implementation + qualification plan

Direction: genuine upstream DSH (`639ed01`, v0.2.0-rc.2) as the front door,
STC capabilities as a versioned `dsh-plugin` bundle. Reversible until
qualification; Alt C is the documented fallback (§13 procedure on concrete
upstream incompatibility).

## Phase 1 — Upstream runtime identity (done: clone + toolchain)

- [x] Shallow clone @ `639ed01`; record pin (commit, root version, pnpm,
      node engines).
- [x] Toolchain: node v22.23.3 (SHA256 OK) + pnpm 11.7.0 @ `/tmp/toolchain`.
- [ ] `pnpm install` + `pnpm run build` in `/tmp/dsh-upstream` (proxy env!).
- [ ] Boot identity: `dsh --version`, `dsh --profile web --dump-config`
      (capture full tree), `dsh web --no-open` reachability on :3080.
- [ ] Decide durable checkout location (operator): proposal `../dsh`
      sibling + `dsh-nightly` pin file in STC. /tmp stays scratch.

## Phase 2 — STC plugin bundle v0 (tools-first, no UI fork)

New repo dir `dsh-plugin-stc/` (own package.json, `dsh-plugin` topic):
bundle `stc-tools` with `cordis.patch.yml` inserting:

- tools (each `defineTool`, typed I/O, `exec.signal` honored):
  `stc_preview` (argv/env/budget block via backend builders),
  `stc_run` (spawn `stc run --target stc …` as background job via
  `ctx.jobs.start`, console.log-style streaming),
  `stc_status`/`stc_log` (poll RunRecord-equivalent),
  `stc_cancel` (SIGTERM/KILL + proof),
  `stc_dossier` (read-only final_outcome/spend/qa/branches/review).
- policy hooks: `tools/pre-execute` budget/approval gate (reuses legacy
  launch-guard semantics: pins, handshake, SIM-only mock, typed confirm
  surfaced as DSH approval), `ctx.tools.guard()` monotonic deny for
  destructive ops outside session scope.
- session use: durable DSH sessions for conversation; STC run records for
  execution truth; interruption resumes without repeating side effects.

Verification per tool: unit (vitest per DSH repo conventions) + integration
against `--exec-harness` deterministic fixtures (quota-free) + one
`--manual` path test. Runtime identity test: `--dump-config` contains
`stc-tools` rows; disable-bundle test proves effect-unregister.

## Phase 3 — Workspace surfaces (ConversationNodes, no DSH fork)

- `ConversationNodeDefinition` + keyed Chat renderers: brief, acceptance,
  progress, decision, diff, evidence cards (prototype journey is the spec).
- Settings card for STC roots/budgets (cookbook `adding-a-settings-card.md`).
- First-launch tour, empty/loading/error states, keyboard access pass.
- Verify: DSH web profile boots with bundle; HTTP + CDP/DOM checks where
  the sandbox allows; operator pixel pass (browser blocker!).

## Phase 4 — Delivery-policy experiments (quota-free first)

- Baselines: B0 simple single-agent (DSH headless + stc tools), B1 existing
  STC workflow via `stc run`, B2 fixed localize→repair→validate.
- Contenders: P1 event-driven ACI loop, P3 manager-guided search (P2 == B2).
- Tasks: new feature, unfamiliar-repo change, bug repair, cross-module
  change, ambiguous spec, visible-UI task; dev set for tuning, HELD-OUT set
  for qualification (policy authors never see answers).
- Harness: headless/sdk profiles + patch overlays per policy; Python SDK
  runner for batching; metrics = verified success first, then regressions,
  time, tokens/compute, retries, rework, interventions. Failures/timeouts in
  denominator. Predeclared bounds + stop rules; keep baseline on inconclusive.
- Live-model batch: NO spend without the budget decision. Prepare one bounded
  batch (estimate, hard cap, expected information gain) as the decision ask.
  Label fixture sim vs coordinator-assisted vs unattended provider runs.

## Phase 5 — Discovery lane + promotion controls

- Modular boundary in STC repo (no new service): `policy/` versioned
  definitions, `experiments/` runner + theoracle, `promotion/` checklist.
- Invariants (tested): resource accounting, isolation, authoritative eval,
  promotion controls outside candidate authority; candidates may propose
  evaluators, never rewrite the judging eval; existing runs keep policy id;
  migration deliberate + recoverable.
- Promotion: eval on held-out set → versioned release note → deliberate
  migration. Discovery lane cannot silently alter delivery (config-layer
  separation test).

## Phase 6 — Qualification

Local-production envelope (single-user Linux/WSL, loopback browser):
install/startup from pins, `ruff`/`mypy --strict`/pytest gates (CI matrix),
console suite, DSH repo checks for touched packages, durable sessions,
interrupted-run recovery, cancellation proof, budgets, credential handling
(explicit DSH_HOME, never `~/.dsh` silently), FS boundaries, actionable
errors, isolation assessment for model-generated code, upgrade/rollback doc.
Real task + follow-up demonstrated; walkthrough evidence captured.
Competitive capability reported as scoped result vs named dated baselines —
no "frontier-grade" self-award.

Explicitly unqualified until runnable: pixel-level browser QA (env blocker),
live-provider behavior (budget decision pending).

## Work split

- Coordinator (this session): phases, reconciliation, experiments, qual.
- Specialist workers as needed: dsh-build, plugin-tools, plugin-ui,
  experiment-runner, independent auditor (fresh eyes on release candidate).
- Native subagents preferred over Workflow tool until provider-network
  flakiness clears (2 workflow failures observed; payloads recovered manually).
