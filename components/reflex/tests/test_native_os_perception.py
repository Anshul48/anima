"""Unit and integration tests for native OS perception adapters (Windows UIA, macOS AX, Linux AT-SPI2)."""

from __future__ import annotations

import asyncio
import unittest

from reflex.perception.native.base import (
    NativeObservationConfig,
    NativeObservationPort,
    NativeUIElement,
)
from reflex.perception.native.linux_atspi import (
    LinuxATSPIObservationAdapter,
    MockLinuxATSPISubstrate,
    ROLE_CHECK_BOX,
    ROLE_DIALOG,
    ROLE_ENTRY,
    ROLE_FRAME,
    ROLE_HEADING,
    ROLE_IMAGE,
    ROLE_LINK,
    ROLE_PUSH_BUTTON,
    ROLE_RADIO_BUTTON,
    ROLE_SCROLL_BAR,
    ROLE_TOGGLE_BUTTON,
)
from reflex.perception.native.macos_ax import (
    AX_BUTTON_ROLE,
    AX_CHECK_BOX_ROLE,
    AX_COMBO_BOX_ROLE,
    AX_DIALOG_ROLE,
    AX_HEADING_ROLE,
    AX_IMAGE_ROLE,
    AX_LINK_ROLE,
    AX_RADIO_BUTTON_ROLE,
    AX_SCROLL_BAR_ROLE,
    AX_STATIC_TEXT_ROLE,
    AX_SWITCH_ROLE,
    AX_TEXT_FIELD_ROLE,
    AX_WINDOW_ROLE,
    MacOSAXObservationAdapter,
    MockMacOSAXSubstrate,
)
from reflex.perception.native.windows_uia import (
    MockWindowsUIASubstrate,
    UIA_BUTTON_CONTROL_TYPE_ID,
    UIA_CHECK_BOX_CONTROL_TYPE_ID,
    UIA_COMBO_BOX_CONTROL_TYPE_ID,
    UIA_DOCUMENT_CONTROL_TYPE_ID,
    UIA_EDIT_CONTROL_TYPE_ID,
    UIA_HEADER_CONTROL_TYPE_ID,
    UIA_HYPERLINK_CONTROL_TYPE_ID,
    UIA_IMAGE_CONTROL_TYPE_ID,
    UIA_RADIO_BUTTON_CONTROL_TYPE_ID,
    UIA_SCROLL_BAR_CONTROL_TYPE_ID,
    UIA_TEXT_CONTROL_TYPE_ID,
    UIA_WINDOW_CONTROL_TYPE_ID,
    WindowsUIAObservationAdapter,
)
from reflex.ports.clock import DeterministicClock
from reflex.schemas.state import (
    BoundingBox,
    CanonicalUIGraph,
    ModalitySource,
    NodeRole,
    UIStateNode,
)


class TestNativeObservationConfig(unittest.TestCase):
    def test_config_serialization(self):
        cfg = NativeObservationConfig(
            max_depth=25,
            include_invisible=True,
            cache_subtrees=False,
            timeout_ms=500.0,
            prefetch_properties=["Name", "BoundingRectangle"],
            target_window_title="Calculator",
            target_process_id=4567,
            screen_width=2560,
            screen_height=1440,
        )
        d = cfg.to_dict()
        self.assertEqual(d["max_depth"], 25)
        self.assertTrue(d["include_invisible"])
        self.assertFalse(d["cache_subtrees"])
        self.assertEqual(d["timeout_ms"], 500.0)
        self.assertEqual(d["prefetch_properties"], ["Name", "BoundingRectangle"])
        self.assertEqual(d["target_window_title"], "Calculator")
        self.assertEqual(d["target_process_id"], 4567)
        self.assertEqual(d["screen_width"], 2560)
        self.assertEqual(d["screen_height"], 1440)

        restored = NativeObservationConfig.from_dict(d)
        self.assertEqual(restored, cfg)


