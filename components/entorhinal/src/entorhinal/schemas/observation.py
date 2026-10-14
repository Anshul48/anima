"""Reflex-Entorhinal Observation Ingestion Schema (vNext-2026.1).

Governs cross-platform perception telemetry pushed from Reflex to Entorhinal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from entorhinal.schemas.models import RawSignalEvent, SourceType


class ObservationBoundingBox(BaseModel):
    """Bounding box coordinates for UI active elements."""
    model_config = ConfigDict(extra="ignore")

    x1: float
    y1: float
    x2: float
    y2: float


class ActiveElementInfo(BaseModel):
    """Active or focused UI element information."""
    model_config = ConfigDict(extra="ignore")

    role: Optional[str] = None
    label: Optional[str] = None
    bounds: Optional[ObservationBoundingBox] = None


class ObservationEpistemicUncertainty(BaseModel):
    """Epistemic uncertainty and sensor confidence metadata."""
    model_config = ConfigDict(extra="ignore")

    grounding_confidence: float = Field(..., ge=0.0, le=1.0)
    is_inferred: bool = False
    freshness_ttl_ms: float = 60000.0


class ObservationPerceptionPayload(BaseModel):
    """Sensory observation payload captured by Reflex."""
    model_config = ConfigDict(extra="ignore")

    app_identifier: str
    window_title: str
    target_uri: Optional[str] = None
    active_element: Optional[ActiveElementInfo] = None
    custom_attributes: Dict[str, Any] = Field(default_factory=dict)


class PerceptionObservationEvent(BaseModel):
    """Observation telemetry event matching Reflex-Entorhinal Contract vNext-2026.1."""
    model_config = ConfigDict(extra="ignore")

    contract_version: str = Field(default="vNext-2026.1")
    observation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    observed_at_ms: float
    source_system: str
    source_subsystem: str
    consent_scope: str
    epistemic_uncertainty: ObservationEpistemicUncertainty
    perception_payload: ObservationPerceptionPayload
    provenance_signature: Optional[str] = None

    def to_raw_signal_event(self) -> RawSignalEvent:
        """Convert perception event into internal RawSignalEvent for IngestionPipeline."""
        # Determine appropriate SourceType
        lower_sys = self.source_system.lower()
        lower_uri = (self.perception_payload.target_uri or "").lower()

        if "browser" in lower_sys or lower_uri.startswith("http://") or lower_uri.startswith("https://"):
            src_type = SourceType.BROWSER
        elif "pty" in lower_sys or "shell" in lower_sys or "terminal" in lower_sys:
            src_type = SourceType.TERMINAL_PTY
        else:
            src_type = SourceType.OS_WINDOW

        # Reconstruct timestamp
        dt = datetime.fromtimestamp(self.observed_at_ms / 1000.0, tz=timezone.utc)

        raw_payload = dict(self.perception_payload.custom_attributes)
        raw_payload["source_subsystem"] = self.source_subsystem
        raw_payload["consent_scope"] = self.consent_scope
        raw_payload["epistemic_uncertainty"] = self.epistemic_uncertainty.model_dump()
        raw_payload["contract_version"] = self.contract_version
        raw_payload["observation_id"] = self.observation_id
        if self.perception_payload.active_element:
            raw_payload["active_element"] = self.perception_payload.active_element.model_dump()

        return RawSignalEvent(
            source_type=src_type,
            adapter_id=self.source_system,
            app_identifier=self.perception_payload.app_identifier,
            window_title=self.perception_payload.window_title,
            target_uri=self.perception_payload.target_uri,
            raw_payload=raw_payload,
            captured_at=dt,
        )


class ObservationIngestResult(BaseModel):
    """Structured response from Entorhinal observation ingestion."""
    status: str
    observation_id: str
    evidence_id: Optional[str] = None
    provenance_hash: Optional[str] = None
    admitted: bool = True
    reason: Optional[str] = None
