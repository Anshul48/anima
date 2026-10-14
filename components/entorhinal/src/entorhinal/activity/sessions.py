"""Observation spans and stable logical sessions.

Layering (required by docs/plans/08-ACTIVITY-CONTINUITY-AND-DISCOVERY.md):

- An **observed span** is a maximal run of observations of one foreground (or
  background) context. A foreground transition supplies evidence for a span
  boundary; it never by itself creates or merges a logical session.
- A **logical session** groups spans that continue the same activity (same
  content identity + continuity evidence). Session ids are deterministic
  content hashes, stable across restarts and replay.

Required example: lecture 30m -> code 5m -> SAME lecture yields TWO logical
sessions over THREE observed spans, with active (not elapsed) time preserved
per session and pause/resume provenance retained.

Anti-merging rules (hard requirements, not tuning):

- App equality alone never merges. URL equality alone never merges. A gap
  length alone never merges and never splits.
- Unknown content identity never auto-merges.
- Linking requires: same canonical content key AND >= 1 continuity evidence
  AND no contradiction AND no user split between the spans.
- Position restart (same media, back to ~0 after progress) opens a NEW
  session; discovery may propose a ``same-content`` connection instead.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from entorhinal.activity.events import (
    ActivityEvent,
    ActivityKind,
    ContentIdentity,
)

#: Confidence weights for resumption evidence. Documented and versioned;
#: main must surface them in inspection views, not hide them.
EVIDENCE_WEIGHTS = {
    "position-continuity": 0.45,
    "resume-marker": 0.45,
    "title-fingerprint-match": 0.15,
    "same-file-continuity": 0.35,
    "app-context-continuity": 0.10,
}
LINK_THRESHOLD = 0.50
LINK_CONFIDENCE_CAP = 0.95

#: Position tolerances (seconds of media time).
POSITION_CONTINUITY_TOL_S = 45.0
RESTART_NEW_POSITION_S = 60.0
RESTART_OLD_PROGRESS_S = 300.0

#: Active-time accumulation cap between consecutive in-span observations.
#: Without heartbeats, idle silence must not be charged as active time.
DEFAULT_ACTIVE_STEP_CAP_S = 120.0

SESSION_BUILDER_VERSION = "session-builder/1"


def _hash12(*parts: str) -> str:
    blob = "\u0000".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class SpanProvenance(BaseModel):
    """How a span was segmented and timed (inspectable, no hidden inputs)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_basis: str = "observed"
    clock_notes: List[str] = Field(default_factory=list)
    pause_intervals_s: List[Tuple[float, float]] = Field(default_factory=list)
    active_step_cap_s: float = DEFAULT_ACTIVE_STEP_CAP_S
    capped_steps: int = 0
    marker_event_ids: List[str] = Field(default_factory=list)
    background: bool = False


class ObservedSpan(BaseModel):
    """One maximal run of same-context observations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    span_id: str
    start: datetime
    end: datetime
    active_seconds: float = Field(ge=0.0)
    elapsed_seconds: float = Field(ge=0.0)
    kind: str
    app: str
    uri: Optional[str] = None
    title_snapshot: Optional[str] = None
    background: bool = False
    content_identity: Optional[ContentIdentity] = None
    identity_status: str = "known"
    identity_note: str = ""
    first_position_s: Optional[float] = None
    last_position_s: Optional[float] = None
    event_ids: List[str] = Field(default_factory=list)
    provenance: SpanProvenance = Field(default_factory=SpanProvenance)


class ResumptionLink(BaseModel):
    """Evidence-backed link from one span to the next within a session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_span_id: str
    to_span_id: str
    evidence: List[str] = Field(default_factory=list)
    evidence_detail: Dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty_reasons: List[str] = Field(default_factory=list)
    user_confirmed: bool = False


