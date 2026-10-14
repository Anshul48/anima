from __future__ import annotations
import asyncio
import time
import unittest

from reflex.execution.browser.cdp_action_adapter import CDPActionAdapter
from reflex.host.identity.lease_manager import ActionLease, ActionLeaseManager, InvalidLeaseError
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.ports.action import ActionReceipt, ActionStatus
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.identity import ActionIdentity


class TestBrowserActionAdapter(unittest.IsolatedAsyncioTestCase):
    """Comprehensive test suite for CDPActionAdapter across all supported action primitives."""

    def setUp(self):
        self.page = FakeBrowserPage(viewport_width=1280, viewport_height=800)
        self.lease_manager = ActionLeaseManager(default_ttl_ms=5000.0)
        self.adapter = CDPActionAdapter(page=self.page, lease_manager=self.lease_manager)

    def _create_lease(self, action: TypedAction, ttl_ms: float = 5000.0, expired: bool = False) -> ActionLease:
        identity = ActionIdentity.create(session_id="sess_test_001", step_index=1)
        now_ms = time.time() * 1000.0
        if expired:
            now_ms -= 10000.0
        return self.lease_manager.issue_lease(identity=identity, action=action, ttl_ms=ttl_ms, current_time_ms=now_ms)

    async def test_click_action_with_locator(self):
        btn = self.page.register_element("#submit-btn", tag_name="button", text="Submit")
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="#submit-btn",
            safety_class=SafetyClass.REVERSIBLE,
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)

        self.assertIsInstance(receipt, ActionReceipt)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(receipt.lease_id, lease.lease_id)
        self.assertEqual(receipt.action_id, lease.identity.action_id)
        self.assertEqual(receipt.adapter_name, "CDPActionAdapter")
        self.assertIsNone(receipt.error)
        self.assertGreaterEqual(receipt.duration_ms, 0.0)
        self.assertIn("locator.click", receipt.raw_adapter_response.get("dispatched_method", ""))

        # Check page event log
        click_events = [e for e in self.page.event_log if e.get("event") == "element_click"]
        self.assertEqual(len(click_events), 1)
        self.assertEqual(click_events[0]["selector"], "#submit-btn")

    async def test_click_action_with_target_label(self):
        self.page.register_element("text=Save Changes", tag_name="button", text="Save Changes")
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_label="Save Changes",
            safety_class=SafetyClass.REVERSIBLE,
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        click_events = [e for e in self.page.event_log if e.get("event") == "element_click"]
        self.assertEqual(len(click_events), 1)

    async def test_double_click_action(self):
        self.page.register_element("#item-card", tag_name="div")
        action = TypedAction(
            action_type=ActionType.DOUBLE_CLICK,
            target_node_id="#item-card",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        dblclick_events = [e for e in self.page.event_log if e.get("event") == "element_dblclick"]
        self.assertEqual(len(dblclick_events), 1)
        self.assertEqual(dblclick_events[0]["selector"], "#item-card")

    async def test_right_click_action(self):
        self.page.register_element("#context-area", tag_name="div")
        action = TypedAction(
            action_type=ActionType.RIGHT_CLICK,
            target_node_id="#context-area",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        click_events = [e for e in self.page.event_log if e.get("event") == "element_click"]
        self.assertEqual(len(click_events), 1)
        self.assertEqual(click_events[0]["button"], "right")

    async def test_type_action_with_locator(self):
        input_elem = self.page.register_element("#search-box", tag_name="input", value="")
        action = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="#search-box",
            text_payload="Reflex Autonomous Engine",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(input_elem.value, "Reflex Autonomous Engine")
        self.assertEqual(receipt.raw_adapter_response.get("typed_length"), len("Reflex Autonomous Engine"))

    async def test_type_action_without_locator(self):
        action = TypedAction(
            action_type=ActionType.TYPE,
            text_payload="Global Text Input",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(self.page.keyboard.typed_text, "Global Text Input")

    async def test_key_press_action(self):
        action = TypedAction(
            action_type=ActionType.KEY_PRESS,
            key_code="Enter",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        press_events = [e for e in self.page.event_log if e.get("action") == "press" or e.get("event") == "element_press"]
        self.assertTrue(any(e.get("key") == "Enter" for e in press_events))

    async def test_scroll_action_with_delta(self):
        action = TypedAction(
            action_type=ActionType.SCROLL,
            scroll_delta=(0.0, 500.0),
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        wheel_events = [e for e in self.page.event_log if e.get("action") == "wheel"]
        self.assertEqual(len(wheel_events), 1)
        self.assertEqual(wheel_events[0]["delta_y"], 500.0)

    async def test_scroll_into_view_element(self):
        self.page.register_element("#footer", tag_name="footer")
        action = TypedAction(
            action_type=ActionType.SCROLL,
            target_node_id="#footer",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        scroll_events = [e for e in self.page.event_log if e.get("event") == "element_scroll_into_view"]
        self.assertEqual(len(scroll_events), 1)

    async def test_drag_and_drop_locators(self):
        self.page.register_element("#source-item", tag_name="div")
        self.page.register_element("#target-dropzone", tag_name="div")
        action = TypedAction(
            action_type=ActionType.DRAG_AND_DROP,
            target_node_id="#source-item",
            metadata={"target_node_id": "#target-dropzone"},
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        drag_events = [e for e in self.page.event_log if e.get("event") == "element_drag_to"]
        self.assertEqual(len(drag_events), 1)
        self.assertEqual(drag_events[0]["source_selector"], "#source-item")
        self.assertEqual(drag_events[0]["target_selector"], "#target-dropzone")

    async def test_hover_action(self):
        self.page.register_element("#dropdown-menu", tag_name="nav")
        action = TypedAction(
            action_type=ActionType.HOVER,
            target_node_id="#dropdown-menu",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        hover_events = [e for e in self.page.event_log if e.get("event") == "element_hover"]
        self.assertEqual(len(hover_events), 1)

    async def test_wait_action(self):
        action = TypedAction(
            action_type=ActionType.WAIT,
            metadata={"duration_ms": 10.0},
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        wait_events = [e for e in self.page.event_log if e.get("event") == "wait_for_timeout"]
        self.assertEqual(len(wait_events), 1)
        self.assertEqual(wait_events[0]["timeout_ms"], 10.0)

    async def test_noop_action(self):
        action = TypedAction(action_type=ActionType.NOOP)
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(receipt.raw_adapter_response.get("dispatched_method"), "noop")

    async def test_navigate_action(self):
        action = TypedAction(
            action_type=ActionType.NAVIGATE,
            text_payload="https://example.org/dashboard",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(self.page.url, "https://example.org/dashboard")

    async def test_click_action_with_coords_only(self):
        action = TypedAction(
            action_type=ActionType.CLICK,
            coords=NormalizedCoords(0.5, 0.5),
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertIn("mouse.click", receipt.raw_adapter_response.get("dispatched_method", ""))
        self.assertEqual(receipt.raw_adapter_response.get("coords_px"), (640, 400))

    async def test_double_click_with_coords(self):
        action = TypedAction(
            action_type=ActionType.DOUBLE_CLICK,
            coords=NormalizedCoords(0.25, 0.25),
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertIn("mouse.dblclick", receipt.raw_adapter_response.get("dispatched_method", ""))
        self.assertEqual(receipt.raw_adapter_response.get("coords_px"), (320, 200))

    async def test_right_click_with_coords(self):
        action = TypedAction(
            action_type=ActionType.RIGHT_CLICK,
            coords=NormalizedCoords(0.75, 0.75),
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertIn("mouse.click(button='right')", receipt.raw_adapter_response.get("dispatched_method", ""))
        self.assertEqual(receipt.raw_adapter_response.get("coords_px"), (960, 600))

    async def test_drag_and_drop_with_coords(self):
        action = TypedAction(
            action_type=ActionType.DRAG_AND_DROP,
            coords=NormalizedCoords(0.1, 0.1),
            metadata={"target_coords": {"x": 0.8, "y": 0.8}},
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(receipt.raw_adapter_response.get("from_px"), (128, 80))
        self.assertEqual(receipt.raw_adapter_response.get("to_px"), (1024, 640))

    async def test_disabled_element_click_records_failed_receipt(self):
        self.page.register_element("#disabled-btn", tag_name="button", disabled=True)
        action = TypedAction(
            action_type=ActionType.CLICK,
            target_node_id="#disabled-btn",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.FAILED)
        self.assertIsNotNone(receipt.error)
        self.assertIn("disabled", receipt.error.lower())

    async def test_dispatch_action_via_port_interface(self):
        identity = ActionIdentity.create(session_id="sess_port_test", step_index=1)
        action = TypedAction(
            action_type=ActionType.NAVIGATE,
            text_payload="https://example.org/home",
        )
        self.lease_manager.issue_lease(identity=identity, action=action)
        result_dict = await self.adapter.dispatch_action(action=action, identity=identity)
        self.assertIsInstance(result_dict, dict)
        self.assertEqual(result_dict["status"], "dispatched")
        self.assertEqual(result_dict["adapter_name"], "CDPActionAdapter")


if __name__ == "__main__":
    unittest.main()

