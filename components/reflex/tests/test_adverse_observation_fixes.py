"""Focused regression tests for the nine adverse observation findings.

Each test uses nontrivial fault inputs against the repaired code paths:
observed-viewport grounding, dimension binding, tree-fault preservation,
cross-modality tear detection, focus loss, reparenting, stream pixel
comparison, source-identity advance, and snapshot immutability.
"""

from __future__ import annotations

import io
import json
import unittest

from reflex.perception.browser.cdp_provider import CDPObservationProvider, FakeCDPClient
from reflex.perception.browser.managed_chromium import CDPPage
from reflex.ports.observation import ObservationPort, bind_pixel_geometry
from reflex.schemas.actions import NormalizedCoords
from reflex.schemas.observation import ObservationQuality, ObservationRecord, SemanticEventType
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


def make_png(color: str = "red", width: int = 64, height: int = 48) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="PNG")
    return buf.getvalue()


def make_node(node_id="target", **kw):
    args = dict(label="Target", value="")
    args.update(kw)
    return UIStateNode(node_id, NodeRole.BUTTON, BoundingBox(1, 1, 20, 20), **args)


def make_graph(nodes, viewport=(64, 48), **kw):
    return CanonicalUIGraph(1000.0, nodes, viewport_size=viewport, **kw)


def make_obs(identifier, graph, png=None, adapter="synthetic", platform="linux", meta=None, quality=None):
    return ObservationRecord(
        identifier, 1000.0, adapter, platform, graph,
        screenshot_bytes=png,
        quality=quality or (ObservationQuality.HEALTHY if png else ObservationQuality.DEGRADED),
        platform_metadata=meta or {},
    )


class FlippingPage:
    """Page whose tree flips label after the first screenshot (torn fixture)."""

    def __init__(self, png_a, png_b, torn=True):
        self.png_a, self.png_b = png_a, png_b
        self.torn = torn
        self.shots = 0

    async def evaluate(self, script):
        label = "FRAME-A" if (not self.torn or self.shots == 0) else "FRAME-B"
        return {
            "url": "http://fixture/", "title": "T",
            "document_revision": 0 if label == "FRAME-A" else 1,
            "viewport_size": [64, 48],
            "nodes": {"target": {"role": "button", "label": label, "bounds": [1, 1, 20, 20]}},
        }

    async def screenshot(self, type="png"):
        self.shots += 1
        return self.png_a if self.shots == 1 else self.png_b


class FailingPage:
    async def evaluate(self, script):
        raise ConnectionError("DevTools target crashed")

    async def screenshot(self, type="png"):
        return make_png("red")


class EmptyPage:
    async def evaluate(self, script):
        return {"url": "http://fixture/", "title": "T", "viewport_size": [64, 48], "nodes": {}}

    async def screenshot(self, type="png"):
        return make_png("red")


