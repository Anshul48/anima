"""Reflex Ecosystem Bridge Coordinator.

Lifecycle manager, dynamic feature flag controller, and unified health monitor
for optional external bridges (Entorhinal personal context and Trace episodic memory).

Ensures complete, graceful degradation to local standalone operation whenever
external services are absent, unconfigured, or failing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from typing import Any, Dict, Optional

from reflex.integrations.bridges.config import EcosystemIntegrationConfig

try:  # Optional, git-ignored component; coordinator degrades without it.
    from reflex.integrations.bridges.entorhinal_bridge import (
        CircuitState,
        EntorhinalBridge,
        HttpTransport,
    )
except ImportError:
    CircuitState = None  # type: ignore[assignment]
    EntorhinalBridge = None  # type: ignore[assignment]
    HttpTransport = None  # type: ignore[assignment]

ENTORHINAL_AVAILABLE = EntorhinalBridge is not None
from reflex.integrations.bridges.trace_bridge import (
    TraceBridge,
    TraceHttpTransport,
)
from reflex.integrations.fakes.fake_context import FakeContextProvider
from reflex.ports.context import ContextProvider
from reflex.ports.memory import MemoryPort

logger = logging.getLogger(__name__)


class EcosystemBridgeCoordinator:
    """Manages lifecycle, health monitoring, and graceful degradation of ecosystem bridges."""

    def __init__(
        self,
        config: Optional[EcosystemIntegrationConfig] = None,
        fallback_context_provider: Optional[ContextProvider] = None,
        fallback_memory_port: Optional[MemoryPort] = None,
        entorhinal_transport: Optional[HttpTransport] = None,
        trace_transport: Optional[TraceHttpTransport] = None,
    ) -> None:
        self.config = config or EcosystemIntegrationConfig()
        self.fallback_context_provider = fallback_context_provider or FakeContextProvider()
        self.fallback_memory_port = fallback_memory_port

        # Initialize bridge instances (Entorhinal optional: None when absent).
        self.entorhinal_bridge = (
            EntorhinalBridge(
                config=self.config,
                transport=entorhinal_transport,
            )
            if EntorhinalBridge is not None
            else None
        )
        self.trace_bridge = TraceBridge(
            config=self.config,
            transport=trace_transport,
        )
        self._running = False

    @property
    def context_provider(self) -> ContextProvider:
        """Active ContextProvider: returns EntorhinalBridge if enabled, else fallback."""
        if self.config.entorhinal_enabled and self.entorhinal_bridge is not None:
            return self.entorhinal_bridge
        return self.fallback_context_provider

    @property
    def memory_port(self) -> MemoryPort:
        """Active MemoryPort: returns TraceBridge if enabled, else fallback memory port."""
        if self.config.trace_enabled:
            return self.trace_bridge
        if self.fallback_memory_port is not None:
            return self.fallback_memory_port
        return self.trace_bridge  # TraceBridge in disabled mode safely acts as local no-op/buffer

    async def start(self) -> None:
        """Starts all active bridge background tasks."""
        if self._running:
            return
        self._running = True
        if self.config.trace_enabled:
            await self.trace_bridge.start()

    async def stop(self) -> None:
        """Stops all bridge background tasks and performs clean teardown."""
        self._running = False
        await self.trace_bridge.close()

    async def close(self) -> None:
        """Alias for stop()."""
        await self.stop()

    def enable_entorhinal(self, endpoint: Optional[str] = None) -> None:
        """Dynamically enables Entorhinal personal context integration."""
        if self.entorhinal_bridge is None:
            logger.warning("Entorhinal bridge not installed; staying disabled.")
            self.config.entorhinal_enabled = False
            return
        self.config.entorhinal_enabled = True
        if endpoint:
            self.config.entorhinal_endpoint = endpoint
        self.entorhinal_bridge.config = self.config
        self.entorhinal_bridge.reset_circuit_breaker()

    def disable_entorhinal(self) -> None:
        """Dynamically disables Entorhinal personal context integration."""
        self.config.entorhinal_enabled = False
        if self.entorhinal_bridge is not None:
            self.entorhinal_bridge.config = self.config

    async def enable_trace(self, endpoint: Optional[str] = None) -> None:
        """Dynamically enables Trace episodic memory integration."""
        self.config.trace_enabled = True
        if endpoint:
            self.config.trace_endpoint = endpoint
        self.trace_bridge.config = self.config
        if self._running:
            await self.trace_bridge.start()

    async def disable_trace(self) -> None:
        """Dynamically disables Trace episodic memory integration."""
        self.config.trace_enabled = False
        self.trace_bridge.config = self.config
        await self.trace_bridge.close()

    def update_config(self, new_config: EcosystemIntegrationConfig) -> None:
        """Updates integration configuration across all managed bridges."""
        was_trace_enabled = self.config.trace_enabled
        self.config = new_config
        if self.entorhinal_bridge is not None:
            self.entorhinal_bridge.config = new_config
        self.trace_bridge.config = new_config

        if self._running:
            if not was_trace_enabled and new_config.trace_enabled:
                asyncio.create_task(self.trace_bridge.start())
            elif was_trace_enabled and not new_config.trace_enabled:
                asyncio.create_task(self.trace_bridge.close())

    async def check_health(self) -> Dict[str, Any]:
        """Performs unified health checking across all optional bridges and aggregates status."""
        if self.entorhinal_bridge is None:
            entorhinal_health: Dict[str, Any] = {
                "status": "UNAVAILABLE",
                "reason": "entorhinal_bridge not installed",
            }
        else:
            entorhinal_health = await self.entorhinal_bridge.check_health()
        trace_health = await self.trace_bridge.check_health()

        # Determine overall ecosystem status
        # If both disabled: DISABLED
        # If any enabled is UNAVAILABLE: DEGRADED (or UNAVAILABLE if all enabled are down)
        # If all enabled are HEALTHY: HEALTHY
        statuses = [entorhinal_health.get("status"), trace_health.get("status")]
        enabled_statuses = [
            s for s, enabled in [
                (entorhinal_health.get("status"), self.config.entorhinal_enabled),
                (trace_health.get("status"), self.config.trace_enabled),
            ] if enabled
        ]

        if not enabled_statuses:
            overall_status = "DISABLED"
        elif all(s == "HEALTHY" for s in enabled_statuses):
            overall_status = "HEALTHY"
        elif any(s == "HEALTHY" for s in enabled_statuses):
            overall_status = "DEGRADED"
        elif all(s == "UNAVAILABLE" for s in enabled_statuses):
            overall_status = "UNAVAILABLE"
        else:
            overall_status = "DEGRADED"

        return {
            "status": overall_status,
            "standalone_ready": True,  # Reflex core runtime is always ready regardless of bridges
            "entorhinal": entorhinal_health,
            "trace": trace_health,
        }
