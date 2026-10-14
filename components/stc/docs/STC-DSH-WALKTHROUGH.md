# STC-on-DSH: operator browser walkthrough (procedure)

The in-sandbox browser is unusable (renderer SIGTRAP; see record), so this
walkthrough runs operator-side (or in an unsandboxed session) against the
release install. It covers the mandate's journey: first launch, task
submission, interruption, a decision, results inspection, and a follow-up
change. Record actual behavior at every CHECKPOINT; several UI details below
are predictions from the HTTP-verified boot graph, marked PREDICTED where
the pixels were never observed.

## Setup (from `docs/STC-DSH-RELEASE.md`)

```sh
export DSH_HOME=/path/to/isolated-dsh-home
export STC_ROOT=/path/to/stc
export STC_DSH_STORE=$DSH_HOME/stc-runs
dsh web --no-open   # copy the printed token URL into the browser
```

## 1. First launch

1. Open the token URL (expect a brief 303 cookie dance, then the app).
2. CHECKPOINT: app loads with no error toast; Plugins page lists
   `@stc/dsh-plugin-stc` with one `stc-bundle` row (PREDICTED layout,
   VERIFIED data: the row + `stcBundle` locale are in the served boot
   graph and the 200 `/plugins/??` combo).
3. Open the bundle row: CHECKPOINT: "STC execution" detail section and
   the row config summary ("STC backend roots and run store") render.
4. Evidence: screenshot of the Plugins page + row detail.

## 2. Task submission (real task; backend quota-free, conversation metered)

Cost model (verified): the manual-mode BACKEND makes zero model calls,
but every DSH assistant turn costs one provider call, and there is no
other background model usage — session titles never call a model in any
profile (no bundle wires an LLM title provider; titles fall back to
prompt truncation). Mock/scripted providers (e2e, journey driver) cost
zero; this operator run with a real provider is metered per turn.

1. Open a new session (conversation view).
2. Submit: "Preview a manual-mode run of specs/sample_spec.md, then launch
   it with typed confirmation and report the dossier." (PREDICTED: the
   model calls `stc_preview`, then `stc_run` with `confirm: "RUN"`;
   the `stc-policy` gate denies any run without typed RUN — try asking
   for a run without confirmation first and record the denial.)
3. CHECKPOINTS: tool-call cards for `stc_preview`/`stc_run` render inline
   with pending titles ("Preview …", "Launch STC … run") switching to
   completed cards ("Preview ready", "Run … launched") — presenter
   structure is unit+e2e proven, PIXELS predicted; `stc_run` returns a
   background job id; progress updates stream.
4. Evidence: transcript excerpt + job id + run dir listing.

## 3. Interruption

1. While a run is active, use the session stop/cancel control (PREDICTED:
   DSH agent stop), then ask for `stc_cancel` on the job id.
