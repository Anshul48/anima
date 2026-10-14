"""Unit and Conformance Tests for LearnedPredictorGate (Neural Predictor Promotion Gate)."""

from __future__ import annotations

import unittest

from reflex.cognition.prediction.delta_engine import ExpectedDeltaEngine
from reflex.cognition.prediction.learned_gate import (
    BenchmarkMetrics,
    GateValidationResult,
    LearnedPredictorGate,
    LearnedPredictorGateConfig,
    LearnedPredictorPort,
    ShadowStepRecord,
)
from reflex.ports.clock import DeterministicClock
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import CanonicalUIGraph


class MockLearnedPredictor(LearnedPredictorPort):
    """Configurable mock neural predictor for promotion testing."""

    def __init__(
        self,
        accuracy_ratio: float = 0.95,
        memory_mb: float = 256.0,
        divergence_ratio: float = 0.0,
    ) -> None:
        self.accuracy_ratio = accuracy_ratio
        self.memory_mb = memory_mb
        self.divergence_ratio = divergence_ratio
        self._call_count = 0

    def predict_delta(
        self,
        current_state: CanonicalUIGraph,
        action: TypedAction,
    ) -> StateDelta:
        self._call_count += 1
        # If simulating divergence / error on fraction of calls
        if self.divergence_ratio > 0 and (self._call_count % int(1.0 / self.divergence_ratio)) == 0:
            return StateDelta(outcome_class=OutcomeClass.ERROR, pixel_change_ratio=0.99)
        return StateDelta(
            modified_nodes=[action.target_node_id] if action.target_node_id else [],
            pixel_change_ratio=0.01,
            outcome_class=OutcomeClass.SUCCESS,
        )

    def get_memory_usage_mb(self) -> float:
        return self.memory_mb


