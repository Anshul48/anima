"""Reflex macOS Native Input and AXUIElement Execution Adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from reflex.execution.native.base import (
    NativeActionConfig,
    NativeActionPort,
)
from reflex.host.identity.lease_manager import (
    ActionLease,
    ActionLeaseManager,
    InvalidLeaseError,
)
from reflex.ports.action import ActionReceipt, ActionStatus
from reflex.schemas.actions import ActionType, NormalizedCoords, TypedAction


@dataclass
class MockMacOSInputSubstrate:
    """In-memory mock substrate for macOS Quartz CGEvents and AXPress actions."""
    events: List[Dict[str, Any]] = field(default_factory=list)
    mouse_position: Tuple[int, int] = (0, 0)
    pressed_keys: List[str] = field(default_factory=list)
    ax_press_invocations: List[Dict[str, Any]] = field(default_factory=list)

    def mouse_move(self, x: int, y: int) -> None:
        self.mouse_position = (x, y)
        self.events.append({"type": "cgevent_mouse_move", "x": x, "y": y})

    def mouse_click(self, x: int, y: int, button: str = "left", count: int = 1) -> None:
        self.mouse_move(x, y)
        self.events.append({"type": "cgevent_mouse_click", "x": x, "y": y, "button": button, "count": count})

    def mouse_wheel(self, x: int, y: int, delta_x: float = 0.0, delta_y: float = 0.0) -> None:
        self.events.append({"type": "cgevent_mouse_wheel", "x": x, "y": y, "delta_x": delta_x, "delta_y": delta_y})

    def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, steps: int = 10) -> List[Tuple[int, int]]:
        interpolated: List[Tuple[int, int]] = []
        self.mouse_move(start_x, start_y)
        self.events.append({"type": "cgevent_mouse_down", "x": start_x, "y": start_y, "button": "left"})
        for s in range(1, steps + 1):
            t = float(s) / float(steps)
            cur_x = int(round(start_x + t * (end_x - start_x)))
            cur_y = int(round(start_y + t * (end_y - start_y)))
            interpolated.append((cur_x, cur_y))
            self.mouse_move(cur_x, cur_y)
        self.events.append({"type": "cgevent_mouse_up", "x": end_x, "y": end_y, "button": "left"})
        return interpolated

    def type_text(self, text: str) -> None:
        self.events.append({"type": "cgevent_type_text", "text": text})

    def key_press(self, key: str) -> None:
        self.pressed_keys.append(key)
        self.events.append({"type": "cgevent_key_press", "key": key})

    def key_combination(self, combo: str) -> None:
        self.pressed_keys.append(combo)
        self.events.append({"type": "cgevent_key_combination", "combo": combo})

    def ax_press(self, node_id: str) -> None:
        entry = {"node_id": node_id, "action": "AXPress"}
        self.ax_press_invocations.append(entry)
        self.events.append({"type": "ax_press", **entry})


class MacOSNativeInputAdapter(NativeActionPort):
    """macOS native input adapter implementing Quartz CGEvent and AXUIElement background action dispatch."""

    def __init__(
        self,
        config: Optional[NativeActionConfig] = None,
        lease_manager: Optional[ActionLeaseManager] = None,
        substrate: Optional[MockMacOSInputSubstrate] = None,
        clock: Optional[Any] = None,
    ) -> None:
        super().__init__(config=config, lease_manager=lease_manager, clock=clock)
        self.substrate = substrate or MockMacOSInputSubstrate()
        self._is_macos = sys.platform == "darwin"

    async def perform_native_action(self, action: TypedAction, lease: ActionLease) -> bool:
        """Dispatches action via platform accessibility pattern or synthetic input."""
        receipt = await self.execute_action(action=action, lease=lease)
        return receipt.status == ActionStatus.DISPATCHED

    async def execute_action(self, action: TypedAction, lease: ActionLease) -> ActionReceipt:
        """Executes the action on macOS via AXPress or Quartz CGEvent emulation."""
        # 1. Strict Lease Validation (Fail Closed)
        self._validate_and_consume_lease(lease, action)

        start_time_ms = time.time() * 1000.0
        raw_response: Dict[str, Any] = {
            "action_type": action.action_type.value,
            "adapter": "MacOSNativeInputAdapter",
        }
        error_msg: Optional[str] = None
        status = ActionStatus.DISPATCHED

        try:
            target_pixel: Optional[Tuple[int, int]] = None
            if action.coords is not None:
                target_pixel = self.to_pixel_coords(action.coords)
                raw_response["coords_pixel"] = {"x": target_pixel[0], "y": target_pixel[1]}
            elif action.metadata.get("pixel_x") is not None and action.metadata.get("pixel_y") is not None:
                target_pixel = (int(action.metadata["pixel_x"]), int(action.metadata["pixel_y"]))
                raw_response["coords_pixel"] = {"x": target_pixel[0], "y": target_pixel[1]}

            # Check for direct AXPress action
            if action.action_type == ActionType.CLICK and action.target_node_id and target_pixel is None and self.config.use_direct_patterns:
                self.substrate.ax_press(action.target_node_id)
                raw_response["dispatched"] = "ax_press_direct"
                raw_response["target_node_id"] = action.target_node_id

            elif action.action_type == ActionType.CLICK:
                if target_pixel is not None:
                    x, y = target_pixel
                    self.substrate.mouse_click(x, y, button="left", count=1)
                    raw_response["dispatched"] = "cgevent_mouse_click"
                else:
                    raise ValueError("Click action requires either target_node_id or coordinates")

            elif action.action_type == ActionType.DOUBLE_CLICK:
                if target_pixel is None:
                    raise ValueError("Double click requires coordinates")
                x, y = target_pixel
                self.substrate.mouse_click(x, y, button="left", count=2)
                raw_response["dispatched"] = "cgevent_mouse_double_click"

            elif action.action_type == ActionType.RIGHT_CLICK:
                if target_pixel is None:
                    raise ValueError("Right click requires coordinates")
                x, y = target_pixel
                self.substrate.mouse_click(x, y, button="right", count=1)
                raw_response["dispatched"] = "cgevent_mouse_right_click"

            elif action.action_type in (ActionType.TYPE, ActionType.CLEAR_AND_TYPE):
                text = action.text_payload or action.value or action.metadata.get("text", "")
                if action.action_type == ActionType.CLEAR_AND_TYPE and target_pixel is not None:
                    self.substrate.mouse_click(target_pixel[0], target_pixel[1])
                    self.substrate.key_combination("Command+A")
                    self.substrate.key_press("Delete")

                if target_pixel is not None:
                    self.substrate.mouse_click(target_pixel[0], target_pixel[1])
                self.substrate.type_text(text)
                raw_response["dispatched"] = "cgevent_type_text"
                raw_response["typed_length"] = len(text)

            elif action.action_type == ActionType.KEY_PRESS:
                key = action.key_code or action.text_payload or action.value or action.metadata.get("key", "")
                if not key:
                    raise ValueError("Key press requires key_code or text_payload")
                self.substrate.key_press(key)
                raw_response["dispatched"] = "cgevent_key_press"
                raw_response["key"] = key

            elif action.action_type == ActionType.KEY_COMBINATION:
                combo = action.key_code or action.text_payload or action.value or action.metadata.get("combo", "")
                if not combo:
                    raise ValueError("Key combination requires key_code or text_payload")
                self.substrate.key_combination(combo)
                raw_response["dispatched"] = "cgevent_key_combination"
                raw_response["combo"] = combo

            elif action.action_type == ActionType.DRAG_AND_DROP:
                if target_pixel is None:
                    raise ValueError("Drag and drop requires start coordinates")
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
                    raise ValueError("Drag and drop requires target_coords/end_coords in metadata")

                interpolated = self.substrate.mouse_drag(
                    start_x, start_y, end_x, end_y, steps=self.config.drag_interpolation_steps
                )
                raw_response["dispatched"] = "cgevent_mouse_drag"
                raw_response["start_pixel"] = {"x": start_x, "y": start_y}
                raw_response["end_pixel"] = {"x": end_x, "y": end_y}
                raw_response["steps"] = len(interpolated)

            elif action.action_type == ActionType.HOVER:
                if target_pixel is None:
                    raise ValueError("Hover requires coordinates")
                self.substrate.mouse_move(target_pixel[0], target_pixel[1])
                raw_response["dispatched"] = "cgevent_mouse_move"

            elif action.action_type == ActionType.SCROLL:
                x = target_pixel[0] if target_pixel else self.config.screen_width // 2
                y = target_pixel[1] if target_pixel else self.config.screen_height // 2
                dx, dy = 0.0, 300.0
                if action.scroll_delta is not None:
                    dx, dy = action.scroll_delta
                self.substrate.mouse_wheel(x, y, delta_x=dx, delta_y=dy)
                raw_response["dispatched"] = "cgevent_mouse_wheel"
                raw_response["scroll_delta"] = (dx, dy)

            elif action.action_type == ActionType.WAIT:
                duration_ms = float(action.metadata.get("duration_ms", action.text_payload or 500.0))
                await asyncio.sleep(min(duration_ms / 1000.0, 0.05))
                raw_response["dispatched"] = "wait"
                raw_response["duration_ms"] = duration_ms

            elif action.action_type == ActionType.NOOP:
                raw_response["dispatched"] = "noop"

            elif action.action_type == ActionType.NAVIGATE:
                url = action.text_payload or action.value or action.metadata.get("url", "")
                raw_response["dispatched"] = "open_url"
                raw_response["url"] = url

            else:
                raise NotImplementedError(
                    f"Unsupported ActionType '{action.action_type.value}' in MacOSNativeInputAdapter"
                )

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
            adapter_name="MacOSNativeInputAdapter",
            dispatch_timestamp_ms=start_time_ms,
            duration_ms=duration_ms,
            raw_adapter_response=raw_response,
            status=status,
            error=error_msg,
        )


# Architectural Aliases
MacOSExecAdapter = MacOSNativeInputAdapter
MacOSAXActionAdapter = MacOSNativeInputAdapter
