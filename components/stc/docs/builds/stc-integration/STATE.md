# STC Integration — Current state

Updated: 2026-09-26 (operator-release tranche COMMITTED: 4 release blockers fixed + reviewed, suite 679/0, offline proof 3/3, T5 agent trial → QUALIFIED champion APPROVED; manual route released, codex route still blocked)
Current objective/tranche: ATTEMPT-5 CLOSED 2026-09-23 (Option 1 executed under goal authorization): STC-owned newline repair committed separately (441ab0b, reviewed), complete-path preflight GREEN on the new base, one bounded live qualification consumed → terminal FAIL caused by codex CLI auth (refresh token already used; 0 model bytes served). Attempt-4 attempt-1 preserved unchanged (terminal FAIL, packet committed). No champion exists; nothing promotable. Any new live qualification needs SEPARATE operator authorization + operator codex re-login. AUDIT CLOSEOUT 2026-09-24 (offline, this commit): operator audit found 3 gaps — (E1) leg5b never measured champion mutation, (E2) auth "no product fault" overstated, (E3) clean-checkout unproven. All closed offline: ERRATA.md corrects the record (packet immutable); fixture fix commits (1ab7ecf + ffa0247, reviewed) make the suite green from pristine clones (625/625, no manual extras); leg5c measures the combined path (ChampionResult APPROVED, mutmut_count=1, 36/36 @100%, dossier verifies); AUTH-DIAGNOSIS.md roots the auth failure in copy-out-only seeding orphaning rotated tokens (re-login enables exactly the next run); driver3 re-pinned to ffa0247 (72/72). Attempt-5 attempt-1 stays failed. Gate G (re-login + fresh authorization) is the only path to attempt-5/attempt-2.
Current contract revision: INT-2026-09-13.2 INTEGRATED (immutable M1 record); INT-2026-09-14.1 CLOSED (fix tranche, honest NOT-READY partial; P03-fix + P04-fix VERIFIED, P05-fix VERIFIED as evidence); follow-up close recorded under existing revisions (no new revision — design tranche pending approval); deterministic close recorded under existing revisions (no new revision — champion-scoped-mutmut amendment executed per P1-ADDENDUM §4 proposal, approval-chain wording open for readiness ruling); attempt-4 recorded under existing revisions (no new revision — failed qualification, no contract change)
Workspace/base/candidate: stc HEAD 3d20863 + trial-manual tranche (this commit). Product delta since 3263569: fb3aad8 (attempt-5 PLAN finding docs), 441ab0b (STC-owned newline repair + regression tests, reviewed), 1ab7ecf + ffa0247 (dossier-store fixture self-seeding to tmp + M3 pin 18->20, reviewed), f4da6f7 (credential sync-back repair + 4 tests, reviewed twice), + STC_GATE_TIMEOUT_S knob + 3 tests (reviewed; default 120s unchanged). Driver4 (/tmp, re-pinned f4da6f7, 87/87 offline) dispatched attempt-5/attempt-2 2026-09-24T03:14:44Z: leg 1 refresh_token_reused, auth-halt tripped, 1/8 spent, 0 bytes, NoChampionResult (packet attempt-2/, 41 files incl. FROZEN.sha256). Preflight on 441ab0b GREEN: legs 1–5 (mutmut 36/36 @100% component, champion APPROVED leg5b with mutmut unmeasured — see E1, measured by leg5c on ffa0247; dossier verifies; binding b20860ad… identical across legs). Tree clean except store.db-shm/-wal transient (never commit). Volatile originals (/tmp/a5-live, /tmp/a5-pre, /tmp/a5-driver2, merged trees) are NOT durable; attempt-5/attempt-1/ (64 files) + attempt-5/attempt-2/ (41 files) packets, each with FROZEN.sha256, are. Trial-manual (this commit): codex/muse/agy all unauthenticated → existing --manual operator handoff selected; TTL task; offline proof good→APPROVED (mutmut 33/33) + bad→fail-closed; T4 agent trial (2 gen + 1 verify used) → search champion, all gates green, mutmut 33/33, judiciary REJECTED ZERO_MOCK (rule worker-invisible) → NO qualified champion, no relaunch; packet trial-manual/trial-run/ (25 files incl. FROZEN.sha256 24/24) + runbook/specs/env + 5 findings. Attempts 1-2 preserved failed. Operator-release (this commit): Fix 1 final_outcome single authority (CLI/JSON/exit/STATUS/branches/run_ref/review agree; REJECTED→exit 1 NEEDS_REPAIR judiciary-*); Fix 2 provenance witness + RT-03 Rule 3 (both SST shapes incl. fenced/cortex-evaluations, verifier-fail slot-skip; starved-critique veto tested); Fix 3 WORKER_CONSTRAINTS in bundle/capsule/prompts (auditor unweakened); Fix 4 manual_payloads validation + manual-template (paste re-prompt + fixture load gate). H1 ctx-package re-pinned by anchor-tracking (4042 B, eb81c590, mechanical). Suite 679 passed/0 failed/6 deselected-live; ruff+mypy--strict clean; independent review REVIEW-PASS 0 blocking (1 advisory deferred: transient-OSError witness gap → MANUAL-ROUTE.md §8). Offline proof: good→APPROVED COMPLETE (mutmut 32/33 96.97%), bad→NEEDS_REPAIR zero artifacts, T4-replay→exit 1 judiciary-rejected:ZERO_MOCK_VIOLATION. T5 agent trial (fresh impl+reviewer, corrected briefs; 2 voids V0/R1 mechanical, R2 terminal): QUALIFIED champion — exit 0 COMPLETE, judiciary APPROVED 0 findings, gates 4×0, mutmut 32/36 88.89%, 3 invocations (2 ok + 1 budgeted harness-error). Packet evidence/BUILD/trial-5/ + MANUAL-ROUTE.md (operator execution + frontend interface contract). T4 + attempts 1-2 + SST/trace/prompt-kit untouched. Historical: OFFLINE-SETUP verified release @3263569; P2 green scripted @7dc2dc0; attempt-4 terminal FAIL preserved. No remote; no pushes.
Coordinator notes: KIT copies identical (prompt-kit/ == trace/docs/prompt-kit/); authoritative KIT per contract is trace/docs/prompt-kit. Builder harness: codex exec (ChatGPT login = CLI-session budget per R5; no API env vars present). Observed: stc has NO git remote — P00 push will likely take the git-bundle fallback (pre-authorized in packet).

