# H1 prep — Deliverable 3: STC-owned marker handling determination (MARKERS.md)

Record type: builder analysis (evidence-writing only)
Author role and date: h1-prep-builder / 2026-09-15
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (re-verified read-only; sst `079f4de6…` clean, custody bytes
`43c24681…ec864` = tolerance-NOT-landed). Method: byte census over all
live §2 payloads + code read of the STC gateway return path and every SST
`gateway.invoke` error handler (SST read-only). **0 live calls; no product
edits.** Question: can STC-owned output handling reject or safely handle
the known `***` markers WITHOUT changing patch content and WITHOUT
weakening custody?

## 1. The known marker shapes (complete live census, 6 §2 emissions)

Every live proposal payload was byte-scanned this session (`***` at any
position; Begin/End breakdown). Prior records characterized 5 of 6; the
P2-winner trailer below is newly established.

| Emission | Bytes | Shape | `***` lines |
| --- | --- | --- | --- |
| P2-H3a winner (live-exp) | 4338 | unified (`diff --git`, `b/` headers) + trailing `*** End Patch`, NO Begin (line 140/141) | 1 |
| accept-a1 cand | 3685 | pure apply_patch (`Begin`/`Add File:`/`End`) | 3 |
| a2c0 | 5182 | unified (`b/` headers) + trailing End, NO Begin | 1 |
| a2c1 | 3929 | pure apply_patch (`Begin`/`Add File:`/`End`) | 3 |
| a3c0 | 5534 | unified (bare `+++`) + trailing End, NO Begin (tail: `+`, `*** End Patch`) | 1 |
| a3c1 (pin-held) | 4299 | unified, marker-free (zero `***` anywhere — verified) | 0 |

Two shapes cover all 5 marker-bearing emissions: **trailer-only** (P2, a2c0,
a3c0 — well-formed unified diff + a lone trailing End, never a Begin) and
**pure apply_patch** (a1, a2c1). No live payload has ever carried a Begin
without the full apply_patch envelope, and none carries markers mid-hunk.

Two consequences follow. First, the P2 "WIN" was §2-parse-only: its bytes
carry the same trailer that killed a2c0/a3c0 at custody apply (strict
`git apply` rejects the trailer line; the SST fallback rejects it as
`Unrecognized diff line format … '*** End Patch'`). Parse success never
implied custody success — for 5 of 6 live emissions the pipeline's first
real filter is the marker question this record answers. Second, the
dominant failure (3/6) is the R1-salvageable trailer shape: the SST
tolerance proposal strips exactly it, while any STC-side refusal (which
must not rewrite bytes) can only discard it. Refusal-vs-salvage is the
decision, quantified in §3.

## 2. The rejected wrapper-sanitizing option, re-examined (stays rejected)

The a3-fix readiness rejected sanitizing inside `STCCustodyWrapper` on two
grounds: (i) it forks proposal identity (NODE_PROPOSED bytes vs applied
bytes vs `patch_hash` vs `render_merged_diff`), and (ii) branch (b) scoped
STC to the framing pin. The new live data strengthens (i) and adds (iii):

- (i) The fork is now concrete, not hypothetical. `patch_hash` is computed
  over the raw proposed bytes inside `apply_proposal`
  (`sst/src/sst/sandbox/custody.py:218`); NODE_PROPOSED records
  `proposal.patch_diff` as parsed (`controller.py:164-173`); the merge
  path re-applies the same proposal object (`dialectic_runner.py:838`).
  A wrapper rewrite between parse and apply makes the attested hash, the
  recorded bytes, and the merged bytes three different objects — and the
  rewrite would need shape-dependent rules (strip-trailer vs
  translate-envelope) that duplicate the SST R1/R2 logic in STC, drifting
  from the custody it shadows.
- (iii) Sanitizing silently changes judiciary coverage (PATH-REVIEW J1):
  rewritten bytes with synthesized `b/` headers would scan, while the raw
  recorded bytes would not — audit findings would attest to bytes that
  exist nowhere in the event record.
- The pin-held leg (a3c1) proves clean bytes CAN arrive, so rewriting is
  not the only road to custody success — enforcement (refusal) is now a
  live-grounded alternative where before it was speculative.

Sanitizing stays rejected. It changes patch content by definition and is
the one option that affirmatively weakens the identity chain custody
rests on.

## 3. Frame-side refusal pre-dispatch (the STC-owned option that meets the bar)

**Definition.** "Pre-dispatch" here means: inside the STC gateway return
path, after the harness serves the response and BEFORE the bytes are
dispatched into SST parsing — i.e. in `CLIModelGateway.invoke`
(`src/stc/integration/cli_gateway.py:319-346`) after
`backend.generate()` returns, or equivalently inside
`CLIGatewayBackend.generate` before `return result.content` (:240).
Validate the response; on a marker hit, raise `ProviderGatewayError` and
forward NOTHING to SST. Refusal is not sanitizing: no byte is altered,
added, or removed — the response is either forwarded verbatim or not
forwarded at all.

