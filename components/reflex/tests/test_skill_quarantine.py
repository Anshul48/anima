"""Test Suite: Skill Quarantine, Demotion, and Retirement (R10 Stage 6)."""

from __future__ import annotations

import unittest

from reflex.cognition.skills.extractor import SkillExtractor
from reflex.cognition.skills.registry import (
    SkillMetadata,
    SkillRegistry,
    SkillStatus,
)
from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.delta import StateDelta
from reflex.schemas.memory import MotorSkill
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestSkillQuarantine(unittest.TestCase):
    """Tests automated quarantine upon verification failure, demotion, and retirement."""

    def setUp(self) -> None:
        self.extractor = SkillExtractor()
        self.registry = SkillRegistry(db_path=":memory:", extractor=self.extractor)

    def tearDown(self) -> None:
        self.registry.close()

    def _create_mock_state(self) -> CanonicalUIGraph:
        nodes = {
            "btn_submit": UIStateNode(
                node_id="btn_submit",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(100, 100, 200, 140),
                label="Submit",
                is_clickable=True,
            )
        }
        return CanonicalUIGraph(timestamp_ms=1000.0, nodes=nodes, url="https://example.com")

    def _create_mock_skill(self, skill_id: str = "skill_test_q") -> MotorSkill:
        graph = self._create_mock_state()
        return MotorSkill(
            skill_id=skill_id,
            version=1,
            preconditions_hash=self.extractor.compute_preconditions_hash(graph),
            goal_embedding=[0.1] * 384,
            visual_context_embedding=[0.1] * 384,
            action_sequence=[
                TypedAction(
                    action_type=ActionType.CLICK,
                    target_node_id="btn_submit",
                    target_label="Submit",
                )
            ],
            expected_delta=StateDelta(added_nodes=["success_msg"]),
            timing_mean_ms=100.0,
            timing_std_ms=5.0,
            confidence=0.90,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep_01"],
            validated_count=5,
        )

    def test_single_verification_failure_quarantines_promoted_skill(self) -> None:
        """Promote a mock skill; inject a deliberate verification failure; assert status immediately transitions to QUARANTINED."""
        graph = self._create_mock_state()
        skill = self._create_mock_skill("skill_quarantine_live")

        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)

        # 1. Verified live match returns skill
        res_live = self.registry.find_matching_skill(graph, "Submit form")
        self.assertIsNotNone(res_live)
        self.assertEqual(res_live.skill.skill_id, "skill_quarantine_live")

        # 2. Inject deliberate verification failure
        self.registry.record_execution_outcome(skill.skill_id, success=False, surprise_score=0.95)

        # 3. Status immediately transitions to QUARANTINED
        meta = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta.status, SkillStatus.QUARANTINED)
        self.assertTrue(meta.is_quarantined)
        self.assertIn("Verification failure", meta.quarantine_reason or "")
        self.assertLess(meta.confidence, 0.40)

        # 4. Subsequent queries return None
        res_after = self.registry.find_matching_skill(graph, "Submit form")
        self.assertIsNone(res_after)

    def test_manual_quarantine_and_reactivation(self) -> None:
        """Tests explicit manual quarantine and reactivating back to shadow evaluation."""
        graph = self._create_mock_state()
        skill = self._create_mock_skill("skill_manual_q")
        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)

        # Manual quarantine
        self.registry.quarantine_skill(skill.skill_id, reason="Flagged by policy audit")
        meta = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta.status, SkillStatus.QUARANTINED)
        self.assertEqual(meta.quarantine_reason, "Flagged by policy audit")

        # Live lookup returns None
        self.assertIsNone(self.registry.find_matching_skill(graph, "Submit form"))

        # Reactivate to shadow mode
        self.registry.reactivate_quarantined_skill(skill.skill_id)
        meta_reactivated = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta_reactivated.status, SkillStatus.SHADOW_EVALUATION)
        self.assertEqual(meta_reactivated.confidence, 0.50)

    def test_permanent_retirement_lifecycle(self) -> None:
        """Tests retiring a skill permanently and preventing reactivation."""
        skill = self._create_mock_skill("skill_retire_perm")
        self.registry.register_candidate(skill)

        self.registry.retire_skill(skill.skill_id, reason="Deprecated workflow")
        meta = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta.status, SkillStatus.RETIRED)
        self.assertTrue(meta.is_retired)
        self.assertEqual(meta.confidence, 0.0)

        # Reactivation must fail
        with self.assertRaises(ValueError):
            self.registry.reactivate_quarantined_skill(skill.skill_id)


if __name__ == "__main__":
    unittest.main()
