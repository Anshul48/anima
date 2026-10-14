from __future__ import annotations
import asyncio
import time
import unittest

from reflex.execution.input.synthetic_input_adapter import SyntheticInputAdapter
from reflex.host.identity.lease_manager import ActionLease, ActionLeaseManager
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.ports.action import ActionReceipt, ActionStatus
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.identity import ActionIdentity


class TestCanvasFallbackInput(unittest.IsolatedAsyncioTestCase):
    """Test suite for SyntheticInputAdapter coordinate-based fallback physical input injection."""

    def setUp(self):
        self.page = FakeBrowserPage(viewport_width=1280, viewport_height=800)
        self.lease_manager = ActionLeaseManager(default_ttl_ms=5000.0)
        self.adapter = SyntheticInputAdapter(
            page=self.page,
            lease_manager=self.lease_manager,
            viewport_width=1280,
            viewport_height=800,
            inter_key_delay_ms=2.0,
            drag_interpolation_steps=10,
        )

    def _create_lease(self, action: TypedAction) -> ActionLease:
        identity = ActionIdentity.create(session_id="sess_synth_001", step_index=1)
        return self.lease_manager.issue_lease(identity=identity, action=action)

    def test_coordinate_normalization_scaling(self):
        """Asserts sub-pixel rounding accuracy on normalized coordinates."""
        coords_center = NormalizedCoords(x=0.5, y=0.5)
        px_x, px_y = self.adapter.to_pixel_coords(coords_center)
        self.assertEqual(px_x, 640)
        self.assertEqual(px_y, 400)

        coords_quarter = NormalizedCoords(x=0.25, y=0.75)
        px_x, px_y = self.adapter.to_pixel_coords(coords_quarter)
        self.assertEqual(px_x, 320)
        self.assertEqual(px_y, 600)

        coords_edge = NormalizedCoords(x=0.1234, y=0.5678)
        px_x, px_y = self.adapter.to_pixel_coords(coords_edge)
        self.assertEqual(px_x, int(round(0.1234 * 1280)))
        self.assertEqual(px_y, int(round(0.5678 * 800)))

    async def test_synthetic_canvas_click(self):
        """Simulates coordinate click on HTML5 canvas and asserts CDP dispatch events."""
        coords = NormalizedCoords(x=0.5, y=0.5)
        action = TypedAction(
            action_type=ActionType.CLICK,
            coords=coords,
            metadata={"is_canvas": True},
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)

        self.assertIsInstance(receipt, ActionReceipt)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(receipt.adapter_name, "SyntheticInputAdapter")
        self.assertEqual(receipt.raw_adapter_response["coords_pixel"], {"x": 640, "y": 400})

        # Verify CDP sent messages
        cdp_messages = self.page.cdp_session.sent_messages
        mouse_events = [m for m in cdp_messages if m["method"] == "Input.dispatchMouseEvent"]
        self.assertGreaterEqual(len(mouse_events), 2)

        press_ev = next(m for m in mouse_events if m["params"].get("type") == "mousePressed")
        release_ev = next(m for m in mouse_events if m["params"].get("type") == "mouseReleased")
        self.assertEqual(press_ev["params"]["x"], 640)
        self.assertEqual(press_ev["params"]["y"], 400)
        self.assertEqual(press_ev["params"]["button"], "left")
        self.assertEqual(release_ev["params"]["x"], 640)
        self.assertEqual(release_ev["params"]["y"], 400)

    async def test_synthetic_double_click(self):
        """Asserts rapid click sequence for double click dispatch."""
        coords = NormalizedCoords(x=0.2, y=0.3)
        action = TypedAction(
            action_type=ActionType.DOUBLE_CLICK,
            coords=coords,
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)

        cdp_messages = self.page.cdp_session.sent_messages
        press_events = [m for m in cdp_messages if m["params"].get("type") == "mousePressed"]
        self.assertEqual(len(press_events), 2)
        self.assertEqual(press_events[0]["params"]["clickCount"], 1)
        self.assertEqual(press_events[1]["params"]["clickCount"], 2)

    async def test_synthetic_right_click(self):
        """Asserts right click button dispatch."""
        coords = NormalizedCoords(x=0.4, y=0.6)
        action = TypedAction(
            action_type=ActionType.RIGHT_CLICK,
            coords=coords,
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)

        cdp_messages = self.page.cdp_session.sent_messages
        press_events = [m for m in cdp_messages if m["params"].get("type") == "mousePressed"]
        self.assertTrue(any(p["params"].get("button") == "right" for p in press_events))

    async def test_synthetic_drag_and_drop_interpolation(self):
        """Asserts smooth coordinate interpolation during drag-and-drop."""
        start_coords = NormalizedCoords(x=0.1, y=0.1)  # 128, 80
        end_coords = NormalizedCoords(x=0.5, y=0.5)    # 640, 400
        action = TypedAction(
            action_type=ActionType.DRAG_AND_DROP,
            coords=start_coords,
            metadata={"target_coords": end_coords.to_dict()},
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(receipt.raw_adapter_response["interpolation_steps"], 10)

        # Check that intermediate moves occurred
        cdp_messages = self.page.cdp_session.sent_messages
        move_events = [m for m in cdp_messages if m["params"].get("type") == "mouseMoved"]
        self.assertGreaterEqual(len(move_events), 10)

        # First move should be start
        self.assertEqual(move_events[0]["params"]["x"], 128)
        self.assertEqual(move_events[0]["params"]["y"], 80)

        # Last move before release should be close to end
        last_move = move_events[-1]
        self.assertEqual(last_move["params"]["x"], 640)
        self.assertEqual(last_move["params"]["y"], 400)

    async def test_synthetic_physical_typing(self):
        """Asserts character-by-character key events dispatch."""
        action = TypedAction(
            action_type=ActionType.TYPE,
            text_payload="Hello 123!",
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)
        self.assertEqual(receipt.raw_adapter_response["typed_length"], 10)

        cdp_messages = self.page.cdp_session.sent_messages
        key_events = [m for m in cdp_messages if m["method"] == "Input.dispatchKeyEvent"]
        self.assertEqual(len(key_events), 20)  # 10 chars * (keyDown + keyUp)

    async def test_synthetic_key_combination(self):
        """Asserts modifier and key combinations like Control+A and Shift+Tab."""
        action_select_all = TypedAction(
            action_type=ActionType.KEY_PRESS,
            key_code="Control+A",
        )
        lease1 = self._create_lease(action_select_all)
        receipt1 = await self.adapter.execute_action(action=action_select_all, lease=lease1)
        self.assertEqual(receipt1.status, ActionStatus.DISPATCHED)

        cdp_messages = self.page.cdp_session.sent_messages
        keys_down = [m["params"].get("key") for m in cdp_messages if m["params"].get("type") == "keyDown"]
        self.assertIn("Control", keys_down)
        self.assertIn("A", keys_down)

    async def test_synthetic_wheel_scroll(self):
        """Asserts synthetic mouse wheel scroll dispatch."""
        coords = NormalizedCoords(x=0.5, y=0.5)
        action = TypedAction(
            action_type=ActionType.SCROLL,
            coords=coords,
            scroll_delta=(0.0, 450.0),
        )
        lease = self._create_lease(action)

        receipt = await self.adapter.execute_action(action=action, lease=lease)
        self.assertEqual(receipt.status, ActionStatus.DISPATCHED)

        cdp_messages = self.page.cdp_session.sent_messages
        wheel_events = [m for m in cdp_messages if m["params"].get("type") == "mouseWheel"]
        self.assertEqual(len(wheel_events), 1)
        self.assertEqual(wheel_events[0]["params"]["deltaY"], 450.0)


if __name__ == "__main__":
    unittest.main()
