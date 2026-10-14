"""Dialectic runner: SST search under STC substrate custody (P04).

Owns the STC-side search loop: a composition-based custody wrapper that routes
every candidate through the STC substrate gates (ruff + mypy --strict + pytest
per node; mutmut NEVER per node per D4/ADR-INT-01), and a runner that drives
``SSTSearchController.execute_search``, vetoes fallback-critique champions by
scraping SCORE_RECORDED events, receipts synthesis, ledgers sub-threshold
partials, merges the champion, runs mutmut exactly once on the merged tree,
and audits via the judiciary with ``with_codex=False``.

Seams (re-verified B1 at sst HEAD 079f4de, zero drift): controller ctor
``(task, gateway, store, custody_manager, policy, capsule_compiler)``,
``execute_search(tree_id)``, ``verify_candidate_proposal(task, proposal,
source_dir, acceptance_command=None, timeout=120)``, SCORE_RECORDED payload
``{value_score, verdict, critique}``, fallback rationale
"Passed all verifier acceptance tests" with 0.85 live-default / 0.95-floor
scores (controller.py:710,714,731,739).

D7: SST is consumed read-only (imports only); no SST source is modified.
Inhibitor injection (BT-11b) rides the owned bundle→packet call site (BT-11a):
FileBackedMemory hits are appended to ``bundle.membrane_protocols`` (prefixed
``memory-inhibitor: ``), forward-project to tagged packet invariants via P01,
and reach ``capsule_compiler.compile`` through the controller's own call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from stc.integration.harness_worker import CritiqueProvenance

from pydantic import BaseModel, ConfigDict, Field
from sst.context.capsule import ContextCapsuleCompiler
from sst.core.contracts import CandidateProposal, ScoreBreakdown, TaskPacket
from sst.core.events import EventKind, SSTEvent
from sst.core.models import DeterministicGateResult
from sst.gateway.gateway import ModelGateway
from sst.sandbox.custody import CandidateCustodyManager
from sst.search.controller import SSTSearchController
from sst.search.policy import SearchPolicy
from sst.storage.store import SQLiteSSTStore

from stc.integration.adapters import (
    AdapterContext,
    receipt_to_score,
    task_bundle_to_packet,
)
from stc.integration.diff_binding import (
    DiffBindingError,
    normalize_diff,
    recount_patch_hunk_headers,
    render_binding_diff,
    restore_patch_trailing_newline,
    write_scratch_bundle,
)
from stc.integration.env_probe import (
    FloorViolationError,
    check_floor,
    env_digest_of,
    env_requalifies,
)
from stc.integration.identity import IntegrationError
from stc.integration.lease_git import (
    MANIFEST_EXCLUDE_DIRS,
    LeaseGitError,
    LeaseTripwire,
    TripwireBreach,
    assert_head_equals,
    checkout_ref,
    commit_tree,
    create_scratch_ref,
    ensure_disposable_git,
    hash_tree_manifest,
    prove_import_integrity,
    verify_baseline_manifest,
)
from stc.integration.linked_records import (
    CONTRACT_REV,
    CustodyIntake,
    MergeRecord,
    SelectionOutcomeRecord,
    SelectionRecord,
    candidate_content_digest,
    digest_of,
    dossier_digest_list,
    dossier_signature,
    save_record,
)
from stc.integration.memory import FileBackedMemory
from stc.integration.selection import (
    SelectionError,
    SelectionResult,
    is_external_target_root,
    load_owning_suite_map,
    load_selection_config,
    run_selection,
)
from stc.judiciary.auditor import JudiciaryAuditor
from stc.schemas.models import ExecutionReceipt, JudiciaryVerdict, TaskBundle
from stc.substrate.runner import MUTMUT_TARGETS_PREFIX, SubstrateRunner, parse_mutmut_targets

__all__ = [
    "DEFAULT_LIVE_CRITIQUE_RATIONALE",
    "DEFAULT_LIVE_CRITIQUE_SCORE",
    "FALLBACK_CRITIQUE_RATIONALE",
    "INHIBITOR_PREFIX",
    "MAX_INJECTED_INHIBITORS",
    "MUTMUT_NON_REPORT_MARKERS",
    "SYNTHESIS_THRESHOLD",
    "ChampionResult",
    "DialecticError",
    "DialecticRunner",
    "LossLedger",
    "LossLedgerEntry",
    "NoChampionResult",
    "STCCustodyWrapper",
    "SynthesisReceipt",
    "VetoRecord",
    "count_mutmut_runs",
    "lease_id_for",
    "mirror_source_tree",
    "render_merged_diff",
    "sanitize_lease_segment",
    "scrape_tainted_scores",
]

#: Exact fallback rationale the controller emits when the Cortex Critic path is
#: unavailable (controller.py:739). Veto rule 1 keys on this verbatim.
FALLBACK_CRITIQUE_RATIONALE: Final[str] = "Passed all verifier acceptance tests"

#: Live-path garbage default: unparseable critic JSON yields score 0.85 with
#: this rationale (controller.py:710-716). Veto rule 2 keys on the PAIR
#: (score == 0.85 AND this rationale); neither alone taints.
DEFAULT_LIVE_CRITIQUE_RATIONALE: Final[str] = "Evaluated by Cortex Critic"
DEFAULT_LIVE_CRITIQUE_SCORE: Final[float] = 0.85

#: Prefix of deterministic verifier-fail rationales (controller.py:664: the
#: controller prunes WITHOUT a gateway critique call). Scores bearing this
#: prefix consume no Rule-3 pairing slot, so later witness-bearing scores
#: still align with their own critique calls.
_DETERMINISTIC_FAIL_PREFIX: Final[str] = "Deterministic verifier failed:"

#: Controller's colimit-synthesis trigger (controller.py:274-277).
SYNTHESIS_THRESHOLD: Final[float] = 0.8

#: Prefix marking memory-sourced inhibitors injected into membrane_protocols.
INHIBITOR_PREFIX: Final[str] = "memory-inhibitor: "

#: Cap on injected inhibitors per run (corpus retrieval is small; fail-closed).
MAX_INJECTED_INHIBITORS: Final[int] = 8

#: Mutmut snippet classes that are NOT a real report (RT-05 counting rule).
#: A run counts iff duration>0 AND a non-empty snippet AND none of these
#: markers is present. "Gate timed out" (substrate wording, never mutmut
#: wording) and module-missing markers are conservative extensions: a timeout
#: or a missing binary produced no measurement. See B1.2.
MUTMUT_NON_REPORT_MARKERS: Final[tuple[str, ...]] = (
    "NOT-MEASURED",
    "DEFERRED:",
    "disabled by runner configuration",
    "skipped under active mutation",
    "No module named mutmut",
    'No module named "mutmut"',
    "No module named 'mutmut'",
    "Gate timed out",
)


class DialecticError(IntegrationError):
    """Runner/wrapper misuse or invariant breach (never a search outcome)."""


def count_mutmut_runs(receipt: ExecutionReceipt) -> int:
    """RT-05 counting rule: 1 iff the receipt carries a REAL mutmut report."""
    gate = receipt.gate_mutmut
    if gate.duration_seconds <= 0:
        return 0
    snippet = gate.raw_output_snippet or ""
    if not snippet.strip():
        return 0
    for marker in MUTMUT_NON_REPORT_MARKERS:
        if marker in snippet:
            return 0
    return 1


class VetoRecord(BaseModel):
    """One champion-veto decision with its scraping evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    value_score: float
    rationale: str
    rule: str  # veto rule name (see scrape_tainted_scores Rules 0-3)


class SynthesisReceipt(BaseModel):
    """Receipt for one colimit synthesis: parents + scores + verification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    synthesis_id: str
    tree_id: str
    parent_ids: list[str]
    parent_scores: dict[str, float]
    synth_candidate_id: str
    synth_score: float
    verification_passed: bool
    verification_exit_code: int
    verification_duration_s: float


class LossLedgerEntry(BaseModel):
    """One collapsed partial: verified but below the synthesis threshold."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    tree_id: str
    normalized_reward: float
    critic_verdict: str | None
    reason: str  # "below-synthesis-threshold"


class LossLedger(BaseModel):
    """Typed refs for collapsed partials (RT-06: never silent)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_id: str
    entries: list[LossLedgerEntry] = Field(default_factory=list)


class NoChampionResult(BaseModel):
    """Typed no-champion outcome for P05's partial dossier (RT-10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_id: str
    run_id: str
    branch_refs: list[str]
    scores_summary: dict[str, float]
    veto_log: list[VetoRecord] = Field(default_factory=list)
    budget_state: dict[str, float] = Field(default_factory=dict)
    reason: str
    evidence_dir: str
    # D-zeta: dossier digest list over the linked records present for this
    # outcome (intake + per-node selection + selection-outcome; the merge
    # record is absent by design — no champion => no success artifacts)
    # plus the HMAC over that list. Empty only when no records exist.
    linked_record_digests: dict[str, str] = Field(default_factory=dict)
    dossier_signature: str = ""


