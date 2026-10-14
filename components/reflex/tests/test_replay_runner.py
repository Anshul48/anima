"""Unit and integration test suite for EpisodeReplayRunner.

Tests deterministic episode replay, drift detection, determinism ratio metrics,
parameter binding substitution, and early termination on drift.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional
import unittest

from reflex.episodes.journal import LocalEpisodeJournal
from reflex.episodes.replay_runner import (
    EpisodeReplayRunner,
    ReplayReport,
    ReplayStepResult,
)
from reflex.ports.action import ActionPort, ActionReceipt, ActionStatus
from reflex.ports.observation import ObservationPort
from reflex.schemas.actions import ActionType, NormalizedCoords, SafetyClass, TypedAction
from reflex.schemas.delta import OutcomeClass, StateDelta
from reflex.schemas.identity import ActionIdentity
from reflex.schemas.memory import TransitionTuple
from reflex.schemas.state import BoundingBox, CanonicalUIGraph, NodeRole, UIStateNode


class MockObservationPort(ObservationPort):
    """Deterministic Mock Observation Port returning pre-configured state sequence."""

    def __init__(self, states_sequence: Optional[List[CanonicalUIGraph]] = None) -> None:
        self.states = list(states_sequence or [])
        self.call_index: int = 0

    def add_state(self, state: CanonicalUIGraph) -> None:
        self.states.append(state)

    async def capture_state(self) -> CanonicalUIGraph:
        if self.call_index < len(self.states):
            state = self.states[self.call_index]
            self.call_index += 1
            return state
        elif self.states:
            return self.states[-1]
        return CanonicalUIGraph(timestamp_ms=0.0, nodes={})

    async def capture_screenshot(self) -> bytes:
        return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


class MockActionPort(ActionPort):
    """Deterministic Mock Action Port recording dispatched actions."""

    def __init__(self) -> None:
        self.dispatched_actions: List[Tuple[TypedAction, ActionIdentity]] = []

    async def dispatch_action(self, action: TypedAction, identity: ActionIdentity) -> Dict[str, Any]:
        self.dispatched_actions.append((action, identity))
        return {
            "lease_id": f"lease_{identity.action_id}",
            "action_id": identity.action_id,
            "status": "dispatched",
        }


class TestEpisodeReplayRunner(unittest.IsolatedAsyncioTestCase):
    """Test suite for Deterministic Replay Engine."""

    def _build_state(
        self,
        node_labels: Dict[str, str],
        url: str = "http://example.com/app",
        timestamp_ms: float = 1000.0,
    ) -> CanonicalUIGraph:
        nodes = {}
        for nid, label in node_labels.items():
            nodes[nid] = UIStateNode(
                node_id=nid,
                role=NodeRole.BUTTON if "btn" in nid else NodeRole.INPUT,
                bounds=BoundingBox(10, 10, 100, 30),
                label=label,
            )
        return CanonicalUIGraph(
            timestamp_ms=timestamp_ms,
            nodes=nodes,
            url=url,
        )

    def _create_transition(
        self,
        trans_id: str,
        ep_id: str,
        step_idx: int,
        state_0: CanonicalUIGraph,
        state_1: CanonicalUIGraph,
        action: TypedAction,
    ) -> TransitionTuple:
        return TransitionTuple(
            transition_id=trans_id,
            episode_id=ep_id,
            step_index=step_idx,
            timestamp_ms=state_0.timestamp_ms,
            ui_state_hash=state_0.compute_state_hash(),
            goal_text="Step goal",
            goal_embedding=[0.1, 0.2],
            visual_embedding=None,
            action=action,
            next_ui_state_hash=state_1.compute_state_hash(),
            delta=StateDelta(outcome_class=OutcomeClass.SUCCESS),
            duration_ms=50.0,
            surprise_score=0.0,
            provenance={},
        )

    # =========================================================================
    # 1. Deterministic Replay Pass (determinism_ratio == 1.0)
    # =========================================================================

    async def test_deterministic_replay_pass(self) -> None:
        """Asserts replaying identical state progression yields determinism_ratio == 1.0."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            # Build States
            s0 = self._build_state({"btn_login": "Login", "inp_user": ""})
            s1 = self._build_state({"btn_login": "Login", "inp_user": "alice"})
            s2 = self._build_state({"btn_submit": "Submit Form", "dashboard_view": "Welcome Alice"})

            # Build Actions
            a0 = TypedAction(action_type=ActionType.TYPE, target_node_id="inp_user", text_payload="alice")
            a1 = TypedAction(action_type=ActionType.CLICK, target_node_id="btn_submit")

            # Build Transitions
            t0 = self._create_transition("t0", "ep_auth", 0, s0, s1, a0)
            t1 = self._create_transition("t1", "ep_auth", 1, s1, s2, a1)

            await journal.record_transition(t0)
            await journal.record_transition(t1)

            # Replay against mock environment emitting [s1, s2] upon action dispatch
            mock_obs = MockObservationPort([s1, s2])
            mock_act = MockActionPort()

            runner = EpisodeReplayRunner(
                journal=journal,
                observation_port=mock_obs,
                action_port=mock_act,
            )

            report = await runner.replay_episode("ep_auth")

            # Assert Report Metrics
            self.assertEqual(report.episode_id, "ep_auth")
            self.assertEqual(report.total_steps, 2)
            self.assertEqual(report.matched_steps, 2)
            self.assertEqual(report.determinism_ratio, 1.0)
            self.assertTrue(report.is_fully_deterministic)

            # Assert Action Dispatches
            self.assertEqual(len(mock_act.dispatched_actions), 2)
            self.assertEqual(mock_act.dispatched_actions[0][0].text_payload, "alice")
            self.assertEqual(mock_act.dispatched_actions[1][0].target_node_id, "btn_submit")

            # Step Results Verification
            for res in report.step_results:
                self.assertTrue(res.is_deterministic_match)
                self.assertIsNone(res.drift_details)
        finally:
            await journal.close()

    # =========================================================================
    # 2. Non-Deterministic Drift Detection
    # =========================================================================

    async def test_drift_detection_and_determinism_ratio(self) -> None:
        """Asserts state drift is detected, reported, and determinism_ratio reflects mismatches."""
        journal = LocalEpisodeJournal(":memory:")
        try:
            s0 = self._build_state({"btn_1": "Step 1"})
            s1_expected = self._build_state({"btn_2": "Step 2"})
            s2_expected = self._build_state({"btn_3": "Step 3"})

            # Drifting s1 observed in replay (button text changed or unexpected popup)
            s1_drifted = self._build_state({"btn_2": "Drifted Text", "popup_alert": "Server Error"})

            t0 = self._create_transition(
                "t0", "ep_drift", 0, s0, s1_expected,
                TypedAction(action_type=ActionType.CLICK, target_node_id="btn_1"),
            )
            t1 = self._create_transition(
                "t1", "ep_drift", 1, s1_expected, s2_expected,
                TypedAction(action_type=ActionType.CLICK, target_node_id="btn_2"),
            )

            await journal.record_transition(t0)
            await journal.record_transition(t1)

            # Environment emits [s1_drifted, s2_expected]
            mock_obs = MockObservationPort([s1_drifted, s2_expected])
            mock_act = MockActionPort()

            runner = EpisodeReplayRunner(
                journal=journal,
                observation_port=mock_obs,
                action_port=mock_act,
                stop_on_drift=False,
            )

            report = await runner.replay_episode("ep_drift")

            # Assert Metrics
            self.assertEqual(report.total_steps, 2)
            self.assertEqual(report.matched_steps, 1)  # Step 0 drifted, Step 1 matched
            self.assertEqual(report.determinism_ratio, 0.5)
            self.assertFalse(report.is_fully_deterministic)

            # Step 0 Drift Inspection
            res0 = report.step_results[0]
            self.assertFalse(res0.is_deterministic_match)
            self.assertIsNotNone(res0.drift_details)
            self.assertIn("Hash mismatch", res0.drift_details or "")

            # Step 1 Pass Inspection
            res1 = report.step_results[1]
            self.assertTrue(res1.is_deterministic_match)
        finally:
            await journal.close()

    # =========================================================================
    # 3. Stop on Drift Flag
    # =========================================================================

    async def test_stop_on_drift_aborts_early(self) -> None:
        """Asserts stop_on_drift=True halts execution immediately upon first drift."""
        s0 = self._build_state({"a": "1"})
        s1_expected = self._build_state({"b": "2"})
        s2_expected = self._build_state({"c": "3"})
        s1_drifted = self._build_state({"b": "MISMATCH"})

        t0 = self._create_transition("t0", "ep_stop", 0, s0, s1_expected, TypedAction(action_type=ActionType.NOOP))
        t1 = self._create_transition("t1", "ep_stop", 1, s1_expected, s2_expected, TypedAction(action_type=ActionType.NOOP))

        mock_obs = MockObservationPort([s1_drifted, s2_expected])
        mock_act = MockActionPort()

        runner = EpisodeReplayRunner(
            observation_port=mock_obs,
            action_port=mock_act,
            stop_on_drift=True,
        )

        report = await runner.replay_transitions("ep_stop", [t0, t1])

        self.assertEqual(report.total_steps, 2)
        # Only 1 step attempted before halting
        self.assertEqual(len(report.step_results), 1)
        self.assertEqual(report.matched_steps, 0)
        self.assertEqual(report.determinism_ratio, 0.0)
        self.assertFalse(report.step_results[0].is_deterministic_match)

    # =========================================================================
    # 4. Parameter Binding Substitution
    # =========================================================================

    async def test_parameter_bindings_substitution(self) -> None:
        """Asserts parameterized template variables {{param}} and [param] are substituted in replayed actions."""
        s0 = self._build_state({"inp_query": ""})
        s1 = self._build_state({"inp_query": "Reflex Engine"})

        action_template = TypedAction(
            action_type=ActionType.TYPE,
            target_node_id="inp_query",
            text_payload="Search for {{search_term}} in [category]",
        )
        t0 = self._create_transition("t0", "ep_param", 0, s0, s1, action_template)

        mock_obs = MockObservationPort([s1])
        mock_act = MockActionPort()

        runner = EpisodeReplayRunner(
            observation_port=mock_obs,
            action_port=mock_act,
        )

        bindings = {"search_term": "Reflex Engine", "category": "docs"}
        report = await runner.replay_transitions("ep_param", [t0], parameter_bindings=bindings)

        self.assertEqual(report.matched_steps, 1)
        dispatched_action = mock_act.dispatched_actions[0][0]
        self.assertEqual(dispatched_action.text_payload, "Search for Reflex Engine in docs")

    # =========================================================================
    # 5. Empty Episode and Serialization Roundtrip
    # =========================================================================

    async def test_empty_episode_replay(self) -> None:
        """Asserts replaying an empty episode returns determinism_ratio 1.0 without error."""
        runner = EpisodeReplayRunner()
        report = await runner.replay_transitions("ep_empty", [])

        self.assertEqual(report.total_steps, 0)
        self.assertEqual(report.matched_steps, 0)
        self.assertEqual(report.determinism_ratio, 1.0)
        self.assertEqual(len(report.step_results), 0)

    def test_replay_report_serialization(self) -> None:
        """Asserts ReplayReport and ReplayStepResult roundtrip to and from dictionary."""
        step = ReplayStepResult(
            step_index=0,
            action_id="btn_1",
            expected_state_hash="hash_a",
            observed_state_hash="hash_a",
            is_deterministic_match=True,
            drift_details=None,
        )
        report = ReplayReport(
            episode_id="ep_ser",
            total_steps=1,
            matched_steps=1,
            determinism_ratio=1.0,
            step_results=[step],
        )

        d = report.to_dict()
        self.assertEqual(d["episode_id"], "ep_ser")
        self.assertEqual(d["determinism_ratio"], 1.0)
        self.assertTrue(d["is_fully_deterministic"])

        restored = ReplayReport.from_dict(d)
        self.assertEqual(restored.episode_id, report.episode_id)
        self.assertEqual(restored.total_steps, report.total_steps)
        self.assertEqual(restored.matched_steps, report.matched_steps)
        self.assertEqual(restored.determinism_ratio, report.determinism_ratio)
        self.assertEqual(len(restored.step_results), 1)
        self.assertEqual(restored.step_results[0].action_id, "btn_1")
        self.assertTrue(restored.step_results[0].is_deterministic_match)


if __name__ == "__main__":
    unittest.main()
