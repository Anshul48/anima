"""CLI-backed gateway backend: prompt-kit-harness model channel for SST (P03).

``CLIModelGateway`` is a ``ModelGateway`` subclass serving the controller's
invoke path (``GatewayRequest`` -> ``GatewayResponse``) through the same
harness + spend core as ``HarnessWorker`` (D10/BT-04). Every gateway call is
spend-logged and pre-dispatch-budgeted on the ``gateway`` channel. The
``generate``/``generate_async`` methods are ``SSTLLMClient``-compatible for
the engine's model-function path. No SST sources are modified (read-only).

Token counts are unavailable from CLI harnesses, so responses report zero
tokens with a ``raw_metadata`` note; spend is tracked in STC ledger rows, and
``cost_usd`` is 0.0 (CLI-session budget per R5, never API-key spend).

Fix tranche (INT-2026-09-14.1, D15): prompts are emitter-framed by
``shape_gateway_prompt`` (SST bytes verbatim, never edited) and native calls
run confined (scratch cwd, read-only codex sandbox, -o capture, tracked-status
assertion failing closed).

F1 (follow-up): harness failures preserve FULL stdout/stderr in the
failure-evidence sidecar; the ledger note is a short pointer and the raised
error carries the error TAIL, never a truncated head.

Marker refusal (follow-up, MARKERS.md §5): responses carrying column-0 `***`
lines are refused pre-dispatch (no bytes forwarded to SST); the served ledger
row keeps `ok=True` with a refusal note, and the full refused bytes land in a
separate refusal-evidence sidecar. No byte is ever rewritten (sanitizing stays
rejected).

H1 context (follow-up, CONTEXT.md): the pinned read-only source-context
package rides in the closing frame after the SST block (reference text only).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sst.gateway.contracts import (
    GatewayRequest,
    GatewayResponse,
    MissingModelError,
    ProviderGatewayError,
)
from sst.gateway.gateway import ModelGateway
from sst.search.controller import SSTSearchController

from stc.integration.harness_worker import (
    NOTE_BUDGET,
    CritiqueProvenance,
    GatewayConfinementError,
    HarnessConfigError,
    HarnessT,
    RunnerFn,
    SpendLedger,
    default_runner,
    failure_note_pointer,
    run_harness_attempt,
    validate_harness_name,
    write_failure_evidence,
)
from stc.integration.manual_payloads import parse_critique_content, validate_critique

__all__ = [
    "H1_CONTEXT_PACKAGE",
    "MARKER_REFUSAL_RULE",
    "REFUSAL_EVIDENCE_VERSION",
    "SST_PROMPT_BEGIN",
    "SST_PROMPT_END",
    "CLIGatewayBackend",
    "CLIModelGateway",
    "marker_refusal_reason",
    "render_gateway_prompt",
    "shape_gateway_prompt",
    "write_refusal_evidence",
]

logger = logging.getLogger(__name__)


def render_gateway_prompt(messages: list[dict[str, Any]]) -> str:
    """Render gateway messages to plain prompt text (role-prefixed lines)."""
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = str(message.get("content", ""))
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


#: Delimiters bracketing the verbatim SST prompt block inside shaped gateway prompts.
SST_PROMPT_BEGIN = "--- SST PROMPT BEGIN (verbatim; do not edit, do not reorder) ---"
SST_PROMPT_END = "--- SST PROMPT END ---"

#: H1 read-only source context (follow-up, CONTEXT.md package): pinned frame
#: content, mechanically generated from
#: evidence/FOLLOWUP/h1-prep/ctx-package.txt (4073 B) — NEVER hand-edit.
#: Payload sha256:
#: c41b9857e493f5037dd08970f39f772fd541855c86b8e99f6ca5e78cdf0e7e2e
#: Staleness rule: if any source file below drifts, rebuild from the same
#: ranges and re-pin. Provenance whole-file sha256 (operator-release
#: 2026-09-25; finalization + SST cand-02 re-pins 2026-10-04; ranges
#: track the original semantic anchors):
#: src/stc/integration/dialectic_runner.py
#: 19dbaf30087a6a699391708ddd3f7b386a9f25a238456661768fcfc8644eea21
#: tests/unit/test_integration_dialectic.py
#: df9aa909d4e473e6d5b4dafdd74ce625d2ce03cbb3c7dbf2335ea7f85b3fc296
#: src/stc/judiciary/auditor.py
#: 9236d39c47f3649546afb542c1bd7d3570d8ee60d72b7bab4b9458fa048f9a5e
#: Frame-budget note: 4073 B roughly doubles emission input; attempt-4
#: must keep the reasoning-medium profile — treat any stall as a
#: prompt-size signal, not a content signal.
H1_CONTEXT_PACKAGE = (
    "[H1-CTX/pinned] read-only source context (NOT a patch target)\n"
    "--- 1 test_integration_dialectic.py:21-22,24-26,28-29,33-55\n"
    "from sst.core.contracts import CandidateProposal, TaskPacket\n"
    "from sst.core.events import EventKind, SSTEvent\n"
    "from sst.gateway.gateway import ModelGateway\n"
    "from sst.sandbox.custody import CandidateCustodyManager\n"
    "from sst.search.policy import SearchPolicy\n"
    "from stc.integration.adapters import AdapterContext, Budgets\n"
    "from stc.integration.dialectic_runner import (\n"
    "    ChampionResult,\n"
    "    DialecticError,\n"
    "    DialecticRunner,\n"
    "    LossLedgerEntry,\n"
    "    NoChampionResult,\n"
    "    STCCustodyWrapper,\n"
    "    SynthesisReceipt,\n"
    "    count_mutmut_runs,\n"
    "    lease_id_for,\n"
    "    mirror_source_tree,\n"
    "    render_merged_diff,\n"
    "    sanitize_lease_segment,\n"
    "    scrape_tainted_scores,\n"
    ")\n"
    "from stc.integration.harness_worker import CritiqueProvenance\n"
    "from stc.judiciary.auditor import JudiciaryAuditor\n"
    "from stc.schemas.models import (\n"
    "    ExecutionReceipt,\n"
    "    FileTarget,\n"
    "    GateReport,\n"
    "    JudiciaryVerdict,\n"
    "    TaskBundle,\n"
    ")\n"
    "--- 2 dialectic_runner.py:127-128,199-200,204-211\n"
    '    "SynthesisReceipt",\n'
    '    "VetoRecord",\n'
    "\n"
    '    model_config = ConfigDict(frozen=True, extra="forbid")\n'
    "    rationale: str\n"
    "    rule: str  # veto rule name (see scrape_tainted_scores Rules 0-3)\n"
    "\n"
    "\n"
    "class SynthesisReceipt(BaseModel):\n"
    '    """Receipt for one colimit synthesis: parents + scores + verification."""\n'
    "\n"
    '    model_config = ConfigDict(frozen=True, extra="forbid")\n'
    "--- 3 dialectic_runner.py:747-758,777-778\n"
    "        except FileExistsError:\n"
    '            self.quarantine_lease(lease_id, "stale lease dir present at allocation")\n'
    "            lease_ws.mkdir(parents=True, exist_ok=False)\n"
    "        try:\n"
    "            mirror_source_tree(src, lease_ws)\n"
    "            # T2 custody: disposable git (sanitized mirror or fresh init),\n"
    "            # then the tripwire opens over the mirrored bytes.\n"
    "            try:\n"
    "                lease_mode = ensure_disposable_git(lease_ws)\n"
    "            except LeaseGitError as exc:\n"
    "                self.release_lease(lease_id)\n"
    '                return _non_pass(f"Lease {lease_id}: disposable git setup failed: {exc}")\n'
    '                        f"({drift[0]}; re-pin T0, never proceed)"\n'
    "                    )\n"
    "--- 4 test_integration_dialectic.py:817-829\n"
    "    runner = DialecticRunner(\n"
    "        ctx=_ctx(str(src), time_budget_seconds=time_budget_seconds),\n"
    "        gateway=ScriptGateway(handler),\n"
    "        substrate=substrate,\n"
    '        evidence_root=tmp_path / "ev",\n'
    "        policy=(\n"
    "            policy\n"
    "            if policy is not None\n"
    "            else SearchPolicy(max_iterations=1, max_depth=2, branching_factor=4)\n"
    "        ),\n"
    "        auditor=auditor,\n"
    "        **kwargs,\n"
    "    )\n"
    "--- 5 dialectic_runner.py:921-923,932,876,887,893-897\n"
    "                self.binding_diffs[proposal.candidate_id] = node_diff\n"
    "                self.import_proofs[proposal.candidate_id] = import_proof\n"
    "            self.release_lease(lease_id)\n"
    "    # L932:\n"
    "                )\n"
    "    # L876/L887/L893-897:\n"
    "            try:\n"
    "                candidate_content_digest=candidate_content_digest(scratch_sha, {}, "
    "node_diff),\n"
    "            record = SelectionRecord(\n"
    "                candidate_id=proposal.candidate_id,\n"
    "                intake_ref=intake.digest(),\n"
    '                config_revision=sel_verify["config_revision"],\n'
    '                mandatory_digest=sel_verify["mandatory_digest"],\n'
    "--- 6 auditor.py:91-96,189-194 + dialectic_runner.py:1030-1039\n"
    "    def __init__(\n"
    "        self,\n"
    "        runner: SubstrateRunnerProtocol | None = None,\n"
    "        with_codex: bool = False,\n"
    "        codex_bin: str | None = None,\n"
    "    ) -> None:\n"
    "    def audit_diff(\n"
    "        self,\n"
    "        diff_text: str,\n"
    "        bundle: TaskBundle,\n"
    "        receipt: ExecutionReceipt,\n"
    "    ) -> JudiciaryVerdict:\n"
    '        chunks.append(f"--- a/{target}\\n+++ b/{target}\\n")\n'
    '        chunks.extend(f"+{line}\\n" for line in diff.splitlines())\n'
    '    return normalize_diff("".join(chunks))\n'
    "\n"
    "\n"
    "def _proposal_from_events(\n"
    "    node_id: str, tree_id: str, events: list[SSTEvent]\n"
    ") -> CandidateProposal | None:\n"
    '    """Reconstructs a verified proposal from its proposal event payload.\n'
    "\n"
)


