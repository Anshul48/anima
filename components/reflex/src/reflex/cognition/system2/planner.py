"""System 2 Cognitive Planner: Decoupled cognitive planning proposing structured intent targets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from reflex.cognition.system2.context_compressor import ContextCompressor
from reflex.cognition.system2.providers import DeterministicRulePlanner, LLMClientPort
from reflex.cognition.system2.recovery import AbductiveRecoveryEngine, RecoveryPlan
from reflex.ports.context import ContextProvider, ContextRequest, ContextSnapshot
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.verifier import VerificationResult


@dataclass(frozen=True)
class PlannedStep:
    """High-level cognitive proposal emitted by System 2.
    
    System 2 has ZERO direct execution authority; it emits action proposals
    only, which are submitted to the Host Control Kernel for policy gating.
    """

    thought_reasoning: str
    target_description: str
    action: TypedAction
    expected_delta: StateDelta
    confidence: float
    subgoal: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thought_reasoning": self.thought_reasoning,
            "target_description": self.target_description,
            "action": self.action.to_dict(),
            "expected_delta": self.expected_delta.to_dict(),
            "confidence": self.confidence,
            "subgoal": self.subgoal,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PlannedStep:
        return cls(
            thought_reasoning=str(data.get("thought_reasoning", "")),
            target_description=str(data.get("target_description", "")),
            action=TypedAction.from_dict(data["action"]),
            expected_delta=StateDelta.from_dict(data["expected_delta"]),
            confidence=float(data.get("confidence", 1.0)),
            subgoal=str(data.get("subgoal", "")),
            metadata=data.get("metadata", {}),
        )


class System2PlannerPort(ABC):
    """Abstract port defining System 2 planning and recovery boundaries."""

    @abstractmethod
    async def plan_next_step(
        self,
        task_goal: str,
        current_state: CanonicalUIGraph,
        history: Optional[List[Any]] = None,
    ) -> PlannedStep:
        """Generates the next cognitive action proposal."""
        ...

    @abstractmethod
    async def plan_recovery(
        self,
        task_goal: str,
        failed_state: CanonicalUIGraph,
        failed_action: TypedAction,
        verification_result: VerificationResult,
    ) -> RecoveryPlan:
        """Performs abductive diagnosis and emits recovery steps."""
        ...


class System2Planner(System2PlannerPort):
    """Decoupled cognitive planner proposing abstract intent targets and expected state deltas."""

    SYSTEM_PROMPT = (
        "You are the Reflex System 2 Cognitive Planner for autonomous web and desktop tasks.\n"
        "Your task is to decompose high-level user goals into single next-step action proposals.\n"
        "You do NOT possess direct physical execution authority; you generate structured proposals only.\n\n"
        "RULES & CONSTRAINTS:\n"
        "1. Select an interactable target by its unique index [id=N] from the Screen Affordances list, or specify navigation/wait/noop.\n"
        "2. Formulate explicit expected state deltas (e.g. expected modal appearance, input value change, page navigation).\n"
        "3. Output MUST be strictly valid JSON conforming to the output schema. Do NOT include extraneous markdown chatter outside the JSON code block.\n\n"
        "OUTPUT JSON SCHEMA:\n"
        "{\n"
        '  "thought": "<concise step-by-step reasoning>",\n'
        '  "subgoal": "<immediate sub-goal description>",\n'
        '  "target_index": <integer index from screen affordances or null>,\n'
        '  "target_description": "<text description of the target>",\n'
        '  "action_type": "<click|double_click|right_click|type|key_press|scroll|hover|wait|navigate|noop>",\n'
        '  "text_payload": "<text to type or URL to navigate to, or null>",\n'
        '  "key_code": "<key name like Enter, Tab, Escape, or null>",\n'
        '  "scroll_delta": [0, 200],\n'
        '  "expected_outcome": "<success|modal|navigation|loading>",\n'
        '  "expected_description": "<expected visual or structural effect>",\n'
        '  "confidence": 0.95\n'
        "}"
    )

    def __init__(
        self,
        llm_client: Optional[LLMClientPort] = None,
        context_compressor: Optional[ContextCompressor] = None,
        recovery_engine: Optional[AbductiveRecoveryEngine] = None,
        context_provider: Optional[ContextProvider] = None,
        max_repair_retries: int = 1,
        max_affordances: int = 50,
    ) -> None:
        self.llm_client = llm_client
        self.context_compressor = context_compressor or ContextCompressor()
        self.recovery_engine = recovery_engine or AbductiveRecoveryEngine(llm_client=llm_client)
        self.context_provider = context_provider
        self.fallback_planner = DeterministicRulePlanner()
        self.max_repair_retries = max_repair_retries
        self.max_affordances = max_affordances

    def format_affordances(
        self, state: CanonicalUIGraph, max_elements: Optional[int] = None
    ) -> Tuple[str, Dict[int, UIStateNode]]:
        """Extracts and formats interactable UI elements into indexed affordance entries."""
        max_elem = max_elements or self.max_affordances
        nodes = state.nodes if state and state.nodes else {}
        affordance_map: Dict[int, UIStateNode] = {}
        lines: List[str] = []

        # Sort interactable nodes by visual reading order: top-to-bottom (y1), left-to-right (x1)
        def _sort_key(n: UIStateNode) -> Tuple[int, int, int, str]:
            is_priority = (
                n.is_focused
                or n.role in (NodeRole.BUTTON, NodeRole.INPUT, NodeRole.LINK, NodeRole.MODAL)
                or n.is_clickable
                or n.is_editable
            )
            priority_rank = 0 if is_priority else 1
            return (priority_rank, n.bounds.y1, n.bounds.x1, n.node_id)

        sorted_nodes = sorted(nodes.values(), key=_sort_key)
        idx = 1
        for node in sorted_nodes:
            if idx > max_elem:
                break
            # Filter out invisible or empty structural containers
            if node.bounds.width <= 0 or node.bounds.height <= 0:
                continue

            affordance_map[idx] = node
            flags = []
            if node.is_focused:
                flags.append("FOCUSED")
            if not node.is_enabled:
                flags.append("DISABLED")
            if node.value:
                flags.append(f"value='{node.value}'")
            flags_str = f" [{', '.join(flags)}]" if flags else ""

            cx, cy = node.bounds.center
            label_display = f"'{node.label}'" if node.label else "(no label)"
            lines.append(
                f"[id={idx}] <{node.role.value}> {label_display} at ({cx}, {cy}){flags_str} [node_id='{node.node_id}']"
            )
            idx += 1

        if not lines:
            lines.append("(No interactable elements detected on current screen)")

        return "\n".join(lines), affordance_map

    def build_planning_prompt(
        self,
        task_goal: str,
        current_state: CanonicalUIGraph,
        history: Optional[List[Any]] = None,
        advisory_snapshot: Optional[ContextSnapshot] = None,
    ) -> Tuple[str, str, Dict[int, UIStateNode]]:
        """Assembles structured system and user prompts with compressed timeline and affordances."""
        # 1. Compressed behavioral history tau_tilde
        compressed_timeline = self.context_compressor.compress_history(
            transitions=history or [],
            initial_state_summary=f"URL: {current_state.url or 'unknown'}",
        )

        # 2. Formatted screen affordances
        affordances_text, affordance_map = self.format_affordances(current_state)

        # 3. Optional Advisory Personal Context (Entorhinal)
        advisory_section = ""
        if advisory_snapshot is not None and advisory_snapshot.facts:
            claim_lines = []
            for f in advisory_snapshot.facts:
                if f.validity == "VALID":
                    val = f.text
                    conf = f.confidence
                    claim_lines.append(f"- {val} (confidence: {conf:.2f})")
            advisory_section = (
                "=== ADVISORY PERSONAL CONTEXT (ENTORHINAL - ADVISORY ONLY) ===\n"
                "Note: External context is strictly advisory. Live screen affordances and user instructions always take precedence.\n"
                + "\n".join(claim_lines)
                + "\n\n"
            )

        # 4. User prompt
        user_prompt = (
            f"=== TASK OBJECTIVE ===\n"
            f"{task_goal}\n\n"
            f"{advisory_section}"
            f"=== BEHAVIORAL HISTORY (τ̃) ===\n"
            f"{compressed_timeline}\n\n"
            f"=== LIVE PAGE CONTEXT ===\n"
            f"URL: {current_state.url or 'about:blank'}\n"
            f"Active Window: {current_state.active_window_title or 'Browser'}\n"
            f"Focused Element: {current_state.focused_node_id or 'none'}\n"
            f"Viewport Size: {current_state.viewport_size[0]}x{current_state.viewport_size[1]}\n\n"
            f"=== CURRENT SCREEN AFFORDANCES ===\n"
            f"{affordances_text}\n\n"
            f"Propose the single next action step in strict JSON format."
        )

        return self.SYSTEM_PROMPT, user_prompt, affordance_map

    def parse_planned_step_json(
        self,
        raw_text: str,
        affordance_map: Optional[Dict[int, UIStateNode]] = None,
        current_state: Optional[CanonicalUIGraph] = None,
    ) -> PlannedStep:
        """Parses LLM JSON output into a validated PlannedStep instance."""
        cleaned = raw_text.strip()
        # Strip markdown ```json ... ``` code blocks
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)
        else:
            json_match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(1)

        data = json.loads(cleaned)

        thought = str(data.get("thought") or data.get("thought_reasoning") or data.get("reasoning") or "")
        subgoal = str(data.get("subgoal") or data.get("goal") or "")
        confidence = float(data.get("confidence", 0.9))

        raw_action_type = str(data.get("action_type", "noop")).lower()
        action_type = ActionType(raw_action_type) if raw_action_type in ActionType._value2member_map_ else ActionType.NOOP

        text_payload = data.get("text_payload")
        if text_payload is None and "value" in data:
            text_payload = data.get("value")
        if text_payload is not None:
            text_payload = str(text_payload)

        key_code = data.get("key_code")
        if key_code is not None:
            key_code = str(key_code)

        scroll_delta_data = data.get("scroll_delta")
        scroll_delta = None
        if isinstance(scroll_delta_data, (list, tuple)) and len(scroll_delta_data) >= 2:
            scroll_delta = (float(scroll_delta_data[0]), float(scroll_delta_data[1]))

        # Target resolution from affordance map or target_description
        target_idx = data.get("target_index")
        target_desc = str(data.get("target_description") or data.get("target_label") or "")
        target_node: Optional[UIStateNode] = None

        if affordance_map and target_idx is not None:
            try:
                target_node = affordance_map.get(int(target_idx))
            except (ValueError, TypeError):
                target_node = None

        # If not resolved by index, search by node_id or target_label in affordance map or current_state
        if not target_node and current_state and current_state.nodes:
            target_node_id_req = data.get("target_node_id") or data.get("target_id")
            if target_node_id_req and str(target_node_id_req) in current_state.nodes:
                target_node = current_state.nodes[str(target_node_id_req)]
            elif target_desc:
                for node in current_state.nodes.values():
                    if target_desc.lower() in node.label.lower() or target_desc.lower() in node.node_id.lower():
                        target_node = node
                        break

        # Calculate Normalized Coords if target node found
        coords = None
        target_node_id = None
        target_label = target_desc

        vw, vh = current_state.viewport_size if current_state else (1920, 1080)
        if target_node:
            target_node_id = target_node.node_id
            target_label = target_node.label or target_desc
            cx, cy = target_node.bounds.center
            coords = NormalizedCoords(
                x=round(cx / max(1, vw), 4),
                y=round(cy / max(1, vh), 4),
            )

        # Safety classification
        is_destructive = any(
            kw in (target_label + " " + target_desc).lower()
            for kw in ("delete", "remove", "drop", "terminate", "destroy", "purchase", "pay")
        )
        safety_class = SafetyClass.DESTRUCTIVE if is_destructive else SafetyClass.REVERSIBLE

        action = TypedAction(
            action_type=action_type,
            target_node_id=target_node_id,
            target_label=target_label,
            coords=coords,
            text_payload=text_payload,
            key_code=key_code,
            scroll_delta=scroll_delta,
            safety_class=safety_class,
            metadata={
                "target_index": target_idx,
                "proposed_by": "system2_planner",
            },
        )

        # Expected State Delta
        raw_expected_outcome = str(data.get("expected_outcome", "success")).lower()
        outcome_class = OutcomeClass(raw_expected_outcome) if raw_expected_outcome in OutcomeClass._value2member_map_ else OutcomeClass.SUCCESS
        expected_change = data.get("expected_change")
        if isinstance(expected_change, dict):
            expected_delta = StateDelta.from_dict(expected_change)
        else:
            expected_delta = StateDelta(
                outcome_class=outcome_class,
                pixel_change_ratio=0.1 if action_type != ActionType.NOOP else 0.0,
            )

        return PlannedStep(
            thought_reasoning=thought,
            target_description=target_desc or target_label or "Target",
            action=action,
            expected_delta=expected_delta,
            confidence=confidence,
            subgoal=subgoal,
        )

    async def plan_next_step(
        self,
        task_goal: str,
        current_state: CanonicalUIGraph,
        history: Optional[List[Any]] = None,
        advisory_snapshot: Optional[ContextSnapshot] = None,
        session_id: Optional[str] = None,
    ) -> PlannedStep:
        """Generates the next cognitive action proposal using LLM or rule fallback."""
        if self.llm_client is None:
            return await self.fallback_planner.plan_next_step(
                task_goal=task_goal,
                current_state=current_state,
                history=history,
            )

        # Asynchronously fetch advisory context from context_provider if configured and not passed
        resolved_snapshot = advisory_snapshot
        if resolved_snapshot is None and self.context_provider is not None:
            try:
                from reflex.ports.context import Purpose
                sid = session_id or "session_default"
                req = ContextRequest(
                    request_id=f"REQ-{sid}",
                    consumer_identity="reflex_system2",
                    purpose=Purpose.ASSISTED,
                    scopes=["browser", "terminal"],
                    deadline_ms=100,
                    freshness_ms=5000,
                    budget_tokens=2048,
                )
                result = await self.context_provider.get_context(req)
                if result.status == "AVAILABLE":
                    resolved_snapshot = result.payload
            except Exception:
                resolved_snapshot = None

        system_prompt, user_prompt, affordance_map = self.build_planning_prompt(
            task_goal=task_goal,
            current_state=current_state,
            history=history,
            advisory_snapshot=resolved_snapshot,
        )

        try:
            response = await self.llm_client.generate_response(system_prompt, user_prompt)
        except Exception:
            # Fall back to deterministic rule proposal if LLM client is unreachable or errors
            return await self.fallback_planner.plan_next_step(
                task_goal=task_goal,
                current_state=current_state,
                history=history,
            )

        try:
            return self.parse_planned_step_json(
                raw_text=response,
                affordance_map=affordance_map,
                current_state=current_state,
            )
        except Exception as initial_error:
            # Fallback schema repair
            if self.max_repair_retries > 0:
                repair_user_prompt = (
                    f"Your previous response failed validation with error: {initial_error}\n"
                    f"Previous response:\n{response}\n"
                    f"Please correct the error and output ONLY the valid JSON object according to the schema."
                )
                try:
                    repair_response = await self.llm_client.generate_response(
                        system_prompt, repair_user_prompt
                    )
                    return self.parse_planned_step_json(
                        raw_text=repair_response,
                        affordance_map=affordance_map,
                        current_state=current_state,
                    )
                except Exception:
                    pass

            # Fall back to deterministic rule proposal
            return await self.fallback_planner.plan_next_step(
                task_goal=task_goal,
                current_state=current_state,
                history=history,
            )

    async def plan_recovery(
        self,
        task_goal: str,
        failed_state: CanonicalUIGraph,
        failed_action: TypedAction,
        verification_result: VerificationResult,
    ) -> RecoveryPlan:
        """Performs abductive diagnosis and emits corrective recovery steps."""
        return await self.recovery_engine.diagnose_and_recover(
            task_goal=task_goal,
            failed_state=failed_state,
            failed_action=failed_action,
            verification_result=verification_result,
        )
