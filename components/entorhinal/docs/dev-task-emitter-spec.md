# Dev-task emitter / verifier harness spec (M1-source, EAP-20261004-v0.2)

Source `entorhinal.dev-task.01` captures real newly-executed development work.
This spec defines the two EXTERNAL processes that publish into the inbox and
the independence rules that keep Entorhinal an observer, not an executor.

Reference implementation: `scripts/dev_task_emit.py` (stdlib-only).
Manifest draft: `/tmp/entorhinal-coordinator/evidence/producer-manifest-draft.json`.
Envelope schema: `src/entorhinal/schemas/task_event.py`
(`entorhinal.task-event/v1-draft`). Tailer: `src/entorhinal/sources/dev_task.py`.

## 1. Roles and non-goals

| Role | Owns | Must never |
| --- | --- | --- |
| Task emitter (external) | Publishing explicit goal/start/pause/resume/decision/correction/observation events and attempt records from REAL newly executed commands | Import Entorhinal admission internals to self-approve; Entorhinal never instructs it to run a command |
| Requirement verifier (external, independent) | Checking task outcomes from ARTIFACT BYTES and publishing `checked-outcome` events | Derive verdicts from event narratives, excerpts, or producer assertions |
| Entorhinal tailer (`DevTaskSourceAdapter`) | Tailing the one configured inbox file, producer-side redaction, bounded sanitized spool, truthful health | Execute commands, crawl repos, watch anything else |

A command exit status is an observed check result. A task is complete only
when its stated requirement is independently verified from artifacts.

## 2. Inbox protocol

- Location: exactly one resolved file, `capture-inbox/task-events.jsonl`
  under the coordinator run dir, named in the producer manifest.
- Format: one complete JSON object per line (UTF-8, `\n`-terminated).
  Partial trailing lines are ignored until completed by the writer.
- The tailer starts at the recorded activation boundary byte offset; bytes
  before the boundary are never read.
- Every line carries a full `entorhinal.task-event/v1-draft` envelope:
  stable source-local `event_id` assigned before delivery,
  `producer_run_id` + monotonic `producer_sequence`, work identity,
  kind, timing, payload, epistemic status, revision links, admission and
  assistance blocks. Undeclared fields are rejected (`extra="forbid"`).
- `event_id` is the idempotency key: a client whose delivery failed retries
  the SAME event object; a genuinely repeated observation gets a NEW id.
- `admission.grant_revision` must equal the manifest grant revision;
  `source_id` must equal the configured source id. Both come from runtime
  configuration, never from caller-supplied labels.

## 3. Emitter behavior

### 3.1 Identity and sequencing

- `producer_run_id`: one UUID per emitter run state, persisted in
  `<run-dir>/emitter-state.json`.
- `producer_sequence`: monotonic counter persisted in the same file,
  incremented per emitted event. Gaps in the observed sequence are a
  visible tailer health signal, not silently repaired.
- `producer_version`: emitter implementation version
  (reference: `dev_task_emit/v1-draft`).

### 3.2 Goal / lifecycle / decision / correction / observation

- `goal` (epistemic `assertion`): states the task goal in
  `payload.condition` plus a short excerpt. Requires `work.session_id`
  and `work.task_id`.
- `lifecycle` (epistemic `assertion`): `payload.value.transition` in
  `start | pause | resume | complete | abandon`.
- `decision` (epistemic `assertion`): `payload.value.choice` records the
  selected option; `payload.condition` states the decision.
- `correction` (epistemic `correction`): targets `revision.corrects[]`
  event IDs and/or `revision.supersedes[]` with a stable `claim_key`.
- `observation` / `source-status` (epistemic `observation`): short
  diagnostic notes; excerpts bounded (4 KiB each, 8 max, 16 KiB total).

### 3.3 Attempt records (real execution only)

The emitter EXECUTES the command in an external harness (`subprocess` in
the reference) and records:

- `payload.attempt.attempt_id`, `command_identity` (exact argv),
  optional `check_identity`, `started_at` / `ended_at` (real wall clock),
  real `exit_status` (None only when the process never exited:
  timeout or spawn failure, recorded in `payload.value.failure_reason`),
  optional `working_directory`.
- `payload.outcome`: `succeeded` (exit 0), `failed` (non-zero exit),
  `inconclusive` (no exit status).
- `payload.excerpts[]`: bounded tail of combined stdout/stderr
  (deliberately emitted short diagnostics only; no env dumps).
