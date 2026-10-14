"""Reflex Integrations Package.

Provides local fakes and optional ecosystem bridges (Entorhinal and Trace).
"""

from __future__ import annotations

from reflex.integrations.bridges import (
    CircuitState,
    EcosystemBridgeCoordinator,
    EcosystemIntegrationConfig,
    EntorhinalBridge,
    EntorhinalBridgeMetrics,
    EntorhinalContextAdapter,
    TraceBridge,
    TraceBridgeMetrics,
    TraceMemoryAdapter,
)
from reflex.integrations.fakes import (
    ContextFaultMode,
    FakeBrowserPage,
    FakeCDPSession,
    FakeContextConfig,
    FakeContextProvider,
    FakeElementLocator,
    FakeKeyboard,
    FakeMemoryConfig,
    FakeMemoryPort,
    FakeMouse,
    MemoryFaultMode,
)

__all__ = [
    "CircuitState",
    "ContextFaultMode",
    "EcosystemBridgeCoordinator",
    "EcosystemIntegrationConfig",
    "EntorhinalBridge",
    "EntorhinalBridgeMetrics",
    "EntorhinalContextAdapter",
    "FakeBrowserPage",
    "FakeCDPSession",
    "FakeContextConfig",
    "FakeContextProvider",
    "FakeElementLocator",
    "FakeKeyboard",
    "FakeMemoryConfig",
    "FakeMemoryPort",
    "FakeMouse",
    "MemoryFaultMode",
    "TraceBridge",
    "TraceBridgeMetrics",
    "TraceMemoryAdapter",
]
