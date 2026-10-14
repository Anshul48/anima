"""Unit and integration tests for EntorhinalBridge context provider."""

from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock

from reflex.integrations.bridges.config import EcosystemIntegrationConfig
import pytest

pytest.importorskip(
    "reflex.integrations.bridges.entorhinal_bridge",  # optional, git-ignored component
)

from reflex.integrations.bridges.entorhinal_bridge import (
    CircuitState,
    EntorhinalBridge,
    EntorhinalContextAdapter,
)
from reflex.ports.context import ContextRequest, ContextResultStatus, Purpose


class TestEntorhinalBridge(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.config = EcosystemIntegrationConfig(
            entorhinal_enabled=True,
            entorhinal_endpoint="http://127.0.0.1:4140",
            entorhinal_timeout_ms=100.0,
            entorhinal_circuit_breaker_threshold=3,
            entorhinal_circuit_breaker_reset_ms=200.0,
        )
        self.req = ContextRequest(
            request_id="req_1",
            consumer_identity="test",
            purpose=Purpose.ASSISTED,
            scopes=["scope1"],
            deadline_ms=100,
            freshness_ms=1000,
            budget_tokens=100,
        )

    async def test_disabled_returns_unavailable(self) -> None:
        self.config.entorhinal_enabled = False
        transport = AsyncMock()
        bridge = EntorhinalBridge(config=self.config, transport=transport)
        result = await bridge.get_context(self.req)
        self.assertEqual(result.status, ContextResultStatus.UNAVAILABLE)
        transport.assert_not_called()

    async def test_valid_context_ingestion(self) -> None:
        mock_response = {
            "status": "AVAILABLE",
            "payload": {
                "snapshot_id": "snap_valid_001",
                "provider": "test_provider",
                "contract_revision": "vNext",
                "issued_at": "2026-08-23T00:00:00Z",
                "expires_at": "2026-08-23T01:00:00Z",
                "granted_purpose": "ASSISTED",
                "granted_scopes": ["scope1"],
                "facts": [
                    {
                        "fact_id": "f1",
                        "epistemic_category": "CONFIRMED",
                        "confidence": 1.0,
                        "validity": "VALID",
                        "provenance_ref": "doc",
                        "text": "test fact",
                    }
                ],
            }
        }
        transport = AsyncMock(return_value=mock_response)
        bridge = EntorhinalBridge(config=self.config, transport=transport)
        result = await bridge.get_context(self.req)
        self.assertEqual(result.status, ContextResultStatus.AVAILABLE)
        self.assertIsNotNone(result.payload)
        self.assertEqual(result.payload.snapshot_id, "snap_valid_001")
        self.assertEqual(len(result.payload.facts), 1)

    async def test_circuit_breaker_trip(self) -> None:
        transport = AsyncMock(side_effect=RuntimeError("Connection refused"))
        bridge = EntorhinalBridge(config=self.config, transport=transport)

        for _ in range(3):
            result = await bridge.get_context(self.req)
            self.assertEqual(result.status, ContextResultStatus.UNAVAILABLE)

        self.assertTrue(bridge._circuit_open)
        
        # Next call short-circuits
        transport.reset_mock()
        result = await bridge.get_context(self.req)
        self.assertEqual(result.status, ContextResultStatus.UNAVAILABLE)
        transport.assert_not_called()

    async def test_malformed_payload_handling(self) -> None:
        malformed = {"status": "AVAILABLE", "payload": "not_a_dict"}
        transport = AsyncMock(return_value=malformed)
        bridge = EntorhinalBridge(config=self.config, transport=transport)
        result = await bridge.get_context(self.req)
        self.assertEqual(result.status, ContextResultStatus.MALFORMED)

    async def test_check_health_reporting(self) -> None:
        bridge = EntorhinalBridge(config=self.config, transport=AsyncMock())
        health = await bridge.check_health()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertTrue(health["enabled"])

        bridge.config.entorhinal_enabled = False
        health_disabled = await bridge.check_health()
        self.assertEqual(health_disabled["status"], "DISABLED")
        self.assertFalse(health_disabled["enabled"])

if __name__ == "__main__":
    unittest.main()
