"""Unit and integration test suite for IndependentVerifier."""

import asyncio
import unittest

from reflex.ports.clock import DeterministicClock, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.ports.verification import VerificationEnginePort, VerificationPort
from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.settlement_observer import SettlementObserver
from reflex.verification.verifier import (
    AssertionRule,
    IndependentVerifier,
    VerificationResult,
)


class MockObservationAdapter(ObservationPort):
    """Mock observation adapter returning programmed UI state graphs."""

    def __init__(self, states: list[CanonicalUIGraph]):
        self._states = list(states)
        self._index = 0

    async def capture_state(self) -> CanonicalUIGraph:
        if self._index < len(self._states):
            state = self._states[self._index]
            self._index += 1
            return state
        return self._states[-1] if self._states else CanonicalUIGraph(timestamp_ms=0.0, nodes={})

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_bytes"


class TestIndependentVerifier(unittest.TestCase):
    """Test suite covering post-action independent verification and outcome classification."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000.0)
        self.btn_node = UIStateNode(
            node_id="btn_submit",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(100, 100, 200, 140),
            label="Submit Order",
        )
        self.input_node = UIStateNode(
            node_id="inp_username",
            role=NodeRole.INPUT,
            bounds=BoundingBox(100, 50, 300, 80),
            label="Username",
            value="",
            is_editable=True,
        )
        self.initial_graph = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={"btn_submit": self.btn_node, "inp_username": self.input_node},
            url="https://shop.example.com/checkout",
            active_window_title="Checkout",
        )

    def test_form_submission_success_verification(self):
        """Verifies successful form submission resulting in confirmation banner node."""
        async def run():
            success_banner = UIStateNode(
                node_id="banner_success",
                role=NodeRole.TEXT,
                bounds=BoundingBox(100, 20, 400, 50),
                label="Order Submitted Successfully #12345",
            )
            after_graph = CanonicalUIGraph(
                timestamp_ms=1200.0,
                nodes={
                    "btn_submit": self.btn_node,
                    "inp_username": self.input_node,
                    "banner_success": success_banner,
                },
                url="https://shop.example.com/checkout",
                active_window_title="Checkout",
            )

            obs = MockObservationAdapter([after_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_submit",
                safety_class=SafetyClass.DESTRUCTIVE,
            )

            custom_rules = [
                AssertionRule(assertion_type="element_present", target_value="Order Submitted"),
                AssertionRule(assertion_type="no_console_error", target_value=""),
            ]

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
                custom_assertions=custom_rules,
            )

            self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
            self.assertIn("banner_success", result.delta.added_nodes)
            self.assertIn("element_present(Order Submitted)", result.passed_assertions)
            self.assertIn("no_fatal_console_errors", result.passed_assertions)
            self.assertFalse(result.requires_reconciliation)

        asyncio.run(run())

    def test_page_navigation_verification(self):
        """Verifies full page URL and title transition."""
        async def run():
            after_graph = CanonicalUIGraph(
                timestamp_ms=1300.0,
                nodes={
                    "h1_title": UIStateNode(
                        node_id="h1_title",
                        role=NodeRole.TEXT,
                        bounds=BoundingBox(50, 50, 300, 90),
                        label="Order Confirmation",
                    )
                },
                url="https://shop.example.com/confirmation/12345",
                active_window_title="Order Confirmation",
            )

            obs = MockObservationAdapter([after_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_submit",
            )

            custom_rules = [
                AssertionRule(assertion_type="url_contains", target_value="confirmation"),
            ]

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
                custom_assertions=custom_rules,
            )

            self.assertEqual(result.outcome, OutcomeClass.NAVIGATION)
            self.assertIn("url_contains(confirmation)", result.passed_assertions)
            self.assertFalse(result.requires_reconciliation)

        asyncio.run(run())

    def test_modal_interception_detection(self):
        """Verifies detection of unexpected modal / cookie banner interception."""
        async def run():
            cookie_modal = UIStateNode(
                node_id="modal_cookie_banner",
                role=NodeRole.MODAL,
                bounds=BoundingBox(0, 0, 1920, 1080),
                label="Accept Cookies",
                attributes={"role": "dialog", "class": "modal-overlay"},
            )
            after_graph = CanonicalUIGraph(
                timestamp_ms=1150.0,
                nodes={
                    "btn_submit": self.btn_node,
                    "inp_username": self.input_node,
                    "modal_cookie_banner": cookie_modal,
                },
                url="https://shop.example.com/checkout",
            )

            obs = MockObservationAdapter([after_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_submit",
            )

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
            )

            self.assertEqual(result.outcome, OutcomeClass.MODAL_APPEARED)
            self.assertIn("modal_cookie_banner", result.delta.added_nodes)

        asyncio.run(run())

    def test_fatal_console_error_classification(self):
        """Verifies fatal JavaScript runtime errors trigger ERROR classification."""
        async def run():
            obs = MockObservationAdapter([self.initial_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            verifier.record_console_event(
                level="error",
                text="Uncaught TypeError: Cannot read properties of undefined (reading 'submit')",
            )

            action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit")

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
            )

            self.assertEqual(result.outcome, OutcomeClass.ERROR)
            self.assertTrue(result.requires_reconciliation)
            self.assertTrue(any("fatal_console_error" in f for f in result.failed_assertions))

        asyncio.run(run())

    def test_http_status_error_classification(self):
        """Verifies HTTP 4xx/5xx status codes trigger ERROR classification."""
        async def run():
            obs = MockObservationAdapter([self.initial_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            verifier.record_http_response(
                url="https://shop.example.com/api/checkout",
                status=500,
                method="POST",
            )

            action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit")

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
            )

            self.assertEqual(result.outcome, OutcomeClass.ERROR)
            self.assertTrue(result.requires_reconciliation)
            self.assertTrue(any("http_status_error" in f for f in result.failed_assertions))

        asyncio.run(run())

    def test_loading_indicator_classification(self):
        """Verifies loading spinner or aria-busy triggers LOADING classification."""
        async def run():
            loading_spinner = UIStateNode(
                node_id="spinner_1",
                role=NodeRole.CONTAINER,
                bounds=BoundingBox(100, 100, 120, 120),
                label="Loading...",
                attributes={"aria-busy": "true", "class": "spinner-active"},
            )
            after_graph = CanonicalUIGraph(
                timestamp_ms=1100.0,
                nodes={
                    "btn_submit": self.btn_node,
                    "inp_username": self.input_node,
                    "spinner_1": loading_spinner,
                },
                url="https://shop.example.com/checkout",
            )

            obs = MockObservationAdapter([after_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit")

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
            )

            self.assertEqual(result.outcome, OutcomeClass.LOADING)

        asyncio.run(run())

    def test_noop_classification_on_zero_delta(self):
        """Verifies zero state delta on state-mutating action is classified as NOOP requiring reconciliation."""
        async def run():
            # After graph is identical to initial graph
            obs = MockObservationAdapter([self.initial_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit")

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
            )

            self.assertEqual(result.outcome, OutcomeClass.NOOP)
            self.assertTrue(result.requires_reconciliation)
            self.assertEqual(len(result.delta.added_nodes), 0)
            self.assertEqual(len(result.delta.removed_nodes), 0)
            self.assertEqual(len(result.delta.modified_nodes), 0)

        asyncio.run(run())

    def test_explicit_noop_action_classified_as_success(self):
        """Verifies explicit NOOP / WAIT actions with 0 delta are classified as SUCCESS."""
        async def run():
            obs = MockObservationAdapter([self.initial_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            action = TypedAction(action_type=ActionType.NOOP)

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
            )

            self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
            self.assertFalse(result.requires_reconciliation)

        asyncio.run(run())

    def test_custom_assertion_rules_evaluation(self):
        """Evaluates custom assertion rules: element_present, element_value_equals, element_absent."""
        async def run():
            typed_input = UIStateNode(
                node_id="inp_username",
                role=NodeRole.INPUT,
                bounds=BoundingBox(100, 50, 300, 80),
                label="Username",
                value="alice_doe",
                is_editable=True,
            )
            after_graph = CanonicalUIGraph(
                timestamp_ms=1100.0,
                nodes={"btn_submit": self.btn_node, "inp_username": typed_input},
                url="https://shop.example.com/checkout",
            )

            obs = MockObservationAdapter([after_graph])
            verifier = IndependentVerifier(observation_port=obs, clock=self.clock)

            action = TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="inp_username",
                text_payload="alice_doe",
            )

            rules = [
                AssertionRule(
                    assertion_type="element_value_equals",
                    target_value="alice_doe",
                    target_node_id="inp_username",
                ),
                AssertionRule(
                    assertion_type="element_absent",
                    target_value="error_message",
                ),
                AssertionRule(
                    assertion_type="delta_not_empty",
                    target_value="",
                ),
            ]

            result = await verifier.verify_action(
                before_state=self.initial_graph,
                action=action,
                custom_assertions=rules,
            )

            self.assertEqual(result.outcome, OutcomeClass.SUCCESS)
            self.assertEqual(len(result.failed_assertions), 0)
            self.assertEqual(len(result.passed_assertions), 5)  # 2 default + 3 custom

        asyncio.run(run())

    def test_verification_port_conformance(self):
        """Verifies IndependentVerifier implements VerificationPort.verify_transition."""
        async def run():
            verifier = IndependentVerifier(clock=self.clock)
            self.assertIsInstance(verifier, VerificationPort)
            self.assertIsInstance(verifier, VerificationEnginePort)

            action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit")
            delta = await verifier.verify_transition(
                before_state=self.initial_graph,
                action=action,
                after_state=self.initial_graph,
            )

            self.assertIsInstance(delta, StateDelta)
            self.assertEqual(delta.outcome_class, OutcomeClass.NOOP)

        asyncio.run(run())

    def test_assertion_rule_and_result_serialization(self):
        """AssertionRule and VerificationResult serialize and deserialize accurately."""
        rule = AssertionRule(
            assertion_type="url_equals",
            target_value="https://example.com/success",
            is_critical=True,
            target_node_id="node_x",
            metadata={"source": "test"},
        )
        rule_dict = rule.to_dict()
        rule_reconstructed = AssertionRule.from_dict(rule_dict)
        self.assertEqual(rule, rule_reconstructed)

        v_res = VerificationResult(
            outcome=OutcomeClass.SUCCESS,
            delta=StateDelta(added_nodes=["n1"], outcome_class=OutcomeClass.SUCCESS),
            passed_assertions=["a1", "a2"],
            failed_assertions=[],
            settlement_duration_ms=45.2,
            requires_reconciliation=False,
            details="Passed",
            after_state=self.initial_graph,
        )
        v_dict = v_res.to_dict()
        v_reconstructed = VerificationResult.from_dict(v_dict)
        self.assertEqual(v_res.outcome, v_reconstructed.outcome)
        self.assertEqual(v_res.passed_assertions, v_reconstructed.passed_assertions)
        self.assertEqual(v_res.settlement_duration_ms, v_reconstructed.settlement_duration_ms)
        self.assertEqual(v_res.delta.added_nodes, v_reconstructed.delta.added_nodes)


if __name__ == "__main__":
    unittest.main()
