# STC → genuine-DSH workspace: gap analysis and alternatives

Date: 2026-09-29. Evidence: 5 recovered audit payloads (`/tmp/child-*.json`),
upstream DSH @ `639ed01` (v0.2.0-rc.2) inspected at `/tmp/dsh-upstream`,
coordinator mandate `docs/STC-COORDINATOR-PROMPT.md` (§N refs below).

## 1. Current state, separated

**Intended (legacy plans):** DSH-*inspired* operator surface over a closed
backend harness world, preview-then-launch, dossier read model
(`docs/plans/2026-09-27…:3-5`, `docs/plans/2026-09-24…`).

**Implemented (verified bodies):** stdlib `ThreadingHTTPServer` console
(`operator-console/server.py:96,184-335`), hp-1 harness plugins + `harnesses.d`
discovery + quota-free handshakes (`harnesses.py:156-244,397-728`), preview
quoting backend builders (`harnesses.py:736-784`), token-bound launch
(`server.py:561-583`, `lab.py:218,350-388`), one-run-at-a-time lifecycle with
cancel (`lab.py:433,463,519`), `--exec-harness` backend flag (`src/stc/cli.py`
+54/−2, `exec_harness.py`). 83 console + 10 exec-harness + 36 CLI tests.

**Reproduced (this env):** console suite 82/83 in 460 s (1 load flake in
`test_http_smoke_lists_registered_run`, passes isolated + file-level);
`cli.py` diff matches HANDOFF §5; DSH README/architecture fetched; DSH
cloned; node v22.23.3 + pnpm 11.7.0 provisioned and verified.

**Unverified:** live-provider runs (by design, quota-free so far); browser
rendering of anything (no browser tooling yet); DSH build/run from source.

## 2. Gaps to the mandate

- **G1 — Not genuine DSH.** Zero upstream DSH/Cordis imports (grep-clean);
  self-labeled "DSH-inspired" (HANDOFF:10, plan :3-5). Mandate §13 requires
  upstream DSH + real Cordis, pinned and runtime-verified.
- **G2 — No build-anything workspace.** No conversation, brief, decisions,
  projects/sessions, previews, diffs, or deliverables — only dossier screens
  + launch lab. Mandate §11, §50-52.
- **G3 — No autonomous execution semantics.** Cancel-only; no pause/redirect/
  resume, no interruption recovery, no durable sessions. Mandate §51-53.
- **G4 — No delivery policy / discovery lane.** Single entry point
  (`stc run --target stc`), one-run-at-a-time, no versioned policies,
  baselines, or promotion controls. Mandate §17-20, §34-44.
- **G5 — Unqualified envelope.** No browser QA, no budget/credential/isolation
  evidence, no upgrade/rollback story. Mandate §62, §69.
- **G6 — Governance conflicts (docs audit C1-C5).** Legacy read-only/manual-
  first constraints (2026-09-24 Constraints, KD-1..KD-4) directly contradict
  §50-56 autonomy; stdlib-only preference contradicts the Node/pnpm DSH
  stack. Resolution: legacy console constraints retire with the console;
  backend authority boundaries (scheduler/verdicts/receipts/dossiers stay
  backend-owned) are preserved and re-expressed as plugin policy.

## 3. Mechanisms to preserve

Preview-then-launch with typed confirmation; preview-token/exe binding;
handshake-before-run; backend-entry-point-only spawning with cwd=backend root;
dossier/spend/qa-log read contracts (`dossier.py:36-50,53-103,143-232`);
frozen Pydantic membranes; fail-closed gates; `mock`-is-simulated labeling.

## 4. Upstream DSH extension surface (inspected)

- Tools: `ctx.tools.register(defineTool({…execute…}))`, effect-unregistered
  on unload; background jobs via `ctx.jobs.start` (`adding-a-tool.md`).
- Policy: `tools/pre-execute` waterfall gates, `ctx.tools.guard()` monotonic
  deny, `tools/execute`/`post-execute`/`result` observation
  (`extension-cookbook.md`).
- UI: `session/event` durable records + `agent/assistant-stream` frames;
  business rows in the built-in Web Client via `ConversationNodeDefinition` +
  keyed Chat renderer (`subsystems/conversation.md`).
