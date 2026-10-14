"""Browser Source Adapter for Permitted Semantic Ingestion.

Captures active tab navigation, page titles, structured DOM metadata, and user text selection.
Enforces pre-capture suppression of password inputs, credit cards, and incognito sessions.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Set

from entorhinal.schemas.models import RawSignalEvent, SourceType, generate_uuidv7
from entorhinal.sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)

# Patterns identifying password and sensitive payment input fields
SENSITIVE_INPUT_TYPES: Set[str] = {"password", "pin"}
SENSITIVE_AUTOCOMPLETE_VALUES: Set[str] = {
    "current-password", "new-password", "one-time-code", "cc-number",
    "cc-exp", "cc-exp-month", "cc-exp-year", "cc-csc", "cc-type",
    "transaction-currency", "transaction-amount"
}
SENSITIVE_FIELD_NAMES: Set[str] = {
    "password", "passwd", "pwd", "user_password", "cardnumber",
    "card_number", "creditcard", "credit_card", "cvv", "cvc",
    "ccv", "security_code", "ssn", "social_security", "secret"
}
SENSITIVE_SUBSTRINGS: Set[str] = {
    "password", "passwd", "creditcard", "credit card", "card number",
    "card_number", "card-number", "cvv", "cvc", "security code",
    "security_code", "ssn", "social security",
}


def is_sensitive_dom_element(
    tag_name: str,
    attributes: Optional[Dict[str, str]] = None,
) -> bool:
    """Detect if a DOM element represents a password or financial input field."""
    if not attributes:
        return False

    # Check element type
    input_type = attributes.get("type", "").lower().strip()
    if input_type in SENSITIVE_INPUT_TYPES:
        return True

    # Check autocomplete attribute
    autocomplete = attributes.get("autocomplete", "").lower().strip()
    if autocomplete in SENSITIVE_AUTOCOMPLETE_VALUES:
        return True

    # Check name, id, placeholder, and aria-label attributes
    for attr in ("name", "id", "aria-label", "placeholder", "title"):
        val = attributes.get(attr, "").lower().strip()
        if not val:
            continue
        # Split tokens
        tokens = set(re.split(r"[-_.\s]+", val))
        if tokens & SENSITIVE_FIELD_NAMES:
            return True
        if any(sens in val for sens in SENSITIVE_SUBSTRINGS):
            return True

    # Explicit opt-out attribute
    if attributes.get("data-private", "").lower() in ("true", "1", "sensitive"):
        return True

    return False


class BrowserSourceAdapter(BaseSourceAdapter):
    """Permitted capture adapter for browser navigation, tab shifts, and highlighted text."""

    def __init__(
        self,
        adapter_id: str = "browser.semantic.cdp",
        max_buffer_size: int = 5000,
        suppress_incognito: bool = True,
    ) -> None:
        super().__init__(max_buffer_size=max_buffer_size)
        self._adapter_id = adapter_id
        self._suppress_incognito = suppress_incognito

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def source_type(self) -> SourceType:
        return SourceType.BROWSER

    async def capture_navigation(
        self,
        url: str,
        title: str,
        app_identifier: str = "Google Chrome",
        is_incognito: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawSignalEvent]:
        """Capture a top-level page navigation event."""
        if not self._is_running:
            return None

        meta = dict(metadata or {})
        meta["is_incognito"] = is_incognito

        if self._suppress_incognito and is_incognito:
            self._events_dropped += 1
            return None

        event = RawSignalEvent(
            signal_id=generate_uuidv7(),
            source_type=self.source_type,
            adapter_id=self.adapter_id,
            app_identifier=app_identifier,
            window_title=title,
            target_uri=url,
            raw_payload={
                "event_type": "navigation",
                "url": url,
                "title": title,
            },
            metadata=meta,
        )

        await self.emit_signal(event)
        return event

    async def capture_text_selection(
        self,
        url: str,
        title: str,
        selected_text: str,
        app_identifier: str = "Google Chrome",
        element_tag: Optional[str] = None,
        element_attributes: Optional[Dict[str, str]] = None,
        is_incognito: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawSignalEvent]:
        """Capture user-highlighted or selected DOM text, dropping password/sensitive selections."""
        if not self._is_running:
            return None

        if self._suppress_incognito and is_incognito:
            self._events_dropped += 1
            return None

        if element_tag and is_sensitive_dom_element(element_tag, element_attributes):
            self._events_dropped += 1
            return None

        meta = dict(metadata or {})
        meta["is_incognito"] = is_incognito

        event = RawSignalEvent(
            signal_id=generate_uuidv7(),
            source_type=self.source_type,
            adapter_id=self.adapter_id,
            app_identifier=app_identifier,
            window_title=title,
            target_uri=url,
            raw_payload={
                "event_type": "text_selection",
                "selected_text": selected_text,
                "element_tag": element_tag,
            },
            metadata=meta,
        )

        await self.emit_signal(event)
        return event

    async def capture_dom_focus(
        self,
        url: str,
        title: str,
        element_tag: str,
        element_attributes: Optional[Dict[str, str]] = None,
        value: Optional[str] = None,
        app_identifier: str = "Google Chrome",
        is_incognito: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[RawSignalEvent]:
        """Capture an active DOM focus or interaction event, strictly suppressing sensitive inputs."""
        if not self._is_running:
            return None

        if self._suppress_incognito and is_incognito:
            self._events_dropped += 1
            return None

        # Pre-capture drop for sensitive password/credit card fields
        if is_sensitive_dom_element(element_tag, element_attributes):
            self._events_dropped += 1
            return None

        meta = dict(metadata or {})
        meta["is_incognito"] = is_incognito

        event = RawSignalEvent(
            signal_id=generate_uuidv7(),
            source_type=self.source_type,
            adapter_id=self.adapter_id,
            app_identifier=app_identifier,
            window_title=title,
            target_uri=url,
            raw_payload={
                "event_type": "dom_focus",
                "element_tag": element_tag,
                "element_id": (element_attributes or {}).get("id"),
                "value": value,
            },
            metadata=meta,
        )

        await self.emit_signal(event)
        return event

    async def process_raw_browser_event(self, event_dict: Dict[str, Any]) -> Optional[RawSignalEvent]:
        """Process an unnormalized JSON payload received from extension IPC or CDP."""
        event_type = event_dict.get("event_type", "navigation")
        url = event_dict.get("url", "")
        title = event_dict.get("title", "")
        app_name = event_dict.get("app_identifier", "Google Chrome")
        is_incognito = bool(event_dict.get("is_incognito", False))

        if event_type == "navigation":
            return await self.capture_navigation(
                url=url,
                title=title,
                app_identifier=app_name,
                is_incognito=is_incognito,
                metadata=event_dict.get("metadata"),
            )
        elif event_type == "text_selection":
            return await self.capture_text_selection(
                url=url,
                title=title,
                selected_text=event_dict.get("selected_text", ""),
                app_identifier=app_name,
                element_tag=event_dict.get("element_tag"),
                element_attributes=event_dict.get("element_attributes"),
                is_incognito=is_incognito,
                metadata=event_dict.get("metadata"),
            )
        elif event_type == "dom_focus":
            return await self.capture_dom_focus(
                url=url,
                title=title,
                element_tag=event_dict.get("element_tag", "input"),
                element_attributes=event_dict.get("element_attributes"),
                value=event_dict.get("value"),
                app_identifier=app_name,
                is_incognito=is_incognito,
                metadata=event_dict.get("metadata"),
            )
        else:
            if is_incognito and self._suppress_incognito:
                self._events_dropped += 1
                return None
            event = RawSignalEvent(
                signal_id=generate_uuidv7(),
                source_type=self.source_type,
                adapter_id=self.adapter_id,
                app_identifier=app_name,
                window_title=title,
                target_uri=url,
                raw_payload=event_dict.get("payload", {}),
                metadata=event_dict.get("metadata", {}),
            )
            await self.emit_signal(event)
            return event
