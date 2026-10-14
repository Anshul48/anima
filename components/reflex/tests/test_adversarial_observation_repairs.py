"""Adversarial regression tests for the coordinator's R1 observation findings.

Mirrors /tmp/reflex-coordinator-audit/adversarial-observation-results.json:
(1) capture_screenshot returning None must not yield healthy with no screenshot
modality entry; (2) record_transition_from_perception must reject a prev_obs
whose ID disagrees with delta.source_snapshot_id; (3) caller provenance must
not override authoritative source identity.

Tests inspect the sink's independent record count and observation quality
directly rather than mirroring implementation internals.
"""

from __future__ import annotations

import io
import unittest

from reflex.episodes.bridge import PerceptionEpisodeBridge
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.observation import (
    ObservationQuality,
    ObservationRecord,
    PerceptionError,
)
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


def make_observation(identifier: str, viewport=(1920, 1080), **changes) -> ObservationRecord:
    node = UIStateNode(
        "control", NodeRole.BUTTON, BoundingBox(5, 5, 55, 25), label="Send", **changes
    )
    graph = CanonicalUIGraph(
        1000.0,
        {node.node_id: node},
        active_window_title="Synthetic diagnostic",
        viewport_size=viewport,
    )
    return ObservationRecord(identifier, 1000.0, "synthetic_probe", "fixture", graph)


def make_png_bytes(width: int = 8, height: int = 6) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="blue").save(buf, format="PNG")
    return buf.getvalue()


class PixelSource(ObservationPort):
    """ObservationPort stub returning a fixed screenshot payload."""

    def __init__(self, payload, viewport=(1920, 1080)):
        self.payload = payload
        self.viewport = viewport

    async def capture_state(self):
        return make_observation("source", viewport=self.viewport).graph

    async def capture_screenshot(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class CountingSink:
    """Independent sink that only counts and retains recorded transitions."""

    def __init__(self):
        self.transitions = []

    async def record_transition(self, transition):
        self.transitions.append(transition)


class TestAdversarialObservationRepairs(unittest.IsolatedAsyncioTestCase):
    async def test_none_pixels_are_absent_never_healthy(self):
        obs = await PixelSource(None).capture_observation()
        self.assertIsNone(obs.screenshot_bytes)
        self.assertNotEqual(obs.quality, ObservationQuality.HEALTHY)
        self.assertEqual(obs.quality, ObservationQuality.DEGRADED)
        status = obs.platform_metadata["modality_status"]
        self.assertIn("screenshot", status)
        self.assertTrue(status["screenshot"].startswith("absent"))
        self.assertIsNotNone(obs.error_message)

    async def test_empty_pixels_are_absent_never_healthy(self):
        obs = await PixelSource(b"").capture_observation()
        self.assertEqual(obs.screenshot_bytes, b"")
        self.assertEqual(obs.quality, ObservationQuality.DEGRADED)
        status = obs.platform_metadata["modality_status"]
        self.assertIn("screenshot", status)
        self.assertTrue(status["screenshot"].startswith("absent"))
        self.assertIsNotNone(obs.error_message)

    async def test_garbage_pixels_stay_corrupt(self):
        obs = await PixelSource(b"\x89PNG\r\n\x1a\nnot-a-real-png").capture_observation()
        self.assertEqual(obs.quality, ObservationQuality.CORRUPTED)
        self.assertIsNotNone(obs.error_message)

    async def test_valid_pixels_stay_healthy(self):
        obs = await PixelSource(make_png_bytes(), viewport=(8, 6)).capture_observation()
        self.assertEqual(obs.quality, ObservationQuality.HEALTHY)
        self.assertIsNone(obs.error_message)
        self.assertEqual(
            obs.platform_metadata["modality_status"]["screenshot"], "ok: 8x6"
        )

    async def test_mismatched_before_is_rejected_with_zero_sink_writes(self):
        sink = CountingSink()
        bridge = PerceptionEpisodeBridge(sink)
        before = make_observation("real-before")
        after = make_observation("real-after", value="2")
        delta = ObservationPort.compute_delta(before, after)
        unrelated = make_observation("unrelated-before")
        with self.assertRaises(PerceptionError):
            await bridge.record_transition_from_perception(
                episode_id="ep_adv",
                step_index=0,
                prev_obs=unrelated,
                delta=delta,
                action=TypedAction(action_type=ActionType.NOOP),
                next_obs=after,
            )
        self.assertEqual(len(sink.transitions), 0)

    async def test_mismatched_after_is_rejected_with_zero_sink_writes(self):
        sink = CountingSink()
        bridge = PerceptionEpisodeBridge(sink)
        before = make_observation("real-before")
        after = make_observation("real-after", value="2")
        delta = ObservationPort.compute_delta(before, after)
        unrelated = make_observation("unrelated-after", value="2")
        with self.assertRaises(PerceptionError):
            await bridge.record_transition_from_perception(
                episode_id="ep_adv",
                step_index=0,
                prev_obs=before,
                delta=delta,
                action=TypedAction(action_type=ActionType.NOOP),
                next_obs=unrelated,
            )
        self.assertEqual(len(sink.transitions), 0)

    async def test_forged_source_provenance_is_rejected_with_zero_sink_writes(self):
        sink = CountingSink()
        bridge = PerceptionEpisodeBridge(sink)
        before = make_observation("real-before")
        after = make_observation("real-after", value="2")
        delta = ObservationPort.compute_delta(before, after)
        with self.assertRaises(PerceptionError):
            await bridge.record_transition_from_perception(
                episode_id="ep_adv",
                step_index=0,
                prev_obs=before,
                delta=delta,
                action=TypedAction(action_type=ActionType.NOOP),
                next_obs=after,
                provenance={"source_snapshot_id": "forged-source"},
            )
        self.assertEqual(len(sink.transitions), 0)

    async def test_forged_target_provenance_is_rejected_with_zero_sink_writes(self):
        sink = CountingSink()
        bridge = PerceptionEpisodeBridge(sink)
        before = make_observation("real-before")
        after = make_observation("real-after", value="2")
        delta = ObservationPort.compute_delta(before, after)
        with self.assertRaises(PerceptionError):
            await bridge.record_transition_from_perception(
                episode_id="ep_adv",
                step_index=0,
                prev_obs=before,
                delta=delta,
                action=TypedAction(action_type=ActionType.NOOP),
                next_obs=after,
                provenance={"target_snapshot_id": "forged-target"},
            )
        self.assertEqual(len(sink.transitions), 0)

    async def test_matching_ids_record_exactly_once_with_authoritative_identity(self):
        sink = CountingSink()
        bridge = PerceptionEpisodeBridge(sink)
        before = make_observation("real-before")
        after = make_observation("real-after", value="2")
        delta = ObservationPort.compute_delta(before, after)
        tx = await bridge.record_transition_from_perception(
            episode_id="ep_adv",
            step_index=0,
            prev_obs=before,
            delta=delta,
            action=TypedAction(action_type=ActionType.NOOP),
            next_obs=after,
            provenance={"note": "caller annotation"},
        )
        self.assertEqual(len(sink.transitions), 1)
        self.assertIs(sink.transitions[0], tx)
        self.assertEqual(tx.provenance["source_snapshot_id"], "real-before")
        self.assertEqual(tx.provenance["target_snapshot_id"], "real-after")
        self.assertEqual(tx.provenance["note"], "caller annotation")


if __name__ == "__main__":
    unittest.main()
