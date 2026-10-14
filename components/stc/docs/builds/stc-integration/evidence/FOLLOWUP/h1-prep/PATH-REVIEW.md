# H1 prep — Deliverable 2: remaining-path review (PATH-REVIEW.md)

Record type: builder analysis (evidence-writing only)
Author role and date: h1-prep-builder / 2026-09-15
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (re-verified read-only: `cli_gateway aedffa12…bb392`,
`dialectic_runner c072f1da…0ff5`, `cli.py 2ddfd6cb…d82f1` 594/0,
`dispatch.py dc75c56e…13c7`; sst `079f4de6…` clean, custody bytes
`43c24681…ec864` = tolerance-NOT-landed value). Method: code read (STC
wrapper + SST custody/controller, SST read-only) + deterministic local
replays in `/tmp` scratch. **0 live calls; no product edits.** These
checks establish integration behavior, not live success.

Path shorthand: `h1-prep/` = `docs/builds/stc-integration/evidence/FOLLOWUP/h1-prep/`.
Replay scripts live in `/tmp` only (`/tmp/h1-path-replay.py`,
`/tmp/h1-j1-probe.py`) — never under the tree, per the gate-hygiene rule
in §4 (G1). Transcripts: `h1-prep/custody.txt`, `gates-kg.txt`,
`gates-bad.txt`, `score-judiciary.txt`, `j1-contrast.txt`, `g2-collect.txt`.
Environment: real-gates python 3.11.15, live-identical `PYTHONPATH`
(`src:/tmp/p04-shim:/tmp/p01-shim:<ws>/sst/src:/tmp/p03-pinned-kit`),
`PYTHONDONTWRITEBYTECODE=1`, ruff 0.16.1 / mypy 2.3.0.

## 1. Code walk: proposal parsing → custody → gates → judiciary → champion

**1a. Proposal parsing (SST controller, read-only).**
`_generate_divergent_candidates` (`sst/src/sst/search/controller.py:414-489`)
sends `GatewayRequest(role="diverge")`, parses the response with
`_parse_json_dict` (:751-761: fence-tolerant, `{}` on any failure), and maps
each `branches[]` entry through `_clean_code` (:743-748: strips whitespace +
markdown fences ONLY — `***` markers pass through untouched) into
`CandidateProposal.patch_diff` with `target_paths=[allowed_paths[0]]`
(:447-467). Empty/unparseable branches fall to the raw-code path (:468-485:
whole content becomes `patch_diff`). Refine (:491-554) and synthesize
(:556-639) follow the same parse-then-`_clean_code` shape. Critique
(:653-739) scores verified candidates via the `critique` gateway role, with
two scripted fallbacks the STC veto keys on verbatim: live-default
`0.85` + `"Evaluated by Cortex Critic"` (:710-716) and
`"Passed all verifier acceptance tests"` (:739). Every `gateway.invoke`
call site (diverge :440, refine :521, synthesize :604, critique :703) is
covered — the first three by `except ProviderGatewayError` (→ warning +
empty proposals), critique by broad `except Exception` (:726). Nothing in
this stage validates patch shape: any string becomes a proposal.

**1b. Custody (STC wrapper + SST custody).**
`STCCustodyWrapper.verify_candidate_proposal`
(`stc/src/stc/integration/dialectic_runner.py:414-519`): denylist pre-check
on `target_paths`+`file_operations` (:430-448, no lease on hit) → lease
alloc (:461-465, stale dir quarantined) → `mirror_source_tree` (:467; the
A1-fixed dst-exclusion+refusal at :283-300) → parent
`apply_proposal(proposal, lease_ws, task=task)` (:468) → apply-fail returns
`DeterministicGateResult(passed=False, duration 0.0)` (:469-479) → substrate
gates with `run_mutmut=False` (:480-485) → `receipt_to_score` (:486) →
lease released (:490). Exceptions quarantine with a reason file (:509-519).
SST `apply_proposal` (`sst/src/sst/sandbox/custody.py:118-226`): secret scan
(:128-134) → scope check on declared paths (:137-144) → `file_operations`
verbatim writes (:149-177) → unified-diff dispatch at :181
(`startswith("--- ")` / `"@@" in` / `startswith("diff --git")`; note: NO
`b/`-prefix requirement — bare `+++ <path>` dispatches as a diff) → `git
apply` with the strict manual fallback (:186-198; fallback
`_apply_unified_diff_manually` :343-494 rejects non-` `/`+`/`-`/``\``
hunk lines) → else direct-replacement verbatim write to `target_paths[0]`
(:200-216, the a2c1 garbage path). `patch_hash` covers the raw proposed
bytes (:218).