## Packet status

| Packet | State | Owner | Candidate | Evidence/review | Blocker or next action |
| --- | --- | --- | --- | --- | --- |
| P00 checkpoint+ADR | VERIFIED | subagent-verify-P00 | 565b1ed (pin) + 9da124e (records) | evidence/P00/verify-1/REVIEW.md (PASS, all 5 criteria reproduced) | Done. V-OBS-1→P01 B1 (diff pins for ro checkouts?); V-OBS-2/3 none. Base for all packets: 565b1ed |
| P01 adapters | VERIFIED | subagent-verify-P01 | 9ef28e9 + 5 owned files (UNCOMMITTED, deliberate) | evidence/P01/verify-1/REVIEW.md (PASS; 99+37 green, mypy 0 owned) | Done. O-1: builder patched EXECUTION.md unreported (LAUNCH_KIT-mandated alignment, content verified, kept); briefs now require status-after-last-write |
| P02 memory | VERIFIED | subagent-verify-P02 | 7c7f872 + P01 loose (5) + P02 owned (4, UNCOMMITTED) | evidence/P02/verify-1/REVIEW.md (PASS, no findings) | Done. Brief lesson (V10): never ask diff-vs-base on uncommitted files — ask structural + behavioral checks |
| P03 worker+gateway | VERIFIED | subagent-verify-P03 | a122c5e + loose (P01/P02 9 + P03 owned + dispatch hunks; pyproject 1-liner COMMITTED) | evidence/P03/verify-1/REVIEW.md (PASS, R1–R6 + pyproject ACCEPTED, live rerun green) | Done. N1: prompt-kit parallel drift predates P03 (exonerated, pristine-export posture holds) |
| P04 runner | VERIFIED | subagent-verify-P04 | 55c91f8 + loose (P01–P04 code) | verify-1/REVIEW.md + mutmut-closure + mutmut-confirm/REVIEW.md (CONFIRMED) | Done unconditionally. Limitation LIFTED: once-test runs+passes on genuine mutmut 3.8.0 report. Remaining follow-ups: F-B3-3/F-B3-4 pins (= P05 task), R1 proposal |
| P05 run+accept | VERIFIED | subagent-verify-P05 | 3299078 + loose (P01–P04 code) + P05 owned (cli +576, dossier.py, e2e, spec, dossier/) | evidence/P05/verify-1/REVIEW.md (PASS all 6; honest-partial ruled SOUND) | Done. Key B3 inputs for B5/A2: INFO-1 session-sandbox exec confound (A2 must rerun live outside sandbox); INFO-2 budget-elapsed under-report; INFO-6 confabulation source = operator campaign files |
| B5 tranche | INTEGRATED | subagent-b5 | 1fa263b + loose (P01–P05 code, uncommitted per rule) | evidence/B5/REVIEW.md (INTEGRATED) | M1 closed. $0.00 metered total. A2 design delivered @ .1 (D15, Phase 1, re-entry launches); Phase 0 dropped per fix authorization |
| P03-fix gateway profile+shaping+confinement | VERIFIED | fix-builder-P03/verify | 4544190 + loose (4 owned: gateway b6b73ed3, worker 49017ef4, init 10571421, test 3b4a9654) | evidence/P03-fix/verify-1/REVIEW.md (PASS; 71+205 green, live -o 27B exact, tracked+full identical) | Done. V1-INFO-2 bare-text live-test follow-up rides as future work |
| P04-fix runner-wall elapsed | VERIFIED | fix-builder-P04/verify | 4544190 + loose (2 owned: runner 19a2e448, test 6e059f08) | evidence/P04-fix/verify-1/REVIEW.md (PASS; pins 560.0+137.25 both interps, sst clean, discrimination proven) | Done. V1-INFO-1 champion-path elapsed rode P05-fix live (corroborated: 292.976) |
| P05-fix live acceptance re-run | VERIFIED (honest partial) | fix-builder-P05/verify | 4544190 + loose (0 product files touched) | evidence/P05-fix/verify-1/REVIEW.md (PASS as evidence, live_outcome PARTIAL; builder AUTOMATION-NOT-READY) | Done as evidence. No champion: real-prompt diverge 280s timeout reproduced + capacity transients; F1 truncation gap follow-up |
| FIX-B5 close | NOT-READY | fix-b5-integrator | 4544190 + loose (16 MATCH + 6 VERIFIED differs; 2 pre-existing tracked mods) | evidence/FIX-B5/REVIEW.md (NOT-READY: honest no-champion partial, valid evidence) | Tranche closed. C3/INFO-2/A2-RISK-2/B5-OBS-1 CLOSED; A2-RISK-1 SUPERSEDED; F1/F2/F-B3-3/F-B3-4/R1 carried |
| F1 stderr-preservation | VERIFIED | f1-builder/verify | edf5389 + loose (harness sidecars) | evidence/FOLLOWUP/f1-fix/verify-1/REVIEW.md (PASS; F1-only 5/5 + P03 76/76 both) | Done. Truncation gap closed via sidecars |
| Winner-carry fix | VERIFIED | carry-builder/verify | edf5389 + loose | evidence/FOLLOWUP/winner-carry/verify-1/REVIEW.md (PASS) | Done (predecessor hashes chain-verified) |
| Live-exp P2-H3a | WIN (probe) | live-exp-builder | edf5389 + loose | evidence/FOLLOWUP/live-exp/attempt-1/REVIEW.md (WIN — valid diverge proposal via STC-owned variation) | Done. Emission reliable; content is where champions die |
| Accept-1 (gateway win + A1 stall) | VERIFIED (honest partial) | accept-builder/consolidated-verify | edf5389 + pre-A1/pre-A3 9-file base | evidence/FOLLOWUP/accept/attempt-1/REVIEW.md + accept-123-verify/REVIEW.md (PASS; manifest 31/31; intervention separated) | Done. A1 recursion proven by pipeline's own artifact |
| Accept-2 (A1 holds + A3 format) | VERIFIED (honest partial) | accept-builder/consolidated-verify | edf5389 + A1-fixed/pre-A3 base | evidence/FOLLOWUP/accept-2/attempt-1/REVIEW.md + accept-123-verify/REVIEW.md (PASS; 29/30 + V123-INFO-1 typo, file intact) | Done. A3 anatomy byte-identical replays both legs |
| Accept-3 (pin 1/2 + wiring) | VERIFIED (honest partial) | accept-builder/consolidated-verify | edf5389 + A1-fixed + frame-pin base (= current tree at verify) | evidence/FOLLOWUP/accept-3/attempt-1/REVIEW.md + accept-123-verify/REVIEW.md (PASS + BLOCKED-WIRING CONFIRMED; manifest 30/30) | Done. Wiring adjudicated; H1-context is the evidence-backed lever |
| A1 mirror recursion | VERIFIED | a1-builder/verify | edf5389 + loose (dst-exclusion) | evidence/FOLLOWUP/a1-fix/verify-1/REVIEW.md (PASS; 3/3 regression both) | Done. CLOSED ×3 live corroborations |
| A3 patch format | VERIFIED | a3-builder/verify | edf5389 + loose (frame pin) | evidence/FOLLOWUP/a3-fix/verify-1/REVIEW.md (PASS; 18/18 both) | Done. Narrowed to probabilistic remainder + SST landing pending |
| Combined-fix W1/W2/W4/W5 | VERIFIED | combined-builder/closeout-verify | edf5389 + loose (7 owned exact) | evidence/FOLLOWUP/combined-fix/attempt-1/REVIEW.md + verify-1/REVIEW.md (PASS; fresh 68/68 + 61/61 both) | Done. W3 CUT executed via debt-fix; live proof still blocked |
| Debt-fix G1 + exclusion | VERIFIED | debt-builder/closeout-verify | edf5389 + loose (28/28 exact, 1114+/14-) | evidence/FOLLOWUP/debt-fix/attempt-1/REVIEW.md + verify-1/REVIEW.md (PASS; Gates 1+2 green real+mirror, flip holds; V-CO-INFO-1 provenance note) | Done. Debt share complete; Gate-3 exit-0 blocked F1–F4 |
| BUILD fix-2 (mypy repair + §3 PASS + partial preflight) | RECORDED (staged, unadded) | fix-session F1 | 7dc2dc0 + loose (10-site repair, 8 files) | evidence/BUILD/fix-2/REVIEW.md + P1/P2-ADDENDUM.md + R1R2-PACKET.md (§3 PASS first green; P1 GREEN, P3/N1/N3/N4/N6 PASS, P2 honest RED motivating R1/R2/R3) | Staged for records commit. P2 BLOCKED verdict SUPERSEDED by accept-p2 green; P1/P3/N1/N3/N4/N6 stand |
| ACCEPT P2 deterministic champion | GREEN (scripted) + RULED | deterministic execution + coordinator transcription | 7dc2dc0 + R1/R2/R3 working tree | evidence/BUILD/accept-p2/REVIEW.md + RULING.md + dossier (ChampionResult, 4 gates exit 0, mutmut 100% 4/4 once, dossier verifies, N2 PASS, N5 clean) | RULED: deterministic-path demonstration accepted (planning permitted, live gated); amendment ratified for deterministic scope; missing evidence listed in RULING §4; driver fix preserved in driverfix/ |
| Attempt-4 attempt-1 live qualification | FAILED (honest no-champion, VERIFIED) | coordinator + independent verify-1 | c70ac57+worktree-19M+20U (blue: 0 edits) | evidence/BUILD/attempt-4/attempt-1/ (REVIEW.md terminal FAIL + verify-1-REVIEW.md, legs, spend, dossier, replay) | Terminal: NoChampionResult(no-verified-candidate), 2/8 legs (cand-1 pruned all-gates-red 749s; leg-2 marker-refused), dossier verifies, N5 attempt-zero. Independently reproduced zero-divergence. No relaunch; tranche to handoff |
| Attempt-5 repair + preflight + live | CLOSED (repair COMMITTED 441ab0b, preflight GREEN, live terminal FAIL env-auth) | coordinator + builder/review agents | 441ab0b (frozen base) | evidence/BUILD/attempt-5/attempt-1/ (REVIEW.md + RUNBOOK.md + launch-manifest + legs/spend/dossier/preflight/driver, FROZEN.sha256) | Repair: controller-newline restore (idempotent, regression-tested, reviewed). Preflight legs 1–5 green, binding b20860ad… stable. Live attempt-1: NoChampionResult(no-verified-candidate), 2/8 legs, BOTH codex-auth-failed (refresh token already used), 0 bytes served, stop-3 per design; dossier verifies. Spend 2/8 + 0/6 reserve. No champion → no promotion. Operator action: codex re-login + separate authorization for any new qualification. Attempt-4 unchanged. |
| Attempt-5 audit closeout | DONE OFFLINE (erratum + fixture + measured leg5c + auth diagnosis + driver3) | coordinator + review agents | ffa0247 (frozen base) | evidence/BUILD/attempt-5/{ERRATA.md, AUTH-DIAGNOSIS.md, leg5c/ (report + script + dossier, FROZEN.sha256), driver-ffa0247/ (72/72)} | E1: leg5c measures combined path (champion APPROVED, mutmut_count=1, 36/36 @100%, dossier verifies) on pristine clones, no extras. E2: auth rooted in copy-out seeding orphaning rotations; re-login enables one run. E3: suite 625/625 from pristine clone. Attempt-1 stays failed. Gate G pending. |

