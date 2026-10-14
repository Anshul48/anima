"""Unit and Live Integration Tests for Reflex Real-Browser Evaluation Suite (Workstream R7).

Verifies LocalBenchmarkServer endpoints, RealBrowserArtifactManager persistence,
RealBrowserScorecard generation, and full end-to-end execution of TASK-REAL-01
through TASK-REAL-07 against live managed Chromium sessions.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Dict, List, Optional
import unittest
import urllib.request

from reflex.evals.real_browser_suite import (
    TASK_REAL_01_ID,
    TASK_REAL_02_ID,
    TASK_REAL_03_ID,
    TASK_REAL_04_ID,
    TASK_REAL_05_ID,
    TASK_REAL_06_ID,
    TASK_REAL_07_ID,
    LocalBenchmarkServer,
    RealBenchmarkProposalGenerator,
    RealBrowserArtifactManager,
    RealBrowserEvaluationRunner,
    RealBrowserScorecard,
    create_task_real_01,
    create_task_real_02,
    create_task_real_03,
    create_task_real_04,
    create_task_real_05,
    create_task_real_06,
    create_task_real_07,
    get_real_browser_portfolio_tasks,
)
from reflex.evals.reporting.scorecard import TaskBenchmarkResult
from reflex.perception.browser.managed_chromium import (
    ChromiumDiscovery,
    ManagedChromiumSession,
)
from reflex.schemas.actions import ActionType, TypedAction


class TestLocalBenchmarkServer(unittest.TestCase):
    """Tests for the local benchmark HTTP server lifecycle and endpoints."""

    def setUp(self) -> None:
        self.server = LocalBenchmarkServer()
        self.base_url = self.server.start()

    def tearDown(self) -> None:
        self.server.stop()

    def _fetch(self, path: str) -> tuple[int, bytes, Dict[str, str]]:
        url = self.server.get_url(path)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp.read(), headers

    def test_server_startup_and_health(self) -> None:
        self.assertTrue(self.server.actual_port > 0)
        status, body, _ = self._fetch("/health")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")

    def test_benchmark_html_endpoints(self) -> None:
        paths = [
            "/",
            "/registration",
            "/wizard",
            "/catalog",
            "/modal",
            "/async_validation",
            "/canvas",
            "/download",
        ]
        for p in paths:
            status, body, headers = self._fetch(p)
            self.assertEqual(status, 200, f"Path '{p}' returned HTTP {status}")
            self.assertIn("text/html", headers.get("content-type", ""))
            self.assertGreater(len(body), 100)

    def test_api_endpoints(self) -> None:
        # 1. Async validate username API
        status, body, _ = self._fetch("/api/validate_username")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("available"))

        # 2. Download export CSV API
        status, body, headers = self._fetch("/api/download_export")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers.get("content-type", ""))
        self.assertIn(b"TX-1001", body)


class TestRealBrowserArtifactManager(unittest.TestCase):
    """Tests for saving and organizing evidence artifacts to disk."""

    def test_artifact_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = RealBrowserArtifactManager(tmp_dir)
            task_id = "TASK-REAL-01"

            axtree = {"nodes": [{"id": 1, "role": "WebArea"}]}
            dom_snapshot = {"nodes": {}, "url": "http://127.0.0.1/registration"}
            screenshot = b"\x89PNG\r\n\x1a\n\x00\x00\x00fake_png"
            action_journal = [{"step": 1, "action": "TYPE", "latency_ms": 12.5}]
            task_result = {"task_id": task_id, "passed": True, "duration_ms": 150.0}

            saved = manager.save_task_artifacts(
                task_id=task_id,
                axtree=axtree,
                dom_snapshot=dom_snapshot,
                screenshot_bytes=screenshot,
                action_journal=action_journal,
                task_result=task_result,
            )

            self.assertIn("axtree", saved)
            self.assertIn("dom_snapshot", saved)
            self.assertIn("screenshot_final", saved)
            self.assertIn("action_journal", saved)
            self.assertIn("task_result", saved)

            for key, path_str in saved.items():
                p = Path(path_str)
                self.assertTrue(p.exists(), f"Artifact file {p} does not exist")
                self.assertGreater(p.stat().st_size, 0)

            # Verify contents
            saved_ax = json.loads(Path(saved["axtree"]).read_text(encoding="utf-8"))
            self.assertEqual(saved_ax["nodes"][0]["role"], "WebArea")

            saved_png = Path(saved["screenshot_final"]).read_bytes()
            self.assertEqual(saved_png, screenshot)


class TestRealBrowserScorecard(unittest.TestCase):
    """Tests for RealBrowserScorecard metric computation and formatting."""

    def test_scorecard_computation_and_markdown(self) -> None:
        results = [
            TaskBenchmarkResult(
                task_id="TASK-REAL-01",
                lane="browser_e2e",
                passed=True,
                total_steps=5,
                duration_ms=120.0,
                optimal_steps=5,
                step_efficiency=1.0,
                tier="tier_1_forms",
            ),
            TaskBenchmarkResult(
                task_id="TASK-REAL-02",
                lane="browser_e2e",
                passed=True,
                total_steps=4,
                duration_ms=90.0,
                optimal_steps=4,
                step_efficiency=1.0,
                tier="tier_1_forms",
            ),
        ]

        scorecard = RealBrowserScorecard.compute(
            suite_id="test_suite_v1",
            results=results,
            browser_binary="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            browser_version="Chrome/127.0.0.0",
        )

        self.assertEqual(scorecard.total_tasks, 2)
        self.assertEqual(scorecard.passed_tasks, 2)
        self.assertEqual(scorecard.failed_tasks, 0)
        self.assertEqual(scorecard.success_rate, 1.0)
        self.assertEqual(scorecard.execution_type, "REAL_MANAGED_BROWSER")
        self.assertEqual(scorecard.evidence_tier, "REAL_CDP_CHROMIUM")

        # Test JSON serialization
        json_str = scorecard.to_json()
        data = json.loads(json_str)
        self.assertEqual(data["suite_id"], "test_suite_v1")
        self.assertIn("caveats_and_integrity_pledge", data)

        # Test Markdown rendering
        md_str = scorecard.to_markdown()
        self.assertIn("Reflex Real-Browser Evaluation Scorecard", md_str)
        self.assertIn("100.0%", md_str)
        self.assertIn("REAL_MANAGED_BROWSER", md_str)

        # Test file persistence
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_base = Path(tmp_dir) / "test_scorecard"
            saved_paths = scorecard.save(out_base)
            self.assertTrue(Path(saved_paths["json"]).exists())
            self.assertTrue(Path(saved_paths["markdown"]).exists())


class TestRealBrowserTasksPortfolio(unittest.TestCase):
    """Tests task definitions and proposal generators."""

    def test_portfolio_task_definitions(self) -> None:
        base_url = "http://127.0.0.1:8080"
        tasks = get_real_browser_portfolio_tasks(base_url)
        self.assertEqual(len(tasks), 7)

        expected_ids = [
            TASK_REAL_01_ID,
            TASK_REAL_02_ID,
            TASK_REAL_03_ID,
            TASK_REAL_04_ID,
            TASK_REAL_05_ID,
            TASK_REAL_06_ID,
            TASK_REAL_07_ID,
        ]
        for task, exp_id in zip(tasks, expected_ids):
            self.assertEqual(task.task_id, exp_id)
            self.assertTrue(task.target_url.startswith(base_url))
            self.assertIsNotNone(task.proposal_generator)
            self.assertGreater(task.optimal_steps, 0)


class TestRealBrowserLiveExecution(unittest.TestCase):
    """End-to-end live integration test executing real tasks against Managed Chromium."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.browser_exe = ChromiumDiscovery.find_browser_executable()
        if not cls.browser_exe:
            raise unittest.SkipTest("No Chromium/Chrome/Edge executable available on host")

        cls.server = LocalBenchmarkServer()
        cls.base_url = cls.server.start()
        cls.tmp_output_dir = tempfile.mkdtemp(prefix="reflex_real_browser_eval_")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()
        if os.path.exists(cls.tmp_output_dir):
            shutil.rmtree(cls.tmp_output_dir, ignore_errors=True)

    def test_real_task_01_registration_live(self) -> None:
        """Executes TASK-REAL-01 against live Chrome and captures full evidence."""
        async def run():
            runner = RealBrowserEvaluationRunner(
                executable_path=self.browser_exe,
                headless="new",
                window_size=(1280, 800),
                output_dir=self.tmp_output_dir,
            )
            task = create_task_real_01(self.base_url)

            async with ManagedChromiumSession(
                executable_path=self.browser_exe,
                headless="new",
                window_size=(1280, 800),
                disable_gpu=True,
            ) as session:
                res, artifacts = await runner.run_task(task=task, session=session)

                self.assertEqual(res.task_id, TASK_REAL_01_ID)
                self.assertTrue(res.passed, f"Task 01 failed: {res.error_type}: {res.error_message}")
                self.assertEqual(res.total_steps, 5)
                self.assertGreater(res.duration_ms, 0)

                # Verify browser state directly
                submitted = await session.evaluate("window.__form_submitted === true")
                self.assertTrue(submitted, "Form should be submitted in live DOM context")

                # Verify all artifacts exist on disk
                self.assertTrue(Path(artifacts["axtree"]).exists())
                self.assertTrue(Path(artifacts["dom_snapshot"]).exists())
                self.assertTrue(Path(artifacts["screenshot_final"]).exists())
                self.assertTrue(Path(artifacts["action_journal"]).exists())
                self.assertTrue(Path(artifacts["task_result"]).exists())

                # Validate screenshot format
                png_bytes = Path(artifacts["screenshot_final"]).read_bytes()
                self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

        asyncio.run(run())

    def test_real_task_04_modal_interception_live(self) -> None:
        """Executes TASK-REAL-04 (cookie banner dismissal and offer claim) on live Chrome."""
        async def run():
            runner = RealBrowserEvaluationRunner(
                executable_path=self.browser_exe,
                headless="new",
                window_size=(1280, 800),
                output_dir=self.tmp_output_dir,
            )
            task = create_task_real_04(self.base_url)

            async with ManagedChromiumSession(
                executable_path=self.browser_exe,
                headless="new",
                window_size=(1280, 800),
                disable_gpu=True,
            ) as session:
                res, artifacts = await runner.run_task(task=task, session=session)

                self.assertEqual(res.task_id, TASK_REAL_04_ID)
                self.assertTrue(res.passed, f"Task 04 failed: {res.error_type}: {res.error_message}")
                self.assertEqual(res.total_steps, 2)

                claimed = await session.evaluate("window.__offer_claimed === true")
                self.assertTrue(claimed, "Special offer should be claimed after modal dismissal")

        asyncio.run(run())

    def test_real_browser_suite_end_to_end(self) -> None:
        """Executes complete 7-task benchmark suite end-to-end and verifies scorecard."""
        async def run():
            runner = RealBrowserEvaluationRunner(
                executable_path=self.browser_exe,
                headless="new",
                window_size=(1280, 800),
                output_dir=self.tmp_output_dir,
            )

            scorecard = await runner.run_suite(
                suite_id="workstream_r7_real_chromium",
                server=self.server,
            )

            self.assertEqual(scorecard.total_tasks, 7)
            self.assertEqual(scorecard.passed_tasks, 7)
            self.assertEqual(scorecard.failed_tasks, 0)
            self.assertEqual(scorecard.success_rate, 1.0)
            self.assertGreater(scorecard.median_latency_ms, 0)
            self.assertGreater(scorecard.p95_latency_ms, 0)

            # Verify scorecard files written to disk
            json_file = Path(self.tmp_output_dir) / "scorecard.json"
            md_file = Path(self.tmp_output_dir) / "scorecard.md"

            self.assertTrue(json_file.exists(), f"Scorecard JSON missing: {json_file}")
            self.assertTrue(md_file.exists(), f"Scorecard Markdown missing: {md_file}")

            # Verify JSON content
            sc_data = json.loads(json_file.read_text(encoding="utf-8"))
            self.assertEqual(sc_data["execution_type"], "REAL_MANAGED_BROWSER")
            self.assertEqual(sc_data["passed_tasks"], 7)
            self.assertEqual(len(sc_data["task_results"]), 7)
            self.assertEqual(len(sc_data["artifact_manifest"]), 7)

            # Verify all 7 task artifact directories exist
            for task_id in [
                TASK_REAL_01_ID,
                TASK_REAL_02_ID,
                TASK_REAL_03_ID,
                TASK_REAL_04_ID,
                TASK_REAL_05_ID,
                TASK_REAL_06_ID,
                TASK_REAL_07_ID,
            ]:
                task_dir = Path(self.tmp_output_dir) / task_id
                self.assertTrue(task_dir.exists(), f"Task artifact dir {task_dir} missing")
                self.assertTrue((task_dir / "axtree.json").exists())
                self.assertTrue((task_dir / "dom_snapshot.json").exists())
                self.assertTrue((task_dir / "screenshot_final.png").exists())
                self.assertTrue((task_dir / "action_journal.json").exists())
                self.assertTrue((task_dir / "task_result.json").exists())

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
