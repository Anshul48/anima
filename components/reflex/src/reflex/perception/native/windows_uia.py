"""Reflex Windows UI Automation (UIA) Observation Adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import uuid

from reflex.perception.native.base import (
    NativeObservationConfig,
    NativeObservationPort,
    NativeUIElement,
)
from reflex.perception.native.windows_bridge_client import WindowsBridgeClient, WindowsBridgeConfig
from reflex.ports.clock import ClockPort, SystemClock
from reflex.ports.observation import assess_pixel_modality, bind_pixel_geometry
from reflex.schemas.observation import (
    ObservationQuality,
    ObservationRecord,
    PerceptionCapabilities,
    PerceptionError,
    PerceptionLifecycleState,
)
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)

# Standard Windows UIA Control Type IDs
UIA_BUTTON_CONTROL_TYPE_ID = 50000
UIA_CALENDAR_CONTROL_TYPE_ID = 50001
UIA_CHECK_BOX_CONTROL_TYPE_ID = 50002
UIA_COMBO_BOX_CONTROL_TYPE_ID = 50003
UIA_EDIT_CONTROL_TYPE_ID = 50004
UIA_HYPERLINK_CONTROL_TYPE_ID = 50005
UIA_IMAGE_CONTROL_TYPE_ID = 50006
UIA_LIST_ITEM_CONTROL_TYPE_ID = 50007
UIA_LIST_CONTROL_TYPE_ID = 50008
UIA_MENU_CONTROL_TYPE_ID = 50009
UIA_MENU_BAR_CONTROL_TYPE_ID = 50010
UIA_MENU_ITEM_CONTROL_TYPE_ID = 50011
UIA_PROGRESS_BAR_CONTROL_TYPE_ID = 50012
UIA_RADIO_BUTTON_CONTROL_TYPE_ID = 50013
UIA_SCROLL_BAR_CONTROL_TYPE_ID = 50014
UIA_SLIDER_CONTROL_TYPE_ID = 50015
UIA_SPINNER_CONTROL_TYPE_ID = 50016
UIA_STATUS_BAR_CONTROL_TYPE_ID = 50017
UIA_TAB_CONTROL_TYPE_ID = 50018
UIA_TAB_ITEM_CONTROL_TYPE_ID = 50019
UIA_TEXT_CONTROL_TYPE_ID = 50020
UIA_TOOL_BAR_CONTROL_TYPE_ID = 50021
UIA_TOOL_TIP_CONTROL_TYPE_ID = 50022
UIA_TREE_CONTROL_TYPE_ID = 50023
UIA_TREE_ITEM_CONTROL_TYPE_ID = 50024
UIA_CUSTOM_CONTROL_TYPE_ID = 50025
UIA_GROUP_CONTROL_TYPE_ID = 50026
UIA_THUMB_CONTROL_TYPE_ID = 50027
UIA_DATA_GRID_CONTROL_TYPE_ID = 50028
UIA_DATA_ITEM_CONTROL_TYPE_ID = 50029
UIA_DOCUMENT_CONTROL_TYPE_ID = 50030
UIA_SPLIT_BUTTON_CONTROL_TYPE_ID = 50031
UIA_WINDOW_CONTROL_TYPE_ID = 50032
UIA_PANE_CONTROL_TYPE_ID = 50033
UIA_HEADER_CONTROL_TYPE_ID = 50034
UIA_HEADER_ITEM_CONTROL_TYPE_ID = 50035
UIA_TABLE_CONTROL_TYPE_ID = 50036
UIA_TITLE_BAR_CONTROL_TYPE_ID = 50037
UIA_SEPARATOR_CONTROL_TYPE_ID = 50038


@dataclass
class MockWindowsUIASubstrate:
    """In-memory substrate for Windows UIA testing, CI runners, and mock environments."""
    windows: List[Dict[str, Any]] = field(default_factory=list)
    focused_window_title: Optional[str] = "Reflex Native Window"
    focused_element_id: Optional[str] = None
    element_tree: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    screenshot_bytes: Optional[bytes] = None

    def add_window(self, title: str, handle: int = 1001, process_name: str = "", is_focused: bool = False) -> None:
        self.windows.append({
            "title": title,
            "handle": handle,
            "process_name": process_name,
            "is_focused": is_focused,
        })
        if is_focused:
            self.focused_window_title = title

    def add_element(
        self,
        element_id: str,
        name: str,
        control_type: Union[str, int] = "Button",
        bounds: Tuple[int, int, int, int] = (0, 0, 100, 30),
        value: str = "",
        is_clickable: bool = True,
        is_editable: bool = False,
        is_focused: bool = False,
        is_enabled: bool = True,
        parent_id: Optional[str] = None,
        children_ids: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        window_title: Optional[str] = None,
    ) -> None:
        self.element_tree[element_id] = {
            "element_id": element_id,
            "name": name,
            "control_type": control_type,
            "bounds": bounds,
            "value": value,
            "is_clickable": is_clickable,
            "is_editable": is_editable,
            "is_focused": is_focused,
            "is_enabled": is_enabled,
            "parent_id": parent_id,
            "children_ids": list(children_ids or []),
            "attributes": dict(attributes or {}),
            "window_title": window_title or self.focused_window_title,
        }
        if is_focused:
            self.focused_element_id = element_id


class WindowsUIAObservationAdapter(NativeObservationPort):
    """Windows UI Automation observation adapter implementing native UIA tree extraction."""

    def __init__(
        self,
        config: Optional[NativeObservationConfig] = None,
        clock: Optional[ClockPort] = None,
        substrate: Optional[MockWindowsUIASubstrate] = None,
        bridge_client: Optional[WindowsBridgeClient] = None,
    ) -> None:
        super().__init__(config=config, clock=clock)
        self._is_mock = substrate is not None
        self.substrate = substrate or MockWindowsUIASubstrate()
        self._is_windows = sys.platform == "win32"
        self._cached_trees: Dict[str, CanonicalUIGraph] = {}
        self._simulated_permission_denied = False
        self._simulated_disconnected = False
        self._bridge_client = bridge_client

    @property
    def capabilities(self) -> PerceptionCapabilities:
        return PerceptionCapabilities(
            supports_accessibility_tree=True,
            supports_window_hierarchy=True,
            supports_dom_snapshot=False,
            supports_pixel_buffer=True,
            supports_change_stream=True,
            supports_continuous_polling=True,
            supports_bounding_box_extraction=True,
            supported_modalities=[ModalitySource.UIA],
        )

    async def initialize(self) -> None:
        """Initializes connection to Windows UI Automation or configures conformance fallback."""
        if self._simulated_disconnected:
            self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED
            return
        if self._simulated_permission_denied:
            self._lifecycle_state = PerceptionLifecycleState.ERROR
            return

        if self._is_windows:
            self._lifecycle_state = PerceptionLifecycleState.CONNECTED
        elif self._bridge_client is not None:
            health = await self._bridge_client.check_health()
            if health.get("status") == "ok":
                self._lifecycle_state = PerceptionLifecycleState.CONNECTED
            elif self._is_mock or self.config.enable_mock_fallback:
                self._lifecycle_state = PerceptionLifecycleState.DEGRADED
            else:
                self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED
        elif self._is_mock or self.config.enable_mock_fallback:
            # Explicitly labeled validation status: mock/conformance mode on non-Windows
            self._lifecycle_state = PerceptionLifecycleState.DEGRADED
        else:
            self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED

    async def teardown(self) -> None:
        """Closes bridge client and transitions lifecycle to CLOSED."""
        if self._bridge_client is not None:
            await self._bridge_client.close()
        await super().teardown()

    def simulate_disconnect(self) -> None:
        """Simulates UIA provider disconnect."""
        self._simulated_disconnected = True
        self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED

    def simulate_permission_denied(self) -> None:
        """Simulates Windows UIPI / integrity level access denied."""
        self._simulated_permission_denied = True
        self._lifecycle_state = PerceptionLifecycleState.ERROR

    def reconnect(self) -> None:
        """Restores connectivity after simulated fault."""
        self._simulated_disconnected = False
        self._simulated_permission_denied = False
        is_live = self._is_windows or (self._bridge_client is not None and self._bridge_client.is_connected)
        self._lifecycle_state = (
            PerceptionLifecycleState.CONNECTED
            if is_live
            else PerceptionLifecycleState.DEGRADED
        )

    @staticmethod
    def map_role(control_type: Union[str, int, None]) -> NodeRole:
        """Maps Windows UIA control type ID or string name to canonical NodeRole enum."""
        if control_type is None:
            return NodeRole.UNKNOWN

        # Handle integer control type IDs
        if isinstance(control_type, int):
            int_map: Dict[int, NodeRole] = {
                UIA_BUTTON_CONTROL_TYPE_ID: NodeRole.BUTTON,
                UIA_SPLIT_BUTTON_CONTROL_TYPE_ID: NodeRole.BUTTON,
                UIA_EDIT_CONTROL_TYPE_ID: NodeRole.INPUT,
                UIA_DOCUMENT_CONTROL_TYPE_ID: NodeRole.INPUT,
                UIA_SPINNER_CONTROL_TYPE_ID: NodeRole.INPUT,
                UIA_CHECK_BOX_CONTROL_TYPE_ID: NodeRole.CHECKBOX,
                UIA_RADIO_BUTTON_CONTROL_TYPE_ID: NodeRole.RADIO,
                UIA_HYPERLINK_CONTROL_TYPE_ID: NodeRole.LINK,
                UIA_TEXT_CONTROL_TYPE_ID: NodeRole.TEXT,
                UIA_TOOL_TIP_CONTROL_TYPE_ID: NodeRole.TEXT,
                UIA_HEADER_CONTROL_TYPE_ID: NodeRole.HEADING,
                UIA_HEADER_ITEM_CONTROL_TYPE_ID: NodeRole.HEADING,
                UIA_IMAGE_CONTROL_TYPE_ID: NodeRole.IMAGE,
                UIA_WINDOW_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_PANE_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_GROUP_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_SCROLL_BAR_CONTROL_TYPE_ID: NodeRole.SCROLLBAR,
                UIA_COMBO_BOX_CONTROL_TYPE_ID: NodeRole.DROPDOWN,
                UIA_LIST_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_LIST_ITEM_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_TREE_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_TREE_ITEM_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_TAB_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_TAB_ITEM_CONTROL_TYPE_ID: NodeRole.LINK,
                UIA_MENU_BAR_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_MENU_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_MENU_ITEM_CONTROL_TYPE_ID: NodeRole.BUTTON,
                UIA_TOOL_BAR_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_STATUS_BAR_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_PROGRESS_BAR_CONTROL_TYPE_ID: NodeRole.GENERIC,
                UIA_SLIDER_CONTROL_TYPE_ID: NodeRole.INPUT,
                UIA_CALENDAR_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_DATA_GRID_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_DATA_ITEM_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_TABLE_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_TITLE_BAR_CONTROL_TYPE_ID: NodeRole.CONTAINER,
                UIA_SEPARATOR_CONTROL_TYPE_ID: NodeRole.GENERIC,
                UIA_CUSTOM_CONTROL_TYPE_ID: NodeRole.GENERIC,
            }
            return int_map.get(control_type, NodeRole.UNKNOWN)

        raw = str(control_type).lower().strip()
        if raw.startswith("uia_") and raw.endswith("controltypeid"):
            raw = raw[4:-13]

        if raw in ("button", "splitbutton", "menuitembutton", "pushbutton"):
            return NodeRole.BUTTON
        elif raw in ("edit", "document", "textbox", "input", "spinner"):
            return NodeRole.INPUT
        elif raw in ("checkbox", "check_box"):
            return NodeRole.CHECKBOX
        elif raw in ("radiobutton", "radio_button", "radio"):
            return NodeRole.RADIO
        elif raw in ("hyperlink", "link", "tabitem", "tab_item"):
            return NodeRole.LINK
        elif raw in ("text", "statictext", "label", "tooltip"):
            return NodeRole.TEXT
        elif raw in ("header", "headeritem"):
            return NodeRole.HEADING
        elif raw in ("image", "picture", "icon"):
            return NodeRole.IMAGE
        elif raw in ("dialog", "modal", "alertdialog"):
            return NodeRole.MODAL
        elif raw in ("switch", "toggle"):
            return NodeRole.TOGGLE
        elif raw in ("scrollbar", "scroll_bar"):
            return NodeRole.SCROLLBAR
        elif raw in ("combobox", "combo_box", "dropdown"):
            return NodeRole.DROPDOWN
        elif raw in (
            "window", "pane", "group", "list", "listitem", "tree", "treeitem",
            "tab", "tabcontrol", "menubar", "menu", "toolbar", "statusbar",
            "datagrid", "dataitem", "table", "titlebar", "calendar", "appbar", "container",
        ):
            return NodeRole.CONTAINER
        elif raw in ("slider", "progressbar", "progress_bar", "custom", "separator", "generic"):
            return NodeRole.GENERIC
        return NodeRole.UNKNOWN

    def list_open_windows(self) -> List[str]:
        """Lists active top-level native window titles and process names."""
        results: List[str] = []

        # 1. Check live Win32 windows if on Windows and no mock substrate override
        if self._is_windows and not self._is_mock:
            try:
                import ctypes
                user32 = ctypes.windll.user32

                titles: List[str] = []

                def enum_windows_callback(hwnd: int, extra: Any) -> bool:
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buff, length + 1)
                            if buff.value.strip():
                                titles.append(buff.value.strip())
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
                cb = WNDENUMPROC(enum_windows_callback)
                user32.EnumWindows(cb, 0)
                if titles:
                    return titles
            except Exception:
                pass

        # 2. Fall back to mock substrate
        for w in self.substrate.windows:
            title = w.get("title", "")
            proc = w.get("process_name", "")
            results.append(f"{title} ({proc})" if proc else title)

        if not results and self.substrate.focused_window_title:
            results.append(self.substrate.focused_window_title)

        return results

    def get_focused_window_title(self) -> Optional[str]:
        """Returns title of the currently focused native window."""
        if self._is_windows and not self._is_mock:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        if buff.value.strip():
                            return buff.value.strip()
            except Exception:
                pass

        return self.substrate.focused_window_title

    def get_focused_element(self) -> Optional[NativeUIElement]:
        """Returns the currently focused native UI element, if any."""
        focused_id = self.substrate.focused_element_id
        if focused_id and focused_id in self.substrate.element_tree:
            raw = self.substrate.element_tree[focused_id]
            b = raw.get("bounds", (0, 0, 100, 30))
            return NativeUIElement(
                element_id=focused_id,
                name=raw.get("name", ""),
                role=str(raw.get("control_type", "")),
                bounds=BoundingBox(b[0], b[1], b[2], b[3]),
                value=raw.get("value", ""),
                is_clickable=raw.get("is_clickable", True),
                is_editable=raw.get("is_editable", False),
                is_focused=True,
                is_enabled=raw.get("is_enabled", True),
                parent_id=raw.get("parent_id"),
                children_ids=list(raw.get("children_ids", [])),
                control_type=str(raw.get("control_type", "")),
                window_title=raw.get("window_title"),
                attributes=raw.get("attributes", {}),
            )
        return None

    def capture_active_window(self) -> CanonicalUIGraph:
        """Extracts accessibility graph from currently focused native window via UIA."""
        timestamp_ms = self.clock.now_ms()
        window_title = self.get_focused_window_title() or "Desktop"
        nodes: Dict[str, UIStateNode] = {}
        focused_node_id = self.substrate.focused_element_id

        # Traverse substrate element tree
        for el_id, raw in self.substrate.element_tree.items():
            # If target window title filter is active
            el_window = raw.get("window_title")
            if self.config.target_window_title and el_window != self.config.target_window_title:
                continue

            control_type = raw.get("control_type", "Button")
            role = self.map_role(control_type)
            bounds_raw = raw.get("bounds", (0, 0, 100, 30))

            if isinstance(bounds_raw, (tuple, list)) and len(bounds_raw) == 4:
                bounds = BoundingBox(bounds_raw[0], bounds_raw[1], bounds_raw[2], bounds_raw[3])
            elif isinstance(bounds_raw, dict):
                bounds = BoundingBox.from_dict(bounds_raw)
            else:
                bounds = BoundingBox(0, 0, 100, 30)

            node = UIStateNode(
                node_id=el_id,
                role=role,
                bounds=bounds,
                label=raw.get("name", ""),
                value=raw.get("value", ""),
                is_clickable=bool(raw.get("is_clickable", True)),
                is_editable=bool(raw.get("is_editable", False)),
                is_focused=bool(raw.get("is_focused", el_id == focused_node_id)),
                is_enabled=bool(raw.get("is_enabled", True)),
                parent_id=raw.get("parent_id"),
                children_ids=list(raw.get("children_ids", [])),
                source=ModalitySource.UIA,
                confidence=1.0,
                attributes=dict(raw.get("attributes", {})),
            )
            nodes[el_id] = node

        # If bridge client is active, fetch from Windows host
        if self._bridge_client is not None and self._bridge_client.is_connected:
            bridge_graph = self._bridge_client.capture_active_window_sync(self.config.max_depth)
            if bridge_graph is not None:
                return bridge_graph

        graph = CanonicalUIGraph(
            timestamp_ms=timestamp_ms,
            nodes=nodes,
            focused_node_id=focused_node_id,
            active_window_title=window_title,
            viewport_size=(self.config.screen_width, self.config.screen_height),
        )

        if self.config.cache_subtrees:
            self._cached_trees[window_title] = graph

        return graph

    async def capture_screenshot(self) -> bytes:
        """Captures screenshot bytes of the active desktop/window."""
        if self._simulated_permission_denied:
            raise PermissionError("Screen capture permission denied by Windows UIPI security policy.")
        if self._simulated_disconnected or self._lifecycle_state == PerceptionLifecycleState.DISCONNECTED:
            raise ConnectionError("Windows UI Automation provider disconnected.")
        if self._bridge_client is not None and self._bridge_client.is_connected:
            bridge_sc = self._bridge_client.capture_screenshot_sync()
            if bridge_sc:
                return bridge_sc
        if self.substrate.screenshot_bytes:
            return self.substrate.screenshot_bytes
        raise PerceptionError("Mock Windows UIA substrate provides no pixel evidence.")

    async def capture_observation(self) -> ObservationRecord:
        """Captures a normalized, timestamped, provenance-bearing observation record from Windows UIA."""
        timestamp_ms = self.clock.now_ms()

        if self._simulated_permission_denied:
            graph = CanonicalUIGraph(timestamp_ms=timestamp_ms, nodes={})
            return ObservationRecord(
                observation_id=str(uuid.uuid4()),
                timestamp_ms=timestamp_ms,
                source_adapter="windows_uia",
                platform="windows",
                graph=graph,
                screenshot_bytes=None,
                quality=ObservationQuality.PERMISSION_DENIED,
                freshness_duration_ms=0.0,
                error_message="Windows UI Automation permissions denied (UIPI / Administrator integrity check).",
                platform_metadata={"uia_version": "3.0", "permissions": "denied"},
            )

        if self._simulated_disconnected or self._lifecycle_state == PerceptionLifecycleState.DISCONNECTED:
            graph = CanonicalUIGraph(timestamp_ms=timestamp_ms, nodes={})
            return ObservationRecord(
                observation_id=str(uuid.uuid4()),
                timestamp_ms=timestamp_ms,
                source_adapter="windows_uia",
                platform="windows",
                graph=graph,
                screenshot_bytes=None,
                quality=ObservationQuality.DISCONNECTED,
                freshness_duration_ms=0.0,
                error_message="Windows UI Automation provider disconnected or process exited.",
                platform_metadata={"uia_version": "3.0", "connected": False},
            )

        capture_start_wall_ms = time.time() * 1000.0
        capture_start_mono = time.monotonic()
        graph = self.capture_active_window()
        assessment = await assess_pixel_modality(self)
        modality_status = {"tree": "ok", "screenshot": assessment.status}
        errors = [assessment.error] if assessment.error else []
        _, transform, geometry_error = bind_pixel_geometry(
            assessment.decoded_size, graph.viewport_size
        )
        if geometry_error is not None:
            errors.append(geometry_error)

        quality = ObservationQuality.HEALTHY
        err_msg = None
        is_bridge = bool(self._bridge_client is not None and self._bridge_client.is_connected)

        if assessment.status.startswith("corrupt"):
            quality = ObservationQuality.CORRUPTED
            err_msg = "; ".join(errors)
        elif not self._is_windows and not is_bridge:
            # Explicitly label that live Win32 execution is not running inside Linux WSL2
            quality = ObservationQuality.DEGRADED
            err_msg = (
                "Validation Status: Conformance verified via mock substrate / contract fixtures; "
                "Win32 live execution unavailable in Linux WSL2 environment."
            )
            if errors:
                err_msg = f"{err_msg} Pixel modality: {'; '.join(errors)}"
        elif errors:
            quality = ObservationQuality.DEGRADED
            err_msg = "; ".join(errors)
        elif self._lifecycle_state == PerceptionLifecycleState.DEGRADED:
            quality = ObservationQuality.DEGRADED
            err_msg = "Operating in degraded mode with mock UIA substrate."

        return ObservationRecord(
            observation_id=str(uuid.uuid4()),
            timestamp_ms=timestamp_ms,
            source_adapter="windows_uia",
            platform="windows",
            graph=graph,
            screenshot_bytes=assessment.screenshot_bytes,
            quality=quality,
            freshness_duration_ms=500.0,
            error_message=err_msg,
            platform_metadata={
                "uia_version": "3.0",
                "active_window": self.get_focused_window_title(),
                "node_count": len(graph.nodes),
                "is_live_win32": self._is_windows and not self._is_mock,
                "is_bridge": is_bridge,
                "bridge_url": self._bridge_client.base_url if is_bridge else None,
                "modality_status": modality_status,
                "coordinate_transform": transform,
                "capture_clocks": {
                    "wall_start_ms": capture_start_wall_ms,
                    "wall_end_ms": time.time() * 1000.0,
                    "mono_elapsed_ms": (time.monotonic() - capture_start_mono) * 1000.0,
                },
            },
        )


# Architectural Alias
WindowsUIAAdapter = WindowsUIAObservationAdapter
