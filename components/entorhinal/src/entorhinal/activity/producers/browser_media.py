"""Browser media-producer contract helpers (pure, no I/O).

This module is the Python half of the ``browser-extension`` v0.2.0 media
contract. It mirrors the content-script rules (``content/media-observer.js``)
so tests and verification tooling can assert byte-for-shape parity without
a live browser:

- canonical media-id extraction with the same precedence as
  ``events.canonical_content_identity`` (explicit payload id first, then
  URI parse, else unknown — never guessed);
- media state / position / duration normalization and validation;
- heartbeat cadence bounds shared with the extension options page;
- per-host user-grant matching (exact host + subdomains, no wildcards);
- loopback-only receiver-URL gating;
- builders emitting ``ActivityEvent``-valid dicts for media snapshots,
  pause/resume/seek markers, and extension heartbeats.

Nothing here performs I/O, mints grants/tokens/source-ids, or activates
capture. Imports from ``events`` are read-only (validation parity).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from entorhinal.activity.events import (
    ACTIVITY_EVENT_SCHEMA,
    ACTIVITY_SOURCE_PREFIX,
    ActivityEvent,
    ActivityKind,
    canonical_media_id,
)

BROWSER_SOURCE_ID = ACTIVITY_SOURCE_PREFIX + "browser.01"
BROWSER_CLOCK_DOMAIN = "browser-extension"
EXTENSION_VERSION = "0.2.0"

#: Heartbeat cadence bounds (seconds). Mirrors the extension options page:
#: default 30 s, user-configurable within [MIN, MAX]. Heartbeats are only
#: emitted while at least one tracked media element exists on a permitted,
#: visible page — never as blind polling.
HEARTBEAT_DEFAULT_S = 30
HEARTBEAT_MIN_S = 10
HEARTBEAT_MAX_S = 300

#: Position tolerance (seconds) distinguishing "resume" (play after pause at
#: ~same position) from "seeked" (play after a position jump).
RESUME_POSITION_TOLERANCE_S = 2.0

#: Media states the producer may emit. Unknown element states normalize to
#: "idle", never to a guessed playing/paused value.
MEDIA_STATES = frozenset({"playing", "paused", "seeking", "ended", "idle"})

#: Marker transitions for ``media-marker`` events.
MEDIA_MARKERS = frozenset({"pause", "resume", "seeked", "ended"})

MEDIA_ELEMENTS = frozenset({"video", "audio"})

__all__ = [
    "BROWSER_CLOCK_DOMAIN",
    "BROWSER_SOURCE_ID",
    "EXTENSION_VERSION",
    "HEARTBEAT_DEFAULT_S",
    "HEARTBEAT_MAX_S",
    "HEARTBEAT_MIN_S",
    "MEDIA_ELEMENTS",
    "MEDIA_MARKERS",
    "MEDIA_STATES",
    "RESUME_POSITION_TOLERANCE_S",
    "build_heartbeat_event_dict",
    "build_media_marker_payload",
    "build_media_payload",
    "build_producer_event_dict",
    "canonical_media_id",
    "clamp_heartbeat_cadence",
    "clamp_position",
    "host_granted",
    "is_loopback_receiver_url",
    "normalize_hosts",
    "normalize_media_state",
]


def normalize_media_state(raw: Any) -> str:
    """Map a raw element state to the contract enum, defaulting to idle."""
    if isinstance(raw, str) and raw.strip().lower() in MEDIA_STATES:
        return raw.strip().lower()
    return "idle"


def clamp_position(value: Any, duration_s: Optional[float] = None) -> Optional[float]:
    """Normalize a media position to finite seconds, or None if unknown.

    Negative, NaN, infinite, or non-numeric positions are unknown (None),
    never coerced to zero: position 0.0 is a real claim (restart) used by
    session restart detection, so it must not be manufactured.
    """
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    position = float(value)
    if position != position or position in (float("inf"), float("-inf")):
        return None
    if position < 0:
        return None
    if duration_s is not None and duration_s > 0 and position > duration_s:
        return float(duration_s)
    return position


def clamp_heartbeat_cadence(raw_seconds: Any) -> int:
    """Clamp a user-configured heartbeat cadence into [MIN, MAX]."""
    try:
        seconds = int(raw_seconds)
    except (TypeError, ValueError):
        return HEARTBEAT_DEFAULT_S
    return max(HEARTBEAT_MIN_S, min(HEARTBEAT_MAX_S, seconds))


def normalize_hosts(hosts: Any) -> List[str]:
    """Normalize a user host allowlist: lowercase, stripped, deduped.

    Wildcards (``*``), empty entries, and non-strings are dropped — grants
    are exact hosts (+ implicit subdomains at match time), never patterns.
    """
    if not isinstance(hosts, (list, tuple)):
        return []
    seen: List[str] = []
    for raw in hosts:
        if not isinstance(raw, str):
            continue
        host = raw.strip().lower().rstrip(".")
        if not host or "*" in host or "/" in host or " " in host:
            continue
        if host not in seen:
            seen.append(host)
    return seen


def host_granted(url: str, allowed_hosts: List[str]) -> bool:
    """True when the URL's host is granted (exact or subdomain of a grant)."""
    if not url or not allowed_hosts:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    granted = normalize_hosts(allowed_hosts)
    return any(host == g or host.endswith("." + g) for g in granted)


