"""Reflex Browser Closed-Loop Automation Engine (V1).

Orchestrates end-to-end discrete event loop:
Perception -> Proposal -> Host Kernel Authorization -> Lease Issue -> Physical Dispatch ->
Settlement -> Independent Verification -> Outcome Classification & Reconciliation ->
Episode Journaling -> Budget & Termination Checks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import inspect
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from reflex.episodes.journal import EpisodeJournalPort, LocalEpisodeJournal
from reflex.grounding.browser_grounder import (
    BrowserGroundingEngine,
    BrowserGroundingPort,
    GroundingQuery,
)
from reflex.host.identity.lease_manager import ActionLeaseManager
from reflex.host.kernel.host_kernel import (
    DispatchState,
    EmergencyHaltError,
    HostControlKernel,
    KernelDispatchResult,
    PolicyRejectedError,
)
from reflex.orchestration.session_manager import (
    BrowserSession,
    BrowserSessionConfig,
    BrowserSessionManager,
)
from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.ports.verification import VerificationEnginePort, VerificationPort
from reflex.schemas.actions import (
    ActionType,
    NormalizedCoords,
    SafetyClass,
    TypedAction,
)
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.memory import TransitionTuple
from reflex.schemas.policy import CapabilityScope
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.reconciliation import ReconciliationEngine, ReconciliationReport
from reflex.verification.verifier import AssertionRule, IndependentVerifier, VerificationResult


class TaskStatus(str, Enum):
    """Execution status of an autonomous browser task."""
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"
    HALTED_POLICY = "halted_policy"
    HALTED_SURPRISE = "halted_surprise"


@dataclass(frozen=True)
class TaskGoal:
    """User instruction and execution parameters for an autonomous task."""
    task_id: str
    instruction: str
    target_url: str
    max_steps: int = 50
    step_timeout_ms: float = 10000.0
    task_timeout_ms: float = 300000.0  # 5 minutes
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "instruction": self.instruction,
            "target_url": self.target_url,
            "max_steps": self.max_steps,
            "step_timeout_ms": self.step_timeout_ms,
            "task_timeout_ms": self.task_timeout_ms,
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskGoal:
        return cls(
            task_id=str(data["task_id"]),
            instruction=str(data.get("instruction", "")),
            target_url=str(data.get("target_url", "")),
            max_steps=int(data.get("max_steps", 50)),
            step_timeout_ms=float(data.get("step_timeout_ms", 10000.0)),
            task_timeout_ms=float(data.get("task_timeout_ms", 300000.0)),
            parameters=dict(data.get("parameters", {})),
        )


@dataclass(frozen=True)
class TaskExecutionReport:
    """Final summary of closed-loop execution emitted at task completion."""
    task_id: str
    status: TaskStatus
    total_steps: int
    duration_ms: float
    final_url: str
    episode_id: str
    error_summary: Optional[str] = None
    verification_passed_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "total_steps": self.total_steps,
            "duration_ms": self.duration_ms,
            "final_url": self.final_url,
            "episode_id": self.episode_id,
            "error_summary": self.error_summary,
            "verification_passed_count": self.verification_passed_count,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskExecutionReport:
        raw_status = data.get("status", TaskStatus.COMPLETED.value)
        status = TaskStatus(raw_status) if raw_status in TaskStatus._value2member_map_ else TaskStatus(raw_status.lower())
        return cls(
            task_id=str(data["task_id"]),
            status=status,
            total_steps=int(data.get("total_steps", 0)),
            duration_ms=float(data.get("duration_ms", 0.0)),
            final_url=str(data.get("final_url", "")),
            episode_id=str(data.get("episode_id", "")),
            error_summary=data.get("error_summary"),
            verification_passed_count=int(data.get("verification_passed_count", 0)),
            metadata=dict(data.get("metadata", {})),
        )


class BrowserClosedLoopV1:
    """Orchestrates end-to-end closed-loop browser automation tasks."""

    MODAL_DISMISSAL_LABELS = [
        "accept all",
        "accept cookies",
        "accept",
        "agree",
        "i agree",
        "allow all",
        "allow",
        "got it",
        "ok",
        "close",
        "dismiss",
        "x",
        "continue",
        "reject",
        "decline",
    ]

    def __init__(
        self,
        kernel: HostControlKernel,
        observation_port: ObservationPort,
        grounder: Optional[BrowserGroundingEngine] = None,
        verifier: Optional[IndependentVerifier] = None,
        journal: Optional[EpisodeJournalPort] = None,
        session_manager: Optional[BrowserSessionManager] = None,
        clock: Optional[ClockPort] = None,
        reconciler: Optional[ReconciliationEngine] = None,
        surprise_threshold: float = 0.8,
        halt_on_surprise: bool = False,
        auto_dismiss_modals: bool = True,
        enable_pre_dispatch_regrounding: bool = True,
        regrounding_tolerance_px: int = 5,
        max_consecutive_errors: int = 3,
    ) -> None:
        self.kernel = kernel
        self.observation_port = observation_port
        self.grounder = grounder or BrowserGroundingEngine()
        self.verifier = verifier
        self.journal = journal or LocalEpisodeJournal(db_path=":memory:")
        self.session_manager = session_manager or BrowserSessionManager()
        self.clock: ClockPort = clock or SystemClock()
        self.reconciler = reconciler or ReconciliationEngine(
            observation_port=observation_port,
            clock=self.clock,
        )
        self.surprise_threshold = surprise_threshold
        self.halt_on_surprise = halt_on_surprise
        self.auto_dismiss_modals = auto_dismiss_modals
        self.enable_pre_dispatch_regrounding = enable_pre_dispatch_regrounding
        self.regrounding_tolerance_px = regrounding_tolerance_px
        self.max_consecutive_errors = max_consecutive_errors

    async def run_task(
        self,
        goal: TaskGoal,
        proposal_generator: Any,
        session: Optional[BrowserSession] = None,
        session_id: Optional[str] = None,
    ) -> TaskExecutionReport:
        """Executes the closed-loop autonomous browser automation task to completion or budget exhaustion."""
        start_mono_ms = self.clock.monotonic_ms()
        start_wall_ms = self.clock.now_ms()
        sid = session_id or (session.session_id if session else f"sess_{goal.task_id}")
        episode_id = f"ep_{goal.task_id}_{int(start_wall_ms)}"

        # 1. Initialize Episode in Journal
        await self.journal.start_episode(
            episode_id=episode_id,
            session_id=sid,
            task_goal=goal.instruction,
            start_time_ms=start_wall_ms,
            metadata={"target_url": goal.target_url, "parameters": goal.parameters},
        )

        owned_session: Optional[BrowserSession] = None
        active_session = session

        # If no session provided, create one managed session
        if active_session is None:
            owned_session = await self.session_manager.create_session(session_id=sid)
            active_session = owned_session

        step_index = 0
        action_sequence_counter = 0
        verification_passed_count = 0
        consecutive_errors = 0
        last_error_summary: Optional[str] = None
        current_state: Optional[CanonicalUIGraph] = None
        status = TaskStatus.COMPLETED

        try:
            # 2. Initial state capture S_0
            try:
                current_state = await self.observation_port.capture_state()
            except Exception as e:
                current_state = CanonicalUIGraph(
                    timestamp_ms=self.clock.now_ms(),
                    nodes={},
                    url=goal.target_url,
                )

            # 3. Main Discrete Event Loop
            while True:
                now_mono = self.clock.monotonic_ms()
                elapsed_ms = now_mono - start_mono_ms

                # Budget Check A: Task Timeout
                if elapsed_ms >= goal.task_timeout_ms:
                    status = TaskStatus.MAX_STEPS_EXCEEDED
                    last_error_summary = f"Task timeout reached ({elapsed_ms:.1f}ms >= {goal.task_timeout_ms}ms)"
                    break

                # Budget Check B: Max Steps
                if step_index >= goal.max_steps:
                    status = TaskStatus.MAX_STEPS_EXCEEDED
                    last_error_summary = f"Max step budget exceeded ({step_index} >= {goal.max_steps})"
                    break

                # 4. Generate Candidate Action Proposal
                proposal = await self._generate_candidate_proposal(
                    generator=proposal_generator,
                    goal=goal,
                    current_state=current_state,
                    step_index=step_index,
                    session_id=sid,
                    action_sequence_index=action_sequence_counter + 1,
                )

                # None proposal signifies goal reached / completed trajectory
                if proposal is None:
                    status = TaskStatus.COMPLETED
                    break

                action_sequence_counter += 1
                step_start_time = self.clock.now_ms()
                before_state = current_state

                # 5. Pre-Dispatch Target Re-grounding & Staleness Check
                proposal, is_stale = await self._reground_proposal_if_needed(
                    proposal=proposal,
                    current_state=current_state,
                )

                if is_stale:
                    # Stale target detected! Do not blindly click stale coordinates.
                    last_error_summary = f"Stale target intercepted: element '{proposal.action.target_node_id}' vanished or mutated before dispatch"
                    consecutive_errors += 1

                    # Diagnostic reconciliation
                    recon_report = await self.reconciler.reconcile(
                        before_state=before_state,
                        action=proposal.action,
                        action_id=proposal.identity.action_id,
                        outcome=OutcomeClass.ERROR,
                        verification_details=last_error_summary,
                    )

                    # Record intercepted transition in journal
                    intercept_delta = StateDelta(outcome_class=OutcomeClass.ERROR)
                    intercept_tx = TransitionTuple(
                        transition_id=f"tx_{episode_id}_{step_index}",
                        episode_id=episode_id,
                        step_index=step_index,
                        timestamp_ms=step_start_time,
                        ui_state_hash=before_state.compute_state_hash() if before_state else "hash_empty",
                        goal_text=goal.instruction,
                        goal_embedding=[],
                        visual_embedding=None,
                        action=proposal.action,
                        next_ui_state_hash=before_state.compute_state_hash() if before_state else "hash_empty",
                        delta=intercept_delta,
                        duration_ms=self.clock.now_ms() - step_start_time,
                        surprise_score=1.0,
                        provenance={"interception": "stale_target", "cause": last_error_summary},
                    )
                    await self.journal.record_transition(intercept_tx)

                    if consecutive_errors >= self.max_consecutive_errors:
                        status = TaskStatus.FAILED
                        break

                    # Re-capture fresh state and loop back to planner
                    try:
                        current_state = await self.observation_port.capture_state()
                    except Exception:
                        pass
                    step_index += 1
                    continue

                # 6. Submit Proposal to Host Control Kernel
                try:
                    dispatch_result: KernelDispatchResult = await self.kernel.submit_proposal(proposal)
                except EmergencyHaltError as ehe:
                    status = TaskStatus.HALTED_POLICY
                    last_error_summary = f"Emergency halt triggered: {ehe}"
                    break
                except Exception as ex:
                    dispatch_result = KernelDispatchResult(
                        identity=proposal.identity,
                        outcome=OutcomeClass.ERROR,
                        execution_latency_ms=self.clock.now_ms() - step_start_time,
                        verification_passed=False,
                        requires_reconciliation=True,
                        error_message=str(ex),
                        state=DispatchState.RETIRED_FAILED,
                    )

                # Check Policy Rejection
                if dispatch_result.error_message and (
                    "policy rejected" in dispatch_result.error_message.lower()
                    or "missing required capability" in dispatch_result.error_message.lower()
                    or "blacklisted" in dispatch_result.error_message.lower()
                ):
                    status = TaskStatus.HALTED_POLICY
                    last_error_summary = dispatch_result.error_message
                    break

                # 7. Post-Action Settlement & Independent Verification Observation
                try:
                    after_state = await self.observation_port.capture_state()
                except Exception:
                    after_state = current_state

                # Check verification result
                if dispatch_result.verification_passed:
                    verification_passed_count += 1
                    consecutive_errors = 0
                    last_error_summary = None
                else:
                    consecutive_errors += 1
                    last_error_summary = dispatch_result.error_message

                # 8. Compute Surprise Score
                surprise_score = self._compute_surprise_score(
                    expected_delta=proposal.expected_delta,
                    actual_delta=dispatch_result.state_delta,
                    outcome=dispatch_result.outcome,
                )

                # 9. Loss-Free Journaling of Transition
                transition = TransitionTuple(
                    transition_id=f"tx_{episode_id}_{step_index}",
                    episode_id=episode_id,
                    step_index=step_index,
                    timestamp_ms=step_start_time,
                    ui_state_hash=before_state.compute_state_hash() if before_state else "hash_empty",
                    goal_text=goal.instruction,
                    goal_embedding=[],
                    visual_embedding=None,
                    action=proposal.action,
                    next_ui_state_hash=after_state.compute_state_hash() if after_state else "hash_empty",
                    delta=dispatch_result.state_delta or StateDelta(outcome_class=dispatch_result.outcome),
                    duration_ms=dispatch_result.execution_latency_ms,
                    surprise_score=surprise_score,
                    provenance={
                        "lease_id": dispatch_result.receipt.lease_id if dispatch_result.receipt else None,
                        "adapter": dispatch_result.receipt.adapter_name if dispatch_result.receipt else None,
                        "outcome": dispatch_result.outcome.value,
                    },
                )
                await self.journal.record_transition(transition)

                # 10. Surprise Circuit Breaker Check
                if surprise_score > self.surprise_threshold and self.halt_on_surprise:
                    status = TaskStatus.HALTED_SURPRISE
                    last_error_summary = f"Circuit breaker tripped: surprise score {surprise_score:.2f} > threshold {self.surprise_threshold:.2f}"
                    break

                # 11. Modal Interception & Trajectory Resumption
                if dispatch_result.outcome == OutcomeClass.MODAL_APPEARED or self._has_active_modal(after_state):
                    if self.auto_dismiss_modals:
                        action_sequence_counter += 1
                        dismissed, post_dismiss_state = await self._dismiss_active_modal(
                            state=after_state,
                            session_id=sid,
                            step_index=action_sequence_counter,
                            episode_id=episode_id,
                            goal=goal,
                        )
                        if dismissed and post_dismiss_state is not None:
                            after_state = post_dismiss_state
                            consecutive_errors = 0
                            last_error_summary = None
                            step_index += 1  # Modal dismissal consumed a sub-step

                # 12. State Reconciliation on Failures
                if dispatch_result.requires_reconciliation:
                    recon_report = await self.reconciler.reconcile(
                        before_state=before_state,
                        action=proposal.action,
                        action_id=proposal.identity.action_id,
                        outcome=dispatch_result.outcome,
                        verification_details=dispatch_result.error_message or "",
                    )
                    if consecutive_errors >= self.max_consecutive_errors:
                        status = TaskStatus.FAILED
                        last_error_summary = f"Exceeded consecutive error limit ({consecutive_errors} errors): {recon_report.inferred_cause}"
                        break

                # Update State S_t <- S_{t+1}
                current_state = after_state
                step_index += 1

        finally:
            # 13. Clean Shutdown and Episode Finalization
            total_duration_ms = self.clock.monotonic_ms() - start_mono_ms
            final_url = current_state.url or goal.target_url if current_state else goal.target_url

            await self.journal.end_episode(
                episode_id=episode_id,
                final_outcome=status.value,
                end_time_ms=self.clock.now_ms(),
                metadata={"total_steps": step_index, "error_summary": last_error_summary},
            )

            # Close internally owned session
            if owned_session is not None:
                await owned_session.close()

        final_error = last_error_summary if status != TaskStatus.COMPLETED else None
        return TaskExecutionReport(
            task_id=goal.task_id,
            status=status,
            total_steps=step_index,
            duration_ms=total_duration_ms,
            final_url=final_url,
            episode_id=episode_id,
            error_summary=final_error,
            verification_passed_count=verification_passed_count,
            metadata={"consecutive_errors": consecutive_errors},
        )

    async def _generate_candidate_proposal(
        self,
        generator: Any,
        goal: TaskGoal,
        current_state: Optional[CanonicalUIGraph],
        step_index: int,
        session_id: str,
        action_sequence_index: Optional[int] = None,
    ) -> Optional[ActionProposal]:
        """Invokes the candidate proposal generator and wraps return values into validated ActionProposal."""
        proposal_raw = None
        current_g = current_state or CanonicalUIGraph(timestamp_ms=self.clock.now_ms(), nodes={})
        seq_idx = action_sequence_index if action_sequence_index is not None else (step_index + 1)

        if isinstance(generator, (list, tuple)):
            if step_index < len(generator):
                proposal_raw = generator[step_index]
            else:
                return None
        elif hasattr(generator, "generate_proposal"):
            res = generator.generate_proposal(goal, current_g, step_index)
            proposal_raw = await res if inspect.isawaitable(res) else res
        elif callable(generator):
            res = generator(goal, current_g, step_index)
            proposal_raw = await res if inspect.isawaitable(res) else res
        else:
            proposal_raw = None

        if proposal_raw is None:
            return None

        # If generator returned a TypedAction, wrap into ActionProposal
        if isinstance(proposal_raw, TypedAction):
            identity = ActionIdentity.create(session_id=session_id, step_index=seq_idx)
            required_scopes = {CapabilityScope.BROWSER_NAVIGATE} if proposal_raw.action_type == ActionType.NAVIGATE else {CapabilityScope.BROWSER_INTERACT}
            return ActionProposal(
                identity=identity,
                action=proposal_raw,
                required_scopes=required_scopes,
            )

        # If generator returned an ActionProposal, ensure monotonic step index and session_id
        if isinstance(proposal_raw, ActionProposal):
            identity = proposal_raw.identity
            if identity.session_id != session_id or identity.step_index != seq_idx:
                new_identity = ActionIdentity.create(session_id=session_id, step_index=seq_idx)
                return ActionProposal(
                    identity=new_identity,
                    action=proposal_raw.action,
                    expected_delta=proposal_raw.expected_delta,
                    required_scopes=proposal_raw.required_scopes,
                    reasoning_summary=proposal_raw.reasoning_summary,
                    metadata=proposal_raw.metadata,
                )
            return proposal_raw

        return None

    async def _reground_proposal_if_needed(
        self,
        proposal: ActionProposal,
        current_state: Optional[CanonicalUIGraph],
    ) -> Tuple[ActionProposal, bool]:
        """Validates target element stability and re-grounds immediately prior to physical dispatch.

        Returns (updated_proposal, is_stale).
        """
        if not self.enable_pre_dispatch_regrounding or current_state is None:
            return proposal, False

        action = proposal.action
        target_id = action.target_node_id

        # Actions without target node (e.g. NAVIGATE, WAIT, NOOP, or keyboard typing) don't need grounding
        if not target_id and action.action_type in (ActionType.NAVIGATE, ActionType.WAIT, ActionType.NOOP):
            return proposal, False

        # If target node exists in current state
        if target_id and target_id in current_state.nodes:
            node = current_state.nodes[target_id]
            if not node.is_enabled or node.bounds.width <= 0 or node.bounds.height <= 0:
                # Disabled or zero-dimension target is considered stale
                return proposal, True

            # If action has coordinates, verify if bounds shifted
            if action.coords is not None:
                vw, vh = current_state.viewport_size
                curr_px = action.coords.to_pixel(vw, vh)
                cx, cy = node.bounds.center
                if abs(curr_px[0] - cx) > self.regrounding_tolerance_px or abs(curr_px[1] - cy) > self.regrounding_tolerance_px:
                    # Update coordinates to fresh node center
                    norm_coords = NormalizedCoords(x=cx / max(vw, 1), y=cy / max(vh, 1))
                    updated_action = TypedAction(
                        action_type=action.action_type,
                        target_node_id=action.target_node_id,
                        coords=norm_coords,
                        text_payload=action.text_payload,
                        key_code=action.key_code,
                        scroll_delta=action.scroll_delta,
                        target_label=action.target_label,
                        safety_class=action.safety_class,
                        metadata=action.metadata,
                    )
                    return ActionProposal(
                        identity=proposal.identity,
                        action=updated_action,
                        expected_delta=proposal.expected_delta,
                        required_scopes=proposal.required_scopes,
                        reasoning_summary=proposal.reasoning_summary,
                        metadata=proposal.metadata,
                    ), False

            return proposal, False

        # If target node ID is missing from current state, attempt semantic re-grounding
        target_label = action.target_label or action.metadata.get("target_label") or action.metadata.get("label") or ""
        if target_label and self.grounder:
            query = GroundingQuery(
                target_text=target_label,
                target_role=action.metadata.get("target_role"),
                container_hint=action.metadata.get("container_hint"),
                min_confidence=0.75,
            )
            grounding_res = self.grounder.resolve_target(current_state, query)
            if grounding_res is not None:
                new_node = grounding_res.target_node
                vw, vh = current_state.viewport_size
                norm_coords = NormalizedCoords(
                    x=grounding_res.click_coords[0] / max(vw, 1),
                    y=grounding_res.click_coords[1] / max(vh, 1),
                )
                updated_action = TypedAction(
                    action_type=action.action_type,
                    target_node_id=new_node.node_id,
                    coords=norm_coords,
                    text_payload=action.text_payload,
                    key_code=action.key_code,
                    scroll_delta=action.scroll_delta,
                    target_label=action.target_label or new_node.label,
                    safety_class=action.safety_class,
                    metadata=action.metadata,
                )
                return ActionProposal(
                    identity=proposal.identity,
                    action=updated_action,
                    expected_delta=proposal.expected_delta,
                    required_scopes=proposal.required_scopes,
                    reasoning_summary=proposal.reasoning_summary,
                    metadata=proposal.metadata,
                ), False

        # Target missing and cannot be re-grounded -> stale target
        return proposal, True

    def _has_active_modal(self, state: Optional[CanonicalUIGraph]) -> bool:
        """Checks if a modal overlay or dialog node is present in the UI graph."""
        if not state or not state.nodes:
            return False
        for node in state.nodes.values():
            if node.role == NodeRole.MODAL:
                return True
            if node.attributes.get("role") in ("dialog", "alertdialog"):
                return True
            if "modal" in str(node.attributes.get("class", "")).lower():
                return True
        return False

    async def _dismiss_active_modal(
        self,
        state: CanonicalUIGraph,
        session_id: str,
        step_index: int,
        episode_id: str,
        goal: TaskGoal,
    ) -> Tuple[bool, Optional[CanonicalUIGraph]]:
        """Identifies and auto-dismisses an unexpected modal/cookie dialog overlay."""
        # 1. Find modal node and candidate dismiss buttons
        modal_node: Optional[UIStateNode] = None
        for node in state.nodes.values():
            if node.role == NodeRole.MODAL or node.attributes.get("role") in ("dialog", "alertdialog") or "modal" in str(node.attributes.get("class", "")).lower():
                modal_node = node
                break

        dismiss_button_node: Optional[UIStateNode] = None

        def _is_dismiss_label_match(label: str) -> bool:
            norm = label.strip().lower()
            tokens = set(norm.replace("_", " ").replace("-", " ").split())
            for target in self.MODAL_DISMISSAL_LABELS:
                t_lower = target.lower()
                if len(t_lower) <= 3:
                    if t_lower in tokens or norm == t_lower:
                        return True
                else:
                    if t_lower in norm:
                        return True
            return False

        if modal_node:
            # Search within modal subtree (children first, ensuring button/link role)
            candidate_ids = [cid for cid in modal_node.children_ids if cid in state.nodes]
            if not candidate_ids and modal_node.node_id in state.nodes:
                candidate_ids = [modal_node.node_id]

            for node_id in candidate_ids:
                cand = state.nodes[node_id]
                if cand.role in (NodeRole.BUTTON, NodeRole.LINK) or cand.attributes.get("role") in ("button", "link") or cand != modal_node:
                    if _is_dismiss_label_match(cand.label):
                        dismiss_button_node = cand
                        break

        if not dismiss_button_node:
            # Search global graph for prominent cookie/modal dismiss buttons
            for cand in state.nodes.values():
                if cand.role in (NodeRole.BUTTON, NodeRole.LINK) or cand.attributes.get("role") in ("button", "link"):
                    if _is_dismiss_label_match(cand.label):
                        dismiss_button_node = cand
                        break

        dismiss_action: TypedAction
        if dismiss_button_node:
            vw, vh = state.viewport_size
            cx, cy = dismiss_button_node.bounds.center
            dismiss_action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id=dismiss_button_node.node_id,
                coords=NormalizedCoords(x=cx / max(vw, 1), y=cy / max(vh, 1)),
                safety_class=SafetyClass.REVERSIBLE,
                metadata={"reason": "auto_modal_dismissal"},
            )
        else:
            # Fallback: Press Escape to close modal
            dismiss_action = TypedAction(
                action_type=ActionType.KEY_PRESS,
                key_code="Escape",
                safety_class=SafetyClass.REVERSIBLE,
                metadata={"reason": "auto_modal_dismissal_escape"},
            )

        dismiss_proposal = ActionProposal(
            identity=ActionIdentity.create(session_id=session_id, step_index=step_index),
            action=dismiss_action,
            required_scopes={CapabilityScope.BROWSER_INTERACT},
        )

        # Dispatch modal dismissal via host kernel
        try:
            res = await self.kernel.submit_proposal(dismiss_proposal)
        except Exception:
            return False, None

        # Capture post-dismissal state
        post_state: Optional[CanonicalUIGraph] = None
        try:
            post_state = await self.observation_port.capture_state()
        except Exception:
            post_state = state

        # Record dismissal transition in journal
        dismiss_tx = TransitionTuple(
            transition_id=f"tx_{episode_id}_{step_index}_dismiss",
            episode_id=episode_id,
            step_index=step_index,
            timestamp_ms=self.clock.now_ms(),
            ui_state_hash=state.compute_state_hash(),
            goal_text=f"Dismiss modal for: {goal.instruction}",
            goal_embedding=[],
            visual_embedding=None,
            action=dismiss_action,
            next_ui_state_hash=post_state.compute_state_hash() if post_state else state.compute_state_hash(),
            delta=res.state_delta or StateDelta(outcome_class=res.outcome),
            duration_ms=res.execution_latency_ms,
            surprise_score=0.1,
            provenance={"interception": "modal_dismissal", "status": res.outcome.value},
        )
        await self.journal.record_transition(dismiss_tx)

        return True, post_state

    def _compute_surprise_score(
        self,
        expected_delta: Optional[StateDelta],
        actual_delta: Optional[StateDelta],
        outcome: OutcomeClass,
    ) -> float:
        """Computes Bayesian surprise metric score in [0.0, 1.0]."""
        if expected_delta is not None and actual_delta is not None:
            # If outcome differs from expectation
            if expected_delta.outcome_class != actual_delta.outcome_class:
                return 0.90

            # Compare modified and added node overlap
            exp_nodes = set(expected_delta.added_nodes + expected_delta.modified_nodes)
            act_nodes = set(actual_delta.added_nodes + actual_delta.modified_nodes)

            if not exp_nodes and not act_nodes:
                return 0.0

            if not exp_nodes or not act_nodes:
                return 0.50

            overlap = len(exp_nodes & act_nodes)
            union = len(exp_nodes | act_nodes)
            jaccard = overlap / union if union > 0 else 1.0
            return round(max(0.0, 1.0 - jaccard), 4)

        # Heuristic surprise scoring based on outcome class
        if outcome in (OutcomeClass.SUCCESS, OutcomeClass.NAVIGATION):
            return 0.0
        elif outcome == OutcomeClass.MODAL_APPEARED:
            return 0.40
        elif outcome == OutcomeClass.LOADING:
            return 0.20
        elif outcome == OutcomeClass.NOOP:
            return 0.50
        elif outcome == OutcomeClass.UNKNOWN_EFFECT:
            return 0.70
        elif outcome == OutcomeClass.ERROR:
            return 1.0

        return 0.0
