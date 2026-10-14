"""Independent Verifier: Objective programmatic post-action evaluation and classification."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.ports.verification import VerificationEnginePort, VerificationPort
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.settlement_observer import SettlementObserver, SettlementResult


@dataclass(frozen=True)
class AssertionRule:
    """Individual assertion rule evaluated during verification."""
    assertion_type: str  # e.g., "element_present", "url_equals", "no_console_error", "element_value_equals"
    target_value: str = ""
    is_critical: bool = True
    target_node_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assertion_type": self.assertion_type,
            "target_value": self.target_value,
            "is_critical": self.is_critical,
            "target_node_id": self.target_node_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AssertionRule:
        return cls(
            assertion_type=data["assertion_type"],
            target_value=str(data.get("target_value", "")),
            is_critical=bool(data.get("is_critical", True)),
            target_node_id=data.get("target_node_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class VerificationResult:
    """Comprehensive verification outcome emitted to the Host Kernel."""
    outcome: OutcomeClass
    delta: StateDelta
    passed_assertions: List[str]
    failed_assertions: List[str]
    settlement_duration_ms: float
    requires_reconciliation: bool = False
    details: str = ""
    after_state: Optional[CanonicalUIGraph] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value if isinstance(self.outcome, OutcomeClass) else str(self.outcome),
            "delta": self.delta.to_dict(),
            "passed_assertions": list(self.passed_assertions),
            "failed_assertions": list(self.failed_assertions),
            "settlement_duration_ms": self.settlement_duration_ms,
            "requires_reconciliation": self.requires_reconciliation,
            "details": self.details,
            "after_state": self.after_state.to_dict() if self.after_state else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VerificationResult:
        raw_outcome = data.get("outcome", OutcomeClass.SUCCESS.value)
        outcome = OutcomeClass(raw_outcome) if raw_outcome in OutcomeClass._value2member_map_ else OutcomeClass(raw_outcome.lower())
        return cls(
            outcome=outcome,
            delta=StateDelta.from_dict(data["delta"]),
            passed_assertions=list(data.get("passed_assertions", [])),
            failed_assertions=list(data.get("failed_assertions", [])),
            settlement_duration_ms=float(data.get("settlement_duration_ms", 0.0)),
            requires_reconciliation=bool(data.get("requires_reconciliation", False)),
            details=str(data.get("details", "")),
            after_state=CanonicalUIGraph.from_dict(data["after_state"]) if data.get("after_state") else None,
        )


class IndependentVerifier(VerificationEnginePort):
    """Independent verification engine performing decoupled post-action assertion checking."""

    FATAL_ERROR_PATTERNS = [
        re.compile(r"TypeError:", re.IGNORECASE),
        re.compile(r"ReferenceError:", re.IGNORECASE),
        re.compile(r"SyntaxError:", re.IGNORECASE),
        re.compile(r"RangeError:", re.IGNORECASE),
        re.compile(r"Uncaught\s+", re.IGNORECASE),
        re.compile(r"UnhandledPromiseRejection", re.IGNORECASE),
        re.compile(r"Cannot read propert", re.IGNORECASE),
        re.compile(r"null is not an object", re.IGNORECASE),
        re.compile(r"undefined is not a function", re.IGNORECASE),
    ]

    def __init__(
        self,
        observation_port: Optional[ObservationPort] = None,
        settlement_observer: Optional[SettlementObserver] = None,
        clock: Optional[ClockPort] = None,
        reconciliation_engine: Optional[Any] = None,
    ) -> None:
        self.observation_port = observation_port
        self.settlement_observer = settlement_observer or SettlementObserver(clock=clock)
        self.clock: ClockPort = clock or SystemClock()
        self.reconciliation_engine = reconciliation_engine

        self._console_events: List[Dict[str, Any]] = []
        self._http_responses: List[Dict[str, Any]] = []

    def record_console_event(self, level: str, text: str, source: str = "") -> None:
        """Records a browser console message / error event."""
        self._console_events.append({
            "level": level.lower(),
            "text": text,
            "source": source,
            "timestamp_ms": self.clock.now_ms(),
        })

    def record_http_response(self, url: str, status: int, method: str = "GET") -> None:
        """Records an HTTP response status code."""
        self._http_responses.append({
            "url": url,
            "status": int(status),
            "method": method.upper(),
            "timestamp_ms": self.clock.now_ms(),
        })

    def clear_events(self) -> None:
        """Clears recorded console events and HTTP responses."""
        self._console_events.clear()
        self._http_responses.clear()

    @property
    def console_events(self) -> List[Dict[str, Any]]:
        return list(self._console_events)

    @property
    def http_responses(self) -> List[Dict[str, Any]]:
        return list(self._http_responses)

    def compute_state_delta(
        self,
        before_state: CanonicalUIGraph,
        after_state: CanonicalUIGraph,
    ) -> StateDelta:
        """Computes structural and visual difference between S_t and S_{t+1}."""
        before_nodes = before_state.nodes if before_state and before_state.nodes else {}
        after_nodes = after_state.nodes if after_state and after_state.nodes else {}

        added_node_ids = [n_id for n_id in after_nodes if n_id not in before_nodes]
        removed_node_ids = [n_id for n_id in before_nodes if n_id not in after_nodes]
        modified_node_ids: List[str] = []

        changed_boxes: List[Tuple[int, int, int, int]] = []

        # Find modified nodes
        for n_id in after_nodes:
            if n_id in before_nodes:
                b_node = before_nodes[n_id]
                a_node = after_nodes[n_id]
                if (
                    b_node.value != a_node.value
                    or b_node.label != a_node.label
                    or b_node.is_focused != a_node.is_focused
                    or b_node.is_enabled != a_node.is_enabled
                    or b_node.bounds != a_node.bounds
                    or b_node.attributes != a_node.attributes
                ):
                    modified_node_ids.append(n_id)
                    changed_boxes.append((a_node.bounds.x1, a_node.bounds.y1, a_node.bounds.x2, a_node.bounds.y2))

        # Add boxes of added and removed nodes
        for n_id in added_node_ids:
            node = after_nodes[n_id]
            changed_boxes.append((node.bounds.x1, node.bounds.y1, node.bounds.x2, node.bounds.y2))

        for n_id in removed_node_ids:
            node = before_nodes[n_id]
            changed_boxes.append((node.bounds.x1, node.bounds.y1, node.bounds.x2, node.bounds.y2))

        # Pixel change ratio estimation
        vw, vh = after_state.viewport_size if after_state else (1920, 1080)
        viewport_area = max(1, vw * vh)
        total_changed_area = sum(
            max(0, b[2] - b[0]) * max(0, b[3] - b[1]) for b in changed_boxes
        )

        pixel_change_ratio = min(1.0, total_changed_area / viewport_area)
        if before_state and after_state and before_state.url != after_state.url and after_state.url is not None:
            pixel_change_ratio = max(pixel_change_ratio, 0.5)

        return StateDelta(
            added_nodes=added_node_ids,
            removed_nodes=removed_node_ids,
            modified_nodes=modified_node_ids,
            pixel_change_ratio=pixel_change_ratio,
            changed_bounding_boxes=changed_boxes,
            outcome_class=OutcomeClass.SUCCESS,
        )

    def evaluate_assertions(
        self,
        before_state: CanonicalUIGraph,
        after_state: CanonicalUIGraph,
        delta: StateDelta,
        action: TypedAction,
        custom_assertions: Optional[List[AssertionRule]] = None,
    ) -> Tuple[List[str], List[str], List[str]]:
        """Evaluates objective assertions against post-state and recorded events.

        Returns (passed_assertions, failed_assertions, failed_critical_assertions).
        """
        passed: List[str] = []
        failed: List[str] = []
        critical_failed: List[str] = []

        # 1. Objective Assertion: No Fatal Console Errors
        has_fatal_console_error = False
        fatal_error_msg = ""
        for ev in self._console_events:
            lvl = ev.get("level", "")
            txt = ev.get("text", "")
            if lvl in ("error", "fatal", "exception"):
                has_fatal_console_error = True
                fatal_error_msg = txt
                break
            for pat in self.FATAL_ERROR_PATTERNS:
                if pat.search(txt):
                    has_fatal_console_error = True
                    fatal_error_msg = txt
                    break
            if has_fatal_console_error:
                break

        if not has_fatal_console_error:
            passed.append("no_fatal_console_errors")
        else:
            msg = f"fatal_console_error: {fatal_error_msg}"
            failed.append(msg)
            critical_failed.append(msg)

        # 2. Objective Assertion: HTTP Status != 4xx/5xx
        has_http_error = False
        http_err_msg = ""
        for resp in self._http_responses:
            st = resp.get("status", 200)
            if st >= 400:
                has_http_error = True
                http_err_msg = f"{resp.get('url')} responded with HTTP {st}"
                break

        if not has_http_error:
            passed.append("http_status_ok")
        else:
            msg = f"http_status_error: {http_err_msg}"
            failed.append(msg)
            critical_failed.append(msg)

        # 3. Evaluate Custom Assertions
        rules = custom_assertions or []
        for rule in rules:
            rule_name = f"{rule.assertion_type}({rule.target_value})"
            rule_passed = self._evaluate_single_assertion(
                rule=rule,
                before_state=before_state,
                after_state=after_state,
                delta=delta,
                action=action,
            )

            if rule_passed:
                passed.append(rule_name)
            else:
                failed.append(rule_name)
                if rule.is_critical:
                    critical_failed.append(rule_name)

        return passed, failed, critical_failed

    def _evaluate_single_assertion(
        self,
        rule: AssertionRule,
        before_state: CanonicalUIGraph,
        after_state: CanonicalUIGraph,
        delta: StateDelta,
        action: TypedAction,
    ) -> bool:
        """Evaluates an individual AssertionRule."""
        atype = rule.assertion_type.lower()
        tval = rule.target_value
        tid = rule.target_node_id

        after_nodes = after_state.nodes if after_state else {}

        if atype == "no_console_error":
            return not any(
                ev.get("level") in ("error", "fatal", "exception") for ev in self._console_events
            )

        elif atype in ("http_status_ok", "status_code_ok"):
            return not any(resp.get("status", 200) >= 400 for resp in self._http_responses)

        elif atype == "url_equals":
            return after_state.url == tval if after_state else False

        elif atype == "url_contains":
            return tval in (after_state.url or "") if after_state else False

        elif atype == "element_present":
            if tid and tid in after_nodes:
                return True
            if tval:
                return any(
                    tval.lower() in n.label.lower() or tval.lower() in n.value.lower()
                    for n in after_nodes.values()
                )
            return False

        elif atype == "element_absent":
            if tid and tid in after_nodes:
                return False
            if tval:
                return not any(
                    tval.lower() in n.label.lower() or tval.lower() in n.value.lower()
                    for n in after_nodes.values()
                )
            return True

        elif atype == "element_value_equals":
            node = after_nodes.get(tid) if tid else None
            if not node and tval:
                for n in after_nodes.values():
                    if n.label == rule.metadata.get("target_label", ""):
                        node = n
                        break
            return node.value == tval if node else False

        elif atype == "element_value_contains":
            node = after_nodes.get(tid) if tid else None
            return tval in (node.value if node else "")

        elif atype == "text_contains":
            return any(
                tval.lower() in n.label.lower() or tval.lower() in n.value.lower()
                for n in after_nodes.values()
            )

        elif atype == "modal_not_present":
            return not any(n.role == NodeRole.MODAL for n in after_nodes.values())

        elif atype == "modal_present":
            return any(n.role == NodeRole.MODAL for n in after_nodes.values())

        elif atype == "element_focused":
            if tid:
                return after_state.focused_node_id == tid or (tid in after_nodes and after_nodes[tid].is_focused)
            return False

        elif atype == "delta_not_empty":
            return (len(delta.added_nodes) + len(delta.removed_nodes) + len(delta.modified_nodes)) > 0

        # Fallback unknown assertion type
        return True

    def classify_outcome(
        self,
        before_state: CanonicalUIGraph,
        after_state: CanonicalUIGraph,
        delta: StateDelta,
        action: TypedAction,
        failed_critical: List[str],
        settlement_timed_out: bool = False,
    ) -> OutcomeClass:
        """Classifies the verified outcome according to architectural rules."""
        # 1. Hard settlement timeout or unconfirmed dispatch
        if settlement_timed_out:
            return OutcomeClass.UNKNOWN_EFFECT

        # 2. Fatal errors (critical assertion failures, console exceptions, HTTP 4xx/5xx)
        if failed_critical:
            return OutcomeClass.ERROR

        after_nodes = after_state.nodes if after_state else {}
        before_nodes = before_state.nodes if before_state else {}

        # 3. Navigation detected
        if (
            after_state
            and before_state
            and after_state.url
            and before_state.url
            and after_state.url != before_state.url
        ):
            return OutcomeClass.NAVIGATION

        if action.action_type == ActionType.NAVIGATE:
            return OutcomeClass.NAVIGATION

        # 4. Modal Intercepted (new modal node appeared)
        new_modal_nodes = [
            n_id
            for n_id in delta.added_nodes
            if n_id in after_nodes and (
                after_nodes[n_id].role == NodeRole.MODAL
                or after_nodes[n_id].attributes.get("role") in ("dialog", "alertdialog")
                or "modal" in after_nodes[n_id].attributes.get("class", "").lower()
            )
        ]
        if new_modal_nodes and action.target_node_id not in new_modal_nodes:
            return OutcomeClass.MODAL_APPEARED

        # 5. Loading State Active
        has_busy = any(
            n.attributes.get("aria-busy") == "true"
            or "spinner" in n.attributes.get("class", "").lower()
            or "loading" in n.attributes.get("class", "").lower()
            for n in after_nodes.values()
        )
        if has_busy or self.settlement_observer.in_flight_request_count > 0:
            return OutcomeClass.LOADING

        # 6. NOOP (0 DOM delta and 0 pixel change for actions expected to mutate state)
        is_zero_delta = (
            len(delta.added_nodes) == 0
            and len(delta.removed_nodes) == 0
            and len(delta.modified_nodes) == 0
            and delta.pixel_change_ratio == 0.0
        )

        if is_zero_delta:
            if action.action_type in (ActionType.NOOP, ActionType.WAIT, ActionType.HOVER):
                return OutcomeClass.SUCCESS
            return OutcomeClass.NOOP

        # 7. Default verified success
        return OutcomeClass.SUCCESS

    async def verify_transition(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
        after_state: CanonicalUIGraph,
        expected_delta: Optional[StateDelta] = None,
    ) -> StateDelta:
        """Implements VerificationPort.verify_transition."""
        delta = self.compute_state_delta(before_state, after_state)
        passed, failed, critical_failed = self.evaluate_assertions(
            before_state=before_state,
            after_state=after_state,
            delta=delta,
            action=action,
        )
        outcome = self.classify_outcome(
            before_state=before_state,
            after_state=after_state,
            delta=delta,
            action=action,
            failed_critical=critical_failed,
        )

        # Return updated delta with classified outcome
        return StateDelta(
            added_nodes=delta.added_nodes,
            removed_nodes=delta.removed_nodes,
            modified_nodes=delta.modified_nodes,
            pixel_change_ratio=delta.pixel_change_ratio,
            changed_bounding_boxes=delta.changed_bounding_boxes,
            outcome_class=outcome,
        )

    async def verify_action(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
        expected_delta: Optional[StateDelta] = None,
        custom_assertions: Optional[List[AssertionRule]] = None,
    ) -> VerificationResult:
        """Awaits browser settlement, captures post-state, and performs independent verification."""
        # 1. Await Settlement
        settle_res: SettlementResult = await self.settlement_observer.wait_for_settlement()

        # 2. Capture fresh post-action state
        after_state: Optional[CanonicalUIGraph] = None
        if self.observation_port is not None:
            try:
                after_state = await self.observation_port.capture_state()
            except Exception:
                after_state = None

        if after_state is None:
            after_state = before_state

        # 3. Compute Delta
        raw_delta = self.compute_state_delta(before_state, after_state)

        # 4. Evaluate Assertions
        passed, failed, critical_failed = self.evaluate_assertions(
            before_state=before_state,
            after_state=after_state,
            delta=raw_delta,
            action=action,
            custom_assertions=custom_assertions,
        )

        # 5. Classify Outcome
        outcome = self.classify_outcome(
            before_state=before_state,
            after_state=after_state,
            delta=raw_delta,
            action=action,
            failed_critical=critical_failed,
            settlement_timed_out=settle_res.timed_out,
        )

        # 6. Build Final Delta
        final_delta = StateDelta(
            added_nodes=raw_delta.added_nodes,
            removed_nodes=raw_delta.removed_nodes,
            modified_nodes=raw_delta.modified_nodes,
            pixel_change_ratio=raw_delta.pixel_change_ratio,
            changed_bounding_boxes=raw_delta.changed_bounding_boxes,
            outcome_class=outcome,
        )

        # 7. Check if reconciliation is required
        requires_reconciliation = outcome in (
            OutcomeClass.UNKNOWN_EFFECT,
            OutcomeClass.NOOP,
            OutcomeClass.ERROR,
        )

        details = (
            f"Verification: {outcome.value} "
            f"({len(passed)} passed, {len(failed)} failed assertions, "
            f"settlement={settle_res.duration_ms:.1f}ms)"
        )

        return VerificationResult(
            outcome=outcome,
            delta=final_delta,
            passed_assertions=passed,
            failed_assertions=failed,
            settlement_duration_ms=settle_res.duration_ms,
            requires_reconciliation=requires_reconciliation,
            details=details,
            after_state=after_state,
        )

    async def reconcile_state(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
    ) -> Any:
        """Delegates state reconciliation to ReconciliationEngine."""
        if self.reconciliation_engine is not None:
            return await self.reconciliation_engine.reconcile(
                before_state=before_state,
                action=action,
                console_events=self._console_events,
                http_responses=self._http_responses,
            )
        from reflex.verification.reconciliation import ReconciliationEngine
        engine = ReconciliationEngine(
            observation_port=self.observation_port,
            settlement_observer=self.settlement_observer,
            clock=self.clock,
        )
        return await engine.reconcile(
            before_state=before_state,
            action=action,
            console_events=self._console_events,
            http_responses=self._http_responses,
        )
