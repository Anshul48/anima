"""Factory and registry for native desktop OS observation adapters."""

from __future__ import annotations

import sys
from typing import Any, Dict, Optional, Type

from reflex.perception.native.base import (
    NativeObservationConfig,
    NativeObservationPort,
)
from reflex.perception.native.linux_atspi import LinuxATSPIObservationAdapter
from reflex.perception.native.macos_ax import MacOSAXObservationAdapter
from reflex.perception.native.windows_uia import WindowsUIAObservationAdapter
from reflex.ports.clock import ClockPort


class NativeObservationFactory:
    """Factory for auto-detecting host OS and constructing appropriate NativeObservationPort adapter."""

    _registry: Dict[str, Type[NativeObservationPort]] = {
        "windows": WindowsUIAObservationAdapter,
        "win32": WindowsUIAObservationAdapter,
        "darwin": MacOSAXObservationAdapter,
        "macos": MacOSAXObservationAdapter,
        "osx": MacOSAXObservationAdapter,
        "linux": LinuxATSPIObservationAdapter,
        "linux2": LinuxATSPIObservationAdapter,
    }

    @classmethod
    def register_adapter(cls, os_name: str, adapter_cls: Type[NativeObservationPort]) -> None:
        """Registers a custom native observation adapter for a target OS identifier."""
        cls._registry[os_name.lower().strip()] = adapter_cls

    @classmethod
    def normalize_os_name(cls, raw_os: Optional[str] = None) -> str:
        """Normalizes arbitrary OS names into canonical platform keys."""
        target = (raw_os or sys.platform).lower().strip()
        if "darwin" in target or "mac" in target or "osx" in target:
            return "darwin"
        elif "linux" in target:
            return "linux"
        elif "win" in target:
            return "windows"
        return target

    @classmethod
    def get_adapter_class(cls, os_name: Optional[str] = None) -> Type[NativeObservationPort]:
        """Resolves the adapter class for the specified or detected operating system."""
        canonical = cls.normalize_os_name(os_name)
        if canonical in cls._registry:
            return cls._registry[canonical]
        raw_key = (os_name or sys.platform).lower().strip()
        if raw_key in cls._registry:
            return cls._registry[raw_key]
        # Fallback to Windows UIA adapter
        return WindowsUIAObservationAdapter

    @classmethod
    def create(
        cls,
        os_name: Optional[str] = None,
        config: Optional[NativeObservationConfig] = None,
        substrate: Any = None,
        clock: Optional[ClockPort] = None,
    ) -> NativeObservationPort:
        """Constructs and returns an instantiated NativeObservationPort adapter."""
        adapter_cls = cls.get_adapter_class(os_name)
        kwargs: Dict[str, Any] = {
            "config": config,
            "clock": clock,
        }
        if substrate is not None:
            kwargs["substrate"] = substrate

        return adapter_cls(**kwargs)


# Architectural Registry Alias
PlatformAdapterRegistry = NativeObservationFactory
