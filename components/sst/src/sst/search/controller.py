"""Async search controller coordinating State Space Tree expansion, role routing, and event recording."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sst.context.capsule import ContextCapsuleCompiler, memory_tree_payload_fragment
from sst.core.contracts import (
    AlternativeCandidate,
    BudgetConsumed,
    CandidateProposal,
    GatewayBinding,
    ProviderErrorRecord,
    ScoreBreakdown,
    SearchResult,
    TaskPacket,
    TerminationReason,
)
from sst.core.errors import LeaseAcquisitionError, UnpricedCostBudgetError
from sst.core.events import EventKind, SSTEvent
from sst.core.models import (
    AuDHDContextCapsule,
    DeterministicGateResult,
    DomainMode,
    NodeRole,
    PayloadType,
    SSTNode,
)
from sst.gateway.contracts import GatewayRequest, GatewayResponse, ProviderGatewayError
from sst.gateway.gateway import ModelGateway
from sst.prompts.dialectic import (
    render_adhd_explorer_prompt,
    render_asd_exploiter_prompt,
    render_cortex_critic_prompt,
    render_cortex_synthesizer_prompt,
)
from sst.protocols.executor import ExecutorProtocol
from sst.sandbox.custody import CandidateCustodyManager
from sst.search.policy import BudgetTracker, SearchPolicy
from sst.storage.store import SQLiteSSTStore

logger = logging.getLogger(__name__)


class SSTSearchController:
    """Coordinates MCTS expansion, functional role routing, candidate custody, and append-only event recording.

    Single-writer posture: a run assumes it is the only writer appending to
    its ``tree_id`` event log. Concurrent writers to the same tree are not
    coordinated by default; enable the optional lease guard
    (``SearchPolicy.require_lease`` or ``run_search(acquire_lease=True)``) to
    fail closed with :class:`LeaseAcquisitionError` on contention.
    """

    def __init__(
        self,
        task: TaskPacket,
        gateway: ModelGateway,
        store: SQLiteSSTStore,
        custody_manager: CandidateCustodyManager,
        policy: SearchPolicy | None = None,
        capsule_compiler: ContextCapsuleCompiler | None = None,
        executor: ExecutorProtocol | None = None,
    ) -> None:
        self.task = task
        self.gateway = gateway
        self.store = store
        self.custody_manager = custody_manager
        self.executor: ExecutorProtocol = executor if executor is not None else custody_manager
        self.policy = policy or SearchPolicy()
        self.budget_tracker = BudgetTracker()
        self.capsule_compiler = capsule_compiler or ContextCapsuleCompiler(workspace_root=self.task.source_repo_root)
        self._cancelled = False
        self._provider_errors: list[ProviderErrorRecord] = []

    def _role_max_tokens(self, default: int) -> int:
        """Returns the per-request completion cap for a role (policy override or default)."""
        return self.policy.response_max_tokens or default

    def _cost_cap_enabled(self) -> bool:
        """Returns True when either the task or the policy sets a USD cost cap."""
        return bool(self.task.cost_budget_usd or self.policy.max_cost_usd)

    def _accumulate_usage(self, resp: GatewayResponse) -> None:
        """Accumulates usage; rejects USD caps without valid cost accounting."""
        if self._cost_cap_enabled() and not resp.cost_known:
            raise UnpricedCostBudgetError(
                f"A USD cost cap is set but profile '{resp.profile}' has no USD pricing: "
                "set input_usd_per_1k_tokens/output_usd_per_1k_tokens on the profile or "
                "remove the cost cap. Refusing to run an unenforceable budget."
            )
        self.budget_tracker.tokens_consumed += resp.total_tokens
        self.budget_tracker.estimated_cost_usd += resp.cost_usd

    def cancel(self) -> None:
        """Cooperatively requests cancellation of search loop."""
        self._cancelled = True

    async def execute_search(self, tree_id: str) -> CandidateProposal | None:
        """Runs bounded tree search and returns the winning candidate proposal if found.

        Backwards-compatible wrapper over run_search(): same search, same
        champion selection, champion only. Prefer run_search() for the full
        typed envelope (termination, alternatives, budget, provider errors).
        """
        result = await self.run_search(tree_id)
        return result.champion

    async def run_search(self, tree_id: str, *, acquire_lease: bool | None = None) -> SearchResult:
        """Runs bounded tree search and returns the full typed result envelope.

        Single-writer posture: the run assumes it is the only writer for
        ``tree_id``. Pass ``acquire_lease=True`` (or set
        ``SearchPolicy.require_lease``) to first acquire the tree's exclusive
        SQLite writer lease; contention raises :class:`LeaseAcquisitionError`
        before any event is appended, and the lease is released when the run
        ends. The default (``None`` + policy default ``False``) preserves the
        unguarded STC-compatible behavior.
        """
        use_lease = self.policy.require_lease if acquire_lease is None else acquire_lease
        if not use_lease:
            return await self._run_search_inner(tree_id)
        owner = f"sst-controller-{uuid.uuid4().hex[:8]}"
        if not self.store.acquire_lease(tree_id, owner):
            raise LeaseAcquisitionError(
                f"Cannot start guarded search: tree '{tree_id}' is already leased to another writer."
            )
        try:
            return await self._run_search_inner(tree_id)
        finally:
            self.store.release_lease(tree_id, owner)

    def report_outcome(
        self,
        tree_id: str,
        candidate_id: str,
        verdict: str,
        *,
        actor: str = "controller",
        evidence_refs: Sequence[str] | None = None,
        note: str | None = None,
        idempotency_key: str | None = None,
        event_id: str | None = None,
    ) -> int:
        """Records a domain outcome verdict verbatim as an OUTCOME_REPORTED event.

        Thin delegate of :func:`sst.sandbox.outcomes.report_outcome` against
        this controller's store: the verdict is stored verbatim under
        ``payload.domain_verdict`` with ``sst_authoritative: false`` and never
        satisfies promotion gates. Returns the appended sequence id.
        """
        from sst.sandbox.outcomes import report_outcome as _report_outcome

        return _report_outcome(
            self.store,
            tree_id=tree_id,
            candidate_id=candidate_id,
            verdict=verdict,
            evidence_refs=evidence_refs,
            actor=actor,
            note=note,
            idempotency_key=idempotency_key,
            event_id=event_id,
        )

    def _effective_policy(self) -> SearchPolicy:
        """Merges TaskPacket caller budgets with engine policy caps.

        The effective cap is the minimum of the enabled sides; 0/None
        disables a side (both disabled means unbounded for that resource).
        Iteration/depth/temperature settings always come from the policy.
        """
        enabled_tokens = [v for v in (self.task.token_budget, self.policy.max_token_budget) if v]
        enabled_cost = [v for v in (self.task.cost_budget_usd, self.policy.max_cost_usd) if v]
        enabled_time = [v for v in (self.task.time_budget_seconds, self.policy.max_time_seconds) if v]
        return self.policy.model_copy(
            update={
                "max_token_budget": min(enabled_tokens) if enabled_tokens else None,
                "max_cost_usd": min(enabled_cost) if enabled_cost else None,
                "max_time_seconds": min(enabled_time) if enabled_time else 0,
            }
        )

    def _gateway_bindings(self) -> list[GatewayBinding]:
        """Snapshots role/profile/model/kind wiring for the result envelope.

        Introspection only: caller gateways may hold arbitrary profile/route
        shapes (subclasses that override invoke can stuff non-ProviderProfile
        values), so every attribute read degrades to "UNKNOWN"/"" instead of
        raising.
        """
        bindings: list[GatewayBinding] = []
        routed_profiles: set[str] = set()
        for role, target in self.gateway.routes.items():
            profile_name = str(getattr(target, "profile", "") or "")
            model = str(getattr(target, "model", "") or "")
            profile = self.gateway.get_profile(profile_name) if profile_name else None
            kind = str(getattr(getattr(profile, "kind", None), "name", "UNKNOWN") or "UNKNOWN")
            bindings.append(
                GatewayBinding(
                    role=str(role),
                    profile=profile_name,
                    model=model,
                    kind=kind,
                )
            )
            routed_profiles.add(profile_name)
        for name, profile in self.gateway.profiles.items():
            if str(name) not in routed_profiles:
                kind = str(getattr(getattr(profile, "kind", None), "name", "UNKNOWN") or "UNKNOWN")
                model = str(getattr(profile, "selected_model", "") or "")
                bindings.append(
                    GatewayBinding(
                        role="*",
                        profile=str(name),
                        model=model,
                        kind=kind,
                    )
                )
        return bindings

    async def _run_search_inner(self, tree_id: str) -> SearchResult:
        """Executes the bounded search loop (single-writer guarded by run_search)."""
        start_time = time.perf_counter()
        self._provider_errors = []
        policy = self._effective_policy()
        gateway_bindings = self._gateway_bindings()

        # 1. Compile Context Capsule with AST interfaces and bounded scopes
        capsule = self.capsule_compiler.compile(
            goal=self.task.goal,
            target_files=self.task.allowed_paths,
            invariants=self.task.invariants,
        )

        # 2. Emit TREE_CREATED
        init_evt = SSTEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            tree_id=tree_id,
            kind=EventKind.TREE_CREATED,
            idempotency_key=f"init_{tree_id}",
            payload={
                "tree_id": tree_id,
                "root_goal": self.task.goal,
                "domain": "AUTOBUILD",
                "task_id": self.task.task_id,
                "base_commit": self.task.base_commit,
                "snapshot_hash": self.task.snapshot_hash,
                "root_node_id": f"root_{tree_id}",
                "allowed_paths": self.task.allowed_paths,
                "forbidden_paths": self.task.forbidden_paths,
                "invariants": capsule.invariants,
                "interfaces": capsule.interfaces,
                # Memory provenance fragment (additive; {} when no report).
                **memory_tree_payload_fragment(self.capsule_compiler.last_report),
            },
        )
        self.store.append_event(init_evt)

        # Frontier entries: (node_id, depth, proposal)
        frontier: list[tuple[str, int, CandidateProposal | None]] = [(f"root_{tree_id}", 0, None)]
        verified_candidates: dict[str, CandidateProposal] = {}
        evaluated_candidates: dict[str, CandidateProposal] = {}
        verifier_outcomes: dict[str, DeterministicGateResult] = {}
        scores: dict[str, ScoreBreakdown] = {}
        champion_id: str | None = None
        champion_score: float = -1.0
        synthesized_pairs: set[tuple[str, str]] = set()
        pruned_attempts: list[str] = []
        termination = TerminationReason.NO_CANDIDATE
        budget_violation_msg: str | None = None
        iterations_run = 0

        for iteration in range(policy.max_iterations):
            if self._cancelled:
                termination = TerminationReason.CANCELLED
                break

            self.budget_tracker.elapsed_seconds = time.perf_counter() - start_time
            self.budget_tracker.iterations_completed = iteration

            budget_violation = self.budget_tracker.check_budget(policy)
            if budget_violation:
                self.store.append_event(
                    SSTEvent(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        tree_id=tree_id,
                        kind=EventKind.BUDGET_EXHAUSTED,
                        idempotency_key=f"budget_{tree_id}_{iteration}",
                        payload={"reason": budget_violation},
                    )
                )
                termination = TerminationReason.BUDGET_EXHAUSTED
                budget_violation_msg = budget_violation
                break

            iterations_run += 1

            if not frontier:
                if not champion_id and iteration < policy.max_iterations:
                    frontier.append((f"root_{tree_id}", 0, None))
                else:
                    break

            current_parent, parent_depth, parent_proposal = frontier.pop(0)

            # Depth limit enforcement
            if parent_depth >= policy.max_depth:
                continue

            current_depth = parent_depth + 1

            # Determine expansion mode: Root/divergence (depth 0) vs Refinement (depth > 0)
            if parent_depth == 0:
                generated_proposals = await self._generate_divergent_candidates(
                    tree_id=tree_id,
                    iteration=iteration,
                    parent_id=current_parent,
                    capsule=capsule,
                    pruned_attempts=pruned_attempts[-5:],
                )
            else:
                generated_proposals = await self._generate_refined_candidates(
                    tree_id=tree_id,
                    iteration=iteration,
                    parent_id=current_parent,
                    current_depth=current_depth,
                    parent_proposal=parent_proposal,
                    capsule=capsule,
                )

            for proposal in generated_proposals:
                cand_id = proposal.candidate_id

                # Emit NODE_PROPOSED / CANDIDATE_CREATED
                self.store.append_event(
                    SSTEvent(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        tree_id=tree_id,
                        node_id=cand_id,
                        kind=EventKind.NODE_PROPOSED,
                        idempotency_key=f"proposed_{cand_id}",
                        payload={
                            "parent_id": current_parent,
                            "depth": current_depth,
                            "role": proposal.role,
                            "title": proposal.title,
                            "rationale": proposal.rationale,
                            "patch_diff": proposal.patch_diff,
                            "target_paths": proposal.target_paths,
                            "file_operations": proposal.file_operations,
                            "model_id": proposal.model_id,
                        },
                    )
                )

                # Sandbox Verification
                self.store.append_event(
                    SSTEvent(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        tree_id=tree_id,
                        node_id=cand_id,
                        kind=EventKind.VERIFIER_STARTED,
                        idempotency_key=f"ver_start_{cand_id}",
                        payload={},
                    )
                )

                source_dir = Path(self.task.source_repo_root)
                ver_res = await asyncio.to_thread(
                    self.executor.verify_candidate_proposal,
                    task=self.task,
                    proposal=proposal,
                    source_dir=source_dir,
                )
                evaluated_candidates[cand_id] = proposal
                verifier_outcomes[cand_id] = ver_res

                self.store.append_event(
                    SSTEvent(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        tree_id=tree_id,
                        node_id=cand_id,
                        kind=EventKind.VERIFIER_FINISHED,
                        idempotency_key=f"ver_fin_{cand_id}",
                        payload={
                            "passed": ver_res.passed,
                            "exit_code": ver_res.exit_code,
                            "stdout": ver_res.stdout[:500],
                            "stderr": ver_res.stderr[:500],
                            "duration_seconds": ver_res.duration_seconds,
                            "patch_hash": ver_res.patch_hash,
                            "post_patch_digest": ver_res.post_patch_digest,
                        },
                    )
                )

                if not ver_res.passed:
                    pruned_attempts.append(f"{proposal.title}: {ver_res.stderr[:100] or 'Verification failed'}")
                    continue

                verified_candidates[cand_id] = proposal

                # Cortex Critique & Value Scoring
                score_bd = await self._critique_candidate(proposal, ver_res, capsule, iteration=iteration)
                scores[cand_id] = score_bd

                self.store.append_event(
                    SSTEvent(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        tree_id=tree_id,
                        node_id=cand_id,
                        kind=EventKind.SCORE_RECORDED,
                        idempotency_key=f"score_{cand_id}",
                        payload={
                            "value_score": score_bd.normalized_reward,
                            "verdict": score_bd.critic_verdict or "CRITIQUE_FAILED",
                            "critique": score_bd.critic_rationale or "",
                        },
                    )
                )

                # Escalation trigger: file deletions or Cortex uncertainty
                has_deletions = (
                    any(op.get("action") == "delete" for op in proposal.file_operations)
                    or "deleted file mode" in proposal.patch_diff
                )
                is_uncertain = score_bd.critic_verdict == "ESCALATE_HUMAN"
                if is_uncertain or has_deletions:
                    escalation_reason = (
                        "Destructive file deletion detected in candidate proposal"
                        if has_deletions
                        else (score_bd.critic_rationale or "High architectural uncertainty or breaking change detected")
                    )
                    self.store.append_event(
                        SSTEvent(
                            event_id=f"evt_{uuid.uuid4().hex[:12]}",
                            tree_id=tree_id,
                            node_id=cand_id,
                            kind=EventKind.HUMAN_DECISION_REQUESTED,
                            idempotency_key=f"escalate_{cand_id}",
                            payload={
                                "reason": escalation_reason,
                                "verdict": score_bd.critic_verdict or "ESCALATE_HUMAN",
                                "has_deletions": has_deletions,
                            },
                        )
                    )

                if score_bd.normalized_reward > champion_score and score_bd.critic_verdict != "ESCALATE_HUMAN":
                    champion_score = score_bd.normalized_reward
                    champion_id = cand_id

                # Add to frontier for deeper refinement if high quality and depth allowed
                if score_bd.normalized_reward >= 0.7 and current_depth < policy.max_depth:
                    frontier.append((cand_id, current_depth, proposal))

            # Colimit Synthesis Trigger: check if multiple distinct high-scoring branches exist (>= 0.8)
            high_scoring = [
                cid
                for cid, s in scores.items()
                if s.normalized_reward >= 0.8 and cid in verified_candidates and s.critic_verdict != "ESCALATE_HUMAN"
            ]
            if len(high_scoring) >= 2:
                high_scoring.sort(key=lambda cid: scores[cid].normalized_reward, reverse=True)
                synth_pairs_count = 0
                max_synth_pairs_per_iter = 2
                for i in range(len(high_scoring)):
                    if synth_pairs_count >= max_synth_pairs_per_iter:
                        break
                    for j in range(i + 1, len(high_scoring)):
                        if synth_pairs_count >= max_synth_pairs_per_iter:
                            break
                        c_a_id = high_scoring[i]
                        c_b_id = high_scoring[j]
                        pair_key = (c_a_id, c_b_id) if c_a_id < c_b_id else (c_b_id, c_a_id)
                        if pair_key in synthesized_pairs:
                            continue
                        synthesized_pairs.add(pair_key)
                        synth_pairs_count += 1

                        cand_a = verified_candidates[c_a_id]
                        cand_b = verified_candidates[c_b_id]

                        synth_proposal = await self._synthesize_candidates(
                            tree_id=tree_id,
                            iteration=iteration,
                            cand_a=cand_a,
                            cand_b=cand_b,
                            capsule=capsule,
                        )
                        if not synth_proposal:
                            continue

                        # Emit SYNTHESIS_PROPOSED event
                        self.store.append_event(
                            SSTEvent(
                                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                                tree_id=tree_id,
                                node_id=synth_proposal.candidate_id,
                                kind=EventKind.SYNTHESIS_PROPOSED,
                                idempotency_key=f"synth_prop_{synth_proposal.candidate_id}",
                                payload={
                                    "parent_ids": [c_a_id, c_b_id],
                                    "title": synth_proposal.title,
                                    "rationale": synth_proposal.rationale,
                                    "patch_diff": synth_proposal.patch_diff,
                                    "target_paths": synth_proposal.target_paths,
                                    "file_operations": synth_proposal.file_operations,
                                    "model_id": synth_proposal.model_id,
                                },
                            )
                        )

                        # Verify synthesized proposal in sandbox
                        self.store.append_event(
                            SSTEvent(
                                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                                tree_id=tree_id,
                                node_id=synth_proposal.candidate_id,
                                kind=EventKind.VERIFIER_STARTED,
                                idempotency_key=f"ver_start_{synth_proposal.candidate_id}",
                                payload={},
                            )
                        )

                        ver_res_synth = await asyncio.to_thread(
                            self.executor.verify_candidate_proposal,
                            task=self.task,
                            proposal=synth_proposal,
                            source_dir=source_dir,
                        )
                        evaluated_candidates[synth_proposal.candidate_id] = synth_proposal
                        verifier_outcomes[synth_proposal.candidate_id] = ver_res_synth

                        self.store.append_event(
                            SSTEvent(
                                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                                tree_id=tree_id,
                                node_id=synth_proposal.candidate_id,
                                kind=EventKind.VERIFIER_FINISHED,
                                idempotency_key=f"ver_fin_{synth_proposal.candidate_id}",
                                payload={
                                    "passed": ver_res_synth.passed,
                                    "exit_code": ver_res_synth.exit_code,
                                    "stdout": ver_res_synth.stdout[:500],
                                    "stderr": ver_res_synth.stderr[:500],
                                    "duration_seconds": ver_res_synth.duration_seconds,
                                    "patch_hash": ver_res_synth.patch_hash,
                                    "post_patch_digest": ver_res_synth.post_patch_digest,
                                },
                            )
                        )

                        if ver_res_synth.passed:
                            verified_candidates[synth_proposal.candidate_id] = synth_proposal
                            score_synth = await self._critique_candidate(
                                synth_proposal, ver_res_synth, capsule, iteration=iteration
                            )
                            scores[synth_proposal.candidate_id] = score_synth

                            self.store.append_event(
                                SSTEvent(
                                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                                    tree_id=tree_id,
                                    node_id=synth_proposal.candidate_id,
                                    kind=EventKind.SCORE_RECORDED,
                                    idempotency_key=f"score_{synth_proposal.candidate_id}",
                                    payload={
                                        "value_score": score_synth.normalized_reward,
                                        "verdict": score_synth.critic_verdict or "CRITIQUE_FAILED",
                                        "critique": score_synth.critic_rationale or "",
                                    },
                                )
                            )

                            if (
                                score_synth.normalized_reward > champion_score
                                and score_synth.critic_verdict != "ESCALATE_HUMAN"
                            ):
                                champion_score = score_synth.normalized_reward
                                champion_id = synth_proposal.candidate_id

                            if score_synth.normalized_reward >= 0.7 and current_depth < policy.max_depth:
                                frontier.append((synth_proposal.candidate_id, current_depth, synth_proposal))

        # Emit winning recommendation if champion found
        champion: CandidateProposal | None = None
        if champion_id and champion_id in verified_candidates:
            self.store.append_event(
                SSTEvent(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    tree_id=tree_id,
                    node_id=champion_id,
                    kind=EventKind.PROMOTION_RECOMMENDED,
                    idempotency_key=f"promo_rec_{tree_id}_{champion_id}",
                    payload={
                        "champion_node_id": champion_id,
                        "score": champion_score,
                    },
                )
            )
            champion = verified_candidates[champion_id]

        if termination is TerminationReason.NO_CANDIDATE and champion is not None:
            termination = TerminationReason.CHAMPION_FOUND

        final_elapsed = time.perf_counter() - start_time

        if termination is TerminationReason.CANCELLED:
            self.store.append_event(
                SSTEvent(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    tree_id=tree_id,
                    kind=EventKind.SEARCH_CANCELLED,
                    idempotency_key=f"cancelled_{tree_id}",
                    payload={
                        "termination_reason": termination.value,
                        "iterations_completed": iterations_run,
                        "evaluated_count": len(evaluated_candidates),
                        "champion_node_id": champion_id,
                    },
                )
            )

        self.store.append_event(
            SSTEvent(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                tree_id=tree_id,
                kind=EventKind.SEARCH_COMPLETED,
                idempotency_key=f"completed_{tree_id}",
                payload={
                    "termination_reason": termination.value,
                    "champion_node_id": champion_id,
                    "champion_score": champion_score if champion is not None else None,
                    "evaluated_count": len(evaluated_candidates),
                    "verified_count": len(verified_candidates),
                    "provider_error_count": len(self._provider_errors),
                    "budget_violation": budget_violation_msg,
                    "budget": {
                        "tokens_consumed": self.budget_tracker.tokens_consumed,
                        "estimated_cost_usd": self.budget_tracker.estimated_cost_usd,
                        "elapsed_seconds": final_elapsed,
                        "iterations_completed": iterations_run,
                    },
                    "gateway_bindings": [b.model_dump(mode="json") for b in gateway_bindings],
                },
            )
        )

        evidence_refs: dict[str, list[str]] = {}
        for evt in self.store.get_events(tree_id):
            if evt.node_id:
                evidence_refs.setdefault(evt.node_id, []).append(evt.event_id)

        ranked = sorted(
            evaluated_candidates.values(),
            key=lambda p: scores[p.candidate_id].normalized_reward if p.candidate_id in scores else -1.0,
            reverse=True,
        )
        alternatives = [
            AlternativeCandidate(
                candidate=p,
                score=scores.get(p.candidate_id),
                verifier_outcome=verifier_outcomes.get(p.candidate_id),
                evidence_refs=evidence_refs.get(p.candidate_id, []),
            )
            for p in ranked
        ]

        return SearchResult(
            tree_id=tree_id,
            termination_reason=termination,
            champion=champion,
            alternatives=alternatives,
            budget_consumed=BudgetConsumed(
                tokens_consumed=self.budget_tracker.tokens_consumed,
                estimated_cost_usd=self.budget_tracker.estimated_cost_usd,
                elapsed_seconds=final_elapsed,
                iterations_completed=iterations_run,
            ),
            provider_errors=list(self._provider_errors),
            gateway_bindings=gateway_bindings,
            event_log_ref=f"sqlite:{self.store.db_path}::tree:{tree_id}",
        )

    def _record_provider_error(
        self,
        *,
        tree_id: str,
        role: str,
        error: Exception,
        iteration: int | None,
        node_id: str | None = None,
    ) -> None:
        """Records a provider failure as a PROVIDER_ERROR event plus an envelope record."""
        if isinstance(error, ProviderGatewayError):
            category = error.category
            remediation = error.remediation
            message = error.message
            profile = error.profile
        else:
            category = f"{role}_error"
            remediation = "Model invocation failed; the controller fell back to deterministic scoring."
            message = str(error)
            profile = None
        self._provider_errors.append(
            ProviderErrorRecord(
                role=role,
                category=category,
                remediation=remediation,
                message=message,
                profile=profile,
                iteration=iteration,
            )
        )
        self.store.append_event(
            SSTEvent(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                tree_id=tree_id,
                node_id=node_id,
                kind=EventKind.PROVIDER_ERROR,
                idempotency_key=f"provider_err_{uuid.uuid4().hex[:12]}",
                payload={
                    "role": role,
                    "category": category,
                    "remediation": remediation,
                    "message": message,
                    "profile": profile,
                    "iteration": iteration,
                },
            )
        )

    async def _generate_divergent_candidates(
        self,
        tree_id: str,
        iteration: int,
        parent_id: str,
        capsule: AuDHDContextCapsule,
        pruned_attempts: list[str] | None = None,
    ) -> list[CandidateProposal]:
        """Invokes role 'diverge' (ADHD Explorer) with render_adhd_explorer_prompt."""
        prompt = render_adhd_explorer_prompt(
            goal=self.task.goal,
            capsule=capsule,
            domain=DomainMode.AUTOBUILD,
            branch_count=self.policy.branching_factor,
            prior_attempts=pruned_attempts,
        )

        req = GatewayRequest(
            role="diverge",
            messages=[{"role": "user", "content": prompt}],
            temperature=self.policy.temperature_diverge,
            max_tokens=self._role_max_tokens(2048),
        )

        proposals: list[CandidateProposal] = []
        try:
            resp = await asyncio.to_thread(self.gateway.invoke, req)
            self._accumulate_usage(resp)

            parsed = self._parse_json_dict(resp.content)
            branches = parsed.get("branches", [])

            target_path = self.task.allowed_paths[0] if self.task.allowed_paths else "main.py"

            if isinstance(branches, list) and branches:
                for b_idx, branch in enumerate(branches[: self.policy.branching_factor]):
                    cand_id = f"cand_{tree_id}_{iteration}_{b_idx}"
                    code_body = self._clean_code(str(branch.get("proposed_changes", "")))
                    if not code_body:
                        continue
                    proposals.append(
                        CandidateProposal(
                            candidate_id=cand_id,
                            tree_id=tree_id,
                            parent_ids=[parent_id],
                            role="DIVERGE",
                            title=str(branch.get("strategy_title", f"Proposal {cand_id}")),
                            rationale=str(branch.get("hypothesis_or_rationale", "Divergent exploration candidate")),
                            target_paths=[target_path],
                            patch_diff=code_body,
                            model_id=resp.model,
                        )
                    )
            else:
                # Raw code fallback
                cand_id = f"cand_{tree_id}_{iteration}_0"
                code_body = self._clean_code(resp.content)
                if code_body:
                    proposals.append(
                        CandidateProposal(
                            candidate_id=cand_id,
                            tree_id=tree_id,
                            parent_ids=[parent_id],
                            role="DIVERGE",
                            title=f"Proposal {cand_id}",
                            rationale="Divergent exploration candidate",
                            target_paths=[target_path],
                            patch_diff=code_body,
                            model_id=resp.model,
                        )
                    )
        except ProviderGatewayError as e:
            logger.warning(f"Model gateway error during diverge: {e.message}")
            self._record_provider_error(tree_id=tree_id, role="diverge", error=e, iteration=iteration)

        return proposals

    async def _generate_refined_candidates(
        self,
        tree_id: str,
        iteration: int,
        parent_id: str,
        current_depth: int,
        parent_proposal: CandidateProposal | None,
        capsule: AuDHDContextCapsule,
    ) -> list[CandidateProposal]:
        """Invokes role 'refine' (ASD Exploiter @ low temperature T=0.05) with render_asd_exploiter_prompt."""
        mutation_title = parent_proposal.title if parent_proposal else f"Candidate {parent_id}"
        mutation_content = parent_proposal.patch_diff if parent_proposal else ""

        prompt = render_asd_exploiter_prompt(
            parent_goal=self.task.goal,
            mutation_title=mutation_title,
            mutation_content=mutation_content,
            capsule=capsule,
            domain=DomainMode.AUTOBUILD,
        )

        req = GatewayRequest(
            role="refine",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.05,
            max_tokens=self._role_max_tokens(2048),
        )

        proposals: list[CandidateProposal] = []
        try:
            resp = await asyncio.to_thread(self.gateway.invoke, req)
            self._accumulate_usage(resp)

            parsed = self._parse_json_dict(resp.content)
            refined_title = str(parsed.get("refined_title", f"Refined {mutation_title}"))
            refactoring_notes = str(parsed.get("refactoring_notes", "ASD first-principles refinement"))
            code_body = self._clean_code(str(parsed.get("executable_content", resp.content)))

            target_path = (
                parent_proposal.target_paths[0]
                if (parent_proposal and parent_proposal.target_paths)
                else (self.task.allowed_paths[0] if self.task.allowed_paths else "main.py")
            )

            cand_id = f"cand_{tree_id}_{iteration}_refine_0"
            if code_body:
                proposals.append(
                    CandidateProposal(
                        candidate_id=cand_id,
                        tree_id=tree_id,
                        parent_ids=[parent_id],
                        role="REFINE",
                        title=refined_title,
                        rationale=refactoring_notes,
                        target_paths=[target_path],
                        patch_diff=code_body,
                        model_id=resp.model,
                    )
                )
        except ProviderGatewayError as e:
            logger.warning(f"Model gateway error during refine: {e.message}")
            self._record_provider_error(tree_id=tree_id, role="refine", error=e, iteration=iteration)

        return proposals

    async def _synthesize_candidates(
        self,
        tree_id: str,
        iteration: int,
        cand_a: CandidateProposal,
        cand_b: CandidateProposal,
        capsule: AuDHDContextCapsule,
    ) -> CandidateProposal | None:
        """Invokes role 'synthesize' (Colimit Synthesizer) with render_cortex_synthesizer_prompt."""
        node_a = SSTNode(
            node_id=cand_a.candidate_id,
            tree_id=tree_id,
            depth=1,
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.DIVERGE,
            title=cand_a.title,
            payload_type=PayloadType.CODE_DIFF,
            content=cand_a.patch_diff,
        )
        node_b = SSTNode(
            node_id=cand_b.candidate_id,
            tree_id=tree_id,
            depth=1,
            domain=DomainMode.AUTOBUILD,
            role=NodeRole.REFINE,
            title=cand_b.title,
            payload_type=PayloadType.CODE_DIFF,
            content=cand_b.patch_diff,
        )

        synthesis_guidance = f"Blend complementary strengths of '{cand_a.title}' and '{cand_b.title}' into a single unified implementation."

        prompt = render_cortex_synthesizer_prompt(
            goal=self.task.goal,
            capsule=capsule,
            node_a=node_a,
            node_b=node_b,
            synthesis_guidance=synthesis_guidance,
        )

        req = GatewayRequest(
            role="synthesize",
            messages=[{"role": "user", "content": prompt}],
            temperature=self.policy.temperature_synthesize,
            max_tokens=self._role_max_tokens(2048),
        )

        try:
            resp = await asyncio.to_thread(self.gateway.invoke, req)
            self._accumulate_usage(resp)

            parsed = self._parse_json_dict(resp.content)
            synth_title = str(parsed.get("synthesized_title", f"Synthesized [{cand_a.title} + {cand_b.title}]"))
            synth_rationale = str(parsed.get("synthesis_rationale", "Colimit dialectic synthesis"))
            code_body = self._clean_code(str(parsed.get("executable_content", resp.content)))

            target_path = self.task.allowed_paths[0] if self.task.allowed_paths else "main.py"
            cand_id = f"cand_{tree_id}_{iteration}_synth_{cand_a.candidate_id[-4:]}_{cand_b.candidate_id[-4:]}"

            if code_body:
                return CandidateProposal(
                    candidate_id=cand_id,
                    tree_id=tree_id,
                    parent_ids=[cand_a.candidate_id, cand_b.candidate_id],
                    role="SYNTHESIZE",
                    title=synth_title,
                    rationale=synth_rationale,
                    target_paths=[target_path],
                    patch_diff=code_body,
                    model_id=resp.model,
                )
        except ProviderGatewayError as e:
            logger.warning(f"Model gateway error during synthesize: {e.message}")
            self._record_provider_error(tree_id=tree_id, role="synthesize", error=e, iteration=iteration)

        return None

    async def _generate_divergent_candidate(
        self, tree_id: str, candidate_id: str, parent_id: str
    ) -> CandidateProposal | None:
        """Backwards-compatible helper to generate a single divergent proposal."""
        capsule = self.capsule_compiler.compile(
            goal=self.task.goal,
            target_files=self.task.allowed_paths,
            invariants=self.task.invariants,
        )
        proposals = await self._generate_divergent_candidates(
            tree_id=tree_id,
            iteration=0,
            parent_id=parent_id,
            capsule=capsule,
        )
        if proposals:
            proposals[0] = proposals[0].model_copy(update={"candidate_id": candidate_id})
            return proposals[0]
        return None

    async def _critique_candidate(
        self,
        proposal: CandidateProposal,
        ver_res: Any,
        capsule: AuDHDContextCapsule | None = None,
        iteration: int | None = None,
    ) -> ScoreBreakdown:
        """Scores a candidate using live Cortex Critic model evaluation when available."""
        if not ver_res.passed:
            return ScoreBreakdown(
                passed_hard_gates=False,
                hard_gates={"verifier_passed": False},
                soft_scores={"value_score": 0.0},
                normalized_reward=0.0,
                critic_verdict="PRUNE",
                critic_rationale=f"Deterministic verifier failed: {ver_res.stderr or ver_res.failure_reason}",
            )

        critique_route = self.gateway.get_route("critique")
        if critique_route or len(self.gateway.profiles) == 1:
            node = SSTNode(
                node_id=proposal.candidate_id,
                tree_id=proposal.tree_id,
                depth=1,
                domain=DomainMode.AUTOBUILD,
                role=NodeRole.DIVERGE if proposal.role == "DIVERGE" else NodeRole.REFINE,
                title=proposal.title,
                payload_type=PayloadType.CODE_DIFF,
                content=proposal.patch_diff,
            )
            prompt = (
                render_cortex_critic_prompt(
                    goal=self.task.goal,
                    capsule=capsule or AuDHDContextCapsule(goal=self.task.goal),
                    surviving_candidates=[node],
                    domain=DomainMode.AUTOBUILD,
                )
                if capsule
                else (
                    f"You are the Executive Cortex Critic evaluating a code candidate.\n"
                    f"Goal: {self.task.goal}\n"
                    f"Invariants: {self.task.invariants}\n"
                    f"Proposed Implementation:\n{proposal.patch_diff}\n\n"
                    f"Provide your critique. Respond with a JSON object: "
                    f'{{"value_score": 0.0-1.0, "verdict": "APPROVE"|"PRUNE"|"ESCALATE_HUMAN", "rationale": "..."}}'
                )
            )
            req = GatewayRequest(
                role="critique",
                messages=[{"role": "user", "content": prompt}],
                temperature=self.policy.temperature_critique,
                max_tokens=self._role_max_tokens(1024),
            )
            try:
                resp = await asyncio.to_thread(self.gateway.invoke, req)
                self._accumulate_usage(resp)

                parsed = self._parse_json_dict(resp.content)
                if "evaluations" not in parsed and "value_score" not in parsed:
                    raise ValueError("malformed critique response: missing value_score/evaluations")
                if "evaluations" in parsed and isinstance(parsed["evaluations"], list) and parsed["evaluations"]:
                    eval_item = parsed["evaluations"][0]
                    val_score = float(eval_item.get("value_score", 0.85))
                    verdict = str(eval_item.get("verdict", "APPROVE" if val_score >= 0.7 else "PRUNE"))
                    rationale = str(eval_item.get("critique", "Evaluated by Cortex Critic"))
                else:
                    val_score = float(parsed.get("value_score", 0.85))
                    verdict = str(parsed.get("verdict", "APPROVE" if val_score >= 0.7 else "PRUNE"))
                    rationale = str(parsed.get("rationale", "Evaluated by Cortex Critic"))

                return ScoreBreakdown(
                    passed_hard_gates=True,
                    hard_gates={"verifier_passed": True},
                    soft_scores={"value_score": val_score},
                    normalized_reward=min(1.0, max(0.0, val_score)),
                    critic_verdict=verdict,
                    critic_rationale=rationale,
                )
            except Exception as e:
                logger.warning(f"Cortex Critic invocation fallback: {e}")
                self._record_provider_error(
                    tree_id=proposal.tree_id,
                    role="critique",
                    error=e,
                    iteration=iteration,
                    node_id=proposal.candidate_id,
                )
                return ScoreBreakdown(
                    passed_hard_gates=True,
                    hard_gates={"verifier_passed": True},
                    soft_scores={"value_score": 0.5},
                    normalized_reward=0.5,
                    critic_verdict="CRITIQUE_FAILED",
                    critic_rationale=(
                        f"Critique unavailable ({e}); verifier-only fallback rank 0.5. "
                        "No semantic approval was granted."
                    ),
                )

        # No critique route configured: verifier-gated but explicitly unreviewed.
        return ScoreBreakdown(
            passed_hard_gates=True,
            hard_gates={"verifier_passed": True},
            soft_scores={"value_score": 0.5},
            normalized_reward=0.5,
            critic_verdict="CRITIQUE_FAILED",
            critic_rationale=(
                "No critique route configured; verifier-only fallback rank 0.5. No semantic approval was granted."
            ),
        )

    @staticmethod
    def _clean_code(code_body: str) -> str:
        code_body = code_body.strip()
        match = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", code_body)
        if match:
            return match.group(1).strip()
        return code_body

    @staticmethod
    def _parse_json_dict(raw_text: str) -> dict[str, Any]:
        raw_text = raw_text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            res = json.loads(raw_text)
            return res if isinstance(res, dict) else {}
        except Exception:
            return {}
