"""Base interfaces, data structures, and configuration for native OS action execution adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from reflex.host.identity.lease_manager import (
    ActionLease,
    ActionLeaseManager,
    InvalidLeaseError,
)
from reflex.ports.action import ActionPort, ActionReceipt, ActionStatus
from reflex.schemas.actions import ActionType, NormalizedCoords, TypedAction
from reflex.schemas.identity import ActionIdentity


@dataclass(frozen=True)
class NativeActionConfig:
    """Configuration options for native desktop OS action execution adapters."""
    mouse_move_duration_s: float = 0.0
    inter_key_delay_s: float = 0.01
    lease_ttl_ms: float = 5000.0
    screen_width: int = 1920
    screen_height: int = 1080
    enable_mock_fallback: bool = True
    use_direct_patterns: bool = True
    drag_interpolation_steps: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mouse_move_duration_s": self.mouse_move_duration_s,
            "inter_key_delay_s": self.inter_key_delay_s,
            "lease_ttl_ms": self.lease_ttl_ms,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "enable_mock_fallback": self.enable_mock_fallback,
            "use_direct_patterns": self.use_direct_patterns,
            "drag_interpolation_steps": self.drag_interpolation_steps,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NativeActionConfig:
        return cls(
            mouse_move_duration_s=float(data.get("mouse_move_duration_s", 0.0)),
            inter_key_delay_s=float(data.get("inter_key_delay_s", 0.01)),
            lease_ttl_ms=float(data.get("lease_ttl_ms", 5000.0)),
            screen_width=int(data.get("screen_width", 1920)),
            screen_height=int(data.get("screen_height", 1080)),
            enable_mock_fallback=bool(data.get("enable_mock_fallback", True)),
            use_direct_patterns=bool(data.get("use_direct_patterns", True)),
            drag_interpolation_steps=int(data.get("drag_interpolation_steps", 10)),
        )


class NativeActionPort(ActionPort, ABC):
    """Abstract port for executing native OS actions under the authority of an ActionLease."""

    def __init__(
        self,
        config: Optional[NativeActionConfig] = None,
        lease_manager: Optional[ActionLeaseManager] = None,
        clock: Optional[ClockPort] = None,
    ) -> None:
        self.config = config or NativeActionConfig()
        self.lease_manager = lease_manager
        from reflex.ports.clock import SystemClock
        self.clock = clock or (getattr(lease_manager, "clock", None) or SystemClock())
        self._consumed_leases: Set[str] = set()
        self._dispatched_identities: Set[str] = set()

    def to_pixel_coords(self, coords: Optional[NormalizedCoords]) -> Tuple[int, int]:
        """Converts normalized [0.0, 1.0] coordinates to screen pixel space."""
        if coords is None:
            raise ValueError("Coordinates are required for native physical input")
        return coords.to_pixel(self.config.screen_width, self.config.screen_height)

    def _validate_and_consume_lease(self, lease: Optional[ActionLease], action: TypedAction) -> None:
        if self.lease_manager is None:
            raise InvalidLeaseError("Execution requires its issuing ActionLeaseManager")
        self.lease_manager.consume_lease(lease, action=action)

    @abstractmethod
    async def perform_native_action(self, action: TypedAction, lease: ActionLease) -> bool:
        """Dispatches action via platform accessibility pattern or synthetic input."""
        ...

    @abstractmethod
    async def execute_action(self, action: TypedAction, lease: ActionLease) -> ActionReceipt:
        """Executes the action under the authority of an active lease, returning an ActionReceipt."""
        ...

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        """Dispatch only a registered, kernel-issued action; never mint authority."""
        manager = getattr(self, "lease_manager", None)
        if manager is None:
            raise InvalidLeaseError("Dispatch requires its issuing ActionLeaseManager")
        lease = manager.get_lease_by_action_id(identity.action_id)
        if lease is None or lease.identity != identity:
            raise InvalidLeaseError("No issued lease matches the dispatch identity")
        receipt = await self.execute_action(action=action, lease=lease)
        return receipt.to_dict()
