"""Reflex Conformance Test Suite for Entorhinal Integration (vNext)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict
import unittest
from unittest.mock import AsyncMock
import urllib.error

from reflex.integrations.bridges.config import EcosystemIntegrationConfig
import pytest

pytest.importorskip(
    "reflex.integrations.bridges.entorhinal_bridge",  # optional, git-ignored component
)

from reflex.integrations.bridges.entorhinal_bridge import EntorhinalBridge
from reflex.integrations.fakes.fake_context import (
    ContextFaultMode,
    FakeContextProvider,
)
from reflex.ports.context import (
    ContextRequest,
    ContextResultStatus,
    Purpose,
)

CORPUS_PATH = Path(__file__).parent.parent / "docs" / "contract" / "vNext" / "corpus.json"

def load_corpus() -> Dict[str, Any]:
    if not CORPUS_PATH.exists():
        # Fallback if path is wrong in test environment
        alt_path = Path("docs/contract/vNext/corpus.json")
        if alt_path.exists():
            with open(alt_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"fixtures": []}
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

class TestEntorhinalConformance(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.config = EcosystemIntegrationConfig(
            entorhinal_enabled=True,
            entorhinal_endpoint="http://127.0.0.1:4140",
            entorhinal_timeout_ms=100.0,
            entorhinal_circuit_breaker_threshold=3,
            entorhinal_circuit_breaker_reset_ms=200.0,
        )
        self.corpus = load_corpus()
        self.fixtures = {f["id"]: f for f in self.corpus.get("fixtures", [])}

    def _get_request(self) -> ContextRequest:
        return ContextRequest(
            request_id="test_req",
            consumer_identity="test",
            purpose=Purpose.EVALUATION,
            scopes=["project_identity"],
            deadline_ms=100,
            freshness_ms=5000,
            budget_tokens=10
        )

    async def test_01_valid_snapshot(self) -> None:
        fixture = self.fixtures.get("CORPUS-01-MINIMAL-VALID")
        if not fixture:
            self.skipTest("Fixture not found")

        transport = AsyncMock(return_value=fixture["response"])
        bridge = EntorhinalBridge(config=self.config, transport=transport)
        req = self._get_request()
        
        result = await bridge.get_context(req)
        self.assertEqual(result.status, ContextResultStatus.AVAILABLE)
        self.assertIsNotNone(result.payload)
        self.assertEqual(result.payload.snapshot_id, "10000000-0000-0000-0000-000000000001")
        self.assertEqual(len(result.payload.facts), 1)
        self.assertEqual(result.payload.facts[0].fact_id, "fact_01")

    async def test_02_no_context(self) -> None:
        fixture = self.fixtures.get("CORPUS-02-NO-CONTEXT")
        if not fixture:
            self.skipTest("Fixture not found")

        transport = AsyncMock(return_value=fixture["response"])
        bridge = EntorhinalBridge(config=self.config, transport=transport)
        req = self._get_request()
        
        result = await bridge.get_context(req)
        self.assertEqual(result.status, ContextResultStatus.NO_CONTEXT)
        self.assertIsNone(result.payload)

    async def test_03_policy_denial(self) -> None:
        fixture = self.fixtures.get("CORPUS-03-POLICY-DENIAL")
        if not fixture:
            self.skipTest("Fixture not found")

        transport = AsyncMock(return_value=fixture["response"])
        bridge = EntorhinalBridge(config=self.config, transport=transport)
        req = self._get_request()
        
        result = await bridge.get_context(req)
        self.assertEqual(result.status, ContextResultStatus.DENIED)
        self.assertIsNone(result.payload)

    async def test_12_injection_passive(self) -> None:
        fixture = self.fixtures.get("CORPUS-12-INJECTION")
        if not fixture:
            self.skipTest("Fixture not found")

        transport = AsyncMock(return_value=fixture["response"])
        bridge = EntorhinalBridge(config=self.config, transport=transport)
        req = self._get_request()
        
        result = await bridge.get_context(req)
        self.assertEqual(result.status, ContextResultStatus.AVAILABLE)
        self.assertIsNotNone(result.payload)
        fact_text = result.payload.facts[0].text
        self.assertIn("rm -rf", fact_text)

    async def test_timeout_fallback(self) -> None:
        async def delayed_transport(*args, **kwargs):
            await asyncio.sleep(0.3)
            return {}
            
        bridge = EntorhinalBridge(config=self.config, transport=delayed_transport)
        req = self._get_request()
        result = await bridge.get_context(req)
        self.assertEqual(result.status, ContextResultStatus.TIMEOUT)

    async def test_http_error(self) -> None:
        transport = AsyncMock(side_effect=urllib.error.HTTPError("url", 403, "msg", {}, None))
        bridge = EntorhinalBridge(config=self.config, transport=transport)
        req = self._get_request()
        result = await bridge.get_context(req)
        self.assertEqual(result.status, ContextResultStatus.DENIED)

if __name__ == "__main__":
    unittest.main()
