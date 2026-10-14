"""Reflex Native OS Perception Subsystem."""

from __future__ import annotations

from reflex.perception.native.base import (
    NativeObservationConfig,
    NativeObservationPort,
    NativeUIElement,
)
from reflex.perception.native.factory import (
    NativeObservationFactory,
    PlatformAdapterRegistry,
)
from reflex.perception.native.linux_atspi import (
    LinuxATSPIAdapter,
    LinuxATSPIObservationAdapter,
    MockLinuxATSPISubstrate,
)
from reflex.perception.native.macos_ax import (
    MacOSAXAdapter,
    MacOSAXObservationAdapter,
    MockMacOSAXSubstrate,
)
from reflex.perception.native.windows_uia import (
    MockWindowsUIASubstrate,
    WindowsUIAAdapter,
    WindowsUIAObservationAdapter,
)

__all__ = [
    "NativeObservationConfig",
    "NativeObservationPort",
    "NativeUIElement",
    "NativeObservationFactory",
    "PlatformAdapterRegistry",
    "WindowsUIAObservationAdapter",
    "WindowsUIAAdapter",
    "MockWindowsUIASubstrate",
    "MacOSAXObservationAdapter",
    "MacOSAXAdapter",
    "MockMacOSAXSubstrate",
    "LinuxATSPIObservationAdapter",
    "LinuxATSPIAdapter",
    "MockLinuxATSPISubstrate",
]
