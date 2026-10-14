"""Deterministic and sandboxed evaluation gates for State Space Tree nodes."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sst.core.models import DeterministicGateResult, DomainMode, PayloadType, SSTNode


class SSTDeterministicEvaluator:
    """Evaluates SST nodes through deterministic gates (compilers, linters, sandboxes, sanity checks)."""

    def __init__(self, default_timeout_seconds: int = 120) -> None:
        self.default_timeout_seconds = default_timeout_seconds

    def evaluate(
        self,
        node: SSTNode,
        workspace_dir: Path | str,
        test_command: str | None = None,
        baseline_metrics: dict[str, float] | None = None,
    ) -> DeterministicGateResult:
        """Dispatches node evaluation according to domain mode."""
        ws = Path(workspace_dir)
        if node.domain == DomainMode.AUTOBUILD:
            return self.evaluate_code(node, ws, test_command)
        else:
            return self.evaluate_research(node, ws, baseline_metrics)

    def evaluate_code(
        self,
        node: SSTNode,
        workspace_dir: Path | str,
        test_command: str | None = None,
    ) -> DeterministicGateResult:
        """Evaluates a code node: AST parsing, isolated workspace patching, and test suite execution."""
        start_time = time.perf_counter()
        ws = Path(workspace_dir)

        # Step 1: Pre-flight Syntax / AST check (if content is python code rather than raw diff)
        is_diff = node.payload_type == PayloadType.CODE_DIFF and (
            node.content.startswith("--- ") or node.content.startswith("diff ") or "@@" in node.content
        )

        code_to_check = self._extract_code_content(node.content)

        if not is_diff and node.metadata.get("language", "python") == "python":
            try:
                ast.parse(code_to_check)
            except SyntaxError as e:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=1,
                    stdout="",
                    stderr=f"AST SyntaxError: {e}",
                    duration_seconds=time.perf_counter() - start_time,
                    failure_reason=f"SyntaxError in generated code at line {e.lineno}: {e.msg}",
                )

        # If no test command is provided, AST pass is sufficient for a standalone code unit
        if not test_command:
            return DeterministicGateResult(
                passed=True,
                exit_code=0,
                stdout="Syntax and structure check passed.",
                duration_seconds=time.perf_counter() - start_time,
                tests_passed=1,
            )

        # Step 2: Create ephemeral isolated workspace and apply patch/code
        with tempfile.TemporaryDirectory() as tmp_dir:
            isolated_ws = Path(tmp_dir) / "workspace"
            isolated_ws.mkdir(parents=True, exist_ok=True)

            if ws.exists() and ws.is_dir():
                self._copy_workspace(ws, isolated_ws)

            # Apply changes into isolated workspace
            patch_err = self._apply_payload(node, isolated_ws)
            if patch_err:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=1,
                    stderr=patch_err,
                    duration_seconds=time.perf_counter() - start_time,
                    failure_reason=f"Patch application failed: {patch_err}",
                )

            # Step 3: Run test suite in the patched isolated workspace
            env = {
                k: v
                for k, v in os.environ.items()
                if not any(
                    pat in k.upper()
                    for pat in ["KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL", "AWS_", "SSH_", "GH_"]
                )
            }
            env["AUTO_SANDBOX"] = "1"
            env["SST_SANDBOX"] = "1"
            current_bin = str(Path(sys.executable).parent)
            existing_path = env.get("PATH", "")
            if current_bin not in existing_path.split(os.pathsep):
                env["PATH"] = f"{current_bin}{os.pathsep}{existing_path}" if existing_path else current_bin

            try:
                res = subprocess.run(
                    test_command,
                    shell=True,
                    cwd=str(isolated_ws),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.default_timeout_seconds,
                )
                passed = res.returncode == 0
                tests_passed = 1 if passed else 0
                tests_failed = 0 if passed else 1

                # Extract pytest test count if present
                pass_match = re.search(r"(\d+)\s+passed", res.stdout)
                if pass_match:
                    tests_passed = int(pass_match.group(1))
                fail_match = re.search(r"(\d+)\s+failed", res.stdout)
                if fail_match:
                    tests_failed = int(fail_match.group(1))

                return DeterministicGateResult(
                    passed=passed,
                    exit_code=res.returncode,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    duration_seconds=time.perf_counter() - start_time,
                    tests_passed=tests_passed,
                    tests_failed=tests_failed,
                    failure_reason=None if passed else f"Test suite failed with exit code {res.returncode}",
                )
            except subprocess.TimeoutExpired:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=-1,
                    stderr="Test execution timed out in isolated sandbox",
                    duration_seconds=float(self.default_timeout_seconds),
                    failure_reason="Execution timed out in sandbox",
                )
            except Exception as e:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=-2,
                    stderr=str(e),
                    duration_seconds=time.perf_counter() - start_time,
                    failure_reason=f"Sandbox execution error: {e}",
                )

    def evaluate_research(
        self,
        node: SSTNode,
        workspace_dir: Path | str,
        baseline_metrics: dict[str, float] | None = None,
    ) -> DeterministicGateResult:
        """Evaluates a research experiment script: Sanity/Leakage checks and trial execution."""
        start_time = time.perf_counter()
        code_to_check = self._extract_code_content(node.content)

        # Step 1: AST check and Sanity/Leakage audit
        try:
            ast.parse(code_to_check)
        except SyntaxError as e:
            return DeterministicGateResult(
                passed=False,
                exit_code=1,
                stderr=f"Research script SyntaxError: {e}",
                duration_seconds=time.perf_counter() - start_time,
                failure_reason=f"Python SyntaxError at line {e.lineno}: {e.msg}",
            )

        # Sanity check: Disallow monkey-patching evaluation ground-truth or cheating
        forbidden_patterns = [
            "test_labels = train_labels",
            "test_data = train_data",
            "fit_transform(X_test)",
            "os.system('rm -rf",
            "shutil.rmtree",
        ]
        for pattern in forbidden_patterns:
            if pattern in code_to_check:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=2,
                    stderr=f"Forbidden pattern detected: {pattern}",
                    duration_seconds=time.perf_counter() - start_time,
                    failure_reason=f"Sanity gate failed: suspicious or cheating code pattern '{pattern}'",
                )

        # Step 2: Execute script in isolated temp directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            script_path = Path(tmp_dir) / "experiment_trial.py"
            script_path.write_text(code_to_check, encoding="utf-8")

            env = {
                k: v
                for k, v in os.environ.items()
                if not any(
                    pat in k.upper()
                    for pat in ["KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL", "AWS_", "SSH_", "GH_"]
                )
            }
            env["AUTO_SANDBOX"] = "1"
            env["SST_SANDBOX"] = "1"
            current_bin = str(Path(sys.executable).parent)
            existing_path = env.get("PATH", "")
            if current_bin not in existing_path.split(os.pathsep):
                env["PATH"] = f"{current_bin}{os.pathsep}{existing_path}" if existing_path else current_bin

            try:
                res = subprocess.run(
                    [sys.executable, str(script_path)],
                    cwd=tmp_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.default_timeout_seconds,
                )

                if res.returncode != 0:
                    return DeterministicGateResult(
                        passed=False,
                        exit_code=res.returncode,
                        stdout=res.stdout,
                        stderr=res.stderr,
                        duration_seconds=time.perf_counter() - start_time,
                        failure_reason=f"Experiment crashed with exit code {res.returncode}",
                    )

                # Parse JSON metrics from stdout
                metrics: dict[str, float] = {}
                for line in res.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            parsed = json.loads(line)
                            if isinstance(parsed, dict) and "metrics" in parsed:
                                metrics.update(parsed["metrics"])
                            elif isinstance(parsed, dict):
                                metrics.update(parsed)
                        except json.JSONDecodeError:
                            pass

                passed = True
                failure_reason = None
                if baseline_metrics and metrics:
                    primary_metric = str(node.metadata.get("primary_metric", "accuracy"))
                    if primary_metric in baseline_metrics and primary_metric in metrics:
                        delta = metrics[primary_metric] - baseline_metrics[primary_metric]
                        metrics["delta_vs_baseline"] = delta
                        if delta < 0 and node.metadata.get("require_improvement", False):
                            passed = False
                            failure_reason = f"Metric {primary_metric} regressed by {delta:.4f}"

                return DeterministicGateResult(
                    passed=passed,
                    exit_code=0,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    duration_seconds=time.perf_counter() - start_time,
                    metrics=metrics,
                    failure_reason=failure_reason,
                    tests_passed=1 if passed else 0,
                )

            except subprocess.TimeoutExpired:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=-1,
                    stderr="Experiment execution timed out",
                    duration_seconds=float(self.default_timeout_seconds),
                    failure_reason="Experiment exceeded runtime budget",
                )
            except Exception as e:
                return DeterministicGateResult(
                    passed=False,
                    exit_code=-2,
                    stderr=str(e),
                    duration_seconds=time.perf_counter() - start_time,
                    failure_reason=f"Experiment execution error: {e}",
                )

    def _copy_workspace(self, src: Path, dst: Path) -> None:
        """Copies workspace ignoring VCS and build caches."""
        ignore_patterns = shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".auto", ".sst", "*.pyc", "*.egg-info"
        )
        for item in src.iterdir():
            if item.name in {".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".auto", ".sst"}:
                continue
            target = dst / item.name
            if item.is_dir():
                shutil.copytree(item, target, ignore=ignore_patterns, dirs_exist_ok=True)
            elif item.is_file():
                shutil.copy2(item, target)

    def _apply_payload(self, node: SSTNode, workspace: Path) -> str | None:
        """Applies node code or diff to the isolated workspace."""
        content = node.content.strip()

        # 1. Target file specified in metadata
        target_file = node.metadata.get("target_file") or node.metadata.get("file_path")
        if target_file:
            clean_path = str(target_file).strip().lstrip("/\\")
            target_path = (workspace / clean_path).resolve()
            ws_resolved = workspace.resolve()
            if not target_path.is_relative_to(ws_resolved):
                return f"Path Traversal Violation: Target path '{target_file}' escapes workspace boundary."
            target_path.parent.mkdir(parents=True, exist_ok=True)
            code = self._extract_code_content(content)
            target_path.write_text(code, encoding="utf-8")
            return None

        # 2. Check if content is a Unified Diff
        if content.startswith("--- ") or content.startswith("diff ") or "@@" in content:
            patch_file = workspace / "_temp_patch.patch"
            patch_file.write_text(content, encoding="utf-8")
            git_err: str | None = None
            try:
                res = subprocess.run(
                    ["git", "apply", "--ignore-whitespace", str(patch_file)],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if res.returncode == 0:
                    return None
                git_err = res.stderr
            except Exception as e:
                git_err = str(e)
            finally:
                if patch_file.exists():
                    patch_file.unlink()

            # Fallback to manual hunk parser
            from sst.sandbox.custody import CandidateCustodyManager

            custody = CandidateCustodyManager()
            fallback_err = custody._apply_unified_diff_manually(content, workspace)
            if fallback_err is None:
                return None
            return f"Patch application failed: git apply ({git_err}) | fallback ({fallback_err})"

        # 3. Default fallback: Write to solution.py or root module
        code = self._extract_code_content(content)
        default_target = workspace / "solution.py"
        default_target.write_text(code, encoding="utf-8")
        return None

    def _extract_code_content(self, text: str) -> str:
        """Extracts python code from markdown code fences if wrapped."""
        text = text.strip()
        if "```python" in text:
            return text.split("```python", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            return text.split("```", 1)[1].split("```", 1)[0].strip()
        return text
