"""Unit and integration tests for TraceBridge telemetry and memory exporter.

SYNTHETIC PROVENANCE: secret-like strings here ("my_secret_pass123",
"raw_secret_value", "[REDACTED]") are synthetic redaction-test vectors.
"""

from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock

from reflex.episodes.redactor import PrivacyRedactor
from reflex.integrations.bridges.config import EcosystemIntegrationConfig
from reflex.integrations.bridges.trace_bridge import (
    TraceBridge,
    TraceBridgeMetrics,
    TraceMemoryAdapter,
)
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill, TransitionTuple


def make_transition(
    transition_id: str = "tx_001",
    episode_id: str = "ep_001",
    step_index: int = 0,
    goal_text: str = "Click submit button",
    text_payload: str = None,
    action_metadata: dict = None,
) -> TransitionTuple:
    return TransitionTuple(
        transition_id=transition_id,
        episode_id=episode_id,
        step_index=step_index,
        timestamp_ms=time.time() * 1000.0,
        ui_state_hash="hash_state_a",
        goal_text=goal_text,
        goal_embedding=[0.1, 0.2, 0.3],
        visual_embedding=None,
        action=TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn_submit",
            coords=NormalizedCoords(0.5, 0.5),
            text_payload=text_payload,
            metadata=action_metadata or {},
        ),
        next_ui_state_hash="hash_state_b",
        delta=StateDelta(
            added_nodes=["modal_success"],
            outcome_class=OutcomeClass.SUCCESS,
        ),
        duration_ms=45.0,
        surprise_score=0.05,
        provenance={"source": "system2"},
    )


