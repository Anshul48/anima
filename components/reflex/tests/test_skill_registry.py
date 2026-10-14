"""Test Suite: Skill Registry, Promotion Lifecycle & Fast-Path Retrieval (R10 Stages 4, 5, 6)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest

from reflex.cognition.skills.executor import SkillGroundingError, SkillReplayExecutor
from reflex.cognition.skills.extractor import SkillExtractor
from reflex.cognition.skills.registry import (
    SkillMatchResult,
    SkillMetadata,
    SkillRegistry,
    SkillStatus,
)
from reflex.cognition.skills.shadow_validator import ShadowRunReport
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestSkillRegistry(unittest.TestCase):
    """Tests SkillRegistry lifecycle, sub-5ms lookup, automated quarantine, and dynamic re-grounding."""

    def setUp(self) -> None:
        self.extractor = SkillExtractor()
        self.registry = SkillRegistry(
            db_path=":memory:",
            extractor=self.extractor,
            min_promotion_shadow_runs=5,
            min_promotion_agreement=0.95,
        )
        self.executor = SkillReplayExecutor()

    def tearDown(self) -> None:
        self.registry.close()

    def _create_mock_state(
        self,
        url: str = "https://example.com/checkout",
        window: str = "Checkout Page",
    ) -> CanonicalUIGraph:
        nodes = {
            "btn_checkout": UIStateNode(
                node_id="btn_checkout",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(100, 100, 250, 140),
                label="Complete Order",
                is_clickable=True,
            ),
            "input_coupon": UIStateNode(
                node_id="input_coupon",
                role=NodeRole.INPUT,
                bounds=BoundingBox(100, 160, 300, 200),
                label="Promo Code",
                is_editable=True,
            ),
            "btn_apply": UIStateNode(
                node_id="btn_apply",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(310, 160, 380, 200),
                label="Apply",
                is_clickable=True,
            ),
        }
        return CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes=nodes,
            url=url,
            active_window_title=window,
            viewport_size=(1920, 1080),
        )

    def _create_mock_skill(self, graph: CanonicalUIGraph, skill_id: str = "skill_order_01") -> MotorSkill:
        preconditions_hash = self.extractor.compute_preconditions_hash(graph)
        actions = [
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="input_coupon",
                target_label="Promo Code",
                text_payload="{{promo_code}}",
            ),
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_apply",
                target_label="Apply",
            ),
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="btn_checkout",
                target_label="Complete Order",
            ),
        ]
        return MotorSkill(
            skill_id=skill_id,
            version=1,
            preconditions_hash=preconditions_hash,
            goal_embedding=[0.1] * 384,
            visual_context_embedding=[0.1] * 384,
            action_sequence=actions,
            expected_delta=StateDelta(added_nodes=["order_confirmation"]),
            timing_mean_ms=250.0,
            timing_std_ms=15.0,
            confidence=0.80,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep_01"],
            validated_count=1,
        )

    # =========================================================================
    # Lifecycle Progression Tests
    # =========================================================================

    def test_full_lifecycle_progression(self) -> None:
        """Tests complete 6-stage lifecycle: EXTRACTED -> SHADOW -> CANDIDATE -> PROMOTED."""
        graph = self._create_mock_state()
        skill = self._create_mock_skill(graph, "skill_lifecycle_01")

        # 1. Register extracted
        sk_id = self.registry.register_extracted(skill)
        meta = self.registry.get_metadata(sk_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.status, SkillStatus.EXTRACTED)

        # 2. Record shadow runs -> advances to SHADOW_EVALUATION then CANDIDATE
        for i in range(5):
            report = ShadowRunReport(
                skill_id=sk_id,
                run_id=f"run_{i}",
                total_steps=3,
                agreed_steps=3,
                agreement_ratio=1.0,
                locator_stability_ratio=1.0,
                step_evaluations=[],
                divergences=[],
                passed=True,
            )
            self.registry.record_shadow_evaluation(sk_id, report)

        meta = self.registry.get_metadata(sk_id)
        self.assertEqual(meta.status, SkillStatus.CANDIDATE)
        self.assertEqual(meta.shadow_runs_count, 5)
        self.assertEqual(meta.shadow_agreement_ratio, 1.0)

        # 3. Promote to TRUSTED / PROMOTED
        self.registry.promote_skill(sk_id)
        meta = self.registry.get_metadata(sk_id)
        self.assertEqual(meta.status, SkillStatus.PROMOTED)
        self.assertTrue(meta.is_trusted)
        self.assertGreaterEqual(meta.confidence, 0.85)

    def test_promotion_fails_if_shadow_criteria_not_met(self) -> None:
        """Tests that promotion is blocked if shadow passes < 5 or agreement < 95%."""
        graph = self._create_mock_state()
        skill = self._create_mock_skill(graph, "skill_unpromoted_01")
        sk_id = self.registry.register_extracted(skill)

        # Only 2 shadow passes
        for i in range(2):
            self.registry.record_shadow_evaluation(
                sk_id,
                ShadowRunReport(
                    skill_id=sk_id,
                    run_id=f"run_{i}",
                    total_steps=3,
                    agreed_steps=3,
                    agreement_ratio=1.0,
                    locator_stability_ratio=1.0,
                    step_evaluations=[],
                    divergences=[],
                    passed=True,
                ),
            )

        with self.assertRaises(ValueError) as ctx:
            self.registry.promote_skill(sk_id)
        self.assertIn("shadow runs 2 < required 5", str(ctx.exception))

    # =========================================================================
    # Fast-Path Retrieval (< 5ms) & Dynamic Parameter Extraction
    # =========================================================================

    def test_fast_path_retrieval_under_5ms(self) -> None:
        """Tests that matching a promoted skill takes well under 5ms in memory."""
        graph = self._create_mock_state()
        skill = self._create_mock_skill(graph, "skill_fast_01")

        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)

        # Warmup and timed lookup
        t0 = time.perf_counter()
        match_result = self.registry.find_matching_skill(graph, goal_text="Apply 'SUMMER20' and complete order")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertIsNotNone(match_result)
        self.assertLess(elapsed_ms, 5.0)  # Sub-5ms requirement!
        self.assertEqual(match_result.skill.skill_id, "skill_fast_01")
        self.assertEqual(match_result.parameter_bindings.get("promo_code"), "SUMMER20")

    def test_unpromoted_candidate_skill_not_returned_in_live_lookup(self) -> None:
        """Tests that candidate/extracted/shadow skills are not returned for live execution."""
        graph = self._create_mock_state()
        skill = self._create_mock_skill(graph, "skill_unpromoted_lookup")

        self.registry.register_candidate(skill)  # status: CANDIDATE (not PROMOTED)

        match_result = self.registry.find_matching_skill(graph, goal_text="Complete order")
        self.assertIsNone(match_result)

    # =========================================================================
    # Automated Quarantine on Live Verification Failure
    # =========================================================================

    def test_automated_quarantine_on_verification_failure(self) -> None:
        """Tests that a single verification failure on a live promoted skill immediately drops confidence and quarantines."""
        graph = self._create_mock_state()
        skill = self._create_mock_skill(graph, "skill_quarantine_01")

        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)

        # Before failure: live lookup succeeds
        res_before = self.registry.find_matching_skill(graph, goal_text="Complete order")
        self.assertIsNotNone(res_before)

        # Trigger live verification failure
        self.registry.record_execution_outcome(skill.skill_id, success=False, surprise_score=0.85)

        meta = self.registry.get_metadata(skill.skill_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.status, SkillStatus.QUARANTINED)
        self.assertTrue(meta.is_quarantined)
        self.assertLess(meta.confidence, 0.40)  # Confidence dropped
        self.assertIn("Verification failure", meta.quarantine_reason or "")

        # After quarantine: live lookup immediately returns None
        res_after = self.registry.find_matching_skill(graph, goal_text="Complete order")
        self.assertIsNone(res_after)

    def test_automatic_retirement_after_3_failures(self) -> None:
        """Tests that reaching 3 failures automatically transitions skill to RETIRED."""
        graph = self._create_mock_state()
        skill = self._create_mock_skill(graph, "skill_retire_01")
        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)

        # Failure 1 -> QUARANTINED
        self.registry.record_execution_outcome(skill.skill_id, success=False)
        self.assertEqual(self.registry.get_metadata(skill.skill_id).status, SkillStatus.QUARANTINED)

        # Reactivate and fail 2
        self.registry.reactivate_quarantined_skill(skill.skill_id)
        self.registry.promote_skill(skill.skill_id, force=True)
        self.registry.record_execution_outcome(skill.skill_id, success=False)
        self.assertEqual(self.registry.get_metadata(skill.skill_id).status, SkillStatus.QUARANTINED)

        # Reactivate and fail 3 -> RETIRED
        self.registry.reactivate_quarantined_skill(skill.skill_id)
        self.registry.promote_skill(skill.skill_id, force=True)
        self.registry.record_execution_outcome(skill.skill_id, success=False)

        meta = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta.status, SkillStatus.RETIRED)
        self.assertTrue(meta.is_retired)
        self.assertEqual(meta.confidence, 0.0)

    # =========================================================================
    # Dynamic Re-Grounding (No Fixed Pixel Coordinates)
    # =========================================================================

    def test_dynamic_regrounding_resolves_shifted_live_targets(self) -> None:
        """Tests that SkillReplayExecutor dynamically resolves shifted element bounds."""
        # Original state at extraction
        original_graph = self._create_mock_state()
        skill = self._create_mock_skill(original_graph, "skill_reground_01")

        # Live state during replay has elements shifted by 50px
        shifted_nodes = {
            "btn_checkout": UIStateNode(
                node_id="btn_checkout",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(150, 150, 300, 190),  # Shifted bounds
                label="Complete Order",
                is_clickable=True,
            ),
            "input_coupon": UIStateNode(
                node_id="input_coupon",
                role=NodeRole.INPUT,
                bounds=BoundingBox(150, 210, 350, 250),  # Shifted bounds
                label="Promo Code",
                is_editable=True,
            ),
            "btn_apply": UIStateNode(
                node_id="btn_apply",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(360, 210, 430, 250),  # Shifted bounds
                label="Apply",
                is_clickable=True,
            ),
        }
        live_graph = CanonicalUIGraph(
            timestamp_ms=2000.0,
            nodes=shifted_nodes,
            url="https://example.com/checkout",
            viewport_size=(1920, 1080),
        )

        # Step 0: Input promo code
        prop0 = self.executor.instantiate_step(
            skill=skill,
            step_index=0,
            current_state=live_graph,
            parameter_bindings={"promo_code": "SAVE10"},
        )
        self.assertEqual(prop0.action.action_type, ActionType.TYPE)
        self.assertEqual(prop0.action.text_payload, "SAVE10")
        self.assertEqual(prop0.action.target_node_id, "input_coupon")
        self.assertIsNotNone(prop0.action.coords)
        # Verify coordinates resolved to the shifted center (250/1920, 230/1080)
        self.assertAlmostEqual(prop0.action.coords.x, 250 / 1920, places=2)
        self.assertAlmostEqual(prop0.action.coords.y, 230 / 1080, places=2)

    # =========================================================================
    # SQLite Persistence & Hydration Tests
    # =========================================================================

    def test_sqlite_persistence_across_restarts(self) -> None:
        """Tests that skill registry state persists cleanly across database restarts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "skills_test.sqlite3")

            # 1. Initialize registry, register and promote skill
            reg1 = SkillRegistry(db_path=db_file, extractor=self.extractor)
            graph = self._create_mock_state()
            skill = self._create_mock_skill(graph, "skill_persist_01")
            reg1.register_candidate(skill)
            reg1.promote_skill(skill.skill_id, force=True)
            reg1.close()

            # 2. Open new registry instance on same DB file
            reg2 = SkillRegistry(db_path=db_file, extractor=self.extractor)
            loaded_skill = reg2.get_skill("skill_persist_01")
            loaded_meta = reg2.get_metadata("skill_persist_01")

            self.assertIsNotNone(loaded_skill)
            self.assertIsNotNone(loaded_meta)
            self.assertEqual(loaded_meta.status, SkillStatus.PROMOTED)
            self.assertTrue(loaded_meta.is_trusted)

            # Fast-path query on reloaded instance
            res = reg2.find_matching_skill(graph, goal_text="Complete order")
            self.assertIsNotNone(res)
            self.assertEqual(res.skill.skill_id, "skill_persist_01")
            reg2.close()


if __name__ == "__main__":
    unittest.main()
