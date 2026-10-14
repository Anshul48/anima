"""Test Suite: Efference Copy Verifier & Surprise Circuit Breaker Closed-Loop Monitoring."""

from __future__ import annotations

import time
import unittest

from reflex.cognition.prediction.circuit_breaker import (
    BreakerFailureContext,
    SurpriseCircuitBreaker,
    SurpriseCircuitBreakerConfig,
)
from reflex.cognition.prediction.delta_engine import ExpectedDeltaEngine
from reflex.cognition.prediction.efference_verifier import (
    EfferenceCopyVerifier,
    EfferenceVerificationResult,
)
from reflex.cognition.prediction.surprise_evaluator import SurpriseEvaluator
from reflex.ports.prediction import PredictionEvaluation
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestEfferenceCopyVerifier(unittest.TestCase):
    """Tests forward model prediction, delta observation, and closed-loop verification."""

    def setUp(self) -> None:
        self.verifier = EfferenceCopyVerifier()

    def _build_test_graph(
        self,
        nodes: dict[str, UIStateNode] | None = None,
        url: str = "https://app.example.com",
    ) -> CanonicalUIGraph:
        default_nodes = {
            "input_search": UIStateNode(
                node_id="input_search",
                role=NodeRole.INPUT,
                bounds=BoundingBox(10, 10, 200, 40),
                label="Search query",
                value="",
                is_editable=True,
            ),
            "btn_search": UIStateNode(
                node_id="btn_search",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(210, 10, 280, 40),
                label="Search",
                is_clickable=True,
            ),
        }
        return CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=nodes if nodes is not None else default_nodes,
            url=url,
            viewport_size=(1920, 1080),
        )

    def test_result_roundtrip_serialization(self) -> None:
        exp = StateDelta(modified_nodes=["input_search"], outcome_class=OutcomeClass.SUCCESS)
        obs = StateDelta(modified_nodes=["input_search"], outcome_class=OutcomeClass.SUCCESS)
        eval_res = PredictionEvaluation(
            prediction_error=0.05,
            surprise_threshold=0.25,
            is_surprised=False,
            structural_mismatch=0.02,
            text_mismatch=0.01,
            visual_mismatch=0.02,
            inferred_cause="expected_change",
        )
        res = EfferenceVerificationResult(
            is_verified=True,
            prediction_error=0.05,
            surprise_threshold=0.25,
            circuit_breaker_tripped=False,
            expected_delta=exp,
            observed_delta=obs,
            evaluation=eval_res,
            inferred_cause="expected_change",
            details="Efference verification PASSED",
        )
        d = res.to_dict()
        res2 = EfferenceVerificationResult.from_dict(d)
        self.assertEqual(res.is_verified, res2.is_verified)
        self.assertEqual(res.prediction_error, res2.prediction_error)
        self.assertEqual(res.circuit_breaker_tripped, res2.circuit_breaker_tripped)
        self.assertEqual(res.inferred_cause, res2.inferred_cause)

    def test_generate_efference_copy(self) -> None:
        graph = self._build_test_graph()
        action = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="input_search",
            text_payload="jarvis assistant",
        )

        efference_copy = self.verifier.generate_efference_copy(graph, action)
        self.assertIsInstance(efference_copy, StateDelta)
        self.assertIn("input_search", efference_copy.modified_nodes)

    def test_compute_observed_delta_modifications_and_navigation(self) -> None:
        pre_graph = self._build_test_graph()

        # Simulate typing: modified value
        post_nodes = dict(pre_graph.nodes)
        post_nodes["input_search"] = UIStateNode(
            node_id="input_search",
            role=NodeRole.INPUT,
            bounds=BoundingBox(10, 10, 200, 40),
            label="Search query",
            value="jarvis assistant",
            is_editable=True,
        )
        post_graph = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=post_nodes,
            url=pre_graph.url,
            viewport_size=(1920, 1080),
        )

        obs_delta = self.verifier.compute_observed_delta(pre_graph, post_graph)
        self.assertIn("input_search", obs_delta.modified_nodes)
        self.assertEqual(len(obs_delta.added_nodes), 0)
        self.assertEqual(len(obs_delta.removed_nodes), 0)

        # Simulate Navigation
        nav_graph = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=post_nodes,
            url="https://app.example.com/results",
            viewport_size=(1920, 1080),
        )
        nav_delta = self.verifier.compute_observed_delta(post_graph, nav_graph)
        self.assertEqual(nav_delta.outcome_class, OutcomeClass.NAVIGATION)

    def test_low_surprise_verification_passes(self) -> None:
        """Asserts that normal matching state transition passes verification without tripping breaker."""
        pre_graph = self._build_test_graph()
        action = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="input_search",
            text_payload="test",
        )

        post_nodes = dict(pre_graph.nodes)
        post_nodes["input_search"] = UIStateNode(
            node_id="input_search",
            role=NodeRole.INPUT,
            bounds=BoundingBox(10, 10, 200, 40),
            label="Search query",
            value="test",
            is_editable=True,
        )
        post_graph = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=post_nodes,
            url=pre_graph.url,
            viewport_size=(1920, 1080),
        )

        result = self.verifier.verify_transition(pre_graph, action, post_graph)
        self.assertTrue(result.is_verified)
        self.assertFalse(result.circuit_breaker_tripped)
        self.assertFalse(self.verifier.is_tripped)
        self.assertLess(result.prediction_error, result.surprise_threshold)

    def test_unexpected_modal_trips_circuit_breaker(self) -> None:
        """Asserts that unexpected blocking modal popup halts motor execution and trips circuit breaker."""
        pre_graph = self._build_test_graph()
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn_search",
        )

        # Expected: normal search results
        expected_delta = StateDelta(
            pixel_change_ratio=0.15,
            outcome_class=OutcomeClass.SUCCESS,
        )

        # Observed: unexpected error modal popup!
        post_nodes = dict(pre_graph.nodes)
        post_nodes["modal_err"] = UIStateNode(
            node_id="modal_err",
            role=NodeRole.MODAL,
            bounds=BoundingBox(500, 300, 1400, 800),
            label="Security Alert: Rate limit exceeded",
            is_clickable=True,
        )
        post_graph = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=post_nodes,
            url=pre_graph.url,
            viewport_size=(1920, 1080),
        )

        result = self.verifier.verify_transition(
            pre_state=pre_graph,
            action=action,
            post_state=post_graph,
            expected_delta=expected_delta,
        )

        self.assertFalse(result.is_verified)
        self.assertTrue(result.circuit_breaker_tripped)
        self.assertTrue(self.verifier.is_tripped)
        self.assertGreater(result.prediction_error, result.surprise_threshold)
        self.assertIsNotNone(result.failure_context)
        self.assertEqual(result.failure_context.trip_count, 1)

    def test_dead_click_trips_circuit_breaker(self) -> None:
        """Asserts that dead click (expected substantial delta, but observed zero effect) triggers breaker."""
        pre_graph = self._build_test_graph()
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn_search",
        )

        # Expected: navigation or significant visual update
        expected_delta = StateDelta(
            added_nodes=["results_list"],
            pixel_change_ratio=0.6,
            outcome_class=OutcomeClass.NAVIGATION,
        )

        # Observed: NOOP - identical state, no nodes added/modified
        post_graph = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=dict(pre_graph.nodes),
            url=pre_graph.url,
            viewport_size=(1920, 1080),
        )

        result = self.verifier.verify_transition(
            pre_state=pre_graph,
            action=action,
            post_state=post_graph,
            expected_delta=expected_delta,
        )

        self.assertFalse(result.is_verified)
        self.assertTrue(result.circuit_breaker_tripped)
        self.assertTrue(self.verifier.is_tripped)

    def test_circuit_breaker_reset(self) -> None:
        """Asserts resetting clears the tripped status and resets verification state."""
        pre_graph = self._build_test_graph()
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_search")
        expected_delta = StateDelta(outcome_class=OutcomeClass.NAVIGATION, pixel_change_ratio=0.8)
        post_graph = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=dict(pre_graph.nodes),
            url=pre_graph.url,
        )

        # Trip breaker
        self.verifier.verify_transition(pre_graph, action, post_graph, expected_delta=expected_delta)
        self.assertTrue(self.verifier.is_tripped)

        # Reset
        self.verifier.reset()
        self.assertFalse(self.verifier.is_tripped)


if __name__ == "__main__":
    unittest.main()