class TestNativeUIElement(unittest.TestCase):
    def test_element_to_ui_state_node(self):
        el = NativeUIElement(
            element_id="btn_submit",
            name="Submit",
            role="Button",
            bounds=BoundingBox(10, 20, 110, 60),
            value="Submit Form",
            is_clickable=True,
            is_editable=False,
            is_focused=True,
            is_enabled=True,
            parent_id="form_root",
            children_ids=["txt_1"],
            control_type="Button",
            handle=12345,
            process_id=999,
            window_title="App Main",
            attributes={"aria_label": "Submit Button"},
        )
        node = el.to_ui_state_node(mapped_role=NodeRole.BUTTON, source=ModalitySource.UIA)
        self.assertEqual(node.node_id, "btn_submit")
        self.assertEqual(node.role, NodeRole.BUTTON)
        self.assertEqual(node.bounds.x1, 10)
        self.assertEqual(node.bounds.y1, 20)
        self.assertEqual(node.bounds.x2, 110)
        self.assertEqual(node.bounds.y2, 60)
        self.assertEqual(node.label, "Submit")
        self.assertEqual(node.value, "Submit Form")
        self.assertTrue(node.is_clickable)
        self.assertFalse(node.is_editable)
        self.assertTrue(node.is_focused)
        self.assertEqual(node.parent_id, "form_root")
        self.assertEqual(list(node.children_ids), ["txt_1"])
        self.assertEqual(node.source, ModalitySource.UIA)
        self.assertEqual(node.attributes["control_type"], "Button")
        self.assertEqual(node.attributes["handle"], 12345)
        self.assertEqual(node.attributes["window_title"], "App Main")

    def test_element_serialization(self):
        el = NativeUIElement(
            element_id="el_1",
            name="Test",
            role="Edit",
            bounds=BoundingBox(0, 0, 100, 50),
        )
        d = el.to_dict()
        restored = NativeUIElement.from_dict(d)
        self.assertEqual(restored.element_id, el.element_id)
        self.assertEqual(restored.name, el.name)
        self.assertEqual(restored.bounds, el.bounds)


class TestWindowsUIAObservationAdapter(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=5000.0)
        self.substrate = MockWindowsUIASubstrate()
        self.adapter = WindowsUIAObservationAdapter(clock=self.clock, substrate=self.substrate)

    def test_role_mapping(self):
        # Integer IDs
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_BUTTON_CONTROL_TYPE_ID), NodeRole.BUTTON)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_EDIT_CONTROL_TYPE_ID), NodeRole.INPUT)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_DOCUMENT_CONTROL_TYPE_ID), NodeRole.INPUT)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_CHECK_BOX_CONTROL_TYPE_ID), NodeRole.CHECKBOX)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_RADIO_BUTTON_CONTROL_TYPE_ID), NodeRole.RADIO)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_HYPERLINK_CONTROL_TYPE_ID), NodeRole.LINK)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_TEXT_CONTROL_TYPE_ID), NodeRole.TEXT)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_IMAGE_CONTROL_TYPE_ID), NodeRole.IMAGE)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_WINDOW_CONTROL_TYPE_ID), NodeRole.CONTAINER)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_SCROLL_BAR_CONTROL_TYPE_ID), NodeRole.SCROLLBAR)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_COMBO_BOX_CONTROL_TYPE_ID), NodeRole.DROPDOWN)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(UIA_HEADER_CONTROL_TYPE_ID), NodeRole.HEADING)

        # String names
        self.assertEqual(WindowsUIAObservationAdapter.map_role("Button"), NodeRole.BUTTON)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("UIA_ButtonControlTypeId"), NodeRole.BUTTON)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("Edit"), NodeRole.INPUT)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("CheckBox"), NodeRole.CHECKBOX)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("RadioButton"), NodeRole.RADIO)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("Hyperlink"), NodeRole.LINK)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("Text"), NodeRole.TEXT)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("Image"), NodeRole.IMAGE)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("Dialog"), NodeRole.MODAL)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("Switch"), NodeRole.TOGGLE)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("ScrollBar"), NodeRole.SCROLLBAR)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("ComboBox"), NodeRole.DROPDOWN)
        self.assertEqual(WindowsUIAObservationAdapter.map_role("Pane"), NodeRole.CONTAINER)
        self.assertEqual(WindowsUIAObservationAdapter.map_role(None), NodeRole.UNKNOWN)

    def test_window_list_and_focus(self):
        self.substrate.add_window("Calculator", handle=2001, process_name="calc.exe", is_focused=True)
        self.substrate.add_window("Notepad", handle=2002, process_name="notepad.exe", is_focused=False)

        windows = self.adapter.list_open_windows()
        self.assertIn("Calculator (calc.exe)", windows)
        self.assertIn("Notepad (notepad.exe)", windows)
        self.assertEqual(self.adapter.get_focused_window_title(), "Calculator")

    def test_tree_extraction_and_state_hash(self):
        self.substrate.focused_window_title = "Notepad"
        self.substrate.add_element(
            element_id="txt_editor",
            name="Text Editor",
            control_type="Edit",
            bounds=(50, 50, 500, 400),
            value="Hello Reflex Native Windows",
            is_editable=True,
            is_focused=True,
        )
        self.substrate.add_element(
            element_id="btn_save",
            name="Save",
            control_type="Button",
            bounds=(10, 10, 40, 30),
            is_clickable=True,
            parent_id=None,
        )

        focused_el = self.adapter.get_focused_element()
        self.assertIsNotNone(focused_el)
        assert focused_el is not None
        self.assertEqual(focused_el.element_id, "txt_editor")

        graph = self.adapter.capture_active_window()
        self.assertIsInstance(graph, CanonicalUIGraph)
        self.assertEqual(graph.timestamp_ms, 5000.0)
        self.assertEqual(graph.active_window_title, "Notepad")
        self.assertEqual(graph.focused_node_id, "txt_editor")
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(graph.nodes["txt_editor"].role, NodeRole.INPUT)
        self.assertEqual(graph.nodes["btn_save"].role, NodeRole.BUTTON)

        # Verify state hash determinism
        h1 = graph.compute_state_hash()
        h2 = graph.compute_state_hash()
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_async_capture_state_and_screenshot(self):
        async def run():
            self.substrate.screenshot_bytes = b"custom_win_screenshot_bytes"
            graph = await self.adapter.capture_state()
            self.assertIsInstance(graph, CanonicalUIGraph)

            screenshot = await self.adapter.capture_screenshot()
            self.assertEqual(screenshot, b"custom_win_screenshot_bytes")

        asyncio.run(run())


