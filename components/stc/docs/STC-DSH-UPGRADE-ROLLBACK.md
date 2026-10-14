# STC-on-DSH: upgrade + rollback

No DSH fork: STC rides upstream via version pins + Cordis patch layers
(`cordis.bundle.yml`, `--patch` overlays). Upgrades move the pins;
rollbacks restore them. Nothing in the procedure rewrites history.

## Upgrade (DSH pin move)

1. Record the current pin (`git -C <dsh> rev-parse HEAD`) and the last
   green verification (record § + date).
2. `git -C <dsh> fetch origin && git -C <dsh> checkout <new-pin>`.
3. `pnpm install --frozen-lockfile && pnpm run build` in the checkout.
4. Rebuild the bundle (`pnpm build` in `dsh-plugin-stc`) — no source
   change expected, but the loader contract is re-verified, not assumed.
5. Fresh `DSH_HOME`: packaged install → boot → acceptance smoke
   (`docs/STC-DSH-RELEASE.md` §Verify). Compare against the previous
   pin's recorded evidence (row count, boot markers, HTTP codes/sizes,
   unit/e2e counts).
6. On green: update the pin table (release doc + record) with the new
   commit, date, and verification evidence. On red: follow §Rollback,
   then triage per plan §13 (Alt C fallback procedure) before adopting.

STC-backend upgrades are independent (this repo's own tests + dossier
`base_commit` pins the bytes each run executed against).

## Rollback (DSH pin or bundle)

- DSH: `git -C <dsh> checkout <previous-pin>`, rebuild, reinstall the
  bundle into a fresh `DSH_HOME` (or keep the previous `DSH_HOME`
  untouched during upgrade trials so rollback is just a restart).
- Bundle only (preferred): wipe the trial `DSH_HOME` (or keep the
  previous home and just restart it), then `add file:` the previous
  bundle directory into a fresh home. Installs are copies — the
  previous install is unaffected by a later `add` elsewhere.
  Alternative: `dsh plugin --profile <name> remove @stc/dsh-plugin-stc`
  (`plugin` passes through to pnpm; layer detachment unverified —
  prefer the fresh-home path for releases).
- Data preserved across both: run stores (`STC_DSH_STORE`), dossiers
  (`STC_DOSSIER_DIR`), DSH sessions (inside each `DSH_HOME`), and the
  evidence roots under past run dirs. Rollback never deletes these;
  a new home starts empty beside them.

## Policy-lane rollback

Delivery-policy promotion is versioned (`policy/registry.ts`): existing
runs keep their policy id; a promoted policy that regresses is retired
in the registry and the previous blessed version is re-selected. The
discovery lane cannot silently alter delivery (config-layer separation
is tested), so discovery experiments need no rollback path — only
promotion does, and it is deliberate + recoverable by construction.
