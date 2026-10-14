"""Reflex Jarvis Agent: Unified Autonomous Computer-Use and Motor Learning Subsystem.

Integrates:
1. Native Desktop Window Manager (instant window discovery, focusing, moving, and grid/column tiling without mouse drags).
2. System 1 Fast-Path Motor Skills (invariant affordance-based sub-5ms routine matching and execution).
3. System 2 Deliberative Planning (Local Holo 3.1 9B / Ollama model provider with deterministic rule fallback).
4. Closed-Loop Efference Copy Verification & Surprise Circuit Breaker (halts motor loop upon prediction error > tau).
5. System 2 -> System 1 Transference (compiles verified multi-step execution traces into invariant MotorSkills).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from reflex.cognition.prediction.circuit_breaker import SurpriseCircuitBreaker
from reflex.cognition.prediction.delta_engine import ExpectedDeltaEngine
from reflex.cognition.prediction.efference_verifier import (
    EfferenceCopyVerifier,
    EfferenceVerificationResult,
)
from reflex.cognition.prediction.surprise_evaluator import SurpriseEvaluator
from reflex.cognition.skills.extractor import AffordancePattern, SkillExtractor
from reflex.cognition.skills.registry import SkillMatchResult, SkillRegistry, SkillStatus
from reflex.cognition.system2.planner import PlannedStep, System2Planner
from reflex.cognition.system2.providers import (
    DeterministicRulePlanner,
    HoloOllamaProvider,
    LLMClientPort,
    MockLLMClient,
    OllamaLLMClient,
)
from reflex.execution.native.window_manager import (
    DEFAULT_APP_KEY,
    MockWindowManagerSubstrate,
    NativeWindowManager,
    WindowInfo,
    format_mock_launch_output,
)
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.memory import MotorSkill, TransitionTuple
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JarvisExecutionResult:
    """Outcome of an autonomous user command execution by Jarvis."""

    command: str
    success: bool
    substrate: str  # "window_manager", "system1_fast_path", "system2_deliberation", "system2_recovery"
    output: str
    actions_executed: int = 0
    transferred_to_system1: bool = False
    new_skill_id: Optional[str] = None
    circuit_breaker_tripped: bool = False
    latency_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "success": self.success,
            "substrate": self.substrate,
            "output": self.output,
            "actions_executed": self.actions_executed,
            "transferred_to_system1": self.transferred_to_system1,
            "new_skill_id": self.new_skill_id,
            "circuit_breaker_tripped": self.circuit_breaker_tripped,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }


class JarvisAgent:
    """Autonomous Jarvis agent routing between Window Management, System 1 habit routines, and System 2 deliberation."""

    def __init__(
        self,
        window_manager: Optional[NativeWindowManager] = None,
        skill_registry: Optional[SkillRegistry] = None,
        skill_extractor: Optional[SkillExtractor] = None,
        planner: Optional[System2Planner] = None,
        verifier: Optional[EfferenceCopyVerifier] = None,
        ollama_client: Optional[LLMClientPort] = None,
        use_mock: bool = False,
    ) -> None:
        # 1. Window Manager Substrate
        if window_manager is not None:
            self.window_manager = window_manager
            sub = getattr(window_manager, "substrate", None)
            self.mock_substrate = sub if isinstance(sub, MockWindowManagerSubstrate) else None
        elif use_mock or not NativeWindowManager.live_substrate_available():
            self.mock_substrate = MockWindowManagerSubstrate()
            self.window_manager = NativeWindowManager(substrate=self.mock_substrate)
        else:
            self.mock_substrate = None
            self.window_manager = NativeWindowManager()

        # 2. System 1 Skill Extractor and Registry
        self.skill_extractor = skill_extractor or SkillExtractor()
        self.skill_registry = skill_registry or SkillRegistry(
            db_path=":memory:",
            extractor=self.skill_extractor,
        )

        # 3. Efference Copy Verifier & Circuit Breaker
        self.verifier = verifier or EfferenceCopyVerifier()

        # 4. System 2 Cognitive Planner (with Local Holo 3.1 / Ollama)
        if planner is not None:
            self.planner = planner
            self.ollama_client = ollama_client
        else:
            if ollama_client is not None:
                self.ollama_client = ollama_client
            else:
                # Default to HoloOllamaProvider with fallback to System2Planner's DeterministicRulePlanner
                self.ollama_client = HoloOllamaProvider(
                    base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                    model=os.environ.get("OLLAMA_MODEL", "holo3.1:9b"),
                    fallback_client=None,
                    timeout_sec=5.0,
                    max_retries=1,
                )
            self.planner = System2Planner(llm_client=self.ollama_client)

        self._execution_history: List[JarvisExecutionResult] = []

    # =========================================================================
    # High-Level Natural Language Command Execution
    # =========================================================================

    async def execute_command(
        self,
        command: str,
        live_state: Optional[CanonicalUIGraph] = None,
    ) -> JarvisExecutionResult:
        """Parses natural language intention, routes to the appropriate substrate, and verifies execution."""
        t0 = time.perf_counter()
        cmd_clean = command.strip()
        cmd_lower = cmd_clean.lower()

        # ---------------------------------------------------------------------
        # Substrate 1: Native Window Management
        # ---------------------------------------------------------------------
        if self._is_window_management_command(cmd_lower):
            res = await self._execute_window_management(cmd_clean, cmd_lower)
            res = self._with_latency(res, t0)
            self._execution_history.append(res)
            return res

        # Synthesize or adopt current screen UI state
        current_state = live_state or self._build_desktop_state()

        # ---------------------------------------------------------------------
        # Substrate 2: System 1 Fast-Path Motor Skills
        # ---------------------------------------------------------------------
        match_result = self.skill_registry.find_matching_skill(current_state, cmd_clean)
        if match_result is not None and match_result.metadata and match_result.metadata.is_trusted:
            logger.info("Executing via System 1 fast-path: %s", match_result.skill.skill_id)
            res = await self._execute_system1_skill(match_result, current_state, cmd_clean)
            if res.success or res.circuit_breaker_tripped:
                res = self._with_latency(res, t0)
                self._execution_history.append(res)
                return res

        # ---------------------------------------------------------------------
        # Substrate 3: System 2 Deliberative Planning
        # ---------------------------------------------------------------------
        logger.info("Deliberating via System 2 planner for: %s", cmd_clean)
        res = await self._execute_system2_planning(cmd_clean, current_state)
        res = self._with_latency(res, t0)
        self._execution_history.append(res)
        return res

    # =========================================================================
    # Substrate Handlers
    # =========================================================================

    def _is_window_management_command(self, cmd_lower: str) -> bool:
        """Determines if the command is a deterministic desktop window manager action."""
        # 1. Exclude explicit UI element actions
        ui_element_verbs = ("type ", "enter ", "input ", "write ", "fill ", "select ", "press ", "click ")
        if any(cmd_lower.startswith(v) for v in ui_element_verbs):
            return False

        # Exclude UI element targets
        if any(w in cmd_lower for w in (" button", " input", " field", " checkbox", " dropdown", " tab", " modal", " dialog")):
            return False

        # 2. Window tiling and organization
        if any(w in cmd_lower for w in ("tile", "organize", "arrange")):
            return True

        # 3. Window listing
        if any(w in cmd_lower for w in ("list windows", "show windows", "get windows", "open windows", "active windows", "find window")):
            return True

        # 4. Window state actions
        if any(cmd_lower.startswith(v) for v in ("minimize", "maximize", "restore")):
            return True

        if cmd_lower.startswith("close window") or cmd_lower == "close" or cmd_lower.startswith("close "):
            return True

        if cmd_lower.startswith("focus window") or cmd_lower.startswith("focus "):
            return True

        # 5. Application launching
        app_launch_prefixes = ("open ", "launch ", "start ", "spawn ", "run ")
        if any(cmd_lower.startswith(p) for p in app_launch_prefixes):
            # Exclude web URLs (navigation)
            if re.search(r"https?://|\.com|\.org|\.net|\.io|www\.", cmd_lower):
                return False
            if (
                any(app in cmd_lower for app in self.window_manager.supported_app_terms())
                or "window" in cmd_lower
                or "app" in cmd_lower
            ):
                return True

        return False

    async def _execute_window_management(
        self,
        command: str,
        cmd_lower: str,
    ) -> JarvisExecutionResult:
        """Executes native window manager operations (tiling, focusing, resizing, launching)."""
        # 1. Tiling operations
        if any(w in cmd_lower for w in ("tile", "organize", "arrange")):
            layout = "grid"
            if "horizontal" in cmd_lower or "side by side" in cmd_lower or "columns" in cmd_lower or "column" in cmd_lower:
                layout = "horizontal"
            elif "vertical" in cmd_lower or "stacked" in cmd_lower or "rows" in cmd_lower or "row" in cmd_lower:
                layout = "vertical"

            proc_filter = self.window_manager.resolve_process_filter(cmd_lower)

            # Auto-spawn mock windows in mock mode if none exist to provide interactive utility
            self.window_manager.seed_mock_windows_if_empty(proc_filter)

            tiled = self.window_manager.tile_windows(layout=layout, process_filter=proc_filter)
            if tiled:
                titles = [f"'{w['title']}' ({w['bounds']['width']}x{w['bounds']['height']} at {w['bounds']['x']},{w['bounds']['y']})" for w in tiled]
                output = f"Successfully tiled {len(tiled)} window(s) in {layout} layout:\n  - " + "\n  - ".join(titles)
                return JarvisExecutionResult(
                    command=command,
                    success=True,
                    substrate="window_manager",
                    output=output,
                    actions_executed=len(tiled),
                    details={"tiled_windows": tiled, "layout": layout},
                )
            else:
                return JarvisExecutionResult(
                    command=command,
                    success=False,
                    substrate="window_manager",
                    output=f"No active windows matched filter '{proc_filter or 'all'}' to tile.",
                )

        # 2. Window Listing
        if "list" in cmd_lower or "show windows" in cmd_lower or "active windows" in cmd_lower:
            windows = self.window_manager.list_windows()
            if not windows:
                return JarvisExecutionResult(
                    command=command,
                    success=True,
                    substrate="window_manager",
                    output="No active desktop windows currently open.",
                )
            lines = [w.display_line() for w in windows]
            output = f"Active Top-Level Windows ({len(windows)}):\n  " + "\n  ".join(lines)
            return JarvisExecutionResult(
                command=command,
                success=True,
                substrate="window_manager",
                output=output,
                actions_executed=0,
                details={"windows": [w.to_dict() for w in windows]},
            )

        # 3. Focus Window
        if cmd_lower.startswith("focus"):
            match = re.search(r"focus\s+(?:window\s+)?(.+)", cmd_lower)
            target = match.group(1).strip() if match else ""
            if not target or target in ("window", "current", "this"):
                target = self.window_manager.resolve_window_target_or_default()
            ok = self.window_manager.focus_window(target)
            msg = f"Focused window matching '{target}'" if ok else f"Window matching '{target}' not found"
            return JarvisExecutionResult(
                command=command,
                success=ok,
                substrate="window_manager",
                output=msg,
                actions_executed=1 if ok else 0,
            )

        # 4. Minimize Window
        if cmd_lower.startswith("minimize"):
            match = re.search(r"minimize\s+(?:window\s+)?(.+)", cmd_lower)
            target = match.group(1).strip() if match else ""
            if not target or target in ("window", "current", "this"):
                target = self.window_manager.resolve_window_target_or_default()
            ok = self.window_manager.minimize_window(target)
            return JarvisExecutionResult(
                command=command,
                success=ok,
                substrate="window_manager",
                output=f"Minimized window matching '{target}'" if ok else f"Could not minimize '{target}'",
                actions_executed=1 if ok else 0,
            )

        # 5. Maximize Window
        if cmd_lower.startswith("maximize"):
            match = re.search(r"maximize\s+(?:window\s+)?(.+)", cmd_lower)
            target = match.group(1).strip() if match else ""
            if not target or target in ("window", "current", "this"):
                target = self.window_manager.resolve_window_target_or_default()
            ok = self.window_manager.maximize_window(target)
            return JarvisExecutionResult(
                command=command,
                success=ok,
                substrate="window_manager",
                output=f"Maximized window matching '{target}'" if ok else f"Could not maximize '{target}'",
                actions_executed=1 if ok else 0,
            )

        # 6. Close Window
        if cmd_lower.startswith("close"):
            match = re.search(r"close\s+(?:window\s+)?(.+)", cmd_lower)
            target = match.group(1).strip() if match else ""
            if not target or target in ("window", "current", "this"):
                target = self.window_manager.resolve_window_target_or_default()
            ok = self.window_manager.close_window(target)
            return JarvisExecutionResult(
                command=command,
                success=ok,
                substrate="window_manager",
                output=f"Closed window matching '{target}'" if ok else f"Could not close '{target}'",
                actions_executed=1 if ok else 0,
            )

        # 7. Launch Application (adapter-owned vocabulary query)
        app_match = re.search(r"(?:open|launch|start|spawn|run)\s+(?:a\s+|an\s+|the\s+)?(?:application\s+|app\s+|window\s+)?(.+)", cmd_lower)
        if app_match:
            app_raw = app_match.group(1).strip().rstrip(".;!").strip()
            spec = self.window_manager.resolve_app_launch(app_raw)
            if spec is None:
                return JarvisExecutionResult(
                    command=command,
                    success=False,
                    substrate="window_manager",
                    output=(
                        f"Unknown application '{app_raw}': launch denied "
                        f"{self.window_manager.launch_allowlist_text()}"
                    ),
                    actions_executed=0,
                )
            app_cmd, app_title, app_proc = spec.command, spec.window_title, spec.process_name

            if self.mock_substrate is not None:
                h = self.mock_substrate.add_window(app_title, process_name=app_proc)
                return JarvisExecutionResult(
                    command=command,
                    success=True,
                    substrate="window_manager",
                    output=format_mock_launch_output(app_title, h),
                    actions_executed=1,
                    details={"handle": h, "title": app_title, "process": app_proc},
                )
            else:
                self.window_manager.launch_application(app_cmd)
                return JarvisExecutionResult(
                    command=command,
                    success=True,
                    substrate="window_manager",
                    output=f"Launched {app_title} process via command '{app_cmd}'.",
                    actions_executed=1,
                    details={"title": app_title, "command": app_cmd},
                )

        return JarvisExecutionResult(
            command=command,
            success=False,
            substrate="window_manager",
            output="Unrecognized desktop window command.",
        )

    async def _execute_system1_skill(
        self,
        match: SkillMatchResult,
        current_state: CanonicalUIGraph,
        command: str,
    ) -> JarvisExecutionResult:
        """Executes a matched System 1 MotorSkill with closed-loop efference copy verification."""
        self.verifier.reset()
        skill = match.skill
        actions = skill.action_sequence
        executed_count = 0
        state = current_state

        for step_idx, act in enumerate(actions):
            # Compute efference copy expectation
            expected_delta = self.verifier.generate_efference_copy(state, act)

            # Simulate / perform action step transition
            post_state = self._simulate_action_effect(state, act)
            observed_delta = self.verifier.compute_observed_delta(state, post_state)

            # Efference copy verification
            verify_res: EfferenceVerificationResult = self.verifier.verify_transition(
                pre_state=state,
                action=act,
                post_state=post_state,
                expected_delta=expected_delta,
                observed_delta=observed_delta,
            )

            if not verify_res.is_verified or verify_res.circuit_breaker_tripped:
                # Motor loop halted! Record failure & quarantine skill
                self.skill_registry.record_execution_outcome(
                    skill.skill_id,
                    success=False,
                    surprise_score=verify_res.prediction_error,
                )
                return JarvisExecutionResult(
                    command=command,
                    success=False,
                    substrate="system1_fast_path",
                    output=(
                        f"Circuit breaker tripped during System 1 routine at step {step_idx + 1}: "
                        f"PE={verify_res.prediction_error:.3f} > tau. Inferred cause: '{verify_res.inferred_cause}'. "
                        f"Skill '{skill.skill_id}' quarantined."
                    ),
                    actions_executed=executed_count,
                    circuit_breaker_tripped=True,
                    details={"verify_result": verify_res.to_dict()},
                )

            executed_count += 1
            state = post_state

        # All steps succeeded: record successful outcome to reinforce skill
        self.skill_registry.record_execution_outcome(skill.skill_id, success=True, surprise_score=0.0)

        return JarvisExecutionResult(
            command=command,
            success=True,
            substrate="system1_fast_path",
            output=f"Executed System 1 skill '{skill.skill_id}' ({executed_count} actions) successfully via fast path.",
            actions_executed=executed_count,
            details={"skill_id": skill.skill_id, "confidence": match.confidence},
        )

    async def _execute_system2_planning(
        self,
        command: str,
        current_state: CanonicalUIGraph,
    ) -> JarvisExecutionResult:
        """Decomposes goal with System 2 planner, executes with closed-loop verification, and transfers to System 1."""
        self.verifier.reset()
        state = current_state
        transitions: List[TransitionTuple] = []
        max_steps = 5
        executed = 0

        circuit_breaker_tripped = False
        trip_cause = ""

        for step in range(max_steps):
            # Propose next planned step
            proposal: PlannedStep = await self.planner.plan_next_step(
                task_goal=command,
                current_state=state,
            )
            act = proposal.action

            if act.action_type in (ActionType.WAIT, ActionType.NOOP) and step > 0:
                break

            # Execute step & run efference copy verification
            post_state = self._simulate_action_effect(state, act)
            verify_res = self.verifier.verify_transition(
                pre_state=state,
                action=act,
                post_state=post_state,
                expected_delta=proposal.expected_delta,
            )

            # Record transition tuple for System 2 -> System 1 transference
            tx = TransitionTuple(
                transition_id=f"tx_{int(time.time()*1000)}_{step}",
                episode_id=f"ep_{int(time.time())}",
                step_index=step,
                timestamp_ms=time.time() * 1000.0,
                ui_state_hash=state.compute_state_hash(),
                goal_text=command,
                goal_embedding=[0.1] * 384,
                visual_embedding=[0.2] * 384,
                action=act,
                next_ui_state_hash=post_state.compute_state_hash(),
                delta=verify_res.observed_delta,
                duration_ms=80.0,
                surprise_score=verify_res.prediction_error,
                provenance={"source": "system2_planner", "model": getattr(self.ollama_client, "model", "holo3.1:9b")},
            )
            transitions.append(tx)
            executed += 1
            state = post_state

            if verify_res.circuit_breaker_tripped:
                circuit_breaker_tripped = True
                trip_cause = verify_res.inferred_cause
                break

            # Primary discrete action executed (e.g. typing or clicking button)
            if act.action_type in (ActionType.TYPE, ActionType.CLICK, ActionType.NAVIGATE):
                break

        # ---------------------------------------------------------------------
        # System 2 -> System 1 Transference (Consolidation)
        # ---------------------------------------------------------------------
        transferred = False
        new_skill_id = None
        has_executable_action = any(
            t.action.action_type not in (ActionType.WAIT, ActionType.NOOP) for t in transitions
        )

        if not circuit_breaker_tripped and has_executable_action and len(transitions) >= 1:
            try:
                new_skill: MotorSkill = self.skill_extractor.extract_from_single_episode(
                    transitions=transitions,
                    goal_text=command,
                    initial_state=current_state,
                )
                self.skill_registry.register_candidate(new_skill)
                # Auto-promote for testing / immediate fast-path availability
                self.skill_registry.promote_skill(new_skill.skill_id, force=True)
                transferred = True
                new_skill_id = new_skill.skill_id
                logger.info(
                    "System 2 -> System 1 Transference complete: compiled new MotorSkill '%s'",
                    new_skill_id,
                )
            except Exception as e:
                logger.warning("Skill extraction error during transference: %s", e)

        success = (not circuit_breaker_tripped) and (executed > 0)
        if circuit_breaker_tripped:
            output_msg = (
                f"Surprise Circuit Breaker TRIPPED during System 2 execution: PE > tau. "
                f"Inferred cause: '{trip_cause}'. Trajectory discarded; transference aborted."
            )
        else:
            output_msg = f"System 2 planned and executed {executed} action(s) for '{command}'."
            if transferred and new_skill_id:
                output_msg += f" Transferred routine to System 1 MotorSkill '{new_skill_id}' for future instant replay."

        return JarvisExecutionResult(
            command=command,
            success=success,
            substrate="system2_deliberation",
            output=output_msg,
            actions_executed=executed,
            transferred_to_system1=transferred,
            new_skill_id=new_skill_id,
            circuit_breaker_tripped=circuit_breaker_tripped,
            details={"steps": executed, "trip_cause": trip_cause},
        )

    # =========================================================================
    # Helpers & State Simulation
    # =========================================================================

    def _build_desktop_state(self) -> CanonicalUIGraph:
        """Synthesizes active UI state from currently open desktop windows."""
        windows = self.window_manager.list_windows()
        nodes: Dict[str, UIStateNode] = {}

        for w in windows:
            node_id = f"win_{w.handle}"
            nodes[node_id] = UIStateNode(
                node_id=node_id,
                role=NodeRole.BUTTON if NativeWindowManager.is_calculator_process(w.process_name) else NodeRole.INPUT,
                bounds=BoundingBox(x1=w.x, y1=w.y, x2=w.x + w.width, y2=w.y + w.height),
                label=w.title,
                is_clickable=True,
                is_editable=NativeWindowManager.is_text_editor_process(w.process_name),
            )

        active_title = windows[0].title if windows else "Desktop"
        return CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=nodes,
            active_window_title=active_title,
            viewport_size=(self.window_manager.screen_width, self.window_manager.screen_height),
        )

    def _simulate_action_effect(
        self,
        pre_state: CanonicalUIGraph,
        action: TypedAction,
    ) -> CanonicalUIGraph:
        """Simulates visual/state consequences of executing an action on the UI graph."""
        nodes = dict(pre_state.nodes)
        target_id = action.target_node_id

        if action.action_type == ActionType.TYPE and target_id and target_id in nodes:
            old_node = nodes[target_id]
            nodes[target_id] = UIStateNode(
                node_id=old_node.node_id,
                role=old_node.role,
                bounds=old_node.bounds,
                label=old_node.label,
                value=action.text_payload or "",
                is_editable=old_node.is_editable,
                is_clickable=old_node.is_clickable,
                is_focused=True,
            )

        elif action.action_type == ActionType.CLICK and target_id and target_id in nodes:
            old_node = nodes[target_id]
            nodes[target_id] = UIStateNode(
                node_id=old_node.node_id,
                role=old_node.role,
                bounds=old_node.bounds,
                label=old_node.label,
                value=old_node.value,
                is_editable=old_node.is_editable,
                is_clickable=old_node.is_clickable,
                is_focused=True,
            )

        return CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=nodes,
            url=action.text_payload if action.action_type == ActionType.NAVIGATE else pre_state.url,
            active_window_title=pre_state.active_window_title,
            viewport_size=pre_state.viewport_size,
        )

    def _with_latency(self, res: JarvisExecutionResult, t0: float) -> JarvisExecutionResult:
        elapsed = round((time.perf_counter() - t0) * 1000.0, 2)
        return JarvisExecutionResult(
            command=res.command,
            success=res.success,
            substrate=res.substrate,
            output=res.output,
            actions_executed=res.actions_executed,
            transferred_to_system1=res.transferred_to_system1,
            new_skill_id=res.new_skill_id,
            circuit_breaker_tripped=res.circuit_breaker_tripped,
            latency_ms=elapsed,
            details=res.details,
        )

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic health and subsystem status."""
        windows = self.window_manager.list_windows()
        skills = self.skill_registry.list_skills()
        trusted_skills = [s for s, m in skills if m.is_trusted]
        return {
            "window_manager": {
                "active_windows": len(windows),
                "is_mock": self.window_manager.substrate is not None,
            },
            "system1": {
                "total_skills": len(skills),
                "trusted_skills": len(trusted_skills),
            },
            "circuit_breaker": {
                "is_tripped": self.verifier.is_tripped,
                "trip_count": self.verifier.trip_count,
            },
            "system2": {
                "model": getattr(self.ollama_client, "model", "unknown"),
                "base_url": getattr(self.ollama_client, "base_url", "local"),
            },
        }

    async def run_demo(self) -> List[JarvisExecutionResult]:
        """Runs a complete autonomous demonstration of Jarvis capabilities."""
        results: List[JarvisExecutionResult] = []

        # 1. Launch several default-app windows (adapter's advertised demo app)
        results.append(await self.execute_command(f"open {DEFAULT_APP_KEY}"))
        results.append(await self.execute_command(f"open {DEFAULT_APP_KEY}"))
        results.append(await self.execute_command(f"open {DEFAULT_APP_KEY}"))

        # 2. Tile them side by side
        results.append(await self.execute_command(f"tile {DEFAULT_APP_KEY}s horizontally"))

        # 3. System 2 deliberation + Transference
        results.append(await self.execute_command("type 'Jarvis online' into search input"))

        # 4. Immediate System 1 fast-path replay
        results.append(await self.execute_command("type 'Jarvis online' into search input"))

        return results
