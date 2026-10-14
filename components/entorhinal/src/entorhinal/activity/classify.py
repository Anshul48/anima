"""Local activity classification: deterministic, explainable, correctable.

No remote inference, no network, no model weights. Rules map locally observed
features (app, URI host/path, title tokens, media state, file extensions) to
an activity label plus entity hints (repos, files, topics). Every label
carries the exact rule hits it rests on, a confidence, and explicit
uncertainty reasons. Unknown input yields ``unknown`` with reasons — never a
confident guess.

Heuristic limits (stated, not hidden):

- Title/app keyword signals are English-biased and vendor-specific.
- Same-host web content without a media/content id cannot be distinguished.
- Novel apps, games, and creative tools fall back to ``unknown`` or ``browsing``.
- Confidence is a calibrated-by-construction rule score, not a measured
  probability; treat it as rankable evidence strength.
- User corrections pin labels and always outrank rules.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from entorhinal.activity.sessions import LogicalSession, ObservedSpan

CLASSIFIER_RULE_VERSION = "activity-rules/1"

LECTURE_TITLE_HINTS = (
    "lecture", "lesson", "tutorial", "course", "class", "seminar", "workshop",
    "keynote", "talk:", "episode", "part 1", "part 2", "module",
)
MEETING_APPS = ("zoom", "meet", "teams", "webex", "chime", "jitsi", "discord")
MEETING_TITLE_HINTS = ("meeting", "standup", "call with", "zoom meeting", "| meet ")
CODE_APPS = (
    "code", "vscode", "visual studio", "pycharm", "intellij", "vim", "neovim",
    "emacs", "sublime", "terminal", "iterm", "gnome-terminal", "alacritty",
    "kitty", "wezterm", "powershell", "cmd",
)
CODE_EXTENSIONS = (".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java",
                   ".c", ".cpp", ".h", ".md", ".yaml", ".yml", ".toml", ".sql")
READING_HINTS = ("docs", "documentation", "readthedocs", "wikipedia", "arxiv",
                 "paper", "manual", "handbook", "rfc ", "spec")
WRITING_APPS = ("word", "libreoffice writer", "google docs", "notion", "obsidian",
                "typora", "latex", "overleaf")
BROWSER_APPS = ("chrome", "chromium", "firefox", "safari", "edge", "brave", "arc")


class EntityHint(BaseModel):
    """One extracted entity (repo, file, topic) with its evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str  # repo | file | topic | host
    value: str
    evidence: str


class ActivityLabel(BaseModel):
    """Classification of one span or session (immutable; corrections supersede)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label_id: str
    target_kind: str  # span | session
    target_id: str
    activity: str
    entities: List[EntityHint] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    uncertainty_reasons: List[str] = Field(default_factory=list)
    rule_version: str = CLASSIFIER_RULE_VERSION
    corrected: bool = False
    correction_id: Optional[str] = None


class LabelCorrection(BaseModel):
    """User pin of a label's activity/entities (outranks rules on rebuild)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correction_id: str
    target_kind: str
    target_id: str
    activity: Optional[str] = None
    entities: Optional[List[EntityHint]] = None
    actor: str = "user"
    reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _label_id(target_kind: str, target_id: str) -> str:
    digest = hashlib.sha256(
        f"{target_kind}\u0000{target_id}\u0000{CLASSIFIER_RULE_VERSION}".encode("utf-8")
    ).hexdigest()[:12]
    return f"actlabel_{digest}"


def _host_of(uri: Optional[str]) -> str:
    if not uri:
        return ""
    try:
        return (urlparse(uri).hostname or "").lower()
    except Exception:
        return ""


def extract_entities(
    app: str, uri: Optional[str], title: Optional[str]
) -> List[EntityHint]:
    """Extract repo/file/topic/host hints from local fields (no network)."""
    hints: List[EntityHint] = []
    host = _host_of(uri)
    if host:
        hints.append(EntityHint(kind="host", value=host, evidence=f"uri host {host}"))
    if uri and uri.startswith("file://"):
        path = urlparse(uri).path
        hints.append(EntityHint(kind="file", value=path, evidence=f"file uri {path}"))
        match = re.search(r"/([^/]+)/[^/]*$", path)
        if match:
            hints.append(EntityHint(
                kind="repo", value=match.group(1),
                evidence=f"parent dir of {path}",
            ))
    lowered_title = (title or "").lower()
    lect = re.search(r"(lecture|lesson|module|episode)\s+(\d+[a-z]?)", lowered_title)
    if lect:
        hints.append(EntityHint(
            kind="topic", value=f"{lect.group(1)}-{lect.group(2)}",
            evidence=f"title pattern {lect.group(0)!r}",
        ))
    course = re.search(r"([a-z]{2,4})\s?(\d{3})", lowered_title)
    if course and any(w in lowered_title for w in ("lecture", "course", "class", "cs", "math")):
        hints.append(EntityHint(
            kind="topic", value=f"course-{course.group(1)}{course.group(2)}",
            evidence=f"title pattern {course.group(0)!r}",
        ))
    return hints


