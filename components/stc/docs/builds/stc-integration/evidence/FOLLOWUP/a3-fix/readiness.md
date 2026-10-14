# FOLLOWUP a3-fix — Readiness (B1)

Record type: builder readiness
Author role and date: a3-fix-builder / 2026-09-14
Packet: STC follow-up tranche, A3-fix stage (close the patch-format gap
that killed all three live proposals: model emits codex apply_patch
markers in §2 `proposed_changes` despite the unified-diff instruction;
custody has no marker-tolerant path; 0 live calls this stage).
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (9 hashes re-verified byte-exact below, zero drift).
Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`.

## Gate 0 — Predecessor gates (full read, nothing inherited)

| Record | Outcome carried |
| --- | --- |
| `evidence/FOLLOWUP/accept-2/attempt-1/REVIEW.md` | **AUTOMATION-NOT-READY (honest partial), A1 holds live**: gateway won twice on medium (45.5 s + 42.0 s valid §2); both verifies RAN TO JUDGMENT with zero stall; both failed on patch FORMAT. Finding **A3** (high, this stage's target): cand-0 5182 B unified-diff-with-`*** End Patch`-trailer → `git apply` corrupt + strict fallback reject; cand-1 3929 B pure apply_patch → verbatim garbage → all gates red. Custody dispatch `custody.py:176-216` has no marker-tolerant path. Wiring STILL unadjudicated (do not conflate). A2 header gap carried. |
| `evidence/FOLLOWUP/a1-fix/verify-1/REVIEW.md` | **PASS (predecessor)**: dst-exclusion + loud-refusal bound at the single `mirror_source_tree` fix point; 3/3 new + 61/61 unit + fixture green both interpreters; P04 lines byte-identical at +22; A2-deferral agreed. Owned pair now `dialectic_runner c072f1da…0ff5` + `test_dialectic eea1a7ee…0ec0`. |
| `evidence/FOLLOWUP/live-exp/attempt-1/REVIEW.md` | **WIN P2-H3a** + wiring caveat: P2 §2 contract proven via SST's own parse (`_parse_json_dict` + `_clean_code` + `CandidateProposal`); medium profile 3-for-3; guessed module paths may fail verify — adjudicate live if reached. The §2 contract is parsed but its content convention (unified diff) is not followed — the A3 gap. |
| `evidence/FOLLOWUP/a1-fix/readiness.md` + `attempt-1/REVIEW.md` | B1/B2 format + proof-shape precedent mirrored by this stage (gates, Hash Identity, guards, 0-call discipline). |

Dossier chain re-verified: attempt-2 `events.json`
`683860d0e3c49bd22bc3603c84ee2749b0c42db2f6d64351474958df25e00c1b` and
`store.db` `cc93680c932f4dad2f23cb142d2c6353b5d6ff910c655cb4d9df841511b2e293`
both byte-exact vs the accept-2 REVIEW Identity block.

## Gate 1 — Drift gate (re-verified this session, STOP on unexplained drift)

- HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` = tasked base. ✓
- 9/9 file hashes byte-exact at tasked values (full sha256 this session):
  `dialectic_runner c072f1dac2725f470bfeb9753288e2158064838467784d3f8ceb279b640a0ff5`,
  `test_dialectic eea1a7eea04eebbe21680836e4823e01bb2bfa62729f4bcd41bcb219f52a0ec0`,
  `cli.py 2ddfd6cbced44cf205aa061364c3681f52d4f28311294d008bfd3b41e50d82f1`
  (numstat 594/0),
  `test_winner_carry.py 0b5c3a8a85dea963ef8b95e43679bc504020152d105e89a2aaef05b677b69762`,
  `harness_worker ced79ed572d50f5c67d7e8556fe08127f59e0c529fc50bdaf1bc6898805a7867`,
  `cli_gateway f9dda17ec411c567dfccc51515cedfa69d79b75a6effd2c6e75c72ec76207b8a`,
  `test_integration_harness_worker.py e96db8d00a2950166f77ec6069ab98d9a944a344bfb452a4ffb7e6f3ce070b45`,
  `__init__ 105714219afcfbef9c81c50ce4216de4ce93096482aff2a4597cb4aaf04bac40`,
  `dispatch.py dc75c56eb48a097570a432e89610fa77cbdf89cc1bc2ae561bccb16fe26513c7`
  (numstat 333/7). ✓
- Pins exact: sst `079f4de6fd43881c2f1b529f0612f1df64a62f32` (status empty),
  prompt-kit `4f442a6c829bc06b60f9979fdc8d7585e30bac9a`,
  trace `a24a937009fec41e6dcb6d2ca31d3c1783ac97f7`. ✓
- Interpreters + shims: joint `<ws>/trace/.venv-linux/bin/python` 3.12.3,
  real-gates `<ws>/learn-anything/.venv/bin/python` 3.11.15;
  `/tmp/p01-shim`, `/tmp/p04-shim`, `/tmp/p03-pinned-kit` all present,
  no recreation. Gate tools: ruff 0.16.1, mypy 2.3.0 (real-gates venv),
  git 2.43.0, pytest 9.1.1 both interpreters. ✓
