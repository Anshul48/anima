# STC manual/operator-assisted route — execution + interface contract

Release contract for the operator-assisted first release (verified
2026-09-25 on stc HEAD `7dd14a21` + release tranche; suite 679
passed / 0 failed / 6 deselected-live; trial-5 qualified champion).
A future frontend builds on THIS contract, not on CLI prose.

## 1. Entry point

```sh
cd stc
export PYTHONPATH="<sst>/src:<prompt-kit-pin>"
export STC_PROMPT_KIT_ROOT=<prompt-kit-pin>   # == pin dir (Q3)
export STC_SST_ROOT=<sst> STC_TRACE_ROOT=<trace> STC_WORKSPACE_ROOT=<workspace>
export STC_GATE_TIMEOUT_S=3600                # operator override; CLI default 120s
export STC_SOURCE_ROOT=<target-tree> STC_DOSSIER_DIR=<dossier-dir>
.venv/bin/python -m stc run <spec.md> --target stc --manual \
  --budget 'time=21600,tokens=500000,usd=10,iters=2,branching=1,depth=3'
```

Clean-checkout setup (venv, pins, env proof): `OFFLINE-SETUP.md`
§§0–3 (counts refreshed: ruff 80 files under `src tests`, mypy
--strict 80 files, pytest `-m "not live"` 679 passed). The sst tree
stays read-only; prompt-kit resolves ONLY to the byte-pinned dir
(F3c fails closed otherwise).

## 2. Paste protocol (normative)

- The loop prints one role prompt per model call (`diverge`,
  `refine`, `synthesize`, `critique`) and reads stdin to EOF.
- Paste exactly one JSON document per prompt, then EOF. It is
  validated BEFORE submission (§4); failures print every problem
  and re-prompt. Re-prompts are free — only accepted executions
  count against budget (≤8 gen/repair + ≤6 verify per policy).
- Empty input or EOF with no bytes is a harness error (failed
  invocation, fail-closed fallback downstream), never a silent skip.
- Fixture mode (`STC_MANUAL_FIXTURE_DIR`): all `*.json` files load-
  validated upfront (filename role vs content shape); any failure
  aborts with exit 2 before the loop starts. Files serve in sorted
  order; exhaustion is a harness error.
- Role/sh prompt templates: `stc manual-template <role>` (diverge,
  refine, synthesize, critique) prints the exact JSON shape. NOTE:
  the command needs the §1 env (sst import); bare shells crash.

## 3. Final outcome (single authority — frontend reads THIS)

`final_outcome` (dossier.py) is the only success definition. CLI
text, `--json` envelope, exit status, `STATUS`, `branches.json`,
`run_ref.json`, and `review.md` all key off it; they cannot disagree.

| Condition | STATUS | Exit | branches.json |
|---|---|---|---|
| Champion + judiciary APPROVED | COMPLETE | 0 | outcome=champion |
| Champion + judiciary NOT approved | NEEDS_REPAIR | 1 | outcome=no-champion, reason=`judiciary-<status>:<rules>` |
| No verified candidate / vetoed / error | NEEDS_REPAIR | 1 | outcome=no-champion, reason=`<cause>` |

- Rejected-champion records (`merged.diff`, `execution_receipt.json`,
  `judiciary_verdict.json`) are KEPT as failure evidence; only their
  success CLAIM is removed. `review.md` says UNSUCCESSFUL + "do not
  merge". Pure no-champion runs write ZERO success artifacts.
- Usage/validation aborts (bad flags, fixture load failure): exit 2.
- Frontend rule: success ⟺ exit 0 AND STATUS=COMPLETE AND
  `branches.json:outcome == "champion"` AND verdict APPROVED.
  Anything else is unsuccessful, no matter which file you read first.

## 4. Payload contracts (normative shapes)

- diverge: `{"branches": [{"strategy_title": str(non-empty),
  "hypothesis_or_rationale": str(non-empty), "proposed_changes":
  str (pure unified diff: `diff --git`/`---`/`@@` hunks)}]}`
  (1 branch in current search shape; `branch_index` accepted).
- refine/synthesize: `{"refined_title": str, "refactoring_notes":
  str, "executable_content": str (pure unified diff)}`. A
  diverge-shaped payload here parses to an EMPTY patch (validator
  rejects it first with the fix).
- critique (EITHER shape): flat `{"value_score": number[0,1],
  "verdict": APPROVE|PRUNE|ESCALATE_HUMAN, "rationale": non-empty}`
  or cortex `{"evaluations": [{"value_score", "verdict":
  APPROVE|PRUNE|SYNTHESIZE|ESCALATE_HUMAN, "critique": non-empty,
  ...}]}` (first item governs).
- Fences: leading/trailing ```json / ``` wrappers are stripped
  before parsing (mirrors the SST controller on all roles).
- Shape mismatch (right JSON, wrong role) is an explicit error
  naming the expected keys + `stc manual-template <role>`.

## 5. Worker-visible judiciary constraints (verbatim, enforced)

These four lines ship in every role prompt (bundle invariants →
capsule → prompts) AND in the auditor. Violations REJECT even
fully green candidates:

1. zero-mock, 0% mocks: added lines must not import/use
   unittest.mock, MagicMock, mock.patch, mock.Mock, nor assert on
   mocks. Hand-rolled fakes (plain classes, real assertions, no
   mock imports) are legitimate.
2. fail-closed fallbacks: no empty excepts, no silent empty returns.
3. no hardcoded secrets (16+ char literals to key-named vars).
4. immutable contracts (01_INVARIANTS.md text; protocols/schemas
   interfaces).

## 6. Review veto (RT-03 + provenance)

A score is TAINTED (vetoed, recorded in `veto_log.json` with rule +
node + score + rationale/ledger cite; first match wins) when:

1. rationale is exactly `Passed all verifier acceptance tests`
   (controller fallback layer 1), or
2. score == 0.85 AND rationale is exactly `Evaluated by Cortex
   Critic` (live-path default pair, fallback layer 2), or
3. the paired critique-call witness is invalid (call failed /
   refused / content not an explicit critique object per §4 shapes
   as the controller parses them). Pairing: k-th witness-bearing
   score ↔ k-th critique call; deterministic verifier-fail scores
   consume no slot. Unwitnessed gateways fall back to rules 1–2.

Consequence: a vetoed champion with no alternative ends the run as
`champion-vetoed-no-alternative` (exit 1, NEEDS_REPAIR) — a missing
or failed review can never supply approval.

## 7. Dossier layout (stable paths)

`STATUS`, `branches.json`, `run_ref.json`, `review.md`,
`spend.json`, `spend_ledger.jsonl`, `veto_log.json`, `qa_log.json`
always; `merged.diff`, `execution_receipt.json`,
`judiciary_verdict.json` only when a search champion exists
(kept-as-evidence on rejection, §3). Per-round records under
`runs/<tree>/` (events, selection, custody, merge, receipts).

## 8. Out of scope / limitations

- Codex/muse/agy live routes: unqualified (no credentials; no
  retry). Only `--manual` is released.
- Budgets above are policy, not code defaults; the coordinator
  enforces by stopping pastes.
- Advisory (independent review, non-blocking): a non-timeout
  exception escaping `harness.execute()` records no witness while
  SST still scores, shifting later Rule-3 slots by one. Follow-up
  tranche item; fail direction preserved by rules 1–2.
