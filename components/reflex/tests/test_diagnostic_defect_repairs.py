"""Regression tests for the seven repaired source-audit diagnostic defects (R1).

Each test pins the repaired behavior; the pre-repair behavior is recorded in
evidence/linux-candidate-probes-before.json.
"""

from __future__ import annotations

import io
import unittest

from reflex.episodes.bridge import PerceptionEpisodeBridge, compute_ui_state_hash
from reflex.perception.native.linux_atspi import (
    LinuxATSPIObservationAdapter,
    MockLinuxATSPISubstrate,
)
from reflex.perception.native.windows_uia import (
    MockWindowsUIASubstrate,
    WindowsUIAObservationAdapter,
)
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.observation import (
    CorruptedObservationError,
    ObservationQuality,
    ObservationRecord,
    SemanticEventType,
    validate_screenshot_bytes,
)
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


def make_observation(identifier: str, **changes) -> ObservationRecord:
    node = UIStateNode(
        "control", NodeRole.BUTTON, BoundingBox(5, 5, 55, 25), label="Send", **changes
    )
    graph = CanonicalUIGraph(
        1000.0, {node.node_id: node}, active_window_title="Synthetic diagnostic"
    )
    return ObservationRecord(identifier, 1000.0, "synthetic_probe", "fixture", graph)


class FailingScreenshotSource(ObservationPort):
    async def capture_state(self):
        return make_observation("source").graph

    async def capture_screenshot(self):
        raise ConnectionError("Deliberate synthetic screenshot acquisition failure")


class CounterSource(ObservationPort):
    def __init__(self):
        self.records = []

    async def capture_state(self):
        return make_observation("unused").graph

    async def capture_screenshot(self):
        return b""

    async def capture_observation(self):
        result = make_observation(
            f"capture-{len(self.records) + 1}", value=str(len(self.records) + 1)
        )
        self.records.append(result)
        return result


class InMemorySink:
    def __init__(self):
        self.transitions = []

    async def record_transition(self, transition):
        self.transitions.append(transition)