class ChampionResult(BaseModel):
    """Typed champion outcome: merged diff + post-merge receipt + audit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_id: str
    run_id: str
    champion_id: str
    reselected: bool
    merged_diff: str
    post_merge_receipt: ExecutionReceipt
    retry_receipts: list[ExecutionReceipt] = Field(default_factory=list)
    mutmut_count: int
    retry_mutmut_counts: list[int] = Field(default_factory=list)
    mutmut_disposition: str
    synthesis_receipts: list[SynthesisReceipt] = Field(default_factory=list)
    loss_ledger: LossLedger
    judiciary_verdict: JudiciaryVerdict
    first_verdict: JudiciaryVerdict | None = None
    veto_log: list[VetoRecord] = Field(default_factory=list)
    scores_summary: dict[str, float] = Field(default_factory=dict)
    evidence_dir: str
    # D-zeta: dossier digest list covering all four linked records
    # (CustodyIntake + per-node SelectionRecords + selection-outcome +
    # merge) plus the HMAC over that list.
    linked_record_digests: dict[str, str] = Field(default_factory=dict)
    dossier_signature: str = ""


def scrape_tainted_scores(
    events: list[SSTEvent],
    critique_provenance: Sequence[CritiqueProvenance] | None = None,
) -> dict[str, VetoRecord]:
    """Scrapes SCORE_RECORDED events for fallback-critique taint (RT-03 veto).

    Rule 0 (explicit failure verdict): verdict == CRITIQUE_FAILED (new
    SST: critique failure/malformed/no-route discloses itself instead
    of a fabricated APPROVE; taints at any score).
    Rule 1 (exact fallback): critique == FALLBACK_CRITIQUE_RATIONALE.
    Rule 2 (live-path garbage default): score == 0.85 AND critique ==
    DEFAULT_LIVE_CRITIQUE_RATIONALE. Scores alone never taint: a genuine
    0.85/0.95 with a real rationale stays clean.
    Rule 3 (provenance, Fix 2): the k-th witness-bearing SCORE_RECORDED
    event pairs with the k-th critique call (the controller issues critiques
    sequentially, one score per call); when the paired witness is invalid
    (call failed/refused or content was not an explicit critique object),
    the score is tainted no matter its value — fallback scores must never
    approve. Deterministic verifier-fail scores bear no witness (the
    controller prunes without a gateway call) and consume no pairing slot.
    Unpaired scores (gateway without provenance) are left to Rules 1-2.
    First matching rule wins.
    """
    tainted: dict[str, VetoRecord] = {}
    score_index = 0
    for evt in events:
        if evt.kind != EventKind.SCORE_RECORDED:
            continue
        node_id = evt.node_id
        if not node_id or node_id in tainted:
            continue
        try:
            value_score = float(evt.payload.get("value_score", 0.0))
        except (TypeError, ValueError):
            continue
        rationale = str(evt.payload.get("critique", ""))
        verdict = str(evt.payload.get("verdict", ""))
        rule: str | None = None
        veto_rationale = rationale[:200]
        # Deterministic verifier-fail PRUNEs never issue a gateway critique
        # call, so they pair with no witness and consume no slot.
        bears_witness = not rationale.startswith(_DETERMINISTIC_FAIL_PREFIX)
        if verdict == "CRITIQUE_FAILED":
            rule = "explicit-critique-failed"
        elif rationale == FALLBACK_CRITIQUE_RATIONALE:
            rule = "exact-fallback-rationale"
        elif (
            rationale == DEFAULT_LIVE_CRITIQUE_RATIONALE
            and value_score == DEFAULT_LIVE_CRITIQUE_SCORE
        ):
            rule = "default-score-0.85"
        elif (
            bears_witness
            and critique_provenance is not None
            and score_index < len(critique_provenance)
        ):
            witness = critique_provenance[score_index]
            if not witness.valid:
                rule = "critique-unprovenanced"
                veto_rationale = (
                    f"critique call #{witness.seq + 1} unprovenanced "
                    f"({witness.detail}); ledger row {witness.ledger_row}"
                )[:200]
        if bears_witness:
            score_index += 1
        if rule is not None:
            tainted[node_id] = VetoRecord(
                candidate_id=node_id,
                value_score=value_score,
                rationale=veto_rationale,
                rule=rule,
            )
    return tainted


def sanitize_lease_segment(value: str) -> str:
    """Sanitizes one path segment so lease ids cannot escape leases_root."""
    cleaned = value.replace("/", "_").replace("\\", "_").replace("\x00", "_")
    cleaned = cleaned.replace("..", "__")
    return cleaned or "_"


def lease_id_for(task_id: str, candidate_id: str) -> str:
    """RT-12 lease id: candidate-suffixed task id."""
    return f"{sanitize_lease_segment(task_id)}__{sanitize_lease_segment(candidate_id)}"


#: Lease/merge mirror skip-set: tripwire-manifest names (single taxonomy)
#: minus .git, which is deliberately INCLUDED (unlike the parent
#: custody skip-set) because substrate receipts require commit binding
#: (_resolve_commit_hash raises on non-git trees — B1.3 finding). Unlike
#: the manifest, the mirror applies the set TOP LEVEL ONLY (direct
#: children of the mirror root): nested dirs with these names
#: (docs/.../dossier evidence) are evaluated content the lease must
#: contain — R4B regression, every-level skip emptied them and red-lit
#: the real-gates green path. Mirror ⊃ manifest from here on: every
#: hashed byte is still mirrored, but nested runtime-named evidence is
#: mirrored without being hashed.
_MIRROR_SKIP_DIRS: Final[frozenset[str]] = frozenset(set(MANIFEST_EXCLUDE_DIRS) - {".git"})


def mirror_source_tree(src: Path, dst: Path) -> None:
    """Mirrors a source tree into a lease/merge workspace (fail-closed).

    FOLLOWUP a1-fix (NOT Delta A1 — the dst-exclusion mirror rule): when
    ``dst`` lives inside ``src`` (the live layout — leases and the merged
    tree sit under the in-repo dossier), the ``dst`` subtree itself is
    excluded from the copy at every level; otherwise the mirror copies the
    destination into itself without bound. ``src == dst`` and
    ``src``-inside-``dst`` cannot be mirrored faithfully and raise loudly.
    """
    if not src.is_dir():
        raise DialecticError(f"source tree not found: {src}")
    src_resolved = src.resolve()
    dst_resolved = dst.resolve()
    if dst_resolved == src_resolved or src_resolved.is_relative_to(dst_resolved):
        raise DialecticError(f"refusing to mirror source into itself: src={src} dst={dst}")
    excluded = dst_resolved if dst_resolved.is_relative_to(src_resolved) else None
    dst.mkdir(parents=True, exist_ok=True)
    _mirror_into(src, dst, excluded)


def _mirror_into(src: Path, dst: Path, excluded: Path | None, top_level: bool = True) -> None:
    """Recursive copy step: top-level skip-set + dst-subtree exclusion.

    The skip-set applies to direct children of the mirror root ONLY
    (see _MIRROR_SKIP_DIRS); the dst-subtree exclusion stays
    every-level. Directory symlinks are replicated as links, never
    descended: package managers and dev wiring create link cycles that
    would ELOOP (or copy unbounded foreign bytes into) the lease. File
    symlinks keep the historical behavior (target bytes materialized
    via copy2). The dst-exclusion check is purely lexical (no
    resolve()) so cyclic links cannot break the comparison itself.
    """
    for item in list(src.iterdir()):
        if top_level and item.name in _MIRROR_SKIP_DIRS:
            continue
        if excluded is not None:
            # Purely lexical (absolute() never touches the FS): resolve()
            # would follow links and ELOOP on cycles.
            lexical = item.absolute()
            if lexical == excluded or lexical.is_relative_to(excluded):
                continue
        target = dst / item.name
        if item.is_symlink():
            try:
                link_is_dir = item.is_dir()
            except OSError:
                # Unstatable target (link cycle): replicate the link
                # itself rather than following it into the failure.
                link_is_dir = True
            if link_is_dir:
                if os.path.lexists(target):
                    if target.is_dir() and not target.is_symlink():
                        raise DialecticError(f"mirror link/dir collision at {target} (from {item})")
                    target.unlink()
                target.symlink_to(item.readlink())
                continue
            shutil.copy2(item, target)
            continue
        if item.is_dir():
            target.mkdir(exist_ok=True)
            _mirror_into(item, target, excluded, False)
        else:
            shutil.copy2(item, target)


def _denylist_hit(clean_path: str, forbidden_paths: list[str]) -> str | None:
    """Mirrors custody._validate_path_containment prefix semantics verbatim."""
    for forbidden in forbidden_paths:
        clean_forbid = forbidden.strip().lstrip("/\\")
        if (
            clean_path == clean_forbid
            or clean_path.startswith(f"{clean_forbid}/")
            or clean_path.startswith(f"{clean_forbid}\\")
        ):
            return forbidden
    return None


def _epoch_from_packet(packet: TaskPacket) -> int:
    """Reads the run epoch back from forward-projected evidence (default 1)."""
    raw = packet.evidence_references.get("stc.epoch_index", "1")
    try:
        epoch = int(raw)
    except (TypeError, ValueError):
        return 1
    return epoch if 1 <= epoch <= 3 else 1


def _receipt_gate_duration(receipt: ExecutionReceipt) -> float:
    total = (
        receipt.gate_ruff.duration_seconds
        + receipt.gate_mypy.duration_seconds
        + receipt.gate_pytest.duration_seconds
        + receipt.gate_mutmut.duration_seconds
    )
    return round(total, 4)


def _score_summary(lease_id: str, score: ScoreBreakdown) -> str:
    gates = score.hard_gates
    return (
        f"lease {lease_id}: ruff={gates.get('stc_ruff')} "
        f"mypy={gates.get('stc_mypy')} pytest={gates.get('stc_pytest')} "
        f"reward={score.normalized_reward:.2f}"
    )


def _score_failure_detail(score: ScoreBreakdown, lease_id: str) -> str:
    # SST prunes on stderr[:100]: gates + first signals lead, lease/reward ride the tail.
    bad = sorted(name for name, ok in score.hard_gates.items() if not ok)
    found = score.raw_metrics.get("first_signals", [])
    signals = [str(item) for item in found] if isinstance(found, list) else []
    return _render_gate_failure_detail(bad, signals, score.normalized_reward, lease_id)


def _non_pass(reason: str) -> DeterministicGateResult:
    """Deterministic non-pass (rejection/fail-closed), never a partial score."""
    return DeterministicGateResult(
        passed=False,
        exit_code=1,
        stdout="",
        stderr=reason[:2000],
        duration_seconds=0.0,
        failure_reason=reason[:500],
    )


def _selection_diff_inputs(proposal: CandidateProposal) -> tuple[list[str], list[str], list[str]]:
    """Extracts trusted-selection inputs from a proposal (deterministic).

    Returns ``(diff_paths, symbols, suggested_tests)``. Paths come from
    target paths + file operations; symbols from file-operation symbol
    annotations when present; suggested tests from proposal metadata
    (additive-only, satisfy nothing).
    """
    paths: list[str] = [str(p) for p in proposal.target_paths]
    symbols: list[str] = []
    for op in proposal.file_operations:
        paths.append(str(op.get("path", "")))
        raw_symbols = op.get("symbols", [])
        if isinstance(raw_symbols, list):
            symbols.extend(str(item) for item in raw_symbols if str(item).strip())
    suggested: list[str] = []
    metadata = proposal.metadata if isinstance(proposal.metadata, dict) else {}
    raw_suggested = metadata.get("suggested_tests", [])
    if isinstance(raw_suggested, list):
        suggested = [str(item) for item in raw_suggested if str(item).strip()]
    return paths, symbols, suggested


def _observed_argv(substrate: Any, call_shape: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Actual gate argv for the SelectionRecord (D-zeta).

    Prefers the substrate's OBSERVED argv (what ran) when the runner
    exposes it; otherwise records the call shape with explicit
    provenance (test substrates expose no observed argv).
    """
    observed = getattr(substrate, "last_gate_argv", None)
    if isinstance(observed, dict) and observed:
        return (
            {"observed_gate_argv": observed, "call": call_shape},
            "observed-substrate-argv",
        )
    return ({"call": call_shape}, "substrate-call-shape (no observed argv)")