## Budget table (R10 defaults; builders report, coordinator writes)

| Packet | Wall | CLI calls | Gateway calls | Spend record |
| --- | --- | --- | --- | --- |
| P00 | ~30 min incl. B3 (~8) | 4 CLI (2 codex env-fail, 1 agy build, 1 agy quota-rejected) + subagent repair + subagent B3 | 0 | $0 API; codex ~65k tokens env-failed; agy quota exhausted (resets ~166h) |
| P01 | ~80 min (55 build + 25 B3) | ~34 batches | 0 | $0 API; 0 installs (shim=/tmp/p01-shim symlink to existing venv) |
| P02 | ~75 min (45 build + 30 B3) | ~25 batches | 0 | $0 API; 0 installs (joint env + shim) |
| P03 | ~140 min (100 build + 40 B3) | ~45 batches | 10 CLI model calls | $0 API (cap was $2); 0 installs |
| P04 | build + B3 + closure + confirm (walls n.r.) | ~50 batches | 2 gateway calls | $0 API; 1 authorized install (mutmut 3.8.0 + 7 deps into learn-anything/.venv) |
| P05 | build + B3 (walls n.r.) | 7 codex CLI calls | 0 ok / 4 diverge attempts | $0 API; 0 installs |
| B5 | ~40 min | 0 calls | 0 | $0; 0 installs |
| A2-revisit | plan (wall n.r.) | 0 calls | 0 | $0; 0 installs, 0 model calls |
| P03-fix | build+B3 (walls n.r.) | 12 CLI (9 builder + 3 verifier; cap 40) | 4 live gateway legs (s1/s2/v1/committed smoke) | $0 API; 0 installs |
| P04-fix | build+B3 (walls n.r.) | 0 CLI (cap 10) | 0 (deterministic fake-clock pins) | $0 API; 0 installs |
| P05-fix | build+B3 (walls n.r.) | 6 CLI (cap 60) | 6 live legs (B1 smoke + B2×2 + 3 diags), 1 ok | $0 API; 0 installs |
| FIX-B5 | ~10 min | 0 calls | 0 | $0; 0 installs |
| FOLLOW-UP (F1/carry/live/accept×3/A1/A3/combined/debt + close-out verify) | walls n.r. | 8 CLI (cap 20; 6-call reserve INTACT) | 5 preserved live legs (accepts 1–3) + live-exp probes per its record | $0 API; 0 installs; all verification scripted |
| DESIGN (draft + verdict + P1/P2/corrections) | walls n.r. | 3 CLI sessions (doc-authorship: drafting, HANDOFF-NEXT verdict, P1/P2+corrections 01a0ba10; pasted reviews uncounted, no box record) | 0 | $0 API; 0 installs; records-only |
| BUILD (S1 implement + S2 env/gate + S3 refix) | walls n.r. | 3 CLI sessions (S1 §1 build ACCEPTED; S2 §2 env + §3 4/5 STOP format; S3 format-fix + §3 re-run STOP mypy-10; box EXHAUSTED) | 0 | $0 API; 1 §2-box env (uv sync --locked, STC-owned .venv 3.12.3, digest b43db3e4); preflight NOT RUN |
| DETERMINISTIC (fix-2 repair + R1/R2/R3 + ACCEPT P2) | P2 ≈1.5–2h (pytest 1071s + mutmut 3243s); suite ≈19–24 min; mutprobe 3259s | CLI sessions n.r. (no box record kept) | 0 | $0 API; 0 installs; S2 env reused (digest re-matched b43db3e4, lockfile daee99b7); transcription session: reads + copies + 3 read-only corroborations |
| ATTEMPT-4 (completion tranche) | tranche ≈3h (18:44→21:36Z + close-out); attempt ≈20 min (21:15:43→21:36Z) | 0 CLI build sessions (coordinator native) | 2 live (leg-1 diverge ok 77s; leg-2 diverge ok-harness + stc-refused 96s) / 8 box; reserve 0/6 | $0 API; 0 installs; blue 0 edits; red folded §12; oracle 3/3 ×2; N5/N2/dossier green; terminal FAIL verified zero-divergence |
| ATTEMPT-5 (repair + preflight + 1 live) | repair + review + preflight (legs 1–5, leg4 1675s) + live attempt ≈6 min (11:45–11:51Z 2026-09-23) | builder + review + preflight + driver sessions (box per goal authorization, not R10) | 2 live (leg-1/2 diverge auth-failed 70s/105s, 0 bytes) / 8 box; reserve 0/6; preflight 0 live | $0 API; 0 installs; product commit 441ab0b (reviewed); preflight green (mutmut 36/36, champion APPROVED, dossier verifies); terminal FAIL env-auth (codex refresh token), packet committed |
| CLOSEOUT (erratum + fixture + leg5c + auth + driver3) | fixture + leg5c 2189s + auth diag + driver re-pin | coordinator + review sessions (goal authorization) | 0 live (all scripted/offline) | $0 API; 0 installs; commits 1ab7ecf + ffa0247 (reviewed); leg5c measured green; driver3 72/72; Gate G (re-login + fresh auth) user-owned |

