"""System 2 Model Providers and Pluggable LLM Client Interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

logger = logging.getLogger(__name__)

from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.state import CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.verifier import VerificationResult

if TYPE_CHECKING:
    from reflex.cognition.system2.planner import PlannedStep, System2PlannerPort
    from reflex.cognition.system2.recovery import RecoveryPlan


class LLMClientPort(ABC):
    """Abstract port for communicating with local or remote LLM / VLM backends."""

    @abstractmethod
    async def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """Sends a system and user prompt to the configured model and returns the response string."""
        ...


class MockLLMClient(LLMClientPort):
    """Deterministic, configurable mock LLM client for unit and integration testing."""

    def __init__(
        self,
        default_response: str = "",
        responses: Optional[Sequence[str]] = None,
        pattern_responses: Optional[Dict[str, str]] = None,
        custom_handler: Optional[Callable[[str, str], Union[str, Any]]] = None,
        delay_ms: float = 0.0,
    ) -> None:
        self.default_response: str = default_response
        self._responses_queue: List[str] = list(responses or [])
        self._pattern_responses: Dict[str, str] = dict(pattern_responses or {})
        self._custom_handler = custom_handler
        self.delay_ms: float = delay_ms
        self.call_history: List[Tuple[str, str]] = []

    def add_response(self, response: str) -> None:
        """Appends a response to the sequential FIFO queue."""
        self._responses_queue.append(response)

    def add_pattern_response(self, pattern: str, response: str) -> None:
        """Registers a response triggered when user_prompt matches pattern (substring or regex)."""
        self._pattern_responses[pattern] = response

    def set_custom_handler(
        self, handler: Callable[[str, str], Union[str, Any]]
    ) -> None:
        """Sets a dynamic custom callback handler."""
        self._custom_handler = handler

    def clear(self) -> None:
        """Clears queue and history."""
        self._responses_queue.clear()
        self._pattern_responses.clear()
        self.call_history.clear()

    async def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """Evaluates prompt against configured patterns, queue, or handlers."""
        self.call_history.append((system_prompt, user_prompt))

        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)

        # 1. Custom handler
        if self._custom_handler is not None:
            res = self._custom_handler(system_prompt, user_prompt)
            if asyncio.iscoroutine(res):
                return await res
            return str(res)

        # 2. Sequential queue
        if self._responses_queue:
            return self._responses_queue.pop(0)

        # 3. Pattern responses
        for pattern, response in self._pattern_responses.items():
            if pattern in user_prompt or re.search(pattern, user_prompt, re.IGNORECASE):
                return response

        # 4. Fallback default response
        return self.default_response


class DeterministicRulePlanner:
    """Deterministic, rule-based System 2 planner and recovery engine.
    
    Provides high-reliability fallback planning and fast local test execution
    without requiring foundation model inference.
    """

    def __init__(self) -> None:
        pass

    async def plan_next_step(
        self,
        task_goal: str,
        current_state: CanonicalUIGraph,
        history: Optional[List[Any]] = None,
    ) -> PlannedStep:
        """Proposes next deterministic action based on task goal and UI affordances."""
        from reflex.cognition.system2.planner import PlannedStep

        goal_lower = task_goal.strip().lower()
        nodes = current_state.nodes if current_state and current_state.nodes else {}
        vw, vh = current_state.viewport_size if current_state else (1920, 1080)

        # 1. Check for explicit navigation goal (e.g. navigate to https://..., go to https://..., open https://...)
        nav_match = re.search(r"(?:navigate(?:\s+to)?|go\s+to|open)\s+(https?://\S+|/\S+)", goal_lower)
        if nav_match:
            target_url = nav_match.group(1)
            action = TypedAction(
                action_type=ActionType.NAVIGATE,
                text_payload=target_url,
                safety_class=SafetyClass.REVERSIBLE,
                metadata={"reason": "deterministic_rule_nav"},
            )
            return PlannedStep(
                thought_reasoning=f"Navigating to destination URL: {target_url}",
                target_description=f"Destination URL {target_url}",
                action=action,
                expected_delta=StateDelta(
                    pixel_change_ratio=0.8,
                    outcome_class=OutcomeClass.NAVIGATION,
                ),
                confidence=1.0,
                subgoal=f"Navigate to {target_url}",
            )

        # 2. Check for typing goal (e.g. type 'hello' in search / enter email '...')
        type_match = re.search(r"(?:type|enter|input|write)\s+['\"]([^'\"]+)['\"]\s+(?:in|into|to)\s+(.+)", goal_lower)
        if type_match:
            payload = type_match.group(1)
            target_desc = type_match.group(2).strip().lower()

            # Find matching input node (exact label or substring)
            matched_node: Optional[UIStateNode] = None
            for node in nodes.values():
                if node.role == NodeRole.INPUT or node.is_editable:
                    if target_desc == node.label.lower() or target_desc == node.node_id.lower():
                        matched_node = node
                        break
            if not matched_node:
                for node in nodes.values():
                    if node.role == NodeRole.INPUT or node.is_editable:
                        if target_desc in node.label.lower() or target_desc in node.node_id.lower():
                            matched_node = node
                            break
            if not matched_node:
                for node in nodes.values():
                    if node.role == NodeRole.INPUT or node.is_editable:
                        matched_node = node
                        break

            if matched_node:
                cx, cy = matched_node.bounds.center
                coords = NormalizedCoords(x=round(cx / max(1, vw), 4), y=round(cy / max(1, vh), 4))
                action = TypedAction(
                    action_type=ActionType.TYPE,
                    target_node_id=matched_node.node_id,
                    target_label=matched_node.label,
                    coords=coords,
                    text_payload=payload,
                    safety_class=SafetyClass.REVERSIBLE,
                )
                return PlannedStep(
                    thought_reasoning=f"Entering text payload '{payload}' into input field '{matched_node.label or matched_node.node_id}'",
                    target_description=matched_node.label or matched_node.node_id,
                    action=action,
                    expected_delta=StateDelta(
                        modified_nodes=[matched_node.node_id],
                        pixel_change_ratio=0.05,
                        outcome_class=OutcomeClass.SUCCESS,
                    ),
                    confidence=0.95,
                    subgoal=f"Fill {matched_node.label or 'input'}",
                )

        # 3. Check for click goal (e.g. click button 'Submit' / click 'Search')
        click_match = re.search(r"(?:click|press|submit|select)\s+(?:button\s+|link\s+)?['\"]?([^'\"]+)['\"]?", goal_lower)
        if click_match:
            target_keyword = click_match.group(1).strip().lower()
            matched_node = None

            # Priority 1: Exact label/id match on button or link
            for node in nodes.values():
                if node.role in (NodeRole.BUTTON, NodeRole.LINK) or node.is_clickable:
                    if target_keyword == node.label.lower() or target_keyword == node.node_id.lower():
                        matched_node = node
                        break

            # Priority 2: Substring match on button or link
            if not matched_node:
                for node in nodes.values():
                    if node.role in (NodeRole.BUTTON, NodeRole.LINK) or node.is_clickable:
                        if target_keyword in node.label.lower() or target_keyword in node.node_id.lower():
                            matched_node = node
                            break

            # Priority 3: Any node matching exact label
            if not matched_node:
                for node in nodes.values():
                    if target_keyword == node.label.lower():
                        matched_node = node
                        break

            if matched_node:
                cx, cy = matched_node.bounds.center
                coords = NormalizedCoords(x=round(cx / max(1, vw), 4), y=round(cy / max(1, vh), 4))
                is_destructive = any(
                    kw in matched_node.label.lower()
                    for kw in ("delete", "remove", "drop", "terminate", "purchase", "pay")
                )
                safety = SafetyClass.DESTRUCTIVE if is_destructive else SafetyClass.REVERSIBLE
                action = TypedAction(
                    action_type=ActionType.CLICK,
                    target_node_id=matched_node.node_id,
                    target_label=matched_node.label,
                    coords=coords,
                    safety_class=safety,
                )
                return PlannedStep(
                    thought_reasoning=f"Clicking interactable target '{matched_node.label or matched_node.node_id}'",
                    target_description=matched_node.label or matched_node.node_id,
                    action=action,
                    expected_delta=StateDelta(
                        pixel_change_ratio=0.15,
                        outcome_class=OutcomeClass.SUCCESS,
                    ),
                    confidence=0.95,
                    subgoal=f"Click {matched_node.label or 'element'}",
                )

        # 4. Default fallback: NOOP or wait
        return PlannedStep(
            thought_reasoning="No direct rule match found; proposing observation step",
            target_description="Current UI Viewport",
            action=TypedAction(
                action_type=ActionType.WAIT,
                safety_class=SafetyClass.REVERSIBLE,
            ),
            expected_delta=StateDelta(
                outcome_class=OutcomeClass.SUCCESS,
            ),
            confidence=0.5,
            subgoal="Observe UI state",
        )

    async def plan_recovery(
        self,
        task_goal: str,
        failed_state: CanonicalUIGraph,
        failed_action: TypedAction,
        verification_result: VerificationResult,
    ) -> RecoveryPlan:
        """Emits deterministic recovery plan without blind retry."""
        from reflex.cognition.system2.recovery import AbductiveRecoveryEngine

        engine = AbductiveRecoveryEngine()
        return await engine.diagnose_and_recover(
            task_goal=task_goal,
            failed_state=failed_state,
            failed_action=failed_action,
            verification_result=verification_result,
        )


class OllamaLLMClient(LLMClientPort):
    """Local Ollama-backed LLM / VLM client for System 2 planning.
    
    Supports local models such as Holo 3.1 9B, Llama 3.1, or Qwen2.5.
    Connects to local Ollama server (default http://localhost:11434).
    Features native structured JSON mode, timeouts, retries, and fallback handler.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        seed: Optional[int] = None,
        format: Optional[str] = "json",
        timeout_sec: float = 60.0,
        max_retries: int = 2,
        fallback_client: Optional[LLMClientPort] = None,
        http_client: Optional[Any] = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", "holo3.1:9b")
        self.temperature = temperature
        self.seed = seed
        self.format = format
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.fallback_client = fallback_client
        self._external_client = http_client

    async def _get_client(self) -> Any:
        if self._external_client is not None:
            return self._external_client
        if httpx is None:
            raise RuntimeError("httpx package is required for OllamaLLMClient but not installed")
        return httpx.AsyncClient(timeout=self.timeout_sec)

    async def check_health(self) -> bool:
        """Pings Ollama server to verify availability."""
        try:
            client = await self._get_client()
            should_close = self._external_client is None
            try:
                resp = await client.get(f"{self.base_url}/api/version")
                return resp.status_code == 200
            finally:
                if should_close:
                    await client.aclose()
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Lists locally available models in Ollama."""
        try:
            client = await self._get_client()
            should_close = self._external_client is None
            try:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    return [m.get("name", "") for m in data.get("models", [])]
            finally:
                if should_close:
                    await client.aclose()
        except Exception:
            pass
        return []

    async def is_model_available(self, model_name: Optional[str] = None) -> bool:
        """Checks if the configured model is installed locally in Ollama."""
        target = (model_name or self.model).lower()
        models = [m.lower() for m in await self.list_models()]
        return any(target == m or target in m or m.startswith(target) for m in models)

    async def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """Sends inference request to Ollama /api/generate with system prompt and JSON format."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
            },
        }
        if self.seed is not None:
            payload["options"]["seed"] = self.seed
        if self.format:
            payload["format"] = self.format

        client = await self._get_client()
        should_close = self._external_client is None
        attempts = 0
        last_error: Optional[Exception] = None

        try:
            while attempts <= self.max_retries:
                try:
                    resp = await client.post(
                        f"{self.base_url}/api/generate",
                        json=payload,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        response_text = data.get("response", "")
                        if response_text:
                            return response_text
                        last_error = ValueError("Ollama returned empty response string")
                    else:
                        last_error = RuntimeError(f"Ollama HTTP {resp.status_code}: {resp.text}")

                    logger.warning(
                        "Ollama returned non-200 or empty response: %s: %s",
                        resp.status_code,
                        resp.text,
                    )
                    # Non-transient client errors: fail fast to avoid unnecessary backoff
                    if resp.status_code in (400, 401, 403, 404):
                        break
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "Ollama request error on attempt %d: %s", attempts + 1, e
                    )

                attempts += 1
                if attempts <= self.max_retries:
                    await asyncio.sleep(0.5 * attempts)
        finally:
            if should_close:
                await client.aclose()

        # If fallback client is configured, fall back to it
        if self.fallback_client is not None:
            logger.info("Ollama unavailable; delegating to fallback LLM client")
            return await self.fallback_client.generate_response(system_prompt, user_prompt)

        raise ConnectionError(
            f"Failed to communicate with Ollama model '{self.model}' at {self.base_url} "
            f"after {self.max_retries + 1} attempts: {last_error}. Ensure Ollama is running (`ollama serve`)."
        )


class HoloOllamaProvider(OllamaLLMClient):
    """Specialized Ollama client pre-configured for Holo 3.1 9B execution.
    
    Optimized for 8GB VRAM / 32GB RAM local environments.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "holo3.1:9b",
        temperature: float = 0.1,
        seed: Optional[int] = None,
        format: Optional[str] = "json",
        timeout_sec: float = 60.0,
        max_retries: int = 2,
        fallback_client: Optional[LLMClientPort] = None,
        http_client: Optional[Any] = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            temperature=temperature,
            seed=seed,
            format=format,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
            fallback_client=fallback_client,
            http_client=http_client,
        )
