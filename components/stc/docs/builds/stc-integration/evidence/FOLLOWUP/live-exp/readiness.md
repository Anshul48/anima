# FOLLOWUP live-exp — B1 readiness (experiment plan + gates + probe matrix)

Author role and date: live-experiment-builder / 2026-09-14
Packet: STC follow-up tranche, live-experiment stage (find an STC-owned
variation yielding a valid diverge proposal through the real confined gateway).
Base/candidate: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` + loose set
(all 8 hashes re-verified below; `evidence/FOLLOWUP/live-exp/` = this stage's
own writes). Agency-dominance is UNPROVEN input (INSPECTION §5) — this plan
tests H0 first and treats every hypothesis as guilty-until-proven.

## Gate 0 — required full reads (all read in full, in-session)

- `evidence/FOLLOWUP/inspect-prompt/INSPECTION.md`: H0–H4 input; failing prompt
  identity (M1 4364 B, sha `3154b3bb…f391b61`); §2 response contract
  (`{"branches": [...]}` + `_clean_code(proposed_changes)`); §3 zero-source-context
  verdict; §4 36-fragment invariant chain; §5 experiment rules (≤14 calls, one
  lever per probe, short timeouts, ≤2 served failures per hypothesis).
- `evidence/FOLLOWUP/f1-fix/verify-1/REVIEW.md`: PASS gate; F1 CLOSED — every
  fast failure now preserves full bytes in the sidecar; success/confinement
  unchanged; 0 CLI calls spent there (20/20 remain entering this stage).
- `evidence/P05-fix/attempt-1/REVIEW.md` + `verify-1/REVIEW.md`: prior live
  shapes — B1 small-prompt 35.5 s valid-JSON success vs B2 call-1 281.4 s
  served timeout (exit 124, 0 B) + diag-retry 282.1 s served timeout + 60 s
  misrun hanging at cutoff + 2 capacity-transient fast fails (exit 1, 0 B,
  `Selected model is at capacity`); C3 confinement closed (6/6 legs clean).
- `evidence/FIX-B5/REVIEW.md`: NOT-READY baseline; F-B3-3/F-B3-4 pins open;
  target module absent; R1 proposal-only (stays deferred unless evidence shows
  it blocks — no such evidence at B1).
- Gate 0: SATISFIED.

## Gate 1 — candidate identity + drift (re-verified at start, in-session)

- `git rev-parse HEAD` = `edf5389873e4d4a2a4752ee0aa2159289398495e` (tasked base).
- F1-fix VERIFIED owned byte-exact: `harness_worker.py ced79ed5…7867`,
  `cli_gateway.py f9dda17e…07b8a`, `test_integration_harness_worker.py
  e96db8d0…70b45` (full-sha recompute match).
- Fix-owned byte-exact at VERIFIED hashes: `dialectic_runner 19a2e448…8283b`,
  `test_dialectic 6e059f08…f1019`, `__init__ 10571421…bac40`.
- Tracked mods exact: `cli.py 33476f34…124bb` (576/0), `dispatch.py
  dc75c56e…13c7` (333/7); numstat identical to F1-verify baseline.
- HEAD move `4544190 → edf5389` is evidence-only: the inter-HEAD diff touches
  zero paths outside `docs/builds/` (numstat grep-confirmed) — no product-code
  drift between the P05-fix live shapes and this candidate.
- Gate 1: SATISFIED — no unexplained drift, proceeding.

## Gate 2 — pins + read-only repos (open; re-probed before/after every leg)

- sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (status clean), prompt-kit
  `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`, trace
  `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7` — all exact at B1.
- SST, prompt-kit, trace, trace-lite are READ-ONLY for this stage. If evidence
  shows an SST contract change is necessary, it returns WITH evidence + a
  concrete proposed diff; no edits here. `trace-lite/` is never listed/read.
- Gate 2: SATISFIED (standing per-leg guard).

## Gate 3 — environment + live path

- Joint `trace/.venv-linux/bin/python` 3.12.3
  (`PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`, all three
  present, no recreation) — matches the P05-fix diag precedent; all probes run
  here for single-interpreter consistency. `PYTHONDONTWRITEBYTECODE=1`, cwd
  `ws/stc`. (Real-gates reserved for the later acceptance stage, not mine.)
- codex-cli `0.154.0`; operator login `~/.codex/auth.json` present; base config
  `model = "gpt-5.6-luna"` + `model_reasoning_effort = "max"`.
- Zero competing processes at B1 (no python/codex/stc/node beyond own shell).
- Live path (every probe): `CLIModelGateway`/`CLIGatewayBackend("codex")` +
  `GatewayRequest(role="diverge", temperature=1.2, max_tokens=2048)` (controller
  §2 shape) + single `cli` TEST profile (B2-faithful wiring per `cli.py:1409+`:
  profile-only registration, no routes) → fixed confined argv
  (`codex exec --skip-git-repo-check -s read-only -C <scratch> --ephemeral -o
  … -`, plus `--model X` ONLY on pre-registered model legs) with scratch cwd,
  seeded scratch CODEX_HOME (deleted after), pre/post tracked+full status,
  sst clean pre/post, header capture. No mocks on live legs.
- F1 sidecar (`spend-ledger.failures.jsonl` per probe) carries full bytes for
  every failure diagnosis; timeout legs still lose agent stderr by construction
  (process killed) — recorded as served-hang, not diagnosed from bytes.
- Gate 3: SATISFIED.

## Gate 4 — recorded baseline (0 new calls; the comparator for every probe)

- B-real: M1 4364 B prompt (sha `3154b3bb…f391b61`) + baseline frame + codex
  default model (gpt-5.6-luna) + reasoning max + 280 s → SERVED TIMEOUT
  exit 124, 0 B (B2 call-1 281.4 s; diag-retry 282.1 s; 60 s misrun hanging at
  cutoff). Shaped stdin 5044 B (frame + `user: ` + SST verbatim + tail).
- B-small: diverge-shaped small prompt + same path → OK 35.5 s, 955 B valid
  JSON (`task` + 2 `branches`). Header: codex 0.154.0 / gpt-5.6-luna /
  read-only / reasoning max / scratch workdir.
- Capacity transients: 2 fast exit-1/0 B legs (`Selected model is at capacity`
  ×2 in full stderr), interleaved with served legs — fail-loud, minutes-scale.
  A capacity refusal is UNSERVED (not a served failure): 150 s cooldown, one
  retry, still spends budget.
- Gate 4: SATISFIED.

## Hypothesis order (B1-justified): H0 → H3 → H4 → H1 → H2

- H0 (capacity/transient) FIRST as controls: P0 re-confirms B-small on the
  current candidate (path alive?); P1 re-checks B-real with a SHORT timeout
  (hang reproduces past the known 60 s mark without a 280 s sink?).
- H3 (output enormity / reasoning) FIRST among variations: it varies ZERO
  prompt bytes (purest isolation — identical shaped stdin hash), directly tests
  whether reasoning-max drives the hang (whole 280 s budget spent reasoning,
  never emitting; `reasoning summaries: none` hides it), and a win is a
  one-line STC-owned profile change. Hang-signature fit: strongest (a
  context-starved or conflicted model emits *something wrong*; a max-reasoning
  model on an enormous single artifact plausibly never converges to emission).
- H4 (instruction conflict) second: STC-frame-only bytes change (SST verbatim);
  cheap reconciliation sentence; hang-fit weaker (dither), but cheap to rule out.
- H1 (context deficit) third: STC-frame context append (SST verbatim, NO
  `allowed_paths`/target widening); hang-fit weakest (missing context usually
  yields wrong-fast, not hang-slow) — but a win here is decisive for the
  pins-task feasibility question.
- H2 (fragmented invariants) last: most invasive (frame restatement, or
  simulated-rejoin bytes standing in for an adapter fix + version bump that
  would follow only on a win); 36-shard shape is real but its link to the hang
  is the least mechanical.
- R1 stays deferred (no blocking evidence at B1).

## Per-probe matrix (one lever per probe vs Gate-4 baseline; ≤2 served failures per H)

| Probe | H | Single lever vs baseline | SST bytes | Shaped bytes | Timeout | Stop/next |
| --- | --- | --- | --- | --- | --- | --- |
| P0 H0a | H0 | small prompt (B-small re-confirm; exact B1 string) | n/a (small) | B-small hash | 120 s | ok→P1; fail→diagnose, H0 open |
| P1 H0b | H0 | SHORT timeout only (150 s vs 280 s) | 3154b3bb… (verbatim) | B-real hash | 150 s | hang→H3; ok→WIN path; capacity→cooldown+retry once |
| P2 H3a | H3 | reasoning medium (scratch config; argv+bytes identical) | verbatim | B-real hash | 180 s | ok→WIN path; served-fail→P3 |
| P3 H3b | H3 | reasoning low (stronger dose; bytes identical) | verbatim | B-real hash | 180 s | ok→WIN path; served-fail→close H3, open H4 |
| P4 H4a | H4 | frame +conflict-reconciliation sentence | verbatim | NEW (recorded) | 180 s | ok→WIN path; served-fail→P5 |
| P5 H4b | H4 | frame +complete-anyway anti-dither sentence (distinct variant) | verbatim | NEW (recorded) | 180 s | ok→WIN path; served-fail→close H4, open H1 |
| P6 H1a | H1 | frame +runner/API source excerpts (~2–4 KB) | verbatim | NEW (recorded) | 180 s | ok→WIN path; served-fail→P7 |
| P7 H1b | H1 | frame +minimal-signature context (smaller dose) | verbatim | NEW (recorded) | 180 s | ok→WIN path; served-fail→close H1, open H2 |
| P8 H2a | H2 | frame +coherent pin restatement (shards kept verbatim above) | verbatim | NEW (recorded) | 180 s | ok→WIN path; served-fail→P9 |
| P9 H2b | H2 | SIMULATED-rejoin bytes (stand-in for adapter fix; real fix iff win) | rejoined (recorded) | NEW (recorded) | 180 s | ok→WIN path + adapter-fix follow-up; fail→close H2, report |

- WIN = content parses per INSPECTION §2 (SST's own `_parse_json_dict` +
  `_clean_code`: dict with non-empty `branches`; `branches[0]` has non-empty
  cleaned `proposed_changes`; title/rationale recorded). On WIN: STOP
  experimenting, preserve everything, report WINNER + exact reproduction (the
  driver + probe dir are the reproduction; acceptance itself is later, not mine).
- Served failure = exit-124 timeout at cutoff (0 B, process alive until kill)
  or served exit≠0 with provider output — counts toward the hypothesis's 2.
  Unserved = capacity refusal / harness spawn failure — cooldown + at most one
  same-shape retry, spends budget but not the 2.
- Capacity/header confession rule: every H3 leg is VOID (not a served failure)
  unless `header.txt` shows the intended `reasoning effort:` value.
- Inter-leg pause 30 s; post-capacity pause 150 s (P05 precedent).
- Budget: ≤14 CLI calls TOTAL here (6-call reserve NEVER touched). Planned max
  10 (P0–P9) + up to 4 capacity retries. Every call lands in `attempt-1/spend.jsonl`.

## Per-probe record (under `attempt-1/<probe>/`)

`variation.json` (lever diff vs baseline) + `prompt-src-sha256.txt` +
`prompt.txt` (shaped stdin) + `stderr.txt` + `stdout.txt` + `header.txt` +
`config-toml.txt` (scratch config used) + `argv.txt` + `cwd.txt` + `exit.txt` +
`byte-counts.txt` + `outcome.json` (incl. §2 validity verdict) +
`spend-ledger.jsonl` + `spend-ledger.failures.jsonl` (F1 sidecar) +
`status-before/after-tracked/full.txt` + `sst-before/after.txt`.

## B1 verdict: READY

No B1 evidence changes the plan: proceed P0 → P1 → H3 → H4 → H1 → H2 per the
matrix. No commits, no STATE.md writes. Driver: `/tmp/liveexp-probe.py`
(preserved copy under `attempt-1/`).

## Spend (B1)

CLI calls so far: 0. Cap 14 → 14 remain (reserve 6 intact, untouched).