## Current decisions

- Accepted changes since the previous handoff: A3 REVISE executed — contract
  .2 re-issued (seam choice D9, gateway D10, TL absent D11, serialized D12,
  live-mark D13, run-extension D14); DESIGN_REVIEW.md holds all dispositions.
- Pending user decisions and why they matter: Q1 CLI caps (R10 defaults apply).
  P05 acceptance task approved 2026-09-14 (F-B3-3/F-B3-4 pins; reused for P05-fix).
  Fix tranche authorized with 6 amendments (snapshot first; no unrestricted-gateway
  Phase 0 in ordinary checkout; confinement+proposals+elapsed scope; serialized
  builders + fresh verifiers with hash-bound evidence; live-success bar; ask only
  on consequential decisions / hard boundaries).
- Fix-tranche deviations from A2-revisit plan (operator-authorized): (1) Phase 0
  unsandboxed-unrestricted diagnostic DROPPED — confinement is fixed first and the
  P05-fix live run through the confined gateway is the diagnostic; disposable-env
  comparison only if still needed (not assumed to need manual execution).
  (2) Full-strength shaping (A2 outcome-b/c path) since no Phase 0 calibration.
  (3) FIX-INTEGRATED requires live FULL success; honest partial = NOT-READY.
- Pre-change snapshot: evidence/FIX-TRANCHE/snapshot/ (MANIFEST.sha256 + tarball
  candidate-snapshot-83bc1e2.tgz, tarball sha256
  d979b37cb72c5af51955ca9abaeac61d77d0167f48b33fda779e6c2514d12294).
  Pre-change tree verified == B5-S1 loose set (cli 576/0, dispatch 333/7,
  integration/ 8 files, tests 5+2, specs/, memory/, 2 P04 shm/wal strays).
