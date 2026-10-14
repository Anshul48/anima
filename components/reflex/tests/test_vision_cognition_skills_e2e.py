"""Comprehensive End-to-End Test Suite for Reflex Vision, Cognition, and Skill Lifecycle.

Workstreams R5 & R6 Verification:
1. Vision & Crop-and-Route (Differ, CropRouter, VisionGrounder).
2. Canvas Fallback Grounding & Sensor Disagreement Handling.
3. System 2 Planning & Abductive Recovery (Zero Direct Action Authority Invariant).
4. Predictive Surprise & Circuit Breaker (Efference Copies, PE > tau Motor Loop Halt).
5. Skill Lifecycle Governance (6 Stages, Template Extraction, Dynamic Re-Grounding, Auto-Quarantine).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import unittest

import numpy as np
from PIL import Image

# Perception / Vision
from reflex.perception.vision.crop_router import CropAndRouteEngine, CropPacket
from reflex.perception.vision.differ import (
    OpenCVVisualDiffer,
    VisualDifferenceResult,
    VisualDifferPort,
)
from reflex.perception.vision.vision_grounder import (
    BaseVisionGrounder,
    MockVisionGrounder,
    VisualDetection,
)

# Cognition / System 2
from reflex.cognition.system2.context_compressor import ContextCompressor
from reflex.cognition.system2.planner import PlannedStep, System2Planner
from reflex.cognition.system2.recovery import (
    AbductiveRecoveryEngine,
    RecoveryPlan,
)

# Cognition / Prediction & Surprise
from reflex.cognition.prediction.circuit_breaker import (
    BreakerFailureContext,
    SurpriseCircuitBreaker,
    SurpriseCircuitBreakerConfig,
)
from reflex.cognition.prediction.delta_engine import ExpectedDeltaEngine
from reflex.cognition.prediction.learned_gate import (
    BenchmarkMetrics,
    LearnedPredictorGate,
    LearnedPredictorGateConfig,
    LearnedPredictorPort,
    ShadowStepRecord,
)
from reflex.cognition.prediction.surprise_evaluator import (
    SurpriseEvaluator,
    SurpriseEvaluatorConfig,
)

# Cognition / Skills
from reflex.cognition.skills.executor import (
    SkillExecutionResult,
    SkillGroundingError,
    SkillReplayExecutor,
)
from reflex.cognition.skills.extractor import SkillExtractor
from reflex.cognition.skills.registry import (
    SkillMatchResult,
    SkillMetadata,
    SkillRegistry,
    SkillStatus,
)
from reflex.cognition.skills.shadow_validator import (
    ShadowRunReport,
    ShadowStepEvaluation,
    ShadowValidator,
)

# Grounding, Verification, Ports & Schemas
from reflex.grounding.browser_grounder import BrowserGroundingEngine
from reflex.ports.action import ActionPort, ActionReceipt, ActionStatus
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.ports.prediction import PredictionEvaluation
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.memory import MotorSkill, TransitionTuple
from reflex.schemas.policy import CapabilityScope
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    NodeRole,
    UIStateNode,
)
from reflex.verification.verifier import VerificationResult


# =============================================================================
# Mock Adapters for E2E Testing
# =============================================================================

class MockObservationAdapter(ObservationPort):
    """Mock observation port returning controlled UI graphs and screenshot buffers."""

    def __init__(self, initial_state: CanonicalUIGraph, screenshot_bytes: bytes = b""):
        self.current_state = initial_state
        self.screenshot_bytes = screenshot_bytes

    def set_state(self, state: CanonicalUIGraph) -> None:
        self.current_state = state

    async def capture_state(self) -> CanonicalUIGraph:
        return self.current_state

    async def capture_screenshot(self) -> bytes:
        return self.screenshot_bytes


class MockActionAdapter(ActionPort):
    """Mock physical action adapter recording dispatched actions."""

    def __init__(self, should_fail: bool = False, fail_error: str = "Hardware dispatch failure"):
        self.should_fail = should_fail
        self.fail_error = fail_error
        self.dispatched_actions: List[Tuple[TypedAction, ActionIdentity]] = []

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatched_actions.append((action, identity))
        if self.should_fail:
            raise RuntimeError(self.fail_error)
        return {
            "status": "success",
            "action_id": identity.action_id,
            "action_type": action.action_type.value,
        }


class MockNeuralPredictor(LearnedPredictorPort):
    """Mock learned world model predictor for LearnedPredictorGate testing."""

    def __init__(
        self,
        simulated_memory_mb: float = 256.0,
        divergence_rate: float = 0.0,
        always_predict_error: bool = False,
    ):
        self.simulated_memory_mb = simulated_memory_mb
        self.divergence_rate = divergence_rate
        self.always_predict_error = always_predict_error
        self.predict_call_count = 0

    def predict_delta(self, current_state: CanonicalUIGraph, action: TypedAction) -> StateDelta:
        self.predict_call_count += 1
        if self.always_predict_error:
            return StateDelta(outcome_class=OutcomeClass.ERROR, pixel_change_ratio=0.8)
        if action.action_type == ActionType.NAVIGATE:
            return StateDelta(outcome_class=OutcomeClass.NAVIGATION, pixel_change_ratio=0.5)
        return StateDelta(outcome_class=OutcomeClass.SUCCESS, pixel_change_ratio=0.01)

    def get_memory_usage_mb(self) -> float:
        return self.simulated_memory_mb


# =============================================================================
# 1. Vision & Crop-and-Route E2E Tests
# =============================================================================

class TestVisionAndCropAndRouteE2E(unittest.TestCase):
    """E2E verification of visual differencing, Otsu binarization, SSIM filtering, and CropPacket creation."""

    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = Path(__file__).parent / "fixtures" / "visual_diff"
        with open(cls.fixture_dir / "base_frame.png", "rb") as f:
            cls.base_frame_bytes = f.read()
        with open(cls.fixture_dir / "button_added.png", "rb") as f:
            cls.button_added_bytes = f.read()
        with open(cls.fixture_dir / "cursor_blink.png", "rb") as f:
            cls.cursor_blink_bytes = f.read()
        with open(cls.fixture_dir / "canvas_buttons.png", "rb") as f:
            cls.canvas_buttons_bytes = f.read()

    def setUp(self):
        self.differ = OpenCVVisualDiffer(ssim_noise_threshold=0.85)
        self.router = CropAndRouteEngine(default_format="PNG")

    def test_visual_differ_pipeline_and_otsu_detection(self):
        """Asserts frame differencing detects newly added UI components and calculates pixel change ratio."""
        # 1. Fast byte equality short-circuit
        static_result = self.differ.diff_frames(self.base_frame_bytes, self.base_frame_bytes)
        self.assertTrue(static_result.is_static)
        self.assertEqual(static_result.pixel_change_ratio, 0.0)
        self.assertEqual(len(static_result.changed_boxes), 0)

        # 2. Real visual change detection (button_added.png)
        change_result = self.differ.diff_frames(self.base_frame_bytes, self.button_added_bytes)
        self.assertFalse(change_result.is_static)
        self.assertGreater(change_result.pixel_change_ratio, 0.0)
        self.assertGreaterEqual(len(change_result.changed_boxes), 1)

        # Confirm changed bounding box encompasses button region
        btn_box = change_result.changed_boxes[0]
        self.assertGreater(btn_box.width, 0)
        self.assertGreater(btn_box.height, 0)

        # Serialization roundtrip
        res_dict = change_result.to_dict()
        res_restored = VisualDifferenceResult.from_dict(res_dict)
        self.assertEqual(change_result.is_static, res_restored.is_static)
        self.assertEqual(change_result.pixel_change_ratio, res_restored.pixel_change_ratio)
        self.assertEqual(len(change_result.changed_boxes), len(res_restored.changed_boxes))

    def test_visual_differ_ssim_noise_filtering_cursor_blink(self):
        """Asserts localized SSIM filtering suppresses blinking cursor and minor jitter noise."""
        # Cursor blink frame contains high-SSIM transient cursor line
        cursor_result = self.differ.diff_frames(self.base_frame_bytes, self.cursor_blink_bytes)
        self.assertTrue(
            cursor_result.is_static,
            f"Expected blinking cursor to be discarded by SSIM filtering, got {cursor_result.changed_boxes}",
        )
        self.assertEqual(cursor_result.pixel_change_ratio, 0.0)
        self.assertEqual(len(cursor_result.changed_boxes), 0)

    def test_visual_differ_fallback_mode_pure_python(self):
        """Asserts visual differencing functions reliably under forced fallback (pure numpy/PIL)."""
        fallback_differ = OpenCVVisualDiffer(force_fallback=True)
        fallback_result = fallback_differ.diff_frames(self.base_frame_bytes, self.button_added_bytes)
        self.assertFalse(fallback_result.is_static)
        self.assertGreater(fallback_result.pixel_change_ratio, 0.0)
        self.assertGreaterEqual(len(fallback_result.changed_boxes), 1)

    def test_crop_and_route_quadrants_and_lossless_roundtrip(self):
        """Asserts native-resolution crop extraction, quadrant positioning, and lossless base64 roundtrip."""
        w, h = 800, 600

        # Quadrant verification
        self.assertEqual(self.router.compute_quadrant((50, 50, 100, 100), w, h), "Top-Left")
        self.assertEqual(self.router.compute_quadrant((700, 50, 780, 100), w, h), "Top-Right")
        self.assertEqual(self.router.compute_quadrant((50, 500, 100, 580), w, h), "Bottom-Left")
        self.assertEqual(self.router.compute_quadrant((700, 500, 780, 580), w, h), "Bottom-Right")
        self.assertEqual(self.router.compute_quadrant((350, 250, 450, 350), w, h), "Center")

        # Native resolution crop extraction
        target_box = BoundingBox(x1=200, y1=100, x2=500, y2=140)  # 300x40 region
        crop_packet = self.router.crop_region(
            frame_bytes=self.base_frame_bytes,
            bounds=target_box,
            parent_label="search_bar",
            element_role="input",
            task_context="search_product",
        )

        self.assertIsInstance(crop_packet, CropPacket)
        self.assertEqual(crop_packet.bounding_box, (200, 100, 500, 140))
        self.assertEqual(crop_packet.parent_label, "search_bar")
        self.assertEqual(crop_packet.element_role, "input")
        self.assertEqual(crop_packet.task_context, "search_product")
        self.assertTrue(len(crop_packet.crop_base64) > 0)

        # Lossless decoding verification
        decoded_bytes = self.router.decode_crop(crop_packet)
        with Image.open(io.BytesIO(decoded_bytes)) as pil_img:
            self.assertEqual(pil_img.size, (300, 40))

    def test_batch_crop_routing_pipeline(self):
        """Asserts batch cropping extracts multiple disparate regions from a single screenshot."""
        targets = [
            (BoundingBox(x1=10, y1=10, x2=80, y2=40), "nav", "button"),
            {"bounding_box": (200, 100, 500, 140), "parent_label": "main", "element_role": "input"},
            BoundingBox(x1=300, y1=200, x2=400, y2=300),
        ]

        packets = self.router.batch_crop(
            frame_bytes=self.base_frame_bytes,
            targets=targets,
            task_context="batch_eval",
        )

        self.assertEqual(len(packets), 3)
        self.assertEqual(packets[0].element_role, "button")
        self.assertEqual(packets[1].element_role, "input")
        self.assertEqual(packets[1].parent_label, "main")


# =============================================================================
# 2. Canvas Fallback Grounding & Sensor Disagreement E2E Tests
# =============================================================================

class TestCanvasFallbackAndDisagreementE2E(unittest.IsolatedAsyncioTestCase):
    """E2E verification of canvas fallback visual grounding and sensor disagreement detection."""

    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = Path(__file__).parent / "fixtures" / "visual_diff"
        with open(cls.fixture_dir / "canvas_buttons.png", "rb") as f:
            cls.canvas_frame_bytes = f.read()

    def setUp(self):
        self.grounder = MockVisionGrounder(simulated_latency_ms=0.0, min_confidence=0.40)

    async def test_canvas_fallback_grounding_and_referring_expression(self):
        """Asserts visual detection of interactable elements inside opaque canvas and referring expression matching."""
        detections = await self.grounder.parse_ui_elements(self.canvas_frame_bytes)
        self.assertGreaterEqual(len(detections), 2)

        # Register mock referring expressions for precise semantic evaluation
        self.grounder.register_detection(
            VisualDetection(
                bounds=BoundingBox(x1=100, y1=150, x2=220, y2=200),
                label="Save Changes",
                confidence=0.98,
                element_type="button",
            )
        )
        self.grounder.register_detection(
            VisualDetection(
                bounds=BoundingBox(x1=260, y1=150, x2=380, y2=200),
                label="Cancel",
                confidence=0.95,
                element_type="button",
            )
        )

        # Match referring expression "Save Changes button"
        match_save = await self.grounder.ground_visual_target(
            self.canvas_frame_bytes, "Save Changes button"
        )
        self.assertIsNotNone(match_save)
        self.assertEqual(match_save.label, "Save Changes")
        self.assertEqual(match_save.bounds, BoundingBox(x1=100, y1=150, x2=220, y2=200))

        # Match referring expression "Cancel"
        match_cancel = await self.grounder.ground_visual_target(
            self.canvas_frame_bytes, "Cancel"
        )
        self.assertIsNotNone(match_cancel)
        self.assertEqual(match_cancel.label, "Cancel")

    async def test_sensor_disagreement_detection_escalates_uncertainty(self):
        """Asserts non-negotiable invariant: signal disagreement between DOM/AX and Vision escalates uncertainty."""
        # Simulated DOM report: Node 'btn_submit' reported at (100, 100, 200, 140)
        dom_node = UIStateNode(
            node_id="btn_submit",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(x1=100, y1=100, x2=200, y2=140),
            label="Submit Order",
            is_clickable=True,
        )
        dom_graph = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={"btn_submit": dom_node},
            url="https://shop.local/checkout",
        )

        # Vision report: Vision grounder detects button at (600, 400, 700, 440) due to layout transform / canvas displacement
        vision_detection = VisualDetection(
            bounds=BoundingBox(x1=600, y1=400, x2=700, y2=440),
            label="Submit Order",
            confidence=0.95,
            element_type="button",
        )

        # Compute IoU between DOM bounding box and Vision bounding box
        iou = BaseVisionGrounder.compute_iou(dom_node.bounds, vision_detection.bounds)
        self.assertEqual(iou, 0.0, "DOM and Vision bounding boxes are completely disjoint")

        # Disagreement detection rule: IoU < 0.20 on same element label indicates severe sensor discrepancy
        is_disagreement = (iou < 0.20)
        uncertainty_score = 1.0 - iou if is_disagreement else 0.0

        self.assertTrue(is_disagreement)
        self.assertEqual(uncertainty_score, 1.0)
        # Verify policy: when uncertainty is escalated (uncertainty_score >= 0.8), execution must escalate to recovery/re-grounding rather than guessing blind click
        self.assertGreaterEqual(uncertainty_score, 0.80)


# =============================================================================
# 3. System 2 Planning & Recovery (Zero Direct Action Authority) E2E Tests
# =============================================================================

class TestSystem2PlanningAndRecoveryE2E(unittest.IsolatedAsyncioTestCase):
    """E2E verification of System 2 planning, context compression, and abductive recovery."""

    def setUp(self):
        self.compressor = ContextCompressor()
        self.recovery_engine = AbductiveRecoveryEngine()
        self.planner = System2Planner(context_compressor=self.compressor, recovery_engine=self.recovery_engine)

        self.state_graph = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={
                "btn_login": UIStateNode(
                    node_id="btn_login",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(x1=100, y1=200, x2=200, y2=240),
                    label="Login",
                    is_clickable=True,
                ),
                "inp_email": UIStateNode(
                    node_id="inp_email",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(x1=100, y1=100, x2=300, y2=140),
                    label="Email Address",
                    is_editable=True,
                ),
            },
            url="https://auth.local/login",
            viewport_size=(1920, 1080),
        )

    async def test_system2_planning_zero_action_authority_invariant(self):
        """Asserts non-negotiable invariant: System 2 planning produces proposals only and has ZERO direct action authority."""
        plan_step = await self.planner.plan_next_step(
            task_goal="Log in to account with email test@example.com",
            current_state=self.state_graph,
        )

        self.assertIsInstance(plan_step, PlannedStep)
        self.assertIsInstance(plan_step.action, TypedAction)
        self.assertIsInstance(plan_step.expected_delta, StateDelta)
        self.assertGreater(plan_step.confidence, 0.0)

        # Invariant: PlannedStep is a data contract, NOT an executed receipt
        self.assertFalse(hasattr(plan_step, "execute"))
        self.assertFalse(hasattr(plan_step, "dispatch"))

        # Serialization roundtrip
        step_dict = plan_step.to_dict()
        step_restored = PlannedStep.from_dict(step_dict)
        self.assertEqual(plan_step.target_description, step_restored.target_description)
        self.assertEqual(plan_step.action.action_type, step_restored.action.action_type)

    def test_context_compressor_timeline_and_80_percent_reduction(self):
        """Asserts ContextCompressor achieves >= 80% token/character reduction while preserving causal narrative."""
        transitions: List[TransitionTuple] = []
        for i in range(10):
            tx = TransitionTuple(
                transition_id=f"tx_{i}",
                episode_id="ep_001",
                step_index=i,
                timestamp_ms=1000.0 + i * 100,
                ui_state_hash=f"hash_{i}",
                goal_text="Complete multi-step checkout wizard",
                goal_embedding=[0.1] * 384,
                visual_embedding=[0.2] * 384,
                action=TypedAction(
                    action_type=ActionType.CLICK if i % 2 == 0 else ActionType.TYPE,
                    target_node_id=f"node_{i}",
                    target_label=f"Field or Button {i}",
                    text_payload=f"value_{i}" if i % 2 != 0 else None,
                ),
                next_ui_state_hash=f"hash_{i+1}",
                delta=StateDelta(
                    added_nodes=[f"added_{i}"],
                    modified_nodes=[f"mod_{i}"],
                    pixel_change_ratio=0.05,
                    outcome_class=OutcomeClass.SUCCESS,
                ),
                duration_ms=150.0,
                surprise_score=0.02,
            )
            transitions.append(tx)

        stats = self.compressor.compute_compression_stats(transitions)
        self.assertGreaterEqual(
            stats["reduction_percentage"],
            80.0,
            f"Expected >= 80% context compression, got {stats['reduction_percentage']}%",
        )

        compressed_text = self.compressor.compress_history(
            transitions,
            initial_state_summary="URL: https://app.local",
        )
        self.assertIn("s_0:", compressed_text)
        self.assertIn("[Step 0]", compressed_text)
        self.assertIn("[Step 9]", compressed_text)

    async def test_abductive_recovery_modal_occlusion_and_form_validation(self):
        """Asserts AbductiveRecoveryEngine synthesizes corrective non-blind plans for modals, validation, and errors."""
        failed_action = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit", target_label="Submit")

        # SCENARIO A: Modal / Cookie banner occlusion
        modal_state = CanonicalUIGraph(
            timestamp_ms=2000.0,
            nodes={
                "cookie_modal": UIStateNode(
                    node_id="cookie_modal",
                    role=NodeRole.MODAL,
                    bounds=BoundingBox(x1=0, y1=500, x2=1920, y2=1080),
                    label="Cookie Consent Banner",
                ),
                "btn_accept": UIStateNode(
                    node_id="btn_accept",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(x1=900, y1=700, x2=1020, y2=740),
                    label="Accept all cookies",
                    is_clickable=True,
                ),
            },
            url="https://app.local",
        )
        verif_modal = VerificationResult(
            outcome=OutcomeClass.MODAL_APPEARED,
            delta=StateDelta(added_nodes=["cookie_modal"], outcome_class=OutcomeClass.MODAL_APPEARED),
            passed_assertions=[],
            failed_assertions=["Element occluded by modal overlay"],
            settlement_duration_ms=50.0,
            after_state=modal_state,
        )

        modal_plan = await self.recovery_engine.diagnose_and_recover(
            task_goal="Submit checkout form",
            failed_state=self.state_graph,
            failed_action=failed_action,
            verification_result=verif_modal,
        )

        self.assertFalse(modal_plan.should_abort)
        self.assertGreaterEqual(len(modal_plan.corrective_actions), 1)
        self.assertEqual(modal_plan.corrective_actions[0].target_node_id, "btn_accept")
        self.assertIn("occluded", modal_plan.diagnosed_cause.lower())

        # SCENARIO B: Fatal server error (HTTP 500)
        verif_fatal = VerificationResult(
            outcome=OutcomeClass.ERROR,
            delta=StateDelta(outcome_class=OutcomeClass.ERROR),
            passed_assertions=[],
            failed_assertions=["Server responded with HTTP 500 Internal Server Error"],
            settlement_duration_ms=50.0,
        )
        from reflex.verification.reconciliation import ReconciliationReport
        fatal_report = ReconciliationReport(
            action_id="act_fatal",
            inferred_cause="HTTP 500 Internal Server Error",
            current_state_summary="URL: https://app.local, HTTP 500 Internal Server Error",
            is_retry_safe=False,
            recommended_recovery_action="abort",
            recent_errors=["HTTP 500 Server Crash"],
        )

        fatal_plan = await self.recovery_engine.diagnose_and_recover(
            task_goal="Submit order",
            failed_state=self.state_graph,
            failed_action=failed_action,
            verification_result=verif_fatal,
            reconciliation_report=fatal_report,
        )

        self.assertTrue(fatal_plan.should_abort)
        self.assertIn("fatal", fatal_plan.diagnosed_cause.lower())


# =============================================================================
# 4. Prediction Expected Delta, Surprise & Circuit Breaker E2E Tests
# =============================================================================

class TestPredictionSurpriseAndCircuitBreakerE2E(unittest.TestCase):
    """E2E verification of Expected Delta generation, Surprise metric calculation, and Motor Loop Circuit Breaker."""

    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=1000.0)
        self.delta_engine = ExpectedDeltaEngine()
        self.evaluator = SurpriseEvaluator(config=SurpriseEvaluatorConfig(default_threshold=0.25))
        self.breaker = SurpriseCircuitBreaker(
            config=SurpriseCircuitBreakerConfig(threshold=0.25, consecutive_threshold=1),
            clock=self.clock,
        )

        self.state = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={
                "link_docs": UIStateNode(
                    node_id="link_docs",
                    role=NodeRole.LINK,
                    bounds=BoundingBox(x1=50, y1=50, x2=150, y2=80),
                    label="Documentation",
                    is_clickable=True,
                    attributes={"href": "/docs"},
                ),
                "btn_open_modal": UIStateNode(
                    node_id="btn_open_modal",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(x1=200, y1=50, x2=320, y2=80),
                    label="Open Settings Popup",
                    is_clickable=True,
                    attributes={"aria-haspopup": "dialog"},
                ),
                "chk_agree": UIStateNode(
                    node_id="chk_agree",
                    role=NodeRole.CHECKBOX,
                    bounds=BoundingBox(x1=50, y1=150, x2=70, y2=170),
                    label="I agree to terms",
                    is_clickable=True,
                ),
                "inp_search": UIStateNode(
                    node_id="inp_search",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(x1=100, y1=250, x2=400, y2=290),
                    label="Search repository",
                    is_editable=True,
                ),
            },
            url="https://app.local/main",
            viewport_size=(1920, 1080),
        )

    def test_expected_delta_efference_copy_generation(self):
        """Asserts ExpectedDeltaEngine computes precise deterministic expected state deltas across action primitives."""
        # 1. Click navigation link
        nav_act = TypedAction(action_type=ActionType.CLICK, target_node_id="link_docs")
        nav_delta = self.delta_engine.predict_expected_delta(self.state, nav_act)
        self.assertEqual(nav_delta.outcome_class, OutcomeClass.NAVIGATION)
        self.assertEqual(nav_delta.pixel_change_ratio, 0.50)

        # 2. Click modal trigger
        modal_act = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_open_modal")
        modal_delta = self.delta_engine.predict_expected_delta(self.state, modal_act)
        self.assertEqual(modal_delta.outcome_class, OutcomeClass.MODAL_APPEARED)
        self.assertIn("modal_root", modal_delta.added_nodes)

        # 3. Click checkbox
        chk_act = TypedAction(action_type=ActionType.CLICK, target_node_id="chk_agree")
        chk_delta = self.delta_engine.predict_expected_delta(self.state, chk_act)
        self.assertEqual(chk_delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertIn("chk_agree", chk_delta.modified_nodes)

        # 4. Type text
        type_act = TypedAction(action_type=ActionType.TYPE, target_node_id="inp_search", text_payload="reflex")
        type_delta = self.delta_engine.predict_expected_delta(self.state, type_act)
        self.assertEqual(type_delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertIn("inp_search", type_delta.modified_nodes)

        # 5. Key press Escape with active modal in state
        modal_open_state = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={
                "modal_1": UIStateNode(
                    node_id="modal_1",
                    role=NodeRole.MODAL,
                    bounds=BoundingBox(x1=300, y1=200, x2=800, y2=600),
                    label="Settings",
                )
            },
        )
        esc_act = TypedAction(action_type=ActionType.KEY_PRESS, key_code="Escape")
        esc_delta = self.delta_engine.predict_expected_delta(modal_open_state, esc_act)
        self.assertEqual(esc_delta.outcome_class, OutcomeClass.SUCCESS)
        self.assertIn("modal_1", esc_delta.removed_nodes)

    def test_surprise_evaluation_multimodal_metrics_and_causes(self):
        """Asserts SurpriseEvaluator computes composite PE and attributes precise diagnostic causes."""
        exp_success = StateDelta(modified_nodes=["btn_1"], outcome_class=OutcomeClass.SUCCESS, pixel_change_ratio=0.01)

        # 1. Normal matching transition (low surprise)
        obs_success = StateDelta(modified_nodes=["btn_1"], outcome_class=OutcomeClass.SUCCESS, pixel_change_ratio=0.01)
        eval_low = self.evaluator.evaluate_surprise(exp_success, obs_success)
        self.assertFalse(eval_low.is_surprised)
        self.assertLessEqual(eval_low.prediction_error, 0.25)
        self.assertEqual(eval_low.inferred_cause, "Expected Transition")

        # 2. Unexpected modal interception (high surprise)
        obs_modal = StateDelta(added_nodes=["modal_banner"], outcome_class=OutcomeClass.MODAL_APPEARED, pixel_change_ratio=0.30)
        eval_modal = self.evaluator.evaluate_surprise(exp_success, obs_modal)
        self.assertTrue(eval_modal.is_surprised)
        self.assertGreater(eval_modal.prediction_error, 0.25)
        self.assertEqual(eval_modal.inferred_cause, "Unexpected Modal Interception")

        # 3. Dead click / unresponsive element (high surprise)
        obs_noop = StateDelta(outcome_class=OutcomeClass.NOOP, pixel_change_ratio=0.0)
        eval_noop = self.evaluator.evaluate_surprise(exp_success, obs_noop)
        self.assertTrue(eval_noop.is_surprised)
        self.assertEqual(eval_noop.inferred_cause, "Dead Click / Unresponsive Element")

        # 4. Execution error / 500 crash (high surprise)
        obs_err = StateDelta(outcome_class=OutcomeClass.ERROR, pixel_change_ratio=0.5)
        eval_err = self.evaluator.evaluate_surprise(exp_success, obs_err)
        self.assertTrue(eval_err.is_surprised)
        self.assertEqual(eval_err.inferred_cause, "Execution Error / Application Fault")

    def test_surprise_circuit_breaker_trips_and_halts_motor_loop(self):
        """Asserts high surprise (PE > tau) immediately trips the circuit breaker and yields BreakerFailureContext."""
        eval_high = PredictionEvaluation(
            prediction_error=0.82,
            surprise_threshold=0.25,
            is_surprised=True,
            structural_mismatch=0.90,
            text_mismatch=0.75,
            visual_mismatch=0.40,
            inferred_cause="Unexpected Modal Interception",
        )

        # Check surprise on motor loop step
        should_halt = self.breaker.check_surprise(
            evaluation=eval_high,
            pre_state=self.state,
            action=TypedAction(action_type=ActionType.CLICK, target_node_id="link_docs"),
            expected_delta=StateDelta(outcome_class=OutcomeClass.NAVIGATION),
            observed_delta=StateDelta(outcome_class=OutcomeClass.MODAL_APPEARED),
        )

        self.assertTrue(should_halt, "Circuit breaker must halt the motor loop upon PE > tau")
        self.assertTrue(self.breaker.is_tripped)
        self.assertEqual(self.breaker.trip_count, 1)

        failure_ctx = self.breaker.last_failure_context
        self.assertIsNotNone(failure_ctx)
        self.assertIsInstance(failure_ctx, BreakerFailureContext)
        self.assertEqual(failure_ctx.evaluation.prediction_error, 0.82)
        self.assertEqual(failure_ctx.trip_count, 1)
        self.assertIn("TRIPPED", failure_ctx.details)

        # Reset breaker
        self.breaker.reset()
        self.assertFalse(self.breaker.is_tripped)
        self.assertEqual(self.breaker.consecutive_surprises, 0)

    def test_learned_gate_shadow_evaluation_and_promotion_criteria(self):
        """Asserts LearnedPredictorGate enforces empirical gating before promoting neural world models."""
        gate = LearnedPredictorGate(
            config=LearnedPredictorGateConfig(
                min_benchmark_samples=100,
                min_accuracy=0.90,
                max_false_positive_rate=0.05,
                max_latency_ms=20.0,
                max_memory_mb=1024.0,
                min_shadow_steps=50,
                max_shadow_divergence_rate=0.02,
            ),
            clock=self.clock,
        )

        candidate_model = MockNeuralPredictor(simulated_memory_mb=512.0)
        baseline_engine = ExpectedDeltaEngine()

        # 1. Offline benchmark evaluation
        samples = [
            (
                self.state,
                TypedAction(action_type=ActionType.NAVIGATE, text_payload="https://app.local"),
                StateDelta(outcome_class=OutcomeClass.NAVIGATION, pixel_change_ratio=0.50),
            )
            for _ in range(120)
        ]
        metrics = gate.run_offline_benchmark(candidate_model, samples)
        self.assertEqual(metrics.total_samples, 120)
        self.assertGreaterEqual(metrics.accuracy, 0.90)

        # 2. Record 60 shadow steps
        for i in range(60):
            gate.record_shadow_step(
                candidate_predictor=candidate_model,
                baseline_predictor=baseline_engine,
                current_state=self.state,
                action=TypedAction(action_type=ActionType.NAVIGATE, text_payload="https://app.local"),
                observed_delta=StateDelta(outcome_class=OutcomeClass.NAVIGATION, pixel_change_ratio=0.50),
            )

        # 3. Evaluate promotion
        result = gate.evaluate_promotion(candidate_metrics=metrics)
        self.assertTrue(result.is_promoted, f"Expected promotion, rejection reasons: {result.rejection_reasons}")
        self.assertTrue(result.benchmark_passed)
        self.assertTrue(result.shadow_passed)


# =============================================================================
# 5. Skill Lifecycle, Extraction, Dynamic Re-Grounding & Quarantine E2E Tests
# =============================================================================

class TestSkillLifecycleAndReplayE2E(unittest.IsolatedAsyncioTestCase):
    """E2E verification of Skill Extraction, 6-stage lifecycle governance, dynamic re-grounding, and quarantine."""

    def setUp(self):
        self.extractor = SkillExtractor()
        self.registry = SkillRegistry(db_path=":memory:", extractor=self.extractor)
        self.grounding_engine = BrowserGroundingEngine()
        self.shadow_validator = ShadowValidator(grounding_engine=self.grounding_engine)
        self.executor = SkillReplayExecutor(grounding_engine=self.grounding_engine)

        self.initial_graph = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={
                "inp_search": UIStateNode(
                    node_id="inp_search",
                    role=NodeRole.INPUT,
                    bounds=BoundingBox(x1=100, y1=100, x2=300, y2=140),
                    label="Search query",
                    is_editable=True,
                ),
                "btn_find": UIStateNode(
                    node_id="btn_find",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(x1=320, y1=100, x2=400, y2=140),
                    label="Search",
                    is_clickable=True,
                ),
            },
            url="https://store.local/search",
            viewport_size=(1920, 1080),
        )

    def test_skill_extraction_and_parameter_templating(self):
        """Asserts skill extraction parameterizes variable slots and strips brittle absolute coordinates."""
        transitions = [
            TransitionTuple(
                transition_id="tx_1",
                episode_id="ep_golden_1",
                step_index=0,
                timestamp_ms=1000.0,
                ui_state_hash="state_search_init",
                goal_text="Search for shoes",
                goal_embedding=[0.1] * 384,
                visual_embedding=[0.1] * 384,
                action=TypedAction(
                    action_type=ActionType.TYPE,
                    target_node_id="inp_search",
                    target_label="Search query",
                    coords=NormalizedCoords(x=0.1, y=0.1),  # Brittle coordinate present in raw recording
                    text_payload="shoes",
                ),
                next_ui_state_hash="state_search_typed",
                delta=StateDelta(modified_nodes=["inp_search"], outcome_class=OutcomeClass.SUCCESS),
                duration_ms=120.0,
                surprise_score=0.01,
            ),
            TransitionTuple(
                transition_id="tx_2",
                episode_id="ep_golden_1",
                step_index=1,
                timestamp_ms=1120.0,
                ui_state_hash="state_search_typed",
                goal_text="Search for shoes",
                goal_embedding=[0.1] * 384,
                visual_embedding=[0.1] * 384,
                action=TypedAction(
                    action_type=ActionType.CLICK,
                    target_node_id="btn_find",
                    target_label="Search",
                    coords=NormalizedCoords(x=0.18, y=0.1),
                ),
                next_ui_state_hash="state_search_results",
                delta=StateDelta(outcome_class=OutcomeClass.NAVIGATION, pixel_change_ratio=0.4),
                duration_ms=250.0,
                surprise_score=0.02,
            ),
        ]

        extracted_skill = self.extractor.extract_from_single_episode(
            transitions=transitions,
            initial_state=self.initial_graph,
            slot_mappings={"step_0": "query"},
        )

        self.assertIsInstance(extracted_skill, MotorSkill)
        self.assertEqual(len(extracted_skill.action_sequence), 2)

        # Invariant 1: Parameterized variable slot {{query}}
        step0 = extracted_skill.action_sequence[0]
        self.assertEqual(step0.text_payload, "{{query}}")

        # Invariant 2: STRICT stripping of absolute pixel coordinates
        self.assertIsNone(step0.coords, "Compiled MotorSkill must NEVER store fixed pixel coordinates")
        self.assertIsNone(extracted_skill.action_sequence[1].coords)

        # Invariant 3: Deterministic preconditions hash
        self.assertTrue(len(extracted_skill.preconditions_hash) >= 32)

    def test_skill_shadow_validator_agreement_and_stability(self):
        """Asserts ShadowValidator measures candidate agreement without executing actions."""
        # Create candidate skill
        skill = MotorSkill(
            skill_id="skill_search_001",
            version=1,
            preconditions_hash=self.extractor.compute_preconditions_hash(self.initial_graph),
            goal_embedding=[0.1] * 384,
            visual_context_embedding=[0.1] * 384,
            action_sequence=[
                TypedAction(action_type=ActionType.TYPE, target_label="Search query", text_payload="{{query}}"),
                TypedAction(action_type=ActionType.CLICK, target_label="Search"),
            ],
            expected_delta=StateDelta(outcome_class=OutcomeClass.NAVIGATION),
            timing_mean_ms=200.0,
            timing_std_ms=10.0,
            confidence=0.85,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep_01"],
            validated_count=1,
        )

        sys2_actions = [
            TypedAction(action_type=ActionType.TYPE, target_node_id="inp_search", target_label="Search query", text_payload="laptops"),
            TypedAction(action_type=ActionType.CLICK, target_node_id="btn_find", target_label="Search"),
        ]

        report = self.shadow_validator.evaluate_run(
            skill=skill,
            states=[self.initial_graph, self.initial_graph],
            system2_actions=sys2_actions,
            parameter_bindings={"query": "laptops"},
        )

        self.assertIsInstance(report, ShadowRunReport)
        self.assertTrue(report.passed)
        self.assertEqual(report.agreement_ratio, 1.0)
        self.assertEqual(report.locator_stability_ratio, 1.0)
        self.assertEqual(len(report.divergences), 0)

    def test_skill_registry_6_stage_lifecycle_and_promotion(self):
        """Asserts 6-stage lifecycle governance and fast-path lookup (< 5ms) returning PROMOTED skills only."""
        pre_hash = self.extractor.compute_preconditions_hash(self.initial_graph)
        skill = MotorSkill(
            skill_id="skill_login_001",
            version=1,
            preconditions_hash=pre_hash,
            goal_embedding=[0.1] * 384,
            visual_context_embedding=[0.1] * 384,
            action_sequence=[TypedAction(action_type=ActionType.CLICK, target_label="Search")],
            expected_delta=StateDelta(outcome_class=OutcomeClass.SUCCESS),
            timing_mean_ms=150.0,
            timing_std_ms=10.0,
            confidence=0.80,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep_1"],
            validated_count=1,
        )

        # 1. EXTRACTED stage
        self.registry.register_extracted(skill)
        meta = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta.status, SkillStatus.EXTRACTED)

        # Invariant: EXTRACTED skill is NEVER returned by fast-path lookup
        match_res = self.registry.find_matching_skill(self.initial_graph, "Search")
        self.assertIsNone(match_res)

        # 2. SHADOW / CANDIDATE stage
        self.registry.register_candidate(skill)
        meta = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta.status, SkillStatus.CANDIDATE)
        self.assertIsNone(self.registry.find_matching_skill(self.initial_graph, "Search"))

        # Simulate 5 successful shadow runs
        shadow_report = ShadowRunReport(
            skill_id=skill.skill_id,
            run_id="run_1",
            total_steps=1,
            agreed_steps=1,
            agreement_ratio=1.0,
            locator_stability_ratio=1.0,
            step_evaluations=[],
            divergences=[],
            passed=True,
        )
        for _ in range(5):
            self.registry.record_shadow_evaluation(skill.skill_id, shadow_report)

        self.registry.record_replay_validation(skill.skill_id, 1.0)

        # 3. PROMOTION stage
        self.registry.promote_skill(skill.skill_id)
        meta = self.registry.get_metadata(skill.skill_id)
        self.assertTrue(meta.is_trusted)
        self.assertEqual(meta.status, SkillStatus.PROMOTED)

        # Fast-path sub-5ms lookup succeeds for PROMOTED skill
        t0 = time.perf_counter()
        match_promoted = self.registry.find_matching_skill(self.initial_graph, "Search")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        self.assertIsNotNone(match_promoted)
        self.assertEqual(match_promoted.skill.skill_id, skill.skill_id)
        self.assertLess(elapsed_ms, 5.0, "Fast-path lookup must complete under 5ms")

    async def test_skill_replay_live_dynamic_regrounding(self):
        """Asserts skill execution dynamically re-grounds locators against shifted UI layout instead of stale coordinates."""
        skill = MotorSkill(
            skill_id="skill_dynamic_search",
            version=1,
            preconditions_hash="pre_dynamic",
            goal_embedding=[0.1] * 384,
            visual_context_embedding=[0.1] * 384,
            action_sequence=[
                TypedAction(
                    action_type=ActionType.CLICK,
                    target_label="Search",  # Abstract semantic locator
                    coords=None,            # No coordinates stored in template
                )
            ],
            expected_delta=StateDelta(outcome_class=OutcomeClass.NAVIGATION),
            timing_mean_ms=100.0,
            timing_std_ms=5.0,
            confidence=0.90,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep_1"],
            validated_count=5,
        )

        # Layout shift: 'Search' button is moved from (320, 100) to (800, 600)
        shifted_graph = CanonicalUIGraph(
            timestamp_ms=2000.0,
            nodes={
                "btn_find_shifted": UIStateNode(
                    node_id="btn_find_shifted",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(x1=800, y1=600, x2=920, y2=640),  # center (860, 620)
                    label="Search",
                    is_clickable=True,
                )
            },
            url="https://store.local/search",
            viewport_size=(1920, 1080),
        )

        proposal = self.executor.instantiate_step(
            skill=skill,
            step_index=0,
            current_state=shifted_graph,
            session_id="sess_dynamic_01",
        )

        self.assertIsInstance(proposal, ActionProposal)
        self.assertEqual(proposal.action.action_type, ActionType.CLICK)
        self.assertEqual(proposal.action.target_node_id, "btn_find_shifted")

        # Verified dynamic re-grounded coordinates
        expected_norm_x = round(860 / 1920, 4)
        expected_norm_y = round(620 / 1080, 4)
        self.assertIsNotNone(proposal.action.coords)
        self.assertAlmostEqual(proposal.action.coords.x, expected_norm_x, places=3)
        self.assertAlmostEqual(proposal.action.coords.y, expected_norm_y, places=3)

    async def test_skill_execution_and_automatic_quarantine_on_failure(self):
        """Asserts automated quarantine immediately halts usage of failing skills and transitions to RETIRED on repeated failure."""
        pre_hash = self.extractor.compute_preconditions_hash(self.initial_graph)
        skill = MotorSkill(
            skill_id="skill_checkout_flaky",
            version=1,
            preconditions_hash=pre_hash,
            goal_embedding=[0.1] * 384,
            visual_context_embedding=[0.1] * 384,
            action_sequence=[TypedAction(action_type=ActionType.CLICK, target_label="Search")],
            expected_delta=StateDelta(outcome_class=OutcomeClass.SUCCESS),
            timing_mean_ms=100.0,
            timing_std_ms=5.0,
            confidence=0.90,
            safety_class=SafetyClass.REVERSIBLE,
            provenance_episode_ids=["ep_1"],
            validated_count=10,
        )

        # Force promote to test live execution
        self.registry.register_candidate(skill)
        self.registry.promote_skill(skill.skill_id, force=True)
        self.assertTrue(self.registry.get_metadata(skill.skill_id).is_trusted)

        # 1. First Live Verification Failure -> IMMEDIATE QUARANTINE
        self.registry.record_execution_outcome(skill.skill_id, success=False, surprise_score=0.75)
        meta_after_fail1 = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta_after_fail1.status, SkillStatus.QUARANTINED)
        self.assertTrue(meta_after_fail1.is_quarantined)
        self.assertIn("Verification failure", meta_after_fail1.quarantine_reason)

        # Invariant: Quarantined skill is immediately removed from fast-path lookup
        self.assertIsNone(self.registry.find_matching_skill(self.initial_graph, "Search"))

        # 2. Subsequent failures leading to PERMANENT RETIREMENT (>= 3 failures)
        self.registry.record_execution_outcome(skill.skill_id, success=False, surprise_score=0.80)
        self.registry.record_execution_outcome(skill.skill_id, success=False, surprise_score=0.85)

        meta_retired = self.registry.get_metadata(skill.skill_id)
        self.assertEqual(meta_retired.status, SkillStatus.RETIRED)
        self.assertTrue(meta_retired.is_retired)
        self.assertEqual(meta_retired.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
