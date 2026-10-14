from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

class ContextProviderError(Exception):
    pass

ContextError = ContextProviderError

class ContextUnavailableError(ContextProviderError):
    pass

class ContextPermissionDeniedError(ContextProviderError):
    pass

class ContextTimeoutError(ContextProviderError):
    pass

class ContextMalformedError(ContextProviderError):
    pass

class ContextResultStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    NO_CONTEXT = "NO_CONTEXT"
    DENIED = "DENIED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    REVOKED = "REVOKED"
    MALFORMED = "MALFORMED"
    OVERSIZE = "OVERSIZE"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"

class Purpose(str, Enum):
    EVALUATION = "EVALUATION"
    SHADOW = "SHADOW"
    ASSISTED = "ASSISTED"

@dataclass(frozen=True)
class ContextRequest:
    request_id: str
    consumer_identity: str
    purpose: Purpose
    scopes: List[str]
    deadline_ms: int
    freshness_ms: int
    budget_tokens: int

@dataclass(frozen=True)
class Fact:
    fact_id: str
    epistemic_category: str
    confidence: float
    validity: str
    provenance_ref: str
    text: str = ""

@dataclass(frozen=True)
class ContextSnapshot:
    snapshot_id: str
    provider: str
    contract_revision: str
    issued_at: str
    expires_at: str
    granted_purpose: str
    granted_scopes: List[str]
    facts: List[Fact]

@dataclass(frozen=True)
class ContextResult:
    status: ContextResultStatus
    payload: Optional[ContextSnapshot]
    redacted_diagnostics: Dict[str, str]

class ContextProvider(ABC):
    @abstractmethod
    async def get_context(self, request: ContextRequest) -> ContextResult:
        ...
