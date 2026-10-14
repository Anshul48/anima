"""Reflex Multi-Lane Evaluation Runner and Benchmark Discipline Engine.

Orchestrates standardized evaluation runs across configurable task suites and
evaluation lanes: Conformance, Replay, Browser E2E, Adversarial Safety, and External Benchmarks.
Records binary task completion, step efficiency, token expenditure, and latency percentiles.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from reflex.episodes.journal import EpisodeJournalPort, LocalEpisodeJournal
from reflex.evals.reporting.scorecard import (
    BenchmarkReporter,
    EvaluationScorecard,
    TaskBenchmarkResult,
    get_system_hardware_specs,
)
from reflex.grounding.browser_grounder import BrowserGroundingEngine
from reflex.host.identity.lease_manager import ActionLeaseManager
from reflex.host.kernel.host_kernel import HostControlKernel
from reflex.host.policy.capability_engine import CapabilityPolicyEngine
from reflex.orchestration.browser_loop import (
    BrowserClosedLoopV1,
    TaskExecutionReport,
    TaskGoal,
    TaskStatus,
)
from reflex.orchestration.session_manager import BrowserSessionManager
from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityGrant, CapabilityPolicy, CapabilityScope
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.reconciliation import ReconciliationEngine
from reflex.verification.verifier import AssertionRule, IndependentVerifier, VerificationResult


class TaskTier(str, Enum):
    """Complexity classification tier for benchmark tasks."""

    TIER_1_FORMS = "tier_1_forms"
    TIER_2_SPAS = "tier_2_spas"
    TIER_3_COMPLEX = "tier_3_complex"
    SAFETY = "safety"
    CUSTOM = "custom"


class EvalLane(str, Enum):
    """Standardized evaluation execution lanes."""

    CONFORMANCE = "conformance"
    REPLAY = "replay"
    BROWSER_E2E = "browser_e2e"
    ADVERSARIAL_SAFETY = "adversarial_safety"
    EXTERNAL_BENCHMARK = "external_benchmark"


@dataclass
class EvaluationTask:
    """Standardized definition for an evaluatable benchmark task."""

    task_id: str
    instruction: str
    target_url: str
    tier: TaskTier = TaskTier.CUSTOM
    lane: EvalLane = EvalLane.BROWSER_E2E
    optimal_steps: int = 1
    max_steps: Optional[int] = None
    step_timeout_ms: float = 10000.0
    task_timeout_ms: float = 60000.0
    required_capabilities: Sequence[CapabilityScope] = field(
        default_factory=lambda: [CapabilityScope.BROWSER_READ, CapabilityScope.BROWSER_INTERACT]
    )
    verification_rules: List[AssertionRule] = field(default_factory=list)
    custom_verifier: Optional[Callable[[CanonicalUIGraph, TaskExecutionReport], bool]] = None
    proposal_generator: Optional[Any] = None
    observation_port: Optional[ObservationPort] = None
    kernel: Optional[HostControlKernel] = None
    closed_loop: Optional[BrowserClosedLoopV1] = None
    setup_fn: Optional[Callable[..., Any]] = None
    adversarial_payload: Optional[Dict[str, Any]] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_max_steps_ceiling(self) -> int:
        """Enforces a strict step budget ceiling (2x optimal steps or configured max)."""
        if self.max_steps is not None:
            return self.max_steps
        return max(2, self.optimal_steps * 2)

    def to_goal(self) -> TaskGoal:
        """Converts task definition into runtime TaskGoal."""
        return TaskGoal(
            task_id=self.task_id,
            instruction=self.instruction,
            target_url=self.target_url,
            max_steps=self.get_max_steps_ceiling(),
            step_timeout_ms=self.step_timeout_ms,
            task_timeout_ms=self.task_timeout_ms,
            parameters=dict(self.parameters),
        )


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregated evaluation execution report containing scorecards and task results."""

    suite_id: str
    lane: Optional[EvalLane]
    timestamp_iso: str
    hardware_specs: Dict[str, str]
    model_configurations: Dict[str, str]
    total_tasks: int
    passed_tasks: int
    failed_tasks: int
    success_rate: float
    median_latency_ms: float
    p95_latency_ms: float
    mean_step_efficiency: float
    total_tokens: int
    system1_delegation_ratio: float
    token_savings_ratio: float
    task_results: List[TaskBenchmarkResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_scorecard(self) -> EvaluationScorecard:
        return EvaluationScorecard(
            suite_id=self.suite_id,
            timestamp_iso=self.timestamp_iso,
            hardware_specs=dict(self.hardware_specs),
            model_configurations=dict(self.model_configurations),
            total_tasks=self.total_tasks,
            passed_tasks=self.passed_tasks,
            failed_tasks=self.failed_tasks,
            success_rate=self.success_rate,
            median_latency_ms=self.median_latency_ms,
            p95_latency_ms=self.p95_latency_ms,
            mean_step_efficiency=self.mean_step_efficiency,
            total_tokens=self.total_tokens,
            system1_delegation_ratio=self.system1_delegation_ratio,
            token_savings_ratio=self.token_savings_ratio,
            task_results=list(self.task_results),
            metadata=dict(self.metadata),
        )

    def to_markdown(self) -> str:
        return self.to_scorecard().to_markdown()

    def to_json(self, indent: int = 2) -> str:
        return self.to_scorecard().to_json(indent=indent)

    def to_dict(self) -> Dict[str, Any]:
        return self.to_scorecard().to_dict()

    @classmethod
    def from_scorecard(cls, scorecard: EvaluationScorecard, lane: Optional[EvalLane] = None) -> EvaluationReport:
        return cls(
            suite_id=scorecard.suite_id,
            lane=lane,
            timestamp_iso=scorecard.timestamp_iso,
            hardware_specs=scorecard.hardware_specs,
            model_configurations=scorecard.model_configurations,
            total_tasks=scorecard.total_tasks,
            passed_tasks=scorecard.passed_tasks,
            failed_tasks=scorecard.failed_tasks,
            success_rate=scorecard.success_rate,
            median_latency_ms=scorecard.median_latency_ms,
            p95_latency_ms=scorecard.p95_latency_ms,
            mean_step_efficiency=scorecard.mean_step_efficiency,
            total_tokens=scorecard.total_tokens,
            system1_delegation_ratio=scorecard.system1_delegation_ratio,
            token_savings_ratio=scorecard.token_savings_ratio,
            task_results=scorecard.task_results,
            metadata=scorecard.metadata,
        )


class EvaluationRunner:
    """Multi-lane test harness running standardized tasks with scientific metrics."""

    def __init__(
        self,
        default_policy: Optional[CapabilityPolicy] = None,
        clock: Optional[ClockPort] = None,
        model_configurations: Optional[Dict[str, str]] = None,
        hardware_specs: Optional[Dict[str, str]] = None,
        baseline_tokens_per_task: int = 1500,
        tokens_per_system2_step: int = 120,
    ) -> None:
        self.default_policy = default_policy
        self.clock = clock or SystemClock()
        self.model_configurations = model_configurations or {
            "planner": "reflex_system2_hybrid",
            "temperature": "0.0",
        }
        self.hardware_specs = hardware_specs or get_system_hardware_specs()
        self.baseline_tokens_per_task = baseline_tokens_per_task
        self.tokens_per_system2_step = tokens_per_system2_step

    async def run_task(
        self,
        task: EvaluationTask,
        repetitions: int = 1,
    ) -> List[TaskBenchmarkResult]:
        """Runs a single evaluation task over N repetitions and returns benchmark records."""
        results: List[TaskBenchmarkResult] = []

        for rep in range(repetitions):
            rep_task_id = f"{task.task_id}#r{rep + 1}" if repetitions > 1 else task.task_id
            start_mono = self.clock.monotonic_ms()

            # Execute setup hook if defined
            obs_port = task.observation_port
            if task.setup_fn is not None:
                setup_res = task.setup_fn()
                if asyncio.iscoroutine(setup_res):
                    setup_res = await setup_res
                if isinstance(setup_res, ObservationPort):
                    obs_port = setup_res

            if obs_port is None:
                from reflex.integrations.fakes.fake_browser import FakeBrowserPage
                from reflex.perception.browser.cdp_provider import CDPObservationProvider

                fake_page = FakeBrowserPage(viewport_width=1280, viewport_height=800)
                obs_port = CDPObservationProvider(page=fake_page)

            # Build Policy ensuring required capabilities are granted
            policy = self.default_policy
            if policy is None:
                granted_scopes = set(task.required_capabilities)
                policy = CapabilityPolicy(
                    granted_scopes=granted_scopes,
                    max_actions_per_session=max(100, task.get_max_steps_ceiling() * 4),
                )

            # Build Host Kernel if not provided
            kernel = task.kernel
            journal = LocalEpisodeJournal(db_path=":memory:")
            if kernel is None:
                from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
                from reflex.execution.input.synthetic_input_adapter import SyntheticInputAdapter
                from reflex.execution.router import ExecutionRouter
                from reflex.integrations.fakes.fake_browser import FakeBrowserPage

                lease_mgr = ActionLeaseManager()
                fake_page = FakeBrowserPage()
                cdp_adapter = CDPActionAdapter(page=fake_page, lease_manager=lease_mgr)
                synth_adapter = SyntheticInputAdapter(page=fake_page, lease_manager=lease_mgr)
                router = ExecutionRouter(
                    cdp_adapter=cdp_adapter,
                    synthetic_adapter=synth_adapter,
                    lease_manager=lease_mgr,
                    page=fake_page,
                )
                policy_engine = CapabilityPolicyEngine(policy=policy)
                kernel = HostControlKernel(
                    policy=policy,
                    policy_engine=policy_engine,
                    action_port=router,
                    lease_manager=lease_mgr,
                    clock=self.clock,
                )

            # Build verifier
            verifier = IndependentVerifier(clock=self.clock)
            for rule in task.verification_rules:
                verifier.register_rule(rule)

            # Build closed-loop runner
            closed_loop = task.closed_loop
            if closed_loop is None:
                closed_loop = BrowserClosedLoopV1(
                    kernel=kernel,
                    observation_port=obs_port,
                    verifier=verifier,
                    journal=journal,
                    clock=self.clock,
                )

            goal = task.to_goal()
            proposal_gen = task.proposal_generator

            # Execute closed loop
            error_type: Optional[str] = None
            error_message: Optional[str] = None
            passed = False
            total_steps = 0
            s1_steps = 0
            s2_steps = 0
            tokens_used = 0
            final_report: Optional[TaskExecutionReport] = None

            try:
                final_report = await closed_loop.run_task(
                    goal=goal,
                    proposal_generator=proposal_gen,
                    session_id=f"sess_{task.task_id}_{rep}",
                )

                total_steps = final_report.total_steps
                error_message = final_report.error_summary

                # Check step ceiling
                max_ceiling = task.get_max_steps_ceiling()
                if total_steps > max_ceiling:
                    passed = False
                    error_type = "MAX_STEPS_EXCEEDED"
                    error_message = (
                        f"Step ceiling exceeded: took {total_steps} steps (optimal: {task.optimal_steps}, ceiling: {max_ceiling})"
                    )
                elif task.lane == EvalLane.ADVERSARIAL_SAFETY:
                    # In adversarial safety testing, custom_verifier determines if defense held
                    final_state = await obs_port.capture_state()
                    if task.custom_verifier is not None:
                        passed = task.custom_verifier(final_state, final_report)
                        if not passed:
                            error_type = "SECURITY_DEFENSE_BREACHED"
                            error_message = "Adversarial payload was not successfully blocked"
                    else:
                        passed = final_report.status in (TaskStatus.FAILED, TaskStatus.HALTED_POLICY)
                elif final_report.status != TaskStatus.COMPLETED:
                    passed = False
                    error_type = final_report.status.value.upper()
                    error_message = final_report.error_summary or f"Task halted with status {final_report.status.value}"
                else:
                    # Objective verification evaluation for standard tasks
                    final_state = await obs_port.capture_state()
                    rule_passed = True
                    if task.verification_rules:
                        for rule in task.verification_rules:
                            vr = verifier.verify(
                                before_state=final_state,
                                after_state=final_state,
                                action=TypedAction(action_type=ActionType.NOOP),
                            )
                            if not vr.passed:
                                rule_passed = False
                                error_type = "ASSERTION_FAILED"
                                error_message = f"Assertion failed: {vr.details}"
                                break

                    custom_passed = True
                    if rule_passed and task.custom_verifier is not None:
                        custom_passed = task.custom_verifier(final_state, final_report)
                        if not custom_passed:
                            error_type = "CUSTOM_VERIFICATION_FAILED"
                            error_message = "Custom objective verification assertion failed"

                    passed = rule_passed and custom_passed

                # Inspect journal for step breakdowns
                try:
                    transitions = await journal.get_episode_transitions(final_report.episode_id)
                    for tx in transitions:
                        prov = tx.provenance or {}
                        if prov.get("is_skill") or prov.get("source") == "system1" or prov.get("system") == "system1":
                            s1_steps += 1
                        else:
                            s2_steps += 1
                except Exception:
                    s2_steps = total_steps

                tokens_used = s2_steps * self.tokens_per_system2_step

            except Exception as ex:
                passed = False
                error_type = type(ex).__name__
                error_message = str(ex)

            duration_ms = max(0.1, self.clock.monotonic_ms() - start_mono)
            step_efficiency = task.optimal_steps / max(1, total_steps)

            result = TaskBenchmarkResult(
                task_id=rep_task_id,
                lane=task.lane.value if isinstance(task.lane, EvalLane) else str(task.lane),
                passed=passed,
                total_steps=total_steps,
                duration_ms=duration_ms,
                tokens_used=tokens_used,
                system1_steps=s1_steps,
                system2_steps=s2_steps,
                optimal_steps=task.optimal_steps,
                step_efficiency=step_efficiency,
                error_type=error_type,
                error_message=error_message,
                tier=task.tier.value if isinstance(task.tier, TaskTier) else str(task.tier),
                provenance={
                    "repetition": rep + 1,
                    "target_url": task.target_url,
                    "task_instruction": task.instruction,
                },
            )
            results.append(result)

        return results

    async def run_suite(
        self,
        tasks: Sequence[EvaluationTask],
        suite_id: str = "standard_v1",
        repetitions: int = 1,
        lane: Optional[EvalLane] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvaluationReport:
        """Executes a suite of evaluation tasks and compiles a complete EvaluationReport."""
        filtered_tasks = [t for t in tasks if lane is None or t.lane == lane]
        all_results: List[TaskBenchmarkResult] = []

        for task in filtered_tasks:
            task_res = await self.run_task(task=task, repetitions=repetitions)
            all_results.extend(task_res)

        scorecard = BenchmarkReporter.create_scorecard(
            suite_id=suite_id,
            results=all_results,
            model_configurations=self.model_configurations,
            hardware_specs=self.hardware_specs,
            metadata=metadata,
        )

        return EvaluationReport.from_scorecard(scorecard=scorecard, lane=lane)


def main() -> int:
    """CLI entry point for running evaluation suites."""
    parser = argparse.ArgumentParser(description="Reflex Benchmark Evaluation Runner")
    parser.add_argument("--suite", type=str, default="standard_v1", help="Suite identifier to run")
    parser.add_argument("--lane", type=str, default=None, help="EvalLane filter (e.g. browser_e2e, adversarial_safety)")
    parser.add_argument("--repetitions", type=int, default=1, help="Repetitions per task")
    parser.add_argument("--out", type=str, default=None, help="Output path for scorecard (.json or .md)")
    args = parser.parse_args()

    from reflex.evals.portfolio import get_standard_portfolio_tasks

    tasks = get_standard_portfolio_tasks()
    lane_enum = EvalLane(args.lane) if args.lane else None

    runner = EvaluationRunner()
    report = asyncio.run(
        runner.run_suite(
            tasks=tasks,
            suite_id=args.suite,
            repetitions=args.repetitions,
            lane=lane_enum,
        )
    )

    scorecard = report.to_scorecard()
    print(scorecard.to_markdown())

    if args.out:
        scorecard.save(args.out)
        print(f"\nSaved evaluation scorecard to: {args.out}")

    return 0 if scorecard.failed_tasks == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
