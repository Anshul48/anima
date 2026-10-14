"""Editor focus-producer contract helpers + opt-in sender (code activity).

This module is the Python half of the ``editor-extension`` v0.1.0 contract
(VS Code + Chromium supported scenario). It mirrors the extension rules so
tests and verification tooling can assert shape parity without a live
editor:

- workspace-scoped allowlist matching (absolute workspace roots; a file
  outside every granted root is suppressed, never reported);
- file-URI building for ``file://`` observations that flow into the
  existing ``events.canonical_content_identity`` code/document keys,
  ``classify`` coding votes, and ``sessions`` same-file continuity;
- language-id normalization and edit-count-only payload builders (file
  contents, selection text, terminal, SCM, and diagnostics are never
  fields — there is nowhere to put them);
- heartbeat cadence bounds shared with the extension settings page;
- loopback-only receiver-URL gating with parity to
  ``producers.browser_media.is_loopback_receiver_url``;
- builders emitting ``ActivityEvent``-valid dicts for editor focus
  transitions, edit-count markers, and extension heartbeats;
- ``EditorMetadataSender``: an explicitly-enabled client that POSTs those
  events to the loopback ``POST /activity/v1/events`` contract (reference
  transport: ``browser_sender.LocalActivityReceiver``; same receipt
  shapes, same ``(source_id, event_id)`` idempotency).

Nothing here performs capture, mints grants/tokens/source-ids, or activates
anything: the sender defaults to ``enabled=False`` and refuses to construct
against a non-loopback receiver URL. Imports from ``events``/``grants`` are
read-only (validation parity); the receiver/sink types are reused unchanged
from ``browser_sender``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import httpx
from pydantic import ValidationError

from entorhinal.activity.events import (
    ACTIVITY_EVENT_SCHEMA,
    ACTIVITY_SOURCE_PREFIX,
    ActivityEvent,
    ActivityKind,
)
from entorhinal.activity.producers.browser_media import (
    is_loopback_receiver_url as _browser_loopback_gate,
)
from entorhinal.activity.producers.browser_sender import (
    ACTIVITY_RECEIVER_PATH,
    ReceiverReceipt,
)

EDITOR_SOURCE_ID = ACTIVITY_SOURCE_PREFIX + "editor.01"
EDITOR_CLOCK_DOMAIN = "editor-extension"
EDITOR_APP_DEFAULT = "VSCode"
EXTENSION_VERSION = "0.1.0"

#: Heartbeat cadence bounds (seconds). Mirrors the editor-extension settings:
#: default 60 s (editor focus is coarser than media state), configurable
#: within [MIN, MAX]. Heartbeats are only emitted while the producer is
#: enabled and at least one granted workspace folder is open — never blind.
HEARTBEAT_DEFAULT_S = 60
HEARTBEAT_MIN_S = 10
HEARTBEAT_MAX_S = 300

__all__ = [
    "ACTIVITY_RECEIVER_PATH",
    "EDITOR_APP_DEFAULT",
    "EDITOR_CLOCK_DOMAIN",
    "EDITOR_SOURCE_ID",
    "EXTENSION_VERSION",
    "HEARTBEAT_DEFAULT_S",
    "HEARTBEAT_MAX_S",
    "HEARTBEAT_MIN_S",
    "EditorMetadataSender",
    "build_editor_event_dict",
    "build_editor_heartbeat_dict",
    "build_editor_payload",
    "clamp_heartbeat_cadence",
    "file_uri_for",
    "filter_editor_event",
    "is_loopback_receiver_url",
    "normalize_language",
    "normalize_roots",
    "workspace_rel",
]


def _split_path(path: str) -> List[str]:
    """Split an absolute path into segments, accepting / and \\ separators."""
    cleaned = path.replace("\\", "/")
    return [seg for seg in cleaned.split("/") if seg not in ("", ".")]


def _is_absolute(path: str) -> bool:
    cleaned = path.replace("\\", "/")
    if cleaned.startswith("/"):
        return True
    # Windows drive-absolute (C:/...) — the editor may run on a Windows host.
    return len(cleaned) >= 3 and cleaned[1] == ":" and cleaned[2] == "/"


def _fold(segment: str, windows: bool) -> str:
    return segment.lower() if windows else segment


def _looks_windows(path: str) -> bool:
    return "\\" in path or (len(path) >= 2 and path[1] == ":")


def normalize_roots(roots: Any) -> List[str]:
    """Normalize a user workspace-root allowlist: absolute dirs, deduped.

    Relative entries, empty entries, and non-strings are dropped — a
    workspace grant must name an absolute folder, never a pattern.
    """
    if not isinstance(roots, (list, tuple)):
        return []
    seen: List[str] = []
    for raw in roots:
        if not isinstance(raw, str):
            continue
        candidate = raw.strip()
        if not candidate or not _is_absolute(candidate):
            continue
        normalized = "/".join(_split_path(candidate))
        if candidate.replace("\\", "/").startswith("/"):
            normalized = "/" + normalized
        # Drive-absolute ("C:/repo") already round-trips via the join above.
        if normalized not in seen:
            seen.append(normalized)
    return seen


def workspace_rel(abs_path: str, allowed_roots: List[str]) -> Optional[Tuple[str, str]]:
    """Return (root, rel) when abs_path is inside a granted root, else None.

    Matching is segment-boundary aware (``/repo`` never matches
    ``/repo-other``) and rejects ``..`` escapes. Windows-style paths match
    case-insensitively; POSIX paths match case-sensitively.
    """
    if not isinstance(abs_path, str) or not abs_path.strip():
        return None
    candidate = abs_path.strip()
    if not _is_absolute(candidate):
        return None
    if ".." in _split_path(candidate):
        return None
    windows = _looks_windows(candidate)
    cand_segs = [_fold(s, windows) for s in _split_path(candidate)]
    for root in normalize_roots(allowed_roots):
        root_segs = [_fold(s, windows) for s in _split_path(root)]
        if len(cand_segs) <= len(root_segs):
            continue
        if cand_segs[: len(root_segs)] != root_segs:
            continue
        # Relative path from the ORIGINAL segments (preserve case).
        rel = "/".join(_split_path(candidate)[len(root_segs):])
        if not rel or rel.startswith("/"):
            continue
        return (root, rel)
    return None


def filter_editor_event(
    abs_path: str,
    allowed_roots: List[str],
) -> Tuple[bool, str]:
    """Client-side pre-capture suppression. (allowed, reason)."""
    if not normalize_roots(allowed_roots):
        return False, "suppressed:no-workspace"
    if workspace_rel(abs_path, allowed_roots) is None:
        return False, "suppressed:outside-workspace"
    return True, "allowed"


def normalize_language(raw: Any) -> Optional[str]:
    """Normalize a VS Code language id, or None when unknown/not-an-id."""
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().lower()
    if not candidate or len(candidate) > 32:
        return None
    if not all(ch.isalnum() or ch in ("#", "+", "-", "_") for ch in candidate):
        return None
    return candidate


def file_uri_for(abs_path: str) -> str:
    """Build the ``file://`` URI for an absolute path (identity use only).

    Returns ``""`` for anything that is not an absolute path: callers must
    suppress the event (no URI guessing — unknown identity stays unknown).
    """
    if not isinstance(abs_path, str) or not _is_absolute(abs_path.strip()):
        return ""
    posix = abs_path.strip().replace("\\", "/")
    if _looks_windows(abs_path):
        return "file:///" + quote(posix, safe="/:")
    return "file://" + quote(posix, safe="/")


def clamp_heartbeat_cadence(raw_seconds: Any) -> int:
    """Clamp a user-configured heartbeat cadence into [MIN, MAX]."""
    try:
        seconds = int(raw_seconds)
    except (TypeError, ValueError):
        return HEARTBEAT_DEFAULT_S
    return max(HEARTBEAT_MIN_S, min(HEARTBEAT_MAX_S, seconds))


def is_loopback_receiver_url(raw_url: str) -> bool:
    """True only for http(s) URLs on a loopback host with no credentials.

    Parity wrapper: the browser-media gate is the single implementation;
    this alias keeps the editor contract import-local while a focused test
    asserts agreement on a fixed corpus.
    """
    return _browser_loopback_gate(raw_url)


def build_editor_payload(
    *,
    workspace_name: str,
    file_rel: str,
    language_id: Any = None,
    edit_events: Any = None,
    focus_s: Any = None,
    heartbeat_seq: Any = None,
) -> Dict[str, Any]:
    """Build an editor ``payload`` dict. Unknown fields are absent, never guessed.

    The payload carries workspace/file METADATA only. There are no fields
    for file contents, selection text, terminal output, SCM state, or
    diagnostics — counts (edit events) are the finest observation allowed.
    """
    payload: Dict[str, Any] = {}
    if isinstance(workspace_name, str) and workspace_name.strip():
        payload["workspace"] = workspace_name.strip()[:128]
    if isinstance(file_rel, str) and file_rel.strip():
        payload["file_rel"] = file_rel.strip()[:512]
    language = normalize_language(language_id)
    if language is not None:
        payload["language"] = language
    if isinstance(edit_events, int) and not isinstance(edit_events, bool) and edit_events >= 0:
        payload["edit_events"] = edit_events
    if isinstance(focus_s, (int, float)) and not isinstance(focus_s, bool):
        focus = float(focus_s)
        if focus == focus and 0 <= focus <= 86400:
            payload["focus_s"] = focus
    if isinstance(heartbeat_seq, int) and not isinstance(heartbeat_seq, bool) and heartbeat_seq >= 0:
        payload["heartbeat_seq"] = heartbeat_seq
    return payload


def build_editor_event_dict(
    *,
    event_id: str,
    kind: ActivityKind,
    observed_at: Optional[datetime],
    uri: str,
    window_title: Optional[str],
    payload: Dict[str, Any],
    foreground: bool = True,
    app: str = EDITOR_APP_DEFAULT,
    source_id: str = EDITOR_SOURCE_ID,
    grant_id: str,
    source_seq: Optional[int] = None,
    synthetic: bool = False,
    redaction_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build an ``ActivityEvent``-valid editor event dict (contract keys).

    Raises the underlying validation error when the inputs violate the
    contract — producers must fail loudly, never emit almost-valid events.
    """
    event = ActivityEvent(
        event_id=event_id,
        source_id=source_id,
        grant_id=grant_id,
        observed_at=observed_at,
        source_seq=source_seq,
        clock_domain=EDITOR_CLOCK_DOMAIN,
        kind=kind,
        app=app,
        window_title=(window_title or "")[:300] or None,
        uri=uri,
        foreground=foreground,
        payload=dict(payload),
        redaction_labels=list(redaction_labels or []),
        synthetic=synthetic,
    )
    blob = event.to_json_dict()
    assert blob.get("schema") == ACTIVITY_EVENT_SCHEMA
    return blob