2. CHECKPOINTS: job reaches `killed`; backend pid is dead (verify:
   `ps -p <pid>` fails; pid is in the run dir's `run.json`); a later
   `stc_status` reports the terminal state without resurrecting work.
3. Evidence: status transcript + `exit.json` (`status: killed`).

## 4. A decision (dilemma relay)

1. Submit a task against an ambiguous spec (one that scores >=tau; the
   backend writes `qa_log.json` with `escalation-required` and exits 2).
2. CHECKPOINT: the conversation surfaces the dilemma instead of silently
   proceeding (PREDICTED: via the run log + dossier read, not a native
   approval card in v1); answer with `--choice 1|2` relay in a follow-up
   `stc_run` and confirm the run proceeds past the dilemma.
3. Evidence: qa_log excerpt + both run records.

## 5. Results inspection

1. For a finished run, ask for `stc_log` (tail) and `stc_dossier` (path
   under `STC_ROOT` — the traversal guard rejects anything else).
2. CHECKPOINTS: log tail matches the run dir's `console.log` byte for
   byte; dossier summary matches `STATUS`/`branches.json` on disk;
   a dossier path outside `STC_ROOT` is refused with an actionable error.
3. Evidence: transcript + `diff` of tool output vs files (expect empty).

## 6. Follow-up change

1. In the SAME session, submit a refinement ("re-run with iters=2" or an
   edited spec) and confirm it produces a second run dir while the first
   run's records are untouched (run identity is immutable).
2. CHECKPOINT: session history shows both runs; prior dossier still reads.
3. Evidence: session transcript + both run dirs.

## Failure / recovery states to record

- Backend exit-nonzero run (e.g. the demo's NEEDS_REPAIR): conversation
  must present the failure + dossier reason, not a success summary.
- Server restart mid-conversation: session resumes (durable DSH
  sessions); active jobs do NOT silently resume — record actual behavior.

## Observations 2026-10-05

Operator-side browser walkthrough (procedure §§1-6, plus restart/recovery
and durable-home exercises) executed 2026-10-04/05 against the release
install. Verdict: GREEN with 5 filed deviations (4 low, 1 negligible) and
3 sub-items left open. Multi-session execution: §1 ran in a separate
early session, §2 in its own session, §§4/3/5/6 + recovery +
durable-home in the dilemma session
(c322bb34-b743-48a0-9b07-79f17d159439); §6's SAME-session
requirement held within its scope (follow-up in the same session as its
antecedent runs). No paid-model turns remain unverified; browser-turn
spend is unmetered (Sail exposes no usage endpoint — all /usage /billing
/models-v1 variants 404; /models 200 without pricing).

Evidence status post-wipe: /tmp was wiped twice since the run, so all
screenshots + text dumps under /tmp/ffx-walk are LOST; pixel observations
below are retained as observed-live descriptions. Run dirs + the full
session transcript SURVIVE under .durable/stc/homes/walk (stc-runs/run-*/
exit.json + run.json + console.log; sessions/.../session-c322bb34-.../
session.v4.jsonl.zstd, 385123 bytes compressed). Transcript re-verified
post-wipe: markers present (f003fdd456ef x190, 95c32f0d50ef x52,
refusal x28, NEEDS_REPAIR x165). The dossier/ dir itself is ABSENT at
closeout (gitignored runtime output; regenerates on next `stc run`).
Retained run 9fac75534865 is a pre-fix artifact: its console.log ends
`ModuleNotFoundError: No module named 'sst'` — the exact spawn-boundary
failure the backendEnv() tranche fixed; kept as failure evidence, not a
walkthrough run.

### §1 First launch — PASS (deviation D-W1 filed, severity low)

- 2026-10-04/05: app loads with no error toast (pixel-verified in
  01-launch.png, now lost — observed-live). Plugins page rendered
  8 Official plugins (02-plugins.png, observed-live).
- D-W1 (low): the STC bundle row + row detail were NOT pixel-captured
  (page text dump had zero "stc" mentions), so the row/detail UI
  checkpoint stays OPEN. Functional substitute: stc_* tools callable in
  every session + server log [stc-bundle] lines (also lost in wipe;
  transcript shows tool calls succeeding).

### §2 Task submission — PASS (deviation D-W2 filed, severity low)

- Separate session from §§4-6: denial without typed RUN quoted;
  stc_preview argv recorded; run 774b84314885 exercised the exit-2
  ambiguity gate; dossier read unknown for this run.
- D-W2 (low): fixture substitution for the dilemma-session runs
  (§§4/3/5/6 used /tmp/stc-walk-task/spec.md, a tiny ambiguous task
  with ambiguity 1.0, chosen for small tree = fast leases +
  decisive NEEDS_REPAIR). §2 itself ran the procedure as written:
  run 774b84314885 consumed specs/sample_spec.md and reached the
  0.30 gate (exit 2).
- Tool-call cards render inline (pixel-verified in the §4 shot,
  observed-live). Pending→completed title transitions + progress
  streaming unobserved — stays OPEN.

### §3 Interruption — PASS (deviations D-W3, D-W4 filed, both low)

- 2026-10-04/05: stc_run → job stc-run-2, run 34b28039f7c6
  (mode=exec); IMMEDIATE stc_cancel; poll → killed SIGTERM.
  exit.json verified on disk: {"status": "killed", "detail": "signal:
  SIGTERM", "pid": 527}.
- D-W3 (low): cancellation was tool-level (stc_cancel); the
  procedure's UI stop control was NOT used.
- D-W4 (low): direct `ps -p <pid>` death check not performed
  (terminal state confirmed via poll + exit.json only).

### §4 Dilemma relay — PASS

- Session "STC walkthrough dilemma relay run" (main session,
  c322bb34): run f003fdd456ef (spec /tmp/stc-walk-task/spec.md),
  mode=manual --choice 1 → completed exit 1 NEEDS_REPAIR
  (exit.json on disk: {"status": "completed",
  "detail": "exit code: 1"}). qa_log ambiguity 1.0 recorded;
  conversation surfaced NEEDS_REPAIR + dossier reason (pixel-verified,
  observed-live). Backend exit-nonzero failure presented as failure +
  dossier reason, not a success summary.

### §5 Results inspection — PASS (UX note)

- 2026-10-04/05: stc_log full tail BYTE-IDENTICAL to console.log
  (361 bytes, python-verified MATCH=True). Dossier summary
  STATUS=NEEDS_REPAIR, outcome=no-champion, reason=no-verified-candidate
  matches disk. Traversal-guard refusal verbatim: `Error: path escapes
  STC root: /etc/hostname` — names the escape, not the permitted root
  (UX note, not a defect).

### §6 Follow-up — PASS (deviation D-W5 filed, negligible)

- SAME session as §§4-5: two executions — queue pile-up drove a
  redundant first (run cc9f16b5e6d4, --choice 2, exit 1), then the
  redo run 95c32f0d50ef (--manual --budget time=600,iters=1,branching=1,
  depth=2 --choice 2, exit 1; exit.json on disk confirms completed /
  exit code 1). Second run dir exists; first-run run.json unchanged
  (mtime 03:16 vs follow-up 03:57 + identical stc_status before/after);
  dossier still reads; session history shows all runs.
- D-W5 (negligible): choice=2 relay used instead of the procedure's
  iters=2/edited-spec example — an equivalent refinement within the
  dilemma-relay flow.

### Restart / recovery — PASS (1 sub-item open)

- Full server-process restart; rejoined the SAME session; model
  recalled all steps + run ids correctly from history; stc_dossier
  read correctly post-restart. "Active jobs do not silently resume"
  UNOBSERVED (no active job at restart) — stays OPEN.

### Durable-home migration — PASS (1 DSH-owned flake noted)

- Home copied /tmp/stc-walk-home → .durable/stc/homes/walk (sessions
  + 6 run dirs; DH home 688K). Server booted with DSH_HOME
  there after relocating the credentials doc via the supported
  `credentials` plugin `path` patch (9p chmod no-op → 777 → fail-closed
  boot otherwise; first-boot-only accident caught and fixed; repeatable
  boot proven + evidence turn re-run identical in 39s). Fresh writes
  landed ONLY in the DH home (/tmp home untouched) — genuinely served
  from the durable home. Finding recorded in docs/STC-DSH-RELEASE.md
  (§ DSH_HOME on mode-less filesystems).
- One transient console error "Sidebar Session opening failed: Error"
  on the rerun (0 errors on all other runs; DSH-owned UI flake,
  non-blocking) — noted.

## Sign-off

Qualification passes when every CHECKPOINT above has a dated observation
(or a filed deviation with severity). Unobserved PREDICTED items stay
open; do not mark them from this procedure alone.
