from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class ActionType(str, Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    KEY_PRESS = "key_press"
    SCROLL = "scroll"
    DRAG_AND_DROP = "drag_and_drop"
    HOVER = "hover"
    WAIT = "wait"
    NAVIGATE = "navigate"
    NOOP = "noop"
    CLEAR_AND_TYPE = "clear_and_type"
    SELECT_OPTION = "select_option"
    KEY_COMBINATION = "key_combination"


class SafetyClass(str, Enum):
    REVERSIBLE = "reversible"     # e.g., focus field, scroll, type in draft
    DESTRUCTIVE = "destructive"   # e.g., delete file, submit form, drop database
    AMBIGUOUS = "ambiguous"       # e.g., modal button, toggle setting


@dataclass(frozen=True)
class NormalizedCoords:
    """Normalized screen coordinates in [0.0, 1.0] relative to frame width/height."""
    x: float
    y: float

    def to_pixel(self, screen_width: int, screen_height: int) -> Tuple[int, int]:
        return int(round(self.x * screen_width)), int(round(self.y * screen_height))

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NormalizedCoords:
        return cls(x=float(data["x"]), y=float(data["y"]))


@dataclass(frozen=True)
class TypedAction:
    """Canonical action representation for execution and memory logging."""
    action_type: ActionType
    target_node_id: Optional[str] = None
    target_label: Optional[str] = None
    coords: Optional[NormalizedCoords] = None
    text_payload: Optional[str] = None
    key_code: Optional[str] = None
    scroll_delta: Optional[Tuple[float, float]] = None  # (dx, dy)
    safety_class: SafetyClass = SafetyClass.REVERSIBLE
    metadata: Dict[str, Any] = field(default_factory=dict)
    value: Optional[str] = None

    def __post_init__(self) -> None:
        if self.text_payload is None and self.value is not None:
            object.__setattr__(self, "text_payload", self.value)
        elif self.value is None and self.text_payload is not None:
            object.__setattr__(self, "value", self.text_payload)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type.value if isinstance(self.action_type, ActionType) else str(self.action_type),
            "target_node_id": self.target_node_id,
            "target_label": self.target_label,
            "coords": self.coords.to_dict() if self.coords else None,
            "text_payload": self.text_payload,
            "key_code": self.key_code,
            "scroll_delta": list(self.scroll_delta) if self.scroll_delta is not None else None,
            "safety_class": self.safety_class.value if isinstance(self.safety_class, SafetyClass) else str(self.safety_class),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TypedAction:
        coords_data = data.get("coords")
        coords = NormalizedCoords.from_dict(coords_data) if coords_data else None
        scroll_delta_data = data.get("scroll_delta")
        scroll_delta = (float(scroll_delta_data[0]), float(scroll_delta_data[1])) if scroll_delta_data else None
        raw_action_type = data["action_type"]
        action_type = ActionType(raw_action_type) if raw_action_type in ActionType._value2member_map_ else ActionType(raw_action_type.lower())
        raw_safety = data.get("safety_class", SafetyClass.REVERSIBLE.value)
        safety_class = SafetyClass(raw_safety) if raw_safety in SafetyClass._value2member_map_ else SafetyClass(raw_safety.lower())

        return cls(
            action_type=action_type,
            target_node_id=data.get("target_node_id"),
            target_label=data.get("target_label"),
            coords=coords,
            text_payload=data.get("text_payload"),
            key_code=data.get("key_code"),
            scroll_delta=scroll_delta,
            safety_class=safety_class,
            metadata=data.get("metadata", {}),
        )
