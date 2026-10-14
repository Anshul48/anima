"""Reflex Efference Copy Verifier & Predictive Monitoring.

Implements active inference closed-loop motor verification:
1. Generates the forward model efference copy (expected state delta ΔS_hat) before or during action dispatch.
2. Compares efference copy against observed post-action state delta ΔS (re-afference).
3. Computes multimodal prediction error (PE).
4. Monitors surprise with an automatic circuit breaker: if PE > tau, trips the breaker, halts the motor loop,
   and yields structured failure context to System 2 abductive recovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from reflex.cognition.prediction.circuit_breaker import (
    BreakerFailureContext,
    SurpriseCircuitBreaker,
    SurpriseCircuitBreakerConfig,
)
from reflex.cognition.prediction.delta_engine import ExpectedDeltaEngine
from reflex.cognition.prediction.surprise_evaluator import (
    SurpriseEvaluator,
    SurpriseEvaluatorConfig,
)
from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.prediction import (
    ExpectedDeltaPredictorPort,
    PredictionEvaluation,
    SurpriseEvaluatorPort,
)
from reflex.schemas.actions import TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import CanonicalUIGraph


@dataclass(frozen=True)
class EfferenceVerificationResult:
    """Outcome of efference copy forward model prediction vs actual observed re-afference."""

    is_verified: bool
    prediction_error: float
    surprise_threshold: float
    circuit_breaker_tripped: bool
    expected_delta: StateDelta
    observed_delta: StateDelta
    evaluation: PredictionEvaluation
    failure_context: Optional[BreakerFailureContext] = None
    inferred_cause: str = ""
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_verified": self.is_verified,
            "prediction_error": self.prediction_error,
            "surprise_threshold": self.surprise_threshold,
            "circuit_breaker_tripped": self.circuit_breaker_tripped,
            "expected_delta": self.expected_delta.to_dict(),
            "observed_delta": self.observed_delta.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "failure_context": self.failure_context.to_dict() if self.failure_context else None,
            "inferred_cause": self.inferred_cause,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EfferenceVerificationResult:
        return cls(
            is_verified=bool(data["is_verified"]),
            prediction_error=float(data["prediction_error"]),
            surprise_threshold=float(data.get("surprise_threshold", 0.25)),
            circuit_breaker_tripped=bool(data["circuit_breaker_tripped"]),
            expected_delta=StateDelta.from_dict(data["expected_delta"]),
            observed_delta=StateDelta.from_dict(data["observed_delta"]),
            evaluation=PredictionEvaluation.from_dict(data["evaluation"]),
            failure_context=BreakerFailureContext.from_dict(data["failure_context"]) if data.get("failure_context") else None,
            inferred_cause=str(data.get("inferred_cause", "")),
            details=str(data.get("details", "")),
        )


class EfferenceCopyVerifier:
    """Coordinates forward model efference copy generation, prediction error calculation, and circuit breaker tripping."""

    def __init__(
        self,
        delta_engine: Optional[ExpectedDeltaPredictorPort] = None,
        evaluator: Optional[SurpriseEvaluatorPort] = None,
        circuit_breaker: Optional[SurpriseCircuitBreaker] = None,
        clock: Optional[ClockPort] = None,
    ) -> None:
        self.clock: ClockPort = clock or SystemClock()
        self.delta_engine: ExpectedDeltaPredictorPort = delta_engine or ExpectedDeltaEngine()
        self.evaluator: SurpriseEvaluatorPort = evaluator or SurpriseEvaluator()
        self.circuit_breaker: SurpriseCircuitBreaker = circuit_breaker or SurpriseCircuitBreaker(clock=self.clock)

    @property
    def is_tripped(self) -> bool:
        """Returns whether the surprise circuit breaker is currently tripped."""
        return self.circuit_breaker.is_tripped

    @property
    def trip_count(self) -> int:
        """Total trip count of the circuit breaker."""
        return self.circuit_breaker.trip_count

    @property
    def last_failure_context(self) -> Optional[BreakerFailureContext]:
        """Failure context from the most recent trip event."""
        return self.circuit_breaker.last_failure_context

    def generate_efference_copy(
        self,
        pre_state: CanonicalUIGraph,
        action: TypedAction,
    ) -> StateDelta:
        """Generates the expected state delta (ΔS_hat) as an efference copy before execution."""
        return self.delta_engine.predict_expected_delta(pre_state, action)

    def compute_observed_delta(
        self,
        before_state: CanonicalUIGraph,
        after_state: CanonicalUIGraph,
    ) -> StateDelta:
        """Computes the observed delta between before and after states."""
        before_nodes = before_state.nodes if before_state and before_state.nodes else {}
        after_nodes = after_state.nodes if after_state and after_state.nodes else {}

        added = [n_id for n_id in after_nodes if n_id not in before_nodes]
        removed = [n_id for n_id in before_nodes if n_id not in after_nodes]
        modified: List[str] = []
        changed_boxes: List[Tuple[int, int, int, int]] = []

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
                ):
                    modified.append(n_id)
                    changed_boxes.append(
                        (a_node.bounds.x1, a_node.bounds.y1, a_node.bounds.x2, a_node.bounds.y2)
                    )

        for n_id in added:
            node = after_nodes[n_id]
            changed_boxes.append((node.bounds.x1, node.bounds.y1, node.bounds.x2, node.bounds.y2))
        for n_id in removed:
            node = before_nodes[n_id]
            changed_boxes.append((node.bounds.x1, node.bounds.y1, node.bounds.x2, node.bounds.y2))

        vw, vh = after_state.viewport_size if after_state else (1920, 1080)
        viewport_area = max(1, vw * vh)
        total_changed_area = sum(
            max(0, b[2] - b[0]) * max(0, b[3] - b[1]) for b in changed_boxes
        )
        pixel_change = min(1.0, total_changed_area / viewport_area)

        outcome = OutcomeClass.SUCCESS
        if before_state and after_state and before_state.url != after_state.url and after_state.url:
            outcome = OutcomeClass.NAVIGATION
            pixel_change = max(pixel_change, 0.5)

        # Check for modals
        if any(n.role.value == "modal" for n in after_nodes.values()):
            if not any(n.role.value == "modal" for n in before_nodes.values()):
                outcome = OutcomeClass.MODAL_APPEARED

        if len(added) == 0 and len(removed) == 0 and len(modified) == 0 and pixel_change == 0.0:
            outcome = OutcomeClass.NOOP

        return StateDelta(
            added_nodes=added,
            removed_nodes=removed,
            modified_nodes=modified,
            pixel_change_ratio=pixel_change,
            changed_bounding_boxes=changed_boxes,
            outcome_class=outcome,
        )

    def verify_transition(
        self,
        pre_state: CanonicalUIGraph,
        action: TypedAction,
        post_state: CanonicalUIGraph,
        expected_delta: Optional[StateDelta] = None,
        observed_delta: Optional[StateDelta] = None,
        threshold: Optional[float] = None,
    ) -> EfferenceVerificationResult:
        """Closed-loop verification of efference copy against observed transition.

        Computes prediction error, checks surprise against threshold, and triggers
        the circuit breaker if surprise exceeds tolerance.
        """
        # 1. Forward Model Efference Copy
        exp_delta = expected_delta or self.generate_efference_copy(pre_state, action)

        # 2. Observed Re-afference Delta
        obs_delta = observed_delta or self.compute_observed_delta(pre_state, post_state)

        # 3. Prediction Error Evaluation
        evaluation = self.evaluator.evaluate_surprise(
            expected_delta=exp_delta,
            observed_delta=obs_delta,
            threshold=threshold,
            before_state=pre_state,
            after_state=post_state,
            action=action,
        )

        # 4. Surprise Circuit Breaker Check
        tripped = self.circuit_breaker.check_surprise(
            evaluation=evaluation,
            pre_state=pre_state,
            action=action,
            post_state=post_state,
            expected_delta=exp_delta,
            observed_delta=obs_delta,
        )

        is_verified = (not tripped) and (not evaluation.is_surprised)
        failure_ctx = self.circuit_breaker.last_failure_context if tripped else None

        details = (
            f"Efference verification {'PASSED' if is_verified else 'FAILED'}: "
            f"PE={evaluation.prediction_error:.3f}, tau={evaluation.surprise_threshold:.3f}, "
            f"cause='{evaluation.inferred_cause}', breaker_tripped={tripped}"
        )

        return EfferenceVerificationResult(
            is_verified=is_verified,
            prediction_error=evaluation.prediction_error,
            surprise_threshold=evaluation.surprise_threshold,
            circuit_breaker_tripped=tripped,
            expected_delta=exp_delta,
            observed_delta=obs_delta,
            evaluation=evaluation,
            failure_context=failure_ctx,
            inferred_cause=evaluation.inferred_cause,
            details=details,
        )

    def reset(self) -> None:
        """Resets the circuit breaker and clears trip state."""
        self.circuit_breaker.reset()
