# H1 prep — Deliverable 1: missing-context specification (CONTEXT.md)

Record type: builder analysis (evidence-writing only)
Author role and date: h1-prep-builder / 2026-09-15
Base/candidate identity: stc HEAD `edf5389873e4d4a2a4752ee0aa2159289398495e` +
loose set (re-verified read-only this session: `cli_gateway aedffa12…bb392`,
`dialectic_runner c072f1da…0ff5`, `cli.py 2ddfd6cb…d82f1` 594/0,
`dispatch.py dc75c56e…13c7`; sst `079f4de6…` clean; prompt-kit `4f442a6c…`,
trace `a24a9370…` exact). Method: full reads + local byte inspection.
**0 live calls; no product edits; SST bytes verbatim; no `allowed_paths` /
target widening.** This package is STC-frame content for a later implement
stage — not applied here.

Path shorthand: `evidence/...` = `docs/builds/stc-integration/evidence/...`;
`h1-prep/` = `evidence/FOLLOWUP/h1-prep/`.

## 1. What the model saw (captured live prompt bytes)

The closest captured emission inputs are the live-exp P2-H3a shaped prompt
(`evidence/FOLLOWUP/live-exp/attempt-1/P2-H3a/prompt.txt`, 5044 B) and the
M1 SST source bytes
(`evidence/P05/attempt-1/trial-timeout/p05-diverge-prompt.md`, 4364 B,
sha256 `3154b3bb…f391b61`, recomputed exact this session). Attempt-2/3
dossiers preserve no shaped-prompt payload; what they do preserve is the
compiled live intent in `TREE_CREATED`: **39 invariants (37 `bundle:` +
2 `membrane:`)**, `allowed_paths` exactly
`[tests/unit/test_integration_runner_pins.py]`, base `edf5389` (recounted
this session in both `events.json`). The 36-shard fragmentation verdict
(INSPECTION §4) stands: the model sees per-line shards, never a paragraph.

The accept-3 legs additionally carried the A3 frame pin
(`src/stc/integration/cli_gateway.py:103-106`, 4 lines after `SST_PROMPT_END`;
SST bytes verbatim between unchanged delimiters). Reconstructed shape is
deterministic from `shape_gateway_prompt` (read, not re-sent): baseline
frame + pin + verbatim SST + closing instruction.

Source-code content of every captured emission input: **zero.**

- The P2/M1 `CONTEXT REPOSITORY FILES` block holds only the target path with
  the 1-line sentinel `this definitely does not exist` (M1 harness
  out-of-loop write, since removed).
- In the current tree the target file is ABSENT (`ls`-confirmed this
  session), so live runs compile `relevant_files={}`: SST
  `ContextCapsuleCompiler` includes a file only
  `if full_path.exists() and full_path.is_file()`
  (`sst/src/sst/context/capsule.py:36`, read-only read). The live files
  block is EMPTY.
- No `DialecticRunner` source, no import paths, no API signatures, no
  reason-literal code anchors, no auditor contract, no repo test example
  reach the emitter. The emitter must author a complete test module for
  unseen APIs from task prose alone.

What the prose *does* carry (so the package below does NOT duplicate it):
the type names `DialecticRunner` / `NoChampionResult` / `DialecticError`,
the entry name `run_async`, the seam name `apply_proposal`, the literals
`merge-apply-failed` / `reselect-reconstruction-failed`, the token `RT-08`,
and the evidence filenames. The model got the literals right
(`result.reason == "merge-apply-failed"`); what it could not get right is
everything prose cannot state: paths, signatures, anchors, conventions.

## 2. What was missing, precisely (guess → missing fact)

Guessed constructs below are quoted from the exact attempt-3 cand-1 payload
(4299 B, sha256 `a6c8f1d3…e670b`, `events.json` ev4). "Package §" points at
the excerpt in §3 that supplies the missing fact.

