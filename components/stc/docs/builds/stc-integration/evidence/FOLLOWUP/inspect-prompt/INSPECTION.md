# FOLLOWUP — Coordinator inspection: failing prompt + response contract + emitter context

Author role and date: coordinator / 2026-09-14
Goal: bounded follow-up to achieve live success (20 CLI calls, ≥6 reserved for acceptance+verification)
Candidate: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` + loose set
(6 fix-owned hashes re-verified match; sst `079f4de6` clean; no duplicate workers —
11/11 subagents terminal, zero python/codex/node/stc processes at inspection time).
Method: read-only source + evidence reads. Zero live calls spent.

## 1. Exact failing prompt (identity)

- M1 bytes: `evidence/P05/attempt-1/trial-timeout/p05-diverge-prompt.md` (4364 B).
  P05-fix diags replayed these bytes verbatim (sha `3154b3bb…f391b61`, B3-verified).
- Live B2 (P05-fix) sent a freshly compiled prompt (same spec/shape; own bytes not
  preserved — F1 gap); it timed out identically (281.4 s, exit 124, 0 B).
- Confined emitter input = `shape_gateway_prompt` frame + `user: ` + SST bytes
  verbatim-once + tail (re-verified byte-exact: 5044 B shaped / 4364 B SST).
  Frame: `src/stc/integration/cli_gateway.py:71-97`.

## 2. Response contract (SST side, read-only)

- `SSTSearchController._generate_divergent_candidates` (`sst/.../controller.py:414`):
  `GatewayRequest(role="diverge", temperature=1.2, max_tokens=2048)`.
- Response content must JSON-parse to `{"branches": [...]}`; each branch needs
  `strategy_title`, `hypothesis_or_rationale`, `proposed_changes` → `_clean_code`
  → `patch_diff` against `allowed_paths[0]` (= `tests/unit/test_integration_runner_pins.py`).
  Fallback: raw-code parse of the whole content.
- `max_tokens=2048` and `temperature=1.2` are IGNORED on the CLI path (codex exec
  honors neither); output length and sampling are provider-determined.

## 3. Emitter-context verdict: NOT complete — zero source context

The confined emitter receives the full task spec (as invariants, see §4) but
NO source code of the system under test:

- `CONTEXT REPOSITORY FILES` in the M1 replay = target file containing the
  1-line sentinel `this definitely does not exist` (an M1 harness out-of-loop
  write, since removed — P05 attempt REVIEW).
- In the CURRENT tree `tests/unit/test_integration_runner_pins.py` is ABSENT
  (ls-confirmed), so a fresh run compiles `relevant_files={}` (SST
  `ContextCapsuleCompiler` skips missing files) — the files block is EMPTY.
- No `DialecticRunner` source, no contracts, no API signatures reach the emitter;
  it must author a complete test module exercising `run_async` merge/audit paths
  and exact typed reasons (`merge-apply-failed`, `reselect-reconstruction-failed`,
  `RT-08`) for unseen APIs.

## 4. Invariant fragmentation (STC-side chain, SST template only renders)

The prompt's SYSTEM INVARIANTS hold 36 `- bundle:`-prefixed LINE FRAGMENTS,
many mid-sentence (e.g. `- bundle:cleanly at verify time but ... FAILS at merge
time`; `- bundle:The candidate patch MUST be a unified diff (raw code can never
pass the` — cut off). Chain (all STC-owned except the final render):

1. `socratic/decomposer.py` splits spec prose per cleaned LINE into
   `domain_invariants.invariants` (one entry per source line).
2. `compiler/bundler.py:274` copies them into `TaskBundle.invariants`.
3. `integration/adapters.py:355` tags each `bundle:` into the packet.
4. SST template (`sst/.../prompts/dialectic.py`) renders `- {inv}` per entry.

The model never sees a coherent invariant paragraph — only shards. Whether this
contributes to the timeout is UNPROVEN (hypothesis H2, not a finding).

## 5. Explicit hypotheses for bounded experiments (agency-dominance NOT assumed)

- H0 capacity/transient: provider-side slowness/refusal. Control: small-prompt
  success + cheap short probes; rule out WITHOUT 280 s repeats.
- H1 context deficit (§3): no source context stalls authoring a complete module.
  STC-owned lever: context packaging in the emitter frame (verbatim SST bytes
  stay intact; do NOT widen `allowed_paths`/target_files — that would authorize
  modifying the runner).
- H2 fragmented invariants (§4): 36 shards vs coherent spec. STC-owned lever:
  adapter/frame-level rejoin or restatement (membrane bytes change ⇒ adapter
  version bump; decomposer core edits OUT of scope).
- H3 output enormity: complete module in one JSON field, one call, reasoning
  max → timeout. STC-owned levers: reasoning-effort variation, output-schema
  shaping (smaller first artifact? NO — acceptance task is fixed; vary only how
  the SAME artifact is elicited).
- H4 instruction conflict: HIGH-ENTROPY "unconstrained creative architect" +
  novelty demands vs emitter discipline + exacting typed pins. STC-owned lever:
  framing variations.

Budget for experiments: ≤14 CLI calls (20 total − 6 reserved). No repeated
unchanged 280 s attempts: vary exactly one lever per probe, prefer short
timeouts that discriminate fast, stop each hypothesis after at most 2 served
failures and move on.