**1c. Gates (substrate, whole-tree).** `execute_gates(worktree, …)`
(`stc/src/stc/substrate/runner.py:176`): ruff :289 (`ruff check .` then
`ruff format --check .`, `cwd`=lease) → mypy :361 (`mypy --strict src
tests`) → pytest :420 (bare `pytest -v --tb=short`, NO `-m` filter; any
skip forces exit 1 per the 0-skipped invariant) → mutmut (forced OFF
per-node by the wrapper). `receipt_to_score`
(`stc/src/stc/integration/adapters.py:459-483`) maps exactly the three
gates + `verifier_passed` into `ScoreBreakdown` (`reward = passed/4`;
mutmut is metric-only per D4/ADR-INT-01). Scope fact: all three gates run
over the WHOLE lease tree, which mirrors the whole repo (dst-exclusion
removes only the current dossier dir). Pre-existing tree state therefore
gates every candidate — see G1/G2 in §4.

**1d. Judiciary.** `render_merged_diff`
(`dialectic_runner.py:553-581`): verbatim unified diffs pass through
untouched (:561-562); anything else renders as synthetic `+++ b/` diffs
(:563-581). `_audit` (:946-955) asserts `with_codex is False` (RT-08,
raises `DialecticError` naming it) and delegates to
`JudiciaryAuditor.audit_diff` (`stc/src/stc/judiciary/auditor.py:167-369`):
receipt-signature check (:177) → `is_passing` check (:190) → line scans
keyed on `+++ b/` attribution (:220; only `.py`-attributed `+` lines are
scanned for mock/fallback/secret patterns) → headless-codex extension iff
`with_codex` (:341; forced False on this path) → verdict (:344-369).
Attribution gap: bare-`+++` verbatim diffs are never attributed — see J1.

**1e. Champion handling (all STC-owned, post-search).** Veto scrape :749
(`scrape_tainted_scores` :225-260: rule 1 exact-fallback rationale, rule 2
0.85+live-default pair); veto-reselect :776-804 via `_proposal_from_events`
(NODE_PROPOSED :597, SYNTHESIS_PROPOSED :610; `None` →
`"reselect-reconstruction-failed"` :792; no alternate →
`"champion-vetoed-no-alternative"` :803); no-champion reasons
`"budget-exhausted"`/`"no-verified-candidate"` (:809-813); merge :836-849
(mirror + `wrapper.custody.apply_proposal`; fail →
`"merge-apply-failed"` :848); `merged.diff` :851; post-merge receipt with
mutmut-once :855-864; `mutmut_count` :865 + disposition :866-870;
`_audit` :871 with one re-receipt+re-audit on REJECTED :875-889;
`ChampionResult` :890-908. Merge re-applies through the SAME pristine
custody — no second tolerance layer exists anywhere on the path.

## 2. Replay (a): KNOWN-GOOD pins diff (proves the path works when the patch is right)

