"""Unit and integration test suite for ReconciliationEngine."""

import asyncio
import unittest

from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.reconciliation import (
    ReconciliationEngine,
    ReconciliationReport,
)
from reflex.verification.settlement_observer import SettlementObserver


class MockObservationAdapter(ObservationPort):
    """Mock observation adapter for state reconciliation probes."""

    def __init__(self, probe_state: CanonicalUIGraph):
        self._probe_state = probe_state

    async def capture_state(self) -> CanonicalUIGraph:
        return self._probe_state

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nprobe_bytes"


class TestReconciliationEngine(unittest.TestCase):
    """Test suite covering non-destructive diagnostic probes and recovery advisory."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000.0)
        self.btn_submit = UIStateNode(
            node_id="btn_submit",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(100, 100, 200, 140),
            label="Pay $50.00",
            is_clickable=True,
        )
        self.input_field = UIStateNode(
            node_id="inp_query",
            role=NodeRole.INPUT,
            bounds=BoundingBox(50, 50, 200, 80),
            label="Search Query",
            value="",
            is_editable=True,
            is_focused=False,
        )
        self.before_graph = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={"btn_submit": self.btn_submit, "inp_query": self.input_field},
            url="https://app.example.com/pay",
            active_window_title="Payment Form",
        )

    def test_timeout_probe_generates_diagnostic_report_without_blind_retry(self):
        """Simulates action timeout; engine conducts fresh probe and returns diagnostic report without re-executing."""
        async def run():
            obs = MockObservationAdapter(self.before_graph)
            engine = ReconciliationEngine(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_submit",
                safety_class=SafetyClass.DESTRUCTIVE,
            )

            report = await engine.reconcile(
                before_state=self.before_graph,
                action=action,
                action_id="act_checkout_123",
                outcome=OutcomeClass.UNKNOWN_EFFECT,
            )

            self.assertEqual(report.action_id, "act_checkout_123")
            self.assertFalse(report.is_retry_safe)  # Destructive action timeout: retry is UNSAFE
            self.assertIn("URL: https://app.example.com/pay", report.current_state_summary)
            self.assertIn("Total Nodes: 2", report.current_state_summary)
            self.assertIn("replan", report.recommended_recovery_action.lower())

        asyncio.run(run())

    def test_focus_miss_on_reversible_action_permits_safe_retry(self):
        """When a reversible action (e.g. typing) experiences zero delta and focus miss, engine advises reground_and_retry."""
        async def run():
            # In fresh probe, inp_query is still not focused and value is empty
            obs = MockObservationAdapter(self.before_graph)
            engine = ReconciliationEngine(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_query",
                text_payload="test search",
                safety_class=SafetyClass.REVERSIBLE,
            )

            report = await engine.reconcile(
                before_state=self.before_graph,
                action=action,
                action_id="act_type_001",
                outcome=OutcomeClass.NOOP,
            )

            self.assertTrue(report.is_retry_safe)  # Reversible action: safe to retry
            self.assertIn("reground_and_retry", report.recommended_recovery_action)
            self.assertIn("focus_miss", report.inferred_cause)

        asyncio.run(run())

    def test_modal_interception_diagnosed_with_dismissal_guidance(self):
        """When an unexpected modal is discovered in fresh probe, engine advises modal dismissal."""
        async def run():
            modal_node = UIStateNode(
                node_id="modal_intercept",
                role=NodeRole.MODAL,
                bounds=BoundingBox(0, 0, 1920, 1080),
                label="Session Expired Alert",
                attributes={"role": "alertdialog"},
            )
            probe_graph = CanonicalUIGraph(
                timestamp_ms=1100.0,
                nodes={
                    "btn_submit": self.btn_submit,
                    "inp_query": self.input_field,
                    "modal_intercept": modal_node,
                },
                url="https://app.example.com/pay",
            )

            obs = MockObservationAdapter(probe_graph)
            engine = ReconciliationEngine(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_submit",
                safety_class=SafetyClass.DESTRUCTIVE,
            )

            report = await engine.reconcile(
                before_state=self.before_graph,
                action=action,
                action_id="act_submit_456",
                outcome=OutcomeClass.MODAL_APPEARED,
            )

            self.assertFalse(report.is_retry_safe)
            self.assertIn("modal_interception", report.inferred_cause)
            self.assertIn("dismiss_modal", report.recommended_recovery_action)

        asyncio.run(run())

    def test_runtime_console_error_diagnosis(self):
        """When fatal console exceptions are detected, engine diagnoses crash and flags retry as unsafe."""
        async def run():
            obs = MockObservationAdapter(self.before_graph)
            engine = ReconciliationEngine(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_submit",
                safety_class=SafetyClass.REVERSIBLE,
            )

            console_events = [
                {"level": "error", "text": "Uncaught ReferenceError: submitHandler is not defined"}
            ]

            report = await engine.reconcile(
                before_state=self.before_graph,
                action=action,
                action_id="act_click_err",
                outcome=OutcomeClass.ERROR,
                console_events=console_events,
            )

            self.assertFalse(report.is_retry_safe)
            self.assertIn("runtime_exception", report.inferred_cause)
            self.assertEqual(len(report.recent_errors), 1)
            self.assertIn("replan", report.recommended_recovery_action)

        asyncio.run(run())

    def test_delayed_transition_landed_prevents_duplicate_dispatch(self):
        """When state changed despite timeout, engine flags retry as unsafe to prevent duplicate dispatch."""
        async def run():
            # In fresh probe, target node value mutated (delayed landing)
            mutated_input = UIStateNode(
                node_id="inp_query",
                role=NodeRole.INPUT,
                bounds=BoundingBox(50, 50, 200, 80),
                label="Search Query",
                value="completed query text",
                is_editable=True,
            )
            probe_graph = CanonicalUIGraph(
                timestamp_ms=1500.0,
                nodes={"btn_submit": self.btn_submit, "inp_query": mutated_input},
                url="https://app.example.com/pay",
            )

            obs = MockObservationAdapter(probe_graph)
            engine = ReconciliationEngine(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_query",
                text_payload="completed query text",
                safety_class=SafetyClass.REVERSIBLE,
            )

            report = await engine.reconcile(
                before_state=self.before_graph,
                action=action,
                action_id="act_delayed_landing",
                outcome=OutcomeClass.UNKNOWN_EFFECT,
            )

            self.assertFalse(report.is_retry_safe)  # Already landed: duplicate retry prohibited
            self.assertIn("delayed_transition_completed", report.inferred_cause)
            self.assertIn("advance_trajectory", report.recommended_recovery_action)

        asyncio.run(run())

    def test_reconciliation_report_serialization(self):
        """ReconciliationReport serializes to and from dictionary accurately."""
        report = ReconciliationReport(
            action_id="act_999",
            inferred_cause="test_cause",
            current_state_summary="URL: http://test, Total Nodes: 5",
            is_retry_safe=True,
            recommended_recovery_action="reground_and_retry",
            active_focus_node_id="inp_1",
            recent_errors=["error1"],
            pending_requests=["r1"],
            metadata={"k": "v"},
        )

        d = report.to_dict()
        reconstructed = ReconciliationReport.from_dict(d)
        self.assertEqual(report.action_id, reconstructed.action_id)
        self.assertEqual(report.inferred_cause, reconstructed.inferred_cause)
        self.assertEqual(report.is_retry_safe, reconstructed.is_retry_safe)
        self.assertEqual(report.recent_errors, reconstructed.recent_errors)
        self.assertEqual(report.pending_requests, reconstructed.pending_requests)


if __name__ == "__main__":
    unittest.main()
