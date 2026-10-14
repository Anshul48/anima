"""Activity tracking records: permitted, provenance-bearing event model.

This module defines the activity builder's event contract (``activity-event/1``)
and its bridge to the existing ``RawSignalEvent`` ingestion path. It introduces
no shared-schema changes: conversion helpers map to and from ``RawSignalEvent``
so main can admit activity events through the unchanged factory pump.

Identity: the idempotency key is ``(source_id, event_id)``. Re-ingest with
identical content is a no-op returning the original outcome; the same key with
changed content is a conflict, never a silent merge.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from entorhinal.schemas.models import EvidenceRecord, RawSignalEvent, SourceType

ACTIVITY_EVENT_SCHEMA = "activity-event/1"

#: Source-id namespace owned by the activity builder. Must not collide with
#: ``entorhinal.dev-task.01`` or API-builder sources.
ACTIVITY_SOURCE_PREFIX = "entorhinal.activity."


class ActivityKind(str, Enum):
    """Observed activity-event kinds (foreground vs background is explicit)."""

    WINDOW_FOREGROUND = "window-foreground"
    WINDOW_BACKGROUND = "window-background"
    MEDIA_FOREGROUND = "media-foreground"
    MEDIA_BACKGROUND = "media-background"
    MEDIA_MARKER = "media-marker"  # pause/resume/seek with position evidence
    INPUT_MARKER = "input-marker"  # permitted counts only, never key content
    RESUME_MARKER = "resume-marker"  # explicit user resume signal
    HEARTBEAT = "heartbeat"


class ContentIdentity(BaseModel):
    """Canonical content identity used for resumption decisions.

    ``kind`` distinguishes media items (lectures, videos) from code/documents.
    ``key`` is the canonical join key (e.g. ``media:host:media_id``). Unknown
    identity is represented by absence (None on the event), never by a
    guessed key: unknown content must never auto-merge.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    display: str = Field(default="")
    fingerprint: Optional[str] = Field(default=None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_media_id(uri: str) -> Optional[str]:
    """Extract a canonical media id from a URI without network access.

    Supports common lecture/video URL shapes (watch?v=, youtu.be, /video/,
    /embed/). Returns None when no stable media id is present: callers must
    treat that as unknown identity, not as a mergeable key.
    """
    if not uri:
        return None
    try:
        parsed = urlparse(uri)
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    query = parse_qs(parsed.query)
    for param in ("v", "video_id", "media_id", "lecture"):
        values = query.get(param)
        if values and values[0].strip():
            return f"{host}|{param}={values[0].strip()}"
    path = parsed.path or ""
    segments = [s for s in path.split("/") if s]
    if host.endswith("youtu.be") and segments:
        return f"{host}|v={segments[0]}"
    for marker in ("watch", "video", "videos", "embed", "lecture", "lectures", "play"):
        if marker in segments:
            idx = segments.index(marker)
            if idx + 1 < len(segments):
                return f"{host}|{marker}={segments[idx + 1]}"
    return None


def title_fingerprint(title: Optional[str]) -> Optional[str]:
    """Stable fingerprint of a window/media title for corroboration only.

    A fingerprint match alone never merges sessions; it only corroborates a
    media-id match (or records a mismatch as contradictory evidence).
    """
    if not title or not title.strip():
        return None
    normalized = " ".join(title.strip().lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


def canonical_content_identity(
    uri: Optional[str],
    title: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[ContentIdentity]:
    """Derive canonical content identity from local fields only.

    Precedence: explicit ``payload.media_id`` (+ ``media_host``) supplied by a
    permitted producer; else media id parsed from the URI; else a code/document
    key for file URIs; else None (unknown). No network, no model.
    """
    payload = payload or {}
    media_id = payload.get("media_id")
    media_host = payload.get("media_host")
    if isinstance(media_id, str) and media_id.strip():
        host = str(media_host).strip().lower() if media_host else "unspecified-host"
        key = f"media:{host}:{media_id.strip()}"
        return ContentIdentity(
            kind="media",
            key=key,
            display=str(payload.get("media_title") or title or media_id).strip(),
            fingerprint=title_fingerprint(title),
        )
    if uri:
        parsed_id = canonical_media_id(uri)
        if parsed_id:
            return ContentIdentity(
                kind="media",
                key=f"media:{parsed_id}",
                display=(title or uri).strip(),
                fingerprint=title_fingerprint(title),
            )
        try:
            parsed = urlparse(uri)
        except Exception:
            parsed = None
        if parsed is not None and parsed.scheme == "file" and parsed.path:
            return ContentIdentity(
                kind="code" if parsed.path.endswith((".py", ".ts", ".js", ".go", ".rs", ".java", ".c", ".cpp", ".md")) else "document",
                key=f"file:{parsed.path}",
                display=(title or parsed.path).strip(),
                fingerprint=title_fingerprint(title),
            )
    return None


class ActivityEvent(BaseModel):
    """One permitted activity observation with provenance and consent scope."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # JSON key stays "schema" (contract); the attribute avoids shadowing
    # BaseModel.schema. Always dump with by_alias=True (see to_json_dict).
    schema_version: str = Field(default=ACTIVITY_EVENT_SCHEMA, alias="schema")
    event_id: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    grant_id: str = Field(..., min_length=1)
    observed_at: Optional[datetime] = Field(
        default=None,
        description="Source observation time; None means genuinely unknown.",
    )
    received_at: datetime = Field(default_factory=_utcnow)
    source_seq: Optional[int] = Field(default=None, ge=0)
    clock_domain: Optional[str] = Field(default=None)
    kind: ActivityKind = Field(...)
    app: str = Field(..., min_length=1)
    window_title: Optional[str] = Field(default=None)
    uri: Optional[str] = Field(default=None)
    foreground: bool = Field(default=True)
    payload: Dict[str, Any] = Field(default_factory=dict)
    redaction_labels: List[str] = Field(default_factory=list)
    synthetic: bool = Field(default=False)

    @field_validator("schema_version")
    @classmethod
    def _check_schema(cls, value: str) -> str:
        if value != ACTIVITY_EVENT_SCHEMA:
            raise ValueError(f"unsupported activity schema {value!r}")
        return value

    def to_json_dict(self) -> Dict[str, Any]:
        """Canonical JSON dict (contract keys, e.g. "schema")."""
        return self.model_dump(mode="json", by_alias=True)

    @field_validator("source_id")
    @classmethod
    def _check_source(cls, value: str) -> str:
        if not value.startswith(ACTIVITY_SOURCE_PREFIX):
            raise ValueError(
                f"source_id {value!r} is outside the activity namespace "
                f"{ACTIVITY_SOURCE_PREFIX!r}"
            )
        return value

    def idempotency_key(self) -> str:
        return f"{self.source_id}\u0000{self.event_id}"

    def content_identity(self) -> Optional[ContentIdentity]:
        return canonical_content_identity(self.uri, self.window_title, self.payload)

    def content_hash(self) -> str:
        canonical = self.to_json_dict()
        # received_at is transport metadata, not content: retries must hash equal.
        canonical.pop("received_at", None)
        blob = json.dumps(canonical, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # -- RawSignalEvent bridge (existing pipeline path, no schema change) --

    def to_raw_signal_event(self) -> RawSignalEvent:
        """Map onto the existing volatile signal for the factory pump."""
        if self.uri and self.uri.startswith(("http://", "https://")):
            source_type = SourceType.BROWSER
        elif self.kind in (ActivityKind.MEDIA_FOREGROUND, ActivityKind.MEDIA_BACKGROUND,
                            ActivityKind.MEDIA_MARKER) and not self.uri:
            source_type = SourceType.BROWSER
        else:
            source_type = SourceType.OS_WINDOW
        metadata: Dict[str, Any] = {
            "activity_schema": self.schema_version,
            "activity_source_id": self.source_id,
            "activity_grant_id": self.grant_id,
            "activity_kind": self.kind.value,
            "activity_foreground": self.foreground,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "clock_domain": self.clock_domain,
            "synthetic": self.synthetic,
        }
        if self.source_seq is not None:
            metadata["source_sequence"] = self.source_seq
        raw_payload: Dict[str, Any] = {
            "activity_event_id": self.event_id,
            "activity_payload": dict(self.payload),
            "redaction_labels": list(self.redaction_labels),
            # Full snapshot so main can reconstruct the event from committed
            # evidence (post-redaction) without shared-schema changes.
            "activity_event": self.to_json_dict(),
        }
        return RawSignalEvent(
            signal_id=self.event_id,
            source_type=source_type,
            adapter_id=self.source_id,
            captured_at=self.observed_at or self.received_at,
            app_identifier=self.app,
            window_title=self.window_title,
            target_uri=self.uri,
            raw_payload=raw_payload,
            metadata=metadata,
        )

    @classmethod
    def from_raw_signal_event(cls, signal: RawSignalEvent) -> "ActivityEvent":
        """Recover an ActivityEvent previously mapped with to_raw_signal_event."""
        metadata = dict(signal.metadata or {})
        if metadata.get("activity_schema") != ACTIVITY_EVENT_SCHEMA:
            raise ValueError("signal is not an activity-bridge event")
        raw_payload = dict(signal.raw_payload or {})
        snapshot = raw_payload.get("activity_event")
        if isinstance(snapshot, dict):
            return cls.model_validate(snapshot)
        observed_raw = metadata.get("observed_at")
        observed_at = None
        if isinstance(observed_raw, str) and observed_raw:
            try:
                observed_at = datetime.fromisoformat(observed_raw)
            except ValueError:
                observed_at = None
        source_seq = metadata.get("source_sequence")
        return cls(
            event_id=raw_payload.get("activity_event_id", signal.signal_id),
            source_id=str(metadata.get("activity_source_id", signal.adapter_id)),
            grant_id=str(metadata.get("activity_grant_id", "")),
            observed_at=observed_at,
            received_at=signal.captured_at,
            source_seq=source_seq if isinstance(source_seq, int) else None,
            clock_domain=metadata.get("clock_domain"),
            kind=ActivityKind(str(metadata.get("activity_kind", ActivityKind.WINDOW_FOREGROUND.value))),
            app=signal.app_identifier,
            window_title=signal.window_title,
            uri=signal.target_uri,
            foreground=bool(metadata.get("activity_foreground", True)),
            payload=dict(raw_payload.get("activity_payload", {})),
            redaction_labels=list(raw_payload.get("redaction_labels", [])),
            synthetic=bool(metadata.get("synthetic", False)),
        )

    @classmethod
    def from_evidence_record(cls, record: EvidenceRecord) -> "ActivityEvent":
        """Reconstruct from committed evidence (post-redaction content).

        Raises ValueError when the record carries no activity snapshot.
        Identity keys are stable; free-text fields reflect policy redaction.
        """
        snapshot = dict(record.sanitized_payload or {}).get("activity_event")
        if not isinstance(snapshot, dict):
            raise ValueError("evidence record carries no activity snapshot")
        return cls.model_validate(snapshot)