- Synthesized, replayed, or guessed attempt records are forbidden: every
  attempt event corresponds to one real process execution. The reference
  emitter refuses to emit an attempt without executing.

### 3.4 Payload hygiene

- Excerpts are bounded by the schema and redacted producer-side before
  spool persistence (shared deterministic policy redaction helpers).
- No credentials, tokens, private keys, env dumps, historical chats, or
  personal data in any field. The emitter SHOULD pre-scan excerpts and
  refuse to emit on a positive secret-pattern match.
- `payload.value` is a bounded string-keyed scalar map (32 entries max).

## 4. Verifier behavior (independent requirement check)

The verifier answers ONE question per run: does the task's PREDECLARED
requirement hold, judged from artifact bytes? Procedure:

1. Take the requirement statement (`--requirement`) and a set of artifact
   predicates, all evaluated against file bytes:
   - `--require-file PATH[:SHA256]`: file exists (and matches hash);
   - `--require-contains PATH:SUBSTRING`: file bytes contain a marker
     (e.g. a test-run summary line, a build stamp).
2. Every checked path must be on the manifest artifact allow-list;
   non-listed paths fail the check (default-deny).
3. Verdict `succeeded` iff ALL predicates hold, else `failed`.
4. Publish ONE `checked-outcome` event (epistemic `checked-outcome`)
   with `payload.outcome`, `payload.condition` = requirement text,
   `payload.value` = `{checks_run, checks_failed}`, a short
   `verifier-report` excerpt, and `payload.artifact_refs[]` carrying
   exact path + sha256 + revision + `verifier` identity for every
   artifact examined.
5. The verifier MUST NOT read prior event narratives to decide; it reads
   artifact bytes. Its evidence (path/hash/revision) is distinct from any
   producer assertion that an attempt succeeded.

## 5. Manifest consistency

The producer manifest and this harness agree on:

- `source_id` = `entorhinal.dev-task.01`;
- `inbox_path` = exact resolved inbox file (draft points at the intended
  coordinator run dir; finalize at activation);
- `activation_boundary_offset` = inbox byte size recorded by `init`;
- `permitted_fields` = the envelope field tree in §2 (any other field
  rejected);
- `artifact_allow_list` = exact `{path, sha256?, revision?}` entries;
  empty by default (every `artifact_ref` rejected until entries are added);
- `grant_revision` mirrored into every event's `admission.grant_revision`;
- `retention_class` mirrored into every event's `admission.retention_class`.

Finalization checklist before capture: create run dir + inbox, record the
boundary, add allow-list entries for every artifact the verifier will
cite, ratify the grant revision in BOTH manifest and emitter state.

## 6. Reference CLI walkthrough

```bash
PY=<workspace-root>/entorhinal/.venv-linux/bin/python
RUN=/tmp/demo-run
MAN=/tmp/entorhinal-coordinator/evidence/producer-manifest-draft.json

$PY scripts/dev_task_emit.py init --run-dir $RUN --manifest $MAN
$PY scripts/dev_task_emit.py goal --run-dir $RUN --manifest $MAN \
    --session s1 --task t1 --text "Fix login redirect"
$PY scripts/dev_task_emit.py lifecycle --run-dir $RUN --manifest $MAN \
    --session s1 --task t1 --transition start
$PY scripts/dev_task_emit.py attempt --run-dir $RUN --manifest $MAN \
    --session s1 --task t1 --attempt a1 --check pytest-login -- pytest -q
$PY scripts/dev_task_emit.py verify --run-dir $RUN --manifest $MAN \
    --session s1 --task t1 --attempt a1 --requirement "login tests pass" \
    --revision r1 --require-file /path/to/report.xml
```

Add `--validate` to any emit command to check the record against the live
Entorhinal envelope when the package is importable.

## 7. Failure and abuse cases

- Malformed line / wrong `source_id` / grant mismatch / undeclared field /
  non-allow-listed artifact path: tailer records an attributable
  denial/error disposition, advances past the line, and exposes
  denied/malformed counts in health. No silent loss, no silent repair.
- Inbox truncated or rotated: visible `gap` state; tailer resumes at
  current EOF and reports the gap interval.
- Spool budget (10 MiB) reached or volatile queue saturated: `backpressure`
  state; admission pauses; nothing is discarded.
- Verifier artifact missing or hash mismatch: verdict `failed`, published
  as evidence like any other outcome.
