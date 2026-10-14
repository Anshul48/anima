"""Unit and integration tests for Abductive Recovery Engine."""

from __future__ import annotations

import json
import unittest

from reflex.cognition.system2.providers import MockLLMClient
from reflex.cognition.system2.recovery import AbductiveRecoveryEngine, RecoveryPlan
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.reconciliation import ReconciliationReport
from reflex.verification.verifier import VerificationResult


class TestAbductiveRecoveryEngine(unittest.IsolatedAsyncioTestCase):
    """Test suite for failure diagnosis and corrective action generation."""

    def setUp(self) -> None:
        self.engine = AbductiveRecoveryEngine()

    async def test_cookie_banner_occlusion_diagnosis_and_recovery(self) -> None:
        """Tests that a cookie banner modal is detected and a dismiss -> proceed plan is generated."""
        save_button = UIStateNode(
            node_id="save-btn",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(x1=500, y1=800, x2=600, y2=840),
            label="Save Changes",
            is_clickable=True,
        )
        accept_cookie_btn = UIStateNode(
            node_id="accept-cookies-btn",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(x1=400, y1=600, x2=550, y2=640),
            label="Accept All Cookies",
            is_clickable=True,
        )
        cookie_modal = UIStateNode(
            node_id="cookie-dialog",
            role=NodeRole.MODAL,
            bounds=BoundingBox(x1=300, y1=500, x2=700, y2=700),
            label="Cookie Preferences",
        )

        before_state = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={"save-btn": save_button},
            viewport_size=(1000, 1000),
        )
        after_state = CanonicalUIGraph(
            timestamp_ms=1500.0,
            nodes={
                "save-btn": save_button,
                "cookie-dialog": cookie_modal,
                "accept-cookies-btn": accept_cookie_btn,
            },
            viewport_size=(1000, 1000),
        )

        failed_action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="save-btn",
            target_label="Save Changes",
            coords=NormalizedCoords(x=0.55, y=0.82),
            safety_class=SafetyClass.REVERSIBLE,
        )

        verif_result = VerificationResult(
            outcome=OutcomeClass.MODAL_APPEARED,
            delta=StateDelta(
                added_nodes=["cookie-dialog", "accept-cookies-btn"],
                outcome_class=OutcomeClass.MODAL_APPEARED,
            ),
            passed_assertions=[],
            failed_assertions=["expected_page_save"],
            settlement_duration_ms=200.0,
            requires_reconciliation=True,
            after_state=after_state,
        )

        recon_report = ReconciliationReport(
            action_id="act_001",
            inferred_cause="modal_interception: an unexpected modal or dialog blocked interaction",
            current_state_summary="Modals Active: 1",
            is_retry_safe=False,
            recommended_recovery_action="dismiss_modal: interact with or close the dialog before continuing",
            captured_state=after_state,
        )

        plan: RecoveryPlan = await self.engine.diagnose_and_recover(
            task_goal="Save profile settings",
            failed_state=before_state,
            failed_action=failed_action,
            verification_result=verif_result,
            reconciliation_report=recon_report,
        )

        self.assertFalse(plan.should_abort)
        self.assertIn("occluded by cookie banner", plan.diagnosed_cause.lower())
        self.assertEqual(len(plan.corrective_actions), 2)
        # First corrective action: click Accept Cookies
        dismiss_action = plan.corrective_actions[0]
        self.assertEqual(dismiss_action.action_type, ActionType.CLICK)
        self.assertEqual(dismiss_action.target_node_id, "accept-cookies-btn")
        self.assertEqual(dismiss_action.target_label, "Accept All Cookies")
        # Second corrective action: re-attempt Save Changes
        retry_action = plan.corrective_actions[1]
        self.assertEqual(retry_action.target_node_id, "save-btn")

    async def test_form_validation_error_recovery(self) -> None:
        """Tests that a form validation failure generates a populate input -> submit plan."""
        email_input = UIStateNode(
            node_id="email-input",
            role=NodeRole.INPUT,
            bounds=BoundingBox(x1=200, y1=100, x2=400, y2=140),
            label="Email Address",
            value="",
            is_editable=True,
            attributes={"aria-invalid": "true", "class": "input-error"},
        )
        submit_btn = UIStateNode(
            node_id="submit-form-btn",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(x1=200, y1=200, x2=300, y2=240),
            label="Register",
            is_clickable=True,
        )

        state = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={"email-input": email_input, "submit-form-btn": submit_btn},
            viewport_size=(1000, 1000),
        )

        failed_action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="submit-form-btn",
            target_label="Register",
            coords=NormalizedCoords(x=0.25, y=0.22),
            safety_class=SafetyClass.REVERSIBLE,
        )

        verif_result = VerificationResult(
            outcome=OutcomeClass.ERROR,
            delta=StateDelta(outcome_class=OutcomeClass.ERROR),
            passed_assertions=[],
            failed_assertions=["form_submission_success"],
            settlement_duration_ms=100.0,
            requires_reconciliation=True,
            after_state=state,
        )

        recon_report = ReconciliationReport(
            action_id="act_002",
            inferred_cause="runtime_exception: form validation rejected empty email",
            current_state_summary="Validation errors present",
            is_retry_safe=False,
            recommended_recovery_action="replan: handle error or fill form",
            recent_errors=["Validation error: Email is required"],
        )

        plan: RecoveryPlan = await self.engine.diagnose_and_recover(
            task_goal="Register new user account",
            failed_state=state,
            failed_action=failed_action,
            verification_result=verif_result,
            reconciliation_report=recon_report,
        )

        self.assertFalse(plan.should_abort)
        self.assertIn("validation", plan.diagnosed_cause.lower())
        self.assertEqual(len(plan.corrective_actions), 2)
        # Action 1: Type into Email Address
        fill_action = plan.corrective_actions[0]
        self.assertEqual(fill_action.action_type, ActionType.TYPE)
        self.assertEqual(fill_action.target_node_id, "email-input")
        self.assertIn("@", fill_action.text_payload)
        # Action 2: Click Register
        submit_action = plan.corrective_actions[1]
        self.assertEqual(submit_action.target_node_id, "submit-form-btn")

    async def test_click_miss_noop_recovery(self) -> None:
        """Tests that a NOOP / focus miss triggers center-coordinate re-grounding."""
        btn_node = UIStateNode(
            node_id="btn-settings",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(x1=300, y1=400, x2=400, y2=450),
            label="Settings",
            is_clickable=True,
        )
        state = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={"btn-settings": btn_node},
            viewport_size=(1000, 1000),
        )

        failed_action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn-settings",
            target_label="Settings",
            coords=NormalizedCoords(x=0.29, y=0.39),  # slightly off-target
            safety_class=SafetyClass.REVERSIBLE,
        )

        verif_result = VerificationResult(
            outcome=OutcomeClass.NOOP,
            delta=StateDelta(outcome_class=OutcomeClass.NOOP),
            passed_assertions=[],
            failed_assertions=["delta_not_empty"],
            settlement_duration_ms=100.0,
            requires_reconciliation=True,
            after_state=state,
        )

        recon_report = ReconciliationReport(
            action_id="act_003",
            inferred_cause="focus_miss: target element did not receive focus or input event",
            current_state_summary="0 DOM delta",
            is_retry_safe=True,
            recommended_recovery_action="reground_and_retry: re-focus element or click center coordinates",
        )

        plan: RecoveryPlan = await self.engine.diagnose_and_recover(
            task_goal="Open Settings menu",
            failed_state=state,
            failed_action=failed_action,
            verification_result=verif_result,
            reconciliation_report=recon_report,
        )

        self.assertFalse(plan.should_abort)
        self.assertIn("miss", plan.diagnosed_cause.lower())
        self.assertEqual(len(plan.corrective_actions), 1)
        reground_action = plan.corrective_actions[0]
        self.assertEqual(reground_action.action_type, ActionType.CLICK)
        self.assertEqual(reground_action.target_node_id, "btn-settings")
        # Center of (300..400, 400..450) -> x=350/1000=0.35, y=425/1000=0.425
        self.assertAlmostEqual(reground_action.coords.x, 0.35, places=2)
        self.assertAlmostEqual(reground_action.coords.y, 0.425, places=2)

    async def test_fatal_unrecoverable_error_aborts(self) -> None:
        """Tests that a 500 server crash or fatal exception sets should_abort=True."""
        state = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={},
            viewport_size=(1000, 1000),
        )
        failed_action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="btn-checkout",
        )

        verif_result = VerificationResult(
            outcome=OutcomeClass.ERROR,
            delta=StateDelta(outcome_class=OutcomeClass.ERROR),
            passed_assertions=[],
            failed_assertions=["http_status_ok"],
            settlement_duration_ms=100.0,
            requires_reconciliation=True,
            after_state=state,
        )

        recon_report = ReconciliationReport(
            action_id="act_004",
            inferred_cause="runtime_exception: HTTP 500 Internal Server Error",
            current_state_summary="Server error",
            is_retry_safe=False,
            recommended_recovery_action="replan: abort",
            recent_errors=["HTTP 500 on /api/checkout"],
        )

        plan: RecoveryPlan = await self.engine.diagnose_and_recover(
            task_goal="Complete checkout",
            failed_state=state,
            failed_action=failed_action,
            verification_result=verif_result,
            reconciliation_report=recon_report,
        )

        self.assertTrue(plan.should_abort)
        self.assertEqual(len(plan.corrective_actions), 0)
        self.assertIn("fatal", plan.diagnosed_cause.lower())

    async def test_llm_abductive_recovery_reasoning(self) -> None:
        """Tests LLM-driven abductive recovery with structured JSON parsing."""
        llm_response = json.dumps({
            "diagnosed_cause": "Rate limit exceeded on payment gateway",
            "should_abort": False,
            "explanation": "Wait for 2 seconds before requesting token again.",
            "subgoal": "Backoff and retry",
            "corrective_actions": [
                {
                    "action_type": "wait",
                    "safety_class": "reversible",
                }
            ],
            "confidence": 0.85,
        })

        mock_llm = MockLLMClient(default_response=llm_response)
        engine = AbductiveRecoveryEngine(llm_client=mock_llm)

        state = CanonicalUIGraph(timestamp_ms=1000.0, nodes={}, viewport_size=(1000, 1000))
        failed_action = TypedAction(action_type=ActionType.CLICK)
        verif_result = VerificationResult(
            outcome=OutcomeClass.ERROR,
            delta=StateDelta(outcome_class=OutcomeClass.ERROR),
            passed_assertions=[],
            failed_assertions=["no_rate_limit"],
            settlement_duration_ms=50.0,
        )

        plan: RecoveryPlan = await engine.diagnose_and_recover(
            task_goal="Pay invoice",
            failed_state=state,
            failed_action=failed_action,
            verification_result=verif_result,
        )

        self.assertEqual(plan.diagnosed_cause, "Rate limit exceeded on payment gateway")
        self.assertEqual(len(plan.corrective_actions), 1)
        self.assertEqual(plan.corrective_actions[0].action_type, ActionType.WAIT)
        self.assertEqual(plan.confidence, 0.85)

    def test_recovery_plan_serialization_roundtrip(self) -> None:
        """Tests RecoveryPlan serialization to and from dict."""
        plan = RecoveryPlan(
            diagnosed_cause="Modal dialog occlusion",
            corrective_actions=[
                TypedAction(
                    action_type=ActionType.CLICK,
                    target_node_id="btn-close",
                    target_label="Close",
                )
            ],
            should_abort=False,
            explanation="Close dialog",
            subgoal="Dismiss modal",
            confidence=0.95,
            metadata={"test_key": "test_val"},
        )

        d = plan.to_dict()
        roundtripped = RecoveryPlan.from_dict(d)

        self.assertEqual(roundtripped.diagnosed_cause, plan.diagnosed_cause)
        self.assertEqual(len(roundtripped.corrective_actions), 1)
        self.assertEqual(roundtripped.corrective_actions[0].target_node_id, "btn-close")
        self.assertEqual(roundtripped.metadata["test_key"], "test_val")


if __name__ == "__main__":
    unittest.main()
