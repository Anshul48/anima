from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from reflex.schemas.actions import TypedAction
from reflex.schemas.identity import ActionIdentity


class ActionStatus(str, Enum):
    DISPATCHED = "dispatched"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ActionReceipt:
    """Proof of physical dispatch attempt emitted by an execution adapter."""
    lease_id: str
    action_id: str
    adapter_name: str
    dispatch_timestamp_ms: float
    duration_ms: float
    raw_adapter_response: Dict[str, Any] = field(default_factory=dict)
    status: ActionStatus = ActionStatus.DISPATCHED
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "action_id": self.action_id,
            "adapter_name": self.adapter_name,
            "dispatch_timestamp_ms": self.dispatch_timestamp_ms,
            "duration_ms": self.duration_ms,
            "raw_adapter_response": dict(self.raw_adapter_response),
            "status": self.status.value if isinstance(self.status, ActionStatus) else str(self.status),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ActionReceipt:
        raw_status = data.get("status", ActionStatus.DISPATCHED.value)
        status = ActionStatus(raw_status) if raw_status in ActionStatus._value2member_map_ else ActionStatus(raw_status.lower())
        return cls(
            lease_id=data["lease_id"],
            action_id=data["action_id"],
            adapter_name=data["adapter_name"],
            dispatch_timestamp_ms=float(data["dispatch_timestamp_ms"]),
            duration_ms=float(data["duration_ms"]),
            raw_adapter_response=data.get("raw_adapter_response", {}),
            status=status,
            error=data.get("error"),
        )


class ActionPort(ABC):
    """Abstract port for dispatching authorized actions to browser/OS adapters."""

    @abstractmethod
    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        """Dispatches an authorized physical action to the target adapter."""
        ...