class TestTraceBridge(unittest.IsolatedAsyncioTestCase):
    """Test suite for TraceBridge memory and telemetry exporter."""

    def setUp(self) -> None:
        self.config = EcosystemIntegrationConfig(
            trace_enabled=True,
            trace_endpoint="http://127.0.0.1:4150",
            trace_batch_size=10,
            trace_buffer_capacity=20,  # Small capacity for fast overflow testing
            trace_flush_interval_ms=100.0,  # Fast flush for testing
            trace_timeout_ms=1000.0,
            auto_redact=True,
        )

    async def test_disabled_trace_bridge(self) -> None:
        """When trace_enabled is False, record_transition is a local no-op."""
        self.config.trace_enabled = False
        transport = AsyncMock()
        bridge = TraceBridge(config=self.config, transport=transport)

        tx = make_transition("tx_1")
        await bridge.record_transition(tx)

        self.assertEqual(bridge.buffer_size, 0)
        self.assertEqual(bridge.metrics.total_recorded, 1)
        transport.assert_not_called()

    async def test_nonblocking_async_record(self) -> None:
        """record_transition enqueues immediately in sub-millisecond time."""
        transport = AsyncMock()
        bridge = TraceBridge(config=self.config, transport=transport)

        t_start = time.time()
        for i in range(15):
            await bridge.record_transition(make_transition(f"tx_{i}", step_index=i))
        elapsed_ms = (time.time() - t_start) * 1000.0

        # Enqueueing 15 items should take well under 50ms
        self.assertLess(elapsed_ms, 50.0)
        self.assertEqual(bridge.buffer_size, 15)
        self.assertEqual(bridge.metrics.total_recorded, 15)
        self.assertEqual(bridge.dropped_count, 0)

    async def test_secret_redacted_payload_validation(self) -> None:
        """Sensitive credentials, passwords, tokens, and credit cards are scrubbed prior to queueing."""
        transport = AsyncMock()
        bridge = TraceBridge(config=self.config, transport=transport)

        sensitive_tx = make_transition(
            transition_id="tx_secret_01",
            goal_text="Log in with password: my_secret_pass123 and token: ghp_123456789012345678901234567890123456",
            text_payload="my_secret_pass123",
            action_metadata={"password": "raw_secret_value", "sessionid": "sess_xyz123", "is_password": True},
        )

        await bridge.record_transition(sensitive_tx)

        transitions = await bridge.get_episode_transitions(sensitive_tx.episode_id)
        self.assertEqual(len(transitions), 1)
        buffered_tx = transitions[0]

        # Verify sensitive goal text was scrubbed
        self.assertNotIn("my_secret_pass123", buffered_tx.goal_text)
        self.assertNotIn("ghp_123456789012345678901234567890123456", buffered_tx.goal_text)
        self.assertIn("[REDACTED", buffered_tx.goal_text)

        # Verify action payload and metadata scrubbed
        self.assertEqual(buffered_tx.action.text_payload, "[REDACTED_PASSWORD]")
        self.assertEqual(buffered_tx.action.metadata.get("password"), "[REDACTED]")
        self.assertEqual(buffered_tx.action.metadata.get("sessionid"), "[REDACTED]")

    async def test_ring_buffer_drop_oldest_overflow(self) -> None:
        """When ring buffer capacity is exceeded, oldest items are dropped and dropped_count increments."""
        self.config.trace_buffer_capacity = 5  # Set small buffer capacity of 5
        bridge = TraceBridge(config=self.config)

        # Record 8 transitions (0 to 7)
        for i in range(8):
            await bridge.record_transition(make_transition(f"tx_{i}", step_index=i))

        self.assertEqual(bridge.buffer_size, 5)
        self.assertEqual(bridge.metrics.total_recorded, 8)
        self.assertEqual(bridge.dropped_count, 3)

        # Verify oldest (tx_0, tx_1, tx_2) were dropped; buffer contains (tx_3..tx_7)
        buffered_ids = [tx.transition_id for tx in await bridge.get_episode_transitions("ep_001")]
        self.assertEqual(buffered_ids, ["tx_3", "tx_4", "tx_5", "tx_6", "tx_7"])

    async def test_batch_flush_to_trace_endpoint(self) -> None:
        """flush_now flushes batches of transitions to configured Trace endpoint."""
        transport = AsyncMock(return_value={"status": "ok", "ingested": 5})
        bridge = TraceBridge(config=self.config, transport=transport)

        for i in range(5):
            await bridge.record_transition(make_transition(f"tx_{i}", step_index=i))

        self.assertEqual(bridge.buffer_size, 5)

        exported = await bridge.flush_now()
        self.assertEqual(exported, 5)
        self.assertEqual(bridge.buffer_size, 0)
        self.assertEqual(bridge.exported_count, 5)
        self.assertEqual(bridge.metrics.batch_count, 1)

        transport.assert_called_once()
        call_args = transport.call_args
        self.assertIn("http://127.0.0.1:4150/telemetry/transitions", call_args[0][0])
        payload = call_args[0][1]
        self.assertEqual(len(payload), 5)
        self.assertEqual(payload[0]["transition_id"], "tx_0")

    async def test_loss_tolerance_on_trace_outage(self) -> None:
        """Trace backend outages / 500 errors do not raise exceptions and record metrics."""
        transport = AsyncMock(side_effect=RuntimeError("500 Internal Server Error / Trace Offline"))
        bridge = TraceBridge(config=self.config, transport=transport)

        await bridge.record_transition(make_transition("tx_1"))
        self.assertEqual(bridge.buffer_size, 1)

        # Flush fails under outage
        exported = await bridge.flush_now()
        self.assertEqual(exported, 0)
        self.assertEqual(bridge.failed_export_count, 1)
        self.assertEqual(bridge.exported_count, 0)

        # Subsequent recordings still succeed without error
        await bridge.record_transition(make_transition("tx_2"))
        self.assertEqual(bridge.buffer_size, 1)  # tx_1 was drained in batch attempt; tx_2 is now buffered

    async def test_background_flusher_task(self) -> None:
        """Background flusher task automatically flushes items periodically."""
        transport = AsyncMock(return_value={"status": "ok"})
        bridge = TraceBridge(config=self.config, transport=transport)

        await bridge.start()
        for i in range(3):
            await bridge.record_transition(make_transition(f"tx_{i}"))

        self.assertEqual(bridge.buffer_size, 3)

        # Wait for background flusher (flush interval is 100ms)
        await asyncio.sleep(0.25)

        self.assertEqual(bridge.buffer_size, 0)
        self.assertEqual(bridge.exported_count, 3)

        await bridge.close()

    async def test_motor_skill_caching(self) -> None:
        """save_skill, get_skill, find_skills_by_preconditions, and list_skills work in memory."""
        bridge = TraceBridge(config=self.config)

        skill = MotorSkill(
            skill_id="skill_login_001",
            version=1,
            preconditions_hash="pre_login_form",
            goal_embedding=[0.1, 0.2],
            visual_context_embedding=[0.3, 0.4],
            action_sequence=[
                TypedAction(ActionType.CLICK, target_node_id="btn_login"),
            ],
            expected_delta=StateDelta(added_nodes=["dashboard"]),
            timing_mean_ms=120.0,
            timing_std_ms=10.0,
            confidence=0.95,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep_001"],
            validated_count=5,
        )

        await bridge.save_skill(skill)

        fetched = await bridge.get_skill("skill_login_001")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.skill_id, "skill_login_001")
        self.assertEqual(fetched.confidence, 0.95)

        matched = await bridge.find_skills_by_preconditions("pre_login_form")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].skill_id, "skill_login_001")

        all_skills = await bridge.list_skills()
        self.assertEqual(len(all_skills), 1)

    async def test_health_check(self) -> None:
        """check_health returns structured health dictionary."""
        transport = AsyncMock(return_value={"status": "ok"})
        bridge = TraceBridge(config=self.config, transport=transport)

        health = await bridge.check_health()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertTrue(health["enabled"])

        # Disabled health check
        bridge.config.trace_enabled = False
        health_disabled = await bridge.check_health()
        self.assertEqual(health_disabled["status"], "DISABLED")
        self.assertFalse(health_disabled["enabled"])

    async def test_backward_compatibility_alias(self) -> None:
        """TraceMemoryAdapter is an alias for TraceBridge."""
        self.assertIs(TraceMemoryAdapter, TraceBridge)


if __name__ == "__main__":
    unittest.main()
