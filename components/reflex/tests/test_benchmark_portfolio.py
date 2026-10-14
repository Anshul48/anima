"""Standardized 12-Task Benchmark Portfolio Test Suite for Reflex.

Verifies end-to-end autonomous execution across Tier 1 (Forms & Wizards),
Tier 2 (Dynamic SPAs, Modals & Tables), and Tier 3 (Complex Flows, Downloads & Canvas).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from reflex.evals.portfolio import (
    create_task_eval_01,
    create_task_eval_02,
    create_task_eval_03,
    create_task_eval_04,
    create_task_eval_05,
    create_task_eval_06,
    create_task_eval_07,
    create_task_eval_08,
    create_task_eval_09,
    create_task_eval_10,
    create_task_eval_11,
    create_task_eval_12,
    get_standard_portfolio_tasks,
    get_tier_tasks,
)
from reflex.evals.runner import EvaluationReport, EvaluationRunner, EvaluationTask, TaskTier


class TestBenchmarkPortfolio(unittest.IsolatedAsyncioTestCase):
    """Test suite executing the normative 12-task benchmark portfolio on local fixtures."""

    async def asyncSetUp(self):
        self.runner = EvaluationRunner()

    async def test_tier1_tasks_individually(self):
        """Tier 1 tasks (T01 - T04) execute autonomously with 100% success and optimal steps."""
        tier1_tasks = [
            (create_task_eval_01(), 5),
            (create_task_eval_02(), 7),
            (create_task_eval_03(), 4),
            (create_task_eval_04(), 4),
        ]

        for task, expected_opt_steps in tier1_tasks:
            with self.subTest(task_id=task.task_id):
                results = await self.runner.run_task(task=task)
                self.assertEqual(len(results), 1)
                res = results[0]
                self.assertTrue(res.passed, f"Task {task.task_id} failed: {res.error_message}")
                self.assertEqual(res.optimal_steps, expected_opt_steps)
                self.assertEqual(res.tier, TaskTier.TIER_1_FORMS.value)
                self.assertAlmostEqual(res.step_efficiency, 1.0, places=2)

    async def test_tier2_tasks_individually(self):
        """Tier 2 tasks (T05 - T08) handle dynamic SPAs, popups, async validation, and iframes."""
        tier2_tasks = [
            (create_task_eval_05(), 4),
            (create_task_eval_06(), 3),
            (create_task_eval_07(), 4),
            (create_task_eval_08(), 5),
        ]

        for task, expected_opt_steps in tier2_tasks:
            with self.subTest(task_id=task.task_id):
                results = await self.runner.run_task(task=task)
                self.assertEqual(len(results), 1)
                res = results[0]
                self.assertTrue(res.passed, f"Task {task.task_id} failed: {res.error_message}")
                self.assertEqual(res.optimal_steps, expected_opt_steps)
                self.assertEqual(res.tier, TaskTier.TIER_2_SPAS.value)

    async def test_tier3_tasks_individually(self):
        """Tier 3 tasks (T09 - T12) handle downloads, drag-and-drop, canvas grounding, and multi-tabs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            t09 = create_task_eval_09(download_dir=tmpdir)
            t10 = create_task_eval_10()
            t11 = create_task_eval_11()
            t12 = create_task_eval_12()

            tier3_tasks = [
                (t09, 2),
                (t10, 1),
                (t11, 1),
                (t12, 4),
            ]

            for task, expected_opt_steps in tier3_tasks:
                with self.subTest(task_id=task.task_id):
                    results = await self.runner.run_task(task=task)
                    self.assertEqual(len(results), 1)
                    res = results[0]
                    self.assertTrue(res.passed, f"Task {task.task_id} failed: {res.error_message}")
                    self.assertEqual(res.optimal_steps, expected_opt_steps)
                    self.assertEqual(res.tier, TaskTier.TIER_3_COMPLEX.value)

    async def test_full_12_task_portfolio_suite(self):
        """Standardized 12-task portfolio suite runs to 100% completion generating valid scorecard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks = [
                create_task_eval_01(),
                create_task_eval_02(),
                create_task_eval_03(),
                create_task_eval_04(),
                create_task_eval_05(),
                create_task_eval_06(),
                create_task_eval_07(),
                create_task_eval_08(),
                create_task_eval_09(download_dir=tmpdir),
                create_task_eval_10(),
                create_task_eval_11(),
                create_task_eval_12(),
            ]

            report: EvaluationReport = await self.runner.run_suite(
                tasks=tasks,
                suite_id="standard_12_task_v1",
                repetitions=1,
            )

            self.assertEqual(report.total_tasks, 12)
            self.assertEqual(report.passed_tasks, 12)
            self.assertEqual(report.failed_tasks, 0)
            self.assertAlmostEqual(report.success_rate, 1.0)
            self.assertAlmostEqual(report.mean_step_efficiency, 1.0, places=2)
            self.assertGreater(report.median_latency_ms, 0.0)
            self.assertGreater(report.total_tokens, 0)

            # Scorecard formatting
            scorecard = report.to_scorecard()
            md = scorecard.to_markdown()
            self.assertIn("100.0% (12/12)", md)
            self.assertIn("TASK-EVAL-01", md)
            self.assertIn("TASK-EVAL-12", md)

    def test_tier_filtering_helper(self):
        """get_tier_tasks correctly partitions tasks into tiers."""
        t1 = get_tier_tasks(TaskTier.TIER_1_FORMS)
        t2 = get_tier_tasks(TaskTier.TIER_2_SPAS)
        t3 = get_tier_tasks(TaskTier.TIER_3_COMPLEX)

        self.assertEqual(len(t1), 4)
        self.assertEqual(len(t2), 4)
        self.assertEqual(len(t3), 4)