**Rule.** Mirror SST's own parse shape (PATH-REVIEW §1a): parse the
content with SST's `_parse_json_dict` semantics; if `branches[]` is a
non-empty list, scan each `proposed_changes` field; otherwise scan the
whole content (the raw-fallback shape). Refuse iff any scanned payload
line begins with `***` at column 0. Column-0-only matching keeps
legitimate content (` ***bold***`, indented markers) admissible — the
same predicate the validated SST proposal uses (R0), so STC refusal and
SST tolerance agree exactly on what "marker-bearing" means.

**Why the bar is met:**

- *No patch-content change.* Refused legs emit NO proposal, so
  NODE_PROPOSED / `patch_hash` / `render_merged_diff` never observe them
  — zero identity fork, the inverse of sanitizing. Admitted payloads
  travel the byte-identical current path.
- *No custody weakening.* Custody code is untouched; admitted payloads
  face identical strict-then-fallback-then-verbatim dispatch. Refusal only
  shrinks the input set custody ever sees, toward the marker-free subset
  the frame pin already targets.
- *Handled honestly upstream.* All four SST `gateway.invoke` sites catch
  the error (diverge :486, refine :551, synthesize :628 → warning + empty
  proposals; critique :726 broad-except → scripted fallback score). A
  refused leg consumes 1 live call, yields 0 proposals for that iteration,
  writes no VERIFIER events and no `pruned_attempts` entry (nothing
  became a proposal), and the frontier re-seeds root when empty
  (:120-124), so a later iteration retries within budget. The pipeline
  shape is "served error", a first-class honest outcome — not a new
  failure mode.

**Retroactive effect on the census (§1):** refusal admits exactly a3c1
(the pin-held leg) and refuses the other 5 — including the P2 winner.
That reads as harsh until compared with what actually happened to those
5: all died at custody apply or on verbatim garbage. Refusal converts
late, expensive failures (full mirror + 25–76 s gate runs) into early,
cheap ones (no lease, no gates), at identical call spend.

**What refusal costs (stated plainly):** (i) it cannot SALVAGE near-miss
shapes — the 3 trailer-only payloads die instead of being stripped (the
SST R1 path would have saved their format; wiring would still have
adjudicated them); (ii) each refused leg spends a live call with zero
proposals, so a high refusal rate burns budget faster per proposal —
mitigated by, not a substitute for, cleaner emission (H1 context, the
pin); (iii) refused bytes need forensic preservation outside the F1
harness-failure sidecar (refusal is a gateway policy decision, not a
harness failure) — specified in §5.

## 4. Determination

**STC-side handling SUFFICES for the stated bar.** Frame-side
refusal pre-dispatch (§3, specified in §5) rejects every known marker
shape without changing any patch byte and without weakening custody
(admitted payloads face byte-identical custody; refused payloads leave
no proposal records to fork). **No SST change is necessary for safety.**

An SST change remains the ONLY route to **salvage** — recovering the
trailer-only and pure-apply_patch shapes instead of discarding them.
That option already exists as a concrete validated artifact; it is cited
here by exact identity (no SST edits, no new diff proposed):

- `evidence/FOLLOWUP/a3-fix/attempt-1/sst-custody-tolerance.diff`,
  sha256 `84fb6e20…89f32` (recomputed exact this session), scope 113+/1-
  on `src/sst/sandbox/custody.py` @ sst `079f4de6`: R0 byte-identical
  fast path / R1 stray-envelope strip + redispatch / R2 Add-File
  translation / R3 loud refusal; validated (applies cleanly, gate-green
  under SST config, live-byte discrimination) in the a3-fix attempt-1
  record. Landing it is an SST-authorized decision, out of this brief.

Recommended sequencing for the coordinator: land STC refusal first (safety
floor + deterministic enforcement of the pin, STC-owned, no cross-repo
landing); pursue SST tolerance landing second (salvage yield); pursue H1
context in parallel (emission quality — every clean emission is a leg
neither mechanism needs to touch).

## 5. Precise specification for a later implement stage (STC-owned refusal)

Target file: `src/stc/integration/cli_gateway.py` (STC-owned). No other
product file need change. SST stays read-only (import-only precedent).

1. **Placement.** A module-level pure predicate +
   a 3-line call site in `CLIModelGateway.invoke` after
   `backend.generate()` returns and before the `GatewayResponse` is
   built (so refusal covers every routed role, and the spend ledger row
   — written in `backend.generate`'s `finally` — already records the
   served call honestly as `ok=True`: the harness DID serve).
2. **Predicate.** `def _refuses(response_text: str) -> str | None`
   (name illustrative): parse with SST's own
   `SSTSearchController._parse_json_dict` (import it — STC already
   imports SST read-only; do NOT reimplement the 11-line parse, drift
   risk); collect scan targets (`branches[].proposed_changes` when
   branches is a non-empty list, else the whole content); return the
   first offending line (truncated 80 chars) if any target has a
   column-0 `***` line, else `None`.
