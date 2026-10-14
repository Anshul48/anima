from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from reflex.schemas.actions import SafetyClass, TypedAction
from reflex.schemas.delta import StateDelta


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TransitionTuple:
    """Single step transition for episodic recording (System A)."""
    transition_id: str
    episode_id: str
    step_index: int
    timestamp_ms: float
    ui_state_hash: str
    goal_text: str
    goal_embedding: List[float]             # 384-dim or 768-dim vector
    visual_embedding: Optional[List[float]] # Frozen vision encoder output (DINO/SigLIP)
    action: TypedAction
    next_ui_state_hash: Optional[str]
    delta: StateDelta
    duration_ms: float
    surprise_score: float
    provenance: Dict[str, Any] = field(default_factory=dict)  # e.g. {"source": "human"|"system2"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "episode_id": self.episode_id,
            "step_index": self.step_index,
            "timestamp_ms": self.timestamp_ms,
            "ui_state_hash": self.ui_state_hash,
            "goal_text": self.goal_text,
            "goal_embedding": list(self.goal_embedding),
            "visual_embedding": list(self.visual_embedding) if self.visual_embedding is not None else None,
            "action": self.action.to_dict(),
            "next_ui_state_hash": self.next_ui_state_hash,
            "delta": self.delta.to_dict(),
            "duration_ms": self.duration_ms,
            "surprise_score": self.surprise_score,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TransitionTuple:
        visual_emb = [float(x) for x in data["visual_embedding"]] if data.get("visual_embedding") is not None else None
        return cls(
            transition_id=data["transition_id"],
            episode_id=data["episode_id"],
            step_index=int(data["step_index"]),
            timestamp_ms=float(data["timestamp_ms"]),
            ui_state_hash=data["ui_state_hash"],
            goal_text=data["goal_text"],
            goal_embedding=[float(x) for x in data.get("goal_embedding", [])],
            visual_embedding=visual_emb,
            action=TypedAction.from_dict(data["action"]),
            next_ui_state_hash=data.get("next_ui_state_hash"),
            delta=StateDelta.from_dict(data["delta"]),
            duration_ms=float(data["duration_ms"]),
            surprise_score=float(data["surprise_score"]),
            provenance=data.get("provenance", {}),
        )


@dataclass
class MotorSkill:
    """Compiled, parameterized System-1 motor skill (System B)."""
    skill_id: str
    version: int
    preconditions_hash: str                 # Exact structural matching key
    goal_embedding: List[float]
    visual_context_embedding: List[float]
    action_sequence: List[TypedAction]
    expected_delta: StateDelta
    timing_mean_ms: float
    timing_std_ms: float
    confidence: float                       # Calibrated success probability
    safety_class: SafetyClass
    provenance_episode_ids: List[str]
    validated_count: int
    last_validated: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "preconditions_hash": self.preconditions_hash,
            "goal_embedding": list(self.goal_embedding),
            "visual_context_embedding": list(self.visual_context_embedding),
            "action_sequence": [a.to_dict() for a in self.action_sequence],
            "expected_delta": self.expected_delta.to_dict(),
            "timing_mean_ms": self.timing_mean_ms,
            "timing_std_ms": self.timing_std_ms,
            "confidence": self.confidence,
            "safety_class": self.safety_class.value if isinstance(self.safety_class, SafetyClass) else str(self.safety_class),
            "provenance_episode_ids": list(self.provenance_episode_ids),
            "validated_count": self.validated_count,
            "last_validated": self.last_validated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MotorSkill:
        raw_safety = data.get("safety_class", SafetyClass.REVERSIBLE.value)
        safety_class = SafetyClass(raw_safety) if raw_safety in SafetyClass._value2member_map_ else SafetyClass(raw_safety.lower())
        last_val_raw = data.get("last_validated")
        last_validated = datetime.fromisoformat(last_val_raw) if last_val_raw else _utc_now()

        return cls(
            skill_id=data["skill_id"],
            version=int(data["version"]),
            preconditions_hash=data["preconditions_hash"],
            goal_embedding=[float(x) for x in data.get("goal_embedding", [])],
            visual_context_embedding=[float(x) for x in data.get("visual_context_embedding", [])],
            action_sequence=[TypedAction.from_dict(a) for a in data.get("action_sequence", [])],
            expected_delta=StateDelta.from_dict(data["expected_delta"]),
            timing_mean_ms=float(data["timing_mean_ms"]),
            timing_std_ms=float(data["timing_std_ms"]),
            confidence=float(data["confidence"]),
            safety_class=safety_class,
            provenance_episode_ids=list(data.get("provenance_episode_ids", [])),
            validated_count=int(data.get("validated_count", 0)),
            last_validated=last_validated,
        )