class TestMacOSAXObservationAdapter(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=6000.0)
        self.substrate = MockMacOSAXSubstrate()
        self.adapter = MacOSAXObservationAdapter(clock=self.clock, substrate=self.substrate)

    def test_role_mapping(self):
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_BUTTON_ROLE), NodeRole.BUTTON)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_TEXT_FIELD_ROLE), NodeRole.INPUT)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_CHECK_BOX_ROLE), NodeRole.CHECKBOX)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_RADIO_BUTTON_ROLE), NodeRole.RADIO)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_LINK_ROLE), NodeRole.LINK)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_STATIC_TEXT_ROLE), NodeRole.TEXT)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_HEADING_ROLE), NodeRole.HEADING)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_IMAGE_ROLE), NodeRole.IMAGE)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_WINDOW_ROLE), NodeRole.CONTAINER)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_DIALOG_ROLE), NodeRole.MODAL)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_SWITCH_ROLE), NodeRole.TOGGLE)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_SCROLL_BAR_ROLE), NodeRole.SCROLLBAR)
        self.assertEqual(MacOSAXObservationAdapter.map_role(AX_COMBO_BOX_ROLE), NodeRole.DROPDOWN)
        self.assertEqual(MacOSAXObservationAdapter.map_role(None), NodeRole.UNKNOWN)

    def test_tree_extraction_and_batch_query(self):
        self.substrate.add_window("Safari - Home", app_name="Safari", is_focused=True)
        self.substrate.add_element(
            element_id="ax_url_bar",
            title="Search or enter website name",
            role=AX_TEXT_FIELD_ROLE,
            position=(100, 20),
            size=(600, 30),
            value="https://reflex.ai",
            is_editable=True,
            is_focused=True,
        )
        self.substrate.add_element(
            element_id="ax_bookmark_btn",
            title="Bookmark",
            role=AX_BUTTON_ROLE,
            position=(720, 20),
            size=(40, 30),
        )

        windows = self.adapter.list_open_windows()
        self.assertIn("Safari - Home (Safari)", windows)
        self.assertEqual(self.adapter.get_focused_window_title(), "Safari - Home")

        focused_el = self.adapter.get_focused_element()
        self.assertIsNotNone(focused_el)
        assert focused_el is not None
        self.assertEqual(focused_el.element_id, "ax_url_bar")

        graph = self.adapter.capture_active_window()
        self.assertEqual(graph.timestamp_ms, 6000.0)
        self.assertEqual(graph.active_window_title, "Safari - Home")
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(graph.nodes["ax_url_bar"].role, NodeRole.INPUT)
        self.assertEqual(graph.nodes["ax_url_bar"].bounds.x2, 700)
        self.assertEqual(graph.nodes["ax_bookmark_btn"].role, NodeRole.BUTTON)

        h = graph.compute_state_hash()
        self.assertEqual(len(h), 64)

    def test_async_capture_state_and_screenshot(self):
        async def run():
            self.substrate.screenshot_bytes = b"custom_macos_screenshot"
            graph = await self.adapter.capture_state()
            self.assertEqual(len(graph.nodes), 0)
            sc = await self.adapter.capture_screenshot()
            self.assertEqual(sc, b"custom_macos_screenshot")

        asyncio.run(run())


