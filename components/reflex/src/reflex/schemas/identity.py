from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import time
from typing import Any, Dict, Optional, Set
import uuid

from reflex.schemas.actions import TypedAction
from reflex.schemas.delta import StateDelta
from reflex.schemas.policy import CapabilityScope


@dataclass(frozen=True)
class ActionIdentity:
    """Globally unique, immutable identity for a single physical action attempt."""
    action_id: str
    session_id: str
    step_index: int
    idempotency_key: str
    created_at_ms: float
    nonce: str = ""
    episode_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        session_id: str,
        step_index: int,
        nonce: Optional[str] = None,
        created_at_ms: Optional[float] = None,
        episode_id: Optional[str] = None,
    ) -> ActionIdentity:
        """Constructs a collision-free ActionIdentity using SHA-256 idempotency key hashing."""
        if nonce is None:
            nonce = uuid.uuid4().hex[:16]
        if created_at_ms is None:
            created_at_ms = time.time() * 1000.0

        raw_token = f"{session_id}:{step_index}:{nonce}:{created_at_ms:.3f}"
        idempotency_key = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        action_id = f"act_{idempotency_key[:16]}"

        return cls(
            action_id=action_id,
            session_id=session_id,
            step_index=step_index,
            idempotency_key=idempotency_key,
            created_at_ms=created_at_ms,
            nonce=nonce,
            episode_id=episode_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "action_id": self.action_id,
            "session_id": self.session_id,
            "step_index": self.step_index,
            "idempotency_key": self.idempotency_key,
            "created_at_ms": self.created_at_ms,
            "nonce": self.nonce,
        }
        if self.episode_id is not None:
            res["episode_id"] = self.episode_id
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ActionIdentity:
        return cls(
            action_id=data["action_id"],
            session_id=data["session_id"],
            step_index=int(data["step_index"]),
            idempotency_key=data["idempotency_key"],
            created_at_ms=float(data["created_at_ms"]),
            nonce=data.get("nonce", ""),
            episode_id=data.get("episode_id"),
        )


@dataclass(frozen=True)
class ActionProposal:
    """Action proposal emitted by Planner or Skill before host authorization."""
    identity: ActionIdentity
    action: TypedAction
    expected_delta: Optional[StateDelta] = None
    required_scopes: Set[CapabilityScope] = field(default_factory=set)
    reasoning_summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "action": self.action.to_dict(),
            "expected_delta": self.expected_delta.to_dict() if self.expected_delta else None,
            "required_scopes": [
                s.value if isinstance(s, CapabilityScope) else str(s)
                for s in sorted(self.required_scopes, key=lambda x: str(x))
            ],
            "reasoning_summary": self.reasoning_summary,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ActionProposal:
        identity = ActionIdentity.from_dict(data["identity"])
        action = TypedAction.from_dict(data["action"])
        expected_delta = (
            StateDelta.from_dict(data["expected_delta"])
            if data.get("expected_delta") is not None
            else None
        )
        required_scopes = {
            CapabilityScope(s) if s in CapabilityScope._value2member_map_ else CapabilityScope(s.lower())
            for s in data.get("required_scopes", [])
        }
        return cls(
            identity=identity,
            action=action,
            expected_delta=expected_delta,
            required_scopes=required_scopes,
            reasoning_summary=data.get("reasoning_summary", ""),
            metadata=data.get("metadata", {}),
        )
