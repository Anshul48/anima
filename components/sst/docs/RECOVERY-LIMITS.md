# SST recovery limits

The event log (`SQLiteSSTStore`) is the source of truth; the DAG read model is
rebuilt by replay (`rebuild_tree_from_events`). Recovery reconstructs results,
it does not resume execution.

## Finished marker

`SEARCH_COMPLETED` is appended on every terminal path (champion, no-candidate,
budget-exhausted, cancelled). A tree without it did not finish.
`get_search_result` raises `IncompleteSearchError` for missing or unfinished
trees. Callers must treat that as "unknown, re-run" — never success.

## Reconstruction fidelity

- Proposals carry fields persisted in `NODE_PROPOSED`/`SYNTHESIS_PROPOSED`
  payloads. Timestamps and unpersisted in-memory fields differ from the live
  envelope.
- `VERIFIER_FINISHED` payloads truncate stdout/stderr to 500 chars each; the
  full text lives only in the live `DeterministicGateResult`.
- Scores rebuild from `SCORE_RECORDED` (value, verdict, critique); original
  `raw_metrics` and full `hard_gates` maps are not all persisted.
- `gateway_bindings` persist in `SEARCH_COMPLETED` and rebuild exactly.
- Outcome events (`OUTCOME_REPORTED`) are never replayed into node state.

## Idempotency and re-runs

- `append_event` returns the existing sequence id when `idempotency_key`
  already exists: replaying with the same deterministic keys converges.
- Exception: `PROVIDER_ERROR` events carry unique keys; each provider failure
  is a distinct audit record and re-runs append new ones.
- There is no mid-run resume: recovery answers "what happened", not "continue
  where it stopped". Crashed runs must be re-run under a new or resumed
  `tree_id` according to caller policy; duplicate `tree_id` appends are the
  caller's responsibility (optional writer leases guard contention).

## What recovery does not guarantee

- Verifier stdout beyond the truncation cap.
- Restoration of in-memory budget trackers, gateway sessions, or worker threads.
- Validity of results against a changed workspace (see promote-time base-commit
  and snapshot checks, which run independently of log recovery).
