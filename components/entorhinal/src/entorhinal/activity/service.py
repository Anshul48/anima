"""Activity service: ingest, sessions, labels, discovery, corrections, deletion.

``ActivityService`` is the component main wires into durable serving, user
inspection, and controls. It owns derived state (spans, sessions, labels,
connections) built deterministically from admitted ``ActivityEvent``s plus
user corrections/decisions. Source evidence stays in main's store via the
``RawSignalEvent`` bridge; this service additionally persists its own
snapshot files (events + corrections + decisions + tombstones) under a
configured directory until main wires durable serving.

Idempotency: ingest is keyed by ``(source_id, event_id)``. Exact re-ingest
returns the original outcome; same key with changed content is a conflict.
Deletion tombstones events and rebuilds derived state; nothing derived
survives its evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from entorhinal.activity.classify import (
    ActivityLabel,
    LabelCorrection,
    LocalActivityClassifier,
)
from entorhinal.activity.discovery import (
    ConsideredPair,
    Connection,
    DiscoveryEngine,
)
from entorhinal.activity.events import ActivityEvent
from entorhinal.activity.grants import GrantStore
from entorhinal.activity.sessions import (
    ActivityCorrection,
    LogicalSession,
    ObservedSpan,
    SessionBuilder,
)
from entorhinal.schemas.models import EvidenceRecord

ACTIVITY_SERVICE_VERSION = "activity-service/1"


class IngestOutcome(BaseModel):
    """Result of ingesting one activity event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str  # admitted | duplicate | conflict | denied | rejected
    source_id: str = ""
    event_id: str = ""
    reason: str = ""


class TombstoneEntry(BaseModel):
    """Record of one deleted activity event (audit, not content)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tombstone_id: str
    source_id: str
    event_id: str
    reason: str
    deleted_at: datetime


class DeletionResult(BaseModel):
    """Outcome of a deletion request (cascade included)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deleted_events: int
    tombstone_ids: List[str] = Field(default_factory=list)
    dropped_corrections: List[Dict[str, str]] = Field(default_factory=list)
    remaining_events: int = 0
    remaining_sessions: int = 0


class SessionView(BaseModel):
    """Full inspection view of one session (spans + labels + connections)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session: LogicalSession
    spans: List[ObservedSpan] = Field(default_factory=list)
    session_label: Optional[ActivityLabel] = None
    span_labels: List[ActivityLabel] = Field(default_factory=list)
    connections: List[Connection] = Field(default_factory=list)


class SessionExplanation(BaseModel):
    """Why a session is shaped the way it is (links + non-links + labels)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    summary: str
    resumption_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    why_not_linked: List[Dict[str, Any]] = Field(default_factory=list)
    label_basis: List[str] = Field(default_factory=list)
    label_uncertainty: List[str] = Field(default_factory=list)
    corrections: List[str] = Field(default_factory=list)


def _tombstone_id(source_id: str, event_id: str, reason: str) -> str:
    digest = hashlib.sha256(
        f"{source_id}\u0000{event_id}\u0000{reason}".encode("utf-8")
    ).hexdigest()[:12]
    return f"acttomb_{digest}"


