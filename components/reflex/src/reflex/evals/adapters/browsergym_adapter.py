"""BrowserGym and AgentLab Benchmark Adapter for Reflex.

Provides seamless bidirectional translation between BrowserGym/AgentLab environment
interfaces and Reflex's CanonicalUIGraph, TypedAction, and HostControlKernel.
Enables Reflex to evaluate on WebArena, MiniWoB++, WorkArena, and VisualWebArena benchmarks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from reflex.host.identity.lease_manager import ActionLeaseManager
from reflex.host.kernel.host_kernel import HostControlKernel
from reflex.host.policy.capability_engine import CapabilityPolicyEngine
from reflex.ports.clock import SystemClock
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityPolicy, CapabilityScope
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class FakeBrowserGymEnv:
    """Deterministic local fake environment simulating a BrowserGym / AgentLab gym interface."""

    def __init__(
        self,
        task_id: str = "browsergym_task_01",
        goal: str = "Submit contact form with name and email",
        initial_url: str = "http://localhost:8000/contact",
    ) -> None:
        self.task_id = task_id
        self.goal = goal
        self.url = initial_url
        self.step_count = 0
        self.is_terminated = False
        self.is_truncated = False
        self.last_action: Optional[str] = None
        self.elements: Dict[str, Dict[str, Any]] = {
            "1": {"tag": "input", "role": "textbox", "name": "Name", "value": "", "bbox": [10, 10, 200, 30]},
            "2": {"tag": "input", "role": "textbox", "name": "Email", "value": "", "bbox": [10, 50, 200, 30]},
            "3": {"tag": "button", "role": "button", "name": "Submit", "value": "", "bbox": [10, 90, 80, 30]},
        }

    def reset(self, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        self.step_count = 0
        self.is_terminated = False
        self.is_truncated = False
        self.last_action = None
        self.elements["1"]["value"] = ""
        self.elements["2"]["value"] = ""
        return self._get_obs(), {"goal": self.goal, "task_id": self.task_id}

    def step(self, action_str: str) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        self.step_count += 1
        self.last_action = action_str
        reward = 0.0

        # Parse basic BrowserGym high-level action strings
        # fill("1", "John")
        fill_match = re.match(r'fill\s*\(\s*["\']?([^"\',]+)["\']?\s*,\s*["\']?(.*)["\']?\s*\)', action_str)
        if fill_match:
            elem_id, val = fill_match.group(1).strip(), fill_match.group(2).strip()
            if elem_id in self.elements:
                self.elements[elem_id]["value"] = val

        # click("3")
        click_match = re.match(r'click\s*\(\s*["\']?([^"\',]+)["\']?\s*\)', action_str)
        if click_match:
            elem_id = click_match.group(1).strip()
            if elem_id == "3" and self.elements["1"]["value"] and self.elements["2"]["value"]:
                self.is_terminated = True
                reward = 1.0

        if self.step_count >= 20:
            self.is_truncated = True

        return self._get_obs(), reward, self.is_terminated, self.is_truncated, {"step": self.step_count}

    def _get_obs(self) -> Dict[str, Any]:
        # Formats observation dictionary in standard BrowserGym schema
        axtree = []
        for bid, el in self.elements.items():
            axtree.append({
                "browsergym_id": bid,
                "role": el["role"],
                "name": el["name"],
                "value": el["value"],
                "bbox": el["bbox"],
            })
        return {
            "goal": self.goal,
            "url": self.url,
            "axtree_object": axtree,
            "dom_object": {"children": []},
            "screenshot": b"\x89PNG\r\n\x1a\nfake_bg_screenshot",
            "last_action_error": "",
            "active_page_index": 0,
            "open_pages_urls": [self.url],
        }


class BrowserGymAdapter:
    """Conforms Reflex cognition and execution kernel to BrowserGym / AgentLab benchmark environments."""

    def __init__(
        self,
        env: Any,
        kernel: Optional[HostControlKernel] = None,
        policy: Optional[CapabilityPolicy] = None,
        clock: Optional[Any] = None,
    ) -> None:
        self.env = env
        self.clock = clock or SystemClock()
        self.current_obs_raw: Dict[str, Any] = {}
        self.current_graph: Optional[CanonicalUIGraph] = None
        self.step_counter = 0

        # Build Host Control Kernel if not supplied
        if kernel is None:
            pol = policy or CapabilityPolicy(
                granted_scopes={
                    CapabilityScope.BROWSER_READ,
                    CapabilityScope.BROWSER_INTERACT,
                    CapabilityScope.BROWSER_NAVIGATE,
                }
            )
            policy_engine = CapabilityPolicyEngine(policy=pol)
            lease_mgr = ActionLeaseManager()
            self.kernel = HostControlKernel(
                policy_engine=policy_engine,
                lease_manager=lease_mgr,
                clock=self.clock,
            )
        else:
            self.kernel = kernel

    def reset(self) -> Tuple[CanonicalUIGraph, Dict[str, Any]]:
        """Resets the benchmark environment and returns the initial CanonicalUIGraph."""
        obs_raw, info = self.env.reset()
        self.current_obs_raw = obs_raw
        self.current_graph = self.convert_observation_to_graph(obs_raw)
        self.step_counter = 0
        return self.current_graph, info

    def convert_observation_to_graph(self, obs: Dict[str, Any]) -> CanonicalUIGraph:
        """Converts BrowserGym raw observation dict into Reflex CanonicalUIGraph."""
        nodes: Dict[str, UIStateNode] = {}
        url = obs.get("url", "about:blank")
        timestamp_ms = self.clock.now_ms()

        # Parse Accessibility Tree representation
        axtree = obs.get("axtree_object") or []
        if isinstance(axtree, list):
            for item in axtree:
                if isinstance(item, dict):
                    node_id = str(item.get("browsergym_id") or item.get("id") or item.get("nodeId") or len(nodes))
                    role_str = str(item.get("role", "generic")).lower()
                    name = str(item.get("name") or item.get("label") or "")
                    val = str(item.get("value") or "")
                    bbox_raw = item.get("bbox") or [0, 0, 100, 30]

                    bbox = BoundingBox(
                        x=float(bbox_raw[0]),
                        y=float(bbox_raw[1]),
                        width=float(bbox_raw[2]),
                        height=float(bbox_raw[3]),
                    ) if len(bbox_raw) == 4 else BoundingBox(0, 0, 100, 30)

                    # Map role to NodeRole
                    node_role = NodeRole.GENERIC
                    if "button" in role_str:
                        node_role = NodeRole.BUTTON
                    elif "text" in role_str or "input" in role_str or "box" in role_str:
                        node_role = NodeRole.TEXT_FIELD
                    elif "link" in role_str:
                        node_role = NodeRole.LINK
                    elif "check" in role_str:
                        node_role = NodeRole.CHECKBOX
                    elif "combo" in role_str or "select" in role_str or "dropdown" in role_str:
                        node_role = NodeRole.DROPDOWN

                    is_clickable = node_role in (NodeRole.BUTTON, NodeRole.LINK, NodeRole.CHECKBOX)
                    is_editable = node_role in (NodeRole.TEXT_FIELD, NodeRole.DROPDOWN)

                    node = UIStateNode(
                        node_id=node_id,
                        role=node_role,
                        label=name,
                        value=val,
                        bounds=bbox,
                        is_clickable=is_clickable,
                        is_editable=is_editable,
                        attributes={"browsergym_id": node_id, "raw_role": role_str},
                    )
                    nodes[node_id] = node

        return CanonicalUIGraph(
            timestamp_ms=timestamp_ms,
            nodes=nodes,
            url=url,
            active_window_title=obs.get("goal", ""),
        )

    def convert_typed_action_to_bg_action(self, action: TypedAction) -> str:
        """Converts Reflex TypedAction into BrowserGym Python action string."""
        target_id = action.target_node_id or ""

        if action.action_type == ActionType.CLICK:
            if action.coords is not None and not target_id:
                # Coordinate click
                x = int(action.coords.x * 1280)
                y = int(action.coords.y * 800)
                return f"mouse_click({x}, {y})"
            return f"click('{target_id}')"

        elif action.action_type in (ActionType.TYPE, ActionType.CLEAR_AND_TYPE):
            text = action.text_payload.replace("'", "\\'")
            return f"fill('{target_id}', '{text}')"

        elif action.action_type == ActionType.SELECT_OPTION:
            val = (action.text_payload or "").replace("'", "\\'")
            return f"select_option('{target_id}', '{val}')"

        elif action.action_type == ActionType.SCROLL:
            coords = action.coords or NormalizedCoords(0.0, 0.0)
            dx = int(coords.x * 500)
            dy = int(coords.y * 500)
            return f"scroll({dx}, {dy})"

        elif action.action_type == ActionType.NAVIGATE:
            url = action.text_payload or ""
            return f"goto('{url}')"

        elif action.action_type == ActionType.KEY_COMBINATION:
            key = action.key_code or "Enter"
            return f"press_key('{key}')"

        elif action.action_type == ActionType.DRAG_AND_DROP:
            dest_id = action.metadata.get("destination_node_id", "")
            return f"drag_and_drop('{target_id}', '{dest_id}')"

        return "noop()"

    def convert_bg_action_to_typed_action(self, bg_action_str: str) -> TypedAction:
        """Parses a BrowserGym action string into a Reflex TypedAction."""
        s = bg_action_str.strip()

        # click('id')
        m = re.match(r"click\s*\(\s*['\"]?([^'\"]+)['\"]?\s*\)", s)
        if m:
            return TypedAction(action_type=ActionType.CLICK, target_node_id=m.group(1))

        # fill('id', 'text')
        m = re.match(r"fill\s*\(\s*['\"]?([^'\"]+)['\"]?\s*,\s*['\"]?(.*)['\"]?\s*\)", s)
        if m:
            return TypedAction(action_type=ActionType.TYPE, target_node_id=m.group(1), text_payload=m.group(2))

        # mouse_click(x, y)
        m = re.match(r"mouse_click\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", s)
        if m:
            x_norm = float(m.group(1)) / 1280.0
            y_norm = float(m.group(2)) / 800.0
            return TypedAction(action_type=ActionType.CLICK, coords=NormalizedCoords(x_norm, y_norm))

        # goto('url')
        m = re.match(r"goto\s*\(\s*['\"]?([^'\"]+)['\"]?\s*\)", s)
        if m:
            return TypedAction(action_type=ActionType.NAVIGATE, text_payload=m.group(1))

        # scroll(dx, dy)
        m = re.match(r"scroll\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", s)
        if m:
            return TypedAction(
                action_type=ActionType.SCROLL,
                coords=NormalizedCoords(float(m.group(1)) / 500.0, float(m.group(2)) / 500.0),
            )

        return TypedAction(action_type=ActionType.NOOP)

    async def step(
        self,
        action: Union[TypedAction, ActionProposal],
    ) -> Tuple[CanonicalUIGraph, float, bool, bool, Dict[str, Any]]:
        """Executes a step through Host Kernel gating and BrowserGym environment dispatch."""
        self.step_counter += 1

        proposal: ActionProposal
        if isinstance(action, ActionProposal):
            proposal = action
        else:
            proposal = ActionProposal(
                identity=ActionIdentity.create(session_id="browsergym_session", step_index=self.step_counter),
                action=action,
                expected_delta=StateDelta(outcome_class=OutcomeClass.DIRECT_MATCH),
                required_scopes={CapabilityScope.BROWSER_READ, CapabilityScope.BROWSER_INTERACT},
            )

        # 1. Authorize action via Host Control Kernel policy gate
        dispatch_res = await self.kernel.submit_proposal(proposal)

        if not dispatch_res.verification_passed and dispatch_res.outcome == OutcomeClass.ERROR:
            # Policy rejected or dispatch error
            return (
                self.current_graph or CanonicalUIGraph(timestamp_ms=self.clock.now_ms(), nodes={}),
                0.0,
                False,
                True,
                {"error": dispatch_res.error_message, "status": "POLICY_REJECTED"},
            )

        # 2. Convert to BrowserGym executable action
        bg_action_str = self.convert_typed_action_to_bg_action(proposal.action)

        # 3. Dispatch to Gym environment
        obs_raw, reward, terminated, truncated, info = self.env.step(bg_action_str)
        self.current_obs_raw = obs_raw
        self.current_graph = self.convert_observation_to_graph(obs_raw)

        return self.current_graph, float(reward), bool(terminated), bool(truncated), info
