# STC-on-DSH release: install / startup / verify

Repeatable release instructions for the local-production envelope
(single-user Linux/WSL, loopback browser). All paths below are examples;
`DSH_HOME` must always be explicit — never `~/.dsh` silently.

## Pins (release candidate)

Machine-readable pin file: `dsh-plugin-stc/DSH_PIN`.

| Component | Pin | Evidence |
|---|---|---|
| Upstream DSH | `639ed01` (v0.2.0-rc.2) | `dsh --version`, record |
| Node | v22.23.3 (SHA256-verified tarball) | toolchain probe |
| pnpm | 11.7.0 (corepack) | `pnpm --version` |
| esbuild (bundle build) | 0.28.2 (`dsh-plugin-stc/pnpm-lock.yaml`) | lockfile |
| STC backend | this checkout (`git rev-parse HEAD` at install) | dossier `base_commit` |
| SST (deliberate pin) | `df78f42894a6` (full hash in `docs/STC-SST-CALLER-CONTRACT.md`) | compat probe + dossier |
| prompt-kit (deliberate pin) | `4f442a6c829b` (full hash in caller contract) | import-integrity test |

## Locations

Canonical durable layout (user-owned WSL): `~/dsh` (checkout),
`~/.local/share/stc/toolchain`, `~/.local/share/stc/homes`,
`~/.local/share/stc/runs`. Migrate with
`dsh-plugin-stc/scripts/migrate-durable.sh` (idempotent, verifies each
step; needs home writes). Until migration runs, `/tmp/toolchain`,
`/tmp/dsh-upstream`, `/tmp/dsh-home*` remain the working scratch.

## Install

```sh
# 1. Toolchain: node 22 + pnpm on PATH (verify: node --version, pnpm --version).
# 2. DSH checkout at the pin, then:
cd /path/to/deepseek-harness
pnpm install --frozen-lockfile
pnpm run build
# 3. STC bundle build:
cd /path/to/stc/dsh-plugin-stc
pnpm install --frozen-lockfile
pnpm build            # emits lib/index.js (required: packaged installs load JS)
# 4. Dependency pins (required: `run --target stc` imports both):
git clone <sst-remote> /path/to/sst-pin && git -C /path/to/sst-pin checkout -q <sst-pin>
git clone <prompt-kit-remote> /path/to/prompt-kit-pin && git -C /path/to/prompt-kit-pin checkout -q <prompt-kit-pin>
# 5. Isolated harness home + plugin install:
export DSH_HOME=/path/to/isolated-dsh-home
dsh plugin --profile web add file:/path/to/stc/dsh-plugin-stc
```

Sandbox caveats (this environment only): the DSH `build` needs the
`node_modules/.bin/tsx` → `node --import tsx/esm` shim (AF_UNIX EPERM;
orig kept as `tsx.orig`); inner pnpm needs `XDG_DATA_HOME`,
`XDG_CACHE_HOME`, `COREPACK_HOME` redirected to writable paths; unset
all proxy vars (`no_proxy='*'`) for loopback checks.

## Startup

```sh
export DSH_HOME=/path/to/isolated-dsh-home
export STC_ROOT=/path/to/stc                 # backend root for stc_* tools
export STC_DSH_STORE=$DSH_HOME/stc-runs      # durable run store (default under DSH_HOME)
export STC_SST_ROOT=/path/to/sst-pin         # required: absolute pinned SST checkout
export STC_PROMPT_KIT_ROOT=/path/to/prompt-kit-pin  # required: absolute pinned prompt-kit
dsh web --no-open                            # prints the token URL; both
# dsh --profile web --no-open                # forms verified equivalent
```

Dev iteration instead of packaged install:

```sh
cd /path/to/stc/dsh-plugin-stc && sh scripts/gen-dev-overlay.sh
dsh web --patch /path/to/stc/dsh-plugin-stc/cordis.dev.yml --no-open
```

`plugin add file:` COPIES: after any bundle source change, `pnpm build`
and reinstall (or re-resolve) before the running server sees it.

### DSH_HOME on mode-less filesystems (9p/WSL mounts, some NAS)

`credentials-local` fail-closes boot when `$DSH_HOME/.credentials.yaml`
is group/other-readable, and `chmod` is a no-op on mounts that don't
store POSIX modes (observed: 9p reports 777; first boot succeeds only
because the file is still absent, every later boot fails). Supported
layout: keep `DSH_HOME` on the durable path and relocate the document
to a mode-capable filesystem via the plugin's `path` config:

```yaml
- id: credentials
  config:
    path: /tmp/stc-creds/.credentials.yaml   # 0600-capable dir; re-provisioned per host
```

(Verified 2026-10-05: repeatable boots, migrated sessions + run
store served from the durable home, credentials provisioned at the
patched path with mode 600. Do not migrate `.credentials.yaml`
between homes — secrets re-provision, sessions/runs migrate.)

## Verify (acceptance smoke, quota-free)

```sh
node --test tests/*.test.ts                                 # dsh-plugin-stc: 99/99
pytest operator-console/tests/test_stc_probe.py -q          # 6/6
sh scripts/run-e2e.sh /path/to/deepseek-harness             # 7/7 bundle (+3+2+3+1 specs)
```

Boot checks (fresh `DSH_HOME`): log shows `[stc-bundle] composed` plus
all four `[stc-*]` registrations with no `did not activate` / `startup
failed`; token URL → 303 → cookie → 200 with `@stc/dsh-plugin-stc`
boot-graph entries and a 200 `/plugins/??` combo containing `stcBundle`;
untokened root → 401.

## Limits (explicitly unqualified)

- In-browser mount / pixel walkthrough: headless Chrome SIGTRAPs under
  this sandbox's seccomp; needs an operator-side or unsandboxed run.
- Live-model behavior + delivery-policy quality ranking: needs the
  budgeted live batch (see `docs/STC-LIVE-BATCH-PROPOSAL.md`).
- Backend gates at release: `mypy --strict src tests` 0 errors / 83
  files; backend suite 709 passed / 6 deselected (live per D13);
  ruff check+format clean (189 files).
