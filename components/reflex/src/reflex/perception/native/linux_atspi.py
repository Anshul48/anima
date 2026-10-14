"""Reflex Linux AT-SPI2 D-Bus Accessibility Observation Adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import os
import uuid

from reflex.perception.native.base import (
    NativeObservationConfig,
    NativeObservationPort,
    NativeUIElement,
)
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

# Standard AT-SPI2 Role Identifiers
ROLE_PUSH_BUTTON = "ROLE_PUSH_BUTTON"
ROLE_TOGGLE_BUTTON = "ROLE_TOGGLE_BUTTON"
ROLE_CHECK_BOX = "ROLE_CHECK_BOX"
ROLE_RADIO_BUTTON = "ROLE_RADIO_BUTTON"
ROLE_ENTRY = "ROLE_ENTRY"
ROLE_TEXT = "ROLE_TEXT"
ROLE_PASSWORD_TEXT = "ROLE_PASSWORD_TEXT"
ROLE_TERMINAL = "ROLE_TERMINAL"
ROLE_LABEL = "ROLE_LABEL"
ROLE_HEADING = "ROLE_HEADING"
ROLE_LINK = "ROLE_LINK"
ROLE_IMAGE = "ROLE_IMAGE"
ROLE_ICON = "ROLE_ICON"
ROLE_DIALOG = "ROLE_DIALOG"
ROLE_ALERT = "ROLE_ALERT"
ROLE_FRAME = "ROLE_FRAME"
ROLE_WINDOW = "ROLE_WINDOW"
ROLE_PANEL = "ROLE_PANEL"
ROLE_SCROLL_PANE = "ROLE_SCROLL_PANE"
ROLE_SCROLL_BAR = "ROLE_SCROLL_BAR"
ROLE_COMBO_BOX = "ROLE_COMBO_BOX"
ROLE_LIST = "ROLE_LIST"
ROLE_LIST_ITEM = "ROLE_LIST_ITEM"
ROLE_TABLE = "ROLE_TABLE"
ROLE_TABLE_CELL = "ROLE_TABLE_CELL"
ROLE_MENU = "ROLE_MENU"
ROLE_MENU_BAR = "ROLE_MENU_BAR"
ROLE_MENU_ITEM = "ROLE_MENU_ITEM"
ROLE_PAGE_TAB = "ROLE_PAGE_TAB"
ROLE_PAGE_TAB_LIST = "ROLE_PAGE_TAB_LIST"
ROLE_SLIDER = "ROLE_SLIDER"
ROLE_SPIN_BUTTON = "ROLE_SPIN_BUTTON"
ROLE_PROGRESS_BAR = "ROLE_PROGRESS_BAR"
ROLE_STATUS_BAR = "ROLE_STATUS_BAR"
ROLE_SEPARATOR = "ROLE_SEPARATOR"


@dataclass
class MockLinuxATSPISubstrate:
    """In-memory substrate for Linux AT-SPI2 D-Bus testing and mock environments."""
    applications: List[Dict[str, Any]] = field(default_factory=list)
    focused_window_title: Optional[str] = "GNOME Terminal"
    focused_app_name: Optional[str] = "gnome-terminal"
    focused_element_id: Optional[str] = None
    element_tree: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    screenshot_bytes: Optional[bytes] = None

    def add_window(
        self,
        title: str,
        app_name: str = "gnome-terminal",
        is_focused: bool = False,
    ) -> None:
        self.applications.append({
            "title": title,
            "app_name": app_name,
            "is_focused": is_focused,
        })
        if is_focused:
            self.focused_window_title = title
            self.focused_app_name = app_name

    def add_element(
        self,
        element_id: str,
        name: str,
        role: str = ROLE_PUSH_BUTTON,
        extents: Tuple[int, int, int, int] = (0, 0, 100, 30),  # (x, y, width, height)
        value: str = "",
        is_clickable: bool = True,
        is_editable: bool = False,
        is_focused: bool = False,
        is_enabled: bool = True,
        parent_id: Optional[str] = None,
        children_ids: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        window_title: Optional[str] = None,
        depth: int = 1,
    ) -> None:
        self.element_tree[element_id] = {
            "element_id": element_id,
            "name": name,
            "role": role,
            "extents": extents,
            "value": value,
            "is_clickable": is_clickable,
            "is_editable": is_editable,
            "is_focused": is_focused,
            "is_enabled": is_enabled,
            "parent_id": parent_id,
            "children_ids": list(children_ids or []),
            "attributes": dict(attributes or {}),
            "window_title": window_title or self.focused_window_title,
            "depth": depth,
        }
        if is_focused:
            self.focused_element_id = element_id


class LinuxATSPIObservationAdapter(NativeObservationPort):
    """Linux AT-SPI2 D-Bus accessibility observation adapter with targeted lazy traversal."""

    def __init__(
        self,
        config: Optional[NativeObservationConfig] = None,
        clock: Optional[ClockPort] = None,
        substrate: Optional[MockLinuxATSPISubstrate] = None,
    ) -> None:
        super().__init__(config=config, clock=clock)
        self.substrate = substrate or MockLinuxATSPISubstrate()
        self._is_mock = substrate is not None
        self._is_linux = sys.platform.startswith("linux")
        self._simulated_permission_denied = False
        self._simulated_disconnected = False
        self._a11y_bus: Optional[Any] = None
        self._a11y_bus_address: Optional[str] = None

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

    def _connect_live_dbus(self, bus_addr: Optional[str] = None) -> None:
        """Connects to live AT-SPI2 D-Bus bus if available in Linux environment."""
        try:
            import dbus
        except ImportError:
            if os.path.exists("/usr/lib/python3/dist-packages") and "/usr/lib/python3/dist-packages" not in sys.path:
                sys.path.append("/usr/lib/python3/dist-packages")
            try:
                import dbus
            except ImportError:
                dbus = None

        if dbus is None:
            return

        try:
            if not bus_addr:
                sbus = dbus.SessionBus()
                a11y_obj = sbus.get_object("org.a11y.Bus", "/org/a11y/bus")
                bus_addr = str(a11y_obj.GetAddress(dbus_interface="org.a11y.Bus"))
            if bus_addr:
                self._a11y_bus = dbus.bus.BusConnection(bus_addr)
                self._a11y_bus_address = bus_addr
        except Exception:
            self._a11y_bus = None

    async def initialize(self) -> None:
        """Initializes connection to AT-SPI2 bus or configures degraded fallback."""
        if self._simulated_disconnected:
            self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED
            return
        if self._simulated_permission_denied:
            self._lifecycle_state = PerceptionLifecycleState.ERROR
            return

        if self._is_mock:
            self._lifecycle_state = PerceptionLifecycleState.CONNECTED
            return

        if not self._is_linux:
            self._lifecycle_state = PerceptionLifecycleState.DEGRADED
            return

        # Check real Linux AT-SPI D-Bus availability
        bus_addr = os.environ.get("AT_SPI_BUS_ADDRESS")
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}" if hasattr(os, "getuid") else "")
        socket_path = os.path.join(runtime_dir, "at-spi", "bus") if runtime_dir else None

        has_atspi = bool(bus_addr or (socket_path and os.path.exists(socket_path)))

        if has_atspi:
            self._connect_live_dbus(bus_addr)
            if self._a11y_bus is not None:
                self._lifecycle_state = PerceptionLifecycleState.CONNECTED
            elif self.config.enable_mock_fallback:
                self._lifecycle_state = PerceptionLifecycleState.DEGRADED
            else:
                self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED
        elif self.config.enable_mock_fallback:
            self._lifecycle_state = PerceptionLifecycleState.DEGRADED
        else:
            self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED

    async def teardown(self) -> None:
        """Closes live AT-SPI D-Bus connection and transitions to CLOSED."""
        if self._a11y_bus is not None:
            try:
                self._a11y_bus.close()
            except Exception:
                pass
            self._a11y_bus = None
        await super().teardown()

    def simulate_disconnect(self) -> None:
        """Simulates AT-SPI2 D-Bus daemon disconnect."""
        self._simulated_disconnected = True
        self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED

    def simulate_permission_denied(self) -> None:
        """Simulates accessibility permissions revoked by OS."""
        self._simulated_permission_denied = True
        self._lifecycle_state = PerceptionLifecycleState.ERROR

    def reconnect(self) -> None:
        """Restores connectivity after simulated fault."""
        self._simulated_disconnected = False
        self._simulated_permission_denied = False
        self._lifecycle_state = PerceptionLifecycleState.CONNECTED

    @staticmethod
    def map_role(atspi_role: Union[str, int, None]) -> NodeRole:
        """Maps AT-SPI2 role string to canonical NodeRole enum."""
        if not atspi_role:
            return NodeRole.UNKNOWN

        r = str(atspi_role).strip().upper()
        if not r.startswith("ROLE_"):
            r = f"ROLE_{r}"

        if r in (ROLE_PUSH_BUTTON, "ROLE_BUTTON"):
            return NodeRole.BUTTON
        elif r == ROLE_TOGGLE_BUTTON:
            return NodeRole.TOGGLE
        elif r in (ROLE_ENTRY, ROLE_TEXT, ROLE_PASSWORD_TEXT, ROLE_TERMINAL, "ROLE_SPIN_BUTTON"):
            return NodeRole.INPUT
        elif r == ROLE_CHECK_BOX:
            return NodeRole.CHECKBOX
        elif r == ROLE_RADIO_BUTTON:
            return NodeRole.RADIO
        elif r in (ROLE_LINK, ROLE_PAGE_TAB):
            return NodeRole.LINK
        elif r in (ROLE_LABEL, "ROLE_STATIC"):
            return NodeRole.TEXT
        elif r == ROLE_HEADING:
            return NodeRole.HEADING
        elif r in (ROLE_IMAGE, ROLE_ICON):
            return NodeRole.IMAGE
        elif r in (ROLE_DIALOG, ROLE_ALERT):
            return NodeRole.MODAL
        elif r == ROLE_SCROLL_BAR:
            return NodeRole.SCROLLBAR
        elif r == ROLE_COMBO_BOX:
            return NodeRole.DROPDOWN
        elif r in (ROLE_MENU_ITEM, "ROLE_CHECK_MENU_ITEM", "ROLE_RADIO_MENU_ITEM"):
            return NodeRole.BUTTON
        elif r in (
            ROLE_FRAME, ROLE_WINDOW, ROLE_PANEL, ROLE_SCROLL_PANE,
            ROLE_LIST, ROLE_LIST_ITEM, ROLE_TABLE, ROLE_TABLE_CELL,
            ROLE_MENU, ROLE_MENU_BAR, ROLE_PAGE_TAB_LIST, "ROLE_FILLER", "ROLE_TREE_TABLE",
        ):
            return NodeRole.CONTAINER
        elif r in (ROLE_SLIDER, ROLE_PROGRESS_BAR, ROLE_STATUS_BAR, ROLE_SEPARATOR):
            return NodeRole.GENERIC
        return NodeRole.UNKNOWN

    def list_open_windows(self) -> List[str]:
        """Lists active top-level Linux application windows."""
        results: List[str] = []
        for app in self.substrate.applications:
            title = app.get("title", "")
            name = app.get("app_name", "")
            results.append(f"{title} ({name})" if name else title)

        if not results and self.substrate.focused_window_title:
            app_name = self.substrate.focused_app_name
            t = self.substrate.focused_window_title
            results.append(f"{t} ({app_name})" if app_name else t)

        return results

    def get_focused_window_title(self) -> Optional[str]:
        """Returns title of currently focused Linux window."""
        return self.substrate.focused_window_title

    def get_focused_element(self) -> Optional[NativeUIElement]:
        """Returns the currently focused native AT-SPI element, if any."""
        focused_id = self.substrate.focused_element_id
        if focused_id and focused_id in self.substrate.element_tree:
            raw = self.substrate.element_tree[focused_id]
            ext = raw.get("extents", (0, 0, 100, 30))
            bounds = BoundingBox(ext[0], ext[1], ext[0] + ext[2], ext[1] + ext[3])
            return NativeUIElement(
                element_id=focused_id,
                name=raw.get("name", ""),
                role=str(raw.get("role", ROLE_PUSH_BUTTON)),
                bounds=bounds,
                value=raw.get("value", ""),
                is_clickable=raw.get("is_clickable", True),
                is_editable=raw.get("is_editable", False),
                is_focused=True,
                is_enabled=raw.get("is_enabled", True),
                parent_id=raw.get("parent_id"),
                children_ids=list(raw.get("children_ids", [])),
                control_type=str(raw.get("role", "")),
                window_title=raw.get("window_title"),
                attributes=raw.get("attributes", {}),
            )
        return None

    def _query_live_atspi_tree(self) -> Tuple[Dict[str, UIStateNode], Optional[str], Optional[str]]:
        """Queries live AT-SPI2 D-Bus registry for active applications and accessible trees."""
        if self._a11y_bus is None:
            return {}, None, None

        import dbus
        nodes: Dict[str, UIStateNode] = {}
        focused_id: Optional[str] = None
        active_title: Optional[str] = None

        try:
            root_obj = self._a11y_bus.get_object("org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root")
            root_iface = dbus.Interface(root_obj, "org.a11y.atspi.Accessible")
            children = root_iface.GetChildren()
            for service_name, obj_path in children:
                self._traverse_atspi_accessible(
                    service_name=str(service_name),
                    obj_path=str(obj_path),
                    parent_id=None,
                    depth=1,
                    nodes=nodes,
                )
        except Exception:
            pass

        return nodes, focused_id, active_title

    def _traverse_atspi_accessible(
        self,
        service_name: str,
        obj_path: str,
        parent_id: Optional[str],
        depth: int,
        nodes: Dict[str, UIStateNode],
    ) -> None:
        """Recursively traverses a live AT-SPI accessible object up to max_depth."""
        if depth > self.config.max_depth or len(nodes) >= 500:
            return

        import dbus
        try:
            node_obj = self._a11y_bus.get_object(service_name, obj_path)
            acc_iface = dbus.Interface(node_obj, "org.a11y.atspi.Accessible")
            props_iface = dbus.Interface(node_obj, "org.freedesktop.DBus.Properties")

            name = str(props_iface.Get("org.a11y.atspi.Accessible", "Name"))
            role_name = str(acc_iface.GetRoleName())
            role = self.map_role(role_name)

            bounds = BoundingBox(0, 0, 100, 30)
            try:
                comp_iface = dbus.Interface(node_obj, "org.a11y.atspi.Component")
                ext = comp_iface.GetExtents(0)
                if len(ext) == 4:
                    bounds = BoundingBox(int(ext[0]), int(ext[1]), int(ext[0] + ext[2]), int(ext[1] + ext[3]))
            except Exception:
                pass

            states = acc_iface.GetState()
            is_focused = bool(states[0] & (1 << 16)) if len(states) > 0 else False
            is_enabled = bool(states[0] & (1 << 3)) if len(states) > 0 else True

            node_id = f"{service_name}:{obj_path}"
            child_refs = acc_iface.GetChildren()
            children_ids = [f"{str(c[0])}:{str(c[1])}" for c in child_refs]

            node = UIStateNode(
                node_id=node_id,
                role=role,
                bounds=bounds,
                label=name,
                is_focused=is_focused,
                is_enabled=is_enabled,
                parent_id=parent_id,
                children_ids=children_ids,
                source=ModalitySource.UIA,
                confidence=1.0,
            )
            nodes[node_id] = node

            for child_service, child_path in child_refs:
                self._traverse_atspi_accessible(
                    service_name=str(child_service),
                    obj_path=str(child_path),
                    parent_id=node_id,
                    depth=depth + 1,
                    nodes=nodes,
                )
        except Exception:
            pass

    def capture_active_window(self) -> CanonicalUIGraph:
        """Extracts accessibility graph from focused Linux window via targeted lazy AT-SPI query."""
        timestamp_ms = self.clock.now_ms()
        window_title = self.get_focused_window_title() or "GNOME Desktop"
        nodes: Dict[str, UIStateNode] = {}
        focused_node_id = self.substrate.focused_element_id

        # If live AT-SPI D-Bus is connected and has live nodes, extract them
        if self._a11y_bus is not None:
            try:
                live_nodes, live_focused, live_title = self._query_live_atspi_tree()
                if live_nodes:
                    return CanonicalUIGraph(
                        timestamp_ms=timestamp_ms,
                        nodes=live_nodes,
                        focused_node_id=live_focused or focused_node_id,
                        active_window_title=live_title or window_title,
                        viewport_size=(self.config.screen_width, self.config.screen_height),
                    )
            except Exception:
                pass

        # Targeted lazy traversal filtering by max_depth and window scoping on substrate
        for el_id, raw in self.substrate.element_tree.items():
            # Check depth limitation to avoid D-Bus latency bottleneck
            depth = raw.get("depth", 1)
            if depth > self.config.max_depth:
                continue

            # Scope to active/target window
            el_window = raw.get("window_title")
            if self.config.target_window_title and el_window != self.config.target_window_title:
                continue

            role_str = raw.get("role", ROLE_PUSH_BUTTON)
            role = self.map_role(role_str)

            ext = raw.get("extents", (0, 0, 100, 30))
            if len(ext) == 4:
                # (x, y, width, height)
                bounds = BoundingBox(ext[0], ext[1], ext[0] + ext[2], ext[1] + ext[3])
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

        return CanonicalUIGraph(
            timestamp_ms=timestamp_ms,
            nodes=nodes,
            focused_node_id=focused_node_id,
            active_window_title=window_title,
            viewport_size=(self.config.screen_width, self.config.screen_height),
        )

    async def capture_screenshot(self) -> bytes:
        """Captures screenshot bytes of the active Linux display."""
        if self._simulated_permission_denied:
            raise PermissionError("Screen capture permission denied by OS security policy.")
        if self._simulated_disconnected or self._lifecycle_state == PerceptionLifecycleState.DISCONNECTED:
            raise ConnectionError("Display server / AT-SPI daemon disconnected.")
        if self.substrate.screenshot_bytes:
            return self.substrate.screenshot_bytes
        raise PerceptionError("Mock Linux AT-SPI substrate provides no pixel evidence.")

    async def capture_observation(self) -> ObservationRecord:
        """Captures a normalized, timestamped, provenance-bearing observation record from Linux AT-SPI."""
        timestamp_ms = self.clock.now_ms()

        if self._simulated_permission_denied:
            graph = CanonicalUIGraph(timestamp_ms=timestamp_ms, nodes={})
            return ObservationRecord(
                observation_id=str(uuid.uuid4()),
                timestamp_ms=timestamp_ms,
                source_adapter="linux_atspi",
                platform="linux",
                graph=graph,
                screenshot_bytes=None,
                quality=ObservationQuality.PERMISSION_DENIED,
                freshness_duration_ms=0.0,
                error_message="AT-SPI accessibility permissions denied by platform security policy.",
                platform_metadata={"bus": "at-spi2", "permissions": "denied"},
            )

        if self._simulated_disconnected or self._lifecycle_state == PerceptionLifecycleState.DISCONNECTED:
            graph = CanonicalUIGraph(timestamp_ms=timestamp_ms, nodes={})
            return ObservationRecord(
                observation_id=str(uuid.uuid4()),
                timestamp_ms=timestamp_ms,
                source_adapter="linux_atspi",
                platform="linux",
                graph=graph,
                screenshot_bytes=None,
                quality=ObservationQuality.DISCONNECTED,
                freshness_duration_ms=0.0,
                error_message="AT-SPI D-Bus daemon disconnected or unreachable.",
                platform_metadata={"bus": "at-spi2", "connected": False},
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
        if assessment.status.startswith("corrupt"):
            quality = ObservationQuality.CORRUPTED
        elif errors:
            quality = ObservationQuality.DEGRADED
        elif self._lifecycle_state == PerceptionLifecycleState.DEGRADED:
            quality = ObservationQuality.DEGRADED
            errors.append("Operating in degraded mode: live AT-SPI daemon not found; mock substrate active.")
        err_msg = "; ".join(errors) if errors else None

        is_live = bool(self._a11y_bus is not None)
        return ObservationRecord(
            observation_id=str(uuid.uuid4()),
            timestamp_ms=timestamp_ms,
            source_adapter="linux_atspi",
            platform="linux",
            graph=graph,
            screenshot_bytes=assessment.screenshot_bytes,
            quality=quality,
            freshness_duration_ms=500.0,
            error_message=err_msg,
            platform_metadata={
                "bus": "at-spi2",
                "is_live": is_live,
                "bus_address": self._a11y_bus_address,
                "display": os.environ.get("DISPLAY", ":0"),
                "active_window": self.get_focused_window_title(),
                "active_app": self.substrate.focused_app_name,
                "node_count": len(graph.nodes),
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
LinuxATSPIAdapter = LinuxATSPIObservationAdapter