class TestLinuxATSPIObservationAdapter(unittest.TestCase):
    def setUp(self):
        self.clock = DeterministicClock(start_time_ms=7000.0)
        self.substrate = MockLinuxATSPISubstrate()
        self.adapter = LinuxATSPIObservationAdapter(clock=self.clock, substrate=self.substrate)

    def test_role_mapping(self):
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_PUSH_BUTTON), NodeRole.BUTTON)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_TOGGLE_BUTTON), NodeRole.TOGGLE)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_ENTRY), NodeRole.INPUT)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_CHECK_BOX), NodeRole.CHECKBOX)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_RADIO_BUTTON), NodeRole.RADIO)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_LINK), NodeRole.LINK)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_HEADING), NodeRole.HEADING)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_IMAGE), NodeRole.IMAGE)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_DIALOG), NodeRole.MODAL)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_FRAME), NodeRole.CONTAINER)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(ROLE_SCROLL_BAR), NodeRole.SCROLLBAR)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role("ROLE_UNKNOWN"), NodeRole.UNKNOWN)
        self.assertEqual(LinuxATSPIObservationAdapter.map_role(None), NodeRole.UNKNOWN)

    def test_targeted_lazy_traversal_and_depth_limits(self):
        config = NativeObservationConfig(max_depth=2)
        adapter = LinuxATSPIObservationAdapter(config=config, clock=self.clock, substrate=self.substrate)

        self.substrate.add_window("Settings", app_name="gnome-control-center", is_focused=True)
        # Depth 1
        self.substrate.add_element("root_frame", "Settings Frame", role=ROLE_FRAME, extents=(0, 0, 800, 600), depth=1)
        # Depth 2
        self.substrate.add_element(
            "btn_wifi", "Wi-Fi Settings", role=ROLE_PUSH_BUTTON, extents=(10, 50, 150, 40), depth=2, is_focused=True
        )
        # Depth 3 (exceeds max_depth=2, should be skipped by targeted lazy query)
        self.substrate.add_element("deep_icon", "Wi-Fi Icon", role=ROLE_IMAGE, extents=(15, 55, 20, 20), depth=3)

        graph = adapter.capture_active_window()
        self.assertEqual(graph.timestamp_ms, 7000.0)
        self.assertEqual(graph.active_window_title, "Settings")
        self.assertEqual(len(graph.nodes), 2)
        self.assertIn("root_frame", graph.nodes)
        self.assertIn("btn_wifi", graph.nodes)
        self.assertNotIn("deep_icon", graph.nodes)  # Verified lazy depth cutoff!

        focused = adapter.get_focused_element()
        self.assertIsNotNone(focused)
        assert focused is not None
        self.assertEqual(focused.element_id, "btn_wifi")

    def test_async_capture_state_and_screenshot(self):
        async def run():
            self.substrate.screenshot_bytes = b"custom_linux_screenshot"
            graph = await self.adapter.capture_state()
            self.assertEqual(len(graph.nodes), 0)
            sc = await self.adapter.capture_screenshot()
            self.assertEqual(sc, b"custom_linux_screenshot")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
