"""Reflex Skill Replay Executor.

Instantiates parameterized MotorSkill routines into concrete ActionProposal instances.
Strictly enforces mandatory live dynamic re-grounding (never fixed pixel coordinates)
via BrowserGroundingEngine at each step before host dispatch.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

from reflex.grounding.browser_grounder import BrowserGroundingEngine, GroundingQuery
from reflex.host.kernel.host_kernel import (
    DispatchState,
    HostControlKernel,
    HostControlKernelPort,
)
from reflex.ports.action import ActionPort
from reflex.ports.observation import ObservationPort
from reflex.ports.verification import VerificationPort
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.memory import MotorSkill
from reflex.schemas.policy import CapabilityScope
from reflex.schemas.state import CanonicalUIGraph, UIStateNode


class SkillGroundingError(Exception):
    """Raised when an abstract skill target cannot be dynamically resolved in live UI."""
    pass


@dataclass(frozen=True)
class SkillExecutionStepResult:
    """Outcome of a single re-grounded skill step execution."""

    step_index: int
    proposal: ActionProposal
    resolved_target_node_id: Optional[str]
    success: bool
    observed_state_hash: str
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "proposal": self.proposal.to_dict(),
            "resolved_target_node_id": self.resolved_target_node_id,
            "success": self.success,
            "observed_state_hash": self.observed_state_hash,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class SkillExecutionResult:
    """Comprehensive outcome of executing a compiled MotorSkill routine."""

    skill_id: str
    session_id: str
    total_steps: int
    executed_steps: int
    success: bool
    step_results: List[SkillExecutionStepResult]
    final_state_hash: Optional[str] = None
    error: Optional[str] = None
    total_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "session_id": self.session_id,
            "total_steps": self.total_steps,
            "executed_steps": self.executed_steps,
            "success": self.success,
            "step_results": [s.to_dict() for s in self.step_results],
            "final_state_hash": self.final_state_hash,
            "error": self.error,
            "total_duration_ms": self.total_duration_ms,
        }


class SkillReplayExecutor:
    """Instantiates and executes compiled MotorSkills with mandatory live re-grounding at each step."""

    def __init__(
        self,
        grounding_engine: Optional[BrowserGroundingEngine] = None,
        verification_engine: Optional[VerificationPort] = None,
    ) -> None:
        self.grounding_engine = grounding_engine or BrowserGroundingEngine()
        self.verification_engine = verification_engine

    # =========================================================================
    # Step-Level Dynamic Re-Grounding & Proposal Instantiation
    # =========================================================================

    def instantiate_step(
        self,
        skill: MotorSkill,
        step_index: int,
        current_state: CanonicalUIGraph,
        parameter_bindings: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> ActionProposal:
        """Dynamically resolves abstract skill action into a concrete ActionProposal.
        
        CRITICAL INVARIANT: Re-resolves target against live CanonicalUIGraph.
        Never relies on stale pixel coordinates.
        """
        if step_index < 0 or step_index >= len(skill.action_sequence):
            raise IndexError(f"Step index {step_index} out of bounds for skill {skill.skill_id}")

        template_action = skill.action_sequence[step_index]
        sess_id = session_id or f"skill_{skill.skill_id[:8]}"

        # 1. Parameter substitution
        bound_text = self._substitute_templates(template_action.text_payload, parameter_bindings)

        # 2. Dynamic live target re-grounding
        resolved_node, click_coords = self._reground_target(template_action, current_state)

        # 3. Construct concrete TypedAction
        target_id = resolved_node.node_id if resolved_node else template_action.target_node_id
        target_lbl = resolved_node.label if resolved_node else template_action.target_label

        normalized_coords = None
        if click_coords and current_state.viewport_size:
            vw, vh = current_state.viewport_size
            if vw > 0 and vh > 0:
                normalized_coords = NormalizedCoords(
                    x=round(click_coords[0] / vw, 4),
                    y=round(click_coords[1] / vh, 4),
                )

        concrete_action = TypedAction(
            action_type=template_action.action_type,
            target_node_id=target_id,
            target_label=target_lbl,
            coords=normalized_coords,
            text_payload=bound_text,
            key_code=template_action.key_code,
            scroll_delta=template_action.scroll_delta,
            safety_class=template_action.safety_class,
            metadata={
                **template_action.metadata,
                "regrounded": True,
                "regrounded_node_id": target_id,
                "skill_id": skill.skill_id,
                "step_index": step_index,
            },
        )

        # 4. Wrap into ActionProposal with required capability scopes
        identity = ActionIdentity.create(
            session_id=sess_id,
            step_index=step_index,
        )

        required_scopes = {CapabilityScope.BROWSER_INTERACT}
        if concrete_action.safety_class == SafetyClass.DESTRUCTIVE:
            required_scopes.add(CapabilityScope.DESTRUCTIVE_EXECUTION)

        return ActionProposal(
            identity=identity,
            action=concrete_action,
            expected_delta=skill.expected_delta,
            required_scopes=required_scopes,
            reasoning_summary=f"Fast-path execution of skill {skill.skill_id} step {step_index}",
            metadata={"skill_id": skill.skill_id, "step_index": step_index},
        )

    # =========================================================================
    # Full Routine Execution
    # =========================================================================

    async def execute_skill(
        self,
        skill: MotorSkill,
        observation_port: ObservationPort,
        action_port: ActionPort,
        parameter_bindings: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        step_delay_ms: float = 0.0,
        kernel: Optional[HostControlKernelPort] = None,
    ) -> SkillExecutionResult:
        """Executes all steps of a compiled MotorSkill routine against live ports.

        Performs fresh observation and dynamic re-grounding at each step.
        Every step dispatches through the HostControlKernel authority (an
        explicitly provided kernel, or one owned by this call built around the
        given action port). Terminates on grounding error or dispatch failure.
        """
        sess_id = session_id or f"replay_{skill.skill_id[:8]}_{uuid.uuid4().hex[:6]}"
        dispatch_kernel = kernel or HostControlKernel(action_port=action_port)
        total_steps = len(skill.action_sequence)
        step_results: List[SkillExecutionStepResult] = []
        t0 = time.perf_counter()

        for step_idx in range(total_steps):
            step_t0 = time.perf_counter()

            # 1. Capture live fresh UI observation
            try:
                live_state = await observation_port.capture_state()
            except Exception as obs_err:
                step_dur = (time.perf_counter() - step_t0) * 1000.0
                return SkillExecutionResult(
                    skill_id=skill.skill_id,
                    session_id=sess_id,
                    total_steps=total_steps,
                    executed_steps=len(step_results),
                    success=False,
                    step_results=step_results,
                    error=f"Observation capture failed at step {step_idx}: {obs_err}",
                    total_duration_ms=(time.perf_counter() - t0) * 1000.0,
                )

            # 2. Dynamically re-ground and instantiate proposal
            try:
                proposal = self.instantiate_step(
                    skill=skill,
                    step_index=step_idx,
                    current_state=live_state,
                    parameter_bindings=parameter_bindings,
                    session_id=sess_id,
                )
            except SkillGroundingError as ground_err:
                step_dur = (time.perf_counter() - step_t0) * 1000.0
                return SkillExecutionResult(
                    skill_id=skill.skill_id,
                    session_id=sess_id,
                    total_steps=total_steps,
                    executed_steps=len(step_results),
                    success=False,
                    step_results=step_results,
                    error=f"Dynamic re-grounding failed at step {step_idx}: {ground_err}",
                    total_duration_ms=(time.perf_counter() - t0) * 1000.0,
                )

            # 3. Dispatch action through the HostControlKernel authority
            try:
                dispatch_result = await dispatch_kernel.submit_proposal(proposal)
                if dispatch_result.state != DispatchState.RETIRED_SUCCESS:
                    raise RuntimeError(
                        f"Kernel refused dispatch: {dispatch_result.error_message}"
                    )
                step_dur = (time.perf_counter() - step_t0) * 1000.0

                step_res = SkillExecutionStepResult(
                    step_index=step_idx,
                    proposal=proposal,
                    resolved_target_node_id=proposal.action.target_node_id,
                    success=True,
                    observed_state_hash=live_state.compute_state_hash(),
                    duration_ms=step_dur,
                )
                step_results.append(step_res)
            except Exception as dispatch_err:
                step_dur = (time.perf_counter() - step_t0) * 1000.0
                step_res = SkillExecutionStepResult(
                    step_index=step_idx,
                    proposal=proposal,
                    resolved_target_node_id=proposal.action.target_node_id,
                    success=False,
                    observed_state_hash=live_state.compute_state_hash(),
                    error=str(dispatch_err),
                    duration_ms=step_dur,
                )
                step_results.append(step_res)
                return SkillExecutionResult(
                    skill_id=skill.skill_id,
                    session_id=sess_id,
                    total_steps=total_steps,
                    executed_steps=len(step_results),
                    success=False,
                    step_results=step_results,
                    error=f"Action dispatch failed at step {step_idx}: {dispatch_err}",
                    total_duration_ms=(time.perf_counter() - t0) * 1000.0,
                )

            if step_delay_ms > 0:
                await asyncio.sleep(step_delay_ms / 1000.0)

        # Capture final state
        try:
            final_state = await observation_port.capture_state()
            final_hash = final_state.compute_state_hash()
        except Exception:
            final_hash = None

        return SkillExecutionResult(
            skill_id=skill.skill_id,
            session_id=sess_id,
            total_steps=total_steps,
            executed_steps=len(step_results),
            success=all(r.success for r in step_results),
            step_results=step_results,
            final_state_hash=final_hash,
            total_duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    # =========================================================================
    # Internal Target Resolution & Substitution
    # =========================================================================

    def _reground_target(
        self,
        template_action: TypedAction,
        graph: CanonicalUIGraph,
    ) -> Tuple[Optional[UIStateNode], Optional[Tuple[int, int]]]:
        """Resolves target against live graph using BrowserGroundingEngine."""
        # Non-targeted actions do not need grounding
        if template_action.action_type in (ActionType.WAIT, ActionType.NOOP):
            return None, None
        if (
            template_action.action_type == ActionType.KEY_PRESS
            and not template_action.target_label
            and not template_action.target_node_id
        ):
            return None, None

        # 1. Direct node ID match
        if template_action.target_node_id and template_action.target_node_id in graph.nodes:
            node = graph.nodes[template_action.target_node_id]
            return node, node.bounds.center

        # 2. Semantic grounding resolution
        query_text = template_action.target_label or template_action.target_node_id or ""
        if not query_text:
            return None, None

        query = GroundingQuery(
            target_text=query_text,
            target_role=template_action.metadata.get("target_role"),
            container_hint=template_action.metadata.get("container_hint"),
            min_confidence=0.75,
        )

        result = self.grounding_engine.resolve_target(graph, query)
        if result:
            return result.target_node, result.click_coords

        # 3. Fuzzy label fallback
        norm_query = self._normalize(query_text)
        for node in graph.nodes.values():
            if self._normalize(node.label) == norm_query:
                return node, node.bounds.center

        # Target required but unresolved
        raise SkillGroundingError(
            f"Failed to dynamically re-ground target '{query_text}' against live UI state graph "
            f"({len(graph.nodes)} nodes present)"
        )

    def _substitute_templates(
        self,
        text: Optional[str],
        bindings: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Substitutes template placeholders with sanitized bound arguments."""
        if not text:
            return text
        if not bindings:
            return text

        result = text
        for k, v in bindings.items():
            clean_val = self._sanitize_param_value(str(v))
            pattern_jinja = f"{{{{{k}}}}}"
            if pattern_jinja in result:
                result = result.replace(pattern_jinja, clean_val)
            pattern_spaces = f"{{{{ {k} }}}}"
            if pattern_spaces in result:
                result = result.replace(pattern_spaces, clean_val)
            bracket_pattern = f"[{k}]"
            if bracket_pattern in result:
                result = result.replace(bracket_pattern, clean_val)

        return result

    def _sanitize_param_value(self, val: str) -> str:
        """Sanitizes variable input against null bytes and control code exploits."""
        return val.replace("\x00", "").strip()

    @staticmethod
    def _normalize(text: Optional[str]) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", str(text).strip().lower())