- Assumptions that changed and affected dependents: none pending — all audit
  assumptions closed in .2.
- Operator commit rule (2026-09-13, standing): coordinator may commit packet
  records + STATE.md at packet boundaries on stc main (no push — no remote);
  builders/verifiers never commit; product code stays uncommitted for review
  until the operator says otherwise.
- Operator approvals (2026-09-14): (1) P05 acceptance task = F-B3-3/F-B3-4
  pinning tests (merge-apply-failure probe + with_codex audit-time pin);
  (2) mutmut install into learn-anything/.venv authorized (one-shot override
  of the no-installs rule) to close the P04 mutmut-once leg — rerun + B3-confirm
  required before P04 limitation is lifted.
- Follow-up close (2026-09-19, operator-authorized): all follow-up packets
  VERIFIED (F1/carry/A1/A3/combined/debt PASS; accepts 1–3 honest partials
  PASS; live-exp WIN; attempt-3 BLOCKED-WIRING CONFIRMED); tranche CLOSED
  NOT-READY per the live-success bar (no champion ever across M1 + fix +
  follow-up). F2 (lease-layout skips), F3 (committed-bytes E2E), F4 (3.11 vs
  3.12 env assert) explicitly UNRESOLVED; F1 (joint tool absence) env-blocked.
  Close-out verification ran on real-gates Python 3.11.15 primary per operator
  instruction. Errata append-only per V1-INFO-1 precedent (V123-INFO-1 +
  V-CO-INFO-1 corroborated; originals byte-exact). Records-only commit; product
  code stays uncommitted per commit rule.
