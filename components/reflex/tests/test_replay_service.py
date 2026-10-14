"""Offline tests for replay source, local service, and source epochs.

Uses synthetic observations and a real subprocess-hosted service over
localhost. The coordinator-executed runner replays these checks against a
real recorded source, an installed wheel, and a separately launched service
(see COORDINATOR-EXEC-REQUEST.md).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from reflex.perception.browser.cdp_provider import CDPObservationProvider, FakeCDPClient
from reflex.perception.replay import RecordingWriter, ReplaySource
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.observation import (
    CorruptedObservationError,
    ObservationQuality,
    ObservationRecord,
    PerceptionError,
)
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode
from reflex.service.client import PerceptionServiceClient, ServiceError


def make_png(color: str = "red", width: int = 16, height: int = 12) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="PNG")
    return buf.getvalue()


def make_obs(identifier: str, png: bytes | None = None, value: str = "1") -> ObservationRecord:
    node = UIStateNode(
        "control", NodeRole.BUTTON, BoundingBox(5, 5, 55, 25), label="Send", value=value
    )
    graph = CanonicalUIGraph(
        1000.0, {node.node_id: node}, active_window_title="Synthetic replay"
    )
    return ObservationRecord(
        identifier,
        1000.0,
        "synthetic_probe",
        "fixture",
        graph,
        screenshot_bytes=png,
        quality=ObservationQuality.HEALTHY if png else ObservationQuality.DEGRADED,
        platform_metadata={"modality_status": {"tree": "ok"}},
    )


class TestRecordingReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.recording = os.path.join(self.tmp.name, "rec-001")

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_replay_in_order_with_same_ids(self):
        writer = RecordingWriter(self.recording, source_identity={"adapter": "synthetic"})
        png_a, png_b = make_png("red"), make_png("blue")
        writer.write(make_obs("frame-a", png=png_a, value="1"))
        writer.write(make_obs("frame-b", png=png_b, value="2"))
        writer.write(make_obs("frame-c", png=None, value="3"))
        manifest = writer.manifest()
        self.assertEqual([f["frame_id"] for f in manifest["frames"]], ["frame-a", "frame-b", "frame-c"])
        self.assertIsNotNone(manifest["frames"][0]["png_sha256"])
        self.assertIsNone(manifest["frames"][2]["png_sha256"])

        import asyncio

        async def run():
            source = ReplaySource(self.recording)
            first = await source.capture_observation()
            second = await source.capture_observation()
            return source, first, second

        source, first, second = asyncio.run(run())
        self.assertEqual(first.observation_id, "frame-a")
        self.assertEqual(second.observation_id, "frame-b")
        self.assertTrue(first.platform_metadata["replay"])
        self.assertEqual(first.platform_metadata["recording_id"], "rec-001")
        self.assertEqual(first.screenshot_bytes, png_a)
        self.assertEqual(second.screenshot_bytes, png_b)
        # Replayed frames keep recorded timestamps: stale against a live clock,
        # never silently acquiring live validity.
        self.assertFalse(first.is_fresh())
        # Delta over replayed pair binds the recorded IDs.
        delta = ObservationPort.compute_delta(first, second)
        self.assertEqual(delta.source_snapshot_id, "frame-a")
        self.assertEqual(delta.target_snapshot_id, "frame-b")

    def test_tampered_pixels_fail_closed(self):
        writer = RecordingWriter(self.recording)
        writer.write(make_obs("frame-a", png=make_png("red")))
        with open(os.path.join(self.recording, "frames", "frame-a.png"), "wb") as fh:
            fh.write(make_png("green"))

        import asyncio

        async def run():
            await ReplaySource(self.recording).capture_observation()

        with self.assertRaises(CorruptedObservationError):
            asyncio.run(run())

    def test_missing_pixels_with_expected_digest_fail_explicitly(self):
        writer = RecordingWriter(self.recording)
        writer.write(make_obs("frame-a", png=make_png("red")))
        os.remove(os.path.join(self.recording, "frames", "frame-a.png"))

        import asyncio

        async def run():
            await ReplaySource(self.recording).capture_observation()

        with self.assertRaises(PerceptionError):
            asyncio.run(run())

    def test_seek_and_unknown_frame(self):
        writer = RecordingWriter(self.recording)
        writer.write(make_obs("frame-a", png=make_png("red")))
        writer.write(make_obs("frame-b", png=make_png("blue")))
        source = ReplaySource(self.recording)
        source.seek("frame-b")
        self.assertEqual(source.cursor_frame_id, "frame-b")
        with self.assertRaises(PerceptionError):
            source.seek("no-such-frame")


class TestCdpEpochs(unittest.TestCase):
    def test_epoch_stamped_and_rotates(self):
        import asyncio

        async def run():
            fake = FakeCDPClient()
            fake.screenshot_bytes = make_png("red", 32, 24)
            provider = CDPObservationProvider(
                cdp_session=fake, prefer_js_distiller=False, viewport_size=(32, 24)
            )
            first = await provider.capture_observation()
            epoch = provider.session_epoch
            provider.new_epoch()
            second = await provider.capture_observation()
            return first, second, epoch, provider.session_epoch

        first, second, epoch, rotated = asyncio.run(run())
        self.assertEqual(first.source_adapter, "cdp_chromium")
        self.assertEqual(first.platform, "linux")
        self.assertEqual(first.platform_metadata["session_epoch"], epoch)
        self.assertNotEqual(epoch, rotated)
        self.assertEqual(second.platform_metadata["session_epoch"], rotated)
        self.assertEqual(first.quality, ObservationQuality.HEALTHY)

    def test_binding_epochs_stamped_for_warm_and_tracking(self):
        import asyncio

        async def run():
            fake = FakeCDPClient()
            fake.screenshot_bytes = make_png("red", 32, 24)
            provider = CDPObservationProvider(
                cdp_session=fake, prefer_js_distiller=False, viewport_size=(32, 24)
            )
            return provider, await provider.capture_observation()

        provider, obs = asyncio.run(run())
        meta = obs.platform_metadata
        self.assertEqual(meta["surface_epoch"], provider.session_epoch)
        self.assertTrue(meta["surface_epoch"])
        doc_a = meta["document_epoch"]
        self.assertTrue(isinstance(doc_a, str) and len(doc_a) == 16)
        # Same document, second capture: stable.
        obs2 = asyncio.run(provider.capture_observation())
        self.assertEqual(obs2.platform_metadata["document_epoch"], doc_a)
        # URL change advances the document epoch.
        other = provider._document_epoch(
            type(obs.graph)(timestamp_ms=1.0, nodes={}, url="http://other/")
        )
        self.assertNotEqual(other, doc_a)

    def test_unbound_provider_reports_unavailable_not_dummy_bytes(self):
        import asyncio

        async def run():
            return await CDPObservationProvider().capture_observation()

        obs = asyncio.run(run())
        self.assertEqual(obs.quality, ObservationQuality.DEGRADED)
        self.assertIsNone(obs.screenshot_bytes)
        self.assertIn("no bound page", (obs.error_message or "").lower())


SERVICE_MAIN = """\
import sys
from reflex.perception.replay import ReplaySource
from reflex.service.server import serve_forever
serve_forever(ReplaySource(sys.argv[1]))
"""


class TestSeparateProcessService(unittest.TestCase):
    def test_subprocess_service_observe_update_query(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        recording = os.path.join(tmp.name, "rec-svc")
        writer = RecordingWriter(recording)
        writer.write(make_obs("frame-a", png=make_png("red"), value="1"))
        writer.write(make_obs("frame-b", png=make_png("blue"), value="2"))

        main_path = os.path.join(tmp.name, "svc_main.py")
        with open(main_path, "w", encoding="utf-8") as fh:
            fh.write(SERVICE_MAIN)
        env = dict(os.environ)
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
            env.pop(var, None)
        proc = subprocess.Popen(
            [sys.executable, main_path, recording],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=tmp.name,
        )
        self.addCleanup(lambda: proc.kill() if proc.poll() is None else None)
        try:
            assert proc.stdout is not None
            base_url = None
            deadline = time.time() + 30.0
            output_lines = []
            while time.time() < deadline:
                line = proc.stdout.readline()
                if not line:
                    break
                output_lines.append(line)
                if line.startswith("REFLEX_SERVICE_URL="):
                    base_url = line.strip().split("=", 1)[1]
                    break
            self.assertIsNotNone(base_url, f"service did not start: {''.join(output_lines)}")
            assert base_url is not None
            client = PerceptionServiceClient(base_url, timeout_s=10.0)
            health = client.health()
            self.assertEqual(health["status"], "ok")
            self.assertEqual(health["recording_id"], "rec-svc")

            first = client.observe()
            self.assertEqual(first.observation_id, "frame-a")
            import hashlib

            self.assertEqual(
                hashlib.sha256(first.screenshot_bytes or b"").hexdigest(),
                writer.manifest()["frames"][0]["png_sha256"],
            )
            second, delta = client.update("frame-a")
            self.assertEqual(second.observation_id, "frame-b")
            self.assertEqual(delta.source_snapshot_id, "frame-a")
            self.assertEqual(delta.target_snapshot_id, "frame-b")
            nodes = client.query("frame-b", by="role", value="button")
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0]["node_id"], "control")
            with self.assertRaises(ServiceError) as ctx:
                client.update("no-such-id")
            self.assertEqual(ctx.exception.status, 404)
            client.shutdown()
            proc.wait(timeout=15.0)
        finally:
            if proc.poll() is None:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
