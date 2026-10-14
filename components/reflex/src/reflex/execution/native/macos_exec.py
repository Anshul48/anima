"""macOS Native Execution Adapter module alias."""

from __future__ import annotations

from reflex.execution.native.macos_input import (
    MacOSAXActionAdapter,
    MacOSExecAdapter,
    MacOSNativeInputAdapter,
    MockMacOSInputSubstrate,
)

__all__ = [
    "MacOSNativeInputAdapter",
    "MacOSExecAdapter",
    "MacOSAXActionAdapter",
    "MockMacOSInputSubstrate",
]
