"""Evaluation Scorecard and Reporting Module for Reflex Benchmark Harness.

Generates standardized Markdown and JSON evaluation scorecards with complete
hardware provenance, model configurations, latency percentiles, step efficiency,
and token economics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
import platform
import statistics
import sys
from typing import Any, Dict, List, Optional, Sequence

from reflex.schemas.actions import ActionType, SafetyClass


def get_system_hardware_specs() -> Dict[str, str]:
    """Discovers host hardware and runtime specifications for provenance tracking."""
    specs = {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor() or "unknown_cpu",
        "cpu_count": str(os.cpu_count() or 1),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
    }
    # Optional chromium check
    chromium_path = os.environ.get("CHROMIUM_PATH", "")
    if chromium_path:
        specs["chromium_path"] = chromium_path
    return specs


@dataclass(frozen=True)
class TaskBenchmarkResult:
    """Standardized result record for an individual benchmark task run."""

    task_id: str
    lane: str  # EvalLane string value
    passed: bool
    total_steps: int
    duration_ms: float
    tokens_used: int = 0
    system1_steps: int = 0
    system2_steps: int = 0
    optimal_steps: int = 1
    step_efficiency: float = 1.0
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    tier: str = "custom"
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "lane": str(self.lane),
            "passed": self.passed,
            "total_steps": self.total_steps,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used,
            "system1_steps": self.system1_steps,
            "system2_steps": self.system2_steps,
            "optimal_steps": self.optimal_steps,
            "step_efficiency": self.step_efficiency,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "tier": self.tier,
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskBenchmarkResult:
        return cls(
            task_id=str(data["task_id"]),
            lane=str(data.get("lane", "browser_e2e")),
            passed=bool(data.get("passed", False)),
            total_steps=int(data.get("total_steps", 0)),
            duration_ms=float(data.get("duration_ms", 0.0)),
            tokens_used=int(data.get("tokens_used", 0)),
            system1_steps=int(data.get("system1_steps", 0)),
            system2_steps=int(data.get("system2_steps", 0)),
            optimal_steps=int(data.get("optimal_steps", 1)),
            step_efficiency=float(data.get("step_efficiency", 1.0)),
            error_type=data.get("error_type"),
            error_message=data.get("error_message"),
            tier=str(data.get("tier", "custom")),
            provenance=dict(data.get("provenance", {})),
        )


@dataclass(frozen=True)
class EvaluationScorecard:
    """Comprehensive benchmark evaluation scorecard for Reflex."""

    suite_id: str
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

    @classmethod
    def compute(
        cls,
        suite_id: str,
        results: Sequence[TaskBenchmarkResult],
        model_configurations: Optional[Dict[str, str]] = None,
        hardware_specs: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        baseline_tokens_per_task: int = 1500,
    ) -> EvaluationScorecard:
        """Constructs an EvaluationScorecard by computing statistics from task results."""
        hw = hardware_specs if hardware_specs is not None else get_system_hardware_specs()
        models = model_configurations or {"planner": "deterministic_rule_v1", "temperature": "0.0"}
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        sr = (passed / total) if total > 0 else 0.0

        durations = [r.duration_ms for r in results] if results else [0.0]
        median_lat = float(statistics.median(durations)) if durations else 0.0
        if len(durations) >= 20:
            # 95th percentile
            sorted_durations = sorted(durations)
            p95_idx = int(0.95 * len(sorted_durations))
            p95_lat = float(sorted_durations[min(p95_idx, len(sorted_durations) - 1)])
        else:
            p95_lat = float(max(durations)) if durations else 0.0

        step_efficiencies = [r.step_efficiency for r in results] if results else [1.0]
        mean_se = float(statistics.mean(step_efficiencies)) if step_efficiencies else 1.0

        total_tokens = sum(r.tokens_used for r in results)
        total_s1 = sum(r.system1_steps for r in results)
        total_s2 = sum(r.system2_steps for r in results)
        total_steps = total_s1 + total_s2
        s1_ratio = (total_s1 / total_steps) if total_steps > 0 else 0.0

        baseline_total = max(1, baseline_tokens_per_task * total)
        token_savings = max(0.0, 1.0 - (total_tokens / baseline_total))

        return cls(
            suite_id=suite_id,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            hardware_specs=hw,
            model_configurations=models,
            total_tasks=total,
            passed_tasks=passed,
            failed_tasks=failed,
            success_rate=sr,
            median_latency_ms=median_lat,
            p95_latency_ms=p95_lat,
            mean_step_efficiency=mean_se,
            total_tokens=total_tokens,
            system1_delegation_ratio=s1_ratio,
            token_savings_ratio=token_savings,
            task_results=list(results),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "timestamp_iso": self.timestamp_iso,
            "hardware_specs": dict(self.hardware_specs),
            "model_configurations": dict(self.model_configurations),
            "total_tasks": self.total_tasks,
            "passed_tasks": self.passed_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": self.success_rate,
            "median_latency_ms": self.median_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "mean_step_efficiency": self.mean_step_efficiency,
            "total_tokens": self.total_tokens,
            "system1_delegation_ratio": self.system1_delegation_ratio,
            "token_savings_ratio": self.token_savings_ratio,
            "task_results": [r.to_dict() for r in self.task_results],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvaluationScorecard:
        results = [TaskBenchmarkResult.from_dict(r) for r in data.get("task_results", [])]
        return cls(
            suite_id=str(data["suite_id"]),
            timestamp_iso=str(data.get("timestamp_iso", "")),
            hardware_specs=dict(data.get("hardware_specs", {})),
            model_configurations=dict(data.get("model_configurations", {})),
            total_tasks=int(data.get("total_tasks", len(results))),
            passed_tasks=int(data.get("passed_tasks", 0)),
            failed_tasks=int(data.get("failed_tasks", 0)),
            success_rate=float(data.get("success_rate", 0.0)),
            median_latency_ms=float(data.get("median_latency_ms", 0.0)),
            p95_latency_ms=float(data.get("p95_latency_ms", 0.0)),
            mean_step_efficiency=float(data.get("mean_step_efficiency", 1.0)),
            total_tokens=int(data.get("total_tokens", 0)),
            system1_delegation_ratio=float(data.get("system1_delegation_ratio", 0.0)),
            token_savings_ratio=float(data.get("token_savings_ratio", 0.0)),
            task_results=results,
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serializes scorecard to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Generates a professional Markdown scorecard table with scientific provenance."""
        lines: List[str] = [
            f"# Reflex Evaluation Scorecard: `{self.suite_id}`",
            "",
            f"> **Generated**: {self.timestamp_iso}  ",
            f"> **Tasks Evaluated**: {self.total_tasks}  ",
            f"> **Overall Success Rate**: {self.success_rate * 100:.1f}% ({self.passed_tasks}/{self.total_tasks})",
            "",
            "## 1. Executive Summary & Core Metrics",
            "",
            "| Metric | Value | Target / Benchmark Standard |",
            "| :--- | :--- | :--- |",
            f"| **Task Success Rate (SR)** | **{self.success_rate * 100:.1f}%** | 100% Binary Objective Completion |",
            f"| **Mean Step Efficiency (SE)** | **{self.mean_step_efficiency:.2f}x** | $\\ge 0.85$ of Optimal Step Count |",
            f"| **Median Latency ($p_{{50}}$)** | **{self.median_latency_ms:.1f} ms** | Sub-second Discrete Step Execution |",
            f"| **Tail Latency ($p_{{95}}$)** | **{self.p95_latency_ms:.1f} ms** | Bounded Settlement & Verification |",
            f"| **System-1 Delegation Ratio** | **{self.system1_delegation_ratio * 100:.1f}%** | Fast Motor Skill Routine Hit Rate |",
            f"| **Token Savings vs Baseline** | **{self.token_savings_ratio * 100:.1f}%** | $\\ge 70\\%$ LLM Token Expenditure Reduction |",
            f"| **Total Tokens Expended** | **{self.total_tokens} tokens** | Economically Bounded S2 Cognition |",
            "",
            "## 2. Hardware & Model Provenance",
            "",
            "### Hardware & OS Environment",
            "| Property | Value |",
            "| :--- | :--- |",
        ]

        for k, v in sorted(self.hardware_specs.items()):
            lines.append(f"| `{k}` | `{v}` |")

        lines.extend([
            "",
            "### Model & Cognition Configuration",
            "| Parameter | Configuration |",
            "| :--- | :--- |",
        ])

        for k, v in sorted(self.model_configurations.items()):
            lines.append(f"| `{k}` | `{v}` |")

        lines.extend([
            "",
            "## 3. Detailed Task Breakdown",
            "",
            "| Task ID | Tier / Lane | Status | Steps (Act/Opt) | SE Ratio | Latency | Tokens | Error Summary |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
        ])

        for r in self.task_results:
            status_icon = "PASS" if r.passed else "FAIL"
            err_str = f"`{r.error_type or 'None'}`" if not r.passed else "None"
            if r.error_message and not r.passed:
                err_str += f": {r.error_message[:40]}"
            lines.append(
                f"| `{r.task_id}` | `{r.tier}` | **{status_icon}** | {r.total_steps}/{r.optimal_steps} | "
                f"{r.step_efficiency:.2f} | {r.duration_ms:.1f}ms | {r.tokens_used} | {err_str} |"
            )

        lines.extend([
            "",
            "---",
            "*Report compiled autonomously by Reflex Evaluation Runner.*",
        ])

        return "\n".join(lines)

    def save(self, filepath: str) -> None:
        """Saves scorecard to JSON or Markdown depending on file extension."""
        directory = os.path.dirname(filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)
        if filepath.endswith(".json"):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.to_json())
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.to_markdown())


class BenchmarkReporter:
    """Helper service for aggregating, formatting, and persisting benchmark scorecards."""

    @staticmethod
    def create_scorecard(
        suite_id: str,
        results: Sequence[TaskBenchmarkResult],
        model_configurations: Optional[Dict[str, str]] = None,
        hardware_specs: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvaluationScorecard:
        return EvaluationScorecard.compute(
            suite_id=suite_id,
            results=results,
            model_configurations=model_configurations,
            hardware_specs=hardware_specs,
            metadata=metadata,
        )

    @staticmethod
    def render_markdown(scorecard: EvaluationScorecard) -> str:
        return scorecard.to_markdown()

    @staticmethod
    def render_json(scorecard: EvaluationScorecard, indent: int = 2) -> str:
        return scorecard.to_json(indent=indent)

    @staticmethod
    def write_artifacts(scorecard: EvaluationScorecard, base_path_without_ext: str) -> Dict[str, str]:
        """Writes both JSON and Markdown representations of the scorecard."""
        json_path = f"{base_path_without_ext}.json"
        md_path = f"{base_path_without_ext}.md"
        scorecard.save(json_path)
        scorecard.save(md_path)
        return {"json": json_path, "markdown": md_path}
