from __future__ import annotations
import asyncio
from dataclasses import dataclass
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from reflex.execution.browser.cdp_action_adapter import BrowserActionPort
from reflex.host.identity.lease_manager import ActionLease, ActionLeaseManager, InvalidLeaseError
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.ports.action import ActionReceipt, ActionStatus
from reflex.schemas.actions import ActionType, NormalizedCoords, TypedAction
from reflex.schemas.identity import ActionIdentity


class SyntheticInputAdapter(BrowserActionPort):
    """Fallback physical input adapter for synthetic coordinate-based mouse and keyboard events via CDP."""

    def __init__(
        self,
        page: Any = None,
        cdp_session: Any = None,
        lease_manager: Optional[ActionLeaseManager] = None,
        viewport_width: int = 1280,
        viewport_height: int = 800,
        inter_key_delay_ms: float = 15.0,
        drag_interpolation_steps: int = 10,
        options: Optional[Dict[str, Any]] = None,
    ):
        self.page = page if page is not None else FakeBrowserPage(viewport_width, viewport_height)
        self.cdp_session = cdp_session
        self.lease_manager = lease_manager
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.inter_key_delay_ms = inter_key_delay_ms
        self.drag_interpolation_steps = max(2, drag_interpolation_steps)
        self.options = options or {}
        self._consumed_leases: Set[str] = set()
        self._dispatched_identities: Set[str] = set()

    def _get_viewport(self) -> Tuple[int, int]:
        """Gets active viewport dimensions."""
        if hasattr(self.page, "viewport_size") and self.page.viewport_size:
            v = self.page.viewport_size
            return int(v.get("width", self.viewport_width)), int(v.get("height", self.viewport_height))
        return self.viewport_width, self.viewport_height

    def to_pixel_coords(self, coords: Optional[NormalizedCoords]) -> Tuple[int, int]:
        """Converts normalized [0.0, 1.0] coordinates to viewport pixel space with sub-pixel rounding."""
        if coords is None:
            raise ValueError("Coordinates are required for synthetic physical input adapter")
        w, h = self._get_viewport()
        px = int(round(coords.x * w))
        py = int(round(coords.y * h))
        return px, py

    def _get_cdp_session(self) -> Any:
        """Retrieves or creates CDP session for raw CDP command dispatch."""
        if self.cdp_session is not None:
            return self.cdp_session
        if hasattr(self.page, "get_cdp_session"):
            return self.page.get_cdp_session()
        if hasattr(self.page, "cdp_session"):
            return self.page.cdp_session
        return None

    async def _send_cdp(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches CDP command directly if available, otherwise delegates to page interfaces."""
        session = self._get_cdp_session()
        if session is not None and hasattr(session, "send"):
            return await session.send(method, params)
        return {}

    def _validate_and_consume_lease(self, lease: Optional[ActionLease], action: TypedAction) -> None:
        """Enforces strict pre-execution lease validation and single-use consumption."""
        if lease is None:
            raise InvalidLeaseError("Execution failed: ActionLease is required but was None")

        now_ms = time.time() * 1000.0

        if self.lease_manager is not None:
            self.lease_manager.consume_lease(lease, action=action, current_time_ms=now_ms)
            return

        if lease.lease_id in self._consumed_leases:
            raise InvalidLeaseError(
                f"Action lease '{lease.lease_id}' has already been consumed (at-most-one dispatch violation)"
            )

        if lease.identity.action_id in self._dispatched_identities:
            raise InvalidLeaseError(
                f"Action identity '{lease.identity.action_id}' has already been dispatched"
            )

        if lease.is_expired(now_ms):
            raise InvalidLeaseError(
                f"Action lease '{lease.lease_id}' expired at {lease.expires_at_ms:.2f}ms (current: {now_ms:.2f}ms)"
            )

        if action.action_type != lease.action.action_type:
            raise InvalidLeaseError(
                f"Action type mismatch: lease specifies '{lease.action.action_type.value}', got '{action.action_type.value}'"
            )

        self._consumed_leases.add(lease.lease_id)
        self._dispatched_identities.add(lease.identity.action_id)

    async def execute_action(self, action: TypedAction, lease: ActionLease) -> ActionReceipt:
        """Dispatches coordinate-based synthetic physical mouse/keyboard events."""
        # 1. Strict Lease Validation (Fail Closed)
        self._validate_and_consume_lease(lease, action)

        start_time_ms = time.time() * 1000.0
        raw_response: Dict[str, Any] = {
            "action_type": action.action_type.value,
            "adapter": "SyntheticInputAdapter",
        }
        error_msg: Optional[str] = None
        status = ActionStatus.DISPATCHED

        try:
            # Handle coordinate extraction
            coords = action.coords
            target_pixel: Optional[Tuple[int, int]] = None
            if coords is not None:
                target_pixel = self.to_pixel_coords(coords)
                raw_response["coords_normalized"] = {"x": coords.x, "y": coords.y}
                raw_response["coords_pixel"] = {"x": target_pixel[0], "y": target_pixel[1]}
            elif action.metadata.get("pixel_x") is not None and action.metadata.get("pixel_y") is not None:
                target_pixel = (int(action.metadata["pixel_x"]), int(action.metadata["pixel_y"]))
                raw_response["coords_pixel"] = {"x": target_pixel[0], "y": target_pixel[1]}

            if action.action_type == ActionType.CLICK:
                if target_pixel is None:
                    raise ValueError("Synthetic CLICK requires coordinates")
                x, y = target_pixel
                await self._dispatch_mouse_click(x, y, button="left", click_count=1)
                raw_response["dispatched"] = "mouse_click"

            elif action.action_type == ActionType.DOUBLE_CLICK:
                if target_pixel is None:
                    raise ValueError("Synthetic DOUBLE_CLICK requires coordinates")
                x, y = target_pixel
                await self._dispatch_mouse_click(x, y, button="left", click_count=1)
                await asyncio.sleep(0.05)  # 50ms rapid double-click delta
                await self._dispatch_mouse_click(x, y, button="left", click_count=2)
                raw_response["dispatched"] = "mouse_double_click"

            elif action.action_type == ActionType.RIGHT_CLICK:
                if target_pixel is None:
                    raise ValueError("Synthetic RIGHT_CLICK requires coordinates")
                x, y = target_pixel
                await self._dispatch_mouse_click(x, y, button="right", click_count=1)
                raw_response["dispatched"] = "mouse_right_click"

            elif action.action_type == ActionType.HOVER:
                if target_pixel is None:
                    raise ValueError("Synthetic HOVER requires coordinates")
                x, y = target_pixel
                await self._dispatch_mouse_move(x, y)
                raw_response["dispatched"] = "mouse_move"

            elif action.action_type == ActionType.SCROLL:
                x = target_pixel[0] if target_pixel else self._get_viewport()[0] // 2
                y = target_pixel[1] if target_pixel else self._get_viewport()[1] // 2
                dx = 0.0
                dy = 300.0
                if action.scroll_delta is not None:
                    dx, dy = action.scroll_delta
                await self._dispatch_mouse_wheel(x, y, delta_x=dx, delta_y=dy)
                raw_response["dispatched"] = "mouse_wheel"
                raw_response["scroll_delta"] = (dx, dy)

            elif action.action_type == ActionType.DRAG_AND_DROP:
                if target_pixel is None:
                    raise ValueError("Synthetic DRAG_AND_DROP requires starting coordinates")
                start_x, start_y = target_pixel

                target_coords_raw = action.metadata.get("target_coords") or action.metadata.get("end_coords")
                if isinstance(target_coords_raw, dict):
                    t_norm = NormalizedCoords.from_dict(target_coords_raw)
                    end_x, end_y = self.to_pixel_coords(t_norm)
                elif isinstance(target_coords_raw, (tuple, list)):
                    end_x, end_y = int(target_coords_raw[0]), int(target_coords_raw[1])
                elif action.metadata.get("target_pixel_x") is not None and action.metadata.get("target_pixel_y") is not None:
                    end_x = int(action.metadata["target_pixel_x"])
                    end_y = int(action.metadata["target_pixel_y"])
                else:
                    raise ValueError("Synthetic DRAG_AND_DROP requires target_coords/end_coords in metadata")

                interpolated_points = await self._dispatch_drag_and_drop(start_x, start_y, end_x, end_y)
                raw_response["dispatched"] = "drag_and_drop"
                raw_response["start_pixel"] = {"x": start_x, "y": start_y}
                raw_response["end_pixel"] = {"x": end_x, "y": end_y}
                raw_response["interpolation_steps"] = len(interpolated_points)

            elif action.action_type == ActionType.TYPE:
                text = action.text_payload or action.metadata.get("text", "")
                # Optional pre-focus at coordinates
                if target_pixel is not None:
                    await self._dispatch_mouse_click(target_pixel[0], target_pixel[1])
                    await asyncio.sleep(0.01)

                await self._dispatch_type_text(text)
                raw_response["dispatched"] = "keyboard_type"
                raw_response["typed_length"] = len(text)

            elif action.action_type == ActionType.KEY_PRESS:
                key = action.key_code or action.text_payload or action.metadata.get("key", "")
                if not key:
                    raise ValueError("Synthetic KEY_PRESS requires key_code or text_payload")
                await self._dispatch_key_combination(key)
                raw_response["dispatched"] = "key_combination"
                raw_response["key"] = key

            elif action.action_type == ActionType.WAIT:
                duration_ms = float(action.metadata.get("duration_ms", action.text_payload or 500.0))
                if hasattr(self.page, "wait_for_timeout"):
                    await self.page.wait_for_timeout(duration_ms)
                else:
                    await asyncio.sleep(duration_ms / 1000.0)
                raw_response["dispatched"] = "wait"
                raw_response["duration_ms"] = duration_ms

            elif action.action_type == ActionType.NOOP:
                raw_response["dispatched"] = "noop"

            elif action.action_type == ActionType.NAVIGATE:
                url = action.text_payload or action.metadata.get("url", "")
                if not url:
                    raise ValueError("Navigate action requires target URL")
                await self._send_cdp("Page.navigate", {"url": url})
                if hasattr(self.page, "goto"):
                    await self.page.goto(url)
                raw_response["dispatched"] = "navigate"
                raw_response["url"] = url

            else:
                raise NotImplementedError(f"Unsupported ActionType '{action.action_type.value}' in SyntheticInputAdapter")

        except InvalidLeaseError:
            raise
        except Exception as exc:
            status = ActionStatus.FAILED
            error_msg = str(exc)
            raw_response["error"] = error_msg

        end_time_ms = time.time() * 1000.0
        duration_ms = max(0.0, end_time_ms - start_time_ms)

        return ActionReceipt(
            lease_id=lease.lease_id,
            action_id=lease.identity.action_id,
            adapter_name="SyntheticInputAdapter",
            dispatch_timestamp_ms=start_time_ms,
            duration_ms=duration_ms,
            raw_adapter_response=raw_response,
            status=status,
            error=error_msg,
        )

    async def _dispatch_mouse_move(self, x: int, y: int) -> None:
        """Dispatches mouseMoved event."""
        await self._send_cdp("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        if hasattr(self.page, "mouse"):
            await self.page.mouse.move(x, y)

    async def _dispatch_mouse_click(self, x: int, y: int, button: str = "left", click_count: int = 1) -> None:
        """Dispatches complete mousePressed -> mouseReleased event cycle."""
        await self._dispatch_mouse_move(x, y)
        await self._send_cdp(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x, "y": y, "button": button, "clickCount": click_count},
        )
        await self._send_cdp(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": button, "clickCount": click_count},
        )
        if hasattr(self.page, "mouse"):
            if click_count == 2:
                await self.page.mouse.dblclick(x, y, button=button)
            else:
                await self.page.mouse.click(x, y, button=button, click_count=click_count)

    async def _dispatch_mouse_wheel(self, x: int, y: int, delta_x: float, delta_y: float) -> None:
        """Dispatches mouseWheel event."""
        await self._send_cdp(
            "Input.dispatchMouseEvent",
            {"type": "mouseWheel", "x": x, "y": y, "deltaX": delta_x, "deltaY": delta_y},
        )
        if hasattr(self.page, "mouse") and hasattr(self.page.mouse, "wheel"):
            await self.page.mouse.wheel(delta_x, delta_y)

    async def _dispatch_drag_and_drop(
        self, start_x: int, start_y: int, end_x: int, end_y: int
    ) -> List[Tuple[int, int]]:
        """Dispatches a mouse drag with smooth intermediate interpolation steps."""
        interpolated: List[Tuple[int, int]] = []
        steps = self.drag_interpolation_steps

        # 1. Move to start position and press mouse down
        await self._dispatch_mouse_move(start_x, start_y)
        await self._send_cdp(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": start_x, "y": start_y, "button": "left", "clickCount": 1},
        )
        if hasattr(self.page, "mouse"):
            await self.page.mouse.down(button="left")

        # 2. Intermediate interpolated movement steps
        for step in range(1, steps + 1):
            t = float(step) / float(steps)
            cur_x = int(round(start_x + t * (end_x - start_x)))
            cur_y = int(round(start_y + t * (end_y - start_y)))
            interpolated.append((cur_x, cur_y))
            await self._dispatch_mouse_move(cur_x, cur_y)
            await asyncio.sleep(0.005)

        # 3. Release mouse at final destination
        await self._send_cdp(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": end_x, "y": end_y, "button": "left", "clickCount": 1},
        )
        if hasattr(self.page, "mouse"):
            await self.page.mouse.up(button="left")

        return interpolated

    async def _dispatch_type_text(self, text: str) -> None:
        """Dispatches physical keystrokes per character with inter-key delay."""
        for char in text:
            await self._send_cdp("Input.dispatchKeyEvent", {"type": "keyDown", "text": char, "key": char})
            await self._send_cdp("Input.dispatchKeyEvent", {"type": "keyUp", "text": char, "key": char})
            if hasattr(self.page, "keyboard"):
                await self.page.keyboard.type(char)
            if self.inter_key_delay_ms > 0:
                await asyncio.sleep(min(self.inter_key_delay_ms / 1000.0, 0.01))

    async def _dispatch_key_combination(self, combo_str: str) -> None:
        """Parses and dispatches key combinations (e.g. 'Control+A', 'Shift+Tab', 'Enter')."""
        parts = [p.strip() for p in combo_str.split("+") if p.strip()]
        if not parts:
            return

        modifiers = parts[:-1]
        main_key = parts[-1]

        # Modifier key mapping
        mod_keys = []
        for mod in modifiers:
            norm_mod = mod.capitalize()
            if norm_mod in ("Ctrl", "Control"):
                mod_keys.append("Control")
            elif norm_mod == "Shift":
                mod_keys.append("Shift")
            elif norm_mod in ("Alt", "Option"):
                mod_keys.append("Alt")
            elif norm_mod in ("Meta", "Command", "Cmd", "Win"):
                mod_keys.append("Meta")
            else:
                mod_keys.append(mod)

        # Press modifiers down
        for mod in mod_keys:
            await self._send_cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": mod})
            if hasattr(self.page, "keyboard") and hasattr(self.page.keyboard, "down"):
                await self.page.keyboard.down(mod)

        # Press and release main key
        await self._send_cdp("Input.dispatchKeyEvent", {"type": "keyDown", "key": main_key, "text": main_key})
        await self._send_cdp("Input.dispatchKeyEvent", {"type": "keyUp", "key": main_key, "text": main_key})
        if hasattr(self.page, "keyboard"):
            if hasattr(self.page.keyboard, "press"):
                await self.page.keyboard.press(combo_str if not mod_keys else main_key)

        # Release modifiers up in reverse order
        for mod in reversed(mod_keys):
            await self._send_cdp("Input.dispatchKeyEvent", {"type": "keyUp", "key": mod})
            if hasattr(self.page, "keyboard") and hasattr(self.page.keyboard, "up"):
                await self.page.keyboard.up(mod)