def build_editor_heartbeat_dict(
    *,
    event_id: str,
    observed_at: Optional[datetime],
    grant_id: str,
    source_id: str = EDITOR_SOURCE_ID,
    source_seq: Optional[int] = None,
    synthetic: bool = False,
) -> Dict[str, Any]:
    """Build the editor-level liveness heartbeat event dict."""
    return build_editor_event_dict(
        event_id=event_id,
        kind=ActivityKind.HEARTBEAT,
        observed_at=observed_at,
        uri="",
        window_title=None,
        payload={"sender": "editor-extension", "version": EXTENSION_VERSION},
        foreground=True,
        source_id=source_id,
        grant_id=grant_id,
        source_seq=source_seq,
        synthetic=synthetic,
    )


class EditorMetadataSender:
    """Explicitly-enabled client that POSTs permitted editor metadata events."""

    def __init__(
        self,
        receiver_url: str,
        token: str,
        grant_id: str,
        allowed_roots: List[str],
        app: str = EDITOR_APP_DEFAULT,
        source_id: str = EDITOR_SOURCE_ID,
        enabled: bool = False,
        timeout_s: float = 5.0,
    ) -> None:
        if not token:
            raise ValueError("sender requires a non-empty token")
        if not is_loopback_receiver_url(receiver_url):
            raise ValueError("sender requires a loopback http(s) receiver URL")
        self._receiver_url = receiver_url.strip().rstrip("/")
        self._token = token
        self._grant_id = grant_id
        self._allowed_roots = normalize_roots(allowed_roots)
        self._app = app
        self._source_id = source_id
        self._enabled = enabled
        self._timeout_s = timeout_s
        self._seq = 0
        self.dropped: List[str] = []
        # Loopback receiver traffic must never traverse a proxy: the Bearer
        # token is scoped to the local receiver, and proxies break loopback
        # delivery in sandboxed runtimes.
        self._client = httpx.Client(trust_env=False, timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EditorMetadataSender":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        """Explicit user opt-in (the extension settings toggle calls this)."""
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def _post(self, event: ActivityEvent) -> ReceiverReceipt:
        if not self._enabled:
            self.dropped.append(f"{event.event_id}:sender-disabled")
            return ReceiverReceipt(
                status="dropped", source_id=event.source_id,
                event_id=event.event_id, admitted=False, reason="sender-disabled",
            )
        try:
            response = self._client.post(
                self._receiver_url + ACTIVITY_RECEIVER_PATH,
                json=event.to_json_dict(),
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except httpx.HTTPError as exc:
            return ReceiverReceipt(
                status="transport-error", source_id=event.source_id,
                event_id=event.event_id, admitted=False, reason=str(exc),
            )
        try:
            body = response.json()
        except ValueError:
            return ReceiverReceipt(
                status="bad-receipt", source_id=event.source_id,
                event_id=event.event_id, admitted=False,
                reason=f"http-{response.status_code}",
            )
        try:
            return ReceiverReceipt.model_validate(body)
        except ValidationError:
            return ReceiverReceipt(
                status="bad-receipt", source_id=event.source_id,
                event_id=event.event_id, admitted=False, reason="receipt-schema",
            )

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _workspace_of(self, abs_path: str) -> Optional[Tuple[str, str]]:
        return workspace_rel(abs_path, self._allowed_roots)

    def _suppressed(self, event_id: str, reason: str) -> ReceiverReceipt:
        self.dropped.append(f"{event_id}:{reason}")
        return ReceiverReceipt(
            status="dropped", source_id=self._source_id,
            event_id=event_id, admitted=False, reason=reason,
        )

    def send_focus(
        self,
        event_id: str,
        abs_path: str,
        workspace_name: str,
        language_id: Optional[str] = None,
        foreground: bool = True,
        observed_at: Optional[datetime] = None,
    ) -> ReceiverReceipt:
        """Report an editor focus transition onto a workspace file."""
        allowed, reason = filter_editor_event(abs_path, self._allowed_roots)
        if not allowed:
            return self._suppressed(event_id, reason)
        match = self._workspace_of(abs_path)
        assert match is not None  # filter passed
        _, rel = match
        uri = file_uri_for(abs_path)
        if not uri:
            return self._suppressed(event_id, "suppressed:bad-path")
        title = f"{rel} — {workspace_name}" if workspace_name else rel
        event = ActivityEvent(
            event_id=event_id,
            source_id=self._source_id,
            grant_id=self._grant_id,
            observed_at=observed_at or datetime.now(timezone.utc),
            source_seq=self._next_seq(),
            clock_domain=EDITOR_CLOCK_DOMAIN,
            kind=ActivityKind.WINDOW_FOREGROUND if foreground else ActivityKind.WINDOW_BACKGROUND,
            app=self._app,
            window_title=title[:300],
            uri=uri,
            foreground=foreground,
            payload=build_editor_payload(
                workspace_name=workspace_name, file_rel=rel, language_id=language_id
            ),
        )
        return self._post(event)

    def send_edit_marker(
        self,
        event_id: str,
        abs_path: str,
        workspace_name: str,
        edit_events: int,
        language_id: Optional[str] = None,
        observed_at: Optional[datetime] = None,
    ) -> ReceiverReceipt:
        """Report an edit-count marker (counts only, never content)."""
        allowed, reason = filter_editor_event(abs_path, self._allowed_roots)
        if not allowed:
            return self._suppressed(event_id, reason)
        match = self._workspace_of(abs_path)
        assert match is not None  # filter passed
        _, rel = match
        uri = file_uri_for(abs_path)
        if not uri:
            return self._suppressed(event_id, "suppressed:bad-path")
        event = ActivityEvent(
            event_id=event_id,
            source_id=self._source_id,
            grant_id=self._grant_id,
            observed_at=observed_at or datetime.now(timezone.utc),
            source_seq=self._next_seq(),
            clock_domain=EDITOR_CLOCK_DOMAIN,
            kind=ActivityKind.INPUT_MARKER,
            app=self._app,
            window_title=f"{rel} — {workspace_name}"[:300],
            uri=uri,
            foreground=True,
            payload=build_editor_payload(
                workspace_name=workspace_name, file_rel=rel,
                language_id=language_id, edit_events=edit_events,
            ),
        )
        return self._post(event)

    def send_heartbeat(
        self,
        event_id: str,
        observed_at: Optional[datetime] = None,
    ) -> ReceiverReceipt:
        """Report producer liveness (no file observation attached)."""
        if not self._allowed_roots:
            return self._suppressed(event_id, "suppressed:no-workspace")
        blob = build_editor_heartbeat_dict(
            event_id=event_id,
            observed_at=observed_at or datetime.now(timezone.utc),
            grant_id=self._grant_id,
            source_id=self._source_id,
            source_seq=self._next_seq(),
        )
        return self._post(ActivityEvent.model_validate(blob))