class LocalActivityClassifier:
    """Deterministic rule classifier with pinned user corrections."""

    #: Activities this heuristic set can emit. Anything else -> unknown.
    ACTIVITIES = (
        "lecture-viewing", "coding", "reading", "writing", "meeting",
        "browsing", "media-other", "unknown",
    )

    def __init__(self) -> None:
        self._label_corrections: Dict[Tuple[str, str], LabelCorrection] = {}

    def apply_correction(self, correction: LabelCorrection) -> None:
        if correction.activity is not None and correction.activity not in self.ACTIVITIES:
            raise ValueError(f"unknown activity {correction.activity!r}")
        self._label_corrections[(correction.target_kind, correction.target_id)] = correction

    def label_corrections(self) -> List[LabelCorrection]:
        return sorted(self._label_corrections.values(), key=lambda c: c.correction_id)

    def classify_span(self, span: ObservedSpan) -> ActivityLabel:
        return self._label("span", span.span_id, span.app, span.uri,
                           self._span_title(span), span)

    def classify_session(
        self, session: LogicalSession, spans: List[ObservedSpan]
    ) -> ActivityLabel:
        by_id = {s.span_id: s for s in spans}
        ordered = [by_id[sid] for sid in session.span_ids if sid in by_id]
        if not ordered:
            return ActivityLabel(
                label_id=_label_id("session", session.session_id),
                target_kind="session",
                target_id=session.session_id,
                activity="unknown",
                confidence=0.0,
                uncertainty_reasons=["session has no surviving spans"],
            )
        # Majority vote of span activities weighted by active seconds;
        # ties break toward the earliest span (deterministic).
        votes: Dict[str, float] = {}
        first_seen: Dict[str, int] = {}
        span_labels = [self.classify_span(s) for s in ordered]
        for index, (span, label) in enumerate(zip(ordered, span_labels)):
            votes[label.activity] = votes.get(label.activity, 0.0) + max(span.active_seconds, 0.01)
            first_seen.setdefault(label.activity, index)
        best = min(votes, key=lambda a: (-votes[a], first_seen[a]))
        evidence = [f"span {s.span_id} -> {lbl.activity} ({s.active_seconds:.0f}s active)"
                    for s, lbl in zip(ordered, span_labels)]
        entities: List[EntityHint] = []
        seen: set[Tuple[str, str]] = set()
        for lbl in span_labels:
            for ent in lbl.entities:
                if (ent.kind, ent.value) not in seen:
                    seen.add((ent.kind, ent.value))
                    entities.append(ent)
        total = sum(votes.values())
        confidence = round(min(0.9, votes[best] / total if total else 0.0), 3)
        uncertainty = []
        if len(votes) > 1:
            uncertainty.append(f"mixed span activities: {sorted(votes)}; majority kept")
        if confidence < 0.6:
            uncertainty.append("weak majority across spans")
        label = ActivityLabel(
            label_id=_label_id("session", session.session_id),
            target_kind="session",
            target_id=session.session_id,
            activity=best,
            entities=entities,
            confidence=confidence,
            evidence=evidence,
            uncertainty_reasons=uncertainty,
        )
        return self._apply_pin(label)

    # -- internals -----------------------------------------------------

    def _span_title(self, span: ObservedSpan) -> Optional[str]:
        if span.title_snapshot:
            return span.title_snapshot
        if span.content_identity is not None and span.content_identity.display:
            return span.content_identity.display
        return None

    def _label(
        self,
        target_kind: str,
        target_id: str,
        app: str,
        uri: Optional[str],
        title: Optional[str],
        span: Optional[ObservedSpan] = None,
    ) -> ActivityLabel:
        pinned = self._label_corrections.get((target_kind, target_id))
        activity, confidence, evidence, uncertainty = self._rule_vote(app, uri, title, span)
        entities = extract_entities(app, uri, title)
        label = ActivityLabel(
            label_id=_label_id(target_kind, target_id),
            target_kind=target_kind,
            target_id=target_id,
            activity=activity,
            entities=entities,
            confidence=confidence,
            evidence=evidence,
            uncertainty_reasons=uncertainty,
        )
        if pinned is not None:
            return label.model_copy(update={
                "activity": pinned.activity or label.activity,
                "entities": list(pinned.entities) if pinned.entities is not None else label.entities,
                "confidence": 1.0,
                "evidence": label.evidence + [f"user-pinned by {pinned.actor}: {pinned.reason}"],
                "uncertainty_reasons": [],
                "corrected": True,
                "correction_id": pinned.correction_id,
            })
        return label

    def _apply_pin(self, label: ActivityLabel) -> ActivityLabel:
        pinned = self._label_corrections.get((label.target_kind, label.target_id))
        if pinned is None:
            return label
        return label.model_copy(update={
            "activity": pinned.activity or label.activity,
            "entities": list(pinned.entities) if pinned.entities is not None else label.entities,
            "confidence": 1.0,
            "evidence": label.evidence + [f"user-pinned by {pinned.actor}: {pinned.reason}"],
            "uncertainty_reasons": [],
            "corrected": True,
            "correction_id": pinned.correction_id,
        })

    def _rule_vote(
        self,
        app: str,
        uri: Optional[str],
        title: Optional[str],
        span: Optional[ObservedSpan],
    ) -> Tuple[str, float, List[str], List[str]]:
        app_l = app.lower()
        title_l = (title or "").lower()
        host = _host_of(uri)
        path_l = (uri or "").lower()
        evidence: List[str] = []
        uncertainty: List[str] = []
        scores: Dict[str, float] = {}

        def vote(activity: str, weight: float, reason: str) -> None:
            scores[activity] = scores.get(activity, 0.0) + weight
            evidence.append(f"{activity}: {reason}")

        # Media with an explicit media identity: lecture vs other media.
        if span is not None and span.content_identity is not None \
                and span.content_identity.kind == "media":
            if any(h in title_l for h in LECTURE_TITLE_HINTS):
                vote("lecture-viewing", 0.55, f"media + lecture title hint in {title!r}")
            elif span.first_position_s is not None and (span.last_position_s or 0) - (span.first_position_s or 0) >= 60:
                vote("lecture-viewing", 0.30, "media with >=60s position progress")
                uncertainty.append("long media progress without lecture title hints")
            else:
                vote("media-other", 0.40, "media identity without lecture signals")
                uncertainty.append("media content but lecture-vs-other unclear")
        # Meeting apps / titles.
        if any(m in app_l for m in MEETING_APPS) or any(h in title_l for h in MEETING_TITLE_HINTS):
            vote("meeting", 0.50, f"meeting app/title signal app={app!r}")
        # Code: app or file extension.
        if any(c in app_l for c in CODE_APPS):
            vote("coding", 0.35, f"code app {app!r}")
        if path_l.startswith("file://") and path_l.endswith(CODE_EXTENSIONS):
            vote("coding", 0.45, f"code file extension in {uri!r}")
        # Reading: doc hosts / title hints.
        if any(h in host or h in title_l for h in READING_HINTS):
            vote("reading", 0.40, "doc/reading host or title hint")
        # Writing apps.
        if any(w in app_l for w in WRITING_APPS):
            vote("writing", 0.40, f"writing app {app!r}")
        # Browser fallback.
        if any(b in app_l for b in BROWSER_APPS) and not scores:
            vote("browsing", 0.25, f"browser {app!r} without specific signals")
            uncertainty.append("generic browser use; specific activity unclear")

        if not scores:
            return ("unknown", 0.0, ["no rule fired"],
                    ["no app/uri/title/media signal matched; heuristic set is limited"])
        best = min(scores, key=lambda a: (-scores[a], a))
        confidence = round(min(0.9, scores[best]), 3)
        if len(scores) > 1:
            runner = sorted(scores, key=lambda a: (-scores[a], a))[1]
            if scores[best] - scores[runner] < 0.15:
                uncertainty.append(
                    f"close runner-up {runner} ({scores[runner]:.2f} vs {scores[best]:.2f})"
                )
        if confidence < 0.5:
            uncertainty.append("weak rule support; consider user correction")
        return best, confidence, evidence, uncertainty
