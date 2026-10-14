"""Unit and Conformance Tests for SurpriseEvaluator (Multimodal Prediction Error Metric)."""

from __future__ import annotations

import time
import unittest

from reflex.cognition.prediction.surprise_evaluator import (
    SurpriseEvaluator,
    SurpriseEvaluatorConfig,
)
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestSurpriseEvaluator(unittest.TestCase):
    """Test suite for surprise calculation, benign noise filtering, and high surprise triggering."""

    def setUp(self) -> None:
        self.evaluator = SurpriseEvaluator()

    def test_matching_transition_zero_surprise(self) -> None:
        """Asserts exact match between expectation and observation yields PE <= 0.05 and no surprise."""
        expected = StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=["chk_1"],
            pixel_change_ratio=0.005,
            outcome_class=OutcomeClass.SUCCESS,
        )
        observed = StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=["chk_1"],
            pixel_change_ratio=0.005,
            outcome_class=OutcomeClass.SUCCESS,
        )

        res = self.evaluator.evaluate_surprise(expected, observed, threshold=0.25)

        self.assertLessEqual(res.prediction_error, 0.05)
        self.assertFalse(res.is_surprised)
        self.assertEqual(res.structural_mismatch, 0.0)
        self.assertEqual(res.text_mismatch, 0.0)
        self.assertEqual(res.visual_mismatch, 0.0)
        self.assertEqual(res.inferred_cause, "Expected Transition")

    def test_benign_noise_filtering_cursor_blink(self) -> None:
        """Asserts blinking cursor or minor rendering delta yields PE <= 0.10 and no surprise alarm."""
        expected = StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=["input_name"],
            pixel_change_ratio=0.005,
            outcome_class=OutcomeClass.SUCCESS,
        )
        # Observed slight pixel delta from blinking cursor (e.g. 0.018 vs 0.005)
        observed = StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=["input_name"],
            pixel_change_ratio=0.018,
            outcome_class=OutcomeClass.SUCCESS,
        )

        res = self.evaluator.evaluate_surprise(expected, observed, threshold=0.25)

        self.assertLessEqual(res.prediction_error, 0.10)
        self.assertFalse(res.is_surprised)
        self.assertEqual(res.structural_mismatch, 0.0)
        self.assertIn("Benign Noise", res.inferred_cause)

    def test_benign_loading_transition(self) -> None:
        """Asserts transition into temporary loading state yields low surprise below default threshold."""
        expected = StateDelta(
            modified_nodes=["btn_submit"],
            pixel_change_ratio=0.02,
            outcome_class=OutcomeClass.SUCCESS,
        )
        observed = StateDelta(
            modified_nodes=["btn_submit"],
            pixel_change_ratio=0.04,
            outcome_class=OutcomeClass.LOADING,
        )

        res = self.evaluator.evaluate_surprise(expected, observed, threshold=0.25)

        # Loading outcome penalty is benign (0.10 * 0.60 * 0.50 = 0.03)
        self.assertLessEqual(res.prediction_error, 0.15)
        self.assertFalse(res.is_surprised)

    def test_high_surprise_unexpected_modal(self) -> None:
        """Asserts unexpected modal appearance triggers PE >= 0.70 and trips surprise."""
        expected = StateDelta(
            modified_nodes=["btn_checkout"],
            pixel_change_ratio=0.01,
            outcome_class=OutcomeClass.SUCCESS,
        )
        observed = StateDelta(
            added_nodes=["modal_cookie_consent", "btn_accept_all"],
            removed_nodes=[],
            modified_nodes=[],
            pixel_change_ratio=0.35,
            outcome_class=OutcomeClass.MODAL_APPEARED,
        )

        res = self.evaluator.evaluate_surprise(expected, observed, threshold=0.25)

        self.assertGreaterEqual(res.prediction_error, 0.70)
        self.assertTrue(res.is_surprised)
        self.assertGreaterEqual(res.structural_mismatch, 0.70)
        self.assertEqual(res.inferred_cause, "Unexpected Modal Interception")

    def test_high_surprise_dead_click_noop(self) -> None:
        """Asserts dead click (NOOP when expecting navigation/mutation) triggers PE >= 0.70."""
        expected = StateDelta(
            modified_nodes=["btn_submit"],
            pixel_change_ratio=0.50,
            outcome_class=OutcomeClass.NAVIGATION,
        )
        observed = StateDelta(
            added_nodes=[],
            removed_nodes=[],
            modified_nodes=[],
            pixel_change_ratio=0.0,
            outcome_class=OutcomeClass.NOOP,
        )

        res = self.evaluator.evaluate_surprise(expected, observed, threshold=0.25)

        self.assertGreaterEqual(res.prediction_error, 0.70)
        self.assertTrue(res.is_surprised)
        self.assertEqual(res.inferred_cause, "Dead Click / Unresponsive Element")

    def test_high_surprise_application_error_404(self) -> None:
        """Asserts unexpected error outcome triggers PE >= 0.70."""
        expected = StateDelta(
            modified_nodes=["link_item"],
            pixel_change_ratio=0.50,
            outcome_class=OutcomeClass.NAVIGATION,
        )
        observed = StateDelta(
            added_nodes=["err_banner"],
            removed_nodes=[],
            modified_nodes=[],
            pixel_change_ratio=0.40,
            outcome_class=OutcomeClass.ERROR,
        )

        res = self.evaluator.evaluate_surprise(expected, observed, threshold=0.25)

        self.assertGreaterEqual(res.prediction_error, 0.70)
        self.assertTrue(res.is_surprised)
        self.assertEqual(res.inferred_cause, "Execution Error / Application Fault")

    def test_high_surprise_text_value_mismatch(self) -> None:
        """Asserts typing failure where input element does not update value triggers high surprise."""
        expected = StateDelta(
            modified_nodes=["input_pwd"],
            pixel_change_ratio=0.005,
            outcome_class=OutcomeClass.SUCCESS,
        )
        observed = StateDelta(
            modified_nodes=["input_pwd"],
            pixel_change_ratio=0.005,
            outcome_class=OutcomeClass.SUCCESS,
        )

        after_state = CanonicalUIGraph(
            timestamp_ms=2000.0,
            nodes={
                "input_pwd": UIStateNode(
                    node_id="input_pwd",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(x1=10, y1=10, x2=100, y2=40),
                    value="",  # Failed to update
                )
            },
        )
        action = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="input_pwd",
            text_payload="Secret123!",
        )

        res = self.evaluator.evaluate_surprise(
            expected_delta=expected,
            observed_delta=observed,
            after_state=after_state,
            action=action,
            threshold=0.25,
        )

        self.assertTrue(res.is_surprised)
        self.assertGreater(res.text_mismatch, 0.50)
        self.assertEqual(res.inferred_cause, "Text / Value Mismatch")

    def test_navigation_failure_cause_tagging(self) -> None:
        """Asserts failing to navigate when expected tags Navigation Failure."""
        expected = StateDelta(outcome_class=OutcomeClass.NAVIGATION, pixel_change_ratio=0.50)
        observed = StateDelta(outcome_class=OutcomeClass.SUCCESS, pixel_change_ratio=0.01)

        res = self.evaluator.evaluate_surprise(expected, observed, threshold=0.25)

        self.assertTrue(res.is_surprised)
        self.assertEqual(res.inferred_cause, "Navigation Failure")

    def test_sub_millisecond_execution_performance(self) -> None:
        """Asserts deterministic surprise evaluation executes in < 2ms on CPU (Criteria 4)."""
        expected = StateDelta(
            modified_nodes=["node_1"],
            pixel_change_ratio=0.01,
            outcome_class=OutcomeClass.SUCCESS,
        )
        observed = StateDelta(
            modified_nodes=["node_1"],
            pixel_change_ratio=0.015,
            outcome_class=OutcomeClass.SUCCESS,
        )

        # Warm up
        for _ in range(10):
            self.evaluator.evaluate_surprise(expected, observed)

        t0 = time.perf_counter()
        iterations = 1000
        for _ in range(iterations):
            self.evaluator.evaluate_surprise(expected, observed)
        total_time_ms = (time.perf_counter() - t0) * 1000.0
        avg_latency_ms = total_time_ms / iterations

        self.assertLess(
            avg_latency_ms,
            2.0,
            f"Surprise evaluation took {avg_latency_ms:.4f}ms per call (threshold: 2.0ms)",
        )

    def test_custom_evaluator_config_weights(self) -> None:
        """Asserts custom evaluator configuration weights and default threshold."""
        custom_cfg = SurpriseEvaluatorConfig(
            weight_structural=0.80,
            weight_text=0.10,
            weight_visual=0.10,
            default_threshold=0.50,
        )
        evaluator = SurpriseEvaluator(config=custom_cfg)

        expected = StateDelta(outcome_class=OutcomeClass.SUCCESS)
        observed = StateDelta(outcome_class=OutcomeClass.MODAL_APPEARED)

        res = evaluator.evaluate_surprise(expected, observed)

        self.assertEqual(res.surprise_threshold, 0.50)
        self.assertTrue(res.is_surprised)


if __name__ == "__main__":
    unittest.main()