| # | Guessed construct (cand-1) | Missing source fact | Package § |
| --- | --- | --- | --- |
| G1 | `from praxist.dialectic.errors import DialecticError` | Real path: `DialecticError` lives in `stc.integration.dialectic_runner` (:120); nothing exists under `praxist.*` | §1, §2 |
| G2 | `from praxist.dialectic.models import NoChampionResult` | Real path: same module (:186); full field list incl. `reason: str` | §1, §2 |
| G3 | `from praxist.dialectic.runner import DialecticRunner` | Real path: same module (:648); keyword-only ctor, fixed kwargs | §1, §3 |
| G4 | `DialecticRunner.__new__` + invented attrs (`store`, `output_dir`, `artifact_dir`, `gateway`, `harness`) | Ctor signature: `ctx, gateway, substrate, evidence_root, memory, policy, auditor, champion_mutmut` — none of the guessed attrs exist | §3, §4 |
| G5 | `runner.execute_search = AsyncMock(...)` | Search is driven by the SST controller *inside* `run_async`; the worker-owned double point is the `gateway: ModelGateway` ctor arg (repo pattern: `ScriptGateway(handler)`) | §3, §4 |
| G6 | `await runner.run_async()` (zero args) | `run_async(self, bundle: TaskBundle) -> ChampionResult \| NoChampionResult` — takes the bundle, returns the typed union | §3 |
| G7 | `_event` dicts (`{"event_type": ...}`) + `_store` SimpleNamespace | Real event/store types: `SSTEvent(kind=EventKind..., node_id, payload)` (`sst.core.events`), `SQLiteSSTStore` | §1 |
| G8 | `result.reason == "merge-apply-failed"` (right literal, unanchored) | Code anchor: merge step `wrapper.custody.apply_proposal(...)` (:838) → `if not app_result.success:` (:839) → reason (:848); the double seam for PIN-1 | §5 |
| G9 | `with pytest.raises(DialecticError, match="RT-08")` (right shape, unanchored) | Anchor: `_audit` (:946-955) raises `DialecticError("auditor with_codex must be False (RT-08).")`; auditor ctor flag `with_codex: bool = False` (:69-74); `audit_diff` signature (:167-172) | §6 |
| G10 | `from unittest.mock import AsyncMock` | Judiciary-banned: `ZERO_MOCK_VIOLATION` matches `unittest\.mock`; repo convention is hand-written fakes (`ScriptGateway`/`FakeSubstrate`/`FakeAuditor` in the test file) | §1, §4 |
| G11 | Remaining reason literals (`reselect-reconstruction-failed`, `champion-vetoed-no-alternative`, `budget-exhausted`, `no-verified-candidate`) | Exact literals with code context: veto-reselect (:792/:803), budget/default (:809-813) | §5 |

## 3. The pinned package (STC-frame content, NOT applied)

Provenance (all sha256 recomputed this session; STC-owned files only):

- `src/stc/integration/dialectic_runner.py`
  `c072f1dac2725f470bfeb9753288e2158064838467784d3f8ceb279b640a0ff5`
- `tests/unit/test_integration_dialectic.py`
  `eea1a7eea04eebbe21680836e4823e01bb2bfa62729f4bcd41bcb219f52a0ec0`
- `src/stc/judiciary/auditor.py`
  `0f76845d427d8aa8cea0f56407751722fe772865ae6143db186008d089bb69c2`

Payload: `h1-prep/ctx-package.txt`, **3921 B** (sha256
`e0c814e5…adbca`), assembled from literal source ranges by script
(`/tmp/h1ctx-build.py`, kept out of the tree per gate-hygiene note in
PATH-REVIEW). Every non-tag line below is a verbatim source line; `--- N`
tags and the two `# L…:` joins are the only added bytes (frame orientation).

```text
[H1-CTX/pinned] read-only source context (NOT a patch target)
--- 1 test_integration_dialectic.py:21-22,24-26,28-29,33-54
from sst.core.contracts import CandidateProposal, TaskPacket
from sst.core.events import EventKind, SSTEvent
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager
from sst.search.policy import SearchPolicy
from stc.integration.adapters import AdapterContext, Budgets
from stc.integration.dialectic_runner import (
    ChampionResult,
    DialecticError,
    DialecticRunner,
    LossLedgerEntry,
    NoChampionResult,
    STCCustodyWrapper,
    SynthesisReceipt,
    count_mutmut_runs,
    lease_id_for,
    mirror_source_tree,
    render_merged_diff,
    sanitize_lease_segment,
    scrape_tainted_scores,
)
from stc.judiciary.auditor import JudiciaryAuditor
from stc.schemas.models import (
    ExecutionReceipt,
    FileTarget,
    GateReport,
    JudiciaryVerdict,
    TaskBundle,
)
--- 2 dialectic_runner.py:120-121,186-187,191-198
class DialecticError(IntegrationError):
    """Runner/wrapper misuse or invariant breach (never a search outcome)."""
class NoChampionResult(BaseModel):
    """Typed no-champion outcome for P05's partial dossier (RT-10)."""
    tree_id: str
    run_id: str
    branch_refs: list[str]
    scores_summary: dict[str, float]
    veto_log: list[VetoRecord] = Field(default_factory=list)
    budget_state: dict[str, float] = Field(default_factory=dict)
    reason: str
    evidence_dir: str
--- 3 dialectic_runner.py:663-674,693-694
    def __init__(
        self,
        *,
        ctx: AdapterContext,
        gateway: ModelGateway,
        substrate: SubstrateRunner,
        evidence_root: Path | str,
        memory: FileBackedMemory | None = None,
        policy: SearchPolicy | None = None,
        auditor: JudiciaryAuditor | None = None,
        champion_mutmut: bool = True,
    ) -> None:
    async def run_async(self, bundle: TaskBundle) -> ChampionResult | NoChampionResult:
        """Runs the full dialectic loop (awaitable for loop-resident callers)."""
--- 4 test_integration_dialectic.py:742-754
    runner = DialecticRunner(
        ctx=_ctx(str(src)),
        gateway=ScriptGateway(handler),
        substrate=substrate,
        evidence_root=tmp_path / "ev",
        policy=(
            policy
            if policy is not None
            else SearchPolicy(max_iterations=1, max_depth=2, branching_factor=4)
        ),
        auditor=auditor,
        **kwargs,
    )
--- 5 dialectic_runner.py:837-839,848,792,803,809-813
        mirror_source_tree(Path(packet.source_repo_root), merged_dir)
        app_result = wrapper.custody.apply_proposal(final_proposal, merged_dir, task=packet)
        if not app_result.success:
    # L848:
                "merge-apply-failed",
    # L792/L803/L809-813:
                        "reselect-reconstruction-failed",
                    "champion-vetoed-no-alternative",
            reason = (
                "budget-exhausted"
                if any(evt.kind == EventKind.BUDGET_EXHAUSTED for evt in events)
                else "no-verified-candidate"
            )
--- 6 auditor.py:69-74,167-172 + dialectic_runner.py:946-955
    def __init__(
        self,
        runner: SubstrateRunnerProtocol | None = None,
        with_codex: bool = False,
        codex_bin: str | None = None,
    ) -> None:
    def audit_diff(
        self,
        diff_text: str,
        bundle: TaskBundle,
        receipt: ExecutionReceipt,
    ) -> JudiciaryVerdict:
    def _audit(
        self,
        merged_diff: str,
        bundle: TaskBundle,
        receipt: ExecutionReceipt,
    ) -> JudiciaryVerdict:
        """Audits the merged champion; with_codex=False asserted (RT-08)."""
        if self._auditor.with_codex:
            raise DialecticError("auditor with_codex must be False (RT-08).")
        return self._auditor.audit_diff(merged_diff, bundle, receipt)
```

