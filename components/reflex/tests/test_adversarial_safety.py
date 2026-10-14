"""Adversarial Security Test Suite for Reflex.

Verifies defenses against indirect prompt injections, hidden DOM text,
clickjacking overlays, confused-deputy file exfiltration, and capability escalation.
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any, Dict, List, Optional

from reflex.evals.runner import EvalLane, EvaluationRunner, EvaluationTask, TaskTier
from reflex.evals.safety.adversarial_suite import AdversarialSecuritySuite
from reflex.host.identity.lease_manager import ActionLeaseManager
from reflex.host.kernel.host_kernel import HostControlKernel
from reflex.host.policy.capability_engine import CapabilityPolicyEngine
from reflex.orchestration.browser_loop import BrowserClosedLoopV1, TaskExecutionReport, TaskGoal, TaskStatus
from reflex.ports.clock import SystemClock
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityPolicy, CapabilityScope
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class TestAdversarialSafety(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying fail-closed policy enforcement and zero confused-deputy actuation."""

    async def test_indirect_prompt_injection_hidden_div_blocked(self):
        """Host kernel policy gate intercepts unauthorized destructive action injected via hidden DOM div."""
        task = AdversarialSecuritySuite.create_prompt_injection_hidden_div_task()
        runner = EvaluationRunner()

        results = await runner.run_task(task=task)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertTrue(res.passed, "Adversarial test must pass by blocking unauthorized destructive execution")
        self.assertEqual(res.lane, EvalLane.ADVERSARIAL_SAFETY.value)

    async def test_indirect_prompt_injection_comment_scope_escalation_blocked(self):
        """Host kernel rejects ungranted FS_WRITE scope injection attempt fail-closed."""
        task = AdversarialSecuritySuite.create_prompt_injection_comment_task()
        runner = EvaluationRunner()

        results = await runner.run_task(task=task)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertTrue(res.passed, "Adversarial test must pass by rejecting ungranted capability scopes")

    async def test_clickjacking_overlay_and_layout_shift_intercepted(self):
        """Pre-dispatch verification intercepts mutated bounding box without blind clicking."""
        task = AdversarialSecuritySuite.create_clickjacking_overlay_task()
        runner = EvaluationRunner()

        results = await runner.run_task(task=task)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertTrue(res.passed)

    async def test_confused_deputy_exfiltration_blocked(self):
        """Malicious webpage attempting confused-deputy FS_READ exfiltration is rejected fail-closed."""
        task = AdversarialSecuritySuite.create_confused_deputy_exfiltration_task()
        runner = EvaluationRunner()

        results = await runner.run_task(task=task)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertTrue(res.passed)

    async def test_blacklisted_domain_navigation_blocked(self):
        """Attempt to navigate to blacklisted phishing domain is rejected by policy engine."""
        task = AdversarialSecuritySuite.create_blacklisted_domain_task()
        runner = EvaluationRunner()

        results = await runner.run_task(task=task)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertTrue(res.passed)

    async def test_full_adversarial_safety_suite_run(self):
        """AdversarialSecuritySuite executes all safety tasks and generates complete report."""
        report = await AdversarialSecuritySuite.run_all_safety_suites()

        self.assertEqual(report.total_tasks, 5)
        self.assertEqual(report.passed_tasks, 5)
        self.assertEqual(report.failed_tasks, 0)
        self.assertAlmostEqual(report.success_rate, 1.0)
        self.assertEqual(report.lane, EvalLane.ADVERSARIAL_SAFETY)
