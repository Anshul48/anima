from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

class ContextPurpose(str, Enum):
    EVALUATION = "EVALUATION"
    SHADOW = "SHADOW"
    ASSISTED = "ASSISTED"

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

class EpistemicCategory(str, Enum):
    CONFIRMED = "CONFIRMED"
    HYPOTHESIS = "HYPOTHESIS"

class FactValidity(str, Enum):
    VALID = "VALID"
    REVOKED = "REVOKED"
    CORRECTED = "CORRECTED"

class FactVNext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    fact_id: str
    epistemic_category: EpistemicCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    validity: FactValidity
    provenance_ref: str
    text: Optional[str] = None
    value: Optional[Any] = None

class ContextSnapshotVNext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider: str = Field(default="entorhinal")
    contract_revision: str = Field(default="vNext")
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    granted_purpose: ContextPurpose
    granted_scopes: List[str]
    facts: List[FactVNext]

class ContextRequestVNext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    request_id: str
    consumer_identity: str
    purpose: ContextPurpose
    scopes: List[str] = Field(..., min_length=1)
    deadline_ms: int = Field(default=500)
    freshness_ms: int = Field(default=5000)
    budget_tokens: int = Field(default=10)

class ContextResultVNext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    status: ContextResultStatus
    payload: Optional[ContextSnapshotVNext] = None
    redacted_diagnostics: Dict[str, str] = Field(default_factory=dict)