class TestLearnedPredictorGate(unittest.TestCase):
    """Test suite for learned neural predictor evaluation harness and promotion gate."""

    def setUp(self) -> None:
        self.clock = DeterministicClock(start_time_ms=1000.0)
        self.gate_config = LearnedPredictorGateConfig(
            min_benchmark_samples=5000,
            min_accuracy=0.90,
            max_false_positive_rate=0.05,
            max_latency_ms=20.0,
            max_memory_mb=1024.0,
            min_shadow_steps=500,
            max_shadow_divergence_rate=0.02,
        )
        self.gate = LearnedPredictorGate(config=self.gate_config, clock=self.clock)
        self.baseline = ExpectedDeltaEngine()

    def test_promotion_approved_when_all_criteria_satisfied(self) -> None:
        """Asserts candidate is approved when benchmark, latency, memory, and shadow tests pass."""
        candidate_metrics = BenchmarkMetrics(
            total_samples=5000,
            accuracy=0.94,
            false_positive_rate=0.02,
            false_negative_rate=0.04,
            mean_latency_ms=8.5,
            max_latency_ms=14.2,
            peak_memory_mb=512.0,
        )
        baseline_metrics = BenchmarkMetrics(
            total_samples=5000,
            accuracy=0.91,
            false_positive_rate=0.04,
            false_negative_rate=0.05,
            mean_latency_ms=0.5,
            max_latency_ms=1.2,
            peak_memory_mb=10.0,
        )

        # Simulate 500 shadow steps with 0 divergence
        mock_pred = MockLearnedPredictor()
        st = CanonicalUIGraph(timestamp_ms=1000.0, nodes={})
        act = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_1")
        obs_delta = StateDelta(modified_nodes=["btn_1"], outcome_class=OutcomeClass.SUCCESS)

        for _ in range(500):
            self.gate.record_shadow_step(
                candidate_predictor=mock_pred,
                baseline_predictor=self.baseline,
                current_state=st,
                action=act,
                observed_delta=obs_delta,
            )

        res = self.gate.evaluate_promotion(
            candidate_metrics=candidate_metrics,
            baseline_metrics=baseline_metrics,
        )

        self.assertTrue(res.is_promoted)
        self.assertTrue(res.benchmark_passed)
        self.assertTrue(res.accuracy_passed)
        self.assertTrue(res.false_positive_passed)
        self.assertTrue(res.latency_passed)
        self.assertTrue(res.memory_passed)
        self.assertTrue(res.shadow_passed)
        self.assertEqual(len(res.rejection_reasons), 0)

    def test_rejection_insufficient_samples(self) -> None:
        """Asserts promotion rejected when benchmark dataset has fewer than 5,000 samples."""
        candidate_metrics = BenchmarkMetrics(
            total_samples=1200,  # Below 5000
            accuracy=0.98,
            false_positive_rate=0.01,
            false_negative_rate=0.01,
            mean_latency_ms=5.0,
            max_latency_ms=10.0,
            peak_memory_mb=256.0,
        )

        res = self.gate.evaluate_promotion(candidate_metrics)

        self.assertFalse(res.is_promoted)
        self.assertFalse(res.benchmark_passed)
        self.assertTrue(any("Insufficient benchmark samples" in r for r in res.rejection_reasons))

    def test_rejection_low_accuracy(self) -> None:
        """Asserts promotion rejected when accuracy is below 90% or lower than baseline."""
        candidate_metrics = BenchmarkMetrics(
            total_samples=5000,
            accuracy=0.88,  # Below 0.90
            false_positive_rate=0.02,
            false_negative_rate=0.10,
            mean_latency_ms=5.0,
            max_latency_ms=10.0,
            peak_memory_mb=256.0,
        )

        res = self.gate.evaluate_promotion(candidate_metrics)

        self.assertFalse(res.is_promoted)
        self.assertFalse(res.accuracy_passed)
        self.assertTrue(any("Accuracy below minimum threshold" in r for r in res.rejection_reasons))

    def test_rejection_high_latency(self) -> None:
        """Asserts promotion rejected when forward pass latency exceeds 20ms."""
        candidate_metrics = BenchmarkMetrics(
            total_samples=5000,
            accuracy=0.95,
            false_positive_rate=0.02,
            false_negative_rate=0.03,
            mean_latency_ms=28.5,  # Exceeds 20ms
            max_latency_ms=45.0,
            peak_memory_mb=256.0,
        )

        res = self.gate.evaluate_promotion(candidate_metrics)

        self.assertFalse(res.is_promoted)
        self.assertFalse(res.latency_passed)
        self.assertTrue(any("latency exceeds bound" in r for r in res.rejection_reasons))

    def test_rejection_excessive_memory(self) -> None:
        """Asserts promotion rejected when peak memory exceeds 1024 MB (1.0 GB)."""
        candidate_metrics = BenchmarkMetrics(
            total_samples=5000,
            accuracy=0.95,
            false_positive_rate=0.02,
            false_negative_rate=0.03,
            mean_latency_ms=10.0,
            max_latency_ms=15.0,
            peak_memory_mb=2048.0,  # Exceeds 1024 MB
        )

        res = self.gate.evaluate_promotion(candidate_metrics)

        self.assertFalse(res.is_promoted)
        self.assertFalse(res.memory_passed)
        self.assertTrue(any("memory exceeds bound" in r for r in res.rejection_reasons))

    def test_rejection_shadow_divergence(self) -> None:
        """Asserts promotion rejected when live shadow mode divergence exceeds 2%."""
        candidate_metrics = BenchmarkMetrics(
            total_samples=5000,
            accuracy=0.95,
            false_positive_rate=0.02,
            false_negative_rate=0.03,
            mean_latency_ms=10.0,
            max_latency_ms=15.0,
            peak_memory_mb=256.0,
        )

        # Mock model with 10% divergence rate
        mock_pred = MockLearnedPredictor(divergence_ratio=0.10)
        st = CanonicalUIGraph(timestamp_ms=1000.0, nodes={})
        act = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_1")
        obs_delta = StateDelta(modified_nodes=["btn_1"], outcome_class=OutcomeClass.SUCCESS)

        for _ in range(500):
            self.gate.record_shadow_step(
                candidate_predictor=mock_pred,
                baseline_predictor=self.baseline,
                current_state=st,
                action=act,
                observed_delta=obs_delta,
            )

        res = self.gate.evaluate_promotion(candidate_metrics)

        self.assertFalse(res.is_promoted)
        self.assertFalse(res.shadow_passed)
        self.assertTrue(any("Shadow divergence rate too high" in r for r in res.rejection_reasons))

    def test_metrics_serialization_roundtrip(self) -> None:
        """Asserts BenchmarkMetrics and GateValidationResult serialization roundtrip."""
        metrics = BenchmarkMetrics(
            total_samples=5000,
            accuracy=0.92,
            false_positive_rate=0.03,
            false_negative_rate=0.05,
            mean_latency_ms=12.4,
            max_latency_ms=18.9,
            peak_memory_mb=500.0,
        )
        data = metrics.to_dict()
        restored = BenchmarkMetrics.from_dict(data)

        self.assertEqual(restored.total_samples, 5000)
        self.assertEqual(restored.accuracy, 0.92)
        self.assertEqual(restored.peak_memory_mb, 500.0)


if __name__ == "__main__":
    unittest.main()
