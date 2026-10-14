from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, Optional, Tuple
import unittest

from reflex.integrations.fakes import (
    ContextFaultMode,
    FakeContextConfig,
    FakeContextProvider,
)
from reflex.ports.context import (
    ContextProvider,
    ContextRequest,
    ContextSnapshot,
)
from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class MockActionExecutionLoop:
    """Mock host execution kernel demonstrating non-blocking advisory context retrieval."""

    def __init__(self, context_provider: Optional[ContextProvider] = None, context_timeout_ms: float = 50.0):
        self.context_provider = context_provider
        self.context_timeout_ms = context_timeout_ms
        self.dispatched_actions: list[TypedAction] = []
        self.last_context_used: Optional[ContextSnapshot] = None

    async def execute_step(
        self,
        ui_graph: CanonicalUIGraph,
        user_goal: str,
    ) -> Tuple[TypedAction, float]:
        """Executes a single closed-loop step.
        
        Advisory context is queried asynchronously with a strict deadline or in background;
        the action dispatch path NEVER hangs even if the context provider hangs for 10+ seconds.
        """
        step_start_time = time.perf_counter()
        advisory_snapshot: Optional[ContextSnapshot] = None

        if self.context_provider is not None:
            try:
                # Bounded advisory query: strict timeout ceiling
                from reflex.ports.context import Purpose, ContextResultStatus
                timeout_sec = self.context_timeout_ms / 1000.0
                result = await asyncio.wait_for(
                    self.context_provider.get_context(
                        ContextRequest(
                            request_id="mock_session_1",
                            consumer_identity="reflex_test",
                            purpose=Purpose.ASSISTED,
                            scopes=["browser"],
                            deadline_ms=int(self.context_timeout_ms),
                            freshness_ms=5000,
                            budget_tokens=100
                        )
                    ),
                    timeout=timeout_sec,
                )
                if result.status == ContextResultStatus.AVAILABLE:
                    advisory_snapshot = result.payload
            except (asyncio.TimeoutError, Exception):
                # Graceful degradation: live UI observation always outranks missing/failed external context
                advisory_snapshot = None

        self.last_context_used = advisory_snapshot

        # Live UI observation resolution (direct state always takes precedence)
        target_node_id = next(iter(ui_graph.nodes.keys())) if ui_graph.nodes else None
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id=target_node_id,
            target_label="Submit",
            safety_class=SafetyClass.REVERSIBLE,
        )

        # Dispatch action
        self.dispatched_actions.append(action)
        step_duration_ms = (time.perf_counter() - step_start_time) * 1000.0
        return action, step_duration_ms


class TestNonblockingContext(unittest.IsolatedAsyncioTestCase):
    """Verifies that ContextProvider latency, hangs, or failures never block the action path."""

    def _create_mock_ui_graph(self) -> CanonicalUIGraph:
        node = UIStateNode(
            node_id="btn_submit",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(10, 10, 100, 50),
            label="Submit",
        )
        return CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes={"btn_submit": node},
            url="https://app.reflex.local/checkout",
        )

    async def test_action_dispatches_immediately_with_normal_context(self) -> None:
        """With a fast normal provider, context is captured and action dispatches rapidly."""
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.NORMAL))
        loop = MockActionExecutionLoop(context_provider=provider, context_timeout_ms=50.0)

        ui_graph = self._create_mock_ui_graph()
        action, duration_ms = await loop.execute_step(ui_graph, "Submit the checkout form")

        self.assertEqual(action.action_type, ActionType.CLICK)
        self.assertEqual(len(loop.dispatched_actions), 1)
        self.assertIsNotNone(loop.last_context_used)
        self.assertLess(duration_ms, 50.0)

    async def test_10_second_hang_does_not_block_action_dispatch(self) -> None:
        """Injects a 10-second hang in FakeContextProvider; verifies step completes in < 100ms."""
        # Simulated 10-second hang in ContextProvider
        provider = FakeContextProvider(
            FakeContextConfig(mode=ContextFaultMode.TIMEOUT, delay_ms=10000.0)
        )
        loop = MockActionExecutionLoop(context_provider=provider, context_timeout_ms=50.0)

        ui_graph = self._create_mock_ui_graph()
        step_t0 = time.perf_counter()
        action, duration_ms = await loop.execute_step(ui_graph, "Submit form despite context hang")
        real_elapsed_ms = (time.perf_counter() - step_t0) * 1000.0

        # Action must be dispatched successfully
        self.assertEqual(action.action_type, ActionType.CLICK)
        self.assertEqual(len(loop.dispatched_actions), 1)
        # Context should gracefully degrade to None
        self.assertIsNone(loop.last_context_used)
        # Step execution latency must not be stalled by the 10-second hang
        self.assertLess(
            real_elapsed_ms,
            150.0,
            f"Step took {real_elapsed_ms:.2f}ms, which blocked on the 10s context hang!",
        )

    async def test_provider_crash_does_not_halt_action_loop(self) -> None:
        """When ContextProvider crashes with an unhandled exception, action dispatch still succeeds."""
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.CRASH))
        loop = MockActionExecutionLoop(context_provider=provider, context_timeout_ms=50.0)

        ui_graph = self._create_mock_ui_graph()
        action, duration_ms = await loop.execute_step(ui_graph, "Submit form when context crashes")

        self.assertEqual(action.action_type, ActionType.CLICK)
        self.assertEqual(len(loop.dispatched_actions), 1)
        self.assertIsNone(loop.last_context_used)
        self.assertLess(duration_ms, 50.0)

    async def test_permission_denied_does_not_halt_action_loop(self) -> None:
        """When ContextProvider denies permission, action dispatch proceeds unhindered."""
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.PERMISSION_DENIED))
        loop = MockActionExecutionLoop(context_provider=provider, context_timeout_ms=50.0)

        ui_graph = self._create_mock_ui_graph()
        action, duration_ms = await loop.execute_step(ui_graph, "Submit form without permission")

        self.assertEqual(action.action_type, ActionType.CLICK)
        self.assertEqual(len(loop.dispatched_actions), 1)
        self.assertIsNone(loop.last_context_used)
        self.assertLess(duration_ms, 50.0)

    async def test_absent_provider_runs_standalone(self) -> None:
        """When context_provider is None (standalone mode), action dispatches immediately."""
        loop = MockActionExecutionLoop(context_provider=None)

        ui_graph = self._create_mock_ui_graph()
        action, duration_ms = await loop.execute_step(ui_graph, "Standalone action")

        self.assertEqual(action.action_type, ActionType.CLICK)
        self.assertEqual(len(loop.dispatched_actions), 1)
        self.assertIsNone(loop.last_context_used)
        self.assertLess(duration_ms, 20.0)


if __name__ == "__main__":
    unittest.main()