- **Zero drift. No STOP.**

## Ownership determination (FIRST — file paths + reads)

**`custody.py` is SST-owned.** The dispatch + direct-replacement path +
strict fallback exist in exactly one file in the workspace:

- `sst/src/sst/sandbox/custody.py` (sst repo, clean at pinned
  `079f4de6fd43881c2f1b529f0612f1df64a62f32`): `apply_proposal` dispatch
  predicate at :181 (`startswith("--- ")` / `"@@" in` / `startswith("diff
  --git")`), direct-replacement branch at :200-216 (writes non-diff
  payloads verbatim to `target_paths[0]`), strict fallback
  `_apply_unified_diff_manually` at :343-494 (rejects any hunk line
  outside ` `/`+`/`-`/`\` at :484). Full file read (494 lines).
- No second copy: workspace glob `**/custody*` over `stc/` + `sst/`
  resolves to that single file; no `def apply_proposal` and no
  `def _apply_unified_diff_manually` anywhere under `stc/src` or
  `stc/tests`; no `*** Begin/End Patch` handling anywhere under `stc/`.
- Citation note (explained, not drift): the accept-2 REVIEW cites the
  dispatch as `custody.py:176`; the predicate is actually at :181 (:176
  sits inside the `file_operations` write block). The operative ranges
  (:179-216 dispatch + direct-replacement, :343-494 fallback) are
  confirmed by full read against the pinned, clean sst tree — the file
  is exactly as reviewed live.

STC owns only the delegation boundary around SST custody, not custody
itself:

- `stc/src/stc/integration/dialectic_runner.py`: `STCCustodyWrapper`
  (:370-413, "composed around (never subclassing) SST custody") whose
  `verify_candidate_proposal` (:414-489) delegates patch application
  untouched at :468 (`self._custody.apply_proposal(proposal, lease_ws,
  task=task)`); merge path delegates at :838. Read in full.
- `stc/src/stc/integration/cli_gateway.py`: `shape_gateway_prompt`
  (:78-104), the STC-owned emitter frame and single choke point for all
  gateway emission (`generate` shapes at :165). Read in full.
- Controller mapping (SST-side, read-only): §2 JSON field
  `proposed_changes` (`sst/src/sst/prompts/dialectic.py:59`: `"<Complete
  implementation code or diff>"`) is mapped to `CandidateProposal.patch_diff`
  via `_clean_code` (`sst/src/sst/search/controller.py:452,743-748`),
  which strips only whitespace + markdown fences — markers pass through
  untouched. `patch_hash`/`post_patch_digest` have zero consumers in
  `sst/src` + `stc/src` (produced, never read).

**Ruling: branch (b) of the brief — custody is SST-owned.** The STC
product change is the framing pin only; the SST custody-tolerance change
rides as evidence + concrete proposed diff (no SST edits — sst stays
clean at its pin throughout).

## Fix design (branch (b))

**Live-byte pins (sourced from the dossier this session, both stores
agree byte-exact):** cand `_0_0` 5182 B,
sha256 `44a77e3048d6ce0ee9c5571912d41f1cac5de6a617ceb4793a291d0c90509a11`
(169 lines, no trailing newline; lines 0-167 well-formed new-file
unified diff with hunk `@@ -0,0 +1,213 @@` over 165 actual body lines,
line 168 `*** End Patch`); cand `_1_0` 3929 B,
sha256 `0c7052d6bc37e6e7d26a7037842244228c75b38fb3bc6f6b6d72567a03db2fe3`
(130 lines, no trailing newline; `*** Begin Patch` /
`*** Add File: tests/unit/test_integration_runner_pins.py` / 127
all-`+`-prefixed body lines / `*** End Patch`). Both reproduce the live
verdicts through pristine SST custody in /tmp scratch (cand-0 stderr
byte-identical to live; cand-1 dispatches direct-replacement).

**(1) STC product change — emitter-frame pin (unified-diff-only).**
`shape_gateway_prompt` gains 4 lines in the closing instruction (after
`SST_PROMPT_END`, before the terminal "Now emit..." line — recency;
single choke point covers every gateway call):

```text
If the JSON carries proposed code changes, emit that patch string
(proposed_changes) as a pure unified diff: '---'/'+++' headers with
'@@' hunks only. NEVER emit codex apply_patch markers: no patch line
may begin with '***' ('*** Begin Patch' / '*** Add File:' / '*** End Patch').
```

D15/D7 intact: SST bytes stay verbatim between unchanged delimiters;
only STC-owned frame lines are added. No pin line begins with `***`
at column 0 (self-consistency, scripted-tested). Existing frame tests
assert substring properties only (`in shaped`), never byte-exact
shaped output — verified by read, so the pin breaks no pinned test.

**(2) SST custody-tolerance change — evidence + concrete proposed diff**
(`evidence/FOLLOWUP/a3-fix/attempt-1/sst-custody-tolerance.diff`,
unified diff vs sst @ `079f4de6`, `src/sst/sandbox/custody.py`):
one pure module-level `_normalize_patch_markers(diff_text)` +
a 4-line call site in `apply_proposal` (normalize after the scope
check, before dispatch; `patch_hash` stays over the raw proposed
bytes to preserve the identity invariant). Exact translation rules:

- R0 (no-op fast path): if no line starts with `***` at column 0,
  return the input unchanged (byte-identical; every existing behavior —
  git path, fallback path, raw path — preserved bit-for-bit).
- R1 (stray-envelope strip, cand-0 shape): remove every column-0 line
  whose stripped text is exactly `*** Begin Patch` / `*** End Patch`;
  if the remainder has no other column-0 `***` line AND satisfies the
  existing unified-diff dispatch predicate, return it with exactly one
  trailing `\n`. (Column-0-only matching keeps legitimate diff content
  such as context line ` ***bold***` safe — it never triggers.)
- R2 (Add-File translation, cand-1 shape): if blank-stripped ends are
  `*** Begin Patch` … `*** End Patch`, every column-0 `***` line is
  Begin/End/`*** Add File: <non-empty path>`, no unified-diff header
  line is present, and every body line starts with `+`, translate each
  section to `--- /dev/null` / `+++ b/<path>` /
  `@@ -0,0 +1,<n> @@` + verbatim body (`<n>` exact), sections
  concatenated, exactly one trailing `\n`. (N sections supported by
  the same loop; single-section is the live shape.)
- R3 (loud refusal, never verbatim garbage): any other marker-bearing
  shape — `*** Update/Delete File`, `*** Move to:`, unknown `***`
  verbs, mixed unified+apply_patch, empty path, empty section,
  non-`+` body line — returns `(original, error)` naming the
  offending marker (truncated 80 chars); `apply_proposal` returns
  `success=False` before any write.

Scratch-proven this session (/tmp only, pristine SST + git 2.43.0):
R1-stripped cand-0 → `git apply` still fails (hunk count 213-vs-165
trips git at the last line) but the SST fallback applies → overall
`success=True`; R2-translated cand-1 (exact count + trailing `\n`)
→ `git apply` rc=0. So post-fix cand-0 applies via fallback, cand-1
via git — both succeed. Refusal runs before dispatch, so refused
payloads never reach the verbatim-write branch (target-absent
scripted-tested).

**Rejected alternatives:** (i) sanitizing in `STCCustodyWrapper`
(STC-owned but out of branch: it would fork proposal identity —
NODE_PROPOSED bytes vs applied bytes vs `patch_hash` vs
`render_merged_diff` — a new semantics question, not minimal; and
the brief scopes (b) to framing pin only); (ii) spec edit (the
p05-acceptance spec is SAME-approved — re-approval out of scope; the
frame pin is the STC-owned lever); (iii) hunk-count repair in the
proposal (unneeded — the fallback is the designed second path and
applies correctly); (iv) killing the raw direct-replacement path
(unneeded widening — R0 leaves non-marker payloads byte-identical).

**Owned files:** `src/stc/integration/cli_gateway.py` (frame pin +
docstring line) + new `tests/unit/test_a3_patch_format.py`
(hash-pinned live bytes; frame-pin tests incl. SST-verbatim-with-markers
and frame self-consistency; SST-proposal validation via scratch-apply
of the evidence diff + importlib load: cand-0 apply-succeeds with
byte-exact content, cand-1 translate-to-valid-diff with byte-exact
content, refusal shapes with target-absent, no-regression pristine-vs-patched
byte-identity incl. R0 no-op proof). SST NEVER writable (proposal
validated against a /tmp copy; sst clean before/after).

## B2 proof plan (0 CLI calls)

- New tests green + `tests/unit/test_integration_harness_worker.py`
  (the frame-test host — affected suite) green live-deselected
  (`-m "not live"`) on BOTH interpreters (joint 3.12.3
  `PYTHONPATH=src:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`;
  real-gates 3.11.15
  `PYTHONPATH=src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`;
  `PYTHONDONTWRITEBYTECODE=1`; cwd `ws/stc`; `-p no:cacheprovider`).
- `ruff check` + `ruff format --check` and `mypy --strict` on both
  owned files (new test file must be strict-clean: zero pre-existing).
- Evidence diff: `git apply --check` clean vs pinned sst + scratch-apply
  transcript; sst clean before/after; tracked-diff audit (only the 2
  pre-existing loose-set mods + this stage's owned-file delta — both
  owned files are untracked loose-set, so `git diff --numstat` must
  still read exactly 594/0 + 333/7); Hash Identity for every file
  created/modified. No commits, no STATE.md writes;
  sst/prompt-kit/trace read-only; `trace-lite/` never touched.
  Spend 0 (tranche 6/20; 6-call reserve untouched).

## Verdict

**READY** — predecessors read, zero drift, custody ruled SST-owned
with file paths, branch-(b) fix designed with exact translation rules
+ refusal cases (scratch-proven on the exact live bytes), owned
surface minimal (1 frame file + 1 new test file), proof plan
scripted. Proceeding to B2.
