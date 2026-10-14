"""Regression tests for CHECK-A leg-(iii): platform-neutral UI-state identity.

Ports the failing cases from the CHECK-A instrument into the suite: the
Tier-1 envelope-only lanes (identical canonical graphs, Win vs Linux envelope)
diverged at exactly `tx.ui_state_hash`, `tx.next_ui_state_hash`,
`ui_state_hash0/1` because `compute_ui_state_hash` mixed the adapter platform
label into core memory identity. These tests pin the fixed contract in
docs/contract/ui-state-hash-spec.md — the same instrument that found the
defect now verifies the fix.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import unittest

from reflex.episodes.bridge import (
    LEGACY_UI_STATE_HASH_LABEL,
    UI_STATE_HASH_LENGTH,
    UI_STATE_HASH_TAG,
    UI_STATE_HASH_VERSION,
    PerceptionEpisodeBridge,
    compute_ui_state_hash,
    compute_ui_state_hash_legacy,
)
from reflex.episodes.journal import LocalEpisodeJournal
from reflex.perception.native.linux_atspi import (
    LinuxATSPIObservationAdapter,
    MockLinuxATSPISubstrate,
)
from reflex.ports.clock import DeterministicClock
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, TypedAction
from reflex.schemas.observation import ObservationQuality, ObservationRecord
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


def _wifi_graph(value: str, timestamp_ms: float = 50000.0) -> CanonicalUIGraph:
    """CHECK-A leg-(iii) canonical graph: one wifi toggle node."""
    return CanonicalUIGraph(
        timestamp_ms=timestamp_ms,
        nodes={
            "wifi_toggle": UIStateNode(
                node_id="wifi_toggle",
                role=NodeRole.TOGGLE,
                bounds=BoundingBox(50, 100, 130, 132),
                label="Wi-Fi Enable",
                value=value,
                is_clickable=True,
                is_focused=True,
            )
        },
        active_window_title="Settings",
    )


def _envelope_obs(graph: CanonicalUIGraph, lane: str) -> ObservationRecord:
    """Same canonical graph, adapter-distinctive envelope per CHECK-A Tier 1."""
    if lane == "win":
        return ObservationRecord(
            observation_id="obs_win_001",
            timestamp_ms=50100.0,
            source_adapter="windows_uia",
            platform="windows",
            graph=graph,
            screenshot_bytes=b"\x89PNG-win",
            quality=ObservationQuality.DEGRADED,
            error_message="Win32 live execution unavailable in Linux WSL2 environment.",
            platform_metadata={"uia_version": "3.0", "is_live_win32": False},
        )
    return ObservationRecord(
        observation_id="obs_linux_001",
        timestamp_ms=50200.0,
        source_adapter="linux_atspi",
        platform="linux",
        graph=graph,
        screenshot_bytes=b"\x89PNG-linux",
        quality=ObservationQuality.HEALTHY,
        error_message=None,
        platform_metadata={"bus": "at-spi2", "is_live": False},
    )


class TestUIStateHashPlatformNeutral(unittest.IsolatedAsyncioTestCase):
    """CHECK-A Tier-1 identity: envelope differs, core hash must not."""

    def test_tier1_same_graph_different_envelope_identical_hash(self) -> None:
        """CHECK-A T1 failing paths ui_state_hash0/1: identical across lanes."""
        graph = _wifi_graph("off")
        win_hash = compute_ui_state_hash(_envelope_obs(graph, "win"))
        linux_hash = compute_ui_state_hash(_envelope_obs(graph, "linux"))
        self.assertEqual(win_hash, linux_hash)

    async def test_tier1_transition_hashes_identical_across_platforms(self) -> None:
        """CHECK-A T1 failing paths tx.ui_state_hash/next: identical post-N1 lanes."""
        for lane in ("win", "linux"):
            journal = LocalEpisodeJournal(db_path=":memory:")
            bridge = PerceptionEpisodeBridge(journal=journal)
            obs0 = _envelope_obs(_wifi_graph("off"), lane)
            obs1 = dataclasses.replace(
                _envelope_obs(_wifi_graph("on"), lane),
                observation_id=f"obs_{lane}_002",
            )
            delta = ObservationPort.compute_delta(obs0, obs1)
            tx = await bridge.record_transition_from_perception(
                episode_id="checka-iii",
                step_index=1,
                prev_obs=obs0,
                delta=delta,
                action=TypedAction(action_type=ActionType.CLICK, target_node_id="wifi_toggle"),
                next_obs=obs1,
                goal_text="toggle wifi",
            )
            if lane == "win":
                win_prev, win_next = tx.ui_state_hash, tx.next_ui_state_hash
            else:
                linux_prev, linux_next = tx.ui_state_hash, tx.next_ui_state_hash
            await journal.close()
        self.assertEqual(win_prev, linux_prev)
        self.assertEqual(win_next, linux_next)

    async def test_real_adapter_relabel_identical_hash(self) -> None:
        """CHECK-A corrob.py: real adapter output relabeled linux->windows."""
        clock = DeterministicClock(start_time_ms=50000.0)
        sub = MockLinuxATSPISubstrate()
        sub.add_window(title="Settings Manager", app_name="gnome-settings", is_focused=True)
        sub.add_element(
            element_id="wifi_toggle",
            name="Wi-Fi Enable",
            role="ROLE_TOGGLE_BUTTON",
            extents=(50, 100, 80, 32),
            value="off",
            is_clickable=True,
            is_focused=True,
        )
        adapter = LinuxATSPIObservationAdapter(clock=clock, substrate=sub)
        await adapter.initialize()
        obs = await adapter.capture_observation()
        relabeled = dataclasses.replace(obs, platform="windows")
        self.assertEqual(compute_ui_state_hash(obs), compute_ui_state_hash(relabeled))

    def test_value_change_still_alters_hash(self) -> None:
        """Sensitivity preserved: content changes alter identity."""
        before = compute_ui_state_hash(_envelope_obs(_wifi_graph("off"), "linux"))
        after = compute_ui_state_hash(_envelope_obs(_wifi_graph("on"), "linux"))
        self.assertNotEqual(before, after)

    def test_deterministic(self) -> None:
        """Same observation hashes identically on repeat (CHECK-A self-check)."""
        obs = _envelope_obs(_wifi_graph("off"), "win")
        self.assertEqual(compute_ui_state_hash(obs), compute_ui_state_hash(obs))


class TestUIStateHashSpecConformance(unittest.TestCase):
    """Pins docs/contract/ui-state-hash-spec.md reference formula + legacy split."""

    def test_reference_recomputation_and_format(self) -> None:
        obs = _envelope_obs(_wifi_graph("off"), "linux")
        expected = hashlib.sha256(
            f"{UI_STATE_HASH_TAG}:{obs.graph.compute_evidence_hash()}".encode("utf-8")
        ).hexdigest()[:UI_STATE_HASH_LENGTH]
        actual = compute_ui_state_hash(obs)
        self.assertEqual(actual, expected)
        self.assertEqual(UI_STATE_HASH_VERSION, "v1")
        self.assertEqual(UI_STATE_HASH_TAG, "reflex-ui-state/v1")
        self.assertRegex(actual, r"\A[0-9a-f]{16}\Z")

    def test_spec_test_vector(self) -> None:
        """Worked vector from spec §4 guards the full serialization stack."""
        graph = _wifi_graph("off")
        self.assertEqual(
            graph.compute_evidence_hash(),
            "5a233714a6b73ed2730d6e5b1f1406453ee76a5df12d35ab2c900a10297b56ac",
        )
        obs = ObservationRecord(
            observation_id="obs_vector",
            timestamp_ms=50000.0,
            source_adapter="spec",
            platform="spec",
            graph=graph,
        )
        self.assertEqual(compute_ui_state_hash(obs), "3a757f998594459e")

    def test_legacy_generation_split(self) -> None:
        """v0 stays platform-qualified (labeled legacy); v1 differs by design."""
        self.assertEqual(LEGACY_UI_STATE_HASH_LABEL, "legacy/v0-platform-qualified")
        graph = _wifi_graph("off")
        win = _envelope_obs(graph, "win")
        linux = _envelope_obs(graph, "linux")
        # The CHECK-A defect, frozen as the legacy characterization:
        self.assertNotEqual(
            compute_ui_state_hash_legacy(win), compute_ui_state_hash_legacy(linux)
        )
        # Generations never collide on this graph (spec §5: never compare):
        self.assertNotEqual(compute_ui_state_hash(linux), compute_ui_state_hash_legacy(linux))


if __name__ == "__main__":
    unittest.main()
