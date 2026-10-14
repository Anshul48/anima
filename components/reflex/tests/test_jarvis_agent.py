"""Test Suite: Jarvis Agent Autonomous Command Routing, Transference, and Fast-Path Replay."""

from __future__ import annotations

import asyncio
import time
from typing import Optional
import unittest

from reflex.agent.jarvis import JarvisAgent, JarvisExecutionResult
from reflex.cognition.prediction.circuit_breaker import BreakerFailureContext, SurpriseCircuitBreaker
from reflex.cognition.prediction.efference_verifier import (
    EfferenceCopyVerifier,
    EfferenceVerificationResult,
)
from reflex.cognition.skills.extractor import SkillExtractor
from reflex.cognition.skills.registry import SkillRegistry
from reflex.cognition.system2.planner import PlannedStep, System2Planner
from reflex.cognition.system2.providers import DeterministicRulePlanner, MockLLMClient
from reflex.execution.native.window_manager import (
    MockWindowManagerSubstrate,
    NativeWindowManager,
)
from reflex.ports.prediction import PredictionEvaluation
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestJarvisAgentWindowManagement(unittest.IsolatedAsyncioTestCase):
    """Asserts deterministic desktop window manager commands."""

    async def asyncSetUp(self) -> None:
        self.substrate = MockWindowManagerSubstrate()
        self.wm = NativeWindowManager(substrate=self.substrate, screen_width=1920, screen_height=1080)
        self.agent = JarvisAgent(window_manager=self.wm, use_mock=True)

    async def test_tile_windows_grid_command(self) -> None:
        # Prepopulate windows
        self.substrate.add_window("Doc 1 - Notepad", process_name="notepad.exe")
        self.substrate.add_window("Doc 2 - Notepad", process_name="notepad.exe")
        self.substrate.add_window("Doc 3 - Notepad", process_name="notepad.exe")

        res: JarvisExecutionResult = await self.agent.execute_command("tile notepads grid")
        self.assertTrue(res.success)
        self.assertEqual(res.substrate, "window_manager")
        self.assertEqual(res.actions_executed, 3)
        self.assertIn("grid layout", res.output)

    async def test_tile_windows_columns_command(self) -> None:
        self.substrate.add_window("Doc A - Notepad", process_name="notepad.exe")
        self.substrate.add_window("Doc B - Notepad", process_name="notepad.exe")

        res = await self.agent.execute_command("tile notepads horizontal side by side")
        self.assertTrue(res.success)
        self.assertEqual(res.substrate, "window_manager")
        self.assertEqual(res.actions_executed, 2)
        self.assertIn("horizontal layout", res.output)

    async def test_list_windows_command(self) -> None:
        self.substrate.add_window("Calc", process_name="calc.exe")
        res = await self.agent.execute_command("list windows")
        self.assertTrue(res.success)
        self.assertEqual(res.substrate, "window_manager")
        self.assertIn("Active Top-Level Windows", res.output)
        self.assertIn("Calc", res.output)

    async def test_focus_and_minimize_command(self) -> None:
        h = self.substrate.add_window("MyNotes - Notepad", process_name="notepad.exe")

        # Focus
        res_focus = await self.agent.execute_command("focus MyNotes")
        self.assertTrue(res_focus.success)
        self.assertEqual(self.wm.get_focused_window().handle, h)

        # Minimize
        res_min = await self.agent.execute_command("minimize MyNotes")
        self.assertTrue(res_min.success)
        self.assertTrue(self.substrate.windows[h]["is_minimized"])

        # Maximize
        res_max = await self.agent.execute_command("maximize MyNotes")
        self.assertTrue(res_max.success)
        self.assertTrue(self.substrate.windows[h]["is_maximized"])

        # Close
        res_close = await self.agent.execute_command("close MyNotes")
        self.assertTrue(res_close.success)
        self.assertEqual(len(self.wm.list_windows()), 0)

    async def test_launch_notepad_command(self) -> None:
        res = await self.agent.execute_command("open notepad")
        self.assertTrue(res.success)
        self.assertEqual(res.substrate, "window_manager")
        self.assertEqual(len(self.wm.list_windows()), 1)


