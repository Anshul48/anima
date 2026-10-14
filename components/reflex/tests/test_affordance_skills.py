"""Test Suite: Invariant Affordance-Based Skill Extraction, Registry, and Re-grounding."""

from __future__ import annotations

import time
from typing import List, Optional
import unittest

from reflex.cognition.skills.extractor import (
    AffordanceItem,
    AffordancePattern,
    SkillExtractor,
)
from reflex.cognition.skills.registry import SkillRegistry, SkillStatus
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


def _create_test_skill(
    skill_id: str,
    action_sequence: List[TypedAction],
    preconditions_hash: str = "hash_123",
    confidence: float = 0.90,
) -> MotorSkill:
    """Helper to instantiate valid MotorSkill with default required fields."""
    return MotorSkill(
        skill_id=skill_id,
        version=1,
        preconditions_hash=preconditions_hash,
        goal_embedding=[0.0] * 384,
        visual_context_embedding=[0.0] * 384,
        action_sequence=action_sequence,
        expected_delta=StateDelta(outcome_class=OutcomeClass.SUCCESS),
        timing_mean_ms=100.0,
        timing_std_ms=10.0,
        confidence=confidence,
        safety_class=SafetyClass.REVERSIBLE,
        provenance_episode_ids=["ep_test_1"],
        validated_count=1,
    )


class TestAffordanceDataStructures(unittest.TestCase):
    """Tests AffordanceItem and AffordancePattern serialization and properties."""

    def test_affordance_item_roundtrip(self) -> None:
        item = AffordanceItem(role="button", label="Submit", is_clickable=True, is_editable=False)
        d = item.to_dict()
        self.assertEqual(d["role"], "button")
        self.assertEqual(d["label"], "Submit")
        self.assertTrue(d["is_clickable"])
        self.assertFalse(d["is_editable"])

        item2 = AffordanceItem.from_dict(d)
        self.assertEqual(item, item2)

    def test_affordance_pattern_roundtrip(self) -> None:
        items = (
            AffordanceItem(role="input", label="Username", is_editable=True),
            AffordanceItem(role="button", label="Login", is_clickable=True),
        )
        pattern = AffordancePattern(
            app_or_domain="example.com",
            required_affordances=items,
            pattern_signature="affordance:[app:example.com]:[button:login]|[input:username]",
        )
        d = pattern.to_dict()
        pattern2 = AffordancePattern.from_dict(d)
        self.assertEqual(pattern, pattern2)


