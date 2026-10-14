"""Unit and Integration Tests for SurpriseCircuitBreaker (Motor Loop Halt & Failure Context)."""

from __future__ import annotations

import unittest

from reflex.cognition.prediction.circuit_breaker import (
    BreakerFailureContext,
    SurpriseCircuitBreaker,
    SurpriseCircuitBreakerConfig,
)
from reflex.cognition.prediction.surprise_evaluator import SurpriseEvaluator
from reflex.ports.clock import DeterministicClock
from reflex.ports.prediction import PredictionEvaluation
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestSurpriseCircuitBreaker(unittest.TestCase):
    """Test suite for surprise circuit breaker tripping, motor halts, and failure context propagation."""

    def setUp(self) -> None:
        self.clock = DeterministicClock(start_time_ms=1000.0)
        self.config = SurpriseCircuitBreakerConfig(threshold=0.25, consecutive_threshold=1)
        self.breaker = SurpriseCircuitBreaker(config=self.config, clock=self.clock)
        self.evaluator = SurpriseEvaluator()

    def _create_sample_state(self, url: str = "https://app.local") -> CanonicalUIGraph:
        return CanonicalUIGraph(
            timestamp_ms=self.clock.now_ms(),
            nodes={
                "btn_1": UIStateNode(
                    node_id="btn_1",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(x1=10, y1=10, x2=100, y2=40),
                    label="Submit",
                )
            },
            url=url,
        )

    def test_low_surprise_does_not_trip_breaker(self) -> None:
        """Asserts benign / matching transitions (PE <= tau) do not trip the circuit breaker."""
        eval_low = PredictionEvaluation(
            prediction_error=0.04,
            surprise_threshold=0.25,
            is_surprised=False,
            structural_mismatch=0.0,
            text_mismatch=0.0,
            visual_mismatch=0.04,
            inferred_cause="Expected Transition",
        )

        should_halt = self.breaker.check_surprise(eval_low)

        self.assertFalse(should_halt)
        self.assertFalse(self.breaker.is_tripped)
        self.assertEqual(self.breaker.trip_count, 0)
        self.assertIsNone(self.breaker.last_failure_context)

    def test_high_surprise_trips_breaker_and_captures_context(self) -> None:
        """Asserts high surprise (PE > tau) immediately trips the breaker and yields failure context."""
        eval_high = PredictionEvaluation(
            prediction_error=0.78,
            surprise_threshold=0.25,
            is_surprised=True,
            structural_mismatch=0.85,
            text_mismatch=0.70,
            visual_mismatch=0.35,
            inferred_cause="Unexpected Modal Interception",
        )
        pre_state = self._create_sample_state("https://app.local/cart")
        post_state = self._create_sample_state("https://app.local/cart")
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_checkout")
        exp_delta = StateDelta(modified_nodes=["btn_checkout"], outcome_class=OutcomeClass.SUCCESS)
        obs_delta = StateDelta(added_nodes=["modal_overlay"], outcome_class=OutcomeClass.MODAL_APPEARED)

        should_halt = self.breaker.check_surprise(
            evaluation=eval_high,
            pre_state=pre_state,
            action=action,
            post_state=post_state,
            expected_delta=exp_delta,
            observed_delta=obs_delta,
        )

        self.assertTrue(should_halt)
        self.assertTrue(self.breaker.is_tripped)
        self.assertEqual(self.breaker.trip_count, 1)

        ctx = self.breaker.last_failure_context
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.evaluation.prediction_error, 0.78)
        self.assertEqual(ctx.evaluation.inferred_cause, "Unexpected Modal Interception")
        self.assertEqual(ctx.action.target_node_id, "btn_checkout")
        self.assertEqual(ctx.observed_delta.outcome_class, OutcomeClass.MODAL_APPEARED)
        self.assertIn("Surprise Circuit Breaker TRIPPED", ctx.details)

    def test_failure_context_serialization_roundtrip(self) -> None:
        """Asserts BreakerFailureContext serializes to and from dict without loss."""
        eval_res = PredictionEvaluation(
            prediction_error=0.82,
            surprise_threshold=0.25,
            is_surprised=True,
            structural_mismatch=0.90,
            text_mismatch=0.80,
            visual_mismatch=0.40,
            inferred_cause="Dead Click / Unresponsive Element",
        )
        ctx = BreakerFailureContext(
            evaluation=eval_res,
            timestamp_ms=1234.5,
            trip_count=2,
            pre_state=self._create_sample_state(),
            action=TypedAction(action_type=ActionType.CLICK, target_node_id="btn_1"),
            expected_delta=StateDelta(modified_nodes=["btn_1"]),
            observed_delta=StateDelta(outcome_class=OutcomeClass.NOOP),
            details="Test Trip",
        )

        data = ctx.to_dict()
        restored = BreakerFailureContext.from_dict(data)

        self.assertEqual(restored.evaluation.prediction_error, ctx.evaluation.prediction_error)
        self.assertEqual(restored.trip_count, ctx.trip_count)
        self.assertEqual(restored.details, ctx.details)
        self.assertEqual(restored.action.target_node_id, ctx.action.target_node_id)
        self.assertEqual(restored.observed_delta.outcome_class, OutcomeClass.NOOP)

    def test_circuit_breaker_reset(self) -> None:
        """Asserts resetting the breaker clears tripped state while preserving trip history."""
        eval_high = PredictionEvaluation(
            prediction_error=0.75,
            surprise_threshold=0.25,
            is_surprised=True,
            structural_mismatch=0.8,
            text_mismatch=0.8,
            visual_mismatch=0.2,
            inferred_cause="Execution Error / Application Fault",
        )
        self.breaker.check_surprise(eval_high)
        self.assertTrue(self.breaker.is_tripped)

        self.breaker.reset()

        self.assertFalse(self.breaker.is_tripped)
        self.assertEqual(self.breaker.trip_count, 1)
        self.assertEqual(len(self.breaker.history), 1)

    def test_consecutive_threshold_policy(self) -> None:
        """Asserts consecutive threshold requires K consecutive high surprises before tripping."""
        cfg = SurpriseCircuitBreakerConfig(threshold=0.25, consecutive_threshold=3)
        breaker = SurpriseCircuitBreaker(config=cfg, clock=self.clock)

        eval_high = PredictionEvaluation(
            prediction_error=0.80,
            surprise_threshold=0.25,
            is_surprised=True,
            structural_mismatch=0.8,
            text_mismatch=0.8,
            visual_mismatch=0.8,
            inferred_cause="Unexpected Change",
        )
        eval_low = PredictionEvaluation(
            prediction_error=0.02,
            surprise_threshold=0.25,
            is_surprised=False,
            structural_mismatch=0.0,
            text_mismatch=0.0,
            visual_mismatch=0.02,
            inferred_cause="Expected Transition",
        )

        # 1st high surprise -> does not trip yet
        self.assertFalse(breaker.check_surprise(eval_high))
        self.assertFalse(breaker.is_tripped)
        self.assertEqual(breaker.consecutive_surprises, 1)

        # 2nd high surprise -> does not trip yet
        self.assertFalse(breaker.check_surprise(eval_high))
        self.assertFalse(breaker.is_tripped)
        self.assertEqual(breaker.consecutive_surprises, 2)

        # 1 low surprise -> resets streak to 0
        self.assertFalse(breaker.check_surprise(eval_low))
        self.assertEqual(breaker.consecutive_surprises, 0)

        # 3 consecutive high surprises -> now trips!
        self.assertFalse(breaker.check_surprise(eval_high))
        self.assertFalse(breaker.check_surprise(eval_high))
        self.assertTrue(breaker.check_surprise(eval_high))
        self.assertTrue(breaker.is_tripped)
        self.assertEqual(breaker.trip_count, 1)

    def test_manual_trip(self) -> None:
        """Asserts manual trip sets tripped status and records context."""
        ctx = self.breaker.trip_manual("Watchdog Timeout Detected")

        self.assertTrue(self.breaker.is_tripped)
        self.assertEqual(self.breaker.trip_count, 1)
        self.assertIn("Watchdog Timeout", ctx.details)

    def test_closed_loop_motor_halt_simulation(self) -> None:
        """Simulates an autonomous motor loop where an unexpected modal trips the breaker and halts execution."""
        breaker = self.breaker
        evaluator = self.evaluator

        steps_executed = 0
        halt_occurred = False
        failure_context: BreakerFailureContext | None = None

        # Simulated 5-step sequence where Step 4 encounters an unexpected modal
        for step in range(1, 6):
            if step == 4:
                # Step 4: unexpected modal dialog intercepts click
                expected = StateDelta(modified_nodes=["btn_submit"], outcome_class=OutcomeClass.SUCCESS)
                observed = StateDelta(
                    added_nodes=["modal_cookie"],
                    pixel_change_ratio=0.35,
                    outcome_class=OutcomeClass.MODAL_APPEARED,
                )
            else:
                # Normal successful step
                expected = StateDelta(modified_nodes=[f"field_{step}"], outcome_class=OutcomeClass.SUCCESS)
                observed = StateDelta(modified_nodes=[f"field_{step}"], outcome_class=OutcomeClass.SUCCESS)

            eval_res = evaluator.evaluate_surprise(expected, observed, threshold=0.25)
            should_halt = breaker.check_surprise(
                evaluation=eval_res,
                expected_delta=expected,
                observed_delta=observed,
            )

            if should_halt:
                halt_occurred = True
                failure_context = breaker.last_failure_context
                break

            steps_executed += 1

        self.assertTrue(halt_occurred)
        self.assertEqual(steps_executed, 3)  # Steps 1, 2, 3 succeeded; Step 4 halted
        self.assertIsNotNone(failure_context)
        self.assertEqual(failure_context.evaluation.inferred_cause, "Unexpected Modal Interception")


if __name__ == "__main__":
    unittest.main()
