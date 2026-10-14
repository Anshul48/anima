from __future__ import annotations
from dataclasses import dataclass, field
import threading
from typing import Any, Dict, Optional

from reflex.ports.clock import ClockPort, SystemClock
from reflex.schemas.identity import ActionIdentity


class IdempotencyError(Exception):
    """Base exception for idempotency engine errors."""
    pass


class IdempotencyCollisionError(IdempotencyError):
    """Raised when an ActionIdentity or idempotency key collision is detected."""
    pass


class NonMonotonicStepError(IdempotencyError):
    """Raised when an action proposal violates monotonic step ordering within a session."""
    pass


class ActionExecutionLockedError(IdempotencyError):
    """Raised when an action identity has already received a physical execution dispatch attempt."""
    pass


@dataclass
class ActionRecord:
    """Ledger record tracking the lifecycle and execution count of an ActionIdentity."""
    identity: ActionIdentity
    state: str
    registered_at_ms: float
    dispatched_at_ms: Optional[float] = None
    terminal_at_ms: Optional[float] = None
    dispatch_count: int = 0
    result: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "state": self.state,
            "registered_at_ms": self.registered_at_ms,
            "dispatched_at_ms": self.dispatched_at_ms,
            "terminal_at_ms": self.terminal_at_ms,
            "dispatch_count": self.dispatch_count,
            "error": self.error,
        }


class IdempotencyRegistry:
    """In-memory transactional ledger enforcing monotonic step tracking and single-dispatch guarantees."""

    def __init__(self, clock: Optional[ClockPort] = None):
        self._clock: ClockPort = clock or SystemClock()
        self._records_by_action_id: Dict[str, ActionRecord] = {}
        self._action_id_by_key: Dict[str, str] = {}
        self._last_step_by_session: Dict[str, int] = {}
        self._lock = threading.RLock()

    def register_proposal(
        self,
        identity: ActionIdentity,
        initial_state: str = "proposal_received",
    ) -> ActionRecord:
        """Atomically registers an incoming ActionProposal.
        
        Enforces:
        1. Unique action_id
        2. Unique idempotency_key
        3. Monotonic step_index per session
        
        Raises:
            IdempotencyCollisionError: If action_id or idempotency_key has already been registered.
            NonMonotonicStepError: If step_index <= last seen step_index for the session.
        """
        with self._lock:
            # 1. Check action_id uniqueness
            if identity.action_id in self._records_by_action_id:
                raise IdempotencyCollisionError(
                    f"Action identity '{identity.action_id}' has already been registered."
                )

            # 2. Check idempotency_key uniqueness
            if identity.idempotency_key in self._action_id_by_key:
                existing_action_id = self._action_id_by_key[identity.idempotency_key]
                raise IdempotencyCollisionError(
                    f"Idempotency token collision for key '{identity.idempotency_key}' (already used by action '{existing_action_id}')."
                )

            # 3. Check monotonic step ordering
            session_id = identity.session_id
            if session_id in self._last_step_by_session:
                last_step = self._last_step_by_session[session_id]
                if identity.step_index <= last_step:
                    raise NonMonotonicStepError(
                        f"Non-monotonic step index {identity.step_index} for session '{session_id}' (last seen: {last_step}). Step index must strictly increase."
                    )

            # Atomic registration
            now_ms = self._clock.now_ms()
            record = ActionRecord(
                identity=identity,
                state=initial_state,
                registered_at_ms=now_ms,
                dispatch_count=0,
            )

            self._records_by_action_id[identity.action_id] = record
            self._action_id_by_key[identity.idempotency_key] = identity.action_id
            self._last_step_by_session[session_id] = identity.step_index

            return record

    def atomic_begin_dispatch(self, action_id: str) -> bool:
        """Atomically locks and verifies that at most one physical dispatch attempt occurs.
        
        Raises:
            IdempotencyError: If action_id was never registered.
            ActionExecutionLockedError: If dispatch attempt count >= 1.
        """
        with self._lock:
            if action_id not in self._records_by_action_id:
                raise IdempotencyError(f"Action '{action_id}' was not registered in idempotency ledger.")

            record = self._records_by_action_id[action_id]
            if record.dispatch_count >= 1:
                raise ActionExecutionLockedError(
                    f"Action '{action_id}' already has {record.dispatch_count} physical dispatch attempt(s). At-most-one dispatch invariant violated."
                )

            # Atomic increment
            record.dispatch_count += 1
            record.dispatched_at_ms = self._clock.now_ms()
            record.state = "in_flight"
            return True

    def update_state(
        self,
        action_id: str,
        new_state: str,
        expected_state: Optional[str] = None,
    ) -> bool:
        """Performs atomic Compare-And-Swap (CAS) state update for an action."""
        with self._lock:
            if action_id not in self._records_by_action_id:
                return False

            record = self._records_by_action_id[action_id]
            if expected_state is not None and record.state != expected_state:
                return False

            record.state = new_state
            return True

    def record_terminal_result(
        self,
        action_id: str,
        terminal_state: str,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        """Transitions action to a terminal state and persists execution results."""
        with self._lock:
            if action_id in self._records_by_action_id:
                record = self._records_by_action_id[action_id]
                record.state = terminal_state
                record.terminal_at_ms = self._clock.now_ms()
                record.result = result
                record.error = error

    def get_record(self, action_id: str) -> Optional[ActionRecord]:
        """Retrieves action ledger record by action_id."""
        with self._lock:
            return self._records_by_action_id.get(action_id)

    def get_record_by_key(self, idempotency_key: str) -> Optional[ActionRecord]:
        """Retrieves action ledger record by idempotency_key."""
        with self._lock:
            action_id = self._action_id_by_key.get(idempotency_key)
            if action_id:
                return self._records_by_action_id.get(action_id)
            return None

    def has_action_id(self, action_id: str) -> bool:
        with self._lock:
            return action_id in self._records_by_action_id

    def has_idempotency_key(self, idempotency_key: str) -> bool:
        with self._lock:
            return idempotency_key in self._action_id_by_key

    def get_last_step_index(self, session_id: str) -> Optional[int]:
        with self._lock:
            return self._last_step_by_session.get(session_id)

    def get_dispatch_count(self, action_id: str) -> int:
        with self._lock:
            record = self._records_by_action_id.get(action_id)
            return record.dispatch_count if record else 0

    def clear(self) -> None:
        """Clears all records in the registry."""
        with self._lock:
            self._records_by_action_id.clear()
            self._action_id_by_key.clear()
            self._last_step_by_session.clear()