class TestAffordanceExtractionAndMatching(unittest.TestCase):
    """Tests invariant affordance extraction, matching, and dynamic re-grounding."""

    def setUp(self) -> None:
        self.extractor = SkillExtractor()

    def _create_sample_graph(
        self,
        domain: str = "https://app.example.com/login",
        node_prefix: str = "node_",
        btn_coords: tuple[int, int, int, int] = (100, 200, 200, 240),
    ) -> CanonicalUIGraph:
        nodes = {
            f"{node_prefix}user": UIStateNode(
                node_id=f"{node_prefix}user",
                role=NodeRole.INPUT,
                bounds=BoundingBox(50, 100, 250, 140),
                label="Username",
                is_clickable=True,
                is_editable=True,
            ),
            f"{node_prefix}btn": UIStateNode(
                node_id=f"{node_prefix}btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(*btn_coords),
                label="Submit",
                is_clickable=True,
                is_editable=False,
            ),
            f"{node_prefix}unrelated": UIStateNode(
                node_id=f"{node_prefix}unrelated",
                role=NodeRole.TEXT,
                bounds=BoundingBox(0, 0, 50, 50),
                label="Copyright 2026",
            ),
        }
        return CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=nodes,
            url=domain,
            viewport_size=(1920, 1080),
        )

    def test_extract_affordance_pattern_from_actions(self) -> None:
        graph = self._create_sample_graph()
        actions = [
            TypedAction(action_type=ActionType.TYPE, target_label="Username", text_payload="alice"),
            TypedAction(action_type=ActionType.CLICK, target_label="Submit"),
        ]

        pattern = self.extractor.extract_affordance_pattern(graph, actions)
        self.assertEqual(pattern.app_or_domain, "app.example.com")
        self.assertEqual(len(pattern.required_affordances), 2)
        sig = pattern.pattern_signature
        self.assertIn("app.example.com", sig)
        self.assertIn("submit", sig)
        self.assertIn("username", sig)

    def test_extract_affordance_pattern_from_skill(self) -> None:
        actions = [
            TypedAction(action_type=ActionType.TYPE, target_label="Search Input", text_payload="docs"),
            TypedAction(action_type=ActionType.CLICK, target_label="Go"),
        ]
        skill = _create_test_skill("skill_search", actions)
        pattern = self.extractor.extract_affordance_pattern_from_skill(skill)
        self.assertEqual(pattern.app_or_domain, "*")
        self.assertEqual(len(pattern.required_affordances), 2)
        sig = pattern.pattern_signature
        self.assertIn("search input", sig)
        self.assertIn("go", sig)

    def test_affordance_matching_invariant_to_node_ids_and_shifts(self) -> None:
        """Asserts that state matching succeeds when node IDs change or layout shifts."""
        graph1 = self._create_sample_graph(node_prefix="v1_id_")
        actions = [
            TypedAction(action_type=ActionType.CLICK, target_label="Submit"),
        ]
        pattern = self.extractor.extract_affordance_pattern(graph1, actions)

        # Graph 2 has completely different internal node IDs and shifted coordinates
        graph2 = self._create_sample_graph(
            node_prefix="dynamic_v2_generated_999_",
            btn_coords=(300, 400, 420, 450),
        )

        # Exact hashes will completely mismatch
        self.assertNotEqual(graph1.compute_state_hash(), graph2.compute_state_hash())

        # Invariant affordance matching MUST succeed
        matches = self.extractor.matches_affordance_pattern(pattern, graph2)
        self.assertTrue(matches)

    def test_affordance_matching_fails_when_required_element_missing(self) -> None:
        """Asserts rejection when required button or input is absent."""
        graph = self._create_sample_graph()
        # Pattern requires 'Logout' which doesn't exist
        req_logout = AffordancePattern(
            app_or_domain="app.example.com",
            required_affordances=(AffordanceItem(role="button", label="Logout", is_clickable=True),),
            pattern_signature="affordance:[app:app.example.com]:[button:logout]",
        )
        self.assertFalse(self.extractor.matches_affordance_pattern(req_logout, graph))

    def test_reground_action_sequence(self) -> None:
        """Asserts actions are dynamically bound to live coordinates and template slots interpolated."""
        graph = self._create_sample_graph(
            node_prefix="live_",
            btn_coords=(200, 300, 400, 350),  # Center: (300, 325) -> Normalized: (300/1920, 325/1080)
        )
        actions = [
            TypedAction(
                action_type=ActionType.TYPE,
                target_label="Username",
                text_payload="{{user_name}}",
            ),
            TypedAction(
                action_type=ActionType.CLICK,
                target_label="Submit",
                coords=None,
            ),
        ]

        bindings = {"user_name": "jarvis_operator"}
        regrounded = self.extractor.reground_action_sequence(actions, graph, bindings)

        self.assertEqual(len(regrounded), 2)
        # Check slot interpolation
        self.assertEqual(regrounded[0].text_payload, "jarvis_operator")
        self.assertEqual(regrounded[0].target_node_id, "live_user")

        # Check coordinate re-grounding
        self.assertIsNotNone(regrounded[1].coords)
        expected_nx = round(300.0 / 1920.0, 4)
        expected_ny = round(325.0 / 1080.0, 4)
        self.assertAlmostEqual(regrounded[1].coords.x, expected_nx, places=3)
        self.assertAlmostEqual(regrounded[1].coords.y, expected_ny, places=3)


