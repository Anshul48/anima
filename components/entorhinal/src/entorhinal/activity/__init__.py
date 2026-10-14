"""Entorhinal local activity capabilities (activity builder owns).

Tracking records, opt-in producers, stable logical sessions, local
classification, and connection discovery — all local-first, all
deterministic, none requiring Trace or remote inference.
"""

from entorhinal.activity.classify import (
    CLASSIFIER_RULE_VERSION,
    ActivityLabel,
    EntityHint,
    LabelCorrection,
    LocalActivityClassifier,
    extract_entities,
)
from entorhinal.activity.discovery import (
    DISCOVERY_RULE_VERSION,
    ConsideredPair,
    Connection,
    ConnectionKind,
    ConnectionStatus,
    DiscoveryEngine,
)
from entorhinal.activity.events import (
    ACTIVITY_EVENT_SCHEMA,
    ACTIVITY_SOURCE_PREFIX,
    ActivityEvent,
    ActivityKind,
    ContentIdentity,
    canonical_content_identity,
    canonical_media_id,
    title_fingerprint,
)
from entorhinal.activity.grants import GrantStore, SourceGrant
from entorhinal.activity.service import (
    ActivityService,
    DeletionResult,
    IngestOutcome,
    SessionView,
)
from entorhinal.activity.sessions import (
    LINK_CONFIDENCE_CAP,
    LINK_THRESHOLD,
    SESSION_BUILDER_VERSION,
    ActivityCorrection,
    ConsideredLink,
    LogicalSession,
    ObservedSpan,
    ResumptionLink,
    SessionBuilder,
    SpanProvenance,
)
from entorhinal.activity.trace_port import (
    NullTraceOrganizer,
    RecordingTraceOrganizer,
    TraceEnrichment,
    TraceOrganizerPort,
)

__all__ = [
    "ACTIVITY_EVENT_SCHEMA",
    "ACTIVITY_SOURCE_PREFIX",
    "ActivityCorrection",
    "ActivityEvent",
    "ActivityKind",
    "ActivityLabel",
    "ActivityService",
    "ConsideredLink",
    "ConsideredPair",
    "Connection",
    "ConnectionKind",
    "ConnectionStatus",
    "ContentIdentity",
    "DeletionResult",
    "DiscoveryEngine",
    "EntityHint",
    "GrantStore",
    "IngestOutcome",
    "LINK_CONFIDENCE_CAP",
    "LINK_THRESHOLD",
    "SESSION_BUILDER_VERSION",
    "CLASSIFIER_RULE_VERSION",
    "DISCOVERY_RULE_VERSION",
    "LabelCorrection",
    "LocalActivityClassifier",
    "LogicalSession",
    "NullTraceOrganizer",
    "ObservedSpan",
    "RecordingTraceOrganizer",
    "ResumptionLink",
    "SessionBuilder",
    "SessionView",
    "SourceGrant",
    "SpanProvenance",
    "TraceEnrichment",
    "TraceOrganizerPort",
    "canonical_content_identity",
    "canonical_media_id",
    "extract_entities",
    "title_fingerprint",
]
