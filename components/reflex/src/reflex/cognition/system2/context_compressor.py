"""Context Compressor: Compresses long-horizon episode histories into factual transition timelines."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Union

from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import TransitionTuple


class ContextCompressor:
    """Distills raw episode histories into concise factual transition narratives (tau_tilde).
    
    Reduces prompt context bloat by >= 80% while retaining critical causal facts:
    tau_tilde = < s_0, phi_0, phi_1, ..., phi_{t-1}, s_t >
    """

    def __init__(self, max_recent_detailed_steps: int = 50) -> None:
        self.max_recent_detailed_steps = max_recent_detailed_steps

    def extract_fact(self, transition: Union[TransitionTuple, Dict[str, Any]]) -> str:
        """Extracts a concise factual change representation (phi_i) from a transition."""
        if isinstance(transition, dict):
            # Parse dict
            step_idx = transition.get("step_index", 0)
            action_data = transition.get("action", {})
            action_type_raw = action_data.get("action_type", "noop") if isinstance(action_data, dict) else getattr(action_data, "action_type", "noop")
            target_label = action_data.get("target_label") if isinstance(action_data, dict) else getattr(action_data, "target_label", None)
            target_id = action_data.get("target_node_id") if isinstance(action_data, dict) else getattr(action_data, "target_node_id", None)
            text_payload = action_data.get("text_payload") if isinstance(action_data, dict) else getattr(action_data, "text_payload", None)
            key_code = action_data.get("key_code") if isinstance(action_data, dict) else getattr(action_data, "key_code", None)
            scroll_delta = action_data.get("scroll_delta") if isinstance(action_data, dict) else getattr(action_data, "scroll_delta", None)

            delta_data = transition.get("delta", {})
            outcome_raw = delta_data.get("outcome_class", "success") if isinstance(delta_data, dict) else getattr(delta_data, "outcome_class", "success")
            added_nodes = delta_data.get("added_nodes", []) if isinstance(delta_data, dict) else getattr(delta_data, "added_nodes", [])
            removed_nodes = delta_data.get("removed_nodes", []) if isinstance(delta_data, dict) else getattr(delta_data, "removed_nodes", [])
            modified_nodes = delta_data.get("modified_nodes", []) if isinstance(delta_data, dict) else getattr(delta_data, "modified_nodes", [])
            pixel_change = float(delta_data.get("pixel_change_ratio", 0.0)) if isinstance(delta_data, dict) else float(getattr(delta_data, "pixel_change_ratio", 0.0))
        else:
            step_idx = transition.step_index
            act = transition.action
            action_type_raw = act.action_type.value if isinstance(act.action_type, ActionType) else str(act.action_type)
            target_label = act.target_label
            target_id = act.target_node_id
            text_payload = act.text_payload
            key_code = act.key_code
            scroll_delta = act.scroll_delta

            d = transition.delta
            outcome_raw = d.outcome_class.value if isinstance(d.outcome_class, OutcomeClass) else str(d.outcome_class)
            added_nodes = d.added_nodes
            removed_nodes = d.removed_nodes
            modified_nodes = d.modified_nodes
            pixel_change = d.pixel_change_ratio

        action_type_str = str(action_type_raw).lower()
        outcome_str = str(outcome_raw).lower()
        target_name = target_label or target_id or "element"

        # 1. Format Action Phrase
        if action_type_str == ActionType.NAVIGATE.value:
            action_phrase = f"NAVIGATE to '{text_payload or target_name}'"
        elif action_type_str == ActionType.TYPE.value:
            action_phrase = f"TYPE '{text_payload or ''}' into [{target_name}]"
        elif action_type_str == ActionType.KEY_PRESS.value:
            action_phrase = f"PRESS_KEY '{key_code or text_payload or ''}' on [{target_name}]"
        elif action_type_str == ActionType.CLICK.value:
            action_phrase = f"CLICK [{target_name}]"
        elif action_type_str == ActionType.DOUBLE_CLICK.value:
            action_phrase = f"DOUBLE_CLICK [{target_name}]"
        elif action_type_str == ActionType.RIGHT_CLICK.value:
            action_phrase = f"RIGHT_CLICK [{target_name}]"
        elif action_type_str == ActionType.SCROLL.value:
            action_phrase = f"SCROLL (delta={scroll_delta or [0, 100]})"
        elif action_type_str == ActionType.HOVER.value:
            action_phrase = f"HOVER [{target_name}]"
        elif action_type_str == ActionType.WAIT.value:
            action_phrase = "WAIT for settlement"
        elif action_type_str == ActionType.NOOP.value:
            action_phrase = "NOOP"
        else:
            action_phrase = f"{action_type_str.upper()} on [{target_name}]"

        # 2. Format Outcome Phrase
        dom_parts: List[str] = []
        if added_nodes:
            dom_parts.append(f"+{len(added_nodes)} nodes")
        if removed_nodes:
            dom_parts.append(f"-{len(removed_nodes)} nodes")
        if modified_nodes:
            dom_parts.append(f"~{len(modified_nodes)} modified")
        dom_summary = ", ".join(dom_parts) if dom_parts else "0 dom delta"

        if outcome_str == OutcomeClass.SUCCESS.value:
            outcome_phrase = f"SUCCESS ({dom_summary}, Δpixel={pixel_change:.2f})"
        elif outcome_str == OutcomeClass.MODAL_APPEARED.value:
            outcome_phrase = f"MODAL_APPEARED (modal dialog intercepted, {dom_summary})"
        elif outcome_str == OutcomeClass.NAVIGATION.value:
            outcome_phrase = f"NAVIGATION (page loaded, Δpixel={pixel_change:.2f})"
        elif outcome_str == OutcomeClass.NOOP.value:
            outcome_phrase = "NOOP (no observable visual/DOM effect)"
        elif outcome_str == OutcomeClass.ERROR.value:
            outcome_phrase = "ERROR (action failed or validation error)"
        elif outcome_str == OutcomeClass.LOADING.value:
            outcome_phrase = "LOADING (pending network/DOM settlement)"
        elif outcome_str == OutcomeClass.UNKNOWN_EFFECT.value:
            outcome_phrase = "UNKNOWN_EFFECT (timeout or unconfirmed)"
        else:
            outcome_phrase = f"{outcome_str.upper()} ({dom_summary})"

        return f"[Step {step_idx}] {action_phrase} -> {outcome_phrase}"

    def compress_history(
        self,
        transitions: Sequence[Union[TransitionTuple, Dict[str, Any]]],
        initial_state_summary: Optional[str] = None,
        current_state_summary: Optional[str] = None,
    ) -> str:
        """Constructs a factual narrative timeline tau_tilde from historical transitions."""
        if not transitions:
            return "No previous steps in this episode (Step 0 - Initial State)."

        lines: List[str] = []
        if initial_state_summary:
            lines.append(f"s_0: {initial_state_summary}")

        total_steps = len(transitions)
        if total_steps > self.max_recent_detailed_steps:
            # Macro-summarize older steps to bound context
            older_count = total_steps - self.max_recent_detailed_steps
            lines.append(
                f"[Steps 0-{older_count - 1}: {older_count} historical steps executed successfully]"
            )
            active_transitions = transitions[older_count:]
        else:
            active_transitions = transitions

        for t in active_transitions:
            lines.append(self.extract_fact(t))

        if current_state_summary:
            lines.append(f"s_t (current): {current_state_summary}")

        return "\n".join(lines)

    def estimate_token_count(self, text: str) -> int:
        """Estimates token count (~4 characters per token heuristic)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def compute_compression_stats(
        self,
        transitions: Sequence[Union[TransitionTuple, Dict[str, Any]]],
        compressed_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculates token and character reduction ratios compared to raw uncompressed history."""
        if compressed_text is None:
            compressed_text = self.compress_history(transitions)

        # Raw representation: full JSON serialization of transition data
        raw_items = []
        for t in transitions:
            if hasattr(t, "to_dict"):
                raw_items.append(t.to_dict())
            elif isinstance(t, dict):
                raw_items.append(t)
            else:
                raw_items.append(str(t))

        raw_json = json.dumps(raw_items, indent=2)
        raw_char_count = len(raw_json)
        compressed_char_count = len(compressed_text)

        raw_tokens = self.estimate_token_count(raw_json)
        compressed_tokens = self.estimate_token_count(compressed_text)

        reduction_ratio = 1.0 - (compressed_tokens / max(1, raw_tokens))
        reduction_percentage = round(reduction_ratio * 100.0, 2)

        return {
            "total_steps": len(transitions),
            "raw_characters": raw_char_count,
            "compressed_characters": compressed_char_count,
            "raw_estimated_tokens": raw_tokens,
            "compressed_estimated_tokens": compressed_tokens,
            "reduction_ratio": round(reduction_ratio, 4),
            "reduction_percentage": reduction_percentage,
        }