def _routes_to_git_apply(proposal: CandidateProposal) -> bool:
    """Mirrors SST's apply-dispatch for ``patch_diff`` (custody.py, read-only).

    SST feeds ``patch_diff`` to ``git apply`` iff the proposal carries no
    file operations and the text is diff-shaped (``--- `` / ``diff --git``
    / ``@@``). Only those bytes can hit "corrupt patch", so only those
    are repair candidates; raw-code payloads stay byte-exact (pinned by
    the raw-merge contract). Drift fails loudly via the mirror tests.
    """
    if proposal.file_operations:
        return False
    diff = proposal.patch_diff
    return diff.startswith("--- ") or "@@" in diff or diff.startswith("diff --git")


def _with_restored_patch_newline(proposal: CandidateProposal) -> CandidateProposal:
    """Returns the proposal with transport-repaired bytes for custody apply.

    Option 1 repair (STC-owned): the SST controller strips the trailing
    newline of every ``proposed_changes``, so STC restores exactly one LF
    before handing the patch to ``CandidateCustodyManager.apply_proposal``.
    Returns the SAME object unless these exact bytes would route to
    ``git apply`` AND lack the trailing LF; otherwise a copy with only
    ``patch_diff`` changed. Callers pass the result ONLY to the apply
    call — records, digests, and selection keep the original bytes.
    """
    if not proposal.patch_diff or not _routes_to_git_apply(proposal):
        return proposal
    restored = restore_patch_trailing_newline(proposal.patch_diff)
    if restored == proposal.patch_diff:
        return proposal
    return proposal.model_copy(update={"patch_diff": restored})


def _with_recounted_patch_headers(proposal: CandidateProposal) -> CandidateProposal:
    """Returns the proposal with recounted ``@@`` hunk headers.

    Option 2 repair (STC-owned): model emitters routinely miscount
    hunk ``oldcount``/``newcount`` while context stays verbatim, and
    ``git apply`` rejects the patch as corrupt before judging content
    (csvledger run-1 triage: 15/15 rejections, all rescued by
    ``git apply --recount``). Rewrites counts only; starts, section
    text, and body lines pass through, so ``git apply`` still judges
    the actual content. Returns the SAME object unless these exact
    bytes would route to ``git apply`` AND a count changes; otherwise
    a copy with only ``patch_diff`` changed. Callers chain it BEFORE
    :func:`_with_restored_patch_newline` and pass the result ONLY to
    the apply call — records, digests, and selection keep the original
    bytes.
    """
    if not proposal.patch_diff or not _routes_to_git_apply(proposal):
        return proposal
    recounted = recount_patch_hunk_headers(proposal.patch_diff)
    if recounted == proposal.patch_diff:
        return proposal
    return proposal.model_copy(update={"patch_diff": recounted})


