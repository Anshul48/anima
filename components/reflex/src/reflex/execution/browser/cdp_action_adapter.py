from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
import time
from typing import Any, Dict, Optional, Set

from reflex.host.identity.lease_manager import ActionLease, ActionLeaseManager, InvalidLeaseError
from reflex.integrations.fakes.fake_browser import FakeBrowserPage
from reflex.ports.action import ActionPort, ActionReceipt, ActionStatus
from reflex.schemas.actions import ActionType, NormalizedCoords, TypedAction
from reflex.schemas.identity import ActionIdentity


class BrowserActionPort(ActionPort, ABC):
    """Abstract port for executing actions under the authority of an ActionLease."""

    @abstractmethod
    async def execute_action(self, action: TypedAction, lease: ActionLease) -> ActionReceipt:
        """Executes the action under the authority of an active lease."""
        ...

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        """Dispatch only a registered, kernel-issued action; never mint authority."""
        manager = getattr(self, "lease_manager", None)
        if manager is None:
            raise InvalidLeaseError("Dispatch requires its issuing ActionLeaseManager")
        lease = manager.get_lease_by_action_id(identity.action_id)
        if lease is None or lease.identity != identity:
            raise InvalidLeaseError("No issued lease matches the dispatch identity")
        receipt = await self.execute_action(action=action, lease=lease)
        return receipt.to_dict()


