from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from reflex.schemas.actions import SafetyClass


class CapabilityScope(str, Enum):
    BROWSER_READ = "browser:read"
    BROWSER_INTERACT = "browser:interact"
    BROWSER_NAVIGATE = "browser:navigate"
    BROWSER_DOWNLOAD = "browser:download"
    OS_INPUT_INJECT = "os:input:inject"
    FS_READ = "fs:read"
    FS_WRITE = "fs:write"
    CLIPBOARD_READ = "clipboard:read"
    CLIPBOARD_WRITE = "clipboard:write"


@dataclass(frozen=True)
class CapabilityGrant:
    """Explicit grant of a capability scope with optional expiration and constraints."""
    scope: CapabilityScope
    granted_at_ms: float = 0.0
    expires_at_ms: Optional[float] = None
    requires_user_confirmation: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, current_time_ms: float) -> bool:
        """Checks if this grant has expired relative to current_time_ms."""
        if self.expires_at_ms is None:
            return False
        return current_time_ms > self.expires_at_ms

    def is_valid(self, current_time_ms: float) -> bool:
        """Checks if this grant is currently valid (not expired)."""
        return not self.is_expired(current_time_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope.value if isinstance(self.scope, CapabilityScope) else str(self.scope),
            "granted_at_ms": self.granted_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "requires_user_confirmation": self.requires_user_confirmation,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CapabilityGrant:
        raw_scope = data["scope"]
        scope = CapabilityScope(raw_scope) if raw_scope in CapabilityScope._value2member_map_ else CapabilityScope(raw_scope.lower())
        return cls(
            scope=scope,
            granted_at_ms=float(data.get("granted_at_ms", 0.0)),
            expires_at_ms=float(data["expires_at_ms"]) if data.get("expires_at_ms") is not None else None,
            requires_user_confirmation=bool(data.get("requires_user_confirmation", False)),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class CapabilityPolicy:
    """Security rules governing permitted actions and required confirmation gates."""
    granted_scopes: Set[CapabilityScope] = field(default_factory=set)
    disallowed_domains: List[str] = field(default_factory=list)
    require_human_confirmation_for: Set[SafetyClass] = field(
        default_factory=lambda: {SafetyClass.DESTRUCTIVE, SafetyClass.AMBIGUOUS}
    )
    max_actions_per_session: int = 500
    grants: List[CapabilityGrant] = field(default_factory=list)

    @classmethod
    def default_browser_policy(cls) -> CapabilityPolicy:
        """Safe default policy for browser automation."""
        return cls(
            granted_scopes={
                CapabilityScope.BROWSER_READ,
                CapabilityScope.BROWSER_INTERACT,
                CapabilityScope.BROWSER_NAVIGATE,
            },
            disallowed_domains=[
                "banking.example.com",
                "*.internal",
                "169.254.169.254",
            ],
            require_human_confirmation_for={
                SafetyClass.DESTRUCTIVE,
                SafetyClass.AMBIGUOUS,
            },
            max_actions_per_session=500,
        )

    @classmethod
    def permissive_policy(cls) -> CapabilityPolicy:
        """Permissive policy for test environments and unconstrained local runners."""
        return cls(
            granted_scopes=set(CapabilityScope),
            disallowed_domains=[],
            require_human_confirmation_for=set(),
            max_actions_per_session=10000,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "granted_scopes": [s.value if isinstance(s, CapabilityScope) else str(s) for s in sorted(self.granted_scopes, key=lambda x: str(x))],
            "disallowed_domains": list(self.disallowed_domains),
            "require_human_confirmation_for": [sc.value if isinstance(sc, SafetyClass) else str(sc) for sc in sorted(self.require_human_confirmation_for, key=lambda x: str(x))],
            "max_actions_per_session": self.max_actions_per_session,
            "grants": [g.to_dict() for g in self.grants],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CapabilityPolicy:
        scopes = {
            CapabilityScope(s) if s in CapabilityScope._value2member_map_ else CapabilityScope(s.lower())
            for s in data.get("granted_scopes", [])
        }
        safety_classes = {
            SafetyClass(sc) if sc in SafetyClass._value2member_map_ else SafetyClass(sc.lower())
            for sc in data.get("require_human_confirmation_for", [])
        }
        grants = [CapabilityGrant.from_dict(g) for g in data.get("grants", [])]

        return cls(
            granted_scopes=scopes,
            disallowed_domains=list(data.get("disallowed_domains", [])),
            require_human_confirmation_for=safety_classes,
            max_actions_per_session=int(data.get("max_actions_per_session", 500)),
            grants=grants,
        )
