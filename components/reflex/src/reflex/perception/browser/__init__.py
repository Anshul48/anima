"""Reflex Perception Browser Package: CDP observation, DOM distillation, and Managed Chromium driver."""

from reflex.perception.browser.cdp_provider import (
    CDPObservationProvider,
    CDPSessionProtocol,
    FakeCDPClient,
)
from reflex.perception.browser.managed_chromium import (
    CDPChildSession,
    CDPConnectionClosedError,
    CDPError,
    CDPKeyboard,
    CDPLocator,
    CDPMouse,
    CDPPage,
    CDPWebSocketClient,
    ChromiumDiscovery,
    ManagedChromiumProcess,
    ManagedChromiumSession,
)

__all__ = [
    "CDPChildSession",
    "CDPConnectionClosedError",
    "CDPError",
    "CDPKeyboard",
    "CDPLocator",
    "CDPMouse",
    "CDPObservationProvider",
    "CDPPage",
    "CDPSessionProtocol",
    "CDPWebSocketClient",
    "ChromiumDiscovery",
    "FakeCDPClient",
    "ManagedChromiumProcess",
    "ManagedChromiumSession",
]