class TestAdverseObservationFixes(unittest.IsolatedAsyncioTestCase):
    async def test_01_grounding_uses_observed_viewport(self):
        from reflex.execution.input.synthetic_input_adapter import SyntheticInputAdapter

        client = FakeCDPClient(viewport_size=(800, 457))
        page = CDPPage(client, viewport_size=(800, 600))
        adapter = SyntheticInputAdapter(page=page)
        # Grounding only (no dispatch, no lease): observed 800x457 wins.
        self.assertEqual(
            adapter.to_pixel_coords(NormalizedCoords(x=0.5, y=0.5)), (400, 228)
        )
        self.assertEqual(page.requested_viewport_size, (800, 600))

    async def test_01b_capture_updates_page_viewport(self):
        page = FlippingPage(make_png("red"), make_png("red"), torn=False)
        provider = CDPObservationProvider(page=page, viewport_size=(999, 999))
        real_page = CDPPage(FakeCDPClient(), viewport_size=(999, 999))
        provider.page = real_page
        real_page.evaluate = page.evaluate  # type: ignore[method-assign]

        async def shot(type="png"):
            return make_png("red")

        real_page.screenshot = shot  # type: ignore[method-assign]
        await provider.capture_observation()
        self.assertEqual(
            (real_page.viewport_size["width"], real_page.viewport_size["height"]), (64, 48)
        )
        self.assertEqual(real_page.requested_viewport_size, (999, 999))

    async def test_02_dimension_mismatch_degrades_with_transform(self):
        ok, transform, error = bind_pixel_geometry((64, 48), (640, 480))
        self.assertFalse(ok)
        self.assertFalse(transform["verified"])
        self.assertIsNotNone(error)

        class Mismatched(ObservationPort):
            async def capture_state(self):
                return make_graph({"t": make_node("t")}, viewport=(640, 480))

            async def capture_screenshot(self):
                return make_png("red")

        obs = await Mismatched().capture_observation()
        self.assertEqual(obs.quality, ObservationQuality.DEGRADED)
        self.assertIn("coordinate_transform", obs.platform_metadata)
        self.assertFalse(obs.platform_metadata["coordinate_transform"]["verified"])
        self.assertIsNotNone(obs.error_message)

    async def test_02b_matching_dimensions_stay_healthy(self):
        class Matched(ObservationPort):
            async def capture_state(self):
                return make_graph({"t": make_node("t")}, viewport=(64, 48))

            async def capture_screenshot(self):
                return make_png("red")

        obs = await Matched().capture_observation()
        self.assertEqual(obs.quality, ObservationQuality.HEALTHY)
        self.assertTrue(obs.platform_metadata["coordinate_transform"]["verified"])

    async def test_03_tree_fault_is_not_valid_empty(self):
        provider = CDPObservationProvider(page=FailingPage())
        obs = await provider.capture_observation()
        self.assertEqual(len(obs.graph.nodes), 0)
        self.assertNotEqual(obs.quality, ObservationQuality.HEALTHY)
        self.assertTrue(
            obs.platform_metadata["modality_status"]["tree"].startswith("fault")
        )
        self.assertIsNotNone(obs.error_message)

    async def test_03b_honest_empty_tree_stays_ok(self):
        provider = CDPObservationProvider(page=EmptyPage())
        obs = await provider.capture_observation()
        self.assertEqual(len(obs.graph.nodes), 0)
        self.assertEqual(obs.platform_metadata["modality_status"]["tree"], "ok")

    async def test_04_torn_modalities_degrade_with_binding(self):
        provider = CDPObservationProvider(
            page=FlippingPage(make_png("red"), make_png("blue"), torn=True)
        )
        obs = await provider.capture_observation()
        self.assertNotEqual(obs.quality, ObservationQuality.HEALTHY)
        binding = obs.platform_metadata["capture_binding"]
        self.assertFalse(binding["same_state"])
        self.assertEqual(binding["status"], "asynchronous")
        self.assertTrue(binding["requires_target_revalidation"])
        self.assertEqual(binding["tree_revision"], 0)
        self.assertEqual(binding["pixel_revision"], 1)

    async def test_04b_stable_capture_reports_consistent_binding(self):
        provider = CDPObservationProvider(
            page=FlippingPage(make_png("red"), make_png("red"), torn=False)
        )
        obs = await provider.capture_observation()
        binding = obs.platform_metadata["capture_binding"]
        self.assertTrue(binding["same_state"])
        self.assertEqual(binding["status"], "pre-post-consistent")

    async def test_05_focus_loss_emits_event(self):
        before = make_obs("a", make_graph({"t": make_node("t", is_focused=True)}))
        after = make_obs("b", make_graph({"t": make_node("t", is_focused=False)}))
        delta = ObservationPort.compute_delta(before, after)
        self.assertFalse(delta.is_static)
        self.assertEqual(delta.semantic_events[0].event_type, SemanticEventType.FOCUS_CHANGED)
        self.assertIn("lost", delta.semantic_events[0].description)

    async def test_06_reparenting_is_represented(self):
        before = make_obs(
            "a",
            make_graph({
                "p1": make_node("p1", children_ids=["t"]),
                "p2": make_node("p2"),
                "t": make_node("t", parent_id="p1"),
            }),
        )
        after = make_obs(
            "b",
            make_graph({
                "p1": make_node("p1"),
                "p2": make_node("p2", children_ids=["t"]),
                "t": make_node("t", parent_id="p2"),
            }),
        )
        delta = ObservationPort.compute_delta(before, after)
        self.assertFalse(delta.is_static)
        target = [m for m in delta.modified_nodes if m["node_id"] == "t"][0]
        self.assertIn("parent_id", target["changes"])

    async def test_07_stream_computes_pixel_change(self):
        red, blue = make_png("red"), make_png("blue")

        class Flip(ObservationPort):
            def __init__(self):
                self.n = 0

            async def capture_state(self):
                return make_graph({"t": make_node("t")}, viewport=(64, 48))

            async def capture_screenshot(self):
                self.n += 1
                return red if self.n == 1 else blue

        deltas = []
        async for delta in Flip().observe_stream(interval_ms=0, max_iterations=1):
            deltas.append(delta)
        self.assertGreater(deltas[0].pixel_change_ratio, 0.0)
        self.assertEqual(deltas[0].pixel_status, "ok")
        self.assertTrue(len(deltas[0].changed_bounding_boxes) > 0)

    async def test_07b_missing_pixels_have_explicit_status(self):
        class NoPixels(ObservationPort):
            async def capture_state(self):
                return make_graph({"t": make_node("t")})

            async def capture_screenshot(self):
                return None

        deltas = []
        async for delta in NoPixels().observe_stream(interval_ms=0, max_iterations=1):
            deltas.append(delta)
        self.assertEqual(deltas[0].pixel_status, "missing")
        self.assertEqual(deltas[0].pixel_change_ratio, 0.0)

    async def test_08_target_epoch_change_detected(self):
        old = make_obs(
            "a", make_graph({"t": make_node("t")}),
            meta={"target_id": "A", "session_epoch": "e1"},
        )
        new = make_obs(
            "b", make_graph({"t": make_node("t")}),
            meta={"target_id": "B", "session_epoch": "e2"},
        )
        delta = ObservationPort.compute_delta(old, new)
        types = [e.event_type for e in delta.semantic_events]
        self.assertIn(SemanticEventType.SOURCE_CHANGED, types)
        self.assertTrue(delta.source_binding["changed"])
        self.assertNotEqual(delta.outcome_class.value, "noop")

    async def test_08b_same_source_static_stays_noop(self):
        old = make_obs("a", make_graph({"t": make_node("t")}), meta={"target_id": "A"})
        new = make_obs("b", make_graph({"t": make_node("t")}), meta={"target_id": "A"})
        delta = ObservationPort.compute_delta(old, new)
        self.assertTrue(delta.is_static)
        self.assertEqual(delta.outcome_class.value, "noop")
        self.assertIsNone(delta.source_binding)

    async def test_09_nested_mutation_blocked_hash_stable(self):
        graph = make_graph({"t": make_node("t", attributes={"caller": {"deep": [1]}})})
        obs = make_obs(
            "a", graph, png=make_png("red"),
            meta={"modality_status": {"tree": "ok", "screenshot": "ok: 64x48"}},
        )
        before = graph.compute_evidence_hash()
        with self.assertRaises(TypeError):
            obs.graph.nodes["t"].attributes["caller-written"] = "x"
        with self.assertRaises(TypeError):
            obs.graph.nodes["evil"] = make_node("evil")
        with self.assertRaises(TypeError):
            obs.graph.nodes["t"].children_ids.append("x")
        with self.assertRaises(TypeError):
            obs.platform_metadata["modality_status"]["screenshot"] = "forged"
        self.assertEqual(graph.compute_evidence_hash(), before)
        # Frozen containers still equal and serialize like plain ones.
        self.assertEqual(dict(obs.graph.nodes["t"].attributes["caller"]), {"deep": [1]})
        json.dumps(obs.to_dict())
        json.dumps(obs.platform_metadata)


if __name__ == "__main__":
    unittest.main()
