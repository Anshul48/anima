"""Unit and integration test suite for Reflex Evaluation Runner, Metrics & Scorecards."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from reflex.evals.adapters.browsergym_adapter import BrowserGymAdapter, FakeBrowserGymEnv
from reflex.evals.portfolio import (
    create_task_eval_01,
    create_task_eval_02,
    create_task_eval_03,
    get_tier_tasks,
)
from reflex.evals.reporting.scorecard import (
    BenchmarkReporter,
    EvaluationScorecard,
    TaskBenchmarkResult,
    get_system_hardware_specs,
)
from reflex.evals.runner import (
    EvalLane,
    EvaluationReport,
    EvaluationRunner,
    EvaluationTask,
    TaskTier,
)
from reflex.orchestration.browser_loop import TaskGoal, TaskStatus
from reflex.ports.clock import DeterministicClock
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityPolicy, CapabilityScope
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestEvaluationRunner(unittest.IsolatedAsyncioTestCase):
    """Test suite for evaluation harness orchestration, metrics aggregation, and scorecards."""

    async def test_runner_executes_single_task_success(self):
        """EvaluationRunner runs task, checks objective assertions, and records valid metrics."""
        task = create_task_eval_01()
        runner = EvaluationRunner()

        results = await runner.run_task(task=task, repetitions=1)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.task_id, "TASK-EVAL-01")
        self.assertTrue(res.passed)
        self.assertEqual(res.total_steps, 5)
        self.assertEqual(res.optimal_steps, 5)
        self.assertAlmostEqual(res.step_efficiency, 1.0, places=2)
        self.assertGreater(res.duration_ms, 0.0)
        self.assertGreater(res.tokens_used, 0)
        self.assertEqual(res.tier, TaskTier.TIER_1_FORMS.value)

    async def test_runner_enforces_step_budget_ceiling(self):
        """Tasks exceeding step budget ceiling fail with MAX_STEPS_EXCEEDED."""
        # Create a task with optimal_steps=2, max_steps ceiling = 3, but 5 proposals
        from reflex.evals.portfolio import DeterministicBenchmarkProposalGenerator, MockTaskObservationPort

        obs = MockTaskObservationPort(CanonicalUIGraph(1000.0, {}))
        proposals = [
            TypedAction(action_type=ActionType.NOOP),
            TypedAction(action_type=ActionType.NOOP),
            TypedAction(action_type=ActionType.NOOP),
            TypedAction(action_type=ActionType.NOOP),
            TypedAction(action_type=ActionType.NOOP),
        ]
        proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EXCEED-CEILING", proposals, obs_port=obs)

        task = EvaluationTask(
            task_id="TASK-EXCEED-CEILING",
            instruction="Exceed step budget ceiling",
            target_url="http://test.local",
            optimal_steps=2,
            max_steps=3,  # Ceiling is 3 steps
            observation_port=obs,
            proposal_generator=proposal_gen,
        )

        runner = EvaluationRunner()
        results = await runner.run_task(task=task)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertFalse(res.passed)
        self.assertIn("MAX_STEPS_EXCEEDED", res.error_type or "")

    async def test_runner_multi_task_suite_aggregation(self):
        """EvaluationRunner runs multiple tasks and aggregates metrics into EvaluationReport."""
        tasks = [create_task_eval_01(), create_task_eval_02(), create_task_eval_03()]
        runner = EvaluationRunner()

        report = await runner.run_suite(tasks=tasks, suite_id="tier1_test_suite", repetitions=1)

        self.assertEqual(report.suite_id, "tier1_test_suite")
        self.assertEqual(report.total_tasks, 3)
        self.assertEqual(report.passed_tasks, 3)
        self.assertEqual(report.failed_tasks, 0)
        self.assertAlmostEqual(report.success_rate, 1.0)
        self.assertGreater(report.median_latency_ms, 0.0)
        self.assertGreater(report.p95_latency_ms, 0.0)
        self.assertAlmostEqual(report.mean_step_efficiency, 1.0, places=2)
        self.assertGreater(report.total_tokens, 0)

    async def test_runner_repetitions_support(self):
        """Runner executes repetitions with distinct provenance tags."""
        task = create_task_eval_01()
        runner = EvaluationRunner()

        results = await runner.run_task(task=task, repetitions=3)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].task_id, "TASK-EVAL-01#r1")
        self.assertEqual(results[1].task_id, "TASK-EVAL-01#r2")
        self.assertEqual(results[2].task_id, "TASK-EVAL-01#r3")
        self.assertTrue(all(r.passed for r in results))

    async def test_runner_lane_filtering(self):
        """Runner filters tasks by execution lane."""
        task1 = create_task_eval_01()  # BROWSER_E2E
        task2 = EvaluationTask(
            task_id="TASK-CONFORMANCE-01",
            instruction="Conformance check",
            target_url="http://test.local",
            lane=EvalLane.CONFORMANCE,
            optimal_steps=1,
        )

        runner = EvaluationRunner()
        report = await runner.run_suite(
            tasks=[task1, task2],
            suite_id="lane_filter_suite",
            lane=EvalLane.BROWSER_E2E,
        )

        self.assertEqual(report.total_tasks, 1)
        self.assertEqual(report.task_results[0].task_id, "TASK-EVAL-01")

    def test_scorecard_serialization_and_markdown(self):
        """EvaluationScorecard generates valid JSON and rich Markdown reports."""
        res1 = TaskBenchmarkResult(
            task_id="T01",
            lane="browser_e2e",
            passed=True,
            total_steps=5,
            duration_ms=120.0,
            tokens_used=600,
            system1_steps=0,
            system2_steps=5,
            optimal_steps=5,
            step_efficiency=1.0,
            tier="tier_1_forms",
        )
        res2 = TaskBenchmarkResult(
            task_id="T02",
            lane="browser_e2e",
            passed=False,
            total_steps=8,
            duration_ms=250.0,
            tokens_used=960,
            system1_steps=0,
            system2_steps=8,
            optimal_steps=4,
            step_efficiency=0.5,
            error_type="MAX_STEPS_EXCEEDED",
            error_message="Step limit exceeded",
            tier="tier_1_forms",
        )

        scorecard = BenchmarkReporter.create_scorecard(
            suite_id="unit_test_scorecard",
            results=[res1, res2],
            model_configurations={"planner": "mock_v1", "temp": "0.0"},
        )

        self.assertEqual(scorecard.total_tasks, 2)
        self.assertEqual(scorecard.passed_tasks, 1)
        self.assertEqual(scorecard.failed_tasks, 1)
        self.assertAlmostEqual(scorecard.success_rate, 0.5)

        # Test Markdown formatting
        md = scorecard.to_markdown()
        self.assertIn("# Reflex Evaluation Scorecard: `unit_test_scorecard`", md)
        self.assertIn("Task Success Rate (SR)", md)
        self.assertIn("| `T01` |", md)
        self.assertIn("| `T02` |", md)

        # Test JSON serialization roundtrip
        json_str = scorecard.to_json()
        data = json.loads(json_str)
        restored = EvaluationScorecard.from_dict(data)
        self.assertEqual(restored.suite_id, scorecard.suite_id)
        self.assertEqual(restored.passed_tasks, scorecard.passed_tasks)
        self.assertEqual(len(restored.task_results), 2)

    def test_scorecard_file_saving(self):
        """EvaluationScorecard can save to .json and .md files."""
        scorecard = BenchmarkReporter.create_scorecard(
            suite_id="file_save_suite",
            results=[],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "scorecard.json")
            md_path = os.path.join(tmpdir, "scorecard.md")

            scorecard.save(json_path)
            scorecard.save(md_path)

            self.assertTrue(os.path.exists(json_path))
            self.assertTrue(os.path.exists(md_path))
            self.assertGreater(os.path.getsize(json_path), 0)
            self.assertGreater(os.path.getsize(md_path), 0)

    def test_hardware_specs_discovery(self):
        """Hardware discovery extracts valid host specifications."""
        specs = get_system_hardware_specs()
        self.assertIn("os_name", specs)
        self.assertIn("python_version", specs)
        self.assertIn("cpu_count", specs)
        self.assertTrue(int(specs["cpu_count"]) >= 1)

    async def test_browsergym_adapter_flow(self):
        """BrowserGymAdapter bridges Gym environment to Reflex CanonicalUIGraph and actions."""
        env = FakeBrowserGymEnv(goal="Fill and submit form")
        adapter = BrowserGymAdapter(env=env)

        graph, info = adapter.reset()
        self.assertIn("1", graph.nodes)
        self.assertIn("2", graph.nodes)
        self.assertIn("3", graph.nodes)

        # Step 1: Type name
        type_name = TypedAction(action_type=ActionType.TYPE, target_node_id="1", text_payload="Alice")
        graph2, reward, term, trunc, info = await adapter.step(type_name)
        self.assertFalse(term)

        # Step 2: Type email
        type_email = TypedAction(action_type=ActionType.TYPE, target_node_id="2", text_payload="alice@test.com")
        graph3, reward, term, trunc, info = await adapter.step(type_email)
        self.assertFalse(term)

        # Step 3: Click submit
        click_sub = TypedAction(action_type=ActionType.CLICK, target_node_id="3")
        graph4, reward, term, trunc, info = await adapter.step(click_sub)
        self.assertTrue(term)
        self.assertEqual(reward, 1.0)
