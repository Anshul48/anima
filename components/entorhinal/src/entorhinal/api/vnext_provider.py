import logging
import time
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
import uuid

from entorhinal.schemas.vnext import (
    ContextRequestVNext, ContextResultVNext, ContextSnapshotVNext, 
    ContextResultStatus, ContextPurpose, FactVNext, EpistemicCategory, FactValidity
)
from entorhinal.schemas.models import ContextRequest as V1Request, ContextSnapshot as V1Snapshot, DerivedFact
from entorhinal.query.service import ContextSnapshotService, PermissionDeniedError

logger = logging.getLogger(__name__)

class VNextProvider:
    def __init__(self, service: ContextSnapshotService):
        self.service = service
        
    async def handle_request(self, request: ContextRequestVNext, client_pid: Optional[int]) -> ContextResultVNext:
        if not request.scopes:
            return ContextResultVNext(status=ContextResultStatus.MALFORMED, redacted_diagnostics={"reason": "empty_scopes"})
            
        if request.budget_tokens <= 0:
            return ContextResultVNext(status=ContextResultStatus.MALFORMED, redacted_diagnostics={"reason": "invalid_budget"})

        try:
            v1_req = V1Request(
                consumer_id=request.consumer_identity,
                stated_purpose=request.purpose.value,
                requested_scopes=request.scopes,
            )
            
            try:
                v1_snap = await self.service.request_snapshot(v1_req)
            except PermissionDeniedError:
                return ContextResultVNext(status=ContextResultStatus.DENIED, redacted_diagnostics={"reason": "policy_denial"})
            
            if not v1_snap.active_facts:
                return ContextResultVNext(status=ContextResultStatus.NO_CONTEXT, redacted_diagnostics={"reason": "scope_not_found"})
                
            vnext_facts = []
            for f in v1_snap.active_facts:
                vnext_facts.append(
                    FactVNext(
                        fact_id=f.fact_id,
                        epistemic_category=EpistemicCategory.CONFIRMED,
                        confidence=f.confidence,
                        validity=FactValidity.VALID,
                        provenance_ref=f.supporting_evidence_ids[0] if f.supporting_evidence_ids else "unknown",
                        text=f.value if isinstance(f.value, str) else str(f.value)
                    )
                )
            
            vnext_snap = ContextSnapshotVNext(
                snapshot_id=v1_snap.snapshot_id,
                provider="entorhinal",
                contract_revision="vNext",
                issued_at=v1_snap.issued_at,
                expires_at=v1_snap.expires_at,
                granted_purpose=request.purpose,
                granted_scopes=v1_snap.scope_granted,
                facts=vnext_facts
            )
            
            return ContextResultVNext(status=ContextResultStatus.AVAILABLE, payload=vnext_snap)
            
        except Exception as e:
            logger.error(f"Provider error: {e}")
            return ContextResultVNext(status=ContextResultStatus.UNAVAILABLE, redacted_diagnostics={"reason": "internal_error"})
