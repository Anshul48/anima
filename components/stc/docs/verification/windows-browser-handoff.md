# Windows browser handoff (STC verification)

Scope: forward browser verification of two OPTIONAL residuals (see
acceptance-closeout §2). Not an acceptance blocker. STC is Linux-only;
Windows acts as browser client + visual verifier only.

## Frozen identities

- STC code: `7e72226`, tree `dd4c682fd61b3b2a8fe26e6722fd811bb788874c`
  (release commit `c77fbc1` adds docs only).
- Deps: SST `df78f42894a65c48f524337a498032617689a013` (pristine
  `/tmp/sst-pin-df78f42`, reprovisionable from `../sst`);
  prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`
  (`/tmp/prompt-kit-pin-4f442a6` from `../prompt-kit`); DSH
  `639ed015397290b3745d163aafe02ffee4aa3f84` (`.durable/dsh`,
  content-clean); node v22.23.3 + pnpm 11.7.0
  (`.durable/toolchain`, `corepack-home` + `pnpm-store` inside).
- Config: STC dev overlay `dsh-plugin-stc/cordis.dev.yml`
  (sha256 `2cfc2197…d12cc`); packaged bundle
  `dsh-plugin-stc/cordis.bundle.yml` (sha256 `57824e9f…7914da02`).
- Linux runtime: WSL2 Ubuntu 24.04.3; DSH_HOME under
  `.durable/stc/homes/` (see release doc § mode-less filesystems
  for the credentials-path requirement on 9p).

## Endpoint + access (PRECONDITION — READ FIRST)

The Linux backend is NOT currently servable: full-server boots stall
under host 9p degradation (measured; see closeout §4). Do not attempt
browser verification until the coordinator confirms a live endpoint.
When servable, the endpoint is `http://127.0.0.1:PORT/?token=...`
(token printed at boot; reachable from Windows via WSL localhost
forwarding). Private access = the per-boot token URL, delivered
directly to the verifier (never committed).

## Verification home/store + sessions

- Dedicated home: a fresh `DSH_HOME` (isolated per run); run store
  `$DSH_HOME/stc-runs`.
- Retained references (dilemma session c322bb34… in
  `.durable/stc/homes/walk`): run f003fdd456ef (manual choice=1,
  NEEDS_REPAIR), run 34b28039f7c6 (killed SIGTERM), runs
  cc9f16b5e6d4 + 95c32f0d50ef (follow-ups).

## Checklist (optional residuals only)

1. Packaged-install STC row: `plugin add file:` the built bundle,
   open Plugins, screenshot the STC row + open row detail.
   (Dev-overlay boots never render a row — by construction.)
2. Card titles: during any stc_preview/stc_run turn, screenshot a
   pending→completed tool-call card transition + any progress
   streaming.
3. Expected: rows/cards render with correct titles; no error toasts;
   behavior matches the accepted walkthrough observations.

## Budget + provider-call controls ($10 aggregate, unchanged)

- Remaining: $1.92 conservative (≈$9.40 realistic). Shared across
  all agents; the Linux coordinator is the budget owner.
- Verifier calls must be $0 pixel checks (no model turns) unless the
  coordinator explicitly approves a paid turn. Flash tier only.
  Stop and report on any unexpected charge, auth failure, or quota
  error. Never expose `.env` credentials; never commit the token URL.
- Receipt: the verifier writes its evidence receipt (screenshots +
  per-item verdicts) to an agreed shared path and notifies via
  available agent messaging; no human relay for routine details.
