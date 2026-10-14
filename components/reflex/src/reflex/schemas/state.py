from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple


class FrozenDict(dict):
    """A dict that raises on any mutation attempt.

    Unlike mapping proxies, it stays a real dict: JSON-serializable,
    equality-compatible with plain dicts, and deepcopy-safe. Readers see a
    dict; only writers notice the difference.
    """

    def _immutable(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("FrozenDict is immutable: published evidence cannot be edited in place")

    __setitem__ = _immutable  # type: ignore[assignment]
    __delitem__ = _immutable  # type: ignore[assignment]
    clear = _immutable  # type: ignore[assignment]
    pop = _immutable  # type: ignore[assignment]
    popitem = _immutable  # type: ignore[assignment]
    setdefault = _immutable  # type: ignore[assignment]
    update = _immutable  # type: ignore[assignment]
    __ior__ = _immutable  # type: ignore[assignment]


class FrozenList(list):
    """A list that raises on any mutation attempt.

    Stays a real list: JSON-serializable and equality-compatible with plain
    lists, so frozen snapshots compare equal to their wire form.
    """

    def _immutable(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("FrozenList is immutable: published evidence cannot be edited in place")

    __setitem__ = _immutable  # type: ignore[assignment]
    __delitem__ = _immutable  # type: ignore[assignment]
    append = _immutable  # type: ignore[assignment]
    extend = _immutable  # type: ignore[assignment]
    insert = _immutable  # type: ignore[assignment]
    remove = _immutable  # type: ignore[assignment]
    pop = _immutable  # type: ignore[assignment]
    clear = _immutable  # type: ignore[assignment]
    sort = _immutable  # type: ignore[assignment]
    reverse = _immutable  # type: ignore[assignment]
    __iadd__ = _immutable  # type: ignore[assignment]
    __imul__ = _immutable  # type: ignore[assignment]


def freeze_evidence(value: Any) -> Any:
    """Recursively converts mutable containers into immutable equivalents.

    Published snapshots must survive caller mutation: dict -> FrozenDict,
    list/tuple/set -> FrozenList, with keys and order preserved. Frozen
    containers still compare equal to their plain equivalents. Scalars pass
    through.
    """
    if isinstance(value, (FrozenDict, FrozenList)):
        return value
    if isinstance(value, dict):
        return FrozenDict({key: freeze_evidence(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return FrozenList([freeze_evidence(item) for item in value])
    if isinstance(value, (set, frozenset)):
        return FrozenList([freeze_evidence(item) for item in sorted(value, key=repr)])
    return value


def thaw_evidence(value: Any) -> Any:
    """Recursively converts frozen containers back to plain detached types."""
    if isinstance(value, Mapping):
        return {key: thaw_evidence(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_evidence(item) for item in value]
    return value


class NodeRole(str, Enum):
    BUTTON = "button"
    INPUT = "input"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    TOGGLE = "toggle"
    LINK = "link"
    TEXT = "text"
    IMAGE = "image"
    CONTAINER = "container"
    SCROLLBAR = "scrollbar"
    MODAL = "modal"
    UNKNOWN = "unknown"
    TEXT_FIELD = "text_field"
    DROPDOWN = "dropdown"
    GENERIC = "generic"
    FORM = "form"
    HEADING = "heading"


class ModalitySource(str, Enum):
    DOM = "dom"               # CDP DOM tree
    UIA = "uia"               # Windows UI Automation
    VISION = "vision"         # YOLOv11 / SegFormer fallback
    FUSED = "fused"           # Structural + visual fusion


@dataclass(frozen=True, init=False)
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def __init__(
        self,
        x1: Optional[int | float] = None,
        y1: Optional[int | float] = None,
        x2: Optional[int | float] = None,
        y2: Optional[int | float] = None,
        *,
        x: Optional[int | float] = None,
        y: Optional[int | float] = None,
        width: Optional[int | float] = None,
        height: Optional[int | float] = None,
    ) -> None:
        if x is not None and y is not None:
            _x1 = int(round(x))
            _y1 = int(round(y))
            _w = int(round(width or 0))
            _h = int(round(height or 0))
            _x2 = _x1 + _w
            _y2 = _y1 + _h
        else:
            _x1 = int(round(x1 or 0))
            _y1 = int(round(y1 or 0))
            _x2 = int(round(x2 or 0))
            _y2 = int(round(y2 or 0))
        object.__setattr__(self, "x1", _x1)
        object.__setattr__(self, "y1", _y1)
        object.__setattr__(self, "x2", _x2)
        object.__setattr__(self, "y2", _y2)

    @property
    def x(self) -> int:
        return self.x1

    @property
    def y(self) -> int:
        return self.y1

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x1 + self.width // 2, self.y1 + self.height // 2)

    def to_dict(self) -> Dict[str, int]:
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BoundingBox:
        return cls(
            x1=int(data["x1"]),
            y1=int(data["y1"]),
            x2=int(data["x2"]),
            y2=int(data["y2"]),
        )


@dataclass(frozen=True)
class UIStateNode:
    """Unified UI element node across DOM, UIA, and Vision sources."""
    node_id: str
    role: NodeRole
    bounds: BoundingBox
    label: str = ""
    value: str = ""
    is_clickable: bool = True
    is_editable: bool = False
    is_focused: bool = False
    is_enabled: bool = True
    parent_id: Optional[str] = None
    children_ids: Sequence[str] = field(default_factory=list)
    source: ModalitySource = ModalitySource.DOM
    confidence: float = 1.0
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "children_ids", freeze_evidence(list(self.children_ids)))
        object.__setattr__(self, "attributes", freeze_evidence(dict(self.attributes)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role.value if isinstance(self.role, NodeRole) else str(self.role),
            "bounds": self.bounds.to_dict(),
            "label": self.label,
            "value": self.value,
            "is_clickable": self.is_clickable,
            "is_editable": self.is_editable,
            "is_focused": self.is_focused,
            "is_enabled": self.is_enabled,
            "parent_id": self.parent_id,
            "children_ids": list(self.children_ids),
            "source": self.source.value if isinstance(self.source, ModalitySource) else str(self.source),
            "confidence": self.confidence,
            "attributes": thaw_evidence(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UIStateNode:
        raw_role = data["role"]
        role = NodeRole(raw_role) if raw_role in NodeRole._value2member_map_ else NodeRole(raw_role.lower())
        raw_source = data.get("source", ModalitySource.DOM.value)
        source = ModalitySource(raw_source) if raw_source in ModalitySource._value2member_map_ else ModalitySource(raw_source.lower())

        return cls(
            node_id=data["node_id"],
            role=role,
            bounds=BoundingBox.from_dict(data["bounds"]),
            label=data.get("label", ""),
            value=data.get("value", ""),
            is_clickable=bool(data.get("is_clickable", True)),
            is_editable=bool(data.get("is_editable", False)),
            is_focused=bool(data.get("is_focused", False)),
            is_enabled=bool(data.get("is_enabled", True)),
            parent_id=data.get("parent_id"),
            children_ids=list(data.get("children_ids", [])),
            source=source,
            confidence=float(data.get("confidence", 1.0)),
            attributes=data.get("attributes", {}),
        )


@dataclass(frozen=True)
class CanonicalUIGraph:
    """Complete snapshot of the UI state at timestamp t."""
    timestamp_ms: float
    nodes: Mapping[str, UIStateNode]
    focused_node_id: Optional[str] = None
    active_window_title: Optional[str] = None
    url: Optional[str] = None
    viewport_size: Tuple[int, int] = (1920, 1080)

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", freeze_evidence(dict(self.nodes)))

    def compute_state_hash(self) -> str:
        """SHA-256 fingerprint of structural topology, roles, labels, and bounds.

        Restricted scope by design: values, focus/enabled/clickable/editable
        flags, attributes, and relationships are intentionally excluded. Use
        compute_evidence_hash() when value/state changes must alter identity.
        """
        serialized = json.dumps(
            {
                "url": self.url,
                "window": self.active_window_title,
                "nodes": [
                    {
                        "id": n.node_id,
                        "role": n.role.value,
                        "label": n.label,
                        "bounds": [n.bounds.x1, n.bounds.y1, n.bounds.x2, n.bounds.y2],
                    }
                    for n in sorted(self.nodes.values(), key=lambda x: x.node_id)
                ],
            },
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def compute_evidence_hash(self) -> str:
        """SHA-256 identity over full node evidence: topology plus values, state
        flags, attributes, and parent/child relationships. Any observed
        interaction-relevant change alters this hash."""
        serialized = json.dumps(
            {
                "url": self.url,
                "window": self.active_window_title,
                "focused_node_id": self.focused_node_id,
                "nodes": [
                    {
                        "id": n.node_id,
                        "role": n.role.value,
                        "label": n.label,
                        "value": n.value,
                        "bounds": [n.bounds.x1, n.bounds.y1, n.bounds.x2, n.bounds.y2],
                        "is_clickable": n.is_clickable,
                        "is_editable": n.is_editable,
                        "is_focused": n.is_focused,
                        "is_enabled": n.is_enabled,
                        "parent_id": n.parent_id,
                        "children_ids": sorted(n.children_ids),
                        "source": n.source.value,
                        "attributes": thaw_evidence(n.attributes),
                    }
                    for n in sorted(self.nodes.values(), key=lambda x: x.node_id)
                ],
            },
            sort_keys=True,
            # Pinned explicitly (values equal the json defaults): the evidence
            # digest is Layer 1 of the UI-state hash spec; any drift here
            # silently re-keys all episode memory. See
            # docs/contract/ui-state-hash-spec.md.
            separators=(", ", ": "),
            ensure_ascii=True,
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "focused_node_id": self.focused_node_id,
            "active_window_title": self.active_window_title,
            "url": self.url,
            "viewport_size": list(self.viewport_size),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CanonicalUIGraph:
        nodes = {k: UIStateNode.from_dict(v) for k, v in data.get("nodes", {}).items()}
        viewport_data = data.get("viewport_size", [1920, 1080])
        viewport_size = (int(viewport_data[0]), int(viewport_data[1]))
        return cls(
            timestamp_ms=float(data.get("timestamp_ms", 0.0)),
            nodes=nodes,
            focused_node_id=data.get("focused_node_id"),
            active_window_title=data.get("active_window_title"),
            url=data.get("url"),
            viewport_size=viewport_size,
        )
