"""OS Window and Process Source Adapter.

Tracks active window titles, process names, process IDs, and focus transitions.
Enforces client-side pre-filtering against password managers, security keychains, and private tools.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set

from entorhinal.policy.engine import DEFAULT_APP_BLACKLIST
from entorhinal.schemas.models import RawSignalEvent, SourceType, generate_uuidv7
from entorhinal.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)


class OSWindowSourceAdapter(BaseSourceAdapter):
    """Permitted capture adapter for OS foreground window and process focus changes."""

    def __init__(
        self,
        adapter_id: str = "os.window.focus",
        max_buffer_size: int = 5000,
        app_blacklist: Optional[Set[str]] = None,
    ) -> None:
        super().__init__(max_buffer_size=max_buffer_size)
        self._adapter_id = adapter_id
        self._app_blacklist = set(app_blacklist) if app_blacklist is not None else set(DEFAULT_APP_BLACKLIST)

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def source_type(self) -> SourceType:
        return SourceType.OS_WINDOW

    def is_blacklisted(self, app_name: str, window_title: Optional[str] = None) -> bool:
        """Client pre-filter: Check if application or window matches known password managers."""
        app_lower = app_name.lower().strip()
        for bl in self._app_blacklist:
            bl_lower = bl.lower().strip()
            if bl_lower in app_lower:
                return True
        if window_title:
            win_lower = window_title.lower()
            for bl in self._app_blacklist:
                bl_lower = bl.lower().strip()
                if bl_lower in win_lower:
                    return True
        return False

    async def capture_focus_change(
        self,
        app_name: str,
        window_title: str,
        pid: Optional[int] = None,
        bounds: Optional[Dict[str, int]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawSignalEvent]:
        """Capture an OS window focus transition, dropping blacklisted processes."""
        if not self._is_running:
            return None

        # Pre-capture drop for password managers / keychains
        if self.is_blacklisted(app_name, window_title):
            self._events_dropped += 1
            return None

        meta = dict(metadata or {})
        if pid is not None:
            meta["pid"] = pid
        if bounds is not None:
            meta["bounds"] = bounds

        event = RawSignalEvent(
            signal_id=generate_uuidv7(),
            source_type=self.source_type,
            adapter_id=self.adapter_id,
            app_identifier=app_name,
            window_title=window_title,
            target_uri=None,
            raw_payload={
                "event_type": "focus_change",
                "app_name": app_name,
                "window_title": window_title,
                "pid": pid,
            },
            metadata=meta,
        )

        await self.emit_signal(event)
        return event

    async def capture_accessibility_node(
        self,
        app_name: str,
        window_title: str,
        role: str,
        name: str,
        value: Optional[str] = None,
        is_password: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawSignalEvent]:
        """Capture UI Automation / Accessibility tree inspection event."""
        if not self._is_running:
            return None

        if self.is_blacklisted(app_name, window_title) or is_password or role.lower() == "password":
            self._events_dropped += 1
            return None

        meta = dict(metadata or {})
        meta["accessibility_role"] = role

        event = RawSignalEvent(
            signal_id=generate_uuidv7(),
            source_type=SourceType.OS_ACCESSIBILITY,
            adapter_id=f"{self.adapter_id}.accessibility",
            app_identifier=app_name,
            window_title=window_title,
            target_uri=None,
            raw_payload={
                "event_type": "accessibility_node",
                "role": role,
                "name": name,
                "value": value,
            },
            metadata=meta,
        )

        await self.emit_signal(event)
        return event

    async def process_raw_window_event(self, event_dict: Dict[str, Any]) -> Optional[RawSignalEvent]:
        """Process an unnormalized dictionary event from native OS listeners."""
        app_name = event_dict.get("app_name", event_dict.get("app_identifier", "Unknown"))
        window_title = event_dict.get("window_title", "")
        pid = event_dict.get("pid")
        bounds = event_dict.get("bounds")
        metadata = event_dict.get("metadata")

        return await self.capture_focus_change(
            app_name=app_name,
            window_title=window_title,
            pid=pid,
            bounds=bounds,
            metadata=metadata,
        )
