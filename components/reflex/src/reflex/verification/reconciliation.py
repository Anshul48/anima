"""Reconciliation Engine: Non-destructive diagnostic state probe and recovery advisor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.settlement_observer import SettlementObserver


@dataclass(frozen=True)
class ReconciliationReport:
    """Diagnostic state assessment produced after an uncertain or failed outcome."""
    action_id: str
    inferred_cause: str
    current_state_summary: str
    is_retry_safe: bool
    recommended_recovery_action: str
    captured_state: Optional[CanonicalUIGraph] = None
    active_focus_node_id: Optional[str] = None
    recent_errors: List[str] = field(default_factory=list)
    pending_requests: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "inferred_cause": self.inferred_cause,
            "current_state_summary": self.current_state_summary,
            "is_retry_safe": self.is_retry_safe,
            "recommended_recovery_action": self.recommended_recovery_action,
            "captured_state": self.captured_state.to_dict() if self.captured_state else None,
            "active_focus_node_id": self.active_focus_node_id,
            "recent_errors": list(self.recent_errors),
            "pending_requests": list(self.pending_requests),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ReconciliationReport:
        return cls(
            action_id=str(data.get("action_id", "")),
            inferred_cause=str(data.get("inferred_cause", "")),
            current_state_summary=str(data.get("current_state_summary", "")),
            is_retry_safe=bool(data.get("is_retry_safe", False)),
            recommended_recovery_action=str(data.get("recommended_recovery_action", "")),
            captured_state=CanonicalUIGraph.from_dict(data["captured_state"]) if data.get("captured_state") else None,
            active_focus_node_id=data.get("active_focus_node_id"),
            recent_errors=list(data.get("recent_errors", [])),
            pending_requests=list(data.get("pending_requests", [])),
            metadata=data.get("metadata", {}),
        )


class ReconciliationEngine:
    """Performs non-destructive diagnostic probes and advises System 2 on safe recovery."""

    def __init__(
        self,
        observation_port: Optional[ObservationPort] = None,
        settlement_observer: Optional[SettlementObserver] = None,
        clock: Optional[ClockPort] = None,
    ) -> None:
        self.observation_port = observation_port
        self.settlement_observer = settlement_observer or SettlementObserver(clock=clock)
        self.clock: ClockPort = clock or SystemClock()

    async def reconcile(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
        action_id: str = "",
        outcome: OutcomeClass = OutcomeClass.UNKNOWN_EFFECT,
        verification_details: str = "",
        console_events: Optional[List[Dict[str, Any]]] = None,
        http_responses: Optional[List[Dict[str, Any]]] = None,
        pending_requests: Optional[List[str]] = None,
    ) -> ReconciliationReport:
        """Executes non-destructive state probe and synthesizes diagnostic reconciliation report."""
        # 1. Capture fresh state snapshot S_{probe}
        captured_state: Optional[CanonicalUIGraph] = None
        if self.observation_port is not None:
            try:
                captured_state = await self.observation_port.capture_state()
            except Exception:
                captured_state = None

        if captured_state is None:
            captured_state = before_state

        probe_nodes = captured_state.nodes if captured_state and captured_state.nodes else {}
        before_nodes = before_state.nodes if before_state and before_state.nodes else {}

        # 2. Focus Audit
        active_focus_node_id = captured_state.focused_node_id
        if not active_focus_node_id:
            for n_id, n in probe_nodes.items():
                if n.is_focused:
                    active_focus_node_id = n_id
                    break

        # 3. Collect Recent Errors
        recent_errors: List[str] = []
        if console_events:
            for ev in console_events:
                if ev.get("level") in ("error", "fatal", "exception"):
                    recent_errors.append(f"Console: {ev.get('text', '')}")
        if http_responses:
            for resp in http_responses:
                st = resp.get("status", 200)
                if st >= 400:
                    recent_errors.append(f"HTTP {st} on {resp.get('url', '')}")

        # 4. In-Flight / Pending Requests
        in_flight_list = list(pending_requests or [])
        if self.settlement_observer:
            for req_id in self.settlement_observer._in_flight_requests:
                if req_id not in in_flight_list:
                    in_flight_list.append(req_id)

        # 5. Compute Structural Changes
        added_node_ids = [n_id for n_id in probe_nodes if n_id not in before_nodes]
        removed_node_ids = [n_id for n_id in before_nodes if n_id not in probe_nodes]
        modified_node_ids = [
            n_id
            for n_id in probe_nodes
            if n_id in before_nodes and (
                before_nodes[n_id].value != probe_nodes[n_id].value
                or before_nodes[n_id].label != probe_nodes[n_id].label
                or before_nodes[n_id].is_focused != probe_nodes[n_id].is_focused
            )
        ]

        total_dom_delta = len(added_node_ids) + len(removed_node_ids) + len(modified_node_ids)

        # Detect Modal Appearance
        modal_nodes = [
            n_id
            for n_id in probe_nodes
            if probe_nodes[n_id].role == NodeRole.MODAL
            or probe_nodes[n_id].attributes.get("role") in ("dialog", "alertdialog")
            or "modal" in probe_nodes[n_id].attributes.get("class", "").lower()
        ]
        new_modal_present = any(m_id not in before_nodes for m_id in modal_nodes)

        # 6. Assess Inferred Cause and Safe Recovery Strategy
        inferred_cause = ""
        is_retry_safe = False
        recommended_recovery_action = ""

        # Case A: Modal Interception
        if new_modal_present:
            inferred_cause = "modal_interception: an unexpected modal or dialog blocked interaction"
            is_retry_safe = False
            recommended_recovery_action = "dismiss_modal: interact with or close the dialog before continuing"

        # Case B: Unhandled Fatal Errors / Exceptions
        elif recent_errors:
            inferred_cause = f"runtime_exception: {recent_errors[0]}"
            is_retry_safe = False
            recommended_recovery_action = "replan: handle error or refresh surface; avoid blind retry"

        # Case C: NOOP / Zero DOM Change
        elif total_dom_delta == 0:
            if action.target_node_id and action.target_node_id not in probe_nodes:
                inferred_cause = f"target_missing: target node '{action.target_node_id}' not found in current UI graph"
                is_retry_safe = False
                recommended_recovery_action = "reground: target node moved or vanished; re-ground active UI state"
            elif action.target_node_id and active_focus_node_id != action.target_node_id:
                inferred_cause = "focus_miss: target element did not receive focus or input event"
                if action.safety_class == SafetyClass.REVERSIBLE:
                    is_retry_safe = True
                    recommended_recovery_action = "reground_and_retry: re-focus element or click center coordinates"
                else:
                    is_retry_safe = False
                    recommended_recovery_action = "replan: target action is destructive; verify backend status first"
            else:
                inferred_cause = "inert_element_or_unresponsive_target: action had zero visual or structural effect"
                if action.safety_class == SafetyClass.REVERSIBLE:
                    is_retry_safe = True
                    recommended_recovery_action = "reground_and_retry: re-estimate target coordinates and retry"
                else:
                    is_retry_safe = False
                    recommended_recovery_action = "replan: verify if action took effect on server side"

        # Case D: Timeout with partial or delayed state changes
        elif outcome == OutcomeClass.UNKNOWN_EFFECT:
            # Check if intended change actually landed
            target_id = action.target_node_id
            if target_id and (target_id in modified_node_ids or target_id in added_node_ids):
                inferred_cause = "delayed_transition_completed_after_timeout: target state mutated after timeout limit"
                is_retry_safe = False
                recommended_recovery_action = "advance_trajectory: state transition landed; re-ground and proceed"
            else:
                inferred_cause = "unconfirmed_dispatch_timeout: partial DOM mutations detected without definitive confirmation"
                is_retry_safe = False
                recommended_recovery_action = "replan: perform fresh full-state observation before continuing"

        # Case E: Default fallback
        else:
            inferred_cause = f"unverified_outcome_{outcome.value}: {verification_details}"
            is_retry_safe = (action.safety_class == SafetyClass.REVERSIBLE and total_dom_delta == 0)
            recommended_recovery_action = "reground_and_retry" if is_retry_safe else "replan: inspect current state"

        # 7. State Summary
        current_state_summary = (
            f"URL: {captured_state.url or 'unknown'}, "
            f"Total Nodes: {len(probe_nodes)}, "
            f"Active Focus: {active_focus_node_id or 'none'}, "
            f"Modals Active: {len(modal_nodes)}, "
            f"In-Flight Requests: {len(in_flight_list)}, "
            f"Recent Errors: {len(recent_errors)}"
        )

        return ReconciliationReport(
            action_id=action_id,
            inferred_cause=inferred_cause,
            current_state_summary=current_state_summary,
            is_retry_safe=is_retry_safe,
            recommended_recovery_action=recommended_recovery_action,
            captured_state=captured_state,
            active_focus_node_id=active_focus_node_id,
            recent_errors=recent_errors,
            pending_requests=in_flight_list,
            metadata={
                "added_nodes_count": len(added_node_ids),
                "removed_nodes_count": len(removed_node_ids),
                "modified_nodes_count": len(modified_node_ids),
                "action_type": action.action_type.value,
                "safety_class": action.safety_class.value,
            },
        )
