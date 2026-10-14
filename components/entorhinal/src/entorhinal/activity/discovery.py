"""Local connection discovery across sessions and time.

Discovery proposes relationships between logical sessions from permitted
local evidence only. Every proposal carries its provenance (rule + source
span/event ids), confidence, and uncertainty reasons. Proposed connections
are hypotheses, never facts: the user accepts or rejects them, and rejected
pairs are never re-proposed.

Hard rule: bare temporal adjacency alone NEVER proposes a connection. A
considered-but-rejected record explains why when inspection asks.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from entorhinal.activity.classify import ActivityLabel
from entorhinal.activity.sessions import LogicalSession, ObservedSpan

DISCOVERY_RULE_VERSION = "discovery-rules/1"


class ConnectionKind(str, Enum):
    RESUME_OF = "resume-of"
    INTERRUPTED_BY = "interrupted-by"
    SAME_CONTENT = "same-content"
    SAME_PROJECT = "same-project"
    SAME_TOPIC = "same-topic"
    REFERENCE = "reference"
    TEMPORAL_ADJACENCY = "temporal-adjacency"


class ConnectionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Connection(BaseModel):
    """One discovered session relationship (proposed until accepted)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connection_id: str
    kind: ConnectionKind
    a_session_id: str
    b_session_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    provenance: Dict[str, str] = Field(default_factory=dict)
    status: ConnectionStatus = ConnectionStatus.PROPOSED
    uncertainty_reasons: List[str] = Field(default_factory=list)
    rule_version: str = DISCOVERY_RULE_VERSION
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None