def shape_gateway_prompt(sst_prompt: str) -> str:
    """Wrap opaque SST prompt bytes in APPEND-ONLY emitter framing (fix tranche, D15).

    The SST bytes are embedded verbatim between delimiters and are NEVER edited
    (D7 intact: no SST change, no template rewrite). The surrounding STC-owned
    frame assigns the emitter role, no-tools/no-write discipline, and the
    emit-exactly-one-JSON instruction that the text-emission contract needs.
    A3 (follow-up): the closing instruction additionally pins unified-diff-only
    patch emission (no codex apply_patch markers) — SST bytes still verbatim.
    H1 (follow-up): a pinned read-only source-context block rides after the
    SST block (reference text only — grants no write scope); the A3 pin and
    the final emit instruction stay last.
    """
    return "\n".join(
        [
            "STC GATEWAY EMITTER FRAME (role=gateway; text-emission contract).",
            "You are a JSON emitter, not an autonomous agent: you have no tools,",
            "no shell, no file access, and no network. Do not call tools, do not",
            "read or write files, do not browse the web, do not ask questions.",
            "Your ONLY action is to emit text: exactly one response message,",
            "no tool calls, no writes anywhere.",
            "Emit exactly one JSON document as your entire response message —",
            "no prose before or after it, no markdown fences, no commentary.",
            "",
            SST_PROMPT_BEGIN,
            sst_prompt,
            SST_PROMPT_END,
            "",
            H1_CONTEXT_PACKAGE,
            "If the JSON carries proposed code changes, emit that patch string",
            "(proposed_changes) as a pure unified diff: '---'/'+++' headers with",
            "'@@' hunks only. NEVER emit codex apply_patch markers: no patch line",
            "may begin with '***' ('*** Begin Patch' / '*** Add File:' / '*** End Patch').",
            "Now emit exactly one JSON document satisfying the SST prompt above,",
            "and nothing else.",
        ]
    )