- Composition: profiles (`web/headless/sdk/sdk-minimal/acp`) = ordered
  bundles + `cordis.patch.yml` layers + `--patch` overlays; external bundles
  via `dsh plugin --profile add file:…`; introspect with
  `dsh --profile web --dump-config` (`architecture.md`, `python/sdk/README.md`).
- Python SDK: `deepseek-harness-sdk` drives bundled `dsh --profile sdk` over
  stdio JSON-RPC; explicit `dsh_home` required; `sdk-minimal` standalone tree.
- Pins: `639ed01`, root 0.2.0-rc.2, pnpm 11.7.0, node ^22.19||>=24.

## 5. Alternatives

### Alt A — DSH-native workspace + STC plugin bundle (recommended)

Run upstream `dsh web` as the front door. STC ships a `dsh-plugin` bundle:
tools (`stc.spec`, `stc.preview`, `stc.run`, `stc.dossier`, `stc.cancel`),
`pre-execute` policy gates (budgets, approvals, destructive-op boundaries),
and ConversationNode renderers (brief, acceptance criteria, progress,
decision, diff, evidence cards). STC Python stays authoritative for
execution/verdicts/dossiers via the existing `stc run` child-process bridge.
Delivery policies = versioned bundle+patch compositions; experiments run
headless/sdk profiles with patch overlays; promotion = versioned bundle
release + patch promotion, candidates unable to touch authoritative eval.

Journey: open `dsh web` → STC workspace → describe outcome, attach repo →
brief + acceptance cards → autonomous execution with progress cards →
decision card (redirect/approve) → runnable preview + diff + evidence →
refine → handoff. Interruption: durable DSH sessions + STC run records
resume without repeating side effects.

Tradeoffs: most faithful to §13 ("start from the DSH experience, extend");
inherits DSH conversation/sessions/sandbox/approvals; Node+Python two-stack
cost; tracks a developer-preview upstream (breaking changes; pin + patch).

### Alt B — STC-orchestrated, DSH-as-engine via Python SDK

STC keeps the outer loop (trias/DAG/judiciary); DSH runs headless per task
(`sdk`/`sdk-minimal`) as the worker brain with per-policy patch
compositions. Workspace UI is STC-owned, consuming DSH JSON-RPC events.
Genuine DSH runtime (bundled binary, verified identity), but DSH is an
engine, not the experience.

Tradeoffs: maximal STC authority reuse; policy experiments cheap in Python;
but contradicts "start from the DSH experience", rebuilds conversation/
session/UI in STC (replacement-shell risk), and splits product coherence.

### Alt C — Thin DSH shell over fixed STC pipeline

STC's dialectic/DAG pipeline exposed behind a versioned policy API; `dsh web`
is purely conversational with one thin `stc.run` tool; discovery lane lives
in STC Python. Minimal DSH extension, fastest to demo.

Tradeoffs: conversation and execution visibility split across two systems;
weak autonomous-progress story; workspace gravity pulls back into STC-owned
UI (G2/G3 regress). Viable fallback if Alt A hits a concrete upstream
incompatibility (§13 procedure: reproduce, then smallest choice).

### Delivery-policy options (experiments will select)

P1 event-driven ACI loop (OpenHands/SWE-agent: step() over event history +
condenser + security gate); P2 fixed localize→repair→validate (Agentless,
32.0% SWE-bench Lite @ $0.70); P3 manager-guided tree search (AI Scientist-v2).
Baselines first: simple single-agent, existing STC workflow (§36-44).

## 6. Recommendation and decision packet

Recommend **Alt A**. Reversible choices taken: DSH pin `639ed01`;
`/tmp/dsh-upstream` + `/tmp/toolchain` as scratch (durable install path TBD);
legacy console retained read-only until Alt A qualifies, then retired.

Choices needing the operator (one packet, defaults marked *):
1. Live-model budget for experiments: none authorized → quota-free
   implementation + a bounded live batch proposal later (*default: defer*).
2. Durable toolchain/home locations: `/tmp` is scratch; propose
   `~/.local` + `~/.stc-dsh` at release time (*default: approve at release*).
3. DSH breakage policy: pin + patch on upstream drift (*default: yes*).

No aesthetic review required before the prototype; UI direction stays
reversible until qualification.
