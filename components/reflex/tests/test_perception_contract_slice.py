"""End-to-end controlled perception slice testing the public ObservationPort interface.

Demonstrates:
- Initial observation and subsequent meaningful changes (single char edit, checkbox toggle, warning banner).
- Stable source identity, timestamps, and freshness duration.
- Relevant structure/content and geometry.
- Noise handling without suppressing meaningful small changes.
- Unavailable permissions, disconnect, malformed input, and recovery.
- Output consumed through the public perception interface.
"""

from __future__ import annotations

import asyncio
import io
import time
import unittest

import numpy as np
from PIL import Image, ImageDraw

from reflex.perception.native.linux_atspi import LinuxATSPIObservationAdapter, MockLinuxATSPISubstrate
from reflex.perception.vision.differ import OpenCVVisualDiffer
from reflex.perception.vision.vision_grounder import CorruptedFrameError, MockVisionGrounder
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.delta import OutcomeClass
from reflex.schemas.observation import (
    ObservationQuality,
    ObservationRecord,
    PerceptionCapabilities,
    PerceptionDelta,
    PerceptionLifecycleState,
    SemanticEventType,
)
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, ModalitySource, NodeRole, UIStateNode


class ControlledAppPerceptionAdapter(ObservationPort):
    """Controlled application perception adapter backed by a deterministic UI form and renderer."""

    def __init__(self, clock: Optional[DeterministicClock] = None) -> None:
        self.clock = clock or DeterministicClock(start_time_ms=10000.0)
        self._lifecycle_state = PerceptionLifecycleState.UNINITIALIZED
        self._simulated_permission_denied = False
        self._simulated_disconnected = False

        # Controlled form state
        self.window_title = "Controlled Account Settings"
        self.username = "johndoe"
        self.remember_me = False
        self.warning_active = False
        self.cursor_blink_on = False

    @property
    def capabilities(self) -> PerceptionCapabilities:
        return PerceptionCapabilities(
            supports_accessibility_tree=True,
            supports_window_hierarchy=True,
            supports_dom_snapshot=True,
            supports_pixel_buffer=True,
            supports_change_stream=True,
            supports_continuous_polling=True,
            supports_bounding_box_extraction=True,
            supported_modalities=[ModalitySource.DOM, ModalitySource.UIA],
        )

    @property
    def lifecycle_state(self) -> PerceptionLifecycleState:
        return self._lifecycle_state

    async def initialize(self) -> None:
        if self._simulated_disconnected:
            self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED
        elif self._simulated_permission_denied:
            self._lifecycle_state = PerceptionLifecycleState.ERROR
        else:
            self._lifecycle_state = PerceptionLifecycleState.CONNECTED

    async def teardown(self) -> None:
        self._lifecycle_state = PerceptionLifecycleState.CLOSED

    def simulate_disconnect(self) -> None:
        self._simulated_disconnected = True
        self._lifecycle_state = PerceptionLifecycleState.DISCONNECTED

    def simulate_permission_denied(self) -> None:
        self._simulated_permission_denied = True
        self._lifecycle_state = PerceptionLifecycleState.ERROR

    def reconnect(self) -> None:
        self._simulated_disconnected = False
        self._simulated_permission_denied = False
        self._lifecycle_state = PerceptionLifecycleState.CONNECTED

    def build_ui_graph(self) -> CanonicalUIGraph:
        """Constructs canonical UI graph for current controlled state."""
        nodes: Dict[str, UIStateNode] = {}

        # 1. Container window
        nodes["root"] = UIStateNode(
            node_id="root",
            role=NodeRole.CONTAINER,
            bounds=BoundingBox(0, 0, 400, 300),
            label="Root Window",
            children_ids=["username_input", "remember_cb", "save_btn"] + (["warn_banner"] if self.warning_active else []),
        )

        # 2. Username input
        nodes["username_input"] = UIStateNode(
            node_id="username_input",
            role=NodeRole.INPUT,
            bounds=BoundingBox(100, 50, 250, 80),
            label="Username",
            value=self.username,
            is_clickable=True,
            is_editable=True,
            is_focused=True,
            parent_id="root",
        )

        # 3. Checkbox
        nodes["remember_cb"] = UIStateNode(
            node_id="remember_cb",
            role=NodeRole.CHECKBOX,
            bounds=BoundingBox(20, 100, 34, 114),
            label="Remember me",
            value="true" if self.remember_me else "false",
            is_clickable=True,
            parent_id="root",
        )

        # 4. Save Button
        nodes["save_btn"] = UIStateNode(
            node_id="save_btn",
            role=NodeRole.BUTTON,
            bounds=BoundingBox(100, 150, 200, 185),
            label="Save Changes",
            is_clickable=True,
            parent_id="root",
        )

        # 5. Warning Banner (if triggered)
        if self.warning_active:
            nodes["warn_banner"] = UIStateNode(
                node_id="warn_banner",
                role=NodeRole.MODAL,
                bounds=BoundingBox(260, 57, 277, 77),
                label="Warning: Username already taken",
                parent_id="root",
            )

        return CanonicalUIGraph(
            timestamp_ms=self.clock.now_ms(),
            nodes=nodes,
            focused_node_id="username_input",
            active_window_title=self.window_title,
            viewport_size=(400, 300),
        )

    def render_screenshot(self) -> bytes:
        """Renders controlled application frame as PNG bytes."""
        img = Image.new("RGB", (400, 300), color=(255, 255, 255))
        d = ImageDraw.Draw(img)

        # Title
        d.text((20, 20), self.window_title, fill=(0, 0, 0))

        # Username input
        d.text((20, 60), "Username:", fill=(50, 50, 50))
        d.rectangle([(100, 50), (250, 80)], outline=(180, 180, 180), fill=(245, 245, 245))
        d.text((105, 58), self.username, fill=(0, 0, 0))

        # Cursor noise (if blinking on)
        if self.cursor_blink_on:
            cx = 105 + len(self.username) * 7
            d.line([(cx, 56), (cx, 74)], fill=(0, 0, 0), width=1)

        # Checkbox
        d.rectangle([(20, 100), (34, 114)], outline=(100, 100, 100), fill=(255, 255, 255))
        d.text((40, 100), "Remember me", fill=(50, 50, 50))
        if self.remember_me:
            d.line([(22, 107), (26, 112)], fill=(0, 120, 215), width=2)
            d.line([(26, 112), (32, 103)], fill=(0, 120, 215), width=2)

        # Save Button
        d.rectangle([(100, 150), (200, 185)], fill=(0, 120, 215))
        d.text((115, 160), "Save", fill=(255, 255, 255))

        # Warning icon
        if self.warning_active:
            d.polygon([(260, 57), (276, 57), (268, 77)], fill=(220, 50, 50))
            d.line([(268, 62), (268, 70)], fill=(255, 255, 255), width=2)
            d.point([(268, 73)], fill=(255, 255, 255))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def capture_state(self) -> CanonicalUIGraph:
        return self.build_ui_graph()

    async def capture_screenshot(self) -> bytes:
        if self._simulated_permission_denied:
            raise PermissionError("Screen capture permission denied by OS security policy.")
        if self._simulated_disconnected:
            raise ConnectionError("Display disconnected.")
        return self.render_screenshot()

    async def capture_observation(self) -> ObservationRecord:
        now_ms = self.clock.now_ms()

        if self._simulated_permission_denied:
            return ObservationRecord(
                observation_id=f"obs_{int(now_ms)}",
                timestamp_ms=now_ms,
                source_adapter="controlled_app",
                platform="linux",
                graph=CanonicalUIGraph(timestamp_ms=now_ms, nodes={}),
                quality=ObservationQuality.PERMISSION_DENIED,
                freshness_duration_ms=0.0,
                error_message="Screen recording permissions denied.",
            )

        if self._simulated_disconnected:
            return ObservationRecord(
                observation_id=f"obs_{int(now_ms)}",
                timestamp_ms=now_ms,
                source_adapter="controlled_app",
                platform="linux",
                graph=CanonicalUIGraph(timestamp_ms=now_ms, nodes={}),
                quality=ObservationQuality.DISCONNECTED,
                freshness_duration_ms=0.0,
                error_message="Display connection lost.",
            )

        graph = self.build_ui_graph()
        shot = await self.capture_screenshot()

        return ObservationRecord(
            observation_id=f"obs_{int(now_ms)}",
            timestamp_ms=now_ms,
            source_adapter="controlled_app",
            platform="linux",
            graph=graph,
            screenshot_bytes=shot,
            quality=ObservationQuality.HEALTHY,
            freshness_duration_ms=500.0,
            platform_metadata={"window": self.window_title, "elements": len(graph.nodes)},
        )