#: Refusal rule id for marker-bearing gateway responses (MARKERS.md §5).
MARKER_REFUSAL_RULE = "column0-triple-star"

#: Suffix mapping a spend ledger path to its refusal-evidence sidecar:
#: ``<stem>.refusals.jsonl`` next to the ledger. Refusal is a gateway policy
#: decision on successfully served bytes — never the F1 harness-failure sidecar.
_REFUSAL_EVIDENCE_SUFFIX = ".refusals.jsonl"

#: Refusal-evidence record version (mirrors the F1 sidecar convention).
REFUSAL_EVIDENCE_VERSION = 1

#: Offending-line budget inside refusal notes/errors (truncated head); the
#: full refused bytes live only in the refusal-evidence sidecar record.
_REFUSAL_LINE_BUDGET = 80


def marker_refusal_reason(response_text: str) -> str | None:
    """Return the first column-0 `***` line, or None when admissible (MARKERS §5).

    Mirrors SST's own parse shape: SST's `_parse_json_dict` parses the
    response; when `branches[]` is a non-empty list each `proposed_changes`
    field is scanned, otherwise the whole content (the raw-fallback shape).
    Column-0-only matching keeps legitimate content (` ***bold***`, indented
    markers) admissible. Pure predicate: no I/O, no byte rewriting.
    """
    parsed = SSTSearchController._parse_json_dict(response_text)
    branches = parsed.get("branches", [])
    targets: list[str] = []
    if isinstance(branches, list) and branches:
        for branch in branches:
            if isinstance(branch, dict):
                targets.append(str(branch.get("proposed_changes", "")))
    else:
        targets.append(response_text)
    for target in targets:
        for line in target.splitlines():
            if line.startswith("***"):
                return line[:_REFUSAL_LINE_BUDGET]
    return None


