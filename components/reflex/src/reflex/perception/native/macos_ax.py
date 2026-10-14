"""Reflex macOS Accessibility (AXUIElement) Observation Adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from reflex.perception.native.base import (
    NativeObservationConfig,
    NativeObservationPort,
    NativeUIElement,
)
from reflex.ports.clock import ClockPort, SystemClock
from reflex.schemas.observation import PerceptionError
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)

# Standard macOS AX Roles
AX_BUTTON_ROLE = "AXButton"
AX_TEXT_FIELD_ROLE = "AXTextField"
AX_TEXT_AREA_ROLE = "AXTextArea"
AX_SEARCH_FIELD_ROLE = "AXSearchField"
AX_CHECK_BOX_ROLE = "AXCheckBox"
AX_RADIO_BUTTON_ROLE = "AXRadioButton"
AX_LINK_ROLE = "AXLink"
AX_STATIC_TEXT_ROLE = "AXStaticText"
AX_HEADING_ROLE = "AXHeading"
AX_IMAGE_ROLE = "AXImage"
AX_WINDOW_ROLE = "AXWindow"
AX_SHEET_ROLE = "AXSheet"
AX_DRAWER_ROLE = "AXDrawer"
AX_DIALOG_ROLE = "AXDialog"
AX_GROUP_ROLE = "AXGroup"
AX_SCROLL_AREA_ROLE = "AXScrollArea"
AX_SCROLL_BAR_ROLE = "AXScrollBar"
AX_POP_UP_BUTTON_ROLE = "AXPopUpButton"
AX_COMBO_BOX_ROLE = "AXComboBox"
AX_MENU_BAR_ROLE = "AXMenuBar"
AX_MENU_ROLE = "AXMenu"
AX_MENU_ITEM_ROLE = "AXMenuItem"
AX_TABLE_ROLE = "AXTable"
AX_OUTLINE_ROLE = "AXOutline"
AX_ROW_ROLE = "AXRow"
AX_COLUMN_ROLE = "AXColumn"
AX_CELL_ROLE = "AXCell"
AX_SLIDER_ROLE = "AXSlider"
AX_PROGRESS_INDICATOR_ROLE = "AXProgressIndicator"
AX_SWITCH_ROLE = "AXSwitch"
AX_TAB_GROUP_ROLE = "AXTabGroup"


@dataclass
class MockMacOSAXSubstrate:
    """In-memory substrate for macOS AXUIElement testing, CI runners, and mock environments."""
    windows: List[Dict[str, Any]] = field(default_factory=list)
    focused_app_name: Optional[str] = "Finder"
    focused_window_title: Optional[str] = "Finder Main Window"
    focused_element_id: Optional[str] = None
    element_tree: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    screenshot_bytes: Optional[bytes] = None

    def add_window(
        self,
        title: str,
        app_name: str = "Finder",
        is_focused: bool = False,
    ) -> None:
        self.windows.append({
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
        title: str,
        role: str = "AXButton",
        position: Tuple[int, int] = (0, 0),
        size: Tuple[int, int] = (100, 30),
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
            "title": title,
            "role": role,
            "position": position,
            "size": size,
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


class MacOSAXObservationAdapter(NativeObservationPort):
    """macOS Accessibility API (AXUIElement) observation adapter."""

    def __init__(
        self,
        config: Optional[NativeObservationConfig] = None,
        clock: Optional[ClockPort] = None,
        substrate: Optional[MockMacOSAXSubstrate] = None,
    ) -> None:
        super().__init__(config=config, clock=clock)
        self.substrate = substrate or MockMacOSAXSubstrate()
        self._is_macos = sys.platform == "darwin"

    @staticmethod
    def map_role(ax_role: Optional[str]) -> NodeRole:
        """Maps macOS AXRole string to canonical NodeRole enum."""
        if not ax_role:
            return NodeRole.UNKNOWN

        r = ax_role.strip()
        r_lower = r.lower()

        if r in (AX_BUTTON_ROLE, "AXPressButton", "AXBevelButton") or r_lower in ("button", "axbutton"):
            return NodeRole.BUTTON
        elif r in (AX_TEXT_FIELD_ROLE, AX_TEXT_AREA_ROLE, AX_SEARCH_FIELD_ROLE) or r_lower in (
            "axtextfield", "axtextarea", "axsearchfield", "textfield", "textarea", "input"
        ):
            return NodeRole.INPUT
        elif r == AX_CHECK_BOX_ROLE or r_lower in ("axcheckbox", "checkbox"):
            return NodeRole.CHECKBOX
        elif r == AX_RADIO_BUTTON_ROLE or r_lower in ("axradiobutton", "radiobutton", "radio"):
            return NodeRole.RADIO
        elif r == AX_LINK_ROLE or r_lower in ("axlink", "link"):
            return NodeRole.LINK
        elif r in (AX_STATIC_TEXT_ROLE,) or r_lower in ("axstatictext", "statictext", "text", "label"):
            return NodeRole.TEXT
        elif r == AX_HEADING_ROLE or r_lower in ("axheading", "heading"):
            return NodeRole.HEADING
        elif r == AX_IMAGE_ROLE or r_lower in ("aximage", "image"):
            return NodeRole.IMAGE
        elif r in (AX_DIALOG_ROLE, AX_SHEET_ROLE) or r_lower in ("axdialog", "axsheet", "dialog", "modal", "sheet"):
            return NodeRole.MODAL
        elif r == AX_SWITCH_ROLE or r_lower in ("axswitch", "switch", "toggle"):
            return NodeRole.TOGGLE
        elif r == AX_SCROLL_BAR_ROLE or r_lower in ("axscrollbar", "scrollbar"):
            return NodeRole.SCROLLBAR
        elif r in (AX_POP_UP_BUTTON_ROLE, AX_COMBO_BOX_ROLE) or r_lower in ("axpopupbutton", "axcombobox", "popupbutton", "combobox", "dropdown"):
            return NodeRole.DROPDOWN
        elif r == AX_MENU_ITEM_ROLE or r_lower in ("axmenuitem", "menuitem"):
            return NodeRole.BUTTON
        elif r in (
            AX_WINDOW_ROLE, AX_GROUP_ROLE, AX_SCROLL_AREA_ROLE, AX_DRAWER_ROLE,
            AX_MENU_BAR_ROLE, AX_MENU_ROLE, AX_TABLE_ROLE, AX_OUTLINE_ROLE,
            AX_ROW_ROLE, AX_COLUMN_ROLE, AX_CELL_ROLE, AX_TAB_GROUP_ROLE,
        ) or r_lower in ("axwindow", "axgroup", "axscrollarea", "axtable", "container", "window"):
            return NodeRole.CONTAINER
        elif r in (AX_SLIDER_ROLE, AX_PROGRESS_INDICATOR_ROLE) or r_lower in ("axslider", "slider", "progressindicator", "progressbar"):
            return NodeRole.GENERIC
        return NodeRole.UNKNOWN

    def list_open_windows(self) -> List[str]:
        """Lists active top-level native window titles and application names."""
        results: List[str] = []
        for w in self.substrate.windows:
            title = w.get("title", "")
            app = w.get("app_name", "")
            results.append(f"{title} ({app})" if app else title)

        if not results and self.substrate.focused_window_title:
            app = self.substrate.focused_app_name
            t = self.substrate.focused_window_title
            results.append(f"{t} ({app})" if app else t)

        return results

    def get_focused_window_title(self) -> Optional[str]:
        """Returns title of currently focused macOS window."""
        return self.substrate.focused_window_title

    def get_focused_element(self) -> Optional[NativeUIElement]:
        """Returns the currently focused native AXUIElement, if any."""
        focused_id = self.substrate.focused_element_id
        if focused_id and focused_id in self.substrate.element_tree:
            raw = self.substrate.element_tree[focused_id]
            pos = raw.get("position", (0, 0))
            sz = raw.get("size", (100, 30))
            bounds = BoundingBox(pos[0], pos[1], pos[0] + sz[0], pos[1] + sz[1])
            return NativeUIElement(
                element_id=focused_id,
                name=raw.get("title", ""),
                role=str(raw.get("role", "AXButton")),
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

    def copy_multiple_attributes(self, element_id: str, attribute_names: List[str]) -> Dict[str, Any]:
        """Simulates batch attribute querying (AXUIElementCopyMultipleAttributeValues)."""
        if element_id not in self.substrate.element_tree:
            return {}
        raw = self.substrate.element_tree[element_id]
        results: Dict[str, Any] = {}
        for attr in attribute_names:
            if attr in ("kAXTitleAttribute", "AXTitle", "title"):
                results[attr] = raw.get("title", "")
            elif attr in ("kAXRoleAttribute", "AXRole", "role"):
                results[attr] = raw.get("role", "AXButton")
            elif attr in ("kAXValueAttribute", "AXValue", "value"):
                results[attr] = raw.get("value", "")
            elif attr in ("kAXPositionAttribute", "AXPosition", "position"):
                results[attr] = raw.get("position", (0, 0))
            elif attr in ("kAXSizeAttribute", "AXSize", "size"):
                results[attr] = raw.get("size", (100, 30))
            elif attr in ("kAXEnabledAttribute", "AXEnabled", "enabled"):
                results[attr] = raw.get("is_enabled", True)
            elif attr in ("kAXFocusedAttribute", "AXFocused", "focused"):
                results[attr] = raw.get("is_focused", False)
            elif attr in ("kAXChildrenAttribute", "AXChildren", "children"):
                results[attr] = raw.get("children_ids", [])
            elif attr in ("kAXParentAttribute", "AXParent", "parent"):
                results[attr] = raw.get("parent_id")
            elif attr in raw.get("attributes", {}):
                results[attr] = raw["attributes"][attr]
        return results

    def capture_active_window(self) -> CanonicalUIGraph:
        """Extracts accessibility graph from currently focused macOS window via AXUIElement."""
        timestamp_ms = self.clock.now_ms()
        window_title = self.get_focused_window_title() or "Finder"
        nodes: Dict[str, UIStateNode] = {}
        focused_node_id = self.substrate.focused_element_id

        # Batch query all elements
        attrs_to_query = [
            "kAXTitleAttribute",
            "kAXRoleAttribute",
            "kAXValueAttribute",
            "kAXPositionAttribute",
            "kAXSizeAttribute",
            "kAXEnabledAttribute",
            "kAXFocusedAttribute",
            "kAXChildrenAttribute",
            "kAXParentAttribute",
        ]

        for el_id in self.substrate.element_tree:
            raw = self.substrate.element_tree[el_id]
            el_window = raw.get("window_title")
            if self.config.target_window_title and el_window != self.config.target_window_title:
                continue

            batch_attrs = self.copy_multiple_attributes(el_id, attrs_to_query)
            role_str = batch_attrs.get("kAXRoleAttribute", "AXButton")
            role = self.map_role(role_str)

            pos = batch_attrs.get("kAXPositionAttribute", (0, 0))
            sz = batch_attrs.get("kAXSizeAttribute", (100, 30))
            bounds = BoundingBox(pos[0], pos[1], pos[0] + sz[0], pos[1] + sz[1])

            node = UIStateNode(
                node_id=el_id,
                role=role,
                bounds=bounds,
                label=batch_attrs.get("kAXTitleAttribute", ""),
                value=str(batch_attrs.get("kAXValueAttribute", "")),
                is_clickable=bool(raw.get("is_clickable", True)),
                is_editable=bool(raw.get("is_editable", False)),
                is_focused=bool(batch_attrs.get("kAXFocusedAttribute", el_id == focused_node_id)),
                is_enabled=bool(batch_attrs.get("kAXEnabledAttribute", True)),
                parent_id=batch_attrs.get("kAXParentAttribute"),
                children_ids=list(batch_attrs.get("kAXChildrenAttribute", [])),
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
        """Captures screenshot bytes of the active macOS display."""
        if self.substrate.screenshot_bytes:
            return self.substrate.screenshot_bytes
        raise PerceptionError("Mock macOS AX substrate provides no pixel evidence.")


# Architectural Alias
MacOSAXAdapter = MacOSAXObservationAdapter
