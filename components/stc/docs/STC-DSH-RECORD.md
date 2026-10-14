# STC genuine-DSH workspace — canonical record

Objective: polished AI-assisted software-building workspace powered by actual
upstream DSH + Cordis plugins (custom "DSH-inspired" console does NOT satisfy),
with an experiment-selected delivery policy and a separate process-discovery lane.
Mandate: [STC-COORDINATOR-PROMPT.md](/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/stc/docs/STC-COORDINATOR-PROMPT.md).
Prior state: [HANDOFF.md](/mnt/c/Users/anshu/OneDrive/Documents/Code/Utilities/stc/operator-console/HANDOFF.md) (Phases 1–4, DSH-inspired console, 83+10+36 tests).

## Accepted constraints
- Upstream DSH is the foundation; verify runtime identity, plugin loading, config, sessions, execution path.
- Envelope: single-user local Linux/WSL, browser access, loopback-only.
- Spend: only explicitly authorized allowances; otherwise prepare bounded live batch for one budget decision.

## Verification gates (repo-configured, must run before done)
- `uv run ruff check src tests` + `ruff format --check src tests` (CI literal)
- `uv run mypy src tests` (strict)
- `uv run pytest --cov=stc --cov-report=term-missing`
- Console: `pytest operator-console/tests`, console ruff.toml gates
- CI: ubuntu-latest + windows-latest matrix

## Environment probes (observed 2026-09-29)
- uv 0.12.9, python 3.12.3, node present; no chromium/firefox on PATH (browser QA needs tooling).
- Sibling checkouts present: sst, prompt-kit, trace (STC pins may resolve).

## Decisions / results / evidence
- (pending) Phase-0 workflow: 5-angle audit + critic + synthesis.
- Phase-0 research recovered (2026-09-29): workflow runtime failed twice on
  provider-network errors, but all 5 researcher + critic payloads were recovered
  from subagent logs (/tmp/child-*.json). Gap-followup + synthesis never ran —
  coordinator synthesizes inline. CAVEAT: the critic's "D-UPSTREAM absent"
  verdict is an artifact (it received JSON sliced to 6000 chars); the actual
  upstream payload exists and matches my independent fetches. Critic's line-level
  corrections to the backend audit (SearchPolicy def in SST pin, dispatch
  no-shell overbroad, budget conflation, etc.) stand and are preserved.
- Toolchain provisioned (2026-09-29): node v22.23.3 (SHA256 OK) + pnpm 11.7.0
  via corepack at /tmp/toolchain (HOME is read-only in sandbox; durable install
  location is an operator decision). Proxy env present (UNDICI-EHPA warnings).
- Baseline console suite (2026-09-29, this env): full run 82/83 in 460s —
  `test_console.py::test_http_smoke_lists_registered_run` failed once (server-side
  BrokenPipeError in log). Passes in isolation (9.85s) and at file level (23/23,
  14.82s). test_console runs first alphabetically, so no cross-file pollution —
  characterized as load/timing flake (10s fetch timeout vs slow-FS readiness
  probes; cf. HANDOFF §9 git slowness). No legacy-console fix; note for qualification.

## Observations (2026-09-29, inline survey)
- `src/stc/`: cli + compiler/core/genome/integration/judiciary/memory/orchestrator/protocols/schemas/services/socratic/substrate/worktree.
- Uncommitted worktree state: `src/stc/cli.py` modified; untracked `operator-console/`, `docs/plans/`, `exec_harness.py`, `test_exec_harness.py`, coordinator prompt, this record.
- `../prompt-kit/dsh/` is a Node workbench (index.js/run.mjs/workbench.html) — almost certainly NOT DeepSeek Harness; do not confuse.
- `../sst/src/sst` present.

## Upstream DSH facts (primary sources, fetched 2026-09-29)
- Repo: deepseek-ai/deepseek-harness, default branch `master`, MIT, developer preview (breaking changes expected).
- Runtime: Node.js; `npx @deepseek-ai/dsh web` → Web UI at 127.0.0.1:3080; source build via pnpm.
- Framework: Cordis (cordiverse/cordis) — plugins contribute services/typed events/reversible effects; no privileged core; extend by mounting plugins.
- Composition: profiles (web/headless/sdk/sdk-minimal/acp) = ordered bundles + `cordis.patch.yml` layers + `--patch` overlays. `dsh-base` first layer; `dsh-web-app` adds browser app.
- Introspection: `dsh --profile web --dump-config` prints boot tree; any row replaceable by patch.
- Implication: genuine adoption = Node/pnpm stack beside STC Python backend; STC capabilities surface as Cordis plugins (likely via `stc` CLI child-process bridge). Confirm with child research + local checkout.
- Local checkout `/tmp/dsh-upstream` @ `639ed01` (master 2026-09-29, v0.2.0-rc.2): 14k files, pnpm monorepo, profiles web/headless/sdk/sdk-minimal/acp.
- DSH ships a **Python SDK** (`python/sdk` + `python/sdk-runtime`): drives bundled `dsh` over newline-delimited JSON-RPC on stdio; explicit Harness home required. Prime STC↔DSH bridge candidate.
- TOOLCHAIN GAP: DSH engines require node ^22.19 || >=24; env has node v18.19.1, no pnpm on PATH (corepack is a Windows-path shim). Need WSL-side node 22+/pnpm 11.7.0 before any DSH build/run.
- DSH source build (2026-09-29): `pnpm install --frozen-lockfile` green
  (1685 entries; retry needed after transient fetch failure). `pnpm run build`
  blocked: tsx CLI's AF_UNIX IPC pipe gets EPERM under the sandbox.
  SCRATCH-ONLY workaround in /tmp/dsh-upstream: `node_modules/.bin/tsx`
  replaced by `node --import tsx/esm` shim (orig kept as `tsx.orig`; no repo
  script uses tsx CLI flags). Build re-launched through the normal path.