- Operator approvals (2026-09-19): (1) close-out as above; (2) focused
  integration-contract design tranche next — resolve gate bytes, lease layout/
  imports, runtime versions, required-test coverage + skip handling, and
  baseline/candidate/integration separation; compare smallest coherent
  alternatives; NO product changes and NO live attempt-4 until the revised
  contract is approved; a local preflight through the actual remaining gate
  path is required before another live attempt.

## Continuation

- Next ready action and exact launch/reference: FOLLOW-UP TRANCHE CLOSED
  NOT-READY (evidence/FOLLOWUP/*/verify-1/REVIEW.md + accept-123-verify).
  Integration-contract DESIGN tranche next (operator-authorized 2026-09-19):
  plan first, approval gate, no product changes, no attempt-4 until the
  revised contract is approved + a local preflight through the actual
  remaining gate path passes. No pre-authorized D7 exception; any SST-side
  proposal needs operator evidence review. Code stays UNCOMMITTED per commit
  rule; follow-up records + STATE committed at close (this commit).
- Design-tranche plan rev 2 (evidence/FOLLOWUP/design-tranche/PLAN.md,
  uncommitted) APPROVED for the focused architecture session only: Q1 Yes
  (genuine git isolation incl refs/worktree-metadata/cleanup), Q2 Yes
  (STC-owned 3.12 preferred, no install authorized), Q3 keep 12-incl-6
  (attempt-4 cap derived from call topology at the later execution
  authorization). Walkthrough + ratification packet drafted (same dir:
  WALKTHROUGH.md + RATIFICATION.md, uncommitted); session stopped at
  contract review — no implementation, installs, live calls, or readiness
  claims. Session handoff: design-tranche/HANDOFF-TEMP.md (consume then
  delete at tranche close).
  Standing:
  native subagents serialized; commit rule = coordinator commits records +
  STATE at boundaries, code uncommitted; status-after-last-write in all briefs.
  Overnight (operator 2026-09-13): $10 API latitude unused ($0.00 metered
  total); safety cron fd115cbe one-shot fired 00:01 UTC Sept 14 — delete on
  completion (coordinator). Praxist disposition: no task existed for this
  tranche; held as fallback execution route under the $10 cap (unused).
- Work safe to perform concurrently: follow-up scoping (new authorization needed).
- Build session (2026-09-19, cap-hit honest-partial): S1 §1 implementation ACCEPTED (evidence/BUILD/attempt-1/, 9 edited + 8 created, 17/17 hashes); S2 constructed the §2 env (STC-owned .venv 3.12.3, env_digest b43db3e4…, lockfile unchanged daee99b7) and STOPPED at §3 item 5 (ruff format 5 files, all S1-authored); S3 applied ONLY the mechanical format fix (11/11 hunks audited formatting-only in S1 regions, 5/5 + 12/12 hashes) and STOPPED at the §3 re-run item 5 (mypy --strict 10 errors in 8 files, stable ×2 + coordinator ×1: 4 S1-owned no-any-return/unreachable + 5 pre-existing yaml unused-ignores under typed lockfile pyyaml/mypy-2.3.1 + 1 pre-existing cli.py:1423 operator). Preflight P1–P3/N1–N6 NOT RUN (unproven, not failed). Box 3/3 spent; 6-call verification reserve INTACT. Next: operator decision — a bounded budget amendment (mypy-fix + full gate + preflight re-run) or redirect; evidence/BUILD/fix-1/REVIEW.md §5 is the blocker spec. No readiness ruling (separate decision). Product code stays UNCOMMITTED per commit rule; this commit is records + STATE only.
- Deterministic close (2026-09-21, SUPERSEDES build cap-hit): fix-2 repair (§3 PASS, P1 GREEN, P2 honest RED) + R1/R2/R3 execution + ACCEPT P2 GREEN (evidence/BUILD/accept-p2/, 85 files + MANIFEST, transcribed record). READY-FOR-COMMIT add-set (all `git add -f`): evidence/BUILD/accept-p2/ + evidence/BUILD/fix-2/ + STATE.md; NOT in set: design-tranche/ (separate auth), memory/ + specs/ (loose set), P04 shm/wal strays, any product code. Commit AUTHORIZED (operator decisions 1–5). Ruling RECORDED (accept-p2/RULING.md). After commit: hygiene exclusion commit (separate, decision 4), then attempt-4 design-only planning (reads + probes, zero live calls; plan for review; live execution separately gated). Original dossier at /tmp/accept-p2/ev is volatile — commit is the durability step.
- Environment or permission blockers: none; live provider capacity transients observed (fail-loud, minutes-scale).
- Remaining budget, if one was set: fix tranche spent 18 CLI total (P03-fix 12 + P04-fix 0 + P05-fix 6); follow-up spent 8/20 CLI, 12 remaining INCLUDING the protected 6-call verification reserve; design spent 3 (drafting + verdict + P1/P2/corrections) → 3 spendable + 6 reserve remaining; implementation cap = lesser of 6 and 3 = 3 sessions; $0.00 API throughout. Loose-manifest accounting: the 28-file manifest = 10 tracked files (git diff numstat 1114+/14-) + 18 untracked files (content-hash manifest) — the numstat never describes the untracked share.
- Praxist disposition (standing, operator 2026-09-20): HOLD for live-champion search resumption only (attempt-4-class work; 0 champions ever across M1+fix+follow-up — emission reliable, champion content never). NOT for deterministic gate/preflight/repair/triage execution. Any agent seeing live-search resumption discussed SHOULD suggest a Praxist readiness check (runnable task project, metrics, budget) before any launch; never auto-launch.
- Deterministic close (2026-09-21, records staged, commit pending):
  P2 GREEN scripted (ChampionResult cand_ACCEPT-P2-242ffb28_0_0,
  4 gates exit 0, mutmut 100% 4/4 counted-once, dossier verifies,
  N2 PASS, N5 clean) on 7dc2dc0 + R1/R2/R3 working tree; supersedes
  BUILD cap-hit + fix-2 P2-BLOCKED. Standing traps: (1) `build/`
  .gitignore line matches `BUILD/` case-insensitively here — both new
  evidence dirs are INVISIBLE to default git status and need
  `git add -f`; (2) binding verify inherits cwd — run from inside a
  repo or `git bundle verify` fails closed (harness sensitivity, not
  evidence rot); (3) driver exit 1 is cosmetic (mutmut_paths bug,
  own fix — never rerun P2); (4) main-tree dag×4/cli_json red is
  stale-HEAD (uncommitted ruff exclusion), not product.
- Readiness ruling (2026-09-21, operator decision 3, evidence/BUILD/
  accept-p2/RULING.md): P2 ACCEPTED as deterministic acceptance-path
  demonstration for the recorded candidate + snapshot. Attempt-4
  planning permitted (design-only, zero live); live execution stays
  gated on plan review + separate authorization. Amendment ratified
  for deterministic scope only; live takes its own bar. Binding /
  contrast / R1/R2/R3 reconciled; 6 missing/weak evidence items
  listed explicitly (merged bytes, transcript-only originals,
  R2a-green log, CLI count, reviewer text, live scope). Paused
  reviewer notes not a prerequisite per decision; a required
  unresolved finding therein would reopen the ruling.
- Integration/release state: M1 INTEGRATED @ .2 (immutable); fix tranche
  NOT-READY (honest partial, valid evidence — NOT FIX-INTEGRATED per the
  live-success bar); no release authority.

## Known limitations

- Tripwire confinement (2 dirs + .git subset) is NOT a sandbox; /tmp/$HOME/
  siblings unwatched; OS confinement post-M1.
- Champion-veto (not per-node fail-closed); D7-exception subclass deferred
  with trigger.
- Copy/worktree isolation is not OS confinement.
- SST custody single-command/empty-PASS bypassed by wrapper, not fixed upstream.
- INTEGRATION_EXECUTION_PLAN.md from prior chats absent in workspace; superseded.
- Trace-lite absent from M1 by operator decision (D11).
- RECORDED LIMITATION (B5): live-model search never produced a proposal
  (codex diverge timeouts; agency/sandbox confound unresolved) — loops
  fail closed honestly; live custody/gates/veto/champion stand verified
  by P04 + manual e2e only. A2-revisit owns the fix plan.
- RECORDED LIMITATION (FIX-B5): fix tranche closed NOT-READY — real-prompt
  diverge still times out at 280s through the FIXED gateway (served, 0 bytes,
  0 sandbox traces; agency-dominant per A2 rule b, small-prompt control
  succeeds in 35s); 0 live proposals ever across M1 + fix tranche. F1:
  300-char ledger truncation loses fast-failure causes (recovered only via
  out-of-band diag). Confinement (C3) + elapsed (INFO-2) closed on evidence.
- RECORDED LIMITATION (FOLLOW-UP CLOSE): follow-up closed NOT-READY —
  emission now reliable (5/5 live legs ok across accepts 1–3 + live-exp win)
  but 0 champions ever across M1 + fix + follow-up (format → wiring →
  gate-contract layers); live judiciary / merge-execution / mutmut-on-champion
  / worker harnesses NEVER exercised live. Gate-3 exit-0 blocked by
  F1 (joint lacks ruff/mypy) + F2 (lease-layout skips vs 0-skipped invariant)
  + F3 (dag×4 + cli_json gate committed-main bytes) + F4 (3.12 env assert vs
  3.11 real-gates). SST tolerance validated-but-UNLANDED; served-header gap
  (A2) open. Debt share complete; contract questions ride the design tranche.
- RECORDED LIMITATION (BUILD cap-hit): T0 Gate-2 red under the lockfile
  toolchain (mypy 2.3.1 --strict, 10 errors in 8 files: 4 S1-owned +
  6 pre-existing lines newly flagged — 5 yaml unused-ignores now that
  lockfile pyyaml resolves typed + cli.py:1423 operator); Gate-1 green
  both legs, §3 items 1–4 pass; preflight P1–P3/N1–N6 unproven (NOT
  RUN). Clearing the red needs product edits beyond the exhausted
  3-session box → operator budget amendment required.
- RECORDED LIMITATION (DETERMINISTIC CLOSE): P2 green is SCRIPTED
  (fixed DIFF served by ScriptGateway — no live model in the loop),
  THIN scope (4 mutants, one version-bump production file, literal
  pins), and confers NO live-model/live-champion qualification; the
  live loop is unplanned and highest-risk. Record is transcribed
  (no gate reruns; only read-only binding/N2/N5/pin corroborations).
  Merged-tree bytes (213 MB) live ONLY in volatile /tmp + a content
  manifest at the boundary. Amendment approval-chain wording is open
  for the readiness ruling.