class ConsideredPair(BaseModel):
    """A session pair examined but not connected, with the reason why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a_session_id: str
    b_session_id: str
    reason: str


def _connection_id(kind: str, a: str, b: str) -> str:
    first, second = sorted((a, b))
    digest = hashlib.sha256(
        f"{kind}\u0000{first}\u0000{second}\u0000{DISCOVERY_RULE_VERSION}".encode("utf-8")
    ).hexdigest()[:12]
    return f"actconn_{digest}"


def _spans_overlap(a: ObservedSpan, b: ObservedSpan) -> bool:
    return a.start < b.end and b.start < a.end


def _interleaved(spans_a: List[ObservedSpan], spans_b: List[ObservedSpan]) -> Optional[str]:
    """Detect A interrupted by B: an A span, then B, then A again (or overlap)."""
    if not spans_a or not spans_b:
        return None
    for span_b in spans_b:
        earlier = [s for s in spans_a if s.end <= span_b.start]
        later = [s for s in spans_a if s.start >= span_b.end]
        if earlier and later:
            return (
                f"session spans interleave: {earlier[-1].span_id} before "
                f"{span_b.span_id} before {later[0].span_id}"
            )
    for span_a in spans_a:
        for span_b in spans_b:
            if _spans_overlap(span_a, span_b) and span_a.background != span_b.background:
                return (
                    f"overlapping foreground/background observations: "
                    f"{span_a.span_id} + {span_b.span_id}"
                )
    return None


class DiscoveryEngine:
    """Deterministic local discovery with accept/reject memory."""

    def __init__(self) -> None:
        self._decisions: Dict[str, Connection] = {}

    def decide(self, connection_id: str, accept: bool, actor: str = "user") -> Connection:
        current = self._decisions.get(connection_id)
        if current is None:
            raise ValueError(f"unknown connection {connection_id!r}")
        updated = current.model_copy(update={
            "status": ConnectionStatus.ACCEPTED if accept else ConnectionStatus.REJECTED,
            "decided_by": actor,
            "decided_at": datetime.now(timezone.utc),
        })
        self._decisions[connection_id] = updated
        return updated

    def decisions(self) -> List[Connection]:
        return sorted(self._decisions.values(), key=lambda c: c.connection_id)

    def discover(
        self,
        sessions: List[LogicalSession],
        spans: List[ObservedSpan],
        labels: List[ActivityLabel],
    ) -> Tuple[List[Connection], List[ConsideredPair]]:
        """Propose connections; returns (connections, considered-but-rejected)."""
        by_id = {s.session_id: s for s in sessions}
        spans_by_session: Dict[str, List[ObservedSpan]] = {s.session_id: [] for s in sessions}
        for span in spans:
            for session in sessions:
                if span.span_id in session.span_ids:
                    spans_by_session[session.session_id].append(span)
        for span_list in spans_by_session.values():
            span_list.sort(key=lambda s: (s.start.isoformat(), s.span_id))
        session_labels = {lbl.target_id: lbl for lbl in labels if lbl.target_kind == "session"}

        ordered = sorted(sessions, key=lambda s: (
            s.first_start.isoformat() if s.first_start else "", s.session_id))
        fresh: Dict[str, Connection] = {}
        considered: List[ConsideredPair] = []

        for i, sess_a in enumerate(ordered):
            for sess_b in ordered[i + 1:]:
                proposals = self._propose_pair(
                    sess_a, sess_b,
                    spans_by_session.get(sess_a.session_id, []),
                    spans_by_session.get(sess_b.session_id, []),
                    session_labels.get(sess_a.session_id),
                    session_labels.get(sess_b.session_id),
                )
                if proposals:
                    for connection in proposals:
                        prior = self._decisions.get(connection.connection_id)
                        if prior is not None and prior.status == ConnectionStatus.REJECTED:
                            considered.append(ConsideredPair(
                                a_session_id=sess_a.session_id,
                                b_session_id=sess_b.session_id,
                                reason=(
                                    f"{connection.kind.value} suppressed: user rejected "
                                    f"{connection.connection_id}"
                                ),
                            ))
                            continue
                        if prior is not None and prior.status == ConnectionStatus.ACCEPTED:
                            connection = connection.model_copy(update={
                                "status": ConnectionStatus.ACCEPTED,
                                "decided_by": prior.decided_by,
                                "decided_at": prior.decided_at,
                            })
                        fresh[connection.connection_id] = connection
                        self._decisions.setdefault(connection.connection_id, connection)
                else:
                    considered.append(ConsideredPair(
                        a_session_id=sess_a.session_id,
                        b_session_id=sess_b.session_id,
                        reason="no content/entity evidence; bare time adjacency never connects",
                    ))
        # Refresh stored decisions for connections that survive.
        for connection in fresh.values():
            stored = self._decisions.get(connection.connection_id)
            if stored is not None and stored.status != ConnectionStatus.PROPOSED:
                fresh[connection.connection_id] = connection.model_copy(update={
                    "status": stored.status,
                    "decided_by": stored.decided_by,
                    "decided_at": stored.decided_at,
                })
        return sorted(fresh.values(), key=lambda c: c.connection_id), considered

    # -- pair rules ----------------------------------------------------

    def _propose_pair(
        self,
        a: LogicalSession,
        b: LogicalSession,
        spans_a: List[ObservedSpan],
        spans_b: List[ObservedSpan],
        label_a: Optional[ActivityLabel],
        label_b: Optional[ActivityLabel],
    ) -> List[Connection]:
        proposals: List[Connection] = []

        # resume-of: explicit resumption links already exist within a session,
        # so cross-session resume-of comes from considered-but-not-linked pairs
        # with same content key (uncertain, correctable).
        same_key = (
            a.content_identity is not None and b.content_identity is not None
            and a.content_identity.key == b.content_identity.key
        )
        if same_key:
            assert a.content_identity is not None
            span_set_a = {s.span_id for s in spans_a}
            span_set_b = {s.span_id for s in spans_b}
            considered_evidence: List[str] = []
            for session in (a, b):
                for considered in session.considered_but_not_linked:
                    pair = {considered.from_span_id, considered.to_span_id}
                    if pair & span_set_a and pair & span_set_b:
                        considered_evidence.extend(considered.evidence)
            # Position restart (rewatch from ~0 after progress) is same content,
            # never a resume: the builder separated them for that reason.
            positions_a = [s.last_position_s for s in spans_a if s.last_position_s is not None]
            positions_b = [s.first_position_s for s in spans_b if s.first_position_s is not None]
            restart = (
                positions_a and positions_b
                and max(positions_a) >= 300.0 and min(positions_b) <= 60.0
            )
            if considered_evidence and not restart:
                # Same content + sub-threshold continuity signals: an uncertain
                # resume the builder would not assert on its own.
                proposals.append(Connection(
                    connection_id=_connection_id("resume-of", a.session_id, b.session_id),
                    kind=ConnectionKind.RESUME_OF,
                    a_session_id=a.session_id,
                    b_session_id=b.session_id,
                    confidence=0.45,
                    evidence=[f"same content key {a.content_identity.key}"]
                    + [f"sub-threshold signal: {e}" for e in sorted(set(considered_evidence))],
                    provenance={
                        "rule": "same-key-plus-considered-link",
                        "content_key": a.content_identity.key,
                        "spans": ",".join([s.span_id for s in spans_a + spans_b]),
                    },
                    uncertainty_reasons=[
                        "continuity evidence was below the session link threshold; "
                        "accept only if this is genuinely one resumed activity"
                    ],
                ))
            else:
                proposals.append(Connection(
                    connection_id=_connection_id("same-content", a.session_id, b.session_id),
                    kind=ConnectionKind.SAME_CONTENT,
                    a_session_id=a.session_id,
                    b_session_id=b.session_id,
                    confidence=0.55,
                    evidence=[f"same content key {a.content_identity.key}"],
                    provenance={
                        "rule": "same-content-key",
                        "content_key": a.content_identity.key,
                        "spans": ",".join([s.span_id for s in spans_a + spans_b]),
                    },
                    uncertainty_reasons=[
                        "sessions were kept separate (no continuity evidence or a "
                        "position restart); merge only if the user confirms sameness"
                    ],
                ))

        # interrupted-by: interleaved spans across sessions.
        interleave = _interleaved(spans_a, spans_b) or _interleaved(spans_b, spans_a)
        if interleave:
            # Direction: the session whose span sits in the middle is the interrupter.
            proposals.append(Connection(
                connection_id=_connection_id("interrupted-by", a.session_id, b.session_id),
                kind=ConnectionKind.INTERRUPTED_BY,
                a_session_id=a.session_id,
                b_session_id=b.session_id,
                confidence=0.8,
                evidence=[interleave],
                provenance={
                    "rule": "span-interleave",
                    "spans": ",".join([s.span_id for s in spans_a + spans_b]),
                },
                uncertainty_reasons=[],
            ))

        # same-project: shared repo/file entity values (>=1, from labels).
        if label_a is not None and label_b is not None:
            repos_a = {e.value for e in label_a.entities if e.kind in ("repo", "file")}
            repos_b = {e.value for e in label_b.entities if e.kind in ("repo", "file")}
            shared_repos = sorted(repos_a & repos_b)
            if shared_repos and not same_key:
                proposals.append(Connection(
                    connection_id=_connection_id("same-project", a.session_id, b.session_id),
                    kind=ConnectionKind.SAME_PROJECT,
                    a_session_id=a.session_id,
                    b_session_id=b.session_id,
                    confidence=0.6,
                    evidence=[f"shared project entity {r}" for r in shared_repos],
                    provenance={
                        "rule": "shared-project-entity",
                        "labels": f"{label_a.label_id},{label_b.label_id}",
                    },
                    uncertainty_reasons=[
                        "shared directory/file hints may be coincidental; "
                        "accept only if the project is genuinely shared"
                    ],
                ))
            # same-topic: >=2 independent shared topic/host signals required.
            topics_a = {(e.kind, e.value) for e in label_a.entities if e.kind in ("topic", "host")}
            topics_b = {(e.kind, e.value) for e in label_b.entities if e.kind in ("topic", "host")}
            shared_topics = sorted(topics_a & topics_b)
            if len(shared_topics) >= 2 and not same_key:
                proposals.append(Connection(
                    connection_id=_connection_id("same-topic", a.session_id, b.session_id),
                    kind=ConnectionKind.SAME_TOPIC,
                    a_session_id=a.session_id,
                    b_session_id=b.session_id,
                    confidence=0.5,
                    evidence=[f"shared {k} {v}" for k, v in shared_topics],
                    provenance={
                        "rule": "shared-topic-signals>=2",
                        "labels": f"{label_a.label_id},{label_b.label_id}",
                    },
                    uncertainty_reasons=[
                        "topic hints are heuristic title/host signals; verify sameness"
                    ],
                ))

        # reference: one session's span URI appears in another's title/evidence
        # is out of scope for heuristic v1 (needs link extraction); recorded
        # as unsupported rather than guessed.
        return proposals