class TestJarvisAgentCognitionAndTransference(unittest.IsolatedAsyncioTestCase):
    """Asserts System 2 deliberative execution, closed-loop verification, and System 1 transference."""

    def _create_mock_ui_state(self) -> CanonicalUIGraph:
        nodes = {
            "search_box": UIStateNode(
                node_id="search_box",
                role=NodeRole.INPUT,
                bounds=BoundingBox(100, 100, 400, 140),
                label="Search",
                value="",
                is_editable=True,
            ),
            "btn_go": UIStateNode(
                node_id="btn_go",
                role=NodeRole.BUTTON,
                bounds=BoundingBox(410, 100, 480, 140),
                label="Go",
                is_clickable=True,
            ),
        }
        return CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=nodes,
            url="https://app.example.com",
            viewport_size=(1920, 1080),
        )

    async def asyncSetUp(self) -> None:
        self.substrate = MockWindowManagerSubstrate()
        self.wm = NativeWindowManager(substrate=self.substrate)
        self.extractor = SkillExtractor()
        self.registry = SkillRegistry(db_path=":memory:", extractor=self.extractor)
        self.verifier = EfferenceCopyVerifier()

        # Deterministic rule planner for System 2 to ensure instant unit test execution
        self.planner = System2Planner(llm_client=None)

        self.agent = JarvisAgent(
            window_manager=self.wm,
            skill_registry=self.registry,
            skill_extractor=self.extractor,
            planner=self.planner,
            verifier=self.verifier,
            use_mock=True,
        )

    async def test_system2_planning_and_system1_transference(self) -> None:
        """Asserts goal runs through System 2 deliberation and automatically compiles to System 1."""
        ui_state = self._create_mock_ui_state()
        command = "type 'jarvis query' into search"

        # 1. First execution: no skill exists -> System 2 deliberation
        res1 = await self.agent.execute_command(command, live_state=ui_state)
        self.assertTrue(res1.success)
        self.assertEqual(res1.substrate, "system2_deliberation")
        self.assertTrue(res1.transferred_to_system1)
        self.assertIsNotNone(res1.new_skill_id)
        self.assertGreaterEqual(res1.actions_executed, 1)

        # Confirm new skill is trusted in the registry
        skill = self.registry.get_skill(res1.new_skill_id)
        self.assertIsNotNone(skill)
        meta = self.registry.get_metadata(res1.new_skill_id)
        self.assertIsNotNone(meta)
        self.assertTrue(meta.is_trusted)

        # 2. Second execution: identical state & command -> System 1 Fast-Path Replay!
        res2 = await self.agent.execute_command(command, live_state=ui_state)
        self.assertTrue(res2.success)
        self.assertEqual(res2.substrate, "system1_fast_path")
        self.assertIn("fast path", res2.output)
        self.assertEqual(res2.actions_executed, len(skill.action_sequence))

    async def test_system1_circuit_breaker_trip_quarantines_skill(self) -> None:
        """Asserts that failure during fast-path execution trips circuit breaker and quarantines skill."""
        ui_state = self._create_mock_ui_state()
        command = "type 'jarvis query' into search"

        # Train and promote skill
        res1 = await self.agent.execute_command(command, live_state=ui_state)
        self.assertTrue(res1.transferred_to_system1)
        skill_id = res1.new_skill_id

        # Replace verifier with one that triggers surprise
        failing_verifier = EfferenceCopyVerifier()
        # Mock verify_transition to simulate high surprise
        def mock_verify(*args, **kwargs):
            eval_res = PredictionEvaluation(
                prediction_error=0.85,
                surprise_threshold=0.25,
                is_surprised=True,
                structural_mismatch=0.8,
                text_mismatch=0.0,
                visual_mismatch=0.8,
                inferred_cause="unexpected_modal_interception",
            )
            return EfferenceVerificationResult(
                is_verified=False,
                prediction_error=0.85,
                surprise_threshold=0.25,
                circuit_breaker_tripped=True,
                expected_delta=StateDelta(),
                observed_delta=StateDelta(),
                evaluation=eval_res,
                inferred_cause="unexpected_modal_interception",
                details="Mock circuit breaker trip",
            )
        failing_verifier.verify_transition = mock_verify
        self.agent.verifier = failing_verifier

        # Execute again -> Fast path trips breaker
        res_fail = await self.agent.execute_command(command, live_state=ui_state)
        self.assertFalse(res_fail.success)
        self.assertEqual(res_fail.substrate, "system1_fast_path")
        self.assertTrue(res_fail.circuit_breaker_tripped)
        self.assertIn("quarantined", res_fail.output)

        # Assert skill is now quarantined
        meta = self.registry.get_metadata(skill_id)
        self.assertIsNotNone(meta)
        self.assertTrue(meta.is_quarantined)

        # Restore normal verifier and query again: quarantined skill MUST NOT be executed via System 1
        self.agent.verifier = EfferenceCopyVerifier()
        res3 = await self.agent.execute_command(command, live_state=ui_state)
        # Quarantined skill was bypassed, cascading to System 2 deliberation
        self.assertEqual(res3.substrate, "system2_deliberation")

    async def test_system2_circuit_breaker_trip_aborts_transference(self) -> None:
        """Asserts that high prediction error during System 2 deliberation trips breaker and aborts transference."""
        ui_state = self._create_mock_ui_state()
        command = "type 'crash test' into search"

        # Verifier that triggers circuit breaker trip during System 2 planning
        failing_verifier = EfferenceCopyVerifier()
        def mock_verify(*args, **kwargs):
            eval_res = PredictionEvaluation(
                prediction_error=0.95,
                surprise_threshold=0.25,
                is_surprised=True,
                structural_mismatch=0.95,
                text_mismatch=0.0,
                visual_mismatch=0.95,
                inferred_cause="unexpected_state_interception",
            )
            return EfferenceVerificationResult(
                is_verified=False,
                prediction_error=0.95,
                surprise_threshold=0.25,
                circuit_breaker_tripped=True,
                expected_delta=StateDelta(),
                observed_delta=StateDelta(),
                evaluation=eval_res,
                inferred_cause="unexpected_state_interception",
                details="Mock breaker trip in System 2",
            )
        failing_verifier.verify_transition = mock_verify
        self.agent.verifier = failing_verifier

        res = await self.agent.execute_command(command, live_state=ui_state)
        self.assertFalse(res.success)
        self.assertEqual(res.substrate, "system2_deliberation")
        self.assertTrue(res.circuit_breaker_tripped)
        self.assertFalse(res.transferred_to_system1)
        self.assertIsNone(res.new_skill_id)
        self.assertIn("Circuit Breaker TRIPPED", res.output)
        self.assertEqual(len(self.registry.list_skills()), 0)

    async def test_launch_browser_and_app_commands(self) -> None:
        """Asserts open browser and calculator spawn windows in window manager."""
        res_browser = await self.agent.execute_command("open browser")
        self.assertTrue(res_browser.success)
        self.assertEqual(res_browser.substrate, "window_manager")
        self.assertTrue(any("chrome" in w.process_name.lower() or "browser" in w.title.lower() for w in self.wm.list_windows()))

        res_calc = await self.agent.execute_command("launch calculator")
        self.assertTrue(res_calc.success)
        self.assertEqual(res_calc.substrate, "window_manager")
        self.assertTrue(any("calc" in w.process_name.lower() for w in self.wm.list_windows()))

    async def test_click_close_button_not_hijacked_by_wm(self) -> None:
        """Asserts that 'click close button' routes to cognitive layer and not window manager."""
        ui_state = CanonicalUIGraph(
            timestamp_ms=0,
            nodes={
                "close_btn": UIStateNode(
                    node_id="close_btn",
                    role=NodeRole.BUTTON,
                    bounds=BoundingBox(10, 10, 50, 50),
                    label="Close",
                    is_clickable=True,
                )
            }
        )
        res = await self.agent.execute_command("click close button", live_state=ui_state)
        self.assertNotEqual(res.substrate, "window_manager")
        self.assertEqual(res.substrate, "system2_deliberation")

    async def test_minimize_and_close_window_active_fallback(self) -> None:
        """Asserts 'minimize window' and 'close window' target active window when no title given."""
        h = self.substrate.add_window("Active WorkDoc - WordPad", process_name="wordpad.exe")
        self.substrate.focus_window(h)

        res_min = await self.agent.execute_command("minimize window")
        self.assertTrue(res_min.success)
        self.assertTrue(self.substrate.windows[h]["is_minimized"])

        res_close = await self.agent.execute_command("close window")
        self.assertTrue(res_close.success)
        self.assertNotIn(h, self.substrate.windows)


if __name__ == "__main__":
    unittest.main()
