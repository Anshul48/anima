"""Unit and integration tests for EcosystemBridgeCoordinator."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock

from reflex.integrations.bridges.config import EcosystemIntegrationConfig
from reflex.integrations.bridges.coordinator import EcosystemBridgeCoordinator
import pytest

pytest.importorskip(
    "reflex.integrations.bridges.entorhinal_bridge",  # optional, git-ignored component
)

from reflex.integrations.bridges.entorhinal_bridge import CircuitState, EntorhinalBridge
from reflex.integrations.bridges.trace_bridge import TraceBridge
from reflex.integrations.fakes.fake_context import FakeContextProvider
from reflex.integrations.fakes.fake_memory import FakeMemoryPort
from reflex.ports.context import ContextRequest
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import StateDelta
from reflex.schemas.memory import TransitionTuple


def make_sample_transition(transition_id: str = "tx_01") -> TransitionTuple:
    return TransitionTuple(
        transition_id=transition_id,
        episode_id="ep_01",
        step_index=0,
        timestamp_ms=1000.0,
        ui_state_hash="hash_a",
        goal_text="Sample goal",
        goal_embedding=[0.1],
        visual_embedding=None,
        action=TypedAction(action_type=ActionType.CLICK, target_node_id="btn"),
        next_ui_state_hash="hash_b",
        delta=StateDelta(),
        duration_ms=10.0,
        surprise_score=0.0,
        provenance={},
    )


class TestBridgeCoordinator(unittest.IsolatedAsyncioTestCase):
    """Test suite for EcosystemBridgeCoordinator."""

    def setUp(self) -> None:
        self.config = EcosystemIntegrationConfig(
            entorhinal_enabled=False,
            trace_enabled=False,
        )
        self.fallback_context = FakeContextProvider()
        self.fallback_memory = FakeMemoryPort()

    async def test_standalone_operation_both_disabled(self) -> None:
        """Standalone Reflex V1 runs with complete functionality when all bridges are disabled."""
        coordinator = EcosystemBridgeCoordinator(
            config=self.config,
            fallback_context_provider=self.fallback_context,
            fallback_memory_port=self.fallback_memory,
        )

        # ContextProvider resolves to fallback provider
        self.assertIs(coordinator.context_provider, self.fallback_context)

        # MemoryPort resolves to fallback memory port
        self.assertIs(coordinator.memory_port, self.fallback_memory)

        # Health check reports DISABLED status and standalone readiness
        health = await coordinator.check_health()
        self.assertEqual(health["status"], "DISABLED")
        self.assertTrue(health["standalone_ready"])
        self.assertFalse(health["entorhinal"]["enabled"])
        self.assertFalse(health["trace"]["enabled"])

    async def test_dynamic_enabling_and_disabling_entorhinal(self) -> None:
        """Entorhinal bridge can be dynamically toggled at runtime without restart."""
        coordinator = EcosystemBridgeCoordinator(
            config=self.config,
            fallback_context_provider=self.fallback_context,
            fallback_memory_port=self.fallback_memory,
        )

        self.assertIs(coordinator.context_provider, self.fallback_context)

        # Dynamically enable Entorhinal
        coordinator.enable_entorhinal("http://127.0.0.1:4140")
        self.assertTrue(coordinator.config.entorhinal_enabled)
        self.assertIs(coordinator.context_provider, coordinator.entorhinal_bridge)

        # Dynamically disable Entorhinal
        coordinator.disable_entorhinal()
        self.assertFalse(coordinator.config.entorhinal_enabled)
        self.assertIs(coordinator.context_provider, self.fallback_context)

    async def test_dynamic_enabling_and_disabling_trace(self) -> None:
        """Trace bridge can be dynamically toggled at runtime."""
        coordinator = EcosystemBridgeCoordinator(
            config=self.config,
            fallback_context_provider=self.fallback_context,
            fallback_memory_port=self.fallback_memory,
        )

        self.assertIs(coordinator.memory_port, self.fallback_memory)

        # Dynamically enable Trace
        await coordinator.enable_trace("http://127.0.0.1:4150")
        self.assertTrue(coordinator.config.trace_enabled)
        self.assertIs(coordinator.memory_port, coordinator.trace_bridge)

        # Dynamically disable Trace
        await coordinator.disable_trace()
        self.assertFalse(coordinator.config.trace_enabled)
        self.assertIs(coordinator.memory_port, self.fallback_memory)

    async def test_health_monitoring_aggregation(self) -> None:
        """Health monitor aggregates statuses across active and failing bridges."""
        entorhinal_transport = AsyncMock(return_value={"status": "ok"})
        trace_transport = AsyncMock(side_effect=RuntimeError("Trace connection refused"))

        self.config.entorhinal_enabled = True
        self.config.trace_enabled = True

        coordinator = EcosystemBridgeCoordinator(
            config=self.config,
            entorhinal_transport=entorhinal_transport,
            trace_transport=trace_transport,
        )

        health = await coordinator.check_health()

        # One healthy, one unavailable -> Overall status is DEGRADED
        self.assertEqual(health["status"], "DEGRADED")
        self.assertTrue(health["standalone_ready"])
        self.assertEqual(health["entorhinal"]["status"], "HEALTHY")
        self.assertEqual(health["trace"]["status"], "UNAVAILABLE")

    async def test_lifecycle_start_and_stop(self) -> None:
        """start() and stop() properly manage lifecycle and background tasks."""
        self.config.trace_enabled = True
        coordinator = EcosystemBridgeCoordinator(config=self.config)

        await coordinator.start()
        self.assertTrue(coordinator._running)
        self.assertTrue(coordinator.trace_bridge._running)

        await coordinator.stop()
        self.assertFalse(coordinator._running)
        self.assertFalse(coordinator.trace_bridge._running)

    async def test_update_config(self) -> None:
        """update_config propagates settings changes across all bridges."""
        coordinator = EcosystemBridgeCoordinator(config=self.config)

        new_config = EcosystemIntegrationConfig(
            entorhinal_enabled=True,
            entorhinal_endpoint="http://10.0.0.1:4140",
            trace_enabled=True,
            trace_endpoint="http://10.0.0.1:4150",
            trace_batch_size=100,
        )

        coordinator.update_config(new_config)
        self.assertEqual(coordinator.entorhinal_bridge.config.entorhinal_endpoint, "http://10.0.0.1:4140")
        self.assertEqual(coordinator.trace_bridge.config.trace_batch_size, 100)
        self.assertIs(coordinator.context_provider, coordinator.entorhinal_bridge)
        self.assertIs(coordinator.memory_port, coordinator.trace_bridge)


if __name__ == "__main__":
    unittest.main()