class ConsideredLink(BaseModel):
    """A same-key pairing deliberately NOT linked, with reasons (why-not)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_span_id: str
    to_span_id: str
    evidence: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons_not_linked: List[str] = Field(default_factory=list)


class LogicalSession(BaseModel):
    """Stable logical activity session over one or more spans."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    span_ids: List[str] = Field(default_factory=list)
    first_start: Optional[datetime] = None
    last_end: Optional[datetime] = None
    total_active_seconds: float = Field(default=0.0, ge=0.0)
    total_elapsed_seconds: float = Field(default=0.0, ge=0.0)
    content_identity: Optional[ContentIdentity] = None
    identity_status: str = "known"
    resumption_links: List[ResumptionLink] = Field(default_factory=list)
    considered_but_not_linked: List[ConsideredLink] = Field(default_factory=list)
    correction_ids: List[str] = Field(default_factory=list)
    builder_version: str = SESSION_BUILDER_VERSION


class ActivityCorrection(BaseModel):
    """Explicit user override of session structure (outranks inference)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correction_id: str
    kind: str  # split-session | merge-sessions | reassign-span
    targets: Dict[str, Any] = Field(default_factory=dict)
    actor: str = "user"
    reason: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


def _event_sort_key(event: ActivityEvent) -> Tuple[str, int, str]:
    moment = event.observed_at or event.received_at
    seq = event.source_seq if event.source_seq is not None else 10**12
    return (_as_utc(moment).isoformat(), seq, event.event_id)


def _order_basis(event: ActivityEvent) -> Tuple[str, List[str]]:
    notes: List[str] = []
    if event.observed_at is None:
        basis = "received-fallback"
        notes.append("observed_at unknown; ordered by received_at")
    else:
        basis = "observed"
        if _as_utc(event.observed_at) > _as_utc(event.received_at):
            notes.append("clock-anomaly: observed_at after received_at")
    return basis, notes


def _span_key(event: ActivityEvent) -> Tuple[str, Optional[ContentIdentity]]:
    identity = event.content_identity()
    if identity is not None:
        return f"known:{identity.key}", identity
    return f"unknown:{event.app}:{event.kind.value}", None


def _is_foreground(event: ActivityEvent) -> bool:
    if event.kind in (ActivityKind.WINDOW_BACKGROUND, ActivityKind.MEDIA_BACKGROUND):
        return False
    return event.foreground


def _media_position(event: ActivityEvent) -> Optional[float]:
    value = event.payload.get("media_position_s")
    return float(value) if isinstance(value, (int, float)) else None


def _media_state(event: ActivityEvent) -> Optional[str]:
    value = event.payload.get("media_state")
    return str(value) if isinstance(value, str) else None


class SessionBuilder:
    """Deterministic span segmentation + logical session assignment.

    Usage: ``builder.ingest(events)`` then ``builder.sessions()`` /
    ``builder.spans()``; or ``SessionBuilder.rebuild(events, corrections)``
    for a pure deterministic rebuild (restart/replay path).
    """

    def __init__(self, active_step_cap_s: float = DEFAULT_ACTIVE_STEP_CAP_S) -> None:
        self._active_step_cap_s = active_step_cap_s
        self._events: Dict[str, ActivityEvent] = {}
        self._corrections: List[ActivityCorrection] = []
        self._spans: Dict[str, ObservedSpan] = {}
        self._sessions: Dict[str, LogicalSession] = {}
        self._dirty = True

    # -- mutation ------------------------------------------------------

    def ingest(self, events: List[ActivityEvent]) -> None:
        for event in events:
            key = event.idempotency_key()
            existing = self._events.get(key)
            if existing is not None:
                if existing.content_hash() != event.content_hash():
                    raise ValueError(
                        f"event identity conflict for {event.source_id}/{event.event_id}"
                    )
                continue
            self._events[key] = event
        self._dirty = True

    def remove_events(self, idempotency_keys: List[str]) -> int:
        removed = 0
        for key in idempotency_keys:
            if self._events.pop(key, None) is not None:
                removed += 1
        self._dirty = True
        return removed

    def apply_correction(self, correction: ActivityCorrection) -> List[LogicalSession]:
        if correction.kind not in ("split-session", "merge-sessions", "reassign-span"):
            raise ValueError(f"unknown correction kind {correction.kind!r}")
        self._corrections.append(correction)
        self._corrections.sort(key=lambda c: (c.created_at.isoformat(), c.correction_id))
        self._dirty = True
        self._ensure_built()
        for dropped in self.dropped_corrections():
            if dropped["correction_id"] == correction.correction_id:
                raise ValueError(f"correction not applicable: {dropped['reason']}")
        touched = [
            s for s in self._sessions.values()
            if correction.correction_id in s.correction_ids
        ]
        return sorted(touched, key=lambda s: s.session_id)

    @classmethod
    def rebuild(
        cls,
        events: List[ActivityEvent],
        corrections: Optional[List[ActivityCorrection]] = None,
        active_step_cap_s: float = DEFAULT_ACTIVE_STEP_CAP_S,
    ) -> "SessionBuilder":
        builder = cls(active_step_cap_s=active_step_cap_s)
        builder.ingest(events)
        for correction in corrections or []:
            builder._corrections.append(correction)
        builder._corrections.sort(key=lambda c: (c.created_at.isoformat(), c.correction_id))
        builder._dirty = True
        builder._ensure_built()
        return builder

    # -- accessors -----------------------------------------------------

    def spans(self) -> List[ObservedSpan]:
        self._ensure_built()
        return sorted(self._spans.values(), key=lambda s: (s.start.isoformat(), s.span_id))

    def sessions(self) -> List[LogicalSession]:
        self._ensure_built()
        return sorted(
            self._sessions.values(),
            key=lambda s: ((s.first_start.isoformat() if s.first_start else ""), s.session_id),
        )

    def span(self, span_id: str) -> Optional[ObservedSpan]:
        self._ensure_built()
        return self._spans.get(span_id)

    def session(self, session_id: str) -> Optional[LogicalSession]:
        self._ensure_built()
        return self._sessions.get(session_id)

    def corrections(self) -> List[ActivityCorrection]:
        return list(self._corrections)

    def events(self) -> List[ActivityEvent]:
        return sorted(self._events.values(), key=_event_sort_key)

    # -- build ---------------------------------------------------------

    def _ensure_built(self) -> None:
        if self._dirty:
            self._build()
            # Corrections outrank inference and replay in order on every build,
            # so restart/replay plus the same correction log yields the same
            # sessions. Corrections referencing deleted spans/sessions are
            # dropped with a recorded note instead of failing the rebuild.
            surviving: List[ActivityCorrection] = []
            self._dropped_corrections: List[Dict[str, str]] = []
            for correction in self._corrections:
                try:
                    if correction.kind == "split-session":
                        self._apply_split(correction)
                    elif correction.kind == "merge-sessions":
                        self._apply_merge(correction)
                    elif correction.kind == "reassign-span":
                        self._apply_reassign(correction)
                    surviving.append(correction)
                except ValueError as exc:
                    self._dropped_corrections.append(
                        {"correction_id": correction.correction_id, "reason": str(exc)}
                    )
            self._corrections = surviving
            self._dirty = False

    def dropped_corrections(self) -> List[Dict[str, str]]:
        self._ensure_built()
        return list(getattr(self, "_dropped_corrections", []))

    def _build(self) -> None:
        ordered = sorted(self._events.values(), key=_event_sort_key)
        self._spans = self._segment_spans(ordered)
        self._sessions = self._assign_sessions()

    def _segment_spans(self, ordered: List[ActivityEvent]) -> Dict[str, ObservedSpan]:
        spans: Dict[str, ObservedSpan] = {}
        # Two open runs: foreground and background interleave independently.
        open_runs: Dict[bool, Dict[str, Any]] = {}

        def close_run(background: bool) -> None:
            run = open_runs.pop(background, None)
            if run is None:
                return
            span = self._finalize_run(run)
            spans[span.span_id] = span

        for event in ordered:
            background = not _is_foreground(event)
            if event.kind in (ActivityKind.MEDIA_MARKER, ActivityKind.RESUME_MARKER,
                              ActivityKind.INPUT_MARKER, ActivityKind.HEARTBEAT):
                self._attach_marker(event, background, open_runs, spans)
                continue
            key, identity = _span_key(event)
            run = open_runs.get(background)
            if run is None or run["key"] != key:
                close_run(background)
                open_runs[background] = {
                    "key": key,
                    "identity": identity,
                    "background": background,
                    "events": [event],
                    "kind": event.kind.value,
                    "app": event.app,
                    "uri": event.uri,
                }
            else:
                run["events"].append(event)
                if event.uri and not run["uri"]:
                    run["uri"] = event.uri

        close_run(False)
        close_run(True)
        # Marker-only runs created via _attach_marker are already in spans.
        return spans

    def _attach_marker(
        self,
        event: ActivityEvent,
        background: bool,
        open_runs: Dict[bool, Dict[str, Any]],
        spans: Dict[str, ObservedSpan],
    ) -> None:
        key, identity = _span_key(event)
        # Prefer the open run with the same key (either plane). A marker with
        # known identity must NEVER join a different-key run (that would mix
        # provenances, e.g. a lecture resume marker inside a code span); it
        # opens its own run instead. Identity-less markers (heartbeats,
        # input counts) attach to the open run on their plane.
        for plane in (background, not background):
            run = open_runs.get(plane)
            if run is not None and run["key"] == key:
                run["events"].append(event)
                return
        if identity is None:
            run = open_runs.get(background)
            if run is not None:
                run["events"].append(event)
                return
        # The marker's key starts a new run: close whatever was open on this
        # plane first so no observations are lost.
        displaced = open_runs.pop(background, None)
        if displaced is not None:
            closed = self._finalize_run(displaced)
            spans[closed.span_id] = closed
        open_runs[background] = {
            "key": key,
            "identity": identity,
            "background": background,
            "events": [event],
            "kind": event.kind.value,
            "app": event.app,
            "uri": event.uri,
        }

    def _finalize_run(self, run: Dict[str, Any]) -> ObservedSpan:
        events: List[ActivityEvent] = sorted(run["events"], key=_event_sort_key)
        first = events[0]
        last = events[-1]
        start = _as_utc(first.observed_at or first.received_at)
        end = _as_utc(last.observed_at or last.received_at)
        if end < start:
            start, end = end, start
        elapsed = max(0.0, (end - start).total_seconds())

        clock_notes: List[str] = []
        bases = set()
        for event in events:
            basis, notes = _order_basis(event)
            bases.add(basis)
            clock_notes.extend(n for n in notes if n not in clock_notes)
        order_basis = "observed" if bases == {"observed"} else "mixed:" + "+".join(sorted(bases))

        # Pause intervals from explicit markers; active time excludes them.
        pause_intervals: List[Tuple[float, float]] = []
        paused_since: Optional[datetime] = None
        marker_ids: List[str] = []
        for event in events:
            if event.kind == ActivityKind.MEDIA_MARKER:
                marker_ids.append(event.event_id)
                state = _media_state(event)
                moment = _as_utc(event.observed_at or event.received_at)
                if state == "paused" and paused_since is None:
                    paused_since = moment
                elif state in ("playing", "resumed") and paused_since is not None:
                    if moment > paused_since:
                        pause_intervals.append(
                            ((paused_since - start).total_seconds(),
                             (moment - start).total_seconds())
                        )
                    paused_since = None
            elif event.kind == ActivityKind.RESUME_MARKER:
                marker_ids.append(event.event_id)
        if paused_since is not None and end > paused_since:
            pause_intervals.append(
                ((paused_since - start).total_seconds(), (end - start).total_seconds())
            )

        # Active time: capped steps between consecutive observations, minus pauses.
        active = 0.0
        capped = 0
        moments = [_as_utc(e.observed_at or e.received_at) for e in events]
        for prev, cur in zip(moments, moments[1:]):
            step = max(0.0, (cur - prev).total_seconds())
            if step > self._active_step_cap_s:
                capped += 1
                step = self._active_step_cap_s
            active += step
        if len(moments) == 1:
            active = 0.0
        paused_total = sum(b - a for a, b in pause_intervals)
        active = max(0.0, active - paused_total)

        positions = [_media_position(e) for e in events]
        positions = [p for p in positions if p is not None]

        identity: Optional[ContentIdentity] = run["identity"]
        if identity is None:
            identity_status = "unknown"
            identity_note = (
                f"no content identity derivable from app={run['app']!r} "
                f"uri={run['uri']!r}; never auto-merged"
            )
        else:
            identity_status = "known"
            identity_note = ""

        span_id = "actspan_" + _hash12(
            first.source_id, first.event_id, start.isoformat(), run["key"]
        )
        title_snapshot: Optional[str] = None
        for event in events:
            if event.window_title:
                title_snapshot = event.window_title
                break
        return ObservedSpan(
            span_id=span_id,
            start=start,
            end=end,
            active_seconds=round(active, 3),
            elapsed_seconds=round(elapsed, 3),
            kind=run["kind"],
            app=run["app"],
            uri=run["uri"],
            title_snapshot=title_snapshot,
            background=bool(run["background"]),
            content_identity=identity,
            identity_status=identity_status,
            identity_note=identity_note,
            first_position_s=positions[0] if positions else None,
            last_position_s=positions[-1] if positions else None,
            event_ids=[e.event_id for e in events],
            provenance=SpanProvenance(
                order_basis=order_basis,
                clock_notes=sorted(clock_notes),
                pause_intervals_s=[(round(a, 3), round(b, 3)) for a, b in pause_intervals],
                active_step_cap_s=self._active_step_cap_s,
                capped_steps=capped,
                marker_event_ids=marker_ids,
                background=bool(run["background"]),
            ),
        )

    # -- session assignment --------------------------------------------

    def _assign_sessions(self) -> Dict[str, LogicalSession]:
        ordered = sorted(self._spans.values(), key=lambda s: (s.start.isoformat(), s.span_id))
        sessions: Dict[str, LogicalSession] = {}
        # content key -> session ids (in creation order); user splits can fork keys.
        key_index: Dict[str, List[str]] = {}
        # user-split pairs that must never relink: frozenset({span_a, span_b}) boundaries.
        split_boundaries: set[frozenset[str]] = set()
        for correction in self._corrections:
            if correction.kind == "split-session":
                boundary = correction.targets.get("boundary_span_ids", [])
                if len(boundary) == 2:
                    split_boundaries.add(frozenset(boundary))

        for span in ordered:
            if span.identity_status != "known" or span.content_identity is None:
                sessions[self._new_session_id(span)] = self._singleton_session(span)
                continue
            key = span.content_identity.key
            candidates = [sessions[sid] for sid in key_index.get(key, []) if sid in sessions]
            linked = False
            best_considered: Optional[ConsideredLink] = None
            for session in reversed(candidates):
                prev_span = self._spans[session.span_ids[-1]]
                if frozenset({prev_span.span_id, span.span_id}) in split_boundaries:
                    best_considered = ConsideredLink(
                        from_span_id=prev_span.span_id,
                        to_span_id=span.span_id,
                        reasons_not_linked=["user split between these spans"],
                    )
                    continue
                link = self._evaluate_link(prev_span, span)
                if link is not None:
                    sessions[session.session_id] = self._extend_session(session, span, link)
                    linked = True
                    break
                best_considered = self._considered_link(prev_span, span)
            if not linked:
                session = self._singleton_session(span)
                if best_considered is not None:
                    session = session.model_copy(
                        update={"considered_but_not_linked": [best_considered]}
                    )
                sessions[session.session_id] = session
                key_index.setdefault(key, []).append(session.session_id)
            else:
                # key already indexed; nothing to add.
                pass
        return sessions

    def _new_session_id(self, span: ObservedSpan) -> str:
        key = span.content_identity.key if span.content_identity else "unknown"
        return "actsess_" + _hash12(key, span.span_id, SESSION_BUILDER_VERSION)

    def _singleton_session(self, span: ObservedSpan) -> LogicalSession:
        return LogicalSession(
            session_id=self._new_session_id(span),
            span_ids=[span.span_id],
            first_start=span.start,
            last_end=span.end,
            total_active_seconds=span.active_seconds,
            total_elapsed_seconds=span.elapsed_seconds,
            content_identity=span.content_identity,
            identity_status=span.identity_status,
        )

    def _extend_session(
        self, session: LogicalSession, span: ObservedSpan, link: ResumptionLink
    ) -> LogicalSession:
        span_ids = session.span_ids + [span.span_id]
        first_start = session.first_start
        if first_start is None or span.start < first_start:
            first_start = span.start
        last_end = session.last_end
        if last_end is None or span.end > last_end:
            last_end = span.end
        return session.model_copy(
            update={
                "span_ids": span_ids,
                "first_start": first_start,
                "last_end": last_end,
                "total_active_seconds": round(
                    session.total_active_seconds + span.active_seconds, 3
                ),
                "total_elapsed_seconds": round(
                    session.total_elapsed_seconds + span.elapsed_seconds, 3
                ),
                "resumption_links": session.resumption_links + [link],
            }
        )

    def _evaluate_link(self, prev: ObservedSpan, nxt: ObservedSpan) -> Optional[ResumptionLink]:
        """Return a link iff continuity evidence clears the threshold."""
        assert prev.content_identity is not None and nxt.content_identity is not None
        if prev.content_identity.key != nxt.content_identity.key:
            return None
        evidence: List[str] = []
        detail: Dict[str, str] = {}
        uncertainty: List[str] = []

        kind = prev.content_identity.kind
        if kind == "media":
            # Position continuity: resumed near where it paused.
            if prev.last_position_s is not None and nxt.first_position_s is not None:
                drift = abs(nxt.first_position_s - prev.last_position_s)
                if drift <= POSITION_CONTINUITY_TOL_S:
                    evidence.append("position-continuity")
                    detail["position-continuity"] = (
                        f"resumed at {nxt.first_position_s:.0f}s vs paused "
                        f"{prev.last_position_s:.0f}s (drift {drift:.0f}s)"
                    )
                elif (
                    nxt.first_position_s <= RESTART_NEW_POSITION_S
                    and prev.last_position_s >= RESTART_OLD_PROGRESS_S
                ):
                    # Restart from the beginning: a NEW viewing, not a resume.
                    uncertainty.append(
                        "position-restart: same media restarted from "
                        f"{nxt.first_position_s:.0f}s after reaching "
                        f"{prev.last_position_s:.0f}s; kept as separate session"
                    )
                    return None
                else:
                    uncertainty.append(
                        f"position discontinuity: resumed at {nxt.first_position_s:.0f}s "
                        f"vs paused {prev.last_position_s:.0f}s"
                    )
            else:
                uncertainty.append("no media position evidence on one or both spans")
            # Title fingerprint corroboration (never sufficient alone).
            fp_prev = prev.content_identity.fingerprint
            fp_nxt = nxt.content_identity.fingerprint
            if fp_prev and fp_nxt:
                if fp_prev == fp_nxt:
                    evidence.append("title-fingerprint-match")
                    detail["title-fingerprint-match"] = f"both {fp_prev}"
                else:
                    uncertainty.append("title fingerprint differs between spans")
            # Explicit resume marker on the later span.
            if self._span_has_resume_marker(nxt):
                evidence.append("resume-marker")
                detail["resume-marker"] = "explicit resume-marker event on later span"
        elif kind in ("code", "document"):
            evidence.append("same-file-continuity")
            detail["same-file-continuity"] = f"same file key {prev.content_identity.key}"
            if prev.app == nxt.app:
                evidence.append("app-context-continuity")
                detail["app-context-continuity"] = f"same app {prev.app!r}"
            else:
                uncertainty.append(f"app changed from {prev.app!r} to {nxt.app!r}")
        else:  # pragma: no cover - future kinds stay conservative
            uncertainty.append(f"unsupported content kind {kind!r}")
            return None

        confidence = min(
            LINK_CONFIDENCE_CAP, sum(EVIDENCE_WEIGHTS[e] for e in evidence)
        )
        if confidence < LINK_THRESHOLD:
            return None
        if confidence < LINK_CONFIDENCE_CAP:
            uncertainty.append(
                f"heuristic link at confidence {confidence:.2f}; user correction outranks it"
            )
        return ResumptionLink(
            from_span_id=prev.span_id,
            to_span_id=nxt.span_id,
            evidence=evidence,
            evidence_detail=detail,
            confidence=round(confidence, 3),
            uncertainty_reasons=uncertainty,
        )

    def _considered_link(self, prev: ObservedSpan, nxt: ObservedSpan) -> ConsideredLink:
        evidence: List[str] = []
        if prev.content_identity and nxt.content_identity:
            if prev.content_identity.key == nxt.content_identity.key:
                evidence.append("same-content-key")
            fp_prev = prev.content_identity.fingerprint
            fp_nxt = nxt.content_identity.fingerprint
            if fp_prev and fp_nxt and fp_prev == fp_nxt:
                evidence.append("title-fingerprint-match")
        if self._span_has_resume_marker(nxt):
            evidence.append("resume-marker")
        reasons = [
            "same content key but continuity evidence below link threshold; "
            "kept separate (correctable via merge-sessions)"
        ]
        if prev.last_position_s is not None and nxt.first_position_s is not None:
            reasons.append(
                f"positions {prev.last_position_s:.0f}s -> {nxt.first_position_s:.0f}s "
                "do not show continuity"
            )
        return ConsideredLink(
            from_span_id=prev.span_id,
            to_span_id=nxt.span_id,
            evidence=evidence,
            confidence=0.0,
            reasons_not_linked=reasons,
        )

    def _span_has_resume_marker(self, span: ObservedSpan) -> bool:
        for event_id in span.provenance.marker_event_ids:
            for event in self._events.values():
                if event.event_id == event_id and event.kind == ActivityKind.RESUME_MARKER:
                    return True
        # Also accept resume markers embedded as media markers with resume state.
        for event in self._events.values():
            if event.event_id in span.event_ids and event.kind == ActivityKind.MEDIA_MARKER:
                if _media_state(event) in ("resumed",):
                    return True
        return False

    # -- corrections (outrank inference; replayed on rebuild) -------------

    def _apply_split(self, correction: ActivityCorrection) -> List[LogicalSession]:
        session_id = str(correction.targets.get("session_id", ""))
        at_span_id = str(correction.targets.get("at_span_id", ""))
        session = self._sessions.get(session_id)
        if session is None or at_span_id not in session.span_ids:
            raise ValueError("split-session targets unknown session/span")
        idx = session.span_ids.index(at_span_id)
        if idx == 0:
            raise ValueError("split-session at first span would leave an empty session")
        left_ids = session.span_ids[:idx]
        right_ids = session.span_ids[idx:]
        left = self._rebuild_session_from_spans(
            left_ids, correction.correction_id, session.resumption_links, session
        )
        right = self._rebuild_session_from_spans(
            right_ids, correction.correction_id, session.resumption_links, session
        )
        del self._sessions[session_id]
        self._sessions[left.session_id] = left
        self._sessions[right.session_id] = right
        return [left, right]

    def _rebuild_session_from_spans(
        self,
        span_ids: List[str],
        correction_id: str,
        links: List[ResumptionLink],
        template: LogicalSession,
    ) -> LogicalSession:
        spans = [self._spans[sid] for sid in span_ids]
        kept_links = [
            link for link in links
            if link.from_span_id in set(span_ids) and link.to_span_id in set(span_ids)
        ]
        first_start = min(s.start for s in spans)
        last_end = max(s.end for s in spans)
        session_id = "actsess_" + _hash12(
            "split", span_ids[0], correction_id, SESSION_BUILDER_VERSION
        )
        return LogicalSession(
            session_id=session_id,
            span_ids=list(span_ids),
            first_start=first_start,
            last_end=last_end,
            total_active_seconds=round(sum(s.active_seconds for s in spans), 3),
            total_elapsed_seconds=round(sum(s.elapsed_seconds for s in spans), 3),
            content_identity=template.content_identity,
            identity_status=template.identity_status,
            resumption_links=kept_links,
            correction_ids=template.correction_ids + [correction_id],
        )

    def _apply_merge(self, correction: ActivityCorrection) -> LogicalSession:
        session_ids = [str(s) for s in correction.targets.get("session_ids", [])]
        if len(session_ids) < 2:
            raise ValueError("merge-sessions needs at least two session ids")
        sessions = [self._sessions.get(sid) for sid in session_ids]
        if any(s is None for s in sessions):
            raise ValueError("merge-sessions targets unknown session")
        assert all(s is not None for s in sessions)
        ordered_spans = sorted(
            {sid for s in sessions for sid in s.span_ids},  # type: ignore[union-attr]
            key=lambda sid: (self._spans[sid].start.isoformat(), sid),
        )
        links: List[ResumptionLink] = []
        for left_id, right_id in zip(ordered_spans, ordered_spans[1:]):
            links.append(
                ResumptionLink(
                    from_span_id=left_id,
                    to_span_id=right_id,
                    evidence=["user-confirmed-merge"],
                    evidence_detail={"user-confirmed-merge": correction.correction_id},
                    confidence=1.0,
                    uncertainty_reasons=[],
                    user_confirmed=True,
                )
            )
        spans = [self._spans[sid] for sid in ordered_spans]
        merged_id = "actsess_" + _hash12(
            "merge", "+".join(sorted(session_ids)), correction.correction_id
        )
        first = sessions[0]
        assert first is not None
        merged = LogicalSession(
            session_id=merged_id,
            span_ids=ordered_spans,
            first_start=min(s.start for s in spans),
            last_end=max(s.end for s in spans),
            total_active_seconds=round(sum(s.active_seconds for s in spans), 3),
            total_elapsed_seconds=round(sum(s.elapsed_seconds for s in spans), 3),
            content_identity=first.content_identity,
            identity_status=first.identity_status,
            resumption_links=links,
            correction_ids=[correction.correction_id],
        )
        for sid in session_ids:
            self._sessions.pop(sid, None)
        self._sessions[merged.session_id] = merged
        return merged

    def _apply_reassign(self, correction: ActivityCorrection) -> LogicalSession:
        span_id = str(correction.targets.get("span_id", ""))
        to_session_id = str(correction.targets.get("to_session_id", ""))
        span = self._spans.get(span_id)
        target = self._sessions.get(to_session_id)
        if span is None or target is None:
            raise ValueError("reassign-span targets unknown span/session")
        for session in list(self._sessions.values()):
            if span_id in session.span_ids and session.session_id != to_session_id:
                remaining = [sid for sid in session.span_ids if sid != span_id]
                if not remaining:
                    del self._sessions[session.session_id]
                else:
                    kept = [
                        link for link in session.resumption_links
                        if link.from_span_id != span_id and link.to_span_id != span_id
                    ]
                    spans = [self._spans[sid] for sid in remaining]
                    self._sessions[session.session_id] = session.model_copy(
                        update={
                            "span_ids": remaining,
                            "first_start": min(s.start for s in spans),
                            "last_end": max(s.end for s in spans),
                            "total_active_seconds": round(
                                sum(s.active_seconds for s in spans), 3
                            ),
                            "total_elapsed_seconds": round(
                                sum(s.elapsed_seconds for s in spans), 3
                            ),
                            "resumption_links": kept,
                            "correction_ids": session.correction_ids + [correction.correction_id],
                        }
                    )
        ordered = sorted(
            target.span_ids + [span_id],
            key=lambda sid: (self._spans[sid].start.isoformat(), sid),
        )
        spans = [self._spans[sid] for sid in ordered]
        updated = target.model_copy(
            update={
                "span_ids": ordered,
                "first_start": min(s.start for s in spans),
                "last_end": max(s.end for s in spans),
                "total_active_seconds": round(sum(s.active_seconds for s in spans), 3),
                "total_elapsed_seconds": round(sum(s.elapsed_seconds for s in spans), 3),
                "correction_ids": target.correction_ids + [correction.correction_id],
            }
        )
        self._sessions[to_session_id] = updated
        return updated
