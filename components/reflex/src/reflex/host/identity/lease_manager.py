from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Any, Dict, Optional, Set

from reflex.ports.clock import ClockPort, SystemClock
from reflex.schemas.actions import TypedAction
from reflex.schemas.identity import ActionIdentity


class LeaseStatus(str, Enum):
    ISSUED = "issued"
    ACQUIRED = "acquired"
    REVOKED = "revoked"
    EXPIRED = "expired"
    RETIRED = "retired"


class LeaseError(Exception):
    """Base exception for lease operations."""
    pass


class InvalidLeaseError(LeaseError):
    """Raised when an ActionLease is invalid, tampered, expired, revoked, or already consumed."""
    pass


LeaseInvalidError = InvalidLeaseError


class LeaseNotFoundError(InvalidLeaseError):
    """Raised when the requested lease ID does not exist."""
    pass


class LeaseExpiredError(InvalidLeaseError):
    """Raised when an operation is attempted on an expired lease."""
    pass


class LeaseRevokedError(InvalidLeaseError):
    """Raised when an operation is attempted on a revoked lease."""
    pass


class LeaseAlreadyAcquiredError(InvalidLeaseError):
    """Raised when an acquisition is attempted on an already-acquired lease (single-use violated)."""
    pass


@dataclass(frozen=True)
class ActionLease:
    """Cryptographic single-use token granting immediate dispatch authority."""
    lease_id: str
    identity: ActionIdentity
    action: TypedAction
    expires_at_ms: float
    token: str = ""
    created_at_ms: float = 0.0
    granted_at_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, current_time_ms: float) -> bool:
        """Determines if the lease has expired relative to current_time_ms."""
        return current_time_ms >= self.expires_at_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "identity": self.identity.to_dict(),
            "action": self.action.to_dict(),
            "expires_at_ms": self.expires_at_ms,
            "token": self.token,
            "created_at_ms": self.created_at_ms,
            "granted_at_ms": self.granted_at_ms or self.created_at_ms,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ActionLease:
        created_at_ms = float(data.get("created_at_ms", data.get("granted_at_ms", 0.0)))
        granted_at_ms = float(data.get("granted_at_ms", created_at_ms))
        return cls(
            lease_id=data["lease_id"],
            identity=ActionIdentity.from_dict(data["identity"]),
            action=TypedAction.from_dict(data["action"]),
            expires_at_ms=float(data["expires_at_ms"]),
            token=data.get("token", ""),
            created_at_ms=created_at_ms,
            granted_at_ms=granted_at_ms,
            metadata=data.get("metadata", {}),
        )


