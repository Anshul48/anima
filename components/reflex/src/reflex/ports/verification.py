from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, List, Optional
from reflex.schemas.actions import TypedAction
from reflex.schemas.state import CanonicalUIGraph
from reflex.schemas.delta import StateDelta


class VerificationPort(ABC):
    """Abstract port for independent post-action assertion checking and verification."""

    @abstractmethod
    async def verify_transition(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
        after_state: CanonicalUIGraph,
        expected_delta: Optional[StateDelta] = None,
    ) -> StateDelta:
        """Independently evaluates whether the action achieved the expected state transition."""
        ...


class VerificationEnginePort(VerificationPort, ABC):
    """Abstract port combining transition verification with live settlement and reconciliation."""

    @abstractmethod
    async def verify_action(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
        expected_delta: Optional[StateDelta] = None,
        custom_assertions: Optional[List[Any]] = None,
    ) -> Any:
        """Awaits settlement and verifies action outcome."""
        ...

    @abstractmethod
    async def reconcile_state(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
    ) -> Any:
        """Performs non-destructive diagnostic probes to reconcile state."""
        ...