class STCCustodyWrapper:
    """STC substrate custody composed around (never subclassing) SST custody.

    The controller calls ``verify_candidate_proposal`` with the parent's exact
    signature. This wrapper applies the proposal via the parent manager inside
    a per-node lease (lease id = task-id + candidate-id suffix), runs ruff +
    mypy --strict + pytest through the STC substrate runner (mutmut forced
    OFF per node), maps the receipt via P01 ``receipt_to_score``, and returns
    a ``DeterministicGateResult``. ``acceptance_command`` is declared ignored:
    SST's single-command behavior is bypassed by wrapper construction.

    Denylist (packet ``forbidden_paths``) is enforced at lease allocation,
    before any lease directory is created. Leases are released on completion
    and quarantined (moved under ``_quarantine`` with a reason file) on
    substrate crashes. Thread-safe for parallel node leases.
    """

    def __init__(
        self,
        custody: CandidateCustodyManager,
        substrate: SubstrateRunner,
        *,
        leases_root: Path | str,
        baseline_manifest: dict[str, str] | None = None,
        baseline_pin: dict[str, str] | None = None,
        hmac_key: str | bytes | None = None,
        workspace: Path | str | None = None,
    ) -> None:
        self._custody = custody
        self._substrate = substrate
        self.leases_root = Path(leases_root)
        self.quarantine_root = self.leases_root / "_quarantine"
        self.leases_root.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.receipts: dict[str, ExecutionReceipt] = {}
        self.scores: dict[str, ScoreBreakdown] = {}
        # T0 baseline pin for the E4 intake re-hash. The runner passes the
        # explicit T0 manifest; standalone use pins on first intake (the
        # source tree is never mutated in place, so first sight == baseline).
        self._baseline_manifest = dict(baseline_manifest) if baseline_manifest is not None else None
        self._baseline_pin = dict(baseline_pin) if baseline_pin is not None else {}
        self._hmac_key = hmac_key
        self._workspace = Path(workspace) if workspace is not None else None
        # Per-candidate linked records + evidence (persisted by the runner
        # into the run dir; the leases dir itself keeps only _quarantine).
        self.intakes: dict[str, CustodyIntake] = {}
        self.selections: dict[str, SelectionRecord] = {}
        self.env_fingerprints: dict[str, dict[str, Any]] = {}
        self.binding_diffs: dict[str, bytes] = {}
        self.import_proofs: dict[str, dict[str, Any]] = {}
        self._selection_config: dict[str, Any] | None = None
        self._suite_map: dict[str, Any] | None = None

    @property
    def custody(self) -> CandidateCustodyManager:
        """The wrapped parent manager (patch application + scope checks)."""
        return self._custody

    @property
    def substrate(self) -> SubstrateRunner:
        """The STC substrate runner (sole hard-gate authority)."""
        return self._substrate

    def _run_trusted_selection(
        self,
        diff_paths: list[str],
        symbols: list[str],
        suggested: list[str],
        target_root: Path | str | None = None,
    ) -> tuple[SelectionResult, dict[str, Any]]:
        """Runs the section 5.2 trusted selection (config cached in-process).

        ``target_root`` is the construction target tree the lease mirrors;
        targets outside the STC tree scope the lease pytest gate to the
        target suite (STC mandatory IDs are verified, not run).
        """
        with self._lock:
            if self._selection_config is None:
                self._selection_config = load_selection_config()
            if self._suite_map is None:
                self._suite_map = load_owning_suite_map(
                    required_revision=self._selection_config["owning_suite_map_revision"]
                )
            config, suite_map = self._selection_config, self._suite_map
        return run_selection(
            diff_paths,
            symbols,
            suggested,
            workspace=self._workspace,
            config=config,
            suite_map=suite_map,
            target_root=target_root,
        )

    def _suite_map_revision(self) -> str:
        with self._lock:
            suite_map = self._suite_map
        return str(suite_map.get("map_revision", "")) if suite_map else ""

    def _baseline_ref(self, task: TaskPacket) -> dict[str, str]:
        """Baseline receipt ref for the intake (T0 pin, or standalone synth)."""
        if self._baseline_pin:
            return dict(self._baseline_pin)
        manifest = self._baseline_manifest or {}
        return {
            "base_commit": task.base_commit,
            "baseline_content_digest": digest_of({rel: manifest[rel] for rel in sorted(manifest)}),
            "env_digest": "standalone-unpinned",
        }

    def verify_candidate_proposal(
        self,
        task: TaskPacket,
        proposal: CandidateProposal,
        source_dir: Path | str,
        acceptance_command: str | None = None,
        timeout: int = 120,
    ) -> DeterministicGateResult:
        """Verifies one candidate: parent apply + STC gates in a node lease."""
        _ = acceptance_command  # declared ignored: substrate gates always run
        _ = timeout  # gate timeouts governed by substrate config, not per call
        lease_id = lease_id_for(task.task_id, proposal.candidate_id)
        touched: list[str] = list(proposal.target_paths)
        touched.extend(
            str(op.get("path", "")) for op in proposal.file_operations if isinstance(op, dict)
        )
        for path_str in touched:
            if not path_str.strip():
                continue
            clean = path_str.strip().lstrip("/\\")
            hit = _denylist_hit(clean, list(task.forbidden_paths))
            if hit is not None:
                msg = (
                    f"Scope Policy Violation: path '{path_str}' touches "
                    f"forbidden '{hit}' (denied at P04 lease allocation; "
                    "no lease created)."
                )
                return DeterministicGateResult(
                    passed=False,
                    exit_code=1,
                    stdout="",
                    stderr=msg,
                    duration_seconds=0.0,
                    failure_reason=msg,
                )
        src = Path(source_dir)
        if not src.is_dir():
            msg = f"Lease {lease_id}: source tree not found: {src}"
            return DeterministicGateResult(
                passed=False,
                exit_code=1,
                stdout="",
                stderr=msg,
                duration_seconds=0.0,
                failure_reason=msg,
            )
        lease_ws = self._lease_path(lease_id)
        try:
            lease_ws.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            self.quarantine_lease(lease_id, "stale lease dir present at allocation")
            lease_ws.mkdir(parents=True, exist_ok=False)
        try:
            mirror_source_tree(src, lease_ws)
            # T2 custody: disposable git (sanitized mirror or fresh init),
            # then the tripwire opens over the mirrored bytes.
            try:
                lease_mode = ensure_disposable_git(lease_ws)
            except LeaseGitError as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: disposable git setup failed: {exc}")
            tripwire = LeaseTripwire(lease_id)
            try:
                tripwire.manifest_open = hash_tree_manifest(lease_ws)
            except TripwireBreach as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: tripwire open failed: {exc}")
            # E4 intake baseline-manifest re-hash (`--locked` semantics):
            # drift fails closed (re-pin T0, never proceed).
            if self._baseline_manifest is None:
                with self._lock:
                    if self._baseline_manifest is None:
                        self._baseline_manifest = hash_tree_manifest(src)
            else:
                drift = verify_baseline_manifest(src, self._baseline_manifest)
                if drift:
                    self.release_lease(lease_id)
                    return _non_pass(
                        f"Lease {lease_id}: baseline manifest drifted since T0 "
                        f"({drift[0]}; re-pin T0, never proceed)"
                    )
            try:
                base_sha = commit_tree(lease_ws, f"stc baseline ({task.base_commit})")
            except LeaseGitError as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: baseline commit failed: {exc}")
            app_result = self._custody.apply_proposal(
                _with_restored_patch_newline(_with_recounted_patch_headers(proposal)),
                lease_ws,
                task=task,
            )
            if not app_result.success:
                self.release_lease(lease_id)
                err = app_result.error_message or "Patch application failed"
                return DeterministicGateResult(
                    passed=False,
                    exit_code=1,
                    stdout="",
                    stderr=err[:2000],
                    duration_seconds=0.0,
                    failure_reason=err[:500],
                )
            # Proposal application is AUTHORIZED mutation: re-baseline the
            # tripwire explicitly (recorded, never silent).
            try:
                tripwire.rebaseline_after_apply(lease_ws)
            except TripwireBreach as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: tripwire re-baseline failed: {exc}")
            # Scratch ref at intake: commit, name, check out (primary-lease
            # rule — propagation AND head assert, section 5.3).
            try:
                scratch_sha = commit_tree(lease_ws, f"stc scratch {proposal.candidate_id}")
                scratch_ref = create_scratch_ref(lease_ws, proposal.candidate_id, scratch_sha)
                checkout_ref(lease_ws, scratch_ref)
            except LeaseGitError as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: scratch ref setup failed: {exc}")
            # Per-lease import-integrity proof before gates (section Q3):
            # failure fails closed (wrong bytes => verdict void). Preserved
            # to quarantine as evidence (a COPY, never the live lease).
            try:
                import_proof = prove_import_integrity(lease_ws)
            except LeaseGitError as exc:
                self.quarantine_lease(lease_id, f"import-integrity failed: {exc}")
                return _non_pass(f"Lease {lease_id}: import-integrity failed: {exc}")
            # Tripwire pre-gates checkpoint (detection-with-fail-closed).
            try:
                tripwire.check_pre_gates(lease_ws)
            except TripwireBreach as exc:
                self.quarantine_lease(lease_id, f"tripwire pre-gates: {exc}")
                return _non_pass(f"Lease {lease_id}: {exc}")
            # Floor + exact per-check fingerprint (section 5.5). Fails
            # closed ONLY on floor violation or missing tool.
            try:
                fingerprint = check_floor()
            except FloorViolationError as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: {exc}")
            env_digest = env_digest_of(fingerprint)
            # Trusted test selection (section 5.2): mandatory + affected +
            # broadenings + additive suggestions. Missing-fails-closed.
            diff_paths, symbols, suggested = _selection_diff_inputs(proposal)
            try:
                selection, sel_verify = self._run_trusted_selection(
                    diff_paths, symbols, suggested, target_root=src
                )
            except SelectionError as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: trusted selection failed: {exc}")
            # Head assert at gate time (section 5.3): never other bytes.
            try:
                assert_head_equals(lease_ws, scratch_sha)
            except LeaseGitError as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: {exc}")
            # E1 production call site (per-node): the explicit
            # `run_mutmut=False` kwarg takes precedence over the
            # runner.py trap, which therefore cannot arm here — mutmut is
            # already out by ADR-INT-01 as a coverage fact, and the
            # SelectionRecord's safeguard declaration says so.
            call_shape = {
                "worktree": str(lease_ws),
                "task_id": task.task_id,
                "epoch_index": _epoch_from_packet(task),
                "pytest_target": selection.pytest_target,
                "run_mutmut": False,
            }
            receipt = self._substrate.execute_gates(
                lease_ws,
                task_id=task.task_id,
                epoch_index=_epoch_from_packet(task),
                pytest_target=selection.pytest_target,
                run_mutmut=False,
            )
            try:
                assert_head_equals(lease_ws, scratch_sha)
                tripwire.check_close(lease_ws)
            except (LeaseGitError, TripwireBreach) as exc:
                self.quarantine_lease(lease_id, f"close: {exc}")
                return _non_pass(f"Lease {lease_id}: {exc}")
            # Linked records (D-zeta): intake + per-node selection, signed.
            try:
                node_diff = render_binding_diff(lease_ws, base_sha, scratch_sha)
            except DiffBindingError as exc:
                self.release_lease(lease_id)
                return _non_pass(f"Lease {lease_id}: binding diff failed: {exc}")
            actual_argv, argv_provenance = _observed_argv(self._substrate, call_shape)
            intake = CustodyIntake(
                candidate_id=proposal.candidate_id,
                base_commit=task.base_commit,
                scratch_ref=scratch_ref,
                scratch_ref_sha=scratch_sha,
                candidate_content_digest=candidate_content_digest(scratch_sha, {}, node_diff),
                untracked_manifest={},
                baseline_receipt_ref=self._baseline_ref(task),
                target_env_digest=env_digest,
                lease_mode=lease_mode,
            ).signed(self._hmac_key)
            record = SelectionRecord(
                candidate_id=proposal.candidate_id,
                intake_ref=intake.digest(),
                config_revision=sel_verify["config_revision"],
                mandatory_digest=sel_verify["mandatory_digest"],
                affected_inputs={
                    "diff_paths": sorted(set(diff_paths)),
                    "symbols": sorted(set(symbols)),
                    "affected": selection.affected,
                    "owning_suite_map_revision": self._suite_map_revision(),
                },
                broadenings=list(selection.broadenings),
                unrun_with_reasons=list(selection.unrun_with_reasons),
                suggested_tests=list(selection.suggested),
                actual_gate_argv=actual_argv,
                argv_provenance=argv_provenance,
                contract_rev=CONTRACT_REV,
                safeguard_declaration=["ruff", "mypy", "scoped-pytest"],
                safeguards_dropped=["mutmut (ADR-INT-01 champion-only; explicit run_mutmut=False)"],
                env_digest=env_digest,
            ).signed(self._hmac_key)
            score = receipt_to_score(receipt)
            with self._lock:
                self.receipts[proposal.candidate_id] = receipt
                self.scores[proposal.candidate_id] = score
                self.intakes[proposal.candidate_id] = intake
                self.selections[proposal.candidate_id] = record
                self.env_fingerprints[proposal.candidate_id] = fingerprint
                self.binding_diffs[proposal.candidate_id] = node_diff
                self.import_proofs[proposal.candidate_id] = import_proof
            self.release_lease(lease_id)
            summary = _score_summary(lease_id, score)
            if score.passed_hard_gates:
                return DeterministicGateResult(
                    passed=True,
                    exit_code=0,
                    stdout=summary,
                    stderr="",
                    duration_seconds=_receipt_gate_duration(receipt),
                )
            detail = _score_failure_detail(score, lease_id)
            return DeterministicGateResult(
                passed=False,
                exit_code=1,
                stdout=summary,
                stderr=detail,
                duration_seconds=_receipt_gate_duration(receipt),
                failure_reason=detail,
            )
        except Exception as exc:
            self.quarantine_lease(lease_id, f"{type(exc).__name__}: {exc}")
            msg = f"Substrate error in lease {lease_id}: {exc}"
            return DeterministicGateResult(
                passed=False,
                exit_code=1,
                stdout="",
                stderr=msg[:2000],
                duration_seconds=0.0,
                failure_reason=msg[:500],
            )

    def _lease_path(self, lease_id: str) -> Path:
        """Resolves a lease dir, refusing escapes from leases_root."""
        candidate = (self.leases_root / sanitize_lease_segment(lease_id)).resolve()
        root = self.leases_root.resolve()
        if candidate == root or not candidate.is_relative_to(root):
            raise DialecticError(f"refusing lease path outside leases_root: {lease_id!r}")
        return candidate

    def release_lease(self, lease_id: str) -> None:
        """Deletes a completed lease workspace whole (RT-04 + T2d).

        Whole-delete cleanup: the disposable git (mirror copy or clone)
        is removed entirely with the lease. No ref, remote, or worktree
        registration can survive: the lease git never shared state with
        the original repository.
        """
        shutil.rmtree(self._lease_path(lease_id), ignore_errors=True)

    def quarantine_lease(self, lease_id: str, reason: str) -> Path | None:
        """Preserves a COPY of a lease workspace to quarantine + reason file.

        T2d: quarantine preserves a COPY for inspection, never the live
        lease — the live lease is deleted after the copy lands. A
        leftover source (failed delete) is quarantined again as stale at
        the next allocation for this lease id (existing mechanism).
        """
        src = self._lease_path(lease_id)
        if not src.exists():
            return None
        dest = self.quarantine_root / f"{src.name}__{uuid.uuid4().hex[:6]}"
        shutil.copytree(src, dest, symlinks=True)
        (dest / "quarantine_reason.txt").write_text(reason[:2000], encoding="utf-8")
        shutil.rmtree(src, ignore_errors=True)
        return dest


