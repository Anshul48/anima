from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


class OutcomeClass(str, Enum):
    SUCCESS = "success"             # Intended state transition achieved
    LOADING = "loading"             # Delayed render / spinner active
    MODAL_APPEARED = "modal"        # Unexpected popup/modal intercepted
    NAVIGATION = "navigation"       # Page or window URL changed
    NOOP = "noop"                   # Action had zero visual/DOM effect
    ERROR = "error"                 # App crash, 404, or hard failure
    UNKNOWN_EFFECT = "unknown_effect" # Action dispatch timed out or unconfirmed
    DIRECT_MATCH = "direct_match"


@dataclass(frozen=True)
class StateDelta:
    """Visual and structural difference between Frame t and Frame t+1."""
    added_nodes: List[str] = field(default_factory=list)
    removed_nodes: List[str] = field(default_factory=list)
    modified_nodes: List[str] = field(default_factory=list)
    pixel_change_ratio: float = 0.0          # Ratio of changed pixels [0.0, 1.0]
    changed_bounding_boxes: List[Tuple[int, int, int, int]] = field(default_factory=list)  # Crops for L2-L5
    outcome_class: OutcomeClass = OutcomeClass.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "added_nodes": list(self.added_nodes),
            "removed_nodes": list(self.removed_nodes),
            "modified_nodes": list(self.modified_nodes),
            "pixel_change_ratio": self.pixel_change_ratio,
            "changed_bounding_boxes": [list(b) for b in self.changed_bounding_boxes],
            "outcome_class": self.outcome_class.value if isinstance(self.outcome_class, OutcomeClass) else str(self.outcome_class),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StateDelta:
        raw_outcome = data.get("outcome_class", OutcomeClass.SUCCESS.value)
        outcome_class = OutcomeClass(raw_outcome) if raw_outcome in OutcomeClass._value2member_map_ else OutcomeClass(raw_outcome.lower())
        changed_boxes = [
            (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
            for b in data.get("changed_bounding_boxes", [])
        ]
        return cls(
            added_nodes=list(data.get("added_nodes", [])),
            removed_nodes=list(data.get("removed_nodes", [])),
            modified_nodes=list(data.get("modified_nodes", [])),
            pixel_change_ratio=float(data.get("pixel_change_ratio", 0.0)),
            changed_bounding_boxes=changed_boxes,
            outcome_class=outcome_class,
        )


@dataclass(frozen=True)
class SurpriseMetric:
    """Prediction error assessment to trigger System-2 escalation."""
    prediction_error: float          # Cosine distance or graph distance [0.0, 1.0]
    surprise_threshold: float = 0.25
    is_surprised: bool = False
    cause: str = ""                  # e.g., "Unexpected Modal", "Noop Timeout"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_error": self.prediction_error,
            "surprise_threshold": self.surprise_threshold,
            "is_surprised": self.is_surprised,
            "cause": self.cause,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SurpriseMetric:
        return cls(
            prediction_error=float(data["prediction_error"]),
            surprise_threshold=float(data.get("surprise_threshold", 0.25)),
            is_surprised=bool(data.get("is_surprised", False)),
            cause=data.get("cause", ""),
        )