def write_refusal_evidence(
    *,
    ledger_path: str | Path,
    harness: str,
    model: str,
    profile: str | None,
    task_id: str,
    offending_line: str,
    refused_bytes: str,
) -> tuple[Path, str] | None:
    """Append one refusal record with the FULL refused bytes to the sidecar.

    Best-effort (mirrors F1): returns (sidecar_path, record_id), or None when
    the write fails (a logging failure warns, never masks the refusal).
    """
    ledger = Path(ledger_path)
    sidecar = ledger.parent / f"{ledger.stem}{_REFUSAL_EVIDENCE_SUFFIX}"
    record_id = uuid.uuid4().hex[:12]
    record: dict[str, Any] = {
        "v": REFUSAL_EVIDENCE_VERSION,
        "id": record_id,
        "ts": datetime.now(UTC).isoformat(),
        "harness": harness,
        "model": model,
        "profile": profile,
        "task_id": task_id,
        "rule": MARKER_REFUSAL_RULE,
        "offending_line": offending_line,
        "refused_sha256": hashlib.sha256(refused_bytes.encode("utf-8")).hexdigest(),
        "refused_bytes": refused_bytes,
        "ledger": str(ledger_path),
    }
    try:
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        with sidecar.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.warning("Refusal-evidence record dropped (logging failed): %s", exc)
        return None
    return sidecar, record_id


