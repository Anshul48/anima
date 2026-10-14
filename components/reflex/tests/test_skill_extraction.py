"""Test Suite: Skill Extraction and Precondition Hashing (R10 Stage 1)."""

from __future__ import annotations

import asyncio
import unittest

from reflex.cognition.skills.extractor import SkillExtractor
from reflex.episodes.journal import LocalEpisodeJournal
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill, TransitionTuple
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, ModalitySource, NodeRole, UIStateNode


class TestSkillExtraction(unittest.IsolatedAsyncioTestCase):
    """Tests procedural skill extraction, template parameterization, and precondition hashing."""

    def setUp(self) -> None:
        self.extractor = SkillExtractor()

    def _create_mock_graph(
        self,
        url: str = "https://example.com/login",
        window: str = "Example Portal",
        username_label: str = "Username",
        password_label: str = "Password",
        button_label: str = "Sign In",
    ) -> CanonicalUIGraph:
        nodes = {
            "node_user": UIStateNode(
                node_id="node_user",
                role=NodeRole.INPUT,
                bounds=BoundingBox(100, 100, 300, 140),
                label=username_label,
                is_editable=True,
            ),
            "node_pass": UIStateNode(
                node_id="node_pass",
                role=NodeRole.INPUT,
                bounds=BoundingBox(100, 160, 300, 200),
                label=password_label,
                is_editable=True,
            ),
            "node_btn": UIStateNode(
                node_id="node_btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(100, 220, 200, 260),
                label=button_label,
                is_clickable=True,
            ),
            "node_static": UIStateNode(
                node_id="node_static",
                role=NodeRole.TEXT,
                bounds=BoundingBox(50, 50, 400, 80),
                label="Welcome to Example Portal",
                is_clickable=False,
                is_editable=False,
            ),
        }
        return CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes=nodes,
            url=url,
            active_window_title=window,
        )

    def _create_login_trace(
        self,
        episode_id: str,
        user_text: str,
        pass_text: str,
        duration_per_step: float = 120.0,
    ) -> list[TransitionTuple]:
        graph = self._create_mock_graph()
        h0 = graph.compute_state_hash()
        h1 = "hash_step_1"
        h2 = "hash_step_2"
        h3 = "hash_step_3"

        tx0 = TransitionTuple(
            transition_id=f"tx_{episode_id}_0",
            episode_id=episode_id,
            step_index=0,
            timestamp_ms=1000.0,
            ui_state_hash=h0,
            goal_text="Log into portal",
            goal_embedding=[0.1] * 384,
            visual_embedding=[0.2] * 384,
            action=TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="node_user",
                target_label="Username",
                coords=NormalizedCoords(0.15, 0.12),
                text_payload=user_text,
                safety_class=SafetyClass.REVERSIBLE,
            ),
            next_ui_state_hash=h1,
            delta=StateDelta(modified_nodes=["node_user"]),
            duration_ms=duration_per_step,
            surprise_score=0.01,
        )

        tx1 = TransitionTuple(
            transition_id=f"tx_{episode_id}_1",
            episode_id=episode_id,
            step_index=1,
            timestamp_ms=1120.0,
            ui_state_hash=h1,
            goal_text="Log into portal",
            goal_embedding=[0.1] * 384,
            visual_embedding=[0.2] * 384,
            action=TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="node_pass",
                target_label="Password",
                coords=NormalizedCoords(0.15, 0.18),
                text_payload=pass_text,
                safety_class=SafetyClass.REVERSIBLE,
            ),
            next_ui_state_hash=h2,
            delta=StateDelta(modified_nodes=["node_pass"]),
            duration_ms=duration_per_step + 10.0,
            surprise_score=0.01,
        )

        tx2 = TransitionTuple(
            transition_id=f"tx_{episode_id}_2",
            episode_id=episode_id,
            step_index=2,
            timestamp_ms=1250.0,
            ui_state_hash=h2,
            goal_text="Log into portal",
            goal_embedding=[0.1] * 384,
            visual_embedding=[0.2] * 384,
            action=TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="node_btn",
                target_label="Sign In",
                coords=NormalizedCoords(0.15, 0.24),
                safety_class=SafetyClass.REVERSIBLE,
            ),
            next_ui_state_hash=h3,
            delta=StateDelta(
                added_nodes=["dashboard_header"],
                removed_nodes=["node_btn"],
                outcome_class=OutcomeClass.SUCCESS,
            ),
            duration_ms=duration_per_step + 30.0,
            surprise_score=0.02,
        )

        return [tx0, tx1, tx2]

    # =========================================================================
    # Parameterization Tests
    # =========================================================================

    def test_parameterize_action_infers_semantic_slots(self) -> None:
        """Tests inferring slot names based on target labels and regex formats."""
        # 1. Username
        act_user = TypedAction(
            action_type=ActionType.TYPE,
            target_label="Username",
            text_payload="alice_admin",
            coords=NormalizedCoords(0.1, 0.2),
        )
        p_act_user, slots_user = self.extractor.parameterize_action(act_user)
        self.assertEqual(p_act_user.text_payload, "{{username}}")
        self.assertIsNone(p_act_user.coords)  # coordinates stripped!
        self.assertEqual(slots_user, {"username": "alice_admin"})

        # 2. Email payload regex
        act_email = TypedAction(
            action_type=ActionType.TYPE,
            target_label="User Identifier",
            text_payload="john.doe@testcompany.org",
        )
        p_act_email, slots_email = self.extractor.parameterize_action(act_email)
        self.assertEqual(p_act_email.text_payload, "{{user_email}}")
        self.assertEqual(slots_email, {"user_email": "john.doe@testcompany.org"})

        # 3. Search query
        act_search = TypedAction(
            action_type=ActionType.TYPE,
            target_label="Search Query",
            text_payload="mechanical keyboard",
        )
        p_act_search, slots_search = self.extractor.parameterize_action(act_search)
        self.assertEqual(p_act_search.text_payload, "{{query}}")
        self.assertEqual(slots_search, {"query": "mechanical keyboard"})

    def test_parameterize_action_sequence_custom_mappings(self) -> None:
        """Tests explicit slot name mappings for multi-step routines."""
        actions = [
            TypedAction(action_type=ActionType.TYPE, target_label="Field A", text_payload="Value 1"),
            TypedAction(action_type=ActionType.TYPE, target_label="Field B", text_payload="Value 2"),
            TypedAction(action_type=ActionType.CLICK, target_label="Submit"),
        ]
        mappings = {"step_0": "custom_param_a", "step_1": "custom_param_b"}
        param_actions, slots = self.extractor.parameterize_action_sequence(actions, slot_mappings=mappings)

        self.assertEqual(len(param_actions), 3)
        self.assertEqual(param_actions[0].text_payload, "{{custom_param_a}}")
        self.assertEqual(param_actions[1].text_payload, "{{custom_param_b}}")
        self.assertIsNone(param_actions[2].text_payload)
        self.assertEqual(slots["custom_param_a"], "Value 1")
        self.assertEqual(slots["custom_param_b"], "Value 2")

    # =========================================================================
    # Preconditions Hashing Tests
    # =========================================================================

    def test_compute_preconditions_hash_deterministic(self) -> None:
        """Tests that identical UI state graphs yield identical precondition hashes."""
        graph1 = self._create_mock_graph()
        graph2 = self._create_mock_graph()

        h1 = self.extractor.compute_preconditions_hash(graph1)
        h2 = self.extractor.compute_preconditions_hash(graph2)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)  # SHA-256 hex string

    def test_compute_preconditions_hash_structural_sensitivity(self) -> None:
        """Tests that structural changes to interactable elements alter the hash."""
        graph1 = self._create_mock_graph(button_label="Sign In")
        graph2 = self._create_mock_graph(button_label="Create Account")

        h1 = self.extractor.compute_preconditions_hash(graph1)
        h2 = self.extractor.compute_preconditions_hash(graph2)
        self.assertNotEqual(h1, h2)

    def test_compute_preconditions_hash_subgraph_filter(self) -> None:
        """Tests hashing a targeted DOM subgraph using relevant_node_ids."""
        graph = self._create_mock_graph()
        h_sub = self.extractor.compute_preconditions_hash(graph, relevant_node_ids=["node_user", "node_btn"])
        h_all = self.extractor.compute_preconditions_hash(graph)
        self.assertNotEqual(h_sub, h_all)

    # =========================================================================
    # Multi-Episode Trajectory Mining Tests
    # =========================================================================

    def test_extract_from_episodes_mines_recurring_login_routine(self) -> None:
        """Tests extracting 3-step login routine across 3 golden episodes with varying credentials."""
        trace1 = self._create_login_trace("ep_1", "alice@example.com", "SecretPass1!")
        trace2 = self._create_login_trace("ep_2", "bob@example.com", "SecretPass2@")
        trace3 = self._create_login_trace("ep_3", "charlie@example.com", "SecretPass3#")

        skills = self.extractor.extract_from_episodes([trace1, trace2, trace3], min_occurrences=3)
        self.assertEqual(len(skills), 1)

        skill = skills[0]
        self.assertEqual(skill.version, 1)
        self.assertEqual(len(skill.action_sequence), 3)
        self.assertEqual(skill.validated_count, 3)
        self.assertEqual(len(skill.provenance_episode_ids), 3)

        # Check parameterization
        self.assertEqual(skill.action_sequence[0].action_type, ActionType.TYPE)
        self.assertEqual(skill.action_sequence[0].text_payload, "{{username}}")
        self.assertIsNone(skill.action_sequence[0].coords)

        self.assertEqual(skill.action_sequence[1].action_type, ActionType.TYPE)
        self.assertEqual(skill.action_sequence[1].text_payload, "{{password}}")

        self.assertEqual(skill.action_sequence[2].action_type, ActionType.CLICK)
        self.assertEqual(skill.action_sequence[2].target_label, "Sign In")

        # Check timing stats and deltas
        self.assertGreater(skill.timing_mean_ms, 0.0)
        self.assertIn("dashboard_header", skill.expected_delta.added_nodes)
        self.assertEqual(skill.expected_delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertEqual(skill.safety_class, SafetyClass.REVERSIBLE)

    async def test_extract_from_journal_integration(self) -> None:
        """Tests extracting skills directly from LocalEpisodeJournal."""
        journal = LocalEpisodeJournal(db_path=":memory:")

        # Record 2 episodes
        for ep_num, user in enumerate(["user1@test.com", "user2@test.com"], start=1):
            ep_id = f"ep_{ep_num}"
            await journal.start_episode(episode_id=ep_id, session_id="sess", task_goal="Login")
            traces = self._create_login_trace(ep_id, user, "pwd123")
            for tx in traces:
                await journal.record_transition(tx, scrub=False)
            await journal.end_episode(episode_id=ep_id, final_outcome="success")

        skills = await self.extractor.extract_from_journal(journal, min_occurrences=2)
        self.assertEqual(len(skills), 1)
        self.assertEqual(len(skills[0].action_sequence), 3)

        await journal.close()


if __name__ == "__main__":
    unittest.main()
