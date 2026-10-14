"""Tests for Reflex–Entorhinal Perception Episode Bridge.

Verifies WP-03: streaming PerceptionDelta into LocalEpisodeJournal and enforcing
the zero duplicate world models architectural invariant.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from reflex.episodes.bridge import PerceptionEpisodeBridge, compute_ui_state_hash
from reflex.episodes.journal import LocalEpisodeJournal
from reflex.perception.native.linux_atspi import LinuxATSPIObservationAdapter, MockLinuxATSPISubstrate
from reflex.ports.clock import DeterministicClock
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.delta import OutcomeClass
from reflex.schemas.observation import (
    ObservationQuality,
    ObservationRecord,
    PerceptionDelta,
    SemanticChangeEvent,
    SemanticEventType,
)
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestPerceptionEntorhinalBridge(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying bridging Reflex perception into Entorhinal episodic memory."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "episodes.db")
        self.journal = LocalEpisodeJournal(db_path=self.db_path, auto_redact=False)
        self.bridge = PerceptionEpisodeBridge(journal=self.journal)
        self.clock = DeterministicClock(start_time_ms=1000.0)

    async def asyncTearDown(self) -> None:
        await self.journal.close()
        self.temp_dir.cleanup()

    async def test_01_bridge_converts_perception_delta_and_records_transition(self) -> None:
        """Asserts conversion of PerceptionDelta into TransitionTuple and storage in journal."""
        # 1. Previous observation
        prev_node = UIStateNode(
            node_id="cb_remember",
            role=NodeRole.CHECKBOX,
            bounds=BoundingBox(10, 10, 30, 30),
            label="Remember Me",
            value="false",
        )
        prev_graph = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={"cb_remember": prev_node},
            active_window_title="Login Window",
        )
        prev_obs = ObservationRecord(
            observation_id="obs_01",
            timestamp_ms=1000.0,
            source_adapter="linux_atspi",
            platform="linux",
            graph=prev_graph,
            quality=ObservationQuality.HEALTHY,
        )

        # 2. Next observation (checkbox toggled)
        curr_node = UIStateNode(
            node_id="cb_remember",
            role=NodeRole.CHECKBOX,
            bounds=BoundingBox(10, 10, 30, 30),
            label="Remember Me",
            value="true",
        )
        curr_graph = CanonicalUIGraph(
            timestamp_ms=1150.0,
            nodes={"cb_remember": curr_node},
            active_window_title="Login Window",
        )
        curr_obs = ObservationRecord(
            observation_id="obs_02",
            timestamp_ms=1150.0,
            source_adapter="linux_atspi",
            platform="linux",
            graph=curr_graph,
            quality=ObservationQuality.HEALTHY,
        )

        # 3. Perception delta
        delta = PerceptionDelta(
            source_snapshot_id=prev_obs.observation_id,
            target_snapshot_id=curr_obs.observation_id,
            timestamp_ms=1150.0,
            modified_nodes=[{"node_id": "cb_remember", "changes": {"value": {"old": "false", "new": "true"}}}],
            changed_bounding_boxes=[BoundingBox(10, 10, 30, 30)],
            pixel_change_ratio=0.015,
            semantic_events=[
                SemanticChangeEvent(
                    event_type=SemanticEventType.CHECKBOX_TOGGLED,
                    description="Remember Me toggled",
                    target_node_id="cb_remember",
                    previous_value="false",
                    current_value="true",
                    timestamp_ms=1150.0,
                )
            ],
            outcome_class=OutcomeClass.SUCCESS,
        )

        # 4. Bridge records transition
        action = TypedAction(action_type=ActionType.CLICK, target_node_id="cb_remember")
        tx = await self.bridge.record_transition_from_perception(
            episode_id="ep_bridge_01",
            step_index=0,
            prev_obs=prev_obs,
            delta=delta,
            action=action,
            next_obs=curr_obs,
            goal_text="Check remember me",
        )

        self.assertIsNotNone(tx.transition_id)
        self.assertEqual(tx.episode_id, "ep_bridge_01")
        self.assertEqual(tx.step_index, 0)
        self.assertEqual(tx.delta.modified_nodes, ["cb_remember"])
        self.assertEqual(tx.delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(tx.duration_ms, 150.0)

        # 5. Query from Entorhinal journal
        stored_list = await self.journal.get_episode_transitions("ep_bridge_01")
        self.assertEqual(len(stored_list), 1)
        self.assertEqual(stored_list[0].transition_id, tx.transition_id)
        self.assertIn("semantic_events", stored_list[0].provenance)

    async def test_02_stream_and_record_episode(self) -> None:
        """Asserts continuous streaming from ObservationPort into journal."""
        sub = MockLinuxATSPISubstrate()
        sub.add_window("Browser", "chromium", is_focused=True)
        sub.add_element("btn_search", "Search", "ROLE_PUSH_BUTTON", (10, 10, 50, 20), is_clickable=True)
        adapter = LinuxATSPIObservationAdapter(clock=self.clock, substrate=sub)
        await adapter.initialize()

        transitions = await self.bridge.stream_and_record_episode(
            observation_port=adapter,
            episode_id="ep_stream_01",
            goal_text="Stream background UI changes",
            interval_ms=20.0,
            max_steps=3,
        )

        self.assertEqual(len(transitions), 3)
        for i, tx in enumerate(transitions):
            self.assertEqual(tx.episode_id, "ep_stream_01")
            self.assertEqual(tx.step_index, i)

        stored = await self.journal.get_episode_transitions("ep_stream_01")
        self.assertEqual(len(stored), 3)
        await adapter.teardown()

    def test_03_zero_world_model_duplication_invariant(self) -> None:
        """Asserts that ObservationPort maintains NO episode history or predictive graph."""
        sub = MockLinuxATSPISubstrate()
        adapter = LinuxATSPIObservationAdapter(clock=self.clock, substrate=sub)

        # Adapter must not possess episode journals or world model tables
        self.assertFalse(hasattr(adapter, "episode_journal"))
        self.assertFalse(hasattr(adapter, "world_model"))
        self.assertFalse(hasattr(adapter, "transition_graph"))
        self.assertFalse(hasattr(adapter, "history"))


if __name__ == "__main__":
    unittest.main()
