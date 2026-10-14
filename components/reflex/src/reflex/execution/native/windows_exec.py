"""Windows Native Execution Adapter module alias."""

from __future__ import annotations

from reflex.execution.native.windows_input import (
    MockWindowsInputSubstrate,
    WindowsExecAdapter,
    WindowsNativeExecAdapter,
    WindowsNativeInputAdapter,
    WindowsUIAActionAdapter,
)

__all__ = [
    "WindowsNativeInputAdapter",
    "WindowsExecAdapter",
    "WindowsNativeExecAdapter",
    "WindowsUIAActionAdapter",
    "MockWindowsInputSubstrate",
]
