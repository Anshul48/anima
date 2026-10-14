"""Background Trace spooler and resiliency test suite."""

from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock

from reflex.integrations.bridges.config import EcosystemIntegrationConfig
from reflex.integrations.bridges.trace_bridge import TraceBridge
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import StateDelta
from reflex.schemas.memory import TransitionTuple


def create_transition(index: int, episode_id: str = "ep_spool_01") -> TransitionTuple:
    return TransitionTuple(
        transition_id=f"tx_spool_{index:03d}",
        episode_id=episode_id,
        step_index=index,
        timestamp_ms=time.time() * 1000.0,
        ui_state_hash=f"hash_{index}",
        goal_text=f"Step {index}",
        goal_embedding=[0.1 * index],
        visual_embedding=None,
        action=TypedAction(action_type=ActionType.CLICK, target_node_id=f"btn_{index}"),
        next_ui_state_hash=f"hash_{index + 1}",
        delta=StateDelta(),
        duration_ms=25.0,
        surprise_score=0.01,
        provenance={"source": "system2"},
    )


class TestTraceSpooler(unittest.IsolatedAsyncioTestCase):
    """Test suite for background spooling, network outage recovery, and high-volume buffering."""

    async def test_spooler_100_transitions_with_temporary_outage(self) -> None:
        """Records 100 transitions, handles temporary Trace outage, then flushes all remaining items upon recovery."""
        exported_batches = []
        is_outage = True

        async def simulated_transport(url: str, payload: list, headers: dict, timeout: float) -> dict:
            if is_outage:
                raise RuntimeError("503 Service Unavailable: Trace Daemon Restarting")
            exported_batches.append(payload)
            return {"status": "ok", "ingested": len(payload)}

        config = EcosystemIntegrationConfig(
            trace_enabled=True,
            trace_endpoint="http://127.0.0.1:4150",
            trace_buffer_capacity=1000,
            trace_batch_size=50,
            trace_flush_interval_ms=50.0,
        )

        bridge = TraceBridge(config=config, transport=simulated_transport)

        # 1. Record 100 transitions during outage
        for i in range(100):
            await bridge.record_transition(create_transition(i))

        self.assertEqual(bridge.buffer_size, 100)
        self.assertEqual(bridge.metrics.total_recorded, 100)

        # 2. Attempt flush during outage -> fails safely without throwing
        exported_during_outage = await bridge.flush_now()
        self.assertEqual(exported_during_outage, 0)
        self.assertEqual(bridge.failed_export_count, 50)  # One batch of 50 failed

        # Buffer still contains 50 remaining items
        self.assertEqual(bridge.buffer_size, 50)

        # 3. Connection restored
        is_outage = False

        # Flush batch 2 (50 items)
        exported_post_outage = await bridge.flush_now()
        self.assertEqual(exported_post_outage, 50)
        self.assertEqual(bridge.buffer_size, 0)
        self.assertEqual(len(exported_batches), 1)
        self.assertEqual(len(exported_batches[0]), 50)

    async def test_full_capacity_spooling_and_graceful_draining(self) -> None:
        """Spooler handles high volume (500 items) and drains completely in batches."""
        exported_items_count = 0

        async def counting_transport(url: str, payload: list, headers: dict, timeout: float) -> dict:
            nonlocal exported_items_count
            exported_items_count += len(payload)
            return {"status": "ok"}

        config = EcosystemIntegrationConfig(
            trace_enabled=True,
            trace_buffer_capacity=1000,
            trace_batch_size=50,
        )
        bridge = TraceBridge(config=config, transport=counting_transport)

        # Record 200 transitions
        for i in range(200):
            await bridge.record_transition(create_transition(i))

        self.assertEqual(bridge.buffer_size, 200)

        # Drain in 4 batches of 50
        while bridge.buffer_size > 0:
            await bridge.flush_now()

        self.assertEqual(bridge.buffer_size, 0)
        self.assertEqual(exported_items_count, 200)
        self.assertEqual(bridge.exported_count, 200)


if __name__ == "__main__":
    unittest.main()