## Environment lessons (2026-09-29)
- Env forces all traffic through proxy 127.0.0.1:33177 with EMPTY no_proxy:
  loopback curl gets 502 unless ALL proxy vars are unset (http/https/all/ftp,
  both cases) or no_proxy is set. Applies to every future local check (:3080…).
- Gap analysis: `docs/STC-DSH-GAP-ANALYSIS.md` (G1–G6, preserve-list, Alts A/B/C,
  policy options P1–P3, Alt A recommended, 3-item decision packet with defaults).
- Prototype: `docs/prototype-dsh-workspace/index.html` (single-file Alt A
  journey: brief→run→interrupt→decision→evidence→follow-up + recovery states).
  Verified: HTTP 200/9103 bytes + Node DOM-harness load smoke (init + all 6
  steps + approve path, 10 messages, verified end-state, zero errors).
  Smoke server stopped after verification (standalone artifact, no server).
- BROWSER BLOCKER (2026-09-29/30, all in-session paths exhausted):
  headless Chrome 154 runs `--version` but the renderer SIGTRAPs on any
  page load (full chrome, chrome-headless-shell, `--single-process`,
  `--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage` — all
  identical core dumps on a data: URL, so the OUTER bwrap seccomp is the
  killer, not Chrome's own sandbox). Firefox 157 (fresh tarball):
  SIGSEGV with and without its content/GMP/RDD sandboxes. /dev/shm is
  fine (7.7G). Host Chrome exists
  (`/mnt/c/.../chrome.exe`) but WSL interop is dead in-sandbox
  (`UtilBindVsockAnyPort: socket failed`, even for `cmd.exe /c echo`).
  No other engines/tools on PATH, no playwright browsers, no strace.
  `require_escalated` (one unsandboxed chrome run) DENIED: approval
  prompts are disabled. Net access works; only rendering/exec is walled.
- Mitigation landed: client LOGIC is now covered headless
  (`tests/client-smoke.test.ts`: real client.js executed under stubbed
  loader/React/slots; registration + render trees + subject gating).
  Pixels/layout/live mount remain the explicitly unqualified remainder.
  Smallest unblocking action (no full walkthrough, no unsandboxed
  restart): restart with APPROVAL PROMPTS enabled (sandbox stays on),
  so the single narrow unsandboxed-chrome command can be approved.

## Milestone: genuine DSH boots with STC plugin (2026-09-29)
- Build: `pnpm install --frozen-lockfile` + `pnpm run build` green @ `639ed01`
  (scratch-only tsx shim; see above).
- Identity: `dsh --version` → 0.2.0-rc.2; `--dump-config` → 105-row web tree
  incl. webserver/agent-loop/sessions (captured /tmp/dsh-web-config.yml).
- First STC Cordis plugin loads via `--patch dsh-plugin-stc/cordis.dev.yml`.
  (Historical note corrected: the "launcher-level only" claim was wrong —
  both `dsh web --patch` and `dsh --profile web --patch` work; see
  audit+fix §. `--no-open` goes last.)
- Web UI serves real frontend: token URL → 303 → cookie → 200, 34845 bytes,
  DSH boot shell HTML. Untokened root → 401 (browser-trust fence working).
- Sandbox lesson: servers die with the launching bash call (namespace
  reaping); boot+verify must happen in ONE bash call. Prior HANDOFF §8 note
  confirmed.

## Milestone: stc-tools v0 registered (2026-09-29)
- `dsh-plugin-stc/src/stc-tools.ts`: `stc_ping` + read-only `stc_dossier`
  (STATUS/outcome/reason/files/spend/review-head; traversal-guarded roots).
- Pure logic in `src/dossier-read.ts` (no DSH imports); `node --test` 6/6.
- Boot proof: `[stc-tools] registered stc_ping + stc_dossier`, zero errors;
  rows compose in `--dump-config`. Registry validates schemas at boot
  (first attempt failed honestly on missing `additionalProperties`).
- Honest boundary: model-driven tool *invocation* not yet exercised (no
  live-model budget); execution logic is unit-covered, schemas boot-validated.
  Invocation proof deferred to experiments phase, labeled.
- `stc_preview` added (2026-09-29): exact outer argv via quota-free
  `scripts/stc_probe.py` under the venv (reuses `lab.build_backend_argv`,
  `harnesses.preview_argv`, `lab.parse_budget_via_backend`; KD-2 preserved).
  Tests: node:test 10/10 (6 dossier + 4 exec), pytest
  `test_stc_probe.py` 6/6 (outer/inner/budget + JSON-error paths).
  Boot-registered clean alongside ping + dossier.
- Run tools + policy added (2026-09-29): `stc_run` (ctx.jobs background,
  probe-quoted argv, durable run dirs under $DSH_HOME/stc-runs),
  `stc_status`/`stc_log`/`stc_cancel`; `stc-policy` pre-execute gate
  (typed RUN, exe checks, mode allowlist). node:test 20/20 (mode-contract
  tripwire added; guard `dry`→`dry-run` fix). Boot log shows all rows
  mounting with zero errors.
- E2E proof 6/6 (2026-09-29, scratch vitest spec in /tmp checkout, mock
  model → REAL agent loop → REAL tools → REAL backend, quota-free):
  ping, dossier, preview, policy-denial, dry-run completion with durable
  records (exit.json completed + console.log), exec cancel with killed
  status + pid-death proof. Fixed real bug found: jobs owner must be
  `exec.agent?.id`, not `exec.agent`. Scratch spec + node_modules link are
  dev-only (gitignored); durable cover is unit + probe tests + boot logs.
- Client face v1 (2026-09-29, SUPERSEDED — see audit+fix §): the 5-row
  packaged-install claim did not reproduce from a clean state (G1+G2).
  Preserved for archaeology: `client.js` (locale en+zh, detail section,
  row config) was believed served via packaged `plugin add file:`.
  Replaced by the single-entry bundle, verified on both paths.
  `node --check` clean; in-browser mount unverified (browser blocker).
  Custom chat cards deferred to v2 (needs custom session events; built-in
  tool-call nodes already render our tools — no duplication accepted).
- Gate findings (2026-09-29): ruff check + format clean on src/tests/
  and all new files; new Python files mypy-strict clean + 6/6 pytest.
  `mypy src tests` is RED AT HEAD (59 errors/14 files, missing pin stubs
  etc.) plus 3 more from pre-existing uncommitted work — prior debt, not
  caused here; fixing 59 HEAD errors is out of scope (backend-semantics
  risk). My changes add zero gate errors.
- E2E made durable (2026-09-29): spec committed at
  `dsh-plugin-stc/tests/e2e/stc-bundle.e2e.spec.ts`, executed in a DSH
  checkout via `scripts/run-e2e.sh` (copy → import-rewrite → vitest →
  remove). Proven 6/6 from the committed copy.
- Discovery lane skeleton (2026-09-29): `policy/registry.ts`
  (versioned candidates, hash-lock, isolation to `policy/candidates/`,
  promote/revise/retire with no-regression + approver gates),
  `policy/theoracle.ts` (verified-success-first scorer, failures in
  denominator, ties keep baseline) + `policy/score.ts` CLI. Unit 32/32.
- Mechanics battery (2026-09-29): 3 scripted episodes (b1-direct,
  b2-gated, p1-aci) 3/3 green; theoracle selects **b2-gated** over
  b1-direct (equal success, demonstrated fault recovery). SCOPE HONESTY:
  mechanics only — model task-quality comparison needs the live batch.

## Independent audit + packaging fix (2026-09-29)
- Auditor verdicts: node 32/32 PASS, probe 6/6 PASS, packaged
  composition PASS, **web boot FAIL**, e2e 6/6 PASS, no-src-delta +
  ruff PASS. Two release-blocking defects, both reproduced:
- G1 — packaged installs never activated: entries were `.ts`, and Node
  22 refuses type-stripping under `node_modules`
  (`ERR_UNSUPPORTED_NODE_MODULES_TYPE_STRIPPING`); the 200 page served
  with zero `stc` and a "did not activate" warning. The earlier
  "client face v1 live via packaged install" claim did NOT reproduce
  from a clean state and is retracted for the 5-row design.
- G2 — 5-row dev overlay failed web startup: client-modules'
  `reconcilePackage` throws when one package resolves from multiple
  active loader sources (absolute-path rows each resolve to the same
  manifest). Single-row probe booted fine, proving infra OK.
- Fix: single loader entry. `src/index.ts` composes hello/tools/run/
  policy via `ctx.plugin()` (each keeps name/inject); `cordis.bundle.yml`
  + generated `cordis.dev.yml` mount exactly one `stc-bundle` row;
  esbuild 0.28.2 bundles `src/index.ts` → `lib/index.js` (21 KB,
  externals only `node:*` + `@deepseek-ai/*`); exports point at
  `lib/`; subpath exports removed; client row.config key retargeted
  to `#stc-bundle` (key = `pkg#rowId` per `rowConfigKey`).
  `plugin add file:` COPIES (verified stale copy) — rebuild +
  reinstall after every change.
- Fresh re-verification (clean DSH_HOME each): packaged install → 1
  row → boot clean, all 4 plugins register from JS, token → 200
  (35042 B, 10 stc, 5 boot-graph entries incl. `plugins/??@stc/…
  /client.js` combos), combo fetch 200 (374791 B, `stcBundle` ×3),
  untokened 401. Dev overlay: identical results. e2e 6/6 + unit
  36/36 (4 new packaging-contract guards) on the final tree.
- CLI-form correction (auditor + re-verified): BOTH `dsh web --patch
  X --no-open` and `dsh --profile web --patch X --no-open` work; the
  record's earlier "launcher-level only" note was wrong. DSH_HOME must
  always be explicit (default `~/.dsh` is read-only here → EROFS);
  inner pnpm needs XDG_DATA_HOME/XDG_CACHE_HOME/COREPACK_HOME
  redirects in this sandbox.

## Backend suite + real-task demo (2026-09-29)
- Backend gate: `pytest --cov=stc` exit 0 over 695 collected (summary
  line lost to `tail` truncation; exit code is the verdict). No
  src/tests modifications by this work (auditor-confirmed).
- Real-task demo (coordinator-assisted, quota-free): seeded-bug repair
  in a self-built scratch repo, driven preview→run→status→log→dossier
  through the REAL agent loop twice (task + iters=2 follow-up with
  restaged fixtures). Committed at
  `dsh-plugin-stc/tests/e2e/demo-manual-task.e2e.spec.ts`, run via
  `SPEC_FILE=demo-manual-task.e2e.spec.ts sh scripts/run-e2e.sh <dsh>`
  → 1/1 green. Both runs exit 1 with NEEDS_REPAIR dossiers and full
  evidence (run dirs, console.log, branches/qa/spend/review files).
- BACKEND FINDING (not a workspace defect): no champion is achievable
  on foreign trees — trusted test selection (`sel-1`/`osm-1`) injects
  STC's OWN suite (`tests/unit/test_integration_…`, `src`) as the
  pytest target, which cannot collect in a foreign lease (observed in
  `selection_*.json`: `ruff=True mypy=True pytest=False`). Nor on
  the STC tree at HEAD, where `mypy --strict` is red (whole-tree gate
  argv). This precisely bounds the known live-champion problem (see
  Praxist memory note): backend scope, out of workspace scope.
  The demo spec locks NEEDS_REPAIR as a tripwire that must visibly
  flip if backend selection ever changes.

## Conversation cards v2 via host presenters (2026-09-29)
- The "custom chat cards need custom session events" deferral was WRONG.
  Two native paths exist, both proven in-checkout: (1) external packages
  register ConversationNodeDefinitions + `conversation.chat.node`
  renderers (ui-goal/ui-deliverables/ui-trajectory precedent; the
  assembler accepts EVERY matching definition — layering, not
  first-match); (2) tools declare `presentCall`/`presentResult` card
  views + replay-safe `output.presentationMeta` (tool-fs pattern),
  rendered by the stock tool node with zero client changes.
- Chose (2): all 7 STC tools now present pending titles, completed
  generic cards (preview/run-status/evidence/cancel shapes), and
  structured meta. Pure logic in `src/stc-present.ts` (8 unit tests);
  e2e episode asserts meta on real tool/result events (ping/dossier/
  preview). Unit 44/44, e2e 7/7, overlay boot clean (token 200, combo
  200). Card PIXELS still need the operator browser run (walkthrough
  §1 checkpoints cover them); card STRUCTURE is proven headless.
- Path (1) stays available for future wholly-new node kinds (e.g. a
  persistent brief rail); not needed for v2.

## Operator walkthrough procedure (2026-09-29)
- `docs/STC-DSH-WALKTHROUGH.md`: turnkey operator-side browser run (first
  launch → task → interruption → decision → results → follow-up, with
  checkpoints + evidence list). HTTP-verified facts vs PREDICTED UI
  details are marked; nothing is pre-marked from the procedure alone.

## Pilot prepared + dry-validated (2026-09-30)
- Plan `docs/STC-PILOT-PLAN.md`: b1-direct vs b2-gated (gating question
  isolated; b0 waits for full batch), 3 deterministic tasks (bug-repair,
  new-feature, unfamiliar-docs; 4–6 wait for full batch), model
  deepseek-flash via Sail (SAIL_API_KEY + Sail base URL; transfer limits disclosed),
  hard cap $5.00 (abort $4.00), per-episode ceilings, preliminary-only
  framing, held-out twins + contamination disclosure. b2 stays
  explicitly PROVISIONAL.
- Harness: `scripts/pilot-tasks.py` (dev + twin tasks, disjointness
  asserted, sha256 manifest) + `scripts/live-pilot.py` (SDK-driven,
  verdict checkers, spend ledger, refusal gates). Dry run: 6/6 episodes
  quota-free ($0.00), mechanics green, verdicts correctly fail the
  probe, refusals verified. Usage extraction works off real events.
- Budget APPROVED 2026-09-30 ($5 pilot, deepseek-flash). Pricing
  re-verified the same day (flash: in $0.30 peak/$0.15 off-peak, out
  $1.20/$0.60 per M; peak worst-case 6 episodes ≈ $1.44 — cap holds
  3.4×). Runner reads key from env or gitignored STC_ROOT/.env (never
  logged). BLOCKED ONLY on key provisioning; dry re-validated after
  the change ($0.00).

## Product journey GREEN on real runtime (2026-09-30)
- Acceptance journey demonstrated through the REAL DSH runtime
  (sdk-minimal profile: real agent loop, sessions, persistent bash):
  describe feature → coordinator changes repo → working preview +
  verified diff → refinement → updated result. Driver
  `dsh-plugin-stc/scripts/product-journey.py` (ruff/mypy-strict clean):
  13/13 checks green across 2 turns (6+5 bash results; gates
  pytest+ruff green; previews `HELLO, ADA!` → `HELLO, ADA!!!`; git
  diffs; disk state; finish completed). Work dir kept per run.
- Only the provider is scripted (new TEST-ONLY fixture
  `dsh-plugin-scripted/`, single row, serves JSON turns via
  `ctx.llm.registerAdapter(['scripted'])`; NEVER part of release).
  Label: coordinator-assisted, zero model calls, deterministic. The
  superseded iters=2 demo asserted workspace mechanics only; this
  asserts the actual workspace experience (the old demo spec stays as
  the mechanics tripwire).
- Verified model-call sites (walkthrough correction): agent-loop turns
  only. Session titles NEVER call a model in any profile (no bundle
  wires an LLM title provider; titles fall back to prompt truncation).
  Manual-mode backend makes zero model calls — but the surrounding
  DSH conversation costs one provider call per assistant turn with a
  real provider (mock/scripted: zero).

## Durable paths decided + migration ready (2026-09-30)
- Canonical: `~/dsh`, `~/.local/share/stc/{toolchain,homes,runs}`;
  pin file `dsh-plugin-stc/DSH_PIN`; idempotent migration
  `dsh-plugin-stc/scripts/migrate-durable.sh` (copies toolchain incl.
  browser tools, fresh-clones DSH @ pin, installs, builds, verifies,
  prints canonical env; syntax-checked).
- EXECUTION BLOCKED in-session: home writes denied (read-only FS) and
  `require_escalated` needs disabled approval prompts. Same single
  unblock as browser: approval-capable restart. /tmp stays working
  scratch until then; existing data preserved (copy, never move).

## Live pilot executed via Sail (2026-09-30)
- Route: `deepseek-ai/DeepSeek-V4.1-Flash` (Sail default mode) through
  `https://api.sailresearch.com/v1`, key `SAIL_API_KEY` (repo `.env`,
  gitignored). Sail's strict gateway rejects DSH's proprietary
  `dsh_session_log` / `dsh_plugin_packages` fields (400); paid
  episodes now disable both contributors via Cordis config patch
  (`sail.patch.yml`, supported `enabled` toggles, no fork). First
  attempt batch (no patch) failed all 6 at the gateway, $0.00.
- Result: 6/6 completed, spend $0.04 of $5 cap. Strict verdicts tie
  1-1 (both pass unfamiliar-docs; both fail bug-repair + new-feature
  on `diff_only`). Failure analysis: the `diff_only` violations are
  `__pycache__/` bytecode from running pytest — a checker artifact,
  not agent misbehavior (functional checks green: pytest 6/6, cli 5/6).
  The one genuine behavioral failure is b2-gated/new-feature (cli
  false after 73k tokens / ~17 min).
- Preliminary only (n=3, disclosed limits stand): no separation, b2
  stays PROVISIONAL, nothing promotes. Full batch must first fix the
  checker (ignore `__pycache__/` et al).

## Open dependencies
- Upstream DSH repo access + Cordis extension docs.
- Approval-capable restart (browser pixels + durable migration).

## Finalization tranche (2026-10-04, STC owner session)
- Candidate: git HEAD 851e4a4b9072 + dirty (.gitignore, cli.py) +
  untracked (21 at tranche start); plugin src/tests/scripts tree hash
  5ce5b6a9…, backend py tree hash 51cd5935…; DSH pin 639ed01
  (/tmp/dsh-upstream, clean); node 22.23.3 + pnpm 11.7.0
  (/tmp/toolchain); SST consumed at pristine pin 079f4de6
  (/tmp/sst-pin-079f4de, detached clone at exact HEAD; sibling tree
  dirty). Pin form corrected 2026-10-04: archive extracts fail
  `prove_import_integrity` (requires .git + HEAD==pin); see below.
- Gate env (documented; CI has no remote so these are the effective
  gates): `PYTHONPATH=<sst-pin>/src:<prompt-kit-pin>` for pytest;
  same plus `MYPYPATH=<prompt-kit-pin>` for mypy strict 2.3.1;
  node22 + COREPACK_HOME/XDG redirects + no_proxy for DSH.
  Both pins consumed as detached clones at exact HEAD (dirty
  siblings fail closed: F3c refuses the prompt-kit worktree;
  lease integrity refuses dirty SST). SST 079f4de6,
  prompt-kit 4f442a6c. §2 env also exports STC_SST_ROOT,
  STC_PROMPT_KIT_ROOT, MYPYPATH, MYPY_CACHE_DIR (verify-doc
  amendment 2026-10-04: in-lease gates inherit these).
- Baseline green: ruff check+format; backend suite (result below);
  plugin units 95/95; e2e 16/16 (bundle 7, policy 3, brief 2,
  recovery 3, demo 1); probe 6/6; boot on fresh home PASS (landed
  `scripts/boot-check.py`); product journey 13/13.
- Release-hygiene fixes: pnpm `allowBuilds.esbuild=true` (fresh
  install proven in scratch); packaging externals scanner
  line-anchored (was matching English prose in recovery copy);
  dev dsh-tools symlink step documented in plugin README.
- Checker calibration (T3): corrected rescore of the preserved paid
  batch WITHOUT new episodes/spend (`scripts/rescore-pilot.py`):
  b1-direct 3/3, b2-gated 2/3. b2/new-feature confirmed a genuine
  total failure (no persisted implementation, single init commit).
  Confinement adversarial PASS (unauthorized file fails, ignored
  artifact passes). Raw batch + rescore-v1.json landed at
  `dsh-plugin-stc/evidence/pilot-2026-09-30/` (episode repos carry
  local core.fileMode=false: this FS forces 755; statuses verified
  identical). n=3 preliminary scope unchanged; b2 stays provisional.
- Rollback mechanics (T4): packaged install into H1+H2, boots green,
  H2 wiped, H1 restart green (rollback = restart previous home),
  external-store marker survives (`scripts/rollback-check.py` PASS).
  `plugin remove` observed rc=0 but only re-resolves deps (no
  detachment proof) — fresh-home path stays preferred.
- SST caller contract (T5): `docs/STC-SST-CALLER-CONTRACT.md` +
  `scripts/sst_compat_probe.py`. Pristine pin → COMPATIBLE; dirty
  sibling → DIRTY (contracts.py, custody.py differ). STC fails
  leases closed on drift as designed. Live-model SST consumption
  stays UNQUALIFIED, waiting on the SST owner's version + budget.
- Type gate (T6): mypy strict ZERO errors in 82 files (the "59"
  were missing-import fallout without the sibling env). Added
  per-module ignore_errors for prompt_kit.*/sst.* (absence still
  loud — no ignore_missing_imports); removed 5 dead ignores.
- Selection finding disposition (T6): sel-1/osm-1 mandatory set is
  STC-self-referential by ratified contract; on foreign leases the
  pytest target cannot collect, so dialectic champions are
  impossible there under the current contract. NOT changed in this
  tranche (amendment needs its own disposition + M1-chain
  re-verification; live-champion search is separately held).
  Honest envelope: foreign-tree construction via workspace tools
  (journey-proven) with NEEDS_REPAIR tripwire; champion path
  qualified on STC-tree targets. Amendment sketch: workspace-
  relative mandatory set or foreign-workspace gate profile.
- CI note: `.github/workflows/ci.yml` is unrunnable as defined (no
  remotes anywhere; no sst/prompt-kit provisioning) — local gate
  procedure above is authoritative until remotes/publishing exist.
- Env lessons: (1) never pair edit/write_file with bash in one
  block on this mount (two transient file disappearances; cause
  undetermined, idle persistence proven); (2) pkill patterns must
  self-exclude (`[d]sh`); (3) supervise DSH boots with process
  groups + port polling (pnpm orphans the server on SIGTERM).
- Whole-tree Gate-1 green: `ruff check .` + `ruff format --check .`
  (186 files), mypy strict 0 errors (82 files) in the sibling env.
- Learning loop closed, scoped (T7): rescore → theoracle episodes
  (`scripts/rescore-to-episodes.py`) → score.ts →
  `policy/selection.json` (ledger-sha pinned, $0.0386 attributed,
  winner null keeps b1-direct) → live-pilot `--policies` default
  resolution with fail-closed fallback. Demonstrated $0 dry:
  no-selection runs all 6 episodes; recorded selection runs b1-only
  3; corrupt selection falls back to all 6 with provenance.
  Tests: `scripts/test_policy_default.py` 10/10. Limits: n=3;
  default-narrowing starves challengers (periodic explicit full
  runs required); promotion stays human-gated. No broad learning
  claim; loss-ledger remains write-only (no decision arrow).

## Backend-suite finalization (2026-10-04, continued)
- Lease ELOOP fixes (product): `hash_tree_manifest` os.walk rewrite
  (dir-symlinks recorded, never descended; node_modules excluded) +
  `mirror_source_tree` dir-symlink replication (lexical dst
  exclusion). Tests: `test_lease_tripwire_symlinks.py` 5/5 +
  3 mirror tests in `test_integration_dialectic.py`. Real-tree
  manifest: 1613 entries, 0 node_modules, no ELOOP.
- green_path proof FIXED + PASS (4:06 doc-exact). Root cause (proven
  1:1 in a manual lease mirror): the in-lease mandatory set ran
  38 passed + 2 skipped (f3c + fix_shape workspace guards),
  violating the 0-skip gate invariant. Fix is test-local, no
  product/contract/invariant change: f3c resolves the pin from
  STC_PROMPT_KIT_ROOT when no sibling checkout exists (rev-parse
  vs pin for clones, blob-hash vs extract files for extracts;
  skip preserved when neither exists); fix_shape looks up the
  preserved prompt tree-relative. Ambient behavior byte-identical
  (mandatory set 40/40 before and after). "Stale node-ID" seen
  earlier was a truncated display name, not a missing test.
- Pin-form correction: `prove_import_integrity` requires clone-form
  pins; `STC-INDEPENDENT-VERIFY.md` §2 provision corrected from
  `git archive` extracts to detached clones at exact pins
  (SST 079f4de6fd43…, prompt-kit 4f442a6c829b…; both resolve in
  siblings and match EXTERNAL_PINS), with clean-tree checks.
  §2 env amended (+STC_SST_ROOT/STC_PROMPT_KIT_ROOT/MYPYPATH/
  MYPY_CACHE_DIR). mypy count 82→83 (tripwire module).
- dag x4 LANDING-BLOCKED (not fixable in the working tree): N10
  allocates git worktrees from main-branch content and gates it;
  main is mypy-red in the authoritative pins env (3 stale
  unused-ignores: cli.py x2, test_run_e2e x1 — prompt-kit pin is
  typed, the ignores went stale). Proven on a clean HEAD
  worktree (3 errors, nothing else). Minimal landing: remove
  the 3 ignores. Commit decision escalated (T9); no history
  written by this tranche.
- live x1 QUOTA-BLOCKED (external): `test_live_cli_node` — operator
  codex login present, usage limit exhausted; fails honest and
  closed ("Remediation: Check harness availability and retry").
- rollback-check default bug fixed (STC default parents[1]→parents[2];
  the old default doubled the path and failed without STC_ROOT):
  PASS with no env now.
- Fast surface re-verified after all edits: ruff check+format green
  (188); mypy strict 0 errors / 83 files; plugin units 95/95;
  e2e 16/16 (7+3+2+3+1); probe 6/6; boot PASS; journey green;
  rollback PASS; rescore byte-identical; checker 11/11; policy
  default PASS. $0 spent.
- T8 independent verification round 1 (subagent, §§1-6, logs at
  /tmp/stc-verify-logs/): §1 mypy 0/83, §3 (95 + e2e 16 + probe 6),
  §4 (boot/journey/rollback), §5 (rescore b1 3/3 b2 2/3 + checker
  11 + policy), §6 COMPATIBLE — all CONFIRMED green. §2
  CONTRADICTED the predicted 5-red: 12 failed / 691 passed. New
  findings: (a) suite-wide import poisoning — test_exec_harness.py
  collection-time sys.path.insert(0, siblings) shadowed the pins,
  failing ambient f3c + green_path prove in full-suite runs
  (targeted runs were clean); (b) H1 package staleness tripwire
  fired — tranche shifted dialectic_runner.py line numbers;
  (c) 4 more live nodes fail on quota/network (env).
- Rework (T1): (a) exec_harness uses STC_*_ROOT-first + append
  (proven both ways: old code fails paired f3c, new passes);
  (b) H1 re-pinned mechanically to the same semantic anchors
  (spans verified byte-identical at HEAD; payload diff = 6 label
  lines only; 4044 B, new sha, artifact + provenance updated);
  (c) verify-doc §2 deselects live per D13 (`-m "not live"`)
  with an informational live leg. Full §2 re-run (`-m "not live"`,
  /tmp/stc-s2-rework.log): 4 failed, 693 passed, 6 deselected in
  46 min — exactly the predicted terminal state (only dag x4,
  landing-blocked). Poison + H1 fixes confirmed in full-suite.
  Tree clean after the run (no shm/wal/pyc pollution).
- Minimal landing 78a3448 (2026-10-04, operator-authorized): exactly
  the 3 stale unused-ignores (cli.py x2, test_run_e2e x1); staged
  diff verified 3+/3- before commit; all other tranche work left
  uncommitted. New HEAD proven mypy-clean in a scratch worktree
  (gate argv, 80 files) before the suite re-run.
- §2 post-minimal (/tmp/stc-s2-postmini.log): exit 0, 697 passed,
  6 deselected in 39 min — FULL GREEN on the gate set (dag 13/13).
- T8 round 2 (fresh subagent, logs /tmp/stc-verify2-logs/):
  candidate identity matched exactly (HEAD 78a3448 +
  tracked-diff sha 23f46eac…, tree unchanged end-to-end);
  verifier rebuilt DSH byte-identical + re-provisioned pins.
  §1 green (ruff 188, mypy 0/83); §2 RC 0, 697/6 (dag re-run
  13/13); §3 (95 + e2e 16 + probe 6); §4 PASS/GREEN/PASS;
  §5 rescore IDENTICAL + checker 11 + policy PASS; §6
  COMPATIBLE. Verdict CONTRADICTED on one letter-only item:
  §2-live went 5 env-fail + 1 PASS (test_live_handshake_-
  binaries_probe — zero-quota binary-availability probe, no
  model call). All 5 model-calling live nodes env-failed
  (quota/network). Live-model checks remain UNQUALIFIED, not
  passing; D13 scope preserved (live deselected in gates).
  (Verifier's first plugin-units run hit 3 path-sensitive
  failures from its own /tmp copy of the plugin; rerun from
  the tree 95/95 — methodology artifact, not product.)
- Full-tranche landing (this commit): everything above + the
  remaining tranche (manifest in commit message). Deliberately
  NOT landed, preserved untracked: 6 nested evidence git repos
  (raw-batch/*/repo — un-landable gitlinks, required present
  for §5; dsh-home/ + sail.patch.yml + rescore-v1.json landed),
  assignment/context pastes (ANIMA-*, STC-COORDINATOR-PROMPT*),
  working notes (docs/plans/, docs/progress_logs/,
  docs/prototype-dsh-workspace/). Verified candidate =
  landed bytes + these preserved untracked paths.
- Post-landing confirmation (2026-10-04, uncommitted record delta):
  main @ c1bd60a (191 files, +18097/-59, zero gitlinks); pins
  untouched (SST 079f4de6 + prompt-kit 4f442a6c, exact HEAD,
  clean). Post-landing §2 (/tmp/stc-s2-landed.log): exit 0,
  697 passed, 6 deselected in 35 min — N10 gates the full
  tranche on main, green_path on the new base. Tracked tree
  clean after the run; 12 intended untracked paths preserved.
  Exclusions (accepted, D13 scope): 6 live nodes deselected —
  1 binary-availability probe passes (no model call), 5
  model-calling nodes quota/network-blocked, UNQUALIFIED not
  passing. Outstanding requirements (NOT established by this
  milestone): browser-pixel walkthrough, durable-home migration
  execution, live-model SST consumption (SST owner version +
  budget), budgeted quality batch.
- Push-to-completion probes (2026-10-04, uncommitted): both staged
  browsers crash at render (chrome-headless SIGTRAP, firefox
  segfault) — walkthrough stays operator-side. SST sibling moved
  to df78f42 (clean, run_search present); probe DIRTY-vs-old-pin
  as expected. Wrote docs/STC-LIVE-READINESS-PACKET.md
  (identity/acceptance/cost/caps/stops); refreshed flash pricing
  (unchanged: $0.30/$1.20 peak, half off-peak). Fixed stale
  release-doc counts (95/16/6, mypy 0/83). Pending delta for next
  window: packet (new) + release fixes + this appendix.
- SST cand-02 adoption (2026-10-04, contract §4): SST owner handoff
  docs/STC-HANDOFF.md @ df78f42894a65c48f524337a498032617689a013
  (sibling clean at same HEAD; UI + honest budgets + live-qualified
  claimed). STC staged per §4 (record → probe COMPATIBLE
  pin=df78f42894a6 run_search=True → suite + e2e + caller exercise →
  amend): EXTERNAL_PINS/P00_PINS/SST_PIN_DEFAULT →
  df78f42894a65c48f524337a498032617689a013, contract rev
  INT-2026-10-04.1, verify-doc pin path sst-pin-df78f42. Caller-side
  honest-budget fixes (STC-owned): veto Rule 0
  explicit-critique-failed on CRITIQUE_FAILED verdicts (new SST
  discloses critique failure instead of fabricated APPROVE);
  gateway cost_known=True only for provably-$0 backends
  (manual/mock; codex/exec stay unknown → USD caps fail closed,
  UnpricedCostBudgetError preserved); elapsed-budget test recalibrated
  to binding task budgets (600s ctx); 3 committed caller-exercise
  tests (real CLI gateway: named+cap completes, unnamed+cap raises,
  run_search surface). Repins: H1 4061 B sha84ed6531 (3-line exact
  diff, budget holds); A3 attempt-2 diff rebased to new base
  (applies clean, new diff+file_operations hash form); H1 §4 +
  helper params verified byte-exact. Memory curation: pin advance
  tripped staleness on 2 sst-custody seed entries (079f4de6 strict
  ancestor of pin) — verified against df78f42 custody.py:335-348,
  368-369 that BOTH claims inverted (custody now runs EVERY command,
  empty fails closed); revised in place with fresh as-of + dated
  curator note, test pins updated. Round-3 §§1-6 on the final tree:
  §1 ruff check+format green (189 files), mypy strict 0/83; §2
  701 passed / 6 deselected RC=0 in 38:41
  (/tmp/stc-s2-newpin3.log); §3 plugin 95/95, e2e 7+3+2+3+1=16/16,
  probe 6/6; §4 boot PASS, journey 13/13, rollback PASS; §5 rescore
  identical (minus batch path), checker 11/11, policy PASS; §6 probe
  COMPATIBLE. $0 spent. Anomalies (all diagnosed, none product):
  first §2 voided after operator-side session confusion + concurrent
  e2e load (confinement false-breach from a concurrent rescore .pyc
  proven in lease record); dag json_mode red without MYPYPATH (env
  error, green with doc env); circuit_breaker once red in-suite,
  green standalone + in-group + in final run (transient 9p/git
  latency; bare worktree-add p50 ~20s vs 30s timeout, 13 samples
  18-22s); demo-manual-task once crashed (run_dir ENOENT between
  adjacent writes, no deletion path in code) under full concurrency,
  green alone with pristine pins. Left visible: browser-pixel
  walkthrough, durable-home migration execution, live-model SST
  consumption + budgeted quality batch (readiness packet).
- Round-4 verification (2026-10-05, final candidate
  7e722260ed1b9557dc763cf8efe3691a49a60ab5): tranche 5470d4e
  (spawn-boundary pin env + tripwire/mirror parity + H1 repin + batch
  tasks) → f3fa42f (N12 outer-snapshot prune fix: _walk_dir scandir
  walk, faulthandler-proven 30+min rglob hang on 5.2G .durable) →
  7e72226 (top-level-only skip application in mirror + snapshot +
  H1 repin 4061 B sha383c474f, spans ≥455 +6, tag-only, verbatim
  verified). Round-4c ALL GREEN on 7e72226: §1 ruff + mypy strict
  0/83; §2 709 passed / 6 deselected RC=0 in 29:09; §3 plugin 99/99
  (doc expectation updated 95→99: tranche added backendEnv tests),
  e2e 7+3+2+3+1=16/16, probe 6/6; §4 boot PASS, journey 13/13,
  rollback PASS; §5 rescore IDENTICAL, checker 11/11, policy 10
  PASS; §6 COMPATIBLE pin=df78f42894a6. Round-4b VOIDED by the R4B
  mirror regression (every-level skip emptied nested
  docs/.../dossier evidence → real-gates green path red via
  test_embedded_bytes_match_dossier in-lease; fixed by
  top-level-only skip + dispatch depth-0 pruning + unpruned .git
  subset + 6 new regression tests: mirror nested-preservation,
  snapshot bound 10, parity, skip-named-file caught, blind-spot
  pinned top-level, nested-evidence caught end-to-end).
  Round-4d VOIDED by a KNOWN transient (git worktree-add 30s
  timeout under full-suite 9p load; green standalone 81s).
  Round-4e VOIDED by stale LOCKED worktree registrations from
  killed runs + /tmp wipe (N10 "missing but locked"; second test
  the known timeout; both green standalone post-cleanup 2:56;
  worktree list left clean). Round-4f GREEN on retained
  post-wipe evidence: §1 ruff + mypy 0/83; §2 709/0 RC=0 in
  27:41 (/tmp/stc-verify-suite-r4f.log); §3 99/99 + 16/16 + 6/6
  (DSH_CHECKOUT=.durable/dsh, content-clean @639ed01 — 14k
  status entries all mode-change artifacts 100644→100755, zero
  content diffs; /tmp/toolchain + /tmp/dsh-upstream + pnpm store
  recreated as symlinks; e2e purge-prompt was fresh-/tmp pnpm
  state, gone with durable env); §5 IDENTICAL + 11/11 + 10;
  §6 COMPATIBLE. §4 carried from 4c (boot PASS, journey 13/13,
  rollback PASS on identical code): post-wipe rerun
  environmentally blocked — full-server boots stall (0 lines /
  10min detached, 5 bundle lines / 280s foreground, port closed)
  under 9p collapse measured at ~400KB/s sustained (712M / 30min
  copy; cf. ~20s worktree-add p50 earlier). One stray detached
  debug server may linger (unkillable across pid namespaces;
  DSH_HOME=/tmp/stc-boot-debug5; dies on reboot; port 3080
  verified closed). No code path under §4 changed since its
  green; this is a qualified carry, not a silent pass.
- §125 prerequisites closure (2026-10-05): browser walkthrough
  §§1-6 green with 5 filed deviations (D-W1..D-W5: 4 low, 1
  negligible) + 3 open sub-items (STC row pixels, card-title
  transitions, active-job resume) — see walkthrough observations;
  durable-home migration executed (repeatable boot + rejoin +
  store reads from .durable/stc/homes/walk; credentials-path
  finding in release doc); live-model SST consumption qualified
  (runs 3-4 real gates no-champion; run-2 champion UNQUALIFIED
  fake gates; 0 champions ever is an SST-side outcome — STC
  consumption path qualified); budgeted quality batch 18/18
  $0.03. Pins: SST df78f42894a65c48f524337a498032617689a013,
  prompt-kit 4f442a6c829bc06b60f9979fdc8d7585e30bac9a, DSH
  639ed015397290b3745d163aafe02ffee4aa3f84, node 22.23.3,
  pnpm 11.7.0. Spend: metered ≈$0.08 (pilot $0.01 + batch $0.03
  + SST runs $0.035) + 12 unmetered flash browser turns, all
  within the HARD $10 cap with large headroom. Left visible:
  SST cand-02 owner blessing unconfirmed; CI unrunnable (no
  remotes); live-marked tests env-blocked per D13; dossier/
  absent (gitignored runtime output; regenerates); /tmp wiped
  2× (DH-home transcript + runs survive; screenshots lost,
  observed-live descriptions retained). Forward, explicitly
  open: Windows-verifier joint run for the two optional
  residuals, pending backend servability (handoff prepared;
  not an acceptance blocker).