def is_loopback_receiver_url(raw_url: str) -> bool:
    """True only for http(s) URLs on a loopback host with no credentials."""
    if not isinstance(raw_url, str) or not raw_url.strip():
        return False
    try:
        parsed = urlparse(raw_url.strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return host in ("127.0.0.1", "localhost", "::1")


def build_media_payload(
    *,
    media_id: Optional[str],
    media_host: Optional[str],
    media_state: Any,
    position_s: Any = None,
    duration_s: Any = None,
    media_title: Optional[str] = None,
    media_element: Optional[str] = None,
    muted: Optional[bool] = None,
    playback_rate: Any = None,
    audible: Optional[bool] = None,
    page_visible: Optional[bool] = None,
    heartbeat_seq: Optional[int] = None,
) -> Dict[str, Any]:
    """Build a media `payload` dict. Unknown fields are absent, never guessed."""
    payload: Dict[str, Any] = {"media_state": normalize_media_state(media_state)}
    if isinstance(media_id, str) and media_id.strip():
        payload["media_id"] = media_id.strip()
    if isinstance(media_host, str) and media_host.strip():
        payload["media_host"] = media_host.strip().lower()
    if isinstance(media_title, str) and media_title.strip():
        payload["media_title"] = media_title.strip()[:300]
    duration: Optional[float] = None
    if isinstance(duration_s, (int, float)) and not isinstance(duration_s, bool):
        duration_f = float(duration_s)
        if duration_f == duration_f and duration_f not in (float("inf"), float("-inf")) and duration_f > 0:
            duration = duration_f
            payload["media_duration_s"] = duration
    position = clamp_position(position_s, duration)
    if position is not None:
        payload["media_position_s"] = position
    if isinstance(media_element, str) and media_element.strip().lower() in MEDIA_ELEMENTS:
        payload["media_element"] = media_element.strip().lower()
    if muted is not None:
        payload["media_muted"] = bool(muted)
    if isinstance(playback_rate, (int, float)) and not isinstance(playback_rate, bool):
        rate = float(playback_rate)
        if rate == rate and 0 < rate <= 16:
            payload["media_rate"] = rate
    if audible is not None:
        payload["media_audible"] = bool(audible)
    if page_visible is not None:
        payload["page_visible"] = bool(page_visible)
    if isinstance(heartbeat_seq, int) and not isinstance(heartbeat_seq, bool) and heartbeat_seq >= 0:
        payload["heartbeat_seq"] = heartbeat_seq
    return payload


def build_media_marker_payload(
    *,
    marker: str,
    base: Dict[str, Any],
    seek_from_s: Any = None,
) -> Dict[str, Any]:
    """Extend a media payload with a pause/resume/seeked/ended marker."""
    normalized = marker.strip().lower() if isinstance(marker, str) else ""
    if normalized not in MEDIA_MARKERS:
        raise ValueError(f"unknown media marker {marker!r}")
    payload = dict(base)
    payload["marker"] = normalized
    if normalized == "seeked":
        origin = clamp_position(seek_from_s)
        if origin is not None:
            payload["seek_from_s"] = origin
    return payload


def build_producer_event_dict(
    *,
    event_id: str,
    kind: ActivityKind,
    observed_at: Optional[datetime],
    uri: str,
    window_title: Optional[str],
    payload: Dict[str, Any],
    foreground: bool = True,
    source_id: str = BROWSER_SOURCE_ID,
    grant_id: str,
    source_seq: Optional[int] = None,
    synthetic: bool = False,
    redaction_labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build an `ActivityEvent`-valid producer event dict (contract keys).

    Raises the underlying validation error when the inputs violate the
    contract — producers must fail loudly, never emit almost-valid events.
    """
    event = ActivityEvent(
        event_id=event_id,
        source_id=source_id,
        grant_id=grant_id,
        observed_at=observed_at,
        source_seq=source_seq,
        clock_domain=BROWSER_CLOCK_DOMAIN,
        kind=kind,
        app="Chromium",
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


def build_heartbeat_event_dict(
    *,
    event_id: str,
    observed_at: Optional[datetime],
    grant_id: str,
    source_id: str = BROWSER_SOURCE_ID,
    source_seq: Optional[int] = None,
    synthetic: bool = False,
) -> Dict[str, Any]:
    """Build the extension-level liveness heartbeat event dict."""
    return build_producer_event_dict(
        event_id=event_id,
        kind=ActivityKind.HEARTBEAT,
        observed_at=observed_at,
        uri="",
        window_title=None,
        payload={"sender": "browser-extension", "version": EXTENSION_VERSION},
        foreground=True,
        source_id=source_id,
        grant_id=grant_id,
        source_seq=source_seq,
        synthetic=synthetic,
    )
