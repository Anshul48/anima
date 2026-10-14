"""Reflex Surprise Circuit Breaker: Active inference motor loop circuit breaker and failure context capture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.prediction import PredictionEvaluation
from reflex.schemas.actions import TypedAction
from reflex.schemas.delta import StateDelta
from reflex.schemas.state import CanonicalUIGraph


@dataclass(frozen=True)
class BreakerFailureContext:
    """Diagnostic context captured when the surprise circuit breaker trips."""
    evaluation: PredictionEvaluation
    timestamp_ms: float
    trip_count: int
    pre_state: Optional[CanonicalUIGraph] = None
    action: Optional[TypedAction] = None
    post_state: Optional[CanonicalUIGraph] = None
    expected_delta: Optional[StateDelta] = None
    observed_delta: Optional[StateDelta] = None
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation": self.evaluation.to_dict(),
            "timestamp_ms": self.timestamp_ms,
            "trip_count": self.trip_count,
            "pre_state": self.pre_state.to_dict() if self.pre_state else None,
            "action": self.action.to_dict() if self.action else None,
            "post_state": self.post_state.to_dict() if self.post_state else None,
            "expected_delta": self.expected_delta.to_dict() if self.expected_delta else None,
            "observed_delta": self.observed_delta.to_dict() if self.observed_delta else None,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BreakerFailureContext:
        return cls(
            evaluation=PredictionEvaluation.from_dict(data["evaluation"]),
            timestamp_ms=float(data["timestamp_ms"]),
            trip_count=int(data["trip_count"]),
            pre_state=CanonicalUIGraph.from_dict(data["pre_state"]) if data.get("pre_state") else None,
            action=TypedAction.from_dict(data["action"]) if data.get("action") else None,
            post_state=CanonicalUIGraph.from_dict(data["post_state"]) if data.get("post_state") else None,
            expected_delta=StateDelta.from_dict(data["expected_delta"]) if data.get("expected_delta") else None,
            observed_delta=StateDelta.from_dict(data["observed_delta"]) if data.get("observed_delta") else None,
            details=str(data.get("details", "")),
        )


@dataclass
class SurpriseCircuitBreakerConfig:
    """Configuration for SurpriseCircuitBreaker trip thresholds and policies."""
    threshold: float = 0.25
    consecutive_threshold: int = 1
    max_history_entries: int = 100


class SurpriseCircuitBreaker:
    """Monitors prediction surprise in the motor loop and triggers immediate halts on high surprise.

    When PE > tau, trips the breaker, emits motor halt signal, and yields full failure
    context to System 2 recovery to plan alternative courses of action.
    """

    def __init__(
        self,
        config: Optional[SurpriseCircuitBreakerConfig] = None,
        clock: Optional[ClockPort] = None,
    ) -> None:
        self.config = config or SurpriseCircuitBreakerConfig()
        self.clock: ClockPort = clock or SystemClock()

        self._is_tripped: bool = False
        self._trip_count: int = 0
        self._consecutive_surprises: int = 0
        self._last_evaluation: Optional[PredictionEvaluation] = None
        self._last_failure_context: Optional[BreakerFailureContext] = None
        self._history: List[BreakerFailureContext] = []

    @property
    def is_tripped(self) -> bool:
        """Returns True if the circuit breaker is currently in tripped state."""
        return self._is_tripped

    @property
    def trip_count(self) -> int:
        """Total number of times the circuit breaker has tripped."""
        return self._trip_count

    @property
    def consecutive_surprises(self) -> int:
        """Current streak of consecutive high surprise evaluations."""
        return self._consecutive_surprises

    @property
    def last_failure_context(self) -> Optional[BreakerFailureContext]:
        """Failure context from the most recent trip event."""
        return self._last_failure_context

    @property
    def last_evaluation(self) -> Optional[PredictionEvaluation]:
        """Most recent PredictionEvaluation processed by the breaker."""
        return self._last_evaluation

    @property
    def history(self) -> List[BreakerFailureContext]:
        """Chronological list of all trip events."""
        return list(self._history)

    def check_surprise(
        self,
        evaluation: PredictionEvaluation,
        pre_state: Optional[CanonicalUIGraph] = None,
        action: Optional[TypedAction] = None,
        post_state: Optional[CanonicalUIGraph] = None,
        expected_delta: Optional[StateDelta] = None,
        observed_delta: Optional[StateDelta] = None,
    ) -> bool:
        """Evaluates prediction surprise and updates breaker state.

        Returns True if the circuit breaker is tripped (motor loop must halt),
        False if execution is clear to continue.
        """
        self._last_evaluation = evaluation

        if evaluation.is_surprised:
            self._consecutive_surprises += 1
            if self._consecutive_surprises >= self.config.consecutive_threshold:
                self._is_tripped = True
                self._trip_count += 1

                details = (
                    f"Surprise Circuit Breaker TRIPPED: PE={evaluation.prediction_error:.3f} > "
                    f"tau={evaluation.surprise_threshold:.3f}. Cause: '{evaluation.inferred_cause}'"
                )

                ctx = BreakerFailureContext(
                    evaluation=evaluation,
                    timestamp_ms=self.clock.now_ms(),
                    trip_count=self._trip_count,
                    pre_state=pre_state,
                    action=action,
                    post_state=post_state,
                    expected_delta=expected_delta,
                    observed_delta=observed_delta,
                    details=details,
                )

                self._last_failure_context = ctx
                self._history.append(ctx)
                if len(self._history) > self.config.max_history_entries:
                    self._history.pop(0)

                return True
        else:
            # Low surprise: reset consecutive streak
            self._consecutive_surprises = 0

        return self._is_tripped

    def reset(self) -> None:
        """Resets trip status to resume normal motor loop execution."""
        self._is_tripped = False
        self._consecutive_surprises = 0

    def trip_manual(
        self,
        reason: str,
        pre_state: Optional[CanonicalUIGraph] = None,
        action: Optional[TypedAction] = None,
        post_state: Optional[CanonicalUIGraph] = None,
        expected_delta: Optional[StateDelta] = None,
        observed_delta: Optional[StateDelta] = None,
    ) -> BreakerFailureContext:
        """Manually trips the circuit breaker (e.g. from watchdog or external interrupt)."""
        self._is_tripped = True
        self._trip_count += 1
        self._consecutive_surprises += 1

        eval_mock = PredictionEvaluation(
            prediction_error=1.0,
            surprise_threshold=self.config.threshold,
            is_surprised=True,
            structural_mismatch=1.0,
            text_mismatch=1.0,
            visual_mismatch=1.0,
            inferred_cause=f"Manual Trip: {reason}",
        )
        self._last_evaluation = eval_mock

        ctx = BreakerFailureContext(
            evaluation=eval_mock,
            timestamp_ms=self.clock.now_ms(),
            trip_count=self._trip_count,
            pre_state=pre_state,
            action=action,
            post_state=post_state,
            expected_delta=expected_delta,
            observed_delta=observed_delta,
            details=f"Manual Circuit Breaker Trip: {reason}",
        )

        self._last_failure_context = ctx
        self._history.append(ctx)
        return ctx
