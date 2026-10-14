"""Unit and integration tests for System 2 Cognitive Planner."""

from __future__ import annotations

import json
import unittest

from reflex.cognition.system2.context_compressor import ContextCompressor
from reflex.cognition.system2.planner import PlannedStep, System2Planner
from reflex.cognition.system2.providers import (
    DeterministicRulePlanner,
    MockLLMClient,
)
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, ModalitySource, NodeRole, UIStateNode


class TestSystem2Planner(unittest.IsolatedAsyncioTestCase):
    """Test suite for System2Planner structured generation, affordances, and repair fallback."""

    def setUp(self) -> None:
        self.node_search = UIStateNode(
            node_id="search-input",
            role=NodeRole.INPUT,
            bounds=BoundingBox(x1=100, y1=50, x2=400, y2=90),
            label="Search query",
            value="",
            is_clickable=True,
            is_editable=True,
        )
        self.node_submit = UIStateNode(
            node_id="submit-btn",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(x1=420, y1=50, x2=500, y2=90),
            label="Search",
            is_clickable=True,
        )
        self.node_delete = UIStateNode(
            node_id="delete-btn",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(x1=100, y1=200, x2=200, y2=240),
            label="Delete Account",
            is_clickable=True,
        )

        self.sample_graph = CanonicalUIGraph(
            timestamp_ms=1000.0,
            nodes={
                "search-input": self.node_search,
                "submit-btn": self.node_submit,
                "delete-btn": self.node_delete,
            },
            url="https://example.com/home",
            active_window_title="Example Home",
            viewport_size=(1000, 1000),
        )

    async def test_golden_json_planning_click(self) -> None:
        """Tests standard golden JSON response parsing for a click action."""
        llm_response = json.dumps({
            "thought": "I need to click the search button to submit the query.",
            "subgoal": "Submit search query",
            "target_index": 2,
            "target_description": "Search button",
            "action_type": "click",
            "text_payload": None,
            "expected_outcome": "success",
            "expected_description": "Search results loaded",
            "confidence": 0.98,
        })

        mock_llm = MockLLMClient(default_response=llm_response)
        planner = System2Planner(llm_client=mock_llm)

        step: PlannedStep = await planner.plan_next_step(
            task_goal="Search for flight deals",
            current_state=self.sample_graph,
        )

        self.assertIsInstance(step, PlannedStep)
        self.assertEqual(step.action.action_type, ActionType.CLICK)
        self.assertEqual(step.action.target_node_id, "submit-btn")
        self.assertEqual(step.action.target_label, "Search")
        self.assertEqual(step.action.safety_class, SafetyClass.REVERSIBLE)
        self.assertIsNotNone(step.action.coords)
        # Center of (420..500, 50..90) in 1000x1000 -> x=460/1000=0.46, y=70/1000=0.07
        self.assertAlmostEqual(step.action.coords.x, 0.46, places=2)
        self.assertAlmostEqual(step.action.coords.y, 0.07, places=2)
        self.assertEqual(step.confidence, 0.98)
        self.assertEqual(step.expected_delta.outcome_class, OutcomeClass.SUCCESS)

    async def test_golden_json_planning_type(self) -> None:
        """Tests standard golden JSON response parsing for a typing action."""
        llm_response = """```json
{
  "thought": "Type 'flight tickets' into the search box.",
  "subgoal": "Fill search box",
  "target_index": 1,
  "target_description": "Search input box",
  "action_type": "type",
  "text_payload": "flight tickets",
  "expected_outcome": "success",
  "confidence": 0.95
}
```"""

        mock_llm = MockLLMClient(default_response=llm_response)
        planner = System2Planner(llm_client=mock_llm)

        step: PlannedStep = await planner.plan_next_step(
            task_goal="Search for flight tickets",
            current_state=self.sample_graph,
        )

        self.assertEqual(step.action.action_type, ActionType.TYPE)
        self.assertEqual(step.action.target_node_id, "search-input")
        self.assertEqual(step.action.text_payload, "flight tickets")
        self.assertEqual(step.subgoal, "Fill search box")

    async def test_destructive_safety_classification(self) -> None:
        """Tests that actions targeting destructive labels are classified as DESTRUCTIVE."""
        llm_response = json.dumps({
            "thought": "I will delete the account as requested by user.",
            "subgoal": "Delete account",
            "target_index": 3,
            "target_description": "Delete Account button",
            "action_type": "click",
            "confidence": 0.90,
        })

        mock_llm = MockLLMClient(default_response=llm_response)
        planner = System2Planner(llm_client=mock_llm)

        step: PlannedStep = await planner.plan_next_step(
            task_goal="Delete my account",
            current_state=self.sample_graph,
        )

        self.assertEqual(step.action.action_type, ActionType.CLICK)
        self.assertEqual(step.action.target_node_id, "delete-btn")
        self.assertEqual(step.action.safety_class, SafetyClass.DESTRUCTIVE)

    async def test_schema_repair_fallback_on_malformed_json(self) -> None:
        """Tests that a 1-turn repair prompt fixes malformed JSON from the LLM."""
        malformed_response = "Here is the next step:\n{thought: 'click search', target_index: 2, action_type: 'click', invalid_json..."
        repaired_response = json.dumps({
            "thought": "Click search button after fixing format",
            "subgoal": "Click search",
            "target_index": 2,
            "action_type": "click",
            "confidence": 0.92,
        })

        mock_llm = MockLLMClient(responses=[malformed_response, repaired_response])
        planner = System2Planner(llm_client=mock_llm, max_repair_retries=1)

        step: PlannedStep = await planner.plan_next_step(
            task_goal="Search query",
            current_state=self.sample_graph,
        )

        self.assertEqual(step.action.action_type, ActionType.CLICK)
        self.assertEqual(step.action.target_node_id, "submit-btn")
        self.assertEqual(len(mock_llm.call_history), 2)
        # Check that repair prompt contained the error notification
        self.assertIn("failed validation", mock_llm.call_history[1][1])

    async def test_fallback_to_rule_planner_if_llm_fails_completely(self) -> None:
        """Tests that total LLM failure falls back cleanly to deterministic rule planning."""
        mock_llm = MockLLMClient(default_response="Totally unparseable gibberish 12345")
        planner = System2Planner(llm_client=mock_llm, max_repair_retries=1)

        step: PlannedStep = await planner.plan_next_step(
            task_goal="click button 'Search'",
            current_state=self.sample_graph,
        )

        self.assertIsInstance(step, PlannedStep)
        self.assertEqual(step.action.action_type, ActionType.CLICK)
        self.assertEqual(step.action.target_node_id, "submit-btn")

    def test_affordances_formatting_and_prompt_assembly(self) -> None:
        """Tests affordance indexing, prompt construction, and history injection."""
        planner = System2Planner()
        sys_prompt, user_prompt, affordance_map = planner.build_planning_prompt(
            task_goal="Find flights to New York",
            current_state=self.sample_graph,
            history=[],
        )

        self.assertIn("TASK OBJECTIVE", user_prompt)
        self.assertIn("Find flights to New York", user_prompt)
        self.assertIn("CURRENT SCREEN AFFORDANCES", user_prompt)
        self.assertIn("[id=1]", user_prompt)
        self.assertIn("[id=2]", user_prompt)
        self.assertIn("submit-btn", user_prompt)
        self.assertEqual(len(affordance_map), 3)

    def test_planned_step_serialization_roundtrip(self) -> None:
        """Tests serialization and deserialization of PlannedStep."""
        step = PlannedStep(
            thought_reasoning="Navigate to dashboard",
            target_description="Dashboard URL",
            action=TypedAction(
                action_type=ActionType.NAVIGATE,
                text_payload="https://example.com/dashboard",
                safety_class=SafetyClass.REVERSIBLE,
            ),
            expected_delta=StateDelta(
                outcome_class=OutcomeClass.NAVIGATION,
                pixel_change_ratio=0.75,
            ),
            confidence=0.99,
            subgoal="Go to dashboard",
            metadata={"source": "test"},
        )

        d = step.to_dict()
        roundtripped = PlannedStep.from_dict(d)

        self.assertEqual(roundtripped.thought_reasoning, step.thought_reasoning)
        self.assertEqual(roundtripped.action.action_type, ActionType.NAVIGATE)
        self.assertEqual(roundtripped.action.text_payload, "https://example.com/dashboard")
        self.assertEqual(roundtripped.expected_delta.outcome_class, OutcomeClass.NAVIGATION)
        self.assertEqual(roundtripped.confidence, 0.99)
        self.assertEqual(roundtripped.metadata["source"], "test")

    async def test_deterministic_rule_planner_direct(self) -> None:
        """Tests deterministic rule planner without LLM."""
        planner = DeterministicRulePlanner()

        # 1. Navigation
        step_nav = await planner.plan_next_step(
            task_goal="navigate to https://news.ycombinator.com",
            current_state=self.sample_graph,
        )
        self.assertEqual(step_nav.action.action_type, ActionType.NAVIGATE)
        self.assertEqual(step_nav.action.text_payload, "https://news.ycombinator.com")

        # 2. Type
        step_type = await planner.plan_next_step(
            task_goal="type 'laptop' into Search query",
            current_state=self.sample_graph,
        )
        self.assertEqual(step_type.action.action_type, ActionType.TYPE)
        self.assertEqual(step_type.action.target_node_id, "search-input")
        self.assertEqual(step_type.action.text_payload, "laptop")

        # 3. Click
        step_click = await planner.plan_next_step(
            task_goal="click button 'Search'",
            current_state=self.sample_graph,
        )
        self.assertEqual(step_click.action.action_type, ActionType.CLICK)
        self.assertEqual(step_click.action.target_node_id, "submit-btn")


if __name__ == "__main__":
    unittest.main()
