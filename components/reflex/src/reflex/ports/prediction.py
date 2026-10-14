from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from reflex.schemas.actions import TypedAction
from reflex.schemas.delta import StateDelta
from reflex.schemas.state import CanonicalUIGraph


@dataclass(frozen=True)
class PredictionEvaluation:
    """Detailed surprise evaluation result."""
    prediction_error: float
    surprise_threshold: float
    is_surprised: bool
    structural_mismatch: float
    text_mismatch: float
    visual_mismatch: float
    inferred_cause: str

    def to_dict(self) -> dict:
        return {
            "prediction_error": self.prediction_error,
            "surprise_threshold": self.surprise_threshold,
            "is_surprised": self.is_surprised,
            "structural_mismatch": self.structural_mismatch,
            "text_mismatch": self.text_mismatch,
            "visual_mismatch": self.visual_mismatch,
            "inferred_cause": self.inferred_cause,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PredictionEvaluation:
        return cls(
            prediction_error=float(data["prediction_error"]),
            surprise_threshold=float(data.get("surprise_threshold", 0.25)),
            is_surprised=bool(data.get("is_surprised", False)),
            structural_mismatch=float(data.get("structural_mismatch", 0.0)),
            text_mismatch=float(data.get("text_mismatch", 0.0)),
            visual_mismatch=float(data.get("visual_mismatch", 0.0)),
            inferred_cause=str(data.get("inferred_cause", "")),
        )


class ExpectedDeltaPredictorPort(ABC):
    """Abstract port for predicting expected state deltas given pre-state and action."""

    @abstractmethod
    def predict_expected_delta(
        self,
        current_state: CanonicalUIGraph,
        action: TypedAction,
    ) -> StateDelta:
        """Generates deterministic expected state delta."""
        ...


class SurpriseEvaluatorPort(ABC):
    """Abstract port for computing prediction error metric between expectation and observation."""

    @abstractmethod
    def evaluate_surprise(
        self,
        expected_delta: StateDelta,
        observed_delta: StateDelta,
        threshold: float = 0.25,
        before_state: Optional[CanonicalUIGraph] = None,
        after_state: Optional[CanonicalUIGraph] = None,
        action: Optional[TypedAction] = None,
    ) -> PredictionEvaluation:
        """Computes prediction error metric between expectation and observation."""
        ...