class CDPActionAdapter(BrowserActionPort):
    """Primary browser-native direct action adapter for CDP / Playwright DOM dispatch."""

    def __init__(
        self,
        page: Any = None,
        cdp_session: Any = None,
        lease_manager: Optional[ActionLeaseManager] = None,
        options: Optional[Dict[str, Any]] = None,
    ):
        self.page = page if page is not None else FakeBrowserPage()
        self.cdp_session = cdp_session
        self.lease_manager = lease_manager
        self.options = options or {}
        self._consumed_leases: Set[str] = set()
        self._dispatched_identities: Set[str] = set()

    def _resolve_locator(self, target_node_id: Optional[str], target_label: Optional[str] = None) -> Any:
        """Resolves target element into a Playwright Locator or FakeElementLocator."""
        if not target_node_id and not target_label:
            return None

        if target_node_id:
            raw_id = str(target_node_id).strip()
            # If selector syntax is present
            if any(raw_id.startswith(p) for p in ("#", ".", "[", "//", "xpath=", "css=", "text=", "role=")):
                return self.page.locator(raw_id)
            # Default ID or backend node ID targeting
            if hasattr(self.page, "locator"):
                try:
                    return self.page.locator(f"#{raw_id}")
                except Exception:
                    return self.page.locator(raw_id)

        if target_label:
            if hasattr(self.page, "get_by_text"):
                try:
                    return self.page.get_by_text(target_label)
                except Exception:
                    pass
            if hasattr(self.page, "locator"):
                return self.page.locator(f"text={target_label}")

        return None

    def _get_viewport_dimensions(self) -> tuple[int, int]:
        """Extracts (width, height) viewport size."""
        if hasattr(self.page, "viewport_size") and self.page.viewport_size:
            v = self.page.viewport_size
            return int(v.get("width", 1280)), int(v.get("height", 800))
        return 1280, 800

    def _resolve_pixel_coords(self, coords: Optional[NormalizedCoords]) -> Optional[tuple[int, int]]:
        """Converts normalized coords to viewport pixel coordinates."""
        if coords is None:
            return None
        w, h = self._get_viewport_dimensions()
        return coords.to_pixel(w, h)

    def _validate_and_consume_lease(self, lease: Optional[ActionLease], action: TypedAction) -> None:
        if self.lease_manager is None:
            raise InvalidLeaseError("Execution requires its issuing ActionLeaseManager")
        self.lease_manager.consume_lease(lease, action=action)

    async def execute_action(self, action: TypedAction, lease: ActionLease) -> ActionReceipt:
        """Executes the action deterministically on the target DOM via CDP / Playwright."""
        # 1. Strict Lease Validation (Fail Closed)
        self._validate_and_consume_lease(lease, action)

        start_time_ms = time.time() * 1000.0
        raw_response: Dict[str, Any] = {
            "action_type": action.action_type.value,
            "target_node_id": action.target_node_id,
            "target_label": action.target_label,
        }
        error_msg: Optional[str] = None
        status = ActionStatus.DISPATCHED

        try:
            locator = self._resolve_locator(action.target_node_id, action.target_label)
            coords_px = self._resolve_pixel_coords(action.coords)
            force = action.metadata.get("force", False)

            if action.action_type == ActionType.CLICK:
                if locator is not None:
                    if hasattr(locator, "scroll_into_view_if_needed"):
                        await locator.scroll_into_view_if_needed()
                    await locator.click(force=force)
                    raw_response["dispatched_method"] = "locator.click"
                elif coords_px is not None:
                    await self.page.mouse.click(coords_px[0], coords_px[1])
                    raw_response["dispatched_method"] = "mouse.click"
                    raw_response["coords_px"] = coords_px
                else:
                    raise ValueError("Click action requires either target locator or coordinates")

            elif action.action_type == ActionType.DOUBLE_CLICK:
                if locator is not None:
                    if hasattr(locator, "scroll_into_view_if_needed"):
                        await locator.scroll_into_view_if_needed()
                    await locator.dblclick(force=force)
                    raw_response["dispatched_method"] = "locator.dblclick"
                elif coords_px is not None:
                    await self.page.mouse.dblclick(coords_px[0], coords_px[1])
                    raw_response["dispatched_method"] = "mouse.dblclick"
                    raw_response["coords_px"] = coords_px
                else:
                    raise ValueError("Double click action requires either target locator or coordinates")

            elif action.action_type == ActionType.RIGHT_CLICK:
                if locator is not None:
                    if hasattr(locator, "scroll_into_view_if_needed"):
                        await locator.scroll_into_view_if_needed()
                    await locator.click(button="right", force=force)
                    raw_response["dispatched_method"] = "locator.click(button='right')"
                elif coords_px is not None:
                    await self.page.mouse.click(coords_px[0], coords_px[1], button="right")
                    raw_response["dispatched_method"] = "mouse.click(button='right')"
                    raw_response["coords_px"] = coords_px
                else:
                    raise ValueError("Right click action requires either target locator or coordinates")

            elif action.action_type == ActionType.TYPE:
                text = action.text_payload or action.metadata.get("text", "")
                if locator is not None:
                    if hasattr(locator, "fill"):
                        await locator.fill(text)
                        raw_response["dispatched_method"] = "locator.fill"
                    elif hasattr(locator, "type"):
                        await locator.type(text)
                        raw_response["dispatched_method"] = "locator.type"
                else:
                    await self.page.keyboard.type(text)
                    raw_response["dispatched_method"] = "keyboard.type"
                raw_response["typed_length"] = len(text)

            elif action.action_type == ActionType.KEY_PRESS:
                key = action.key_code or action.text_payload or action.metadata.get("key", "")
                if not key:
                    raise ValueError("Key press action requires key_code or text_payload")
                if locator is not None and hasattr(locator, "press"):
                    await locator.press(key)
                    raw_response["dispatched_method"] = "locator.press"
                else:
                    await self.page.keyboard.press(key)
                    raw_response["dispatched_method"] = "keyboard.press"
                raw_response["key_pressed"] = key

            elif action.action_type == ActionType.SCROLL:
                if locator is not None and hasattr(locator, "scroll_into_view_if_needed"):
                    await locator.scroll_into_view_if_needed()
                    raw_response["dispatched_method"] = "locator.scroll_into_view_if_needed"
                elif action.scroll_delta is not None:
                    dx, dy = action.scroll_delta
                    if hasattr(self.page.mouse, "wheel"):
                        await self.page.mouse.wheel(dx, dy)
                    elif hasattr(self.page, "evaluate"):
                        await self.page.evaluate(f"window.scrollBy({dx}, {dy})")
                    raw_response["dispatched_method"] = "mouse.wheel"
                    raw_response["scroll_delta"] = (dx, dy)
                else:
                    # Default downward page scroll
                    if hasattr(self.page.mouse, "wheel"):
                        await self.page.mouse.wheel(0, 300)
                    elif hasattr(self.page, "evaluate"):
                        await self.page.evaluate("window.scrollBy(0, 300)")
                    raw_response["dispatched_method"] = "default_scroll"

            elif action.action_type == ActionType.DRAG_AND_DROP:
                target_selector = (
                    action.metadata.get("target_node_id")
                    or action.metadata.get("target_selector")
                    or action.metadata.get("target_locator")
                )
                if locator is not None and target_selector:
                    target_loc = self._resolve_locator(str(target_selector))
                    if hasattr(locator, "drag_to") and target_loc is not None:
                        await locator.drag_to(target_loc)
                        raw_response["dispatched_method"] = "locator.drag_to"
                    elif hasattr(self.page, "drag_and_drop"):
                        source_sel = action.target_node_id or action.metadata.get("source_selector", "")
                        await self.page.drag_and_drop(source_sel, str(target_selector))
                        raw_response["dispatched_method"] = "page.drag_and_drop"
                elif coords_px is not None:
                    target_coords = action.metadata.get("target_coords") or action.metadata.get("end_coords")
                    if isinstance(target_coords, dict):
                        norm_target = NormalizedCoords.from_dict(target_coords)
                        t_px = self._resolve_pixel_coords(norm_target)
                    elif isinstance(target_coords, (tuple, list)):
                        t_px = (int(target_coords[0]), int(target_coords[1]))
                    else:
                        raise ValueError("Drag and drop with coordinates requires target_coords in metadata")
                    assert t_px is not None
                    await self.page.mouse.move(coords_px[0], coords_px[1])
                    await self.page.mouse.down()
                    await self.page.mouse.move(t_px[0], t_px[1])
                    await self.page.mouse.up()
                    raw_response["dispatched_method"] = "mouse.drag_coords"
                    raw_response["from_px"] = coords_px
                    raw_response["to_px"] = t_px
                else:
                    raise ValueError("Drag and drop requires source and target locators or coordinates")

            elif action.action_type == ActionType.HOVER:
                if locator is not None:
                    if hasattr(locator, "hover"):
                        await locator.hover()
                        raw_response["dispatched_method"] = "locator.hover"
                elif coords_px is not None:
                    await self.page.mouse.move(coords_px[0], coords_px[1])
                    raw_response["dispatched_method"] = "mouse.move"
                    raw_response["coords_px"] = coords_px
                else:
                    raise ValueError("Hover action requires either target locator or coordinates")

            elif action.action_type == ActionType.WAIT:
                duration_ms = action.metadata.get("duration_ms")
                if duration_ms is None and action.text_payload:
                    try:
                        duration_ms = float(action.text_payload)
                    except ValueError:
                        duration_ms = 500.0
                duration_ms = float(duration_ms if duration_ms is not None else 500.0)

                if hasattr(self.page, "wait_for_timeout"):
                    await self.page.wait_for_timeout(duration_ms)
                else:
                    await asyncio.sleep(duration_ms / 1000.0)
                raw_response["dispatched_method"] = "wait_for_timeout"
                raw_response["duration_ms"] = duration_ms

            elif action.action_type == ActionType.NOOP:
                raw_response["dispatched_method"] = "noop"

            elif action.action_type == ActionType.NAVIGATE:
                url = action.text_payload or action.metadata.get("url", "")
                if not url:
                    raise ValueError("Navigate action requires target URL in text_payload or metadata")
                await self.page.goto(url)
                raw_response["dispatched_method"] = "page.goto"
                raw_response["url"] = url

            else:
                raise NotImplementedError(f"Unsupported ActionType '{action.action_type.value}' in CDPActionAdapter")

        except InvalidLeaseError:
            # Re-raise lease errors directly to preserve fail-closed semantics
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
            adapter_name="CDPActionAdapter",
            dispatch_timestamp_ms=start_time_ms,
            duration_ms=duration_ms,
            raw_adapter_response=raw_response,
            status=status,
            error=error_msg,
        )
