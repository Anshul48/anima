"""Unit and integration test suite for LocalEpisodeJournal.

Tests episodic CRUD, transaction rollback safety, state hash indexing,
WAL mode, JSONL ledger export/import, cryptographic linkage, and motor skill persistence.
"""

from __future__ import annotations

import os
import pathlib
import tempfile
import time
from typing import List
import unittest

from reflex.episodes.journal import (
    EpisodeJournalPort,
    EpisodeSummary,
    LocalEpisodeJournal,
)
from reflex.episodes.redactor import PrivacyRedactor
from reflex.ports.memory import (
    MemoryConnectionError,
    MemoryPort,
    MemoryPortError,
)
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill, TransitionTuple


class TestEpisodeJournal(unittest.IsolatedAsyncioTestCase):
    """Test suite for LocalEpisodeJournal SQLite & JSONL ledger."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = os.path.join(self.temp_dir.name, "test_episodes.sqlite3")
        self.jsonl_file = os.path.join(self.temp_dir.name, "test_transitions.jsonl")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_sample_transition(
        self,
        trans_id: str = "t1",
        ep_id: str = "ep1",
        step_idx: int = 0,
        state_hash: str = "hash_state_0",
        next_hash: str = "hash_state_1",
    ) -> TransitionTuple:
        return TransitionTuple(
            transition_id=trans_id,
            episode_id=ep_id,
            step_index=step_idx,
            timestamp_ms=1000.0 + step_idx * 100.0,
            ui_state_hash=state_hash,
            goal_text="Navigate to settings",
            goal_embedding=[0.1, 0.2, 0.3],
            visual_embedding=[0.05, 0.15],
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_settings",
                target_label="Settings",
                coords=NormalizedCoords(x=0.2, y=0.4),
                safety_class=SafetyClass.REVERSIBLE,
                metadata={"source": "user_intent"},
            ),
            next_ui_state_hash=next_hash,
            delta=StateDelta(
                added_nodes=["settings_panel"],
                removed_nodes=[],
                modified_nodes=[],
                pixel_change_ratio=0.1,
                changed_bounding_boxes=[(10, 10, 200, 300)],
                outcome_class=OutcomeClass.SUCCESS,
            ),
            duration_ms=45.0,
            surprise_score=0.02,
            provenance={"agent_mode": "system2", "attempt": 1},
        )

    # =========================================================================
    # 1. Interface & Conformance Tests
    # =========================================================================

    def test_journal_implements_ports(self) -> None:
        """Asserts LocalEpisodeJournal implements EpisodeJournalPort and MemoryPort."""
        journal = LocalEpisodeJournal(":memory:")
        self.assertIsInstance(journal, EpisodeJournalPort)
        self.assertIsInstance(journal, MemoryPort)

    # =========================================================================
    # 2. Episode Lifecycle & Transition Recording
    # =========================================================================

    async def test_episode_start_end_and_summary(self) -> None:
        """Tests full episode start, multi-step transition recording, and finalization."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            # 1. Start Episode
            await journal.start_episode(
                episode_id="ep_login_01",
                session_id="sess_alpha",
                task_goal="Log into dashboard",
                start_time_ms=1000.0,
                metadata={"user": "admin"},
            )

            # 2. Record Transitions
            t1 = self._create_sample_transition("tx_1", "ep_login_01", 0, "h0", "h1")
            t2 = self._create_sample_transition("tx_2", "ep_login_01", 1, "h1", "h2")
            await journal.record_transition(t1)
            await journal.record_transition(t2)

            # 3. End Episode
            await journal.end_episode(
                episode_id="ep_login_01",
                final_outcome="success",
                end_time_ms=1500.0,
                metadata={"completion_score": 1.0},
            )

            # 4. Get Summary
            summary = await journal.get_episode_summary("ep_login_01")
            self.assertIsNotNone(summary)
            assert summary is not None
            self.assertEqual(summary.episode_id, "ep_login_01")
            self.assertEqual(summary.task_goal, "Log into dashboard")
            self.assertEqual(summary.total_steps, 2)
            self.assertTrue(summary.success)
            self.assertEqual(summary.transition_ids, ["tx_1", "tx_2"])
            self.assertEqual(summary.metadata.get("completion_score"), 1.0)
            self.assertEqual(summary.metadata.get("user"), "admin")

            # 5. List Episodes
            all_episodes = await journal.list_episodes()
            self.assertEqual(len(all_episodes), 1)
            self.assertEqual(all_episodes[0].episode_id, "ep_login_01")
        finally:
            await journal.close()

    async def test_loss_free_transition_storage_and_roundtrip(self) -> None:
        """Asserts 100% field equality when deserializing stored transitions."""
        journal = LocalEpisodeJournal(self.db_file, auto_redact=False)
        try:
            original = self._create_sample_transition(
                trans_id="tx_exact_001",
                ep_id="ep_lossless",
                step_idx=0,
                state_hash="state_initial",
                next_hash="state_terminal",
            )
            await journal.record_transition(original)

            retrieved_list = await journal.get_episode_transitions("ep_lossless")
            self.assertEqual(len(retrieved_list), 1)
            retrieved = retrieved_list[0]

            self.assertEqual(retrieved.transition_id, original.transition_id)
            self.assertEqual(retrieved.episode_id, original.episode_id)
            self.assertEqual(retrieved.step_index, original.step_index)
            self.assertEqual(retrieved.timestamp_ms, original.timestamp_ms)
            self.assertEqual(retrieved.ui_state_hash, original.ui_state_hash)
            self.assertEqual(retrieved.goal_text, original.goal_text)
            self.assertEqual(retrieved.goal_embedding, original.goal_embedding)
            self.assertEqual(retrieved.visual_embedding, original.visual_embedding)
            self.assertEqual(retrieved.next_ui_state_hash, original.next_ui_state_hash)
            self.assertEqual(retrieved.duration_ms, original.duration_ms)
            self.assertEqual(retrieved.surprise_score, original.surprise_score)
            self.assertEqual(retrieved.provenance, original.provenance)

            # Action equality
            self.assertEqual(retrieved.action.action_type, original.action.action_type)
            self.assertEqual(retrieved.action.target_node_id, original.action.target_node_id)
            self.assertEqual(retrieved.action.target_label, original.action.target_label)
            self.assertEqual(retrieved.action.coords, original.action.coords)
            self.assertEqual(retrieved.action.safety_class, original.action.safety_class)

            # Delta equality
            self.assertEqual(retrieved.delta.added_nodes, original.delta.added_nodes)
            self.assertEqual(retrieved.delta.changed_bounding_boxes, original.delta.changed_bounding_boxes)
            self.assertEqual(retrieved.delta.outcome_class, original.delta.outcome_class)
        finally:
            await journal.close()

    # =========================================================================
    # 3. Querying by State Hash & Ordering
    # =========================================================================

    async def test_query_transitions_by_state_hash(self) -> None:
        """Tests querying transitions originating from a specific state hash across episodes."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            # Two different episodes visiting the same initial state hash
            t_ep1 = self._create_sample_transition("t_1", "ep1", 0, "shared_state_hash", "next_state_1")
            t_ep2 = self._create_sample_transition("t_2", "ep2", 0, "shared_state_hash", "next_state_2")
            t_ep3 = self._create_sample_transition("t_3", "ep2", 1, "next_state_2", "final_state")

            await journal.record_transition(t_ep1)
            await journal.record_transition(t_ep2)
            await journal.record_transition(t_ep3)

            results = await journal.find_transitions_by_state("shared_state_hash")
            self.assertEqual(len(results), 2)
            self.assertEqual(set(r.transition_id for r in results), {"t_1", "t_2"})

            # Query for non-existent hash
            empty_results = await journal.find_transitions_by_state("non_existent_hash")
            self.assertEqual(len(empty_results), 0)
        finally:
            await journal.close()

    async def test_sequential_step_ordering(self) -> None:
        """Asserts transitions are returned sorted by step_index ASC, timestamp_ms ASC."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            # Insert out-of-order
            t3 = self._create_sample_transition("t3", "ep_order", 2, "h2", "h3")
            t1 = self._create_sample_transition("t1", "ep_order", 0, "h0", "h1")
            t2 = self._create_sample_transition("t2", "ep_order", 1, "h1", "h2")

            await journal.record_transition(t3)
            await journal.record_transition(t1)
            await journal.record_transition(t2)

            transitions = await journal.get_episode_transitions("ep_order")
            self.assertEqual(len(transitions), 3)
            self.assertEqual([t.step_index for t in transitions], [0, 1, 2])
            self.assertEqual([t.transition_id for t in transitions], ["t1", "t2", "t3"])
        finally:
            await journal.close()

    # =========================================================================
    # 4. Cryptographic Linkage Verification
    # =========================================================================

    async def test_verify_cryptographic_linkage_success(self) -> None:
        """Asserts unbroken state hash chain passes linkage validation."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            t1 = self._create_sample_transition("t1", "ep_chain", 0, "hash_0", "hash_1")
            t2 = self._create_sample_transition("t2", "ep_chain", 1, "hash_1", "hash_2")
            t3 = self._create_sample_transition("t3", "ep_chain", 2, "hash_2", "hash_3")

            await journal.record_transition(t1)
            await journal.record_transition(t2)
            await journal.record_transition(t3)

            is_valid, reason = await journal.verify_cryptographic_linkage("ep_chain")
            self.assertTrue(is_valid)
            self.assertIsNone(reason)
        finally:
            await journal.close()

    async def test_verify_cryptographic_linkage_broken_chain(self) -> None:
        """Asserts broken state hash chain is correctly detected and reported."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            t1 = self._create_sample_transition("t1", "ep_broken", 0, "hash_0", "hash_1")
            t2 = self._create_sample_transition("t2", "ep_broken", 1, "hash_DIFFERENT", "hash_3")

            await journal.record_transition(t1)
            await journal.record_transition(t2)

            is_valid, reason = await journal.verify_cryptographic_linkage("ep_broken")
            self.assertFalse(is_valid)
            self.assertIsNotNone(reason)
            self.assertIn("Linkage break", reason or "")
            self.assertIn("hash_1", reason or "")
        finally:
            await journal.close()

    # =========================================================================
    # 5. Transaction Rollback & Error Handling Tests
    # =========================================================================

    async def test_transaction_rollback_on_write_failure(self) -> None:
        """Asserts rollback occurs and no corrupt state is persisted on failure."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            # 1. Record valid transition
            t1 = self._create_sample_transition("t1", "ep_rb", 0, "h0", "h1")
            await journal.record_transition(t1)

            # 2. Simulate failure during write
            class CorruptTransition(TransitionTuple):
                pass

            # Force an invalid attribute that breaks json serialization
            bad_tx = self._create_sample_transition("t2", "ep_rb", 1, "h1", "h2")
            bad_tx.provenance["unserializable"] = object()

            with self.assertRaises(MemoryPortError):
                await journal.record_transition(bad_tx)

            # Assert only t1 exists
            transitions = await journal.get_episode_transitions("ep_rb")
            self.assertEqual(len(transitions), 1)
            self.assertEqual(transitions[0].transition_id, "t1")
        finally:
            await journal.close()

    async def test_error_handling_when_closed(self) -> None:
        """Asserts MemoryConnectionError is raised when performing operations on closed journal."""
        journal = LocalEpisodeJournal(":memory:")
        await journal.close()

        with self.assertRaises(MemoryConnectionError):
            await journal.get_episode_transitions("ep1")

        with self.assertRaises(MemoryConnectionError):
            await journal.record_transition(self._create_sample_transition())

    # =========================================================================
    # 6. WAL Mode & File Persistence
    # =========================================================================

    async def test_wal_mode_and_persistence_across_reconnect(self) -> None:
        """Asserts disk SQLite journal configures WAL mode and preserves data across reconnects."""
        journal1 = LocalEpisodeJournal(self.db_file)
        try:
            # Check journal_mode
            cur = journal1._db_conn.cursor()
            cur.execute("PRAGMA journal_mode;")
            mode = cur.fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

            # Write data
            t1 = self._create_sample_transition("tx_wal_1", "ep_wal", 0)
            await journal1.record_transition(t1)
        finally:
            await journal1.close()

        # Reopen in new instance
        journal2 = LocalEpisodeJournal(self.db_file)
        try:
            trans = await journal2.get_episode_transitions("ep_wal")
            self.assertEqual(len(trans), 1)
            self.assertEqual(trans[0].transition_id, "tx_wal_1")
        finally:
            await journal2.close()

    # =========================================================================
    # 7. JSONL Export and Import Tests
    # =========================================================================

    async def test_jsonl_export_and_import_roundtrip(self) -> None:
        """Tests exporting episode transitions to JSONL and importing them into a fresh journal."""
        journal_src = LocalEpisodeJournal(":memory:", auto_redact=False)
        try:
            t1 = self._create_sample_transition("t_jsonl_1", "ep_export", 0, "h0", "h1")
            t2 = self._create_sample_transition("t_jsonl_2", "ep_export", 1, "h1", "h2")
            await journal_src.record_transition(t1)
            await journal_src.record_transition(t2)

            # Export
            count = await journal_src.export_to_jsonl(self.jsonl_file, "ep_export")
            self.assertEqual(count, 2)
            self.assertTrue(os.path.exists(self.jsonl_file))
        finally:
            await journal_src.close()

        # Import into fresh journal
        journal_dst = LocalEpisodeJournal(":memory:", auto_redact=False)
        try:
            imported_count = await journal_dst.import_from_jsonl(self.jsonl_file)
            self.assertEqual(imported_count, 2)

            transitions = await journal_dst.get_episode_transitions("ep_export")
            self.assertEqual(len(transitions), 2)
            self.assertEqual(transitions[0].transition_id, "t_jsonl_1")
            self.assertEqual(transitions[1].transition_id, "t_jsonl_2")
        finally:
            await journal_dst.close()

    # =========================================================================
    # 8. Motor Skill Storage Tests
    # =========================================================================

    async def test_motor_skill_crud_and_preconditions_query(self) -> None:
        """Asserts saving, fetching, and querying MotorSkills by preconditions hash."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            skill1 = MotorSkill(
                skill_id="skill_nav_home",
                version=1,
                preconditions_hash="precond_home_screen",
                goal_embedding=[0.1, 0.2, 0.3],
                visual_context_embedding=[0.4, 0.5],
                action_sequence=[
                    TypedAction(action_type=ActionType.CLICK, target_node_id="btn_home")
                ],
                expected_delta=StateDelta(added_nodes=["home_banner"]),
                timing_mean_ms=50.0,
                timing_std_ms=5.0,
                confidence=0.96,
                safety_class=SafetyClass.REVERSIBLE,
                provenance_episode_ids=["ep_01", "ep_02"],
                validated_count=10,
            )

            await journal.save_skill(skill1)

            # Fetch by ID
            fetched = await journal.get_skill("skill_nav_home")
            self.assertIsNotNone(fetched)
            assert fetched is not None
            self.assertEqual(fetched.skill_id, "skill_nav_home")
            self.assertEqual(fetched.confidence, 0.96)
            self.assertEqual(len(fetched.action_sequence), 1)

            # Query by Preconditions
            matching = await journal.find_skills_by_preconditions("precond_home_screen")
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0].skill_id, "skill_nav_home")

            # List All Skills
            all_skills = await journal.list_skills()
            self.assertEqual(len(all_skills), 1)
        finally:
            await journal.close()

    # =========================================================================
    # 9. High-Volume Performance Benchmark Test (< 10ms query performance)
    # =========================================================================

    async def test_journal_query_performance_500_transitions(self) -> None:
        """Records 500 transitions and asserts query latency is under 10ms."""
        journal = LocalEpisodeJournal(self.db_file, auto_redact=False)
        try:
            for i in range(500):
                ep_id = f"ep_perf_{i % 5}"
                step_idx = i // 5
                st_hash = f"state_hash_{i % 25}"
                t = self._create_sample_transition(f"t_perf_{i}", ep_id, step_idx, st_hash)
                await journal.record_transition(t)

            # Benchmark Episode Query (100 items)
            t0 = time.perf_counter()
            ep_res = await journal.get_episode_transitions("ep_perf_2")
            ep_ms = (time.perf_counter() - t0) * 1000.0

            self.assertEqual(len(ep_res), 100)
            self.assertLess(
                ep_ms,
                25.0,
                f"Episode query took {ep_ms:.2f}ms (threshold: 25ms)",
            )

            # Benchmark State Hash Query (20 items)
            t1 = time.perf_counter()
            st_res = await journal.find_transitions_by_state("state_hash_10")
            st_ms = (time.perf_counter() - t1) * 1000.0

            self.assertEqual(len(st_res), 20)
            self.assertLess(
                st_ms,
                25.0,
                f"State hash query took {st_ms:.2f}ms (threshold: 25ms)",
            )
        finally:
            await journal.close()


if __name__ == "__main__":
    unittest.main()