def _is_unified_diff(text: str) -> bool:
    return (
        text.startswith("--- ")
        or text.startswith("diff --git")
        or text.startswith("@@ ")
        or "\n@@ " in text
    )


def render_merged_diff(proposal: CandidateProposal) -> str:
    """Renders the champion proposal as judiciary-scannable unified diff text.

    Verbatim unified diffs pass through; raw code and file operations render
    as synthetic single-file diffs so the judiciary's ``+++ b/`` attribution
    and +/- line scans observe the merged content.

    Section 5.6 role: this is the PROPOSAL preview renderer. The bound
    ``merged_diff`` (the merge block) is the frozen-policy diff rendered
    from the merge scratch ref; both pass through the ONE shared
    transport-only ``normalize_diff()`` (also used at audit).
    """
    diff = proposal.patch_diff or ""
    if diff and _is_unified_diff(diff):
        return normalize_diff(diff)
    chunks: list[str] = []
    if proposal.file_operations:
        for op in proposal.file_operations:
            path = str(op.get("path", "")).strip().lstrip("/\\") or "unknown"
            content = str(op.get("content", ""))
            action = str(op.get("action", "write"))
            if action == "delete":
                chunks.append(f"--- a/{path}\n+++ /dev/null\n")
                chunks.extend(f"-{line}\n" for line in content.splitlines())
            else:
                chunks.append(f"--- a/{path}\n+++ b/{path}\n")
                chunks.extend(f"+{line}\n" for line in content.splitlines())
    elif diff:
        target = "unknown"
        if proposal.target_paths:
            target = proposal.target_paths[0].strip().lstrip("/\\") or "unknown"
        chunks.append(f"--- a/{target}\n+++ b/{target}\n")
        chunks.extend(f"+{line}\n" for line in diff.splitlines())
    return normalize_diff("".join(chunks))


def _proposal_from_events(
    node_id: str, tree_id: str, events: list[SSTEvent]
) -> CandidateProposal | None:
    """Reconstructs a verified proposal from its proposal event payload.

    Diverge/refine nodes publish NODE_PROPOSED; the controller publishes
    SYNTHESIS_PROPOSED (never NODE_PROPOSED) for synthesis nodes, so both
    shapes are handled — a veto-reselected synthesis champion must merge.
    """
    for evt in events:
        if evt.node_id != node_id:
            continue
        payload = evt.payload
        if evt.kind == EventKind.NODE_PROPOSED:
            parent_id = str(payload.get("parent_id", ""))
            return CandidateProposal(
                candidate_id=node_id,
                tree_id=tree_id,
                parent_ids=[parent_id] if parent_id else [],
                role=str(payload.get("role", "DIVERGE")),
                title=str(payload.get("title", node_id)),
                rationale="reconstructed from NODE_PROPOSED event (veto re-selection)",
                target_paths=[str(p) for p in payload.get("target_paths", [])],
                patch_diff=str(payload.get("patch_diff", "")),
                model_id=str(payload.get("model_id", "")),
            )
        if evt.kind == EventKind.SYNTHESIS_PROPOSED:
            return CandidateProposal(
                candidate_id=node_id,
                tree_id=tree_id,
                parent_ids=[str(p) for p in payload.get("parent_ids", [])],
                role="SYNTHESIZE",
                title=str(payload.get("title", node_id)),
                rationale=str(payload.get("rationale", "reconstructed from SYNTHESIS_PROPOSED")),
                target_paths=[str(p) for p in payload.get("target_paths", [])],
                patch_diff=str(payload.get("patch_diff", "")),
                model_id=str(payload.get("model_id", "")),
            )
    return None


#: Frozen T0 gate argv (section 5, as corrected): the exact gate command
#: lines the T0 baseline pin binds. Whole-tree Gates 1-3, live deselected.
T0_GATE_ARGV: Final[dict[str, list[list[str]]]] = {
    "ruff": [["ruff", "check", "."], ["ruff", "format", "--check", "."]],
    "mypy": [["mypy", "--strict", "src", "tests"]],
    "pytest": [["pytest", "-v", "--tb=short", "-m", "not live"]],
}


def _build_selection_outcome(
    tree_id: str,
    run_id: str,
    verified: set[str],
    scores_summary: dict[str, float],
    tainted: dict[str, VetoRecord],
    *,
    selected: str | None,
    reason: str | None,
    per_node_refs: dict[str, str],
    key: str | bytes | None,
) -> SelectionOutcomeRecord:
    """Builds the signed T4 selection-outcome record (either outcome)."""
    return SelectionOutcomeRecord(
        tree_id=tree_id,
        run_id=run_id,
        verified=sorted(verified),
        tainted={node: record.rule for node, record in sorted(tainted.items())},
        scores_summary=dict(sorted(scores_summary.items())),
        selected_node=selected,
        no_champion_reason=reason,
        per_node_refs=dict(sorted(per_node_refs.items())),
    ).signed(key)


def _measured_disposition(receipt: ExecutionReceipt) -> str | None:
    """Measured disposition when the receipt carries a targets line (R3).

    Returns ``counted-once:measured:<targets line>`` so the mutated-paths
    list + mutant counts ride the ChampionResult disposition verbatim, or
    None for the legacy/unscoped shape (caller keeps "counted-once").
    """
    snippet = receipt.gate_mutmut.raw_output_snippet or ""
    for line in snippet.splitlines():
        if line.startswith(MUTMUT_TARGETS_PREFIX):
            fields = parse_mutmut_targets(snippet)
            if fields is None:
                return None
            return f"counted-once:measured:{line}"
    return None


def _render_gate_failure_detail(
    bad: list[str], signals: list[str], reward: float, lease_id: str
) -> str:
    """Head-first gate-failure detail: gates + first signals lead (A4-D1).

    SST feeds ``stderr[:100]`` back as the retry hint (controller:214) and
    keeps ``stderr[:500]`` in VERIFIER_FINISHED; the head therefore carries
    failed gate names + first error locations, while lease + reward ride the
    tail. ``verifier_passed`` is implied by the FAIL head and omitted.
    """
    gates = [name for name in bad if name != "verifier_passed"] or list(bad)
    head = " ".join(["FAIL", *gates, *(f"[{sig}]" for sig in signals)])
    return f"{head} | lease {lease_id} (reward {reward:.2f})"


def _mutmut_disposition(champion_mutmut: bool, receipt: ExecutionReceipt) -> str:
    """Honest disposition string for a non-counted champion mutmut gate."""
    if not champion_mutmut:
        return "not-run: disabled-by-config (mutmut-once covered by dedicated test)"
    gate = receipt.gate_mutmut
    snippet = gate.raw_output_snippet or ""
    if "empty mutation set" in snippet:
        return "not-run: NOT-MEASURED (empty mutation set; never-pass)"
    if "scoped mutmut unsupported" in snippet:
        return "not-run: NOT-MEASURED (scoped run refused on this executor; never-pass)"
    if "No module named" in snippet and "mutmut" in snippet:
        return "not-run: mutmut-unavailable (no mutmut module for this interpreter)"
    if "DEFERRED:" in snippet:
        return "not-run: deferred (per-node placeholder leaked to champion)"
    if "disabled by runner configuration" in snippet:
        return "not-run: disabled-by-config"
    if "skipped under active mutation" in snippet:
        return "not-run: skipped under active mutation runner"
    if "NOT-MEASURED" in snippet:
        return "not-run: NOT-MEASURED (WSL deferral, no measurement)"
    if "Gate timed out" in snippet:
        return "not-run: gate timeout (no report produced)"
    if gate.duration_seconds <= 0 or not snippet.strip():
        return "not-run: empty report (no measured run)"
    return "not-run: unclassified snippet (see post_merge_receipt.json)"


def derive_mutation_paths(
    binding_diff: bytes, *, target_root: str | Path | None = None
) -> list[str]:
    """Trusted champion-diff→production-paths derivation (R3).

    Parses the bound merge-scratch file list (the exact policy bytes the
    live/bundle checks verify) and keeps production files: under
    ``src/stc/`` for STC-tree targets, or any ``*.py`` outside test
    locations for external targets (``tests/`` trees and
    ``test_*``/``*_test``/``conftest`` files are never production).
    Deletions (``+++ /dev/null``) are dropped — removed code cannot be
    mutated. No test-only fallback: a champion touching no production
    file derives to [] and the substrate fails the gate closed as
    NOT-MEASURED-never-pass (operator approval: acceptance candidates
    must change production behavior with nonempty targets).
    """
    external = is_external_target_root(target_root)
    paths: list[str] = []
    text = binding_diff.decode("utf-8", errors="replace")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("+++ "):
            continue
        candidate = line[len("+++ ") :].strip()
        if len(candidate) >= 2 and candidate.startswith('"') and candidate.endswith('"'):
            candidate = candidate[1:-1]
        if candidate.startswith("b/"):
            candidate = candidate[len("b/") :]
        if not candidate or candidate in ("/dev/null", "dev/null"):
            continue
        if external:
            if not candidate.endswith(".py"):
                continue
            head, _, base = candidate.rpartition("/")
            if head == "tests" or head.startswith("tests/"):
                continue
            if base.startswith("test_") or base.endswith("_test.py") or base == "conftest.py":
                continue
            paths.append(candidate)
        elif candidate.startswith("src/stc/") and candidate.endswith(".py"):
            paths.append(candidate)
    return sorted(set(paths))


