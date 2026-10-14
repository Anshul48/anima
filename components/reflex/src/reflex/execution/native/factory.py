"""Factory and registry for native desktop OS action execution adapters."""

from __future__ import annotations

import sys
from typing import Any, Dict, Optional, Type

from reflex.execution.native.base import (
    NativeActionConfig,
    NativeActionPort,
)
from reflex.execution.native.linux_input import LinuxNativeInputAdapter
from reflex.execution.native.macos_input import MacOSNativeInputAdapter
from reflex.execution.native.windows_input import WindowsNativeInputAdapter
from reflex.host.identity.lease_manager import ActionLeaseManager


class NativeActionFactory:
    """Factory for auto-detecting host OS and constructing appropriate NativeActionPort adapter."""

    _registry: Dict[str, Type[NativeActionPort]] = {
        "windows": WindowsNativeInputAdapter,
        "win32": WindowsNativeInputAdapter,
        "darwin": MacOSNativeInputAdapter,
        "macos": MacOSNativeInputAdapter,
        "osx": MacOSNativeInputAdapter,
        "linux": LinuxNativeInputAdapter,
        "linux2": LinuxNativeInputAdapter,
    }

    @classmethod
    def register_adapter(cls, os_name: str, adapter_cls: Type[NativeActionPort]) -> None:
        """Registers a custom native action execution adapter for a target OS identifier."""
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
    def get_adapter_class(cls, os_name: Optional[str] = None) -> Type[NativeActionPort]:
        """Resolves the adapter class for the specified or detected operating system."""
        canonical = cls.normalize_os_name(os_name)
        if canonical in cls._registry:
            return cls._registry[canonical]
        raw_key = (os_name or sys.platform).lower().strip()
        if raw_key in cls._registry:
            return cls._registry[raw_key]
        # Fallback to Windows native input adapter
        return WindowsNativeInputAdapter

    @classmethod
    def create(
        cls,
        os_name: Optional[str] = None,
        config: Optional[NativeActionConfig] = None,
        substrate: Any = None,
        lease_manager: Optional[ActionLeaseManager] = None,
        clock: Optional[Any] = None,
    ) -> NativeActionPort:
        """Constructs and returns an instantiated NativeActionPort adapter."""
        adapter_cls = cls.get_adapter_class(os_name)
        kwargs: Dict[str, Any] = {
            "config": config,
            "lease_manager": lease_manager,
            "clock": clock,
        }
        if substrate is not None:
            kwargs["substrate"] = substrate

        return adapter_cls(**kwargs)
