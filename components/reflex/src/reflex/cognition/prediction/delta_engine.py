"""Reflex Expected Delta Engine: Deterministic expected state delta predictor for action primitives."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from reflex.ports.prediction import ExpectedDeltaPredictorPort
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import CanonicalUIGraph, NodeRole, UIStateNode


class ExpectedDeltaEngine(ExpectedDeltaPredictorPort):
    """Generates deterministic expected state deltas (ΔS_hat) for action primitives.

    Evaluates pre-action state and dispatched action according to deterministic DOM rules,
    producing expected node additions/removals/modifications, pixel change ratio,
    and outcome classification (e.g. NAVIGATION, SUCCESS, LOADING, MODAL_APPEARED).
    """

    def __init__(self) -> None:
        self._custom_rules: List[
            Callable[[CanonicalUIGraph, TypedAction], Optional[StateDelta]]
        ] = []

    def register_rule(
        self,
        rule: Callable[[CanonicalUIGraph, TypedAction], Optional[StateDelta]],
    ) -> None:
        """Registers a custom prediction rule evaluated before default heuristics."""
        self._custom_rules.append(rule)

    def find_target_node(
        self,
        current_state: Optional[CanonicalUIGraph],
        action: TypedAction,
    ) -> Optional[UIStateNode]:
        """Resolves target node from action target_node_id, coords, or label."""
        if not current_state or not current_state.nodes:
            return None

        # 1. Direct ID lookup
        if action.target_node_id and action.target_node_id in current_state.nodes:
            return current_state.nodes[action.target_node_id]

        # 2. Coordinate spatial collision lookup
        if action.coords is not None:
            vw, vh = current_state.viewport_size or (1920, 1080)
            px, py = action.coords.to_pixel(vw, vh)
            # Find candidate nodes containing coordinate (prefer smaller/leaf nodes)
            candidates: List[UIStateNode] = []
            for node in current_state.nodes.values():
                b = node.bounds
                if b.x1 <= px <= b.x2 and b.y1 <= py <= b.y2:
                    candidates.append(node)
            if candidates:
                # Sort by bounding box area ascending (deepest / smallest element first)
                candidates.sort(key=lambda n: n.bounds.width * n.bounds.height)
                return candidates[0]

        # 3. Label matching lookup
        if action.target_label:
            target_clean = action.target_label.strip().lower()
            for node in current_state.nodes.values():
                if node.label and target_clean in node.label.strip().lower():
                    return node

        return None

    def predict_expected_delta(
        self,
        current_state: CanonicalUIGraph,
        action: TypedAction,
    ) -> StateDelta:
        """Generates deterministic expected state delta for an action on current UI state."""
        # 1. Evaluate custom registered rules first
        for rule in self._custom_rules:
            res = rule(current_state, action)
            if res is not None:
                return res

        atype = action.action_type
        target_node = self.find_target_node(current_state, action)
        target_id = target_node.node_id if target_node else action.target_node_id
        vw, vh = current_state.viewport_size if current_state else (1920, 1080)
        viewport_box = (0, 0, vw, vh)

        # 2. Handle Action Primitives
        if atype == ActionType.NAVIGATE:
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=[],
                pixel_change_ratio=0.50,
                changed_bounding_boxes=[viewport_box],
                outcome_class=OutcomeClass.NAVIGATION,
            )

        elif atype == ActionType.SCROLL:
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=[],
                pixel_change_ratio=0.15,
                changed_bounding_boxes=[viewport_box],
                outcome_class=OutcomeClass.SUCCESS,
            )

        elif atype in (ActionType.WAIT, ActionType.NOOP):
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=[],
                pixel_change_ratio=0.0,
                changed_bounding_boxes=[],
                outcome_class=OutcomeClass.SUCCESS,
            )

        elif atype == ActionType.HOVER:
            mod_nodes = [target_id] if target_id else []
            changed_boxes = (
                [(target_node.bounds.x1, target_node.bounds.y1, target_node.bounds.x2, target_node.bounds.y2)]
                if target_node else []
            )
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=mod_nodes,
                pixel_change_ratio=0.002,
                changed_bounding_boxes=changed_boxes,
                outcome_class=OutcomeClass.SUCCESS,
            )

        elif atype == ActionType.TYPE:
            mod_nodes = [target_id] if target_id else []
            if not mod_nodes and current_state and current_state.focused_node_id:
                mod_nodes = [current_state.focused_node_id]
            changed_boxes = (
                [(target_node.bounds.x1, target_node.bounds.y1, target_node.bounds.x2, target_node.bounds.y2)]
                if target_node else []
            )
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=mod_nodes,
                pixel_change_ratio=0.005,
                changed_bounding_boxes=changed_boxes,
                outcome_class=OutcomeClass.SUCCESS,
            )

        elif atype in (ActionType.CLICK, ActionType.DOUBLE_CLICK, ActionType.RIGHT_CLICK):
            return self._predict_click_delta(current_state, action, target_node, target_id, viewport_box)

        elif atype == ActionType.KEY_PRESS:
            return self._predict_key_press_delta(current_state, action, target_node, target_id, viewport_box)

        elif atype == ActionType.DRAG_AND_DROP:
            mod_nodes = [target_id] if target_id else []
            changed_boxes = (
                [(target_node.bounds.x1, target_node.bounds.y1, target_node.bounds.x2, target_node.bounds.y2)]
                if target_node else []
            )
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=mod_nodes,
                pixel_change_ratio=0.05,
                changed_bounding_boxes=changed_boxes,
                outcome_class=OutcomeClass.SUCCESS,
            )

        # Default fallback
        return StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=[target_id] if target_id else [],
            pixel_change_ratio=0.01,
            changed_bounding_boxes=[],
            outcome_class=OutcomeClass.SUCCESS,
        )

    def _predict_click_delta(
        self,
        current_state: CanonicalUIGraph,
        action: TypedAction,
        target_node: Optional[UIStateNode],
        target_id: Optional[str],
        viewport_box: Tuple[int, int, int, int],
    ) -> StateDelta:
        """Determines expected delta for CLICK primitive across DOM element types."""
        if target_node is None:
            # Click without resolved target node
            mod_nodes = [target_id] if target_id else []
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=mod_nodes,
                pixel_change_ratio=0.01,
                changed_bounding_boxes=[],
                outcome_class=OutcomeClass.SUCCESS,
            )

        role = target_node.role
        attrs = target_node.attributes or {}
        label = (target_node.label or "").lower()
        node_box = (target_node.bounds.x1, target_node.bounds.y1, target_node.bounds.x2, target_node.bounds.y2)

        # 1. Anchor / Navigation Link
        if role == NodeRole.LINK or attrs.get("href") or attrs.get("tag") == "a":
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=[],
                pixel_change_ratio=0.50,
                changed_bounding_boxes=[viewport_box],
                outcome_class=OutcomeClass.NAVIGATION,
            )

        # 2. Checkbox, Toggle, or Radio element
        if (
            role in (NodeRole.CHECKBOX, NodeRole.TOGGLE, NodeRole.RADIO)
            or attrs.get("type") in ("checkbox", "radio")
            or attrs.get("role") in ("checkbox", "switch", "radio")
        ):
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=[target_node.node_id],
                pixel_change_ratio=0.005,
                changed_bounding_boxes=[node_box],
                outcome_class=OutcomeClass.SUCCESS,
            )

        # 3. Modal Trigger (opens dialog)
        is_modal_trigger = (
            attrs.get("aria-haspopup") in ("dialog", "modal", "true")
            or attrs.get("data-toggle") == "modal"
            or "open modal" in label
            or "show dialog" in label
            or "popup" in label
        )
        if is_modal_trigger:
            return StateDelta(
                added_nodes=["modal_root"],
                removed_nodes=[],
                modified_nodes=[target_node.node_id],
                pixel_change_ratio=0.20,
                changed_bounding_boxes=[node_box],
                outcome_class=OutcomeClass.MODAL_APPEARED,
            )

        # 4. Modal Close / Dismiss Button
        is_modal_close = (
            label in ("close", "dismiss", "cancel", "×", "x")
            or attrs.get("aria-label", "").lower() in ("close", "dismiss")
            or "close" in target_node.node_id.lower()
        )
        has_active_modal = current_state and any(
            n.role == NodeRole.MODAL for n in current_state.nodes.values()
        )
        if is_modal_close and has_active_modal:
            modal_ids = [
                n.node_id for n in current_state.nodes.values() if n.role == NodeRole.MODAL
            ]
            return StateDelta(
                added_nodes=[],
                removed_nodes=modal_ids or ["modal_root"],
                modified_nodes=[],
                pixel_change_ratio=0.20,
                changed_bounding_boxes=[viewport_box],
                outcome_class=OutcomeClass.SUCCESS,
            )

        # 5. Form Submit / Loading Button
        is_submit = (
            attrs.get("type") == "submit"
            or any(kw in label for kw in ("submit", "log in", "login", "sign in", "checkout", "pay", "register"))
        )
        if is_submit:
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=[target_node.node_id],
                pixel_change_ratio=0.05,
                changed_bounding_boxes=[node_box],
                outcome_class=OutcomeClass.SUCCESS,
            )

        # 6. Generic Button or interactive element
        return StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=[target_node.node_id],
            pixel_change_ratio=0.01,
            changed_bounding_boxes=[node_box],
            outcome_class=OutcomeClass.SUCCESS,
        )

    def _predict_key_press_delta(
        self,
        current_state: CanonicalUIGraph,
        action: TypedAction,
        target_node: Optional[UIStateNode],
        target_id: Optional[str],
        viewport_box: Tuple[int, int, int, int],
    ) -> StateDelta:
        """Determines expected delta for KEY_PRESS primitive."""
        key = (action.key_code or "").lower()

        # Escape key closes active modal if present
        if key in ("escape", "esc"):
            has_active_modal = current_state and any(
                n.role == NodeRole.MODAL for n in current_state.nodes.values()
            )
            if has_active_modal:
                modal_ids = [
                    n.node_id for n in current_state.nodes.values() if n.role == NodeRole.MODAL
                ]
                return StateDelta(
                    added_nodes=[],
                    removed_nodes=modal_ids or ["modal_root"],
                    modified_nodes=[],
                    pixel_change_ratio=0.20,
                    changed_bounding_boxes=[viewport_box],
                    outcome_class=OutcomeClass.SUCCESS,
                )

        # Enter key triggers submit / navigation if on input/form
        if key in ("enter", "return"):
            mod_nodes = [target_id] if target_id else []
            if not mod_nodes and current_state and current_state.focused_node_id:
                mod_nodes = [current_state.focused_node_id]
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=mod_nodes,
                pixel_change_ratio=0.05,
                changed_bounding_boxes=[viewport_box],
                outcome_class=OutcomeClass.SUCCESS,
            )

        # Tab key cycles focus
        if key == "tab":
            mod_nodes = [target_id] if target_id else []
            if current_state and current_state.focused_node_id:
                mod_nodes.append(current_state.focused_node_id)
            return StateDelta(
                added_nodes=[],
                removed_nodes=[],
                modified_nodes=list(set(mod_nodes)),
                pixel_change_ratio=0.002,
                changed_bounding_boxes=[],
                outcome_class=OutcomeClass.SUCCESS,
            )

        # Default standard typing key press
        mod_nodes = [target_id] if target_id else []
        if not mod_nodes and current_state and current_state.focused_node_id:
            mod_nodes = [current_state.focused_node_id]

        return StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=mod_nodes,
            pixel_change_ratio=0.005,
            changed_bounding_boxes=[],
            outcome_class=OutcomeClass.SUCCESS,
        )