class DialecticRunner:
    """STC-owned dialectic search loop: controller + custody + veto + merge.

    ``run`` (sync, asyncio bridging over ``execute_search`` per BT-21) and
    ``run_async`` execute: inhibitor injection at the bundle→packet call site,
    search with the STC custody wrapper, champion veto by event scrape,
    synthesis receipts, loss ledger, champion merge, one post-merge receipt
    with mutmut counted once, and judiciary audit with ``with_codex=False``.

    The runner owns the SQLite store under ``evidence_root/<run_id>/store.db``
    with a generated ``tree_id``; the store DB and run JSONs are preserved as
    replay evidence (RT-11). Budget exhaustion or total veto yields a typed
    ``NoChampionResult`` — never a best-effort merge.
    """

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
        hmac_key: str | bytes | None = None,
    ) -> None:
        if auditor is not None and auditor.with_codex:
            raise DialecticError("auditor with_codex must be False (RT-08).")
        self._ctx = ctx
        self._gateway = gateway
        self._substrate = substrate
        self._evidence_root = Path(evidence_root)
        self._memory = memory
        self._policy = policy if policy is not None else SearchPolicy()
        self._auditor = (
            auditor if auditor is not None else JudiciaryAuditor(runner=substrate, with_codex=False)
        )
        self._champion_mutmut = champion_mutmut
        # Linked-record signing key: explicit wins, else the substrate's
        # receipt HMAC key (same authority); None => plain-sha256 mode,
        # recorded explicitly on every record (never inferred).
        substrate_key = getattr(getattr(substrate, "config", None), "hmac_key", None)
        self._hmac_key = hmac_key if hmac_key is not None else substrate_key
        self._evidence_root.mkdir(parents=True, exist_ok=True)

    def run(self, bundle: TaskBundle) -> ChampionResult | NoChampionResult:
        """Runs the full dialectic loop synchronously (BT-21 bridging)."""
        return asyncio.run(self.run_async(bundle))

    async def run_async(self, bundle: TaskBundle) -> ChampionResult | NoChampionResult:
        """Runs the full dialectic loop (awaitable for loop-resident callers)."""
        from stc.integration.harness_worker import SpendCapExceededError

        run_id = f"{sanitize_lease_segment(bundle.task_id)}-{uuid.uuid4().hex[:8]}"
        tree_id = run_id
        run_dir = self._evidence_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        packet_bundle, injected, queries = self._inject_inhibitors(bundle)
        self._write_json(
            run_dir,
            "inhibitors.json",
            {
                "queries": queries,
                "injected": injected,
                "memory_corpus": (
                    str(self._memory.corpus_dir) if self._memory is not None else None
                ),
            },
        )
        packet = task_bundle_to_packet(packet_bundle, self._ctx)
        # T0 baseline pin (precondition, once per base): identity half of
        # the baseline receipt — (base_commit, baseline_content_digest,
        # env_digest, gate_argv). Pins the bytes + env; the whole-tree
        # gate VERDICTS for this key are receipted by the S2 T0 run, not
        # here (no gates run at pin time). Floor failure stops the run.
        try:
            t0_fingerprint = check_floor()
        except FloorViolationError as exc:
            raise DialecticError(f"T0 baseline pin: floor unqualified: {exc}") from exc
        t0_env_digest = env_digest_of(t0_fingerprint)
        try:
            t0_manifest = hash_tree_manifest(packet.source_repo_root)
        except TripwireBreach as exc:
            raise DialecticError(f"T0 baseline pin: manifest failed: {exc}") from exc
        baseline_pin = {
            "base_commit": packet.base_commit,
            "baseline_content_digest": digest_of(
                {rel: t0_manifest[rel] for rel in sorted(t0_manifest)}
            ),
            "env_digest": t0_env_digest,
            "gate_argv_digest": digest_of(T0_GATE_ARGV),
        }
        self._write_json(
            run_dir,
            "baseline_pin.json",
            {
                "pin": baseline_pin,
                "env_fingerprint": t0_fingerprint,
                "gate_argv": T0_GATE_ARGV,
                "manifest_files": len(t0_manifest),
                "note": "identity half of the T0 baseline receipt; gate verdicts "
                "are receipted by the S2 T0 run under this key, not here",
            },
        )
        store = SQLiteSSTStore(run_dir / "store.db")
        wrapper = STCCustodyWrapper(
            CandidateCustodyManager(base_worktree_dir=run_dir / "custody"),
            self._substrate,
            leases_root=run_dir / "leases",
            baseline_manifest=t0_manifest,
            baseline_pin=baseline_pin,
            hmac_key=self._hmac_key,
        )
        capsule_compiler = ContextCapsuleCompiler(workspace_root=packet.source_repo_root)
        controller = SSTSearchController(
            task=packet,
            gateway=self._gateway,
            store=store,
            custody_manager=wrapper,  # type: ignore[arg-type]
            policy=self._policy,
            capsule_compiler=capsule_compiler,
        )
        search_wall_start = time.perf_counter()
        cap_exhausted = False
        try:
            champion = await controller.execute_search(tree_id)
        except SpendCapExceededError:
            # The STC spend ledger is invisible to the SST controller, which
            # catches ProviderGatewayError only: without this the run crashes
            # with no typed result and no result.json. Map to the honest
            # budget-exhausted early path below (partial evidence preserved).
            champion = None
            cap_exhausted = True
        search_wall_seconds = time.perf_counter() - search_wall_start
        events = store.get_events(tree_id)
        (run_dir / "events.json").write_text(
            json.dumps(
                [
                    {
                        "kind": str(evt.kind),
                        "node_id": evt.node_id,
                        "payload": evt.payload,
                    }
                    for evt in events
                ],
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )

        backend = getattr(self._gateway, "backend", None)
        provenance = getattr(backend, "critique_provenance", None)
        tainted = scrape_tainted_scores(events, provenance)
        verified = self._verified_nodes(events)
        scores = self._score_map(events)
        branch_refs = sorted(
            {
                evt.node_id
                for evt in events
                if evt.kind in (EventKind.NODE_PROPOSED, EventKind.SYNTHESIS_PROPOSED)
                and evt.node_id
            }
        )
        scores_summary = {node: score for node, (score, _, _) in scores.items()}
        budget_state = {
            "tokens_consumed": float(controller.budget_tracker.tokens_consumed),
            "estimated_cost_usd": float(controller.budget_tracker.estimated_cost_usd),
            # INFO-2: the controller stamps elapsed at the iteration TOP with
            # no final stamp, omitting the last iteration's work; the runner's
            # own wall around execute_search is authoritative for wall time.
            "elapsed_seconds": max(
                float(controller.budget_tracker.elapsed_seconds), search_wall_seconds
            ),
            "iterations_completed": float(controller.budget_tracker.iterations_completed),
        }
        veto_log: list[VetoRecord] = []
        final_id: str | None = None
        reselected = False
        final_proposal: CandidateProposal | None = None
        if champion is not None and champion.candidate_id in tainted:
            veto_log.append(tainted[champion.candidate_id])
            alternate = self._best_untainted(verified, scores, tainted)
            if alternate is not None:
                final_id = alternate
                reselected = True
                final_proposal = _proposal_from_events(alternate, tree_id, events)
                if final_proposal is None:
                    return self._early_no_champion(
                        run_dir,
                        tree_id,
                        run_id,
                        branch_refs,
                        scores_summary,
                        veto_log,
                        budget_state,
                        wrapper,
                        verified,
                        tainted,
                        "reselect-reconstruction-failed",
                        selected=alternate,
                    )
            else:
                return self._early_no_champion(
                    run_dir,
                    tree_id,
                    run_id,
                    branch_refs,
                    scores_summary,
                    veto_log,
                    budget_state,
                    wrapper,
                    verified,
                    tainted,
                    "champion-vetoed-no-alternative",
                )
        elif champion is not None:
            final_id = champion.candidate_id
            final_proposal = champion
        else:
            reason = (
                "budget-exhausted"
                if cap_exhausted or any(evt.kind == EventKind.BUDGET_EXHAUSTED for evt in events)
                else "no-verified-candidate"
            )
            return self._early_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                wrapper,
                verified,
                tainted,
                reason,
            )
        assert final_id is not None and final_proposal is not None

        synthesis_receipts = self._synthesis_receipts(tree_id, events, scores)
        loss_ledger = self._loss_ledger(tree_id, final_id, verified, scores)
        self._write_json(run_dir, "veto_log.json", [record.model_dump() for record in veto_log])
        self._write_json(
            run_dir,
            "synthesis.json",
            [receipt.model_dump() for receipt in synthesis_receipts],
        )
        self._write_json(run_dir, "loss_ledger.json", loss_ledger.model_dump())

        # T4 selection-outcome record (signed; embedded either way).
        outcome = _build_selection_outcome(
            tree_id,
            run_id,
            verified,
            scores_summary,
            tainted,
            selected=final_id,
            reason=None,
            per_node_refs={cid: record.digest() for cid, record in wrapper.selections.items()},
            key=self._hmac_key,
        )
        self._persist_per_node_records(run_dir, wrapper)
        save_record(run_dir / "selection_outcome.json", outcome)

        # T5 merge: a FRESH lease (never a reused per-node lease) with its
        # own scratch ref; nested E2E leases propagate THAT ref's exact SHA.
        merged_dir = run_dir / "merged"
        mirror_source_tree(Path(packet.source_repo_root), merged_dir)
        try:
            ensure_disposable_git(merged_dir)
        except LeaseGitError as exc:
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-git-setup-failed: {exc}",
            )
        merge_tripwire = LeaseTripwire("merged")
        try:
            merge_tripwire.manifest_open = hash_tree_manifest(merged_dir)
        except TripwireBreach as exc:
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-tripwire-open-failed: {exc}",
            )
        merge_drift = verify_baseline_manifest(packet.source_repo_root, t0_manifest)
        if merge_drift:
            self._quarantine_merge_copy(run_dir, merged_dir, "baseline drift at merge")
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-baseline-drifted: {merge_drift[0]} (re-pin T0)",
            )
        try:
            merge_base_sha = commit_tree(merged_dir, f"stc merge baseline ({final_id})")
        except LeaseGitError as exc:
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-baseline-commit-failed: {exc}",
            )
        app_result = wrapper.custody.apply_proposal(
            _with_restored_patch_newline(_with_recounted_patch_headers(final_proposal)),
            merged_dir,
            task=packet,
        )
        if not app_result.success:
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                "merge-apply-failed",
            )
        try:
            merge_tripwire.rebaseline_after_apply(merged_dir)
            merge_scratch_sha = commit_tree(merged_dir, f"stc merge scratch {final_id}")
            merge_scratch_ref = create_scratch_ref(merged_dir, final_id, merge_scratch_sha)
            checkout_ref(merged_dir, merge_scratch_ref)
            assert_head_equals(merged_dir, merge_scratch_sha)
        except (LeaseGitError, TripwireBreach) as exc:
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-scratch-setup-failed: {exc}",
            )
        try:
            merge_import_proof = prove_import_integrity(merged_dir)
        except LeaseGitError as exc:
            self._quarantine_merge_copy(run_dir, merged_dir, f"import-integrity: {exc}")
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-import-proof-failed: {exc}",
            )
        try:
            merge_tripwire.check_pre_gates(merged_dir)
        except TripwireBreach as exc:
            self._quarantine_merge_copy(run_dir, merged_dir, f"tripwire: {exc}")
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-tripwire-breach: {exc}",
            )
        try:
            merge_fingerprint = check_floor()
        except FloorViolationError as exc:
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-floor-violation: {exc}",
            )
        merge_env_digest = env_digest_of(merge_fingerprint)
        if not env_requalifies(t0_fingerprint, merge_fingerprint):
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                "merge-env-unrequalified (compare would bind unbindable verdicts)",
            )
        try:
            binding_bytes = render_binding_diff(merged_dir, merge_base_sha, merge_scratch_sha)
            bundle_path = write_scratch_bundle(
                merged_dir, merge_scratch_ref, run_dir / "scratch.bundle"
            )
        except DiffBindingError as exc:
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-binding-failed: {exc}",
            )
        self._write_json(
            run_dir,
            "merge_env.json",
            {
                "env_fingerprint": merge_fingerprint,
                "env_digest": merge_env_digest,
                "import_proof": merge_import_proof,
                "merge_base_sha": merge_base_sha,
                "merge_scratch_sha": merge_scratch_sha,
                "merge_scratch_ref": merge_scratch_ref,
                "bundle": str(bundle_path.name),
            },
        )
        # Binding bytes (section 5.6 base/result/policy) are stored
        # separately from the judiciary scan text: merged.diff keeps the
        # proposal-rendered text (test-pinned), binding.diff carries the
        # exact policy bytes the live/bundle checks verify against.
        (run_dir / "binding.diff").write_bytes(binding_bytes)
        # R3: trusted mutation scope from the bound scratch file list.
        # External targets scope to their own production files (never
        # STC's src/stc/); the merge mirror pre-seeds accordingly.
        merge_external = is_external_target_root(packet.source_repo_root)
        mutation_paths = derive_mutation_paths(binding_bytes, target_root=packet.source_repo_root)
        merged_diff = render_merged_diff(final_proposal)
        (run_dir / "merged.diff").write_text(merged_diff, encoding="utf-8")

        # T5 RECEIPT — post-merge receipt: mutmut runs here, exactly once
        # per merge evaluation (each retry is its own merge evaluation with
        # its own receipt — E3 already qualifies, no change). pytest_target
        # is FORBIDDEN here so the safeguard set stays whole-tree + mutmut
        # by construction (the runner.py trap is additionally irrelevant:
        # the explicit run_mutmut bool below takes precedence — E1).
        # Reversion watch (Delta A1): if scoped per-node selection is shown
        # to let mock-gaming suites reach champion routinely, the ADR-INT-01
        # reversion condition triggers.
        post_receipt = self._substrate.execute_gates(
            merged_dir,
            task_id=packet.task_id,
            epoch_index=packet_bundle.epoch_index,
            causation_id=tree_id,
            run_mutmut=self._champion_mutmut,
            paths_to_mutate=mutation_paths,
            external_target=merge_external,
        )
        (run_dir / "post_merge_receipt.json").write_text(
            post_receipt.model_dump_json(indent=2), encoding="utf-8"
        )
        mutmut_count = count_mutmut_runs(post_receipt)
        if mutmut_count == 1:
            disposition = _measured_disposition(post_receipt) or "counted-once"
        else:
            disposition = _mutmut_disposition(self._champion_mutmut, post_receipt)
        # Post-gates close: the merge lease must be byte-stable across
        # gate execution (detection-with-fail-closed).
        try:
            assert_head_equals(merged_dir, merge_scratch_sha)
            merge_tripwire.check_close(merged_dir)
        except (LeaseGitError, TripwireBreach) as exc:
            self._quarantine_merge_copy(run_dir, merged_dir, f"close: {exc}")
            return self._merge_no_champion(
                run_dir,
                tree_id,
                run_id,
                branch_refs,
                scores_summary,
                veto_log,
                budget_state,
                outcome,
                wrapper,
                f"merge-close-failed: {exc}",
            )
        verdict = self._audit(
            merged_diff,
            packet_bundle,
            post_receipt,
            merged_dir=merged_dir,
            base_sha=merge_base_sha,
            scratch_sha=merge_scratch_sha,
            binding_bytes=binding_bytes,
        )
        first_verdict: JudiciaryVerdict | None = None
        retry_receipts: list[ExecutionReceipt] = []
        retry_counts: list[int] = []
        if verdict.status == "REJECTED":
            # E1 production call site (merge retry): explicit run_mutmut
            # bool — same precedence as the post-merge site above. Each
            # retry is its own merge evaluation with its own receipt (E3).
            retry_receipt = self._substrate.execute_gates(
                merged_dir,
                task_id=packet.task_id,
                epoch_index=packet_bundle.epoch_index,
                causation_id=tree_id,
                run_mutmut=self._champion_mutmut,
                paths_to_mutate=mutation_paths,
            )
            (run_dir / "retry_receipt.json").write_text(
                retry_receipt.model_dump_json(indent=2), encoding="utf-8"
            )
            retry_receipts.append(retry_receipt)
            retry_counts.append(count_mutmut_runs(retry_receipt))
            first_verdict = verdict
            verdict = self._audit(
                merged_diff,
                packet_bundle,
                retry_receipt,
                merged_dir=merged_dir,
                base_sha=merge_base_sha,
                scratch_sha=merge_scratch_sha,
                binding_bytes=binding_bytes,
            )
        # T5/T6 linked merge record (pins exactly the four fields) +
        # dossier digest list over all four records.
        merge_record = MergeRecord(
            merge_scratch_ref=merge_scratch_ref,
            selection_outcome_ref=outcome.digest(),
            env_digest=merge_env_digest,
            # sha256 over the binding.diff bytes (section 5.6 render).
            merged_diff_sha256=hashlib.sha256(binding_bytes).hexdigest(),
        ).signed(self._hmac_key)
        save_record(run_dir / "merge_record.json", merge_record)
        digests, dossier_sig = self._write_dossier_digests(run_dir, wrapper, outcome, merge_record)
        result = ChampionResult(
            tree_id=tree_id,
            run_id=run_id,
            champion_id=final_id,
            reselected=reselected,
            merged_diff=merged_diff,
            post_merge_receipt=post_receipt,
            retry_receipts=retry_receipts,
            mutmut_count=mutmut_count,
            retry_mutmut_counts=retry_counts,
            mutmut_disposition=disposition,
            synthesis_receipts=synthesis_receipts,
            loss_ledger=loss_ledger,
            judiciary_verdict=verdict,
            first_verdict=first_verdict,
            veto_log=veto_log,
            scores_summary=scores_summary,
            evidence_dir=str(run_dir),
            linked_record_digests=digests,
            dossier_signature=dossier_sig,
        )
        (run_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    def _inject_inhibitors(self, bundle: TaskBundle) -> tuple[TaskBundle, list[str], list[str]]:
        """BT-11b: injects memory inhibitors into membrane_protocols (BT-11a)."""
        if self._memory is None:
            return bundle, [], []
        queries: list[str] = []
        for target in bundle.target_files:
            stem = Path(target.path).stem.strip()
            if stem and stem not in queries:
                queries.append(stem)
        if bundle.spec_id.strip() and bundle.spec_id.strip() not in queries:
            queries.append(bundle.spec_id.strip())
        seen: set[str] = set()
        hits: list[str] = []
        for query in queries:
            for hit in self._memory.query_negative_inhibitors(query):
                if hit not in seen:
                    seen.add(hit)
                    hits.append(hit)
                if len(hits) >= MAX_INJECTED_INHIBITORS:
                    break
            if len(hits) >= MAX_INJECTED_INHIBITORS:
                break
        existing = list(bundle.membrane_protocols)
        added = [
            f"{INHIBITOR_PREFIX}{hit}" for hit in hits if f"{INHIBITOR_PREFIX}{hit}" not in existing
        ]
        if not added:
            return bundle, [], queries
        return (
            bundle.model_copy(update={"membrane_protocols": existing + added}),
            added,
            queries,
        )

    def _audit(
        self,
        merged_diff: str,
        bundle: TaskBundle,
        receipt: ExecutionReceipt,
        *,
        merged_dir: Path,
        base_sha: str,
        scratch_sha: str,
        binding_bytes: bytes,
    ) -> JudiciaryVerdict:
        """Audits the merged champion; with_codex=False asserted (RT-08).

        T6 live-against-rendered: the auditor recomputes the frozen-policy
        diff from the LIVE merge lease (same shared ``normalize_diff()``
        as the render) and compares against the rendered binding bytes.
        Mismatch fails closed either way (live now, bundle later). The
        ``merged_diff`` proposal text is the judiciary scan input.
        """
        if self._auditor.with_codex:
            raise DialecticError("auditor with_codex must be False (RT-08).")
        try:
            recomputed = render_binding_diff(merged_dir, base_sha, scratch_sha)
        except DiffBindingError as exc:
            raise DialecticError(f"audit live recompute failed: {exc}") from exc
        if normalize_diff(recomputed.decode("utf-8", errors="replace")) != normalize_diff(
            binding_bytes.decode("utf-8", errors="replace")
        ):
            raise DialecticError(
                "audit live-against-rendered mismatch: the merge lease bytes "
                "no longer render the receipted binding diff (fail-closed)"
            )
        return self._auditor.audit_diff(merged_diff, bundle, receipt)

    @staticmethod
    def _verified_nodes(events: list[SSTEvent]) -> set[str]:
        return {
            evt.node_id
            for evt in events
            if evt.kind == EventKind.VERIFIER_FINISHED
            and evt.node_id
            and evt.payload.get("passed") is True
        }

    @staticmethod
    def _score_map(
        events: list[SSTEvent],
    ) -> dict[str, tuple[float, str | None, str]]:
        scores: dict[str, tuple[float, str | None, str]] = {}
        for evt in events:
            if evt.kind != EventKind.SCORE_RECORDED or not evt.node_id:
                continue
            try:
                value = float(evt.payload.get("value_score", 0.0))
            except (TypeError, ValueError):
                continue
            verdict = evt.payload.get("verdict")
            scores[evt.node_id] = (
                value,
                str(verdict) if verdict is not None else None,
                str(evt.payload.get("critique", "")),
            )
        return scores

    @staticmethod
    def _best_untainted(
        verified: set[str],
        scores: dict[str, tuple[float, str | None, str]],
        tainted: dict[str, VetoRecord],
    ) -> str | None:
        """Best verified, untainted, non-escalated node (controller mirrors)."""
        candidates = [
            (score, node)
            for node, (score, verdict, _) in scores.items()
            if node in verified and node not in tainted and verdict != "ESCALATE_HUMAN"
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][1]

    @staticmethod
    def _synthesis_receipts(
        tree_id: str,
        events: list[SSTEvent],
        scores: dict[str, tuple[float, str | None, str]],
    ) -> list[SynthesisReceipt]:
        receipts: list[SynthesisReceipt] = []
        for evt in events:
            if evt.kind != EventKind.SYNTHESIS_PROPOSED or not evt.node_id:
                continue
            node_id = evt.node_id
            parents = [str(p) for p in evt.payload.get("parent_ids", [])]
            verification = next(
                (
                    item
                    for item in events
                    if item.kind == EventKind.VERIFIER_FINISHED and item.node_id == node_id
                ),
                None,
            )
            if verification is None:
                raise DialecticError(f"synthesis {node_id} has no VERIFIER_FINISHED event.")
            receipts.append(
                SynthesisReceipt(
                    synthesis_id=f"synth-{node_id}",
                    tree_id=tree_id,
                    parent_ids=parents,
                    parent_scores={
                        parent: scores.get(parent, (0.0, None, ""))[0] for parent in parents
                    },
                    synth_candidate_id=node_id,
                    synth_score=scores.get(node_id, (0.0, None, ""))[0],
                    verification_passed=verification.payload.get("passed") is True,
                    verification_exit_code=int(verification.payload.get("exit_code", 1)),
                    verification_duration_s=float(
                        verification.payload.get("duration_seconds", 0.0)
                    ),
                )
            )
        receipts.sort(key=lambda receipt: receipt.synthesis_id)
        return receipts

    @staticmethod
    def _loss_ledger(
        tree_id: str,
        final_id: str,
        verified: set[str],
        scores: dict[str, tuple[float, str | None, str]],
    ) -> LossLedger:
        entries = [
            LossLedgerEntry(
                candidate_id=node,
                tree_id=tree_id,
                normalized_reward=score,
                critic_verdict=verdict,
                reason="below-synthesis-threshold",
            )
            for node, (score, verdict, _) in scores.items()
            if node != final_id and node in verified and score < SYNTHESIS_THRESHOLD
        ]
        entries.sort(key=lambda entry: entry.candidate_id)
        return LossLedger(tree_id=tree_id, entries=entries)

    def _persist_per_node_records(self, run_dir: Path, wrapper: STCCustodyWrapper) -> None:
        """Persists per-candidate linked records + evidence into the run dir."""
        for cid in sorted(wrapper.intakes):
            safe = sanitize_lease_segment(cid)
            save_record(run_dir / f"custody_{safe}.json", wrapper.intakes[cid])
        for cid in sorted(wrapper.selections):
            safe = sanitize_lease_segment(cid)
            save_record(run_dir / f"selection_{safe}.json", wrapper.selections[cid])
        for cid in sorted(wrapper.env_fingerprints):
            safe = sanitize_lease_segment(cid)
            self._write_json(
                run_dir,
                f"env_{safe}.json",
                {
                    "env_fingerprint": wrapper.env_fingerprints[cid],
                    "import_proof": wrapper.import_proofs.get(cid, {}),
                },
            )
        for cid in sorted(wrapper.binding_diffs):
            safe = sanitize_lease_segment(cid)
            (run_dir / f"binding_{safe}.diff").write_bytes(wrapper.binding_diffs[cid])

    def _write_dossier_digests(
        self,
        run_dir: Path,
        wrapper: STCCustodyWrapper,
        outcome: SelectionOutcomeRecord,
        merge: MergeRecord | None,
    ) -> tuple[dict[str, str], str]:
        """Writes the HMAC'd dossier digest list; returns (digests, sig)."""
        digests = dossier_digest_list(
            {cid: record.digest() for cid, record in wrapper.intakes.items()},
            {cid: record.digest() for cid, record in wrapper.selections.items()},
            outcome.digest(),
            merge.digest() if merge is not None else None,
        )
        sig = dossier_signature(digests, self._hmac_key)
        self._write_json(
            run_dir, "dossier_digests.json", {"digests": digests, "dossier_signature": sig}
        )
        return digests, sig

    def _quarantine_merge_copy(self, run_dir: Path, merged_dir: Path, reason: str) -> None:
        """Preserves a COPY of the failed merge lease under run _quarantine."""
        dest_root = run_dir / "_quarantine"
        dest_root.mkdir(parents=True, exist_ok=True)
        dest = dest_root / f"merged__{uuid.uuid4().hex[:6]}"
        if merged_dir.is_dir():
            shutil.copytree(merged_dir, dest, symlinks=True)
            (dest / "quarantine_reason.txt").write_text(reason[:2000], encoding="utf-8")

    def _early_no_champion(
        self,
        run_dir: Path,
        tree_id: str,
        run_id: str,
        branch_refs: list[str],
        scores_summary: dict[str, float],
        veto_log: list[VetoRecord],
        budget_state: dict[str, float],
        wrapper: STCCustodyWrapper,
        verified: set[str],
        tainted: dict[str, VetoRecord],
        reason: str,
        *,
        selected: str | None = None,
    ) -> NoChampionResult:
        """No-champion before merge: build + persist outcome, then finish."""
        outcome = _build_selection_outcome(
            tree_id,
            run_id,
            verified,
            scores_summary,
            tainted,
            selected=selected,
            reason=None if selected is not None else reason,
            per_node_refs={cid: record.digest() for cid, record in wrapper.selections.items()},
            key=self._hmac_key,
        )
        self._persist_per_node_records(run_dir, wrapper)
        save_record(run_dir / "selection_outcome.json", outcome)
        digests, sig = self._write_dossier_digests(run_dir, wrapper, outcome, None)
        return self._no_champion(
            run_dir,
            tree_id,
            run_id,
            branch_refs,
            scores_summary,
            veto_log,
            budget_state,
            reason,
            linked_record_digests=digests,
            dossier_sig=sig,
        )

    def _merge_no_champion(
        self,
        run_dir: Path,
        tree_id: str,
        run_id: str,
        branch_refs: list[str],
        scores_summary: dict[str, float],
        veto_log: list[VetoRecord],
        budget_state: dict[str, float],
        outcome: SelectionOutcomeRecord,
        wrapper: STCCustodyWrapper,
        reason: str,
    ) -> NoChampionResult:
        """No-champion after selection: outcome already persisted; add digests."""
        digests, sig = self._write_dossier_digests(run_dir, wrapper, outcome, None)
        return self._no_champion(
            run_dir,
            tree_id,
            run_id,
            branch_refs,
            scores_summary,
            veto_log,
            budget_state,
            reason,
            linked_record_digests=digests,
            dossier_sig=sig,
        )

    def _no_champion(
        self,
        run_dir: Path,
        tree_id: str,
        run_id: str,
        branch_refs: list[str],
        scores_summary: dict[str, float],
        veto_log: list[VetoRecord],
        budget_state: dict[str, float],
        reason: str,
        *,
        linked_record_digests: dict[str, str] | None = None,
        dossier_sig: str = "",
    ) -> NoChampionResult:
        self._write_json(run_dir, "veto_log.json", [record.model_dump() for record in veto_log])
        # Merge-path failures arrive after real synthesis/loss evidence was
        # written: defaults fill absences only, never clobber evidence.
        if not (run_dir / "synthesis.json").exists():
            self._write_json(run_dir, "synthesis.json", [])
        if not (run_dir / "loss_ledger.json").exists():
            self._write_json(run_dir, "loss_ledger.json", LossLedger(tree_id=tree_id).model_dump())
        result = NoChampionResult(
            tree_id=tree_id,
            run_id=run_id,
            branch_refs=branch_refs,
            scores_summary=scores_summary,
            veto_log=veto_log,
            budget_state=budget_state,
            reason=reason,
            evidence_dir=str(run_dir),
            linked_record_digests=dict(linked_record_digests or {}),
            dossier_signature=dossier_sig,
        )
        (run_dir / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    @staticmethod
    def _write_json(run_dir: Path, name: str, payload: Any) -> None:
        (run_dir / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