class TestDiagnosticDefectRepairs(unittest.IsolatedAsyncioTestCase):
    async def test_01_focus_change_returns_focus_event(self):
        delta = ObservationPort.compute_delta(
            make_observation("before"), make_observation("after", is_focused=True)
        )
        self.assertFalse(delta.is_static)
        self.assertEqual(len(delta.semantic_events), 1)
        self.assertEqual(
            delta.semantic_events[0].event_type, SemanticEventType.FOCUS_CHANGED
        )

    async def test_02_enabled_change_is_not_static_noop(self):
        delta = ObservationPort.compute_delta(
            make_observation("before"), make_observation("after", is_enabled=False)
        )
        self.assertFalse(delta.is_static)
        self.assertEqual(len(delta.modified_nodes), 1)
        self.assertIn("is_enabled", delta.modified_nodes[0]["changes"])
        self.assertEqual(
            delta.semantic_events[0].event_type, SemanticEventType.STATE_CHANGED
        )

    async def test_02b_role_change_is_detected(self):
        node = UIStateNode(
            "control", NodeRole.INPUT, BoundingBox(5, 5, 55, 25), label="Send"
        )
        graph = CanonicalUIGraph(
            1000.0, {node.node_id: node}, active_window_title="Synthetic diagnostic"
        )
        after = ObservationRecord("after", 1000.0, "synthetic_probe", "fixture", graph)
        delta = ObservationPort.compute_delta(make_observation("before"), after)
        self.assertFalse(delta.is_static)
        self.assertIn("role", delta.modified_nodes[0]["changes"])

    async def test_03_value_change_alters_episode_and_evidence_identity(self):
        before = make_observation("before", value="passed")
        after = make_observation("after", value="failed")
        self.assertNotEqual(compute_ui_state_hash(before), compute_ui_state_hash(after))
        self.assertNotEqual(
            before.graph.compute_evidence_hash(), after.graph.compute_evidence_hash()
        )
        # Restricted topology fingerprint is unchanged by design and labeled as such.
        self.assertEqual(
            before.graph.compute_state_hash(), after.graph.compute_state_hash()
        )

    async def test_04_stream_binds_exact_before_after_pair(self):
        source = CounterSource()
        sink = InMemorySink()
        transitions = await PerceptionEpisodeBridge(sink).stream_and_record_episode(
            source, "probe", interval_ms=0, max_steps=2
        )
        self.assertEqual(len(transitions), 2)
        self.assertEqual(
            [o.observation_id for o in source.records],
            ["capture-1", "capture-2", "capture-3"],
        )
        for step, tx in enumerate(transitions):
            self.assertEqual(
                tx.provenance["source_snapshot_id"], f"capture-{step + 1}"
            )
            self.assertEqual(
                tx.provenance["target_snapshot_id"], f"capture-{step + 2}"
            )

    async def test_05_screenshot_failure_degrades_with_reason(self):
        obs = await FailingScreenshotSource().capture_observation()
        self.assertEqual(obs.quality, ObservationQuality.DEGRADED)
        self.assertIsNone(obs.screenshot_bytes)
        self.assertIsNotNone(obs.error_message)
        self.assertIn("ConnectionError", obs.error_message)
        self.assertIn("screenshot", obs.platform_metadata["modality_status"])

    async def test_06_default_mock_serves_no_pixel_evidence(self):
        for adapter_cls, substrate_cls in (
            (LinuxATSPIObservationAdapter, MockLinuxATSPISubstrate),
            (WindowsUIAObservationAdapter, MockWindowsUIASubstrate),
        ):
            with self.subTest(adapter=adapter_cls.__name__):
                adapter = adapter_cls(
                    clock=DeterministicClock(start_time_ms=1000.0),
                    substrate=substrate_cls(),
                )
                await adapter.initialize()
                obs = await adapter.capture_observation()
                self.assertIsNone(obs.screenshot_bytes)
                self.assertNotEqual(obs.quality, ObservationQuality.HEALTHY)
                self.assertIsNotNone(obs.error_message)
                await adapter.teardown()

    async def test_06b_undecodable_bytes_are_corrupt_never_healthy(self):
        sub = MockLinuxATSPISubstrate()
        sub.screenshot_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRmock_linux_screenshot"
        adapter = LinuxATSPIObservationAdapter(
            clock=DeterministicClock(start_time_ms=1000.0), substrate=sub
        )
        await adapter.initialize()
        obs = await adapter.capture_observation()
        self.assertEqual(obs.quality, ObservationQuality.CORRUPTED)
        self.assertIsNotNone(obs.error_message)
        await adapter.teardown()

    async def test_06c_validator_accepts_real_png_rejects_garbage(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (8, 6), color="red").save(buf, format="PNG")
        self.assertEqual(validate_screenshot_bytes(buf.getvalue()), (8, 6))
        with self.assertRaises(CorruptedObservationError):
            validate_screenshot_bytes(b"not an image")
        with self.assertRaises(CorruptedObservationError):
            validate_screenshot_bytes(b"")

    async def test_07_future_dated_frame_is_not_fresh(self):
        obs = make_observation("future")
        object.__setattr__(obs, "timestamp_ms", 2000.0)
        object.__setattr__(obs, "freshness_duration_ms", 100.0)
        self.assertFalse(obs.is_fresh(current_time_ms=1000.0))
        # Ordinary freshness windows are unchanged.
        fresh = make_observation("fresh")
        object.__setattr__(fresh, "timestamp_ms", 1000.0)
        object.__setattr__(fresh, "freshness_duration_ms", 500.0)
        self.assertTrue(fresh.is_fresh(current_time_ms=1200.0))
        self.assertFalse(fresh.is_fresh(current_time_ms=1600.0))


if __name__ == "__main__":
    unittest.main()