class ActionLeaseManager:
    """Manages generation, single-use dispatch acquisition, and revocation of ActionLeases."""

    def __init__(
        self,
        clock: Optional[ClockPort] = None,
        default_ttl_ms: float = 5000.0,
        secret_key: Optional[str] = None,
    ):
        self._clock: ClockPort = clock or SystemClock()
        self._default_ttl_ms = default_ttl_ms
        self._secret_key = secret_key.encode("utf-8") if secret_key is not None else secrets.token_bytes(32)
        self._leases: Dict[str, ActionLease] = {}
        self._authority_bindings: Dict[str, bytes] = {}
        self._action_to_lease: Dict[str, str] = {}
        self._acquired: Set[str] = set()
        self._revoked: Dict[str, str] = {}
        self._retired: Set[str] = set()
        self._lock = threading.RLock()

    @staticmethod
    def _authority_payload(
        identity: ActionIdentity,
        action: TypedAction,
        created_at_ms: float,
        expires_at_ms: float,
    ) -> bytes:
        text = action.text_payload
        val = action.value
        if text is not None and val is not None and text != val:
            # Native adapters consume `text_payload or value or metadata...` while
            # TypedAction.to_dict() signs only text_payload: a divergent pair lets
            # approval see one string and execution use another. Fail closed.
            raise InvalidLeaseError(
                "Action authority payload is ambiguous (text_payload != value)"
            )
        try:
            action_dict = action.to_dict()
            action_dict["value"] = val
            return json.dumps(
                {"identity": identity.to_dict(), "action": action_dict,
                 "created_at_ms": created_at_ms, "expires_at_ms": expires_at_ms},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise InvalidLeaseError("Action authority payload is not finite JSON") from exc

    def compute_token(
        self,
        identity: ActionIdentity,
        action: TypedAction,
        created_at_ms: float,
        expires_at_ms: float,
    ) -> str:
        payload = self._authority_payload(identity, action, created_at_ms, expires_at_ms)
        return hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()

    def issue_lease(
        self,
        identity: ActionIdentity,
        action: TypedAction,
        ttl_ms: Optional[float] = None,
        current_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ActionLease:
        """Generates a cryptographic single-use ActionLease bound to an ActionIdentity."""
        with self._lock:
            now_ms = current_time_ms if current_time_ms is not None else self._clock.now_ms()
            ttl = ttl_ms if ttl_ms is not None else self._default_ttl_ms
            expires_at_ms = now_ms + ttl

            if identity.action_id in self._action_to_lease:
                raise InvalidLeaseError("ActionIdentity already has an issued lease")
            token = self.compute_token(identity, action, now_ms, expires_at_ms)
            lease_id = f"lease_{token[:16]}"

            lease = ActionLease(
                lease_id=lease_id,
                identity=identity,
                action=action,
                expires_at_ms=expires_at_ms,
                token=token,
                created_at_ms=now_ms,
                granted_at_ms=now_ms,
                metadata=dict(metadata or {}),
            )

            self._leases[lease_id] = lease
            self._authority_bindings[lease_id] = self._authority_payload(
                identity, action, now_ms, expires_at_ms
            )
            self._action_to_lease[identity.action_id] = lease_id
            return lease

    def validate_lease(
        self,
        lease: Optional[ActionLease],
        action: Optional[TypedAction] = None,
        current_time_ms: Optional[float] = None,
    ) -> None:
        """Reject unknown, altered, expired, revoked, retired or consumed authority."""
        with self._lock:
            if lease is None:
                raise InvalidLeaseError("ActionLease is required")
            registered = self._leases.get(lease.lease_id)
            if registered is None:
                raise InvalidLeaseError("ActionLease was not issued by this authority")
            if not lease.token or not hmac.compare_digest(registered.token, lease.token):
                raise InvalidLeaseError("ActionLease token is missing or not registered")
            payload = self._authority_payload(
                lease.identity, lease.action, lease.created_at_ms, lease.expires_at_ms
            )
            if payload != self._authority_bindings.get(lease.lease_id):
                raise InvalidLeaseError("ActionLease differs from its issued authority")
            expected = self.compute_token(
                lease.identity, lease.action, lease.created_at_ms, lease.expires_at_ms
            )
            if not hmac.compare_digest(expected, lease.token):
                raise InvalidLeaseError("ActionLease signature verification failed")
            now_ms = current_time_ms if current_time_ms is not None else self._clock.now_ms()
            if lease.is_expired(now_ms):
                raise InvalidLeaseError("ActionLease has expired")
            if lease.lease_id in self._revoked:
                raise InvalidLeaseError("ActionLease has been revoked")
            if lease.lease_id in self._retired:
                raise InvalidLeaseError("ActionLease has been retired")
            if lease.lease_id in self._acquired:
                raise InvalidLeaseError("ActionLease has already been consumed")
            if action is not None:
                dispatched = self._authority_payload(
                    lease.identity, action, lease.created_at_ms, lease.expires_at_ms
                )
                if dispatched != payload:
                    raise InvalidLeaseError("Dispatched action differs from authorized action")

    def consume_lease(
        self,
        lease: ActionLease,
        action: Optional[TypedAction] = None,
        current_time_ms: Optional[float] = None,
    ) -> None:
        """Validates and atomically consumes a lease for physical dispatch."""
        with self._lock:
            self.validate_lease(lease, action=action, current_time_ms=current_time_ms)
            self._acquired.add(lease.lease_id)

    def acquire_lease(
        self,
        lease_id: str,
        current_time_ms: Optional[float] = None,
    ) -> ActionLease:
        """Atomically acquires a single-use lease for physical dispatch.
        
        Raises:
            LeaseNotFoundError: If lease_id is unknown.
            LeaseRevokedError: If lease has been revoked.
            LeaseAlreadyAcquiredError: If lease has already been acquired.
            LeaseExpiredError: If lease expiration timestamp has passed.
        """
        with self._lock:
            if lease_id not in self._leases:
                raise LeaseNotFoundError(f"Lease '{lease_id}' not found.")

            if lease_id in self._revoked:
                reason = self._revoked[lease_id]
                raise LeaseRevokedError(f"Lease '{lease_id}' has been revoked: {reason}")

            if lease_id in self._acquired:
                raise LeaseAlreadyAcquiredError(
                    f"Lease '{lease_id}' has already been acquired for physical execution."
                )

            lease = self._leases[lease_id]
            now_ms = current_time_ms if current_time_ms is not None else self._clock.now_ms()

            if lease.is_expired(now_ms):
                raise LeaseExpiredError(
                    f"Lease '{lease_id}' expired at {lease.expires_at_ms:.3f} (current time {now_ms:.3f})."
                )

            # Atomic acquisition mark
            self._acquired.add(lease_id)
            return lease

    def revoke_lease(self, lease_id: str, reason: str = "Explicit revocation") -> bool:
        """Revokes an active lease, invalidating dispatch authority."""
        with self._lock:
            if lease_id not in self._leases:
                return False
            self._revoked[lease_id] = reason
            return True

    def revoke_all_leases(self, reason: str = "Emergency halt / mass revocation") -> int:
        """Revokes all known leases."""
        with self._lock:
            count = 0
            for lease_id in self._leases:
                if lease_id not in self._revoked:
                    self._revoked[lease_id] = reason
                    count += 1
            return count

    def retire_lease(self, lease_id: str) -> None:
        """Marks a lease as retired after successful execution and verification."""
        with self._lock:
            if lease_id in self._leases:
                self._retired.add(lease_id)

    def get_lease(self, lease_id: str) -> Optional[ActionLease]:
        """Retrieves lease by lease_id if present."""
        with self._lock:
            return self._leases.get(lease_id)

    def get_lease_by_action_id(self, action_id: str) -> Optional[ActionLease]:
        """Retrieves lease by associated action_id."""
        with self._lock:
            lease_id = self._action_to_lease.get(action_id)
            if lease_id:
                return self._leases.get(lease_id)
            return None

    def get_lease_status(
        self,
        lease_id: str,
        current_time_ms: Optional[float] = None,
    ) -> LeaseStatus:
        """Evaluates the current lifecycle status of a lease."""
        with self._lock:
            if lease_id not in self._leases:
                raise LeaseNotFoundError(f"Lease '{lease_id}' not found.")

            if lease_id in self._revoked:
                return LeaseStatus.REVOKED
            if lease_id in self._retired:
                return LeaseStatus.RETIRED

            now_ms = current_time_ms if current_time_ms is not None else self._clock.now_ms()
            lease = self._leases[lease_id]
            if lease.is_expired(now_ms):
                return LeaseStatus.EXPIRED

            if lease_id in self._acquired:
                return LeaseStatus.ACQUIRED

            return LeaseStatus.ISSUED

    def is_lease_valid(
        self,
        lease_id: str,
        current_time_ms: Optional[float] = None,
    ) -> bool:
        """Checks if a lease exists, is unrevoked, unexpired, and not retired."""
        with self._lock:
            if lease_id not in self._leases:
                return False
            if lease_id in self._revoked or lease_id in self._retired:
                return False
            now_ms = current_time_ms if current_time_ms is not None else self._clock.now_ms()
            return not self._leases[lease_id].is_expired(now_ms)

    def active_lease_count(self) -> int:
        """Returns the number of active, unretired, unrevoked leases."""
        with self._lock:
            now_ms = self._clock.now_ms()
            return sum(
                1
                for lid, lease in self._leases.items()
                if lid not in self._revoked
                and lid not in self._retired
                and not lease.is_expired(now_ms)
            )

    def clear(self) -> None:
        """Clears all in-memory lease tracking."""
        with self._lock:
            self._leases.clear()
            self._authority_bindings.clear()
            self._action_to_lease.clear()
            self._acquired.clear()
            self._revoked.clear()
            self._retired.clear()
