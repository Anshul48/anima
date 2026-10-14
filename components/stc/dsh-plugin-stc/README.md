# @stc/dsh-plugin-stc

STC execution + verification capabilities as a genuine DeepSeek Harness
plugin bundle. No DSH fork: upstream `dsh` boots, this bundle mounts beside
the others via profile layers.

Upstream pin: DSH `639ed01` (v0.2.0-rc.2) — see `docs/STC-DSH-RECORD.md`.

## Layout

- `src/index.ts` — the SINGLE loader entry: composes hello/tools/run/policy
  as Cordis fibers. (DSH's client-modules registry allows exactly one active
  loader row per package; one row per module fails startup.)
- `src/hello.ts` — load-probe plugin (prints on boot; proves entry works).
- `src/stc-tools.ts` — `stc_ping`, `stc_dossier` (read-only), `stc_preview`
  (exact argv via quota-free probe).
- `src/stc-run.ts` — `stc_run` (background job via `ctx.jobs`), `stc_status`,
  `stc_log`, `stc_cancel` (SIGTERM→SIGKILL).
- `src/stc-policy.ts` — `tools/pre-execute` launch gate (typed `RUN`
  confirm, exec-exe checks, mode allowlist).
- `src/dossier-read.ts`, `src/stc-exec.ts`, `src/stc-runstore.ts`,
  `src/stc-guard.ts` — pure logic, `node --test` covered.
- `src/stc-present.ts` — card presenters (`presentCall`/`presentResult`/
  `presentationMeta` per tool, tool-fs pattern): pending titles, completed
  cards, replay-safe meta on tool/result events. Rendered by DSH's native
  tool node — no custom node kinds, no client changes.
- `lib/index.js` — built bundle (esbuild; gitignored, build before install).
  Packaged installs MUST load this: Node refuses to type-strip `.ts` under
  `node_modules`, so `.ts` entries never activate from an install.
- `scripts/stc_probe.py` — venv probe quoting backend builders (6 pytest).
- `cordis.bundle.yml` — release bundle patch (exactly one row).
- `cordis.dev.yml` — generated dev overlay (absolute path; do not commit).

## Build (required before packaged install)

```sh
cd dsh-plugin-stc
pnpm install --frozen-lockfile   # esbuild, pinned in pnpm-lock.yaml
pnpm build                       # emits lib/index.js (+map)
```

Dev-only: unit/e2e sources import `@deepseek-ai/dsh-tools` (host
external, never bundled). After any fresh `pnpm install` (which
purges gitignored `node_modules`), re-link it to the scratch DSH
checkout before running tests:

```sh
mkdir -p node_modules/@deepseek-ai
ln -sfn /tmp/dsh-upstream/packages/core/tools node_modules/@deepseek-ai/dsh-tools
```

## Dev loop (needs a built DSH checkout + node 22 + pnpm)

```sh
sh scripts/gen-dev-overlay.sh    # regenerate cordis.dev.yml (single row)
# from the DSH checkout (both forms verified):
pnpm dsh web --patch /abs/path/to/stc/dsh-plugin-stc/cordis.dev.yml --no-open
pnpm dsh --profile web --patch /abs/path/to/stc/dsh-plugin-stc/cordis.dev.yml --no-open
```

Terminal must print `[stc-bundle] STC bundle composed …` plus the four
`[stc-*]` registration lines during startup. Dev loads the TS source
directly (type-stripped; allowed outside `node_modules`).

## Release install

```sh
export DSH_HOME=/abs/path/to/isolated-dsh-home   # always explicit; never ~/.dsh silently
cd dsh-plugin-stc && pnpm install --frozen-lockfile && pnpm build
dsh plugin --profile web add file:/abs/path/to/stc/dsh-plugin-stc
```

`plugin add file:` COPIES the directory: rebuild + reinstall after every
source change. Sandbox note: inner pnpm needs `XDG_DATA_HOME` (store),
`XDG_CACHE_HOME`, and `COREPACK_HOME` redirected to writable paths.

## Tests

- Unit (no DSH checkout needed): `node --test tests/*.test.ts`
  (44 tests: dossier reads, probe bridge, runstore, launch guards,
  policy registry + theoracle, packaging contract, card presenters).
- Mechanics battery (needs a built DSH checkout):
  `SPEC_FILE=policy-battery.e2e.spec.ts POLICY_RESULTS=out.jsonl sh scripts/run-e2e.sh <dsh>`
  then `node policy/score.ts out.jsonl b1-direct`.
  Measures launch/verify/evidence/recovery mechanics quota-free —
  NOT model task quality (that needs the live batch).
- Probe (needs STC venv): `pytest operator-console/tests/test_stc_probe.py`
  (6 tests, quota-free).
- E2E (needs a built DSH checkout + node 22 + pnpm on PATH):
  `sh scripts/run-e2e.sh /path/to/deepseek-harness`
  (7 scripted-model episodes through the real agent loop, quota-free;
  the spec is copied into the checkout, run, and removed; one episode
  asserts presentation meta on tool/result events).
- Real-task demo (same requirements):
  `SPEC_FILE=demo-manual-task.e2e.spec.ts sh scripts/run-e2e.sh /path/to/deepseek-harness`
  (coordinator-assisted manual-mode repair task + follow-up run through
  the real agent loop; asserts the workspace journey + evidence, locks
  the diagnosed NEEDS_REPAIR backend outcome as a tripwire).
