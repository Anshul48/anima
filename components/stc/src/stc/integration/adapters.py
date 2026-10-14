"""STC<->SST contract bridge: projection, reward, file targeting (P01).

The disposition tables below are the spec (F1c): every field of both
schemas is disposed as mapped / ctx-recovered / declared-dropped, and the
adapters raise a typed error naming the field ONLY on undisposed input.
By-design drops never raise; run-binding mismatches raise
:class:`RunBindingError`; unknown content raises
:class:`UndisposedFieldError`.

Table 1 -- TaskBundle -> TaskPacket (forward). Every Bundle field::

    task_id            -> packet.task_id (verbatim)
    epoch_index        -> ctx-corroborated (== ctx.epoch_index) + evidence
                          stc.epoch_index
    spec_id            -> ctx-corroborated (== ctx.spec_id) + evidence
                          stc.spec_id
    goal_statement     -> packet.goal (verbatim)
    invariants         -> packet.invariants, "bundle:"-tagged + escaped
    target_files       -> packet.allowed_paths (paths only) + loss note
                          stc.target_files.loss (action/symbols/offsets are
                          not representable in allowed_paths)
    membrane_protocols -> packet.invariants, "membrane:"-tagged + escaped
    negative_inhibitors -> evidence stc.negative_inhibitors (JSON list)
    correlation_id     -> DECLARED-DROPPED: run-scoped trace identity that
                          must not cross the membrane; the inverse
                          regenerates it fresh (F1a)
    causation_id       -> evidence stc.causation_id when present; absent
                          stays absent (inverse reads None)
    compiled_at        -> DECLARED-DROPPED: bundle birth is not packet
                          birth; packet.created_at is fresh, and the
                          inverse regenerates compiled_at (F1a)

Table 1b -- TaskPacket fields filled forward (all 16)::

    task_id / goal               <- bundle.task_id / bundle.goal_statement
    source_repo_root/base_commit <- ctx (verbatim)
    snapshot_hash                <- candidate_identity(ctx.source_repo_root),
                                    computed live (F3d)
    allowed_paths                <- bundle.target_files paths
    forbidden_paths              <- [] (M1: AdapterContext defines no
                                    denylist; enforcement happens at P04
                                    lease allocation, F1d)
    invariants                   <- merged tagged bundle+membrane lists;
                                    escaping: "\\\\" -> "\\\\\\\\", then
                                    ":" -> "\\\\:"; split on first ":"
    interfaces                   <- [] (M1: STC has no interfaces channel;
                                    protocols ride as tagged invariants)
    acceptance_commands          <- ctx (validated non-empty, F2d)
    evidence_references          <- stc.* keys (4 required + causation iff
                                    present)
    time/token/cost budgets      <- ctx.budgets
    prompt_template_hash         <- ctx.adapter_version VERBATIM (a version
                                    label, not a hash, in M1; F3d)
    created_at                   <- now (packet birth)

Table 2 -- TaskPacket -> TaskBundle (inverse). Every Packet field::

    task_id / goal  -> bundle.task_id / bundle.goal_statement (a blank
                       goal fails Bundle validation; pydantic's
                       ValidationError propagates as the typed signal)
    source_repo_root/base_commit/acceptance_commands -> corroborated
                       against ctx (mismatch -> RunBindingError naming
                       the field; binds the packet to this run)
    prompt_template_hash -> corroborated == ctx.adapter_version
                       (binds the packet to this adapter version)
    snapshot_hash    -> DECLARED-DROPPED: point-in-time witness; the tree
                       legitimately advances between forward (compile
                       time) and inverse (audit time), so it is not
                       re-verified here
    allowed_paths    -> target_files as FileTarget(path) defaults
                       (modify, no symbols/offsets -- the documented
                       Table-1 loss, not silent)
    forbidden_paths  -> DECLARED-DROPPED: lease authority stays with the
                       packet at P04; the bundle never had a denylist
                       field (F1d)
    invariants       -> split by tag back into invariants +
                       membrane_protocols (unknown tag or malformed
                       escape -> UndisposedFieldError naming the index)
    interfaces       -> DECLARED-DROPPED: no STC channel in M1;
                       interfaces live packet-side only
    evidence_references -> epoch/spec/inhibitors/causation recovered;
                       unknown key -> UndisposedFieldError; missing
                       required key or malformed value -> same
    time/token/cost budgets -> DECLARED-DROPPED (run envelope; the bundle
                       has no budget fields)
    created_at       -> DECLARED-DROPPED (packet birth is not bundle
                       birth; compiled_at regenerates, F1a)
    + correlation_id/compiled_at regenerate fresh via Bundle defaults
      (ctx-recovered, NOT round-tripped, F1a); output is ceiling-checked
      against MAX_BUNDLE_BYTES (STC native BundleSizeExceededError).

Table 3 -- ExecutionReceipt -> ScoreBreakdown. Receipt fields::

    gate_ruff/gate_mypy/gate_pytest -> stc_ruff/stc_mypy/stc_pytest keys
                       (exit_code == 0) + verifier_passed conjunction;
                       failed-gate first-error signals ride
                       raw_metrics["first_signals"] for the prune hint
    gate_mutmut      -> mutmut_status in raw_metrics only
                       ("deferred" | "passed" | "failed"); the mutmut key
                       is ALWAYS absent per-node (F2a, ADR-INT-01)
    receipt_id/task_id/epoch_index/commit_hash/timestamp_utc/
    python_version/os_platform -> DECLARED-DROPPED (provenance, not score
                       signal)
    sha256_signature -> DECLARED-DROPPED (tamper-evidence is verified by
                       the substrate's verify_receipt BEFORE scoring;
                       scoring assumes a verified receipt)
    correlation_id/causation_id -> DECLARED-DROPPED (trace, not score)

Table 3b -- ScoreBreakdown fields filled (all 8)::

    passed_hard_gates <- all(hard_gates.values())
    hard_gates        <- exactly {"verifier_passed", "stc_ruff",
                         "stc_mypy", "stc_pytest"} (native key + stc_*
                         extensions, F2c); mutmut absent, always
    soft_scores       <- {} (M1: no soft signals; coarse deterministic
                         reward only)
    normalized_reward <- passed_hard_gates_count /
                         evaluated_gates_count over the 4 emitted keys,
                         mutmut excluded (F2b/BT-14); achievable values
                         are exactly {0.0, 0.25, 0.5, 1.0}, monotonic
                         non-decreasing in sub-gate passes
    raw_metrics       <- {"mutmut_status", "ruff_duration_s",
                         "mypy_duration_s", "pytest_duration_s",
                         "first_signals"}
    critic_verdict    <- None (leaves the search default; the P04 runner
                         vetoes on garbage critique -- champion-veto)
    critic_rationale  <- None
    evaluated_at      <- now

Table 4 -- CandidateProposal -> list[FileTarget]. Proposal fields::

    patch_diff       -> PRIMARY: "---"/"+++" file-header pairs yield
                       (path, action); create iff old is /dev/null,
                       delete iff new is /dev/null, else modify.
                       Unquoted paths only; a "+++" without its "---",
                       an empty path, or a quoted path raises
                       UndisposedFieldError naming patch_diff.
    file_operations  -> each op-dict needs "op" in
                       {create, modify, delete} + a non-blank "path";
                       anything else raises naming the index (F1e).
                       Extra keys are ignored (documented).
                       With hunks present, every op must reference a
                       hunk path with the SAME action (containment +
                       agreement; conflict raises). With no hunks, ops
                       are the sole source. Same path + same action
                       dedupes; same path + different actions raises.
    target_paths     -> one-way containment: every derived path must be
                       declared (breach raises, fail-closed on scope);
                       declared-but-untouched paths are allowed.
    candidate_id/tree_id/parent_ids/role/title/rationale/model_id/
    prompt_hash/metadata/created_at -> DECLARED-DROPPED (proposal
                       identity/provenance, not file targeting)

Table 4b -- FileTarget fields filled::

    path/action      <- diff headers / op-dicts (above)
    expected_symbols <- [] (not expressible in a unified diff)
    start/end_line, start/end_byte <- None (deliberate: "@@" ranges are
                       not mapped because multi-hunk spans do not fit
                       FileTarget's single span; P04 custody applies the
                       full patch text -- our targets are lease scope,
                       not an edit script)

Deferred-mutmut fingerprint (F2a): a GateReport counts as DEFERRED iff
exit_code == 0 AND duration_seconds == 0.0 AND raw_output_snippet starts
with "DEFERRED:". The P04 substrate must emit exactly that shape (exit 0,
zero duration, "DEFERRED: <reason>") for per-node mutmut placeholders.
Runner-disclosed non-measurements (the disabled-gate, win32-deferral, and
active-mutation-guard snippets) count as DEFERRED on marker match alone.

Compatibility: frozen in/out schemas; inputs are never mutated;
ValueError-family typed errors only, raised solely per F1c.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from sst.core.contracts import CandidateProposal, ScoreBreakdown, TaskPacket

from stc.compiler.bundler import MAX_BUNDLE_BYTES
from stc.core.errors import BundleSizeExceededError
from stc.integration.identity import IntegrationError, candidate_identity
from stc.schemas.models import ExecutionReceipt, FileTarget, GateReport, TaskBundle

__all__ = [
    "DEFERRED_SNIPPET_PREFIX",
    "EVIDENCE_CAUSATION",
    "EVIDENCE_EPOCH",
    "EVIDENCE_INHIBITORS",
    "EVIDENCE_SPEC",
    "EVIDENCE_TARGET_LOSS",
    "HARD_GATE_KEYS",
    "KNOWN_OPS",
    "REQUIRED_EVIDENCE_KEYS",
    "TAG_BUNDLE",
    "TAG_MEMBRANE",
    "AdapterContext",
    "Budgets",
    "RunBindingError",
    "UndisposedFieldError",
    "proposal_to_filetargets",
    "receipt_to_score",
    "task_bundle_to_packet",
    "task_packet_to_bundle",
]


class UndisposedFieldError(IntegrationError):
    """Input carries content the disposition table does not dispose.

    The message always names the field (and index/key where applicable).
    Raised for unknown evidence keys, missing required evidence, untagged
    or malformed merged invariants, unknown op-dicts, malformed diffs,
    and scope breaches. Never raised for by-design drops.
    """


class RunBindingError(IntegrationError):
    """A disposed field fails corroboration against the AdapterContext.

    The message names the field and shows both sides. Raised when a
    bundle/packet does not belong to the run the context describes.
    """


#: Exact hard-gate vocabulary, in emission order (F2c). The mutmut key is
#: absent by construction -- there is deliberately no constant for it.
HARD_GATE_KEYS: Final[tuple[str, ...]] = (
    "verifier_passed",
    "stc_ruff",
    "stc_mypy",
    "stc_pytest",
)

#: Deferred-mutmut snippet class: the snippet must start with this (F2a).
DEFERRED_SNIPPET_PREFIX: Final[str] = "DEFERRED:"

#: Evidence-reference keys written forward, required back on inverse.
EVIDENCE_EPOCH: Final[str] = "stc.epoch_index"
EVIDENCE_SPEC: Final[str] = "stc.spec_id"
EVIDENCE_INHIBITORS: Final[str] = "stc.negative_inhibitors"
EVIDENCE_TARGET_LOSS: Final[str] = "stc.target_files.loss"
#: Optional evidence key: present iff the bundle carries a causation id.
EVIDENCE_CAUSATION: Final[str] = "stc.causation_id"

REQUIRED_EVIDENCE_KEYS: Final[frozenset[str]] = frozenset(
    {EVIDENCE_EPOCH, EVIDENCE_SPEC, EVIDENCE_INHIBITORS, EVIDENCE_TARGET_LOSS}
)

_KNOWN_EVIDENCE_KEYS: Final[frozenset[str]] = REQUIRED_EVIDENCE_KEYS | {EVIDENCE_CAUSATION}

#: Merge tags for packet.invariants (F1d). Tags contain no ":" or "\\",
#: so splitting an item on the FIRST ":" is unambiguous.
TAG_BUNDLE: Final[str] = "bundle"
TAG_MEMBRANE: Final[str] = "membrane"

#: Known file-operation names (F1e). Rename/move/copy are NOT known: the
#: M1 contract expresses them as delete+create pairs.
KNOWN_OPS: Final[frozenset[str]] = frozenset({"create", "modify", "delete"})


@dataclass(frozen=True)
class Budgets:
    """Run envelope budgets carried by the context into the packet."""

    time_budget_seconds: int
    token_budget: int | None = None
    cost_budget_usd: float | None = None

    def __post_init__(self) -> None:
        if self.time_budget_seconds <= 0:
            raise ValueError("time_budget_seconds must be positive")
        if self.token_budget is not None and self.token_budget < 0:
            raise ValueError("token_budget must be non-negative")
        if self.cost_budget_usd is not None and self.cost_budget_usd < 0:
            raise ValueError("cost_budget_usd must be non-negative")


@dataclass(frozen=True)
class AdapterContext:
    """Typed run context for every membrane crossing (F2d: no untyped ctx)."""

    epoch_index: int
    spec_id: str
    budgets: Budgets
    acceptance_commands: tuple[str, ...]
    source_repo_root: str
    base_commit: str
    adapter_version: str

    def __post_init__(self) -> None:
        if not 1 <= self.epoch_index <= 3:
            raise ValueError("epoch_index must match the bundle domain 1..3")
        for field_name in ("spec_id", "source_repo_root", "base_commit", "adapter_version"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-blank")
        commands = tuple(self.acceptance_commands)
        if not commands:
            raise ValueError("acceptance_commands must be non-empty")
        if any(not cmd.strip() for cmd in commands):
            raise ValueError("acceptance_commands entries must be non-blank")
        object.__setattr__(self, "acceptance_commands", commands)


def _escape_invariant(payload: str) -> str:
    return payload.replace("\\", "\\\\").replace(":", "\\:")


def _split_tagged(item: str, index: int) -> tuple[str, str]:
    """Splits one merged invariant into (tag, payload), strictly."""
    tag, sep, escaped = item.partition(":")
    if not sep or tag not in (TAG_BUNDLE, TAG_MEMBRANE):
        raise UndisposedFieldError(f"invariants[{index}]: untagged item {item!r}")
    chars: list[str] = []
    i = 0
    while i < len(escaped):
        char = escaped[i]
        if char == "\\":
            if i + 1 >= len(escaped) or escaped[i + 1] not in ("\\", ":"):
                raise UndisposedFieldError(f"invariants[{index}]: bad escape in {item!r}")
            chars.append(escaped[i + 1])
            i += 2
        else:
            chars.append(char)
            i += 1
    return tag, "".join(chars)


def task_bundle_to_packet(bundle: TaskBundle, ctx: AdapterContext) -> TaskPacket:
    """Projects a TaskBundle across the membrane into an SST TaskPacket."""
    if bundle.epoch_index != ctx.epoch_index:
        raise RunBindingError(f"epoch_index: bundle={bundle.epoch_index} ctx={ctx.epoch_index}")
    if bundle.spec_id != ctx.spec_id:
        raise RunBindingError(f"spec_id: bundle={bundle.spec_id!r} ctx={ctx.spec_id!r}")
    evidence: dict[str, str] = {
        EVIDENCE_EPOCH: str(bundle.epoch_index),
        EVIDENCE_SPEC: bundle.spec_id,
        EVIDENCE_INHIBITORS: json.dumps(list(bundle.negative_inhibitors)),
        EVIDENCE_TARGET_LOSS: (
            f"{len(bundle.target_files)} target(s); per-file action, "
            "expected_symbols, and line/byte offsets are not representable "
            "in allowed_paths (paths only)"
        ),
    }
    if bundle.causation_id is not None:
        evidence[EVIDENCE_CAUSATION] = bundle.causation_id
    return TaskPacket(
        task_id=bundle.task_id,
        goal=bundle.goal_statement,
        source_repo_root=ctx.source_repo_root,
        base_commit=ctx.base_commit,
        snapshot_hash=candidate_identity(ctx.source_repo_root),
        allowed_paths=[target.path for target in bundle.target_files],
        forbidden_paths=[],
        invariants=[f"{TAG_BUNDLE}:{_escape_invariant(s)}" for s in bundle.invariants]
        + [f"{TAG_MEMBRANE}:{_escape_invariant(s)}" for s in bundle.membrane_protocols],
        interfaces=[],
        acceptance_commands=list(ctx.acceptance_commands),
        evidence_references=evidence,
        time_budget_seconds=ctx.budgets.time_budget_seconds,
        token_budget=ctx.budgets.token_budget,
        cost_budget_usd=ctx.budgets.cost_budget_usd,
        prompt_template_hash=ctx.adapter_version,
        created_at=datetime.now(UTC),
    )


def _check_binding(field: str, packet_value: object, ctx_value: object) -> None:
    if packet_value != ctx_value:
        raise RunBindingError(f"{field}: packet={packet_value!r} ctx={ctx_value!r}")


def _recover_evidence(packet: TaskPacket) -> tuple[int, str, list[str], str | None]:
    """Recovers epoch/spec/inhibitors/causation from evidence references."""
    for key in packet.evidence_references:
        if key not in _KNOWN_EVIDENCE_KEYS:
            raise UndisposedFieldError(f"evidence_references[{key!r}]: unknown key")
    for key in sorted(REQUIRED_EVIDENCE_KEYS):
        if key not in packet.evidence_references:
            raise UndisposedFieldError(f"evidence_references[{key!r}]: missing required key")
    try:
        epoch = int(packet.evidence_references[EVIDENCE_EPOCH])
    except ValueError as exc:
        raise UndisposedFieldError(f"evidence_references[{EVIDENCE_EPOCH!r}]: not an int") from exc
    try:
        inhibitors: Any = json.loads(packet.evidence_references[EVIDENCE_INHIBITORS])
    except json.JSONDecodeError as exc:
        raise UndisposedFieldError(
            f"evidence_references[{EVIDENCE_INHIBITORS!r}]: not JSON"
        ) from exc
    if not isinstance(inhibitors, list) or any(not isinstance(item, str) for item in inhibitors):
        raise UndisposedFieldError(
            f"evidence_references[{EVIDENCE_INHIBITORS!r}]: not a string list"
        )
    return (
        epoch,
        packet.evidence_references[EVIDENCE_SPEC],
        list(inhibitors),
        packet.evidence_references.get(EVIDENCE_CAUSATION),
    )


def task_packet_to_bundle(packet: TaskPacket, ctx: AdapterContext) -> TaskBundle:
    """Reconstructs a TaskBundle from a packet under the run context."""
    _check_binding("source_repo_root", packet.source_repo_root, ctx.source_repo_root)
    _check_binding("base_commit", packet.base_commit, ctx.base_commit)
    _check_binding("acceptance_commands", packet.acceptance_commands, list(ctx.acceptance_commands))
    _check_binding("prompt_template_hash", packet.prompt_template_hash, ctx.adapter_version)
    epoch, spec_id, inhibitors, causation_id = _recover_evidence(packet)
    _check_binding("evidence stc.epoch_index", epoch, ctx.epoch_index)
    _check_binding("evidence stc.spec_id", spec_id, ctx.spec_id)
    invariants: list[str] = []
    membrane_protocols: list[str] = []
    for index, item in enumerate(packet.invariants):
        tag, payload = _split_tagged(item, index)
        if tag == TAG_BUNDLE:
            invariants.append(payload)
        else:
            membrane_protocols.append(payload)
    bundle = TaskBundle(
        task_id=packet.task_id,
        epoch_index=epoch,
        spec_id=spec_id,
        goal_statement=packet.goal,
        invariants=invariants,
        target_files=[FileTarget(path=path) for path in packet.allowed_paths],
        membrane_protocols=membrane_protocols,
        negative_inhibitors=inhibitors,
        causation_id=causation_id,
    )
    size = len(bundle.model_dump_json().encode("utf-8"))
    if size > MAX_BUNDLE_BYTES:
        raise BundleSizeExceededError(
            f"inverse bundle size ({size} bytes) exceeds the {MAX_BUNDLE_BYTES} byte ceiling"
        )
    return bundle


#: Exit-0 mutmut snippet markers the substrate actually emits for
#: non-measurements. The F2a "DEFERRED:" prefix is the placeholder shape;
#: the rest are verbatim runner disclosures (disabled per-node gate,
#: win32 deferral, active-mutation guard) that must never read "passed".
_MUTMUT_NON_MEASURED_MARKERS: Final[tuple[str, ...]] = (
    "disabled by runner configuration",
    "deferred per 01_INVARIANTS.md",
    "skipped under active mutation",
)


def _classify_mutmut(gate: GateReport) -> str:
    """Classifies the per-node mutmut report without ever counting it."""
    if (
        gate.exit_code == 0
        and gate.duration_seconds == 0.0
        and gate.raw_output_snippet.startswith(DEFERRED_SNIPPET_PREFIX)
    ):
        return "deferred"
    if gate.exit_code == 0 and any(
        marker in gate.raw_output_snippet for marker in _MUTMUT_NON_MEASURED_MARKERS
    ):
        return "deferred"
    if gate.exit_code == 0:
        return "passed"
    return "failed"


#: Per-gate first-signal budget: the prune-feedback head must stay dense
#: enough that SST's stderr[:100] retry hint keeps gates + locations.
_FIRST_SIGNAL_BUDGET = 64

_RUFF_SIGNAL_RE = re.compile(r"^(\S+:\d+:\d+: [A-Z]+\d+)\b(.*)$")
_MYPY_SIGNAL_RE = re.compile(r"^(\S+:\d+: error:)(.*)$")
_PYTEST_FAILED_RE = re.compile(r"^(FAILED \S+)(.*)$")
_PYTEST_ERROR_RE = re.compile(r"^(E\s+\S.*)$")


def _fit_signal(text: str) -> str:
    """Collapses a signal to one budgeted line (ASCII-safe truncation)."""
    one_line = " ".join(text.split())
    return one_line[:_FIRST_SIGNAL_BUDGET]


def _first_signal_line(snippet: str, gate: str, exit_code: int) -> str:
    """First actionable error line of a failed gate snippet, compacted."""
    if "Gate timed out" in snippet:
        return "timeout"
    for raw in snippet.splitlines():
        line = raw.strip()
        if not line:
            continue
        if gate == "ruff":
            match = _RUFF_SIGNAL_RE.match(line)
            if match:
                return _fit_signal(f"{match.group(1)}{match.group(2)}")
            if "would be reformatted" in line:
                return _fit_signal(line)
        elif gate == "mypy":
            match = _MYPY_SIGNAL_RE.match(line)
            if match:
                return _fit_signal(f"{match.group(1)}{match.group(2)}")
        elif gate == "pytest":
            match = _PYTEST_FAILED_RE.match(line)
            if match:
                return _fit_signal(f"{match.group(1)}{match.group(2)}")
            if _PYTEST_ERROR_RE.match(line):
                return _fit_signal(line)
    for raw in snippet.splitlines():
        line = raw.strip()
        if line:
            return _fit_signal(line)
    return f"exit {exit_code}"


def _first_gate_signals(receipt: ExecutionReceipt) -> list[str]:
    """Compact first-error signals, one per failed hard gate (A4-D1).

    Attempt-4 demonstrated the gap: the retry hint SST feeds the next
    worker is stderr[:100], and the old detail led with a long fixed
    prefix + lease id, so the worker saw a single gate name ("stc_mypy,")
    with no location. These signals front-load file:line-shaped evidence
    for the detail head; unknown shapes degrade to the exit code.
    """
    gates = (
        ("ruff", receipt.gate_ruff),
        ("mypy", receipt.gate_mypy),
        ("pytest", receipt.gate_pytest),
    )
    signals: list[str] = []
    for name, gate in gates:
        if gate.exit_code == 0:
            continue
        signals.append(
            f"{name} {_first_signal_line(gate.raw_output_snippet or '', name, gate.exit_code)}"
        )
    return signals


def receipt_to_score(receipt: ExecutionReceipt) -> ScoreBreakdown:
    """Scores a verified receipt with the coarse deterministic reward rule."""
    gates: dict[str, bool] = {
        "stc_ruff": receipt.gate_ruff.exit_code == 0,
        "stc_mypy": receipt.gate_mypy.exit_code == 0,
        "stc_pytest": receipt.gate_pytest.exit_code == 0,
    }
    hard_gates = {"verifier_passed": all(gates.values()), **gates}
    assert tuple(hard_gates) == HARD_GATE_KEYS, "hard-gate vocabulary drift"
    passed = sum(1 for value in hard_gates.values() if value)
    return ScoreBreakdown(
        passed_hard_gates=all(hard_gates.values()),
        hard_gates=hard_gates,
        soft_scores={},
        normalized_reward=passed / len(hard_gates),
        raw_metrics={
            "mutmut_status": _classify_mutmut(receipt.gate_mutmut),
            "ruff_duration_s": receipt.gate_ruff.duration_seconds,
            "mypy_duration_s": receipt.gate_mypy.duration_seconds,
            "pytest_duration_s": receipt.gate_pytest.duration_seconds,
            "first_signals": _first_gate_signals(receipt),
        },
        critic_verdict=None,
        critic_rationale=None,
        evaluated_at=datetime.now(UTC),
    )


def _strip_diff_prefix(path: str) -> str:
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _dedupe_targets(pairs: list[tuple[str, str]], where: str) -> list[tuple[str, str]]:
    """Dedupes identical (path, action) pairs; conflicting actions raise."""
    seen: dict[str, str] = {}
    order: list[str] = []
    for path, action in pairs:
        if path in seen:
            if seen[path] != action:
                raise UndisposedFieldError(
                    f"{where}: conflicting actions for {path!r}: {seen[path]!r} vs {action!r}"
                )
            continue
        seen[path] = action
        order.append(path)
    return [(path, seen[path]) for path in order]


def _parse_hunk_targets(patch_diff: str) -> list[tuple[str, str]]:
    """Derives (path, action) pairs from "---"/"+++" file-header pairs."""
    lines = patch_diff.splitlines()
    pairs: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        is_old = line == "---" or line.startswith("--- ")
        is_new = line == "+++" or line.startswith("+++ ")
        if is_old:
            if index + 1 >= len(lines):
                raise UndisposedFieldError("patch_diff: '---' without '+++' pair")
            follower = lines[index + 1]
            if not (follower == "+++" or follower.startswith("+++ ")):
                raise UndisposedFieldError("patch_diff: '---' without '+++' pair")
            old = _strip_diff_prefix(line[3:].strip())
            new = _strip_diff_prefix(follower[3:].strip())
            for candidate in (old, new):
                if not candidate:
                    raise UndisposedFieldError("patch_diff: empty path in header pair")
                if candidate.startswith('"'):
                    raise UndisposedFieldError(
                        "patch_diff: quoted paths unsupported; emit plain paths"
                    )
            if old == "/dev/null" and new == "/dev/null":
                raise UndisposedFieldError("patch_diff: null header pair")
            if old == "/dev/null":
                pairs.append((new, "create"))
            elif new == "/dev/null":
                pairs.append((old, "delete"))
            else:
                pairs.append((new, "modify"))
            index += 2
        elif is_new:
            raise UndisposedFieldError("patch_diff: '+++' without '---' pair")
        else:
            index += 1
    return _dedupe_targets(pairs, "patch_diff")


def _parse_op_dict(op: dict[str, Any], index: int) -> tuple[str, str]:
    """Validates one op-dict against the known-op vocabulary (F1e)."""
    raw_op = op.get("op")
    if not isinstance(raw_op, str) or raw_op not in KNOWN_OPS:
        raise UndisposedFieldError(
            f"file_operations[{index}].op: unknown op {raw_op!r} (known: create|modify|delete)"
        )
    raw_path = op.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise UndisposedFieldError(f"file_operations[{index}].path: missing or blank")
    return raw_path, raw_op


def proposal_to_filetargets(proposal: CandidateProposal) -> list[FileTarget]:
    """Derives lease-scope file targets from a candidate proposal."""
    hunk_targets = _parse_hunk_targets(proposal.patch_diff)
    op_targets = [_parse_op_dict(op, index) for index, op in enumerate(proposal.file_operations)]
    if hunk_targets:
        hunk_actions = dict(hunk_targets)
        for index, (path, action) in enumerate(op_targets):
            if path not in hunk_actions:
                raise UndisposedFieldError(
                    f"file_operations[{index}]: path {path!r} not in patch_diff hunks"
                )
            if hunk_actions[path] != action:
                raise UndisposedFieldError(
                    f"file_operations[{index}]: op {action!r} conflicts with "
                    f"hunk action {hunk_actions[path]!r} for {path!r}"
                )
        derived = hunk_targets
    else:
        derived = _dedupe_targets(op_targets, "file_operations")
    if proposal.target_paths:
        declared = set(proposal.target_paths)
        for path, _ in derived:
            if path not in declared:
                raise UndisposedFieldError(f"target_paths: patch touches undeclared path {path!r}")
    return [FileTarget(path=path, action=action) for path, action in derived]