Hand-written 447 B new-file unified diff (sha `ff8b3aa9…e3815`; exact
`@@ -0,0 +1,10 @@` counts): correct import
`from stc.integration.dialectic_runner import DialecticRunner,
NoChampionResult`, one trivial pin asserting the `reason` field type and
the `run_async` entry point. Through the real `mirror_source_tree` (317 MB
full-tree lease in `/tmp`) → pristine SST `apply_proposal` →
substrate-identical gate commands (file-scoped, §6) → real
`receipt_to_score` → real `render_merged_diff` → real `JudiciaryAuditor`
(`runner=None, with_codex=False`; receipt signature self-consistent per
the auditor's no-runner canonical formula; mutmut honestly NOT-MEASURED).

| Stage | Observed (transcript `custody.txt` / `gates-kg.txt` / `score-judiciary.txt`) |
| --- | --- |
| Custody | `success=True`, 357 B file sha `e13408c8…2394`; strict `git apply --check` rc=0 on pristine (git carries; fallback unneeded) |
| Gates | ruff-check rc 0 (`All checks passed!`), format rc 0, mypy-strict rc 0 (`no issues found in 1 source file`), pytest rc 0 (`1 passed`) |
| Score | `passed=True reward=1.00`, all four hard gates True |
| Judiciary | signature VALID; **zero** content findings; status REJECTED **solely** on `SUBSTRATE_GATE_FAILURE: mutmut (exit 1)` = the honest not-measured marker |

Claim (scoped, §6): custody applies, file-scoped gates go green, scoring
maps to a perfect pass, and the judiciary scan path runs clean on a right
patch. Full APPROVED is unreachable locally for exactly one reason — the
unexercised-live mutmut receipt (§5).

## 3. Replay (b): exact attempt-3 cand-1 bytes (reproduces the wiring failure)

Same path, same commands, with the 4299 B live payload (sha `a6c8f1d3…e670b`,
hash-asserted before replay). Every accept-3 anatomy value reproduces:

| Stage | Observed (transcripts `custody.txt` / `gates-bad.txt` / `score-judiciary.txt`) |
| --- | --- |
| Custody | `success=True`, 4096 B file sha `2e6c187a…1a1b` — byte-identical to the accept-3 record; strict path alone rc=128 `corrupt patch at line 128` (hunk-count mismatch), SST fallback carries |
| Gates | ruff-check rc 1 (I001); format rc 0 (config-loaded — see note); mypy rc 1 with **exactly** 5 errors = 3× `import-not-found` (`praxist.dialectic.*`) + 2× `no-untyped-def`; pytest rc 2 `ModuleNotFoundError: No module named 'praxist'` |
| Score | `passed=False reward=0.00`, all False — matches the live `ruff=False mypy=False pytest=False reward=0.00` verbatim |
| Judiciary | REJECTED on `SUBSTRATE_GATE_FAILURE` (all four gates); content scans skipped — see J1 |

Config-scope note (correction, not contradiction): the accept-3 anatomy
ran gates in a bare-config scratch (ruff "3 errors: import-sort + useless
returns", format rc 1). This replay runs lease-faithfully — full mirror
INCLUDING `pyproject.toml` (repo config: line-length 100, no RET rules) —
so the counts are I001-only and format-clean. The verdict signal (ruff red)
reproduces; the rule detail differs by config scope. Probed both ways:
`--isolated` format reverts to rc 1 (`File would be reformatted`), proving
the difference is config-driven.

## 4. Remaining defects exposed (deterministic, 0 live calls)

**G1 — whole-tree per-node gates are red on pre-existing files (high).**
Read-only baselines on the real tree with the real-gates toolchain:

- `ruff check .`: **123 errors**. 7 in real-tree files —
  `src/stc/integration/adapters.py:170` I001,
  `src/stc/integration/identity.py:41` RUF022,
  `src/stc/integration/memory.py:292` C416,
  `tests/unit/test_integration_adapters.py:3` I001 + `:226`/`:419` RUF043,
  `tests/unit/test_integration_identity.py:3` I001 — plus 116 in
  lease-present evidence `.py` (50+50 `run_deep_research_campaign.py`
  incl. the nested quarantine copy, 8+8 `liveexp-probe.py`).
- `ruff format --check .`: **8 files would be reformatted** — 4 evidence
  copies + `adapters.py`, `memory.py`, `test_integration_adapters.py`,
  `test_integration_memory.py`.
- `mypy --strict src tests`: **18 errors in 8 files**, all real-tree:
  `src/stc/cli.py`(1), `src/stc/compiler/bundler.py`(2),
  `tests/integration/test_dialectic_fixture.py`(5),
  `tests/integration/test_pipeline.py`(1), `tests/unit/test_cli.py`(1),
  `tests/unit/test_compiler.py`(1),
  `tests/unit/test_integration_adapters.py`(2),
  `tests/unit/test_integration_dialectic.py`(5).

Every listed file sits outside any future `evidence/FOLLOWUP/<stage>/
attempt-N/dossier` path, so the lease dst-exclusion never removes them:
**any future live verify inherits these failures before the candidate
file is considered.** Consequence: the §2 green is file-scoped by
necessity; a live champion is impossible while G1 stands, no matter how
clean the emitted patch is. Hygiene corollary (honored by this stage):
no `.py` under evidence — transcripts are `.txt`, records `.md`,
scripts stay in `/tmp` (the 8 `liveexp-probe.py` errors are the
self-inflicted precedent).

**G2 — the bare-pytest gate collects live-marked tests (high).**
`_run_gate_pytest` runs `pytest -v --tb=short` with no `-m` filter
(`runner.py:420`), while D13's "deselected in gate runs" holds only for
evidence/CI invocations. Deterministic collection proof (`--collect-only`:
collects, never executes — `g2-collect.txt`): the bare selection collects
**81/81 including 5 live-marked tests** that drive real CLI harnesses
(`test_live_handshake_binaries_probe` has NO skip guard at all; the rest
skip only if the operator login is absent — and the live lease inherits
the operator environment); `-m "not live"` deselects exactly those 5
(7 repo-wide incl. the fixture file). Consequences: (i) "deterministic"
gates can fire live model calls on unledgered scratch spend; (ii) any
skip trips the 0-skipped invariant → exit 1. Grade: defect by code read +
collection proof; behavioral firing was NOT executed (would spend live
calls — forbidden by this brief).

**J1 — judiciary content scans skip bare-`+++` diffs (high, fail-open on
content).** `audit_diff` attributes files only on `+++ b/` (:220), but
custody + git accept bare `+++ <path>` — and 2 of the 5 live §2 emissions
(a3c0, a3c1) use exactly that shape (survey: P2/a2c0 carry `b/`; a2c1 has
no `+++` line and would synthesize-attributed via `render_merged_diff`).
Causal contrast on the exact cand-1 bytes with a green self-consistent
receipt (`j1-contrast.txt`): bare `+++` → **APPROVED, 0 findings** (the
`from unittest.mock import AsyncMock` line invisible); `+++ b/` (+2 B) →
**REJECTED, `ZERO_MOCK_VIOLATION …:9`**. A 2-byte header difference flips
the verdict. Gate-failure findings are unaffected (fail-closed on gates
is intact); the hole is content-only. STC-owned surface
(`auditor.py:220` + `render_merged_diff` verbatim arm) — no custody
implication; no edit made here.

**C1 — hunk-count mismatch is tolerated by design (info, not a defect).**
Cand-1 declares `@@ -0,0 +1,242 @@` over fewer body lines: git strict
rejects (rc 128), the SST fallback carries (`success=True`). The fallback
is the designed second path; nothing to fix. Noted because MARKERS.md
leans on this exact strict-vs-fallback layering.

## 5. Unexercised-live stages (c): what the replays do and do not prove

No champion has ever existed live (5 §2 emissions, 0 verified), so every
post-verify-live stage below is unexercised-live. Honest accounting:

| Stage (live status: NEVER) | Local replays prove | Local replays do NOT prove |
| --- | --- | --- |
| Judiciary on a real champion | Scan logic + verdict synthesis run; `+++ b/` attribution works and bare-`+++` skips (J1); signature-check path executes (self-consistent); RT-08 `_audit` raise is code-read exact | Substrate-HMAC receipt path (`runner.verify_receipt` with key); headless-codex path (forced False); audit-time `with_codex` flip (PIN-3's target — raise never executed here); real-champion diff shapes |
| Mutmut-on-champion | Counting rule + disposition strings (code read); honest NOT-MEASURED plumbing in the replay receipt | Any measured mutmut run: execution, kill rate, WSL deferral, timeout behavior on a merged tree |
| Merge execution | `apply_proposal` mechanics on both shapes (git-carry + fallback-carry); `mirror_source_tree` plain-copy path ran twice at 317 MB; `render_merged_diff` verbatim arm | Merge-time-only apply failures (PIN-1's target — never observed anywhere); post-merge gate behavior; the REJECTED retry loop (:875-889) |
| Cortex critique / scoring live | Parse fallbacks + veto-rule anchors (code read); `receipt_to_score` mapping on both outcomes (executed) | Any live `critique`-role call; score-driven champion selection; veto-reselect execution (covered only by scripted unit tests, 61/61 precedent, not re-run here) |
| Refine / synthesize roles live | Parse shapes (code read) | Any live invocation ( unreachable without a verified candidate) |

## 6. Scope and limits (read before citing a green)

- Gates are file-scoped: whole-tree gates are red on pre-existing files
  (G1), so whole-tree replay would attribute tree debt to the patch. The
  (a)/(b) contrast is apples-to-apples (identical commands, scope,
  toolchain, config) — the isolation is the point, not a shortcut.
- Receipts are synthetic-local: gate fields mirror observed outcomes;
  the signature is self-consistent under the auditor's no-runner formula,
  NOT a substrate HMAC. It exercises the check path, not the key path.
- Leases live in `/tmp` (outside the source tree), so the A1
  dst-exclusion branch did not trigger; the plain-copy path ran. Mirror
  fidelity is otherwise exact (same function, `.git` included).
- `mypy --follow-imports=silent` attributes errors to the file (a3-fix
  precedent for owned files); the live gate follows imports tree-wide.
- No live calls were made or needed at any point; no behavioral claim
  above depends on provider behavior.

## Identity (sha256 of h1-prep evidence transcripts)

```text
# CREATED (transcripts; this PATH-REVIEW.md + sibling records CONTEXT.md /
# MARKERS.md are records and are named by path, not self-listed)
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
