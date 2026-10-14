# STC acceptance closeout (bounded, 2026-10-05)

Frozen code candidate: `7e72226` (tree `dd4c682fd61b3b2a8fe26e6722fd811bb788874c`).
Release commit (code + docs): `c77fbc1`. No features added in closeout;
no full-battery reruns beyond evidence regeneration.

## 1. Requirements → evidence map

| # | Agreed requirement | Evidence on the final candidate | Status |
|---|---|---|---|
| R1 | Backend: dialectic search, custody, leases, tripwire, honest budgets | Round-4f §2: 709 passed / 0 failed / 6 deselected (live-marked, D13), RC=0, 27:41, retained `/tmp/stc-verify-suite-r4f.log`; H1 9/9 (4061 B sha383c474f); A3 20/20 | SATISFIED |
| R2 | DSH plugin bundle: tools, policy gates, presenter | §3: plugin units 99/99; e2e 7+3+2+3+1=16/16; probe 6/6 (round-4f rerun) | SATISFIED |
| R3 | Product journey: install → run → dossier → rollback | §4: boot PASS, journey 13/13, rollback PASS — observed round-4c on identical code; post-wipe rerun environmentally blocked, carried qualified (see §4 binding below) | SATISFIED (qualified carry) |
| R4 | Evidence reproduction determinism | §5: rescore IDENTICAL, checker 11/11, policy 10 PASS (round-4f rerun) | SATISFIED |
| R5 | SST contract posture + live consumption | §6 COMPATIBLE pin=df78f42894a6 (round-4f rerun); live runs 3–4 through real gates; caller contract + §4 pin procedure followed | SATISFIED |
| R6 | Browser walkthrough §§1–6 | Observations dated 2026-10-05 in walkthrough doc: all sections PASS; deviations D-W1..D-W5 filed; sub-items classified below | SATISFIED with retained optionals |
| R7 | Durable install + restart/recovery | DH-home exercise (repeatable boot, rejoin, store reads) + restart turn (history + dossier post-restart); finding in release doc | SATISFIED |
| R8 | Quality batch + spend within $10 HARD cap | Batch 18/18 $0.03; aggregate reconciled below | SATISFIED |
| R9 | Release docs, pins, handoff | Release/verify/record/walkthrough docs + this closeout + Windows handoff doc, committed | SATISFIED |

## 2. Open browser sub-items: classification (no silent narrowing)

