import asyncio
from typing import Any, Dict, List, Optional
import unittest

from reflex.ports import (
    ActionPort,
    ActionReceipt,
    ActionStatus,
    ClockPort,
    DeterministicClock,
    MemoryPort,
    ObservationPort,
    SystemClock,
    VerificationPort,
)
from reflex.ports.context import (
    ContextProvider,
    ContextRequest,
    ContextSnapshot,
    ContextResult,
)
from reflex.schemas import (
    ActionIdentity,
    ActionType,
    BoundingBox,
    CanonicalUIGraph,
    OutcomeClass,
    NodeRole,
    StateDelta,
    TransitionTuple,
    TypedAction,
    UIStateNode,
)


class MockObservationAdapter(ObservationPort):
    def __init__(self, graph: CanonicalUIGraph):
        self.graph = graph

    async def capture_state(self) -> CanonicalUIGraph:
        return self.graph

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_screenshot_bytes"


class MockActionAdapter(ActionPort):
    def __init__(self):
        self.dispatched_actions = []

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatched_actions.append((action, identity))
        return {"status": "ok", "action_id": identity.action_id}


class MockVerificationAdapter(VerificationPort):
    async def verify_transition(
        self,
        before_state: CanonicalUIGraph,
        action: TypedAction,
        after_state: CanonicalUIGraph,
        expected_delta: Optional[StateDelta] = None,
    ) -> StateDelta:
        return expected_delta or StateDelta(outcome_class=OutcomeClass.SUCCESS)


class MockContextProvider(ContextProvider):
    def __init__(self, snapshot=None):
        pass

    async def get_context(self, request: ContextRequest) -> ContextResult:
        from reflex.ports.context import ContextResultStatus
        return ContextResult(status=ContextResultStatus.AVAILABLE, payload=None, redacted_diagnostics={})


class MockMemoryAdapter(MemoryPort):
    def __init__(self):
        self.transitions: List[TransitionTuple] = []

    async def record_transition(self, transition: TransitionTuple) -> None:
        self.transitions.append(transition)

    async def get_episode_transitions(self, episode_id: str) -> List[TransitionTuple]:
        return [t for t in self.transitions if t.episode_id == episode_id]

    async def find_transitions_by_state(self, state_hash: str) -> List[TransitionTuple]:
        return [t for t in self.transitions if t.ui_state_hash == state_hash]


class TestPortsContract(unittest.TestCase):
    def test_abstract_port_instantiation_prohibited(self):
        """Ensures that abstract port ABCs cannot be instantiated directly without implementations."""
        with self.assertRaises(TypeError):
            ObservationPort()  # type: ignore

        with self.assertRaises(TypeError):
            ActionPort()  # type: ignore

        with self.assertRaises(TypeError):
            VerificationPort()  # type: ignore

        with self.assertRaises(TypeError):
            ContextProvider()  # type: ignore

        with self.assertRaises(TypeError):
            MemoryPort()  # type: ignore

        with self.assertRaises(TypeError):
            ClockPort()  # type: ignore

    def test_mock_observation_port_conformance(self):
        async def run():
            node = UIStateNode(
                node_id="btn1",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(0, 0, 10, 10),
            )
            graph = CanonicalUIGraph(timestamp_ms=100.0, nodes={"btn1": node})
            adapter = MockObservationAdapter(graph)

            captured = await adapter.capture_state()
            self.assertEqual(captured.timestamp_ms, 100.0)
            self.assertIn("btn1", captured.nodes)

            screenshot = await adapter.capture_screenshot()
            self.assertTrue(screenshot.startswith(b"\x89PNG"))

        asyncio.run(run())

    def test_mock_action_port_conformance(self):
        async def run():
            adapter = MockActionAdapter()
            identity = ActionIdentity.create("sess_1", 1)
            action = TypedAction(action_type=ActionType.CLICK)

            res = await adapter.dispatch_action(action, identity)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(len(adapter.dispatched_actions), 1)

        asyncio.run(run())

    def test_mock_verification_port_conformance(self):
        async def run():
            adapter = MockVerificationAdapter()
            graph = CanonicalUIGraph(timestamp_ms=100.0, nodes={})
            action = TypedAction(action_type=ActionType.CLICK)
            delta = StateDelta(added_nodes=["n1"], outcome_class=OutcomeClass.SUCCESS)

            res = await adapter.verify_transition(graph, action, graph, delta)
            self.assertEqual(res.outcome_class, OutcomeClass.SUCCESS)
            self.assertEqual(res.added_nodes, ["n1"])

        asyncio.run(run())

    def test_mock_context_provider_conformance(self):
        async def run():
            provider = MockContextProvider()
            from reflex.ports.context import Purpose
            req = ContextRequest(
                request_id="req1",
                consumer_identity="test",
                purpose=Purpose.ASSISTED,
                scopes=[],
                deadline_ms=100,
                freshness_ms=500,
                budget_tokens=10,
            )
            result = await provider.get_context(req)
            self.assertEqual(result.status, "AVAILABLE")
        asyncio.run(run())

    def test_mock_memory_port_conformance(self):
        async def run():
            adapter = MockMemoryAdapter()
            action = TypedAction(action_type=ActionType.CLICK)
            delta = StateDelta()
            t1 = TransitionTuple(
                transition_id="tr1",
                episode_id="ep1",
                step_index=1,
                timestamp_ms=100.0,
                ui_state_hash="hash_a",
                goal_text="Click button",
                goal_embedding=[0.1, 0.2],
                visual_embedding=None,
                action=action,
                next_ui_state_hash="hash_b",
                delta=delta,
                duration_ms=15.0,
                surprise_score=0.0,
            )
            t2 = TransitionTuple(
                transition_id="tr2",
                episode_id="ep1",
                step_index=2,
                timestamp_ms=120.0,
                ui_state_hash="hash_b",
                goal_text="Click next",
                goal_embedding=[0.1, 0.2],
                visual_embedding=None,
                action=action,
                next_ui_state_hash="hash_c",
                delta=delta,
                duration_ms=12.0,
                surprise_score=0.0,
            )

            await adapter.record_transition(t1)
            await adapter.record_transition(t2)

            ep_transitions = await adapter.get_episode_transitions("ep1")
            self.assertEqual(len(ep_transitions), 2)

            by_state = await adapter.find_transitions_by_state("hash_a")
            self.assertEqual(len(by_state), 1)
            self.assertEqual(by_state[0].transition_id, "tr1")

            # Default skill methods return None / pass
            self.assertIsNone(await adapter.get_skill("skill_none"))

        asyncio.run(run())

    def test_system_clock_and_deterministic_clock(self):
        async def run():
            sys_clock = SystemClock()
            t1 = sys_clock.now_ms()
            m1 = sys_clock.monotonic_ms()
            self.assertGreater(t1, 0.0)
            self.assertGreater(m1, 0.0)

            det_clock = DeterministicClock(start_time_ms=5000.0)
            self.assertEqual(det_clock.now_ms(), 5000.0)
            self.assertEqual(det_clock.monotonic_ms(), 5000.0)

            det_clock.advance(250.0)
            self.assertEqual(det_clock.now_ms(), 5250.0)

            await det_clock.sleep(0.5)  # 500 ms
            self.assertEqual(det_clock.now_ms(), 5750.0)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