class TestPerceptionContractSlice(unittest.IsolatedAsyncioTestCase):
    """End-to-end qualification suite for the public perception contract and controlled slice."""

    async def asyncSetUp(self) -> None:
        self.clock = DeterministicClock(start_time_ms=1000.0)
        self.adapter = ControlledAppPerceptionAdapter(clock=self.clock)
        self.differ = OpenCVVisualDiffer()
        await self.adapter.initialize()

    async def asyncTearDown(self) -> None:
        await self.adapter.teardown()

    async def test_01_initial_observation_provenance_and_freshness(self) -> None:
        """Demonstrates initial observation with stable source identity, timestamps, and freshness."""
        obs = await self.adapter.capture_observation()

        self.assertEqual(obs.source_adapter, "controlled_app")
        self.assertEqual(obs.platform, "linux")
        self.assertEqual(obs.quality, ObservationQuality.HEALTHY)
        self.assertEqual(obs.timestamp_ms, 1000.0)
        self.assertEqual(obs.freshness_duration_ms, 500.0)
        self.assertTrue(obs.is_fresh(current_time_ms=1200.0))
        self.assertFalse(obs.is_fresh(current_time_ms=1600.0))  # Expired freshness

        # Structure and geometry assertions
        self.assertIn("username_input", obs.graph.nodes)
        input_node = obs.graph.nodes["username_input"]
        self.assertEqual(input_node.role, NodeRole.INPUT)
        self.assertEqual(input_node.value, "johndoe")
        self.assertEqual(input_node.bounds, BoundingBox(100, 50, 250, 80))

        # Query consumer interface
        found_inputs = self.adapter.find_nodes_by_role(obs.graph, NodeRole.INPUT)
        self.assertEqual(len(found_inputs), 1)
        self.assertEqual(found_inputs[0].node_id, "username_input")

        found_by_lbl = self.adapter.find_nodes_by_label(obs.graph, "Username")
        self.assertEqual(len(found_by_lbl), 1)

    async def test_02_meaningful_single_character_edit_delta(self) -> None:
        """Demonstrates meaningful single-character edit detected structurally and visually."""
        # Initial observation
        obs1 = await self.adapter.capture_observation()

        # Step time and simulate typing single character 's' -> 'johndoes'
        self.clock.advance(100.0)
        self.adapter.username = "johndoes"
        obs2 = await self.adapter.capture_observation()

        # Compute visual diff
        v_diff = self.differ.diff_frames(obs1.screenshot_bytes, obs2.screenshot_bytes)
        self.assertFalse(v_diff.is_static, "Visual differ must detect single-character edit")
        self.assertGreaterEqual(len(v_diff.changed_boxes), 1)

        # Compute semantic delta through public port
        delta = self.adapter.compute_delta(
            obs1, obs2, pixel_change_ratio=v_diff.pixel_change_ratio, changed_boxes=v_diff.changed_boxes
        )
        self.assertFalse(delta.is_static)
        self.assertEqual(len(delta.modified_nodes), 1)
        self.assertEqual(delta.modified_nodes[0]["node_id"], "username_input")

        val_change = delta.modified_nodes[0]["changes"]["value"]
        self.assertEqual(val_change["old"], "johndoe")
        self.assertEqual(val_change["new"], "johndoes")

        self.assertEqual(len(delta.semantic_events), 1)
        self.assertEqual(delta.semantic_events[0].event_type, SemanticEventType.VALUE_CHANGED)

    async def test_03_meaningful_checkbox_toggle_delta(self) -> None:
        """Demonstrates meaningful checkbox toggle detected structurally and visually."""
        obs1 = await self.adapter.capture_observation()

        # Step time and toggle remember_me checkbox
        self.clock.advance(150.0)
        self.adapter.remember_me = True
        obs2 = await self.adapter.capture_observation()

        v_diff = self.differ.diff_frames(obs1.screenshot_bytes, obs2.screenshot_bytes)
        self.assertFalse(v_diff.is_static, "Visual differ must detect checkbox toggle")

        delta = self.adapter.compute_delta(
            obs1, obs2, pixel_change_ratio=v_diff.pixel_change_ratio, changed_boxes=v_diff.changed_boxes
        )
        self.assertFalse(delta.is_static)

        cb_events = [e for e in delta.semantic_events if e.event_type == SemanticEventType.CHECKBOX_TOGGLED]
        self.assertEqual(len(cb_events), 1)
        self.assertEqual(cb_events[0].previous_value, "false")
        self.assertEqual(cb_events[0].current_value, "true")

    async def test_04_warning_banner_appearance(self) -> None:
        """Demonstrates sudden appearance of a warning banner detected structurally and visually."""
        obs1 = await self.adapter.capture_observation()

        self.clock.advance(150.0)
        self.adapter.warning_active = True
        obs2 = await self.adapter.capture_observation()

        v_diff = self.differ.diff_frames(obs1.screenshot_bytes, obs2.screenshot_bytes)
        self.assertFalse(v_diff.is_static, "Visual differ must detect warning icon")

        delta = self.adapter.compute_delta(
            obs1, obs2, pixel_change_ratio=v_diff.pixel_change_ratio, changed_boxes=v_diff.changed_boxes
        )
        self.assertFalse(delta.is_static)
        self.assertIn("warn_banner", [n.node_id for n in delta.added_nodes])

        warn_events = [e for e in delta.semantic_events if e.event_type == SemanticEventType.WARNING_BANNER_SHOWN]
        self.assertEqual(len(warn_events), 1)

    async def test_05_noise_handling_without_suppressing_small_signals(self) -> None:
        """Demonstrates cursor blink is filtered as noise while single-character edit is preserved."""
        obs_base = await self.adapter.capture_observation()

        # Frame A: Cursor blink ON without typing
        self.clock.advance(500.0)
        self.adapter.cursor_blink_on = True
        obs_blink = await self.adapter.capture_observation()

        diff_blink = self.differ.diff_frames(obs_base.screenshot_bytes, obs_blink.screenshot_bytes)
        self.assertTrue(
            diff_blink.is_static,
            f"Blinking cursor must be rejected as noise by calibrated filter: {diff_blink.changed_boxes}",
        )

        # Frame B: User types 's' with cursor still on
        self.clock.advance(200.0)
        self.adapter.username = "johndoes"
        obs_typed = await self.adapter.capture_observation()

        diff_typed = self.differ.diff_frames(obs_base.screenshot_bytes, obs_typed.screenshot_bytes)
        self.assertFalse(
            diff_typed.is_static,
            "Typing single character with active cursor must NOT be suppressed",
        )

    async def test_06_malformed_input_corrupted_frame_handling(self) -> None:
        """Demonstrates that malformed/corrupted image bytes raise CorruptedFrameError."""
        grounder = MockVisionGrounder()
        corrupt_bytes = b"\x00\x11\x22CORRUPTED_NON_IMAGE_HEADER\xff\xee"

        with self.assertRaises(CorruptedFrameError):
            await grounder.parse_ui_elements(corrupt_bytes)

    async def test_07_unavailable_permissions_disconnect_and_recovery(self) -> None:
        """Demonstrates explicit error / degradation states and subsequent recovery."""
        # 1. Permission Denied Fault
        self.adapter.simulate_permission_denied()
        obs_perm = await self.adapter.capture_observation()
        self.assertEqual(obs_perm.quality, ObservationQuality.PERMISSION_DENIED)
        self.assertIsNotNone(obs_perm.error_message)

        # 2. Recovery from permission fault
        self.adapter.reconnect()
        obs_recovered1 = await self.adapter.capture_observation()
        self.assertEqual(obs_recovered1.quality, ObservationQuality.HEALTHY)

        # 3. Disconnect Fault
        self.adapter.simulate_disconnect()
        obs_disc = await self.adapter.capture_observation()
        self.assertEqual(obs_disc.quality, ObservationQuality.DISCONNECTED)
        self.assertIsNotNone(obs_disc.error_message)

        # 4. Recovery from disconnect
        self.adapter.reconnect()
        obs_recovered2 = await self.adapter.capture_observation()
        self.assertEqual(obs_recovered2.quality, ObservationQuality.HEALTHY)

    async def test_08_observe_stream_consumer(self) -> None:
        """Demonstrates streamed output consumed through the public observe_stream interface."""
        stream_results: List[PerceptionDelta] = []

        async def background_worker():
            async for delta in self.adapter.observe_stream(interval_ms=50.0, max_iterations=3):
                stream_results.append(delta)

        worker_task = asyncio.create_task(background_worker())

        # Simulate state changes while consumer streams
        await asyncio.sleep(0.06)
        self.adapter.username = "johndoe1"
        await asyncio.sleep(0.06)
        self.adapter.remember_me = True

        await worker_task
        self.assertEqual(len(stream_results), 3)
        self.assertIsInstance(stream_results[0], PerceptionDelta)


if __name__ == "__main__":
    unittest.main()