3. **Refusal error.** `raise ProviderGatewayError(f"STC gateway refused
   marker-bearing response (no bytes forwarded to SST): {line!r} …",
   category="stc_marker_refusal", remediation="Emission violated the
   unified-diff-only pin; retry or narrow the emitter frame.",
   profile=profile_name)`. Category string is new and greppable; the
   message carries the offending line, never the full bytes.
4. **Ledger honesty.** The served row keeps `ok=True` (harness truth),
   and the refusal is recorded by appending
   `stc-refused: <rule> (<sidecar>#<id>)` to the row note — the
   row must never read as a silent success. (Implementor: thread the
   note through `generate`'s return or set it before the raise; the
   `finally` logs whatever `note` holds.)
5. **Forensic preservation.** Write the FULL refused bytes to a NEW
   refusal-evidence sidecar (`<ledger-stem>.refusals.jsonl`, one JSON
   record: timestamp, profile, model, role/task label, offending line,
   `sha256` of the refused bytes, bytes). NOT the F1 failure sidecar
   (F1 scope is harness stderr; refusal is a policy decision on
   successfully served bytes). The ledger note points at it
   (`failure_note_pointer` pattern).
6. **No gateway-internal retry.** The controller's iteration loop is the
   retry layer (root re-seed); gateway-internal retries would multiply
   spend opaquely. One served response → at most one refusal → the
   controller decides next.
7. **Tests (new file, `tests/unit/test_gateway_marker_refusal.py`,
   `-m "not live"`, both interpreters, ruff + mypy-strict clean):**
   refuse matrix — trailer-only (exact P2/a2c0/a3c0 tails),
   pure-apply_patch (exact a1/a2c1 envelopes), unified+trailer,
   raw-fallback-with-markers, unparseable-JSON-with-markers;
   admit matrix — exact a3c1 bytes, the §2 known-good diff
   (PATH-REVIEW), indented `***` (non-column-0), markdown-bold
   ` ***bold***` content lines, marker-free raw code; ledger tests —
   refused row reads `ok=True` + refusal note + sidecar pointer, and
   the sidecar record round-trips the exact refused bytes by sha256;
   D-tests — SST prompt bytes still verbatim through the frame
   (D15/D7), admitted payloads byte-identical pre/post change.
8. **Non-goals.** No byte rewriting anywhere (sanitizing stays rejected,
   §2); no custody change; no J1 fix bundled in (attribution is a
   separate STC-owned change with its own tests); no threshold tuning
   (column-0 predicate is exact, not heuristic).

## 6. Interactions (for follow-up scoping, not this stage)

- The A3 pin + refusal compose: the pin constrains emission
  probabilistically (measured 1/2); refusal enforces the constraint
  deterministically. Neither subsumes the other.
- H1 context (CONTEXT.md) reduces the refusal rate at the source; J1
  (bare-`+++` scan skip) is orthogonal — refusal filters markers, not
  header styles. G1/G2 (whole-tree gates red / live tests in the gate)
  dominate live-verdict reality regardless of markers: refusal saves
  gate cost per refused leg but no admitted leg can verify while G1
  stands.

## Identity (sha256 of h1-prep evidence transcripts)

```text
# CREATED (transcripts; this MARKERS.md + sibling records CONTEXT.md /
# PATH-REVIEW.md are records and are named by path, not self-listed)
e0c814e5627f018c7cd51ae2e3e8236db044f2a782e03989c8a2317eee6adbca  evidence/FOLLOWUP/h1-prep/ctx-package.txt
717b9b1e90cc9f781c1df65f9a8b376b5ad82b4c5ca83283fa5acddc8b751c90  evidence/FOLLOWUP/h1-prep/custody.txt
e164358771fbb6d53a8a9e86580e6fb56e179491c56346dde50317dd7c46f847  evidence/FOLLOWUP/h1-prep/g2-collect.txt
51be146f7b6d6e1d408e4419dfc8ed2134a2d7f8a26b206e12b56c8a5fe0f56d  evidence/FOLLOWUP/h1-prep/gates-bad.txt
a49be87c7b648318b8f90f05ecae7f7534aed54d90f7d836c083b87f992050a2  evidence/FOLLOWUP/h1-prep/gates-kg.txt
ab38c8e7943ca6338e0c745090c47141f3f2b853c88ee103596cf2722437f4cc  evidence/FOLLOWUP/h1-prep/j1-contrast.txt
6b24891e79642694987ec788f724b4310b82c4c422a35d4d6ae276840b81cfbd  evidence/FOLLOWUP/h1-prep/score-judiciary.txt
```

No commits, no STATE.md writes; sst/prompt-kit/trace read-only;
`trace-lite/` never touched. Spend 0 this deliverable.
