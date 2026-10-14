"""Reflex Shadow Mode Skill Validator.

Evaluates candidate MotorSkills in background shadow mode alongside System 2 planning
without granting action authority or dispatching physical actions to the host.
Measures action agreement ratio, locator stability against live UI state graphs, and
divergence explanations.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import uuid

from reflex.grounding.browser_grounder import BrowserGroundingEngine, GroundingQuery
from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.memory import MotorSkill
from reflex.schemas.state import CanonicalUIGraph, NodeRole, UIStateNode


@dataclass(frozen=True)
class ShadowStepEvaluation:
    """Detailed evaluation of a single step in shadow execution."""

    step_index: int
    skill_action: TypedAction
    system2_action: TypedAction
    agreed: bool
    action_type_matched: bool
    target_matched: bool
    payload_matched: bool
    locator_resolved: bool
    divergence_reason: Optional[str] = None
    resolved_node_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "skill_action": self.skill_action.to_dict(),
            "system2_action": self.system2_action.to_dict(),
            "agreed": self.agreed,
            "action_type_matched": self.action_type_matched,
            "target_matched": self.target_matched,
            "payload_matched": self.payload_matched,
            "locator_resolved": self.locator_resolved,
            "divergence_reason": self.divergence_reason,
            "resolved_node_id": self.resolved_node_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ShadowStepEvaluation:
        return cls(
            step_index=int(data["step_index"]),
            skill_action=TypedAction.from_dict(data["skill_action"]),
            system2_action=TypedAction.from_dict(data["system2_action"]),
            agreed=bool(data["agreed"]),
            action_type_matched=bool(data["action_type_matched"]),
            target_matched=bool(data["target_matched"]),
            payload_matched=bool(data["payload_matched"]),
            locator_resolved=bool(data["locator_resolved"]),
            divergence_reason=data.get("divergence_reason"),
            resolved_node_id=data.get("resolved_node_id"),
        )


@dataclass(frozen=True)
class ShadowRunReport:
    """Consolidated report for a candidate skill shadow evaluation run."""

    skill_id: str
    run_id: str
    total_steps: int
    agreed_steps: int
    agreement_ratio: float
    locator_stability_ratio: float
    step_evaluations: List[ShadowStepEvaluation]
    divergences: List[str]
    passed: bool
    timestamp_ms: float = field(default_factory=lambda: time.time() * 1000.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "run_id": self.run_id,
            "total_steps": self.total_steps,
            "agreed_steps": self.agreed_steps,
            "agreement_ratio": self.agreement_ratio,
            "locator_stability_ratio": self.locator_stability_ratio,
            "step_evaluations": [s.to_dict() for s in self.step_evaluations],
            "divergences": list(self.divergences),
            "passed": self.passed,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ShadowRunReport:
        return cls(
            skill_id=data["skill_id"],
            run_id=data["run_id"],
            total_steps=int(data["total_steps"]),
            agreed_steps=int(data["agreed_steps"]),
            agreement_ratio=float(data["agreement_ratio"]),
            locator_stability_ratio=float(data["locator_stability_ratio"]),
            step_evaluations=[ShadowStepEvaluation.from_dict(s) for s in data.get("step_evaluations", [])],
            divergences=list(data.get("divergences", [])),
            passed=bool(data["passed"]),
            timestamp_ms=float(data.get("timestamp_ms", 0.0)),
        )


class ShadowValidator:
    """Shadow mode evaluator measuring candidate skill agreement against System 2 or golden runs."""

    def __init__(
        self,
        grounding_engine: Optional[BrowserGroundingEngine] = None,
        min_agreement_threshold: float = 0.95,
        min_locator_stability: float = 0.95,
        target_similarity_threshold: float = 0.80,
    ) -> None:
        self.grounding_engine = grounding_engine or BrowserGroundingEngine()
        self.min_agreement_threshold = min_agreement_threshold
        self.min_locator_stability = min_locator_stability
        self.target_similarity_threshold = target_similarity_threshold

    # =========================================================================
    # Step-Level Shadow Evaluation
    # =========================================================================

    def evaluate_step(
        self,
        skill: MotorSkill,
        step_index: int,
        current_state: CanonicalUIGraph,
        system2_action: TypedAction,
        parameter_bindings: Optional[Dict[str, Any]] = None,
    ) -> ShadowStepEvaluation:
        """Evaluates a single step proposed by a candidate skill against System 2 proposal.
        
        Zero action authority: this does NOT perform physical dispatch.
        """
        if step_index < 0 or step_index >= len(skill.action_sequence):
            return ShadowStepEvaluation(
                step_index=step_index,
                skill_action=TypedAction(action_type=ActionType.NOOP),
                system2_action=system2_action,
                agreed=False,
                action_type_matched=False,
                target_matched=False,
                payload_matched=False,
                locator_resolved=False,
                divergence_reason=f"Step index {step_index} out of bounds for skill with {len(skill.action_sequence)} steps",
            )

        raw_skill_action = skill.action_sequence[step_index]
        instantiated_skill_action = self._bind_action_parameters(raw_skill_action, parameter_bindings)

        # 1. Action type matching
        type_matched = (instantiated_skill_action.action_type == system2_action.action_type)

        # 2. Dynamic locator resolution check
        locator_resolved, resolved_node = self._resolve_skill_locator(
            instantiated_skill_action, current_state
        )

        # 3. Target matching
        target_matched = self._match_targets(
            instantiated_skill_action,
            system2_action,
            resolved_node,
            current_state,
        )

        # 4. Text payload matching
        payload_matched = self._match_payloads(
            instantiated_skill_action,
            system2_action,
        )

        # Overall agreement
        divergence_reasons: List[str] = []
        if not type_matched:
            divergence_reasons.append(
                f"Action type mismatch: skill='{instantiated_skill_action.action_type.value}' vs "
                f"system2='{system2_action.action_type.value}'"
            )
        if not target_matched:
            skill_t = instantiated_skill_action.target_label or instantiated_skill_action.target_node_id or "unspecified"
            sys2_t = system2_action.target_label or system2_action.target_node_id or "unspecified"
            divergence_reasons.append(f"Target mismatch: skill target='{skill_t}' vs system2 target='{sys2_t}'")
        if not payload_matched:
            divergence_reasons.append(
                f"Payload mismatch: skill text='{instantiated_skill_action.text_payload}' vs "
                f"system2 text='{system2_action.text_payload}'"
            )
        if not locator_resolved:
            divergence_reasons.append(
                f"Locator resolution failed: target '{instantiated_skill_action.target_label}' not found in live UI state"
            )

        agreed = type_matched and target_matched and payload_matched and locator_resolved
        div_str = "; ".join(divergence_reasons) if divergence_reasons else None

        return ShadowStepEvaluation(
            step_index=step_index,
            skill_action=instantiated_skill_action,
            system2_action=system2_action,
            agreed=agreed,
            action_type_matched=type_matched,
            target_matched=target_matched,
            payload_matched=payload_matched,
            locator_resolved=locator_resolved,
            divergence_reason=div_str,
            resolved_node_id=resolved_node.node_id if resolved_node else None,
        )

    # =========================================================================
    # Run-Level Shadow Evaluation
    # =========================================================================

    def evaluate_run(
        self,
        skill: MotorSkill,
        states: Sequence[CanonicalUIGraph],
        system2_actions: Sequence[TypedAction],
        parameter_bindings: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> ShadowRunReport:
        """Evaluates an entire candidate skill trajectory against a sequence of live or recorded System 2 steps."""
        run_id_val = run_id or f"shadow_{uuid.uuid4().hex[:8]}"
        step_count = min(len(skill.action_sequence), len(system2_actions), len(states))
        total_steps = len(skill.action_sequence)

        if total_steps == 0 or len(system2_actions) == 0 or len(states) == 0:
            return ShadowRunReport(
                skill_id=skill.skill_id,
                run_id=run_id_val,
                total_steps=total_steps,
                agreed_steps=0,
                agreement_ratio=0.0,
                locator_stability_ratio=0.0,
                step_evaluations=[],
                divergences=["Empty trajectory or state sequence"],
                passed=False,
            )

        step_evaluations: List[ShadowStepEvaluation] = []
        divergences: List[str] = []

        for i in range(step_count):
            state = states[i]
            sys2_act = system2_actions[i]
            step_eval = self.evaluate_step(
                skill=skill,
                step_index=i,
                current_state=state,
                system2_action=sys2_act,
                parameter_bindings=parameter_bindings,
            )
            step_evaluations.append(step_eval)
            if not step_eval.agreed and step_eval.divergence_reason:
                divergences.append(f"Step {i}: {step_eval.divergence_reason}")

        # Check for length mismatch
        if len(system2_actions) != total_steps:
            divergences.append(
                f"Trajectory length mismatch: skill has {total_steps} steps, System 2 produced {len(system2_actions)}"
            )

        agreed_count = sum(1 for s in step_evaluations if s.agreed)
        resolved_count = sum(1 for s in step_evaluations if s.locator_resolved)

        agreement_ratio = agreed_count / max(total_steps, len(system2_actions))
        locator_stability = resolved_count / total_steps if total_steps > 0 else 0.0

        passed = (
            agreement_ratio >= self.min_agreement_threshold
            and locator_stability >= self.min_locator_stability
            and len(system2_actions) == total_steps
        )

        return ShadowRunReport(
            skill_id=skill.skill_id,
            run_id=run_id_val,
            total_steps=total_steps,
            agreed_steps=agreed_count,
            agreement_ratio=round(agreement_ratio, 4),
            locator_stability_ratio=round(locator_stability, 4),
            step_evaluations=step_evaluations,
            divergences=divergences,
            passed=passed,
        )

    # =========================================================================
    # Promotion Screening Multi-Run Assessment
    # =========================================================================

    def check_promotion_eligibility(
        self,
        skill_id: str,
        reports: Sequence[ShadowRunReport],
        min_runs: int = 5,
        min_agreement: Optional[float] = None,
        min_locator_stability: Optional[float] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Determines if a candidate skill meets criteria across N >= 5 shadow passes for promotion."""
        req_agreement = min_agreement if min_agreement is not None else self.min_agreement_threshold
        req_stability = min_locator_stability if min_locator_stability is not None else self.min_locator_stability

        valid_reports = [r for r in reports if r.skill_id == skill_id]
        total_runs = len(valid_reports)

        if total_runs < min_runs:
            return False, {
                "eligible": False,
                "reason": f"Insufficient shadow runs: {total_runs}/{min_runs}",
                "total_runs": total_runs,
                "mean_agreement_ratio": 0.0,
                "mean_locator_stability": 0.0,
            }

        mean_agreement = sum(r.agreement_ratio for r in valid_reports) / total_runs
        mean_stability = sum(r.locator_stability_ratio for r in valid_reports) / total_runs
        passed_runs = sum(1 for r in valid_reports if r.passed)

        is_eligible = (
            mean_agreement >= req_agreement
            and mean_stability >= req_stability
            and (passed_runs / total_runs) >= 0.80
        )

        stats = {
            "eligible": is_eligible,
            "total_runs": total_runs,
            "passed_runs": passed_runs,
            "mean_agreement_ratio": round(mean_agreement, 4),
            "mean_locator_stability": round(mean_stability, 4),
            "min_required_runs": min_runs,
            "min_required_agreement": req_agreement,
            "reason": "All shadow criteria met" if is_eligible else "Agreement or stability below threshold",
        }

        return is_eligible, stats

    # =========================================================================
    # Internal Target Resolution & Matching
    # =========================================================================

    def _resolve_skill_locator(
        self,
        action: TypedAction,
        graph: CanonicalUIGraph,
    ) -> Tuple[bool, Optional[UIStateNode]]:
        """Resolves the skill's abstract target against live CanonicalUIGraph via BrowserGroundingEngine."""
        # If action doesn't require UI target (e.g. wait, noop, key press without target)
        if action.action_type in (ActionType.WAIT, ActionType.NOOP):
            return True, None

        if action.action_type == ActionType.KEY_PRESS and not action.target_label and not action.target_node_id:
            return True, None

        # 1. Direct node ID lookup in current graph
        if action.target_node_id and action.target_node_id in graph.nodes:
            return True, graph.nodes[action.target_node_id]

        # 2. Semantic grounding resolution
        query_text = action.target_label or action.target_node_id or ""
        if not query_text:
            return False, None

        target_role = action.metadata.get("target_role")
        container_hint = action.metadata.get("container_hint")

        grounding_query = GroundingQuery(
            target_text=query_text,
            target_role=target_role,
            container_hint=container_hint,
            min_confidence=self.target_similarity_threshold,
        )

        result = self.grounding_engine.resolve_target(graph, grounding_query)
        if result and result.confidence >= self.target_similarity_threshold:
            return True, result.target_node

        # 3. Fallback: normalized label match across graph nodes
        norm_query = self._normalize(query_text)
        for node in graph.nodes.values():
            if self._normalize(node.label) == norm_query:
                return True, node

        return False, None

    def _match_targets(
        self,
        skill_action: TypedAction,
        sys2_action: TypedAction,
        resolved_skill_node: Optional[UIStateNode],
        graph: CanonicalUIGraph,
    ) -> bool:
        """Determines if the candidate skill target matches the System 2 planned target."""
        # Non-targeted actions match if both have no target
        if not skill_action.target_label and not skill_action.target_node_id:
            if not sys2_action.target_label and not sys2_action.target_node_id:
                return True

        # Node ID direct match
        if skill_action.target_node_id and sys2_action.target_node_id:
            if skill_action.target_node_id == sys2_action.target_node_id:
                return True

        # Resolved node ID matches System 2 target node ID
        if resolved_skill_node and sys2_action.target_node_id:
            if resolved_skill_node.node_id == sys2_action.target_node_id:
                return True

        # Target label similarity match
        skill_label = skill_action.target_label or (resolved_skill_node.label if resolved_skill_node else "")
        sys2_label = sys2_action.target_label or ""
        if sys2_action.target_node_id and sys2_action.target_node_id in graph.nodes:
            sys2_label = graph.nodes[sys2_action.target_node_id].label or sys2_label

        if skill_label and sys2_label:
            sim = self._compute_string_similarity(skill_label, sys2_label)
            return sim >= self.target_similarity_threshold

        return False

    def _match_payloads(
        self,
        skill_action: TypedAction,
        sys2_action: TypedAction,
    ) -> bool:
        """Determines if text or key payloads match."""
        if skill_action.action_type == ActionType.KEY_PRESS:
            return skill_action.key_code == sys2_action.key_code

        if skill_action.action_type == ActionType.TYPE:
            skill_text = skill_action.text_payload or ""
            sys2_text = sys2_action.text_payload or ""

            # Check if skill text is an un-bound template
            if "{{" in skill_text and "}}" in skill_text:
                # In shadow evaluation without explicit binding, template slots match non-empty input
                return len(sys2_text.strip()) > 0 or skill_text == sys2_text

            return self._normalize(skill_text) == self._normalize(sys2_text)

        return True

    def _bind_action_parameters(
        self,
        action: TypedAction,
        bindings: Optional[Dict[str, Any]],
    ) -> TypedAction:
        """Substitutes template variables in action text payload."""
        if not bindings or not action.text_payload:
            return action

        text = action.text_payload
        for k, v in bindings.items():
            pattern_jinja = f"{{{{{k}}}}}"
            if pattern_jinja in text:
                text = text.replace(pattern_jinja, str(v))
            pattern_spaces = f"{{{{ {k} }}}}"
            if pattern_spaces in text:
                text = text.replace(pattern_spaces, str(v))
            bracket_pattern = f"[{k}]"
            if bracket_pattern in text:
                text = text.replace(bracket_pattern, str(v))

        return TypedAction(
            action_type=action.action_type,
            target_node_id=action.target_node_id,
            target_label=action.target_label,
            coords=action.coords,
            text_payload=text,
            key_code=action.key_code,
            scroll_delta=action.scroll_delta,
            safety_class=action.safety_class,
            metadata=dict(action.metadata),
        )

    def _compute_string_similarity(self, s1: str, s2: str) -> float:
        n1 = self._normalize(s1)
        n2 = self._normalize(s2)
        if not n1 or not n2:
            return 0.0
        if n1 == n2:
            return 1.0
        if n1 in n2 or n2 in n1:
            return 0.85

        tokens1 = set(re.findall(r"\w+", n1))
        tokens2 = set(re.findall(r"\w+", n2))
        if tokens1 and tokens2:
            intersection = tokens1.intersection(tokens2)
            union = tokens1.union(tokens2)
            return len(intersection) / len(union)
        return 0.0

    @staticmethod
    def _normalize(text: Optional[str]) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", str(text).strip().lower())
