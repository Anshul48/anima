"""Reflex Native OS Action Execution Subsystem."""

from __future__ import annotations

from reflex.execution.native.base import (
    NativeActionConfig,
    NativeActionPort,
)
from reflex.execution.native.factory import (
    NativeActionFactory,
)
from reflex.execution.native.linux_input import (
    LinuxATSPIActionAdapter,
    LinuxExecAdapter,
    LinuxNativeInputAdapter,
    MockLinuxInputSubstrate,
)
from reflex.execution.native.macos_input import (
    MacOSAXActionAdapter,
    MacOSExecAdapter,
    MacOSNativeInputAdapter,
    MockMacOSInputSubstrate,
)
from reflex.execution.native.windows_input import (
    MockWindowsInputSubstrate,
    WindowsExecAdapter,
    WindowsNativeExecAdapter,
    WindowsNativeInputAdapter,
    WindowsUIAActionAdapter,
)
from reflex.execution.native.window_manager import (
    MockWindowManagerSubstrate,
    NativeWindowManager,
    WindowInfo,
)

__all__ = [
    "NativeActionConfig",
    "NativeActionPort",
    "NativeActionFactory",
    "WindowsNativeInputAdapter",
    "WindowsExecAdapter",
    "WindowsNativeExecAdapter",
    "WindowsUIAActionAdapter",
    "MockWindowsInputSubstrate",
    "MacOSNativeInputAdapter",
    "MacOSExecAdapter",
    "MacOSAXActionAdapter",
    "MockMacOSInputSubstrate",
    "LinuxNativeInputAdapter",
    "LinuxExecAdapter",
    "LinuxATSPIActionAdapter",
    "MockLinuxInputSubstrate",
    "NativeWindowManager",
    "WindowInfo",
    "MockWindowManagerSubstrate",
]