class TestAffordanceRegistryIntegration(unittest.TestCase):
    """Tests SkillRegistry fast-path matching with affordance index and fallbacks."""

    def setUp(self) -> None:
        self.extractor = SkillExtractor()
        self.registry = SkillRegistry(db_path=":memory:", extractor=self.extractor)

    def test_registry_finds_skill_with_affordance_fallback_on_hash_drift(self) -> None:
        """Asserts that when DOM hash changes, affordance compatibility still triggers sub-5ms match."""
        # 1. Create original skill
        actions = [
            TypedAction(
                action_type=ActionType.TYPE,
                target_label="Username",
                text_payload="{{user}}",
            ),
            TypedAction(
                action_type=ActionType.CLICK,
                target_label="Submit",
            ),
        ]
        skill = _create_test_skill("skill_login_affordance", actions, preconditions_hash="orig_hash_xyz")

        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)

        # 2. Query with live state that has totally different node IDs and state hash
        live_nodes = {
            "random_uid_888": UIStateNode(
                node_id="random_uid_888",
                role=NodeRole.INPUT,
                bounds=BoundingBox(10, 20, 100, 50),
                label="Username",
                is_editable=True,
            ),
            "random_uid_999": UIStateNode(
                node_id="random_uid_999",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(10, 60, 100, 90),
                label="Submit",
                is_clickable=True,
            ),
        }
        live_state = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=live_nodes,
            url="https://app.example.com",
            viewport_size=(1920, 1080),
        )

        # Ensure exact hash fails
        self.assertNotEqual(skill.preconditions_hash, live_state.compute_state_hash())

        # Match via affordance compatibility
        t0 = time.perf_counter()
        match = self.registry.find_matching_skill(live_state, "type username 'admin' and click submit")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertIsNotNone(match)
        self.assertEqual(match.skill.skill_id, "skill_login_affordance")
        self.assertLess(elapsed_ms, 25.0)  # Sub-25ms in python testing environment

        # Verify dynamic re-grounding inside match
        self.assertEqual(match.skill.action_sequence[0].target_node_id, "random_uid_888")
        self.assertEqual(match.skill.action_sequence[1].target_node_id, "random_uid_999")

    def test_quarantined_skill_is_never_matched(self) -> None:
        """Asserts that quarantined skill is ignored even if affordances match perfectly."""
        skill = _create_test_skill(
            "skill_quarantined_test",
            [TypedAction(action_type=ActionType.CLICK, target_label="ButtonX")],
        )
        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)

        # Record 1 failure to quarantine
        self.registry.record_execution_outcome(skill.skill_id, success=False, surprise_score=0.9)
        meta = self.registry.get_metadata(skill.skill_id)
        self.assertIsNotNone(meta)
        self.assertTrue(meta.is_quarantined)

        # Query state with ButtonX while quarantined
        state = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes={
                "btn": UIStateNode(
                    node_id="btn",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(10, 10, 50, 50),
                    label="ButtonX",
                    is_clickable=True,
                )
            }
        )
        match = self.registry.find_matching_skill(state, "Click ButtonX")
        self.assertIsNone(match)

        # Record 2 more failures to retire (cumulative failures >= 3)
        self.registry.record_execution_outcome(skill.skill_id, success=False, surprise_score=0.9)
        self.registry.record_execution_outcome(skill.skill_id, success=False, surprise_score=0.9)
        meta = self.registry.get_metadata(skill.skill_id)
        self.assertIsNotNone(meta)
        self.assertTrue(meta.is_retired)
        self.assertIsNone(self.registry.find_matching_skill(state, "Click ButtonX"))

    def test_affordance_item_index_populates_and_matches_fast_path(self) -> None:
        """Asserts that skills are indexed by individual affordance keys and retrieved directly from _affordance_index."""
        skill = _create_test_skill(
            "skill_indexed_search",
            [TypedAction(action_type=ActionType.TYPE, target_label="Search Query", text_payload="{{q}}")],
        )
        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)

        # Check that individual affordance keys are in _affordance_index
        self.assertIn("input:search query", self.registry._affordance_index)
        self.assertIn("*:search query", self.registry._affordance_index)
        self.assertIn(skill.skill_id, self.registry._affordance_index["input:search query"])

        # Query state containing the input
        live_state = CanonicalUIGraph(
            timestamp_ms=0,
            nodes={
                "in1": UIStateNode(
                    node_id="in1",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(10, 10, 200, 40),
                    label="Search Query",
                    is_editable=True,
                )
            }
        )
        match = self.registry.find_matching_skill(live_state, "Search Query for 'phones'")
        self.assertIsNotNone(match)
        self.assertEqual(match.skill.skill_id, "skill_indexed_search")

    def test_reground_action_sequence_bidirectional_label_and_click(self) -> None:
        """Asserts fuzzy/bidirectional label matching and click fallback to clickable nodes."""
        act_click = TypedAction(action_type=ActionType.CLICK, target_label="Search Button")
        live_state = CanonicalUIGraph(
            timestamp_ms=0,
            nodes={
                "btn_search": UIStateNode(
                    node_id="btn_search",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(100, 100, 200, 150),
                    label="Search",
                    is_clickable=True,
                )
            },
            viewport_size=(1000, 1000),
        )

        regrounded = self.extractor.reground_action_sequence([act_click], live_state)
        self.assertEqual(len(regrounded), 1)
        self.assertEqual(regrounded[0].target_node_id, "btn_search")
        self.assertIsNotNone(regrounded[0].coords)
        # Center is (150, 125) -> normalized (0.15, 0.125)
        self.assertAlmostEqual(regrounded[0].coords.x, 0.15, places=3)
        self.assertAlmostEqual(regrounded[0].coords.y, 0.125, places=3)


if __name__ == "__main__":
    unittest.main()
