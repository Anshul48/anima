"""Abductive Recovery Engine: Diagnoses execution failures and generates corrective sub-plans."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from reflex.cognition.system2.providers import LLMClientPort
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.reconciliation import ReconciliationReport
from reflex.verification.verifier import VerificationResult


@dataclass(frozen=True)
class RecoveryPlan:
    """Corrective plan formulated after verification failure or unexpected state transition."""

    diagnosed_cause: str
    corrective_actions: List[TypedAction]
    should_abort: bool = False
    explanation: str = ""
    subgoal: str = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagnosed_cause": self.diagnosed_cause,
            "corrective_actions": [a.to_dict() for a in self.corrective_actions],
            "should_abort": self.should_abort,
            "explanation": self.explanation,
            "subgoal": self.subgoal,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RecoveryPlan:
        return cls(
            diagnosed_cause=str(data.get("diagnosed_cause", "")),
            corrective_actions=[
                TypedAction.from_dict(a) for a in data.get("corrective_actions", [])
            ],
            should_abort=bool(data.get("should_abort", False)),
            explanation=str(data.get("explanation", "")),
            subgoal=str(data.get("subgoal", "")),
            confidence=float(data.get("confidence", 1.0)),
            metadata=data.get("metadata", {}),
        )


class AbductiveRecoveryEngine:
    """Abductive reasoning engine for root-cause failure diagnosis and corrective action generation."""

    COOKIE_DISMISS_PATTERNS = [
        re.compile(r"\baccept(?:\s+all|\s+cookies)?\b", re.IGNORECASE),
        re.compile(r"\ballow(?:\s+all|\s+cookies)?\b", re.IGNORECASE),
        re.compile(r"\bi\s+agree\b", re.IGNORECASE),
        re.compile(r"\bagree\b", re.IGNORECASE),
        re.compile(r"\bgot\s+it\b", re.IGNORECASE),
        re.compile(r"\bdismiss\b", re.IGNORECASE),
        re.compile(r"\bclose\b", re.IGNORECASE),
        re.compile(r"\bok\b", re.IGNORECASE),
        re.compile(r"\bcontinue\b", re.IGNORECASE),
    ]

    def __init__(
        self,
        llm_client: Optional[LLMClientPort] = None,
        max_repair_retries: int = 1,
    ) -> None:
        self.llm_client = llm_client
        self.max_repair_retries = max_repair_retries

    async def diagnose_and_recover(
        self,
        task_goal: str,
        failed_state: CanonicalUIGraph,
        failed_action: TypedAction,
        verification_result: VerificationResult,
        reconciliation_report: Optional[ReconciliationReport] = None,
    ) -> RecoveryPlan:
        """Analyzes failure context and synthesizes a non-blind corrective recovery plan."""
        # 1. If LLM client is available, attempt LLM abductive diagnosis
        if self.llm_client is not None:
            try:
                llm_plan = await self._diagnose_with_llm(
                    task_goal=task_goal,
                    failed_state=failed_state,
                    failed_action=failed_action,
                    verification_result=verification_result,
                    reconciliation_report=reconciliation_report,
                )
                if llm_plan is not None:
                    return llm_plan
            except Exception:
                # Fall through to deterministic abductive rule engine
                pass

        # 2. Deterministic Abductive Rule Engine (high-reliability zero-shot)
        return self._diagnose_with_rules(
            task_goal=task_goal,
            failed_state=failed_state,
            failed_action=failed_action,
            verification_result=verification_result,
            reconciliation_report=reconciliation_report,
        )

    def _diagnose_with_rules(
        self,
        task_goal: str,
        failed_state: CanonicalUIGraph,
        failed_action: TypedAction,
        verification_result: VerificationResult,
        reconciliation_report: Optional[ReconciliationReport] = None,
    ) -> RecoveryPlan:
        """Rule-based abductive diagnosis covering benchmark failure taxonomies."""
        outcome = verification_result.outcome
        after_state = verification_result.after_state or failed_state
        after_nodes = after_state.nodes if after_state and after_state.nodes else {}
        vw, vh = after_state.viewport_size if after_state else (1920, 1080)
        report_cause = reconciliation_report.inferred_cause if reconciliation_report else ""
        recent_errors = reconciliation_report.recent_errors if reconciliation_report else []

        # SCENARIO 1: Fatal Unrecoverable Error (HTTP 5xx, Server Crash, Uncaught Hard Exception)
        is_fatal_server_error = (
            outcome == OutcomeClass.ERROR
            and (
                any("500" in e or "502" in e or "503" in e or "fatal" in e.lower() or "crash" in e.lower() for e in recent_errors)
                or "500" in report_cause
                or "server error" in report_cause.lower()
            )
        )
        if is_fatal_server_error:
            return RecoveryPlan(
                diagnosed_cause=f"Fatal unrecoverable server error or exception: {report_cause or 'HTTP 500'}",
                corrective_actions=[],
                should_abort=True,
                explanation="Fatal server error detected; terminating execution to prevent destructive loop.",
                subgoal="Abort task due to fatal error",
                confidence=0.99,
            )

        # SCENARIO 2: Modal or Cookie Banner Occlusion
        is_modal_outcome = (outcome == OutcomeClass.MODAL_APPEARED)
        is_modal_reported = "modal" in report_cause.lower()
        has_modal_nodes = any(
            n.role == NodeRole.MODAL
            or "cookie" in n.label.lower()
            or "consent" in n.label.lower()
            or "modal" in n.attributes.get("class", "").lower()
            for n in after_nodes.values()
        )

        if is_modal_outcome or is_modal_reported or has_modal_nodes:
            # Find dismiss / accept button in after_nodes
            dismiss_node: Optional[UIStateNode] = None

            # First priority: buttons or links with dismiss keywords
            for node in after_nodes.values():
                if node.role in (NodeRole.BUTTON, NodeRole.LINK) and node.role != NodeRole.MODAL:
                    lbl = node.label.strip()
                    for pat in self.COOKIE_DISMISS_PATTERNS:
                        if pat.search(lbl):
                            dismiss_node = node
                            break
                    if dismiss_node:
                        break

            # Second priority: any clickable node matching dismiss patterns (excluding modal container)
            if not dismiss_node:
                for node in after_nodes.values():
                    if node.is_clickable and node.role != NodeRole.MODAL:
                        lbl = node.label.strip()
                        for pat in self.COOKIE_DISMISS_PATTERNS:
                            if pat.search(lbl):
                                dismiss_node = node
                                break
                        if dismiss_node:
                            break

            if dismiss_node:
                cx, cy = dismiss_node.bounds.center
                dismiss_coords = NormalizedCoords(
                    x=round(cx / max(1, vw), 4),
                    y=round(cy / max(1, vh), 4),
                )
                dismiss_action = TypedAction(
                    action_type=ActionType.CLICK,
                    target_node_id=dismiss_node.node_id,
                    target_label=dismiss_node.label,
                    coords=dismiss_coords,
                    safety_class=SafetyClass.REVERSIBLE,
                    metadata={"recovery_step": "dismiss_occlusion_banner"},
                )

                # Re-issue original intended action after dismissal
                corrective = [dismiss_action]
                if failed_action.action_type not in (ActionType.NOOP, ActionType.WAIT):
                    corrective.append(failed_action)

                return RecoveryPlan(
                    diagnosed_cause="Element was occluded by cookie banner or modal dialog",
                    corrective_actions=corrective,
                    should_abort=False,
                    explanation=f"Dismiss the blocking banner ('{dismiss_node.label}') before re-attempting {failed_action.action_type.value}.",
                    subgoal="Dismiss banner and proceed",
                    confidence=0.95,
                    metadata={"modal_node_id": dismiss_node.node_id},
                )

        # SCENARIO 3: Form Validation Error / Empty Required Field
        has_validation_hint = (
            outcome == OutcomeClass.ERROR
            or "validation" in report_cause.lower()
            or any("required" in err.lower() or "validation" in err.lower() for err in recent_errors)
            or any("error" in err.lower() for err in verification_result.failed_assertions)
        )

        missing_input_node: Optional[UIStateNode] = None
        for node in after_nodes.values():
            if node.role == NodeRole.INPUT or node.is_editable:
                if not node.value or node.attributes.get("aria-invalid") == "true" or "error" in node.attributes.get("class", "").lower():
                    missing_input_node = node
                    break

        if has_validation_hint and missing_input_node:
            cx, cy = missing_input_node.bounds.center
            input_coords = NormalizedCoords(
                x=round(cx / max(1, vw), 4),
                y=round(cy / max(1, vh), 4),
            )
            lbl_lower = missing_input_node.label.lower()
            if "email" in lbl_lower:
                payload = "user@example.com"
            elif "pass" in lbl_lower:
                payload = "Password123!"
            elif "phone" in lbl_lower:
                payload = "555-0199"
            elif "name" in lbl_lower:
                payload = "Test User"
            else:
                payload = "valid_entry"

            fill_action = TypedAction(
                action_type=ActionType.TYPE,
                target_node_id=missing_input_node.node_id,
                target_label=missing_input_node.label,
                coords=input_coords,
                text_payload=payload,
                safety_class=SafetyClass.REVERSIBLE,
                metadata={"recovery_step": "populate_required_field"},
            )

            corrective = [fill_action]
            if failed_action.action_type == ActionType.CLICK:
                corrective.append(failed_action)

            return RecoveryPlan(
                diagnosed_cause=f"Form validation rejected empty or invalid input in '{missing_input_node.label or missing_input_node.node_id}'",
                corrective_actions=corrective,
                should_abort=False,
                explanation=f"Populate required field '{missing_input_node.label}' with valid data and resubmit.",
                subgoal="Fill missing form field",
                confidence=0.90,
                metadata={"input_node_id": missing_input_node.node_id},
            )

        # SCENARIO 4: Click Miss / Focus Miss / NOOP
        if outcome == OutcomeClass.NOOP or "focus_miss" in report_cause.lower() or "inert" in report_cause.lower():
            target_id = failed_action.target_node_id
            target_node = after_nodes.get(target_id) if target_id else None

            if not target_node and failed_action.target_label:
                for node in after_nodes.values():
                    if node.label == failed_action.target_label:
                        target_node = node
                        break

            if target_node:
                cx, cy = target_node.bounds.center
                fresh_coords = NormalizedCoords(
                    x=round(cx / max(1, vw), 4),
                    y=round(cy / max(1, vh), 4),
                )
                regrounded_click = TypedAction(
                    action_type=ActionType.CLICK,
                    target_node_id=target_node.node_id,
                    target_label=target_node.label,
                    coords=fresh_coords,
                    safety_class=failed_action.safety_class,
                    metadata={"recovery_step": "reground_center_click"},
                )
                return RecoveryPlan(
                    diagnosed_cause="Click missed target element or target was inert (NOOP / focus miss)",
                    corrective_actions=[regrounded_click],
                    should_abort=False,
                    explanation="Re-ground to precise center coordinates of target node and re-issue click.",
                    subgoal="Re-click target element",
                    confidence=0.88,
                    metadata={"target_node_id": target_node.node_id},
                )

        # SCENARIO 5: Stale Node / Target Missing
        if failed_action.target_node_id and failed_action.target_node_id not in after_nodes:
            wait_action = TypedAction(
                action_type=ActionType.WAIT,
                safety_class=SafetyClass.REVERSIBLE,
                metadata={"recovery_step": "await_dom_refresh"},
            )
            return RecoveryPlan(
                diagnosed_cause=f"Target node '{failed_action.target_node_id}' vanished from UI hierarchy",
                corrective_actions=[wait_action],
                should_abort=False,
                explanation="Target element is not present in the current DOM; pausing to allow layout to settle.",
                subgoal="Await UI settling and re-ground",
                confidence=0.75,
            )

        # SCENARIO 6: General Fallback
        return RecoveryPlan(
            diagnosed_cause=f"Unverified state transition: {report_cause or outcome.value}",
            corrective_actions=[
                TypedAction(
                    action_type=ActionType.WAIT,
                    safety_class=SafetyClass.REVERSIBLE,
                    metadata={"recovery_step": "general_fallback_observe"},
                )
            ],
            should_abort=False,
            explanation="Unclear failure mode; proposing state observation step.",
            subgoal="Observe state and replan",
            confidence=0.60,
        )

    async def _diagnose_with_llm(
        self,
        task_goal: str,
        failed_state: CanonicalUIGraph,
        failed_action: TypedAction,
        verification_result: VerificationResult,
        reconciliation_report: Optional[ReconciliationReport] = None,
    ) -> Optional[RecoveryPlan]:
        """Queries LLM backend for abductive diagnosis and parses structured recovery plan."""
        if not self.llm_client:
            return None

        system_prompt = (
            "You are the Reflex System 2 Abductive Error Recovery Engine.\n"
            "Your task is to analyze an execution failure and formulate a corrective recovery plan.\n"
            "Do NOT recommend blind retry of the exact failed action without fixing preconditions.\n"
            "Output MUST be valid JSON conforming to the schema:\n"
            "{\n"
            '  "diagnosed_cause": "<root cause description>",\n'
            '  "should_abort": false,\n'
            '  "explanation": "<rationale>",\n'
            '  "subgoal": "<corrective subgoal>",\n'
            '  "corrective_actions": [\n'
            "    {\n"
            '      "action_type": "<click|type|key_press|scroll|hover|wait|navigate|noop>",\n'
            '      "target_node_id": "<optional id>",\n'
            '      "target_label": "<optional label>",\n'
            '      "text_payload": "<optional text>",\n'
            '      "safety_class": "reversible"\n'
            "    }\n"
            "  ],\n"
            '  "confidence": 0.9\n'
            "}"
        )

        after_state = verification_result.after_state or failed_state
        after_nodes = after_state.nodes if after_state else {}

        affordances_summary = ", ".join(
            f"[{n.node_id}] {n.role.value}: '{n.label}' (val='{n.value}')"
            for n in list(after_nodes.values())[:30]
        )

        user_prompt = (
            f"Task Goal: {task_goal}\n"
            f"Failed Action: {failed_action.to_dict()}\n"
            f"Verification Outcome: {verification_result.outcome.value}\n"
            f"Failed Assertions: {verification_result.failed_assertions}\n"
            f"Reconciliation Report: {reconciliation_report.to_dict() if reconciliation_report else 'None'}\n"
            f"Current Screen Affordances: {affordances_summary}\n"
            f"Diagnose root cause and output strict JSON recovery plan."
        )

        response = await self.llm_client.generate_response(system_prompt, user_prompt)
        parsed = self._parse_recovery_json(response)
        if parsed is not None:
            return parsed

        # Schema repair retry
        if self.max_repair_retries > 0:
            repair_prompt = (
                f"Your previous response failed JSON parsing:\n{response}\n"
                f"Please fix and output ONLY valid JSON conforming to the RecoveryPlan schema."
            )
            repair_response = await self.llm_client.generate_response(system_prompt, repair_prompt)
            return self._parse_recovery_json(repair_response)

        return None

    def _parse_recovery_json(self, raw_text: str) -> Optional[RecoveryPlan]:
        """Extracts and validates RecoveryPlan JSON."""
        cleaned = raw_text.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)
        else:
            json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(1)

        try:
            data = json.loads(cleaned)
            diagnosed_cause = str(data.get("diagnosed_cause", "Unspecified error"))
            should_abort = bool(data.get("should_abort", False))
            explanation = str(data.get("explanation", ""))
            subgoal = str(data.get("subgoal", ""))
            confidence = float(data.get("confidence", 0.9))

            corrective_actions: List[TypedAction] = []
            for act_data in data.get("corrective_actions", []):
                act_type_raw = act_data.get("action_type", "wait").lower()
                action_type = ActionType(act_type_raw) if act_type_raw in ActionType._value2member_map_ else ActionType.WAIT
                safety_raw = act_data.get("safety_class", "reversible").lower()
                safety = SafetyClass(safety_raw) if safety_raw in SafetyClass._value2member_map_ else SafetyClass.REVERSIBLE

                corrective_actions.append(
                    TypedAction(
                        action_type=action_type,
                        target_node_id=act_data.get("target_node_id"),
                        target_label=act_data.get("target_label"),
                        text_payload=act_data.get("text_payload"),
                        safety_class=safety,
                    )
                )

            return RecoveryPlan(
                diagnosed_cause=diagnosed_cause,
                corrective_actions=corrective_actions,
                should_abort=should_abort,
                explanation=explanation,
                subgoal=subgoal,
                confidence=confidence,
            )
        except Exception:
            return None