class ActivityService:
    """Integrated activity component: ingest -> sessions -> labels -> links."""

    def __init__(
        self,
        grants: Optional[GrantStore] = None,
        snapshot_dir: Optional[Path] = None,
        active_step_cap_s: float = 120.0,
    ) -> None:
        self._grants = grants if grants is not None else GrantStore()
        self._snapshot_dir = Path(snapshot_dir) if snapshot_dir else None
        self._builder = SessionBuilder(active_step_cap_s=active_step_cap_s)
        self._classifier = LocalActivityClassifier()
        self._discovery = DiscoveryEngine()
        self._tombstones: Dict[str, TombstoneEntry] = {}
        self._admitted_keys: Dict[str, str] = {}  # idempotency key -> content hash
        self._labels: List[ActivityLabel] = []
        self._connections: List[Connection] = []
        self._considered: List[ConsideredPair] = []
        self._derived_dirty = True

    # -- ingest --------------------------------------------------------

    @property
    def grants(self) -> GrantStore:
        return self._grants

    def ingest(self, event: ActivityEvent) -> IngestOutcome:
        allowed, reason = self._grants.check(event)
        if not allowed:
            return IngestOutcome(
                status="denied", source_id=event.source_id,
                event_id=event.event_id, reason=reason,
            )
        key = event.idempotency_key()
        content_hash = event.content_hash()
        prior = self._admitted_keys.get(key)
        if prior is not None:
            if prior != content_hash:
                return IngestOutcome(
                    status="conflict", source_id=event.source_id,
                    event_id=event.event_id,
                    reason="event identity reused with changed content",
                )
            return IngestOutcome(
                status="duplicate", source_id=event.source_id,
                event_id=event.event_id, reason="exact retry; original kept",
            )
        tombstoned = any(
            t.source_id == event.source_id and t.event_id == event.event_id
            for t in self._tombstones.values()
        )
        if tombstoned:
            return IngestOutcome(
                status="rejected", source_id=event.source_id,
                event_id=event.event_id, reason="rejected:event-tombstoned",
            )
        self._builder.ingest([event])
        self._admitted_keys[key] = content_hash
        self._derived_dirty = True
        return IngestOutcome(
            status="admitted", source_id=event.source_id,
            event_id=event.event_id, reason="admitted",
        )

    def ingest_many(self, events: List[ActivityEvent]) -> List[IngestOutcome]:
        return [self.ingest(event) for event in events]

    # -- derived state -------------------------------------------------

    def rebuild(self) -> None:
        """Rebuild all derived state deterministically (restart/replay path)."""
        spans = self._builder.spans()
        sessions = self._builder.sessions()
        span_labels = [self._classifier.classify_span(s) for s in spans]
        session_labels = [self._classifier.classify_session(s, spans) for s in sessions]
        self._labels = span_labels + session_labels
        self._connections, self._considered = self._discovery.discover(
            sessions, spans, session_labels
        )
        self._derived_dirty = False

    def _ensure_derived(self) -> None:
        if self._derived_dirty:
            self.rebuild()

    def spans(self) -> List[ObservedSpan]:
        self._ensure_derived()
        return self._builder.spans()

    def sessions(self) -> List[LogicalSession]:
        self._ensure_derived()
        return self._builder.sessions()

    def labels(self) -> List[ActivityLabel]:
        self._ensure_derived()
        return list(self._labels)

    def connections(self) -> List[Connection]:
        self._ensure_derived()
        return list(self._connections)

    def considered_pairs(self) -> List[ConsideredPair]:
        self._ensure_derived()
        return list(self._considered)

    def events(self) -> List[ActivityEvent]:
        return self._builder.events()

    # -- queries -------------------------------------------------------

    def list_sessions(
        self,
        activity: Optional[str] = None,
        identity_status: Optional[str] = None,
    ) -> List[LogicalSession]:
        self._ensure_derived()
        sessions = self._builder.sessions()
        if activity is not None:
            wanted = {lbl.target_id for lbl in self._labels
                      if lbl.target_kind == "session" and lbl.activity == activity}
            sessions = [s for s in sessions if s.session_id in wanted]
        if identity_status is not None:
            sessions = [s for s in sessions if s.identity_status == identity_status]
        return sessions

    def get_session_view(self, session_id: str) -> Optional[SessionView]:
        self._ensure_derived()
        session = self._builder.session(session_id)
        if session is None:
            return None
        by_id = {s.span_id: s for s in self._builder.spans()}
        spans = [by_id[sid] for sid in session.span_ids if sid in by_id]
        session_label = next(
            (lbl for lbl in self._labels
             if lbl.target_kind == "session" and lbl.target_id == session_id),
            None,
        )
        span_labels = [lbl for lbl in self._labels
                       if lbl.target_kind == "span" and lbl.target_id in set(session.span_ids)]
        connections = [c for c in self._connections
                       if c.a_session_id == session_id or c.b_session_id == session_id]
        return SessionView(
            session=session, spans=spans, session_label=session_label,
            span_labels=span_labels, connections=connections,
        )

    def explain_session(self, session_id: str) -> Optional[SessionExplanation]:
        view = self.get_session_view(session_id)
        if view is None:
            return None
        session = view.session
        summary = (
            f"session {session_id}: {len(session.span_ids)} span(s), "
            f"{session.total_active_seconds:.0f}s active / "
            f"{session.total_elapsed_seconds:.0f}s elapsed"
        )
        if session.content_identity is not None:
            summary += f", content {session.content_identity.key}"
        else:
            summary += ", identity unknown (never auto-merged)"
        resumption = [
            {"from": link.from_span_id, "to": link.to_span_id,
             "evidence": link.evidence_detail, "confidence": link.confidence,
             "uncertainty": link.uncertainty_reasons,
             "user_confirmed": link.user_confirmed}
            for link in session.resumption_links
        ]
        why_not = [
            {"from": c.from_span_id, "to": c.to_span_id,
             "evidence": c.evidence, "reasons": c.reasons_not_linked}
            for c in session.considered_but_not_linked
        ]
        label_basis = list(view.session_label.evidence) if view.session_label else []
        label_uncertainty = list(view.session_label.uncertainty_reasons) if view.session_label else []
        return SessionExplanation(
            session_id=session_id, summary=summary,
            resumption_evidence=resumption, why_not_linked=why_not,
            label_basis=label_basis, label_uncertainty=label_uncertainty,
            corrections=list(session.correction_ids),
        )

    # -- corrections ---------------------------------------------------

    def submit_session_correction(self, correction: ActivityCorrection) -> List[LogicalSession]:
        touched = self._builder.apply_correction(correction)
        self._derived_dirty = True
        return touched

    def submit_label_correction(self, correction: LabelCorrection) -> None:
        self._classifier.apply_correction(correction)
        self._derived_dirty = True

    def decide_connection(self, connection_id: str, accept: bool, actor: str = "user") -> Connection:
        self._ensure_derived()
        updated = self._discovery.decide(connection_id, accept, actor)
        self._derived_dirty = True
        return updated

    def session_corrections(self) -> List[ActivityCorrection]:
        return self._builder.corrections()

    # -- deletion ------------------------------------------------------

    def request_deletion(
        self,
        session_ids: Optional[List[str]] = None,
        time_start: Optional[datetime] = None,
        time_end: Optional[datetime] = None,
        app_substring: Optional[str] = None,
        domain: Optional[str] = None,
        reason: str = "user deletion request",
    ) -> DeletionResult:
        """Tombstone matching events and cascade derived state via rebuild."""
        self._ensure_derived()
        span_ids: Optional[set[str]] = None
        if session_ids is not None:
            span_ids = set()
            for session_id in session_ids:
                session = self._builder.session(session_id)
                if session is not None:
                    span_ids.update(session.span_ids)
        victims: List[ActivityEvent] = []
        for event in self._builder.events():
            moment = event.observed_at or event.received_at
            if time_start is not None and moment < time_start:
                continue
            if time_end is not None and moment > time_end:
                continue
            if app_substring is not None and app_substring.lower() not in event.app.lower():
                continue
            if domain is not None:
                try:
                    host = (urlparse(event.uri or "").hostname or "").lower()
                except Exception:
                    host = ""
                if domain.lower() != host and not host.endswith("." + domain.lower()):
                    continue
            if span_ids is not None:
                event_span = self._span_of_event(event.event_id)
                if event_span is None or event_span not in span_ids:
                    continue
            victims.append(event)
        now = datetime.now(timezone.utc)
        tombstone_ids: List[str] = []
        for event in victims:
            tombstone_id = _tombstone_id(event.source_id, event.event_id, reason)
            self._tombstones[event.idempotency_key()] = TombstoneEntry(
                tombstone_id=tombstone_id, source_id=event.source_id,
                event_id=event.event_id, reason=reason, deleted_at=now,
            )
            tombstone_ids.append(tombstone_id)
            self._admitted_keys.pop(event.idempotency_key(), None)
        self._builder.remove_events([v.idempotency_key() for v in victims])
        self._derived_dirty = True
        self._ensure_derived()
        return DeletionResult(
            deleted_events=len(victims),
            tombstone_ids=sorted(tombstone_ids),
            dropped_corrections=self._builder.dropped_corrections(),
            remaining_events=len(self._builder.events()),
            remaining_sessions=len(self._builder.sessions()),
        )

    def tombstones(self) -> List[TombstoneEntry]:
        return sorted(self._tombstones.values(), key=lambda t: t.tombstone_id)

    def _span_of_event(self, event_id: str) -> Optional[str]:
        for span in self._builder.spans():
            if event_id in span.event_ids:
                return span.span_id
        return None

    # -- snapshots (component-owned until main wires durable serving) ---

    def save_snapshot(self, directory: Optional[Path] = None) -> Path:
        target = Path(directory) if directory else self._snapshot_dir
        if target is None:
            raise ValueError("no snapshot directory configured")
        target.mkdir(parents=True, exist_ok=True)
        events = sorted(self._builder.events(), key=lambda e: (e.source_id, e.event_id))
        (target / "events.jsonl").write_text(
            "".join(json.dumps(e.to_json_dict(), sort_keys=True) + "\n" for e in events),
            encoding="utf-8",
        )
        (target / "session_corrections.json").write_text(
            json.dumps([c.model_dump(mode="json") for c in self._builder.corrections()],
                       indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (target / "label_corrections.json").write_text(
            json.dumps([c.model_dump(mode="json") for c in self._classifier.label_corrections()],
                       indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (target / "decisions.json").write_text(
            json.dumps([c.model_dump(mode="json") for c in self._discovery.decisions()],
                       indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (target / "tombstones.json").write_text(
            json.dumps([t.model_dump(mode="json") for t in self.tombstones()],
                       indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (target / "meta.json").write_text(
            json.dumps({"service_version": ACTIVITY_SERVICE_VERSION,
                        "saved_at": datetime.now(timezone.utc).isoformat(),
                        "event_count": len(events)}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load_snapshot(
        cls,
        directory: Path,
        grants: Optional[GrantStore] = None,
        active_step_cap_s: float = 120.0,
    ) -> "ActivityService":
        directory = Path(directory)
        service = cls(grants=grants, snapshot_dir=directory,
                      active_step_cap_s=active_step_cap_s)
        events_path = directory / "events.jsonl"
        if events_path.exists():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    event = ActivityEvent.model_validate(json.loads(line))
                    service._builder.ingest([event])
                    service._admitted_keys[event.idempotency_key()] = event.content_hash()
        corrections_path = directory / "session_corrections.json"
        if corrections_path.exists():
            for raw in json.loads(corrections_path.read_text(encoding="utf-8")):
                service._builder._corrections.append(ActivityCorrection.model_validate(raw))
            service._builder._corrections.sort(
                key=lambda c: (c.created_at.isoformat(), c.correction_id))
            service._builder._dirty = True
        labels_path = directory / "label_corrections.json"
        if labels_path.exists():
            for raw in json.loads(labels_path.read_text(encoding="utf-8")):
                service._classifier.apply_correction(LabelCorrection.model_validate(raw))
        decisions_path = directory / "decisions.json"
        pending_decisions: List[Connection] = []
        if decisions_path.exists():
            for raw in json.loads(decisions_path.read_text(encoding="utf-8")):
                pending_decisions.append(Connection.model_validate(raw))
        tombstones_path = directory / "tombstones.json"
        if tombstones_path.exists():
            for raw in json.loads(tombstones_path.read_text(encoding="utf-8")):
                entry = TombstoneEntry.model_validate(raw)
                service._tombstones[f"{entry.source_id}\u0000{entry.event_id}"] = entry
        service.rebuild()
        # Restore user decisions over rediscovered connections.
        for prior in pending_decisions:
            current = next(
                (c for c in service._connections if c.connection_id == prior.connection_id),
                None,
            )
            if current is not None and prior.status.value != "proposed":
                service._discovery._decisions[prior.connection_id] = current.model_copy(update={
                    "status": prior.status, "decided_by": prior.decided_by,
                    "decided_at": prior.decided_at,
                })
            elif prior.status.value != "proposed":
                service._discovery._decisions[prior.connection_id] = prior
        service._derived_dirty = True
        service.rebuild()
        return service

    # -- main-owned store path ------------------------------------------

    @classmethod
    def from_evidence_records(
        cls,
        records: List[EvidenceRecord],
        grants: Optional[GrantStore] = None,
        active_step_cap_s: float = 120.0,
    ) -> "ActivityService":
        """Build a service view from committed evidence (main's SQLite path).

        Records without an activity snapshot are skipped (counted in the
        returned service's load report, not raised).
        """
        service = cls(grants=grants, active_step_cap_s=active_step_cap_s)
        skipped = 0
        for record in records:
            if record.is_tombstone:
                skipped += 1
                continue
            try:
                event = ActivityEvent.from_evidence_record(record)
            except ValueError:
                skipped += 1
                continue
            service.ingest(event)
        service._load_skipped = skipped  # type: ignore[attr-defined]
        service.rebuild()
        return service

    @property
    def load_skipped(self) -> int:
        return int(getattr(self, "_load_skipped", 0))
