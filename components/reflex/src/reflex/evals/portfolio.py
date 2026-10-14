"""Reflex 12-Task Standardized Benchmark Portfolio.

Implements normative tasks across Tier 1 (Forms & Wizards), Tier 2 (Dynamic SPAs,
Tables & Modals), and Tier 3 (Complex Flows, Downloads & Canvas) with local test
fixtures, state transitions, and objective assertions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import os
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from reflex.evals.runner import EvalLane, EvaluationTask, TaskTier
from reflex.grounding.browser_grounder import BrowserGroundingEngine
from reflex.orchestration.browser_loop import TaskGoal
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity, ActionProposal
from reflex.schemas.policy import CapabilityScope
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.verification.verifier import AssertionRule


class MockTaskObservationPort(ObservationPort):
    """Observation adapter simulating dynamic state graphs for benchmark tasks."""

    def __init__(self, initial_graph: CanonicalUIGraph):
        self.current_graph = initial_graph
        self.state_history: List[CanonicalUIGraph] = [initial_graph]

    def set_graph(self, graph: CanonicalUIGraph) -> None:
        self.current_graph = graph
        self.state_history.append(graph)

    def update_node(self, node_id: str, **kwargs: Any) -> None:
        if node_id in self.current_graph.nodes:
            old = self.current_graph.nodes[node_id]
            updated = UIStateNode(
                node_id=old.node_id,
                role=kwargs.get("role", old.role),
                bounds=kwargs.get("bounds", old.bounds),
                label=kwargs.get("label", old.label),
                value=kwargs.get("value", old.value),
                is_clickable=kwargs.get("is_clickable", old.is_clickable),
                is_editable=kwargs.get("is_editable", old.is_editable),
                is_focused=kwargs.get("is_focused", old.is_focused),
                is_enabled=kwargs.get("is_enabled", old.is_enabled),
                parent_id=kwargs.get("parent_id", old.parent_id),
                children_ids=kwargs.get("children_ids", list(old.children_ids)),
                source=kwargs.get("source", old.source),
                confidence=kwargs.get("confidence", old.confidence),
                attributes={**old.attributes, **kwargs.get("attributes", {})},
            )
            nodes = dict(self.current_graph.nodes)
            nodes[node_id] = updated
            self.current_graph = CanonicalUIGraph(
                timestamp_ms=time.time() * 1000.0,
                nodes=nodes,
                focused_node_id=kwargs.get("focused_node_id", self.current_graph.focused_node_id),
                active_window_title=kwargs.get("active_window_title", self.current_graph.active_window_title),
                url=kwargs.get("url", self.current_graph.url),
                viewport_size=self.current_graph.viewport_size,
            )
            self.state_history.append(self.current_graph)

    def add_node(self, node: UIStateNode) -> None:
        nodes = dict(self.current_graph.nodes)
        nodes[node.node_id] = node
        self.current_graph = CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes=nodes,
            focused_node_id=self.current_graph.focused_node_id,
            active_window_title=self.current_graph.active_window_title,
            url=self.current_graph.url,
            viewport_size=self.current_graph.viewport_size,
        )
        self.state_history.append(self.current_graph)

    def remove_node(self, node_id: str) -> None:
        if node_id in self.current_graph.nodes:
            nodes = dict(self.current_graph.nodes)
            del nodes[node_id]
            self.current_graph = CanonicalUIGraph(
                timestamp_ms=time.time() * 1000.0,
                nodes=nodes,
                focused_node_id=self.current_graph.focused_node_id,
                active_window_title=self.current_graph.active_window_title,
                url=self.current_graph.url,
                viewport_size=self.current_graph.viewport_size,
            )
            self.state_history.append(self.current_graph)

    async def capture_state(self) -> CanonicalUIGraph:
        return self.current_graph

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_screenshot_eval"


class DeterministicBenchmarkProposalGenerator:
    """Step-by-step proposal generator executing the optimal trajectory for a benchmark task."""

    def __init__(
        self,
        task_id: str,
        step_proposals: List[TypedAction],
        state_transitions: Optional[List[Callable[[MockTaskObservationPort, int], None]]] = None,
        obs_port: Optional[MockTaskObservationPort] = None,
    ) -> None:
        self.task_id = task_id
        self.step_proposals = list(step_proposals)
        self.state_transitions = list(state_transitions or [])
        self.obs_port = obs_port
        self.step_counter = 0

    async def __call__(
        self,
        goal: TaskGoal,
        current_state: Optional[CanonicalUIGraph] = None,
        step_index: int = 0,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[TypedAction]:
        if self.step_counter >= len(self.step_proposals):
            return None

        action = self.step_proposals[self.step_counter]
        idx = self.step_counter
        self.step_counter += 1

        # Apply state transition side-effects on the mock observation port
        if self.obs_port is not None and idx < len(self.state_transitions):
            self.state_transitions[idx](self.obs_port, idx)

        return action


# ==============================================================================
# Tier 1 Tasks: Form Entry & Wizards (T01 - T04)
# ==============================================================================

def create_task_eval_01() -> EvaluationTask:
    """T01: Multi-Field Customer Registration (TASK-EVAL-01). Optimal steps: 5."""
    nodes = {
        "name_input": UIStateNode(
            node_id="name_input", role=NodeRole.INPUT, label="Full Name", value="",
            bounds=BoundingBox(10, 10, 210, 40), is_editable=True, is_clickable=True,
        ),
        "email_input": UIStateNode(
            node_id="email_input", role=NodeRole.INPUT, label="Email Address", value="",
            bounds=BoundingBox(10, 50, 210, 80), is_editable=True, is_clickable=True,
        ),
        "country_select": UIStateNode(
            node_id="country_select", role=NodeRole.INPUT, label="Country", value="USA",
            bounds=BoundingBox(10, 90, 210, 120), is_editable=True, is_clickable=True,
        ),
        "terms_checkbox": UIStateNode(
            node_id="terms_checkbox", role=NodeRole.CHECKBOX, label="Accept Terms of Service", value="false",
            bounds=BoundingBox(10, 130, 30, 150), is_clickable=True, attributes={"checked": False},
        ),
        "submit_btn": UIStateNode(
            node_id="submit_btn", role=NodeRole.BUTTON, label="Register",
            bounds=BoundingBox(10, 170, 110, 205), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/registration.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.TYPE, target_node_id="name_input", text_payload="Jane Doe"),
        TypedAction(action_type=ActionType.TYPE, target_node_id="email_input", text_payload="jane.doe@example.com"),
        TypedAction(action_type=ActionType.SELECT_OPTION, target_node_id="country_select", text_payload="Canada"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="terms_checkbox"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="submit_btn"),
    ]

    transitions: List[Callable[[MockTaskObservationPort, int], None]] = [
        lambda o, i: o.update_node("name_input", value="Jane Doe"),
        lambda o, i: o.update_node("email_input", value="jane.doe@example.com"),
        lambda o, i: o.update_node("country_select", value="Canada"),
        lambda o, i: o.update_node("terms_checkbox", value="true", attributes={"checked": True}),
        lambda o, i: o.add_node(UIStateNode(
            node_id="registration-success", role=NodeRole.TEXT, label="Registration Successful",
            bounds=BoundingBox(10, 220, 310, 260)
        )),
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-01", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        return (
            "registration-success" in final_state.nodes
            and final_state.nodes.get("name_input", UIStateNode("name_input", NodeRole.INPUT, BoundingBox(0,0,0,0))).value == "Jane Doe"
            and final_state.nodes.get("email_input", UIStateNode("email_input", NodeRole.INPUT, BoundingBox(0,0,0,0))).value == "jane.doe@example.com"
        )

    return EvaluationTask(
        task_id="TASK-EVAL-01",
        instruction="Register a new customer named 'Jane Doe' with email 'jane.doe@example.com', country 'Canada', and accept the terms of service.",
        target_url="http://127.0.0.1:8080/eval/registration.html",
        tier=TaskTier.TIER_1_FORMS,
        optimal_steps=5,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def create_task_eval_02() -> EvaluationTask:
    """T02: Multi-Page Onboarding Wizard (TASK-EVAL-02). Optimal steps: 7."""
    nodes = {
        "step_indicator": UIStateNode(
            node_id="step_indicator", role=NodeRole.TEXT, label="Step 1 of 3", value="1",
            bounds=BoundingBox(10, 10, 160, 30),
        ),
        "name_field": UIStateNode(
            node_id="name_field", role=NodeRole.INPUT, label="Personal Details: Name", value="",
            bounds=BoundingBox(10, 50, 210, 80), is_editable=True, is_clickable=True,
        ),
        "wizard_next_btn": UIStateNode(
            node_id="wizard_next_btn", role=NodeRole.BUTTON, label="Next",
            bounds=BoundingBox(10, 100, 90, 130), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/wizard.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.TYPE, target_node_id="name_field", text_payload="Alice Smith"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="wizard_next_btn"),
        TypedAction(action_type=ActionType.TYPE, target_node_id="role_field", text_payload="Engineering Lead"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="wizard_next_btn"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="confirm_checkbox"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="wizard_submit_btn"),
        TypedAction(action_type=ActionType.NOOP),
    ]

    def step_2_transition(o: MockTaskObservationPort, i: int) -> None:
        o.update_node("step_indicator", label="Step 2 of 3", value="2")
        o.add_node(UIStateNode(
            node_id="role_field", role=NodeRole.INPUT, label="Role Preferences", value="",
            bounds=BoundingBox(10, 50, 210, 80), is_editable=True, is_clickable=True,
        ))

    def step_3_transition(o: MockTaskObservationPort, i: int) -> None:
        o.update_node("step_indicator", label="Step 3 of 3", value="3")
        o.add_node(UIStateNode(
            node_id="confirm_checkbox", role=NodeRole.CHECKBOX, label="Confirm Information", value="false",
            bounds=BoundingBox(10, 50, 30, 70), is_clickable=True,
        ))
        o.add_node(UIStateNode(
            node_id="wizard_submit_btn", role=NodeRole.BUTTON, label="Submit",
            bounds=BoundingBox(10, 100, 90, 130), is_clickable=True,
        ))

    def complete_transition(o: MockTaskObservationPort, i: int) -> None:
        o.update_node("step_indicator", label="Completed", value="4")
        o.add_node(UIStateNode(
            node_id="wizard-completed", role=NodeRole.TEXT, label="Onboarding Complete",
            bounds=BoundingBox(10, 10, 210, 50), attributes={"progress": "100%"},
        ))

    transitions = [
        lambda o, i: o.update_node("name_field", value="Alice Smith"),
        step_2_transition,
        lambda o, i: o.update_node("role_field", value="Engineering Lead"),
        step_3_transition,
        lambda o, i: o.update_node("confirm_checkbox", value="true"),
        complete_transition,
        lambda o, i: None,
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-02", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        return "wizard-completed" in final_state.nodes

    return EvaluationTask(
        task_id="TASK-EVAL-02",
        instruction="Complete the 3-step employee onboarding wizard by filling personal details on Step 1, role preferences on Step 2, and submitting on Step 3.",
        target_url="http://127.0.0.1:8080/eval/wizard.html",
        tier=TaskTier.TIER_1_FORMS,
        optimal_steps=7,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def create_task_eval_03() -> EvaluationTask:
    """T03: E-Commerce Product Search & Filter (TASK-EVAL-03). Optimal steps: 4."""
    nodes = {
        "search_input": UIStateNode(
            node_id="search_input", role=NodeRole.INPUT, label="Search Products", value="",
            bounds=BoundingBox(10, 10, 310, 40), is_editable=True, is_clickable=True,
        ),
        "search_btn": UIStateNode(
            node_id="search_btn", role=NodeRole.BUTTON, label="Search",
            bounds=BoundingBox(320, 10, 400, 40), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/catalog.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.TYPE, target_node_id="search_input", text_payload="Wireless Headphones"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="search_btn"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="filter_audiopro"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="product_item_1"),
    ]

    def search_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="filter_audiopro", role=NodeRole.CHECKBOX, label="AudioPro",
            bounds=BoundingBox(10, 60, 110, 80), is_clickable=True,
        ))
        o.add_node(UIStateNode(
            node_id="product_item_1", role=NodeRole.LINK, label="AudioPro Wireless ANC Headphones",
            bounds=BoundingBox(150, 60, 450, 100), is_clickable=True,
        ))

    def select_product_transition(o: MockTaskObservationPort, i: int) -> None:
        o.set_graph(CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes={
                "product_details_header": UIStateNode(
                    node_id="product_details_header", role=NodeRole.TEXT,
                    label="AudioPro Wireless ANC Headphones", bounds=BoundingBox(10, 10, 410, 50),
                )
            },
            url="http://127.0.0.1:8080/eval/product-details.html?id=ap-anc-1",
        ))

    transitions = [
        lambda o, i: o.update_node("search_input", value="Wireless Headphones"),
        search_transition,
        lambda o, i: o.update_node("filter_audiopro", attributes={"checked": True}),
        select_product_transition,
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-03", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        return "product-details.html" in final_state.url and "product_details_header" in final_state.nodes

    return EvaluationTask(
        task_id="TASK-EVAL-03",
        instruction="Search for 'Wireless Headphones', filter by brand 'AudioPro' and rating '4 Stars & Up', then select the first product.",
        target_url="http://127.0.0.1:8080/eval/catalog.html",
        tier=TaskTier.TIER_1_FORMS,
        optimal_steps=4,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def create_task_eval_04() -> EvaluationTask:
    """T04: Hierarchical Settings Configuration (TASK-EVAL-04). Optimal steps: 4."""
    nodes = {
        "settings_tab": UIStateNode(
            node_id="settings_tab", role=NodeRole.CONTAINER, label="Account Settings",
            bounds=BoundingBox(10, 10, 130, 40), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/settings.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.CLICK, target_node_id="settings_tab"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="notifications_subtab"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="email_digest_toggle"),
        TypedAction(action_type=ActionType.SELECT_OPTION, target_node_id="frequency_select", text_payload="Weekly"),
    ]

    def subtab_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="notifications_subtab", role=NodeRole.CONTAINER, label="Notifications",
            bounds=BoundingBox(10, 50, 110, 80), is_clickable=True,
        ))

    def settings_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="email_digest_toggle", role=NodeRole.CHECKBOX, label="Email Digest",
            bounds=BoundingBox(10, 90, 160, 120), is_clickable=True, attributes={"checked": True},
        ))
        o.add_node(UIStateNode(
            node_id="frequency_select", role=NodeRole.INPUT, label="Frequency",
            bounds=BoundingBox(10, 130, 130, 160), is_clickable=True, value="Daily",
        ))

    def save_transition(o: MockTaskObservationPort, i: int) -> None:
        o.update_node("frequency_select", value="Weekly")
        o.add_node(UIStateNode(
            node_id="settings-saved", role=NodeRole.TEXT, label="Settings Saved",
            bounds=BoundingBox(10, 180, 210, 210),
        ))

    transitions = [
        subtab_transition,
        settings_transition,
        lambda o, i: o.update_node("email_digest_toggle", attributes={"checked": False}),
        save_transition,
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-04", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        dummy_node = UIStateNode("dummy", NodeRole.INPUT, BoundingBox(0,0,0,0))
        return (
            "settings-saved" in final_state.nodes
            and final_state.nodes.get("email_digest_toggle", dummy_node).attributes.get("checked") is False
        )

    return EvaluationTask(
        task_id="TASK-EVAL-04",
        instruction="Navigate to Account Settings -> Notifications, toggle 'Email Digest' to OFF, and set frequency to 'Weekly'.",
        target_url="http://127.0.0.1:8080/eval/settings.html",
        tier=TaskTier.TIER_1_FORMS,
        optimal_steps=4,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


# ==============================================================================
# Tier 2 Tasks: Dynamic SPAs, Modals & Complex Layouts (T05 - T08)
# ==============================================================================

def create_task_eval_05() -> EvaluationTask:
    """T05: Dynamic Data Table Pagination & Sorting (TASK-EVAL-05). Optimal steps: 4."""
    nodes = {
        "sort_created_header": UIStateNode(
            node_id="sort_created_header", role=NodeRole.BUTTON, label="Date Created",
            bounds=BoundingBox(10, 10, 130, 40), is_clickable=True,
        ),
        "page_1_btn": UIStateNode(node_id="page_1_btn", role=NodeRole.BUTTON, label="Page 1", bounds=BoundingBox(10, 200, 50, 230)),
        "page_2_btn": UIStateNode(node_id="page_2_btn", role=NodeRole.BUTTON, label="Page 2", bounds=BoundingBox(60, 200, 100, 230), is_clickable=True),
        "row_user_01": UIStateNode(node_id="row_user_01", role=NodeRole.TEXT, label="User_01", bounds=BoundingBox(10, 50, 210, 70)),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/datagrid.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.CLICK, target_node_id="sort_created_header"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="page_2_btn"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="delete_user_42_btn"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="confirm_delete_modal_btn"),
    ]

    def page_2_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="row_user_42", role=NodeRole.TEXT, label="User_42", bounds=BoundingBox(10, 50, 210, 70),
        ))
        o.add_node(UIStateNode(
            node_id="delete_user_42_btn", role=NodeRole.BUTTON, label="Delete User_42",
            bounds=BoundingBox(220, 50, 300, 70), is_clickable=True,
        ))
        o.update_node("page_2_btn", attributes={"active": True})

    def modal_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="confirm_delete_modal_btn", role=NodeRole.BUTTON, label="Confirm Delete",
            bounds=BoundingBox(100, 100, 200, 130), is_clickable=True,
        ))

    def deleted_transition(o: MockTaskObservationPort, i: int) -> None:
        o.remove_node("row_user_42")
        o.remove_node("delete_user_42_btn")
        o.remove_node("confirm_delete_modal_btn")

    transitions = [
        lambda o, i: o.update_node("sort_created_header", attributes={"sorted": "desc"}),
        page_2_transition,
        modal_transition,
        deleted_transition,
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-05", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        dummy_node = UIStateNode("dummy", NodeRole.BUTTON, BoundingBox(0,0,0,0))
        return (
            "row_user_42" not in final_state.nodes
            and final_state.nodes.get("page_2_btn", dummy_node).attributes.get("active") is True
        )

    return EvaluationTask(
        task_id="TASK-EVAL-05",
        instruction="Sort the user table by 'Date Created' descending, advance to Page 2, and delete the user 'User_42'.",
        target_url="http://127.0.0.1:8080/eval/datagrid.html",
        tier=TaskTier.TIER_2_SPAS,
        optimal_steps=4,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def create_task_eval_06() -> EvaluationTask:
    """T06: Cookie Banner & Unexpected Modal Interception (TASK-EVAL-06). Optimal steps: 3."""
    nodes = {
        "cookie_banner_accept": UIStateNode(
            node_id="cookie_banner_accept", role=NodeRole.BUTTON, label="Accept Cookies",
            bounds=BoundingBox(10, 300, 130, 330), is_clickable=True,
        ),
        "promo_close_btn": UIStateNode(
            node_id="promo_close_btn", role=NodeRole.BUTTON, label="Close",
            bounds=BoundingBox(250, 50, 280, 80), is_clickable=True,
        ),
        "download_guide_btn": UIStateNode(
            node_id="download_guide_btn", role=NodeRole.BUTTON, label="Download Free Guide",
            bounds=BoundingBox(10, 100, 170, 140), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/promo.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.CLICK, target_node_id="cookie_banner_accept"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="promo_close_btn"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="download_guide_btn"),
    ]

    transitions = [
        lambda o, i: o.remove_node("cookie_banner_accept"),
        lambda o, i: o.remove_node("promo_close_btn"),
        lambda o, i: o.add_node(UIStateNode(
            node_id="guide-download-triggered", role=NodeRole.TEXT, label="Download Started",
            bounds=BoundingBox(10, 150, 210, 180),
        )),
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-06", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        return "guide-download-triggered" in final_state.nodes

    return EvaluationTask(
        task_id="TASK-EVAL-06",
        instruction="Click the 'Download Free Guide' button on the landing page (handling any cookie consent or promotion popups that appear).",
        target_url="http://127.0.0.1:8080/eval/promo.html",
        tier=TaskTier.TIER_2_SPAS,
        optimal_steps=3,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def create_task_eval_07() -> EvaluationTask:
    """T07: Dynamic Form with Asynchronous Server Validation (TASK-EVAL-07). Optimal steps: 4."""
    nodes = {
        "username_input": UIStateNode(
            node_id="username_input", role=NodeRole.INPUT, label="Username", value="",
            bounds=BoundingBox(10, 10, 210, 40), is_editable=True, is_clickable=True,
        ),
        "signup_submit_btn": UIStateNode(
            node_id="signup_submit_btn", role=NodeRole.BUTTON, label="Submit Signup",
            bounds=BoundingBox(10, 80, 130, 110), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/async_validation.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.TYPE, target_node_id="username_input", text_payload="admin_user"),
        TypedAction(action_type=ActionType.CLEAR_AND_TYPE, target_node_id="username_input", text_payload="admin_user_2026"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="signup_submit_btn"),
        TypedAction(action_type=ActionType.NOOP),
    ]

    def validation_error_transition(o: MockTaskObservationPort, i: int) -> None:
        o.update_node("username_input", value="admin_user")
        o.add_node(UIStateNode(
            node_id="validation_err", role=NodeRole.TEXT, label="Username Taken",
            bounds=BoundingBox(10, 45, 160, 65),
        ))

    def validation_clear_transition(o: MockTaskObservationPort, i: int) -> None:
        o.remove_node("validation_err")
        o.update_node("username_input", value="admin_user_2026")

    def submit_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="signup-confirmed", role=NodeRole.TEXT, label="Account Created Successfully",
            bounds=BoundingBox(10, 120, 260, 150),
        ))

    transitions = [
        validation_error_transition,
        validation_clear_transition,
        submit_transition,
        lambda o, i: None,
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-07", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        dummy_node = UIStateNode("dummy", NodeRole.INPUT, BoundingBox(0,0,0,0))
        return (
            "signup-confirmed" in final_state.nodes
            and final_state.nodes.get("username_input", dummy_node).value == "admin_user_2026"
        )

    return EvaluationTask(
        task_id="TASK-EVAL-07",
        instruction="Enter username 'admin_user' into the signup form. If the server reports 'Username Taken', enter 'admin_user_2026' and submit.",
        target_url="http://127.0.0.1:8080/eval/async_validation.html",
        tier=TaskTier.TIER_2_SPAS,
        optimal_steps=4,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def create_task_eval_08() -> EvaluationTask:
    """T08: Cross-Origin Iframe Checkout Form (TASK-EVAL-08). Optimal steps: 5."""
    nodes = {
        "billing_address": UIStateNode(
            node_id="billing_address", role=NodeRole.INPUT, label="Billing Address", value="",
            bounds=BoundingBox(10, 10, 260, 40), is_editable=True, is_clickable=True,
        ),
        "payment_iframe": UIStateNode(
            node_id="payment_iframe", role=NodeRole.CONTAINER, label="Payment Provider",
            bounds=BoundingBox(10, 60, 310, 210),
        ),
        "card_num_input": UIStateNode(
            node_id="card_num_input", role=NodeRole.INPUT, label="Card Number", value="",
            bounds=BoundingBox(20, 80, 220, 110), is_editable=True, is_clickable=True, parent_id="payment_iframe",
        ),
        "card_exp_input": UIStateNode(
            node_id="card_exp_input", role=NodeRole.INPUT, label="MM/YY", value="",
            bounds=BoundingBox(20, 120, 100, 150), is_editable=True, is_clickable=True, parent_id="payment_iframe",
        ),
        "pay_now_btn": UIStateNode(
            node_id="pay_now_btn", role=NodeRole.BUTTON, label="Pay Now",
            bounds=BoundingBox(20, 160, 120, 190), is_clickable=True, parent_id="payment_iframe",
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/checkout.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.TYPE, target_node_id="billing_address", text_payload="123 Market St"),
        TypedAction(action_type=ActionType.TYPE, target_node_id="card_num_input", text_payload="4000123456789010"),
        TypedAction(action_type=ActionType.TYPE, target_node_id="card_exp_input", text_payload="12/28"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="pay_now_btn"),
        TypedAction(action_type=ActionType.NOOP),
    ]

    def payment_complete_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="payment-receipt", role=NodeRole.TEXT, label="Payment Authorized: Receipt #88219",
            bounds=BoundingBox(10, 220, 310, 260),
        ))

    transitions = [
        lambda o, i: o.update_node("billing_address", value="123 Market St"),
        lambda o, i: o.update_node("card_num_input", value="4000123456789010"),
        lambda o, i: o.update_node("card_exp_input", value="12/28"),
        payment_complete_transition,
        lambda o, i: None,
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-08", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        return "payment-receipt" in final_state.nodes

    return EvaluationTask(
        task_id="TASK-EVAL-08",
        instruction="Fill in billing details in the main page and complete the credit card fields inside the secure payment iframe.",
        target_url="http://127.0.0.1:8080/eval/checkout.html",
        tier=TaskTier.TIER_2_SPAS,
        optimal_steps=5,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


# ==============================================================================
# Tier 3 Tasks: Complex Flows, Downloads & Canvas (T09 - T12)
# ==============================================================================

def create_task_eval_09(download_dir: Optional[str] = None) -> EvaluationTask:
    """T09: Invoice PDF Generation & Download Assertion (TASK-EVAL-09). Optimal steps: 2."""
    if download_dir:
        tmp_dir = download_dir
    else:
        tmp_dir = os.path.join(tempfile.gettempdir(), "reflex_eval_downloads", f"task09_{int(time.time() * 1000)}")
    expected_file = os.path.join(tmp_dir, "INV-1099.pdf")

    nodes = {
        "invoice_row_1099": UIStateNode(
            node_id="invoice_row_1099", role=NodeRole.CONTAINER, label="Invoice #INV-1099",
            bounds=BoundingBox(10, 50, 310, 80), is_clickable=True,
        ),
        "generate_pdf_btn": UIStateNode(
            node_id="generate_pdf_btn", role=NodeRole.BUTTON, label="Generate PDF",
            bounds=BoundingBox(320, 50, 440, 80), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/invoicing.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.CLICK, target_node_id="invoice_row_1099"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="generate_pdf_btn"),
    ]

    def trigger_download_transition(o: MockTaskObservationPort, i: int) -> None:
        os.makedirs(tmp_dir, exist_ok=True)
        with open(expected_file, "wb") as f:
            f.write(b"%PDF-1.4 mock pdf document content for invoice #INV-1099 " + (b"0" * 2000))
        o.add_node(UIStateNode(
            node_id="download_complete_toast", role=NodeRole.TEXT, label="INV-1099.pdf generated",
            bounds=BoundingBox(10, 100, 210, 130),
        ))

    transitions = [
        lambda o, i: o.update_node("invoice_row_1099", attributes={"selected": True}),
        trigger_download_transition,
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-09", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        return os.path.exists(expected_file) and os.path.getsize(expected_file) > 1024

    return EvaluationTask(
        task_id="TASK-EVAL-09",
        instruction="Select Invoice #INV-1099, click 'Generate PDF', and verify the downloaded file exists on disk with non-zero size.",
        target_url="http://127.0.0.1:8080/eval/invoicing.html",
        tier=TaskTier.TIER_3_COMPLEX,
        optimal_steps=2,
        required_capabilities=[CapabilityScope.BROWSER_READ, CapabilityScope.BROWSER_INTERACT, CapabilityScope.FS_READ],
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
        parameters={"download_file": expected_file},
    )


def create_task_eval_10() -> EvaluationTask:
    """T10: Drag-and-Drop Kanban Task Movement (TASK-EVAL-10). Optimal steps: 1."""
    nodes = {
        "column_in_progress": UIStateNode(
            node_id="column_in_progress", role=NodeRole.CONTAINER, label="In Progress",
            bounds=BoundingBox(200, 50, 380, 450),
        ),
        "column_completed": UIStateNode(
            node_id="column_completed", role=NodeRole.CONTAINER, label="Completed",
            bounds=BoundingBox(400, 50, 580, 450),
        ),
        "card_deploy_v1": UIStateNode(
            node_id="card_deploy_v1", role=NodeRole.CONTAINER, label="Deploy V1",
            bounds=BoundingBox(210, 70, 370, 120), parent_id="column_in_progress", is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/kanban.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(
            action_type=ActionType.DRAG_AND_DROP,
            target_node_id="card_deploy_v1",
            coords=NormalizedCoords(0.5, 0.5),
            metadata={"destination_node_id": "column_completed"},
        ),
    ]

    def dnd_transition(o: MockTaskObservationPort, i: int) -> None:
        o.update_node("card_deploy_v1", parent_id="column_completed", bounds=BoundingBox(410, 70, 570, 120))
        o.add_node(UIStateNode(
            node_id="completed_counter", role=NodeRole.TEXT, label="Completed (1)",
            bounds=BoundingBox(400, 20, 500, 40),
        ))

    transitions = [dnd_transition]
    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-10", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        card = final_state.nodes.get("card_deploy_v1")
        return card is not None and card.parent_id == "column_completed"

    return EvaluationTask(
        task_id="TASK-EVAL-10",
        instruction="Drag the task card 'Deploy V1' from the 'In Progress' column to the 'Completed' column.",
        target_url="http://127.0.0.1:8080/eval/kanban.html",
        tier=TaskTier.TIER_3_COMPLEX,
        optimal_steps=1,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def create_task_eval_11() -> EvaluationTask:
    """T11: HTML5 Canvas Interactive Chart Grounding (TASK-EVAL-11). Optimal steps: 1."""
    nodes = {
        "financial_chart_canvas": UIStateNode(
            node_id="financial_chart_canvas", role=NodeRole.CONTAINER, label="Financial Chart Canvas",
            bounds=BoundingBox(50, 50, 650, 450), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=nodes, url="http://127.0.0.1:8080/eval/canvas_chart.html"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="financial_chart_canvas",
            coords=NormalizedCoords(0.85, 0.15),  # Top right 'Export Chart' canvas button
            metadata={"interaction_mode": "vision_fallback"},
        ),
    ]

    def canvas_click_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="canvas_export_modal", role=NodeRole.CONTAINER, label="Export Chart Options",
            bounds=BoundingBox(200, 150, 500, 350),
        ))

    transitions = [canvas_click_transition]
    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-11", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        return "canvas_export_modal" in final_state.nodes

    return EvaluationTask(
        task_id="TASK-EVAL-11",
        instruction="Click on the 'Export Chart' button rendered inside the financial chart canvas.",
        target_url="http://127.0.0.1:8080/eval/canvas_chart.html",
        tier=TaskTier.TIER_3_COMPLEX,
        optimal_steps=1,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def create_task_eval_12() -> EvaluationTask:
    """T12: Multi-Tab Data Extraction & Report Entry (TASK-EVAL-12). Optimal steps: 4."""
    tab1_nodes = {
        "report_revenue_text": UIStateNode(
            node_id="report_revenue_text", role=NodeRole.TEXT, label="Total Revenue: $4,250,000",
            value="$4,250,000", bounds=BoundingBox(10, 50, 210, 80),
        ),
        "tab_nav_summary": UIStateNode(
            node_id="tab_nav_summary", role=NodeRole.CONTAINER, label="Summary Tab",
            bounds=BoundingBox(10, 10, 110, 40), is_clickable=True,
        ),
    }
    initial_graph = CanonicalUIGraph(
        timestamp_ms=1000.0, nodes=tab1_nodes, url="http://127.0.0.1:8080/eval/multitab.html#tab1"
    )
    obs = MockTaskObservationPort(initial_graph)

    step_proposals = [
        TypedAction(action_type=ActionType.CLICK, target_node_id="tab_nav_summary"),
        TypedAction(action_type=ActionType.TYPE, target_node_id="summary_revenue_input", text_payload="$4,250,000"),
        TypedAction(action_type=ActionType.CLICK, target_node_id="summary_submit_btn"),
        TypedAction(action_type=ActionType.NOOP),
    ]

    def switch_tab_transition(o: MockTaskObservationPort, i: int) -> None:
        o.set_graph(CanonicalUIGraph(
            timestamp_ms=time.time() * 1000.0,
            nodes={
                "summary_revenue_input": UIStateNode(
                    node_id="summary_revenue_input", role=NodeRole.INPUT, label="Revenue Entry",
                    value="", bounds=BoundingBox(10, 50, 210, 80), is_editable=True, is_clickable=True,
                ),
                "summary_submit_btn": UIStateNode(
                    node_id="summary_submit_btn", role=NodeRole.BUTTON, label="Submit Report",
                    bounds=BoundingBox(10, 100, 130, 130), is_clickable=True,
                ),
            },
            url="http://127.0.0.1:8080/eval/multitab.html#tab2",
        ))

    def submit_report_transition(o: MockTaskObservationPort, i: int) -> None:
        o.add_node(UIStateNode(
            node_id="report-submitted", role=NodeRole.TEXT, label="Report Submitted Successfully",
            bounds=BoundingBox(10, 150, 260, 180),
        ))

    transitions = [
        switch_tab_transition,
        lambda o, i: o.update_node("summary_revenue_input", value="$4,250,000"),
        submit_report_transition,
        lambda o, i: None,
    ]

    proposal_gen = DeterministicBenchmarkProposalGenerator("TASK-EVAL-12", step_proposals, transitions, obs)

    def custom_verify(final_state: CanonicalUIGraph, report: Any) -> bool:
        return "report-submitted" in final_state.nodes and "#tab2" in final_state.url

    return EvaluationTask(
        task_id="TASK-EVAL-12",
        instruction="Open Tab 1 to read the total revenue figure from 'Report A', then switch to Tab 2 and enter the revenue into the summary form.",
        target_url="http://127.0.0.1:8080/eval/multitab.html",
        tier=TaskTier.TIER_3_COMPLEX,
        optimal_steps=4,
        observation_port=obs,
        proposal_generator=proposal_gen,
        custom_verifier=custom_verify,
    )


def get_standard_portfolio_tasks() -> List[EvaluationTask]:
    """Returns all 12 tasks in the standardized benchmark portfolio."""
    return [
        create_task_eval_01(),
        create_task_eval_02(),
        create_task_eval_03(),
        create_task_eval_04(),
        create_task_eval_05(),
        create_task_eval_06(),
        create_task_eval_07(),
        create_task_eval_08(),
        create_task_eval_09(),
        create_task_eval_10(),
        create_task_eval_11(),
        create_task_eval_12(),
    ]


def get_tier_tasks(tier: TaskTier) -> List[EvaluationTask]:
    """Returns benchmark tasks belonging to a specific tier."""
    all_tasks = get_standard_portfolio_tasks()
    return [t for t in all_tasks if t.tier == tier]
