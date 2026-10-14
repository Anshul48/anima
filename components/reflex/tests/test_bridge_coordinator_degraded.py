"""Coordinator graceful-degradation tests (run with AND without entorhinal_bridge).

These tests never import the optional git-ignored entorhinal component, so
they execute on clean checkouts too, proving standalone operation.
"""

from __future__ import annotations

import asyncio
import unittest

from reflex.integrations.bridges import ENTORHINAL_AVAILABLE
from reflex.integrations.bridges.config import EcosystemIntegrationConfig
from reflex.integrations.bridges.coordinator import EcosystemBridgeCoordinator
from reflex.integrations.fakes.fake_context import FakeContextProvider


class TestCoordinatorDegraded(unittest.TestCase):
    def test_import_exposes_availability_flag(self) -> None:
        self.assertIsInstance(ENTORHINAL_AVAILABLE, bool)

    def test_coordinator_constructs_without_bridge(self) -> None:
        coordinator = EcosystemBridgeCoordinator()
        if ENTORHINAL_AVAILABLE:
            self.assertIsNotNone(coordinator.entorhinal_bridge)
        else:
            self.assertIsNone(coordinator.entorhinal_bridge)

    def test_context_provider_falls_back_when_bridge_absent(self) -> None:
        coordinator = EcosystemBridgeCoordinator()
        if not ENTORHINAL_AVAILABLE:
            self.assertIsInstance(
                coordinator.context_provider, FakeContextProvider
            )
        else:
            self.assertIsNotNone(coordinator.context_provider)

    def test_enable_is_safe_without_bridge(self) -> None:
        coordinator = EcosystemBridgeCoordinator()
        coordinator.disable_entorhinal()
        coordinator.enable_entorhinal()
        if not ENTORHINAL_AVAILABLE:
            self.assertFalse(coordinator.config.entorhinal_enabled)

    def test_health_reports_unavailable_without_bridge(self) -> None:
        if ENTORHINAL_AVAILABLE:
            self.skipTest("requires absent entorhinal_bridge")
        coordinator = EcosystemBridgeCoordinator()
        health = asyncio.run(coordinator.check_health())
        self.assertEqual(health["entorhinal"]["status"], "UNAVAILABLE")
        self.assertTrue(health["standalone_ready"])


if __name__ == "__main__":
    unittest.main()
