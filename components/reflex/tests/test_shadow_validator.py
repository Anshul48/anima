"""Test Suite: Shadow Mode Validator and Divergence Measurement (R10 Stage 3)."""

from __future__ import annotations

import unittest

from reflex.cognition.skills.shadow_validator import (
    ShadowRunReport,
    ShadowStepEvaluation,
    ShadowValidator,
)
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestShadowValidator(unittest.TestCase):
    """Tests background shadow evaluation, locator stability, and agreement metrics."""

    def setUp(self) -> None:
        self.validator = ShadowValidator()

    def _create_mock_state(self) -> CanonicalUIGraph:
        nodes = {
            "search_box": UIStateNode(
                node_id="search_box",
                role=NodeRole.INPUT,
                bounds=BoundingBox(100, 100, 400, 140),
                label="Search Products",
                is_editable=True,
            ),
            "search_btn": UIStateNode(
                node_id="search_btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(410, 100, 480, 140),
                label="Search",
                is_clickable=True,
            ),
            "cancel_btn": UIStateNode(
                node_id="cancel_btn",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(500, 100, 560, 140),
                label="Cancel",
                is_clickable=True,
            ),
        }
        return CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes=nodes,
            url="https://shop.example.com",
            viewport_size=(1920, 1080),
        )

    def _create_search_skill(self) -> MotorSkill:
        actions = [
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="search_box",
                target_label="Search Products",
                text_payload="{{query}}",
            ),
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="search_btn",
                target_label="Search",
            ),
        ]
        return MotorSkill(
            skill_id="skill_search_01",
            version=1,
            preconditions_hash="mock_hash_search",
            goal_embedding=[0.1] * 384,
            visual_context_embedding=[0.1] * 384,
            action_sequence=actions,
            expected_delta=StateDelta(added_nodes=["results_list"]),
            timing_mean_ms=150.0,
            timing_std_ms=10.0,
            confidence=0.85,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep_01"],
            validated_count=1,
        )

    # =========================================================================
    # Step-Level Agreement & Divergence Tests
    # =========================================================================

    def test_evaluate_step_exact_agreement(self) -> None:
        """Tests that matching action type, target, and payload produces agreed=True."""
        state = self._create_mock_state()
        skill = self._create_search_skill()

        # System 2 emits identical intent
        sys2_act = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="search_box",
            target_label="Search Products",
            text_payload="laptop stand",
        )

        step_eval = self.validator.evaluate_step(
            skill=skill,
            step_index=0,
            current_state=state,
            system2_action=sys2_act,
            parameter_bindings={"query": "laptop stand"},
        )

        self.assertTrue(step_eval.agreed)
        self.assertTrue(step_eval.action_type_matched)
        self.assertTrue(step_eval.target_matched)
        self.assertTrue(step_eval.payload_matched)
        self.assertTrue(step_eval.locator_resolved)
        self.assertIsNone(step_eval.divergence_reason)
        self.assertEqual(step_eval.resolved_node_id, "search_box")

    def test_evaluate_step_divergence_action_type_mismatch(self) -> None:
        """Tests detecting action type mismatch (e.g. skill clicked, System 2 typed)."""
        state = self._create_mock_state()
        skill = self._create_search_skill()

        sys2_act = TypedAction(
            action_type=ActionType.CLICK,  # Mismatch: step 0 is TYPE
            target_node_id="search_box",
            target_label="Search Products",
        )

        step_eval = self.validator.evaluate_step(
            skill=skill,
            step_index=0,
            current_state=state,
            system2_action=sys2_act,
        )

        self.assertFalse(step_eval.agreed)
        self.assertFalse(step_eval.action_type_matched)
        self.assertIn("Action type mismatch", step_eval.divergence_reason or "")

    def test_evaluate_step_divergence_target_mismatch(self) -> None:
        """Tests detecting target mismatch (e.g. skill clicked Search, System 2 clicked Cancel)."""
        state = self._create_mock_state()
        skill = self._create_search_skill()

        sys2_act = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="cancel_btn",
            target_label="Cancel",
        )

        step_eval = self.validator.evaluate_step(
            skill=skill,
            step_index=1,
            current_state=state,
            system2_action=sys2_act,
        )

        self.assertFalse(step_eval.agreed)
        self.assertFalse(step_eval.target_matched)
        self.assertIn("Target mismatch", step_eval.divergence_reason or "")

    def test_evaluate_step_locator_resolution_failure(self) -> None:
        """Tests that a target missing from live CanonicalUIGraph fails locator stability."""
        # Empty graph without search elements
        empty_state = CanonicalUIGraph(timestamp_ms=1000.0, nodes={})
        skill = self._create_search_skill()

        sys2_act = TypedAction(
            action_type=ActionType.CLICK,
            target_label="Search",
        )

        step_eval = self.validator.evaluate_step(
            skill=skill,
            step_index=1,
            current_state=empty_state,
            system2_action=sys2_act,
        )

        self.assertFalse(step_eval.agreed)
        self.assertFalse(step_eval.locator_resolved)
        self.assertIn("Locator resolution failed", step_eval.divergence_reason or "")

    # =========================================================================
    # Run-Level Trajectory Evaluation Tests
    # =========================================================================

    def test_evaluate_run_100_percent_agreement(self) -> None:
        """Tests a 2-step shadow run with 100% agreement and locator stability."""
        state = self._create_mock_state()
        skill = self._create_search_skill()

        sys2_actions = [
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="search_box",
                target_label="Search Products",
                text_payload="wireless mouse",
            ),
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="search_btn",
                target_label="Search",
            ),
        ]

        report = self.validator.evaluate_run(
            skill=skill,
            states=[state, state],
            system2_actions=sys2_actions,
            parameter_bindings={"query": "wireless mouse"},
        )

        self.assertTrue(report.passed)
        self.assertEqual(report.total_steps, 2)
        self.assertEqual(report.agreed_steps, 2)
        self.assertEqual(report.agreement_ratio, 1.0)
        self.assertEqual(report.locator_stability_ratio, 1.0)
        self.assertEqual(len(report.divergences), 0)

    def test_evaluate_run_detects_divergence_in_trajectory(self) -> None:
        """Tests a shadow run with partial agreement."""
        state = self._create_mock_state()
        skill = self._create_search_skill()

        sys2_actions = [
            TypedAction(
                action_type=ActionType.TYPE,
                target_node_id="search_box",
                target_label="Search Products",
                text_payload="wireless mouse",
            ),
            TypedAction(
                action_type=ActionType.CLICK,
                target_node_id="cancel_btn",  # Divergent step 1
                target_label="Cancel",
            ),
        ]

        report = self.validator.evaluate_run(
            skill=skill,
            states=[state, state],
            system2_actions=sys2_actions,
            parameter_bindings={"query": "wireless mouse"},
        )

        self.assertFalse(report.passed)
        self.assertEqual(report.agreed_steps, 1)
        self.assertEqual(report.agreement_ratio, 0.5)
        self.assertGreater(len(report.divergences), 0)

    # =========================================================================
    # Multi-Run Promotion Eligibility Tests (N >= 5 Runs)
    # =========================================================================

    def test_check_promotion_eligibility_passes_after_5_successful_runs(self) -> None:
        """Tests that candidate skill qualifies for promotion after 5 shadow passes with >=95% agreement."""
        skill_id = "skill_search_01"
        reports = [
            ShadowRunReport(
                skill_id=skill_id,
                run_id=f"run_{i}",
                total_steps=2,
                agreed_steps=2,
                agreement_ratio=1.0,
                locator_stability_ratio=1.0,
                step_evaluations=[],
                divergences=[],
                passed=True,
            )
            for i in range(5)
        ]

        is_eligible, stats = self.validator.check_promotion_eligibility(skill_id, reports, min_runs=5)
        self.assertTrue(is_eligible)
        self.assertEqual(stats["total_runs"], 5)
        self.assertEqual(stats["mean_agreement_ratio"], 1.0)
        self.assertEqual(stats["mean_locator_stability"], 1.0)

    def test_check_promotion_eligibility_fails_on_insufficient_runs_or_divergence(self) -> None:
        """Tests that skill fails promotion check if runs < 5 or agreement < 95%."""
        skill_id = "skill_search_01"

        # Case 1: Insufficient runs (3/5)
        short_reports = [
            ShadowRunReport(
                skill_id=skill_id,
                run_id=f"run_{i}",
                total_steps=2,
                agreed_steps=2,
                agreement_ratio=1.0,
                locator_stability_ratio=1.0,
                step_evaluations=[],
                divergences=[],
                passed=True,
            )
            for i in range(3)
        ]
        is_eligible, stats = self.validator.check_promotion_eligibility(skill_id, short_reports, min_runs=5)
        self.assertFalse(is_eligible)
        self.assertIn("Insufficient shadow runs", stats["reason"])

        # Case 2: 5 runs but low agreement (mean agreement 0.70 < 0.95)
        flaky_reports = [
            ShadowRunReport(
                skill_id=skill_id,
                run_id=f"run_{i}",
                total_steps=2,
                agreed_steps=1 if i % 2 == 0 else 2,
                agreement_ratio=0.50 if i % 2 == 0 else 1.0,
                locator_stability_ratio=1.0,
                step_evaluations=[],
                divergences=["Divergence"],
                passed=(i % 2 != 0),
            )
            for i in range(5)
        ]
        is_eligible_flaky, stats_flaky = self.validator.check_promotion_eligibility(skill_id, flaky_reports, min_runs=5)
        self.assertFalse(is_eligible_flaky)


if __name__ == "__main__":
    unittest.main()