## 4. Byte justification (every byte against the guess it prevents)

Total **3921 / 4096 B** (175 B headroom for the implement stage's framing
glue, if any). Measured per section on the artifact bytes.

| § | Bytes | Guesses killed | Deliberate cuts (and why) |
| --- | --- | --- | --- |
| head | 62 | Scope guard: read-only, not a patch target (prevents the model "fixing" the context) | — |
| §1 imports | 894 | G1/G2/G3 (every `praxist.*` line dies on sight); G7 (`EventKind`/`SSTEvent`, `CandidateProposal`/`TaskPacket`); G5/G10 (`ModelGateway` double point + `ScriptGateway` convention pointer); `TaskBundle` (G6's missing arg type) | `sst.gateway.contracts` line (unused by pins); `DEFAULT_*`/`FALLBACK_*` consts (veto internals, not pin surface) |
| §2 types | 535 | G1/G2 anchors (`never a search outcome` disambiguates PIN-1-never-raise vs PIN-3-must-raise); `reason: str` + evidence fields (the asserted shape) | `model_config` line + blanks (pydantic boilerplate, zero pin value) |
| §3 API | 580 | G4 (exact kwargs, keyword-only marker kills `__new__` + invented attrs); G6 (`run_async(bundle)` kills the zero-arg call; return union names both result types) | `run()` bridge (pins await `run_async`; sync wrapper adds nothing) |
| §4 example | 421 | G4/G5 together: a REAL construction (`ScriptGateway(handler)` kills the `execute_search` AsyncMock; `SearchPolicy(max_iterations=1, …)` shows fast bounded runs; `evidence_root=tmp_path` shows isolation) | Helper `return` line (scaffolding noise) |
| §5 merge+reasons | 638 | G8 (the exact PIN-1 double seam: `wrapper.custody.apply_proposal` + success check); G11 (all 5 literals with the branch context that selects them — `BUDGET_EXHAUSTED` condition included so `no-verified-candidate` isn't misread as unconditional) | `merged_dir` assignment (one line, implied by use) |
| §6 RT-08 | 792 | G9 completely: flag name + default (`with_codex: bool = False`), audited entry (`audit_diff` signature), and the exact raise line whose message carries the `match="RT-08"` target | Auditor method bodies (scan internals unneeded for the pin) |

## 5. Application notes for the later implement stage (not applied here)

- Placement: STC-owned frame text (same layer as the A3 pin,
  `shape_gateway_prompt`), either opening or closing block. SST bytes stay
  byte-verbatim between the delimiters (D15/D7); `allowed_paths` and the
  target file are NOT widened by this package (it grants no write scope —
  it is reference text, and the head tag says so).
- Staleness rule: the package is pinned to the three shas in §3. If any of
  the three source files drifts, rebuild from the same ranges (builder
  script pattern preserved in session notes, not in the tree) and re-pin;
  never hand-edit the payload.
- Frame-budget note: 3921 B of context against a ~5044 B shaped prompt
  roughly doubles emission input. The H3 finding (reasoning-medium emits
  where max hangs) interacts with input size in an unmeasured way — the
  implement stage should keep the medium profile and treat any stall as a
  prompt-size signal, not a content signal.
- What this package deliberately does NOT contain: the 36-shard invariant
  chain (H2 lever, separate), full `TaskBundle`/`SearchPolicy` schemas
  (names + example suffice for the pins), or any custody internals (the
  pins double `apply_proposal`, never reimplement it).

## Identity (sha256 of h1-prep evidence transcripts)

```text
# CREATED (transcripts; this CONTEXT.md + sibling records PATH-REVIEW.md /
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
