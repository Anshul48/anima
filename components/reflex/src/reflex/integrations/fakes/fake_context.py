from __future__ import annotations
import asyncio
from dataclasses import dataclass
from enum import Enum
import time
from typing import Any, Dict, List, Optional

from reflex.ports.context import (
    ContextMalformedError,
    ContextPermissionDeniedError,
    ContextProvider,
    ContextRequest,
    ContextSnapshot,
    ContextResult,
    ContextResultStatus,
    ContextUnavailableError,
    Fact,
)


class ContextFaultMode(str, Enum):
    NORMAL = "normal"
    EMPTY = "empty"
    STALE = "stale"
    MALFORMED = "malformed"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    CRASH = "crash"


@dataclass
class FakeContextConfig:
    mode: ContextFaultMode = ContextFaultMode.NORMAL
    delay_ms: float = 0.0
    custom_result: Optional[ContextResult] = None
    stale_age_ms: float = 86400000.0
    error_message: Optional[str] = None


class FakeContextProvider(ContextProvider):
    def __init__(self, config: Optional[FakeContextConfig] = None):
        self.config = config or FakeContextConfig()
        self.query_count: int = 0
        self.queries: List[ContextRequest] = []

    def set_mode(self, mode: ContextFaultMode, delay_ms: float = 0.0) -> None:
        self.config.mode = mode
        self.config.delay_ms = delay_ms

    def set_custom_snapshot(self, result: Optional[ContextResult]) -> None:
        self.config.custom_result = result

    def reset(self) -> None:
        self.query_count = 0
        self.queries.clear()

    async def get_context(self, request: ContextRequest) -> ContextResult:
        self.query_count += 1
        self.queries.append(request)

        mode = self.config.mode

        if mode == ContextFaultMode.TIMEOUT:
            if self.config.delay_ms > 0:
                await asyncio.sleep(self.config.delay_ms / 1000.0)
            return ContextResult(status=ContextResultStatus.TIMEOUT, payload=None, redacted_diagnostics={})

        if mode == ContextFaultMode.EMPTY:
            return ContextResult(status=ContextResultStatus.NO_CONTEXT, payload=None, redacted_diagnostics={})

        if mode == ContextFaultMode.CRASH:
            raise RuntimeError(self.config.error_message or "Simulated Context Service Crash")

        if mode == ContextFaultMode.PERMISSION_DENIED:
            return ContextResult(status=ContextResultStatus.DENIED, payload=None, redacted_diagnostics={"error": "permission denied"})

        if mode == ContextFaultMode.STALE:
            return ContextResult(status=ContextResultStatus.STALE, payload=None, redacted_diagnostics={})

        if mode == ContextFaultMode.MALFORMED:
            return ContextResult(status=ContextResultStatus.MALFORMED, payload=None, redacted_diagnostics={})

        if self.config.delay_ms > 0:
            await asyncio.sleep(self.config.delay_ms / 1000.0)

        if self.config.custom_result is not None:
            return self.config.custom_result

        return self._create_default_result()

    def _create_default_result(self) -> ContextResult:
        return ContextResult(
            status=ContextResultStatus.AVAILABLE,
            payload=ContextSnapshot(
                snapshot_id="snap_golden_001",
                provider="fake_provider",
                contract_revision="vNext",
                issued_at="2026-08-23T00:00:00Z",
                expires_at="2026-08-23T01:00:00Z",
                granted_purpose="EVALUATION",
                granted_scopes=["project_identity"],
                facts=[
                    Fact(
                        fact_id="fact_01",
                        epistemic_category="CONFIRMED",
                        confidence=0.99,
                        validity="VALID",
                        provenance_ref="doc_01",
                        text="project: ReflexAutomation"
                    )
                ]
            ),
            redacted_diagnostics={}
        )

