"""Reflex Bridges Integration Package.

Optional adapter bridges for connecting Reflex to Entorhinal (context layer)
and Trace (episodic memory).
"""

from __future__ import annotations

from reflex.integrations.bridges.config import EcosystemIntegrationConfig
from reflex.integrations.bridges.coordinator import EcosystemBridgeCoordinator

try:  # Entorhinal bridge is an optional, git-ignored component.
    from reflex.integrations.bridges.entorhinal_bridge import (
        CircuitState,
        EntorhinalBridge,
        EntorhinalBridgeMetrics,
        EntorhinalContextAdapter,
    )
except ImportError:
    CircuitState = None  # type: ignore[assignment]
    EntorhinalBridge = None  # type: ignore[assignment]
    EntorhinalBridgeMetrics = None  # type: ignore[assignment]
    EntorhinalContextAdapter = None  # type: ignore[assignment]

ENTORHINAL_AVAILABLE = EntorhinalBridge is not None
from reflex.integrations.bridges.trace_bridge import (
    TraceBridge,
    TraceBridgeMetrics,
    TraceMemoryAdapter,
)

__all__ = [
    "CircuitState",
    "EcosystemBridgeCoordinator",
    "EcosystemIntegrationConfig",
    "EntorhinalBridge",
    "EntorhinalBridgeMetrics",
    "EntorhinalContextAdapter",
    "TraceBridge",
    "TraceBridgeMetrics",
    "TraceMemoryAdapter",
]
