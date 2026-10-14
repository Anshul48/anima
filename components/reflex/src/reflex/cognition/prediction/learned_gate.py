"""Reflex Learned Predictor Gate: Shadow evaluation harness and empirical gating for neural predictors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Sequence

from reflex.cognition.prediction.surprise_evaluator import SurpriseEvaluator
from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.prediction import ExpectedDeltaPredictorPort
from reflex.schemas.actions import TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import TransitionTuple
from reflex.schemas.state import CanonicalUIGraph


class LearnedPredictorPort(ABC):
    """Abstract port for candidate learned neural predictors (JEPA, Latent World Models)."""

    @abstractmethod
    def predict_delta(
        self,
        current_state: CanonicalUIGraph,
        action: TypedAction,
    ) -> StateDelta:
        """Generates action-conditioned predicted state delta."""
        ...

    @abstractmethod
    def get_memory_usage_mb(self) -> float:
        """Returns current VRAM / RAM consumption in megabytes."""
        ...


@dataclass(frozen=True)
class BenchmarkMetrics:
    """Quantitative performance metrics from benchmark evaluation."""
    total_samples: int
    accuracy: float
    false_positive_rate: float
    false_negative_rate: float
    mean_latency_ms: float
    max_latency_ms: float
    peak_memory_mb: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_samples": self.total_samples,
            "accuracy": self.accuracy,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "mean_latency_ms": self.mean_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "peak_memory_mb": self.peak_memory_mb,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BenchmarkMetrics:
        return cls(
            total_samples=int(data["total_samples"]),
            accuracy=float(data["accuracy"]),
            false_positive_rate=float(data["false_positive_rate"]),
            false_negative_rate=float(data["false_negative_rate"]),
            mean_latency_ms=float(data["mean_latency_ms"]),
            max_latency_ms=float(data["max_latency_ms"]),
            peak_memory_mb=float(data["peak_memory_mb"]),
        )


@dataclass(frozen=True)
class ShadowStepRecord:
    """Record of a single non-actuating shadow mode evaluation step."""
    step_index: int
    baseline_pe: float
    candidate_pe: float
    diverged: bool
    timestamp_ms: float
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "baseline_pe": self.baseline_pe,
            "candidate_pe": self.candidate_pe,
            "diverged": self.diverged,
            "timestamp_ms": self.timestamp_ms,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ShadowStepRecord:
        return cls(
            step_index=int(data["step_index"]),
            baseline_pe=float(data["baseline_pe"]),
            candidate_pe=float(data["candidate_pe"]),
            diverged=bool(data["diverged"]),
            timestamp_ms=float(data["timestamp_ms"]),
            details=str(data.get("details", "")),
        )


@dataclass(frozen=True)
class GateValidationResult:
    """Outcome of learned predictor promotion evaluation."""
    is_promoted: bool
    benchmark_passed: bool
    accuracy_passed: bool
    false_positive_passed: bool
    latency_passed: bool
    memory_passed: bool
    shadow_passed: bool
    baseline_metrics: Optional[BenchmarkMetrics]
    candidate_metrics: Optional[BenchmarkMetrics]
    shadow_total_steps: int
    shadow_divergence_rate: float
    rejection_reasons: List[str]
    details: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_promoted": self.is_promoted,
            "benchmark_passed": self.benchmark_passed,
            "accuracy_passed": self.accuracy_passed,
            "false_positive_passed": self.false_positive_passed,
            "latency_passed": self.latency_passed,
            "memory_passed": self.memory_passed,
            "shadow_passed": self.shadow_passed,
            "baseline_metrics": self.baseline_metrics.to_dict() if self.baseline_metrics else None,
            "candidate_metrics": self.candidate_metrics.to_dict() if self.candidate_metrics else None,
            "shadow_total_steps": self.shadow_total_steps,
            "shadow_divergence_rate": self.shadow_divergence_rate,
            "rejection_reasons": list(self.rejection_reasons),
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GateValidationResult:
        return cls(
            is_promoted=bool(data["is_promoted"]),
            benchmark_passed=bool(data["benchmark_passed"]),
            accuracy_passed=bool(data["accuracy_passed"]),
            false_positive_passed=bool(data["false_positive_passed"]),
            latency_passed=bool(data["latency_passed"]),
            memory_passed=bool(data["memory_passed"]),
            shadow_passed=bool(data["shadow_passed"]),
            baseline_metrics=BenchmarkMetrics.from_dict(data["baseline_metrics"]) if data.get("baseline_metrics") else None,
            candidate_metrics=BenchmarkMetrics.from_dict(data["candidate_metrics"]) if data.get("candidate_metrics") else None,
            shadow_total_steps=int(data["shadow_total_steps"]),
            shadow_divergence_rate=float(data["shadow_divergence_rate"]),
            rejection_reasons=list(data.get("rejection_reasons", [])),
            details=str(data.get("details", "")),
        )


@dataclass
class LearnedPredictorGateConfig:
    """Thresholds required before a learned predictor can be promoted to active control."""
    min_benchmark_samples: int = 5000
    min_accuracy: float = 0.90
    max_false_positive_rate: float = 0.05
    max_latency_ms: float = 20.0
    max_memory_mb: float = 1024.0
    min_shadow_steps: int = 500
    max_shadow_divergence_rate: float = 0.02
    surprise_threshold: float = 0.25


class LearnedPredictorGate:
    """Shadow evaluation harness gating future learned neural predictors.

    Enforces empirical validation criteria (accuracy >= 90%, false positive < 5%,
    latency < 20ms, memory < 1.0 GB, shadow divergence < 2% over 500 steps)
    before any learned model can be promoted into the active motor control loop.
    """

    def __init__(
        self,
        config: Optional[LearnedPredictorGateConfig] = None,
        surprise_evaluator: Optional[SurpriseEvaluator] = None,
        clock: Optional[ClockPort] = None,
    ) -> None:
        self.config = config or LearnedPredictorGateConfig()
        self.surprise_evaluator = surprise_evaluator or SurpriseEvaluator()
        self.clock: ClockPort = clock or SystemClock()
        self._shadow_history: List[ShadowStepRecord] = []

    @property
    def shadow_history(self) -> List[ShadowStepRecord]:
        return list(self._shadow_history)

    def reset_shadow_history(self) -> None:
        """Clears all accumulated shadow mode records."""
        self._shadow_history.clear()

    def run_offline_benchmark(
        self,
        predictor: LearnedPredictorPort,
        samples: Sequence[Tuple[CanonicalUIGraph, TypedAction, StateDelta]],
    ) -> BenchmarkMetrics:
        """Evaluates predictor accuracy, false alarms, and latency over a test transition dataset."""
        total = len(samples)
        if total == 0:
            return BenchmarkMetrics(
                total_samples=0,
                accuracy=0.0,
                false_positive_rate=1.0,
                false_negative_rate=1.0,
                mean_latency_ms=0.0,
                max_latency_ms=0.0,
                peak_memory_mb=0.0,
            )

        correct_predictions = 0
        false_positives = 0
        false_negatives = 0
        latencies: List[float] = []
        peak_memory: float = 0.0

        for state, action, observed_delta in samples:
            t0 = time.perf_counter()
            predicted_delta = predictor.predict_delta(state, action)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(latency_ms)

            mem = predictor.get_memory_usage_mb()
            if mem > peak_memory:
                peak_memory = mem

            # Evaluate surprise between predicted and observed
            eval_res = self.surprise_evaluator.evaluate_surprise(
                expected_delta=predicted_delta,
                observed_delta=observed_delta,
                threshold=self.config.surprise_threshold,
            )

            is_actual_success = observed_delta.outcome_class in (
                OutcomeClass.SUCCESS,
                OutcomeClass.NAVIGATION,
            )

            if not eval_res.is_surprised:
                correct_predictions += 1
            else:
                if is_actual_success:
                    # Model flagged high surprise on a normal successful transition
                    false_positives += 1
                else:
                    # Model flagged high surprise on actual error/modal (expected surprise)
                    correct_predictions += 1

        accuracy = correct_predictions / total
        fp_rate = false_positives / total
        fn_rate = false_negatives / total
        mean_lat = sum(latencies) / len(latencies) if latencies else 0.0
        max_lat = max(latencies) if latencies else 0.0

        return BenchmarkMetrics(
            total_samples=total,
            accuracy=round(accuracy, 4),
            false_positive_rate=round(fp_rate, 4),
            false_negative_rate=round(fn_rate, 4),
            mean_latency_ms=round(mean_lat, 3),
            max_latency_ms=round(max_lat, 3),
            peak_memory_mb=round(peak_memory, 2),
        )

    def record_shadow_step(
        self,
        candidate_predictor: LearnedPredictorPort,
        baseline_predictor: ExpectedDeltaPredictorPort,
        current_state: CanonicalUIGraph,
        action: TypedAction,
        observed_delta: StateDelta,
    ) -> ShadowStepRecord:
        """Executes candidate model in shadow mode and records divergence against baseline."""
        baseline_pred = baseline_predictor.predict_expected_delta(current_state, action)
        candidate_pred = candidate_predictor.predict_delta(current_state, action)

        baseline_eval = self.surprise_evaluator.evaluate_surprise(
            expected_delta=baseline_pred,
            observed_delta=observed_delta,
            threshold=self.config.surprise_threshold,
        )
        candidate_eval = self.surprise_evaluator.evaluate_surprise(
            expected_delta=candidate_pred,
            observed_delta=observed_delta,
            threshold=self.config.surprise_threshold,
        )

        # Divergence occurs when candidate and baseline disagree on surprise classification
        diverged = baseline_eval.is_surprised != candidate_eval.is_surprised

        record = ShadowStepRecord(
            step_index=len(self._shadow_history),
            baseline_pe=baseline_eval.prediction_error,
            candidate_pe=candidate_eval.prediction_error,
            diverged=diverged,
            timestamp_ms=self.clock.now_ms(),
            details=(
                f"Candidate PE={candidate_eval.prediction_error:.3f} vs "
                f"Baseline PE={baseline_eval.prediction_error:.3f}"
            ),
        )
        self._shadow_history.append(record)
        return record

    def evaluate_promotion(
        self,
        candidate_metrics: BenchmarkMetrics,
        baseline_metrics: Optional[BenchmarkMetrics] = None,
    ) -> GateValidationResult:
        """Evaluates whether the candidate learned predictor satisfies all promotion criteria."""
        rejection_reasons: List[str] = []

        # 1. Sample Size Check
        benchmark_passed = candidate_metrics.total_samples >= self.config.min_benchmark_samples
        if not benchmark_passed:
            rejection_reasons.append(
                f"Insufficient benchmark samples ({candidate_metrics.total_samples} < {self.config.min_benchmark_samples})"
            )

        # 2. Accuracy Check
        accuracy_passed = candidate_metrics.accuracy >= self.config.min_accuracy
        if baseline_metrics and candidate_metrics.accuracy < baseline_metrics.accuracy:
            accuracy_passed = False
            rejection_reasons.append(
                f"Candidate accuracy ({candidate_metrics.accuracy:.1%}) inferior to baseline ({baseline_metrics.accuracy:.1%})"
            )
        elif not accuracy_passed:
            rejection_reasons.append(
                f"Accuracy below minimum threshold ({candidate_metrics.accuracy:.1%} < {self.config.min_accuracy:.1%})"
            )

        # 3. False Positive Rate Check
        fp_passed = candidate_metrics.false_positive_rate <= self.config.max_false_positive_rate
        if not fp_passed:
            rejection_reasons.append(
                f"False positive surprise rate too high ({candidate_metrics.false_positive_rate:.1%} > {self.config.max_false_positive_rate:.1%})"
            )

        # 4. Latency Check
        latency_passed = candidate_metrics.mean_latency_ms <= self.config.max_latency_ms
        if not latency_passed:
            rejection_reasons.append(
                f"Mean latency exceeds bound ({candidate_metrics.mean_latency_ms:.1f}ms > {self.config.max_latency_ms:.1f}ms)"
            )

        # 5. Memory Check
        memory_passed = candidate_metrics.peak_memory_mb <= self.config.max_memory_mb
        if not memory_passed:
            rejection_reasons.append(
                f"Peak memory exceeds bound ({candidate_metrics.peak_memory_mb:.1f}MB > {self.config.max_memory_mb:.1f}MB)"
            )

        # 6. Shadow Validation Check
        shadow_total = len(self._shadow_history)
        diverged_count = sum(1 for r in self._shadow_history if r.diverged)
        shadow_divergence_rate = diverged_count / shadow_total if shadow_total > 0 else 0.0

        shadow_passed = (
            shadow_total >= self.config.min_shadow_steps
            and shadow_divergence_rate <= self.config.max_shadow_divergence_rate
        )
        if shadow_total < self.config.min_shadow_steps:
            rejection_reasons.append(
                f"Insufficient shadow steps ({shadow_total} < {self.config.min_shadow_steps})"
            )
        elif shadow_divergence_rate > self.config.max_shadow_divergence_rate:
            rejection_reasons.append(
                f"Shadow divergence rate too high ({shadow_divergence_rate:.1%} > {self.config.max_shadow_divergence_rate:.1%})"
            )

        is_promoted = (
            benchmark_passed
            and accuracy_passed
            and fp_passed
            and latency_passed
            and memory_passed
            and shadow_passed
        )

        details = (
            f"Promotion Gate: {'APPROVED' if is_promoted else 'REJECTED'}. "
            f"Samples={candidate_metrics.total_samples}, Acc={candidate_metrics.accuracy:.1%}, "
            f"FP={candidate_metrics.false_positive_rate:.1%}, Latency={candidate_metrics.mean_latency_ms:.1f}ms, "
            f"Mem={candidate_metrics.peak_memory_mb:.1f}MB, Shadow={shadow_total} steps ({shadow_divergence_rate:.1%} div)"
        )

        return GateValidationResult(
            is_promoted=is_promoted,
            benchmark_passed=benchmark_passed,
            accuracy_passed=accuracy_passed,
            false_positive_passed=fp_passed,
            latency_passed=latency_passed,
            memory_passed=memory_passed,
            shadow_passed=shadow_passed,
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            shadow_total_steps=shadow_total,
            shadow_divergence_rate=round(shadow_divergence_rate, 4),
            rejection_reasons=rejection_reasons,
            details=details,
        )
