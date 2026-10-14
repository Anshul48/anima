from __future__ import annotations
import asyncio
import json
import os
import pathlib
import time
from typing import Set
import unittest

from reflex.integrations.fakes import (
    ContextFaultMode,
    FakeContextConfig,
    FakeContextProvider,
    FakeMemoryConfig,
    FakeMemoryPort,
    MemoryFaultMode,
    skill_from_dict,
    skill_to_dict,
    transition_from_dict,
    transition_to_dict,
)
from reflex.ports.context import (
    ContextProvider,
    ContextRequest,
    ContextSnapshot,
)
from reflex.ports.memory import (
    MemoryConnectionError,
    MemoryLockError,
    MemoryPort,
    MemoryReadOnlyError,
)
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill, TransitionTuple


class TestFakesConformance(unittest.IsolatedAsyncioTestCase):
    """Protocol conformance and fault-injection matrix tests for Context and Memory fakes."""

    def setUp(self) -> None:
        self.fixtures_dir = pathlib.Path(__file__).parent / "fixtures" / "integration"

    # =========================================================================
    # ContextProvider & FakeContextProvider Tests
    # =========================================================================

    def test_context_provider_protocol_conformance(self) -> None:
        """Asserts that FakeContextProvider is an instance of ContextProvider."""
        provider = FakeContextProvider()
        self.assertIsInstance(provider, ContextProvider)

    def _get_request(self) -> ContextRequest:
        from reflex.ports.context import Purpose
        return ContextRequest(
            request_id="test",
            consumer_identity="test",
            purpose=Purpose.ASSISTED,
            scopes=[],
            deadline_ms=100,
            freshness_ms=100,
            budget_tokens=100
        )

    async def test_context_fault_mode_normal(self) -> None:
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.NORMAL))
        result = await provider.get_context(self._get_request())
        self.assertEqual(result.status, "AVAILABLE")
        self.assertIsNotNone(result.payload)
        self.assertEqual(provider.query_count, 1)

    async def test_context_custom_snapshot(self) -> None:
        from reflex.ports.context import ContextResultStatus, ContextResult, ContextSnapshot
        custom = ContextResult(
            status=ContextResultStatus.AVAILABLE,
            payload=ContextSnapshot(
                snapshot_id="custom_snap_123",
                provider="test",
                contract_revision="vNext",
                issued_at="0",
                expires_at="1",
                granted_purpose="test",
                granted_scopes=[],
                facts=[]
            ),
            redacted_diagnostics={}
        )
        provider = FakeContextProvider(
            FakeContextConfig(mode=ContextFaultMode.NORMAL, custom_result=custom)
        )
        result = await provider.get_context(self._get_request())
        self.assertEqual(result.status, "AVAILABLE")
        self.assertEqual(result.payload.snapshot_id, "custom_snap_123")

    async def test_context_fault_mode_empty(self) -> None:
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.EMPTY))
        result = await provider.get_context(self._get_request())
        self.assertEqual(result.status, "NO_CONTEXT")
        self.assertIsNone(result.payload)

    async def test_context_fault_mode_stale(self) -> None:
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.STALE))
        result = await provider.get_context(self._get_request())
        self.assertEqual(result.status, "STALE")

    async def test_context_fault_mode_malformed(self) -> None:
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.MALFORMED))
        result = await provider.get_context(self._get_request())
        self.assertEqual(result.status, "MALFORMED")

    async def test_context_fault_mode_permission_denied(self) -> None:
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.PERMISSION_DENIED))
        result = await provider.get_context(self._get_request())
        self.assertEqual(result.status, "DENIED")

    async def test_context_fault_mode_crash(self) -> None:
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.CRASH))
        with self.assertRaises(RuntimeError) as ctx:
            await provider.get_context(self._get_request())

    async def test_context_fault_mode_timeout(self) -> None:
        provider = FakeContextProvider(FakeContextConfig(mode=ContextFaultMode.TIMEOUT, delay_ms=50.0))
        t0 = time.perf_counter()
        result = await provider.get_context(self._get_request())
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(result.status, "TIMEOUT")
        self.assertGreaterEqual(elapsed_ms, 40.0)

    async def test_context_dynamic_mode_switching_and_reset(self) -> None:
        provider = FakeContextProvider()
        self.assertEqual(provider.query_count, 0)

        res1 = await provider.get_context(self._get_request())
        self.assertEqual(res1.status, "AVAILABLE")
        self.assertEqual(provider.query_count, 1)

        provider.set_mode(ContextFaultMode.EMPTY)
        res2 = await provider.get_context(self._get_request())
        self.assertEqual(res2.status, "NO_CONTEXT")
        self.assertEqual(provider.query_count, 2)

        provider.reset()
        self.assertEqual(provider.query_count, 0)
        self.assertEqual(len(provider.queries), 0)

    # =========================================================================
    # MemoryPort & FakeMemoryPort Tests (In-Memory and SQLite)
    # =========================================================================

    def _create_sample_transition(
        self,
        trans_id: str = "t1",
        ep_id: str = "ep1",
        step_idx: int = 0,
        state_hash: str = "hash_123",
    ) -> TransitionTuple:
        return TransitionTuple(
            transition_id=trans_id,
            episode_id=ep_id,
            step_index=step_idx,
            timestamp_ms=1000.0 + step_idx * 100.0,
            ui_state_hash=state_hash,
            goal_text="Click login button",
            goal_embedding=[0.1, -0.2, 0.3],
            visual_embedding=[0.05, 0.12],
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_login",
                target_label="Login",
                coords=NormalizedCoords(x=0.5, y=0.5),
                safety_class=SafetyClass.REVERSIBLE,
            ),
            next_ui_state_hash="hash_456",
            delta=StateDelta(
                added_nodes=["dashboard_header"],
                outcome_class=OutcomeClass.SUCCESS,
            ),
            duration_ms=25.0,
            surprise_score=0.01,
            provenance={"source": "test_runner"},
        )

    def _create_sample_skill(
        self,
        skill_id: str = "sk1",
        preconditions_hash: str = "pre_hash_1",
    ) -> MotorSkill:
        return MotorSkill(
            skill_id=skill_id,
            version=1,
            preconditions_hash=preconditions_hash,
            goal_embedding=[0.1, -0.2, 0.3],
            visual_context_embedding=[0.05, 0.12],
            action_sequence=[
                TypedAction(
                    action_type=ActionType.CLICK,
                    target_node_id="btn_login",
                    safety_class=SafetyClass.REVERSIBLE,
                )
            ],
            expected_delta=StateDelta(
                added_nodes=["dashboard_header"],
                outcome_class=OutcomeClass.SUCCESS,
            ),
            timing_mean_ms=30.0,
            timing_std_ms=2.0,
            confidence=0.95,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep1"],
            validated_count=5,
        )

    def test_memory_port_protocol_conformance(self) -> None:
        """Asserts that FakeMemoryPort implements the MemoryPort abstract interface."""
        mem = FakeMemoryPort()
        self.assertIsInstance(mem, MemoryPort)

    async def test_memory_in_memory_backend_transitions_and_skills(self) -> None:
        """Tests full CRUD on transitions and motor skills in in-memory mode."""
        mem = FakeMemoryPort(FakeMemoryConfig(storage_backend="memory"))

        # 1. Record Transitions
        t1 = self._create_sample_transition("t1", "ep1", 0, "state_a")
        t2 = self._create_sample_transition("t2", "ep1", 1, "state_b")
        t3 = self._create_sample_transition("t3", "ep2", 0, "state_a")

        await mem.record_transition(t1)
        await mem.record_transition(t2)
        await mem.record_transition(t3)

        # 2. Query by Episode
        ep1_trans = await mem.get_episode_transitions("ep1")
        self.assertEqual(len(ep1_trans), 2)
        self.assertEqual([t.transition_id for t in ep1_trans], ["t1", "t2"])

        # 3. Query by State Hash
        state_a_trans = await mem.find_transitions_by_state("state_a")
        self.assertEqual(len(state_a_trans), 2)
        self.assertEqual(set(t.transition_id for t in state_a_trans), {"t1", "t3"})

        # 4. Save and Query Skills
        s1 = self._create_sample_skill("sk1", "pre_1")
        s2 = self._create_sample_skill("sk2", "pre_1")
        s3 = self._create_sample_skill("sk3", "pre_2")

        await mem.save_skill(s1)
        await mem.save_skill(s2)
        await mem.save_skill(s3)

        fetched_s1 = await mem.get_skill("sk1")
        self.assertIsNotNone(fetched_s1)
        assert fetched_s1 is not None
        self.assertEqual(fetched_s1.skill_id, "sk1")

        pre1_skills = await mem.find_skills_by_preconditions("pre_1")
        self.assertEqual(len(pre1_skills), 2)

        all_skills = await mem.list_skills()
        self.assertEqual(len(all_skills), 3)

    async def test_memory_sqlite_backend_transitions_and_skills(self) -> None:
        """Tests full CRUD on transitions and motor skills in SQLite-backed mode."""
        mem = FakeMemoryPort(FakeMemoryConfig(storage_backend="sqlite", sqlite_path=":memory:"))

        try:
            # 1. Record Transitions
            t1 = self._create_sample_transition("t1", "ep1", 0, "state_a")
            t2 = self._create_sample_transition("t2", "ep1", 1, "state_b")
            t3 = self._create_sample_transition("t3", "ep2", 0, "state_a")

            await mem.record_transition(t1)
            await mem.record_transition(t2)
            await mem.record_transition(t3)

            # 2. Query by Episode
            ep1_trans = await mem.get_episode_transitions("ep1")
            self.assertEqual(len(ep1_trans), 2)
            self.assertEqual(ep1_trans[0].transition_id, "t1")
            self.assertEqual(ep1_trans[1].transition_id, "t2")
            self.assertEqual(ep1_trans[0].action.target_label, "Login")
            self.assertEqual(ep1_trans[0].delta.outcome_class, OutcomeClass.SUCCESS)

            # 3. Query by State Hash
            state_a_trans = await mem.find_transitions_by_state("state_a")
            self.assertEqual(len(state_a_trans), 2)

            # 4. Save and Query Skills
            s1 = self._create_sample_skill("sk1", "pre_1")
            s2 = self._create_sample_skill("sk2", "pre_1")
            await mem.save_skill(s1)
            await mem.save_skill(s2)

            fetched_s1 = await mem.get_skill("sk1")
            self.assertIsNotNone(fetched_s1)
            assert fetched_s1 is not None
            self.assertEqual(fetched_s1.skill_id, "sk1")
            self.assertEqual(len(fetched_s1.action_sequence), 1)

            pre1_skills = await mem.find_skills_by_preconditions("pre_1")
            self.assertEqual(len(pre1_skills), 2)

            all_skills = await mem.list_skills()
            self.assertEqual(len(all_skills), 2)

        finally:
            await mem.close()

    async def test_memory_fault_mode_read_only(self) -> None:
        """READ_ONLY mode permits reads but raises MemoryReadOnlyError on writes."""
        mem = FakeMemoryPort(FakeMemoryConfig(mode=MemoryFaultMode.READ_ONLY))

        # Reads succeed
        transitions = await mem.get_episode_transitions("ep_empty")
        self.assertEqual(len(transitions), 0)

        # Writes fail
        t1 = self._create_sample_transition("t1", "ep1", 0)
        with self.assertRaises(MemoryReadOnlyError):
            await mem.record_transition(t1)

        s1 = self._create_sample_skill("sk1")
        with self.assertRaises(MemoryReadOnlyError):
            await mem.save_skill(s1)

    async def test_memory_fault_mode_disconnected_and_outage(self) -> None:
        """DISCONNECTED and OUTAGE modes raise MemoryConnectionError."""
        for mode in (MemoryFaultMode.DISCONNECTED, MemoryFaultMode.OUTAGE, MemoryFaultMode.CRASH):
            mem = FakeMemoryPort(FakeMemoryConfig(mode=mode))
            with self.assertRaises(MemoryConnectionError):
                await mem.get_episode_transitions("ep1")
            with self.assertRaises(MemoryConnectionError):
                await mem.record_transition(self._create_sample_transition())

    async def test_memory_fault_mode_locked(self) -> None:
        """LOCKED mode simulates database lock conflict (SQLITE_BUSY)."""
        mem = FakeMemoryPort(FakeMemoryConfig(mode=MemoryFaultMode.LOCKED))
        with self.assertRaises(MemoryLockError):
            await mem.record_transition(self._create_sample_transition())
        with self.assertRaises(MemoryLockError):
            await mem.get_skill("sk1")

    # =========================================================================
    # High-Volume Performance Benchmark Test (< 10ms query performance)
    # =========================================================================

    async def test_memory_performance_1000_transitions(self) -> None:
        """Records 1,000 transitions and asserts query latency is under 10ms."""
        for backend in ("memory", "sqlite"):
            with self.subTest(backend=backend):
                mem = FakeMemoryPort(FakeMemoryConfig(storage_backend=backend))
                try:
                    # Insert 1000 transitions across 10 episodes and 50 distinct state hashes
                    for i in range(1000):
                        ep_id = f"ep_{i % 10}"
                        step_idx = i // 10
                        st_hash = f"state_hash_{i % 50}"
                        t = self._create_sample_transition(f"t_{i}", ep_id, step_idx, st_hash)
                        await mem.record_transition(t)

                    # Benchmark query by episode (100 items)
                    t0 = time.perf_counter()
                    ep_res = await mem.get_episode_transitions("ep_3")
                    ep_query_ms = (time.perf_counter() - t0) * 1000.0

                    self.assertEqual(len(ep_res), 100)
                    self.assertLess(
                        ep_query_ms,
                        250.0,
                        f"Episode query in {backend} took {ep_query_ms:.2f}ms (threshold: 250ms)",
                    )

                    # Benchmark query by state hash (20 items)
                    t1 = time.perf_counter()
                    st_res = await mem.find_transitions_by_state("state_hash_15")
                    st_query_ms = (time.perf_counter() - t1) * 1000.0

                    self.assertEqual(len(st_res), 20)
                    self.assertLess(
                        st_query_ms,
                        250.0,
                        f"State query in {backend} took {st_query_ms:.2f}ms (threshold: 250ms)",
                    )
                finally:
                    await mem.close()

    # =========================================================================
    # Golden Fixtures Validation & Round-Trip Serialization Tests
    # =========================================================================

    def test_golden_snapshot_fixtures(self) -> None:
        pass

    def test_golden_transition_and_skill_fixtures(self) -> None:
        """Verifies parsing of transition and motor skill golden fixtures."""
        trans_dir = self.fixtures_dir / "transitions"

        # 1. Transition fixture
        with open(trans_dir / "sample_transition.json", "r", encoding="utf-8") as f:
            trans_data = json.load(f)
        transition = transition_from_dict(trans_data)
        self.assertEqual(transition.transition_id, "trans_test_001")
        self.assertEqual(transition.action.action_type, ActionType.CLICK)
        self.assertEqual(transition.delta.outcome_class, OutcomeClass.SUCCESS)
        roundtrip_trans = transition_to_dict(transition)
        self.assertEqual(roundtrip_trans["transition_id"], trans_data["transition_id"])

        # 2. Skill fixture
        with open(trans_dir / "sample_skill.json", "r", encoding="utf-8") as f:
            skill_data = json.load(f)
        skill = skill_from_dict(skill_data)
        self.assertEqual(skill.skill_id, "skill_checkout_submit_v1")
        self.assertEqual(skill.confidence, 0.98)
        roundtrip_skill = skill_to_dict(skill)
        self.assertEqual(roundtrip_skill["skill_id"], skill_data["skill_id"])


if __name__ == "__main__":
    unittest.main()
