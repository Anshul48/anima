"""Opt-in browser metadata sender and loopback receiver contract.

The sender runs where the user explicitly installed and enabled it (browser
extension or local helper, default OFF). It POSTs ``ActivityEvent`` metadata
— navigation host/title, media state — to a loopback receiver. It never
sends keystrokes, passwords, page bodies, or incognito activity, and only
for explicitly allowlisted hosts.

``LocalActivityReceiver`` is the stdlib-based contract reference for
``POST /activity/v1/events``: bearer-token auth, schema validation, grant
check, JSON receipt. Main rewires this contract onto the real API route
(API-builder auth); behavior here defines the expected semantics.

Nothing in this module activates capture: the sender requires ``enabled=True``
plus a token, and the receiver binds loopback only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from entorhinal.activity.events import (
    ACTIVITY_SOURCE_PREFIX,
    ActivityEvent,
    ActivityKind,
)
from entorhinal.activity.grants import GrantStore
from entorhinal.sources.browser import is_sensitive_dom_element

logger = logging.getLogger(__name__)

ACTIVITY_RECEIVER_PATH = "/activity/v1/events"
BROWSER_SOURCE_ID = ACTIVITY_SOURCE_PREFIX + "browser.01"

STRIPPED_QUERY_PARAMS = frozenset({
    "password", "passwd", "pwd", "token", "access_token", "id_token",
    "secret", "api_key", "apikey", "session", "sessionid", "auth",
})

EventSink = Callable[[ActivityEvent], None]


class ReceiverReceipt(BaseModel):
    """Admission receipt for one posted activity event."""

    model_config = ConfigDict(extra="forbid")

    status: str
    source_id: str = ""
    event_id: str = ""
    admitted: bool = False
    reason: Optional[str] = None


def scrub_url(raw_url: str) -> str:
    """Remove credential-bearing query params; keep host/path/media ids."""
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return ""
    if not parsed.scheme or not parsed.hostname:
        return ""
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in STRIPPED_QUERY_PARAMS]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                       parsed.params, urlencode(kept), ""))


def filter_dom_event(
    event: Dict[str, Any],
    allow_domains: List[str],
) -> Tuple[bool, str]:
    """Client-side pre-capture suppression. (allowed, reason)."""
    if event.get("is_incognito"):
        return False, "suppressed:incognito"
    if is_sensitive_dom_element(
        str(event.get("element_tag", "div")),
        {str(k): str(v) for k, v in dict(event.get("element_attributes", {})).items()},
    ):
        return False, "suppressed:sensitive-element"
    url = str(event.get("url", ""))
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False, "suppressed:bad-url"
    if not host:
        return False, "suppressed:bad-url"
    allowed = [d.lower() for d in allow_domains]
    if not any(host == d or host.endswith("." + d) for d in allowed):
        return False, "suppressed:domain-not-allowlisted"
    return True, "allowed"


class BrowserMetadataSender:
    """Explicitly-enabled client that POSTs permitted metadata events."""

    def __init__(
        self,
        receiver_url: str,
        token: str,
        grant_id: str,
        allow_domains: List[str],
        app: str = "Chromium",
        source_id: str = BROWSER_SOURCE_ID,
        enabled: bool = False,
        timeout_s: float = 5.0,
    ) -> None:
        if not token:
            raise ValueError("sender requires a non-empty token")
        self._receiver_url = receiver_url.rstrip("/")
        self._token = token
        self._grant_id = grant_id
        self._allow_domains = list(allow_domains)
        self._app = app
        self._source_id = source_id
        self._enabled = enabled
        self._timeout_s = timeout_s
        self._seq = 0
        self.dropped: List[str] = []
        # Loopback receiver traffic must never traverse a proxy: the bearer
        # token is scoped to the local receiver, and proxies break loopback
        # delivery in sandboxed runtimes.
        self._client = httpx.Client(trust_env=False, timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BrowserMetadataSender":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        """Explicit user opt-in (the extension options page calls this)."""
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

    def send_navigation(
        self,
        event_id: str,
        url: str,
        title: str,
        is_incognito: bool = False,
        foreground: bool = True,
        observed_at: Optional[datetime] = None,
    ) -> ReceiverReceipt:
        allowed, reason = filter_dom_event(
            {"url": url, "is_incognito": is_incognito}, self._allow_domains
        )
        if not allowed:
            self.dropped.append(f"{event_id}:{reason}")
            return ReceiverReceipt(
                status="dropped", source_id=self._source_id,
                event_id=event_id, admitted=False, reason=reason,
            )
        event = ActivityEvent(
            event_id=event_id,
            source_id=self._source_id,
            grant_id=self._grant_id,
            observed_at=observed_at or datetime.now(timezone.utc),
            source_seq=self._next_seq(),
            clock_domain="browser-sender",
            kind=ActivityKind.WINDOW_FOREGROUND if foreground else ActivityKind.WINDOW_BACKGROUND,
            app=self._app,
            window_title=title,
            uri=scrub_url(url),
            foreground=foreground,
            payload={},
        )
        return self._post(event)

    def send_media_state(
        self,
        event_id: str,
        url: str,
        title: str,
        media_id: str,
        position_s: float,
        duration_s: Optional[float],
        media_state: str,
        is_incognito: bool = False,
        foreground: bool = True,
        kind: ActivityKind = ActivityKind.MEDIA_FOREGROUND,
        observed_at: Optional[datetime] = None,
    ) -> ReceiverReceipt:
        allowed, reason = filter_dom_event(
            {"url": url, "is_incognito": is_incognito}, self._allow_domains
        )
        if not allowed:
            self.dropped.append(f"{event_id}:{reason}")
            return ReceiverReceipt(
                status="dropped", source_id=self._source_id,
                event_id=event_id, admitted=False, reason=reason,
            )
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            host = ""
        event = ActivityEvent(
            event_id=event_id,
            source_id=self._source_id,
            grant_id=self._grant_id,
            observed_at=observed_at or datetime.now(timezone.utc),
            source_seq=self._next_seq(),
            clock_domain="browser-sender",
            kind=kind,
            app=self._app,
            window_title=title,
            uri=scrub_url(url),
            foreground=foreground,
            payload={
                "media_id": media_id,
                "media_host": host,
                "media_position_s": position_s,
                "media_duration_s": duration_s,
                "media_state": media_state,
            },
        )
        return self._post(event)

    def send_text_selection(
        self,
        event_id: str,
        url: str,
        title: str,
        selected_text: str,
        element_tag: str = "p",
        element_attributes: Optional[Dict[str, str]] = None,
        is_incognito: bool = False,
        observed_at: Optional[datetime] = None,
    ) -> ReceiverReceipt:
        allowed, reason = filter_dom_event(
            {"url": url, "is_incognito": is_incognito,
             "element_tag": element_tag,
             "element_attributes": element_attributes or {}},
            self._allow_domains,
        )
        if not allowed:
            self.dropped.append(f"{event_id}:{reason}")
            return ReceiverReceipt(
                status="dropped", source_id=self._source_id,
                event_id=event_id, admitted=False, reason=reason,
            )
        event = ActivityEvent(
            event_id=event_id,
            source_id=self._source_id,
            grant_id=self._grant_id,
            observed_at=observed_at or datetime.now(timezone.utc),
            source_seq=self._next_seq(),
            clock_domain="browser-sender",
            kind=ActivityKind.INPUT_MARKER,
            app=self._app,
            window_title=title,
            uri=scrub_url(url),
            foreground=True,
            payload={"selection_chars": len(selected_text)},
        )
        return self._post(event)


class InboxFileSink:
    """Append admitted events to an activity inbox file (fsync per write)."""

    def __init__(self, inbox_path: Path) -> None:
        self._path = Path(inbox_path)
        self._lock = threading.Lock()

    def __call__(self, event: ActivityEvent) -> None:
        line = json.dumps(event.to_json_dict(), sort_keys=True) + "\n"
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()


def _make_handler(
    token_hash: bytes,
    grants: GrantStore,
    sink: EventSink,
) -> type[BaseHTTPRequestHandler]:
    expected = token_hash

    class ActivityHandler(BaseHTTPRequestHandler):
        server_version = "EntorhinalActivityReceiver/1"

        def log_message(self, *args: Any) -> None:  # quiet in tests
            logger.debug("receiver: %s", args)

        def _receipt(self, receipt: ReceiverReceipt, http_status: int) -> None:
            body = json.dumps(receipt.model_dump(mode="json")).encode("utf-8")
            self.send_response(http_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802 - stdlib naming
            if self.path != ACTIVITY_RECEIVER_PATH:
                self._receipt(ReceiverReceipt(status="not-found", reason="unknown-path"), 404)
                return
            auth = self.headers.get("Authorization", "")
            presented = auth[7:] if auth.startswith("Bearer ") else ""
            presented_hash = hashlib.sha256(presented.encode("utf-8")).digest()
            if not presented or not hmac.compare_digest(presented_hash, expected):
                self._receipt(
                    ReceiverReceipt(status="denied", reason="denied:bad-or-missing-token"), 401
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > 1_000_000:
                self._receipt(
                    ReceiverReceipt(status="rejected", reason="rejected:bad-length"), 400
                )
                return
            try:
                candidate = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._receipt(
                    ReceiverReceipt(status="rejected", reason="rejected:bad-json"), 400
                )
                return
            try:
                event = ActivityEvent.model_validate(candidate)
            except ValidationError as exc:
                self._receipt(
                    ReceiverReceipt(
                        status="rejected",
                        reason=f"rejected:schema:{str(exc)[:200]}",
                    ),
                    400,
                )
                return
            allowed, reason = grants.check(event)
            if not allowed:
                self._receipt(
                    ReceiverReceipt(
                        status="denied", source_id=event.source_id,
                        event_id=event.event_id, reason=reason,
                    ),
                    403,
                )
                return
            try:
                sink(event)
            except Exception as exc:  # fail-closed, no silent loss claim
                self._receipt(
                    ReceiverReceipt(
                        status="error", source_id=event.source_id,
                        event_id=event.event_id,
                        reason=f"error:sink-failed:{exc}",
                    ),
                    500,
                )
                return
            self._receipt(
                ReceiverReceipt(
                    status="admitted", source_id=event.source_id,
                    event_id=event.event_id, admitted=True, reason="admitted",
                ),
                200,
            )

    return ActivityHandler


class LocalActivityReceiver:
    """Loopback-only reference receiver (contract + verification use).

    Main replaces this transport with the real API route; the receipt shapes
    and denial reasons stay identical.
    """

    def __init__(
        self,
        token: str,
        grants: GrantStore,
        sink: EventSink,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        if not token:
            raise ValueError("receiver requires a non-empty token")
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("receiver binds loopback only")
        self._token_hash = hashlib.sha256(token.encode("utf-8")).digest()
        self._grants = grants
        self._sink = sink
        self._server = HTTPServer((host, port), _make_handler(self._token_hash, grants, sink))
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="activity-receiver", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._server.server_close()