- **D-W1 STC row pixels** — PROCEDURE BUG, expectation corrected; residual
  retained as OPTIONAL. Root cause proven from DSH source:
  `listBundles()` (packages/boot/plugin-manager/src/index.ts) lists only
  profile-manifest + installation names; the walkthrough's `--patch
  cordis.dev.yml` dev overlay is a composition-layer insert, never a
  manifest entry — so no STC row can render in a dev-overlay boot, by
  construction. The checkpoint holds for packaged installs only.
  Residual (packaged-install row pixels unverified): OPTIONAL —
  admin UI chrome; bundle load proven 3 ways (server `[stc-bundle]`
  lines, stc_* tools callable in every session, packaged-install
  boots green in rollback). Procedure text to be amended on next
  walkthrough revision; the filed D-W1 stands as the correction
  record.
- **Card-title transitions + progress streaming** — OPTIONAL limitation,
  retained explicitly. Presenter structure is unit+e2e proven; inline
  tool-call cards were pixel-verified. The pending→completed title
  transition and streaming progress are UX polish, not journey
  behavior; unobserved, stays open, no acceptance impact.
- **Active-job resume across restart** — CLOSED (proven, no browser
  needed). DSH `LocalJobRegistry` holds `private store = new
  Map<JobId, TrackedJob>()` with zero persistence primitives: jobs
  cannot survive process restart by construction, so silent resume is
  structurally impossible. STC runs persist in the durable store
  (proven readable post-restart in the recovery + DH turns), and
  `stc_recover` re-attaches only to live jobs, else requires verified
  resume (linked continuation) or reports needs-decision — the
  recovery path is covered by the e2e stc-recovery battery (3/3).

Required items: no browser rerun needed. The Windows handoff covers the
two optional residuals as forward work, not acceptance blockers.

## 3. Browser evidence sufficiency

Retained (durable): 6 run dirs with exit.json + run.json + console.log;
1.44M-char session transcript (markers re-verified post-wipe); quoted
reports + refusal + 361 B byte-match, all re-anchored from surviving
bytes. Lost: all PNG/TXT dumps (observed-live descriptions retained).
Assessment: SUFFICIENT for behavioral acceptance (every tool call, run
outcome, refusal, and byte comparison is disk-bound). Pixel acceptance
is partial (2 shots viewed live) — acceptable given the reclassified
sub-items above. Minimum recovery needed: none for required items.

## 4. §4 binding (carried results → exact identities)

Carried: boot PASS, journey 13/13, rollback PASS (round-4c).

- Code: STC `7e72226`, tree `dd4c682f…874c` (identical in 4c and 4f;
  only 4 doc files changed since, committed in `c77fbc1`).
- Dependencies: SST `df78f42…9013` (pristine), prompt-kit
  `4f442a6…ac9a` (pristine), DSH `639ed01539…a3f84`
  (content-clean; 14k status entries all 9p mode artifacts),
  node v22.23.3, pnpm 11.7.0.
- Configuration: STC patch only — `dsh-plugin-stc/cordis.dev.yml`
  (sha256 `2cfc2197…d12cc`, generated single-row stc-bundle →
  src/index.ts); boot env per scripts (PATH/COREPACK_HOME/XDG_*,
  DSH_HOME fresh /tmp home, STC_ROOT, proxy-stripped); journey /
  rollback additionally exercise packaged `plugin add` install
  semantics (`cordis.bundle.yml` sha256 `57824e9f…7914da02`).
- Runtime: WSL2 Ubuntu 24.04.3, kernel 6.6.87.2-microsoft-standard,
  /mnt/c 9p mount, loopback ports (3080 default, any-port accept).
- Installation: dev-overlay boot (boot-check) + packaged-install
  journey/rollback (product-journey / rollback-check).
- Block on rerun: full-server boots stall post-wipe (0 lines/10min
  detached, 5 bundle lines/280s foreground, port closed; boot
  process in `p9_client_rpc` disk sleep) under measured 9p collapse
  (~400 KB/s sustained vs ~84–137 MB/s sequential, two dd samples
  after partial recovery, and ~20 s worktree-add p50 earlier). No code, dependency,
  or configuration under §4 changed since its green. Carry is
  qualified and evidenced, not silent.

## 5. Spend reconciliation (cap $10 HARD, unchanged)

- Metered legs (reported from records; ledgers lost in /tmp wipe):
  pilot $0.01 + quality batch $0.03 + SST runs
  $0.0025+$0.0171+$0.0057+$0.0097=$0.035 → **$0.075 ≈ $0.08**.
- Unmetered browser turns (12): observed cumulative ≈6M tokens
  (dilemma session ≈4.8M @ 95–97% cache hit; all other sessions
  <1M each), ceiling taken at 8M (≈1.2× observed). Sail publishes
  no price list (all usage/billing endpoints 404; /models 200
  without pricing). Conservative bound: flat **$1.00/MTok on all
  tokens, no cache discount** → $8.00. This exceeds any published
  flash-tier rate by several multiples; realistic cache-dominated
  estimate at official DeepSeek V3 proxy rates is ≈$0.50.
- Aggregate: $0.08 + $8.00 = **$8.08 < $10** (conservative);
  ≈$0.58 realistic. Unknown cost is bounded, not zeroed. The cap
  binds only if Sail charged >$1.24/MTok flat — no evidence for
  that on a flash tier. Remaining budget: **$1.92 conservative**
  (≈$9.40 realistic), shared across any follow-up agents.

## 6. SST qualification; cand-02 resolved

Frozen release uses SST `df78f42` = cand-02, adopted via the contract
§4 procedure: owner handoff doc recorded, probe COMPATIBLE (observed
repeatedly incl. round-4f), staged (backend suite + e2e + live caller
exercise), pin amended with dated record (commit 5c65427 + contract
rev INT-2026-10-04.1). Pristine consumption enforced
(prove_import_integrity; dirty trees refused). QUALIFIED. Any SST
newer than df78f42 is an unconfirmed OPTIONAL upgrade → deferred,
not blocking. Nothing required is missing.

## 7. Cleanup + exclusions (accurate disclosure)

- STC-owned debug processes: VERIFIED CLEAN. Host-namespace probe
  shows zero node/tsx processes (the setsid-detached debug boot died
  on its own); port 3080 closed; stale locked git worktree
  registrations from killed runs unlocked + pruned (worktree list
  shows main only; tests self-clean).
- CI (`.github/workflows/ci.yml`): EXCLUDED, unrunnable here (no
  remotes, no pin provisioning in CI).
- Live-marked tests: 6 deselected per D13 (env-blocked, accepted
  exclusion, unchanged).
- Screenshots dumps: lost in wipe; behavioral evidence retained
  (see §3 above).
- .venv: zstandard added (read-only transcript analysis; inert,
  not imported by STC).
- dossier/: absent at closeout (gitignored runtime output; regenerates).
- Forward, explicitly open: Windows-verifier joint run for the two
  optional residuals, pending backend servability (handoff doc
  prepared; not an acceptance blocker).