class CLIGatewayBackend:
    """Harness + spend core behind the CLI gateway (SSTLLMClient-compatible)."""

    def __init__(
        self,
        harness_name: str = "mock",
        model: str | None = "default",
        *,
        project_root: str | Path,
        ledger: SpendLedger | None = None,
        timeout: float = 600.0,
        harness_env: dict[str, str] | None = None,
        harness: HarnessT | None = None,
        runner: RunnerFn | None = None,
        task_label: str = "gateway",
    ) -> None:
        self._name = validate_harness_name(harness_name)
        if harness is not None and (
            hasattr(harness, "command_template") or type(harness).__name__ == "CommandHarness"
        ):
            raise HarnessConfigError("Shell/command-template harnesses are forbidden (F11).")
        if timeout <= 0:
            raise HarnessConfigError("timeout must be positive seconds.")
        self._model = model or "default"
        self._project_root = Path(project_root)
        self._ledger = ledger if ledger is not None else SpendLedger()
        self._timeout = timeout
        self._harness_env = dict(harness_env) if harness_env else {}
        self._harness = harness
        self._runner = runner
        self._task_label = task_label
        self._critique_provenance: list[CritiqueProvenance] = []
        self._rows_logged = 0

    @property
    def harness_name(self) -> str:
        """Allowlisted harness name backing this backend."""
        return self._name

    @property
    def zero_cost_known(self) -> bool:
        """True when every call through this backend provably spends $0.

        SST honest budgets (cand-02): a set USD cap with cost-unknown
        responses fails closed (UnpricedCostBudgetError) instead of
        running an unenforceable budget. Manual/clipboard fixtures
        and the pinned mock harness make no model calls, so $0 there
        is KNOWN, not unknown. CLI subprocess backends (codex) and
        operator executables (exec-harness) have real but unmetered
        spend — STC ledger rows carry no USD — so they stay
        cost-unknown and a USD cap still fails closed, honestly.
        """
        if self._harness is not None:
            return bool(getattr(self._harness, "name", "") in ("manual", "mock"))
        return self._name == "mock"

    @property
    def critique_provenance(self) -> tuple[CritiqueProvenance, ...]:
        """Per-critique-call validity witnesses, in call order (Fix 2)."""
        return tuple(self._critique_provenance)

    def _record_critique(self, content: str | None, detail: str) -> None:
        """Appends one critique witness; valid only if content is explicit.

        Parsing mirrors the SST controller exactly (fence-strip + both
        critique shapes), so genuine fenced/capsule-path critiques validate.
        """
        valid = False
        if content:
            obj = parse_critique_content(content)
            valid = obj is not None and validate_critique(obj) == []
            if not valid and detail == "ok":
                detail = "unparseable critique content"
        self._critique_provenance.append(
            CritiqueProvenance(
                seq=len(self._critique_provenance),
                valid=valid,
                detail=detail[:160],
                ledger_row=self._rows_logged,
            )
        )

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        model: str | None = None,
        timeout: float | None = None,
        profile: str | None = None,
        sst_role: str | None = None,
    ) -> str:
        """Invoke the harness once; budgeted + logged (temperature accepted, CLI-ignored).

        ``sst_role`` is the controller's role label (diverge/refine/critique/…),
        forwarded to the harness for role-aware prompts + payload validation;
        routing always stays on the confinement profile. Gateway prompts are
        emitter-framed (shape_gateway_prompt); native calls run under the
        fix-tranche confinement profile and fail closed as
        ProviderGatewayError (handled honestly upstream by the controller).
        On harness failure the FULL stdout/stderr land in the failure-evidence
        sidecar (F1); the ledger note is a short pointer and the raised error
        carries the error TAIL (where the real cause lives), never a
        truncated head.
        """
        _ = temperature
        target_model = model or self._model
        self._ledger.check_quota("gateway")
        shaped = shape_gateway_prompt(prompt)
        started = time.perf_counter()
        ok = False
        exit_code: int | None = None
        timed_out = False
        out_bytes = 0
        note = ""
        evidence_ref: str | None = None
        try:
            try:
                result, _ = run_harness_attempt(
                    name=self._name,
                    model=target_model,
                    prompt=shaped,
                    role="gateway",
                    project_root=self._project_root,
                    context_extra={"task_id": self._task_label},
                    timeout=timeout if timeout is not None else self._timeout,
                    harness_env=self._harness_env,
                    harness=self._harness,
                    runner=self._runner if self._runner is not None else default_runner,
                    harness_role=sst_role,
                )
            except GatewayConfinementError as exc:
                note = f"confinement breach, failing closed: {exc}"
                if sst_role == "critique":
                    self._record_critique(None, f"confinement breach: {exc}"[:160])
                raise ProviderGatewayError(
                    f"CLI gateway {self._name!r} failed closed: {exc}",
                    category="confinement_breach",
                    remediation=(
                        "Inspect the repo for unexpected tracked changes; retry after review."
                    ),
                    profile=self._name,
                ) from exc
            ok = bool(result.is_success)
            exit_code = result.exit_code
            timed_out = exit_code == 124
            out_bytes = len(result.content or "")
            if not ok:
                err_text = result.error or f"exit {result.exit_code}"
                written = write_failure_evidence(
                    ledger_path=self._ledger.path,
                    channel="gateway",
                    harness=self._name,
                    model=target_model,
                    profile=profile,
                    task_id=self._task_label,
                    lease_id="",
                    attempt=1,
                    exit_code=exit_code,
                    timed_out=timed_out,
                    duration_s=time.perf_counter() - started,
                    out_bytes=out_bytes,
                    stdout_full=result.content or "",
                    stderr_full=result.error or "",
                )
                if written is not None:
                    sidecar, record_id = written
                    evidence_ref = f"{sidecar}#{record_id}"
                    note = failure_note_pointer(err_text, sidecar, record_id)
                    where = f"full output in {sidecar.name}#{record_id}"
                else:
                    note = failure_note_pointer(err_text, None, None)
                    where = "failure-evidence write failed"
                tail = err_text[-NOTE_BUDGET:] if len(err_text) > NOTE_BUDGET else err_text
                if sst_role == "critique":
                    self._record_critique(None, f"harness failure: {tail}"[:160])
                raise ProviderGatewayError(
                    f"CLI harness {self._name!r} failed (exit {exit_code}): {tail} [{where}]",
                    category="harness_error",
                    remediation="Check harness availability and retry.",
                    profile=self._name,
                )
            refusal = marker_refusal_reason(result.content or "")
            if refusal is not None:
                # MARKERS.md §5: refuse pre-dispatch (no bytes forwarded to
                # SST). The served row keeps ok=True (harness truth); the note
                # carries the refusal + sidecar pointer (set before the raise
                # so `finally` logs it). No gateway-internal retry: the
                # controller's iteration loop is the retry layer.
                written = write_refusal_evidence(
                    ledger_path=self._ledger.path,
                    harness=self._name,
                    model=target_model,
                    profile=profile,
                    task_id=self._task_label,
                    offending_line=refusal,
                    refused_bytes=result.content or "",
                )
                if written is not None:
                    sidecar, record_id = written
                    note = f"stc-refused: {MARKER_REFUSAL_RULE} ({sidecar.name}#{record_id})"
                else:
                    note = f"stc-refused: {MARKER_REFUSAL_RULE} (refusal-evidence write failed)"
                if sst_role == "critique":
                    self._record_critique(None, f"marker refusal: {refusal}"[:160])
                raise ProviderGatewayError(
                    "STC gateway refused marker-bearing response "
                    f"(no bytes forwarded to SST): {refusal!r} "
                    "[full bytes in refusal sidecar, see ledger note]",
                    category="stc_marker_refusal",
                    remediation=(
                        "Emission violated the unified-diff-only pin; "
                        "retry or narrow the emitter frame."
                    ),
                    profile=profile,
                )
            if sst_role == "critique":
                self._record_critique(result.content or "", "ok")
            return result.content
        finally:
            self._ledger.log_row(
                "gateway",
                harness=self._name,
                model=target_model,
                task_id=self._task_label,
                lease_id="",
                attempt=1,
                ok=ok,
                exit_code=exit_code,
                timed_out=timed_out,
                duration_s=time.perf_counter() - started,
                out_bytes=out_bytes,
                note=note,
                failure_evidence=evidence_ref,
            )
            self._rows_logged += 1

    async def generate_async(
        self,
        prompt: str,
        temperature: float = 0.7,
        model: str | None = None,
        timeout: float | None = None,
        profile: str | None = None,
        sst_role: str | None = None,
    ) -> str:
        """Async bridge over generate (mirrors SSTLLMClient.generate_async)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate(
                prompt,
                temperature=temperature,
                model=model,
                timeout=timeout,
                profile=profile,
                sst_role=sst_role,
            ),
        )


class CLIModelGateway(ModelGateway):
    """ModelGateway serving every routed request through a CLI backend."""

    def __init__(
        self,
        backend: CLIGatewayBackend,
        profiles: dict[str, Any] | None = None,
        routes: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(profiles=profiles, routes=routes)
        self.backend = backend

    def _resolve_route(self, request: GatewayRequest) -> tuple[str, str]:
        """Mirror base-class profile/model resolution (routing owned by SST)."""
        profile_name = request.profile_name
        model = request.model
        if not profile_name and request.role:
            route = self.get_route(request.role)
            if route:
                profile_name = route.profile
                model = model or route.model
        if not profile_name:
            if len(self.profiles) == 1:
                profile_name = next(iter(self.profiles.keys()))
            else:
                raise ProviderGatewayError(
                    f"No provider profile assigned for role '{request.role}'"
                    " and no profile specified",
                    category="routing_error",
                    remediation="Configure a profile and assign it to this route.",
                )
        profile = self.profiles.get(profile_name)
        if not profile:
            raise ProviderGatewayError(
                f"Provider profile '{profile_name}' is not registered",
                category="routing_error",
                remediation=f"Available profiles: {', '.join(self.profiles.keys()) or 'none'}",
            )
        target_model = model or profile.selected_model
        if not target_model:
            raise MissingModelError(
                f"No model selected for profile '{profile_name}' or role '{request.role}'",
                profile=profile_name,
            )
        return profile_name, target_model

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        """Serve the controller's invoke path via the CLI backend (D10/BT-04)."""
        profile_name, target_model = self._resolve_route(request)
        profile = self.profiles[profile_name]
        timeout = request.timeout_seconds or profile.timeout_seconds
        prompt = render_gateway_prompt(request.messages)
        started = time.perf_counter()
        content = self.backend.generate(
            prompt,
            temperature=request.temperature,
            model=target_model,
            timeout=float(timeout),
            profile=profile_name,
            sst_role=request.role,
        )
        zero_cost = self.backend.zero_cost_known
        return GatewayResponse(
            content=content,
            model=target_model,
            profile=profile_name,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            cost_known=zero_cost,
            duration_seconds=time.perf_counter() - started,
            raw_metadata={
                "harness": self.backend.harness_name,
                "tokens": (
                    "no model calls ($0 known: fixture/mock backend)"
                    if zero_cost
                    else "unavailable (CLI session; spend tracked in STC ledger rows)"
                ),
            },
        )
