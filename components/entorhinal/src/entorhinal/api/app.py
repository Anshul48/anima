"""FastAPI Local REST and WebSocket Server for Entorhinal.

Exposes local loopback (127.0.0.1) IPC endpoints:
- POST /api/v1/context/request -> Returns advisory ContextSnapshot (403 on ungranted scopes).
- POST /api/v1/context/packet -> Returns purpose-bound temporal ResumptionPacket (cutoff).
- GET  /api/v1/context/explain/{fact_id} -> Returns FactExplanation with complete provenance path.
- GET  /api/v1/context/focus -> Returns ImmediateFocusState (<5ms).
- GET  /api/v1/context/timeline -> Returns recent journal evidence timeline.
- GET  /api/v1/context/graph -> Returns semantic entity graph and active facts.
- GET  /api/v1/health -> Minimal liveness publicly; full detail with credentials.
- GET  /ui -> Serves local Trust & Privacy Dashboard (static shell; data via protected routes).
- User Governance endpoints (admin role):
  - GET/POST   /api/v1/user/corrections
  - POST       /api/v1/user/forget
  - GET/POST   /api/v1/user/grants
  - DELETE     /api/v1/user/grants/{rule_id}
  - GET        /api/v1/user/audit
  - GET        /api/v1/user/export
- Admin principal management (admin role):
  - GET/POST   /api/v1/admin/principals
  - POST       /api/v1/admin/principals/{principal_id}/revoke
- WS   /ws/v1/context/focus -> Real-time streaming WebSocket for focus state transitions.

Invariants:
- Loopback only (127.0.0.1 / ::1 / localhost).
- Sub-15ms response latency.
- Fail-closed permission checking on all context queries.
- Runtime serving path (create_app(runtime=...)) authenticates EVERY
  disclosure/governance route: no anonymous access, no bypass knob.
- Legacy constructor (no runtime) preserves exact unauthenticated behavior
  for unit tests; pass auth_store + require_auth=True to enforce there too.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from entorhinal.api.trust_ui import DASHBOARD_HTML, get_trust_ui_html
from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.ingest.pipeline import IngestionPipeline
from entorhinal.policy.engine import (
    BudgetExceededError,
    ConsumerPermission,
    PolicyEngine,
)
from entorhinal.projections.compiler import MultiTimescaleCompiler
from entorhinal.projections.models import ImmediateFocusState
from entorhinal.query.explanations import ExplanationEngine
from entorhinal.query.packets import (
    PacketAccessDenied,
    TemporalPacketService,
    UnknownTaskError,
)
from entorhinal.query.service import ContextSnapshotService, PermissionDeniedError
from entorhinal.runtime.auth import (
    ROLE_ADMIN,
    ROLE_READER,
    ROLE_SOURCE,
    AuthStore,
    extract_bearer,
)
from entorhinal.schemas.models import (
    CLUSTER_ID_ALGORITHM,
    EDGE_ID_ALGORITHM,
    FACT_ID_ALGORITHM,
    SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE,
    ContextRequest,
    ContextSnapshot,
    CorrectionAction,
    DerivedFact,
    EvidenceRecord,
    FactExplanation,
    SourceType,
    fact_matches_scope,
    generate_uuidv7,
    scope_class,
)
from entorhinal.schemas.observation import ObservationIngestResult, PerceptionObservationEvent
from entorhinal.temporal.packet import PacketRequest, ResumptionPacket
from entorhinal.user_control.service import UserControlService

logger = logging.getLogger(__name__)

READ_ROLES = (ROLE_READER, ROLE_ADMIN)
WRITE_SOURCE_ROLES = (ROLE_SOURCE, ROLE_ADMIN)
ADMIN_ROLES = (ROLE_ADMIN,)
TIMELINE_LIMIT_MAX = 500


def _sync_consumer_permissions(policy: PolicyEngine, auth_store: AuthStore) -> None:
    """Make the AuthStore's persisted reader/admin grants authoritative.

    The in-memory policy permission table is rebuilt from persisted grants
    (source principals are ingest-only and never query). Called at startup
    and after every principal mutation.
    """
    for consumer_id in list(policy.consumer_permissions.keys()):
        policy.remove_consumer_permission(consumer_id)
    for principal in auth_store.list_principals():
        if principal.disabled or principal.role == ROLE_SOURCE:
            continue
        policy.register_consumer_permission(
            ConsumerPermission(
                consumer_id=principal.principal_id,
                allowed_purposes=list(principal.allowed_purposes),
                allowed_scopes=list(principal.allowed_scopes),
                max_budget=principal.max_budget,
            )
        )


def create_app(
    service: Optional[ContextSnapshotService] = None,
    compiler: Optional[MultiTimescaleCompiler] = None,
    policy_engine: Optional[PolicyEngine] = None,
    journal: Optional[EvidenceJournal] = None,
    user_control: Optional[UserControlService] = None,
    pipeline: Optional[IngestionPipeline] = None,
    runtime: Optional[Any] = None,
    auth_store: Optional[AuthStore] = None,
    require_auth: Optional[bool] = None,
) -> FastAPI:
    """Application factory initializing FastAPI router and dependency injection.

    When ``runtime`` (built by ``entorhinal.runtime.factory.build_runtime``)
    is supplied, the app uses its transactional store, policy, compiler,
    controls, and source lifecycle, and the ingest path returns truthful
    committed receipts. Authentication is MANDATORY on that serving path.
    Without it, the legacy in-memory/journal behavior is preserved exactly
    unless ``auth_store`` + ``require_auth=True`` are passed explicitly.
    """
    auth_enabled = require_auth if require_auth is not None else (runtime is not None)
    if runtime is not None and require_auth is False:
        raise ValueError("runtime serving path requires authentication (require_auth=False is forbidden)")
    if auth_enabled and auth_store is None:
        if runtime is None:
            raise ValueError("require_auth=True without a runtime needs an explicit auth_store")
        auth_store = AuthStore(runtime.config.auth_path)

    @asynccontextmanager
    async def _runtime_lifespan(app: FastAPI):
        yield
        # Uvicorn does not return to serve_cmd's finally on SIGTERM, so source
        # pump/adapters and the store MUST stop here, in lifespan shutdown.
        # Idempotent with the serve_cmd finally fallback (both guards re-entry).
        if runtime is not None:
            try:
                await runtime.stop_sources()
            finally:
                runtime.close()
            logger.info("runtime shutdown complete (sources stopped, store closed)")

    app = FastAPI(
        title="Entorhinal Contextual Intelligence API",
        description="Local-first purpose-bound context, user sovereignty, and semantic explanation service.",
        version="1.0.0",
        lifespan=_runtime_lifespan,
    )

    if runtime is not None:
        active_journal: Any = runtime.store
        active_policy = runtime.policy
        active_compiler = runtime.compiler
        active_service = runtime.service
        active_user_control = runtime.user_control
        active_pipeline = runtime.pipeline
    else:
        # Initialize dependencies if not provided
        active_journal = journal or EvidenceJournal()
        active_policy = policy_engine or PolicyEngine()
        active_compiler = compiler or MultiTimescaleCompiler(journal=active_journal)
        active_service = service or ContextSnapshotService(
            compiler=active_compiler,
            policy_engine=active_policy,
            journal=active_journal,
        )
        active_user_control = user_control or UserControlService(
            journal=active_journal,
            policy_engine=active_policy,
            compiler=active_compiler,
            snapshot_service=active_service,
        )
        active_pipeline = pipeline or IngestionPipeline(policy_engine=active_policy)

        async def _on_pipeline_record(rec: EvidenceRecord):
            sealed = await active_journal.append(rec)
            active_compiler.process_incremental_event(sealed)

        active_pipeline.register_subscriber(_on_pipeline_record)

    # Auth wiring: persisted grants become the authoritative permission table.
    active_auth: Optional[AuthStore] = auth_store if auth_enabled else None
    if active_auth is not None:
        _sync_consumer_permissions(active_policy, active_auth)
    else:
        logger.warning(
            "API running WITHOUT authentication (legacy/test path only; "
            "must not serve real data)"
        )
    # I-2/N2: the packet service MUST read through the runtime's ONE shared
    # ProjectionHolder. A lazily-owned second holder would never see forget
    # invalidations, serving stale deletion_generation metadata.
    active_packets: Optional[TemporalPacketService] = (
        TemporalPacketService(
            store=active_journal,
            policy=active_policy,
            holder=getattr(runtime, "projection", None),
        )
        if runtime is not None
        else None
    )

    def _authenticate_request(request: Request) -> Optional[Any]:
        if active_auth is None:
            return None
        return active_auth.authenticate(extract_bearer(request.headers.get("authorization")))

    def _require_principal(request: Request, roles: tuple) -> Any:
        principal = _authenticate_request(request)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or unknown credential",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if principal.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{principal.role}' is not authorized for this route",
            )
        return principal

    def _optional_principal(request: Request) -> Optional[Any]:
        try:
            return _authenticate_request(request)
        except Exception:
            return None

    def _resolve_purpose(principal: Any, requested: Optional[str]) -> str:
        allowed = list(getattr(principal, "allowed_purposes", []) or [])
        if requested:
            covers = getattr(principal, "covers_purpose", None)
            ok = covers(requested) if callable(covers) else requested in allowed
            if not ok:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Purpose '{requested}' is not granted to '{principal.principal_id}'",
                )
            return requested
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No purpose granted to '{principal.principal_id}'",
            )
        return allowed[0]

    def _grant_patterns(principal: Any) -> List[str]:
        return list(getattr(principal, "allowed_scopes", []) or [])

    def _record_in_scope(record: EvidenceRecord, patterns: List[str]) -> bool:
        if record.is_tombstone:
            return False
        record_class = SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE.get(record.source_type.value)
        for pattern in patterns:
            pat = (pattern or "").strip()
            if not pat:
                continue
            if pat == "*":
                return record_class is not None
            if pat == (record.target_uri or ""):
                return True
            if record_class is not None and scope_class(pat) == record_class:
                return True
        return False

    async def _record_permitted_now(record: EvidenceRecord) -> bool:
        if record.is_tombstone:
            return False
        try:
            permitted, _ = active_policy.is_consented(
                record.source_type, record.app_identifier, record.target_uri
            )
        except Exception:
            return False
        return bool(permitted)

    def _fact_allowed(fact: DerivedFact, patterns: List[str]) -> bool:
        return any(
            fact_matches_scope(fact.entity_uri, fact.scopes, pattern) for pattern in patterns
        )

    # App state storage
    app.state.journal = active_journal
    app.state.policy = active_policy
    app.state.compiler = active_compiler
    app.state.service = active_service
    app.state.user_control = active_user_control
    app.state.pipeline = active_pipeline
    app.state.runtime = runtime
    app.state.auth = active_auth
    app.state.auth_enabled = auth_enabled
    app.state.packets = active_packets
    app.state.start_time = time.time()
    app.state.active_websockets: list[WebSocket] = []

    # CORS restricted to local origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------------------------------------------------------
    # Trust Dashboard UI
    # --------------------------------------------------------------------------

    @app.get("/ui", response_class=HTMLResponse, summary="Local Trust Dashboard")
    async def serve_trust_ui() -> HTMLResponse:
        """Serve self-contained local Web Trust Dashboard (static shell only)."""
        return get_trust_ui_html()

    # --------------------------------------------------------------------------
    # Observation Ingestion Endpoints (Reflex-Entorhinal Contract vNext-2026.1)
    # --------------------------------------------------------------------------

    @app.post(
        "/api/v1/ingest",
        response_model=ObservationIngestResult,
        status_code=status.HTTP_200_OK,
        summary="Ingest cross-platform observation telemetry from Reflex",
    )
    @app.post(
        "/api/v1/observations",
        response_model=ObservationIngestResult,
        status_code=status.HTTP_200_OK,
        include_in_schema=False,
    )
    async def ingest_observation(
        event: PerceptionObservationEvent, request: Request
    ) -> ObservationIngestResult:
        """Ingest observation event, evaluating policy, persisting to journal, and updating projections."""
        principal = _require_principal(request, WRITE_SOURCE_ROLES) if active_auth is not None else None

        # F2: source identity comes from the authenticated binding, never
        # from caller-supplied labels.
        if principal is not None:
            configured = runtime.config.source_id if runtime is not None else None
            pinned = getattr(principal, "source_id", None)
            if principal.role == ROLE_SOURCE:
                if configured is not None and pinned and pinned != configured:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Source principal is bound to '{pinned}', not '{configured}'",
                    )
                bound_source = pinned or configured
                if not bound_source:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Source principal has no bound source id",
                    )
            else:
                bound_source = configured or pinned or event.source_system
            grant_revision = getattr(principal, "grant_revision", "grant:r1")
            audit_consumer = principal.principal_id
            audit_scopes = [f"source:{bound_source}", f"grant:{grant_revision}"]
            caller_claim = {
                "caller_claimed_source": event.source_system,
                "caller_claimed_scope": event.consent_scope,
            }
        else:
            bound_source = event.source_system
            audit_consumer = event.source_system
            audit_scopes = [event.consent_scope]
            caller_claim = {}

        raw_signal = event.to_raw_signal_event()

        # Pre-storage Policy Check (Fail-Closed)
        decision = active_policy.evaluate_signal(raw_signal)
        if not decision.permitted:
            violation_msg = ", ".join(decision.violations) if decision.violations else "Policy violation"
            active_user_control.audit_manager.record_event(
                action="OBSERVATION_INGEST_DENIED",
                consumer_id=audit_consumer,
                stated_purpose=f"Ingestion from {event.source_subsystem}",
                disclosed_scopes=audit_scopes,
                details={
                    "violations": decision.violations,
                    "observation_id": event.observation_id,
                    **caller_claim,
                },
                permitted=False,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Observation prohibited by policy: {violation_msg}",
            )

        # Ingest through pipeline (debouncing, dedup, and redaction)
        record = await active_pipeline.ingest_event(raw_signal)
        if record is None:
            return ObservationIngestResult(
                status="suppressed",
                observation_id=event.observation_id,
                evidence_id=None,
                provenance_hash=None,
                admitted=False,
                reason="Debounced or deduplicated",
            )

        if runtime is not None:
            return await _ingest_observation_durable(
                event, record, bound_source, audit_consumer, audit_scopes, caller_claim
            )

        active_user_control.audit_manager.record_event(
            action="OBSERVATION_INGESTED",
            consumer_id=audit_consumer,
            stated_purpose=f"Ingestion from {event.source_subsystem}",
            disclosed_scopes=audit_scopes,
            details={
                "observation_id": event.observation_id,
                "evidence_id": record.record_id,
                "app_identifier": record.app_identifier,
                **caller_claim,
            },
            permitted=True,
        )

        return ObservationIngestResult(
            status="ingested",
            observation_id=event.observation_id,
            evidence_id=record.record_id,
            provenance_hash=record.provenance_hash,
            admitted=True,
            reason=None,
        )

    async def _ingest_observation_durable(
        event: PerceptionObservationEvent,
        record: EvidenceRecord,
        bound_source: str,
        audit_consumer: str,
        audit_scopes: List[str],
        caller_claim: Dict[str, Any],
    ) -> ObservationIngestResult:
        """Runtime-backed ingest: transactional commit + committed receipt.

        Returns the STORED evidence ID/hash (never a pre-chain candidate).
        Storage failure yields 503, conflicting ID reuse yields 409 - never
        a generic success. The row is stored under the BOUND source id.
        """
        from entorhinal.evidence.receipts import CommitState

        assert runtime is not None
        observed_at = datetime.fromtimestamp(event.observed_at_ms / 1000.0, tz=timezone.utc)
        receipt = await runtime.store.commit_event(
            source_id=bound_source,
            event_id=event.observation_id,
            record=record,
            observed_at=observed_at,
            received_at=datetime.now(timezone.utc),
        )
        if receipt.state == CommitState.RETRYABLE_STORAGE_FAILURE:
            active_user_control.audit_manager.record_event(
                action="OBSERVATION_COMMIT_FAILED",
                consumer_id=audit_consumer,
                stated_purpose=f"Ingestion from {event.source_subsystem}",
                disclosed_scopes=audit_scopes,
                details={
                    "observation_id": event.observation_id,
                    "reason": receipt.reason,
                    **caller_claim,
                },
                permitted=False,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Durable commit failed (retryable): {receipt.reason}",
            )
        if receipt.state == CommitState.CONFLICT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="observation_id reused with changed content",
            )
        if receipt.state == CommitState.REJECTED or receipt.evidence_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Observation rejected: {receipt.reason}",
            )
        stored = await runtime.store.get_by_id(receipt.evidence_id)
        stored_hash = stored.provenance_hash if stored is not None else receipt.content_hash
        active_user_control.audit_manager.record_event(
            action="OBSERVATION_INGESTED",
            consumer_id=audit_consumer,
            stated_purpose=f"Ingestion from {event.source_subsystem}",
            disclosed_scopes=audit_scopes,
            details={
                "observation_id": event.observation_id,
                "evidence_id": receipt.evidence_id,
                "commit_seq": receipt.commit_seq,
                "commit_state": receipt.state.value,
                "projection_state": receipt.projection_state.value,
                "app_identifier": record.app_identifier,
                **caller_claim,
            },
            permitted=True,
        )
        return ObservationIngestResult(
            status=receipt.state.value,
            observation_id=event.observation_id,
            evidence_id=receipt.evidence_id,
            provenance_hash=stored_hash,
            admitted=True,
            reason=receipt.reason,
        )

    # --------------------------------------------------------------------------
    # Activity event admission (main-owned O3; producer §8.1 contract)
    # --------------------------------------------------------------------------

    @app.post(
        "/activity/v1/events",
        status_code=status.HTTP_200_OK,
        summary="Admit one permitted activity event (opt-in grant)",
    )
    async def admit_activity_event(http_request: Request) -> Response:
        """Admit one ActivityEvent from an explicitly-enabled producer.

        Real-route twin of the reference ``LocalActivityReceiver`` (receipt
        shapes and denial reasons identical; auth failures use this API's
        standard 401/403). Requires a source/admin principal; the stored
        source and grant binding come from the authenticated principal,
        never from caller-supplied labels (F2-style). Admitted events are
        appended to ``<storage_root>/activity/inbox.jsonl`` for the
        ``activity-inbox`` tailer (configure matching ``inbox_path`` /
        ``grants_path`` source-opts on ``serve``). Grants live at
        ``<storage_root>/activity/grants.json`` (see ``activity
        provision-grant``). Loopback daemon only.
        """
        try:
            from entorhinal.activity.events import ActivityEvent
            from entorhinal.activity.grants import GrantStore
            from entorhinal.activity.producers.browser_sender import (
                InboxFileSink,
                ReceiverReceipt,
            )
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Activity component unavailable",
            )
        principal = _require_principal(http_request, WRITE_SOURCE_ROLES) if active_auth is not None else None
        if runtime is None or principal is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Activity event admission requires the authenticated runtime path",
            )

        def _receipt(status_text: str, http_status: int, **fields: Any) -> JSONResponse:
            receipt = ReceiverReceipt(status=status_text, **fields)
            return JSONResponse(
                content=receipt.model_dump(mode="json"), status_code=http_status
            )

        raw = await http_request.body()
        if len(raw) <= 0 or len(raw) > 1_000_000:
            active_user_control.audit_manager.record_event(
                action="ACTIVITY_EVENT_REJECTED",
                consumer_id=principal.principal_id,
                disclosed_scopes=[],
                details={"reason": "rejected:bad-length"},
                permitted=False,
            )
            return _receipt("rejected", 400, reason="rejected:bad-length")
        try:
            candidate = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            active_user_control.audit_manager.record_event(
                action="ACTIVITY_EVENT_REJECTED",
                consumer_id=principal.principal_id,
                disclosed_scopes=[],
                details={"reason": "rejected:bad-json"},
                permitted=False,
            )
            return _receipt("rejected", 400, reason="rejected:bad-json")
        try:
            event = ActivityEvent.model_validate(candidate)
        except Exception as exc:
            active_user_control.audit_manager.record_event(
                action="ACTIVITY_EVENT_REJECTED",
                consumer_id=principal.principal_id,
                disclosed_scopes=[],
                details={"reason": f"rejected:schema:{str(exc)[:200]}"},
                permitted=False,
            )
            return _receipt(
                "rejected", 400, reason=f"rejected:schema:{str(exc)[:200]}"
            )

        # F2-style identity: a pinned source principal admits only its own
        # source; caller-supplied source labels are never trusted.
        pinned = getattr(principal, "source_id", None)
        if principal.role == ROLE_SOURCE and pinned and event.source_id != pinned:
            active_user_control.audit_manager.record_event(
                action="ACTIVITY_EVENT_DENIED",
                consumer_id=principal.principal_id,
                disclosed_scopes=[f"source:{event.source_id}", f"grant:{event.grant_id}"],
                details={
                    "event_id": event.event_id,
                    "reason": "denied:principal-source-mismatch",
                },
                permitted=False,
            )
            return _receipt(
                "denied", 403,
                source_id=event.source_id, event_id=event.event_id,
                reason="denied:principal-source-mismatch",
            )

        activity_dir = Path(runtime.config.storage_root) / "activity"
        try:
            grants = GrantStore(activity_dir / "grants.json")
        except Exception as exc:
            active_user_control.audit_manager.record_event(
                action="ACTIVITY_EVENT_DENIED",
                consumer_id=principal.principal_id,
                disclosed_scopes=[f"source:{event.source_id}", f"grant:{event.grant_id}"],
                details={"event_id": event.event_id, "reason": "error:grants-unavailable"},
                permitted=False,
            )
            return _receipt(
                "error", 500,
                source_id=event.source_id, event_id=event.event_id,
                reason=f"error:grants-unavailable:{exc}",
            )
        grant = grants.get(event.grant_id)
        if (
            principal.role == ROLE_SOURCE
            and grant is not None
            and grant.principal != principal.principal_id
        ):
            active_user_control.audit_manager.record_event(
                action="ACTIVITY_EVENT_DENIED",
                consumer_id=principal.principal_id,
                disclosed_scopes=[f"source:{event.source_id}", f"grant:{event.grant_id}"],
                details={
                    "event_id": event.event_id,
                    "reason": "denied:grant-principal-mismatch",
                },
                permitted=False,
            )
            return _receipt(
                "denied", 403,
                source_id=event.source_id, event_id=event.event_id,
                reason="denied:grant-principal-mismatch",
            )
        allowed, reason = grants.check(event)
        if not allowed:
            active_user_control.audit_manager.record_event(
                action="ACTIVITY_EVENT_DENIED",
                consumer_id=principal.principal_id,
                disclosed_scopes=[f"source:{event.source_id}", f"grant:{event.grant_id}"],
                details={"event_id": event.event_id, "reason": reason},
                permitted=False,
            )
            return _receipt(
                "denied", 403,
                source_id=event.source_id, event_id=event.event_id, reason=reason,
            )
        try:
            InboxFileSink(activity_dir / "inbox.jsonl")(event)
        except Exception as exc:
            active_user_control.audit_manager.record_event(
                action="ACTIVITY_EVENT_DENIED",
                consumer_id=principal.principal_id,
                disclosed_scopes=[f"source:{event.source_id}", f"grant:{event.grant_id}"],
                details={"event_id": event.event_id, "reason": f"error:sink-failed:{exc}"},
                permitted=False,
            )
            return _receipt(
                "error", 500,
                source_id=event.source_id, event_id=event.event_id,
                reason=f"error:sink-failed:{exc}",
            )
        active_user_control.audit_manager.record_event(
            action="ACTIVITY_EVENT_ADMITTED",
            consumer_id=principal.principal_id,
            disclosed_scopes=[f"source:{event.source_id}", f"grant:{event.grant_id}"],
            details={"event_id": event.event_id, "reason": "admitted"},
            permitted=True,
        )
        return _receipt(
            "admitted", 200,
            source_id=event.source_id, event_id=event.event_id,
            admitted=True, reason="admitted",
        )

    # --------------------------------------------------------------------------
    # Context Endpoints
    # --------------------------------------------------------------------------

    @app.post(
        "/api/v1/context/request",
        response_model=ContextSnapshot,
        status_code=status.HTTP_200_OK,
        summary="Request a purpose-bound advisory ContextSnapshot",
    )
    @app.post(
        "/context/snapshot",
        response_model=ContextSnapshot,
        status_code=status.HTTP_200_OK,
        include_in_schema=False,
    )
    async def request_context_snapshot(request: ContextRequest, http_request: Request) -> ContextSnapshot:
        """Evaluate policy grants and compile an advisory ContextSnapshot."""
        principal = _require_principal(http_request, READ_ROLES) if active_auth is not None else None
        if principal is not None and request.consumer_id != principal.principal_id:
            active_user_control.audit_manager.record_event(
                action="CONTEXT_SNAPSHOT_DENIED",
                consumer_id=principal.principal_id,
                stated_purpose=request.stated_purpose,
                disclosed_scopes=request.requested_scopes,
                details={
                    "error": "consumer_id does not match authenticated principal",
                    "claimed_consumer_id": request.consumer_id,
                },
                permitted=False,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="consumer_id must equal the authenticated principal",
            )
        try:
            snapshot = await active_service.request_snapshot(request, principal)
            active_user_control.audit_manager.record_event(
                action="CONTEXT_SNAPSHOT_DELIVERED",
                consumer_id=request.consumer_id,
                stated_purpose=request.stated_purpose,
                disclosed_scopes=request.requested_scopes,
                disclosed_fact_count=len(snapshot.active_facts),
                details={
                    "snapshot_id": snapshot.snapshot_id,
                    "overflow": snapshot.overflow,
                    "authenticated_principal": principal.principal_id if principal else None,
                },
                permitted=True,
            )
            return snapshot
        except PermissionDeniedError as e:
            active_user_control.audit_manager.record_event(
                action="CONTEXT_SNAPSHOT_DENIED",
                consumer_id=request.consumer_id,
                stated_purpose=request.stated_purpose,
                disclosed_scopes=request.requested_scopes,
                details={"error": str(e)},
                permitted=False,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e),
            )
        except BudgetExceededError as e:
            active_user_control.audit_manager.record_event(
                action="CONTEXT_SNAPSHOT_BUDGET_EXCEEDED",
                consumer_id=request.consumer_id,
                stated_purpose=request.stated_purpose,
                disclosed_scopes=request.requested_scopes,
                details={
                    "error": str(e),
                    "budget_tokens": e.budget_tokens,
                    "used_tokens": e.used_tokens,
                    "tokenizer": e.tokenizer,
                },
                permitted=False,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e),
            )
        except Exception as e:
            logger.error("Error synthesizing snapshot: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate context snapshot: {str(e)}",
            )

    @app.post(
        "/api/v1/context/packet",
        status_code=status.HTTP_200_OK,
        summary="Request a purpose-bound temporal ResumptionPacket (cutoff)",
    )
    async def request_context_packet(
        packet_request: PacketRequest, http_request: Request
    ) -> Response:
        """Serve an actual temporal/cutoff packet from the runtime projection."""
        principal = _require_principal(http_request, READ_ROLES) if active_auth is not None else None
        if active_packets is None or principal is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Packet serving requires the authenticated runtime path",
            )
        try:
            packet, report = await active_packets.request_packet(principal, packet_request)
        except PacketAccessDenied as e:
            active_user_control.audit_manager.record_event(
                action="CONTEXT_PACKET_DENIED",
                consumer_id=principal.principal_id,
                stated_purpose=packet_request.purpose,
                disclosed_scopes=_grant_patterns(principal),
                details={"error": str(e), "reason": e.reason, "task_id": packet_request.task_id},
                permitted=False,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
        except UnknownTaskError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown task '{packet_request.task_id}'",
            )
        except BudgetExceededError as e:
            active_user_control.audit_manager.record_event(
                action="CONTEXT_PACKET_BUDGET_EXCEEDED",
                consumer_id=principal.principal_id,
                stated_purpose=packet_request.purpose,
                disclosed_scopes=_grant_patterns(principal),
                details={"error": str(e), "task_id": packet_request.task_id},
                permitted=False,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
            )
        active_user_control.audit_manager.record_event(
            action="CONTEXT_PACKET_DELIVERED",
            consumer_id=principal.principal_id,
            stated_purpose=packet_request.purpose,
            disclosed_scopes=_grant_patterns(principal),
            details={
                "packet_id": packet.packet_id,
                "task_id": packet.task_state.task_id,
                "cutoff_seq": packet.metadata.cutoff_seq,
                "watermark": packet.metadata.watermark,
                "served_events": report.served_events,
                "excluded_out_of_scope": report.excluded_out_of_scope,
                "excluded_restricted": report.excluded_restricted,
                "deletion_generation": report.deletion_generation,
                "revocation_generation": report.revocation_generation,
                "overflow": packet.budget.overflow,
            },
            permitted=True,
        )
        return JSONResponse(
            content=packet.model_dump(mode="json"),
            headers={
                "X-Entorhinal-Excluded-Out-Of-Scope": str(report.excluded_out_of_scope),
                "X-Entorhinal-Excluded-Restricted": str(report.excluded_restricted),
            },
        )

    @app.get(
        "/api/v1/context/explain/{fact_id}",
        response_model=FactExplanation,
        status_code=status.HTTP_200_OK,
        summary="Explain a derived fact with provenance and uncertainty tracing",
    )
    async def explain_fact(
        fact_id: str, request: Request, purpose: Optional[str] = None
    ) -> FactExplanation:
        """Trace full provenance path from derived fact to journal evidence."""
        principal = _require_principal(request, READ_ROLES) if active_auth is not None else None
        patterns = _grant_patterns(principal) if principal is not None else ["*"]
        if principal is not None:
            _resolve_purpose(principal, purpose)
        explanation = await active_service.explain_fact(fact_id)
        if explanation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fact with ID '{fact_id}' not found.",
            )
        if principal is not None:
            fact_scopes: List[str] = []
            for candidate in active_compiler.get_active_facts():
                if candidate.fact_id == fact_id:
                    fact_scopes = list(candidate.scopes)
                    break
            if not any(
                fact_matches_scope(explanation.entity_uri, fact_scopes, pattern)
                for pattern in patterns
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Fact is outside the authenticated principal's granted scopes",
                )
            kept_records: List[EvidenceRecord] = []
            withheld = 0
            for record in explanation.supporting_evidence:
                if not _record_in_scope(record, patterns) or not await _record_permitted_now(record):
                    withheld += 1
                    continue
                kept_records.append(record)
            kept_ids = {r.record_id for r in kept_records}
            reasons = list(explanation.uncertainty_reasons)
            if withheld:
                reasons.append(
                    f"{withheld} supporting record(s) withheld by current access restrictions"
                )
            explanation = FactExplanation(
                fact_id=explanation.fact_id,
                entity_uri=explanation.entity_uri,
                attribute=explanation.attribute,
                value=explanation.value,
                confidence=explanation.confidence,
                supporting_evidence_ids=[i for i in explanation.supporting_evidence_ids if i in kept_ids],
                derived_by=explanation.derived_by,
                reasoning_summary=explanation.reasoning_summary,
                valid_from=explanation.valid_from,
                valid_to=explanation.valid_to,
                derivation_rule=explanation.derivation_rule,
                supporting_evidence=kept_records,
                active_hypotheses=explanation.active_hypotheses,
                uncertainty_reasons=reasons,
                user_override_active=explanation.user_override_active,
            )
        return explanation

    @app.get(
        "/api/v1/context/focus",
        response_model=ImmediateFocusState,
        status_code=status.HTTP_200_OK,
        summary="Get real-time foreground immediate focus state",
    )
    async def get_immediate_focus(
        request: Request, purpose: Optional[str] = None
    ) -> ImmediateFocusState:
        """Return the user's current foreground application and document focus."""
        principal = _require_principal(request, READ_ROLES) if active_auth is not None else None
        if principal is not None:
            _resolve_purpose(principal, purpose)
        context = active_compiler.get_current_context()
        focus = context.immediate_focus
        if isinstance(focus, ImmediateFocusState):
            current = focus
        elif isinstance(focus, dict) and focus.get("app_identifier"):
            current = ImmediateFocusState(**focus)
        else:
            return ImmediateFocusState(
                focus_id=generate_uuidv7(),
                timestamp=datetime.now(timezone.utc),
                app_identifier="system.idle",
                window_title="Idle",
                duration_seconds=0.0,
            )
        if principal is not None:
            patterns = _grant_patterns(principal)
            record_class = SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE.get(current.source_type.value)
            in_scope = any(
                (pat.strip() == "*" and record_class is not None)
                or pat.strip() == (current.target_uri or "")
                or (record_class is not None and scope_class(pat) == record_class)
                for pat in patterns
            )
            if not in_scope:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Current focus is outside the authenticated principal's granted scopes",
                )
            try:
                permitted, _ = active_policy.is_consented(
                    current.source_type, current.app_identifier, current.target_uri
                )
            except Exception:
                permitted = False
            if not permitted:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Current focus is withheld by current access restrictions",
                )
        return current

    @app.get(
        "/api/v1/context/timeline",
        summary="Get recent evidence timeline",
    )
    async def get_timeline(
        request: Request, limit: int = 50, purpose: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return recent evidence records from journal (tombstones excluded)."""
        principal = _require_principal(request, READ_ROLES) if active_auth is not None else None
        if principal is not None:
            _resolve_purpose(principal, purpose)
        bounded = max(1, min(int(limit), TIMELINE_LIMIT_MAX))
        records = await active_journal.scan_evidence(limit=bounded)
        if principal is None:
            return [r.model_dump() for r in records]
        patterns = _grant_patterns(principal)
        out: List[Dict[str, Any]] = []
        for record in records:
            if not _record_in_scope(record, patterns):
                continue
            if not await _record_permitted_now(record):
                continue
            out.append(record.model_dump())
        return out

    @app.get(
        "/api/v1/context/graph",
        summary="Get semantic entity graph state and active facts",
    )
    async def get_semantic_graph(
        request: Request, purpose: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return entity nodes, relation edges, and active compiled facts."""
        principal = _require_principal(request, READ_ROLES) if active_auth is not None else None
        if principal is not None:
            _resolve_purpose(principal, purpose)
        nodes = [n.model_dump() for n in active_compiler.graph_manager.list_nodes()]
        edges = [e.model_dump() for e in active_compiler.graph_manager.get_edges()]
        facts = [f.model_dump() for f in active_compiler.get_active_facts()]
        if principal is None:
            return {"nodes": nodes, "edges": edges, "facts": facts}
        patterns = _grant_patterns(principal)
        node_scopes = getattr(active_compiler.graph_manager, "node_scopes", None)
        kept_uris: set = set()
        kept_nodes: List[Dict[str, Any]] = []
        for node in active_compiler.graph_manager.list_nodes():
            stored = node_scopes(node.entity_uri) if callable(node_scopes) else []
            if any(
                fact_matches_scope(node.entity_uri, stored, pattern) for pattern in patterns
            ):
                kept_uris.add(node.entity_uri)
                kept_nodes.append(node.model_dump())
        kept_edges = [
            e.model_dump()
            for e in active_compiler.graph_manager.get_edges()
            if e.source_uri in kept_uris and e.target_uri in kept_uris
        ]
        kept_facts = [
            f.model_dump() for f in active_compiler.get_active_facts() if _fact_allowed(f, patterns)
        ]
        return {"nodes": kept_nodes, "edges": kept_edges, "facts": kept_facts}

    @app.get(
        "/api/v1/health",
        status_code=status.HTTP_200_OK,
        summary="Health check and service status",
    )
    @app.get(
        "/health",
        status_code=status.HTTP_200_OK,
        include_in_schema=False,
    )
    async def health_check(request: Request) -> Dict[str, Any]:
        """Minimal liveness publicly; full detail only with credentials."""
        principal = _optional_principal(request) if active_auth is not None else "legacy"
        if active_auth is not None and principal is None:
            return {"status": "healthy", "service": "entorhinal", "version": "1.0.0"}
        uptime = time.time() - app.state.start_time
        context = active_compiler.get_current_context()
        records_count = await active_journal.count_records()
        is_valid, _, _ = active_journal.verify_journal_integrity()

        payload: Dict[str, Any] = {
            "status": "healthy",
            "service": "entorhinal",
            "version": "1.0.0",
            "projection_version": active_compiler.graph_manager.version,
            "fact_id_algorithm": FACT_ID_ALGORITHM,
            "cluster_id_algorithm": CLUSTER_ID_ALGORITHM,
            "edge_id_algorithm": EDGE_ID_ALGORITHM,
            "uptime_seconds": round(uptime, 2),
            "journal_records_count": records_count,
            "journal_integrity": "verified" if is_valid else "corrupted",
            "active_facts_count": context.active_facts_count,
            "active_hypotheses_count": context.active_hypotheses_count,
        }
        if runtime is not None:
            payload["runtime_root"] = str(runtime.config.storage_root)
            payload["store"] = runtime.store.health()
            payload["sources"] = runtime.sources.health()
            if active_packets is not None:
                payload["packets"] = active_packets.serving_status()
        return payload

    @app.get(
        "/api/v1/sources/health",
        status_code=status.HTTP_200_OK,
        summary="Truthful source lifecycle health",
    )
    async def sources_health(request: Request) -> Dict[str, Any]:
        """Return actual producer/lifecycle state, or not-configured."""
        if active_auth is not None:
            _require_principal(request, READ_ROLES)
        if runtime is None:
            return {"lifecycle_running": False, "configured_sources": [], "sources": {}}
        return runtime.sources.health()

    # --------------------------------------------------------------------------
    # User Control & Governance Endpoints (admin role on the serving path)
    # --------------------------------------------------------------------------

    @app.get("/api/v1/user/corrections", summary="List active user corrections")
    async def list_user_corrections(request: Request) -> List[Dict[str, Any]]:
        """Return all active user correction locks."""
        if active_auth is not None:
            _require_principal(request, ADMIN_ROLES)
        corrs = active_user_control.list_corrections()
        return [c.model_dump() for c in corrs]

    @app.post("/api/v1/user/corrections", summary="Submit a user correction override lock")
    async def submit_user_correction_endpoint(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a permanent user correction override lock."""
        if active_auth is not None:
            _require_principal(request, ADMIN_ROLES)
        target_id = payload.get("target_entity_or_fact_id")
        if not target_id:
            raise HTTPException(status_code=400, detail="Missing target_entity_or_fact_id")

        action_str = payload.get("override_action", "overwrite")
        action = CorrectionAction(action_str.lower())
        corrected_value = payload.get("corrected_value")
        user_note = payload.get("user_comment") or payload.get("user_note")

        corr = await active_user_control.submit_user_correction(
            target_entity_or_fact_id=target_id,
            corrected_value=corrected_value,
            user_note=user_note,
            override_action=action,
        )
        return corr.model_dump()

    @app.post("/api/v1/user/forget", summary="Execute cascade deletion for time range")
    async def forget_time_range_endpoint(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute cryptographic cascade deletion across a time range."""
        if active_auth is not None:
            _require_principal(request, ADMIN_ROLES)
        start_str = payload.get("start_time")
        end_str = payload.get("end_time")
        reason = payload.get("reason", "User deletion request")

        if not start_str or not end_str:
            raise HTTPException(status_code=400, detail="start_time and end_time are required")

        try:
            st = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            et = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid ISO timestamp format: {e}")

        proof = await active_user_control.forget_time_range(
            start_time=st,
            end_time=et,
            reason=reason,
        )
        return proof

    @app.get("/api/v1/user/grants", summary="List active consent grants")
    async def list_grants_endpoint(request: Request) -> List[Dict[str, Any]]:
        """List active policy consent rules."""
        if active_auth is not None:
            _require_principal(request, ADMIN_ROLES)
        rules = active_user_control.list_consent_rules()
        return [
            {
                "rule_id": r.rule_id,
                "allow": r.allow,
                "source_type": r.source_type.value if r.source_type else None,
                "app_pattern": r.app_pattern,
                "domain_pattern": r.domain_pattern,
                "priority": r.priority,
            }
            for r in rules
        ]

    @app.post("/api/v1/user/grants", summary="Grant capture consent")
    async def grant_consent_endpoint(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add an explicit capture consent rule."""
        if active_auth is not None:
            _require_principal(request, ADMIN_ROLES)
        st_val = payload.get("source_type", "browser")
        st = SourceType(st_val.lower()) if st_val else SourceType.BROWSER
        app_pat = payload.get("app_pattern", "*")
        domain_pat = payload.get("domain_pattern", "*")

        rule_id = await active_user_control.grant_consent(
            source_type=st,
            app_pattern=app_pat,
            domain_pattern=domain_pat,
        )
        return {"rule_id": rule_id, "status": "granted"}

    @app.delete("/api/v1/user/grants/{rule_id}", summary="Revoke a consent rule")
    async def revoke_consent_endpoint(request: Request, rule_id: str) -> Dict[str, Any]:
        """Revoke an active consent rule by ID."""
        if active_auth is not None:
            _require_principal(request, ADMIN_ROLES)
        success = await active_user_control.revoke_consent(rule_id)
        if not success:
            raise HTTPException(status_code=404, detail="Rule ID not found")
        return {"rule_id": rule_id, "status": "revoked"}

    @app.get("/api/v1/user/audit", summary="Get audit logs")
    async def get_audit_endpoint(
        request: Request,
        limit: int = 100,
        consumer: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query recent audit events."""
        if active_auth is not None:
            _require_principal(request, ADMIN_ROLES)
        return await active_user_control.get_audit_log(limit=limit, consumer_filter=consumer)

    @app.get("/api/v1/user/export", summary="Export full system state")
    async def export_data_endpoint(request: Request, format: str = "json") -> Response:
        """Export full system data in JSON or ZIP format."""
        if active_auth is not None:
            _require_principal(request, ADMIN_ROLES)
        exported = await active_user_control.export_data(format=format)
        if format.lower() == "zip":
            return Response(
                content=exported,
                media_type="application/zip",
                headers={"Content-Disposition": "attachment; filename=entorhinal_export.zip"},
            )
        return Response(
            content=exported if isinstance(exported, str) else exported.decode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=entorhinal_export.json"},
        )

    # --------------------------------------------------------------------------
    # Admin principal management (admin role; serving path only)
    # --------------------------------------------------------------------------

    @app.post("/api/v1/admin/principals", summary="Create an authenticated principal")
    async def create_principal_endpoint(request: Request, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a source/reader/admin principal; the secret is returned ONCE."""
        if active_auth is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Principal management requires the authenticated runtime path",
            )
        _require_principal(request, ADMIN_ROLES)
        try:
            principal, secret = active_auth.create_principal(
                role=str(payload.get("role", "")),
                principal_id=str(payload.get("principal_id", "")),
                allowed_purposes=list(payload.get("allowed_purposes", []) or []),
                allowed_scopes=list(payload.get("allowed_scopes", []) or []),
                max_budget=int(payload.get("max_budget", 4096)),
                source_id=payload.get("source_id"),
                grant_revision=str(payload.get("grant_revision", "grant:r1")),
                label=str(payload.get("label", "") or ""),
            )
        except ValueError as e:
            detail = str(e)
            code = status.HTTP_409_CONFLICT if "already exists" in detail else 400
            raise HTTPException(status_code=code, detail=detail)
        _sync_consumer_permissions(active_policy, active_auth)
        return {
            "principal_id": principal.principal_id,
            "role": principal.role,
            "secret": secret,
            "secret_note": "shown once; it cannot be retrieved again",
            "allowed_purposes": principal.allowed_purposes,
            "allowed_scopes": principal.allowed_scopes,
            "max_budget": principal.max_budget,
            "source_id": principal.source_id,
            "grant_revision": principal.grant_revision,
        }

    @app.get("/api/v1/admin/principals", summary="List authenticated principals")
    async def list_principals_endpoint(request: Request) -> List[Dict[str, Any]]:
        """List principals without secret material."""
        if active_auth is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Principal management requires the authenticated runtime path",
            )
        _require_principal(request, ADMIN_ROLES)
        return [
            {
                "principal_id": p.principal_id,
                "role": p.role,
                "allowed_purposes": p.allowed_purposes,
                "allowed_scopes": p.allowed_scopes,
                "max_budget": p.max_budget,
                "source_id": p.source_id,
                "grant_revision": p.grant_revision,
                "label": p.label,
                "created_at": p.created_at,
                "disabled": p.disabled,
            }
            for p in active_auth.list_principals()
        ]

    @app.post(
        "/api/v1/admin/principals/{principal_id}/revoke",
        summary="Revoke an authenticated principal",
    )
    async def revoke_principal_endpoint(request: Request, principal_id: str) -> Dict[str, Any]:
        """Revoke a principal; its credential authenticates as unknown after."""
        if active_auth is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Principal management requires the authenticated runtime path",
            )
        _require_principal(request, ADMIN_ROLES)
        if not active_auth.revoke(principal_id):
            raise HTTPException(status_code=404, detail="Principal ID not found")
        _sync_consumer_permissions(active_policy, active_auth)
        return {"principal_id": principal_id, "status": "revoked"}

    # --------------------------------------------------------------------------
    # WebSocket Streaming Endpoint
    # --------------------------------------------------------------------------

    @app.websocket("/ws/v1/context/focus")
    async def websocket_focus_stream(
        websocket: WebSocket, token: Optional[str] = Query(default=None)
    ) -> None:
        """Stream real-time immediate focus updates to connected clients."""
        principal: Optional[Any] = None
        if active_auth is not None:
            credential = extract_bearer(
                websocket.headers.get("authorization"), query_token=token
            )
            principal = active_auth.authenticate(credential)
            if principal is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            if principal.role not in READ_ROLES:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        await websocket.accept()
        app.state.active_websockets.append(websocket)
        try:
            while True:
                context = active_compiler.get_current_context()
                raw_focus = context.immediate_focus
                if isinstance(raw_focus, ImmediateFocusState):
                    focus_data: Any = raw_focus.model_dump(mode="json")
                    focus_obj: Optional[ImmediateFocusState] = raw_focus
                elif isinstance(raw_focus, dict):
                    focus_data = raw_focus
                    focus_obj = None
                else:
                    focus_data = {}
                    focus_obj = None
                restricted_reason: Optional[str] = None
                if principal is not None and focus_obj is not None and focus_obj.app_identifier:
                    patterns = _grant_patterns(principal)
                    record_class = SOURCE_CLASS_SCOPE_BY_SOURCE_TYPE.get(
                        focus_obj.source_type.value
                    )
                    in_scope = any(
                        (pat.strip() == "*" and record_class is not None)
                        or pat.strip() == (focus_obj.target_uri or "")
                        or (
                            record_class is not None
                            and scope_class(pat) == record_class
                        )
                        for pat in patterns
                    )
                    if not in_scope:
                        restricted_reason = "out_of_scope"
                    else:
                        try:
                            permitted, _ = active_policy.is_consented(
                                focus_obj.source_type,
                                focus_obj.app_identifier,
                                focus_obj.target_uri,
                            )
                        except Exception:
                            permitted = False
                        if not permitted:
                            restricted_reason = "restricted"
                if restricted_reason is not None:
                    await websocket.send_json(
                        {
                            "type": "focus_update",
                            "data": None,
                            "restricted": True,
                            "reason": restricted_reason,
                        }
                    )
                else:
                    await websocket.send_json({"type": "focus_update", "data": focus_data})
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            if websocket in app.state.active_websockets:
                app.state.active_websockets.remove(websocket)
        except Exception as e:
            logger.warning("WebSocket client exception: %s", e)
            if websocket in app.state.active_websockets:
                app.state.active_websockets.remove(websocket)

    return app


# Default app instance
app = create_app()
